"""The force the fluid column exerts on the structure.

``peak_response`` and ``peak_response_jc`` share one integration loop and differ only in
the coupling they pass to it: none, or a ``JunctionCoupling``. Per sub-step the loop
evaluates the coupling force *before* the SDOF update, with the state at the end of the
previous sub-step (the VBA MoC block sits at the top of each ``k`` loop and reads the
current ``a``), and adds the result to the unbalance force (phases 1-2) or uses it alone
(free decay).

The compiled loop of Stage 5 (``response._integrate_kernel``) cannot call Python objects,
so ``response._integrate`` unpacks the coupling: a kind code (0 = none, 1 =
``JunctionCoupling``) and, for the junction, its column arrays and scalars; the kernel
calls ``moc.step`` on the half-grid ``step_index % 2`` selects, keeps ``dF`` as a float,
and ``_integrate`` writes ``d_f`` back.

``step_index`` is a running sub-step counter over the whole run (0 at the first
sub-step); ``JunctionCoupling`` uses its parity for the MoC alternation (approved fix
F-2, NOTES.md). With ``peak_response_jc(parity="per_phase")`` the loop passes the VBA's
per-phase index ``k + (totInd - 1) * stepQTY`` instead (D-19); the coupling only ever
looks at ``step_index % 2``.

This module knows nothing about the force history, output types or the SDOF update.
See ``docs/architecture.md``.
"""

from __future__ import annotations

from surge_sdof import moc

__all__ = ["JunctionCoupling"]


class JunctionCoupling:
    """The junction-coupling solver (``GetPeakResponseJC``).

    A 1-D MoC fluid column inside the span is accelerated with the mass through the
    moving-fraction profiles and feeds the low-pass-filtered pressure-difference force
    ``dF`` back. Owns the column state (``moc.column_at_rest``) and ``dF``.

    Parameters
    ----------
    pipe_seg_qty : int
        ``pipeSegQTY``, cells in the whole column (from ``moc.grid_size``).
    pivot_seg_qty : int
        ``pivotSegQTY``, cells from each end to the portal-frame pivot.
    dt : float
        Sub-step, s.
    rho_c : float
        Acoustic impedance ``fluidDensty * celerity``, Pa·s/m (kg/(m²·s)).
    fluid_area : float
        Internal cross-sectional area of the pipe, m².
    end_pressure_decay_factor : float
        ``dacayFactor`` from ``moc.end_pressure_decay_factor``, dimensionless, per even
        update.
    vav_denominator : {"fixed", "legacy"}, optional
        Divisor of the mean-velocity sum: ``2N + 1`` (approved fix F-1, default) or the
        VBA's ``2N - 1`` (D-17).
    fraction_profile : {"fixed", "legacy"}, optional
        The moving-fraction profiles (``moc.moving_fractions``): the lead author's
        corrected functions (approved fix F-4, default) or the VBA originals (D-4).

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
    The compiled loop (Stage 5) reads the attributes listed in ``__slots__`` and advances
    the column one sub-step at a time (``moc.step``) on the half-grid selected by
    ``step_index % 2`` (even first, as the VBA's index 0) with ``a * dt`` from the
    previous sub-step's acceleration; after the run ``d_f`` and the arrays hold the final
    column state. The parity source (running counter, F-2, or the VBA per-phase index,
    D-19) is the loop's choice. With ``pivot_seg_qty = 4`` the constructor raises
    ``ZeroDivisionError`` on the legacy profile (D-4, at set-up rather than in the first
    MoC update) and ``ValueError`` on the fixed one (the port's guard: the ramp needs
    ``pivot > ext``).
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
        end_pressure_decay_factor: float,
        vav_denominator: str = "fixed",
        fraction_profile: str = "fixed",
    ):
        self.n_seg = int(pipe_seg_qty)
        self.pivot = int(pivot_seg_qty)
        self.frac_a, self.frac_b = moc.moving_fractions(self.n_seg, self.pivot, fraction_profile)
        self.p_a, self.v_a, self.p_b, self.v_b = moc.column_at_rest(self.n_seg)
        self.dt = float(dt)
        self.rho_c = float(rho_c)
        self.fluid_area = float(fluid_area)
        self.decay = float(end_pressure_decay_factor)
        self.vav_div = moc.mean_velocity_divisor(self.n_seg, vav_denominator)
        self.d_f = 0.0
