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

``reference_block`` and ``golden_sweep_rows`` read the fixtures for the ``sweep`` document.
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path
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


def step_spec(args) -> StepSpec:
    """The ``StepSpec`` of the parsed ``add_source_arguments`` options."""
    return StepSpec(**{name: getattr(args, name) for name in StepSpec._fields})


def step_case(spec: StepSpec):
    """A plain step: zero for ``lead_in_s`` (at least one sample), then ``amplitude_bar`` x
    flow area for ``duration_s``."""
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
    return (
        f"step {spec.amplitude_bar:g} bar at t = {spec.lead_in_s:g} s, "
        + (f"area {spec.area:g} m², " if spec.area else f"{spec.internal_diameter_mm:g} mm, ")
        + f"L = {spec.length:g} m, "
        f"{spec.nat_freq:g} Hz, mu = {spec.mu:g} ({spec.solver})"
    )


def forced_substep_count(force, kw) -> int:
    """Sub-steps of the forced phases (transit + history), as the trace capacity counts them."""
    transit_delay_samples = loads.transit_delay(
        kw["physical_length"], kw["celerity"], kw["sample_freq"]
    )
    return int(np.size(force)) * kw["step_qty"] + int(transit_delay_samples * kw["step_qty"]) + 1


def default_trace_every(force, kw, target_frames: int) -> int:
    """The stride that records about ``target_frames`` frames of the forced phases."""
    return max(1, math.ceil(forced_substep_count(force, kw) / target_frames))


def run(force, kw, solver: str, trace_every: int):
    if solver == "jc":
        return response.peak_response_jc(force, **kw, trace_every=trace_every)
    kw = {k: v for k, v in kw.items() if k not in JC_KEYS}
    return response.peak_response(force, **kw, trace_every=trace_every)


def add_source_arguments(ap) -> None:
    """``--golden | --step`` and the step options, ``--name``, ``--trace-every``."""
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


def case_from_args(args):
    """``(force, kwargs, solver, name)`` of the parsed ``add_source_arguments`` options."""
    if args.golden:
        force, kw, solver = golden_case(args.golden)
        return force, kw, solver, args.name or args.golden
    spec = step_spec(args)
    force, kw, solver = step_case(spec)
    return force, kw, solver, args.name or step_name(spec)


# ------------------------------------------------------------------ sweep (fixtures)


def _nominal_size_in(set_name: str) -> float | None:
    m = re.fullmatch(r"curve_(\d+)in", set_name)
    return float(m.group(1)) if m else None


def golden_sweep_rows(cases=None, params=None, set_name: str = "curve_10in") -> list[dict]:
    """``sweep`` rows from the ``curve_10in`` case table: ``case_id``, ``size_in``,
    ``length_m``, ``nat_freq_hz``, ``history_type = "golden"``, ``mu``, ``rho_c`` and the
    ``f_eq_* / f_peak_*`` of the row's own solver; everything else null."""
    cases = tg.load_cases() if cases is None else cases
    params = tg.load_params() if params is None else params
    size_in = _nominal_size_in(set_name)
    rho_c = float(params["fluid_densty"]) * float(params["celerity"])
    rows = []
    for case in cases:
        solver = case["solver"]
        rows.append(
            {
                "case_id": case["case_id"],
                "size_in": size_in,
                "length_m": float(case["physical_length"]),
                "nat_freq_hz": float(case["nat_freq"]),
                "history_type": "golden",
                "mu": float(case["dynamic_fric"]),
                "rho_c": rho_c,
                f"f_eq_{solver}": float(case["max_static_equivalent_force"]),
                f"f_peak_{solver}": float(case["max_applied_force"]),
            }
        )
    return rows


def golden_regen() -> dict:
    return {
        "template": "python tools/export.py trace --golden {case_id} --out {case_id}.json",
        "columns_used": ["case_id"],
        "note": (
            "Every row of this file is a tests/fixtures/curve_10in case, reproduced by "
            "--golden with the file's default stride (--trace-every overrides). Session 5b "
            "rows get their own template once tools/export.py has the history options."
        ),
    }


def sweep_regen() -> dict:
    """``regen`` of a Session 5b CSV: the sweep command of the row's tier (one row is
    reproduced by ``tools/sweep_jc.py``'s ``run_case`` from its columns; a single-case trace
    command is a W.3 item)."""
    return {
        "template": "python tools/sweep_jc.py run --tier {tier}",
        "columns_used": ["tier"],
        "note": (
            "Reruns the whole tier the row belongs to (docs/sweep/tier<N>_<sha>.csv). One row is "
            "reproduced by tools/sweep_jc.run_case on the Case its parameter columns describe; "
            "its history is histories.from_params over the fifteen generator columns "
            "(sweep_jc.history_from_row). A single-case trace command is a W.3 item."
        ),
    }


def uniform_value(rows, column: str):
    """The one value ``column`` holds in every row (empty cells ignored), else None."""
    values = {r.get(column) for r in rows} - {None, ""}
    return values.pop() if len(values) == 1 else None


def reference_block() -> dict:
    """The three Example-sheet cases and the three JC golden rows with their Excel values."""
    params = tg.load_params()
    example = []
    for case in tg.load_example_cases():
        inputs = dict(case["kwargs"])
        if "valve_pattern" in case:
            inputs["valve_pattern"] = np.asarray(case["valve_pattern"], dtype=float)
        if "force_history" in case:
            inputs["force_history"] = np.asarray(case["force_history"], dtype=float).reshape(-1, 1)
        example.append(
            {
                "case_id": case["case_id"],
                "solver": case["solver"],
                "source": dict(case["source"]),
                "inputs": inputs,
                "output_names": list(case["output_names"]) if "output_names" in case else None,
                "excel_values": [float(v) for v in case["expected"]],
                "rtol": tg.EXAMPLE_RTOL,
            }
        )
    names = list(params["expected_outputs"])
    jc_rows = []
    for case in tg.load_cases():
        if case["solver"] != "jc":
            continue
        inputs = tg.case_params(case, params)
        inputs["force"] = dict(params["force"])  # the sheet history's spec, not its 25135 values
        jc_rows.append(
            {
                "case_id": case["case_id"],
                "solver": "jc",
                "source": {"sheet": params["case_sheet"], "source_row": int(case["source_row"])},
                "inputs": inputs,
                "output_names": names,
                "excel_values": [float(case[n]) for n in names],
                "rtol": tg.RTOL["jc"],
            }
        )
    return {"example_cases": example, "jc_golden_rows": jc_rows}


GOLDEN_CSV_HEADER = ("case_id", "source_row", "solver", "max_static_equivalent_force")


def sweep_rows_from_csv(path: str | Path) -> tuple[list[dict], str]:
    """Rows of a CSV: the ``curve_10in`` ``cases.csv`` layout is mapped by
    ``golden_sweep_rows``; a Session 5b CSV whose header is a subset of the sweep columns
    passes through (missing columns null). Returns ``(rows, layout)`` with layout
    ``"golden"`` or ``"sweep"``."""
    from surge_sdof.export import SWEEP_COLUMNS, read_csv

    header, rows = read_csv(path)
    if all(h in header for h in GOLDEN_CSV_HEADER):
        set_name = Path(path).resolve().parent.name
        return golden_sweep_rows(rows, tg.load_params(), set_name), "golden"
    unknown = [h for h in header if h not in SWEEP_COLUMNS]
    if unknown:
        raise SystemExit(f"{path}: not a sweep CSV, unknown columns {unknown}")
    return rows, "sweep"
