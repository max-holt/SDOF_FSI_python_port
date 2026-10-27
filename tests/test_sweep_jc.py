"""Session 5b: ``tools/sweep_jc.py`` (the pipe table, the case grid, the CSV round trip)."""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]


def _load_tool():
    spec = importlib.util.spec_from_file_location("sweep_jc", REPO / "tools" / "sweep_jc.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sw = _load_tool()


def test_pipe_table_reproduces_the_owners_design_pressures_and_the_10in_fixture():
    sw.check_pipe_table(verbose=False)
    params = json.loads((REPO / "tests/fixtures/curve_10in/params.json").read_text())
    p10 = sw.pipe(10)
    assert math.isclose(p10.fluid_area, params["fluid_area"], rel_tol=1e-12)
    assert math.isclose(p10.mass_per_unit_len, params["mass_per_unit_len"], rel_tol=1e-12)
    assert math.isclose(p10.ei, params["flexural_rigidity_ei"], rel_tol=1e-12)
    for size, bar in sw.P_DESIGN_EXPECTED_BAR.items():
        assert abs(sw.pipe(size).p_design / 1e5 - bar) <= 0.1


def test_tier_grids():
    t1 = sw.tier_cases(1)
    assert len(t1) == 2 * 5 * 8 * (1 + 3 + 1) * 2 * 2
    assert len({c.case_id for c in t1}) == len(t1)
    t2 = sw.tier_cases(2)
    assert len(sw.curve_sheet_nat_freqs()) == 15
    assert len(t2) == 4 * 5 * 15 * (1 + 5 + 3) * 3 * 3


def test_stratified_subset_covers_every_level_of_every_dimension():
    cases = sw.tier_cases(1)
    sub = sw.stratified_subset(cases, 0.1)
    assert len(sub) == math.ceil(0.1 * len(cases))
    full = sw.coverage(cases)
    part = sw.coverage(sub)
    for dim, levels in full.items():
        assert set(part[dim]) == set(levels), dim
        counts = part[dim].values()
        assert max(counts) - min(counts) <= 4, (dim, part[dim])
    # deterministic and in grid order
    assert sub == sw.stratified_subset(cases, 0.1)
    assert [cases.index(c) for c in sub] == sorted(cases.index(c) for c in sub)


@pytest.mark.parametrize("kind", ["step", "step_sine", "step_noise"])
def test_run_case_fills_the_row_and_the_history_rebuilds_from_it(kind, tmp_path):
    cases = [c for c in sw.tier_cases(1) if c.history_type == kind and c.nat_freq_hz == 24.0]
    case = cases[0]
    row = sw.run_case(case, 1, "test", "cpu", "sha")
    assert set(row) == set(sw.COLUMNS)
    assert row["error"] is None
    assert row["jc_short_pipe"] == 0
    assert row["ratio_f_eq"] == row["f_eq_jc"] / row["f_eq_lumped"]
    assert row["ratio_v_peak"] == row["v_peak_jc"] / row["v_peak_lumped"]
    assert row["f_peak_lumped"] == row["f_peak_jc"]  # the VBA FMax: an input property
    assert row["p_peak_bar"] == pytest.approx(row["p_cap_bar"], rel=1e-12)
    assert row["daf_lumped"] == pytest.approx(
        row["f_eq_lumped"] / (row["p_peak_bar"] * 1e5 * row["fluid_area_m2"]), rel=1e-12
    )
    assert row["momentum_jc"] == row["mass_total_kg"] * row["v_peak_jc"]
    # CSV round trip: the history is rebuilt bitwise from the row's generator columns
    path = tmp_path / "one.csv"
    sw.write_csv(path, [row])
    (back,) = sw.read_csv(path)
    h = sw.history_from_row(back)
    direct = sw.case_history(case, sw.pipe(case.size_in).p_design)
    assert np.array_equal(h.pressure, direct.pressure)
    assert float(back["history_peak"]) == float(np.abs(direct.force(sw.pipe(10).fluid_area)).max())


def test_data_format_csv_block_lists_the_tool_columns_in_order():
    import re

    doc = (REPO / "docs" / "data_format.md").read_text(encoding="utf-8")
    m = re.search(r"^## sweep CSV \(Session 5b\)\n(.*?)(?=^## )", doc, re.S | re.M)
    assert m, "docs/data_format.md has no 'sweep CSV (Session 5b)' section"
    keys = re.findall(r"^\| `([^`]+)` \|", m.group(1), re.M)
    assert keys == list(sw.COLUMNS)
