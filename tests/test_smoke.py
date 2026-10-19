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
