"""Write the viewer's data files (Session W.1; the contract is ``docs/data_format.md``).

``trace``: rerun a fixture case (``--golden <case_id>``) or a built-in step (``--step ...``,
the options of ``tools/animate.py``) with a trace and write the ``trace`` document, the whole
run at the trace stride (the viewer windows; nothing is windowed here)::

    .venv/bin/python tools/export.py trace --golden example_lumped --out docs/viz/data/example_lumped_step.json
    .venv/bin/python tools/export.py trace --golden r096_jc_L24_f3 --out docs/viz/data/golden_r096_jc.json.gz
    .venv/bin/python tools/export.py trace --step --amplitude 1600 --area 0.05 --length 6 --nat-freq 2 \\
        --mu 0.0001 --sample-freq 10 --step-qty 80 --celerity 1200 --mass-per-len 100 --ei 1e7 \\
        --duration 2.4 --solver jc --out docs/viz/data/example_jc_step.json

``--trace-every`` defaults to the stride that records about 2000 frames of the forced phases
(as ``tools/animate.py``), or the coarser stride that keeps the estimated JSON under
``JSON_BUDGET_MB`` (row 96's 1333 cells at 2000 frames would be ~107 MB); the size written is
printed. A ``.gz`` suffix gzips the file.

``sweep``: convert a CSV to the ``sweep`` document without rerunning anything: the
``tests/fixtures/curve_10in/cases.csv`` layout is mapped to the sweep columns (one row per
golden case, the other solver's columns null), a Session 5b CSV with the fixed header passes
through. The reference block (the three Example-sheet cases and the three JC golden rows with
their Excel values) is always attached::

    .venv/bin/python tools/export.py sweep --from-csv tests/fixtures/curve_10in/cases.csv \\
        --out docs/viz/data/reference_sweep.json
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cases  # noqa: E402  (tools/cases.py)

from surge_sdof import export, moc, structure  # noqa: E402

JSON_BUDGET_MB = 45.0
"""The default stride keeps the estimated trace JSON under this many MB (``estimate_bytes``)."""
BYTES_PER_FLOAT = 20
"""A float via ``repr`` plus its comma, on average."""


def estimated_cells(kw: dict, solver: str) -> int:
    """``2N + 1`` cells a JC run will carry (0 for lumped or a short-pipe fallback)."""
    if solver != "jc":
        return 0
    dt = 1.0 / (kw["sample_freq"] * kw["step_qty"])
    h = structure.solve_portal_height(
        kw["physical_length"], kw["flexural_rigidity_ei"], kw["mass_per_unit_len"], kw["nat_freq"]
    )
    n_seg, pivot = moc.grid_size(kw["physical_length"], h, kw["celerity"], dt)
    return 0 if moc.is_short_pipe(n_seg, pivot) else 2 * n_seg + 1


def estimate_bytes(n_frames: int, n_cells: int, n_samples: int) -> int:
    """``docs/data_format.md`` "Size expectations": about 20 bytes a float."""
    return BYTES_PER_FLOAT * (n_frames * (len(export.FRAME_COLUMNS) + 2 * n_cells) + n_samples)


def export_trace_every(force, kw, solver: str, target_frames: int, budget_mb: float) -> int:
    """The ``tools/animate.py`` default (about ``target_frames`` frames of the forced phases),
    or the coarser stride whose estimated JSON fits ``budget_mb`` (forced phases only; free
    decay adds frames)."""
    stride = cases.default_trace_every(force, kw, target_frames)
    substeps = cases.forced_substeps(force, kw)
    n_cells = estimated_cells(kw, solver)
    n_samples = int(force.size)
    per_frame = BYTES_PER_FLOAT * (len(export.FRAME_COLUMNS) + 2 * n_cells)
    frames_allowed = (budget_mb * 1e6 - BYTES_PER_FLOAT * n_samples) / per_frame
    if frames_allowed < 1:
        raise SystemExit(f"the budget {budget_mb} MB cannot hold even one frame of {n_cells} cells")
    return max(stride, math.ceil(substeps / frames_allowed))


def main_trace(args) -> None:
    force, kw, solver, name = cases.case_from_args(args)
    trace_every = args.trace_every or export_trace_every(
        force, kw, solver, args.trace_frames, args.budget_mb
    )
    result = cases.run(force, kw, solver, trace_every)
    doc = export.to_trace_dict(result, name)
    n_bytes = export.write_json(args.out, doc)
    tr = result.trace
    meta = doc["meta"]
    print(
        f"{name}: {meta['solver']}, trace_every {trace_every} ({tr.n_frames} traced frames + the "
        f"rest frame), dt = {tr.dt:.4g} s ({trace_every * tr.dt * 1e3:.3g} ms a frame), "
        f"{meta['n_cells']} cells, t = 0 .. {tr.t[-1]:.4g} s"
        + ("; trace capped by the history window" if meta["params"]["capped"] else "")
    )
    on_disk = Path(args.out).stat().st_size
    print(
        f"wrote {args.out}: {n_bytes / 1e6:.2f} MB of JSON"
        + (f", {on_disk / 1e6:.2f} MB gzipped" if on_disk != n_bytes else "")
    )


def main_sweep(args) -> None:
    rows, layout = cases.sweep_rows_from_csv(args.from_csv)
    doc = export.to_sweep_dict(
        rows,
        source=str(args.from_csv),
        tier=args.tier,
        cpu=args.cpu,
        histories_version=args.histories_version,
        regen=cases.golden_regen() if layout == "golden" else None,
        reference=cases.reference_block(),
    )
    n_bytes = export.write_json(args.out, doc)
    print(
        f"{args.from_csv} ({layout} layout): {len(rows)} rows, "
        f"{len(doc['reference']['example_cases'])} + {len(doc['reference']['jc_golden_rows'])} "
        f"reference cases; wrote {args.out} ({n_bytes / 1e6:.2f} MB)"
    )


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    tr = sub.add_parser("trace", help="rerun a case with a trace and write the trace document")
    cases.add_source_arguments(tr)
    tr.add_argument("--out", required=True, type=Path, help="output file.json or file.json.gz")
    tr.add_argument(
        "--budget-mb",
        type=float,
        default=JSON_BUDGET_MB,
        help=f"default-stride JSON budget, MB ({JSON_BUDGET_MB:g})",
    )
    sw = sub.add_parser("sweep", help="convert a sweep CSV to the sweep document")
    sw.add_argument("--from-csv", required=True, type=Path, help="cases.csv or a 5b sweep CSV")
    sw.add_argument("--out", required=True, type=Path, help="output file.json")
    sw.add_argument("--tier", help="sweep tier name (meta.tier)")
    sw.add_argument("--cpu", help="CPU the rows were timed on (meta.cpu)")
    sw.add_argument("--histories-version", help="histories.py version (meta.histories_version)")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.command == "trace":
        main_trace(args)
    else:
        main_sweep(args)


if __name__ == "__main__":
    main()
