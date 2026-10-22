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


def _circle_frames(fig):
    """Per animation frame: the circle x array and the cursor x array."""
    return [(f.data[0], f.data[1]) for f in fig.frames]


def _frame_t(frame) -> float:
    return float(frame.layout.title.text.split("t = ")[1].split(" s")[0])


@pytest.mark.parametrize("case_id", [LUMPED_ID, JC_ID])
def test_figure_builds_with_few_frames(case_id):
    fig, info = figure(case_id, 12)
    assert info.n_frames <= 12
    assert len(fig.frames) == info.n_frames
    assert len(fig.layout.sliders[0].steps) == info.n_frames
    n_cells = info.layout.n_cells
    assert len(fig.data[0].x) == n_cells == len(fig.data[0].y)
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
    assert fig.data[0].marker.size == info.nominal_size
    assert fig.data[0].marker.color == animate.COLOUR_MID
    assert fig.data[0].marker.colorbar is None or fig.data[0].marker.colorbar.title.text is None
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
    assert fig.data[0].marker.cmin == -info.v_scale and fig.data[0].marker.cmax == info.v_scale
    assert fig.data[0].marker.colorbar.title.text == "relative fluid velocity (JC arrays)"


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


def test_u_layout_geometry_jc():
    tr = golden_result(JC_ID).trace
    layout = animate.layout_from_trace(tr)
    cell = 2 * tr.inputs["celerity"] * tr.dt
    piv, n_seg = tr.pivot_seg_qty, tr.pipe_seg_qty
    assert layout.run_length == pytest.approx((n_seg - 2 * piv) * cell)
    assert layout.leg_length == pytest.approx(piv * cell)
    # the pivots (A nodes piv and N - piv) are the corners
    assert (layout.x_nominal[2 * piv], layout.y_nominal[2 * piv]) == (0.0, 0.0)
    assert layout.x_nominal[2 * (n_seg - piv)] == pytest.approx(layout.run_length)
    assert layout.y_nominal[2 * (n_seg - piv)] == 0.0
    # anchor ends at the top of the legs, ext cells included
    assert layout.y_nominal[0] == pytest.approx(layout.leg_length)
    assert layout.y_nominal[-1] == pytest.approx(layout.leg_length)
    assert np.all(layout.y_nominal[: 2 * piv + 1] >= 0) and np.all(
        layout.x_nominal[: 2 * piv + 1] == 0
    )
    run = slice(2 * piv, 2 * (n_seg - piv) + 1)
    assert np.all(layout.y_nominal[run] == 0)
    assert np.allclose(np.diff(layout.x_nominal[run]), cell / 2)
    assert layout.portal_height == structure.solve_portal_height(
        tr.inputs["physical_length"],
        tr.inputs["flexural_rigidity_ei"],
        tr.inputs["mass_per_unit_len"],
        tr.inputs["nat_freq"],
    )
    assert np.array_equal(layout.moving_fraction, tr.moving_fraction)


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
