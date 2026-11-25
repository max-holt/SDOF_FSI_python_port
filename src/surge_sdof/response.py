"""Public API: peak response of the SDOF pipe proxy to a force history.

The two entry points take the force history and its sample rate, then keyword-only input
objects (public API session, R.9; ``docs/review/public_interface.md``)::

    peak_response(force_history, sample_rate, *, span, restraint, integration)
    peak_response_jc(force_history, sample_rate, *, span, restraint, fluid, integration,
                     coupling=CouplingModel())

``PipeSpan`` (span length, flexural rigidity, mass per length, celerity), ``Restraint``
(natural frequency, damping, friction, support gap, closed-gap frequency ratio), ``Fluid``
(fluid density, flow area) and ``Integration`` (substeps per sample, trace stride) are frozen
dataclasses in SI units (damping in %). Both return a ``PeakResponse``: the five maxima, the
free-decay sample count, the displacement, velocity and acceleration at the end of every
sample, and the ``Trace`` when one was asked for.

``peak_response`` reproduces ``GetPeakResponse`` (``legacy/vba/Existing Code.bas``
line 309) from the Stage 4 modules: ``structure`` (portal-frame proxy, SDOF kernel),
``loads`` (unbalance force schedule), with no fluid coupling. Set-up is done here per
solver; the sample loop, max trackers, the three response histories and the free-decay
phase live in one shared ``_integrate``. ``peak_response_jc`` reproduces
``GetPeakResponseJC`` (line 622): its own fluid-corrected set-up (``structure.jc_params``,
``moc.grid_size``, the short-pipe fallback to ``peak_response``) and the fluid column
``coupling.fluid_column`` builds, passed to the same loop; the two set-ups are not merged.

The junction-coupling model choices are one ``CouplingModel``, validated on construction
(D-25); ``VBA_COUPLING`` reproduces the workbook. Approved fixes F-1 and F-2 (NOTES.md):
``mean_velocity_divisor`` ("legacy": ``vAv`` divided by ``2N - 1``, D-17; "fixed": by the
``2N + 1`` terms summed) and ``parity`` ("per_phase": the VBA index
``k + (totInd - 1) * stepQTY`` with each phase's own ``k`` range, D-19; "running": one
running substep counter for the whole run, so the even/odd alternation never
double-steps a half-grid at a phase boundary). The parity flag reaches the compiled loop
as ``KernelSettings.is_per_phase_parity``; the loop adds ``_parity_offset`` (0 for the
running counter, fixed per sample for the VBA index) to its running ``substep_index`` and
passes whether the sum is even to ``moc.step`` as ``is_even_substep``.
``fraction_profile`` ("legacy": the VBA ``interpFractionA/B``, D-4; "fixed": the lead
author's corrected profiles, approved fix F-4) is passed to the coupling, which tabulates
the profile once (``moc.moving_fractions``).

Stage 5 (Numba): ``_integrate`` is the Python orchestrator and ``_integrate_kernel`` the
``numba.njit(cache=True)`` loop (no fastmath). The orchestrator concatenates the
``loads.unbalance_force`` per-sample lists once into a flat float64 array with int64
sample offsets, passes ``SdofParams`` whole and the fluid column (``moc.empty_column()``
for the lumped solver, its coupling flag off; ``coupling.fluid_column``'s, on), runs the
kernel and builds the ``PeakResponse``. The kernel takes floats, ints, bools and numpy
arrays only and calls ``structure.step_scalars`` and ``moc.step``, which Numba compiles
into it. With ``NUMBA_DISABLE_JIT=1`` the same source runs as Python (the unbalance value
and ``dF`` are cast with ``float`` so the state stays on Python floats as in Stage 4).

Session V.1 (trace): ``Integration.trace_every`` (default 0). With ``k > 0`` every
``k``-th substep is recorded into preallocated arrays the kernel takes (``trace.allocate_frames``)
and returned as ``PeakResponse.trace`` (a ``trace.Trace``); with ``0`` the kernel takes
empty arrays and the recording branch is never entered. The recording reads the state and
writes to the trace arrays only, so the ``PeakResponse`` values of a traced run are bitwise
those of the untraced run (``tests/test_trace.py``). ``loads.elbow_forces`` supplies the
per-substep elbow forces and the transit / forced boundary for the trace.

Differences from ``legacy_port.get_peak_response`` (all proved value-identical by
``tests/test_differential.py``, bitwise on the sweep and the golden inputs):

* Returns a ``PeakResponse`` dataclass. The three histories are 0-based (element ``t - 1``
  is the state at the end of sample ``t``); the VBA pad element 0 (D-16) is gone, and all
  three are recorded where the VBA's ``outputType`` returned one.
* The state is Python floats (see ``structure``). Overflow therefore no longer raises
  ``FloatingPointError`` mid-run as the numpy state did (D-14); nan/inf are absorbing in
  the update, so the final state is checked once and ``FloatingPointError`` raised then
  (D-23). ``mass = 0`` raises ``ZeroDivisionError`` instead of ``FloatingPointError``;
  a complex portal-frame height (``EI < 0``, D-12) raises ``TypeError`` at the set-up.
* Phase 3 computes ``0.0 - R`` where the VBA has ``-R``: identical except for the sign of
  an exact zero.

Differences of ``peak_response_jc`` from ``legacy_port.get_peak_response_jc`` (proved
value-identical with the legacy flags by ``tests/test_differential.py``): the same
return type and float state; ``rhoC = 0`` raises ``FloatingPointError`` once at the set-up
(Stage 5; the legacy raised it from numpy at the first MoC update) and an overflow in the
fluid raises ``FloatingPointError`` at the end of the run as D-23 (inside the compiled
kernel ``np.errstate`` does not apply; nan/inf propagate to the structure state), so
nothing is swallowed (D-9); a ``pivotSegQTY`` of 4 raises ``ZeroDivisionError`` at the
set-up (D-4) rather than in the first MoC update.
"""

from __future__ import annotations

import dataclasses
import math
import operator
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

import numba
import numpy as np

from surge_sdof import loads, moc, structure
from surge_sdof import trace as tracing
from surge_sdof.coupling import FluidConstants, fluid_column
from surge_sdof.structure import SdofParams, step_scalars
from surge_sdof.trace import (
    PHASE_FORCED,
    PHASE_FREE_DECAY,
    PHASE_TRANSIT,
    Trace,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import SupportsIndex

    from numpy.typing import ArrayLike
from surge_sdof.vba_compat import clng

__all__ = [
    "FIXED_COUPLING",
    "VBA_COUPLING",
    "CouplingModel",
    "Fluid",
    "Integration",
    "PeakResponse",
    "PipeSpan",
    "Restraint",
    "peak_response",
    "peak_response_jc",
]

# Free decay runs while ``x * xZero`` exceeds this, m² (VBA ``Do While x * xZero > 0.01``,
# lines 569 and 1109; ``xZero`` is ``x`` at the end of the forced phase, then 0 once the
# product falls to it, lines 593 and 1188). VBA quirk D-21 preserved: an absolute
# threshold, ``|x| > 0.1`` m at entry.
FREE_DECAY_THRESHOLD = 0.01


@dataclass(frozen=True)
class PipeSpan:
    """The span between the two elbows and the pipe it is made of.

    Attributes
    ----------
    span_length : float
        Length between the elbows, m.
    flexural_rigidity : float
        ``E * I`` of the pipe, N·m².
    mass_per_length : float
        Mass per unit length, pipe and contents, kg/m.
    celerity : float
        Pressure-wave speed in the pipe, m/s; also the speed at which the force travels
        from elbow A to elbow B.
    """

    span_length: float
    flexural_rigidity: float
    mass_per_length: float
    celerity: float


@dataclass(frozen=True)
class Restraint:
    """How the span is held: the dynamics of the SDOF proxy and its supports.

    Attributes
    ----------
    natural_frequency : float
        Natural frequency with the support gaps open, Hz (junction coupling: modelled
        with the fluid included).
    damping_percent : float
        Viscous damping as a percentage of critical, %.
    friction_coefficient : float
        Coulomb friction coefficient at the supports, dimensionless.
    support_gap : float, optional
        Gap at the supports, at the centre of mass, before the closed-gap stiffness acts,
        m (default 0).
    closed_gap_frequency_ratio : float, optional
        Natural frequency with the gaps closed over that with them open, dimensionless
        (default 1).
    """

    natural_frequency: float
    damping_percent: float
    friction_coefficient: float
    support_gap: float = 0
    closed_gap_frequency_ratio: float = 1


@dataclass(frozen=True)
class Fluid:
    """The fluid in the pipe, as the junction coupling sees it.

    Attributes
    ----------
    fluid_density : float
        Density, kg/m³.
    flow_area : float
        Internal cross-sectional area of the pipe (the pressure area), m².
    """

    fluid_density: float
    flow_area: float


@dataclass(frozen=True)
class Integration:
    """How a force history is integrated, and what is recorded.

    Attributes
    ----------
    substep_count : int
        Substeps per sample of the history; one substep is
        ``1 / (sample_rate * substep_count)`` s.
    trace_every : int, optional
        Substeps between recorded trace frames; 0 (default) records no trace.
    """

    substep_count: int
    trace_every: int = 0


PARITIES = ("running", "per_phase")
MEAN_VELOCITY_DIVISORS = ("fixed", "legacy")


@dataclass(frozen=True)
class CouplingModel:
    """The junction-coupling model choices: the approved fixes or the VBA behaviour.

    Validated on construction, so an unknown value raises before the solver runs, on every
    path (DEVIATIONS D-25).

    Attributes
    ----------
    mean_velocity_divisor : {"fixed", "legacy"}
        Divisor of the MoC mean-velocity sum: the number of terms ``2N + 1`` (approved fix
        F-1, default) or the VBA's ``2N - 1`` (D-17).
    parity : {"running", "per_phase"}
        MoC half-grid alternation: one running substep counter (approved fix F-2, default)
        or the VBA per-phase index, which can double-step a half-grid at a phase boundary
        (D-19).
    fraction_profile : {"fixed", "legacy"}
        The moving-fraction profiles: the lead author's corrected functions (approved fix
        F-4, default) or the VBA ``interpFractionA/B`` (D-4).

    Raises
    ------
    ValueError
        Any other value of a field.
    """

    mean_velocity_divisor: str = "fixed"
    parity: str = "running"
    fraction_profile: str = "fixed"

    def __post_init__(self) -> None:
        """Validate the three fields (``ValueError`` names the field and its values)."""
        if self.mean_velocity_divisor not in MEAN_VELOCITY_DIVISORS:
            raise ValueError(
                f"mean_velocity_divisor must be 'legacy' or 'fixed', "
                f"got {self.mean_velocity_divisor!r}"
            )
        if self.parity not in PARITIES:
            raise ValueError(f"parity must be 'per_phase' or 'running', got {self.parity!r}")
        if self.fraction_profile not in moc.FRACTION_PROFILES:
            raise ValueError(
                f"fraction_profile must be one of {moc.FRACTION_PROFILES}, "
                f"got {self.fraction_profile!r}"
            )


FIXED_COUPLING = CouplingModel()
"""The approved fixes F-1, F-2 and F-4b: the default of ``peak_response_jc``."""

VBA_COUPLING = CouplingModel("legacy", "per_phase", "legacy")
"""The VBA behaviour bitwise (D-4, D-17, D-19): the flags of the Excel acceptance runs."""


@dataclass(frozen=True)
class PeakResponse:
    """The peak response of a run and the state history it went through.

    The five maxima are the VBA ``resultArray(0 To 4)`` of ``outputType = 0``; the three
    histories are what ``outputType`` 1, 2 and 3 returned one at a time.

    Attributes
    ----------
    max_static_equivalent_force : float
        ``|effective_displacement(x_max)| * stiffness``, N (VBA line 611).
    max_displacement : float
        Largest ``|x|``, m.
    max_velocity : float
        Largest ``|v|``, m/s.
    max_acceleration : float
        Largest ``|a|``, m/s².
    max_unbalance_force : float
        Largest ``|forceA - forceB|`` of the forced phases, N (VBA ``FMax``).
    displacement_history, velocity_history, acceleration_history : numpy.ndarray
        float64, the displacement (m), velocity (m/s) and acceleration (m/s²) at the end of
        each sample, 0-based (element ``t - 1`` is sample ``t``), ``2 *
        nominal_forced_sample_count`` samples; free decay past them is integrated but not
        recorded, unfilled trailing elements are 0. The VBA pad element 0 (D-16) is not
        present.
    free_decay_sample_count : int
        Samples integrated in the free-decay phase (``Do While x * xZero > 0.01``, D-21).
    trace : trace.Trace or None
        The substep trace when ``Integration.trace_every > 0``; None otherwise.
    """

    max_static_equivalent_force: float
    max_displacement: float
    max_velocity: float
    max_acceleration: float
    max_unbalance_force: float
    # arrays take no part in ==, as in histories.History
    displacement_history: np.ndarray = dataclasses.field(repr=False, compare=False)
    velocity_history: np.ndarray = dataclasses.field(repr=False, compare=False)
    acceleration_history: np.ndarray = dataclasses.field(repr=False, compare=False)
    free_decay_sample_count: int
    trace: Trace | None = None

    def summary(self) -> np.ndarray:
        """The five maxima as the VBA ``resultArray(0 To 4)`` (N, m, m/s, m/s², N)."""
        return np.array(
            [
                self.max_static_equivalent_force,
                self.max_displacement,
                self.max_velocity,
                self.max_acceleration,
                self.max_unbalance_force,
            ]
        )


def peak_response(
    force_history: ArrayLike,
    sample_rate: float,
    *,
    span: PipeSpan,
    restraint: Restraint,
    integration: Integration,
) -> PeakResponse:
    """Peak response of the lumped SDOF proxy of a pipe span to an unbalance force history.

    The force history acts at elbow A at once and at elbow B after the transit delay
    ``span_length / celerity``; their difference drives the proxy through the transit and
    forced phases, then free decay. Units are SI throughout (the friction step fixes m and s
    through ``g = 9.81``).

    Parameters
    ----------
    force_history : array_like
        Force-time history at one elbow, N; 1-D, or 2-D walked column-major (D-10).
    sample_rate : float
        Samples per second of ``force_history``, Hz.
    span : PipeSpan
        Span length (m), flexural rigidity (N·m²), mass per length (kg/m) and celerity
        (m/s).
    restraint : Restraint
        Natural frequency (Hz), damping (% of critical), friction coefficient, support gap
        (m) and closed-gap frequency ratio.
    integration : Integration
        Substeps per sample and the trace stride (``trace_every`` 0: no trace; ``k > 0``:
        every ``k``-th substep into ``PeakResponse.trace``, the other results unchanged
        bitwise).

    Returns
    -------
    PeakResponse

    Raises
    ------
    ValueError
        ``trace_every < 0``, or a trace that would exceed ``trace.MAX_TRACE_VALUES``.
    ZeroDivisionError
        ``substep_count = 1`` (D-7) or a zero mass.
    IndexError
        A single-row 2-D history (D-8).
    TypeError
        A negative flexural rigidity or mass (complex portal-frame seed, D-12).
    FloatingPointError
        Overflow: at the free-decay test or once at the end of the run (D-23).

    Notes
    -----
    Reproduces ``GetPeakResponse`` (``legacy/vba/Existing Code.bas`` line 309);
    value-identical to ``legacy_port.get_peak_response`` (bitwise on the sweep and the
    golden inputs, ``tests/test_differential.py``). Preserved VBA quirks: the force ramp
    plateau D-18, the friction dead zone D-20 and the free-decay threshold D-21; the
    histories have no VBA pad element (D-16).
    """
    integration = _checked_integration(integration)
    sample_rate = float(sample_rate)
    span = _coerced_span(span)

    force_history_2d, nominal_forced_sample_count = _sample_grid(force_history, sample_rate, span)
    setup = solver_setup(sample_rate, span, restraint, integration)
    sdof_params = structure.lumped_params(
        span, restraint, setup.portal_frame_height, setup.substep_duration
    )
    unbalance_force_samples = loads.unbalance_force(
        force_history_2d, sample_rate, span.span_length, span.celerity, integration.substep_count
    )
    trace_request = _trace_request(
        "peak_response",
        {
            "force_history": force_history_2d,
            "sample_rate": sample_rate,
            "span": dataclasses.asdict(span),
            "restraint": dataclasses.asdict(restraint),
            "integration": dataclasses.asdict(integration),
        },
        span,
        integration,
        setup,
    )
    settings = KernelSettings(
        setup.substep_duration, integration.substep_count, nominal_forced_sample_count, False
    )
    return _integrate(
        unbalance_force_samples, sdof_params, settings, moc.empty_column(), trace_request
    )


def peak_response_jc(  # noqa: PLR0913 (7: sample rate beside the history; docs/style.md §11)
    force_history: ArrayLike,
    sample_rate: float,
    *,
    span: PipeSpan,
    restraint: Restraint,
    fluid: Fluid,
    integration: Integration,
    coupling: CouplingModel = FIXED_COUPLING,
) -> PeakResponse:
    """Peak response of the SDOF proxy with junction-coupling FSI: a 1-D MoC fluid column
    inside the span feeds the pressure-difference force at the elbows back to the structure.

    Parameters
    ----------
    force_history, sample_rate, span, restraint, integration
        As ``peak_response``; ``span.mass_per_length`` (kg/m) includes the fluid and
        ``restraint.natural_frequency`` (Hz) is modelled with the fluid mass included. A
        junction-coupling trace also carries the column and its grid (``Trace.column``, a
        ``trace.ColumnTrace``: ``grid_point_pressure``, ``grid_point_velocity``).
    fluid : Fluid
        Fluid density (kg/m³) and flow area (m²). The core fluid is removed from the rigid
        mass and the column inside the span feeds the junction force (N) back.
    coupling : CouplingModel, optional
        The model choices: the approved fixes (``FIXED_COUPLING``, default) or
        ``VBA_COUPLING``, the VBA
        behaviour bitwise.

    Returns
    -------
    PeakResponse
        Spans too short for the MoC grid (``moc.is_short_pipe``) return ``peak_response``
        with the same arguments, as the VBA does; the trace of such a call is a lumped one
        (``trace.solver == "peak_response"``).

    Raises
    ------
    ValueError
        ``trace_every < 0`` or a trace over ``trace.MAX_TRACE_VALUES``; an end-to-elbow
        cell count of 4 at the set-up with the fixed fraction profile (the ramp needs it
        above the inactive end cells).
    ZeroDivisionError
        ``substep_count = 1`` (D-7); an end-to-elbow cell count of 4 with the legacy
        fraction profile (D-4).
    IndexError
        A single-row 2-D history (D-8).
    TypeError
        A negative flexural rigidity (D-12).
    FloatingPointError
        A zero characteristic impedance ``fluid_density * celerity`` (checked once at the
        set-up) or an overflow in the fluid; nothing is swallowed where the VBA's
        ``On Error GoTo ErrFound`` returned an empty array (D-9).

    Notes
    -----
    Reproduces ``GetPeakResponseJC`` (``legacy/vba/Existing Code.bas`` line 622). With
    ``coupling=VBA_COUPLING`` the result is bitwise identical to
    ``legacy_port.get_peak_response_jc`` on the differential sweep. F-1/F-2 change the
    golden cases at rounding level (NOTES.md "Stage 4.2 — F-1/F-2 before/after"); F-4
    changes them by about 1e-3 relative and the fluid-coupled sweep cases by up to 3.6e-2
    (NOTES.md "Session F-4 — done"). The Excel acceptance test (``tests/test_golden.py``,
    the ``jc_slow`` cases) runs with ``VBA_COUPLING``. An unknown flag value raises when the
    ``CouplingModel`` is built, before any path of the solver (D-25).
    """
    integration = _checked_integration(integration)
    sample_rate = float(sample_rate)
    span = _coerced_span(span)
    fluid = Fluid(float(fluid.fluid_density), float(fluid.flow_area))

    force_history_2d, nominal_forced_sample_count = _sample_grid(force_history, sample_rate, span)
    setup = solver_setup(sample_rate, span, restraint, integration)
    # VBA order: mass, stiffness, damping, fricAcc (726-729), then the grid (731-734)
    sdof_params = structure.jc_params(
        span, restraint, fluid, setup.portal_frame_height, setup.substep_duration
    )
    end_pressure_decay_factor = moc.end_pressure_decay_factor(
        span.celerity, setup.substep_duration, span.span_length
    )
    grid = column_grid(setup, span)
    if moc.is_short_pipe(grid.column_cell_count, grid.end_to_elbow_cell_count):
        # insufficient length, use lumped mass (VBA 736-740)
        return peak_response(
            force_history, sample_rate, span=span, restraint=restraint, integration=integration
        )
    characteristic_impedance = fluid.fluid_density * span.celerity
    column = fluid_column(
        grid,
        FluidConstants(characteristic_impedance, fluid.flow_area, end_pressure_decay_factor),
        coupling.mean_velocity_divisor,
        coupling.fraction_profile,
    )
    unbalance_force_samples = loads.unbalance_force(
        force_history_2d, sample_rate, span.span_length, span.celerity, integration.substep_count
    )
    trace_request = _trace_request(
        "peak_response_jc",
        {
            "force_history": force_history_2d,
            "sample_rate": sample_rate,
            "span": dataclasses.asdict(span),
            "restraint": dataclasses.asdict(restraint),
            "fluid": dataclasses.asdict(fluid),
            "integration": dataclasses.asdict(integration),
            "coupling": dataclasses.asdict(coupling),
        },
        span,
        integration,
        setup,
    )
    settings = KernelSettings(
        setup.substep_duration,
        integration.substep_count,
        nominal_forced_sample_count,
        coupling.parity == "per_phase",
    )
    return _integrate(unbalance_force_samples, sdof_params, settings, column, trace_request)


def _coerced_span(span: PipeSpan) -> PipeSpan:
    """``span`` with every field a float, as the entry points have always converted them."""
    return PipeSpan(
        float(span.span_length),
        float(span.flexural_rigidity),
        float(span.mass_per_length),
        float(span.celerity),
    )


def _sample_grid(
    force_history: ArrayLike, sample_rate: float, span: PipeSpan
) -> tuple[np.ndarray, int]:
    """The force history as the walk reads it and the nominal forced sample count.

    Parameters
    ----------
    force_history : array_like
        Force history, N, 1-D or 2-D.
    sample_rate : float
        Its sample rate, Hz.
    span : PipeSpan
        Span length (m) and celerity (m/s) are read.

    Returns
    -------
    history_2d : numpy.ndarray
        float64, 2-D (``loads.as_history_2d``), N.
    nominal_forced_sample_count : int
        The history's samples plus the transit delay rounded as the VBA rounds it.

    Notes
    -----
    VBA ``outMax``, lines 377 and 714.
    """
    force_history_2d = loads.as_history_2d(force_history)
    transit_delay_samples = loads.transit_delay(span.span_length, span.celerity, sample_rate)
    nominal_forced_sample_count = force_history_2d.shape[0] * force_history_2d.shape[1] + clng(
        transit_delay_samples
    )
    return force_history_2d, nominal_forced_sample_count


def _trace_request(
    solver: str, inputs: dict, span: PipeSpan, integration: Integration, setup: SolverSetup
) -> tracing.TraceRequest | None:
    """What ``_integrate`` needs to build a ``Trace``.

    Parameters
    ----------
    solver : {"peak_response", "peak_response_jc"}
        The solver's name in the trace (the entry point's name).
    inputs : dict
        The echo of the entry point's inputs; its 2-D force history (N) and sample rate
        (Hz) are what the elbow forces are walked from.
    span : PipeSpan
        Span length (m) and celerity (m/s) are read.
    integration : Integration
        The substep count and the trace stride are read.
    setup : SolverSetup
        The portal-frame height (m) is read.

    Returns
    -------
    trace.TraceRequest or None
        None when ``integration.trace_every`` is 0; otherwise the stride, the solver name,
        the inputs, the celerity, the portal-frame height and the per-sample elbow forces
        of ``loads.elbow_forces`` (a lazy generator).
    """
    if not integration.trace_every:
        return None
    return tracing.TraceRequest(
        integration.trace_every,
        solver,
        inputs,
        span.celerity,
        setup.portal_frame_height,
        loads.elbow_forces(
            inputs["force_history"],
            inputs["sample_rate"],
            span.span_length,
            span.celerity,
            integration.substep_count,
        ),
    )


def _checked_integration(integration: Integration) -> Integration:
    """``integration`` with the substep count an int and the trace stride checked
    (``_trace_stride``)."""
    return Integration(int(integration.substep_count), _trace_stride(integration.trace_every))


def _trace_stride(trace_every: SupportsIndex) -> int:
    """``trace_every`` as a non-negative int (``operator.index``: no silent truncation;
    ``ValueError`` when negative)."""
    trace_every = operator.index(trace_every)
    if trace_every < 0:
        raise ValueError(f"trace_every must be >= 0, got {trace_every}")
    return trace_every


class SolverSetup(NamedTuple):
    """The set-up both solvers derive from their inputs before the run: the substep and the
    portal-frame height. Returned by ``solver_setup``; the tools and the loop geometry ask it
    too, so the solver's set-up is written once.

    Attributes
    ----------
    substep_duration : float
        One substep, ``1 / (sample_rate * substep_count)``, s.
    portal_frame_height : float
        Leg height of the portal-frame proxy (``structure.solve_portal_height``), m.
    """

    substep_duration: float
    portal_frame_height: float


def solver_setup(
    sample_rate: float, span: PipeSpan, restraint: Restraint, integration: Integration
) -> SolverSetup:
    """The substep and the portal-frame height of a run, as the solver entry points form
    them (VBA lines 377-387 and 714-724).

    Parameters
    ----------
    sample_rate : float
        Samples per second of the force history, Hz.
    span : PipeSpan
        Span length (m), flexural rigidity (N·m²) and mass per length (kg/m) are read.
    restraint : Restraint
        The natural frequency (Hz) is read.
    integration : Integration
        The substep count is read.

    Returns
    -------
    SolverSetup
    """
    substep_duration = 1 / (sample_rate * integration.substep_count)
    portal_frame_height = structure.solve_portal_height(
        span.span_length, span.flexural_rigidity, span.mass_per_length, restraint.natural_frequency
    )
    return SolverSetup(substep_duration, portal_frame_height)


def column_grid(setup: SolverSetup, span: PipeSpan) -> moc.ColumnGrid:
    """The MoC grid of the junction-coupling solver for ``setup`` (``moc.grid_size``); a short
    pipe (``moc.is_short_pipe``) makes the solver fall back to the lumped one.

    Parameters
    ----------
    setup : SolverSetup
        From ``solver_setup``.
    span : PipeSpan
        Span length (m) and celerity (m/s) are read.

    Returns
    -------
    moc.ColumnGrid
    """
    return moc.grid_size(
        span.span_length, setup.portal_frame_height, span.celerity, setup.substep_duration
    )


class KernelSettings(NamedTuple):
    """The settings the compiled sample loop reads, built by the solver entry points (not the
    user-facing ``Integration``).

    Attributes
    ----------
    substep_duration : float
        One substep, ``1 / (sample_rate * substep_count)``, s.
    substep_count : int
        Substeps per sample (VBA ``stepQTY``).
    nominal_forced_sample_count : int
        History samples plus the rounded transit delay (VBA ``outMax``); the response
        histories and the trace keep twice this many samples.
    is_per_phase_parity : bool
        The VBA per-phase MoC parity index (``parity="per_phase"``, D-19) in place of the
        running substep counter; always False for the lumped solver.
    """

    substep_duration: float
    substep_count: int
    nominal_forced_sample_count: int
    is_per_phase_parity: bool


class _ForceSchedule(NamedTuple):
    """The forces of the transit and forced phases, one value per substep, as the kernel
    reads them. Built by ``_integrate`` from the ``loads`` generators.

    Attributes
    ----------
    unbalance_force_by_substep : numpy.ndarray
        float64, shape ``(substeps,)``: the unbalance force per forced substep, N; sample
        ``s`` is
        ``unbalance_force_by_substep[sample_start[s]:sample_start[s + 1]]`` (the truncated
        last transit sample keeps its length).
    sample_start : numpy.ndarray
        int64, shape ``(samples + 1,)``: where each sample's substeps start.
    elbow_a_force_by_substep, elbow_b_force_by_substep : numpy.ndarray
        float64, the elbow forces laid out the same way, N (traced runs only; empty
        otherwise).
    transit_substep_count : int
        Substeps of the transit phase (0 when not tracing): the boundary between the
        transit and forced phases the trace records.
    """

    unbalance_force_by_substep: np.ndarray
    sample_start: np.ndarray
    elbow_a_force_by_substep: np.ndarray
    elbow_b_force_by_substep: np.ndarray
    transit_substep_count: int


class _KernelResult(NamedTuple):
    """What the compiled sample loop returns.

    Attributes
    ----------
    x_max, v_max, a_max : float
        Largest ``abs(x)``, ``abs(v)``, ``abs(a)`` of the run: m, m/s, m/s².
    unbalance_force_max : float
        Largest ``abs()`` of the unbalance force over the forced phases, N (VBA ``FMax``).
    x, v, a : float
        State at the end of the run.
    sample_number : int
        Samples integrated, free decay included (VBA ``totInd``).
    forced_sample_count : int
        Samples of the transit and forced phases.
    frame_count : int
        Trace frames written.
    """

    x_max: float
    v_max: float
    a_max: float
    unbalance_force_max: float
    x: float
    v: float
    a: float
    sample_number: int
    forced_sample_count: int
    frame_count: int


@numba.njit(cache=True)
def _free_decay_product(x: float, x_zero: float) -> float:
    """The product of the displacement and the free-decay reference displacement (m²), the
    free-decay test; ``FloatingPointError`` when it overflows.

    Notes
    -----
    VBA ``x * xZero``; VBA raises error 6 if the product overflows (the numpy state of the
    legacy port did the same), so this does too (D-23).
    """
    free_decay_product = x * x_zero
    if free_decay_product == math.inf:
        raise FloatingPointError("x * xZero overflowed (VBA error 6)")  # D-23
    return free_decay_product


@numba.njit(cache=True)
def _is_frame_due(
    trace_every: int,
    substep_index: int,
    frame_count: int,
    frame_capacity: int,
    is_in_record_window: bool,
) -> bool:
    """Whether substep ``substep_index`` is recorded as a trace frame: tracing is on, the
    index is a multiple of the stride, the frame capacity lasts and the sample lies in the
    recorded window (always, in the transit and forced phases). Scalars only."""
    return (
        trace_every > 0
        and substep_index % trace_every == 0
        and frame_count < frame_capacity
        and is_in_record_window
    )


@numba.njit(cache=True)
def _parity_offset(
    is_per_phase_parity: bool,
    sample_number: int,
    substep_count: int,
    substep_index: int,
    first_substep_number: int,
) -> int:
    """What the kernel adds to the running ``substep_index`` to get the MoC parity index,
    fixed for one sample, at the sample's first substep.

    0 for the running counter (F-2). With the VBA per-phase index (D-19) the parity index
    is ``k + (totInd - 1) * stepQTY`` with the VBA's ``k`` starting at
    ``first_substep_number`` in each sample (0 in the transit and forced phases, 1 in free
    decay); ``sample_number`` is ``totInd``. Integers only.
    """
    if not is_per_phase_parity:
        return 0
    return (sample_number - 1) * substep_count + first_substep_number - substep_index


@numba.njit(cache=True)
def _largest_magnitude(values: np.ndarray) -> float:
    """The largest ``abs()`` of ``values``, from 0.0, as a running maximum over them in
    order (a NaN never wins the comparison). Called once per run (``docs/style.md`` §4)."""
    largest = 0.0
    for value in values:
        magnitude = abs(float(value))
        if magnitude > largest:
            largest = magnitude
    return largest


@numba.njit(cache=True)
def _decay_reference(x: float, x_zero: float) -> float:
    """The free-decay reference displacement (m) after a free-decay substep: unchanged
    while ``x * x_zero`` still exceeds ``FREE_DECAY_THRESHOLD``, 0.0 once it does not, which
    ends free decay at the end of the sample. The product is checked for overflow
    (``_free_decay_product``, D-23).

    Notes
    -----
    VBA ``xZero``, lines 593 and 1188.
    """
    if _free_decay_product(x, x_zero) <= FREE_DECAY_THRESHOLD:
        return 0.0
    return x_zero


class ResponseHistories(NamedTuple):
    """The state at the end of each sample, the three arrays of one run (float64, each of
    ``2 * nominal_forced_sample_count`` samples; unfilled trailing samples are 0).

    Attributes
    ----------
    displacement : numpy.ndarray
        m.
    velocity : numpy.ndarray
        m/s.
    acceleration : numpy.ndarray
        m/s².
    """

    displacement: np.ndarray
    velocity: np.ndarray
    acceleration: np.ndarray


@numba.njit(cache=True)
def _record_sample(histories: ResponseHistories, index: int, x: float, v: float, a: float) -> None:
    """Store the end-of-sample state, ``x`` (m), ``v`` (m/s), ``a`` (m/s²), at ``index``
    of the three ``histories`` (what the VBA ``Select Case outputType`` stores after each
    sample, for every output type at once)."""
    histories.displacement[index] = x
    histories.velocity[index] = v
    histories.acceleration[index] = a


class _RunState(NamedTuple):
    """What one SDOF substep changes: the state, the running maxima and the substep count.

    Passed into ``_structure_substep`` and returned by it (``docs/style.md`` §4: scalars
    that evolve are passed in and returned; a per-substep function takes scalars only).
    """

    x: float  # m
    v: float  # m/s
    a: float  # m/s²
    x_max: float  # largest |x| so far, m
    v_max: float  # largest |v| so far, m/s
    a_max: float  # largest |a| so far, m/s²
    substep_index: int  # running 0-based substep counter: the next substep's index


@numba.njit(cache=True)
def _structure_substep(
    state: _RunState, applied_force: float, sdof_params: SdofParams, dt: float
) -> _RunState:
    """Step the structure one substep under ``applied_force`` (N), update the running
    maxima of ``|a|``, ``|v|``, ``|x|`` and count the substep.

    ``step_scalars`` advances ``x``, ``v``, ``a`` over ``dt`` (s); the maxima are raised in
    the order ``a``, ``v``, ``x``. Scalars in, scalars out (``docs/style.md`` §4).
    """
    x, v, a = step_scalars(state.x, state.v, state.a, applied_force, sdof_params, dt)
    x_max = state.x_max
    v_max = state.v_max
    a_max = state.a_max
    if abs(a) > a_max:
        a_max = abs(a)
    if abs(v) > v_max:
        v_max = abs(v)
    if abs(x) > x_max:
        x_max = abs(x)
    return _RunState(x, v, a, x_max, v_max, a_max, state.substep_index + 1)


class _FrameLoads(NamedTuple):
    """What the loop knows about the substep it records: its index, sample, load phase
    and forces (N)."""

    substep_index: int  # running 0-based substep counter
    sample_index: int  # 0-based sample index
    load_phase: int  # PHASE_TRANSIT, PHASE_FORCED or PHASE_FREE_DECAY
    elbow_a_force: float
    elbow_b_force: float
    unbalance_force: float
    junction_force: float  # 0.0 without fluid coupling


class _FrameInputs(NamedTuple):
    """What every recorded frame reads besides the substep; built once per kernel call."""

    sdof_params: SdofParams
    substep_duration: float  # s
    column: moc.FluidColumn


@numba.njit(cache=True)
def _record_frame(
    buffers: tracing.TraceBuffers,
    frame_index: int,
    loads: _FrameLoads,
    before: _RunState,
    after: _RunState,
    inputs: _FrameInputs,
) -> int:
    """Record one substep as a trace frame.

    Called on recorded substeps only; reads the solver state only.

    Parameters
    ----------
    buffers : trace.TraceBuffers
        Written in place.
    frame_index : int
        The frame to write.
    loads : _FrameLoads
        The substep's index, sample, load phase and elbow forces (N).
    before, after : _RunState
        The state before and after the substep (m, m/s, m/s²).
    inputs : _FrameInputs
        What every frame reads besides the substep.

    Returns
    -------
    int
        The frame count after this frame.

    Notes
    -----
    The row (``loads``, the state ``after``, the friction force and stick flag of
    ``structure.substep_friction`` from ``before`` and ``after``) is written by
    ``trace.write_frame_row``; with fluid coupling, the column by
    ``trace.write_frame_column``.
    """
    friction_force, is_sticking = structure.substep_friction(
        inputs.sdof_params, before.v, before.a, after.v, after.a, inputs.substep_duration
    )
    tracing.write_frame_row(
        buffers,
        frame_index,
        tracing.FrameRow(
            loads.substep_index,
            loads.sample_index,
            loads.load_phase,
            after.x,
            after.v,
            after.a,
            loads.elbow_a_force,
            loads.elbow_b_force,
            loads.unbalance_force,
            friction_force,
            is_sticking,
            loads.junction_force,
        ),
    )
    if inputs.column.is_fluid_coupled:
        tracing.write_frame_column(buffers, frame_index, inputs.column)
    return frame_index + 1


def _integrate(
    unbalance_force_samples: Iterable[list[float]],
    sdof_params: SdofParams,
    settings: KernelSettings,
    column: moc.FluidColumn,
    trace_request: tracing.TraceRequest | None,
) -> PeakResponse:
    """Integrate the SDOF proxy through the transit and forced phases and free decay: the
    sample loop shared by both peak solvers.

    The transit and forced phases are driven by ``unbalance_force_samples``, then free
    decay runs while ``x * x_zero > FREE_DECAY_THRESHOLD``; the maxima and the per-sample
    histories are kept. The Python orchestrator of ``_integrate_kernel``, in three steps:
    prepare the kernel's inputs (``_kernel_inputs``), run the kernel, and build the
    ``PeakResponse`` (``_peak_response``; the trace by ``trace.build_trace``).

    Parameters
    ----------
    unbalance_force_samples : iterable of list of float
        ``loads.unbalance_force``: one list of per-substep unbalance forces (N) per sample.
    sdof_params : structure.SdofParams
        The proxy's constants.
    settings : KernelSettings
        Substep (s), substeps per sample, nominal forced sample count, parity source.
    column : moc.FluidColumn
        ``moc.empty_column()`` (no fluid coupling) or ``coupling.fluid_column``'s, whose
        arrays are updated in place.
    trace_request : trace.TraceRequest or None
        What a trace needs, or None for an untraced run.

    Returns
    -------
    PeakResponse

    Notes
    -----
    The VBA sample loop (``GetPeakResponse`` / ``GetPeakResponseJC``). The MoC parity index
    is the running substep counter ``substep_index`` (0 at the first substep), or with
    ``settings.is_per_phase_parity`` the VBA per-phase index ``k + (totInd - 1) * stepQTY``
    (phase 3: ``k = 1 .. stepQTY``), written as ``substep_index + parity_offset`` with
    ``parity_offset`` (``_parity_offset``) fixed per sample (D-19, approved fix F-2). The kernel is the Stage 5 compiled loop."""
    schedule, histories, buffers = _kernel_inputs(
        unbalance_force_samples, settings, column, trace_request
    )
    result = _integrate_kernel(
        schedule,
        sdof_params,
        settings,
        histories,
        column,
        buffers,
    )

    if not (math.isfinite(result.x) and math.isfinite(result.v) and math.isfinite(result.a)):
        raise FloatingPointError("SDOF state is not finite (VBA error 6: overflow)")  # D-23

    trace = None
    if trace_request is not None:
        trace = tracing.build_trace(trace_request, settings, sdof_params, buffers, result, column)
    return _peak_response(result, sdof_params, histories, trace)


def _kernel_inputs(
    unbalance_force_samples: Iterable[list[float]],
    settings: KernelSettings,
    column: moc.FluidColumn,
    trace_request: tracing.TraceRequest | None,
) -> tuple[_ForceSchedule, ResponseHistories, tracing.TraceBuffers]:
    """The kernel's inputs: the force schedule, the zeroed histories and the trace buffers.

    Parameters
    ----------
    unbalance_force_samples : iterable of list of float
        As ``_integrate``; consumed here.
    settings : KernelSettings
        The nominal forced sample count and the substep count are read.
    column : moc.FluidColumn
        Its cell count sizes the trace's column buffers.
    trace_request : trace.TraceRequest or None
        With a request, its elbow forces are flattened and the buffers sized.

    Returns
    -------
    schedule : _ForceSchedule
        ``unbalance_force_samples`` flattened by ``loads.flatten_unbalance_force`` and,
        with a ``trace_request``, the elbow forces of ``trace_request.elbow_force_samples``
        by ``loads.flatten_elbow_forces``, whose sample starts must agree.
    histories : ResponseHistories
        Zeroed, ``nominal_forced_sample_count * 2`` samples each.
    buffers : trace.TraceBuffers
        Sized by ``trace.check_memory`` and allocated by ``trace.allocate_frames``; without
        a request, a stride of 0 and empty buffers."""
    substep_count = settings.substep_count
    nominal_forced_sample_count = settings.nominal_forced_sample_count
    unbalance_force_by_substep, sample_start = loads.flatten_unbalance_force(
        unbalance_force_samples
    )
    # Proposed derivation, for Ben to confirm: the recorded history holds out_max * 2 samples,
    # the forced samples and an equal allowance for free decay; later free decay is integrated
    # but not recorded.
    recorded_sample_count = nominal_forced_sample_count * 2
    histories = ResponseHistories(
        np.zeros(recorded_sample_count),
        np.zeros(recorded_sample_count),
        np.zeros(recorded_sample_count),
    )

    # ----------------------------------------------------------------- trace set-up
    grid_point_count = 2 * column.column_cell_count + 1 if column.is_fluid_coupled else 0
    transit_substep_count = 0
    trace_every = 0 if trace_request is None else trace_request.stride
    if trace_request is not None:
        (
            elbow_a_force_by_substep,
            elbow_b_force_by_substep,
            elbow_sample_start,
            transit_substep_count,
        ) = loads.flatten_elbow_forces(trace_request.elbow_force_samples)
        if not np.array_equal(elbow_sample_start, sample_start):
            raise AssertionError("elbow_forces and unbalance_force disagree on the samples")
        forced_substep_count = int(sample_start[-1])
        frame_capacity = tracing.check_memory(
            forced_substep_count,
            len(sample_start) - 1,
            int(nominal_forced_sample_count),
            int(substep_count),
            trace_every,
            grid_point_count,
        )
    else:
        elbow_a_force_by_substep = elbow_b_force_by_substep = np.zeros(0)
        frame_capacity = 0
    buffers = tracing.allocate_frames(frame_capacity, grid_point_count, int(trace_every))
    schedule = _ForceSchedule(
        unbalance_force_by_substep,
        sample_start,
        elbow_a_force_by_substep,
        elbow_b_force_by_substep,
        int(transit_substep_count),
    )
    return schedule, histories, buffers


def _peak_response(
    result: _KernelResult,
    sdof_params: SdofParams,
    histories: ResponseHistories,
    trace: Trace | None,
) -> PeakResponse:
    """The ``PeakResponse`` of a finished run: the kernel's maxima as Python floats, the
    static-equivalent force (N) from the largest displacement, the three histories, the
    free-decay sample count and the ``trace`` (None for an untraced run)."""
    # VBA line 611: Abs(minUnsigned(gap, xMax) + max(0, |xMax| - gap) * ...) * stiffness
    static_equivalent_force_max = (
        abs(
            structure.effective_displacement(
                result.x_max, sdof_params.support_gap, sdof_params.closed_gap_stiffness_ratio
            )
        )
        * sdof_params.stiffness
    )
    return PeakResponse(
        max_static_equivalent_force=float(static_equivalent_force_max),
        max_displacement=float(result.x_max),
        max_velocity=float(result.v_max),
        max_acceleration=float(result.a_max),
        max_unbalance_force=float(result.unbalance_force_max),
        displacement_history=histories.displacement,
        velocity_history=histories.velocity,
        acceleration_history=histories.acceleration,
        free_decay_sample_count=int(result.sample_number - result.forced_sample_count),
        trace=trace,
    )


@numba.njit(cache=True)
def _integrate_kernel(  # noqa: PLR0915 (the substep sequence stays visible; docs/style.md §11)
    schedule: _ForceSchedule,
    sdof_params: SdofParams,
    settings: KernelSettings,
    histories: ResponseHistories,
    column: moc.FluidColumn,
    buffers: tracing.TraceBuffers,
) -> _KernelResult:
    """The compiled sample loop of ``_integrate``: for each sample, for each substep,
    advance the column and the structure; then free decay until the decay product test
    fails.

    ``schedule.unbalance_force_by_substep[sample_start[s]:sample_start[s + 1]]`` holds
    sample ``s``'s per-substep unbalance values. Each substep: with
    ``column.is_fluid_coupled`` the MoC column is advanced (``moc.step`` on the half-grid
    selected by the parity of ``substep_index + parity_offset``) and returns the junction
    force, from 0.0; the loop forms the applied force (forced phases ``junction_force +
    unbalance_force`` or ``0.0 + unbalance_force``, free decay ``junction_force`` or
    ``0.0``); ``_structure_substep`` steps the structure, raises the maxima and counts the
    substep. Returns a ``_KernelResult``; the three ``histories`` are filled
    in place.

    Trace: a substep ``_is_frame_due`` says is due (stride, capacity, and in
    free decay ``sample_number <= nominal_forced_sample_count * 2``) is written by
    ``_record_frame`` after the SDOF update, with the elbow forces of the schedule in the
    forced phases (``transit_substep_count`` is the transit -> forced boundary) and the
    friction force and stick flag of ``structure.substep_friction``. With ``trace_every ==
    0`` no frame is due and the buffers are empty.

    Parameters
    ----------
    schedule : _ForceSchedule
        The per-substep forces of the transit and forced phases, N.
    sdof_params : structure.SdofParams
        The proxy's constants.
    settings : KernelSettings
        Substep (s), substeps per sample, nominal forced sample count, parity source.
    histories : ResponseHistories
        Filled in place.
    column : moc.FluidColumn
        Advanced in place when fluid coupling is on.
    buffers : trace.TraceBuffers
        Written in place on recorded substeps.

    Returns
    -------
    _KernelResult

    Notes
    -----
    The Stage 5 kernel (``numba.njit(cache=True)``); the trace frames were added in
    session V.1. The junction force is VBA ``dF``.
    """
    unbalance_force_by_substep = schedule.unbalance_force_by_substep
    sample_start = schedule.sample_start
    elbow_a_force_by_substep = schedule.elbow_a_force_by_substep
    elbow_b_force_by_substep = schedule.elbow_b_force_by_substep
    transit_substep_count = schedule.transit_substep_count
    dt = settings.substep_duration
    substep_count = settings.substep_count
    nominal_forced_sample_count = settings.nominal_forced_sample_count
    is_per_phase_parity = settings.is_per_phase_parity
    is_fluid_coupled = column.is_fluid_coupled
    junction_force = 0.0  # N; stays 0.0 without fluid coupling
    state = _RunState(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0)  # at rest, before the first substep
    frame_inputs = _FrameInputs(sdof_params, dt, column)
    sample_number = 0
    forced_sample_count = sample_start.shape[0] - 1
    # trace (Session V.1)
    frame_count = 0
    trace_every = buffers.trace_every
    frame_capacity = buffers.frame_index_columns.shape[0]

    # ------------------------------------------------- transit and forced phases
    for s in range(forced_sample_count):
        sample_number += 1
        parity_offset = _parity_offset(
            is_per_phase_parity, sample_number, substep_count, state.substep_index, 0
        )
        for i in range(sample_start[s], sample_start[s + 1]):
            unbalance_force = float(unbalance_force_by_substep[i])
            substep_index = state.substep_index
            record_frame = _is_frame_due(
                trace_every, substep_index, frame_count, frame_capacity, True
            )
            before = state
            if is_fluid_coupled:
                junction_force = float(
                    moc.step(
                        (substep_index + parity_offset) % 2 == 0,
                        state.a * dt,
                        column,
                        junction_force,
                    )
                )
                applied_force = junction_force + unbalance_force
            else:
                applied_force = 0.0 + unbalance_force
            state = _structure_substep(state, applied_force, sdof_params, dt)
            if record_frame:
                frame_count = _record_frame(
                    buffers,
                    frame_count,
                    _FrameLoads(
                        substep_index,
                        sample_number - 1,
                        PHASE_TRANSIT if substep_index < transit_substep_count else PHASE_FORCED,
                        elbow_a_force_by_substep[i],
                        elbow_b_force_by_substep[i],
                        unbalance_force,
                        junction_force,
                    ),
                    before,
                    state,
                    frame_inputs,
                )
        _record_sample(histories, sample_number - 1, state.x, state.v, state.a)
    unbalance_force_max = _largest_magnitude(unbalance_force_by_substep)

    # ---------------------------------------------------------- free decay
    forced_samples = sample_number
    decay_start_displacement = state.x
    while _free_decay_product(state.x, decay_start_displacement) > FREE_DECAY_THRESHOLD:
        sample_number += 1
        parity_offset = _parity_offset(
            is_per_phase_parity, sample_number, substep_count, state.substep_index, 1
        )
        # Proposed derivation, for Ben to confirm: the recorded history holds out_max * 2 samples,
        # the forced samples and an equal allowance for free decay; later free decay is integrated
        # but not recorded.
        is_in_record_window = sample_number <= nominal_forced_sample_count * 2
        for _k in range(substep_count):
            substep_index = state.substep_index
            record_frame = _is_frame_due(
                trace_every, substep_index, frame_count, frame_capacity, is_in_record_window
            )
            before = state
            if is_fluid_coupled:
                junction_force = float(
                    moc.step(
                        (substep_index + parity_offset) % 2 == 0,
                        state.a * dt,
                        column,
                        junction_force,
                    )
                )
                applied_force = junction_force
            else:
                applied_force = 0.0
            state = _structure_substep(state, applied_force, sdof_params, dt)
            if record_frame:
                frame_count = _record_frame(
                    buffers,
                    frame_count,
                    _FrameLoads(
                        substep_index,
                        sample_number - 1,
                        PHASE_FREE_DECAY,
                        0.0,
                        0.0,
                        0.0,
                        junction_force,
                    ),
                    before,
                    state,
                    frame_inputs,
                )
            decay_start_displacement = _decay_reference(state.x, decay_start_displacement)
        if is_in_record_window:
            _record_sample(histories, sample_number - 1, state.x, state.v, state.a)

    return _KernelResult(
        state.x_max,
        state.v_max,
        state.a_max,
        unbalance_force_max,
        state.x,
        state.v,
        state.a,
        sample_number,
        forced_samples,
        frame_count,
    )
