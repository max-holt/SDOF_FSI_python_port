"""The force the fluid column exerts on the structure.

``peak_response`` and ``peak_response_jc`` share one integration loop and differ only in
the coupling they pass to it: none, or a ``JunctionCoupling``. Per sub-step the loop
evaluates the coupling force *before* the SDOF update, with the state at the end of the
previous sub-step (the VBA MoC block sits at the top of each ``k`` loop and reads the
current ``a``), and adds the result to the unbalance force (transit and forced phases) or
uses it alone (free decay).

The compiled loop of Stage 5 (``response._integrate_kernel``) cannot call Python objects,
so ``response._integrate`` passes it the coupling's ``moc.FluidColumn`` (its
``is_fluid_coupled`` flag on) or ``moc.empty_column()`` (off) and the junction force; the kernel
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

from typing import NamedTuple

from surge_sdof import moc

__all__ = ["FluidConstants", "JunctionCoupling"]


class FluidConstants(NamedTuple):
    """The fluid constants of the column.

    Attributes
    ----------
    characteristic_impedance : float
        Acoustic impedance ``fluidDensty * celerity``, Pa·s/m (kg/(m²·s)).
    flow_area : float
        Internal cross-sectional area of the pipe, m².
    end_pressure_decay_factor : float
        ``dacayFactor`` from ``moc.end_pressure_decay_factor``, dimensionless, per even
        update.
    """

    characteristic_impedance: float
    flow_area: float
    end_pressure_decay_factor: float


class JunctionCoupling:
    """The junction-coupling solver (``GetPeakResponseJC``).

    A 1-D MoC fluid column inside the span is accelerated with the mass through the
    moving-fraction profiles and feeds the low-pass-filtered pressure-difference force
    ``dF`` back. Owns the column state (``moc.column_at_rest``) and ``dF``.

    Parameters
    ----------
    grid : moc.ColumnGrid
        From ``moc.grid_size``: ``pipeSegQTY``, cells in the whole column, and
        ``pivotSegQTY``, cells from each end to the portal-frame pivot.
    substep_duration : float
        Sub-step, s.
    fluid : FluidConstants
        The characteristic impedance, flow area and end-pressure decay factor.
    vav_denominator : {"fixed", "legacy"}, optional
        Divisor of the mean-velocity sum: ``2N + 1`` (approved fix F-1, default) or the
        VBA's ``2N - 1`` (D-17).
    fraction_profile : {"fixed", "legacy"}, optional
        The moving-fraction profiles (``moc.moving_fractions``): the lead author's
        corrected functions (approved fix F-4, default) or the VBA originals (D-4).

    Attributes
    ----------
    column : moc.FluidColumn
        The column state, grid and fluid constants.
    dt : float
        Sub-step, s.
    d_f : float
        The current junction force, N.

    Notes
    -----
    The compiled loop (Stage 5) takes ``column`` and ``d_f`` and advances
    the column one sub-step at a time (``moc.step``) on the half-grid selected by
    ``step_index % 2`` (even first, as the VBA's index 0) with ``a * dt`` from the
    previous sub-step's acceleration; after the run ``d_f`` and the arrays hold the final
    column state. The parity source (running counter, F-2, or the VBA per-phase index,
    D-19) is the loop's choice. With ``pivot_seg_qty = 4`` the constructor raises
    ``ZeroDivisionError`` on the legacy profile (D-4, at set-up rather than in the first
    MoC update) and ``ValueError`` on the fixed one (the port's guard: the ramp needs
    ``pivot > ext``). ``fluid.characteristic_impedance = 0`` raises ``FloatingPointError``
    before anything else (D-9: the MoC divides by it).
    """

    __slots__ = ("column", "dt", "d_f")

    def __init__(
        self,
        grid: moc.ColumnGrid,
        substep_duration: float,
        fluid: FluidConstants,
        vav_denominator: str = "fixed",
        fraction_profile: str = "fixed",
    ):
        if fluid.characteristic_impedance == 0:
            # D-9: the MoC divides by rhoC at every sub-step. The legacy raised
            # FloatingPointError there (numpy errstate); inside the compiled kernel errstate
            # does not apply, so the check is made once here, before the first update.
            raise FloatingPointError("rhoC = fluidDensty * celerity is 0: the MoC divides by it")
        column_cell_count = int(grid.column_cell_count)
        end_to_elbow_cell_count = int(grid.end_to_elbow_cell_count)
        moving_fraction_a, moving_fraction_b = moc.moving_fractions(
            column_cell_count, end_to_elbow_cell_count, fraction_profile
        )
        pressure_a, velocity_a, pressure_b, velocity_b = moc.column_at_rest(column_cell_count)
        self.dt = float(substep_duration)
        characteristic_impedance = float(fluid.characteristic_impedance)
        flow_area = float(fluid.flow_area)
        decay_factor = float(fluid.end_pressure_decay_factor)
        velocity_divisor = moc.mean_velocity_divisor(column_cell_count, vav_denominator)
        self.column = moc.FluidColumn(
            pressure_a,
            velocity_a,
            pressure_b,
            velocity_b,
            moving_fraction_a,
            moving_fraction_b,
            column_cell_count,
            end_to_elbow_cell_count,
            characteristic_impedance,
            decay_factor,
            velocity_divisor,
            flow_area,
            True,
        )
        self.d_f = 0.0
