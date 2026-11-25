"""Case loading for ``tools/export.py`` (Session W.1; once shared with the retired ``tools/animate.py``).

A case is ``(force_history, kwargs, solver)``: a fixture case rerun from ``tests/fixtures``
(``golden_case``: a ``curve_10in`` id such as ``r096_jc_L24_f3`` or an Example-sheet id,
``example_lumped`` / ``example_jc``) or a plain built-in step (``step_case``: ``--amplitude``
bar on the fluid area of a pipe of ``--size`` mm internal diameter or ``--area`` m², zero for
``--lead-in`` then held for ``--duration``, the remaining inputs defaulting to the
``curve_10in`` parameters). ``add_source_arguments`` puts the ``--golden | --step`` group and
the step options on an argparse parser; ``case_from_args`` resolves them. The sweep's
canonical histories are ``surge_sdof.histories`` (Session 5b); the step here is the plain
one the committed ``example_jc_step.json`` was made with.

The content of the ``sweep`` document (its rows from a CSV, the regen templates, the
reference block) is ``tools/sweep_document.py``.
"""

from __future__ import annotations

import argparse
import math
from typing import NamedTuple

import fixture_cases as tg  # tools/fixture_cases.py: the fixture loaders
import numpy as np

from surge_sdof import loads, response

TRACE_FRAMES = 2000
"""Default target for the traced frames of the forced phases (``default_trace_every``)."""
JC_KEYS = ("fluid_densty", "fluid_area")
MM_PER_M = 1000.0
"""Millimetres per metre: the step case's internal diameter is given in mm."""
PA_PER_BAR = 1e5
"""Pascals per bar: the step case's amplitude is given in bar."""


def golden_case(case_id: str) -> tuple[np.ndarray, dict, str]:
    """A fixture case, rerun from ``tests/fixtures``.

    Parameters
    ----------
    case_id : str
        A ``curve_10in`` id such as ``r096_jc_L24_f3`` or an Example-sheet id.

    Returns
    -------
    tuple
        ``(force_history, kwargs, solver_name)``: the force history (N, float64), the
        fixture keyword arguments (``fixture_cases.case_params``) and ``"lumped"`` or
        ``"jc"``.

    Raises
    ------
    SystemExit
        An unknown id.
    """
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


class StepSpec(NamedTuple):
    """A plain built-in step case: the ``--step`` options (``add_source_arguments``), under
    their argparse names. Units: bar, mm, m², s, m, Hz, kg/m³, kg/m, N·m², m/s, percent."""

    amplitude_bar: float
    internal_diameter_mm: float
    area: float | None  # fluid area, m²; overrides internal_diameter_mm when set
    lead_in_s: float
    duration_s: float
    length: float
    nat_freq: float
    mu: float
    solver: str
    sample_freq: float
    step_qty: int
    celerity: float
    mass_per_len: float
    ei: float
    fluid_density: float
    damping: float


def step_spec(args: argparse.Namespace) -> StepSpec:
    """The ``StepSpec`` of the parsed ``add_source_arguments`` options (an
    ``argparse.Namespace``)."""
    return StepSpec(**{name: getattr(args, name) for name in StepSpec._fields})


def step_case(spec: StepSpec) -> tuple[np.ndarray, dict, str]:
    """A plain step case: zero force for ``lead_in_s`` (at least one sample), then
    ``amplitude_bar`` times the flow area for ``duration_s``.

    Parameters
    ----------
    spec : StepSpec
        The step options.

    Returns
    -------
    tuple
        ``(force_history, kwargs, solver_name)`` as ``golden_case``: the force (N,
        float64, shape ``(samples, 1)``), the fixture keyword arguments with the
        ``curve_10in`` restraint, and the spec's solver.
    """
    params = tg.load_params()
    flow_area = (
        spec.area if spec.area else math.pi * (spec.internal_diameter_mm / MM_PER_M) ** 2 / 4.0
    )
    lead_in_sample_count = max(1, int(round(spec.lead_in_s * spec.sample_freq)))
    hold_sample_count = max(1, int(round(spec.duration_s * spec.sample_freq)))
    force = np.full(
        (lead_in_sample_count + hold_sample_count, 1), spec.amplitude_bar * PA_PER_BAR * flow_area
    )
    force[:lead_in_sample_count, 0] = 0.0
    kw = {
        "step_qty": spec.step_qty,
        "sample_freq": spec.sample_freq,
        "physical_length": spec.length,
        "flexural_rigidity_ei": spec.ei,
        "celerity": spec.celerity,
        "mass_per_unit_len": spec.mass_per_len,
        "damping_percent": spec.damping,
        "dynamic_fric": spec.mu,
        "nat_freq": spec.nat_freq,
        "restrain_freq_ratio": params["restrain_freq_ratio"],
        "gap": params["gap"],
        "fluid_densty": spec.fluid_density,
        "fluid_area": flow_area,
    }
    return force, kw, spec.solver


def step_name(spec: StepSpec) -> str:
    """A one-line description of a step case (amplitude, pipe, span, frequency, friction,
    solver), the default case name."""
    return (
        f"step {spec.amplitude_bar:g} bar at t = {spec.lead_in_s:g} s, "
        + (f"area {spec.area:g} m², " if spec.area else f"{spec.internal_diameter_mm:g} mm, ")
        + f"L = {spec.length:g} m, "
        f"{spec.nat_freq:g} Hz, mu = {spec.mu:g} ({spec.solver})"
    )


def forced_substep_count(force: np.ndarray, kw: dict) -> int:
    """Substeps of the forced phases (transit and forced), as the trace capacity counts
    them.

    Parameters
    ----------
    force : array_like
        The force history, N.
    kw : dict
        Fixture keyword arguments (``physical_length`` m, ``celerity`` m/s,
        ``sample_freq`` Hz, ``step_qty``).

    Returns
    -------
    int
    """
    transit_delay_samples = loads.transit_delay(
        kw["physical_length"], kw["celerity"], kw["sample_freq"]
    )
    return int(np.size(force)) * kw["step_qty"] + int(transit_delay_samples * kw["step_qty"]) + 1


def default_trace_every(force: np.ndarray, kw: dict, target_frames: int) -> int:
    """The trace stride, in substeps, that records about ``target_frames`` frames of the
    forced phases (``force`` and ``kw`` as ``forced_substep_count``); at least 1."""
    return max(1, math.ceil(forced_substep_count(force, kw) / target_frames))


def run(force: np.ndarray, kw: dict, solver: str, trace_every: int) -> response.PeakResponse:
    """Run a case through its solver with a trace.

    Parameters
    ----------
    force : array_like
        The force history, N.
    kw : dict
        Fixture keyword arguments; the fluid ones are dropped for the lumped solver.
    solver : {"lumped", "jc"}
        The solver.
    trace_every : int
        Trace stride, substeps.

    Returns
    -------
    response.PeakResponse
    """
    if solver == "jc":
        return response.peak_response_jc(force, **tg.solver_inputs(kw, trace_every=trace_every))
    kw = {k: v for k, v in kw.items() if k not in JC_KEYS}
    return response.peak_response(force, **tg.solver_inputs(kw, trace_every=trace_every))


def add_source_arguments(ap: argparse.ArgumentParser) -> None:
    """Add the case options to an argparse parser: ``--golden | --step``, the step options,
    ``--name`` and ``--trace-every``."""
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--golden", metavar="CASE_ID", help="fixture case id to rerun with a trace")
    src.add_argument("--step", action="store_true", help="a plain built-in step history")
    ap.add_argument(
        "--name", help="title / case id; defaults to the case id or the step description"
    )
    ap.add_argument(
        "--trace-every", type=int, help=f"solver stride; default: about {TRACE_FRAMES} frames"
    )
    ap.add_argument("--trace-frames", type=int, default=TRACE_FRAMES, help=argparse.SUPPRESS)
    ap.add_argument("--solver", choices=("lumped", "jc"), default="jc", help="--step only")
    ap.add_argument(
        "--amplitude", dest="amplitude_bar", type=float, default=5.0, help="--step: bar"
    )
    ap.add_argument(
        "--size",
        dest="internal_diameter_mm",
        type=float,
        default=254.0,
        help="--step: internal diameter, mm",
    )
    ap.add_argument("--area", type=float, help="--step: fluid area, m² (overrides --size)")
    ap.add_argument(
        "--lead-in",
        dest="lead_in_s",
        type=float,
        default=0.1,
        help="--step: zero force before the step, s",
    )
    ap.add_argument("--length", type=float, default=12.0, help="--step: span between elbows, m")
    ap.add_argument("--nat-freq", type=float, default=3.0, help="--step: Hz")
    ap.add_argument("--mu", type=float, default=0.005, help="--step: dynamicFric")
    ap.add_argument(
        "--duration", dest="duration_s", type=float, default=1.0, help="--step: history length, s"
    )
    curve = tg.load_params()
    ap.add_argument("--sample-freq", type=float, default=curve["sample_freq"])
    ap.add_argument("--step-qty", type=int, default=curve["step_qty"])
    ap.add_argument("--celerity", type=float, default=curve["celerity"])
    ap.add_argument("--mass-per-len", type=float, default=curve["mass_per_unit_len"])
    ap.add_argument("--ei", type=float, default=curve["flexural_rigidity_ei"])
    ap.add_argument("--density", dest="fluid_density", type=float, default=curve["fluid_densty"])
    ap.add_argument("--damping", type=float, default=curve["damping_percent"])


def case_from_args(args: argparse.Namespace) -> tuple[np.ndarray, dict, str, str]:
    """The case the parsed ``add_source_arguments`` options name.

    Returns
    -------
    tuple
        ``(force, kwargs, solver, name)``: as ``golden_case`` or ``step_case``, and the
        case name (``--name``, else the case id or ``step_name``).
    """
    if args.golden:
        force, kw, solver = golden_case(args.golden)
        return force, kw, solver, args.name or args.golden
    spec = step_spec(args)
    force, kw, solver = step_case(spec)
    return force, kw, solver, args.name or step_name(spec)
