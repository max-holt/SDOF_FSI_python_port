"""Smoke tests: the package imports and each ported entry point runs on a small
synthetic input without error, returning finite values of the expected shape.

These are not oracles; the Excel golden fixtures are.
"""

import numpy as np
import pytest

import surge_sdof
from surge_sdof import legacy_port as lp


def test_package_imports():
    assert isinstance(surge_sdof.__version__, str)


# ---------------------------------------------------------------- GetPressureResponse
PRESSURE_KW = dict(
    closure_time=1.0,  # s
    celerity=1000.0,  # m/s
    density=1000.0,  # kg/m3
    time_step=0.005,  # s
    pressure_drop_from_pump=0.5,  # bar
    flow_rate=100.0,  # m3/h
    pipe_area=7850.0,  # mm^2 (DN100)
    valve_cv=500.0,
    length_to_pump=500.0,  # m
    pump_ramp_pressure=2.0,  # bar
)


def linear_closure(n=100):
    """Valve closure 0 -> 1 over n samples as a (n, 1) column."""
    return np.linspace(0.0, 1.0, n).reshape(n, 1)


def test_pressure_response_runs_and_has_expected_shape():
    res = lp.get_pressure_response(linear_closure(), **PRESSURE_KW)
    out_max = round(PRESSURE_KW["closure_time"] / PRESSURE_KW["time_step"])
    assert res.shape == (out_max + 1,)
    assert np.all(np.isfinite(res))
    # water hammer: the valve pressure rises above its initial value
    assert res.max() > res[0] > 0


def test_pressure_response_1d_input_matches_column_input():
    col = linear_closure()
    a = lp.get_pressure_response(col, **PRESSURE_KW)
    b = lp.get_pressure_response(col[:, 0], **PRESSURE_KW)
    np.testing.assert_array_equal(a, b)


def test_pressure_response_2d_pattern_runs():
    # 10 x 10 pattern, walked column-major (first index fastest)
    pat = np.linspace(0.0, 1.0, 100).reshape(10, 10, order="F")
    res = lp.get_pressure_response(pat, **PRESSURE_KW)
    assert np.all(np.isfinite(res))
    assert res.shape == (201,)


def test_pressure_response_short_pipe_limits_segments():
    kw = dict(PRESSURE_KW, length_to_pump=5.0)
    res = lp.get_pressure_response(linear_closure(), **kw)
    assert np.all(np.isfinite(res))


@pytest.mark.parametrize("n", [1, 2, 3, 7, 100, 101])
def test_pressure_response_pattern_lengths(n):
    res = lp.get_pressure_response(linear_closure(n), **PRESSURE_KW)
    assert np.all(np.isfinite(res))


# -------------------------------------------------------------------- GetPeakResponse
PEAK_KW = dict(
    step_qty=10,
    sample_freq=100.0,  # Hz
    physical_length=10.0,  # m
    flexural_rigidity_ei=2e5,  # N m^2
    celerity=1000.0,  # m/s
    mass_per_unit_len=10.0,  # kg/m
    damping_percent=2.0,
    dynamic_fric=0.3,
    nat_freq=5.0,  # Hz
)


def step_force(n=100, amplitude=1000.0):
    """100-sample step force as a (n, 1) column: 0 at the first sample, then amplitude."""
    f = np.full((n, 1), amplitude)
    f[0, 0] = 0.0
    return f


def expected_history_length(force, kw):
    ubsq = kw["physical_length"] / (kw["celerity"] / kw["sample_freq"])
    out_max = force.size + round(ubsq)
    return out_max * 2 + 1


# (physical_length, expected max unbalance force). The step rises over one sample, so
# the unbalance F(t) - F(t - L/c) only reaches the full step when the travel delay
# L/c is at least one sample: 10 m -> 1.0 sample, 12.5 m -> 1.25, 7 m -> 0.7 sample
# (kOverlap = 7 of stepQTY - 1 = 9 interpolation intervals), 0.5 m -> 0.05 sample
# (kOverlap rounds to 0 and the two force samples coincide).
@pytest.mark.parametrize(
    "physical_length, expected_fmax",
    [(10.0, 1000.0), (12.5, 1000.0), (7.0, 1000.0 * 7 / 9), (0.5, 0.0)],
)
def test_peak_response_runs_for_all_output_types(physical_length, expected_fmax):
    kw = dict(PEAK_KW, physical_length=physical_length)
    force = step_force()
    peaks = lp.get_peak_response(force, **kw, output_type=0)
    assert peaks.shape == (5,)
    assert np.all(np.isfinite(peaks))
    assert np.all(peaks >= 0)
    assert peaks[4] == pytest.approx(expected_fmax)  # max applied (unbalance) force
    for output_type in (1, 2, 3):
        hist = lp.get_peak_response(force, **kw, output_type=output_type)
        assert hist.shape == (expected_history_length(force, kw),)
        assert np.all(np.isfinite(hist))
        assert hist[0] == 0.0  # VBA 1-based: element 0 unused
        assert np.any(hist != 0.0) == (expected_fmax > 0)


def test_peak_response_history_peak_matches_summary():
    force = step_force()
    peaks = lp.get_peak_response(force, **PEAK_KW, output_type=0)
    x_hist = lp.get_peak_response(force, **PEAK_KW, output_type=1)
    # the per-sample history is a subsample of the per-step trajectory
    assert np.abs(x_hist).max() <= peaks[1] + 1e-15
    assert np.abs(x_hist).max() > 0.5 * peaks[1]


def test_peak_response_1d_input_matches_column_input():
    force = step_force()
    a = lp.get_peak_response(force, **PEAK_KW, output_type=1)
    b = lp.get_peak_response(force[:, 0], **PEAK_KW, output_type=1)
    np.testing.assert_array_equal(a, b)


def test_peak_response_2d_input_runs():
    force = step_force().reshape(10, 10, order="F")
    peaks = lp.get_peak_response(force, **PEAK_KW)
    assert np.all(np.isfinite(peaks))


def test_peak_response_step_qty_one_divides_by_zero():
    # D-7: k / (stepQTY - 1) with stepQTY = 1 (VBA error 11)
    with pytest.raises(ZeroDivisionError):
        lp.get_peak_response(step_force(), **dict(PEAK_KW, step_qty=1))


def test_peak_response_single_row_history_is_out_of_range():
    # D-8: a 1 x n (horizontal) forceHistory leaves iB = UBound(1) + 1 after the first
    # block and the second block indexes past the array (VBA error 9) whenever the first
    # k loop runs, i.e. kOverlap < stepQTY. With the fixed floor (D-1) an integer delay
    # gives kOverlap = 0, so it fails too (under the original floor an odd-integer delay
    # gave kOverlap = stepQTY and escaped).
    force = step_force().reshape(1, 100)
    for physical_length in (12.5, 10.0):
        with pytest.raises(IndexError):
            lp.get_peak_response(force, **dict(PEAK_KW, physical_length=physical_length))
    # only a fractional part that rounds kOverlap up to stepQTY skips that loop and lets
    # iB be re-based first: unballanceStepQTY = 1.96 -> kOverlap = CLng(9.6) = 10
    lp.get_peak_response(force, **dict(PEAK_KW, physical_length=19.6))


# ------------------------------------------------------------------ GetPeakResponseJC
JC_KW = dict(PEAK_KW, fluid_densty=1000.0, fluid_area=0.005)  # kg/m3, m^2 (5 kg/m fluid)


@pytest.mark.parametrize("physical_length", [10.0, 12.5, 7.0])
def test_peak_response_jc_runs_for_all_output_types(physical_length):
    kw = dict(JC_KW, physical_length=physical_length)
    force = step_force()
    peaks = lp.get_peak_response_jc(force, **kw, output_type=0)
    assert peaks.shape == (5,)
    assert np.all(np.isfinite(peaks))
    assert np.all(peaks >= 0)
    for output_type in (1, 2, 3):
        hist = lp.get_peak_response_jc(force, **kw, output_type=output_type)
        assert hist.shape == (expected_history_length(force, kw),)
        assert np.all(np.isfinite(hist))
        assert hist[0] == 0.0
        assert np.any(hist != 0.0)


def test_peak_response_jc_short_pipe_falls_back_to_lumped_mass():
    # pipeSegQTY - 2 * pivotSegQTY <= 2 -> GetPeakResponse with the same arguments
    force = step_force()
    for output_type in (0, 1):
        kw = dict(JC_KW, physical_length=1.0)
        jc = lp.get_peak_response_jc(force, **kw, output_type=output_type)
        lumped = lp.get_peak_response(
            force,
            **{k: v for k, v in kw.items() if not k.startswith("fluid")},
            output_type=output_type,
        )
        np.testing.assert_array_equal(jc, lumped)


def test_peak_response_jc_fluid_coupling_changes_the_answer():
    force = step_force()
    with_fluid = lp.get_peak_response_jc(force, **JC_KW)
    without = lp.get_peak_response_jc(force, **dict(JC_KW, fluid_area=0.0))
    assert with_fluid[1] != without[1]
    assert with_fluid[4] == without[4] == pytest.approx(1000.0)


def test_peak_response_jc_1d_input_matches_column_input():
    force = step_force()
    a = lp.get_peak_response_jc(force, **JC_KW, output_type=1)
    b = lp.get_peak_response_jc(force[:, 0], **JC_KW, output_type=1)
    np.testing.assert_array_equal(a, b)


def test_peak_response_jc_runtime_errors_are_raised():
    # D-9: the VBA `On Error GoTo ErrFound` returned an uninitialised array; Python raises.
    force = step_force()
    with pytest.raises(ZeroDivisionError):  # D-7 inside the guarded region
        lp.get_peak_response_jc(force, **dict(JC_KW, step_qty=1))
    with pytest.raises((ZeroDivisionError, FloatingPointError)):  # rhoC = 0
        lp.get_peak_response_jc(force, **dict(JC_KW, fluid_densty=0.0))
    with pytest.raises(IndexError):  # D-8 inside the guarded region
        lp.get_peak_response_jc(force.reshape(1, 100), **dict(JC_KW, physical_length=12.5))
