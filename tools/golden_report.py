"""Print the golden-master report table from the results cached by tests/test_golden.py.

Run ``pytest -q tests/test_golden.py -m slow`` (or ``-m "slow or jc_slow"``) first; each
case writes ``tests/.golden_cache/<case_id>.json``. This script only reads those files and
``tests/fixtures/curve_10in/cases.csv``; it never runs a solver and never writes.

Columns: case id, output name of the worst output, max |rel err|, max |abs err|, status.
Status is PASS / FAIL (per the tolerance the test used) or "not run" for a case without a
cached result. For every FAIL the first failing output index and the two values follow.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CASES_CSV = REPO / "tests" / "fixtures" / "curve_10in" / "cases.csv"
CACHE_DIR = REPO / "tests" / ".golden_cache"


def main() -> int:
    with open(CASES_CSV, newline="") as fh:
        cases = list(csv.DictReader(fh))
    header = ("case id", "output", "max |rel err|", "max |abs err|", "status")
    rows, failures, counts = [], [], {"PASS": 0, "FAIL": 0, "not run": 0}
    for case in cases:
        path = CACHE_DIR / f"{case['case_id']}.json"
        if not path.exists():
            rows.append((case["case_id"], "-", "-", "-", "not run"))
            counts["not run"] += 1
            continue
        with open(path) as fh:
            res = json.load(fh)
        worst = max(range(len(res["outputs"])), key=lambda i: res["rel_err"][i])
        status = "PASS" if res["passed"] else "FAIL"
        counts[status] += 1
        rows.append(
            (
                case["case_id"],
                res["outputs"][worst],
                f"{max(res['rel_err']):.3e}",
                f"{max(res['abs_err']):.3e}",
                status,
            )
        )
        if not res["passed"]:
            tol = res["rtol"]
            idx = next(
                i
                for i, (a, e) in enumerate(zip(res["actual"], res["expected"], strict=True))
                if abs(a - e) > tol * abs(e)
            )
            failures.append(
                (
                    case["case_id"],
                    idx,
                    res["outputs"][idx],
                    res["actual"][idx],
                    res["expected"][idx],
                )
            )

    widths = [max(len(str(r[i])) for r in rows + [header]) for i in range(len(header))]
    line = " | ".join(h.ljust(w) for h, w in zip(header, widths, strict=True))
    print(line)
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(" | ".join(str(v).ljust(w) for v, w in zip(r, widths, strict=True)))
    print()
    print(
        f"{counts['PASS']} PASS, {counts['FAIL']} FAIL, {counts['not run']} not run (of {len(cases)})"
    )
    for case_id, idx, name, a, e in failures:
        print(
            f"FAIL {case_id}: first failing output index {idx} ({name}): python {a!r}, excel {e!r}"
        )
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
