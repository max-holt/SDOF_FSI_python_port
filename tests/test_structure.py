"""Structural sanity checks on the peak-response integrators.

These are consistency checks, not oracles: the Excel golden fixtures are the oracle.

1. gap = 0 with restrainFreqRatio = 1 must be bit-identical to gap = 1e9 (the support
   clamp never engages in either case, and the restoring term reduces to x * stiffness).
2. With no damping and no friction, a constant unbalance force drives an undamped
   oscillation about the static deflection F / k: the peak-mean (max + min) / 2 of the
   displacement over the forced phase must be F / k within 1 %.

   Note: the VBA integrator evaluates aNew from the *old* x and v, so it is an explicit
   scheme whose undamped amplitude grows slowly (about 2.5 % per cycle at
   omega * dt = 0.016, i.e. stepQTY = 10 here). The cycle time-mean stays at F / k to
   1e-4 but the peak-mean drifts, so this check integrates with stepQTY = 100
   (omega * dt = 0.0016, growth 0.03 % per cycle). This is a property of the VBA scheme
   that Stage 1 preserves; see NOTES.md.
"""

import numpy as np
import pytest

from surge_sdof import legacy_port as lp

PI_VBA = 3.14159265358979

BASE_KW = dict(
    step_qty=10,
    sample_freq=100.0,
    physical_length=10.0,
    flexural_rigidity_ei=2e5,
    celerity=1000.0,
    mass_per_unit_len=10.0,
    damping_percent=2.0,
    dynamic_fric=0.3,
    nat_freq=5.0,
)


def step_force(n=100, amplitude=1000.0):
    f = np.full((n, 1), amplitude)
    f[0, 0] = 0.0
    return f


PEAK_FUNCS = [lp.get_peak_response]


@pytest.mark.parametrize("func", PEAK_FUNCS)
@pytest.mark.parametrize("output_type", [0, 1, 2, 3])
def test_gap_zero_ratio_one_equals_huge_gap(func, output_type):
    force = step_force()
    ref = func(force, **BASE_KW, restrain_freq_ratio=1, gap=1e9, output_type=output_type)
    same = func(force, **BASE_KW, restrain_freq_ratio=1, gap=0, output_type=output_type)
    np.testing.assert_array_equal(same, ref)
    # with a huge gap the clamp never engages, so the ratio is irrelevant
    ratio = func(force, **BASE_KW, restrain_freq_ratio=3, gap=1e9, output_type=output_type)
    np.testing.assert_array_equal(ratio, ref)
    assert np.any(ref != 0)


@pytest.mark.parametrize("func", PEAK_FUNCS)
def test_engaged_gap_changes_the_answer(func):
    force = step_force()
    ref = func(force, **BASE_KW, restrain_freq_ratio=1, gap=1e9)
    x_max = ref[1]
    engaged = func(force, **BASE_KW, restrain_freq_ratio=3, gap=0.5 * x_max)
    assert engaged[1] < x_max


def static_case():
    """Long pipe so the first (unbalance) block is a long constant-force phase."""
    kw = dict(
        step_qty=100,  # fine step: see module docstring
        sample_freq=100.0,
        physical_length=4003.0,  # unballanceStepQTY = 400.3 samples
        flexural_rigidity_ei=1e-6,  # portal frame height negligible: mass = L * m'
        celerity=1000.0,
        mass_per_unit_len=10.0,
        damping_percent=0.0,
        dynamic_fric=0.0,
        nat_freq=2.5,  # period = 40 samples
    )
    amplitude = 1e5
    force = step_force(100, amplitude)
    stiffness = (2 * PI_VBA * kw["nat_freq"]) ** 2 * kw["physical_length"] * kw["mass_per_unit_len"]
    return kw, force, amplitude / stiffness


@pytest.mark.parametrize("func", PEAK_FUNCS)
def test_undamped_constant_force_oscillates_about_static_deflection(func):
    kw, force, x_static = static_case()
    hist = func(force, **kw, restrain_freq_ratio=1, gap=1e9, output_type=1)
    # forced phase: samples 1..401 carry unbalance forceA - forceB = 0 - F = -F;
    # skip the first natural period (40 samples)
    xs = hist[41:401]
    peak_mean = (xs.max() + xs.min()) / 2
    assert abs(peak_mean) == pytest.approx(x_static, rel=0.01)
    # the time-mean over whole cycles (9 x 40 samples) is a tighter check
    assert abs(xs.mean()) == pytest.approx(x_static, rel=1e-3)
    # undamped from rest: swings between ~0 and ~-2 F / k (slow explicit-scheme growth)
    assert xs.max() <= 0.05 * x_static
    assert abs(xs.min()) == pytest.approx(2 * x_static, rel=0.05)
    # the summary's static-equivalent force is consistent with the same stiffness
    peaks = func(force, **kw, restrain_freq_ratio=1, gap=1e9, output_type=0)
    stiffness = 1e5 / x_static
    assert peaks[0] / peaks[1] == pytest.approx(stiffness, rel=1e-3)
