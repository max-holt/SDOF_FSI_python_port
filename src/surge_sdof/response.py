"""Public API: peak response of the SDOF pipe proxy to a force history.

``peak_response`` reproduces ``GetPeakResponse`` (``legacy/vba/Existing Code.bas``
line 309) from the Stage 4 modules: ``structure`` (portal-frame proxy, SDOF kernel),
``loads`` (unbalance force schedule) and ``coupling`` (``NoCoupling``). Set-up is done
here per solver; the sample loop, max trackers, result history, free-decay phase and
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
the profile once (``moc.interp_fractions``).

Stage 5 (Numba): ``_integrate`` is the Python orchestrator and ``_integrate_kernel`` the
``numba.njit(cache=True)`` loop (no fastmath). The orchestrator concatenates the
``loads.unbalance_force`` per-sample lists once into a flat float64 array with int64
sample offsets, unpacks ``SdofParams`` and the coupling (``Coupling.KIND``: 0 = none, 1 =
junction with its column arrays and scalars), runs the kernel, writes ``dF`` back to the
coupling and builds the ``PeakResponse``. The kernel takes floats, ints, bools and numpy
arrays only and calls ``structure.step_scalars`` and ``moc.step``, which Numba compiles
into it. With ``NUMBA_DISABLE_JIT=1`` the same source runs as Python (the unbalance value
and ``dF`` are cast with ``float`` so the state stays on Python floats as in Stage 4).

Session V.1 (trace): both solvers take ``trace_every: int = 0``. With ``k > 0`` every
``k``-th sub-step is recorded into preallocated arrays the kernel takes (``trace.allocate``)
and returned as ``PeakResponse.trace`` (a ``trace.Trace``); with ``0`` the kernel takes
empty arrays and the recording branch is never entered. The recording reads the state and
writes to the trace arrays only, so the ``PeakResponse`` values of a traced run are bitwise
those of the untraced run (``tests/test_trace.py``). ``loads.elbow_forces`` supplies the
per-sub-step elbow forces and the transit/history boundary for the trace.

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
from surge_sdof.coupling import Coupling, JunctionCoupling, NoCoupling
from surge_sdof.structure import SdofParams, step_scalars
from surge_sdof.trace import (
    F_A,
    F_DF,
    F_FA,
    F_FB,
    F_FFRIC,
    F_FU,
    F_V,
    F_X,
    I_PHASE,
    I_SAMPLE,
    I_STICK,
    I_SUB_STEP,
    PHASE_FREE_DECAY,
    PHASE_HISTORY,
    PHASE_TRANSIT,
    Trace,
)
from surge_sdof.vba_compat import clng

__all__ = ["PeakResponse", "peak_response", "peak_response_jc"]


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

    history = loads.as_history_2d(force_history)
    unb = loads.transit_delay(physical_length, celerity, sample_freq)
    out_max = history.shape[0] * history.shape[1] + clng(unb)  # VBA line 377
    dt = 1 / (sample_freq * step_qty)

    h = structure.solve_portal_height(
        physical_length, flexural_rigidity_ei, mass_per_unit_len, nat_freq
    )
    params = structure.lumped_params(
        physical_length,
        h,
        mass_per_unit_len,
        damping_percent,
        dynamic_fric,
        nat_freq,
        dt,
        gap,
        restrain_freq_ratio,
    )
    forces = loads.unbalance_force(history, sample_freq, physical_length, celerity, step_qty)
    meta = None
    if trace_every:
        meta = _TraceMeta(
            "peak_response",
            {
                "force_history": history,
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
            loads.elbow_forces(history, sample_freq, physical_length, celerity, step_qty),
        )
    return _integrate(
        forces,
        params,
        dt,
        step_qty,
        NoCoupling(),
        out_max,
        output_type,
        trace_every=trace_every,
        meta=meta,
    )


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
        The interp-fraction profiles weighting the mass acceleration along the column:
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
        Unknown ``parity``, ``vav_denominator`` or ``fraction_profile``; ``trace_every <
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

    history = loads.as_history_2d(force_history)
    unb = loads.transit_delay(physical_length, celerity, sample_freq)
    out_max = history.shape[0] * history.shape[1] + clng(unb)  # VBA line 714
    dt = 1 / (sample_freq * step_qty)

    h = structure.solve_portal_height(
        physical_length, flexural_rigidity_ei, mass_per_unit_len, nat_freq
    )
    # VBA order: mass, stiffness, damping, fricAcc (726-729), then the grid (731-734)
    params = structure.jc_params(
        physical_length,
        h,
        mass_per_unit_len,
        fluid_densty,
        fluid_area,
        damping_percent,
        dynamic_fric,
        nat_freq,
        dt,
        gap,
        restrain_freq_ratio,
    )
    decay = moc.decay_factor(celerity, dt, physical_length)
    pipe_seg_qty, pivot_seg_qty = moc.grid_size(physical_length, h, celerity, dt)
    if moc.is_short_pipe(pipe_seg_qty, pivot_seg_qty):
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
    rho_c = fluid_densty * celerity
    if rho_c == 0:
        # D-9: the MoC divides by rhoC at every sub-step. The legacy raised
        # FloatingPointError there (numpy errstate); inside the compiled kernel errstate
        # does not apply, so the check is made once here, before the first update.
        raise FloatingPointError("rhoC = fluidDensty * celerity is 0: the MoC divides by it")
    junction = JunctionCoupling(
        pipe_seg_qty,
        pivot_seg_qty,
        dt,
        rho_c,
        fluid_area,
        decay,
        vav_denominator,
        fraction_profile,
    )
    forces = loads.unbalance_force(history, sample_freq, physical_length, celerity, step_qty)
    meta = None
    if trace_every:
        meta = _TraceMeta(
            "peak_response_jc",
            {
                "force_history": history,
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
            loads.elbow_forces(history, sample_freq, physical_length, celerity, step_qty),
        )
    return _integrate(
        forces,
        params,
        dt,
        step_qty,
        junction,
        out_max,
        output_type,
        legacy_parity=(parity == "per_phase"),
        trace_every=trace_every,
        meta=meta,
    )


def _trace_stride(trace_every) -> int:
    """``trace_every`` as a non-negative int (``operator.index``: no silent truncation)."""
    trace_every = operator.index(trace_every)
    if trace_every < 0:
        raise ValueError(f"trace_every must be >= 0, got {trace_every}")
    return trace_every


class _TraceMeta(NamedTuple):
    """What ``_integrate`` needs beyond the kernel arrays to build a ``Trace``."""

    solver: str
    inputs: dict
    celerity: float
    elbows: object  # the loads.elbow_forces generator


@numba.njit(cache=True)
def _decay_test(x: float, x_zero: float) -> float:
    """``x * xZero`` of the free-decay test; VBA raises error 6 if the product
    overflows (the numpy state of the legacy port did the same), so this does too."""
    p = x * x_zero
    if p == math.inf:
        raise FloatingPointError("x * xZero overflowed (VBA error 6)")  # D-23
    return p


@numba.njit(cache=True)
def _record(
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


@numba.njit(cache=True)
def _trace_frame(
    tr_f: np.ndarray,
    tr_i: np.ndarray,
    tr_p: np.ndarray,
    tr_v: np.ndarray,
    frame: int,
    n: int,
    sample: int,
    phase: int,
    x: float,
    v: float,
    a: float,
    f_a: float,
    f_b: float,
    f_u: float,
    f_fric: float,
    stick: bool,
    d_f: float,
    kind: int,
    p_a: np.ndarray,
    v_a: np.ndarray,
    p_b: np.ndarray,
    v_b: np.ndarray,
    n_seg: int,
) -> None:
    """Write one trace frame (Session V.1): the scalars into row ``frame`` of ``tr_f`` /
    ``tr_i`` (columns ``trace.F_*`` / ``trace.I_*``) and, for ``kind`` 1, the column
    interleaved ``A0 B0 A1 ... A(N)`` into ``tr_p`` / ``tr_v``. Reads only; the solver
    state is untouched."""
    tr_f[frame, F_X] = x
    tr_f[frame, F_V] = v
    tr_f[frame, F_A] = a
    tr_f[frame, F_FA] = f_a
    tr_f[frame, F_FB] = f_b
    tr_f[frame, F_FU] = f_u
    tr_f[frame, F_FFRIC] = f_fric
    tr_f[frame, F_DF] = d_f
    tr_i[frame, I_SUB_STEP] = n
    tr_i[frame, I_SAMPLE] = sample
    tr_i[frame, I_PHASE] = phase
    tr_i[frame, I_STICK] = 1 if stick else 0
    if kind == 1:
        for c in range(n_seg):
            tr_p[frame, 2 * c] = p_a[c]
            tr_p[frame, 2 * c + 1] = p_b[c]
            tr_v[frame, 2 * c] = v_a[c]
            tr_v[frame, 2 * c + 1] = v_b[c]
        tr_p[frame, 2 * n_seg] = p_a[n_seg]
        tr_v[frame, 2 * n_seg] = v_a[n_seg]


def _integrate(
    forces,
    params: SdofParams,
    dt: float,
    step_qty: int,
    coupling: Coupling,
    out_max: int,
    output_type: int,
    legacy_parity: bool = False,
    trace_every: int = 0,
    meta: _TraceMeta | None = None,
) -> PeakResponse:
    """The VBA sample loop shared by both peak solvers: phases 1-2 driven by ``forces``
    (one list of per-sub-step unbalance values per sample), then free decay while
    ``x * xZero > 0.01``; max trackers; result history per sample.

    Python orchestrator of ``_integrate_kernel`` (Stage 5): flattens ``forces`` once,
    unpacks ``params`` and ``coupling`` (``Coupling.KIND`` 0 or 1; the junction's arrays
    are updated in place and its ``d_f`` written back), builds the ``PeakResponse``.

    ``step_index`` the kernel uses for the MoC parity is the running sub-step counter
    ``n`` (0 at the first sub-step), or with ``legacy_parity`` the VBA per-phase index
    ``k + (totInd - 1) * stepQTY`` (phase 3: ``k = 1 .. stepQTY``), written as ``n + off``
    with ``off`` fixed per sample (D-19, approved fix F-2).

    Session V.1: with ``trace_every > 0`` the elbow forces of ``meta.elbows`` are
    flattened like ``forces``, the trace arrays are allocated (``trace.check_memory``,
    ``trace.allocate``) and the kernel fills them; ``trace.build`` makes the ``Trace``.
    With 0 the kernel takes empty arrays."""
    dt = float(dt)
    samples = list(forces)
    offsets = np.zeros(len(samples) + 1, dtype=np.int64)
    for i, sample in enumerate(samples):
        offsets[i + 1] = offsets[i] + len(sample)
    flat = np.fromiter(
        itertools.chain.from_iterable(samples), dtype=np.float64, count=int(offsets[-1])
    )
    history = np.zeros(out_max * 2 if output_type > 0 else 0)
    kind = coupling.KIND

    # ----------------------------------------------------------------- trace set-up
    n_cells = 2 * coupling.n_seg + 1 if kind == JunctionCoupling.KIND else 0
    delay_substeps = 0
    if trace_every > 0:
        if meta is None:
            raise TypeError("trace_every > 0 needs the trace meta")
        elbows = list(meta.elbows)
        if [len(fa) for _ph, fa, _fb in elbows] != [len(s) for s in samples]:
            raise AssertionError("elbow_forces and unbalance_force disagree on the samples")
        n_sub = int(offsets[-1])
        flat_a = np.fromiter(
            itertools.chain.from_iterable(fa for _ph, fa, _fb in elbows), np.float64, count=n_sub
        )
        flat_b = np.fromiter(
            itertools.chain.from_iterable(fb for _ph, _fa, fb in elbows), np.float64, count=n_sub
        )
        delay_substeps = sum(len(fa) for ph, fa, _fb in elbows if ph == 0)
        cap = tracing.check_memory(
            n_sub, len(samples), int(out_max), int(step_qty), trace_every, n_cells
        )
    else:
        flat_a = flat_b = np.zeros(0)
        cap = 0
    tr_f, tr_i, tr_p, tr_v = tracing.allocate(cap, n_cells)
    if kind == JunctionCoupling.KIND:
        jc: JunctionCoupling = coupling
        column = (jc.p_a, jc.v_a, jc.p_b, jc.v_b, jc.frac_a, jc.frac_b)
        scalars = (jc.n_seg, jc.pivot, jc.rho_c, jc.decay, jc.vav_div, jc.fluid_area, jc.d_f)
    elif kind == NoCoupling.KIND:
        empty = np.zeros(0)
        column = (empty, empty, empty, empty, empty, empty)
        scalars = (0, 0, 0.0, 1.0, 1, 0.0, 0.0)
    else:
        raise TypeError(f"unknown coupling kind {kind!r}")

    (x_max, v_max, a_max, f_max, x, v, a, tot_ind, forced_samples, d_f, n_frames) = (
        _integrate_kernel(
            flat,
            offsets,
            params.mass,
            params.stiffness,
            params.damping,
            params.fric_acc,
            params.gap,
            params.ratio2,
            dt,
            int(step_qty),
            int(out_max),
            int(output_type),
            bool(legacy_parity),
            history,
            int(kind),
            *column,
            *scalars,
            int(trace_every),
            flat_a,
            flat_b,
            int(delay_substeps),
            tr_f,
            tr_i,
            tr_p,
            tr_v,
        )
    )
    if kind == JunctionCoupling.KIND:
        jc.d_f = float(d_f)

    if not (math.isfinite(x) and math.isfinite(v) and math.isfinite(a)):
        raise FloatingPointError("SDOF state is not finite (VBA error 6: overflow)")  # D-23

    # VBA line 611: Abs(minUnsigned(gap, xMax) + max(0, |xMax| - gap) * ...) * stiffness
    static_equivalent = (
        abs(structure.effective_displacement(x_max, params.gap, params.ratio2)) * params.stiffness
    )
    trace = None
    if trace_every > 0:
        trace = tracing.build(
            meta.solver,
            meta.inputs,
            trace_every,
            dt,
            step_qty,
            out_max,
            params,
            int(n_frames),
            tr_f,
            tr_i,
            tr_p,
            tr_v,
            jc=coupling if kind == JunctionCoupling.KIND else None,
            celerity=meta.celerity,
            ext_qty=moc.EXT_QTY,
        )
    return PeakResponse(
        max_static_equivalent_force=float(static_equivalent),
        max_displacement=float(x_max),
        max_velocity=float(v_max),
        max_acceleration=float(a_max),
        max_applied_force=float(f_max),
        history=history if output_type > 0 else None,
        output_type=output_type,
        free_decay_samples=int(tot_ind - forced_samples),
        trace=trace,
    )


@numba.njit(cache=True)
def _integrate_kernel(
    flat: np.ndarray,
    offsets: np.ndarray,
    mass: float,
    stiffness: float,
    damping: float,
    fric_acc: float,
    gap: float,
    ratio2: float,
    dt: float,
    step_qty: int,
    out_max: int,
    output_type: int,
    legacy_parity: bool,
    history: np.ndarray,
    kind: int,
    p_a: np.ndarray,
    v_a: np.ndarray,
    p_b: np.ndarray,
    v_b: np.ndarray,
    frac_a: np.ndarray,
    frac_b: np.ndarray,
    n_seg: int,
    pivot: int,
    rho_c: float,
    decay: float,
    vav_div: int,
    fluid_area: float,
    d_f: float,
    trace_every: int,
    flat_a: np.ndarray,
    flat_b: np.ndarray,
    delay_substeps: int,
    tr_f: np.ndarray,
    tr_i: np.ndarray,
    tr_p: np.ndarray,
    tr_v: np.ndarray,
):
    """The sample loop of ``_integrate`` on scalars and arrays only (Stage 5 kernel).

    ``flat[offsets[s]:offsets[s + 1]]`` holds sample ``s``'s per-sub-step unbalance
    values. ``kind`` 1 advances the MoC column (``moc.step`` on the half-grid selected by
    the parity of ``n + off``) before each SDOF sub-step and adds ``dF``; ``kind`` 0 adds
    ``0.0`` (the ``NoCoupling`` of Stage 4). Returns ``(x_max, v_max, a_max, f_max, x, v,
    a, tot_ind, forced_samples, d_f, n_frames)``; ``history`` is filled in place for
    ``output_type`` 1-3.

    Trace (Session V.1): with ``trace_every > 0`` every sub-step whose running index
    ``n`` is a multiple of it, while ``tot_ind <= out_max * 2`` and the capacity lasts,
    is written by ``_trace_frame`` after the SDOF update (``flat_a`` / ``flat_b`` are
    the elbow forces per forced sub-step, ``delay_substeps`` the transit -> history
    boundary). ``f_friction`` is ``mass * (v_new - (v_old + (a_old + a_new) * half_dt))
    / dt`` with the same ``half_dt = dt / 2`` as ``step_scalars``; ``stick`` is ``|v_old| <
    fric_acc``. With ``trace_every == 0`` the branch is never entered and the arrays are
    empty.
    """
    x = 0.0
    v = 0.0
    a = 0.0
    x_max = 0.0
    v_max = 0.0
    a_max = 0.0
    f_max = 0.0
    n = 0  # running sub-step counter
    off = 0  # step_index = n + off
    tot_ind = 0
    n_samples = offsets.shape[0] - 1
    # trace (Session V.1)
    frame = 0
    cap = tr_i.shape[0]
    half_dt = dt / 2
    v_old = 0.0
    a_old = 0.0

    # ------------------------------------------------- phases 1-2: forced response
    for s in range(n_samples):
        tot_ind += 1
        if legacy_parity:
            off = (tot_ind - 1) * step_qty - n
        for i in range(offsets[s], offsets[s + 1]):
            f = float(flat[i])
            rec = trace_every > 0 and n % trace_every == 0 and frame < cap
            if rec:
                v_old = v
                a_old = a
            if kind == 1:
                d_f = float(
                    moc.step(
                        (n + off) % 2 == 0,
                        a * dt,
                        p_a,
                        v_a,
                        p_b,
                        v_b,
                        frac_a,
                        frac_b,
                        n_seg,
                        pivot,
                        rho_c,
                        decay,
                        vav_div,
                        fluid_area,
                        d_f,
                    )
                )
                f_applied = d_f + f
            else:
                f_applied = 0.0 + f
            x, v, a = step_scalars(
                x, v, a, f_applied, mass, stiffness, damping, fric_acc, gap, ratio2, dt
            )
            if rec:
                _trace_frame(
                    tr_f,
                    tr_i,
                    tr_p,
                    tr_v,
                    frame,
                    n,
                    tot_ind - 1,
                    PHASE_TRANSIT if n < delay_substeps else PHASE_HISTORY,
                    x,
                    v,
                    a,
                    flat_a[i],
                    flat_b[i],
                    f,
                    mass * (v - (v_old + (a_old + a) * half_dt)) / dt,
                    abs(v_old) < fric_acc,
                    d_f if kind == 1 else 0.0,
                    kind,
                    p_a,
                    v_a,
                    p_b,
                    v_b,
                    n_seg,
                )
                frame += 1
            n += 1
            if abs(a) > a_max:
                a_max = abs(a)
            if abs(v) > v_max:
                v_max = abs(v)
            if abs(x) > x_max:
                x_max = abs(x)
            if abs(f) > f_max:
                f_max = abs(f)
        if output_type > 0:
            _record(history, output_type, tot_ind - 1, x, v, a)

    # ---------------------------------------------------------- phase 3: free decay
    forced_samples = tot_ind
    x_zero = x
    while _decay_test(x, x_zero) > 0.01:
        tot_ind += 1
        if legacy_parity:
            off = (tot_ind - 1) * step_qty + 1 - n
        for _k in range(step_qty):
            rec = (
                trace_every > 0 and n % trace_every == 0 and frame < cap and tot_ind <= out_max * 2
            )
            if rec:
                v_old = v
                a_old = a
            if kind == 1:
                d_f = float(
                    moc.step(
                        (n + off) % 2 == 0,
                        a * dt,
                        p_a,
                        v_a,
                        p_b,
                        v_b,
                        frac_a,
                        frac_b,
                        n_seg,
                        pivot,
                        rho_c,
                        decay,
                        vav_div,
                        fluid_area,
                        d_f,
                    )
                )
                f_applied = d_f
            else:
                f_applied = 0.0
            x, v, a = step_scalars(
                x, v, a, f_applied, mass, stiffness, damping, fric_acc, gap, ratio2, dt
            )
            if rec:
                _trace_frame(
                    tr_f,
                    tr_i,
                    tr_p,
                    tr_v,
                    frame,
                    n,
                    tot_ind - 1,
                    PHASE_FREE_DECAY,
                    x,
                    v,
                    a,
                    0.0,
                    0.0,
                    0.0,
                    mass * (v - (v_old + (a_old + a) * half_dt)) / dt,
                    abs(v_old) < fric_acc,
                    d_f if kind == 1 else 0.0,
                    kind,
                    p_a,
                    v_a,
                    p_b,
                    v_b,
                    n_seg,
                )
                frame += 1
            n += 1
            if abs(a) > a_max:
                a_max = abs(a)
            if abs(v) > v_max:
                v_max = abs(v)
            if abs(x) > x_max:
                x_max = abs(x)
            if _decay_test(x, x_zero) <= 0.01:
                x_zero = 0.0
        if output_type > 0 and tot_ind <= out_max * 2:
            _record(history, output_type, tot_ind - 1, x, v, a)

    return (x_max, v_max, a_max, f_max, x, v, a, tot_ind, forced_samples, d_f, frame)
