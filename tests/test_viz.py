"""Session V.2: the model animation (``surge_sdof.viz.animate``).

The figure is built from traced runs of one lumped and one JC golden case at a coarse
stride; nothing here touches the solvers.
"""

from __future__ import annotations

import functools

import numpy as np
import pytest
import test_golden as tg

from surge_sdof import moc, response, structure
from surge_sdof.trace import PHASE_FREE_DECAY

pytest.importorskip("plotly")  # the ``viz`` extra
pytest.importorskip("pandas")

from surge_sdof.viz import animate  # noqa: E402

LUMPED_ID = "r020_lumped_L3_f2"
JC_ID = "r096_jc_L24_f3"
# The lumped case runs on its full history (25135 samples, ~200 traced frames at this
# stride); the JC case on the first JC_SAMPLES samples of its history (same inputs and grid,
# 1333 cells) so the pure-Python mode (NUMBA_DISABLE_JIT=1) stays at seconds, not minutes.
LUMPED_STRIDE = 5000
JC_SAMPLES = 500
JC_STRIDE = 100


@functools.cache
def golden_result(case_id):
    params = tg.load_params()
    case = next(c for c in tg.load_cases() if c["case_id"] == case_id)
    force = tg.load_force(params)
    kw = tg.case_params(case, params)
    if case["solver"] == "jc":
        return response.peak_response_jc(force[:JC_SAMPLES], **kw, trace_every=JC_STRIDE)
    return response.peak_response(force, **kw, trace_every=LUMPED_STRIDE)


@functools.cache
def figure(case_id, max_frames):
    return animate.build_figure(golden_result(case_id), case_name=case_id, max_frames=max_frames)


# trace indices: centreline 0, circles 1, friction 2 (drawn under), unbalance 3, cursor 4, status 5
CENTRELINE, CIRCLES, FRICTION, UNBALANCE, CURSOR, STATUS = 0, 1, 2, 3, 4, 5


def _circle_frames(fig):
    """Per animation frame: the circle x array and the cursor x array."""
    return [(f.data[0], f.data[1]) for f in fig.frames]


def _example_jc_result():
    case = next(c for c in tg.load_example_cases() if c["case_id"] == "example_jc")
    force = np.asarray(case["force_history"], dtype=float)
    return response.peak_response_jc(force, **case["kwargs"], trace_every=4)


def _frame_t(frame) -> float:
    """The frame time from its status text (frames carry no layout)."""
    return float(frame.data[2].text[0].split("t = ")[1].split(" s")[0])


@pytest.mark.parametrize("case_id", [LUMPED_ID, JC_ID])
def test_figure_builds_with_few_frames(case_id):
    fig, info = figure(case_id, 12)
    assert info.n_frames <= 12
    assert len(fig.frames) == info.n_frames
    assert len(fig.layout.sliders[0].steps) == info.n_frames
    n_cells = info.layout.n_cells
    assert len(fig.data[CIRCLES].x) == n_cells == len(fig.data[CIRCLES].y)
    # every frame lists every trace (the static ones with an empty update) so plotly.js keeps
    # every subplot layer under ``redraw: false`` (V.2e / V.2f, docs/viz/diagnosis.md)
    assert {tuple(f.traces) for f in fig.frames} == {
        (CIRCLES, CURSOR, STATUS, CENTRELINE, FRICTION, UNBALANCE)
    }
    assert all(f.data[3].to_plotly_json() == {"type": "scatter"} for f in fig.frames)
    # no layout change per frame (it would force a redraw and the lines would flicker)
    assert all(f.layout.title.text is None for f in fig.frames)
    assert all(step["args"][1]["frame"]["redraw"] is False for step in fig.layout.sliders[0].steps)
    for circles, cursor in _circle_frames(fig):
        assert len(circles.x) == n_cells
        assert len(cursor.x) == 2 and cursor.x[0] == cursor.x[1]
    assert info.solver == golden_result(case_id).trace.solver


@pytest.mark.parametrize("case_id", [LUMPED_ID, JC_ID])
def test_synthetic_frame_0_is_at_rest(case_id):
    fig, info = figure(case_id, 12)
    circles, cursor = _circle_frames(fig)[0]
    layout = info.layout
    assert _frame_t(fig.frames[0]) == 0.0
    assert cursor.x[0] == 0.0
    # offsets exactly zero: the circles sit at their nominal positions
    assert np.array_equal(
        np.asarray(circles.x, dtype=np.float64), layout.x_nominal.astype(np.float32)
    )
    if circles.marker is not None and circles.marker.size is not None:
        assert np.all(np.asarray(circles.marker.size) == np.float32(info.nominal_size))
        assert np.all(np.asarray(circles.marker.color) == 0.0)
        assert np.all(np.asarray(circles.customdata) == info.p_ref)


def test_lumped_size_and_colour_are_constant():
    fig, info = figure(LUMPED_ID, 12)
    assert fig.data[CIRCLES].marker.size == info.nominal_size
    assert fig.data[CIRCLES].marker.color == animate.COLOUR_MID
    assert (
        fig.data[CIRCLES].marker.colorbar is None
        or fig.data[CIRCLES].marker.colorbar.title.text is None
    )
    for circles, _cursor in _circle_frames(fig):
        assert circles.marker is None or (
            circles.marker.size is None and circles.marker.color is None
        )
        assert circles.customdata is None
    # and the circles do move
    moved = [np.asarray(c.x) for c, _ in _circle_frames(fig)]
    assert any(not np.array_equal(moved[0], m) for m in moved[1:])


def test_jc_size_and_colour_follow_the_scalings():
    fig, info = figure(JC_ID, 12)
    tr = golden_result(JC_ID).trace
    sizes = np.concatenate([np.asarray(c.marker.size) for c, _ in _circle_frames(fig)[1:]])
    colours = np.concatenate([np.asarray(c.marker.color) for c, _ in _circle_frames(fig)[1:]])
    assert sizes.min() >= np.float32(animate.SIZE_FLOOR * info.nominal_size)
    assert sizes.max() <= np.float32(animate.MAX_SIZE_RATIO * info.nominal_size) * (1 + 1e-6)
    assert np.abs(colours).max() <= np.float32(info.v_scale) * (1 + 1e-6)
    # over the whole trace the largest circle is exactly 2x nominal
    full = info.nominal_size * (1 + info.k_p * (tr.p_cells - info.p_ref) / info.p_scale)
    assert full.max() == pytest.approx(animate.MAX_SIZE_RATIO * info.nominal_size)
    assert info.v_scale == np.abs(tr.v_cells).max()
    assert fig.data[CIRCLES].marker.cmin == -info.v_scale
    assert fig.data[CIRCLES].marker.cmax == info.v_scale
    assert fig.data[CIRCLES].marker.colorbar.title.text == "relative fluid velocity (JC arrays)"


@pytest.mark.parametrize("max_frames", [3, 7, 12, 50, 400])
def test_frame_count_respects_the_cap(max_frames):
    for case_id in (LUMPED_ID, JC_ID):
        n_trace = golden_result(case_id).trace.n_frames
        idx, stride = animate.select_frames(n_trace, max_frames)
        assert 1 + len(idx) <= max_frames
        assert idx[0] == 0 and idx[-1] == n_trace - 1
        assert np.all(np.diff(idx) > 0)
        assert np.all(np.diff(idx)[:-1] == stride)
    fig, info = figure(LUMPED_ID, max_frames)
    assert info.n_frames <= max_frames
    assert info.n_frames == len(fig.frames)


def test_select_frames_uses_stride_1_when_everything_fits():
    idx, stride = animate.select_frames(10, 400)
    assert stride == 1 and list(idx) == list(range(10))
    with pytest.raises(ValueError):
        animate.select_frames(0, 400)
    with pytest.raises(ValueError):
        animate.select_frames(10, 2)


@pytest.mark.parametrize("case_id", [LUMPED_ID, JC_ID])
def test_last_frame_cursor_is_the_last_traced_time(case_id):
    fig, info = figure(case_id, 12)
    tr = golden_result(case_id).trace
    _circles, cursor = _circle_frames(fig)[-1]
    assert cursor.x[0] == np.float32(tr.t[-1])
    assert _frame_t(fig.frames[-1]) == pytest.approx(tr.t[-1], abs=5e-5)
    # the slider's last step and the time axis end there too
    assert fig.layout.sliders[0].steps[-1].label == f"{tr.t[-1]:.3f}"
    assert fig.layout.xaxis2.range[1] == tr.t[-1]


def test_exaggeration_draws_the_peak_as_a_tenth_of_the_run():
    for case_id in (LUMPED_ID, JC_ID):
        fig, info = figure(case_id, 12)
        tr = golden_result(case_id).trace
        assert abs(info.x_peak) == np.abs(tr.x).max()
        assert info.t_peak == tr.t[np.argmax(np.abs(tr.x))]
        assert abs(info.x_peak) * info.exaggeration == pytest.approx(
            animate.PEAK_FRACTION * info.layout.run_length
        )
        # the frame's offsets are x(t) * fraction * exaggeration
        i = int(np.argmax(np.abs(tr.x)))
        idx, _stride = animate.select_frames(tr.n_frames, 12)
        if i in idx:
            j = int(np.flatnonzero(idx == i)[0]) + 1
            expected = (
                info.layout.x_nominal + tr.x[i] * info.layout.moving_fraction * info.exaggeration
            )
            assert np.allclose(np.asarray(fig.frames[j].data[0].x), expected, rtol=1e-6, atol=1e-6)


@pytest.mark.parametrize("which", ["lumped", "jc", "example_jc"])
def test_loop_layout_geometry(which):
    """Fraction-0 cells at their pipe height, fraction-1 cells on the run, uniform spacing
    along the centreline, four elbows with distinct cells either side."""
    res = golden_result(LUMPED_ID if which == "lumped" else JC_ID)
    if which == "example_jc":
        res = _example_jc_result()
    tr = res.trace
    layout = animate.layout_from_trace(tr)
    frac = layout.moving_fraction
    x, y = layout.x_nominal, layout.y_nominal
    zero = frac == 0.0
    one = frac == 1.0
    assert zero.any() and one.any()
    # every fraction-0 cell at the height of its pipe (inlet or outlet), exactly
    inlet = np.arange(layout.n_cells) <= layout.inlet_end
    outlet = np.arange(layout.n_cells) >= layout.outlet_start
    assert np.all(y[zero & inlet] == layout.leg_height)
    assert np.all(y[zero & outlet] == layout.leg_height_2)
    assert np.all(y[zero] == np.where(inlet[zero], layout.leg_height, layout.leg_height_2))
    # every fraction-1 cell on the run, exactly
    assert np.all(y[one] == 0.0)
    assert x[layout.run_start] == 0.0 and x[layout.run_end] == pytest.approx(layout.run_length)
    pos = layout.cell_position
    assert layout.run_length == pos[layout.run_end] - pos[layout.run_start]
    # the inlet extends left of leg 1 (the elbow cell at x = 0), the outlet right of leg 2
    assert np.all(x[inlet] <= 0) and np.all(np.diff(x[inlet]) > 0) and x[layout.inlet_end] == 0
    assert np.all(x[outlet] >= layout.run_length) and x[layout.outlet_start] == layout.run_length
    # sharp corners: the legs are vertical at x = 0 and x = run_length
    leg = ~(inlet | outlet) & ~one
    assert np.all((x[leg] == 0.0) | (x[leg] == layout.run_length))
    assert y[layout.inlet_end] == layout.leg_height == pos[layout.run_start] - pos[layout.inlet_end]
    assert (
        y[layout.outlet_start]
        == layout.leg_height_2
        == pos[layout.outlet_start] - pos[layout.run_end]
    )
    # uniform spacing along the whole centreline: consecutive cells exactly one spacing apart
    d = np.hypot(np.diff(x), np.diff(y))
    assert np.allclose(d, layout.spacing, rtol=1e-12, atol=0)
    # the four elbows: distinct cells at distinct 2-D positions, one spacing apart
    assert len(layout.elbow_pairs) == 4
    for a, b in layout.elbow_pairs:
        assert a != b
        assert (x[a], y[a]) != (x[b], y[b])
        assert np.hypot(x[a] - x[b], y[a] - y[b]) == pytest.approx(layout.spacing)
    assert layout.elbow_pairs[0] == (layout.inlet_end, layout.inlet_end + 1)
    assert layout.elbow_pairs[1] == (layout.run_start - 1, layout.run_start)
    assert layout.elbow_pairs[2] == (layout.run_end, layout.run_end + 1)
    assert layout.elbow_pairs[3] == (layout.outlet_start - 1, layout.outlet_start)
    assert layout.portal_height == structure.solve_portal_height(
        tr.inputs["physical_length"],
        tr.inputs["flexural_rigidity_ei"],
        tr.inputs["mass_per_unit_len"],
        tr.inputs["nat_freq"],
    )
    if tr.moving_fraction is not None:
        assert np.array_equal(layout.moving_fraction, tr.moving_fraction)


def test_example_jc_elbow_cells_are_distinct():
    """The item-4 check of Session V.2b, pinned: at each elbow of the Example JC case the two
    cells are distinct cells at distinct positions and fractions."""
    layout = animate.layout_from_trace(_example_jc_result().trace)
    assert layout.elbow_pairs == ((9, 10), (13, 14), (23, 24), (26, 27))
    for a, b in layout.elbow_pairs:
        assert layout.cell_position[a] != layout.cell_position[b]
        assert layout.moving_fraction[a] != layout.moving_fraction[b]
    assert layout.moving_fraction[9] == 0.0 and layout.moving_fraction[27] == 0.0
    assert layout.moving_fraction[14] == 1.0 and layout.moving_fraction[23] == 1.0


def test_zero_lines_coincide():
    """Both Panel 2 axes have symmetric ranges, so their zero lines are at the same height."""
    for case_id in (LUMPED_ID, JC_ID):
        fig, _info = figure(case_id, 5)
        lo, hi = fig.layout.yaxis2.range
        lo3, hi3 = fig.layout.yaxis3.range
        assert lo == -hi and hi > 0
        assert lo3 == -hi3 and hi3 > 0
        assert fig.data[UNBALANCE].yaxis == "y2" and fig.data[FRICTION].yaxis == "y3"
        assert "left axis" in fig.data[UNBALANCE].name
        assert "right axis" in fig.data[FRICTION].name
        # friction drawn first (under the load line), thinner and translucent
        assert FRICTION < UNBALANCE
        assert fig.data[FRICTION].line.width < fig.data[UNBALANCE].line.width
        assert fig.data[FRICTION].line.color.startswith("rgba(")
        tr = golden_result(case_id).trace
        assert hi == pytest.approx(1.06 * np.abs(tr.f_unbalance).max())
        assert hi3 == pytest.approx(1.06 * max(np.abs(tr.f_friction).max(), 0.0) or 1.06)
        cursor = fig.data[CURSOR]
        assert cursor.yaxis == "y2" and list(cursor.y) == [lo, hi]


def test_play_pause_and_typed_speed(tmp_path):
    fig, _info = figure(LUMPED_ID, 5)
    buttons = fig.layout.updatemenus[0].buttons
    assert [b.label for b in buttons] == ["▶ play", "❚❚ pause"]
    play = buttons[0].args[1]["frame"]
    assert play == {"duration": animate.FRAME_DURATION_MS, "redraw": False}
    assert fig.layout.sliders[0].steps
    # the page replaces the buttons with a typed speed (any positive multiplier), play, pause
    out = tmp_path / "a.html"
    animate.write_html(fig, out)
    html = out.read_text()
    assert '"updatemenus"' not in html
    assert 'type="number"' in html and "-speed" in html and "-play" in html and "-pause" in html
    assert f"var base = {animate.FRAME_DURATION_MS}" in html
    assert "redraw: false" in html and "{plot_id}" not in html
    assert len(fig.layout.updatemenus) == 1  # the figure itself is unchanged


def _window_shapes(fig):
    return [sh for sh in fig.layout.shapes if sh.fillcolor == animate.COLOUR_WINDOW]


def test_t_start_trims_leading_frames():
    res = golden_result(LUMPED_ID)
    tr = res.trace
    t0 = float(tr.t[len(tr.t) // 2])
    fig, info = animate.build_figure(res, max_frames=12, t_start=t0)
    assert info.n_frames <= 12
    ts = [_frame_t(f) for f in fig.frames]
    assert ts[0] == pytest.approx(t0, abs=5e-5) and min(ts) >= t0 - 5e-5
    assert fig.data[CURSOR].x[0] == t0
    # Panel 2 keeps the whole run; the animated window is shaded
    assert fig.layout.xaxis2.range[0] == 0.0 and fig.layout.xaxis2.range[1] == tr.t[-1]
    (win,) = _window_shapes(fig)
    assert win.x0 == t0 and win.x1 == tr.t[-1]
    assert _frame_t(fig.frames[-1]) == pytest.approx(tr.t[-1], abs=5e-5)
    with pytest.raises(ValueError):
        animate.build_figure(res, max_frames=12, t_start=tr.t[-1] + 1.0)


@pytest.mark.parametrize("case_id", [LUMPED_ID, JC_ID])
def test_time_window_animates_at_full_resolution(case_id):
    """A ``t_start .. t_end`` window: every frame inside it, stride 1 when the window's
    traced frames fit the cap, the cursor and status at the window's first frame, the whole
    run still on Panel 2 with the window shaded; no window, no shading."""
    res = golden_result(case_id)
    tr = res.trace
    i0, i1 = len(tr.t) // 3, len(tr.t) // 3 + 20
    t0, t1 = float(tr.t[i0]), float(tr.t[i1])
    fig, info = animate.build_figure(res, max_frames=400, t_start=t0, t_end=t1)
    assert info.frame_stride == 1 and info.n_frames == i1 - i0 + 1
    ts = np.array([_frame_t(f) for f in fig.frames])
    assert np.all(ts >= t0 - 5e-5) and np.all(ts <= t1 + 5e-5)
    assert np.allclose(ts, tr.t[i0 : i1 + 1], atol=5e-5)
    assert fig.data[CURSOR].x[0] == t0
    assert fig.data[STATUS].text[0].startswith(f"t = {t0:.4f} s")
    assert fig.layout.xaxis2.range == (0.0, tr.t[-1])
    (win,) = _window_shapes(fig)
    assert (win.x0, win.x1) == (t0, t1)
    assert "animated window" in fig.layout.title.text
    # the cap still holds inside a window
    fig_c, info_c = animate.build_figure(res, max_frames=8, t_start=t0, t_end=t1)
    assert info_c.n_frames <= 8 and _frame_t(fig_c.frames[-1]) == pytest.approx(t1, abs=5e-5)
    # t_end alone keeps the rest frame
    fig_e, info_e = animate.build_figure(res, max_frames=400, t_end=t1)
    assert _frame_t(fig_e.frames[0]) == 0.0 and info_e.n_frames == i1 + 2
    assert _window_shapes(fig_e)[0].x0 == 0.0
    # no window: no shading
    fig_f, _ = figure(case_id, 12)
    assert not _window_shapes(fig_f)
    with pytest.raises(ValueError):
        animate.build_figure(res, t_start=t1, t_end=t0)


def test_lumped_layout_is_the_grid_the_case_would_have():
    tr = golden_result(LUMPED_ID).trace
    layout = animate.layout_from_trace(tr)
    h = structure.solve_portal_height(
        tr.inputs["physical_length"],
        tr.inputs["flexural_rigidity_ei"],
        tr.inputs["mass_per_unit_len"],
        tr.inputs["nat_freq"],
    )
    n_seg, piv = moc.grid_size(tr.inputs["physical_length"], h, tr.inputs["celerity"], tr.dt)
    frac_a, frac_b = moc.interp_fractions(n_seg, piv)
    assert (layout.pipe_seg_qty, layout.pivot_seg_qty) == (n_seg, piv)
    assert layout.n_cells == 2 * n_seg + 1
    assert np.array_equal(layout.moving_fraction[0::2], frac_a)
    assert np.array_equal(layout.moving_fraction[1::2], frac_b)
    assert np.array_equal(layout.cell_kind, np.arange(2 * n_seg + 1) % 2)


def test_lumped_grid_survives_pivot_seg_qty_4():
    # D-4: interp_fraction_b divides by zero at pivotSegQTY = 4; the display profile must not
    frac_a, frac_b = animate._interp_fractions_display(20, 4)
    assert frac_a.shape == (21,) and frac_b.shape == (20,)
    assert np.all(frac_b[: moc.EXT_QTY] == 0) and frac_b[10] == 1.0
    with pytest.raises(ZeroDivisionError):
        moc.interp_fractions(20, 4)


def test_scalars_table_and_phase_bands():
    tr = golden_result(JC_ID).trace
    table = animate.scalars_table(tr)
    assert len(table) == tr.n_frames + 1
    assert table["t"].iloc[0] == 0.0 and table["trace_index"].iloc[0] == -1
    assert np.array_equal(table["t"].to_numpy()[1:], tr.t)
    assert np.array_equal(table["f_unbalance"].to_numpy()[1:], tr.f_unbalance)
    assert np.array_equal(table["f_friction"].to_numpy()[1:], tr.f_friction)
    bands = animate._phase_bands(table)
    assert bands[0][0] == 0.0 and bands[-1][1] == tr.t[-1]
    assert [b[2] for b in bands] == sorted({b[2] for b in bands})  # transit, history, (decay)
    for (_t0, t1, _p), (t0, _t1, _q) in zip(bands[:-1], bands[1:], strict=True):
        assert t0 == t1


def test_is_capped():
    res = golden_result(JC_ID)
    assert animate.is_capped(res) is False  # the truncated row 96 history ends in phase 1
    assert not np.any(res.trace.phase == PHASE_FREE_DECAY)
    # a run that decays past the window: the Example JC case with a long decay
    case = next(c for c in tg.load_example_cases() if c["case_id"] == "example_jc")
    force = np.asarray(case["force_history"], dtype=float)
    kw = dict(case["kwargs"], dynamic_fric=0.0, damping_percent=0.0)
    r = response.peak_response_jc(force, **kw, trace_every=20)
    assert np.any(r.trace.phase == PHASE_FREE_DECAY)
    assert animate.is_capped(r) is (
        int(r.trace.sample[r.trace.phase == PHASE_FREE_DECAY].min()) + r.free_decay_samples
        > 2 * r.trace.out_max
    )


def test_write_html_uses_the_cdn(tmp_path):
    fig, _info = figure(LUMPED_ID, 5)
    out = tmp_path / "a.html"
    animate.write_html(fig, out)
    html = out.read_text()
    assert "cdn.plot.ly" in html or "plotly-" in html.split("<script")[1][:200]
    assert out.stat().st_size < 1_000_000  # not the full library


def test_build_figure_needs_a_trace():
    res = response.peak_response(
        np.array([[0.0], [1.0], [1.0]]), 4, 10.0, 6.0, 1e7, 1200.0, 100.0, 0.5, 0.0, 2.0
    )
    with pytest.raises(ValueError):
        animate.build_figure(res)
