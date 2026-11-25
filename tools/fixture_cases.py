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

from surge_sdof import response

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
    "solver_inputs",
    "history_of",
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


def load_params() -> dict:
    """The ``curve_10in`` parameters shared by every case (``params.json``): the fixture
    keyword values in SI units, the force-history spec and the sample count."""
    with open(CURVE_DIR / "params.json") as fh:
        return json.load(fh)


def load_cases() -> list[dict]:
    """The ``curve_10in`` case table (``cases.csv``): one dict per case, every cell as its
    text."""
    with open(CURVE_DIR / "cases.csv", newline="") as fh:
        return list(csv.DictReader(fh))


def load_force(params: dict) -> np.ndarray:
    """The ``curve_10in`` force history exactly as Excel built it.

    Parameters
    ----------
    params : dict
        From ``load_params``.

    Returns
    -------
    numpy.ndarray
        float64, shape ``(n_samples, 1)``, N: the first ``n_samples`` of the chosen column,
        multiplied left to right by the recorded multipliers.
    """
    spec = params["force"]
    with open(CURVE_DIR / spec["file"], newline="") as fh:
        reader = csv.DictReader(fh)
        col = np.array([float(row[spec["column"]]) for row in reader])
    col = col[: params["n_samples"]]
    for m in spec["multipliers"]:
        col = col * m
    return col.reshape(-1, 1)


def load_example_cases() -> list[dict]:
    """The three Example-sheet cases (``example/cases.json``), each with its own force
    history, keyword arguments and expected outputs."""
    with open(EXAMPLE_DIR / "cases.json") as fh:
        return json.load(fh)


def case_params(case: dict, params: dict) -> dict:
    """The fixture keyword arguments of one ``curve_10in`` case.

    Parameters
    ----------
    case : dict
        A row of ``load_cases``.
    params : dict
        From ``load_params``.

    Returns
    -------
    dict
        The shared parameters (the fluid ones for a junction-coupling case) with the
        case's span length (m), natural frequency (Hz) and friction coefficient, in the
        fixtures' vocabulary (``solver_inputs`` translates it).
    """
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


_SOLVER_KEYS = frozenset(
    {
        "step_qty",
        "sample_freq",
        "physical_length",
        "flexural_rigidity_ei",
        "celerity",
        "mass_per_unit_len",
        "damping_percent",
        "dynamic_fric",
        "nat_freq",
        "restrain_freq_ratio",
        "gap",
        "output_type",
        "trace_every",
    }
)
_JC_KEYS = frozenset(
    {"fluid_densty", "fluid_area", "vav_denominator", "parity", "fraction_profile"}
)


def solver_inputs(kw: dict, **overrides: object) -> dict:
    """The arguments of ``response.peak_response`` / ``peak_response_jc`` from a dict in the
    fixtures' vocabulary.

    The fixtures keep their keys (``tests/fixtures/`` is frozen), so this is where the two
    vocabularies meet. ``output_type`` is dropped: the result carries all three histories,
    and ``history_of`` picks the one an output type named.

    Parameters
    ----------
    kw : dict
        The keyword names of ``legacy_port`` and of the entry points before the public API
        session (``step_qty``, ``sample_freq``, ``physical_length``, ...), SI units.
    **overrides
        In the same vocabulary; they replace the keys of ``kw``.

    Returns
    -------
    dict
        ``sample_rate`` and the ``span``, ``restraint`` and ``integration`` objects; with
        ``fluid_densty`` in the dict also ``fluid`` and ``coupling`` (the flags it names,
        the approved fixes otherwise).

    Raises
    ------
    TypeError
        A key the entry points never took, or a junction-coupling key without
        ``fluid_densty``.
    """
    kw = dict(kw, **overrides)
    unknown = set(kw) - _SOLVER_KEYS - _JC_KEYS
    if unknown:
        raise TypeError(f"unknown solver arguments {sorted(unknown)}")
    arguments = {
        "sample_rate": kw["sample_freq"],
        "span": response.PipeSpan(
            kw["physical_length"],
            kw["flexural_rigidity_ei"],
            kw["mass_per_unit_len"],
            kw["celerity"],
        ),
        "restraint": response.Restraint(
            kw["nat_freq"],
            kw["damping_percent"],
            kw["dynamic_fric"],
            kw.get("gap", 0),
            kw.get("restrain_freq_ratio", 1),
        ),
        "integration": response.Integration(kw["step_qty"], kw.get("trace_every", 0)),
    }
    if "fluid_densty" not in kw:
        if set(kw) & _JC_KEYS:
            raise TypeError(
                f"junction-coupling arguments {sorted(set(kw) & _JC_KEYS)} without fluid"
            )
        return arguments
    arguments["fluid"] = response.Fluid(kw["fluid_densty"], kw["fluid_area"])
    arguments["coupling"] = response.CouplingModel(
        kw.get("vav_denominator", response.FIXED_COUPLING.mean_velocity_divisor),
        kw.get("parity", response.FIXED_COUPLING.parity),
        kw.get("fraction_profile", response.FIXED_COUPLING.fraction_profile),
    )
    return arguments


def history_of(result: response.PeakResponse, output_type: int) -> np.ndarray | None:
    """The response history a VBA ``outputType`` named.

    Parameters
    ----------
    result : response.PeakResponse
        A solver result.
    output_type : {0, 1, 2, 3}
        The fixtures' ``output_type``.

    Returns
    -------
    numpy.ndarray or None
        None for 0 (peaks only); the displacement (m), velocity (m/s) or acceleration
        (m/s²) history for 1, 2, 3.
    """
    return {
        0: None,
        1: result.displacement_history,
        2: result.velocity_history,
        3: result.acceleration_history,
    }[output_type]
