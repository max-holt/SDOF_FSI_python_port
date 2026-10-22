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
    """What ``response._integrate`` needs from a coupling: one call per sub-step."""

    def coupling_force(self, state: State, step_index: int) -> float:
        """Force on the structure from the fluid at this sub-step (``dF`` in the VBA).

        Parameters
        ----------
        state : State
            ``(x, v, a)`` at the end of the previous sub-step: m, m/s, m/s².
        step_index : int
            Sub-step index whose parity selects the MoC half-grid (see the module docstring).

        Returns
        -------
        float
            ``dF``, N.
        """
        ...


class NoCoupling:
    """The lumped solver (``GetPeakResponse``): no fluid feedback, ``dF = 0``."""

    __slots__ = ()

    def coupling_force(self, state: State, step_index: int) -> float:
        """Always ``0.0`` N (``0.0 + F`` differs from the VBA's ``F`` only in the sign of an
        exact zero).
        """
        return 0.0


class JunctionCoupling:
    """The junction-coupling solver (``GetPeakResponseJC``).

    A 1-D MoC fluid column inside the span is accelerated with the mass through the
    interp-fraction profiles and feeds the low-pass-filtered pressure-difference force
    ``dF`` back. Owns the column state (``moc.new_column``) and ``dF``.

    Parameters
    ----------
    pipe_seg_qty : int
        ``pipeSegQTY``, cells between the elbows (from ``moc.grid_size``).
    pivot_seg_qty : int
        ``pivotSegQTY``, cells from each end to the portal-frame pivot.
    dt : float
        Sub-step, s.
    rho_c : float
        Acoustic impedance ``fluidDensty * celerity``, Pa·s/m (kg/(m²·s)).
    fluid_area : float
        Internal cross-sectional area of the pipe, m².
    decay : float
        ``dacayFactor`` from ``moc.decay_factor``, dimensionless, per even update.
    vav_denominator : {"fixed", "legacy"}, optional
        Divisor of the mean-velocity sum: ``2N + 1`` (approved fix F-1, default) or the
        VBA's ``2N - 1`` (D-17).

    Attributes
    ----------
    p_a, v_a : numpy.ndarray
        Pressure (Pa) and velocity (m/s) on the A nodes ``0 .. N``.
    p_b, v_b : numpy.ndarray
        Pressure (Pa) and velocity (m/s) on the B cells ``0 .. N-1``.
    d_f : float
        The current junction force, N.

    Notes
    -----
    Each ``coupling_force`` call advances the column one sub-step (``moc.step``) on the
    half-grid selected by ``step_index % 2`` (even first, as the VBA's index 0) with
    ``a * dt`` from the state's acceleration. The parity source (running counter, F-2, or
    the VBA per-phase index, D-19) is the loop's choice. With ``pivot_seg_qty = 4`` the
    constructor raises ``ZeroDivisionError`` (D-4, at set-up rather than in the first
    MoC update).
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
        vav_denominator: str = "fixed",
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
        """Advance the column one sub-step and return the new junction force.

        Parameters
        ----------
        state : State
            ``(x, v, a)`` at the end of the previous sub-step; only ``a`` (m/s²) is used.
        step_index : int
            Even: update the A nodes from the B cells; odd: the B cells from the A nodes.

        Returns
        -------
        float
            ``dF``, N, as a Python float (``float(numpy.float64)`` is exact).
        """
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
        ``arrayB(0, :)``, ``arrayB(1, :)`` (Pa, m/s, Pa, m/s).
        """
        return self.p_a.copy(), self.v_a.copy(), self.p_b.copy(), self.v_b.copy()
