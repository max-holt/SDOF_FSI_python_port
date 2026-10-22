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

import functools

import numpy as np
import pytest

from surge_sdof import legacy_port as lp

PI_VBA = 3.14159265358979

BASE_KW = {
    "step_qty": 10,
    "sample_freq": 100.0,
    "physical_length": 10.0,
    "flexural_rigidity_ei": 2e5,
    "celerity": 1000.0,
    "mass_per_unit_len": 10.0,
    "damping_percent": 2.0,
    "dynamic_fric": 0.3,
    "nat_freq": 5.0,
}


def step_force(n=100, amplitude=1000.0):
    f = np.full((n, 1), amplitude)
    f[0, 0] = 0.0
    return f


jc_with_fluid = functools.partial(lp.get_peak_response_jc, fluid_densty=1000.0, fluid_area=0.005)
jc_with_fluid.__name__ = "get_peak_response_jc"

PEAK_FUNCS = [lp.get_peak_response, jc_with_fluid]


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
    kw = {
        "step_qty": 100,  # fine step: see module docstring
        "sample_freq": 100.0,
        "physical_length": 4003.0,  # unballanceStepQTY = 400.3 samples
        "flexural_rigidity_ei": 1e-6,  # portal frame height negligible: mass = L * m'
        "celerity": 1000.0,
        "mass_per_unit_len": 10.0,
        "damping_percent": 0.0,
        "dynamic_fric": 0.0,
        "nat_freq": 2.5,  # period = 40 samples
    }
    amplitude = 1e5
    force = step_force(100, amplitude)
    stiffness = (2 * PI_VBA * kw["nat_freq"]) ** 2 * kw["physical_length"] * kw["mass_per_unit_len"]
    return kw, force, amplitude / stiffness


def test_undamped_constant_force_oscillates_about_static_deflection():
    # Lumped solver only: with a negligible portal frame height the JC variant has
    # pivotSegQTY = extQTY and interpFractionB(3) divides by zero (D-4), as in the VBA.
    func = lp.get_peak_response
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


@pytest.mark.parametrize("output_type", [0, 1, 2, 3])
def test_jc_without_fluid_area_is_identical_to_lumped_mass(output_type):
    """With fluidArea = 0 the JC force dF stays exactly 0 and the mass, stiffness,
    damping and friction formulas reduce to the lumped ones, so the two integrators
    must agree bit for bit (the MoC still runs but cannot feed back)."""
    force = step_force()
    kw = dict(BASE_KW, damping_percent=0.0, dynamic_fric=0.0)
    lumped = lp.get_peak_response(force, **kw, gap=1e9, output_type=output_type)
    jc = lp.get_peak_response_jc(
        force, **kw, fluid_densty=1000.0, fluid_area=0.0, gap=1e9, output_type=output_type
    )
    np.testing.assert_array_equal(jc, lumped)


def test_2d_inputs_are_walked_column_major():
    """D-10: a 2-D forceHistory / valvePattern is flattened first-index-fastest."""
    flat = step_force()[:, 0]
    as_f = flat.reshape(10, 10, order="F")  # column-major: as_f[i, j] = flat[i + 10 j]
    for func, kw in ((lp.get_peak_response, BASE_KW), (jc_with_fluid, BASE_KW)):
        for output_type in (0, 1):
            a = func(flat, **kw, output_type=output_type)
            b = func(as_f, **kw, output_type=output_type)
            np.testing.assert_array_equal(a, b)
    # Valve pattern: exact binary fractions so the identity is exact.
    closure = np.minimum(np.arange(100), 80) / 128.0
    a = lp.get_pressure_response(closure, **PRESSURE_KW)
    b = lp.get_pressure_response(closure.reshape(10, 10, order="F"), **PRESSURE_KW)
    np.testing.assert_array_equal(a, b)
    # and the row-major reshape is a different pattern
    c = lp.get_pressure_response(closure.reshape(10, 10, order="C"), **PRESSURE_KW)
    assert not np.array_equal(a, c)


PRESSURE_KW = {
    "closure_time": 1.0,
    "celerity": 1000.0,
    "density": 1000.0,
    "time_step": 0.005,  # factor * 2 = 1: loop index totInd is the pattern position p
    "pressure_drop_from_pump": 0.5,
    "flow_rate": 100.0,
    "pipe_area": 7850.0,
    "valve_cv": 500.0,
    "length_to_pump": 500.0,
    "pump_ramp_pressure": 2.0,
}


def test_pressure_response_multicolumn_pattern_matches_single_column():
    """D-11 (fixed): under the original floor a 10 x 10 pattern read the *last* pattern
    value early at position p = 91 (floor(91) = 90, modDbl(90, 10) = 10 -> i = 11 ->
    clamped to (10, 10)), so a valve that closes only at the final sample briefly closed
    at p = 91 too. With the fixed floor the index pair is consistent at every p and the
    multi-column result is exactly the single-column one, spike included."""
    spike = np.zeros(100)
    spike[99] = 1.0
    one_col = lp.get_pressure_response(spike, **PRESSURE_KW)
    ten_cols = lp.get_pressure_response(spike.reshape(10, 10, order="F"), **PRESSURE_KW)
    np.testing.assert_array_equal(one_col, ten_cols)
    # the closing sample does change the response, so the equality is not vacuous
    never_closes = lp.get_pressure_response(np.zeros(100), **PRESSURE_KW)
    assert not np.array_equal(one_col, never_closes)
