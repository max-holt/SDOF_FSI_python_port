"""Animate a traced run: ``tools/animate.py --golden <case_id> | --step ... --out <file.html>``.

``--golden`` reruns a fixture case (``tests/fixtures``: a ``curve_10in`` case id such as
``r096_jc_L24_f3`` or an Example-sheet id, ``example_lumped`` / ``example_jc``) through the
Stage 4 solver with ``trace_every`` and animates it. ``--step`` builds a plain step force
history instead: ``--amplitude`` bar on the fluid area of a pipe of ``--size`` mm internal
diameter (or ``--area`` m² directly), zero for the ``--lead-in`` (0.1 s) then held for
``--duration`` s, with ``--length``, ``--nat-freq``, ``--mu`` (dynamicFric) and ``--solver
lumped | jc``; the remaining inputs default to the ``curve_10in`` parameters
(``--sample-freq``, ``--step-qty``, ``--celerity``, ``--mass-per-len``, ``--ei``,
``--density``, ``--damping`` override them). A proper history generator (``histories.py``)
arrives in Session 5b.

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
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))

import test_golden as tg  # noqa: E402  (tests/test_golden.py: fixture loaders)

from surge_sdof import loads, response  # noqa: E402
from surge_sdof.viz import animate  # noqa: E402

TRACE_FRAMES = 2000
JC_KEYS = ("fluid_densty", "fluid_area")


def golden_case(case_id: str):
    """``(force_history, kwargs, solver_name)`` of a fixture case."""
    params = tg.load_params()
    for case in tg.load_cases():
        if case["case_id"] == case_id:
            return tg.load_force(params), tg.case_params(case, params), case["solver"]
    for case in tg.load_example_cases():
        if case["case_id"] == case_id and case["solver"] in ("lumped", "jc"):
            return (
                np.asarray(case["force_history"], dtype=float),
                dict(case["kwargs"]),
                case["solver"],
            )
    raise SystemExit(f"unknown case id {case_id!r}")


def step_case(args):
    """A plain step: zero for ``lead_in`` s (at least one sample), then ``amplitude`` bar x
    fluid area for ``duration`` s."""
    params = tg.load_params()
    area = args.area if args.area else math.pi * (args.size / 1000.0) ** 2 / 4.0
    n_lead = max(1, int(round(args.lead_in * args.sample_freq)))
    n_hold = max(1, int(round(args.duration * args.sample_freq)))
    force = np.full((n_lead + n_hold, 1), args.amplitude * 1e5 * area)
    force[:n_lead, 0] = 0.0
    kw = {
        "step_qty": args.step_qty,
        "sample_freq": args.sample_freq,
        "physical_length": args.length,
        "flexural_rigidity_ei": args.ei,
        "celerity": args.celerity,
        "mass_per_unit_len": args.mass_per_len,
        "damping_percent": args.damping,
        "dynamic_fric": args.mu,
        "nat_freq": args.nat_freq,
        "restrain_freq_ratio": params["restrain_freq_ratio"],
        "gap": params["gap"],
        "fluid_densty": args.density,
        "fluid_area": area,
    }
    return force, kw, args.solver


def default_trace_every(force, kw, target_frames: int) -> int:
    """The stride that records about ``target_frames`` frames of the forced phases."""
    unb = loads.transit_delay(kw["physical_length"], kw["celerity"], kw["sample_freq"])
    substeps = int(np.size(force)) * kw["step_qty"] + int(unb * kw["step_qty"]) + 1
    return max(1, math.ceil(substeps / target_frames))


def run(force, kw, solver: str, trace_every: int):
    if solver == "jc":
        return response.peak_response_jc(force, **kw, trace_every=trace_every)
    kw = {k: v for k, v in kw.items() if k not in JC_KEYS}
    return response.peak_response(force, **kw, trace_every=trace_every)


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--golden", metavar="CASE_ID", help="fixture case id to rerun with a trace")
    src.add_argument("--step", action="store_true", help="a plain built-in step history")
    ap.add_argument("--out", required=True, type=Path, help="output HTML (docs/viz/<name>.html)")
    ap.add_argument("--name", help="title; defaults to the case id or 'step'")
    ap.add_argument(
        "--trace-every", type=int, help=f"solver stride; default: about {TRACE_FRAMES} frames"
    )
    ap.add_argument("--trace-frames", type=int, default=TRACE_FRAMES, help=argparse.SUPPRESS)
    ap.add_argument(
        "--max-frames", type=int, default=animate.MAX_FRAMES, help="animation frame cap (400)"
    )
    ap.add_argument("--nominal-size", type=float, help="circle diameter at rest, px (auto)")
    ap.add_argument("--t-start", type=float, default=0.0, help="drop frames before this time, s")
    ap.add_argument("--t-end", type=float, help="drop frames after this time, s (window)")
    ap.add_argument("--solver", choices=("lumped", "jc"), default="jc", help="--step only")
    ap.add_argument("--amplitude", type=float, default=5.0, help="--step: bar")
    ap.add_argument("--size", type=float, default=254.0, help="--step: internal diameter, mm")
    ap.add_argument("--area", type=float, help="--step: fluid area, m² (overrides --size)")
    ap.add_argument(
        "--lead-in", type=float, default=0.1, help="--step: zero force before the step, s"
    )
    ap.add_argument("--length", type=float, default=12.0, help="--step: span between elbows, m")
    ap.add_argument("--nat-freq", type=float, default=3.0, help="--step: Hz")
    ap.add_argument("--mu", type=float, default=0.005, help="--step: dynamicFric")
    ap.add_argument("--duration", type=float, default=1.0, help="--step: history length, s")
    curve = tg.load_params()
    ap.add_argument("--sample-freq", type=float, default=curve["sample_freq"])
    ap.add_argument("--step-qty", type=int, default=curve["step_qty"])
    ap.add_argument("--celerity", type=float, default=curve["celerity"])
    ap.add_argument("--mass-per-len", type=float, default=curve["mass_per_unit_len"])
    ap.add_argument("--ei", type=float, default=curve["flexural_rigidity_ei"])
    ap.add_argument("--density", type=float, default=curve["fluid_densty"])
    ap.add_argument("--damping", type=float, default=curve["damping_percent"])
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.golden:
        force, kw, solver = golden_case(args.golden)
        name = args.name or args.golden
    else:
        force, kw, solver = step_case(args)
        name = args.name or (
            f"step {args.amplitude:g} bar at t = {args.lead_in:g} s, "
            + (f"area {args.area:g} m², " if args.area else f"{args.size:g} mm, ")
            + f"L = {args.length:g} m, "
            f"{args.nat_freq:g} Hz, mu = {args.mu:g} ({solver})"
        )
    trace_every = args.trace_every or default_trace_every(force, kw, args.trace_frames)
    result = run(force, kw, solver, trace_every)
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
