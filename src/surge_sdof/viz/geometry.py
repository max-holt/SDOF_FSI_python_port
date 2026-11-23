"""The expansion-loop geometry of a traced run (Session V.2b / V.2c, moved here in W.1).

``layout_from_trace(trace)`` lays the interleaved MoC column on the expansion loop the
viewer draws and the data files describe (``docs/data_format.md``, ``trace.geometry``):
inlet pipe, leg down, run, return leg up, outlet pipe, the cells mapped by their moving
fraction (``_segments``: the fraction-1 block is the run, the last fraction-0 cell before it
and the first after it the upper elbows), uniform spacing by ``cell_position`` along the
centreline, sharp elbows (the model has no bends). A JC trace brings its own grid; a lumped
trace gets the grid the case would have (``lumped_grid``: ``moc.grid_size`` /
``moc.moving_fractions`` with the solver's default profile, F-4; a ``pivotSegQTY = 4`` grid,
refused by both profiles, gets the legacy B profile with the ``n < extQTY`` test, display
only). The rules are described in ``docs/architecture.md`` ("The picture", Geometry) and
pinned by ``tests/test_geometry.py``.

Used by ``surge_sdof.export`` (the ``geometry`` block of a trace file); numpy only, no plotly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from surge_sdof import moc, structure
from surge_sdof.trace import Trace

__all__ = [
    "LoopLayout",
    "loop_layout",
    "lumped_grid",
    "layout_from_trace",
]


@dataclass(frozen=True)
class LoopLayout:
    """The column laid on the expansion loop (see the module docstring and ``loop_layout``).

    The elbows of the force model are the two ends of the run: elbow A, which the pressure
    wave reaches first (force A acts at once; the inlet side), is the ``run_start`` corner
    at ``x = 0``; elbow B, reached after the transit delay, is the ``run_end`` corner at
    ``x = run_length``. The junction force taps the column there (``moc.step``).

    Attributes
    ----------
    cell_position, cell_kind, moving_fraction : numpy.ndarray
        As ``Trace`` (m along the column; 0 = A node / 1 = B cell; the moving fraction).
    pivot_seg_qty, pipe_seg_qty, ext_qty : int
        The grid (``moc.grid_size``, ``moc.INACTIVE_END_CELL_COUNT``).
    cell_length : float
        ``2 * celerity * dt``, m (a cell; ``cell_position`` steps by half of it).
    portal_height : float
        ``structure.solve_portal_height`` of the case, m (printed, not used for the layout).
    spacing : float
        Distance between consecutive cells along the centreline, m (``celerity * dt``).
    inlet_end, run_start, run_end, outlet_start : int
        Cell indices: the last fraction-0 cell of the inlet (the inlet / leg elbow), the
        first and last fraction-1 cells (the leg / run elbows), the first fraction-0 cell
        of the outlet (the leg / outlet elbow).
    elbow_pairs : tuple of (int, int)
        The two cells either side of each of the four elbows, in centreline order.
    x_nominal, y_nominal : numpy.ndarray
        Circle centres at rest, m: the run along ``y = 0`` from ``x = 0`` (``run_start``)
        to ``x = run_length`` (``run_end``); leg 1 up ``x = 0`` to the inlet elbow cell at
        ``(0, leg_height)``, the inlet extending left from it at ``y = leg_height``; leg 2
        up ``x = run_length`` to the outlet elbow cell at ``(run_length, leg_height_2)``,
        the outlet extending right from it. Sharp corners: the model has no bends.
    run_length : float
        ``cell_position[run_end] - cell_position[run_start]``, m.
    leg_height, leg_height_2 : float
        Height of the inlet and outlet pipes above the run, m: the centreline length
        between the elbow cells.
    """

    cell_position: np.ndarray
    cell_kind: np.ndarray
    moving_fraction: np.ndarray
    pivot_seg_qty: int
    pipe_seg_qty: int
    ext_qty: int
    cell_length: float
    portal_height: float
    spacing: float
    inlet_end: int
    run_start: int
    run_end: int
    outlet_start: int
    elbow_pairs: tuple
    x_nominal: np.ndarray
    y_nominal: np.ndarray
    run_length: float
    leg_height: float
    leg_height_2: float

    @property
    def n_cells(self) -> int:
        return int(self.cell_position.shape[0])


# ------------------------------------------------------------------ geometry


def _segments(grid_point_moving_fraction: np.ndarray) -> tuple[int, int, int, int]:
    """``(inlet_end, run_start, run_end, outlet_start)`` from the fraction profile: the
    fraction-1 block is the run; the last fraction-0 cell before it and the first after it
    are the upper elbows. With the F-4 profile both legs hold ``2 pivot - 10`` interleaved
    cells and every inlet / outlet cell has fraction 0; with the legacy profile the inlet
    leg is one cell longer and D-4's ``n < 3`` cell (B(3), fraction ``1 / (pivot - 4)^2``)
    is a moving cell on the horizontal inlet (B(4) = 0 is the last zero before the run)."""
    fully_moving = np.flatnonzero(grid_point_moving_fraction == 1.0)
    if fully_moving.size == 0:
        raise ValueError("no fraction-1 cell: the profile has no run")
    run_start_index, run_end_index = int(fully_moving[0]), int(fully_moving[-1])
    still_before_run = np.flatnonzero(grid_point_moving_fraction[:run_start_index] == 0.0)
    still_after_run = np.flatnonzero(grid_point_moving_fraction[run_end_index + 1 :] == 0.0)
    if still_before_run.size == 0 or still_after_run.size == 0:
        raise ValueError("no fraction-0 cell at an end: the profile has no inlet or outlet")
    return (
        int(still_before_run[-1]),
        run_start_index,
        run_end_index,
        run_end_index + 1 + int(still_after_run[0]),
    )


def loop_layout(
    grid_point_position: np.ndarray,
    grid_point_kind: np.ndarray,
    grid_point_moving_fraction: np.ndarray,
    end_to_elbow_cell_count: int,
    column_cell_count: int,
    ext_qty: int,
    cell_length: float,
    portal_frame_height: float,
) -> LoopLayout:
    """Lay the interleaved column on the expansion loop, uniformly by ``grid_point_position``.

    The centreline runs: inlet (horizontal, leftwards from the inlet elbow cell at ``(0,
    leg_height)``), leg 1 (down ``x = 0``), the run (``y = 0`` from ``x = 0`` to ``x =
    run_length``), leg 2 (up ``x = run_length``), outlet (horizontal, rightwards from the
    outlet elbow cell at ``(run_length, leg_height_2)``). The elbows are sharp corners at
    the elbow cells (``_segments``): the model has no bends, and the cells either side of
    a corner are one spacing from the corner cell along its two segments. A grid point at
    ``centreline_position`` along the column is at that centreline length, so every inlet /
    outlet point is at its pipe height and every run point at ``y = 0``.

    Parameters
    ----------
    grid_point_position, grid_point_kind, grid_point_moving_fraction : numpy.ndarray
        Length ``2N + 1`` (``Trace`` layout).
    end_to_elbow_cell_count, column_cell_count, ext_qty : int
    cell_length : float
        ``2 * celerity * dt``, m.
    portal_frame_height : float
        m.

    Returns
    -------
    LoopLayout
    """
    centreline_position = np.asarray(grid_point_position, dtype=np.float64)
    moving_fraction_array = np.asarray(grid_point_moving_fraction, dtype=np.float64)
    inlet_elbow_index, run_start_index, run_end_index, outlet_elbow_index = _segments(
        moving_fraction_array
    )
    grid_point_spacing = (
        float(centreline_position[1] - centreline_position[0])
        if centreline_position.shape[0] > 1
        else float(cell_length) / 2
    )
    inlet_elbow_position, run_start_position, run_end_position, outlet_elbow_position = (
        centreline_position[inlet_elbow_index],
        centreline_position[run_start_index],
        centreline_position[run_end_index],
        centreline_position[outlet_elbow_index],
    )
    run_length = float(run_end_position - run_start_position)
    inlet_leg_height = float(run_start_position - inlet_elbow_position)
    outlet_leg_height = float(outlet_elbow_position - run_end_position)
    x_at_rest = np.empty_like(centreline_position)
    y_at_rest = np.empty_like(centreline_position)
    on_inlet = centreline_position <= inlet_elbow_position
    on_inlet_leg = (centreline_position > inlet_elbow_position) & (
        centreline_position <= run_start_position
    )
    on_run = (centreline_position > run_start_position) & (centreline_position <= run_end_position)
    on_outlet_leg = (centreline_position > run_end_position) & (
        centreline_position <= outlet_elbow_position
    )
    on_outlet = centreline_position > outlet_elbow_position
    x_at_rest[on_inlet], y_at_rest[on_inlet] = (
        centreline_position[on_inlet] - inlet_elbow_position,
        inlet_leg_height,
    )  # leftwards, the elbow cell at x = 0
    x_at_rest[on_inlet_leg], y_at_rest[on_inlet_leg] = (
        0.0,
        inlet_leg_height - (centreline_position[on_inlet_leg] - inlet_elbow_position),
    )
    x_at_rest[on_run], y_at_rest[on_run] = centreline_position[on_run] - run_start_position, 0.0
    x_at_rest[on_outlet_leg], y_at_rest[on_outlet_leg] = (
        run_length,
        centreline_position[on_outlet_leg] - run_end_position,
    )
    x_at_rest[on_outlet], y_at_rest[on_outlet] = (
        run_length + (centreline_position[on_outlet] - outlet_elbow_position),
        outlet_leg_height,
    )
    return LoopLayout(
        cell_position=centreline_position,
        cell_kind=np.asarray(grid_point_kind),
        moving_fraction=moving_fraction_array,
        pivot_seg_qty=int(end_to_elbow_cell_count),
        pipe_seg_qty=int(column_cell_count),
        ext_qty=int(ext_qty),
        cell_length=float(cell_length),
        portal_height=float(portal_frame_height),
        spacing=grid_point_spacing,
        inlet_end=inlet_elbow_index,
        run_start=run_start_index,
        run_end=run_end_index,
        outlet_start=outlet_elbow_index,
        elbow_pairs=(
            (inlet_elbow_index, inlet_elbow_index + 1),
            (run_start_index - 1, run_start_index),
            (run_end_index, run_end_index + 1),
            (outlet_elbow_index - 1, outlet_elbow_index),
        ),
        x_nominal=x_at_rest,
        y_nominal=y_at_rest,
        run_length=run_length,
        leg_height=inlet_leg_height,
        leg_height_2=outlet_leg_height,
    )


def _moving_fractions_display(column_cell_count: int, end_to_elbow_cell_count: int):
    """``moc.moving_fractions`` with the solver's default profile, or, when
    ``pivotSegQTY = 4`` is refused (legacy: ``moving_fraction_b`` divides by zero, D-4;
    fixed: the port's ``pivot > ext`` guard), the legacy B profile with the ``n < extQTY``
    test; display only."""
    try:
        return moc.moving_fractions(column_cell_count, end_to_elbow_cell_count)
    except (ZeroDivisionError, ValueError):
        moving_fraction_a = np.zeros(column_cell_count + 1)
        moving_fraction_b = np.zeros(column_cell_count)
        for n in range(1, column_cell_count):
            moving_fraction_a[n] = moc.moving_fraction_a(
                n, end_to_elbow_cell_count, column_cell_count
            )
        for n in range(moc.INACTIVE_END_CELL_COUNT, column_cell_count):
            moving_fraction_b[n] = moc.moving_fraction_b(
                n, end_to_elbow_cell_count, column_cell_count
            )
        return moving_fraction_a, moving_fraction_b


def lumped_grid(
    inputs: dict, substep_duration: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int, float]:
    """The MoC grid a lumped case *would* have, for the lumped layout.

    Parameters
    ----------
    inputs : dict
        ``Trace.inputs`` (``physical_length``, ``flexural_rigidity_ei``,
        ``mass_per_unit_len``, ``nat_freq``, ``celerity``).
    substep_duration : float
        ``Trace.dt``, s.

    Returns
    -------
    cell_position, cell_kind, moving_fraction : numpy.ndarray
        Interleaved as ``Trace`` (``trace.interleave``).
    column_cell_count, end_to_elbow_cell_count : int
    portal_height : float
        m.
    """
    from surge_sdof.trace import interleave

    portal_frame_height = structure.solve_portal_height(
        inputs["physical_length"],
        inputs["flexural_rigidity_ei"],
        inputs["mass_per_unit_len"],
        inputs["nat_freq"],
    )
    column_cell_count, end_to_elbow_cell_count = moc.grid_size(
        inputs["physical_length"], portal_frame_height, inputs["celerity"], substep_duration
    )
    moving_fraction_a, moving_fraction_b = _moving_fractions_display(
        column_cell_count, end_to_elbow_cell_count
    )
    grid_point_count = 2 * column_cell_count + 1
    grid_point_position = np.arange(grid_point_count, dtype=np.float64) * (
        float(inputs["celerity"]) * float(substep_duration)
    )
    return (
        grid_point_position,
        np.arange(grid_point_count) % 2,
        interleave(moving_fraction_a, moving_fraction_b),
        column_cell_count,
        end_to_elbow_cell_count,
        portal_frame_height,
    )


def layout_from_trace(trace: Trace) -> LoopLayout:
    """The ``LoopLayout`` of a trace: a JC trace's own grid, or ``lumped_grid`` for a lumped
    one.

    Parameters
    ----------
    trace : Trace

    Returns
    -------
    LoopLayout
    """
    inputs = trace.inputs
    cell_length = 2.0 * float(inputs["celerity"]) * float(trace.dt)
    if trace.p_cells is not None:
        portal_frame_height = structure.solve_portal_height(
            inputs["physical_length"],
            inputs["flexural_rigidity_ei"],
            inputs["mass_per_unit_len"],
            inputs["nat_freq"],
        )
        return loop_layout(
            trace.cell_position,
            trace.cell_kind,
            trace.moving_fraction,
            trace.pivot_seg_qty,
            trace.pipe_seg_qty,
            trace.ext_qty,
            cell_length,
            portal_frame_height,
        )
    (
        grid_point_position,
        grid_point_kind,
        grid_point_moving_fraction,
        column_cell_count,
        end_to_elbow_cell_count,
        portal_frame_height,
    ) = lumped_grid(inputs, trace.dt)
    return loop_layout(
        grid_point_position,
        grid_point_kind,
        grid_point_moving_fraction,
        end_to_elbow_cell_count,
        column_cell_count,
        moc.INACTIVE_END_CELL_COUNT,
        cell_length,
        portal_frame_height,
    )
