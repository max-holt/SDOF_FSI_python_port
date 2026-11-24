"""The Excel fixture cases, their tolerances and the flag sets, for tests and tools alike.

``tests/fixtures/`` holds the cases ``tools/extract_fixtures.py`` took from the source
workbook (``manifest.json`` lists the sets): ``curve_10in/`` (the 78 cases of the case table,
75 lumped and 3 junction coupling) and ``example/cases.json`` (the three Example-sheet
cases). This module reads them; ``tests/test_golden.py`` records how the tolerances were
measured and re-exports every name here, so a test or a tool written against it keeps
working. Not a test module: the tools import it without putting ``tests/`` on ``sys.path``,
and pytest finds it through ``pythonpath = ["tools"]`` (``pyproject.toml``).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

__all__ = [
    "RTOL",
    "EXAMPLE_RTOL",
    "LEGACY_FLAGS",
    "FIXED_FLAGS",
    "FIXTURES_DIR",
    "MANIFEST",
    "CURVE_DIR",
    "EXAMPLE_DIR",
    "CACHE_DIR",
    "load_params",
    "load_cases",
    "load_force",
    "load_example_cases",
    "case_params",
]

RTOL = {
    "lumped": 5e-12,  # measured: worst 8.3e-13 over 75 cases
    "jc": 5e-12,  # measured: worst 8.6e-13 over 3 cases (2026-10-21)
}
EXAMPLE_RTOL = 1e-12  # measured: worst 2.8e-14 over the 3 Example cases

LEGACY_FLAGS = {"vav_denominator": "legacy", "parity": "per_phase", "fraction_profile": "legacy"}
"""The junction-coupling flags that reproduce the VBA bitwise (the Excel acceptance runs)."""
FIXED_FLAGS = {"vav_denominator": "fixed", "parity": "running", "fraction_profile": "fixed"}
"""The junction-coupling flags of the approved fixes F-1 / F-2 / F-4b, spelled out."""

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
with open(FIXTURES_DIR / "manifest.json") as _fh:
    MANIFEST = json.load(_fh)
CURVE_DIR = FIXTURES_DIR / MANIFEST["sets"]["curve_10in"]["dir"]
EXAMPLE_DIR = FIXTURES_DIR / MANIFEST["sets"]["example"]["dir"]
CACHE_DIR = FIXTURES_DIR.parent / ".golden_cache"
"""Where the golden tests write each case's comparison for ``tools/golden_report.py``."""


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
