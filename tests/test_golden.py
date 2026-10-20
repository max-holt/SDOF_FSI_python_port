"""Golden-master tests: the Python port against Excel-computed results.

Fixtures (``tests/fixtures/curve_10in/``, produced by ``tools/extract_fixtures.py`` from
the source workbook, never edited by hand):

* ``params.json``   - arguments common to every case, as Excel passed them to the UDFs.
* ``force_history.csv`` - the full ``Sheet1`` extent; the first ``n_samples`` rows of the
  ``history_B`` column, scaled by the ``multipliers`` in order, form the force history.
* ``cases.csv``     - per-case inputs and the five expected outputs (``outputType = 0``).

Tolerance record
----------------
Relative tolerance per solver, ``|py - xl| <= RTOL * |xl|`` for each of the five outputs:

* ``lumped`` (``GetPeakResponse``): RTOL = 1e-10. Measured on 2026-10-20 with the first
  case of each span length (rows 20, 35, 50, 65, 80): max relative error 3.4e-13 over
  25 outputs, 5 of them exactly 0 (max applied force). 1e-10 leaves ~300x margin for
  accumulated last-bit differences (VBA vs Python ``pow``) on the ~1e6-step integration.
* ``jc`` (``GetPeakResponseJC``): RTOL = 1e-8, **provisional**: not yet measured. The JC
  cases run ~5.5e8-6.7e8 MoC cell updates each and are not run by default (see markers);
  their first full run is a Stage 5 deliverable, after which this value must be replaced
  by a measured one (tighten, or justify in NOTES.md/DEVIATIONS.md).

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

RTOL = {"lumped": 1e-10, "jc": 1e-8}

CURVE_DIR = Path(__file__).parent / "fixtures" / "curve_10in"
CACHE_DIR = Path(__file__).parent / ".golden_cache"
SOLVERS = {"lumped": lp.get_peak_response, "jc": lp.get_peak_response_jc}
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


PARAMS = load_params()
CASES = load_cases()
OUTPUT_NAMES = PARAMS["expected_outputs"]


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
    assert len(CASES) == 78
    assert sum(c["solver"] == "lumped" for c in CASES) == 75
    assert sum(c["solver"] == "jc" for c in CASES) == 3
    assert [c["source_row"] for c in CASES if c["solver"] == "jc"] == ["96", "97", "98"]
    force = load_force(PARAMS)
    assert force.shape == (PARAMS["n_samples"], 1) == (25135, 1)
    assert np.all(np.isfinite(force))
    assert PARAMS["output_type"] == 0
    assert set(RTOL) == set(SOLVERS) == {c["solver"] for c in CASES}


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
    actual = np.asarray(solver(force_history, **case_params(case, PARAMS)), dtype=float)
    expected = np.array([float(case[name]) for name in OUTPUT_NAMES])
    assert actual.shape == expected.shape == (5,)

    rtol = RTOL[case["solver"]]
    abs_err = np.abs(actual - expected)
    rel_err = abs_err / np.abs(expected)
    CACHE_DIR.mkdir(exist_ok=True)
    with open(CACHE_DIR / f"{case['case_id']}.json", "w") as fh:
        json.dump(
            {
                "case_id": case["case_id"],
                "source_row": int(case["source_row"]),
                "solver": case["solver"],
                "rtol": rtol,
                "outputs": OUTPUT_NAMES,
                "expected": expected.tolist(),
                "actual": actual.tolist(),
                "abs_err": abs_err.tolist(),
                "rel_err": rel_err.tolist(),
                "passed": bool(np.all(abs_err <= rtol * np.abs(expected))),
            },
            fh,
            indent=1,
        )
    for name, a, e, r in zip(OUTPUT_NAMES, actual, expected, rel_err, strict=True):
        assert abs(a - e) <= rtol * abs(e), f"{name}: python {a!r} vs excel {e!r} (rel {r:.3e})"
