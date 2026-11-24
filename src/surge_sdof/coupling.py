"""The force the fluid column exerts on the structure.

``peak_response`` and ``peak_response_jc`` share one integration loop and differ only in
the fluid column they pass to it: ``moc.empty_column()`` (no fluid coupling) or the column
``fluid_column`` builds. Per sub-step the loop evaluates the coupling force *before* the
SDOF update, with the state at the end of the previous sub-step (the VBA MoC block sits at
the top of each ``k`` loop and reads the current ``a``), and adds the result to the
unbalance force (transit and forced phases) or uses it alone (free decay).

The compiled loop of Stage 5 (``response._integrate_kernel``) takes the ``moc.FluidColumn``
(its ``is_fluid_coupled`` flag on or off) and starts the junction force at 0.0; it calls
``moc.step`` on the half-grid ``step_index % 2`` selects and keeps ``dF`` as a float.

``step_index`` is a running sub-step counter over the whole run (0 at the first
sub-step), whose parity selects the MoC half-grid (approved fix F-2, NOTES.md). With
``peak_response_jc(parity="per_phase")`` the loop passes the VBA's per-phase index
``k + (totInd - 1) * stepQTY`` instead (D-19); the MoC step only ever looks at
``step_index % 2``.

This module knows nothing about the force history, output types or the SDOF update.
See ``docs/architecture.md``.
"""

from __future__ import annotations

from typing import NamedTuple

from surge_sdof import moc

__all__ = ["FluidConstants", "fluid_column"]


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


def fluid_column(
    grid: moc.ColumnGrid,
    fluid: FluidConstants,
    vav_denominator: str = "fixed",
    fraction_profile: str = "fixed",
) -> moc.FluidColumn:
    """The fluid column of a junction-coupling run (``GetPeakResponseJC``), at rest.

    A 1-D MoC fluid column inside the span, accelerated with the mass through the
    moving-fraction profiles; the compiled loop advances it and feeds the
    low-pass-filtered pressure-difference force ``dF`` back (``moc.step``).

    Parameters
    ----------
    grid : moc.ColumnGrid
        From ``moc.grid_size``: ``pipeSegQTY``, cells in the whole column, and
        ``pivotSegQTY``, cells from each end to the portal-frame pivot.
    fluid : FluidConstants
        The characteristic impedance, flow area and end-pressure decay factor.
    vav_denominator : {"fixed", "legacy"}, optional
        Divisor of the mean-velocity sum: ``2N + 1`` (approved fix F-1, default) or the
        VBA's ``2N - 1`` (D-17).
    fraction_profile : {"fixed", "legacy"}, optional
        The moving-fraction profiles (``moc.moving_fractions``): the lead author's
        corrected functions (approved fix F-4, default) or the VBA originals (D-4).

    Returns
    -------
    moc.FluidColumn
        The column state (``moc.column_at_rest``), grid and fluid constants, with
        ``is_fluid_coupled`` on. The compiled loop updates its arrays in place; the
        junction force starts at 0.0 and is carried by the loop, not by the column.

    Raises
    ------
    FloatingPointError
        ``fluid.characteristic_impedance == 0``, before anything else (D-9: the MoC
        divides by it).
    ZeroDivisionError, ValueError
        ``pivot_seg_qty = 4`` on the legacy profile (D-4, at set-up rather than in the
        first MoC update) and on the fixed one (the port's guard: the ramp needs
        ``pivot > ext``).

    Notes
    -----
    The compiled loop (Stage 5) advances the column one sub-step at a time
    (``moc.step``) on the half-grid selected by ``step_index % 2`` (even first, as the
    VBA's index 0) with ``a * dt`` from the previous sub-step's acceleration. The parity
    source (running counter, F-2, or the VBA per-phase index, D-19) is the loop's choice.
    """
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
    characteristic_impedance = float(fluid.characteristic_impedance)
    flow_area = float(fluid.flow_area)
    decay_factor = float(fluid.end_pressure_decay_factor)
    velocity_divisor = moc.mean_velocity_divisor(column_cell_count, vav_denominator)
    return moc.FluidColumn(
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
