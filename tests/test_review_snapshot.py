"""Review snapshot oracle: today's solver outputs, stored bit for bit.

The clean-code review (``docs/review/charter.md``) refactors the solver modules and every
refactoring must leave the results bit-identical. The differential suite compares at rtol
1e-12 and only the legacy-flag path has a reference (``legacy_port``); this test closes
both gaps. A seeded set of cases is run through the two public solvers and every output
is compared, as ``float.hex()`` text, with the files under ``tests/review_snapshot/``,
which were written by ``tools/review_snapshot.py --write`` from the code as it stood before
the review. Equality is exact: text equality of hex floats is bit equality (the sign of
zero included; a NaN payload is the one thing ``float.hex`` does not carry).

Covered: ``peak_response`` and ``peak_response_jc`` with the default flags (F-1, F-2,
F-4b) and with the legacy flags, ``output_type`` 0 to 3 on every case, one traced run of
each solver (every ``Trace`` field except the ``inputs`` echo) and a short-pipe fallback
case; besides the hand-set cases, a seeded sweep of short runs per
solver varies every set-up argument and pins the resolved set-up itself (the trace's
``SdofParams``, ``dt``, grid and fractions, and the transit delay, portal-frame height and
decay factor through the adapter), and one case sits in the friction dead zone (D-20).
The case inputs are fixed numbers and ``random.Random`` draws;
none depends on a solver result, so a case cannot drift with the code under test.

Every solver call goes through ``run_solver``, the one adapter: a later rename of a
function, a keyword, a result attribute or a ``Trace`` field is absorbed there (the
snapshot keys are this file's own and never change).

The files are regenerated only for an approved behaviour change (a DEVIATIONS.md row),
never to make a refactoring pass.
"""

from __future__ import annotations

import functools
import math
import random
from pathlib import Path
from typing import NamedTuple

import fixture_cases as fc
import numpy as np
import pytest

from surge_sdof import loads, moc, response, structure

SNAPSHOT_DIR = Path(__file__).parent / "review_snapshot"
SEED = 20261116

LEGACY_FLAGS = {"vav_denominator": "legacy", "parity": "per_phase", "fraction_profile": "legacy"}
OUTPUT_TYPES = (0, 1, 2, 3)

# ------------------------------------------------------------------ the adapter

# Snapshot key -> attribute of today's result objects. The keys are the snapshot's own
# vocabulary; after a rename in src/, change the attribute on the right, never the key.
_PEAK_FIELDS = {
    "max_static_equivalent_force": "max_static_equivalent_force",
    "max_displacement": "max_displacement",
    "max_velocity": "max_velocity",
    "max_acceleration": "max_acceleration",
    "max_applied_force": "max_unbalance_force",
    "free_decay_samples": "free_decay_sample_count",
}
"""``history``, the last peak key, is the history the case's ``output_type`` names
(``fixture_cases.history_of``): the result carries all three since session R.9."""
_TRACE_FIELDS = {
    "solver": "solver",
    "trace_every": "trace_every",
    "dt": "dt",
    "step_qty": "step_qty",
    "out_max": "out_max",
    "t": "t",
    "sub_step": "sub_step",
    "sample": "sample",
    "phase": "phase",
    "x": "x",
    "v": "v",
    "a": "a",
    "f_a": "f_a",
    "f_b": "f_b",
    "f_unbalance": "f_unbalance",
    "f_friction": "f_friction",
    "stick": "stick",
    "d_f": "d_f",
    "n_cells": "n_cells",
    "pivot_seg_qty": "pivot_seg_qty",
    "pipe_seg_qty": "pipe_seg_qty",
    "ext_qty": "ext_qty",
    "p_cells": "p_cells",
    "v_cells": "v_cells",
    "cell_position": "cell_position",
    "cell_kind": "cell_kind",
    "moving_fraction": "moving_fraction",
}
_PARAM_FIELDS = {
    "mass": "mass",
    "stiffness": "stiffness",
    "damping": "damping",
    "fric_acc": "friction_velocity_step",
    "gap": "support_gap",
    "ratio2": "closed_gap_stiffness_ratio",
}


def run_solver(solver: str, history, params: dict, options: dict) -> dict:
    """Run one solver on one case and return its outputs under the snapshot's own keys.

    With its helper ``_setup_values`` the only place in this file that touches
    ``surge_sdof``: ``solver`` is ``"peak_response"``, ``"peak_response_jc"`` or
    ``"setup"`` (the set-up scalars of a case), ``history`` the force history (N),
    ``params`` the case's physical arguments and
    ``options`` the run's switches (``output_type``, ``trace_every``, the JC flags), all
    under the fixtures' keyword names, which ``fixture_cases.solver_inputs`` translates.
    """
    if solver == "setup":
        return _setup_values(params)
    if solver == "peak_response":
        result = response.peak_response(history, **fc.solver_inputs(params, **options))
    elif solver == "peak_response_jc":
        result = response.peak_response_jc(history, **fc.solver_inputs(params, **options))
    else:
        raise ValueError(f"unknown solver {solver!r}")
    out = {key: getattr(result, attr) for key, attr in _PEAK_FIELDS.items()}
    out["history"] = fc.history_of(result, options.get("output_type", 0))
    if result.trace is not None:
        for key, attr in _TRACE_FIELDS.items():
            out[f"trace.{key}"] = getattr(result.trace, attr)
        for key, attr in _PARAM_FIELDS.items():
            out[f"trace.params.{key}"] = getattr(result.trace.params, attr)
    return out


def _setup_values(params: dict) -> dict:
    """The set-up scalars of a peak-response case that no output carries: a last-bit change
    in one of them is absorbed by the run unless it happens to cross a rounding threshold,
    so they are pinned directly. Part of the adapter: if a refactoring moves or inlines one
    of these functions, point the entry at wherever the value is now computed."""
    length, celerity = params["physical_length"], params["celerity"]
    sample_freq, step_qty = params["sample_freq"], params["step_qty"]
    transit_delay = loads.transit_delay(length, celerity, sample_freq)
    height = structure.solve_portal_height(
        length, params["flexural_rigidity_ei"], params["mass_per_unit_len"], params["nat_freq"]
    )
    dt = 1 / (sample_freq * step_qty)  # pinned itself by ``trace.dt`` of the traced runs
    pipe_cells, pivot_cells = moc.grid_size(length, height, celerity, dt)
    return {
        "transit_delay_samples": transit_delay,
        "overlap_sub_steps": loads.overlap_substeps(transit_delay, step_qty),
        "portal_frame_height": height,
        "pipe_cell_count": pipe_cells,
        "pivot_cell_count": pivot_cells,
        "end_node_decay_factor": moc.end_pressure_decay_factor(celerity, dt, length),
    }


# ------------------------------------------------------------------ the cases


class Run(NamedTuple):
    """One solver call of a snapshot document."""

    label: str
    solver: str
    history: np.ndarray
    params: dict
    options: dict


def _piecewise_levels(rng: random.Random, n: int, amplitude: float) -> list[float]:
    """Random piecewise-constant levels: sharp changes make ``F(t) - F(t - L/c)`` large."""
    out: list[float] = []
    while len(out) < n:
        level = rng.uniform(-amplitude, amplitude)
        out.extend([level] * rng.randint(1, max(2, n // 6)))
    return out[:n]


def _force_history(rng: random.Random, n: int, cols: int, amplitude: float) -> np.ndarray:
    n -= n % cols
    flat = np.array(_piecewise_levels(rng, n, amplitude))
    return flat if cols == 1 else flat.reshape(n // cols, cols, order="F")


def _lumped_case(rng: random.Random, step_qty: int, cols: int, dynamic_fric: float):
    """A seeded lumped case; ``F / k`` of 3 .. 12 model units (the unbalance acts
    only for a transit time, so the response is a small fraction of it) makes the free
    decay (``|x| > 0.1``, D-21) reachable; the gap is a fraction of the response."""
    sample_freq = rng.uniform(50.0, 300.0)
    nat_freq = rng.uniform(0.005, 0.03) * sample_freq * step_qty / (2 * math.pi)
    physical_length = rng.uniform(1.0, 30.0)
    mass_per_unit_len = rng.uniform(2.0, 50.0)
    stiffness_approx = (2 * math.pi * nat_freq) ** 2 * physical_length * mass_per_unit_len
    deflection = rng.uniform(3.0, 12.0)
    n = int(min(max(rng.uniform(1.0, 4.0) * sample_freq / nat_freq, 18), 90))
    history = _force_history(rng, n, cols, deflection * stiffness_approx)
    params = {
        "step_qty": step_qty,
        "sample_freq": sample_freq,
        "physical_length": physical_length,
        "flexural_rigidity_ei": rng.uniform(1e4, 1e6),
        "celerity": rng.uniform(300.0, 1500.0),
        "mass_per_unit_len": mass_per_unit_len,
        "damping_percent": rng.uniform(0.5, 5.0),
        "dynamic_fric": dynamic_fric,
        "nat_freq": nat_freq,
        "restrain_freq_ratio": rng.uniform(0.5, 4.0),
        "gap": rng.uniform(0.005, 0.03) * deflection,
    }
    return history, params


# (step_qty, history columns, friction coefficient) of the seeded lumped cases.
LUMPED_SHAPES = ((2, 1, 0.1), (7, 2, 0.005), (40, 3, 0.0), (7, 1, 0.1), (40, 2, 0.3), (2, 3, 0.005))

# Junction-coupling cases: the smoke-test pipe and variations (grids of 16 to 50 cells,
# pivots at 5 to 9 cells).
JC_BASE = {
    "step_qty": 10,
    "sample_freq": 100.0,
    "physical_length": 10.0,
    "flexural_rigidity_ei": 2e5,
    "celerity": 1000.0,
    "mass_per_unit_len": 10.0,
    "fluid_densty": 1000.0,
    "fluid_area": 0.005,
    "damping_percent": 2.0,
    "dynamic_fric": 0.3,
    "nat_freq": 5.0,
}
# id -> (overrides of JC_BASE, history samples, history columns, force amplitude in N)
JC_SHAPES = {
    "jc_a": ({}, 60, 1, 2.0e5),
    "jc_b": (
        {"physical_length": 12.5, "step_qty": 7, "dynamic_fric": 0.005, "gap": 0.05},
        60,
        2,
        1.5e5,
    ),
    "jc_c": (
        {
            "physical_length": 14.0,
            "step_qty": 4,
            "sample_freq": 250.0,
            "flexural_rigidity_ei": 3e6,
            "fluid_area": 0.004,
            "dynamic_fric": 0.0,
            "restrain_freq_ratio": 2.5,
            "gap": 0.2,
        },
        90,
        3,
        6.0e5,
    ),
    "jc_d": (
        {
            "physical_length": 30.0,
            "step_qty": 20,
            "flexural_rigidity_ei": 5e6,
            "mass_per_unit_len": 25.0,
            "nat_freq": 3.0,
            "fluid_area": 0.012,
            "damping_percent": 4.0,
            "dynamic_fric": 0.1,
            "restrain_freq_ratio": 0.6,
            "gap": 0.1,
        },
        40,
        1,
        4.0e5,
    ),
    "jc_e": (
        {
            "physical_length": 20.0,
            "flexural_rigidity_ei": 4e7,
            "mass_per_unit_len": 60.0,
            "fluid_area": 0.02,
            "damping_percent": 1.0,
            "dynamic_fric": 0.05,
            "nat_freq": 2.0,
            "restrain_freq_ratio": 1.8,
            "gap": 0.15,
        },
        50,
        2,
        5.0e5,
    ),
}
# The span is shorter than the MoC grid needs: ``peak_response_jc`` returns ``peak_response``.
JC_SHORT_PIPE = ({"physical_length": 1.5, "gap": 0.05}, 60, 1, 3.0e5)

# The friction dead zone (D-20): with ``fric_acc`` below the VBA's ``sign`` tolerance of
# 1e-6 m/s, a sub-step whose velocity lies between the two slips without friction. A tiny
# friction coefficient and millinewton forces keep the velocity in that band.
DEAD_ZONE_PARAMS = {
    "step_qty": 10,
    "sample_freq": 100.0,
    "physical_length": 10.0,
    "flexural_rigidity_ei": 2e5,
    "celerity": 1000.0,
    "mass_per_unit_len": 10.0,
    "damping_percent": 2.0,
    "dynamic_fric": 1e-4,
    "nat_freq": 5.0,
}
DEAD_ZONE_AMPLITUDE = 0.1  # N
SIGN_TOLERANCE = 0.000001  # m/s, the VBA ``sign(v, 0.000001)`` of the slip branch

SWEEP_CASES = 30  # per sweep document: short runs that vary every set-up argument
SWEEP_STRIDE = 97  # sub-steps between the trace frames of a sweep run


def _log_uniform(rng: random.Random, low: float, high: float) -> float:
    return math.exp(rng.uniform(math.log(low), math.log(high)))


def _sweep_case(rng: random.Random, with_fluid: bool):
    """One short seeded case of the set-up sweeps: every physical argument drawn, so a
    rounding-level change in any set-up expression shows in some case."""
    step_qty = rng.choice([4, 7, 10, 16])
    sample_freq = rng.uniform(80.0, 250.0)
    physical_length = rng.uniform(8.0, 30.0)
    mass_per_unit_len = rng.uniform(10.0, 60.0)
    nat_freq = rng.uniform(2.0, 6.0)
    stiffness_approx = (2 * math.pi * nat_freq) ** 2 * physical_length * mass_per_unit_len
    deflection = rng.uniform(1.0, 6.0)
    params = {
        "step_qty": step_qty,
        "sample_freq": sample_freq,
        "physical_length": physical_length,
        "flexural_rigidity_ei": _log_uniform(rng, 2e5, 5e7),
        "celerity": rng.uniform(800.0, 1400.0),
        "mass_per_unit_len": mass_per_unit_len,
        "damping_percent": rng.uniform(0.5, 5.0),
        "dynamic_fric": rng.choice([0.0, 0.003, 0.02, 0.07, 0.13, 0.3]) * rng.uniform(0.5, 1.5),
        "nat_freq": nat_freq,
        "restrain_freq_ratio": rng.uniform(0.5, 4.0),
        "gap": rng.uniform(0.005, 0.05) * deflection,
    }
    if with_fluid:
        params["fluid_densty"] = rng.uniform(700.0, 1100.0)
        # the core fluid is at most 40 % of the mass per unit length: rigid mass > 0
        params["fluid_area"] = rng.uniform(0.05, 0.4) * mass_per_unit_len / params["fluid_densty"]
    history = _force_history(
        rng, rng.randint(18, 30), rng.choice([1, 2, 3]), deflection * stiffness_approx
    )
    return history, params


def _output_type_runs(solver: str, history, params: dict, flags: dict) -> list[Run]:
    return [
        Run(f"output_type={ot}", solver, history, params, dict(flags, output_type=ot))
        for ot in OUTPUT_TYPES
    ]


@functools.cache
def documents() -> dict[str, list[Run]]:
    """Every snapshot document: file stem -> the solver calls whose outputs it holds."""
    rng = random.Random(SEED)
    docs: dict[str, list[Run]] = {}

    lumped = []
    for i, shape in enumerate(LUMPED_SHAPES):
        history, params = _lumped_case(rng, *shape)
        lumped.append((history, params))
        docs[f"lumped_{i:02d}"] = _output_type_runs("peak_response", history, params, {})

    jc = {}
    for case_id, (overrides, n, cols, amplitude) in JC_SHAPES.items():
        history = _force_history(rng, n, cols, amplitude)
        params = dict(JC_BASE, **overrides)
        jc[case_id] = (history, params)
        docs[f"{case_id}_default"] = _output_type_runs("peak_response_jc", history, params, {})
        docs[f"{case_id}_legacy"] = _output_type_runs(
            "peak_response_jc", history, params, LEGACY_FLAGS
        )

    overrides, n, cols, amplitude = JC_SHORT_PIPE
    history = _force_history(rng, n, cols, amplitude)
    params = dict(JC_BASE, **overrides)
    docs["jc_short_pipe_default"] = _output_type_runs("peak_response_jc", history, params, {})
    docs["jc_short_pipe_legacy"] = _output_type_runs(
        "peak_response_jc", history, params, LEGACY_FLAGS
    )

    # One traced run of each solver, every sub-step for the lumped one; stride 3 on the
    # junction-coupling one keeps the file small and still lands on both MoC half-grids.
    history, params = lumped[3]
    docs["lumped_traced"] = [
        Run("traced", "peak_response", history, params, {"output_type": 1, "trace_every": 1})
    ]
    history, params = jc["jc_e"]
    docs["jc_traced_default"] = [
        Run("traced", "peak_response_jc", history, params, {"output_type": 2, "trace_every": 3})
    ]
    history, params = jc["jc_b"]
    docs["jc_traced_legacy"] = [
        Run(
            "traced",
            "peak_response_jc",
            history,
            params,
            dict(LEGACY_FLAGS, output_type=3, trace_every=3),
        )
    ]

    history = _force_history(rng, 40, 1, DEAD_ZONE_AMPLITUDE)
    docs["lumped_dead_zone"] = [
        Run(
            "traced",
            "peak_response",
            history,
            DEAD_ZONE_PARAMS,
            {"output_type": 2, "trace_every": 1},
        )
    ]

    # A history that starts at -0.0: the first unbalance value is ``-0.0 - 0.0 = -0.0`` and
    # the lumped path's ``0.0 + F`` turns it into ``+0.0`` (the sign of an exact zero).
    history = _force_history(rng, 20, 1, 2.0e4)
    history[0] = -0.0
    history[1] = 1.0e4
    docs["lumped_signed_zero"] = [
        Run(
            "traced",
            "peak_response",
            history,
            {k: v for k, v in JC_BASE.items() if not k.startswith("fluid_")},
            {"output_type": 3, "trace_every": 1},
        )
    ]

    # Set-up sweeps: many short runs, each sweep on its own generator so that adding a
    # case to one never moves the draws of another. The output type cycles 0 .. 3. The
    # stride of SWEEP_STRIDE sub-steps records a handful of frames and, with them, the
    # resolved set-up of the run (``trace.params``, ``dt``, the grid and the fractions).
    rng = random.Random(SEED + 1)
    lumped_sweep = [_sweep_case(rng, False) for _ in range(SWEEP_CASES)]
    docs["lumped_sweep"] = [
        Run(
            f"case {i:02d}",
            "peak_response",
            *case,
            {"output_type": i % 4, "trace_every": SWEEP_STRIDE},
        )
        for i, case in enumerate(lumped_sweep)
    ]
    rng = random.Random(SEED + 2)
    jc_sweep = [_sweep_case(rng, True) for _ in range(SWEEP_CASES)]
    for flag_set, flags in (("default", {}), ("legacy", LEGACY_FLAGS)):
        docs[f"jc_sweep_{flag_set}"] = [
            Run(
                f"case {i:02d}",
                "peak_response_jc",
                *case,
                dict(flags, output_type=i % 4, trace_every=SWEEP_STRIDE),
            )
            for i, case in enumerate(jc_sweep)
        ]
    docs["setup_sweep"] = [
        Run(f"{kind} case {i:02d}", "setup", *case, {})
        for kind, cases in (("lumped", lumped_sweep), ("jc", jc_sweep))
        for i, case in enumerate(cases)
    ]
    return docs


# ------------------------------------------------------------------ the text format


def _scalar(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, (bool, np.bool_)):
        return "1" if value else "0"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        return float(value).hex()
    if isinstance(value, str):
        return repr(value)
    raise TypeError(f"no snapshot form for {type(value).__name__}")


def _value_lines(key: str, value) -> list[str]:
    """``key = scalar``, or ``key : dtype shape`` followed by one line per 1-D element or
    per row of a 2-D array (floats as ``float.hex()``, ints as decimals, bools as 0 / 1)."""
    if not isinstance(value, np.ndarray):
        return [f"{key} = {_scalar(value)}"]
    lines = [f"{key} : {value.dtype} {value.shape}"]
    if value.ndim == 1:
        lines.extend(_scalar(element) for element in value)
    elif value.ndim == 2:
        lines.extend(" ".join(_scalar(element) for element in row) for row in value)
    else:
        raise TypeError(f"{key}: no snapshot form for ndim {value.ndim}")
    return lines


@functools.cache
def outputs(name: str) -> tuple[dict, ...]:
    """The adapter's outputs for each run of document ``name`` (computed once). A run that
    raises is part of the behaviour: its output is the exception's type name (the message
    is wording, not arithmetic, and is left free)."""
    out = []
    for run in documents()[name]:
        try:
            out.append(run_solver(run.solver, run.history, run.params, run.options))
        except (ArithmeticError, ValueError, IndexError, TypeError) as error:
            out.append({"raises": type(error).__name__})
    return tuple(out)


def render(name: str) -> str:
    """Document ``name`` as the text stored in ``tests/review_snapshot/<name>.txt``."""
    lines = []
    for run, out in zip(documents()[name], outputs(name), strict=True):
        lines.append(f"## {run.solver} {run.label}")
        for key, value in out.items():
            lines.extend(_value_lines(key, value))
    return "\n".join(lines) + "\n"


def _first_difference(expected: str, actual: str) -> str:
    """Where two documents first differ: the line, and the value header above it."""
    exp, act = expected.splitlines(), actual.splitlines()
    header = "(start of file)"
    for number, (e, a) in enumerate(zip(exp, act, strict=False), start=1):
        if " : " in e or " = " in e or e.startswith("## "):
            header = e
        if e != a:
            return f"line {number}, under {header!r}: snapshot {e[:120]!r}, now {a[:120]!r}"
    return f"length differs: snapshot {len(exp)} lines, now {len(act)} lines"


# ------------------------------------------------------------------ the tests


@pytest.mark.parametrize("name", list(documents()))
def test_outputs_equal_the_snapshot_bit_for_bit(name):
    path = SNAPSHOT_DIR / f"{name}.txt"
    assert path.is_file(), f"{path} is missing: tools/review_snapshot.py --write"
    expected = path.read_text(encoding="utf-8")
    actual = render(name)
    if actual != expected:
        pytest.fail(f"{name}: {_first_difference(expected, actual)}", pytrace=False)


def test_snapshot_directory_holds_exactly_the_documents():
    stored = sorted(p.stem for p in SNAPSHOT_DIR.glob("*.txt"))
    assert stored == sorted(documents())


def _first(name: str) -> dict:
    return outputs(name)[0]


def test_case_set_reaches_the_branches_a_refactoring_can_break():
    """The cases are only an oracle if they exercise the code: free decay, the support
    gap, stick and slip, both MoC half-grids, the flags and the fallback."""
    docs = documents()
    lumped = [n for n in docs if n.startswith("lumped_0")]
    jc_default = [f"{case_id}_default" for case_id in JC_SHAPES]

    # free decay entered, and the gap engaged, in most cases of each solver
    for names in (lumped, jc_default):
        assert sum(_first(n)["free_decay_samples"] > 0 for n in names) >= len(names) - 1
        engaged = [
            _first(n)["max_displacement"] > docs[n][0].params["gap"]
            for n in names
            if "gap" in docs[n][0].params
        ]
        assert sum(engaged) >= 3

    # the legacy flags change the result of every junction-coupling case
    for case_id in JC_SHAPES:
        assert render(f"{case_id}_default") != render(f"{case_id}_legacy")

    # the short pipe really takes the lumped fallback, whatever the flags
    assert render("jc_short_pipe_default") == render("jc_short_pipe_legacy")
    short = docs["jc_short_pipe_default"][0]
    lumped_params = {k: v for k, v in short.params.items() if not k.startswith("fluid_")}
    as_lumped = run_solver("peak_response", short.history, lumped_params, short.options)
    assert _value_lines("history", as_lumped["history"]) == _value_lines(
        "history", _first("jc_short_pipe_default")["history"]
    )

    # the traced runs see stick and slip, all three phases, and a moving column
    for name in ("lumped_traced", "jc_traced_default", "jc_traced_legacy"):
        traced = _first(name)
        assert set(traced["trace.stick"].tolist()) == {False, True}
        assert set(traced["trace.phase"].tolist()) == {0, 1, 2}
        assert np.any(traced["trace.f_friction"] != 0.0)
    for name in ("jc_traced_default", "jc_traced_legacy"):
        traced = _first(name)
        assert set((traced["trace.sub_step"] % 2).tolist()) == {0, 1}
        # every cell but the centre one (zero by the antisymmetry of the fixed profile)
        moving = np.any(traced["trace.p_cells"] != 0.0, axis=0)
        assert moving.sum() >= moving.size - 1
        assert np.any(traced["trace.d_f"] != 0.0)

    # the dead-zone case has sub-steps that slip without friction (D-20) and ones that stick
    dead = _first("lumped_dead_zone")
    fric_acc = dead["trace.params.fric_acc"]
    assert 0.0 < fric_acc < SIGN_TOLERANCE
    speed_before = np.abs(np.concatenate([[0.0], dead["trace.v"][:-1]]))
    assert np.sum((speed_before >= fric_acc) & (speed_before < SIGN_TOLERANCE)) >= 20
    assert np.sum(speed_before >= SIGN_TOLERANCE) >= 20
    assert dead["trace.stick"].sum() >= 20

    # the signed-zero case applies -0.0 on its first sub-step and the state stays +0.0
    zero = _first("lumped_signed_zero")
    assert zero["trace.f_unbalance"][0] == 0.0
    assert math.copysign(1.0, zero["trace.f_unbalance"][0]) == -1.0
    assert math.copysign(1.0, zero["trace.a"][0]) == 1.0

    # the sweeps run (no case raises), on real MoC grids, mostly into free decay
    for name in (
        "lumped_sweep",
        "jc_sweep_default",
        "jc_sweep_legacy",
        "setup_sweep",
    ):
        assert not any("raises" in out for out in outputs(name))
    for name in ("lumped_sweep", "jc_sweep_default", "jc_sweep_legacy"):
        assert sum(out["free_decay_samples"] > 0 for out in outputs(name)) >= SWEEP_CASES // 2
    differing = [
        _value_lines("x", a["max_displacement"]) != _value_lines("x", b["max_displacement"])
        for a, b in zip(outputs("jc_sweep_default"), outputs("jc_sweep_legacy"), strict=True)
    ]
    assert all(differing)  # none of the sweep's spans took the lumped fallback
