"""The fluid column of a junction-coupling run, built at rest: ``FluidConstants`` and
``fluid_column``, which returns the ``moc.FluidColumn`` that ``peak_response_jc`` passes to
the shared integration loop (``peak_response`` passes ``moc.empty_column()``).

The column's arithmetic is ``moc.step``; advancing the column each substep and adding the
junction force (VBA ``dF``) to the applied force are the loop's
(``response._integrate_kernel``). This module knows nothing about the force history or the
SDOF update.
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
        Acoustic impedance, density times celerity, Pa·s/m (kg/(m²·s)).
    flow_area : float
        Internal cross-sectional area of the pipe, m².
    end_pressure_decay_factor : float
        From ``moc.end_pressure_decay_factor``, dimensionless, per even update (VBA
        ``dacayFactor``).
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
    """The fluid column of a junction-coupling run, at rest.

    A 1-D MoC fluid column inside the span, accelerated with the mass through the
    moving-fraction profiles; the compiled loop advances it and feeds the
    low-pass-filtered pressure-difference force, the junction force, back (``moc.step``).

    Parameters
    ----------
    grid : moc.ColumnGrid
        From ``moc.grid_size``: the cells in the whole column and the cells from each end
        to the portal-frame pivot.
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
        ``end_to_elbow_cell_count = 4`` on the legacy profile (D-4, at set-up rather than
        in the first MoC update) and on the fixed one (the port's guard: the ramp needs
        ``pivot > ext``).

    Notes
    -----
    The column of VBA ``GetPeakResponseJC``. The compiled loop (Stage 5) advances it one
    substep at a time (``moc.step``) on the half-grid selected by the parity index (even
    first, as the VBA's index 0) with ``a * dt`` from the previous substep's acceleration.
    The parity source (running counter, F-2, or the VBA per-phase index, D-19) is the
    loop's choice.
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
