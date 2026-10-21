"""Performance baseline of the solver entry points on a fixed case set.

Run from the repository root at the end of every Stage 4/5 session::

    .venv/bin/python tools/bench.py            # 3 timed runs per case
    .venv/bin/python tools/bench.py --profile  # ... plus one cProfile run per case

Cases (all inputs come from the golden fixtures and the source workbook; nothing is
synthetic):

* ``lumped_r20``  - golden lumped case ``source_row`` 20 (L = 3 m, f = 2 Hz).
* ``lumped_r80``  - golden lumped case ``source_row`` 80 (L = 48 m, f = 2 Hz).
* ``response_r20``, ``response_r80`` - the same two cases through the Stage 4
  ``response.peak_response`` (structure + loads + NoCoupling); their digests must equal
  the ``lumped_*`` ones.
* ``jc_r96_n2000`` - golden JC case ``source_row`` 96 (L = 24 m, f = 3 Hz) with the force
  history truncated to the first 2000 samples of ``history_B`` so that it finishes
  (the full case is ~1e6 sub-steps). Its result is therefore *not* the golden value.
* ``response_jc_r96_n2000`` - the same truncated case through the Stage 4.2
  ``response.peak_response_jc`` with the legacy flags (``vav_denominator="legacy"``,
  ``parity="per_phase"``); its digest must equal the ``jc_r96_n2000`` one.
* ``pressure_example`` - the ``Example`` sheet ``GetPressureResponse`` call of the source
  workbook (``Example!C3:C123``): valve pattern ``B3:B7``, parameters ``J33:J42``,
  ``pipeArea = PI()*(J39^2/4)``. Transcribed here because ``tools/extract_fixtures.py``
  does not extract that sheet.
* ``response_pressure_example`` - the same call through the Stage 4.3
  ``pressure.pressure_response``; its digest must equal the ``pressure_example`` one.

The "must equal" pairs above (``response_* ↔ lumped_* / jc_* / pressure_example``) are
checked in-run (``DIGEST_PAIRS``): a mismatch is printed and the exit code is 1. The
numerical proof itself lives in ``tests/test_differential.py``; this is a guard against a
bench case drifting from the solver it claims to mirror.

Each case runs ``--repeats`` times (default 3); the median wall time is reported, and for
the peak-response cases the time per SDOF sub-step. The sub-step count is
``n_samples * stepQTY + floor(unb * stepQTY) + 1`` (phase 2 plus the phase-1 delay; phase
3 never runs on these inputs), checked against a call count of the per-sub-step helpers.
For the JC cases the MoC cell-updates per second are also reported: ``sub-steps *
pipeSegQTY / median`` (each sub-step updates one half-grid of ``pipeSegQTY`` cells).

Cloud containers differ between sessions, so absolute times are not comparable across
rows. Case (a), the frozen legacy lumped case ``lumped_r20``, is therefore always run
in-session as the reference (it cannot be skipped with ``--only``) and every case is
reported both in seconds and as a ratio ``median / median(a)``; the README row also
carries the CPU model.

Outputs (committed):

* ``docs/bench/<git-short-sha>.json`` - environment, per-case timings, result digests
  (the five ``outputType = 0`` numbers, or first/max/last of the pressure history) and,
  with ``--profile``, the top 15 functions by cumulative time per case.
* ``docs/bench/README.md`` - one summary row per run, inserted at the end of the main
  table (the JC golden-suite table below it is maintained by hand).

The table printed at the end carries a "vs prev" column (previous median / this median,
> 1 is faster) and a result-digest comparison against the most recent other JSON in
``docs/bench/``, so a Stage 4 refactor sees at once whether it changed timing or numbers.

Requires the ``dev`` extra (``pytest``) because the golden-case loaders are imported
from ``tests/test_golden.py`` rather than duplicated here.
"""

from __future__ import annotations

import argparse
import cProfile
import datetime as dt
import gc
import json
import math
import os
import platform
import pstats
import statistics
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))

import test_golden as tg  # noqa: E402  (tests/test_golden.py: fixture loaders)

from surge_sdof import legacy_port as lp  # noqa: E402
from surge_sdof import moc, pressure, response, structure  # noqa: E402

BENCH_DIR = REPO / "docs" / "bench"
README = BENCH_DIR / "README.md"
TOP_N = 15

# Example!B3:B7 and J33:J42 of tests/fixtures/source/surge_force_data.xlsm, as cached by
# Excel. pipe_area is the formula PI()*(J39^2/4) with J39 = 200 (mm).
EXAMPLE_VALVE_PATTERN = np.array([0.0, 0.2, 0.5, 0.8, 1.0]).reshape(-1, 1)
EXAMPLE_PRESSURE_KW = dict(
    closure_time=1.2,
    celerity=1400.0,
    density=1000.0,
    time_step=0.01,
    pressure_drop_from_pump=0.0001,
    flow_rate=500.0,
    pipe_area=math.pi * (200.0**2 / 4),
    valve_cv=1800.0,
    length_to_pump=400.0,
    pump_ramp_pressure=2.0,
)
JC_TRUNCATE = 2000
REFERENCE_CASE = "lumped_r20"  # case (a): always run, every case is also a ratio to it
# (refactored case, literal-port case) whose result digests must be identical in a run
DIGEST_PAIRS = (
    ("response_r20", "lumped_r20"),
    ("response_r80", "lumped_r80"),
    ("response_jc_r96_n2000", "jc_r96_n2000"),
    ("response_pressure_example", "pressure_example"),
)


def check_digest_pairs(run) -> bool:
    """Print the paired-digest comparison; True when every pair present in the run matches."""
    by_id = {c["id"]: c for c in run["cases"]}
    ok = True
    for new_id, ref_id in DIGEST_PAIRS:
        if new_id in by_id and ref_id in by_id:
            same = by_id[new_id]["result"] == by_id[ref_id]["result"]  # the stored digest
            ok &= same
            print(f"digest {new_id} == {ref_id}: {'yes' if same else 'NO'}")
    return ok


LEGACY_FLAGS = dict(vav_denominator="legacy", parity="per_phase")


def substep_count(n_samples, kw):
    """SDOF sub-steps executed by get_peak_response(_jc) for a single-column history."""
    unb = kw["physical_length"] / (kw["celerity"] / kw["sample_freq"])
    s = kw["step_qty"]
    return n_samples * s + math.floor(unb * s) + 1


def pipe_seg_qty(kw):
    """``pipeSegQTY`` of a JC case (cells of the MoC grid), from the same set-up the
    solvers use."""
    dt = 1 / (kw["sample_freq"] * kw["step_qty"])
    h = structure.solve_portal_height(
        kw["physical_length"], kw["flexural_rigidity_ei"], kw["mass_per_unit_len"], kw["nat_freq"]
    )
    return moc.grid_size(kw["physical_length"], h, kw["celerity"], dt)[0]


def build_cases():
    params = tg.load_params()
    force = tg.load_force(params)
    by_row = {c["source_row"]: c for c in tg.load_cases()}

    def peak_case(cid, row, solver, n=None, summary=lambda res: res, flags=None):
        case = by_row[row]
        kw = tg.case_params(case, params)
        if flags:
            kw = dict(kw, **flags)
        hist = force if n is None else force[:n]
        expected = (
            None if n is not None else [float(case[name]) for name in params["expected_outputs"]]
        )
        return {
            "id": cid,
            "description": f"golden {case['solver']} source_row {row} ({case['case_id']})"
            + (f", first {n} samples" if n is not None else "")
            + (f" via {solver.__module__}.{solver.__name__}")
            + (f" {flags}" if flags else ""),
            "run": lambda: summary(solver(hist, **kw)),
            "substeps": substep_count(hist.shape[0], kw),
            "cells": pipe_seg_qty(kw) if case["solver"] == "jc" else None,
            "expected": expected,
            "digest": lambda res: [float(v) for v in res],
        }

    def peak_response_summary(res):
        return res.summary()

    def pressure_case(cid, solver, description):
        return {
            "id": cid,
            "description": description,
            "run": lambda: solver(EXAMPLE_VALVE_PATTERN, **EXAMPLE_PRESSURE_KW),
            "substeps": None,
            "cells": None,
            "expected": None,
            "digest": lambda res: {
                "first": float(res[0]),
                "max": float(np.max(res)),
                "last": float(res[-1]),
                "len": int(res.shape[0]),
            },
        }

    pressure_legacy = pressure_case(
        "pressure_example",
        lp.get_pressure_response,
        "Example sheet GetPressureResponse (Example!C3:C123)",
    )
    pressure_new = pressure_case(
        "response_pressure_example",
        pressure.pressure_response,
        "Example sheet GetPressureResponse via surge_sdof.pressure.pressure_response",
    )
    return [
        peak_case("lumped_r20", "20", lp.get_peak_response),
        peak_case("lumped_r80", "80", lp.get_peak_response),
        peak_case("response_r20", "20", response.peak_response, summary=peak_response_summary),
        peak_case("response_r80", "80", response.peak_response, summary=peak_response_summary),
        peak_case("jc_r96_n2000", "96", lp.get_peak_response_jc, n=JC_TRUNCATE),
        peak_case(
            "response_jc_r96_n2000",
            "96",
            response.peak_response_jc,
            n=JC_TRUNCATE,
            summary=peak_response_summary,
            flags=LEGACY_FLAGS,
        ),
        pressure_legacy,
        pressure_new,
    ]


# ------------------------------------------------------------------ environment


def git(*args):
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def cpu_model():
    try:
        with open("/proc/cpuinfo") as fh:
            for line in fh:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine() or "unknown"


def environment():
    try:
        import numba

        numba_version = numba.__version__
    except ImportError:
        numba_version = "absent"
    return {
        "git_sha": git("rev-parse", "HEAD"),
        "git_short_sha": git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain", "--", "src", "tests", "tools")),
        "date": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "numba": numba_version,
        "numba_disable_jit": os.environ.get("NUMBA_DISABLE_JIT"),
        "cpu": cpu_model(),
        "platform": platform.platform(),
    }


# ------------------------------------------------------------------ measurement


def time_case(case, repeats):
    times, result = [], None
    for _ in range(repeats):
        gc.collect()
        t0 = time.perf_counter()
        result = case["run"]()
        times.append(time.perf_counter() - t0)
    return times, result


def rel_path(filename):
    try:
        return str(Path(filename).resolve().relative_to(REPO))
    except ValueError:
        return filename


def profile_case(case):
    pr = cProfile.Profile()
    pr.enable()
    case["run"]()
    pr.disable()
    st = pstats.Stats(pr)
    st.sort_stats("cumulative")
    rows = []
    for func in st.fcn_list[:TOP_N]:
        cc, nc, tt, ct, _callers = st.stats[func]
        filename, line, name = func
        rows.append(
            {
                "function": f"{rel_path(filename)}:{line}({name})",
                "ncalls": nc,
                "primitive_calls": cc,
                "tottime_s": round(tt, 6),
                "cumtime_s": round(ct, 6),
            }
        )
    return {"total_s": round(st.total_tt, 6), "total_calls": st.total_calls, "top": rows}


def run_cases(cases, repeats, profile):
    out = []
    for case in cases:
        print(f"{case['id']}: timing x{repeats} ...", flush=True)
        times, result = time_case(case, repeats)
        median = statistics.median(times)
        row = {
            "id": case["id"],
            "description": case["description"],
            "times_s": [round(t, 6) for t in times],
            "median_s": round(median, 6),
            "substeps": case["substeps"],
            "s_per_substep": round(median / case["substeps"], 12) if case["substeps"] else None,
            "cells": case["cells"],
            "cell_updates_per_s": (
                round(case["substeps"] * case["cells"] / median) if case["cells"] else None
            ),
            "result": case["digest"](result),
        }
        if case["expected"] is not None:
            actual = np.asarray(result, dtype=float)
            expected = np.asarray(case["expected"])
            row["golden_max_rel_err"] = float(np.max(np.abs(actual - expected) / np.abs(expected)))
        if profile:
            print(f"{case['id']}: profiling ...", flush=True)
            row["profile"] = profile_case(case)
        print(f"{case['id']}: median {median:.3f} s", flush=True)
        out.append(row)
    ref = next(c["median_s"] for c in out if c["id"] == REFERENCE_CASE)
    for row in out:
        row["ratio_to_reference"] = round(row["median_s"] / ref, 4)
    return out


# ------------------------------------------------------------------ reporting


def previous_run(current_sha):
    """Most recent docs/bench/*.json (by its recorded date) other than the current sha."""
    best = None
    for path in BENCH_DIR.glob("*.json"):
        if path.stem == current_sha:
            continue
        try:
            with open(path) as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if best is None or data.get("date", "") > best.get("date", ""):
            best = data
    return best


def fmt_time(seconds):
    return f"{seconds * 1e3:.2f} ms" if seconds < 0.1 else f"{seconds:.3f} s"


def print_table(run, prev):
    prev_cases = {c["id"]: c for c in prev["cases"]} if prev else {}
    header = ("case", "median", "x ref (a)", "per sub-step", "cells/s", "vs prev", "result vs prev")
    rows = []
    for c in run["cases"]:
        p = prev_cases.get(c["id"])
        if p is None:
            speed, same = "-", "-"
        else:
            speed = f"{p['median_s'] / c['median_s']:.2f}x"
            same = "same" if p.get("result") == c["result"] else "DIFFERS"
        per = f"{c['s_per_substep'] * 1e6:.3f} us" if c["s_per_substep"] else "-"
        cells = f"{c['cell_updates_per_s'] / 1e6:.2f} M" if c.get("cell_updates_per_s") else "-"
        ratio = f"{c['ratio_to_reference']:.3f}"
        rows.append((c["id"], fmt_time(c["median_s"]), ratio, per, cells, speed, same))
    widths = [max(len(str(r[i])) for r in rows + [header]) for i in range(len(header))]
    print()
    print(" | ".join(h.ljust(w) for h, w in zip(header, widths, strict=True)))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(" | ".join(str(v).ljust(w) for v, w in zip(r, widths, strict=True)))
    if prev:
        print(f"\nprevious: {prev['git_short_sha']} ({prev['date']})")
    for c in run["cases"]:
        if "profile" in c:
            print(f"\n{c['id']}: top {TOP_N} by cumulative time (cProfile, one run)")
            print(f"{'ncalls':>12} {'tottime':>10} {'cumtime':>10}  function")
            for f in c["profile"]["top"]:
                print(
                    f"{f['ncalls']:>12} {f['tottime_s']:>10.3f} {f['cumtime_s']:>10.3f}  {f['function']}"
                )


README_HEADER = (
    "# Benchmark history\n\n"
    "One row per `tools/bench.py` run (median of the timed repeats). Cloud containers differ "
    "between sessions, so absolute times are not comparable across rows: case (a), the frozen "
    "legacy lumped case, is re-run in-session as the reference and every other case is given "
    "in seconds and, in brackets, as the ratio of its median to (a)'s. `(c)` and `(g)` are the "
    "JC case truncated to 2000 samples through the literal port and through "
    "`response.peak_response_jc` (legacy flags); `(e)`/`(f)` are `(a)`/`(b)` through "
    "`response.peak_response`; `(h)` is `(d)` through `pressure.pressure_response`; `cells/s` is MoC cell-updates per second (sub-steps x pipeSegQTY "
    "/ s). `sha` is HEAD when the run started (`-dirty` = uncommitted changes under "
    "src/tests/tools), so the commit that adds a row is that sha's child. Details, result "
    "digests and profiles are in `<sha>.json` next to this file.\n\n"
    "| date (UTC) | sha | python | numpy | numba | NUMBA_DISABLE_JIT | cpu | (a) lumped r20 | "
    "(b) lumped r80 | (c) jc r96 n2000 | (d) pressure example | (e) response r20 | "
    "(f) response r80 | (g) response_jc r96 n2000 | (h) response_pressure example | "
    "(c) us/sub-step | (g) us/sub-step | "
    "(c) cells/s | (g) cells/s | profile |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
)


def fmt_ratio(c):
    return f"{fmt_time(c['median_s'])} [{c['ratio_to_reference']:.2f}]"


def readme_row(run):
    by_id = {c["id"]: c for c in run["cases"]}
    jc, rjc = by_id["jc_r96_n2000"], by_id["response_jc_r96_n2000"]
    sha = run["git_short_sha"] + ("-dirty" if run["git_dirty"] else "")
    return (
        f"| {run['date']} | {sha} | {run['python']} | {run['numpy']} | {run['numba']} | "
        f"{run['numba_disable_jit'] or '-'} | {run['cpu']} | "
        f"{fmt_time(by_id[REFERENCE_CASE]['median_s'])} | "
        f"{fmt_ratio(by_id['lumped_r80'])} | {fmt_ratio(jc)} | "
        f"{fmt_ratio(by_id['pressure_example'])} | {fmt_ratio(by_id['response_r20'])} | "
        f"{fmt_ratio(by_id['response_r80'])} | {fmt_ratio(rjc)} | "
        f"{fmt_ratio(by_id['response_pressure_example'])} | "
        f"{jc['s_per_substep'] * 1e6:.1f} | {rjc['s_per_substep'] * 1e6:.1f} | "
        f"{jc['cell_updates_per_s'] / 1e6:.2f} M | {rjc['cell_updates_per_s'] / 1e6:.2f} M | "
        f"{'yes' if run['profile'] else 'no'} |\n"
    )


def append_readme(run):
    """Insert the row at the end of the main table (the first table in the file), so that
    tables maintained by hand below it stay intact."""
    row = readme_row(run)
    if not README.exists():
        README.write_text(README_HEADER + row)
        return
    lines = README.read_text().splitlines(keepends=True)
    header_at = next(i for i, line in enumerate(lines) if line.startswith("| date (UTC) |"))
    end = header_at + 1
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    lines.insert(end, row)
    README.write_text("".join(lines))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--profile", action="store_true", help="also run each case once under cProfile")
    ap.add_argument("--repeats", type=int, default=3, help="timed runs per case (default 3)")
    ap.add_argument(
        "--only", action="append", help="run only this case id (repeatable); no files written"
    )
    args = ap.parse_args(argv)

    env = environment()
    cases = build_cases()
    if args.only:
        cases = [c for c in cases if c["id"] in args.only or c["id"] == REFERENCE_CASE]
    run = dict(env, repeats=args.repeats, profile=args.profile, cases=[])
    run["cases"] = run_cases(cases, args.repeats, args.profile)

    prev = previous_run(env["git_short_sha"])
    print_table(run, prev)
    if args.only:
        return 0

    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    out = BENCH_DIR / f"{env['git_short_sha']}.json"
    with open(out, "w") as fh:
        json.dump(run, fh, indent=1)
        fh.write("\n")
    append_readme(run)
    pairs_ok = check_digest_pairs(run)
    print(f"\nwrote {out.relative_to(REPO)} and appended {README.relative_to(REPO)}")
    return 0 if pairs_ok else 1


if __name__ == "__main__":
    sys.exit(main())
