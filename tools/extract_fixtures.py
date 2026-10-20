"""Extract the ``curve_10in`` golden fixtures from the source workbook.

Reads ``tests/fixtures/source/surge_force_data.xlsm`` (Excel-cached values, i.e. the
numbers the VBA UDFs produced inside Excel) and writes, under ``tests/fixtures/curve_10in/``:

* ``force_history.csv`` - the full numeric extent of ``Sheet1`` (time, history_A,
  history_B); the test slices the first ``n_samples`` rows of ``history_B``.
* ``params.json`` - the arguments common to every case, taken from the parameter cells
  of ``curve_10in`` exactly as Excel passed them to the UDFs (cached doubles).
* ``cases.csv`` - one row per live UDF call in the case table (column H array formula
  ``GetPeakResponse`` -> solver ``lumped``, ``GetPeakResponseJC`` -> ``jc``): the
  per-case inputs (E: physical length, F: natural frequency, G: dynamic friction) and
  the five expected outputs H..L. ``source_row`` is the workbook row the case came from.

Rows whose column H holds a pasted number instead of a formula (rows 100-101 at the time
of writing) are not cases and are skipped. The argument mapping of every formula is
checked against the expected shape so a workbook layout change is caught here, not in
the test.

Floats are written with ``repr`` (shortest round-trip), so the fixtures carry the exact
doubles Excel held.

Run manually (this is the only sanctioned way to produce files under tests/fixtures/):

    python tools/extract_fixtures.py

Requires ``openpyxl``, which is deliberately *not* a project dependency
(``pip install openpyxl`` into the dev venv when regenerating fixtures).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = REPO / "tests" / "fixtures" / "source" / "surge_force_data.xlsm"
DEFAULT_OUT = REPO / "tests" / "fixtures" / "curve_10in"

CASE_SHEET = "curve_10in"
FORCE_SHEET = "Sheet1"
FORCE_HEADER = ("time", "history_A", "history_B")
# curve_10in!C{r} is "=Sheet1!D{r+1}", and Sheet1 column D is history_B.
FORCE_COLUMN = "history_B"
FORCE_SHEET_COL = 4  # D
FIRST_CASE_ROW = 20

# Parameter cells of curve_10in: (label cell, expected label, value cell, name)
PARAM_CELLS = [
    ("E4", "Step QTY", "H4", "step_qty"),
    ("E5", "Sample Frequency", "H5", "sample_freq"),
    ("E6", "Celerity", "H6", "celerity"),
    ("E9", "Density Fluid", "H9", "fluid_densty"),
    ("E11", "Mass/Physical Length", "H11", "mass_per_unit_len"),
    ("E12", "Damping (% Critical)", "H12", "damping_percent"),
    ("E13", "Pipe Area", "H13", "fluid_area"),
    ("E14", "E", "H14", "youngs_modulus"),
    ("E15", "I", "H15", "second_moment"),
    ("N4", "frequency factor", "P4", "restrain_freq_ratio"),
    ("N5", "gap", "P5", "gap"),
    ("N12", "Force Correction", "N13", "force_correction"),
]

FORCE_ARG = r"\$C\$(\d+):\$C\$(\d+)\*1000\*\$N\$13"
LUMPED_RE = re.compile(
    r"^=GetPeakResponse\(" + FORCE_ARG + r",\s*\$H\$4,\s*\$H\$5,\s*E(\d+),\s*\$H\$14\*\$H\$15,"
    r"\s*\$H\$6,\s*\$H\$11,\s*\$H\$12,\s*\$G(\d+),\s*F(\d+),\s*\$P\$4,\s*\$P\$5\)$"
)
JC_RE = re.compile(
    r"^=GetPeakResponseJC\(" + FORCE_ARG + r",\s*\$H\$4,\s*\$H\$5,\s*E(\d+),\s*\$H\$14\*\$H\$15,"
    r"\s*\$H\$6,\s*\$H\$11,\s*\$H\$9,\s*\$H\$13,\s*\$H\$12,\s*G(\d+),\s*F(\d+),\s*\$P\$4,\s*\$P\$5,\s*0\)$"
)
OUTPUT_NAMES = (
    "max_static_equivalent_force",
    "max_displacement",
    "max_velocity",
    "max_acceleration",
    "max_applied_force",
)


def match_case(formula):
    """(solver, match) for a case-table formula, or (None, None)."""
    for solver, rx in (("lumped", LUMPED_RE), ("jc", JC_RE)):
        m = rx.match(formula)
        if m:
            return solver, m
    return None, None


def fmt(v):
    return repr(float(v)) if isinstance(v, float) else str(v)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    print(f"reading {args.workbook} (values) ...", file=sys.stderr)
    wb_val = openpyxl.load_workbook(args.workbook, data_only=True)
    print("reading formulas ...", file=sys.stderr)
    wb_fml = openpyxl.load_workbook(args.workbook, data_only=False)
    cv, cf = wb_val[CASE_SHEET], wb_fml[CASE_SHEET]

    # --- common parameters -------------------------------------------------------
    params = {}
    for label_cell, label, value_cell, name in PARAM_CELLS:
        got = cf[label_cell].value
        if got != label:
            raise SystemExit(f"{CASE_SHEET}!{label_cell} is {got!r}, expected {label!r}")
        params[name] = cv[value_cell].value
    if params["step_qty"] != int(params["step_qty"]):
        raise SystemExit("step_qty is not an integer")
    params["step_qty"] = int(params["step_qty"])
    # Excel evaluates $H$14*$H$15 in the formula; reproduce the single double product.
    params["flexural_rigidity_ei"] = float(params.pop("youngs_modulus")) * float(
        params.pop("second_moment")
    )
    force_correction = params.pop("force_correction")

    # --- cases -------------------------------------------------------------------
    cases = []
    force_rows = None
    for r in range(FIRST_CASE_ROW, cf.max_row + 1):
        cell = cf.cell(r, 8)  # H
        text = getattr(cell.value, "text", None)
        if text is None:
            continue  # empty, or a pasted number: not a live case
        solver, m = match_case(text)
        if m is None:
            raise SystemExit(f"{CASE_SHEET}!H{r}: unexpected formula shape: {text}")
        c0, c1, e_row, g_row, f_row = (int(x) for x in m.groups())
        if not (e_row == g_row == f_row == r):
            raise SystemExit(f"{CASE_SHEET}!H{r}: formula refers to another row: {text}")
        if force_rows is None:
            force_rows = (c0, c1)
        elif force_rows != (c0, c1):
            raise SystemExit(
                f"{CASE_SHEET}!H{r}: force range differs from row {cases[0]['source_row']}"
            )
        expected = [cv.cell(r, c).value for c in range(8, 13)]  # H..L
        if any(not isinstance(v, (int, float)) for v in expected):
            raise SystemExit(f"{CASE_SHEET}!H{r}: cached outputs missing: {expected}")
        L, f, fric = (cv.cell(r, c).value for c in (5, 6, 7))
        cases.append(
            {
                "case_id": f"r{r:03d}_{solver}_L{L:g}_f{f:g}",
                "source_row": r,
                "solver": solver,
                "physical_length": L,
                "nat_freq": f,
                "dynamic_fric": fric,
                **dict(zip(OUTPUT_NAMES, expected, strict=True)),
            }
        )
    if not cases:
        raise SystemExit("no cases found")

    # --- force history -------------------------------------------------------------
    c0, c1 = force_rows
    n_samples = c1 - c0 + 1
    for r in (c0, c1):
        ref = cf.cell(r, 3).value  # curve_10in!C{r}
        if ref != f"={FORCE_SHEET}!D{r + 1}":
            raise SystemExit(f"{CASE_SHEET}!C{r} is {ref!r}, expected '={FORCE_SHEET}!D{r + 1}'")
    first_force_row = c0 + 1  # Sheet1 row holding sample 1
    ws = wb_val[FORCE_SHEET]
    header = tuple(ws.cell(2, c).value for c in (2, 3, 4))
    if header != FORCE_HEADER:
        raise SystemExit(f"{FORCE_SHEET} header is {header}, expected {FORCE_HEADER}")
    force_rows_out = []
    for r in range(3, ws.max_row + 1):
        vals = [ws.cell(r, c).value for c in (2, 3, 4)]
        if all(isinstance(v, (int, float)) for v in vals):
            force_rows_out.append(vals)
        elif any(v is not None for v in vals):
            raise SystemExit(f"{FORCE_SHEET} row {r}: non-numeric data {vals}")
    if first_force_row != 3:
        raise SystemExit(f"force range does not start at {FORCE_SHEET} row 3")
    if n_samples > len(force_rows_out):
        raise SystemExit("force range longer than Sheet1")

    params.update(
        {
            "output_type": 0,
            "n_samples": n_samples,
            "force": {
                "file": "force_history.csv",
                "column": FORCE_COLUMN,
                "source": f"{FORCE_SHEET}!D{first_force_row}:D{first_force_row + n_samples - 1}",
                "excel_expression": f"{CASE_SHEET}!$C${c0}:$C${c1}*1000*$N$13",
                # applied left to right, as Excel evaluates the array expression
                "multipliers": [1000, force_correction],
            },
            "source_workbook": str(args.workbook.relative_to(REPO)),
            "case_sheet": CASE_SHEET,
            "expected_outputs": list(OUTPUT_NAMES),
        }
    )

    # --- write -----------------------------------------------------------------------
    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / "force_history.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(FORCE_HEADER)
        for vals in force_rows_out:
            w.writerow(fmt(v) for v in vals)
    with open(args.out / "cases.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cases[0]))
        w.writeheader()
        for case in cases:
            w.writerow({k: fmt(v) for k, v in case.items()})
    with open(args.out / "params.json", "w") as fh:
        json.dump(params, fh, indent=2)
        fh.write("\n")

    n_l = sum(c["solver"] == "lumped" for c in cases)
    n_j = sum(c["solver"] == "jc" for c in cases)
    print(
        f"wrote {len(force_rows_out)} force rows (n_samples={n_samples}), "
        f"{len(cases)} cases ({n_l} lumped, {n_j} jc) to {args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
