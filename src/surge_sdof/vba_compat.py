"""Small helpers that reproduce VBA runtime semantics for the Stage 1 literal port.

Each helper mirrors one VBA construct or one helper ``Function`` from
``legacy/vba/Existing Code.bas``. They are deliberately tiny and un-optimised; the
only goal is that ``legacy_port.py`` can be read side by side with the VBA.

Array convention (see also the header of ``legacy_port.py``)
------------------------------------------------------------
VBA arrays declared ``(1 To n)`` are stored as numpy arrays of length ``n + 1`` with
index 0 unused, so VBA index values can be used unchanged. ``ubound(arr, dim)``
returns ``shape[dim - 1] - 1`` for such padded arrays, i.e. the VBA ``UBound``.
"""

import math

import numpy as np

__all__ = [
    "clng",
    "vba_floor",
    "mod_dbl",
    "sign",
    "min_unsigned",
    "max_unsigned",
    "ubound",
    "vba_2d",
]


def clng(x):
    """VBA ``CLng``: round to nearest integer, ties to even (banker's rounding).

    Python's built-in ``round`` with no ``ndigits`` implements exactly this on the
    binary value of the double, which is what the VBA runtime does.
    """
    return int(round(float(x)))


def vba_floor(val):
    """VBA ``floor`` (lead author's fixed version, ``legacy/vba`` commit da022b8)::

        floor = max(CLng(val - 0.5), CLng(val + 0.5) - 1)

    That expression is a true mathematical floor for every finite double (within the
    VBA ``Long`` range, where ``val +/- 0.5`` is exact): for a non-integer ``n + f``
    both operands equal ``n``; for an exact integer ``n`` half-to-even rounding makes
    exactly one of the two operands ``n - 1`` and the other ``n``, and ``max`` picks
    ``n``. It is therefore implemented as ``math.floor`` and returns an ``int``.

    The original VBA ``CLng(val - 0.5)`` was one too low for exact odd integers
    (``floor(5.0) = 4``); see DEVIATIONS.md D-1 (fixed). ``tests/test_vba_compat.py``
    pins this function against the literal transcription of the fixed VBA.
    """
    # D-1 fixed: true floor
    return math.floor(val)


def mod_dbl(num, div):
    """VBA ``modDbl``: ``num - (floor(CDbl(num) / CDbl(div)) * div)``.

    With the fixed ``floor`` this is the ordinary floored modulo
    (``modDbl(6, 2) = 0``, ``modDbl(7, 2) = 1``). The original VBA ``floor`` made it
    return ``div`` instead of 0 whenever ``num / div`` was an exact odd integer; see
    DEVIATIONS.md D-2 (fixed).
    """
    return num - (vba_floor(float(num) / float(div)) * div)


def sign(val, lim=0.0):
    """VBA ``sign(val As Double, Optional lim As Double = 0) As Double``.

    Returns 1 if ``val > lim``, -1 if ``val < -lim``, else 0 (as a float).
    """
    if val > lim:
        return 1.0
    elif val < -lim:
        return -1.0
    else:
        return 0.0


def min_unsigned(value_a, value_b):
    """VBA ``minUnsigned``: the smaller magnitude, signed by the product of both signs.

    Literal transcription of the VBA ``If`` ladder, including the zero special cases.
    """
    if abs(value_a) < abs(value_b):
        if value_b == 0:
            return value_a
        else:
            return value_a * sign(float(value_b))
    else:
        if value_a == 0:
            return value_b
        else:
            return value_b * sign(float(value_a))


def max_unsigned(value_a, value_b):
    """VBA ``maxUnsigned``: the larger magnitude, signed by the product of both signs.

    Literal transcription of the VBA ``If`` ladder, including the zero special cases.
    """
    if abs(value_a) > abs(value_b):
        if value_b == 0:
            return value_a
        else:
            return value_a * sign(float(value_b))
    else:
        if value_a == 0:
            return value_b
        else:
            return value_b * sign(float(value_a))


def ubound(arr, dim=1):
    """VBA ``UBound(arr, dim)`` for an array stored with the padded 1-based convention.

    ``dim`` is 1-based as in VBA. For an array produced by ``vba_2d`` (or any array
    whose index 0 is the unused pad) this is ``shape[dim - 1] - 1``.
    """
    return arr.shape[dim - 1] - 1


def vba_2d(arr):
    """Pad a 2-D numpy array so it can be indexed with VBA's 1-based ``(i, j)``.

    ``arr[i - 1, j - 1]`` in Python (0-based) becomes ``out[i, j]`` for
    ``1 <= i <= UBound(1)``, ``1 <= j <= UBound(2)``. Row 0 and column 0 of the result
    are unused and left at zero. The input is not modified; the result is float64.
    """
    arr = np.asarray(arr, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"vba_2d expects a 2-D array, got ndim={arr.ndim}")
    out = np.zeros((arr.shape[0] + 1, arr.shape[1] + 1), dtype=float)
    out[1:, 1:] = arr
    return out
