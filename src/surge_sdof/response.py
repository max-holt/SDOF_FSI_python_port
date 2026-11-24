"""Public API: peak response of the SDOF pipe proxy to a force history.

``peak_response`` reproduces ``GetPeakResponse`` (``legacy/vba/Existing Code.bas``
line 309) from the Stage 4 modules: ``structure`` (portal-frame proxy, SDOF kernel),
``loads`` (unbalance force schedule), with no fluid coupling. Set-up is done here per
solver; the sample loop, max trackers, result history, free-decay phase and
output-type switch live in one shared ``_integrate``. ``peak_response_jc`` reproduces
``GetPeakResponseJC`` (line 622): its own fluid-corrected set-up (``structure.jc_params``,
``moc.grid_size``, the short-pipe fallback to ``peak_response``) and the
``JunctionCoupling`` passed to the same loop; the two set-ups are not merged.

Approved fixes F-1 and F-2 (NOTES.md) are keyword flags of ``peak_response_jc``:
``vav_denominator`` ("legacy": ``vAv`` divided by ``2N - 1``, D-17; "fixed": by the
``2N + 1`` terms summed) and ``parity`` ("per_phase": the VBA index
``k + (totInd - 1) * stepQTY`` with each phase's own ``k`` range, D-19; "running": one
running sub-step counter for the whole run, so the even/odd alternation never
double-steps a half-grid at a phase boundary). The parity flag is applied by
``_integrate``, which passes the chosen index as ``step_index`` to the coupling.
``fraction_profile`` ("legacy": the VBA ``interpFractionA/B``, D-4; "fixed": the lead
author's corrected profiles, approved fix F-4) is passed to the coupling, which tabulates
the profile once (``moc.moving_fractions``).

Stage 5 (Numba): ``_integrate`` is the Python orchestrator and ``_integrate_kernel`` the
``numba.njit(cache=True)`` loop (no fastmath). The orchestrator concatenates the
``loads.unbalance_force`` per-sample lists once into a flat float64 array with int64
sample offsets, passes ``SdofParams`` whole and the fluid column (``moc.empty_column()``
for the lumped solver, its coupling flag off; the ``JunctionCoupling``'s column, on), runs
the kernel,
writes ``dF`` back to the coupling and builds the ``PeakResponse``. The kernel takes floats, ints, bools and numpy
arrays only and calls ``structure.step_scalars`` and ``moc.step``, which Numba compiles
into it. With ``NUMBA_DISABLE_JIT=1`` the same source runs as Python (the unbalance value
and ``dF`` are cast with ``float`` so the state stays on Python floats as in Stage 4).

Session V.1 (trace): both solvers take ``trace_every: int = 0``. With ``k > 0`` every
``k``-th sub-step is recorded into preallocated arrays the kernel takes (``trace.allocate_frames``)
and returned as ``PeakResponse.trace`` (a ``trace.Trace``); with ``0`` the kernel takes
empty arrays and the recording branch is never entered. The recording reads the state and
writes to the trace arrays only, so the ``PeakResponse`` values of a traced run are bitwise
those of the untraced run (``tests/test_trace.py``). ``loads.elbow_forces`` supplies the
per-sub-step elbow forces and the transit / forced boundary for the trace.

Differences from ``legacy_port.get_peak_response`` (all proved value-identical by
``tests/test_differential.py``, bitwise on the sweep and the golden inputs):

* Returns a ``PeakResponse`` dataclass. ``history`` is 0-based (element ``t - 1`` is
  the state at the end of sample ``t``); the VBA pad element 0 (D-16) is gone.
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

import itertools
import math
import operator
from dataclasses import dataclass
from typing import NamedTuple

import numba
import numpy as np

from surge_sdof import loads, moc, structure
from surge_sdof import trace as tracing
from surge_sdof.coupling import FluidConstants, JunctionCoupling
from surge_sdof.structure import SdofParams, step_scalars
from surge_sdof.trace import (
    COL_A,
    COL_ELBOW_A_FORCE,
    COL_ELBOW_B_FORCE,
    COL_FRICTION_FORCE,
    COL_IS_STICKING,
    COL_JUNCTION_FORCE,
    COL_LOAD_PHASE,
    COL_SAMPLE_INDEX,
    COL_SUBSTEP_INDEX,
    COL_UNBALANCE_FORCE,
    COL_V,
    COL_X,
    PHASE_FORCED,
    PHASE_FREE_DECAY,
    PHASE_TRANSIT,
    Trace,
)
from surge_sdof.vba_compat import clng

__all__ = ["PeakResponse", "peak_response", "peak_response_jc"]

# Free decay runs while ``x * xZero`` exceeds this, m² (VBA ``Do While x * xZero > 0.01``,
# lines 569 and 1109; ``xZero`` is ``x`` at the end of the forced phase, then 0 once the
# product falls to it, lines 593 and 1188). VBA quirk D-21 preserved: an absolute
# threshold, ``|x| > 0.1`` m at entry.
FREE_DECAY_THRESHOLD = 0.01


@dataclass(frozen=True)
class PeakResponse:
    """Result of ``peak_response`` / ``peak_response_jc``.

    The five maxima are the VBA ``resultArray(0 To 4)`` of ``outputType = 0``.

    Attributes
    ----------
    max_static_equivalent_force : float
        ``|effective_displacement(xMax)| * stiffness``, N (VBA line 611).
    max_displacement : float
        ``xMax``, m.
    max_velocity : float
        ``vMax``, m/s.
    max_acceleration : float
        ``aMax``, m/s².
    max_applied_force : float
        ``FMax``, the largest ``|forceA - forceB|``, N.
    history : numpy.ndarray or None
        For ``output_type`` 1 / 2 / 3 the displacement (m) / velocity (m/s) /
        acceleration (m/s²) at the end of each sample, 0-based, length ``outMax * 2``
        (element ``t - 1`` is sample ``t``; unfilled trailing elements are 0). None for
        ``output_type = 0``. The VBA pad element 0 (D-16) is not present.
    output_type : int
        The requested output type.
    free_decay_samples : int
        Samples integrated in the free-decay phase (``Do While x * xZero > 0.01``, D-21).
    trace : trace.Trace or None
        The sub-step trace when the solver was called with ``trace_every > 0``
        (Session V.1); None otherwise.
    """

    max_static_equivalent_force: float
    max_displacement: float
    max_velocity: float
    max_acceleration: float
    max_applied_force: float
    history: np.ndarray | None
    """``output_type`` 1/2/3: displacement/velocity/acceleration at the end of each
    sample, length ``outMax * 2`` (unfilled trailing elements 0); None for 0."""
    output_type: int
    free_decay_samples: int
    """Samples integrated in the free-decay phase (``Do While x * xZero > 0.01``)."""
    trace: Trace | None = None
    """``trace.Trace`` of the run when ``trace_every > 0``, else None (Session V.1)."""

    def summary(self) -> np.ndarray:
        """The five maxima as the VBA ``resultArray(0 To 4)`` (N, m, m/s, m/s², N)."""
        return np.array(
            [
                self.max_static_equivalent_force,
                self.max_displacement,
                self.max_velocity,
                self.max_acceleration,
                self.max_applied_force,
            ]
        )


def peak_response(
    force_history,
    step_qty: int,
    sample_freq: float,
    physical_length: float,
    flexural_rigidity_ei: float,
    celerity: float,
    mass_per_unit_len: float,
    damping_percent: float,
    dynamic_fric: float,
    nat_freq: float,
    restrain_freq_ratio: float = 1,
    gap: float = 0,
    output_type: int = 0,
    trace_every: int = 0,
) -> PeakResponse:
    """Peak response of the lumped SDOF proxy to a force history (``GetPeakResponse``).

    Units are consistent SI (the VBA states "consistent units except ``dynamicFric``",
    whose ``9.81`` fixes m and s).

    Parameters
    ----------
    force_history : array_like
        Force-time history at one location, N; 1-D, or 2-D walked column-major (D-10).
    step_qty : int
        Sub-steps per sample.
    sample_freq : float
        Sample rate of the history, Hz.
    physical_length : float
        Length between elbows, m.
    flexural_rigidity_ei : float
        ``E * I``, N·m².
    celerity : float
        Propagation speed of the force along the pipe, m/s.
    mass_per_unit_len : float
        Mass per unit length, kg/m.
    damping_percent : float
        Damping as a percentage of critical, %.
    dynamic_fric : float
        Coulomb friction coefficient, dimensionless.
    nat_freq : float
        Natural frequency with the gaps open, Hz.
    restrain_freq_ratio : float, optional
        Natural frequency with the gaps closed over that with them open, dimensionless
        (default 1).
    gap : float, optional
        Support gap at the centre of mass, m (default 0).
    output_type : int, optional
        0: the five maxima only; 1 / 2 / 3: also the displacement / velocity /
        acceleration history (default 0).
    trace_every : int, optional
        0 (default): no trace. ``k > 0``: record every ``k``-th sub-step into
        ``PeakResponse.trace`` (``trace.Trace``; Session V.1). The maxima and the history
        are the same bitwise either way.

    Returns
    -------
    PeakResponse

    Raises
    ------
    ValueError
        ``trace_every < 0``, or a trace that would exceed ``trace.MAX_TRACE_VALUES``.
    ZeroDivisionError
        ``step_qty = 1`` (D-7) or ``mass = 0``.
    IndexError
        A single-row 2-D history (D-8).
    TypeError
        ``EI < 0`` or ``L * massPerUnitLen < 0`` (complex portal-frame seed, D-12).
    FloatingPointError
        Overflow: at the free-decay test or once at the end of the run (D-23).

    Notes
    -----
    Value-identical to ``legacy_port.get_peak_response`` (bitwise on the sweep and the
    golden inputs, ``tests/test_differential.py``). Preserved VBA quirks: the force ramp
    plateau D-18, the friction dead zone D-20 and the free-decay threshold D-21; the
    history has no VBA pad element (D-16).
    """
    step_qty = int(step_qty)
    sample_freq = float(sample_freq)
    physical_length = float(physical_length)
    flexural_rigidity_ei = float(flexural_rigidity_ei)
    celerity = float(celerity)
    mass_per_unit_len = float(mass_per_unit_len)
    output_type = int(output_type)
    trace_every = _trace_stride(trace_every)

    force_history_2d = loads.as_history_2d(force_history)
    transit_delay_samples = loads.transit_delay(physical_length, celerity, sample_freq)
    # VBA line 377 (outMax)
    nominal_forced_sample_count = force_history_2d.shape[0] * force_history_2d.shape[1] + clng(
        transit_delay_samples
    )
    substep_duration = 1 / (sample_freq * step_qty)

    portal_frame_height = structure.solve_portal_height(
        physical_length, flexural_rigidity_ei, mass_per_unit_len, nat_freq
    )
    sdof_params = structure.lumped_params(
        physical_length,
        portal_frame_height,
        mass_per_unit_len,
        damping_percent,
        dynamic_fric,
        nat_freq,
        substep_duration,
        gap,
        restrain_freq_ratio,
    )
    unbalance_force_samples = loads.unbalance_force(
        force_history_2d, sample_freq, physical_length, celerity, step_qty
    )
    trace_request = None
    if trace_every:
        trace_request = tracing.TraceRequest(
            trace_every,
            "peak_response",
            {
                "force_history": force_history_2d,
                "step_qty": step_qty,
                "sample_freq": sample_freq,
                "physical_length": physical_length,
                "flexural_rigidity_ei": flexural_rigidity_ei,
                "celerity": celerity,
                "mass_per_unit_len": mass_per_unit_len,
                "damping_percent": damping_percent,
                "dynamic_fric": dynamic_fric,
                "nat_freq": nat_freq,
                "restrain_freq_ratio": restrain_freq_ratio,
                "gap": gap,
                "output_type": output_type,
            },
            celerity,
            loads.elbow_forces(force_history_2d, sample_freq, physical_length, celerity, step_qty),
        )
    settings = RunSettings(
        substep_duration, step_qty, nominal_forced_sample_count, output_type, False
    )
    return _integrate(unbalance_force_samples, sdof_params, settings, None, trace_request)


def peak_response_jc(
    force_history,
    step_qty: int,
    sample_freq: float,
    physical_length: float,
    flexural_rigidity_ei: float,
    celerity: float,
    mass_per_unit_len: float,
    fluid_densty: float,
    fluid_area: float,
    damping_percent: float,
    dynamic_fric: float,
    nat_freq: float,
    restrain_freq_ratio: float = 1,
    gap: float = 0,
    output_type: int = 0,
    trace_every: int = 0,
    *,
    vav_denominator: str = "fixed",
    parity: str = "running",
    fraction_profile: str = "fixed",
) -> PeakResponse:
    """Peak response with junction-coupling FSI (``GetPeakResponseJC``).

    Parameters
    ----------
    force_history, step_qty, sample_freq, physical_length, flexural_rigidity_ei, celerity, mass_per_unit_len, damping_percent, dynamic_fric, nat_freq, restrain_freq_ratio, gap, output_type
        As ``peak_response``; ``mass_per_unit_len`` (kg/m) includes the fluid and
        ``nat_freq`` (Hz) is modelled with the fluid mass included.
    fluid_densty : float
        Fluid density, kg/m³ (VBA spelling kept).
    fluid_area : float
        Internal cross-sectional (pressure) area of the pipe, m². The core fluid is
        removed from the rigid mass and a 1-D MoC column inside the span feeds the
        pressure-difference force ``dF`` (N) back.
    trace_every : int, optional
        As ``peak_response``; a JC trace also carries the column (``p_cells``,
        ``v_cells``) and the grid geometry. The short-pipe fallback passes it on, so the
        trace of such a call is a lumped one (``trace.solver == "peak_response"``).
    vav_denominator : {"fixed", "legacy"}, keyword-only
        Divisor of the MoC mean-velocity sum: the number of terms ``2N + 1`` (approved
        fix F-1, default) or the VBA's ``2N - 1`` (D-17).
    parity : {"running", "per_phase"}, keyword-only
        MoC half-grid alternation: one running sub-step counter for the whole run
        (approved fix F-2, default) or the VBA per-phase index ``k + (totInd - 1) *
        stepQTY`` that can double-step a half-grid at a phase boundary (D-19).
    fraction_profile : {"fixed", "legacy"}, keyword-only
        The moving-fraction profiles weighting the mass acceleration along the column:
        the lead author's corrected functions (approved fix F-4, default,
        ``legacy/vba/interpFraction_fix_2026-10-26.bas``) or the VBA ``interpFractionA/B``
        (D-4).

    Returns
    -------
    PeakResponse
        Spans too short for the MoC grid (``moc.is_short_pipe``) return
        ``peak_response`` with the same arguments, as the VBA does (lines 736-740).

    Raises
    ------
    ValueError
        Unknown ``parity`` or ``fraction_profile`` (checked at the entry); unknown
        ``vav_denominator``, but only where the MoC column is built: a short pipe returns
        ``peak_response`` and ``rhoC = 0`` raises ``FloatingPointError`` before that check
        (validation at the entry is planned for the public API session); ``trace_every <
        0`` or a trace over ``trace.MAX_TRACE_VALUES``; ``pivotSegQTY = 4`` at the set-up
        with the fixed fraction profile (the ramp needs ``pivot > ext``).
    ZeroDivisionError
        ``step_qty = 1`` (D-7); ``pivotSegQTY = 4`` at the set-up with the legacy fraction
        profile (D-4).
    IndexError
        A single-row 2-D history (D-8).
    TypeError
        ``EI < 0`` (D-12).
    FloatingPointError
        ``rhoC = 0`` (checked once at the set-up, Stage 5) or an overflow in the fluid;
        nothing is swallowed where the VBA's ``On Error GoTo ErrFound`` returned an empty
        array (D-9).

    Notes
    -----
    With ``vav_denominator="legacy", parity="per_phase", fraction_profile="legacy"`` the
    result is bitwise identical to ``legacy_port.get_peak_response_jc`` on the differential
    sweep. F-1/F-2 change the golden cases at rounding level (NOTES.md "Stage 4.2 — F-1/F-2
    before/after"); F-4 changes them by about 1e-3 relative and the fluid-coupled sweep
    cases by up to 3.6e-2 (NOTES.md "Session F-4 — done"). The Excel acceptance test
    (``tests/test_golden.py``, the ``jc_slow`` cases) runs with the legacy flags.
    """
    if parity not in ("per_phase", "running"):
        raise ValueError(f"parity must be 'per_phase' or 'running', got {parity!r}")
    if fraction_profile not in moc.FRACTION_PROFILES:
        raise ValueError(
            f"fraction_profile must be one of {moc.FRACTION_PROFILES}, got {fraction_profile!r}"
        )
    step_qty = int(step_qty)
    sample_freq = float(sample_freq)
    physical_length = float(physical_length)
    flexural_rigidity_ei = float(flexural_rigidity_ei)
    celerity = float(celerity)
    mass_per_unit_len = float(mass_per_unit_len)
    fluid_densty = float(fluid_densty)
    fluid_area = float(fluid_area)
    output_type = int(output_type)
    trace_every = _trace_stride(trace_every)

    force_history_2d = loads.as_history_2d(force_history)
    transit_delay_samples = loads.transit_delay(physical_length, celerity, sample_freq)
    # VBA line 714 (outMax)
    nominal_forced_sample_count = force_history_2d.shape[0] * force_history_2d.shape[1] + clng(
        transit_delay_samples
    )
    substep_duration = 1 / (sample_freq * step_qty)

    portal_frame_height = structure.solve_portal_height(
        physical_length, flexural_rigidity_ei, mass_per_unit_len, nat_freq
    )
    # VBA order: mass, stiffness, damping, fricAcc (726-729), then the grid (731-734)
    sdof_params = structure.jc_params(
        physical_length,
        portal_frame_height,
        mass_per_unit_len,
        fluid_densty,
        fluid_area,
        damping_percent,
        dynamic_fric,
        nat_freq,
        substep_duration,
        gap,
        restrain_freq_ratio,
    )
    end_pressure_decay_factor = moc.end_pressure_decay_factor(
        celerity, substep_duration, physical_length
    )
    grid = moc.grid_size(physical_length, portal_frame_height, celerity, substep_duration)
    if moc.is_short_pipe(grid.column_cell_count, grid.end_to_elbow_cell_count):
        # insufficient length, use lumped mass (VBA 736-740)
        return peak_response(
            force_history,
            step_qty,
            sample_freq,
            physical_length,
            flexural_rigidity_ei,
            celerity,
            mass_per_unit_len,
            damping_percent,
            dynamic_fric,
            nat_freq,
            restrain_freq_ratio,
            gap,
            output_type,
            trace_every,
        )
    characteristic_impedance = fluid_densty * celerity
    junction_coupling = JunctionCoupling(
        grid,
        substep_duration,
        FluidConstants(characteristic_impedance, fluid_area, end_pressure_decay_factor),
        vav_denominator,
        fraction_profile,
    )
    unbalance_force_samples = loads.unbalance_force(
        force_history_2d, sample_freq, physical_length, celerity, step_qty
    )
    trace_request = None
    if trace_every:
        trace_request = tracing.TraceRequest(
            trace_every,
            "peak_response_jc",
            {
                "force_history": force_history_2d,
                "step_qty": step_qty,
                "sample_freq": sample_freq,
                "physical_length": physical_length,
                "flexural_rigidity_ei": flexural_rigidity_ei,
                "celerity": celerity,
                "mass_per_unit_len": mass_per_unit_len,
                "fluid_densty": fluid_densty,
                "fluid_area": fluid_area,
                "damping_percent": damping_percent,
                "dynamic_fric": dynamic_fric,
                "nat_freq": nat_freq,
                "restrain_freq_ratio": restrain_freq_ratio,
                "gap": gap,
                "output_type": output_type,
                "vav_denominator": vav_denominator,
                "parity": parity,
                "fraction_profile": fraction_profile,
            },
            celerity,
            loads.elbow_forces(force_history_2d, sample_freq, physical_length, celerity, step_qty),
        )
    settings = RunSettings(
        substep_duration,
        step_qty,
        nominal_forced_sample_count,
        output_type,
        parity == "per_phase",
    )
    return _integrate(
        unbalance_force_samples, sdof_params, settings, junction_coupling, trace_request
    )


def _trace_stride(trace_every) -> int:
    """``trace_every`` as a non-negative int (``operator.index``: no silent truncation)."""
    trace_every = operator.index(trace_every)
    if trace_every < 0:
        raise ValueError(f"trace_every must be >= 0, got {trace_every}")
    return trace_every


class RunSettings(NamedTuple):
    """The settings of one run of the sample loop, built by the solver entry points.

    Attributes
    ----------
    substep_duration : float
        One sub-step, ``1 / (sample_freq * step_qty)``, s.
    substep_count : int
        Sub-steps per sample (VBA ``stepQTY``).
    nominal_forced_sample_count : int
        History samples plus the rounded transit delay (VBA ``outMax``); the response
        history and the trace keep twice this many samples.
    output_type : int
        0 (peaks only) or 1 / 2 / 3 (the history of ``x`` / ``v`` / ``a``).
    is_per_phase_parity : bool
        The VBA per-phase MoC parity index (``parity="per_phase"``, D-19) in place of the
        running sub-step counter; always False for the lumped solver.
    """

    substep_duration: float
    substep_count: int
    nominal_forced_sample_count: int
    output_type: int
    is_per_phase_parity: bool


class _ForceSchedule(NamedTuple):
    """The forces of the transit and forced phases, one value per sub-step, as the kernel
    reads them. Built by ``_integrate`` from the ``loads`` generators.

    Attributes
    ----------
    unbalance_force_by_substep : numpy.ndarray
        float64, ``forceA - forceB`` per forced sub-step, N; sample ``s`` is
        ``unbalance_force_by_substep[sample_start[s]:sample_start[s + 1]]`` (the truncated
        last transit sample keeps its length).
    sample_start : numpy.ndarray
        int64, samples + 1: where each sample's sub-steps start.
    elbow_a_force_by_substep, elbow_b_force_by_substep : numpy.ndarray
        float64, the elbow forces laid out the same way, N (traced runs only; empty
        otherwise).
    transit_substep_count : int
        Sub-steps of the transit phase (0 when not tracing): the boundary between the
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
        Largest ``abs(forceA - forceB)`` of the forced phases, N (VBA ``FMax``).
    x, v, a : float
        State at the end of the run.
    sample_number : int
        Samples integrated, free decay included (VBA ``totInd``).
    forced_sample_count : int
        Samples of the transit and forced phases.
    junction_force : float
        The junction force after the last sub-step, N (0.0 without fluid coupling).
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
    junction_force: float
    frame_count: int


@numba.njit(cache=True)
def _free_decay_product(x: float, x_zero: float) -> float:
    """``x * xZero`` of the free-decay test; VBA raises error 6 if the product
    overflows (the numpy state of the legacy port did the same), so this does too."""
    free_decay_product = x * x_zero
    if free_decay_product == math.inf:
        raise FloatingPointError("x * xZero overflowed (VBA error 6)")  # D-23
    return free_decay_product


@numba.njit(cache=True)
def _record_sample(
    history: np.ndarray, output_type: int, index: int, x: float, v: float, a: float
) -> None:
    """Store the end-of-sample state in ``history[index]``: ``x`` for ``output_type`` 1,
    ``v`` for 2, ``a`` for 3 (the VBA ``Select Case outputType`` after each sample)."""
    if output_type == 1:
        history[index] = x
    elif output_type == 2:
        history[index] = v
    elif output_type == 3:
        history[index] = a


class _Frame(NamedTuple):
    """One recorded sub-step: the values ``_trace_frame`` writes into a frame row.

    Built by the kernel only on a traced sub-step, from the expressions it has always
    passed. Units: forces in N, ``x`` / ``v`` / ``a`` in m, m/s, m/s².
    """

    substep_index: int  # running 0-based sub-step counter
    sample_index: int  # 0-based sample index
    load_phase: int  # PHASE_TRANSIT, PHASE_FORCED or PHASE_FREE_DECAY
    x: float
    v: float
    a: float
    elbow_a_force: float
    elbow_b_force: float
    unbalance_force: float
    friction_force: float  # recomputed from the velocity change, as the trace defines it
    is_sticking: bool  # |v before the sub-step| < the friction velocity step
    junction_force: float  # 0.0 without fluid coupling


@numba.njit(cache=True)
def _trace_frame(
    buffers: tracing.TraceBuffers,
    frame_index: int,
    values: _Frame,
    column: moc.FluidColumn,
) -> None:
    """Write one trace frame (Session V.1): the scalars of ``values`` into row
    ``frame_index`` of ``buffers.frame_state`` / ``buffers.frame_index_columns`` (columns
    ``trace.COL_*``) and, with fluid coupling, the column interleaved ``A0 B0 A1 ... A(N)``
    into ``buffers.frame_pressure`` / ``buffers.frame_velocity``. Reads only; the solver
    state is untouched."""
    frame_state = buffers.frame_state
    frame_index_columns = buffers.frame_index_columns
    frame_pressure = buffers.frame_pressure
    frame_velocity = buffers.frame_velocity
    substep_index = values.substep_index
    sample_index = values.sample_index
    load_phase = values.load_phase
    x = values.x
    v = values.v
    a = values.a
    elbow_a_force = values.elbow_a_force
    elbow_b_force = values.elbow_b_force
    unbalance_force = values.unbalance_force
    friction_force = values.friction_force
    is_sticking = values.is_sticking
    junction_force = values.junction_force
    is_fluid_coupled = column.is_fluid_coupled
    pressure_a = column.pressure_a
    velocity_a = column.velocity_a
    pressure_b = column.pressure_b
    velocity_b = column.velocity_b
    column_cell_count = column.column_cell_count
    frame_state[frame_index, COL_X] = x
    frame_state[frame_index, COL_V] = v
    frame_state[frame_index, COL_A] = a
    frame_state[frame_index, COL_ELBOW_A_FORCE] = elbow_a_force
    frame_state[frame_index, COL_ELBOW_B_FORCE] = elbow_b_force
    frame_state[frame_index, COL_UNBALANCE_FORCE] = unbalance_force
    frame_state[frame_index, COL_FRICTION_FORCE] = friction_force
    frame_state[frame_index, COL_JUNCTION_FORCE] = junction_force
    frame_index_columns[frame_index, COL_SUBSTEP_INDEX] = substep_index
    frame_index_columns[frame_index, COL_SAMPLE_INDEX] = sample_index
    frame_index_columns[frame_index, COL_LOAD_PHASE] = load_phase
    frame_index_columns[frame_index, COL_IS_STICKING] = 1 if is_sticking else 0
    if is_fluid_coupled:
        for c in range(column_cell_count):
            frame_pressure[frame_index, 2 * c] = pressure_a[c]
            frame_pressure[frame_index, 2 * c + 1] = pressure_b[c]
            frame_velocity[frame_index, 2 * c] = velocity_a[c]
            frame_velocity[frame_index, 2 * c + 1] = velocity_b[c]
        frame_pressure[frame_index, 2 * column_cell_count] = pressure_a[column_cell_count]
        frame_velocity[frame_index, 2 * column_cell_count] = velocity_a[column_cell_count]


def _integrate(
    unbalance_force_samples,
    sdof_params: SdofParams,
    settings: RunSettings,
    junction_coupling: JunctionCoupling | None,
    trace_request: tracing.TraceRequest | None,
) -> PeakResponse:
    """The VBA sample loop shared by both peak solvers: the transit and forced phases
    driven by ``unbalance_force_samples`` (one list of per-sub-step unbalance values per
    sample), then free decay while ``x * xZero > 0.01``; max trackers; result history per
    sample.

    Python orchestrator of ``_integrate_kernel`` (Stage 5): flattens
    ``unbalance_force_samples`` once, passes ``sdof_params`` and the fluid column of
    ``junction_coupling`` (``None``: ``moc.empty_column()``, no fluid coupling; a
    ``JunctionCoupling``: its column, whose arrays are updated in place, and its ``d_f``,
    written back), builds the ``PeakResponse``.

    ``step_index`` the kernel uses for the MoC parity is the running sub-step counter
    ``n`` (0 at the first sub-step), or with ``settings.is_per_phase_parity`` the VBA
    per-phase index ``k + (totInd - 1) * stepQTY`` (phase 3: ``k = 1 .. stepQTY``), written
    as ``n + off`` with ``off`` fixed per sample (D-19, approved fix F-2).

    Session V.1: with a ``trace_request`` (its ``stride`` > 0) the elbow forces of
    ``trace_request.elbow_force_samples`` are flattened like ``unbalance_force_samples``,
    the trace arrays are allocated (``trace.check_memory``, ``trace.allocate_frames``) and
    the kernel fills them; ``trace.build_trace`` makes the ``Trace``. Without one the kernel
    takes a stride of 0 and empty arrays."""
    substep_count = settings.substep_count
    nominal_forced_sample_count = settings.nominal_forced_sample_count
    output_type = settings.output_type
    unbalance_force_samples = list(unbalance_force_samples)
    offsets = np.zeros(len(unbalance_force_samples) + 1, dtype=np.int64)
    for i, sample in enumerate(unbalance_force_samples):
        offsets[i + 1] = offsets[i] + len(sample)
    flat = np.fromiter(
        itertools.chain.from_iterable(unbalance_force_samples),
        dtype=np.float64,
        count=int(offsets[-1]),
    )
    # Proposed derivation, for Ben to confirm: the recorded history holds out_max * 2 samples,
    # the forced samples and an equal allowance for free decay; later free decay is integrated
    # but not recorded.
    response_history = np.zeros(nominal_forced_sample_count * 2 if output_type > 0 else 0)

    # ----------------------------------------------------------------- trace set-up
    grid_point_count = (
        2 * junction_coupling.column.column_cell_count + 1 if junction_coupling is not None else 0
    )
    delay_substeps = 0
    trace_every = 0 if trace_request is None else trace_request.stride
    if trace_request is not None:
        elbow_force_samples = list(trace_request.elbow_force_samples)
        if [len(fa) for _ph, fa, _fb in elbow_force_samples] != [
            len(s) for s in unbalance_force_samples
        ]:
            raise AssertionError("elbow_forces and unbalance_force disagree on the samples")
        forced_substep_count = int(offsets[-1])
        flat_a = np.fromiter(
            itertools.chain.from_iterable(fa for _ph, fa, _fb in elbow_force_samples),
            np.float64,
            count=forced_substep_count,
        )
        flat_b = np.fromiter(
            itertools.chain.from_iterable(fb for _ph, _fa, fb in elbow_force_samples),
            np.float64,
            count=forced_substep_count,
        )
        delay_substeps = sum(len(fa) for ph, fa, _fb in elbow_force_samples if ph == PHASE_TRANSIT)
        frame_capacity = tracing.check_memory(
            forced_substep_count,
            len(unbalance_force_samples),
            int(nominal_forced_sample_count),
            int(substep_count),
            trace_every,
            grid_point_count,
        )
    else:
        flat_a = flat_b = np.zeros(0)
        frame_capacity = 0
    buffers = tracing.allocate_frames(frame_capacity, grid_point_count, int(trace_every))
    schedule = _ForceSchedule(flat, offsets, flat_a, flat_b, int(delay_substeps))
    if junction_coupling is not None:
        column = junction_coupling.column
        junction_force = junction_coupling.d_f
    else:
        column = moc.empty_column()
        junction_force = 0.0

    result = _integrate_kernel(
        schedule,
        sdof_params,
        settings,
        response_history,
        column,
        junction_force,
        buffers,
    )
    if junction_coupling is not None:
        junction_coupling.d_f = float(result.junction_force)

    if not (math.isfinite(result.x) and math.isfinite(result.v) and math.isfinite(result.a)):
        raise FloatingPointError("SDOF state is not finite (VBA error 6: overflow)")  # D-23

    # VBA line 611: Abs(minUnsigned(gap, xMax) + max(0, |xMax| - gap) * ...) * stiffness
    static_equivalent_force_max = (
        abs(
            structure.effective_displacement(
                result.x_max, sdof_params.support_gap, sdof_params.closed_gap_stiffness_ratio
            )
        )
        * sdof_params.stiffness
    )
    trace = None
    if trace_request is not None:
        trace = tracing.build_trace(
            trace_request, settings, sdof_params, buffers, int(result.frame_count), column
        )
    return PeakResponse(
        max_static_equivalent_force=float(static_equivalent_force_max),
        max_displacement=float(result.x_max),
        max_velocity=float(result.v_max),
        max_acceleration=float(result.a_max),
        max_applied_force=float(result.unbalance_force_max),
        history=response_history if output_type > 0 else None,
        output_type=output_type,
        free_decay_samples=int(result.sample_number - result.forced_sample_count),
        trace=trace,
    )


@numba.njit(cache=True)
def _integrate_kernel(
    schedule: _ForceSchedule,
    sdof_params: SdofParams,
    settings: RunSettings,
    response_history: np.ndarray,
    column: moc.FluidColumn,
    junction_force: float,
    buffers: tracing.TraceBuffers,
) -> _KernelResult:
    """The sample loop of ``_integrate`` (the Stage 5 kernel).

    ``schedule.unbalance_force_by_substep[sample_start[s]:sample_start[s + 1]]`` holds
    sample ``s``'s per-sub-step unbalance values. With ``column.is_fluid_coupled`` the MoC
    column is advanced (``moc.step`` on the half-grid selected by the parity of
    ``substep_index + parity_offset``) before each SDOF sub-step and ``dF`` added; without,
    ``0.0`` is added (no fluid coupling). Returns a ``_KernelResult``;
    ``response_history`` is filled in place for ``output_type`` 1-3.

    Trace (Session V.1): with ``buffers.trace_every > 0`` every sub-step whose running
    index ``substep_index`` is a multiple of it, while ``sample_number <=
    nominal_forced_sample_count * 2`` and the capacity lasts, is written by
    ``_trace_frame`` after the SDOF update (the elbow forces per forced sub-step come from
    the schedule, ``transit_substep_count`` is the transit -> forced boundary). The friction
    force is ``mass * (v_new - (v_before + (a_before + a_new) * half_dt)) / dt`` with the
    same ``half_dt = dt / 2`` as ``step_scalars``; the stick flag is ``|v_before| <
    friction_velocity_step``. With ``trace_every == 0`` the branch is never entered and the
    buffers are empty.
    """
    unbalance_force_by_substep = schedule.unbalance_force_by_substep
    sample_start = schedule.sample_start
    elbow_a_force_by_substep = schedule.elbow_a_force_by_substep
    elbow_b_force_by_substep = schedule.elbow_b_force_by_substep
    transit_substep_count = schedule.transit_substep_count
    dt = settings.substep_duration
    substep_count = settings.substep_count
    nominal_forced_sample_count = settings.nominal_forced_sample_count
    output_type = settings.output_type
    is_per_phase_parity = settings.is_per_phase_parity
    mass = sdof_params.mass
    friction_velocity_step = sdof_params.friction_velocity_step
    is_fluid_coupled = column.is_fluid_coupled
    x = 0.0
    v = 0.0
    a = 0.0
    x_max = 0.0
    v_max = 0.0
    a_max = 0.0
    unbalance_force_max = 0.0
    substep_index = 0  # running sub-step counter
    parity_offset = 0  # the MoC parity index is substep_index + parity_offset
    sample_number = 0
    forced_sample_count = sample_start.shape[0] - 1
    # trace (Session V.1)
    frame_count = 0
    trace_every = buffers.trace_every
    frame_capacity = buffers.frame_index_columns.shape[0]
    half_dt = dt / 2
    v_before = 0.0
    a_before = 0.0

    # ------------------------------------------------- transit and forced phases
    for s in range(forced_sample_count):
        sample_number += 1
        if is_per_phase_parity:
            parity_offset = (sample_number - 1) * substep_count - substep_index
        for i in range(sample_start[s], sample_start[s + 1]):
            unbalance_force = float(unbalance_force_by_substep[i])
            record_frame = (
                trace_every > 0
                and substep_index % trace_every == 0
                and frame_count < frame_capacity
            )
            if record_frame:
                v_before = v
                a_before = a
            if is_fluid_coupled:
                junction_force = float(
                    moc.step(
                        (substep_index + parity_offset) % 2 == 0,
                        a * dt,
                        column,
                        junction_force,
                    )
                )
                applied_force = junction_force + unbalance_force
            else:
                applied_force = 0.0 + unbalance_force
            x, v, a = step_scalars(x, v, a, applied_force, sdof_params, dt)
            if record_frame:
                _trace_frame(
                    buffers,
                    frame_count,
                    _Frame(
                        substep_index,
                        sample_number - 1,
                        PHASE_TRANSIT if substep_index < transit_substep_count else PHASE_FORCED,
                        x,
                        v,
                        a,
                        elbow_a_force_by_substep[i],
                        elbow_b_force_by_substep[i],
                        unbalance_force,
                        mass * (v - (v_before + (a_before + a) * half_dt)) / dt,
                        abs(v_before) < friction_velocity_step,
                        junction_force if is_fluid_coupled else 0.0,
                    ),
                    column,
                )
                frame_count += 1
            substep_index += 1
            if abs(a) > a_max:
                a_max = abs(a)
            if abs(v) > v_max:
                v_max = abs(v)
            if abs(x) > x_max:
                x_max = abs(x)
            if abs(unbalance_force) > unbalance_force_max:
                unbalance_force_max = abs(unbalance_force)
        if output_type > 0:
            _record_sample(response_history, output_type, sample_number - 1, x, v, a)

    # ---------------------------------------------------------- free decay
    forced_samples = sample_number
    decay_start_displacement = x
    while _free_decay_product(x, decay_start_displacement) > FREE_DECAY_THRESHOLD:
        sample_number += 1
        if is_per_phase_parity:
            parity_offset = (sample_number - 1) * substep_count + 1 - substep_index
        for _k in range(substep_count):
            # Proposed derivation, for Ben to confirm: the recorded history holds out_max * 2 samples,
            # the forced samples and an equal allowance for free decay; later free decay is integrated
            # but not recorded.
            record_frame = (
                trace_every > 0
                and substep_index % trace_every == 0
                and frame_count < frame_capacity
                and sample_number <= nominal_forced_sample_count * 2
            )
            if record_frame:
                v_before = v
                a_before = a
            if is_fluid_coupled:
                junction_force = float(
                    moc.step(
                        (substep_index + parity_offset) % 2 == 0,
                        a * dt,
                        column,
                        junction_force,
                    )
                )
                applied_force = junction_force
            else:
                applied_force = 0.0
            x, v, a = step_scalars(x, v, a, applied_force, sdof_params, dt)
            if record_frame:
                _trace_frame(
                    buffers,
                    frame_count,
                    _Frame(
                        substep_index,
                        sample_number - 1,
                        PHASE_FREE_DECAY,
                        x,
                        v,
                        a,
                        0.0,
                        0.0,
                        0.0,
                        mass * (v - (v_before + (a_before + a) * half_dt)) / dt,
                        abs(v_before) < friction_velocity_step,
                        junction_force if is_fluid_coupled else 0.0,
                    ),
                    column,
                )
                frame_count += 1
            substep_index += 1
            if abs(a) > a_max:
                a_max = abs(a)
            if abs(v) > v_max:
                v_max = abs(v)
            if abs(x) > x_max:
                x_max = abs(x)
            if _free_decay_product(x, decay_start_displacement) <= FREE_DECAY_THRESHOLD:
                decay_start_displacement = 0.0
        # Proposed derivation, for Ben to confirm: the recorded history holds out_max * 2 samples,
        # the forced samples and an equal allowance for free decay; later free decay is integrated
        # but not recorded.
        if output_type > 0 and sample_number <= nominal_forced_sample_count * 2:
            _record_sample(response_history, output_type, sample_number - 1, x, v, a)

    return _KernelResult(
        x_max,
        v_max,
        a_max,
        unbalance_force_max,
        x,
        v,
        a,
        sample_number,
        forced_samples,
        junction_force,
        frame_count,
    )
