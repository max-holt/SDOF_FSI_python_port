"""Interleaved A/B timing of two commits on one host: the speed gate of the review.

The charter judges speed by an A/B run of the old code against the new on the same host
in the same session (rulings 43, 50, 54): a 5 % limit on the compiled paths. Raw times
from different sessions, and the ``tools/bench.py`` row of a host that drifts, decide
nothing.

Usage, from the repository root::

    .venv/bin/python tools/review_ab.py OLD NEW            # 5 rounds, min of 3 runs
    .venv/bin/python tools/review_ab.py HEAD~1 HEAD --rounds 9
    .venv/bin/python tools/review_ab.py OLD NEW --only lumped_r20 --only jc_r96_full
    .venv/bin/python tools/review_ab.py HEAD HEAD          # A/A: the harness's own spread

``OLD`` and ``NEW`` are any git revisions. Each is checked out into a temporary worktree;
every round runs both in fresh child processes (compiled, each with its own
``NUMBA_CACHE_DIR``), alternating which goes first, and each case is timed as the minimum
of ``--repeats`` runs after one warm-up call. The table gives, per case, the minimum over
the rounds and the ratio new / old. Read it against an A/A run on the same host: in
session R.6 the A/A spread was about +-5 % on the short cases and +-2 % on the full JC
cases; a ratio beyond the limit that does not repeat in a second run is noise.

Cases (inputs from the golden fixtures, ``tests/test_golden.py``): lumped rows 20 and 80;
JC row 96 on the first 2000 samples with the legacy flags, the default flags and traced
(stride 25); lumped row 20 traced; the full JC rows 96 and 97 (legacy flags); and two cases
that spend about half the run in free decay (a 200-sample ramp to about 1 m, light
damping, no friction; 20 calls per timing), which no golden case reaches. ``sweep_noise``
is one Tier 1 sweep case through ``sweep_rows.run_case`` (the first ``step_noise`` case, 10 in,
3 m: history generation, both solvers and the row), so a change on the sweep path is timed
too (owner's ruling, session R.9). It picks the case and builds the provenance by position, so
it runs against both sides of an A/B across a rename of their fields.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LEGACY_FLAGS = {"vav_denominator": "legacy", "parity": "per_phase", "fraction_profile": "legacy"}
TRACE_STRIDE = 25
DECAY_CALLS = 20


def _cases():
    """The timed cases of the worker, by name (imports from the worktree on ``sys.path``)."""
    import fixture_cases  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    import sweep_grid  # noqa: PLC0415
    import sweep_rows  # noqa: PLC0415
    import test_golden as tg  # noqa: PLC0415

    from surge_sdof import response  # noqa: PLC0415

    params = tg.load_params()
    force = tg.load_force(params)
    by_row = {c["source_row"]: c for c in tg.load_cases()}
    ramp = np.linspace(0, 1e7, 200)

    # the worktree's own call form: the grouped inputs where its fixture_cases translates the
    # fixture keywords (from session R.9), the keywords themselves before
    translate = getattr(fixture_cases, "solver_inputs", lambda kw: kw)

    def kw(row, **extra):
        return translate(dict(tg.case_params(by_row[row], params), **extra))

    lumped, jc = response.peak_response, response.peak_response_jc
    decay = {"damping_percent": 0.5, "dynamic_fric": 0.0}
    # by position: (size, length, natural frequency, history type, ...) and (tier, subset,
    # cpu, sha), so that the field names may differ between the two sides
    sweep_case = next(c for c in sweep_grid.tier_cases(1) if c[3] == "step_noise")
    provenance = sweep_rows.RunProvenance(1, "", "ab", "ab")
    return {
        "lumped_r20": lambda: lumped(force, **kw("20")),
        "lumped_r80": lambda: lumped(force, **kw("80")),
        "jc_r96_n2000_legacy": lambda: jc(force[:2000], **kw("96", **LEGACY_FLAGS)),
        "jc_r96_n2000_default": lambda: jc(force[:2000], **kw("96")),
        "jc_r96_n2000_traced": lambda: jc(force[:2000], **kw("96", trace_every=TRACE_STRIDE)),
        "lumped_r20_traced": lambda: lumped(force, **kw("20", trace_every=TRACE_STRIDE)),
        "jc_r96_full": lambda: jc(force, **kw("96", **LEGACY_FLAGS)),
        "jc_r97_full": lambda: jc(force, **kw("97", **LEGACY_FLAGS)),
        "lumped_r20_decay_x20": lambda: [
            lumped(ramp, **kw("20", **decay)) for _ in range(DECAY_CALLS)
        ],
        "jc_r96_decay_x20": lambda: [jc(ramp, **kw("96", **decay)) for _ in range(DECAY_CALLS)],
        "sweep_noise": lambda: sweep_rows.run_case(sweep_case, provenance),
    }


def worker(worktree: str, repeats: int, only: list[str]) -> None:
    """Time the cases of the code in ``worktree``; print ``{case: seconds}`` as JSON."""
    # tools/ for the fixture loaders that tests/test_golden.py imports (from session R.8)
    sys.path[:0] = [os.path.join(worktree, d) for d in ("src", "tests", "tools")]
    timings = {}
    for name, run in _cases().items():
        if only and name not in only:
            continue
        run()  # compile or cache load
        best = float("inf")
        for _ in range(repeats):
            start = time.perf_counter()
            run()
            best = min(best, time.perf_counter() - start)
        timings[name] = best
    print(json.dumps(timings))


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()


def _run_worker(worktree: Path, cache: Path, args) -> dict:
    env = dict(os.environ, NUMBA_CACHE_DIR=str(cache))
    env.pop("NUMBA_DISABLE_JIT", None)
    command = [sys.executable, __file__, "--worker", str(worktree), "--repeats", str(args.repeats)]
    for name in args.only:
        command += ["--only", name]
    result = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("old", nargs="?", help="git revision of the old code (A)")
    parser.add_argument("new", nargs="?", help="git revision of the new code (B)")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--only", action="append", default=[], help="case name (repeatable)")
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.repeats, args.only)
        return 0
    if not (args.old and args.new):
        parser.error("OLD and NEW are required")
    shas = {
        "A": _git("rev-parse", "--short", args.old),
        "B": _git("rev-parse", "--short", args.new),
    }
    with tempfile.TemporaryDirectory(prefix="review_ab_") as tmp:
        trees = {}
        for side, sha in shas.items():
            trees[side] = Path(tmp) / f"wt_{side}"
            _git("worktree", "add", "-q", "--detach", str(trees[side]), sha)
        timings = {"A": [], "B": []}
        try:
            for round_index in range(args.rounds):
                order = ("A", "B") if round_index % 2 == 0 else ("B", "A")
                for side in order:
                    cache = Path(tmp) / f"cache_{side}"
                    timings[side].append(_run_worker(trees[side], cache, args))
                print(f"round {round_index + 1} of {args.rounds} done", file=sys.stderr)
        finally:
            for tree in trees.values():
                _git("worktree", "remove", "--force", str(tree))
    print(f"A = {shas['A']} ({args.old}), B = {shas['B']} ({args.new})")
    print(f"{args.rounds} rounds, min of {args.repeats} runs per case per round")
    print(f"{'case':24s} {'A min s':>9s} {'B min s':>9s} {'B/A':>7s}")
    for name in timings["A"][0]:
        old = min(t[name] for t in timings["A"])
        new = min(t[name] for t in timings["B"])
        print(f"{name:24s} {old:9.4f} {new:9.4f} {new / old:7.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
