"""Session 5b: ``tools/sweep_jc.py`` (its modules ``sweep_grid`` and ``sweep_rows``) (the pipe table, the case grid, the CSV round trip)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
import sweep_grid  # tools/sweep_grid.py (through pythonpath = ["tools"])
import sweep_rows  # tools/sweep_rows.py

from surge_sdof import export

REPO = Path(__file__).resolve().parents[1]


def test_pipe_table_reproduces_the_owners_design_pressures_and_the_10in_fixture():
    sweep_grid.check_pipe_table(verbose=False)
    params = json.loads((REPO / "tests/fixtures/curve_10in/params.json").read_text())
    p10 = sweep_grid.pipe(10)
    assert math.isclose(p10.flow_area, params["fluid_area"], rel_tol=1e-12)
    assert math.isclose(p10.mass_per_length, params["mass_per_unit_len"], rel_tol=1e-12)
    assert math.isclose(p10.flexural_rigidity, params["flexural_rigidity_ei"], rel_tol=1e-12)
    for size, bar in sweep_grid.P_DESIGN_EXPECTED_BAR.items():
        assert abs(sweep_grid.pipe(size).design_pressure / 1e5 - bar) <= 0.1


def test_tier_grids():
    t1 = sweep_grid.tier_cases(1)
    assert len(t1) == 2 * 5 * 8 * (1 + 3 + 1) * 2 * 2
    assert len({c.case_id for c in t1}) == len(t1)
    t2 = sweep_grid.tier_cases(2)
    assert len(sweep_grid.curve_sheet_nat_freqs()) == 15
    assert len(t2) == 4 * 5 * 15 * (1 + 5 + 3) * 3 * 3


def test_stratified_subset_covers_every_level_of_every_dimension():
    cases = sweep_grid.tier_cases(1)
    sub = sweep_grid.stratified_subset(cases, 0.1)
    assert len(sub) == math.ceil(0.1 * len(cases))
    full = sweep_grid.coverage(cases)
    part = sweep_grid.coverage(sub)
    for dim, levels in full.items():
        assert set(part[dim]) == set(levels), dim
        counts = part[dim].values()
        assert max(counts) - min(counts) <= 4, (dim, part[dim])
    # deterministic and in grid order
    assert sub == sweep_grid.stratified_subset(cases, 0.1)
    assert [cases.index(c) for c in sub] == sorted(cases.index(c) for c in sub)


@pytest.mark.parametrize("kind", ["step", "step_sine", "step_noise"])
def test_run_case_fills_the_row_and_the_history_rebuilds_from_it(kind, tmp_path):
    cases = [
        c
        for c in sweep_grid.tier_cases(1)
        if c.history_type == kind and c.natural_frequency == 24.0
    ]
    case = cases[0]
    row = sweep_rows.run_case(case, sweep_rows.RunProvenance(1, "test", "cpu", "sha"))
    assert set(row) == set(sweep_rows.COLUMNS)
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
    sweep_rows.write_csv(path, [row])
    _, (back,) = export.read_csv(path)
    h = sweep_rows.history_from_row(back)
    direct = sweep_rows.case_history(case, sweep_grid.pipe(case.size_in).design_pressure)
    assert np.array_equal(h.pressure, direct.pressure)
    assert float(back["history_peak"]) == float(
        np.abs(direct.force(sweep_grid.pipe(10).flow_area)).max()
    )


def test_data_format_sweep_columns_are_the_tool_columns_in_order():
    from surge_sdof import export

    assert sweep_rows.COLUMNS is export.SWEEP_COLUMNS
    import re

    doc = (REPO / "docs" / "data_format.md").read_text(encoding="utf-8")
    m = re.search(r"^### sweep\.columns\n(.*?)(?=^### )", doc, re.S | re.M)
    assert m, "docs/data_format.md has no 'sweep.columns' block"
    keys = re.findall(r"^\| `([^`]+)` \|", m.group(1), re.M)
    assert keys == list(sweep_rows.COLUMNS)
