"""Tests for the ported VBA helper functions in legacy_port (not the entry points)."""

import numpy as np
import pytest

from surge_sdof import legacy_port as lp


def test_min_max_tie_returns_value_b():
    # VBA: If valueA < valueB Then min = valueA Else min = valueB
    assert lp.min(2, 3) == 2 and lp.min(3, 2) == 2
    assert lp.max(2, 3) == 3 and lp.max(3, 2) == 3
    # ties return valueB (observable through the type / signed zero)
    assert isinstance(lp.min(0, 0.0), float)
    assert isinstance(lp.max(0, 0.0), float)
    assert str(lp.max(0, -0.0)) == "-0.0"


def test_get_dimension():
    assert lp.get_dimension(np.zeros(3)) == 1
    assert lp.get_dimension(np.zeros((3, 2))) == 2
    assert lp.get_dimension(5.0) == 0


def test_add_dimension_builds_padded_column():
    out = lp.add_dimension(np.array([10.0, 20.0, 30.0]), 1, 1)
    assert out.shape == (4, 2)
    assert out[1, 1] == 10.0 and out[2, 1] == 20.0 and out[3, 1] == 30.0
    assert np.all(out[0, :] == 0) and np.all(out[:, 0] == 0)


def test_array_start_one_returns_empty_array():
    # D-3: the VBA assigns to the wrong name and returns an uninitialised array.
    out = lp.array_start_one(np.ones((3, 2)))
    assert out.shape == (0, 0)


@pytest.mark.parametrize("pivot, pipe", [(8, 40), (6, 20), (5, 18)])
def test_interp_fraction_a_profile(pivot, pipe):
    ext = 4
    f = [lp.interp_fraction_a(n, pivot, pipe) for n in range(pipe)]
    for n in range(ext):
        assert f[n] == 0.0
    for n in range(ext, pivot):
        assert f[n] == ((n - 0.5 - ext) / (pivot - ext)) ** 2
    for n in range(pivot, pipe - pivot + 1):
        assert f[n] == 1.0
    for n in range(pipe - pivot + 1, pipe - ext + 1):
        assert f[n] == ((pipe - 0.5 - ext - n) / (pivot - ext)) ** 2
    for n in range(pipe - ext + 1, pipe):
        assert f[n] == 0.0


@pytest.mark.parametrize("pivot, pipe", [(8, 40), (6, 20), (5, 18)])
def test_interp_fraction_b_profile(pivot, pipe):
    ext = 4
    f = [lp.interp_fraction_b(n, pivot, pipe) for n in range(pipe)]
    for n in range(3):
        assert f[n] == 0.0
    # D-4: n = 3 falls through to the ramp branch instead of returning 0
    assert f[3] == ((3 - ext) / (pivot - ext)) ** 2
    assert lp.interp_fraction_a(3, pivot, pipe) == 0.0
    for n in range(ext, pivot):
        assert f[n] == ((n - ext) / (pivot - ext)) ** 2
    for n in range(pivot, pipe - pivot + 1):
        assert f[n] == 1.0
    for n in range(pipe - pivot + 1, pipe - ext + 1):
        assert f[n] == ((pipe - 1 - ext - n) / (pivot - ext)) ** 2
    for n in range(pipe - ext + 1, pipe):
        assert f[n] == 0.0


def test_interp_fraction_minimal_pivot():
    # pivotSegQTY = extQTY = 4 makes the ramp denominators zero. In interpFractionA
    # the ramps are unreachable (n < pivot coincides with n < ext). In interpFractionB
    # the `n < 3` test (D-4) lets n = 3 reach the ramp and divide by zero, as in VBA.
    for n in range(40):
        lp.interp_fraction_a(n, 4, 40)
    for n in range(40):
        if n == 3:
            with pytest.raises(ZeroDivisionError):
                lp.interp_fraction_b(n, 4, 40)
        else:
            lp.interp_fraction_b(n, 4, 40)


@pytest.mark.parametrize(
    "var_a, var_b, var_c",
    [
        (-2433.0, 100.0, 13.3333),
        (-12 * 2e5 / (2 * 3.14159265358979 * 5) ** 2, 10 * 10.0, 10.0 * 4 / 3),
        (-1e-5, 40030.0, 20.0),
    ],
)
def test_solve_poly_finds_root(var_a, var_b, var_c):
    len_val = lp.solve_poly(var_a, var_b, var_c)
    assert len_val > 0
    residual = var_a + var_b * len_val**3 + var_c * len_val**4
    assert abs(residual / var_a) < 1e-6
