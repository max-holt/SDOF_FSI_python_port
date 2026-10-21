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

The tolerance is ``RTOL = 1e-12`` relative (``atol = 0``) and is the contract; the
restructure is expected to be bitwise, which NOTES.md records as the measured result (not
pinned here, so that a later JIT stage is judged against the tolerance).
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

from surge_sdof import coupling, loads, moc, response, structure
from surge_sdof import legacy_port as lp

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


# ================================================================== JC path (Stage 4.2)
# Reference: ``lp.get_peak_response_jc``. The MoC arrays, ``dF`` and the acceleration the
# MoC block consumed live only in the solver's locals and are read with the same probe
# technique; fallback cases never reach the JC set-up line and are detected by an empty
# trace (the lumped solver runs in its own frame, which the probe does not follow).

JC_KEYS = LUMPED_KEYS[:7] + ("fluid_densty", "fluid_area") + LUMPED_KEYS[7:]
JC_SETUP_NAMES = SETUP_NAMES + (
    "dacay_factor",
    "pivot_seg_qty",
    "pipe_seg_qty",
    "rho_c",
    "fluid_area",
)


@dataclass
class JcSubstep:
    free_decay: bool
    tot_ind: int
    k: int  # the VBA loop variable (phase 3: 1 .. stepQTY)
    f: float | None  # forceA - forceB; None in free decay
    pre: tuple  # (x, v, a) before the SDOF update; ``a`` is what the MoC block used
    post: tuple
    d_f: float  # dF after this sub-step's MoC update
    array_a: np.ndarray | None  # arrayA / arrayB after the MoC update (``arrays=True``)
    array_b: np.ndarray | None

    @property
    def legacy_index(self) -> int:
        """``k + (totInd - 1) * stepQTY``, the VBA parity index (D-19)."""
        return self.k + (self.tot_ind - 1) * self.step_qty

    step_qty: int = 0


def trace_legacy_jc(force, arrays=False, **kw) -> LegacyTrace:
    """Run ``lp.get_peak_response_jc`` under a line tracer; ``setup`` is empty and
    ``substeps`` is empty when the short-pipe fallback was taken."""
    func = lp.get_peak_response_jc
    code = func.__code__
    arm_lines = _line_numbers(func, "a_new = (")
    record_lines = _line_numbers(func, "if abs(a) > a_max:")
    setup_lines = _line_numbers(func, "x = 0.0")
    (decay_line,) = _line_numbers(func, "x_zero = x")
    step_qty = int(kw["step_qty"])
    setup = {}
    substeps = []
    armed = []

    def local_tracer(frame, event, arg):
        if event != "line":
            return local_tracer
        ln = frame.f_lineno
        if ln in arm_lines:
            loc = frame.f_locals
            free = ln > decay_line
            armed[:] = [
                JcSubstep(
                    free,
                    loc["tot_ind"],
                    loc["k"],
                    None if free else loc["force_a"] - loc["force_b"],
                    (loc["x"], loc["v"], loc["a"]),
                    (),
                    loc["d_f"],
                    loc["array_a"].copy() if arrays else None,
                    loc["array_b"].copy() if arrays else None,
                    step_qty,
                )
            ]
        elif ln in record_lines and armed:
            loc = frame.f_locals
            s = armed[0]
            s.post = (loc["x"], loc["v"], loc["a"])
            substeps.append(s)
            armed.clear()
        elif ln in setup_lines and not setup:
            loc = frame.f_locals
            setup.update({n: loc[n] for n in JC_SETUP_NAMES})
        return local_tracer

    def global_tracer(frame, event, arg):
        return local_tracer if frame.f_code is code else None

    previous = sys.gettrace()
    sys.settrace(global_tracer)
    try:
        result = func(force, **kw)
    finally:
        sys.settrace(previous)
    assert bool(setup) == bool(substeps)
    return LegacyTrace(setup, substeps, result)


# Small JC cases (grids of 14-18 cells, 100 samples): the smoke-test parameters at the
# three spans of ``test_smoke.py`` plus the Example-sheet JC case.
JC_SMALL_KW = dict(
    step_qty=10,
    sample_freq=100.0,
    physical_length=10.0,
    flexural_rigidity_ei=2e5,
    celerity=1000.0,
    mass_per_unit_len=10.0,
    damping_percent=2.0,
    dynamic_fric=0.3,
    nat_freq=5.0,
    fluid_densty=1000.0,
    fluid_area=0.005,
)


def _step_force(n=100, amplitude=1000.0):
    f = np.full((n, 1), amplitude)
    f[0, 0] = 0.0
    return f


def _example_jc():
    case = next(c for c in tg.EXAMPLE_CASES if c["solver"] == "jc")
    force = np.asarray(case["force_history"], dtype=float)
    kw = {k: case["kwargs"][k] for k in JC_KEYS if k in case["kwargs"]}
    return case, force, kw


def jc_small_cases():
    cases = [
        (f"smoke_L{L}", _step_force(), dict(JC_SMALL_KW, physical_length=L))
        for L in (10.0, 12.5, 7.0)
    ]
    _case, force, kw = _example_jc()
    cases.append(("example_jc", force, kw))
    return cases


JC_SMALL = jc_small_cases()
JC_SMALL_IDS = [c[0] for c in JC_SMALL]


@functools.cache
def jc_small_trace(idx) -> LegacyTrace:
    _id, force, kw = JC_SMALL[idx]
    return trace_legacy_jc(force, arrays=True, **kw, output_type=0)


# ------------------------------------------------------------------ moc.py


@pytest.mark.parametrize("idx", range(len(JC_SMALL)), ids=JC_SMALL_IDS)
def test_moc_grid_setup_matches_legacy(idx):
    _id, _force, kw = JC_SMALL[idx]
    su = jc_small_trace(idx).setup
    assert su, "expected a MoC run, not the fallback"
    grid = moc.grid_size(kw["physical_length"], su["portal_frame_height"], kw["celerity"], su["dt"])
    assert grid == (su["pipe_seg_qty"], su["pivot_seg_qty"])
    assert not moc.is_short_pipe(*grid)
    assert moc.decay_factor(kw["celerity"], su["dt"], kw["physical_length"]) == su["dacay_factor"]
    assert moc.vav_divisor(grid[0], "legacy") == 2 * grid[0] - 1
    assert moc.vav_divisor(grid[0], "fixed") == 2 * grid[0] + 1
    with pytest.raises(ValueError):
        moc.vav_divisor(grid[0], "other")


def test_interp_fractions_match_the_legacy_helpers():
    for pipe_seg_qty in (14, 16, 18, 30, 64, 546, 666):
        for pivot_seg_qty in (5, 6, 7, 27, 50, 87):
            if moc.is_short_pipe(pipe_seg_qty, pivot_seg_qty):
                continue
            frac_a, frac_b = moc.interp_fractions(pipe_seg_qty, pivot_seg_qty)
            assert frac_a.shape == (pipe_seg_qty + 1,) and frac_b.shape == (pipe_seg_qty,)
            assert frac_a[0] == frac_a[pipe_seg_qty] == 0.0  # never read by step
            for n in range(1, pipe_seg_qty):
                assert frac_a[n] == lp.interp_fraction_a(n, pivot_seg_qty, pipe_seg_qty)
                assert moc.interp_fraction_a(n, pivot_seg_qty, pipe_seg_qty) == frac_a[n]
            for n in range(0, pipe_seg_qty):
                assert frac_b[n] == lp.interp_fraction_b(n, pivot_seg_qty, pipe_seg_qty)
                assert moc.interp_fraction_b(n, pivot_seg_qty, pipe_seg_qty) == frac_b[n]


def test_interp_fractions_minimal_pivot_divides_by_zero_at_setup():
    # D-4: interpFractionB(3) with pivotSegQTY = 4; the legacy raised in its first MoC
    # update, the tabulation raises at set-up
    with pytest.raises(ZeroDivisionError):
        lp.interp_fraction_b(3, 4, 20)
    with pytest.raises(ZeroDivisionError):
        moc.interp_fractions(20, 4)


def _replay_moc(trace: LegacyTrace, vav_denominator="legacy"):
    """Chain ``moc.step`` over the legacy's parity sequence and accelerations, starting
    from rest, and return the per-sub-step (p_a, v_a, p_b, v_b, d_f) it produces."""
    su = trace.setup
    n_seg, pivot = su["pipe_seg_qty"], su["pivot_seg_qty"]
    frac_a, frac_b = moc.interp_fractions(n_seg, pivot)
    p_a, v_a, p_b, v_b = moc.new_column(n_seg)
    vav_div = moc.vav_divisor(n_seg, vav_denominator)
    dt = float(su["dt"])
    d_f = 0.0
    out = []
    for s in trace.substeps:
        even = s.legacy_index % 2 == 0
        d_f = moc.step(
            even,
            float(s.pre[2]) * dt,
            p_a,
            v_a,
            p_b,
            v_b,
            frac_a,
            frac_b,
            n_seg,
            pivot,
            float(su["rho_c"]),
            float(su["dacay_factor"]),
            vav_div,
            float(su["fluid_area"]),
            d_f,
        )
        out.append((p_a.copy(), v_a.copy(), p_b.copy(), v_b.copy(), float(d_f)))
    return out


@pytest.mark.parametrize("idx", range(len(JC_SMALL)), ids=JC_SMALL_IDS)
def test_moc_step_replays_the_legacy_moc_block(idx):
    """Drive ``moc.step`` with the legacy solver's own parity sequence and accelerations
    and compare the four arrays and ``dF`` after every sub-step: the chained replay
    isolates the MoC kernel from the SDOF update and the force scheduling."""
    trace = jc_small_trace(idx)
    replay = _replay_moc(trace)
    assert len(replay) == len(trace.substeps) > 0
    for (p_a, v_a, p_b, v_b, d_f), s in zip(replay, trace.substeps, strict=True):
        assert_close(p_a, s.array_a[0])
        assert_close(v_a, s.array_a[1])
        assert_close(p_b, s.array_b[0])
        assert_close(v_b, s.array_b[1])
        assert_close(d_f, s.d_f)
    assert any(s.d_f != 0.0 for s in trace.substeps)


def test_moc_step_fixed_vav_divisor_changes_the_mean_velocity_only():
    """F-1 behind the flag: with 2N + 1 the replay differs from the legacy, and the
    difference is confined to what vAv touches (every velocity on an even step)."""
    trace = jc_small_trace(0)
    legacy = _replay_moc(trace, "legacy")
    fixed = _replay_moc(trace, "fixed")
    first_even = next(i for i, s in enumerate(trace.substeps) if s.legacy_index % 2 == 0)
    # the first even step from rest: vAv = 0 both ways, no difference yet
    assert legacy[first_even][4] == fixed[first_even][4]
    assert any(a[4] != b[4] for a, b in zip(legacy, fixed, strict=True))


# ------------------------------------------------------------------ coupling.py


@pytest.mark.parametrize("idx", range(len(JC_SMALL)), ids=JC_SMALL_IDS)
def test_junction_coupling_reproduces_the_legacy_df_sequence(idx):
    """Drive ``JunctionCoupling`` with the legacy's per-phase parity index and its
    pre-update state and compare ``dF`` and the column after every sub-step."""
    _id, _force, kw = JC_SMALL[idx]
    trace = jc_small_trace(idx)
    su = trace.setup
    jc = coupling.JunctionCoupling(
        su["pipe_seg_qty"],
        su["pivot_seg_qty"],
        su["dt"],
        su["rho_c"],
        kw["fluid_area"],
        su["dacay_factor"],
        vav_denominator="legacy",
    )
    assert jc.rho_c == kw["fluid_densty"] * kw["celerity"]
    d_fs = []
    for s in trace.substeps:
        d_f = jc.coupling_force(tuple(float(q) for q in s.pre), s.legacy_index)
        assert type(d_f) is float
        d_fs.append(d_f)
        p_a, v_a, p_b, v_b = jc.column()
        assert_close(p_a, s.array_a[0])
        assert_close(v_a, s.array_a[1])
        assert_close(p_b, s.array_b[0])
        assert_close(v_b, s.array_b[1])
    assert_close(d_fs, [s.d_f for s in trace.substeps])
    assert jc.d_f == d_fs[-1]


def test_junction_coupling_without_fluid_area_returns_exact_zero():
    _id, _force, kw = JC_SMALL[0]
    su = jc_small_trace(0).setup
    jc = coupling.JunctionCoupling(
        su["pipe_seg_qty"], su["pivot_seg_qty"], su["dt"], su["rho_c"], 0.0, su["dacay_factor"]
    )
    for n in range(50):
        d_f = jc.coupling_force((0.0, 0.0, 3.0), n)
        assert d_f == 0.0 and not np.signbit(d_f)
    assert np.any(jc.column()[1] != 0.0)  # the column still moves with the mass


def test_no_coupling_is_unchanged():
    assert coupling.NoCoupling().coupling_force((1.0, 2.0, 3.0), 7) == 0.0


# ------------------------------------------------------------------ response.py (JC)

LEGACY_FLAGS = dict(vav_denominator="legacy", parity="per_phase")


@pytest.mark.parametrize("idx", range(len(JC_SMALL)), ids=JC_SMALL_IDS)
def test_jc_params_match_legacy(idx):
    _id, _force, kw = JC_SMALL[idx]
    su = jc_small_trace(idx).setup
    p = structure.jc_params(
        kw["physical_length"],
        su["portal_frame_height"],
        kw["mass_per_unit_len"],
        kw["fluid_densty"],
        kw["fluid_area"],
        kw["damping_percent"],
        kw["dynamic_fric"],
        kw["nat_freq"],
        su["dt"],
        kw.get("gap", 0.0),
        kw.get("restrain_freq_ratio", 1.0),
    )
    assert (p.mass, p.stiffness, p.damping, p.fric_acc) == (
        su["mass"],
        su["stiffness"],
        su["damping"],
        su["fric_acc"],
    )
    assert all(type(v) is float for v in p)


def _check_peak_response_jc(force, kw, output_types, flags=LEGACY_FLAGS):
    """``peak_response_jc`` (with ``flags``) against ``get_peak_response_jc`` per output type."""
    results = {}
    for output_type in output_types:
        legacy = lp.get_peak_response_jc(force, **kw, output_type=output_type)
        res = response.peak_response_jc(force, **kw, output_type=output_type, **flags)
        assert isinstance(res, response.PeakResponse)
        assert res.output_type == output_type
        if output_type == 0:
            assert res.history is None
            assert legacy.shape == (5,)
            assert_close(res.summary(), legacy)
            assert all(type(getattr(res, f)) is float for f in SUMMARY_FIELDS)
        else:
            assert res.history is not None
            assert res.history.shape == (legacy.shape[0] - 1,)
            assert_close(res.history, legacy[1:])
        results[output_type] = res
    return results


@pytest.mark.parametrize("idx", range(len(JC_SMALL)), ids=JC_SMALL_IDS)
def test_peak_response_jc_matches_legacy_on_the_small_cases(idx):
    _id, force, kw = JC_SMALL[idx]
    trace = jc_small_trace(idx)
    results = _check_peak_response_jc(force, kw, (0, 1, 2, 3))
    free = {s.tot_ind for s in trace.substeps if s.free_decay}
    assert all(r.free_decay_samples == len(free) for r in results.values())


def test_peak_response_jc_matches_excel_on_the_example_case():
    case, force, kw = _example_jc()
    res = response.peak_response_jc(force, **kw, **LEGACY_FLAGS)
    np.testing.assert_allclose(
        res.summary(), np.asarray(case["expected"], float), rtol=tg.EXAMPLE_RTOL, atol=0
    )
    assert res.free_decay_samples > 0  # the Example JC case ends with |x| > 0.1


def test_peak_response_jc_short_pipe_falls_back_to_the_lumped_solver():
    force = _step_force()
    kw = dict(JC_SMALL_KW, physical_length=1.0)
    lumped_kw = {k: v for k, v in kw.items() if not k.startswith("fluid")}
    for output_type in (0, 1):
        res = _check_peak_response_jc(force, kw, (output_type,))[output_type]
        lumped = response.peak_response(force, **lumped_kw, output_type=output_type)
        assert np.array_equal(res.summary(), lumped.summary())
        assert res.free_decay_samples == lumped.free_decay_samples
        if output_type == 0:
            assert res.history is None and lumped.history is None
        else:
            assert np.array_equal(res.history, lumped.history)
    # the legacy took its fallback too: no JC sub-step was traced
    assert not trace_legacy_jc(force, **kw, output_type=0).substeps


def test_peak_response_jc_rejects_unknown_flags():
    _id, force, kw = JC_SMALL[0]
    with pytest.raises(ValueError):
        response.peak_response_jc(force, **kw, parity="phase")
    with pytest.raises(ValueError):
        response.peak_response_jc(force, **kw, vav_denominator="2N")


def test_peak_response_jc_runtime_errors_are_raised():
    # D-9 as a raise, like the legacy: D-7, rhoC = 0 (FloatingPointError from the numpy
    # MoC arrays under errstate), D-8
    force = _step_force()
    with pytest.raises(ZeroDivisionError):
        response.peak_response_jc(force, **dict(JC_SMALL_KW, step_qty=1))
    with pytest.raises(FloatingPointError):
        response.peak_response_jc(force, **dict(JC_SMALL_KW, fluid_densty=0.0))
    with pytest.raises(IndexError):
        response.peak_response_jc(force.reshape(1, 100), **dict(JC_SMALL_KW, physical_length=12.5))


@pytest.mark.jc_slow
@pytest.mark.parametrize(
    "case", [c for c in tg.CASES if c["solver"] == "jc"], ids=lambda c: c["case_id"]
)
def test_peak_response_jc_matches_excel_on_the_golden_curve(case):
    """The new solver with the legacy flags against the Excel fixture at the golden
    tolerance. The fixture is the legacy result (the literal port matched it to 8.6e-13);
    bitwise agreement with ``legacy_port`` is established on the small grids above and in
    the sweep, so the legacy solver is not re-run here (owner's decision, Stage 4.2)."""
    kw = {k: v for k, v in tg.case_params(case, tg.PARAMS).items() if k != "output_type"}
    force = tg.load_force(tg.PARAMS)
    res = response.peak_response_jc(force, **kw, **LEGACY_FLAGS)
    expected = [float(case[name]) for name in tg.OUTPUT_NAMES]
    tg.check_and_cache(
        case["case_id"] + "_response",
        "jc",
        f"curve_10in row {case['source_row']} via response.peak_response_jc (legacy flags)",
        tg.OUTPUT_NAMES,
        res.summary(),
        expected,
        tg.RTOL["jc"],
    )
    assert res.free_decay_samples == 0
