"""Unit tests for the VBA-semantics helpers against the VBA definitions.

Reference definitions (legacy/vba/Existing Code.bas):
    CLng          -> round half to even
    floor(val)    = max(CLng(val - 0.5), CLng(val + 0.5) - 1)   (fixed, commit da022b8)
    modDbl(n, d)  = n - (floor(CDbl(n) / CDbl(d)) * d)
    sign(val, lim): 1 if val > lim, -1 if val < -lim, else 0
    minUnsigned / maxUnsigned: see lines 19-49
"""

import math
import random

import numpy as np
import pytest

from surge_sdof.vba_compat import (
    clng,
    max_unsigned,
    min_unsigned,
    mod_dbl,
    sign,
    ubound,
    vba_2d,
    vba_floor,
)


def _clng_reference(x):
    """Independent round-half-to-even built from floor/ceil."""
    f = math.floor(x)
    diff = x - f
    if diff < 0.5:
        return f
    if diff > 0.5:
        return f + 1
    return f if f % 2 == 0 else f + 1


@pytest.mark.parametrize(
    "x, expected",
    [
        (0.0, 0),
        (0.5, 0),
        (1.5, 2),
        (2.5, 2),
        (3.5, 4),
        (-0.5, 0),
        (-1.5, -2),
        (-2.5, -2),
        (2.4, 2),
        (2.6, 3),
        (-2.4, -2),
        (-2.6, -3),
        (7, 7),
        (1e6 + 0.5, 1000000),
    ],
)
def test_clng_half_to_even(x, expected):
    assert clng(x) == expected
    assert isinstance(clng(x), int)


def test_clng_matches_reference_on_random_values():
    rng = random.Random(1234)
    for _ in range(5000):
        x = rng.uniform(-1e4, 1e4)
        assert clng(x) == _clng_reference(x)
    # exact .5 ties on a grid
    for k in range(-50, 51):
        x = k + 0.5
        assert clng(x) == _clng_reference(x)


def test_clng_accepts_numpy_scalars():
    assert clng(np.float64(2.5)) == 2
    assert clng(np.int64(3)) == 3


def _vba_floor_literal(val):
    """Literal transcription of the lead author's fixed VBA floor (line 98):
    floor = max(CLng(val - 0.5), CLng(val + 0.5) - 1)"""
    return max(clng(val - 0.5), clng(val + 0.5) - 1)


@pytest.mark.parametrize(
    "val",
    [
        # exact even integers
        0.0,
        2.0,
        4.0,
        400.0,
        -2.0,
        -4.0,
        # exact odd integers (one too low under the original CLng(val - 0.5))
        1.0,
        3.0,
        5.0,
        7.0,
        -1.0,
        -3.0,
        # fractional part < 0.5
        4.3,
        5.0001,
        0.49,
        0.1,
        -0.3,
        -1.2,
        -5.9999,
        # fractional part = 0.5 (CLng ties)
        4.5,
        5.5,
        0.5,
        -0.5,
        -1.5,
        -2.5,
        # fractional part > 0.5
        4.7,
        4.9999,
        0.51,
        0.9,
        -0.7,
        -1.8,
        -4.0001,
    ],
)
def test_vba_floor(val):
    assert vba_floor(val) == _vba_floor_literal(val)
    assert vba_floor(val) == math.floor(val)
    assert isinstance(vba_floor(val), int)


def test_vba_floor_is_a_true_floor_on_all_integers():
    for n in range(-21, 22):
        assert vba_floor(float(n)) == n
        assert _vba_floor_literal(float(n)) == n


def test_vba_floor_matches_math_floor_and_vba_on_random_values():
    rng = random.Random(99)
    for _ in range(5000):
        x = rng.uniform(-1e3, 1e3)
        assert vba_floor(x) == math.floor(x)
        assert vba_floor(x) == _vba_floor_literal(x)
    # exact .5 ties and exact integers on a grid
    for k in range(-50, 51):
        for x in (k + 0.5, float(k)):
            assert vba_floor(x) == math.floor(x)
            assert vba_floor(x) == _vba_floor_literal(x)


@pytest.mark.parametrize(
    "num, div, expected",
    [
        # regular cases
        (7, 2, 1.0),
        (5, 2, 1.0),
        (1, 2, 1.0),
        (0, 2, 0.0),
        (4, 2, 0.0),
        (8, 2, 0.0),
        (5.5, 2, 1.5),
        (10, 5, 0.0),
        (13, 5, 3.0),
        # quotient is an exact odd integer: result is div, not 0 (floor bug)
        (2, 2, 2.0),
        (6, 2, 2.0),
        (15, 5, 5.0),
        (3, 3, 3.0),
    ],
)
def test_mod_dbl(num, div, expected):
    assert mod_dbl(num, div) == expected


def test_mod_dbl_parity_test_is_true_only_for_multiples_of_four():
    """`modDbl(n, 2) = 0` in the VBA is true iff n % 4 == 0."""
    for n in range(0, 200):
        assert (mod_dbl(n, 2) == 0) == (n % 4 == 0)


@pytest.mark.parametrize(
    "val, lim, expected",
    [
        (5.0, 0.0, 1.0),
        (-5.0, 0.0, -1.0),
        (0.0, 0.0, 0.0),
        (1e-300, 0.0, 1.0),
        (0.5e-6, 1e-6, 0.0),
        (-0.5e-6, 1e-6, 0.0),
        (2e-6, 1e-6, 1.0),
        (-2e-6, 1e-6, -1.0),
        (1e-6, 1e-6, 0.0),  # val > lim is strict
        (-1e-6, 1e-6, 0.0),
    ],
)
def test_sign(val, lim, expected):
    assert sign(val, lim) == expected
    assert isinstance(sign(val, lim), float)


def test_sign_default_lim_is_zero():
    assert sign(3.0) == 1.0
    assert sign(-3.0) == -1.0
    assert sign(0.0) == 0.0


@pytest.mark.parametrize(
    "a, b, expected",
    [
        (2.0, 3.0, 2.0),
        (3.0, 2.0, 2.0),
        (2.0, -3.0, -2.0),  # |a|<|b|, b != 0 -> a * sign(b)
        (-3.0, 2.0, -2.0),  # |a|>=|b|, a != 0 -> b * sign(a)
        (-2.0, 3.0, -2.0),  # |a|<|b|, b != 0 -> a * sign(b) = -2 * 1
        (3.0, -2.0, -2.0),
        (0.0, 5.0, 0.0),  # |a|<|b|, b != 0 -> 0 * 1
        (5.0, 0.0, 0.0),  # else branch, a != 0 -> 0 * sign(5)
        (0.0, 0.0, 0.0),  # else branch, a == 0 -> b
        (2.0, 2.0, 2.0),  # tie: else branch -> b * sign(a)
        (2.0, -2.0, -2.0),  # tie: b * sign(a) = -2 * 1
        (1e9, 0.0025, 0.0025),  # the 'gap never engages' case
        (1e9, -0.0025, -0.0025),
    ],
)
def test_min_unsigned(a, b, expected):
    assert min_unsigned(a, b) == expected


@pytest.mark.parametrize(
    "a, b, expected",
    [
        (2.0, 3.0, 3.0),
        (3.0, 2.0, 3.0),
        (2.0, -3.0, -3.0),  # else branch, a != 0 -> b * sign(a)
        (-3.0, 2.0, -3.0),  # |a|>|b|, b != 0 -> a * sign(b)
        (-2.0, 3.0, -3.0),
        (3.0, -2.0, -3.0),
        (0.0, 5.0, 5.0),  # else branch, a == 0 -> b
        (5.0, 0.0, 5.0),  # |a|>|b|, b == 0 -> a
        (0.0, 0.0, 0.0),
        (2.0, 2.0, 2.0),  # tie: else branch -> b * sign(a)
        (-2.0, 2.0, -2.0),  # tie: 2 * sign(-2)
    ],
)
def test_max_unsigned(a, b, expected):
    assert max_unsigned(a, b) == expected


def test_min_max_unsigned_magnitude_property():
    rng = random.Random(7)
    for _ in range(2000):
        a = rng.uniform(-10, 10)
        b = rng.uniform(-10, 10)
        assert abs(min_unsigned(a, b)) == pytest.approx(min(abs(a), abs(b)))
        assert abs(max_unsigned(a, b)) == pytest.approx(max(abs(a), abs(b)))


def test_vba_2d_pads_leading_row_and_column():
    arr = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    out = vba_2d(arr)
    assert out.shape == (4, 3)
    assert ubound(out, 1) == 3
    assert ubound(out, 2) == 2
    assert out[1, 1] == 1.0 and out[1, 2] == 2.0
    assert out[3, 1] == 5.0 and out[3, 2] == 6.0
    assert np.all(out[0, :] == 0) and np.all(out[:, 0] == 0)
    # input untouched, output is float64
    assert arr[0, 0] == 1.0
    assert out.dtype == np.float64


def test_vba_2d_rejects_non_2d():
    with pytest.raises(ValueError):
        vba_2d(np.zeros(5))


def test_ubound_defaults_to_first_dimension():
    out = vba_2d(np.zeros((7, 1)))
    assert ubound(out) == 7
    assert ubound(out, 2) == 1
