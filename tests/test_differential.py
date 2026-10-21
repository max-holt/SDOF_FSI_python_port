"""Differential tests: every Stage 4 module against the frozen ``legacy_port.py``.

The reference is ``legacy_port.get_peak_response`` (line-for-line VBA, verified against
Excel). Each new module is compared with it on

* the golden inputs (the Example-sheet lumped case, fast; the 75 ``curve_10in`` cases
  under the ``slow`` marker), and
* a seeded random sweep (``SEED``, ``N_CASES`` parameter sets, ``RTOL``) that covers what
  the Excel oracle does not (docs/port_review.md §4): ``restrainFreqRatio != 1``, a gap
  small enough to engage, ``outputType`` 1-3, 2-D histories, other ``stepQTY`` values,
  free decay (phase 3) and the friction branches.

Where a quantity lives only in a local of the legacy solver (the per-sub-step unbalance
force, the state after each sub-step, the set-up constants) it is read through a
``sys.settrace`` probe on the solver's frame, exactly as ``tests/test_quirks.py`` does;
``legacy_port.py`` is not instrumented or modified.

The tolerance is ``RTOL = 1e-12`` relative (``atol = 0``); the restructure is expected to
be bitwise, and ``test_sweep_is_bitwise`` records that it is.
"""

from __future__ import annotations

import functools
import inspect
import random
import sys
from dataclasses import dataclass

import numpy as np
import pytest
import test_golden as tg

from surge_sdof import legacy_port as lp
from surge_sdof import loads, response, structure

SEED = 20261019
N_CASES = 50
RTOL = 1e-12

SUMMARY_FIELDS = (
    "max_static_equivalent_force",
    "max_displacement",
    "max_velocity",
    "max_acceleration",
    "max_applied_force",
)


LUMPED_KEYS = (
    "step_qty",
    "sample_freq",
    "physical_length",
    "flexural_rigidity_ei",
    "celerity",
    "mass_per_unit_len",
    "damping_percent",
    "dynamic_fric",
    "nat_freq",
    "restrain_freq_ratio",
    "gap",
)


def assert_close(actual, expected):
    np.testing.assert_allclose(
        np.asarray(actual, float), np.asarray(expected, float), rtol=RTOL, atol=0
    )


# ------------------------------------------------------------------ legacy probe


@dataclass
class Substep:
    free_decay: bool
    tot_ind: int
    f: float | None  # forceA - forceB as the legacy computed it; None in free decay
    pre: tuple  # (x, v, a) before the update
    post: tuple  # (x, v, a) after the update


@dataclass
class LegacyTrace:
    setup: dict
    substeps: list[Substep]
    result: np.ndarray


def _line_numbers(func, text):
    src, start = inspect.getsourcelines(func)
    lines = {start + i for i, s in enumerate(src) if s.strip() == text}
    assert lines, f"probe text {text!r} not found in {func.__name__}"
    return lines


SETUP_NAMES = (
    "portal_frame_height",
    "mass",
    "stiffness",
    "damping",
    "fric_acc",
    "dt",
    "unballance_step_qty",
    "k_overlap",
    "out_max",
)


def trace_legacy(force, **kw) -> LegacyTrace:
    """Run ``lp.get_peak_response`` under a line tracer and return its set-up constants,
    the per-sub-step (force, pre-state, post-state) records and its result."""
    func = lp.get_peak_response
    code = func.__code__
    arm_lines = _line_numbers(func, "a_new = (")
    record_lines = _line_numbers(func, "if abs(a) > a_max:")
    setup_lines = _line_numbers(func, "x = 0.0")
    (decay_line,) = _line_numbers(func, "x_zero = x")
    setup = {}
    substeps = []
    armed = []

    def local_tracer(frame, event, arg):
        if event != "line":
            return local_tracer
        ln = frame.f_lineno
        if ln in arm_lines:
            loc = frame.f_locals
            armed[:] = [
                (
                    ln > decay_line,
                    loc["tot_ind"],
                    None if ln > decay_line else loc["force_a"] - loc["force_b"],
                    (loc["x"], loc["v"], loc["a"]),
                )
            ]
        elif ln in record_lines and armed:
            loc = frame.f_locals
            free_decay, tot_ind, f, pre = armed[0]
            substeps.append(Substep(free_decay, tot_ind, f, pre, (loc["x"], loc["v"], loc["a"])))
            armed.clear()
        elif ln in setup_lines and not setup:
            loc = frame.f_locals
            setup.update({n: loc[n] for n in SETUP_NAMES})
        return local_tracer

    def global_tracer(frame, event, arg):
        return local_tracer if frame.f_code is code else None

    previous = sys.gettrace()
    sys.settrace(global_tracer)
    try:
        result = func(force, **kw)
    finally:
        sys.settrace(previous)
    assert setup and substeps
    return LegacyTrace(setup, substeps, result)


# ------------------------------------------------------------------ random sweep


@dataclass
class SweepCase:
    id: str
    force: np.ndarray  # as passed to the solvers: 1-D, or 2-D walked column-major
    kw: dict  # keyword arguments of get_peak_response / peak_response (gap engaged)
    history_type: int  # the outputType in 1..3 compared besides 0
    x_max_free: float  # xMax of the same case with gap = 1e9 (clamp never engages)


def _piecewise_levels(rng, n, amplitude):
    """Random piecewise-constant force levels (sharp changes so that the elbow-to-elbow
    unbalance ``F(t) - F(t - L/c)`` is large), as Python floats."""
    out = []
    while len(out) < n:
        level = rng.uniform(-amplitude, amplitude)
        out.extend([level] * rng.randint(1, max(2, n // 6)))
    return out[:n]


def _make_case(rng, idx) -> SweepCase:
    step_qty = rng.choice([2, 7, 40])
    sample_freq = rng.uniform(50.0, 300.0)
    # omega * dt <= 0.03 keeps the explicit scheme stable (NOTES.md: growth per cycle
    # scales with (omega dt)^2)
    nat_freq = rng.uniform(0.005, 0.03) * sample_freq * step_qty / (2 * np.pi)
    physical_length = rng.uniform(1.0, 30.0)
    celerity = rng.uniform(300.0, 1500.0)
    mass_per_unit_len = rng.uniform(2.0, 50.0)
    flexural_rigidity_ei = rng.uniform(1e4, 1e6)
    damping_percent = rng.uniform(0.5, 5.0)  # > 0 so that free decay terminates
    dynamic_fric = rng.choice([0.0, 0.005, 0.1])
    restrain_freq_ratio = rng.uniform(0.5, 4.0)
    cols = rng.choice([1, 2, 3])
    n = int(min(max(rng.uniform(1.0, 4.0) * sample_freq / nat_freq, 18), 400))
    n -= n % cols  # 2-D histories are (rows, cols) with rows >= 6 >= 2 * cols: no D-8
    # F / k of order 0.05 .. 1 (model units) so that the free-decay threshold |x| > 0.1
    # is reachable; k ~ (2 pi f)^2 * L * m'
    stiffness_approx = (2 * np.pi * nat_freq) ** 2 * physical_length * mass_per_unit_len
    amplitude = rng.uniform(0.05, 1.0) * stiffness_approx
    flat = np.array(_piecewise_levels(rng, n, amplitude))
    force = flat if cols == 1 else flat.reshape(n // cols, cols, order="F")
    kw = dict(
        step_qty=step_qty,
        sample_freq=sample_freq,
        physical_length=physical_length,
        flexural_rigidity_ei=flexural_rigidity_ei,
        celerity=celerity,
        mass_per_unit_len=mass_per_unit_len,
        damping_percent=damping_percent,
        dynamic_fric=dynamic_fric,
        nat_freq=nat_freq,
        restrain_freq_ratio=restrain_freq_ratio,
    )
    x_max_free = float(lp.get_peak_response(force, **kw, gap=1e9, output_type=0)[1])
    kw["gap"] = rng.uniform(0.1, 0.5) * x_max_free
    return SweepCase(
        id=f"s{idx:02d}_q{step_qty}_c{cols}_f{dynamic_fric}",
        force=force,
        kw=kw,
        history_type=rng.choice([1, 2, 3]),
        x_max_free=x_max_free,
    )


@functools.cache
def sweep_cases() -> tuple[SweepCase, ...]:
    rng = random.Random(SEED)
    return tuple(_make_case(rng, i) for i in range(N_CASES))


@functools.cache
def sweep_trace(idx) -> LegacyTrace:
    case = sweep_cases()[idx]
    return trace_legacy(case.force, **case.kw, output_type=0)


SWEEP_IDS = [c.id for c in sweep_cases()]


def test_sweep_covers_the_oracle_blind_spots():
    cases = sweep_cases()
    assert len(cases) == N_CASES
    assert {c.kw["step_qty"] for c in cases} == {2, 7, 40}
    assert {c.kw["dynamic_fric"] for c in cases} == {0.0, 0.005, 0.1}
    assert {np.ndim(c.force) for c in cases} == {1, 2}
    assert {c.force.shape[1] for c in cases if c.force.ndim == 2} == {2, 3}
    assert {c.history_type for c in cases} == {1, 2, 3}
    assert all(0.5 <= c.kw["restrain_freq_ratio"] <= 4.0 for c in cases)
    assert all(0.1 * c.x_max_free <= c.kw["gap"] <= 0.5 * c.x_max_free for c in cases)
    traces = [sweep_trace(i) for i in range(N_CASES)]
    assert any(s.free_decay for t in traces for s in t.substeps), "no sweep case enters phase 3"
    # the gap engages when the peak displacement exceeds it
    assert any(t.result[1] > c.kw["gap"] for t, c in zip(traces, cases, strict=True))


# ------------------------------------------------------------------ structure.py


@pytest.mark.parametrize("idx", range(N_CASES), ids=SWEEP_IDS)
def test_solve_portal_height_matches_legacy(idx):
    case, trace = sweep_cases()[idx], sweep_trace(idx)
    kw = case.kw
    h = structure.solve_portal_height(
        kw["physical_length"], kw["flexural_rigidity_ei"], kw["mass_per_unit_len"], kw["nat_freq"]
    )
    assert h == trace.setup["portal_frame_height"]


@pytest.mark.parametrize("idx", range(N_CASES), ids=SWEEP_IDS)
def test_lumped_params_match_legacy(idx):
    case, trace = sweep_cases()[idx], sweep_trace(idx)
    kw, su = case.kw, trace.setup
    p = structure.lumped_params(
        kw["physical_length"],
        su["portal_frame_height"],
        kw["mass_per_unit_len"],
        kw["damping_percent"],
        kw["dynamic_fric"],
        kw["nat_freq"],
        su["dt"],
        kw["gap"],
        kw["restrain_freq_ratio"],
    )
    assert (p.mass, p.stiffness, p.damping, p.fric_acc) == (
        su["mass"],
        su["stiffness"],
        su["damping"],
        su["fric_acc"],
    )
    assert p.gap == kw["gap"] and p.ratio2 == kw["restrain_freq_ratio"] ** 2
    assert all(type(v) is float for v in p)


def test_solve_poly_is_the_legacy_function():
    rng = random.Random(SEED)
    for _ in range(200):
        a, b, c = -rng.uniform(1e2, 1e7), rng.uniform(1.0, 1e3), rng.uniform(1.0, 1e2)
        assert structure.solve_poly(a, b, c) == lp.solve_poly(a, b, c)


def test_restoring_force_matches_the_legacy_expression():
    rng = random.Random(SEED)
    for _ in range(2000):
        x = rng.choice([rng.uniform(-1, 1), 0.0, -0.0, rng.uniform(-1e-3, 1e-3)])
        gap = rng.choice([0.0, rng.uniform(0, 0.5), 1e9, -rng.uniform(0, 0.5)])
        ratio = rng.uniform(0.5, 4.0)
        k = rng.uniform(1e2, 1e6)
        expected = (lp.min_unsigned(gap, x) + lp.max(0, abs(x) - gap) * lp.sign(x) * (ratio**2)) * k
        actual = structure.restoring_force(x, k, gap, ratio)
        assert_close(actual, expected)
        assert np.signbit(actual) == np.signbit(expected)


@pytest.mark.parametrize("idx", range(N_CASES), ids=SWEEP_IDS)
def test_step_replays_the_legacy_substeps(idx):
    """Feed each legacy sub-step's pre-state and applied force through ``structure.step``
    and compare the post-state; this isolates the kernel from the force scheduling."""
    case, trace = sweep_cases()[idx], sweep_trace(idx)
    kw, su = case.kw, trace.setup
    params = structure.SdofParams(
        su["mass"],
        su["stiffness"],
        su["damping"],
        su["fric_acc"],
        kw["gap"],
        kw["restrain_freq_ratio"] ** 2,
    )
    dt = float(su["dt"])
    posts = []
    for s in trace.substeps:
        f = 0.0 if s.free_decay else float(s.f)
        post = structure.step(tuple(float(q) for q in s.pre), f, params, dt)
        assert all(type(q) is float for q in post)
        posts.append(post)
    assert_close(posts, [s.post for s in trace.substeps])
    # the chain is also consistent: every post-state is the next pre-state
    for prev, nxt in zip(trace.substeps, trace.substeps[1:], strict=False):
        assert prev.post == nxt.pre


# ------------------------------------------------------------------ loads.py


def _legacy_forced_samples(trace: LegacyTrace) -> list[list[float]]:
    """The legacy solver's ``forceA - forceB`` per sub-step, grouped by sample."""
    samples: dict[int, list[float]] = {}
    for s in trace.substeps:
        if not s.free_decay:
            samples.setdefault(s.tot_ind, []).append(float(s.f))
    assert sorted(samples) == list(range(1, len(samples) + 1))
    return [samples[t] for t in range(1, len(samples) + 1)]


def _check_unbalance(force, kw, trace):
    expected = _legacy_forced_samples(trace)
    actual = list(
        loads.unbalance_force(
            force, kw["sample_freq"], kw["physical_length"], kw["celerity"], kw["step_qty"]
        )
    )
    assert len(actual) == len(expected)
    for got, want in zip(actual, expected, strict=True):
        assert len(got) == len(want)
        assert all(type(v) is float for v in got)
        assert_close(got, want)
    unb = loads.transit_delay(kw["physical_length"], kw["celerity"], kw["sample_freq"])
    assert unb == trace.setup["unballance_step_qty"]
    assert loads.overlap_substeps(unb, kw["step_qty"]) == trace.setup["k_overlap"]
    return actual


@pytest.mark.parametrize("idx", range(N_CASES), ids=SWEEP_IDS)
def test_unbalance_force_matches_legacy_sequence(idx):
    case, trace = sweep_cases()[idx], sweep_trace(idx)
    samples = _check_unbalance(case.force, case.kw, trace)
    # phase 1 yields totInd samples, the last truncated; phase 2 one full sample per element
    n_elements = int(np.size(case.force))
    s = case.kw["step_qty"]
    n_delay = len(samples) - n_elements
    assert n_delay >= 1
    assert all(len(x) == s for x in samples[: n_delay - 1])
    assert 1 <= len(samples[n_delay - 1]) <= s
    assert all(len(x) == s for x in samples[n_delay:])


def test_unbalance_force_matches_legacy_on_the_example_case():
    case = next(c for c in tg.EXAMPLE_CASES if c["solver"] == "lumped")
    force = np.asarray(case["force_history"], dtype=float)
    kw = {k: case["kwargs"][k] for k in LUMPED_KEYS if k in case["kwargs"]}
    trace = trace_legacy(force, **kw, output_type=0)
    _check_unbalance(force, kw, trace)


def test_unbalance_force_step_qty_one_divides_by_zero():
    # D-7 preserved
    with pytest.raises(ZeroDivisionError):
        next(loads.unbalance_force(np.ones(10), 100.0, 10.0, 1000.0, 1))


def test_unbalance_force_single_row_history_raises_index_error():
    # D-8 preserved: a (1, n) history exhausts the phase-1 walk without Exit For
    force = np.ones((1, 10))
    with pytest.raises(IndexError):
        list(loads.unbalance_force(force, 100.0, 100.0, 1000.0, 10))
    with pytest.raises(IndexError):
        lp.get_peak_response(force, 10, 100.0, 100.0, 2e5, 1000.0, 10.0, 2.0, 0.3, 5.0)


# ------------------------------------------------------------------ response.py


def _check_peak_response(force, kw, output_types):
    """``peak_response`` against ``get_peak_response`` for each output type."""
    results = {}
    for output_type in output_types:
        legacy = lp.get_peak_response(force, **kw, output_type=output_type)
        res = response.peak_response(force, **kw, output_type=output_type)
        assert isinstance(res, response.PeakResponse)
        assert res.output_type == output_type
        if output_type == 0:
            assert res.history is None
            assert legacy.shape == (5,)
            assert_close(res.summary(), legacy)
        else:
            assert res.history is not None
            assert res.history.shape == (legacy.shape[0] - 1,)
            assert_close(res.history, legacy[1:])
        results[output_type] = res
    return results


@pytest.mark.parametrize("idx", range(N_CASES), ids=SWEEP_IDS)
def test_peak_response_matches_legacy_on_the_sweep(idx):
    case, trace = sweep_cases()[idx], sweep_trace(idx)
    results = _check_peak_response(case.force, case.kw, (0, case.history_type))
    free = {s.tot_ind for s in trace.substeps if s.free_decay}
    for res in results.values():
        assert res.free_decay_samples == len(free)
        assert all(type(getattr(res, f)) is float for f in SUMMARY_FIELDS)


def test_sweep_enters_free_decay_and_engages_the_gap():
    cases = sweep_cases()
    results = [response.peak_response(c.force, **c.kw) for c in cases]
    assert sum(r.free_decay_samples > 0 for r in results) >= 1
    assert sum(r.max_displacement > c.kw["gap"] for r, c in zip(results, cases, strict=True)) >= 1
    # and the gap matters: the clamped case differs from the gap-free run
    assert any(r.max_displacement != c.x_max_free for r, c in zip(results, cases, strict=True))


def _example_lumped():
    case = next(c for c in tg.EXAMPLE_CASES if c["solver"] == "lumped")
    force = np.asarray(case["force_history"], dtype=float)
    kw = {k: case["kwargs"][k] for k in LUMPED_KEYS if k in case["kwargs"]}
    return case, force, kw


def test_peak_response_matches_legacy_on_the_example_case():
    case, force, kw = _example_lumped()
    results = _check_peak_response(force, kw, (0, 1, 2, 3))
    np.testing.assert_allclose(
        results[0].summary(), np.asarray(case["expected"], float), rtol=tg.EXAMPLE_RTOL, atol=0
    )


@pytest.mark.slow
@pytest.mark.parametrize(
    "case", [c for c in tg.CASES if c["solver"] == "lumped"], ids=lambda c: c["case_id"]
)
def test_peak_response_matches_legacy_on_the_golden_curve(case):
    kw = {k: v for k, v in tg.case_params(case, tg.PARAMS).items() if k != "output_type"}
    force = tg.load_force(tg.PARAMS)
    results = _check_peak_response(force, kw, (0,))
    expected = [float(case[name]) for name in tg.OUTPUT_NAMES]
    np.testing.assert_allclose(results[0].summary(), expected, rtol=tg.RTOL["lumped"], atol=0)


def test_peak_response_1d_history_equals_its_column():
    case, force, kw = _example_lumped()
    a = response.peak_response(force[:, 0], **kw)
    b = response.peak_response(force, **kw)
    assert a == b or np.array_equal(a.summary(), b.summary())


def test_peak_response_raises_on_overflow():
    # D-23. (a) x ~ 1e301 at the end of the forced phase: the free-decay test x * xZero
    # overflows; the legacy numpy state raises there and so does peak_response.
    _case, _force, kw = _example_lumped()
    force = np.array([0.0, 1e308, -1e308, 1e308, -1e308, 0.0, 0.0, 0.0, 0.0, 0.0])
    with pytest.raises(FloatingPointError):
        lp.get_peak_response(force, **kw)
    with pytest.raises(FloatingPointError):
        response.peak_response(force, **kw)
    # (b) stiffness = inf (pure-Python set-up overflow, D-14): the legacy raises at the
    # first invalid 0 * inf in the restoring term; the Python-float state carries the
    # nan to the end and peak_response raises there.
    _case, force, kw = _example_lumped()
    kw = dict(kw, nat_freq=1e150)
    with pytest.raises(FloatingPointError):
        lp.get_peak_response(force, **kw)
    with pytest.raises(FloatingPointError):
        response.peak_response(force, **kw)
