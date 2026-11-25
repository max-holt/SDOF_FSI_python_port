"""The content of the ``sweep`` document beyond the rows' values, for ``tools/export.py sweep``.

``sweep_rows_from_csv`` reads a CSV into sweep rows (the ``curve_10in`` case table mapped by
``golden_sweep_rows``, or a Session 5b sweep CSV passed through), ``golden_regen`` and
``sweep_regen`` give the document's ``regen`` block, ``reference_block`` its ``reference``
block (the Example-sheet cases and the JC golden rows with their Excel values),
``uniform_value`` the one value a column holds in every row. Moved from ``tools/cases.py``
(review session R.8, plan 5.11).
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import NamedTuple

import fixture_cases as tg  # tools/fixture_cases.py: the fixture loaders
import numpy as np


def _nominal_size_in(set_name: str) -> float | None:
    m = re.fullmatch(r"curve_(\d+)in", set_name)
    return float(m.group(1)) if m else None


def golden_sweep_rows(cases=None, params=None, set_name: str = "curve_10in") -> list[dict]:
    """``sweep`` rows from the ``curve_10in`` case table: ``case_id``, ``size_in``,
    ``span_length``, ``natural_frequency``, ``history_type = "golden"``, ``friction_coefficient``,
    ``characteristic_impedance`` and the ``max_static_equivalent_force_*`` /
    ``max_unbalance_force_*`` of the row's own solver; everything else null."""
    cases = tg.load_cases() if cases is None else cases
    params = tg.load_params() if params is None else params
    size_in = _nominal_size_in(set_name)
    rho_c = float(params["fluid_densty"]) * float(params["celerity"])
    rows = []
    for case in cases:
        solver = case["solver"]
        rows.append(
            {
                "case_id": case["case_id"],
                "size_in": size_in,
                "span_length": float(case["physical_length"]),
                "natural_frequency": float(case["nat_freq"]),
                "history_type": "golden",
                "friction_coefficient": float(case["dynamic_fric"]),
                "characteristic_impedance": rho_c,
                f"max_static_equivalent_force_{solver}": float(case["max_static_equivalent_force"]),
                f"max_unbalance_force_{solver}": float(case["max_applied_force"]),
            }
        )
    return rows


def golden_regen() -> dict:
    return {
        "template": "python tools/export.py trace --golden {case_id} --out {case_id}.json",
        "columns_used": ["case_id"],
        "note": (
            "Every row of this file is a tests/fixtures/curve_10in case, reproduced by "
            "--golden with the file's default stride (--trace-every overrides). Session 5b "
            "rows get their own template once tools/export.py has the history options."
        ),
    }


def sweep_regen() -> dict:
    """``regen`` of a Session 5b CSV: the sweep command of the row's tier (one row is
    reproduced by ``tools/sweep_jc.py``'s ``run_case`` from its columns; a single-case trace
    command is a W.3 item)."""
    return {
        "template": "python tools/sweep_jc.py run --tier {tier}",
        "columns_used": ["tier"],
        "note": (
            "Reruns the whole tier the row belongs to (docs/sweep/tier<N>_<sha>.csv). One row is "
            "reproduced by tools/sweep_jc.run_case on the Case its parameter columns describe; "
            "its history is histories.from_params over the fifteen generator columns "
            "(sweep_jc.history_from_row). A single-case trace command is a W.3 item."
        ),
    }


def uniform_value(rows, column: str):
    """The one value ``column`` holds in every row (empty cells ignored), else None."""
    values = {r.get(column) for r in rows} - {None, ""}
    return values.pop() if len(values) == 1 else None


class ReferenceCase(NamedTuple):
    """One entry of the ``reference`` block: a case with its Excel values (the record's
    ``_asdict()`` is the entry, keys in this order)."""

    case_id: str
    solver: str
    source: dict  # where the case comes from in the workbook
    inputs: dict  # the solver's inputs
    output_names: list | None
    excel_values: list  # floats, in the order of output_names
    rtol: float  # the relative tolerance the golden tests hold the port to


# The trace's output names before the schema bump, as the fixtures list them -> today's.
_OUTPUT_NAMES = {"max_applied_force": "max_unbalance_force"}


def _output_names(names) -> list:
    return [_OUTPUT_NAMES.get(name, name) for name in names]


def _grouped_inputs(kw: dict, history_key: str, history) -> dict:
    """A fixture case's solver keywords in the form of ``Trace.inputs``: the history under
    ``history_key``, then ``sample_rate`` and the input objects as dicts (no ``coupling``:
    the fixtures name no flags)."""
    arguments = tg.solver_inputs(kw)
    grouped = {history_key: history, "sample_rate": arguments["sample_rate"]}
    for group in ("span", "restraint", "fluid", "integration"):
        if group in arguments:
            grouped[group] = dataclasses.asdict(arguments[group])
    return grouped


def reference_block() -> dict:
    """The three Example-sheet cases and the three JC golden rows with their Excel values."""
    params = tg.load_params()
    example = []
    for case in tg.load_example_cases():
        inputs = dict(case["kwargs"])
        if "valve_pattern" in case:
            inputs["valve_pattern"] = np.asarray(case["valve_pattern"], dtype=float)
        if "force_history" in case:
            force_history = np.asarray(case["force_history"], dtype=float).reshape(-1, 1)
            inputs = _grouped_inputs(inputs, "force_history", force_history)
        example.append(
            ReferenceCase(
                case_id=case["case_id"],
                solver=case["solver"],
                source=dict(case["source"]),
                inputs=inputs,
                output_names=_output_names(case["output_names"])
                if "output_names" in case
                else None,
                excel_values=[float(v) for v in case["expected"]],
                rtol=tg.EXAMPLE_RTOL,
            )._asdict()
        )
    names = list(params["expected_outputs"])
    jc_rows = []
    for case in tg.load_cases():
        if case["solver"] != "jc":
            continue
        # the sheet history's spec, not its 25135 values
        inputs = _grouped_inputs(tg.case_params(case, params), "force", dict(params["force"]))
        jc_rows.append(
            ReferenceCase(
                case_id=case["case_id"],
                solver="jc",
                source={"sheet": params["case_sheet"], "source_row": int(case["source_row"])},
                inputs=inputs,
                output_names=_output_names(names),
                excel_values=[float(case[n]) for n in names],
                rtol=tg.RTOL["jc"],
            )._asdict()
        )
    return {"example_cases": example, "jc_golden_rows": jc_rows}


GOLDEN_CSV_HEADER = ("case_id", "source_row", "solver", "max_static_equivalent_force")


def sweep_rows_from_csv(path: str | Path) -> tuple[list[dict], str]:
    """Rows of a CSV: the ``curve_10in`` ``cases.csv`` layout is mapped by
    ``golden_sweep_rows``; a Session 5b CSV whose header is a subset of the sweep columns
    passes through (missing columns null). Returns ``(rows, layout)`` with layout
    ``"golden"`` or ``"sweep"``."""
    from surge_sdof.export import SWEEP_COLUMNS, read_csv

    header, rows = read_csv(path)
    if all(h in header for h in GOLDEN_CSV_HEADER):
        set_name = Path(path).resolve().parent.name
        return golden_sweep_rows(rows, tg.load_params(), set_name), "golden"
    unknown = [h for h in header if h not in SWEEP_COLUMNS]
    if unknown:
        raise SystemExit(f"{path}: not a sweep CSV, unknown columns {unknown}")
    return rows, "sweep"
