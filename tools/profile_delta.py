"""Measure what the fraction-profile correction changes (NOTES.md "Session F-4 / F-4b").

Runs ``response.peak_response_jc`` on the three JC golden rows (96 / 97 / 98) and on the 50
cases of the JC differential sweep (``tests/test_differential.jc_sweep_cases``) with three
flag sets and prints the relative change of the five output-type-0 maxima against the legacy
result:

* ``legacy``: ``vav_denominator="legacy", parity="per_phase", fraction_profile="legacy"``
  (bitwise the literal port; checked here against ``legacy_port.get_peak_response_jc`` on
  the sweep and against the cached legacy ``actual`` of ``tests/.golden_cache`` on the golden
  rows);
* ``F-4 alone``: the legacy flags with ``fraction_profile="fixed"``;
* ``defaults``: no flags (F-1 + F-2 + F-4).

Golden rows need ``tests/.golden_cache/<case>_response.json`` (written by the ``jc_slow``
tests; ``actual`` is the legacy-flag result, ``expected`` Excel). Output is Markdown for the
NOTES tables; ``--json <file>`` also writes every number. Numba is used when available.

    .venv/bin/python tools/profile_delta.py            # both tables
    .venv/bin/python tools/profile_delta.py --golden   # golden rows only
    .venv/bin/python tools/profile_delta.py --sweep    # sweep only
    .venv/bin/python tools/profile_delta.py --tier-csv docs/sweep/tier1_<old>.csv docs/sweep/tier1_<new>_f4b.csv

``--tier-csv OLD NEW`` compares two Session 5b sweep CSVs (``tools/sweep_jc.py run``) row by
row (``case_id``): the lumped columns must be bitwise equal (the profile never reaches the
lumped solver), the applied-force peak too; for every JC column and ratio it prints the number
of changed rows and the max / median relative change, the paragraph of ``docs/jc_sweep_f4b.md``.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "tools"))

import cases  # noqa: E402
import test_differential as td  # noqa: E402

from surge_sdof import legacy_port as lp  # noqa: E402
from surge_sdof import response  # noqa: E402

GOLDEN = ["r096_jc_L24_f3", "r097_jc_L24_f7.5", "r098_jc_L24_f22"]
OUTPUTS = ["f_static_eq", "displacement", "velocity", "acceleration", "applied_force"]
FLAG_SETS = {
    "legacy": td.LEGACY_FLAGS,
    "F-4 alone": dict(td.LEGACY_FLAGS, fraction_profile="fixed"),
    "defaults": {},
}
CACHE = REPO / "tests" / ".golden_cache"


def rel(summary, base):
    """Signed relative change per output; 0 where both are equal (0 / 0 included)."""
    out = np.zeros_like(summary)
    diff = summary != base
    out[diff] = (summary[diff] - base[diff]) / np.abs(base[diff])
    return out


def fmt(x):
    return "0" if x == 0 else f"{x:+.1e}"


def run_golden():
    rows = []
    for case_id in GOLDEN:
        force, kw, solver = cases.golden_case(case_id)
        assert solver == "jc"
        cache = json.loads((CACHE / f"{case_id}_response.json").read_text())
        legacy, excel = np.array(cache["actual"]), np.array(cache["expected"])
        res = {}
        t0 = time.perf_counter()
        for name, flags in FLAG_SETS.items():
            res[name] = response.peak_response_jc(
                force, **dict(kw, output_type=0), **flags
            ).summary()
        elapsed = time.perf_counter() - t0
        assert np.array_equal(res["legacy"], legacy), f"{case_id}: legacy flags != cached legacy"
        rows.append(
            {
                "case_id": case_id,
                "time_s": elapsed,
                "f4_vs_legacy": rel(res["F-4 alone"], legacy).tolist(),
                "defaults_vs_legacy": rel(res["defaults"], legacy).tolist(),
                "defaults_vs_excel": rel(res["defaults"], excel).tolist(),
                "peak_velocity_legacy": float(legacy[2]),
                "peak_velocity_f4": float(res["F-4 alone"][2]),
                "peak_velocity_defaults": float(res["defaults"][2]),
                "max_displacement_defaults": float(res["defaults"][1]),
            }
        )
    print("| row | time (s) | F-4 alone vs legacy | defaults vs legacy | defaults vs Excel |")
    print("|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['case_id']} | {r['time_s']:.1f} | "
            + " / ".join(fmt(x) for x in r["f4_vs_legacy"])
            + " | "
            + " / ".join(fmt(x) for x in r["defaults_vs_legacy"])
            + " | "
            + " / ".join(fmt(x) for x in r["defaults_vs_excel"])
            + " |"
        )
    print(
        "\nPeak velocity, F-4 alone vs legacy: "
        + ", ".join(f"{r['case_id']} {fmt(r['f4_vs_legacy'][2])}" for r in rows)
    )
    print(
        "max |relative change| on the golden cases, F-4 alone: "
        f"{max(np.max(np.abs(r['f4_vs_legacy'])) for r in rows):.2e}; defaults vs Excel: "
        f"{max(np.max(np.abs(r['defaults_vs_excel'])) for r in rows):.2e}"
    )
    return rows


def run_sweep():
    rows = []
    for case in td.jc_sweep_cases():
        base = lp.get_peak_response_jc(case.force, **case.kw, output_type=0)
        res = {
            name: response.peak_response_jc(case.force, **case.kw, output_type=0, **flags).summary()
            for name, flags in FLAG_SETS.items()
        }
        assert np.array_equal(res["legacy"], base), f"{case.id}: legacy flags != legacy_port"
        f12 = response.peak_response_jc(
            case.force, **case.kw, output_type=0, fraction_profile="legacy"
        ).summary()
        rows.append(
            {
                "case_id": case.id,
                "fluid_area": case.kw["fluid_area"],
                "fallback": case.fallback,
                "f1_f2": float(np.max(np.abs(rel(f12, base)))),
                "f4": float(np.max(np.abs(rel(res["F-4 alone"], base)))),
                "all": float(np.max(np.abs(rel(res["defaults"], base)))),
                "f4_velocity": float(rel(res["F-4 alone"], base)[2]),
                "f4_per_output": rel(res["F-4 alone"], base).tolist(),
            }
        )
    f4 = np.array([r["f4"] for r in rows])
    allf = np.array([r["all"] for r in rows])
    v = np.array([r["f4_velocity"] for r in rows])
    changed = f4 > 0
    imax = int(np.argmax(f4))
    print(
        f"F-4 alone: max {f4.max():.2e} ({rows[imax]['case_id'][:3]}), median {np.median(f4):.2e} "
        f"over all {len(rows)} cases, {np.median(f4[changed]):.2e} over the {changed.sum()} "
        f"changed cases; peak velocity: max {np.max(np.abs(v)):.2e} "
        f"({rows[int(np.argmax(np.abs(v)))]['case_id'][:3]}), median {np.median(np.abs(v)):.1e} "
        f"(all) / {np.median(np.abs(v[changed])):.1e} (changed), {(v > 0).sum()} up, "
        f"{(v < 0).sum()} down. All three: max {allf.max():.2e}, median {np.median(allf):.2e} / "
        f"{np.median(allf[changed]):.2e}. Unchanged cases: {(~changed).sum()}."
    )
    unchanged_ok = all((r["fallback"] or r["fluid_area"] == 0.0) == (r["f4"] == 0.0) for r in rows)
    print(f"unchanged cases are exactly the no-fluid and fallback cases: {unchanged_ok}")
    print(
        "\n| case | fluidArea | fallback | F-1+F-2 | F-4 alone | all three | "
        "F-4 alone, peak velocity (signed) |"
    )
    print("|---|---|---|---|---|---|---|")

    def cell(x, signed=False):
        if x == 0:
            return "0"
        return f"{x:+.1e}" if signed else f"{x:.1e}"

    for r in rows:
        print(
            f"| {r['case_id']} | {r['fluid_area']} | {'yes' if r['fallback'] else '-'} | "
            f"{cell(r['f1_f2'])} | {cell(r['f4'])} | {cell(r['all'])} | "
            f"{cell(r['f4_velocity'], signed=True)} |"
        )
    return rows


LUMPED_COLUMNS = [
    "f_eq_lumped",
    "v_peak_lumped",
    "momentum_lumped",
    "ke_peak_lumped",
    "x_peak_lumped",
    "a_peak_lumped",
    "f_peak_lumped",
    "f_eq_over_LD2_lumped",
    "daf_lumped",
]
JC_COLUMNS = [
    "f_eq_jc",
    "x_peak_jc",
    "v_peak_jc",
    "a_peak_jc",
    "momentum_jc",
    "ke_peak_jc",
    "f_eq_over_LD2_jc",
    "daf_jc",
    "ratio_f_eq",
    "ratio_v_peak",
]
UNCHANGED_JC_COLUMNS = ["f_peak_jc"]  # the applied-force peak never depends on the fluid


def _read_csv(path):
    import csv

    with open(path, newline="", encoding="utf-8") as fh:
        return {r["case_id"]: r for r in csv.DictReader(fh)}


def run_tier_csv(old_path, new_path):
    old, new = _read_csv(old_path), _read_csv(new_path)
    assert set(old) == set(new), "the two CSVs do not hold the same case ids"
    ids = sorted(old)
    assert all(old[i]["error"] == new[i]["error"] == "" for i in ids), "rows with errors"
    for col in LUMPED_COLUMNS + UNCHANGED_JC_COLUMNS:
        same = all(float(old[i][col]) == float(new[i][col]) for i in ids)
        assert same, f"{col} differs between the two CSVs"
    print(
        f"`{pathlib.Path(new_path).name}` vs `{pathlib.Path(old_path).name}`: {len(ids)} rows, "
        f"the {len(LUMPED_COLUMNS)} lumped columns and `f_peak_jc` bitwise equal."
    )
    print()
    print(
        "| column | rows changed | max rel. change | median rel. change (changed rows) | max case |"
    )
    print("|---|---|---|---|---|")
    summary = {}
    for col in JC_COLUMNS:
        o = np.array([float(old[i][col]) for i in ids])
        n = np.array([float(new[i][col]) for i in ids])
        r = rel(n, o)
        changed = r != 0
        imax = int(np.argmax(np.abs(r)))
        med = float(np.median(np.abs(r[changed]))) if changed.any() else 0.0
        summary[col] = {
            "changed": int(changed.sum()),
            "max": float(np.abs(r).max()),
            "max_signed": float(r[imax]),
            "median_changed": med,
            "max_case": ids[imax],
        }
        print(
            f"| `{col}` | {changed.sum()} of {len(ids)} | {r[imax]:+.2e} | {med:.2e} | {ids[imax]} |"
        )
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--golden", action="store_true", help="golden rows only")
    ap.add_argument("--sweep", action="store_true", help="sweep only")
    ap.add_argument("--json", help="also write every number to this file")
    ap.add_argument(
        "--tier-csv", nargs=2, metavar=("OLD", "NEW"), help="compare two Session 5b sweep CSVs"
    )
    args = ap.parse_args(argv)
    out = {}
    if args.tier_csv:
        out["tier_csv"] = run_tier_csv(*args.tier_csv)
        if args.json:
            pathlib.Path(args.json).write_text(json.dumps(out, indent=1))
        return
    both = not (args.golden or args.sweep)
    if both or args.golden:
        out["golden"] = run_golden()
    if both or args.sweep:
        if both:
            print()
        out["sweep"] = run_sweep()
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
