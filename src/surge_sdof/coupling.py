"""The force the fluid column exerts on the structure.

``peak_response`` and ``peak_response_jc`` share one integration loop and differ only in
the coupling object they pass to it. Per sub-step the loop calls
``coupling_force(state, step_index)`` *before* the SDOF update, with the state at the end
of the previous sub-step (the VBA MoC block sits at the top of each ``k`` loop and reads
the current ``a``), and adds the result to the unbalance force (phases 1-2) or uses it
alone (free decay).

``step_index`` is a running sub-step counter over the whole run (0 at the first
sub-step); ``JunctionCoupling`` uses its parity for the MoC alternation (approved fix
F-2, NOTES.md). With ``peak_response_jc(parity="per_phase")`` the loop passes the VBA's
per-phase index ``k + (totInd - 1) * stepQTY`` instead (D-19); the coupling only ever
looks at ``step_index % 2``.

This module knows nothing about the force history, output types or the SDOF update.
See ``docs/architecture.md``.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from surge_sdof import moc
from surge_sdof.structure import State

__all__ = ["Coupling", "NoCoupling", "JunctionCoupling"]


class Coupling(Protocol):
    def coupling_force(self, state: State, step_index: int) -> float:
        """Force on the structure from the fluid at this sub-step (``dF`` in the VBA)."""
        ...


class NoCoupling:
    """The lumped solver (``GetPeakResponse``): no fluid feedback, ``dF = 0``."""

    __slots__ = ()

    def coupling_force(self, state: State, step_index: int) -> float:
        return 0.0


class JunctionCoupling:
    """The junction-coupling solver (``GetPeakResponseJC``): a 1-D MoC fluid column
    inside the span is accelerated with the mass through the interp-fraction profiles
    and feeds the low-pass-filtered pressure-difference force ``dF`` back.

    Owns the column state (``moc.new_column``) and ``dF``; each ``coupling_force`` call
    advances the column one sub-step (``moc.step``) on the half-grid selected by
    ``step_index % 2`` (even first, as the VBA's index 0) with ``a * dt`` from the
    state's acceleration, and returns the new ``dF`` as a Python float (the SDOF state
    stays Python floats; ``float(np.float64)`` is exact).

    Parameters: ``pipe_seg_qty`` / ``pivot_seg_qty`` from ``moc.grid_size``; ``dt`` the
    sub-step; ``rho_c = fluidDensty * celerity``; ``fluid_area``; ``decay`` from
    ``moc.decay_factor``; ``vav_denominator`` "legacy" (``2N - 1``, VBA) or "fixed"
    (``2N + 1``, F-1).
    """

    __slots__ = (
        "n_seg",
        "pivot",
        "frac_a",
        "frac_b",
        "p_a",
        "v_a",
        "p_b",
        "v_b",
        "dt",
        "rho_c",
        "fluid_area",
        "decay",
        "vav_div",
        "d_f",
    )

    def __init__(
        self,
        pipe_seg_qty: int,
        pivot_seg_qty: int,
        dt: float,
        rho_c: float,
        fluid_area: float,
        decay: float,
        vav_denominator: str = "legacy",
    ):
        self.n_seg = int(pipe_seg_qty)
        self.pivot = int(pivot_seg_qty)
        self.frac_a, self.frac_b = moc.interp_fractions(self.n_seg, self.pivot)
        self.p_a, self.v_a, self.p_b, self.v_b = moc.new_column(self.n_seg)
        self.dt = float(dt)
        self.rho_c = float(rho_c)
        self.fluid_area = float(fluid_area)
        self.decay = float(decay)
        self.vav_div = moc.vav_divisor(self.n_seg, vav_denominator)
        self.d_f = 0.0

    def coupling_force(self, state: State, step_index: int) -> float:
        d_f = moc.step(
            step_index % 2 == 0,
            state[2] * self.dt,
            self.p_a,
            self.v_a,
            self.p_b,
            self.v_b,
            self.frac_a,
            self.frac_b,
            self.n_seg,
            self.pivot,
            self.rho_c,
            self.decay,
            self.vav_div,
            self.fluid_area,
            self.d_f,
        )
        self.d_f = float(d_f)
        return self.d_f

    def column(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Copies of ``(p_a, v_a, p_b, v_b)``: the VBA ``arrayA(0, :)``, ``arrayA(1, :)``,
        ``arrayB(0, :)``, ``arrayB(1, :)``."""
        return self.p_a.copy(), self.v_a.copy(), self.p_b.copy(), self.v_b.copy()
