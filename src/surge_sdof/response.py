"""Public API: peak response of the SDOF pipe proxy to a force history.

``peak_response`` reproduces ``GetPeakResponse`` (``legacy/vba/Existing Code.bas``
line 309) from the Stage 4 modules: ``structure`` (portal-frame proxy, SDOF kernel),
``loads`` (unbalance force schedule) and ``coupling`` (``NoCoupling``). Set-up is done
here per solver; the sample loop, max trackers, result history, free-decay phase and
output-type switch live in one shared ``_integrate``. ``peak_response_jc`` (a later
session) does its own fluid-corrected set-up and passes the JC coupling to the same loop;
the two set-ups are not merged.

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
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from surge_sdof import loads, structure
from surge_sdof.coupling import Coupling, NoCoupling
from surge_sdof.structure import SdofParams, step
from surge_sdof.vba_compat import clng

__all__ = ["PeakResponse", "peak_response"]


@dataclass(frozen=True)
class PeakResponse:
    """Result of ``peak_response``; the five maxima are the VBA ``resultArray(0 To 4)``."""

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

    def summary(self) -> np.ndarray:
        """The five maxima as the VBA ``resultArray(0 To 4)``."""
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
) -> PeakResponse:
    """Peak displacement response of the lumped SDOF proxy (``GetPeakResponse``).

    Parameters as ``legacy_port.get_peak_response`` (consistent units except
    ``dynamic_fric``, which assumes m and s): ``force_history`` is a 1-D history or a
    2-D one walked column-major; ``step_qty`` sub-steps per sample; ``sample_freq`` in
    Hz; ``physical_length`` between elbows; ``flexural_rigidity_ei``; ``celerity`` of the
    force along the pipe; ``mass_per_unit_len``; ``damping_percent`` of critical;
    ``dynamic_fric`` Coulomb coefficient; ``nat_freq`` in Hz; ``restrain_freq_ratio``
    (gap closed / gap open); ``gap``; ``output_type`` 0 summary, 1/2/3 history.
    """
    step_qty = int(step_qty)
    sample_freq = float(sample_freq)
    physical_length = float(physical_length)
    flexural_rigidity_ei = float(flexural_rigidity_ei)
    celerity = float(celerity)
    mass_per_unit_len = float(mass_per_unit_len)
    output_type = int(output_type)

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
    return _integrate(forces, params, dt, step_qty, NoCoupling(), out_max, output_type)


def _decay_test(x: float, x_zero: float) -> float:
    """``x * xZero`` of the free-decay test; VBA raises error 6 if the product
    overflows (the numpy state of the legacy port did the same), so this does too."""
    p = x * x_zero
    if p == math.inf:
        raise FloatingPointError("x * xZero overflowed (VBA error 6)")  # D-23
    return p


def _integrate(
    forces,
    params: SdofParams,
    dt: float,
    step_qty: int,
    coupling: Coupling,
    out_max: int,
    output_type: int,
) -> PeakResponse:
    """The VBA sample loop shared by both peak solvers: phases 1-2 driven by ``forces``
    (one list of per-sub-step unbalance values per sample), then free decay while
    ``x * xZero > 0.01``; max trackers; result history per sample."""
    dt = float(dt)
    coupling_force = coupling.coupling_force
    x = v = a = 0.0
    x_max = v_max = a_max = f_max = 0.0
    state = (x, v, a)
    n = 0  # running sub-step counter (step_index of the coupling)
    tot_ind = 0
    history = np.zeros(out_max * 2) if output_type > 0 else None

    # ------------------------------------------------- phases 1-2: forced response
    for sample in forces:
        tot_ind += 1
        for f in sample:
            state = step(state, coupling_force(state, n) + f, params, dt)
            n += 1
            x, v, a = state
            if abs(a) > a_max:
                a_max = abs(a)
            if abs(v) > v_max:
                v_max = abs(v)
            if abs(x) > x_max:
                x_max = abs(x)
            if abs(f) > f_max:
                f_max = abs(f)
        if output_type > 0:
            if output_type == 1:
                history[tot_ind - 1] = x
            elif output_type == 2:
                history[tot_ind - 1] = v
            elif output_type == 3:
                history[tot_ind - 1] = a

    # ---------------------------------------------------------- phase 3: free decay
    forced_samples = tot_ind
    x_zero = x
    while _decay_test(x, x_zero) > 0.01:
        tot_ind += 1
        for _k in range(step_qty):
            state = step(state, coupling_force(state, n), params, dt)
            n += 1
            x, v, a = state
            if abs(a) > a_max:
                a_max = abs(a)
            if abs(v) > v_max:
                v_max = abs(v)
            if abs(x) > x_max:
                x_max = abs(x)
            if _decay_test(x, x_zero) <= 0.01:
                x_zero = 0
        if output_type > 0 and tot_ind <= out_max * 2:
            if output_type == 1:
                history[tot_ind - 1] = x
            elif output_type == 2:
                history[tot_ind - 1] = v
            elif output_type == 3:
                history[tot_ind - 1] = a

    if not (math.isfinite(x) and math.isfinite(v) and math.isfinite(a)):
        raise FloatingPointError("SDOF state is not finite (VBA error 6: overflow)")  # D-23

    # VBA line 611: Abs(minUnsigned(gap, xMax) + max(0, |xMax| - gap) * ...) * stiffness
    static_equivalent = (
        abs(structure.effective_displacement(x_max, params.gap, params.ratio2)) * params.stiffness
    )
    return PeakResponse(
        max_static_equivalent_force=static_equivalent,
        max_displacement=x_max,
        max_velocity=v_max,
        max_acceleration=a_max,
        max_applied_force=f_max,
        history=history,
        output_type=output_type,
        free_decay_samples=tot_ind - forced_samples,
    )
