"""The expansion-loop geometry of a traced run (``surge_sdof.viz.geometry``).

The layout tests of the retired ``tests/test_viz.py`` (Sessions V.2b / V.2c; the plotly
animation was removed in Session H.1, the viewer ``docs/viewer/`` draws this geometry from the
exported files). Traces come from one lumped and one JC golden case at a coarse stride;
nothing here touches the solvers.
"""

from __future__ import annotations

import functools

import numpy as np
import pytest
import test_golden as tg

from surge_sdof import moc, response, structure
from surge_sdof.viz import geometry

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


def _example_jc_result(**flags):
    case = next(c for c in tg.load_example_cases() if c["case_id"] == "example_jc")
    force = np.asarray(case["force_history"], dtype=float)
    return response.peak_response_jc(force, **case["kwargs"], trace_every=4, **flags)


@pytest.mark.parametrize("which", ["lumped", "jc", "example_jc"])
def test_loop_layout_geometry(which):
    """Fraction-0 cells at their pipe height, fraction-1 cells on the run, uniform spacing
    along the centreline, four elbows with distinct cells either side."""
    res = golden_result(LUMPED_ID if which == "lumped" else JC_ID)
    if which == "example_jc":
        res = _example_jc_result()
    tr = res.trace
    layout = geometry.layout_from_trace(tr)
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
    # N = 18, pivot = 7. F-4b profile (27 Oct): inlet_end = B(3) at 7, run_start =
    # A(pivot - 1) at 2 pivot - 2 = 12, run_end = A(N - pivot + 1) at 2N - 2 pivot + 2 = 24,
    # outlet_start = B(N - 4) at 2N - 7 = 29 (legs of 4 cells each, 8 fixed cells at each
    # end). The 26 Oct F-4 profile had run_end 22 and outlet_start 27 (equal legs, 10 fixed
    # cells at the outlet). Legacy profile: inlet_end = B(4) at 9, run_start = A(pivot) at
    # 14, run_end = B(N - pivot) at 23, outlet_start 27 (legs of 4 and 3 cells).
    layout = geometry.layout_from_trace(_example_jc_result().trace)
    assert layout.elbow_pairs == ((7, 8), (11, 12), (24, 25), (28, 29))
    assert layout.outlet_start - layout.run_end == layout.run_start - layout.inlet_end
    assert layout.inlet_end + 1 == len(layout.moving_fraction) - layout.outlet_start == 8
    for a, b in layout.elbow_pairs:
        assert layout.cell_position[a] != layout.cell_position[b]
        assert layout.moving_fraction[a] != layout.moving_fraction[b]
    assert layout.moving_fraction[7] == 0.0 and layout.moving_fraction[29] == 0.0
    legacy = geometry.layout_from_trace(_example_jc_result(fraction_profile="legacy").trace)
    assert legacy.elbow_pairs == ((9, 10), (13, 14), (23, 24), (26, 27))
    assert legacy.moving_fraction[9] == 0.0 and legacy.moving_fraction[27] == 0.0
    assert layout.moving_fraction[12] == 1.0 and layout.moving_fraction[24] == 1.0
    assert legacy.moving_fraction[14] == 1.0 and legacy.moving_fraction[23] == 1.0


def test_lumped_layout_is_the_grid_the_case_would_have():
    tr = golden_result(LUMPED_ID).trace
    layout = geometry.layout_from_trace(tr)
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
    # pivotSegQTY = 4 is refused by both profiles (fixed: the pivot > ext guard, F-4;
    # legacy: interp_fraction_b divides by zero, D-4); the display profile must not
    frac_a, frac_b = geometry._interp_fractions_display(20, 4)
    assert frac_a.shape == (21,) and frac_b.shape == (20,)
    assert np.all(frac_b[: moc.EXT_QTY] == 0) and frac_b[10] == 1.0
    with pytest.raises(ValueError):
        moc.interp_fractions(20, 4)
    with pytest.raises(ZeroDivisionError):
        moc.interp_fractions(20, 4, "legacy")
