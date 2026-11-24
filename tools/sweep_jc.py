#!/usr/bin/env python
"""Session 5b: quantify the junction-coupling effect with canonical load histories.

    .venv/bin/python tools/sweep_jc.py check                  # pipe table vs the owner's figures
    .venv/bin/python tools/sweep_jc.py run --tier 1 --subset 0.1   # stratified 10 % of Tier 1
    .venv/bin/python tools/sweep_jc.py run --tier 1               # full Tier 1
    .venv/bin/python tools/sweep_jc.py run --tier 2 --jobs 8      # Tier 2 (the owner, locally)
    .venv/bin/python tools/sweep_jc.py plot docs/sweep/<csv>      # PNGs + docs/jc_sweep.md

Every case runs both solvers, ``response.peak_response`` (lumped) and
``response.peak_response_jc`` (junction coupling, the fixed-path defaults F-1 / F-2 / F-4 on),
with ``restrainFreqRatio = 1``, ``gap = 0`` (inert at ratio 1), ``stepQTY = 40``, celerity
1237 m/s, damping 0.5 %, ``E = 195e9`` Pa. The force history is a ``surge_sdof.histories``
pressure history (``canonical``) times the size's fluid area. Pipe OD / thickness come from the
workbook's ``curve_10in!J7:M8`` table (``PIPES``) and mass, EI and fluid area from the sheet's
formulas (H11, H13, H15, J15); ``p_design = 2 t S / OD`` with ``S = 138`` MPa.

The CSV (``docs/sweep/tier<N>[_subset<pct>]_<sha>[_<tag>].csv``, the ``export.SWEEP_COLUMNS``,
documented in ``docs/data_format.md`` "sweep.columns"; ``tools/export.py sweep --from-csv``
converts it to the ``sweep`` JSON document) carries every parameter of a row's history
(``surge_sdof.histories.from_params`` rebuilds it bitwise through ``history_from_row``), the
results of both solvers, the JC / lumped ratios, the normalised forces, timings, CPU and git
sha. A failed solver run is recorded in ``error`` with its result columns empty; the sweep never
skips a case silently.
The script runs the sweep and the report; the parts live beside it (review session R.8, plan
5.12): ``sweep_grid.py`` (the fixed inputs, the pipe table, the tiers' cases),
``sweep_rows.py`` (one case to its row, the CSV writer) and ``sweep_report.py`` (the plots
and ``docs/jc_sweep.md``).
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from sweep_grid import (  # noqa: E402  (tools/sweep_grid.py: the inputs and the case grid)
    TIERS,
    check_pipe_table,
    coverage,
    stratified_subset,
    tier_cases,
)
from sweep_report import (  # noqa: E402  (tools/sweep_report.py: the plots and the report)
    _load,
    plot_collapse,
    plot_daf,
    plot_ratio,
    write_doc,
)
from sweep_rows import RunProvenance, run_case, write_csv  # noqa: E402  (one case to a row)

from surge_sdof import histories  # noqa: E402

# ------------------------------------------------------------------ the run


def git(*args) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def git_sha_tag() -> str:
    sha = git("rev-parse", "--short", "HEAD") or "nogit"
    if git("status", "--porcelain", "--", "src", "tests", "tools"):
        sha += "-dirty"
    return sha


def cpu_model() -> str:
    try:
        with open("/proc/cpuinfo") as fh:
            for line in fh:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine() or "unknown"


def _worker(args):
    case, provenance = args
    return run_case(case, provenance)


def run(args) -> Path:
    check_pipe_table(verbose=False)
    tier = args.tier
    cases = tier_cases(tier)
    subset = ""
    if args.subset:
        cases = stratified_subset(cases, args.subset, args.subset_seed)
        subset = f"subset{round(args.subset * 100):g}"
    if args.limit:
        cases = cases[: args.limit]
    if args.history:
        cases = [c for c in cases if c.history_type == args.history]
    cpu = cpu_model()
    sha = git_sha_tag()
    tag = f"_{args.tag}" if args.tag else ""
    name = f"tier{tier}{'_' + subset if subset else ''}{'_limit' + str(args.limit) if args.limit else ''}_{sha}{tag}.csv"
    out = Path(args.out) / name
    print(f"tier {tier}: {len(cases)} cases, {args.jobs} jobs, cpu {cpu}, sha {sha}")
    for d, c in coverage(cases).items():
        print(
            f"  {d}: "
            + ", ".join(f"{k!r}: {v}" for k, v in sorted(c.items(), key=lambda kv: repr(kv[0])))
        )
    t_start = time.perf_counter()
    rows = []
    provenance = RunProvenance(tier, subset, cpu, sha)
    jobs = [(c, provenance) for c in cases]
    done = 0
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for row in pool.map(_worker, jobs, chunksize=1):
            rows.append(row)
            done += 1
            if done % args.progress == 0 or done == len(cases):
                elapsed = time.perf_counter() - t_start
                print(
                    f"  {done}/{len(cases)} in {elapsed:.0f} s "
                    f"({elapsed / done:.2f} s/case wall, {len(cases) * elapsed / done - elapsed:.0f} s left)",
                    flush=True,
                )
    wall = time.perf_counter() - t_start
    write_csv(out, rows)
    errors = [r for r in rows if r["error"]]
    t_l = sum(r["t_lumped_s"] or 0 for r in rows)
    t_j = sum(r["t_jc_s"] or 0 for r in rows)
    print(
        f"wrote {out} ({len(rows)} rows, {len(errors)} with errors); wall {wall:.0f} s; "
        f"solver CPU: lumped {t_l:.0f} s, jc {t_j:.0f} s "
        f"(mean {t_l / len(rows):.3f} / {t_j / len(rows):.3f} s per case)"
    )
    for r in errors:
        print(f"  {r['case_id']}: {r['error']}")
    return out


def plot(args) -> None:
    import matplotlib

    matplotlib.use("Agg")
    csv_path = Path(args.csv)
    rows = _load(csv_path)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    mus = sorted({r["mu"] for r in rows})
    mu_on = args.mu if args.mu is not None else max(mus)
    amps = sorted({r["amplitude_fraction"] for r in rows})
    amp = args.amplitude if args.amplitude is not None else max(amps)
    stem = csv_path.stem
    pngs = {
        "ratio_f_eq": out_dir / f"{stem}_ratio_f_eq.png",
        "ratio_v_peak": out_dir / f"{stem}_ratio_v_peak.png",
        "daf": out_dir / f"{stem}_daf.png",
        "collapse": out_dir / f"{stem}_collapse.png",
    }
    plot_ratio(
        rows,
        "ratio_f_eq",
        "F_eq JC / lumped",
        pngs["ratio_f_eq"],
        "JC / lumped equivalent static force",
        mu_on,
    )
    plot_ratio(
        rows,
        "ratio_v_peak",
        "v_peak JC / lumped",
        pngs["ratio_v_peak"],
        "JC / lumped peak velocity",
        mu_on,
    )
    plot_daf(rows, pngs["daf"], mu_on)
    plot_collapse(rows, pngs["collapse"], mu_on, amp)
    write_doc(rows, csv_path, pngs, Path(args.doc), mu_on, amp)
    print("wrote", Path(args.doc), *pngs.values(), sep="\n  ")


# ------------------------------------------------------------------ CLI


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="assert the pipe table against the owner's design pressures")
    r = sub.add_parser(
        "run",
        help="run a tier (or --limit / --subset of it for a smoke run) and write the CSV into --out",
    )
    r.add_argument("--tier", type=int, choices=sorted(TIERS), required=True)
    r.add_argument(
        "--subset",
        type=float,
        default=0.0,
        help="fraction of the tier (0 < f <= 1), stratified over every dimension (smoke run)",
    )
    r.add_argument("--subset-seed", type=int, default=0)
    r.add_argument("--limit", type=int, default=0, help="first N cases only (smoke test)")
    r.add_argument(
        "--history", choices=histories.HISTORY_TYPES, default=None, help="one history type only"
    )
    r.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    r.add_argument("--progress", type=int, default=25, help="print progress every N cases")
    r.add_argument(
        "--out",
        default=str(REPO / "docs" / "sweep"),
        help="directory the CSV is written into (default docs/sweep); the file is named by tier, git sha and --tag",
    )
    r.add_argument(
        "--tag",
        default="",
        help="suffix of the CSV name after the sha (a rerun, e.g. after the F-4b profile correction, must not overwrite an earlier file)",
    )
    p = sub.add_parser("plot", help="PNGs and docs/jc_sweep.md from a sweep CSV")
    p.add_argument("csv")
    p.add_argument("--out", default=str(REPO / "docs" / "sweep" / "png"))
    p.add_argument("--doc", default=str(REPO / "docs" / "jc_sweep.md"))
    p.add_argument(
        "--mu",
        type=float,
        default=None,
        help="friction level to plot (default: the largest in the CSV)",
    )
    p.add_argument(
        "--amplitude",
        type=float,
        default=None,
        help="amplitude for the collapse panel (default: the largest)",
    )
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.command == "check":
        check_pipe_table()
    elif args.command == "run":
        run(args)
    else:
        plot(args)


if __name__ == "__main__":
    main()
