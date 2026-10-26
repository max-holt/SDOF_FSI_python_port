"""The expansion-loop geometry of a traced run (Session V.2b / V.2c, moved here in W.1).

``layout_from_trace(trace)`` lays the interleaved MoC column on the expansion loop the
animation draws and the data files describe (``docs/data_format.md``, ``trace.geometry``):
inlet pipe, leg down, run, return leg up, outlet pipe, the cells mapped by their moving
fraction (``_segments``: the fraction-1 block is the run, the last fraction-0 cell before it
and the first after it the upper elbows), uniform spacing by ``cell_position`` along the
centreline, sharp elbows (the model has no bends). A JC trace brings its own grid; a lumped
trace gets the grid the case would have (``lumped_grid``: ``moc.grid_size`` /
``moc.interp_fractions`` with the solver's default profile, F-4; a ``pivotSegQTY = 4`` grid,
refused by both profiles, gets the legacy B profile with the ``n < extQTY`` test, display
only). The rules and the pinning tests are described in
``docs/architecture.md`` ("the animation", Geometry) and ``tests/test_viz.py``.

Shared by ``surge_sdof.viz.animate`` (which re-exports these names) and ``surge_sdof.export``;
numpy only, no plotly.
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

    Attributes
    ----------
    cell_position, cell_kind, moving_fraction : numpy.ndarray
        As ``Trace`` (m along the column; 0 = A node / 1 = B cell; the interp fraction).
    pivot_seg_qty, pipe_seg_qty, ext_qty : int
        The grid (``moc.grid_size``, ``moc.EXT_QTY``).
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


def _segments(moving_fraction: np.ndarray) -> tuple[int, int, int, int]:
    """``(inlet_end, run_start, run_end, outlet_start)`` from the fraction profile: the
    fraction-1 block is the run; the last fraction-0 cell before it and the first after it
    are the upper elbows. With the F-4 profile both legs hold ``2 pivot - 10`` interleaved
    cells and every inlet / outlet cell has fraction 0; with the legacy profile the inlet
    leg is one cell longer and D-4's ``n < 3`` cell (B(3), fraction ``1 / (pivot - 4)^2``)
    is a moving cell on the horizontal inlet (B(4) = 0 is the last zero before the run)."""
    ones = np.flatnonzero(moving_fraction == 1.0)
    if ones.size == 0:
        raise ValueError("no fraction-1 cell: the profile has no run")
    run_start, run_end = int(ones[0]), int(ones[-1])
    before = np.flatnonzero(moving_fraction[:run_start] == 0.0)
    after = np.flatnonzero(moving_fraction[run_end + 1 :] == 0.0)
    if before.size == 0 or after.size == 0:
        raise ValueError("no fraction-0 cell at an end: the profile has no inlet or outlet")
    return int(before[-1]), run_start, run_end, run_end + 1 + int(after[0])


def loop_layout(
    cell_position: np.ndarray,
    cell_kind: np.ndarray,
    moving_fraction: np.ndarray,
    pivot_seg_qty: int,
    pipe_seg_qty: int,
    ext_qty: int,
    cell_length: float,
    portal_height: float,
) -> LoopLayout:
    """Lay the interleaved column on the expansion loop, uniformly by ``cell_position``.

    The centreline runs: inlet (horizontal, leftwards from the inlet elbow cell at ``(0,
    leg_height)``), leg 1 (down ``x = 0``), the run (``y = 0`` from ``x = 0`` to ``x =
    run_length``), leg 2 (up ``x = run_length``), outlet (horizontal, rightwards from the
    outlet elbow cell at ``(run_length, leg_height_2)``). The elbows are sharp corners at
    the elbow cells (``_segments``): the model has no bends, and the cells either side of
    a corner are one spacing from the corner cell along its two segments. A cell ``s``
    along the column is at centreline length ``s``, so every inlet / outlet cell is at its
    pipe height and every run cell at ``y = 0``.

    Parameters
    ----------
    cell_position, cell_kind, moving_fraction : numpy.ndarray
        Length ``2N + 1`` (``Trace`` layout).
    pivot_seg_qty, pipe_seg_qty, ext_qty : int
    cell_length : float
        ``2 * celerity * dt``, m.
    portal_height : float
        m.

    Returns
    -------
    LoopLayout
    """
    s = np.asarray(cell_position, dtype=np.float64)
    frac = np.asarray(moving_fraction, dtype=np.float64)
    inlet_end, run_start, run_end, outlet_start = _segments(frac)
    spacing = float(s[1] - s[0]) if s.shape[0] > 1 else float(cell_length) / 2
    s1, s2, s3, s4 = s[inlet_end], s[run_start], s[run_end], s[outlet_start]
    run_length = float(s3 - s2)
    height1 = float(s2 - s1)
    height2 = float(s4 - s3)
    x = np.empty_like(s)
    y = np.empty_like(s)
    inlet = s <= s1
    leg1 = (s > s1) & (s <= s2)
    run = (s > s2) & (s <= s3)
    leg2 = (s > s3) & (s <= s4)
    outlet = s > s4
    x[inlet], y[inlet] = s[inlet] - s1, height1  # leftwards, the elbow cell at x = 0
    x[leg1], y[leg1] = 0.0, height1 - (s[leg1] - s1)
    x[run], y[run] = s[run] - s2, 0.0
    x[leg2], y[leg2] = run_length, s[leg2] - s3
    x[outlet], y[outlet] = run_length + (s[outlet] - s4), height2
    return LoopLayout(
        cell_position=s,
        cell_kind=np.asarray(cell_kind),
        moving_fraction=frac,
        pivot_seg_qty=int(pivot_seg_qty),
        pipe_seg_qty=int(pipe_seg_qty),
        ext_qty=int(ext_qty),
        cell_length=float(cell_length),
        portal_height=float(portal_height),
        spacing=spacing,
        inlet_end=inlet_end,
        run_start=run_start,
        run_end=run_end,
        outlet_start=outlet_start,
        elbow_pairs=(
            (inlet_end, inlet_end + 1),
            (run_start - 1, run_start),
            (run_end, run_end + 1),
            (outlet_start - 1, outlet_start),
        ),
        x_nominal=x,
        y_nominal=y,
        run_length=run_length,
        leg_height=height1,
        leg_height_2=height2,
    )


def _interp_fractions_display(pipe_seg_qty: int, pivot_seg_qty: int):
    """``moc.interp_fractions`` with the solver's default profile, or, when
    ``pivotSegQTY = 4`` is refused (legacy: ``interp_fraction_b`` divides by zero, D-4;
    fixed: the port's ``pivot > ext`` guard), the legacy B profile with the ``n < extQTY``
    test; display only."""
    try:
        return moc.interp_fractions(pipe_seg_qty, pivot_seg_qty)
    except (ZeroDivisionError, ValueError):
        frac_a = np.zeros(pipe_seg_qty + 1)
        frac_b = np.zeros(pipe_seg_qty)
        for n in range(1, pipe_seg_qty):
            frac_a[n] = moc.interp_fraction_a(n, pivot_seg_qty, pipe_seg_qty)
        for n in range(moc.EXT_QTY, pipe_seg_qty):
            frac_b[n] = moc.interp_fraction_b(n, pivot_seg_qty, pipe_seg_qty)
        return frac_a, frac_b


def lumped_grid(
    inputs: dict, dt: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int, float]:
    """The MoC grid a lumped case *would* have, for the lumped layout.

    Parameters
    ----------
    inputs : dict
        ``Trace.inputs`` (``physical_length``, ``flexural_rigidity_ei``,
        ``mass_per_unit_len``, ``nat_freq``, ``celerity``).
    dt : float
        ``Trace.dt``, s.

    Returns
    -------
    cell_position, cell_kind, moving_fraction : numpy.ndarray
        Interleaved as ``Trace`` (``trace.interleave``).
    pipe_seg_qty, pivot_seg_qty : int
    portal_height : float
        m.
    """
    from surge_sdof.trace import interleave

    h = structure.solve_portal_height(
        inputs["physical_length"],
        inputs["flexural_rigidity_ei"],
        inputs["mass_per_unit_len"],
        inputs["nat_freq"],
    )
    pipe_seg_qty, pivot_seg_qty = moc.grid_size(
        inputs["physical_length"], h, inputs["celerity"], dt
    )
    frac_a, frac_b = _interp_fractions_display(pipe_seg_qty, pivot_seg_qty)
    n_cells = 2 * pipe_seg_qty + 1
    position = np.arange(n_cells, dtype=np.float64) * (float(inputs["celerity"]) * float(dt))
    return (
        position,
        np.arange(n_cells) % 2,
        interleave(frac_a, frac_b),
        pipe_seg_qty,
        pivot_seg_qty,
        h,
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
        h = structure.solve_portal_height(
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
            h,
        )
    position, kind, fraction, n_seg, pivot, h = lumped_grid(inputs, trace.dt)
    return loop_layout(position, kind, fraction, pivot, n_seg, moc.EXT_QTY, cell_length, h)
