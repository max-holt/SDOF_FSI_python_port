"""Property-based checks on the Stage 4/5 solvers (hypothesis).

These are consistency properties of the model, not oracles: the Excel fixtures are the
oracle (``test_golden.py``) and ``legacy_port`` the reference (``test_differential.py``).
They run on small cases (tens of samples, grids of a few tens of cells) so that the suite
stays fast in both modes (Numba and ``NUMBA_DISABLE_JIT=1``). ``derandomize=True`` makes
every run reproduce the same examples (the repository's sweeps are seeded for the same
reason); ``deadline=None`` because a first call compiles the kernel.

Properties
----------
1. ``gap = 1e9`` (the support clamp never engages) equals ``gap = 0`` with
   ``restrainFreqRatio = 1`` **bitwise**, for both solvers and every output type: with
   ``gap = 0`` the VBA ``minUnsigned(gap, x)`` is ``+-0`` and ``max(0, |x| - 0) * sign(x)
   * 1`` is ``x``; with a huge gap ``minUnsigned`` is ``x`` and the excess term ``0``.
2. Linearity: with ``dynamicFric = 0`` and the gap never engaged the scheme is linear in
   the load. Scaling the force history by a power of two scales every IEEE operation
   exactly, so the result is **bitwise** the scaled one over the samples both runs
   compute, and the summary is bitwise scaled when both runs integrate the same number
   of free-decay samples. For an arbitrary factor the forced-phase history scales at
   rtol 1e-9. The free-decay test ``x * xZero > 0.01`` (D-21) is an *absolute*
   threshold, so the number of phase-3 samples is amplitude-dependent: that is why the
   comparison stops at the shorter run and the summaries are compared conditionally.
3. Every maximum is finite and non-negative and the history finite over the sampled
   parameter space (friction, engaged gaps and ratios != 1 included).
4. ``peak_response_jc`` with ``fluidArea = 0`` equals ``peak_response`` within 1e-12: the
   junction force stays exactly 0 and the fluid-corrected set-up (``jc_params``) reduces
   to the lumped one up to the association of ``mass`` (rounding level). Short spans take
   the lumped fallback and are trivially equal (reported as a hypothesis event).

Parameter space: ``omega * dt <= 0.03`` (explicit scheme, NOTES.md), damping > 0 so that
free decay terminates, ``stepQTY >= 2`` (D-7), 1-D histories (no D-8), rigid mass > 0,
``pivotSegQTY != 4`` (D-4, assumed away).
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, event, given, settings
from hypothesis import strategies as st

from surge_sdof import moc, response, structure

SETTINGS = settings(
    max_examples=30,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)

FLUID_DENSTY = 1000.0


@st.composite
def lumped_cases(draw, with_friction=True):
    """A small lumped case: ``(force, kw)`` without ``gap`` / ``restrain_freq_ratio``."""
    step_qty = draw(st.integers(2, 8))
    sample_freq = draw(st.floats(50.0, 300.0))
    omega_dt = draw(st.floats(0.005, 0.03))
    nat_freq = omega_dt * sample_freq * step_qty / (2 * math.pi)
    physical_length = draw(st.floats(1.0, 30.0))
    celerity = draw(st.floats(300.0, 1500.0))
    mass_per_unit_len = draw(st.floats(60.0, 150.0))
    flexural_rigidity_ei = draw(st.floats(1e4, 1e6))
    damping_percent = draw(st.floats(0.5, 5.0))
    dynamic_fric = draw(st.sampled_from([0.0, 0.005, 0.1, 0.3])) if with_friction else 0.0
    n = draw(st.integers(10, 40))
    stiffness_approx = (2 * math.pi * nat_freq) ** 2 * physical_length * mass_per_unit_len
    amplitude = draw(st.floats(0.05, 1.0)) * stiffness_approx
    # piecewise-constant levels of order F / k ~ 0.05 .. 1: a level is 0 or at least 5 %
    # of the amplitude, so no response is subnormal (where power-of-two scaling would
    # stop being exact) and no history is identically zero
    level = st.one_of(st.just(0.0), st.floats(0.05, 1.0), st.floats(-1.0, -0.05))
    levels = draw(st.lists(level, min_size=2, max_size=6))
    # at least one level is non-zero and sits after the first sample
    levels[draw(st.integers(1, len(levels) - 1))] = draw(st.floats(0.05, 1.0)) * draw(
        st.sampled_from([-1.0, 1.0])
    )
    force = np.array([amplitude * levels[(i * len(levels)) // n] for i in range(n)])
    force[0] = 0.0
    assert np.max(np.abs(force)) > 0
    kw = {
        "step_qty": step_qty,
        "sample_freq": sample_freq,
        "physical_length": physical_length,
        "flexural_rigidity_ei": flexural_rigidity_ei,
        "celerity": celerity,
        "mass_per_unit_len": mass_per_unit_len,
        "damping_percent": damping_percent,
        "dynamic_fric": dynamic_fric,
        "nat_freq": nat_freq,
    }
    return force, kw


def jc_kw(kw, fluid_area):
    """The JC keyword set for a lumped ``kw``; None when the grid would hit D-4."""
    dt = 1 / (kw["sample_freq"] * kw["step_qty"])
    h = structure.solve_portal_height(
        kw["physical_length"], kw["flexural_rigidity_ei"], kw["mass_per_unit_len"], kw["nat_freq"]
    )
    pipe_seg_qty, pivot_seg_qty = moc.grid_size(kw["physical_length"], h, kw["celerity"], dt)
    if pivot_seg_qty == 4:
        return None
    assume(pipe_seg_qty <= 80)  # keeps the suite fast; the grid size is not the point
    event("fallback" if moc.is_short_pipe(pipe_seg_qty, pivot_seg_qty) else "moc path")
    return dict(kw, fluid_densty=FLUID_DENSTY, fluid_area=fluid_area)


def same_result(a: response.PeakResponse, b: response.PeakResponse) -> bool:
    return (
        np.array_equal(a.summary(), b.summary())
        and a.free_decay_samples == b.free_decay_samples
        and ((a.history is None and b.history is None) or np.array_equal(a.history, b.history))
    )


# ------------------------------------------------------------------ 1. gap -> infinity


@SETTINGS
@given(
    case=lumped_cases(),
    output_type=st.integers(0, 3),
    fluid_area=st.sampled_from([None, 0.01, 0.05]),
)
def test_huge_gap_equals_zero_gap_with_unit_ratio(case, output_type, fluid_area):
    force, kw = case
    if fluid_area is None:
        solver = response.peak_response
    else:
        kw = jc_kw(kw, fluid_area)
        assume(kw is not None)
        solver = response.peak_response_jc
    huge = solver(force, **kw, restrain_freq_ratio=1, gap=1e9, output_type=output_type)
    zero = solver(force, **kw, restrain_freq_ratio=1, gap=0, output_type=output_type)
    assert same_result(zero, huge)
    # with a huge gap the stiffness beyond the gap is never used
    ratio = solver(force, **kw, restrain_freq_ratio=3, gap=1e9, output_type=output_type)
    assert same_result(ratio, huge)
    # non-trivial unless the transit delay rounds to zero sub-steps, when forceA == forceB
    # at every sub-step and the VBA response is identically zero
    if huge.max_applied_force > 0:
        assert huge.max_displacement > 0
    else:
        event("transit delay below half a sub-step: zero unbalance force")


# ------------------------------------------------------------------ 2. linearity


@SETTINGS
@given(
    case=lumped_cases(with_friction=False),
    factor=st.sampled_from([0.25, 0.5, 2.0, 4.0, 8.0]),
    fluid_area=st.sampled_from([None, 0.01]),
)
def test_power_of_two_load_scaling_is_bitwise(case, factor, fluid_area):
    force, kw = case
    if fluid_area is None:
        solver = response.peak_response
    else:
        kw = jc_kw(kw, fluid_area)
        assume(kw is not None)
        solver = response.peak_response_jc
    base = solver(force, **kw, gap=1e9, output_type=1)
    scaled = solver(force * factor, **kw, gap=1e9, output_type=1)
    forced = len(force)
    common = forced + min(base.free_decay_samples, scaled.free_decay_samples)
    common = min(common, len(base.history))
    assert np.array_equal(scaled.history[:common], base.history[:common] * factor)
    if base.free_decay_samples == scaled.free_decay_samples:
        assert np.array_equal(scaled.summary(), base.summary() * factor)
    else:
        event("phase-3 length differs with the amplitude (D-21 absolute threshold)")
        # the applied-force maximum does not depend on the free decay
        assert scaled.max_applied_force == base.max_applied_force * factor


@SETTINGS
@given(case=lumped_cases(with_friction=False), factor=st.floats(0.1, 10.0))
def test_arbitrary_load_scaling_is_linear_over_the_forced_phase(case, factor):
    force, kw = case
    assume(abs(factor - 1.0) > 1e-3)
    base = response.peak_response(force, **kw, gap=1e9, output_type=1)
    scaled = response.peak_response(force * factor, **kw, gap=1e9, output_type=1)
    forced = len(force)
    np.testing.assert_allclose(
        scaled.history[:forced], base.history[:forced] * factor, rtol=1e-9, atol=0
    )
    np.testing.assert_allclose(
        scaled.max_applied_force, base.max_applied_force * factor, rtol=1e-12, atol=0
    )


# ------------------------------------------------------------------ 3. finite, non-negative


@SETTINGS
@given(
    case=lumped_cases(),
    ratio=st.floats(0.5, 4.0),
    gap_fraction=st.floats(0.0, 1.5),
    output_type=st.integers(0, 3),
    fluid_area=st.sampled_from([None, 0.0, 0.01, 0.05]),
)
def test_maxima_are_finite_and_non_negative(case, ratio, gap_fraction, output_type, fluid_area):
    force, kw = case
    if fluid_area is None:
        solver = response.peak_response
    else:
        kw = jc_kw(kw, fluid_area)
        assume(kw is not None)
        solver = response.peak_response_jc
    free = solver(force, **kw, restrain_freq_ratio=ratio, gap=1e9, output_type=0)
    gap = gap_fraction * free.max_displacement
    event("gap engaged" if gap < free.max_displacement else "gap not engaged")
    res = solver(force, **kw, restrain_freq_ratio=ratio, gap=gap, output_type=output_type)
    summary = res.summary()
    assert np.all(np.isfinite(summary))
    assert np.all(summary >= 0)
    assert res.max_applied_force == free.max_applied_force  # independent of the restraint
    assert res.free_decay_samples >= 0
    if output_type == 0:
        assert res.history is None
    else:
        assert np.all(np.isfinite(res.history))
        assert np.max(np.abs(res.history)) <= summary[output_type] * (1 + 1e-15)


# ------------------------------------------------------------------ 4. JC with fluidArea = 0


@SETTINGS
@given(
    case=lumped_cases(),
    ratio=st.floats(0.5, 4.0),
    gap_fraction=st.floats(0.1, 1.5),
    output_type=st.integers(0, 3),
)
def test_jc_without_fluid_area_equals_lumped(case, ratio, gap_fraction, output_type):
    force, kw = case
    kw_jc = jc_kw(kw, 0.0)
    assume(kw_jc is not None)
    free = response.peak_response(force, **kw, restrain_freq_ratio=ratio, gap=1e9)
    gap = gap_fraction * free.max_displacement
    lumped = response.peak_response(
        force, **kw, restrain_freq_ratio=ratio, gap=gap, output_type=output_type
    )
    jc = response.peak_response_jc(
        force, **kw_jc, restrain_freq_ratio=ratio, gap=gap, output_type=output_type
    )
    np.testing.assert_allclose(jc.summary(), lumped.summary(), rtol=1e-12, atol=0)
    assert jc.free_decay_samples == lumped.free_decay_samples
    if output_type > 0:
        np.testing.assert_allclose(jc.history, lumped.history, rtol=1e-12, atol=0)


@SETTINGS
@given(case=lumped_cases())
def test_strategy_draws_small_cases(case):
    """Guard on the strategy itself: the examples stay small enough for both modes and
    always carry a load."""
    force, kw = case
    assert 10 <= len(force) <= 40
    assert 2 <= kw["step_qty"] <= 8
    assert kw["damping_percent"] > 0
    assert np.max(np.abs(force)) > 0 and force[0] == 0.0


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
