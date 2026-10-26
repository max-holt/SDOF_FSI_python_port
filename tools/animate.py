"""Animate a traced run: ``tools/animate.py --golden <case_id> | --step ... --out <file.html>``.

``--golden`` reruns a fixture case (``tests/fixtures``: a ``curve_10in`` case id such as
``r096_jc_L24_f3`` or an Example-sheet id, ``example_lumped`` / ``example_jc``) through the
Stage 4 solver with ``trace_every`` and animates it. ``--step`` builds a plain step force
history instead: ``--amplitude`` bar on the fluid area of a pipe of ``--size`` mm internal
diameter (or ``--area`` m² directly), zero for the ``--lead-in`` (0.1 s) then held for
``--duration`` s, with ``--length``, ``--nat-freq``, ``--mu`` (dynamicFric) and ``--solver
lumped | jc``; the remaining inputs default to the ``curve_10in`` parameters
(``--sample-freq``, ``--step-qty``, ``--celerity``, ``--mass-per-len``, ``--ei``,
``--density``, ``--damping`` override them); the case loading is ``tools/cases.py``, shared
with ``tools/export.py`` (Session W.1). A proper history generator (``histories.py``) arrives
in Session 5b.

``--trace-every`` defaults to the stride that gives about ``--trace-frames`` (2000) traced
frames, so Panel 2 keeps its resolution inside the trace memory guard; ``--max-frames``
(400) caps the animation frames; ``--t-start`` / ``--t-end`` animate a time window only (Panel 2
keeps the whole run with the window shaded), the way to see a long run at full resolution
around its peak. The page is written with plotly.js from the CDN.

Examples::

    .venv/bin/python tools/animate.py --golden example_jc --out docs/viz/example_jc_sheet.html
    .venv/bin/python tools/animate.py --golden r096_jc_L24_f3 --t-start 6 --t-end 7.5 \\
        --max-frames 160 --out docs/viz/golden_r096_jc.html
    .venv/bin/python tools/animate.py --step --amplitude 1600 --area 0.05 --length 6 \\
        --nat-freq 2 --mu 0.0001 --sample-freq 10 --step-qty 80 --celerity 1200 \\
        --mass-per-len 100 --ei 1e7 --duration 2.4 --solver jc --out docs/viz/example_jc_step.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cases  # noqa: E402  (tools/cases.py: --golden / --step case loading, shared with tools/export.py)

from surge_sdof.viz import animate  # noqa: E402


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    cases.add_source_arguments(ap)
    ap.add_argument("--out", required=True, type=Path, help="output HTML (docs/viz/<name>.html)")
    ap.add_argument(
        "--max-frames", type=int, default=animate.MAX_FRAMES, help="animation frame cap (400)"
    )
    ap.add_argument("--nominal-size", type=float, help="circle diameter at rest, px (auto)")
    ap.add_argument("--t-start", type=float, default=0.0, help="drop frames before this time, s")
    ap.add_argument("--t-end", type=float, help="drop frames after this time, s (window)")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    force, kw, solver, name = cases.case_from_args(args)
    trace_every = args.trace_every or cases.default_trace_every(force, kw, args.trace_frames)
    result = cases.run(force, kw, solver, trace_every)
    fig, info = animate.build_figure(
        result,
        case_name=name,
        max_frames=args.max_frames,
        nominal_size=args.nominal_size,
        t_start=args.t_start,
        t_end=args.t_end,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    animate.write_html(fig, args.out)
    layout = info.layout
    print(
        f"{name}: {info.solver}, trace_every {info.trace_every} ({result.trace.n_frames} traced "
        f"frames), frame stride {info.frame_stride}, {info.n_frames} frames; "
        f"exaggeration x{info.exaggeration:.4g} (peak |x| {abs(info.x_peak):.4g} m at "
        f"t = {info.t_peak:.4g} s); p_scale {info.p_scale:.4g} Pa, k_p {info.k_p:.4g}, "
        f"v_scale {info.v_scale:.4g} m/s; grid N = {layout.pipe_seg_qty}, pivot "
        f"{layout.pivot_seg_qty}, {layout.n_cells} cells, run {layout.run_length:.4g} m, "
        f"pipe heights {layout.leg_height:.4g} / {layout.leg_height_2:.4g} m (h = "
        f"{layout.portal_height:.4g} m), nominal circle {info.nominal_size:.3g} px"
        + ("; trace capped by the history window" if info.capped else "")
    )
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.2f} MB, plotly.js from the CDN)")


if __name__ == "__main__":
    main()
