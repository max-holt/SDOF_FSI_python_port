"""The model animation (Session V.2): two plotly panels driven by ``trace.Trace``.

``build_figure(result)`` takes the ``PeakResponse`` of a run made with ``trace_every > 0``
and returns a plotly figure with frames, a slider and play / pause:

* **Panel 1** lays the fluid column on a U (``u_layout``): the ``ext_qty`` fixed cells and
  the pivot ramp cells on each vertical leg, the run horizontal between the pivots, 1 m per
  m of ``cell_position``. Per frame each cell is a circle whose horizontal position is the
  nominal one plus ``x(t) * moving_fraction * exaggeration`` (the lumped-mass displacement
  scaled by the cell's reference-velocity correction fraction), whose size is scaled from
  the nominal by the cell pressure (largest circle of the run 2x nominal) and whose colour
  is the cell velocity on a diverging scale centred at zero. A lumped run uses the same U
  and fraction profile (rebuilt from the case inputs with ``moc.grid_size`` /
  ``moc.interp_fractions``) with constant size and the scale's grey midpoint.
* **Panel 2** plots the applied unbalance ``f_unbalance = F_A(t) - F_B(t - L/c)`` and the
  friction force ``f_friction`` against time over the whole trace, shades the phases
  (transit / history / free decay), marks the time of peak ``|x|`` and carries a cursor at
  the frame time.

Frame 0 is synthetic (``t = 0``: ``x = 0``, the column at rest, no forces) so playback
starts from rest; frame ``j >= 1`` is the traced frame ``(j - 1) * frame_stride``, the last
traced frame always included, ``frame_stride`` chosen so there are at most ``max_frames``
frames (``select_frames``). All the scalings are printed in the title and returned in an
``AnimationInfo``. ``write_html`` writes the standalone page with plotly.js from the CDN.
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
    "ULayout",
    "AnimationInfo",
    "u_layout",
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

PHASE_NAMES = {PHASE_TRANSIT: "transit", PHASE_HISTORY: "history", PHASE_FREE_DECAY: "free decay"}

# Diverging scale: blue (negative) - grey midpoint - red (positive); the midpoint is also the
# constant colour of a lumped run.
COLOUR_NEG = "#2a78d6"
COLOUR_MID = "#b9b8b2"
COLOUR_POS = "#d03b3b"
DIVERGING = [[0.0, COLOUR_NEG], [0.5, COLOUR_MID], [1.0, COLOUR_POS]]
COLOUR_UNBALANCE = "#2a78d6"
COLOUR_FRICTION = "#eb6834"
COLOUR_CURSOR = "#0b0b0b"
PHASE_FILL = {PHASE_TRANSIT: "#e8e7e3", PHASE_HISTORY: "#f6f6f4", PHASE_FREE_DECAY: "#e8e7e3"}

SIZE_FLOOR = 0.15
"""Smallest circle, as a fraction of the nominal size (a deep pressure trough stays visible)."""
PEAK_FRACTION = 0.1
"""The exaggeration makes the peak displacement this fraction of the run length."""
MAX_SIZE_RATIO = 2.0
"""The largest circle of the run is this many times the nominal size."""
BAND_LABEL_FRACTION = 0.03
"""A phase band is labelled only when it spans at least this fraction of the time axis."""


@dataclass(frozen=True)
class ULayout:
    """The column laid on the U (see the module docstring).

    Attributes
    ----------
    cell_position, cell_kind, moving_fraction : numpy.ndarray
        As ``Trace`` (m along the column; 0 = A node / 1 = B cell; the interp fraction).
    pivot_seg_qty, pipe_seg_qty, ext_qty : int
        The grid (``moc.grid_size``, ``moc.EXT_QTY``).
    cell_length : float
        ``2 * celerity * dt``, m (a cell; ``cell_position`` steps by half of it).
    portal_height : float
        ``structure.solve_portal_height`` of the case, m (the dashed line on the legs).
    x_nominal, y_nominal : numpy.ndarray
        Circle centres at rest, m: leg 1 at ``x = 0`` from ``y = leg_length`` (anchor end)
        down to the first pivot at the origin, the run along ``y = 0``, leg 2 at ``x =
        run_length`` up to ``y = leg_length``.
    run_length, leg_length : float
        ``(N - 2 piv) * cell_length`` and ``piv * cell_length``, m.
    """

    cell_position: np.ndarray
    cell_kind: np.ndarray
    moving_fraction: np.ndarray
    pivot_seg_qty: int
    pipe_seg_qty: int
    ext_qty: int
    cell_length: float
    portal_height: float
    x_nominal: np.ndarray
    y_nominal: np.ndarray
    run_length: float
    leg_length: float

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
    layout : ULayout
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
    layout: ULayout


# ------------------------------------------------------------------ geometry


def u_layout(
    cell_position: np.ndarray,
    cell_kind: np.ndarray,
    moving_fraction: np.ndarray,
    pivot_seg_qty: int,
    pipe_seg_qty: int,
    ext_qty: int,
    cell_length: float,
    portal_height: float,
) -> ULayout:
    """Lay the interleaved column on the U at 1 m per m of ``cell_position``.

    The pivots are the A nodes ``pivot_seg_qty`` and ``pipe_seg_qty - pivot_seg_qty``
    (interleaved indices ``2 piv`` and ``2 (N - piv)``), at ``s1 = piv * cell_length`` and
    ``s2 = (N - piv) * cell_length`` along the column. Leg 1 (``s <= s1``): ``x = 0``,
    ``y = s1 - s``; run: ``y = 0``, ``x = s - s1``; leg 2 (``s >= s2``): ``x = s2 - s1``,
    ``y = s - s2``. The ``ext_qty`` fixed cells sit at the far (anchor) ends of the legs.

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
    ULayout
    """
    s = np.asarray(cell_position, dtype=np.float64)
    s1 = pivot_seg_qty * cell_length
    s2 = (pipe_seg_qty - pivot_seg_qty) * cell_length
    run_length = s2 - s1
    x = np.where(s <= s1, 0.0, np.where(s >= s2, run_length, s - s1))
    y = np.where(s <= s1, s1 - s, np.where(s >= s2, s - s2, 0.0))
    return ULayout(
        cell_position=s,
        cell_kind=np.asarray(cell_kind),
        moving_fraction=np.asarray(moving_fraction, dtype=np.float64),
        pivot_seg_qty=int(pivot_seg_qty),
        pipe_seg_qty=int(pipe_seg_qty),
        ext_qty=int(ext_qty),
        cell_length=float(cell_length),
        portal_height=float(portal_height),
        x_nominal=x,
        y_nominal=y,
        run_length=float(run_length),
        leg_length=float(s1),
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


def layout_from_trace(trace: Trace) -> ULayout:
    """The ``ULayout`` of a trace: a JC trace's own grid, or ``lumped_grid`` for a lumped one.

    Parameters
    ----------
    trace : Trace

    Returns
    -------
    ULayout
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
        return u_layout(
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
    return u_layout(position, kind, fraction, pivot, n_seg, moc.EXT_QTY, cell_length, h)


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


def build_figure(
    result: PeakResponse,
    case_name: str = "",
    max_frames: int = MAX_FRAMES,
    nominal_size: float | None = None,
    frame_duration_ms: int = 60,
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
        Circle diameter at rest, px; None picks ``clip(1800 / n_cells, 5, 12)``.
    frame_duration_ms : int
        Playback frame duration.

    Returns
    -------
    fig : plotly.graph_objects.Figure
    info : AnimationInfo

    Raises
    ------
    ValueError
        The result has no trace.
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    trace = result.trace
    if trace is None:
        raise ValueError("the result has no trace; run the solver with trace_every > 0")
    layout = layout_from_trace(trace)
    jc = trace.p_cells is not None
    n_cells = layout.n_cells
    if nominal_size is None:
        nominal_size = _auto_nominal_size(n_cells)
    nominal_size = float(nominal_size)

    idx, frame_stride = select_frames(trace.n_frames, max_frames)
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

    # --- per-frame circle arrays (float32: plotly typed arrays, 4 bytes a value)
    frac = layout.moving_fraction
    x_nom = layout.x_nominal

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

    kind_name = np.where(layout.cell_kind == 0, "A node", "B cell")
    text = [
        f"cell {i} ({k}) at {s:.3g} m, fraction {f:.3g}"
        for i, (k, s, f) in enumerate(zip(kind_name, layout.cell_position, frac, strict=True))
    ]
    hover = "%{text}"
    if jc:
        hover += "<br>p = %{customdata:.4g} Pa<br>v = %{marker.color:.4g} m/s"
    hover += "<extra></extra>"

    first = circles(None)
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
        row_heights=[0.62, 0.38],
        vertical_spacing=0.14,
        subplot_titles=(
            "Fluid column on the U (circle x: mass displacement x fraction; "
            + ("size: pressure; colour: velocity)" if jc else "constant size and colour)"),
            "Applied unbalance F<sub>A</sub>(t) - F<sub>B</sub>(t - L/c) and friction force",
        ),
    )
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
    # portal-frame height and the anchors (dashed): the ext cells continue the leg above it
    for x0 in (0.0, layout.run_length):
        fig.add_shape(
            type="line",
            x0=x0 - 0.04 * layout.run_length,
            x1=x0 + 0.04 * layout.run_length,
            y0=layout.portal_height,
            y1=layout.portal_height,
            line={"color": "#52514e", "width": 1, "dash": "dash"},
            row=1,
            col=1,
        )
    fig.add_annotation(
        x=0.0,
        y=layout.portal_height,
        text=f"h = {layout.portal_height:.3g} m",
        showarrow=False,
        xanchor="right",
        xshift=-6,
        font={"size": 11, "color": "#52514e"},
        row=1,
        col=1,
    )

    # --- panel 2: the two force lines, phase bands, peak marker, cursor
    t_all = table["t"].to_numpy()
    fu = table["f_unbalance"].to_numpy()
    ff = table["f_friction"].to_numpy()
    y_lo = float(min(fu.min(), ff.min(), 0.0))
    y_hi = float(max(fu.max(), ff.max(), 0.0))
    pad = 0.06 * (y_hi - y_lo or 1.0)
    y_lo, y_hi = y_lo - pad, y_hi + pad
    fig.add_trace(
        go.Scatter(
            x=t_all,
            y=fu,
            mode="lines",
            line={"color": COLOUR_UNBALANCE, "width": 2},
            name="F<sub>A</sub>(t) - F<sub>B</sub>(t - L/c)",
            hovertemplate="t = %{x:.4g} s<br>unbalance = %{y:.4g} N<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=t_all,
            y=ff,
            mode="lines",
            line={"color": COLOUR_FRICTION, "width": 2},
            name="friction force",
            hovertemplate="t = %{x:.4g} s<br>friction = %{y:.4g} N<extra></extra>",
        ),
        row=2,
        col=1,
    )
    cursor_index = len(fig.data)
    fig.add_trace(
        go.Scatter(
            x=np.array([0.0, 0.0]),
            y=np.array([y_lo, y_hi]),
            mode="lines",
            line={"color": COLOUR_CURSOR, "width": 1.5},
            name="current time",
            hoverinfo="skip",
            showlegend=False,
        ),
        row=2,
        col=1,
    )
    t_span = float(t_all[-1] - t_all[0]) or 1.0
    for t0, t1, phase in _phase_bands(table):
        band = {
            "x0": t0,
            "x1": t1,
            "fillcolor": PHASE_FILL[phase],
            "opacity": 0.6,
            "layer": "below",
            "line_width": 0,
        }
        if (
            t1 - t0
        ) / t_span >= BAND_LABEL_FRACTION:  # a label needs room; the title names the phase
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

    # --- frames: the circles and the cursor; the title carries the frame time and phase
    def title_text(t: float, phase: int) -> str:
        head = f"{case_name} — {trace.solver}" if case_name else trace.solver
        lines = [
            f"<b>{head}</b>   t = {t:.4f} s   phase: {PHASE_NAMES[phase]}",
            f"displacement exaggeration ×{exaggeration:.3g} (peak |x| {abs(x_peak):.3g} m drawn as "
            f"{PEAK_FRACTION:.0%} of the {layout.run_length:.3g} m run); "
            + (
                f"size = nominal (1 + {k_p:.3g} (p - {p_ref:g}) / {p_scale:.3g} Pa), largest "
                f"{MAX_SIZE_RATIO:g}× nominal; colour = v / {v_scale:.3g} m/s"
                if jc
                else "constant size and colour (lumped model)"
            ),
            f"trace_every = {trace.trace_every} sub-steps, frame stride {frame_stride}, "
            f"{len(idx) + 1} frames, dt = {trace.dt:.3g} s"
            + ("; <b>trace capped by the history window</b>" if capped else ""),
        ]
        return "<br>".join(lines)

    frames = []
    slider_steps = []
    phase0 = _synthetic_phase(trace)
    frame_specs = [(None, 0.0, phase0)] + [
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
                ],
                traces=[0, cursor_index],
                name=name,
                layout=go.Layout(title={"text": title_text(t, phase)}),
            )
        )
        slider_steps.append(
            {
                "args": [
                    [name],
                    {
                        "frame": {"duration": 0, "redraw": True},
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
    x_margin = 0.12 * layout.run_length  # offsets reach 10 % of the run
    y_margin = 0.08 * max(layout.leg_length, layout.run_length)
    fig.update_xaxes(
        title_text="m",
        range=[-x_margin, layout.run_length + x_margin],
        constrain="domain",
        zeroline=False,
        row=1,
        col=1,
    )
    fig.update_yaxes(
        title_text="m",
        range=[-y_margin, layout.leg_length + y_margin],
        scaleanchor="x",
        scaleratio=1,
        constrain="domain",
        zeroline=False,
        row=1,
        col=1,
    )
    fig.update_xaxes(title_text="t (s)", range=[float(t_all[0]), float(t_all[-1])], row=2, col=1)
    fig.update_yaxes(title_text="force (N)", range=[y_lo, y_hi], row=2, col=1)
    fig.update_layout(
        title={"text": title_text(0.0, phase0), "x": 0.0, "xanchor": "left", "font": {"size": 13}},
        template="plotly_white",
        height=900,
        margin={"t": 150, "b": 90},
        legend={"orientation": "h", "y": 0.36, "x": 0.0, "xanchor": "left", "yanchor": "bottom"},
        hovermode="closest",
        updatemenus=[
            {
                "type": "buttons",
                "showactive": False,
                "x": 0.0,
                "y": -0.06,
                "xanchor": "left",
                "yanchor": "top",
                "direction": "left",
                "buttons": [
                    {
                        "label": "▶ play",
                        "method": "animate",
                        "args": [
                            None,
                            {
                                "frame": {"duration": frame_duration_ms, "redraw": True},
                                "fromcurrent": True,
                                "transition": {"duration": 0},
                            },
                        ],
                    },
                    {
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
                    },
                ],
            }
        ],
        sliders=[
            {
                "active": 0,
                "steps": slider_steps,
                "x": 0.14,
                "len": 0.86,
                "y": -0.06,
                "yanchor": "top",
                "pad": {"t": 0},
                "currentvalue": {"prefix": "t = ", "suffix": " s", "visible": True},
            }
        ],
    )
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


def write_html(fig, path) -> None:
    """Write the standalone page with plotly.js loaded from the CDN (never the full library,
    which is 3+ MB and must not be committed).

    Parameters
    ----------
    fig : plotly.graph_objects.Figure
    path : str or pathlib.Path
    """
    fig.write_html(str(path), include_plotlyjs="cdn", full_html=True, auto_play=False)
