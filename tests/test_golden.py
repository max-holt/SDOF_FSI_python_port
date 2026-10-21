"""Golden-master tests: the Python port against Excel-computed results.

Fixture sets are listed in ``tests/fixtures/manifest.json``; all are produced by
``tools/extract_fixtures.py`` from the source workbook and never edited by hand.

``curve_10in/`` (the 78 slow cases from the case table):

* ``params.json``   - arguments common to every case, as Excel passed them to the UDFs.
* ``force_history.csv`` - the full ``Sheet1`` extent; the first ``n_samples`` rows of the
  ``history_B`` column, scaled by the ``multipliers`` in order, form the force history.
* ``cases.csv``     - per-case inputs and the five expected outputs (``outputType = 0``).

``example/cases.json`` (3 fast cases from the ``Example`` sheet, each self-contained with
inputs, keyword arguments and expected outputs): ``example_pressure`` (``GetPressureResponse``,
121-sample pressure history), ``example_lumped`` and ``example_jc`` (five peak outputs).

Tolerance record
----------------
Relative tolerance per solver, ``|py - xl| <= RTOL * |xl|`` for each of the five outputs:

* ``lumped`` (``GetPeakResponse``): RTOL = 5e-12. Measured on 2026-10-20 over all 75
  cases (375 outputs): max relative error 8.3e-13 (row 66, max displacement), median
  per-case maximum 1.0e-13, max applied force exact in every case. The ~6x margin covers
  last-bit differences between the C ``pow`` behind Python's ``**`` and Excel's runtime,
  accumulated over the ~1e6-step integration. Run time 3 min 34 s for the 75 cases.
* ``jc`` (``GetPeakResponseJC``): RTOL = 5e-12. Measured on 2026-10-21 over all 3 cases
  (15 outputs, pure Python, first full run): max relative error 8.6e-13 (row 96, max
  velocity; row 97 2.1e-14, row 98 8.4e-15), max applied force exact in every case. All
  three passed at the provisional 1e-12; the tolerance is set by the lumped rule
  (5x the worst, rounded up to one significant figure). Run time 1 h 20 min
  (1827 s, 1565 s, 1411 s).
* ``example`` (all three Example cases): RTOL = 1e-12 (owner's decision, 2026-10-21).
  Measured: pressure 1.2e-14 (10 of 121 samples bit-exact), lumped 2.8e-14, jc 2.6e-15;
  milliseconds each, so they run in the default suite, unmarked.

Markers
-------
``slow``    - the 75 lumped cases (~3.5 min together); ``pytest -m slow``.
``jc_slow`` - the 3 JC cases (hours in pure Python); ``pytest -m "slow or jc_slow"``.
Both are excluded from the default run by ``addopts`` in ``pyproject.toml``.

Each case also writes its actual/expected values to ``tests/.golden_cache/<case_id>.json``
(git-ignored) for ``tools/golden_report.py``.
"""

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from surge_sdof import legacy_port as lp

RTOL = {
    "lumped": 5e-12,  # measured: worst 8.3e-13 over 75 cases
    "jc": 5e-12,  # measured: worst 8.6e-13 over 3 cases (2026-10-21)
}
EXAMPLE_RTOL = 1e-12  # measured: worst 2.8e-14 over the 3 Example cases

FIXTURES_DIR = Path(__file__).parent / "fixtures"
with open(FIXTURES_DIR / "manifest.json") as _fh:
    MANIFEST = json.load(_fh)
CURVE_DIR = FIXTURES_DIR / MANIFEST["sets"]["curve_10in"]["dir"]
EXAMPLE_DIR = FIXTURES_DIR / MANIFEST["sets"]["example"]["dir"]
CACHE_DIR = Path(__file__).parent / ".golden_cache"
SOLVERS = {
    "lumped": lp.get_peak_response,
    "jc": lp.get_peak_response_jc,
    "pressure": lp.get_pressure_response,
}
MARKERS = {"lumped": pytest.mark.slow, "jc": pytest.mark.jc_slow}


def load_params():
    with open(CURVE_DIR / "params.json") as fh:
        return json.load(fh)


def load_cases():
    with open(CURVE_DIR / "cases.csv", newline="") as fh:
        return list(csv.DictReader(fh))


def load_force(params):
    """The force history exactly as Excel built it: first n_samples of the chosen column,
    multiplied left to right by the recorded multipliers, as an (n, 1) column."""
    spec = params["force"]
    with open(CURVE_DIR / spec["file"], newline="") as fh:
        reader = csv.DictReader(fh)
        col = np.array([float(row[spec["column"]]) for row in reader])
    col = col[: params["n_samples"]]
    for m in spec["multipliers"]:
        col = col * m
    return col.reshape(-1, 1)


def load_example_cases():
    with open(EXAMPLE_DIR / "cases.json") as fh:
        return json.load(fh)


PARAMS = load_params()
CASES = load_cases()
EXAMPLE_CASES = load_example_cases()
OUTPUT_NAMES = PARAMS["expected_outputs"]


def check_and_cache(case_id, solver, source, output_names, actual, expected, rtol):
    """Assert ``|py - xl| <= rtol * |xl|`` per output and cache the comparison for
    ``tools/golden_report.py``."""
    actual = np.asarray(actual, dtype=float)
    expected = np.asarray(expected, dtype=float)
    assert actual.shape == expected.shape
    abs_err = np.abs(actual - expected)
    rel_err = abs_err / np.abs(expected)
    CACHE_DIR.mkdir(exist_ok=True)
    with open(CACHE_DIR / f"{case_id}.json", "w") as fh:
        json.dump(
            {
                "case_id": case_id,
                "source": source,
                "solver": solver,
                "rtol": rtol,
                "outputs": list(output_names),
                "expected": expected.tolist(),
                "actual": actual.tolist(),
                "abs_err": abs_err.tolist(),
                "rel_err": rel_err.tolist(),
                "passed": bool(np.all(abs_err <= rtol * np.abs(expected))),
            },
            fh,
            indent=1,
        )
    for name, a, e, r in zip(output_names, actual, expected, rel_err, strict=True):
        assert abs(a - e) <= rtol * abs(e), f"{name}: python {a!r} vs excel {e!r} (rel {r:.3e})"


def case_params(case, params):
    common = {
        k: params[k]
        for k in (
            "step_qty",
            "sample_freq",
            "flexural_rigidity_ei",
            "celerity",
            "mass_per_unit_len",
            "damping_percent",
            "restrain_freq_ratio",
            "gap",
            "output_type",
        )
    }
    if case["solver"] == "jc":
        common["fluid_densty"] = params["fluid_densty"]
        common["fluid_area"] = params["fluid_area"]
    return dict(
        common,
        physical_length=float(case["physical_length"]),
        nat_freq=float(case["nat_freq"]),
        dynamic_fric=float(case["dynamic_fric"]),
    )


# ------------------------------------------------------------------ fixture integrity
# Always on: cheap checks that the extracted fixtures are what the golden cases assume.


def test_fixture_counts_and_shape():
    sets = MANIFEST["sets"]
    assert sets["curve_10in"]["cases"] == len(CASES) == 78
    assert sets["curve_10in"]["solvers"] == {"lumped": 75, "jc": 3}
    assert sets["curve_10in"]["n_samples"] == PARAMS["n_samples"]
    assert sets["example"]["cases"] == len(EXAMPLE_CASES) == 3
    assert [c["solver"] for c in EXAMPLE_CASES] == ["pressure", "lumped", "jc"]
    assert sets["example"]["markers"] == {}
    assert sum(c["solver"] == "lumped" for c in CASES) == 75
    assert sum(c["solver"] == "jc" for c in CASES) == 3
    assert [c["source_row"] for c in CASES if c["solver"] == "jc"] == ["96", "97", "98"]
    force = load_force(PARAMS)
    assert force.shape == (PARAMS["n_samples"], 1) == (25135, 1)
    assert np.all(np.isfinite(force))
    assert PARAMS["output_type"] == 0
    assert set(RTOL) == {c["solver"] for c in CASES} == set(MARKERS)
    assert set(SOLVERS) == {c["solver"] for c in EXAMPLE_CASES}


def test_example_fixture_shapes():
    pressure, lumped, jc = EXAMPLE_CASES
    assert np.array(pressure["valve_pattern"], float).shape == (5, 1)
    assert len(pressure["expected"]) == 121  # outMax + 1 = closureTime / timeStep + 1
    assert pressure["kwargs"]["pipe_area"] == np.pi * (200.0**2 / 4)
    for case in (lumped, jc):
        assert np.array(case["force_history"], float).shape == (25, 1)
        assert len(case["expected"]) == 5
        assert case["output_names"] == OUTPUT_NAMES
        assert case["vba_defaults_used"] == ["restrain_freq_ratio", "gap", "output_type"]


def test_fixture_force_scaling_reproduces_excel_max_applied_force_for_short_spans():
    """For every case the max applied force is max|F(t) - F(t - L/c)|; it depends only on
    the force history and the span, so the lumped and JC cases with the same span agree.
    This checks the scaling without running a solver."""
    by_span = {}
    for c in CASES:
        by_span.setdefault(c["physical_length"], set()).add(c["max_applied_force"])
    assert all(len(v) == 1 for v in by_span.values()), by_span


# ------------------------------------------------------------------ golden cases


@pytest.fixture(scope="module")
def force_history():
    return load_force(PARAMS)


@pytest.mark.parametrize(
    "case",
    [pytest.param(c, id=c["case_id"], marks=MARKERS[c["solver"]]) for c in CASES],
)
def test_golden_peak_response(case, force_history):
    solver = SOLVERS[case["solver"]]
    actual = solver(force_history, **case_params(case, PARAMS))
    expected = [float(case[name]) for name in OUTPUT_NAMES]
    check_and_cache(
        case["case_id"],
        case["solver"],
        f"curve_10in row {case['source_row']}",
        OUTPUT_NAMES,
        actual,
        expected,
        RTOL[case["solver"]],
    )


# ------------------------------------------------------------------ Example sheet (fast)


@pytest.mark.parametrize("case", [pytest.param(c, id=c["case_id"]) for c in EXAMPLE_CASES])
def test_golden_example(case):
    """The three Example-sheet UDF calls, inputs passed as the (n, 1) ``Range.Value`` arrays
    Excel handed to VBA. Unmarked: milliseconds each."""
    solver = SOLVERS[case["solver"]]
    if case["solver"] == "pressure":
        actual = solver(np.array(case["valve_pattern"], float), **case["kwargs"])
        names = [f"p[{i}]" for i in range(len(case["expected"]))]
    else:
        actual = solver(np.array(case["force_history"], float), **case["kwargs"])
        names = case["output_names"]
    src = case["source"]
    check_and_cache(
        case["case_id"],
        case["solver"],
        f"{src['sheet']}!{src['formula_cell']} ({src['spill']})",
        names,
        actual,
        case["expected"],
        EXAMPLE_RTOL,
    )
