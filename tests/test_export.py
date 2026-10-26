"""Session W.1: the results data files (``surge_sdof.export``, ``tools/export.py``) against
their contract ``docs/data_format.md``.

The document's key tables are parsed here (every ``### <block>`` heading and the ``key``
column of its table), so a key is part of the format exactly when the document lists it.
Traces come from the two Example-sheet cases at a coarse stride; the memory test runs the
full golden row 96 (seconds under Numba, ~25 min in pure Python, so it skips there).
"""

from __future__ import annotations

import functools
import importlib.util
import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np
import pytest
import test_golden as tg

from surge_sdof import export, response
from surge_sdof.trace import PHASE_TRANSIT

REPO = Path(__file__).resolve().parents[1]
DOC = (REPO / "docs" / "data_format.md").read_text(encoding="utf-8")
sys.path.insert(0, str(REPO / "tools"))

import cases  # noqa: E402  (tools/cases.py)


def _load_tool(name: str):
    spec = importlib.util.spec_from_file_location(f"tools_{name}", REPO / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


export_cli = _load_tool("export")

PURE_PYTHON = os.environ.get("NUMBA_DISABLE_JIT", "0") not in ("", "0")


# ------------------------------------------------------------------ the document


def doc_keys(block: str) -> list[str]:
    """The ``key`` column of the table under ``### <block>`` in docs/data_format.md."""
    m = re.search(rf"^### {re.escape(block)}\n(.*?)(?=^### |^## |\Z)", DOC, re.S | re.M)
    assert m, f"docs/data_format.md has no '### {block}' block"
    keys = re.findall(r"^\| `([^`]+)` \|", m.group(1), re.M)
    assert keys, f"'### {block}' has no key table"
    assert len(keys) == len(set(keys)), f"'### {block}' lists a key twice"
    return keys


def assert_keys(obj: dict, block: str) -> None:
    assert list(obj) == doc_keys(block), f"{block}: {list(obj)} vs the document"


def assert_array_block(block: dict, where: str) -> None:
    assert_keys(block, "array block")
    n_rows, n_cols = block["shape"]
    assert len(block["data"]) == n_rows * n_cols, where


# ------------------------------------------------------------------ fixtures


@functools.cache
def example_result(case_id: str):
    case = next(c for c in tg.load_example_cases() if c["case_id"] == case_id)
    force = np.asarray(case["force_history"], dtype=float)
    if case["solver"] == "jc":
        return response.peak_response_jc(force, **case["kwargs"], trace_every=4)
    return response.peak_response(force, **case["kwargs"], trace_every=4)


@functools.cache
def trace_doc(case_id: str) -> dict:
    return export.to_trace_dict(
        example_result(case_id), case_id, sha="0" * 40, created="2026-10-26T00:00:00Z"
    )


@functools.cache
def golden_sweep_doc() -> dict:
    rows, layout = cases.sweep_rows_from_csv(tg.CURVE_DIR / "cases.csv")
    assert layout == "golden"
    return export.to_sweep_dict(
        rows,
        source="tests/fixtures/curve_10in/cases.csv",
        regen=cases.golden_regen(),
        reference=cases.reference_block(),
        sha=None,
        created="2026-10-26T00:00:00Z",
    )


# ------------------------------------------------------------------ trace schema


def test_module_constants_match_the_document():
    assert list(export.FRAME_COLUMNS) == doc_keys("trace.frames")
    assert list(export.SWEEP_COLUMNS) == doc_keys("sweep.columns")
    assert len(export.SWEEP_COLUMNS) == 30
    assert "schema_version` | int | `1`" in DOC and export.SCHEMA_VERSION == 1


@pytest.mark.parametrize("case_id", ["example_jc", "example_lumped"])
def test_trace_schema_against_the_document(case_id):
    doc = trace_doc(case_id)
    jc = case_id == "example_jc"
    top = doc_keys("trace")
    assert list(doc) == (top if jc else [k for k in top if k != "cells"])
    assert doc["kind"] == "trace" and doc["schema_version"] == 1
    meta = doc["meta"]
    assert_keys(meta, "trace.meta")
    assert_keys(meta["params"], "trace.meta.params")
    assert_keys(meta["outputs"], "trace.meta.outputs")
    assert_array_block(meta["inputs"]["force_history"], "inputs.force_history")
    geom = doc["geometry"]
    assert_keys(geom, "trace.geometry")
    assert_keys(geom["segments"], "trace.geometry.segments")
    frames = doc["frames"]
    assert_keys(frames, "trace.frames")
    n_frames = meta["n_frames"]
    assert n_frames == example_result(case_id).trace.n_frames + 1
    for name, column in frames.items():
        assert len(column) == n_frames, name
    n = len(geom["cell_position_m"])
    for name in ("cell_kind", "moving_fraction", "x_nominal_m", "y_nominal_m"):
        assert len(geom[name]) == n, name
    assert n == 2 * geom["pipe_seg_qty"] + 1
    seg = geom["segments"]
    assert seg["inlet_end"] < seg["run_start"] <= seg["run_end"] < seg["outlet_start"] < n
    pos = geom["cell_position_m"]
    assert geom["run_length_m"] == pos[seg["run_end"]] - pos[seg["run_start"]]
    assert geom["leg_height_m"] == pos[seg["run_start"]] - pos[seg["inlet_end"]]
    if jc:
        assert meta["n_cells"] == n == 37
        cells = doc["cells"]
        assert_keys(cells, "trace.cells")
        for name in ("p", "v"):
            assert_array_block(cells[name], f"cells.{name}")
            assert cells[name]["shape"] == [n_frames, n]
    else:
        assert meta["n_cells"] == 0
        assert n == 37  # the grid the Example case would have (same inputs as example_jc)
        assert "cells" not in doc
    # types: ints where the document says int, floats elsewhere, no bools in the columns
    for name in ("sub_step", "sample", "phase", "stick"):
        assert all(type(v) is int for v in frames[name]), name
    for name in ("t", "x", "f_friction", "d_f"):
        assert all(type(v) is float for v in frames[name]), name
    assert type(meta["params"]["capped"]) is int
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", meta["created_utc"])


@pytest.mark.parametrize("case_id", ["example_jc", "example_lumped"])
def test_frame_0_is_the_rest_frame_and_frame_1_the_first_traced(case_id):
    doc = trace_doc(case_id)
    tr = example_result(case_id).trace
    f = doc["frames"]
    assert f["t"][0] == 0.0 and f["sub_step"][0] == -1 and f["sample"][0] == -1
    assert f["phase"][0] == PHASE_TRANSIT  # the Example cases have a transit phase
    for name in ("x", "v", "a", "f_a", "f_b", "f_unbalance", "f_friction", "stick", "d_f"):
        assert f[name][0] == 0, name
    # t = (sub_step + 1) dt holds for every frame, the rest frame included
    dt = doc["meta"]["params"]["dt"]
    assert all(
        math.isclose(t, (s + 1) * dt, rel_tol=1e-12, abs_tol=0.0)
        for t, s in zip(f["t"], f["sub_step"], strict=True)
    )
    assert f["t"][1] == tr.t[0] == tr.dt and f["x"][1:] == tr.x.tolist()
    assert f["stick"][1:] == tr.stick.astype(int).tolist()
    if "cells" in doc:
        n = doc["meta"]["n_cells"]
        for name, arr in (("p", tr.p_cells), ("v", tr.v_cells)):
            data = doc["cells"][name]["data"]
            assert data[:n] == [0.0] * n
            assert data[n : 2 * n] == arr[0].tolist()
            assert data[-n:] == arr[-1].tolist()


def test_meta_carries_the_run_as_resolved():
    doc = trace_doc("example_jc")
    r = example_result("example_jc")
    p = doc["meta"]["params"]
    assert p["mass"] == r.trace.params.mass and p["fric_acc"] == r.trace.params.fric_acc
    assert p["trace_every"] == 4 and p["step_qty"] == 80 and p["dt"] == r.trace.dt
    assert doc["meta"]["outputs"]["max_displacement"] == r.max_displacement
    assert doc["meta"]["inputs"]["vav_denominator"] == "fixed"
    assert doc["meta"]["inputs"]["force_history"]["shape"] == [25, 1]
    assert doc["meta"]["solver"] == "peak_response_jc"
    assert trace_doc("example_lumped")["meta"]["solver"] == "peak_response"
    assert "vav_denominator" not in trace_doc("example_lumped")["meta"]["inputs"]


def test_trace_dict_needs_a_trace():
    case = next(c for c in tg.load_example_cases() if c["case_id"] == "example_lumped")
    bare = response.peak_response(np.asarray(case["force_history"], float), **case["kwargs"])
    with pytest.raises(ValueError, match="no trace"):
        export.to_trace_dict(bare, "bare")


# ------------------------------------------------------------------ files


@pytest.mark.parametrize("which", ["example_jc", "example_lumped", "sweep"])
def test_round_trip_dict_json_dict(which):
    doc = golden_sweep_doc() if which == "sweep" else trace_doc(which)
    text = export.dumps(doc)
    assert text.endswith("\n") and "NaN" not in text and "Infinity" not in text
    assert json.loads(text) == doc


def test_gzip_variant_reads_back_identical(tmp_path):
    doc = trace_doc("example_jc")
    n_plain = export.write_json(tmp_path / "a.json", doc)
    n_gz = export.write_json(tmp_path / "a.json.gz", doc)
    assert n_plain == n_gz
    plain = (tmp_path / "a.json").read_bytes()
    assert len(plain) == n_plain and plain.endswith(b"\n") and b"\r" not in plain
    assert (tmp_path / "a.json.gz").stat().st_size < n_plain
    assert export.read_json(tmp_path / "a.json.gz") == export.read_json(tmp_path / "a.json") == doc
    import gzip

    assert gzip.decompress((tmp_path / "a.json.gz").read_bytes()) == plain


def test_floats_are_repr_and_compact():
    text = export.dumps({"x": [0.1, 1e-7, 1325.5451059415939, 3.0], "s": "m²"})
    assert text == '{"x":[0.1,1e-07,1325.5451059415939,3.0],"s":"m²"}\n'


def test_non_finite_values_are_refused(tmp_path):
    with pytest.raises(ValueError):
        export.write_json(tmp_path / "nan.json", {"x": [float("nan")]})
    with pytest.raises(ValueError, match="non-finite"):
        export.to_sweep_dict([{"case_id": "a", "mu": float("nan")}], source="x", sha=None)
    with pytest.raises(ValueError, match="unknown sweep columns"):
        export.to_sweep_dict([{"case_id": "a", "bogus": 1.0}], source="x", sha=None)
    with pytest.raises(TypeError):
        export.to_sweep_dict([{"case_id": 7}], source="x", sha=None)
    with pytest.raises(ValueError, match="integer"):
        export.to_sweep_dict([{"seed": 1.5}], source="x", sha=None)


def test_sweep_values_are_typed_and_null_where_unknown():
    doc = export.to_sweep_dict(
        [{"case_id": "a", "seed": "7", "mu": "0.005", "error": None}, {"error": "boom", "mu": ""}],
        source="x",
        sha=None,
        created="2026-10-26T00:00:00Z",
    )
    c = doc["columns"]
    assert c["seed"] == [7, None] and c["mu"] == [0.005, None] and c["error"] == [None, "boom"]
    assert c["case_id"] == ["a", None] and doc["meta"]["n_rows"] == 2
    assert all(len(v) == 2 for v in c.values())


# ------------------------------------------------------------------ sweep from the golden CSV


def test_sweep_schema_and_reference_block_from_the_golden_csv():
    doc = golden_sweep_doc()
    assert_keys(doc, "sweep")
    assert doc["kind"] == "sweep" and doc["schema_version"] == 1
    assert_keys(doc["meta"], "sweep.meta")
    assert_keys(doc["columns"], "sweep.columns")
    assert_keys(doc["regen"], "sweep.regen")
    assert_keys(doc["reference"], "sweep.reference")
    n = doc["meta"]["n_rows"]
    assert n == 78 and all(len(col) == n for col in doc["columns"].values())
    c = doc["columns"]
    csv_rows = {r["case_id"]: r for r in tg.load_cases()}
    assert c["case_id"] == list(csv_rows)
    assert set(c["history_type"]) == {"golden"} and set(c["size_in"]) == {10.0}
    assert c["error"] == [None] * n and c["od_mm"] == [None] * n
    i96 = c["case_id"].index("r096_jc_L24_f3")
    r96 = csv_rows["r096_jc_L24_f3"]
    assert c["f_eq_jc"][i96] == float(r96["max_static_equivalent_force"])
    assert c["f_peak_jc"][i96] == float(r96["max_applied_force"])
    assert c["f_eq_lumped"][i96] is None and c["ratio_f_eq"][i96] is None
    assert c["length_m"][i96] == 24.0 and c["nat_freq_hz"][i96] == 3.0 and c["mu"][i96] == 1e-6
    i20 = c["case_id"].index("r020_lumped_L3_f2")
    assert c["f_eq_lumped"][i20] == float(
        csv_rows["r020_lumped_L3_f2"]["max_static_equivalent_force"]
    )
    assert c["f_eq_jc"][i20] is None
    params = tg.load_params()
    assert set(c["rho_c"]) == {params["fluid_densty"] * params["celerity"]}
    # regen: the template formats with any row
    row = {name: c[name][i96] for name in export.SWEEP_COLUMNS}
    cmd = doc["regen"]["template"].format(**row)
    assert cmd == "python tools/export.py trace --golden r096_jc_L24_f3 --out r096_jc_L24_f3.json"
    assert doc["regen"]["columns_used"] == ["case_id"]
    # reference: the Excel values exactly as the fixtures hold them
    ref = doc["reference"]
    assert [e["case_id"] for e in ref["example_cases"]] == [
        "example_pressure",
        "example_lumped",
        "example_jc",
    ]
    assert [e["case_id"] for e in ref["jc_golden_rows"]] == [
        "r096_jc_L24_f3",
        "r097_jc_L24_f7.5",
        "r098_jc_L24_f22",
    ]
    for entry in ref["example_cases"] + ref["jc_golden_rows"]:
        assert_keys(entry, "reference entry")
    for entry, case in zip(ref["example_cases"], tg.load_example_cases(), strict=True):
        assert entry["excel_values"] == [float(v) for v in case["expected"]]
        assert entry["rtol"] == tg.EXAMPLE_RTOL and entry["solver"] == case["solver"]
        assert entry["source"] == case["source"]
    pressure = ref["example_cases"][0]
    assert pressure["output_names"] is None and len(pressure["excel_values"]) == 121
    assert pressure["inputs"]["valve_pattern"]["shape"] == [5, 1]
    names = params["expected_outputs"]
    for entry in ref["jc_golden_rows"]:
        case = csv_rows[entry["case_id"]]
        assert entry["output_names"] == names
        assert entry["excel_values"] == [float(case[k]) for k in names]
        assert entry["rtol"] == tg.RTOL["jc"]
        assert entry["source"]["source_row"] == int(case["source_row"])
        assert entry["inputs"]["physical_length"] == float(case["physical_length"])
        assert entry["inputs"]["fluid_area"] == params["fluid_area"]


def test_sweep_csv_passthrough_and_rejection(tmp_path):
    path = tmp_path / "sweep.csv"
    path.write_text("case_id,size_in,mu,seed,error\nrun1,10,0.005,3,\nrun2,10,,,boom\n")
    rows, layout = cases.sweep_rows_from_csv(path)
    assert layout == "sweep" and len(rows) == 2
    doc = export.to_sweep_dict(rows, source=str(path), sha=None)
    assert doc["columns"]["seed"] == [3, None] and doc["columns"]["error"] == [None, "boom"]
    assert doc["columns"]["f_eq_jc"] == [None, None]
    bad = tmp_path / "bad.csv"
    bad.write_text("case_id,nope\na,1\n")
    with pytest.raises(SystemExit, match="unknown columns"):
        cases.sweep_rows_from_csv(bad)


# ------------------------------------------------------------------ the CLI


def test_cli_trace_and_sweep(tmp_path, capsys):
    out = tmp_path / "lumped.json.gz"
    export_cli.main(
        ["trace", "--golden", "example_lumped", "--trace-every", "8", "--out", str(out)]
    )
    doc = export.read_json(out)
    assert doc["kind"] == "trace" and doc["meta"]["case_id"] == "example_lumped"
    assert doc["meta"]["params"]["trace_every"] == 8 and "cells" not in doc
    printed = capsys.readouterr().out
    assert "MB of JSON" in printed and "gzipped" in printed
    out2 = tmp_path / "step.json"
    export_cli.main(
        [
            "trace",
            "--step",
            "--solver",
            "jc",
            "--duration",
            "0.05",
            "--length",
            "6",
            "--sample-freq",
            "10",
            "--step-qty",
            "80",
            "--celerity",
            "1200",
            "--mass-per-len",
            "100",
            "--ei",
            "1e7",
            "--name",
            "tiny",
            "--out",
            str(out2),
        ]
    )
    doc2 = export.read_json(out2)
    assert doc2["meta"]["case_id"] == "tiny" and "cells" in doc2
    assert doc2["meta"]["params"]["trace_every"] == 1  # a short run: the 2000-frame stride is 1
    out3 = tmp_path / "sweep.json"
    export_cli.main(
        [
            "sweep",
            "--from-csv",
            str(tg.CURVE_DIR / "cases.csv"),
            "--tier",
            "golden",
            "--out",
            str(out3),
        ]
    )
    doc3 = export.read_json(out3)
    assert doc3["kind"] == "sweep" and doc3["meta"]["tier"] == "golden"
    assert doc3["meta"]["n_rows"] == 78 and len(doc3["reference"]["jc_golden_rows"]) == 3


def test_default_stride_is_the_2000_frame_stride_unless_the_budget_bites():
    force, kw, solver = cases.golden_case("example_jc")
    assert export_cli.export_trace_every(
        force, kw, solver, 2000, 45.0
    ) == cases.default_trace_every(force, kw, 2000)
    force, kw, solver = cases.golden_case("r096_jc_L24_f3")
    fine = cases.default_trace_every(force, kw, 2000)
    budget = export_cli.export_trace_every(force, kw, solver, 2000, 45.0)
    assert budget > fine  # 1333 cells x 2000 frames would be ~107 MB
    assert export_cli.estimated_cells(kw, solver) == 1333
    assert export_cli.estimated_cells(kw, "lumped") == 0
    with pytest.raises(SystemExit):
        export_cli.export_trace_every(force, kw, solver, 2000, 0.01)


@pytest.mark.skipif(PURE_PYTHON, reason="the full row 96 takes ~25 min without Numba")
def test_row_96_at_the_default_stride_stays_under_50_mb(capsys):
    force, kw, solver = cases.golden_case("r096_jc_L24_f3")
    stride = export_cli.export_trace_every(force, kw, solver, 2000, export_cli.JSON_BUDGET_MB)
    result = cases.run(force, kw, solver, stride)
    doc = export.to_trace_dict(result, "r096_jc_L24_f3", sha=None)
    text = export.dumps(doc)
    size = len(text.encode("utf-8"))
    n_frames = doc["meta"]["n_frames"]
    with capsys.disabled():
        print(
            f"\nrow 96 at the default stride {stride}: {n_frames} frames "
            f"({stride * result.trace.dt * 1e3:.1f} ms a frame), {doc['meta']['n_cells']} cells, "
            f"{size / 1e6:.2f} MB of JSON"
        )
    assert size < 50_000_000
    assert doc["meta"]["n_cells"] == 1333 and n_frames >= 800
    assert math.isclose(
        doc["meta"]["outputs"]["max_displacement"], 0.0036195012413468937, rel_tol=5e-12
    )
