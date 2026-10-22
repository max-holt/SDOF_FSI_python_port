"""Performance record of the solver entry points on a fixed case set, in three
implementations: the literal port, the Stage 4 modules as plain Python, and the Stage 5
Numba build of the same modules.

Run from the repository root at the end of every Stage 4/5 session::

    .venv/bin/python tools/bench.py            # 3 timed runs per case
    .venv/bin/python tools/bench.py --profile  # ... plus one cProfile run per pure-Python case

Cases (all inputs come from the golden fixtures and the source workbook; nothing is
synthetic). Literal (``legacy_port``, pure Python, run in this process):

* ``lumped_r20``  - golden lumped case ``source_row`` 20 (L = 3 m, f = 2 Hz): case (a),
  the in-session reference every other row is a ratio to.
* ``lumped_r80``  - golden lumped case ``source_row`` 80 (L = 48 m, f = 2 Hz).
* ``jc_r96_n2000`` - golden JC case ``source_row`` 96 (L = 24 m, f = 3 Hz) with the force
  history truncated to the first 2000 samples of ``history_B`` so that it finishes in
  pure Python. Its result is therefore *not* the golden value.
* ``pressure_example`` - the ``Example`` sheet ``GetPressureResponse`` call of the source
  workbook (``Example!C3:C123``): valve pattern ``B3:B7``, parameters ``J33:J42``,
  ``pipeArea = PI()*(J39^2/4)``. Transcribed here because ``tools/extract_fixtures.py``
  does not extract that sheet.

Refactored (``response`` / ``pressure``), run twice in child processes, once with
``NUMBA_DISABLE_JIT=1`` (mode ``python``) and once compiled into a fresh
``NUMBA_CACHE_DIR`` (mode ``numba``, so the first call of each case is a true
first call and the compile time is measured, not a cache load):

* ``response_r20``, ``response_r80`` - the two lumped cases through
  ``response.peak_response``; digests must equal ``lumped_r20`` / ``lumped_r80``.
* ``response_jc_r96_n2000`` - the truncated JC case through ``response.peak_response_jc``
  with the legacy flags (``vav_denominator="legacy"``, ``parity="per_phase"``); digest must
  equal ``jc_r96_n2000``.
* ``response_pressure_example`` - the Example call through ``pressure.pressure_response``;
  digest must equal ``pressure_example``. (``pressure.py`` is not compiled: milliseconds.)
* ``response_jc_r96_full``, ``response_jc_r97_full``, ``response_jc_r98_full`` - the three
  full JC golden cases (25135 samples, stepQTY 40) through ``peak_response_jc`` with the
  legacy flags, compared with the Excel fixture (``golden_max_rel_err``). In mode
  ``python`` they take ~15 min each; ``--skip-full-python`` leaves them out of that mode.

Peak memory: two more children run ``outputType = 1`` on the full history under Numba
(``response_r20``, ``response_jc_r96_full``) and report their ``ru_maxrss`` (the figure
includes the compiler's own footprint).

The "must equal" pairs are checked in-run for both refactored modes (``DIGEST_PAIRS``):
a mismatch is printed and the exit code is 1. The numerical proof itself lives in
``tests/test_differential.py``; this is a guard against a bench case drifting from the
solver it claims to mirror.

Each case runs ``--repeats`` times (default 3); the median wall time is reported and, for
the peak-response cases, the time per SDOF sub-step. The sub-step count is ``n_samples *
stepQTY + floor(unb * stepQTY) + 1`` (phase 2 plus the phase-1 delay; phase 3 never runs on
these inputs). JC cases also report MoC cell-updates per second (``sub-steps * pipeSegQTY /
median``). In mode ``numba`` the first call of every case is timed separately
(``first_call_s``); the compile itself is measured once per child as the first call of the
tiny Example lumped case (``compile_s``), since all cases share one kernel specialisation.

Cloud containers differ between sessions, so absolute times are not comparable across
runs: case (a) is always run in-session (it cannot be skipped with ``--only``) and every
row is reported in seconds and as the ratio ``median / median(a)``.

Outputs (committed):

* ``docs/bench/<git-short-sha>.json`` - environment (python, numpy, numba, llvmlite, CPU),
  compile time, per-case timings per mode, result digests, peak RSS and, with
  ``--profile``, the top 15 functions by cumulative time per pure-Python case.
* ``docs/bench/README.md`` - a section per run with the three rows literal / refactored /
  Numba, appended under "Stage 5 runs" (the pre-Stage-5 history table above it is kept).

The table printed at the end carries a "vs prev" column (previous median / this median,
> 1 is faster) and a result-digest comparison against the most recent other JSON in
``docs/bench/`` (same case id and mode; pre-Stage-5 JSONs are read as literal / python).

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
import resource
import statistics
import subprocess
import sys
import tempfile
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
EXAMPLE_PRESSURE_KW = {
    "closure_time": 1.2,
    "celerity": 1400.0,
    "density": 1000.0,
    "time_step": 0.01,
    "pressure_drop_from_pump": 0.0001,
    "flow_rate": 500.0,
    "pipe_area": math.pi * (200.0**2 / 4),
    "valve_cv": 1800.0,
    "length_to_pump": 400.0,
    "pump_ramp_pressure": 2.0,
}
JC_TRUNCATE = 2000
FULL_JC_ROWS = ("96", "97", "98")
REFERENCE_CASE = "lumped_r20"  # case (a): always run, every case is also a ratio to it
LEGACY_FLAGS = {"vav_denominator": "legacy", "parity": "per_phase"}
# (refactored case, literal-port case) whose result digests must be identical in a run,
# in each refactored mode present
DIGEST_PAIRS = (
    ("response_r20", "lumped_r20"),
    ("response_r80", "lumped_r80"),
    ("response_jc_r96_n2000", "jc_r96_n2000"),
    ("response_pressure_example", "pressure_example"),
)
MODES = ("literal", "python", "numba")
MODE_LABELS = {
    "literal": "literal (`legacy_port`, pure Python)",
    "python": "refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`)",
    "numba": "Numba (Stage 5 `njit`, steady state)",
}
# README columns: (heading, literal case id, refactored case id)
COLUMNS = (
    ("(a) lumped r20", "lumped_r20", "response_r20"),
    ("(b) lumped r80", "lumped_r80", "response_r80"),
    ("(c) jc r96 n2000", "jc_r96_n2000", "response_jc_r96_n2000"),
    ("(d) pressure example", "pressure_example", "response_pressure_example"),
    ("jc r96 full", None, "response_jc_r96_full"),
    ("jc r97 full", None, "response_jc_r97_full"),
    ("jc r98 full", None, "response_jc_r98_full"),
)
RSS_CASES = ("rss_response_r20_type1", "rss_response_jc_r96_full_type1")


def log(msg):
    """Progress line: stdout in the parent, stderr in a worker (its stdout is the JSON)."""
    print(msg, file=sys.stderr if os.environ.get("SURGE_BENCH_WORKER") else sys.stdout, flush=True)


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
    """Every case, each with ``group`` "literal", "refactored" or "rss"."""
    params = tg.load_params()
    force = tg.load_force(params)
    by_row = {c["source_row"]: c for c in tg.load_cases()}

    def peak_case(
        cid, row, solver, group, n=None, summary=lambda res: res, flags=None, output_type=None
    ):
        case = by_row[row]
        kw = tg.case_params(case, params)
        if flags:
            kw = dict(kw, **flags)
        if output_type is not None:
            kw = dict(kw, output_type=output_type)
        hist = force if n is None else force[:n]
        expected = (
            None if n is not None else [float(case[name]) for name in params["expected_outputs"]]
        )
        return {
            "id": cid,
            "group": group,
            "description": f"golden {case['solver']} source_row {row} ({case['case_id']})"
            + (f", first {n} samples" if n is not None else "")
            + (f", outputType {output_type}" if output_type is not None else "")
            + f" via {solver.__module__}.{solver.__name__}"
            + (f" {flags}" if flags else ""),
            "run": lambda: summary(solver(hist, **kw)),
            "substeps": substep_count(hist.shape[0], kw),
            "cells": pipe_seg_qty(kw) if case["solver"] == "jc" else None,
            "expected": expected,
            "digest": lambda res: [float(v) for v in res],
            # cProfile only where it is cheap enough and meaningful (pure Python, not the
            # full JC cases)
            "profile_ok": n is not None or case["solver"] != "jc",
            "full": n is None and case["solver"] == "jc",
        }

    def peak_response_summary(res):
        return res.summary()

    def pressure_case(cid, solver, group, description):
        return {
            "id": cid,
            "group": group,
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
            "profile_ok": True,
            "full": False,
        }

    cases = [
        peak_case("lumped_r20", "20", lp.get_peak_response, "literal"),
        peak_case("lumped_r80", "80", lp.get_peak_response, "literal"),
        peak_case("jc_r96_n2000", "96", lp.get_peak_response_jc, "literal", n=JC_TRUNCATE),
        pressure_case(
            "pressure_example",
            lp.get_pressure_response,
            "literal",
            "Example sheet GetPressureResponse (Example!C3:C123)",
        ),
        peak_case(
            "response_r20",
            "20",
            response.peak_response,
            "refactored",
            summary=peak_response_summary,
        ),
        peak_case(
            "response_r80",
            "80",
            response.peak_response,
            "refactored",
            summary=peak_response_summary,
        ),
        peak_case(
            "response_jc_r96_n2000",
            "96",
            response.peak_response_jc,
            "refactored",
            n=JC_TRUNCATE,
            summary=peak_response_summary,
            flags=LEGACY_FLAGS,
        ),
        pressure_case(
            "response_pressure_example",
            pressure.pressure_response,
            "refactored",
            "Example sheet GetPressureResponse via surge_sdof.pressure.pressure_response",
        ),
    ]
    for row in FULL_JC_ROWS:
        cases.append(
            peak_case(
                f"response_jc_r{row}_full",
                row,
                response.peak_response_jc,
                "refactored",
                summary=peak_response_summary,
                flags=LEGACY_FLAGS,
            )
        )
    cases.append(
        peak_case(
            "rss_response_r20_type1",
            "20",
            response.peak_response,
            "rss",
            summary=peak_response_summary,
            output_type=1,
        )
    )
    cases.append(
        peak_case(
            "rss_response_jc_r96_full_type1",
            "96",
            response.peak_response_jc,
            "rss",
            summary=peak_response_summary,
            flags=LEGACY_FLAGS,
            output_type=1,
        )
    )
    return cases


def example_lumped_call():
    """The tiny Example-sheet lumped case: a few ms of integration, so its first call in a
    fresh process measures the kernel compile."""
    case = next(c for c in tg.EXAMPLE_CASES if c["solver"] == "lumped")
    force = np.asarray(case["force_history"], dtype=float)
    return lambda: response.peak_response(force, **case["kwargs"])


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


def _version(module_name):
    try:
        return __import__(module_name).__version__
    except ImportError:
        return "absent"


def environment():
    return {
        "git_sha": git("rev-parse", "HEAD"),
        "git_short_sha": git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain", "--", "src", "tests", "tools")),
        "date": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "numba": _version("numba"),
        "llvmlite": _version("llvmlite"),
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


def run_cases(cases, mode, repeats, profile, first_call):
    """Time every case; ``first_call`` (mode numba) times one untimed-repeat call first."""
    out = []
    for case in cases:
        row = {"id": case["id"], "mode": mode, "description": case["description"]}
        if first_call:
            log(f"[{mode}] {case['id']}: first call ...")
            gc.collect()
            t0 = time.perf_counter()
            case["run"]()
            row["first_call_s"] = round(time.perf_counter() - t0, 6)
        log(f"[{mode}] {case['id']}: timing x{repeats} ...")
        times, result = time_case(case, repeats)
        median = statistics.median(times)
        row.update(
            {
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
        )
        if case["expected"] is not None:
            actual = np.asarray(result, dtype=float)
            expected = np.asarray(case["expected"])
            row["golden_max_rel_err"] = float(np.max(np.abs(actual - expected) / np.abs(expected)))
        if profile and case["profile_ok"]:
            log(f"[{mode}] {case['id']}: profiling ...")
            row["profile"] = profile_case(case)
        log(f"[{mode}] {case['id']}: median {median:.3f} s")
        out.append(row)
    return out


def select(cases, group, only, skip_full=False):
    out = [c for c in cases if c["group"] == group]
    if only:
        out = [c for c in out if c["id"] in only or c["id"] == REFERENCE_CASE]
    if skip_full:
        out = [c for c in out if not c["full"]]
    return out


# ------------------------------------------------------------------ workers


def worker_main(args):
    """Child process: ``--worker python|numba`` times the refactored cases, ``--worker
    rss`` runs one case once and reports its peak RSS. Prints one JSON object."""
    import numba

    jit_disabled = bool(numba.config.DISABLE_JIT)
    cases = build_cases()
    out = {"worker": args.worker, "numba_disable_jit": jit_disabled}
    if args.worker == "rss":
        case = next(c for c in cases if c["id"] == args.rss_case)
        log(f"[rss] {case['id']}: one run, outputType 1 on the full history ...")
        t0 = time.perf_counter()
        result = case["run"]()
        out["case"] = {
            "id": case["id"],
            "description": case["description"],
            "time_s": round(time.perf_counter() - t0, 6),
            "ru_maxrss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
            "result": case["digest"](result),
            "numba_disable_jit": jit_disabled,
        }
    else:
        if args.worker == "numba" and jit_disabled:
            raise SystemExit("worker numba started with the JIT disabled")
        if args.worker == "python" and not jit_disabled:
            raise SystemExit("worker python started with the JIT enabled")
        if args.worker == "numba":
            call = example_lumped_call()
            t0 = time.perf_counter()
            call()
            out["compile_s"] = round(time.perf_counter() - t0, 6)
            log(f"[numba] kernel compile (first call, fresh cache): {out['compile_s']:.3f} s")
        selected = select(
            cases,
            "refactored",
            args.only,
            skip_full=args.skip_full_python and args.worker == "python",
        )
        out["cases"] = run_cases(
            selected,
            args.worker,
            args.repeats,
            profile=args.profile and args.worker == "python",
            first_call=args.worker == "numba",
        )
    print(json.dumps(out))
    return 0


def spawn_worker(mode, args, env_update, rss_case=None):
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        mode,
        "--repeats",
        str(args.repeats),
    ]
    if args.profile:
        cmd.append("--profile")
    if args.skip_full_python:
        cmd.append("--skip-full-python")
    for cid in args.only or ():
        cmd += ["--only", cid]
    if rss_case:
        cmd += ["--rss-case", rss_case]
    env = dict(os.environ, SURGE_BENCH_WORKER="1")
    env.pop("NUMBA_DISABLE_JIT", None)
    env.update(env_update)
    proc = subprocess.run(cmd, cwd=REPO, env=env, stdout=subprocess.PIPE, text=True, check=True)
    return json.loads(proc.stdout.strip().splitlines()[-1])


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


def case_key(row):
    """(id, mode); pre-Stage-5 JSON rows have no mode and were all pure Python."""
    mode = row.get("mode") or ("python" if row["id"].startswith("response_") else "literal")
    return row["id"], mode


def fmt_time(seconds):
    return f"{seconds * 1e3:.2f} ms" if seconds < 0.1 else f"{seconds:.3f} s"


def print_table(run, prev):
    prev_cases = {case_key(c): c for c in prev["cases"]} if prev else {}
    header = (
        "mode",
        "case",
        "median",
        "x ref (a)",
        "first call",
        "per sub-step",
        "cells/s",
        "golden err",
        "vs prev",
        "result vs prev",
    )
    rows = []
    for c in run["cases"]:
        p = prev_cases.get(case_key(c))
        if p is None:
            speed, same = "-", "-"
        else:
            speed = f"{p['median_s'] / c['median_s']:.2f}x"
            same = "same" if p.get("result") == c["result"] else "DIFFERS"
        per = f"{c['s_per_substep'] * 1e6:.3f} us" if c["s_per_substep"] else "-"
        cells = f"{c['cell_updates_per_s'] / 1e6:.2f} M" if c.get("cell_updates_per_s") else "-"
        first = fmt_time(c["first_call_s"]) if "first_call_s" in c else "-"
        gerr = f"{c['golden_max_rel_err']:.1e}" if "golden_max_rel_err" in c else "-"
        rows.append(
            (
                c["mode"],
                c["id"],
                fmt_time(c["median_s"]),
                f"{c['ratio_to_reference']:.3f}",
                first,
                per,
                cells,
                gerr,
                speed,
                same,
            )
        )
    widths = [max(len(str(r[i])) for r in rows + [header]) for i in range(len(header))]
    print()
    print(" | ".join(h.ljust(w) for h, w in zip(header, widths, strict=True)))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(" | ".join(str(v).ljust(w) for v, w in zip(r, widths, strict=True)))
    if run.get("compile_s") is not None:
        print(
            f"\nnumba kernel compile (first call of the Example lumped case, fresh cache): {run['compile_s']:.3f} s"
        )
    for r in run.get("rss", []):
        print(f"peak RSS {r['id']}: {r['ru_maxrss_mb']:.1f} MB ({fmt_time(r['time_s'])})")
    if prev:
        print(f"\nprevious: {prev['git_short_sha']} ({prev['date']})")
    for c in run["cases"]:
        if "profile" in c:
            print(f"\n[{c['mode']}] {c['id']}: top {TOP_N} by cumulative time (cProfile, one run)")
            print(f"{'ncalls':>12} {'tottime':>10} {'cumtime':>10}  function")
            for f in c["profile"]["top"]:
                print(
                    f"{f['ncalls']:>12} {f['tottime_s']:>10.3f} {f['cumtime_s']:>10.3f}  {f['function']}"
                )


def check_digest_pairs(run) -> bool:
    """Print the paired-digest comparison per refactored mode; True when every pair present
    matches."""
    by_key = {case_key(c): c for c in run["cases"]}
    ok = True
    for mode in ("python", "numba"):
        for new_id, ref_id in DIGEST_PAIRS:
            new, ref = by_key.get((new_id, mode)), by_key.get((ref_id, "literal"))
            if new and ref:
                same = new["result"] == ref["result"]
                ok &= same
                print(f"digest [{mode}] {new_id} == {ref_id}: {'yes' if same else 'NO'}")
    return ok


STAGE5_HEADING = "## Stage 5 runs (literal -> refactored -> Numba)\n"
STAGE5_INTRO = (
    "One section per `tools/bench.py` run since Stage 5. Rows: the literal port (pure Python), "
    "the Stage 4 modules as plain Python (`NUMBA_DISABLE_JIT=1`) and the same modules compiled by "
    "Numba (steady state; the first call and the compile are given separately). Every cell is the "
    "median of the timed repeats in seconds and, in brackets, the ratio to case (a), the literal "
    "lumped r20 case run in the same session. Details in `<sha>.json`.\n"
)


def fmt_cell(c):
    return f"{fmt_time(c['median_s'])} [{c['ratio_to_reference']:.3f}]" if c else "-"


def readme_section(run):
    by_key = {case_key(c): c for c in run["cases"]}
    sha = run["git_short_sha"] + ("-dirty" if run["git_dirty"] else "")
    lines = [
        f"### {run['date']} · {sha} · {run['cpu']} · python {run['python']} · numpy {run['numpy']} "
        f"· numba {run['numba']} · llvmlite {run['llvmlite']}\n",
        "\n",
        "| implementation | " + " | ".join(h for h, _, _ in COLUMNS) + " |\n",
        "|---|" + "---|" * len(COLUMNS) + "\n",
    ]
    for mode in MODES:
        cells = []
        for _h, lit_id, ref_id in COLUMNS:
            cid = lit_id if mode == "literal" else ref_id
            cells.append(fmt_cell(by_key.get((cid, mode)) if cid else None))
        lines.append(f"| {MODE_LABELS[mode]} | " + " | ".join(cells) + " |\n")
    notes = []
    if run.get("compile_s") is not None:
        firsts = ", ".join(
            f"{c['id']} {fmt_time(c['first_call_s'])}"
            for c in run["cases"]
            if c["mode"] == "numba" and "first_call_s" in c
        )
        notes.append(
            f"Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): "
            f"{fmt_time(run['compile_s'])}; first call per case: {firsts}."
        )
    cells_s = [
        f"{c['id']} [{c['mode']}] {c['cell_updates_per_s'] / 1e6:.2f} M"
        for c in run["cases"]
        if c.get("cell_updates_per_s")
    ]
    if cells_s:
        notes.append("MoC cell-updates/s: " + ", ".join(cells_s) + ".")
    golden = [
        f"{c['id']} [{c['mode']}] {c['golden_max_rel_err']:.1e}"
        for c in run["cases"]
        if c.get("golden_max_rel_err") is not None and c["mode"] != "literal" and "full" in c["id"]
    ]
    if golden:
        notes.append("Full JC cases vs Excel, max rel err: " + ", ".join(golden) + ".")
    if run.get("rss"):
        notes.append(
            "Peak RSS, `outputType = 1` on the full history under Numba: "
            + ", ".join(f"{r['id']} {r['ru_maxrss_mb']:.0f} MB" for r in run["rss"])
            + "."
        )
    notes.append(
        "Digest pairs (refactored == literal): "
        + ("all equal" if run["digest_pairs_ok"] else "**MISMATCH**")
        + f"; profile {'yes' if run['profile'] else 'no'}."
    )
    lines.append("\n" + "\n".join(notes) + "\n\n")
    return "".join(lines)


def append_readme(run):
    """Append this run's section under the Stage 5 heading (created at the end of the file
    on the first Stage 5 run); the pre-Stage-5 tables above it are untouched."""
    section = readme_section(run)
    text = README.read_text() if README.exists() else "# Benchmark history\n\n"
    if STAGE5_HEADING not in text:
        text = text.rstrip("\n") + "\n\n" + STAGE5_HEADING + "\n" + STAGE5_INTRO + "\n"
    README.write_text(text.rstrip("\n") + "\n\n" + section)


# ------------------------------------------------------------------ main


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--profile",
        action="store_true",
        help="also run each pure-Python case once under cProfile (literal and python modes)",
    )
    ap.add_argument("--repeats", type=int, default=3, help="timed runs per case (default 3)")
    ap.add_argument(
        "--only", action="append", help="run only this case id (repeatable); no files written"
    )
    ap.add_argument(
        "--skip-full-python",
        action="store_true",
        help="leave the three full JC cases out of the NUMBA_DISABLE_JIT=1 mode (~15 min each)",
    )
    ap.add_argument("--worker", choices=("python", "numba", "rss"), help=argparse.SUPPRESS)
    ap.add_argument("--rss-case", help=argparse.SUPPRESS)
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.worker:
        return worker_main(args)

    env = environment()
    if env["numba"] == "absent":
        raise SystemExit("numba is required (pip install -e '.[dev]')")
    cases = build_cases()
    run = dict(env, repeats=args.repeats, profile=args.profile, cases=[], rss=[])

    literal = select(cases, "literal", args.only)
    run["cases"] += run_cases(literal, "literal", args.repeats, args.profile, first_call=False)

    with tempfile.TemporaryDirectory(prefix="surge_numba_cache_") as cache_dir:
        numba_out = spawn_worker("numba", args, {"NUMBA_CACHE_DIR": cache_dir})
    run["compile_s"] = numba_out.get("compile_s")
    run["cases"] += numba_out["cases"]
    python_out = spawn_worker("python", args, {"NUMBA_DISABLE_JIT": "1"})
    run["cases"] += python_out["cases"]
    if not args.only:
        for cid in RSS_CASES:
            run["rss"].append(spawn_worker("rss", args, {}, rss_case=cid)["case"])

    ref = next(c["median_s"] for c in run["cases"] if c["id"] == REFERENCE_CASE)
    for row in run["cases"]:
        row["ratio_to_reference"] = round(row["median_s"] / ref, 4)
    # literal first, then python, then numba, each in case order
    order = {m: i for i, m in enumerate(MODES)}
    run["cases"].sort(key=lambda c: order[c["mode"]])

    prev = previous_run(env["git_short_sha"])
    print_table(run, prev)
    run["digest_pairs_ok"] = check_digest_pairs(run)
    if args.only:
        return 0 if run["digest_pairs_ok"] else 1

    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    out = BENCH_DIR / f"{env['git_short_sha']}.json"
    with open(out, "w") as fh:
        json.dump(run, fh, indent=1)
        fh.write("\n")
    append_readme(run)
    print(f"\nwrote {out.relative_to(REPO)} and appended {README.relative_to(REPO)}")
    return 0 if run["digest_pairs_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
