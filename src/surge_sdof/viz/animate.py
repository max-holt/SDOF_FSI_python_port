"""The model animation (Session V.2): two plotly panels driven by ``trace.Trace``.

``build_figure(result)`` takes the ``PeakResponse`` of a run made with ``trace_every > 0``
and returns a plotly figure with frames, a slider and play / pause:

* **Panel 1** lays the fluid column on an expansion loop (``loop_layout``): inlet pipe,
  leg down, run, return leg up, outlet pipe, the cells mapped by their moving fraction
  (fraction 0 at each end = the horizontal inlet / outlet, 0 < fraction < 1 = the legs,
  fraction 1 = the run along ``y = 0``), uniform spacing by ``cell_position`` along the
  centreline, sharp elbows (the model has no bends). Per frame each cell is a circle whose horizontal position is the
  nominal one plus ``x(t) * moving_fraction * exaggeration`` (the lumped-mass displacement
  scaled by the cell's reference-velocity correction fraction), whose size is scaled from
  the nominal by the cell pressure (largest circle of the run 2x nominal) and whose colour
  is the cell velocity on a diverging scale centred at zero. A lumped run uses the same U
  and fraction profile (rebuilt from the case inputs with ``moc.grid_size`` /
  ``moc.interp_fractions``) with constant size and the scale's grey midpoint.
* **Panel 2** plots the applied unbalance ``f_unbalance = F_A(t) - F_B(t - L/c)`` (left
  axis) over the friction force ``f_friction`` (right axis, drawn first, thinner and
  translucent) against time over the whole trace, both axes symmetric so the zero lines
  coincide, shades the phases (transit / history / free decay), marks the time of peak
  ``|x|`` and carries a cursor at the frame time.

Frame 0 is synthetic (``t = 0``: ``x = 0``, the column at rest, no forces) so playback
starts from rest; frame ``j >= 1`` is the traced frame ``(j - 1) * frame_stride``, the last
traced frame always included, ``frame_stride`` chosen so there are at most ``max_frames``
frames (``select_frames``). ``t_start > 0`` trims the leading frames (and the synthetic
one). A frame changes only trace data (the circles, the cursor and a status text with the
frame time and phase), never the layout, so playback runs without redraws. The figure
carries plotly play (1x) / pause buttons; ``write_html`` replaces them on the page with a
typed playback speed (any positive multiplier of ``frame_duration_ms``), play and pause.
All the scalings are printed in the title and returned in an ``AnimationInfo``.
``write_html`` writes the standalone page with plotly.js from the CDN.
plotly and pandas (the ``viz`` extra) are imported inside the functions that need them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from surge_sdof import moc, structure
from surge_sdof.response import PeakResponse
from surge_sdof.trace import PHASE_FREE_DECAY, PHASE_HISTORY, PHASE_TRANSIT, Trace

__all__ = [
    "MAX_FRAMES",
    "PHASE_NAMES",
    "LoopLayout",
    "AnimationInfo",
    "loop_layout",
    "lumped_grid",
    "layout_from_trace",
    "select_frames",
    "scalars_table",
    "is_capped",
    "build_figure",
    "write_html",
]

MAX_FRAMES = 400
"""Default cap on the number of animation frames (the synthetic ``t = 0`` frame included)."""
FRAME_DURATION_MS = 40
"""Playback frame duration at 1x."""
SIZE_CAP_SPACING = 0.8
"""Nominal circle diameter is capped at this fraction of the on-screen cell spacing."""
SIZE_CAP_FLOOR_PX = 3.0
"""... but never below this many px (a 1333-cell column has sub-pixel spacing)."""
FIG_WIDTH, FIG_HEIGHT = 1200, 900
MARGIN = {"l": 80, "r": 170, "t": 150, "b": 110}
ROW_HEIGHTS = [0.62, 0.38]
VERTICAL_SPACING = 0.14

PHASE_NAMES = {PHASE_TRANSIT: "transit", PHASE_HISTORY: "history", PHASE_FREE_DECAY: "free decay"}

# Diverging scale: blue (negative) - grey midpoint - red (positive); the midpoint is also the
# constant colour of a lumped run.
COLOUR_NEG = "#2a78d6"
COLOUR_MID = "#b9b8b2"
COLOUR_POS = "#d03b3b"
DIVERGING = [[0.0, COLOUR_NEG], [0.5, COLOUR_MID], [1.0, COLOUR_POS]]
COLOUR_UNBALANCE = "#2a78d6"
COLOUR_FRICTION = "rgba(235, 104, 52, 0.55)"
COLOUR_CURSOR = "#0b0b0b"
PHASE_FILL = {PHASE_TRANSIT: "#e8e7e3", PHASE_HISTORY: "#f6f6f4", PHASE_FREE_DECAY: "#e8e7e3"}

SIZE_FLOOR = 0.15
"""Smallest circle, as a fraction of the nominal size (a deep pressure trough stays visible)."""
PEAK_FRACTION = 0.1
"""The exaggeration makes the peak displacement this fraction of the run length."""
MAX_SIZE_RATIO = 2.0
"""The largest circle of the run is this many times the nominal size."""
BAND_LABEL_FRACTION = 0.06
"""A phase band is labelled only when it spans at least this fraction of the time axis."""


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


@dataclass(frozen=True)
class AnimationInfo:
    """What ``build_figure`` chose; everything the title prints.

    Attributes
    ----------
    solver : str
        ``Trace.solver``.
    n_frames : int
        Animation frames, the synthetic ``t = 0`` frame included.
    frame_stride : int
        Traced frames per animation frame (``select_frames``).
    trace_every : int
        The solver's stride in sub-steps.
    exaggeration : float
        Displacement multiplier (peak ``|x|`` drawn as ``PEAK_FRACTION`` of the run).
    x_peak, t_peak : float
        Peak ``|x|`` (m, signed) and its time (s) over the trace.
    p_ref, p_scale, k_p : float
        Size scaling: ``size = nominal * (1 + k_p * (p - p_ref) / p_scale)``, Pa, Pa, -.
    v_scale : float
        ``max |v|`` over the trace, m/s (colour range ``-v_scale .. v_scale``).
    nominal_size : float
        Circle diameter at rest, px.
    capped : bool
        The run decayed past the traced history window (``is_capped``).
    layout : LoopLayout
    """

    solver: str
    n_frames: int
    frame_stride: int
    trace_every: int
    exaggeration: float
    x_peak: float
    t_peak: float
    p_ref: float
    p_scale: float
    k_p: float
    v_scale: float
    nominal_size: float
    capped: bool
    layout: LoopLayout


# ------------------------------------------------------------------ geometry


def _segments(moving_fraction: np.ndarray) -> tuple[int, int, int, int]:
    """``(inlet_end, run_start, run_end, outlet_start)`` from the fraction profile: the
    fraction-1 block is the run; the last fraction-0 cell before it and the first after it
    are the upper elbows (the node-centred B ramp starts at exactly 0 at ``n = extQTY``,
    D-4's ``n < 3`` cell sits one place earlier on the inlet)."""
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
    """``moc.interp_fractions``, or, when ``pivotSegQTY = 4`` divides by zero in
    ``interp_fraction_b`` (D-4), the B profile with the ``n < extQTY`` test; display only."""
    try:
        return moc.interp_fractions(pipe_seg_qty, pivot_seg_qty)
    except ZeroDivisionError:
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


# ------------------------------------------------------------------ frames and scalars


def select_frames(n_trace: int, max_frames: int = MAX_FRAMES) -> tuple[np.ndarray, int]:
    """Traced frame indices to animate and the stride between them.

    ``frame_stride = ceil(n_trace / (max_frames - 2))`` and the indices are ``0, stride,
    2 stride, ...`` plus the last traced frame, so that with the synthetic ``t = 0`` frame
    the animation has at most ``max_frames`` frames and ends at the last traced time.

    Parameters
    ----------
    n_trace : int
        ``Trace.n_frames`` (>= 1).
    max_frames : int
        >= 3.

    Returns
    -------
    indices : numpy.ndarray
        int, strictly increasing, ``indices[-1] == n_trace - 1``.
    frame_stride : int
    """
    if n_trace < 1:
        raise ValueError("the trace has no frames")
    if max_frames < 3:
        raise ValueError(f"max_frames must be >= 3, got {max_frames}")
    stride = max(1, math.ceil(n_trace / (max_frames - 2)))
    idx = np.arange(0, n_trace, stride)
    if idx[-1] != n_trace - 1:
        idx = np.append(idx, n_trace - 1)
    return idx, stride


def _synthetic_phase(trace: Trace) -> int:
    """Phase of the ``t = 0`` frame: transit, unless the run has no transit sub-step."""
    if trace.n_frames and trace.sub_step[0] == 0 and trace.phase[0] != PHASE_TRANSIT:
        return int(trace.phase[0])
    return PHASE_TRANSIT


def scalars_table(trace: Trace):
    """Per-frame scalars for Panel 2 as a pandas ``DataFrame``: a ``t = 0`` row (zeros,
    ``_synthetic_phase``) followed by every traced frame.

    Columns ``t`` (s), ``phase`` (int), ``phase_name``, ``x`` (m), ``f_unbalance`` (N),
    ``f_friction`` (N), ``trace_index`` (-1 for the synthetic row).

    Parameters
    ----------
    trace : Trace

    Returns
    -------
    pandas.DataFrame
    """
    import pandas as pd

    table = pd.DataFrame(
        {
            "t": np.concatenate([[0.0], trace.t]),
            "phase": np.concatenate([[_synthetic_phase(trace)], trace.phase]).astype(int),
            "x": np.concatenate([[0.0], trace.x]),
            "f_unbalance": np.concatenate([[0.0], trace.f_unbalance]),
            "f_friction": np.concatenate([[0.0], trace.f_friction]),
            "trace_index": np.concatenate([[-1], np.arange(trace.n_frames)]).astype(int),
        }
    )
    table["phase_name"] = table["phase"].map(PHASE_NAMES)
    return table


def is_capped(result: PeakResponse) -> bool:
    """True when the run decayed past the traced history window (``trace.py``: free decay
    is traced while ``sample < 2 * out_max``), so the trace ends before the run did.

    Parameters
    ----------
    result : PeakResponse
        With a trace.
    """
    trace = result.trace
    decay = trace.phase == PHASE_FREE_DECAY
    if not decay.any():
        return False
    forced_samples = int(trace.sample[decay].min())
    return forced_samples + int(result.free_decay_samples) > 2 * int(trace.out_max)


def _phase_bands(table) -> list[tuple[float, float, int]]:
    """``(t_start, t_end, phase)`` of each run of equal phase in the scalar table."""
    phases = table["phase"].to_numpy()
    t = table["t"].to_numpy()
    starts = np.flatnonzero(np.diff(phases) != 0) + 1
    bounds = np.concatenate([[0], starts, [len(t)]])
    bands = []
    for lo, hi in zip(bounds[:-1], bounds[1:], strict=True):
        t_end = t[hi] if hi < len(t) else t[-1]
        bands.append((float(t[lo]), float(t_end), int(phases[lo])))
    return bands


def _auto_nominal_size(n_cells: int) -> float:
    return float(np.clip(1800.0 / n_cells, 5.0, 12.0))


def _fmt(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}g}"


# ------------------------------------------------------------------ the figure


def _status_text(t: float, phase: int) -> str:
    """The per-frame status shown in Panel 1 (a text trace, so a frame never touches the
    layout)."""
    return f"t = {t:.4f} s   phase: {PHASE_NAMES[phase]}"


def _px_per_m(x_range: float, y_range: float) -> float:
    """Estimated on-screen scale of Panel 1 for the fixed figure size (``constrain =
    "domain"`` with equal aspect: the smaller of the two axis scales)."""
    plot_w = FIG_WIDTH - MARGIN["l"] - MARGIN["r"]
    plot_h = (FIG_HEIGHT - MARGIN["t"] - MARGIN["b"]) * ROW_HEIGHTS[0] * (1 - VERTICAL_SPACING)
    return min(plot_w / x_range, plot_h / y_range)


def build_figure(
    result: PeakResponse,
    case_name: str = "",
    max_frames: int = MAX_FRAMES,
    nominal_size: float | None = None,
    frame_duration_ms: int = FRAME_DURATION_MS,
    t_start: float = 0.0,
):
    """Build the two-panel animation of a traced run.

    Parameters
    ----------
    result : PeakResponse
        From ``peak_response`` / ``peak_response_jc`` with ``trace_every > 0``.
    case_name : str
        For the title.
    max_frames : int
        Cap on the animation frames (``select_frames``), default ``MAX_FRAMES``.
    nominal_size : float or None
        Circle diameter at rest, px; None picks ``clip(1800 / n_cells, 5, 12)``. Either way
        it is capped at ``SIZE_CAP_SPACING`` of the on-screen cell spacing (estimated for
        the fixed figure size), but not below ``SIZE_CAP_FLOOR_PX``.
    frame_duration_ms : int
        Playback frame duration at 1x (the page's typed speed divides it).
    t_start : float
        Traced frames before this time (s) are left out; with ``t_start > 0`` there is no
        synthetic rest frame.

    Returns
    -------
    fig : plotly.graph_objects.Figure
    info : AnimationInfo

    Raises
    ------
    ValueError
        The result has no trace, or ``t_start`` leaves no frame.
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    trace = result.trace
    if trace is None:
        raise ValueError("the result has no trace; run the solver with trace_every > 0")
    layout = layout_from_trace(trace)
    jc = trace.p_cells is not None
    n_cells = layout.n_cells
    x_nom = layout.x_nominal
    frac = layout.moving_fraction

    # frames to animate
    kept = np.flatnonzero(trace.t >= t_start)
    if kept.size == 0:
        raise ValueError(f"t_start = {t_start} leaves no traced frame (last t {trace.t[-1]})")
    with_rest = t_start <= 0.0
    sel, frame_stride = select_frames(kept.size, max_frames - (1 if with_rest else 0) + 1)
    idx = kept[sel]
    table = scalars_table(trace)
    capped = is_capped(result)

    # --- scalings over the whole trace
    i_peak = int(np.argmax(np.abs(trace.x)))
    x_peak = float(trace.x[i_peak])
    t_peak = float(trace.t[i_peak])
    exaggeration = PEAK_FRACTION * layout.run_length / abs(x_peak) if x_peak != 0.0 else 1.0
    p_ref = 0.0
    if jc:
        dev = trace.p_cells - p_ref
        p_scale = float(np.max(np.abs(dev)))
        p_rise = float(np.max(dev))
        k_p = (MAX_SIZE_RATIO - 1.0) * p_scale / p_rise if p_rise > 0.0 else 1.0
        v_scale = float(np.max(np.abs(trace.v_cells)))
        if p_scale == 0.0:
            p_scale = 1.0
        if v_scale == 0.0:
            v_scale = 1.0
    else:
        p_scale, k_p, v_scale = 1.0, 1.0, 1.0

    # --- panel 1 extent (fixed, so the motion does not rescale it) and the size cap
    x_lo = float(x_nom.min()) - 0.12 * layout.run_length  # offsets reach 10 % of the run
    x_hi = float(x_nom.max()) + 0.12 * layout.run_length
    y_top = max(layout.leg_height, layout.leg_height_2)
    y_margin = 0.08 * max(y_top, layout.run_length)
    y_lo1, y_hi1 = -y_margin, y_top + y_margin
    px_per_m = _px_per_m(x_hi - x_lo, y_hi1 - y_lo1)
    size_cap = max(SIZE_CAP_FLOOR_PX, SIZE_CAP_SPACING * layout.spacing * px_per_m)
    if nominal_size is None:
        nominal_size = _auto_nominal_size(n_cells)
    nominal_size = float(min(nominal_size, size_cap))

    # --- per-frame circle arrays (float32: plotly typed arrays, 4 bytes a value)
    def circles(i_trace: int | None):
        if i_trace is None:
            x = x_nom.copy()
            p = np.zeros(n_cells)
            v = np.zeros(n_cells)
        else:
            x = x_nom + float(trace.x[i_trace]) * frac * exaggeration
            p = trace.p_cells[i_trace] if jc else None
            v = trace.v_cells[i_trace] if jc else None
        out = {"x": x.astype(np.float32)}
        if jc:
            size = nominal_size * (1.0 + k_p * (p - p_ref) / p_scale)
            size = np.maximum(size, SIZE_FLOOR * nominal_size)
            out["size"] = size.astype(np.float32)
            out["colour"] = v.astype(np.float32)
            out["p"] = p.astype(np.float32)
        return out

    segment = np.empty(n_cells, dtype=object)
    segment[:] = "leg"
    segment[: layout.inlet_end + 1] = "inlet"
    segment[layout.run_start : layout.run_end + 1] = "run"
    segment[layout.outlet_start :] = "outlet"
    kind_name = np.where(layout.cell_kind == 0, "A node", "B cell")
    text = [
        f"cell {i} ({k}, {seg}) at {s:.4g} m, fraction {f:.3g}"
        for i, (k, seg, s, f) in enumerate(
            zip(kind_name, segment, layout.cell_position, frac, strict=True)
        )
    ]
    hover = "%{text}"
    if jc:
        hover += "<br>p = %{customdata:.4g} Pa<br>v = %{marker.color:.4g} m/s"
    hover += "<extra></extra>"

    first_i = None if with_rest else int(idx[0])
    first = circles(first_i)
    marker = {
        "size": first["size"] if jc else nominal_size,
        "line": {"width": 0.5, "color": "#52514e"},
        "sizemode": "diameter",
    }
    if jc:
        ticks = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
        marker.update(
            color=first["colour"],
            colorscale=DIVERGING,
            cmin=-v_scale,
            cmax=v_scale,
            colorbar={
                "title": {"text": "relative fluid velocity (JC arrays)", "side": "right"},
                "tickvals": (ticks * v_scale).tolist(),
                "ticktext": [f"{tv * v_scale:.3g} m/s" for tv in ticks],
                "len": 0.55,
                "y": 0.78,
                "thickness": 14,
            },
        )
    else:
        marker["color"] = COLOUR_MID

    fig = make_subplots(
        rows=2,
        cols=1,
        row_heights=ROW_HEIGHTS,
        vertical_spacing=VERTICAL_SPACING,
        specs=[[{}], [{"secondary_y": True}]],
        subplot_titles=(
            "Expansion loop: inlet, leg, run, return leg, outlet (circle x: mass displacement "
            "x fraction; "
            + ("size: pressure; colour: velocity)" if jc else "constant size and colour)"),
            "Applied unbalance F<sub>A</sub>(t) - F<sub>B</sub>(t - L/c) (left) and friction force (right)",
        ),
    )
    # the centreline at rest, under the circles
    fig.add_trace(
        go.Scatter(
            x=x_nom,
            y=layout.y_nominal,
            mode="lines",
            line={"color": "#dcdbd6", "width": 1},
            hoverinfo="skip",
            showlegend=False,
            name="centreline",
        ),
        row=1,
        col=1,
    )
    circle_index = len(fig.data)
    fig.add_trace(
        go.Scatter(
            x=first["x"],
            y=layout.y_nominal.astype(np.float32),
            mode="markers",
            marker=marker,
            text=text,
            customdata=first["p"] if jc else None,
            hovertemplate=hover,
            name="cells",
            showlegend=False,
        ),
        row=1,
        col=1,
    )
    fig.add_annotation(
        x=x_lo,
        y=y_top,
        text=f"pipe height {layout.leg_height:.3g} m (h = {layout.portal_height:.3g} m)",
        showarrow=False,
        xanchor="left",
        yanchor="bottom",
        font={"size": 11, "color": "#52514e"},
        row=1,
        col=1,
    )

    # --- panel 2: friction (right axis) drawn first and translucent, under the unbalance
    # (left axis); symmetric ranges so the zero lines coincide
    t_all = table["t"].to_numpy()
    fu = table["f_unbalance"].to_numpy()
    ff = table["f_friction"].to_numpy()
    fu_max = float(np.max(np.abs(fu))) or 1.0
    ff_max = float(np.max(np.abs(ff))) or 1.0
    fu_lim = 1.06 * fu_max
    ff_lim = 1.06 * ff_max
    friction_index = len(fig.data)
    fig.add_trace(
        go.Scatter(
            x=t_all,
            y=ff,
            mode="lines",
            line={"color": COLOUR_FRICTION, "width": 1.5},
            name="friction force, right axis",
            legendrank=2,  # drawn first, listed second
            hovertemplate="t = %{x:.4g} s<br>friction = %{y:.4g} N<extra></extra>",
        ),
        row=2,
        col=1,
        secondary_y=True,
    )
    unbalance_index = len(fig.data)
    fig.add_trace(
        go.Scatter(
            x=t_all,
            y=fu,
            mode="lines",
            line={"color": COLOUR_UNBALANCE, "width": 2},
            name="F<sub>A</sub>(t) - F<sub>B</sub>(t - L/c), left axis",
            legendrank=1,
            hovertemplate="t = %{x:.4g} s<br>unbalance = %{y:.4g} N<extra></extra>",
        ),
        row=2,
        col=1,
        secondary_y=False,
    )
    cursor_index = len(fig.data)
    t_first = 0.0 if with_rest else float(trace.t[idx[0]])
    fig.add_trace(
        go.Scatter(
            x=np.array([t_first, t_first]),
            y=np.array([-fu_lim, fu_lim]),
            mode="lines",
            line={"color": COLOUR_CURSOR, "width": 1.5},
            name="current time",
            hoverinfo="skip",
            showlegend=False,
        ),
        row=2,
        col=1,
        secondary_y=False,
    )
    status_index = len(fig.data)
    phase0 = _synthetic_phase(trace)
    fig.add_trace(
        go.Scatter(
            x=[x_hi],
            y=[y_hi1],
            mode="text",
            text=[_status_text(0.0 if with_rest else float(trace.t[idx[0]]), phase0)],
            textposition="bottom left",
            textfont={"size": 14, "color": COLOUR_CURSOR},
            hoverinfo="skip",
            showlegend=False,
            name="status",
        ),
        row=1,
        col=1,
    )
    t_axis0 = float(t_all[0]) if with_rest else float(t_start)
    t_span = float(t_all[-1] - t_axis0) or 1.0
    for t0, t1, phase in _phase_bands(table):
        if t1 < t_axis0:
            continue
        band = {
            "x0": max(t0, t_axis0),
            "x1": t1,
            "fillcolor": PHASE_FILL[phase],
            "opacity": 0.6,
            "layer": "below",
            "line_width": 0,
        }
        if (t1 - max(t0, t_axis0)) / t_span >= BAND_LABEL_FRACTION:  # the title names the phase
            band.update(
                annotation_text=PHASE_NAMES[phase],
                annotation_position="top left",
                annotation_font={"size": 11, "color": "#52514e"},
            )
        fig.add_vrect(**band, row=2, col=1)
    fig.add_vline(
        x=t_peak,
        line={"color": "#52514e", "width": 1, "dash": "dot"},
        annotation_text=f"peak |x| = {abs(x_peak):.3g} m at t = {t_peak:.4g} s",
        annotation_position="bottom left" if t_peak > 0.5 * t_all[-1] else "bottom right",
        annotation_font={"size": 11, "color": "#52514e"},
        row=2,
        col=1,
    )

    # --- frames: the circles, the cursor and the status text; no layout change per frame
    # (a layout change forces a full redraw and the lines flicker)
    n_frames = len(idx) + (1 if with_rest else 0)

    def title_text() -> str:
        head = f"{case_name} — {trace.solver}" if case_name else trace.solver
        lines = [
            f"<b>{head}</b>",
            f"displacement exaggeration ×{exaggeration:.3g} (peak |x| {abs(x_peak):.3g} m drawn as "
            f"{PEAK_FRACTION:.0%} of the {layout.run_length:.3g} m run); "
            + (
                f"size = nominal (1 + {k_p:.3g} (p - {p_ref:g}) / {p_scale:.3g} Pa), largest "
                f"{MAX_SIZE_RATIO:g}× nominal; colour = v / {v_scale:.3g} m/s"
                if jc
                else "constant size and colour (lumped model)"
            ),
            f"trace_every = {trace.trace_every} sub-steps, frame stride {frame_stride}, "
            f"{n_frames} frames, dt = {trace.dt:.3g} s, nominal circle {nominal_size:.3g} px"
            + (f", frames from t = {t_start:g} s" if not with_rest else "")
            + ("; <b>trace capped by the history window</b>" if capped else ""),
        ]
        return "<br>".join(lines)

    frames = []
    slider_steps = []
    frame_specs = ([(None, 0.0, phase0)] if with_rest else []) + [
        (int(i), float(trace.t[i]), int(trace.phase[i])) for i in idx
    ]
    for j, (i_trace, t, phase) in enumerate(frame_specs):
        c = circles(i_trace)
        circle_update = {"x": c["x"]}
        if jc:
            circle_update["marker"] = {"size": c["size"], "color": c["colour"]}
            circle_update["customdata"] = c["p"]
        name = str(j)
        frames.append(
            go.Frame(
                data=[
                    go.Scatter(**circle_update),
                    go.Scatter(x=np.array([t, t], dtype=np.float32)),
                    go.Scatter(text=[_status_text(t, phase)]),
                ],
                traces=[circle_index, cursor_index, status_index],
                name=name,
            )
        )
        slider_steps.append(
            {
                "args": [
                    [name],
                    {
                        "frame": {"duration": 0, "redraw": False},
                        "mode": "immediate",
                        "transition": {"duration": 0},
                    },
                ],
                "label": f"{t:.3f}",
                "method": "animate",
            }
        )
    fig.frames = frames

    # --- layout
    fig.update_xaxes(
        title_text="m", range=[x_lo, x_hi], constrain="domain", zeroline=False, row=1, col=1
    )
    fig.update_yaxes(
        title_text="m",
        range=[y_lo1, y_hi1],
        scaleanchor="x",
        scaleratio=1,
        constrain="domain",
        zeroline=False,
        row=1,
        col=1,
    )
    fig.update_xaxes(title_text="t (s)", range=[t_axis0, float(t_all[-1])], row=2, col=1)
    fig.update_yaxes(
        title_text="unbalance (N)", range=[-fu_lim, fu_lim], row=2, col=1, secondary_y=False
    )
    fig.update_yaxes(
        title_text="friction (N)",
        range=[-ff_lim, ff_lim],
        showgrid=False,
        row=2,
        col=1,
        secondary_y=True,
    )
    play_button = {
        "label": "▶ play",
        "method": "animate",
        "args": [
            None,
            {
                "frame": {"duration": frame_duration_ms, "redraw": False},
                "fromcurrent": True,
                "transition": {"duration": 0},
            },
        ],
    }
    pause_button = {
        "label": "❚❚ pause",
        "method": "animate",
        "args": [
            [None],
            {
                "frame": {"duration": 0, "redraw": False},
                "mode": "immediate",
                "transition": {"duration": 0},
            },
        ],
    }
    fig.update_layout(
        title={
            "text": title_text(),
            "x": 0.0,
            "xanchor": "left",
            "font": {"size": 13},
        },
        template="plotly_white",
        width=FIG_WIDTH,
        height=FIG_HEIGHT,
        margin=MARGIN,
        legend={"orientation": "h", "y": 0.36, "x": 0.0, "xanchor": "left", "yanchor": "bottom"},
        hovermode="closest",
        updatemenus=[
            {
                "type": "buttons",
                "showactive": False,
                "x": 0.0,
                "y": -0.07,
                "xanchor": "left",
                "yanchor": "top",
                "direction": "left",
                "pad": {"r": 4},
                "buttons": [play_button, pause_button],
            }
        ],
        sliders=[
            {
                "active": 0,
                "steps": slider_steps,
                "x": 0.0,
                "len": 1.0,
                "y": -0.17,
                "yanchor": "top",
                "pad": {"t": 0},
                "currentvalue": {"prefix": "t = ", "suffix": " s", "visible": True},
            }
        ],
    )
    fig._surge_sdof_animation = {  # read by write_html for the page's speed control
        "frame_duration_ms": float(frame_duration_ms),
        "trace_indices": {
            "centreline": 0,
            "circles": circle_index,
            "friction": friction_index,
            "unbalance": unbalance_index,
            "cursor": cursor_index,
            "status": status_index,
        },
    }
    info = AnimationInfo(
        solver=trace.solver,
        n_frames=len(frames),
        frame_stride=frame_stride,
        trace_every=int(trace.trace_every),
        exaggeration=float(exaggeration),
        x_peak=x_peak,
        t_peak=t_peak,
        p_ref=p_ref,
        p_scale=float(p_scale),
        k_p=float(k_p),
        v_scale=float(v_scale),
        nominal_size=nominal_size,
        capped=capped,
        layout=layout,
    )
    return fig, info


SPEED_CONTROL_JS = """
(function () {
  var gd = document.getElementById('{plot_id}');
  var base = %(base)s;
  var row = document.createElement('div');
  row.style.cssText = 'font: 13px sans-serif; color: #52514e; margin: 4px 0 12px 80px;';
  row.innerHTML = 'playback speed &times;<input id="{plot_id}-speed" type="number" value="1" '
    + 'min="0.001" step="any" style="width: 6em; margin: 0 8px 0 2px;">'
    + '<button id="{plot_id}-play" style="margin-right: 4px;">&#9654; play</button>'
    + '<button id="{plot_id}-pause">&#10074;&#10074; pause</button>'
    + ' <span>(1&times; = ' + base + ' ms a frame; retype and press play to change speed while playing)</span>';
  gd.parentNode.insertBefore(row, gd.nextSibling);
  function speed() {
    var v = parseFloat(document.getElementById('{plot_id}-speed').value);
    return (isFinite(v) && v > 0) ? v : 1;
  }
  document.getElementById('{plot_id}-play').onclick = function () {
    Plotly.animate(gd, null, {
      frame: {duration: base / speed(), redraw: false},
      fromcurrent: true, mode: 'immediate', transition: {duration: 0}
    });
  };
  document.getElementById('{plot_id}-pause').onclick = function () {
    Plotly.animate(gd, [null], {
      frame: {duration: 0, redraw: false}, mode: 'immediate', transition: {duration: 0}
    });
  };
})();
"""


def write_html(fig, path) -> None:
    """Write the standalone page with plotly.js loaded from the CDN (never the full library,
    which is 3+ MB and must not be committed).

    The page gets a typed playback speed (any positive multiplier of the base frame
    duration) with play and pause buttons under the figure (``SPEED_CONTROL_JS``, run after
    the plot is made) in place of the figure's own play / pause buttons, which are removed
    from the written copy.

    Parameters
    ----------
    fig : plotly.graph_objects.Figure
        From ``build_figure``.
    path : str or pathlib.Path
    """
    import plotly.graph_objects as go

    meta = getattr(fig, "_surge_sdof_animation", None)
    base = meta["frame_duration_ms"] if meta else float(FRAME_DURATION_MS)
    page = go.Figure(fig)
    page.layout.updatemenus = []
    page.write_html(
        str(path),
        include_plotlyjs="cdn",
        full_html=True,
        auto_play=False,
        post_script=SPEED_CONTROL_JS % {"base": f"{base:g}"},
    )
