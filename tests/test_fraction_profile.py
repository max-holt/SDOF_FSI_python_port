"""Approved fix F-4: the lead author's corrected interp-fraction profiles (DEVIATIONS D-4).

``moc.interp_fractions(..., fraction_profile="fixed")`` transcribes
``legacy/vba/interpFraction_fix_2026-10-26.bas``; ``"legacy"`` stays the original
``Existing Code.bas`` profile. The expected values below are computed from the VBA
expressions by hand, not from the Python.

Grid conventions (``moc`` module docstring): A nodes ``0 .. N``, B cells ``0 .. N - 1``,
interleaved ``A0 B0 A1 B1 ... B(N-1) A(N)`` at positions ``0 .. 2N`` (``trace.interleave``).
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest
import test_differential as td

from surge_sdof import coupling, moc, response
from surge_sdof.trace import interleave
from surge_sdof.viz import geometry

EXT = moc.EXT_QTY

# (pipeSegQTY, pivotSegQTY): the sweep's 20-45 cell grids and the golden sizes (546-666
# cells, pivot 27-87 per the differential tests), pivot 5 (no ramp cell) included
GRIDS = [
    (20, 5),
    (20, 6),
    (22, 7),
    (30, 8),
    (40, 8),
    (44, 12),
    (100, 27),
    (546, 50),
    (666, 87),
]


def fixed(pipe, pivot):
    return moc.interp_fractions(pipe, pivot, "fixed")


def legacy(pipe, pivot):
    return moc.interp_fractions(pipe, pivot, "legacy")


def ramp_cells(profile):
    """Indices of the cells strictly between 0 and 1, split at the run (the 1-block)."""
    ones = np.flatnonzero(profile == 1.0)
    inlet = np.flatnonzero((profile[: ones[0]] > 0) & (profile[: ones[0]] < 1))
    tail = profile[ones[-1] + 1 :]
    outlet = ones[-1] + 1 + np.flatnonzero((tail > 0) & (tail < 1))
    return inlet, outlet


# ------------------------------------------------------------------ the fixed profile


def test_default_profile_is_fixed():
    """F-4 is on by default in the tabulation, the coupling and the solver."""
    pipe, pivot = 30, 8
    assert moc.interp_fractions.__defaults__ == ("fixed",)
    assert inspect.signature(coupling.JunctionCoupling).parameters["fraction_profile"].default == (
        "fixed"
    )
    assert inspect.signature(response.peak_response_jc).parameters["fraction_profile"].default == (
        "fixed"
    )
    fa, fb = moc.interp_fractions(pipe, pivot)
    xa, xb = fixed(pipe, pivot)
    assert np.array_equal(fa, xa) and np.array_equal(fb, xb)
    assert td.FIXED_FLAGS["fraction_profile"] == "fixed"
    assert td.LEGACY_FLAGS["fraction_profile"] == "legacy"


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError, match="fraction_profile"):
        moc.interp_fractions(30, 8, "corrected")
    _id, force, kw = td.JC_SMALL[0]
    with pytest.raises(ValueError, match="fraction_profile"):
        response.peak_response_jc(force, **kw, fraction_profile="corrected")


def test_table_pivot_8_pipe_30():
    """Hand-computed from the VBA with ``extQTY = 4``, ``pivotSegQTY - extQTY = 4``.

    A: ``n + 1 < 4.5`` -> 0 for n <= 3; ``n + 1 < 8`` -> ((n - 3.5) / 4)^2 for n = 4, 5, 6;
    ``n + 1 > 26.5`` -> 0 for n >= 26; ``n + 1 > 23`` -> ((25.5 - n) / 4)^2 for n = 23, 24,
    25; 1 for n = 7 .. 22.
    B: 0 for n <= 3; ``n + 1 < 8`` -> ((n - 3) / 4)^2 for n = 4, 5, 6; ``n + 1 > 25.5`` ->
    0 for n >= 25; ``n + 1 > 22.5`` -> ((25 - n) / 4)^2 for n = 22, 23, 24; 1 for
    n = 7 .. 21."""
    fa, fb = fixed(30, 8)
    expected_a = [0.0] * 4 + [1 / 64, 9 / 64, 25 / 64] + [1.0] * 16 + [25 / 64, 9 / 64, 1 / 64]
    expected_a += [0.0] * 5
    expected_b = [0.0] * 4 + [1 / 16, 1 / 4, 9 / 16] + [1.0] * 15 + [9 / 16, 1 / 4, 1 / 16]
    expected_b += [0.0] * 5
    assert len(expected_a) == 31 and len(expected_b) == 30
    assert fa.tolist() == expected_a
    assert fb.tolist() == expected_b
    # the per-node functions are what the table tabulates (node 0 and N of A included)
    assert [moc.interp_fraction_a_fixed(n, 8, 30) for n in range(31)] == expected_a
    assert [moc.interp_fraction_b_fixed(n, 8, 30) for n in range(30)] == expected_b
    # the legacy profile on the same grid: the D-4 cell and the duplicated A value
    la, lb = legacy(30, 8)
    assert lb[3] == 1 / 16 and la[4] == la[5] == 1 / 64


@pytest.mark.parametrize("pipe, pivot", GRIDS)
def test_fixed_profile_is_within_0_1(pipe, pivot):
    for f in fixed(pipe, pivot):
        assert np.all(f >= 0.0) and np.all(f <= 1.0)
        assert f[0] == 0.0 and f[-1] == 0.0
        assert np.any(f == 1.0)


@pytest.mark.parametrize("pipe, pivot", GRIDS)
def test_fixed_ramps_are_strictly_monotone(pipe, pivot):
    """Each leg is one strictly increasing (inlet) / decreasing (outlet) squared ramp from
    the zero block to the run; ``pivot - 5`` cells per leg per profile."""
    fa, fb = fixed(pipe, pivot)
    for f in (fa, fb, interleave(fa, fb)):
        inlet, outlet = ramp_cells(f)
        assert np.all(np.diff(f[inlet]) > 0) if inlet.size > 1 else True
        assert np.all(np.diff(f[outlet]) < 0) if outlet.size > 1 else True
        # contiguous: zero block, ramp, run, ramp, zero block
        assert np.all(np.diff(inlet) == 1) and np.all(np.diff(outlet) == 1)
        zeros = np.flatnonzero(f == 0.0)
        ones = np.flatnonzero(f == 1.0)
        first = inlet[0] if inlet.size else ones[0]
        last = outlet[-1] if outlet.size else ones[-1]
        assert np.all((zeros < first) | (zeros > last))
    assert ramp_cells(fa)[0].size == ramp_cells(fb)[0].size == pivot - 5


@pytest.mark.parametrize("pipe, pivot", GRIDS)
def test_fixed_legs_have_the_same_length(pipe, pivot):
    fa, fb = fixed(pipe, pivot)
    for f in (fa, fb):
        inlet, outlet = ramp_cells(f)
        assert inlet.size == outlet.size
    # as the viewer lays it out (geometry._segments on the interleaved profile): equal legs
    # and no moving cell on the horizontal inlet
    inter = interleave(fa, fb)
    inlet_end, run_start, run_end, outlet_start = geometry._segments(inter)
    assert run_start - inlet_end - 1 == outlet_start - run_end - 1 == 2 * pivot - 10
    assert np.all(inter[: inlet_end + 1] == 0.0)
    # the legacy layout (pivot >= 6; at pivot 5 the D-4 cell B(3) is already 1): the legs
    # differ by one cell, and the stray D-4 cell B(3) (position 7) is a moving cell on the
    # horizontal inlet, before the last zero B(4) (position 9)
    if pivot >= 6:
        la, lb = legacy(pipe, pivot)
        inter_l = interleave(la, lb)
        inlet_end, run_start, run_end, outlet_start = geometry._segments(inter_l)
        assert (run_start - inlet_end - 1) - (outlet_start - run_end - 1) == 1
        assert inlet_end == 9 and inter_l[7] == lb[3] != 0.0 and inter_l[9] == lb[4] == 0.0


@pytest.mark.parametrize("pipe, pivot", GRIDS)
def test_fixed_profiles_mirror_about_position_n_minus_1(pipe, pivot):
    """A(n) = A(N - 1 - n), B(n) = B(N - 2 - n): both profiles mirror about interleaved
    position N - 1, the centre of the lead author's ``n = 0 .. pipeSegQTY - 1`` nodes
    (the geometric centre of the N + 1 A nodes is position N, half a MoC cell further;
    NOTES.md F-4 "for the lead author"). The legacy profiles mirror about position N."""
    n_seg = pipe
    fa, fb = fixed(pipe, pivot)
    assert np.array_equal(fa[:n_seg], fa[:n_seg][::-1])  # A0 .. A(N-1)
    assert np.array_equal(fb[: n_seg - 1], fb[: n_seg - 1][::-1])  # B0 .. B(N-2)
    inter = interleave(fa, fb)
    assert np.array_equal(inter[: 2 * n_seg - 1], inter[: 2 * n_seg - 1][::-1])
    # the half-cell offset: the inlet zero block is 8 interleaved cells, the outlet 10
    zeros = np.flatnonzero(inter == 0.0)
    assert zeros[:8].tolist() == list(range(8)) and inter[8] != 0.0
    assert zeros[-10:].tolist() == list(range(2 * n_seg - 9, 2 * n_seg + 1))
    assert fa[4] != 0.0 and fa[n_seg - 4] == 0.0
    # legacy: A mirrors about position N (A(n) = A(N - n)); B does not mirror at all (its
    # inlet ramp runs n = 3 .. pivot - 1, the outlet ramp n = N - pivot + 1 .. N - 4)
    la, lb = legacy(pipe, pivot)
    assert np.array_equal(la, la[::-1])
    assert not np.array_equal(lb, lb[::-1]) and not np.array_equal(lb[:-1], lb[:-1][::-1])


@pytest.mark.parametrize("pipe, pivot", GRIDS)
def test_fixed_b_is_zero_at_n_3_and_legacy_is_not(pipe, pivot):
    fa, fb = fixed(pipe, pivot)
    la, lb = legacy(pipe, pivot)
    assert fb[3] == 0.0 and fa[3] == 0.0
    assert moc.interp_fraction_b_fixed(3, pivot, pipe) == 0.0
    assert lb[3] == ((3 - EXT) / (pivot - EXT)) ** 2 != 0.0  # D-4 on the legacy path
    assert np.array_equal(la, fa) is False and np.array_equal(lb, fb) is False


def test_pivot_4_is_a_value_error_on_the_fixed_path_and_d4_on_the_legacy_path():
    """The corrected expressions never reach the ramp at ``pivotSegQTY = 4`` (the zero
    test covers ``n <= 3``), so they would return a 0 -> 1 step without dividing; the port
    refuses the grid instead (added guard: the ramp needs ``pivot > ext``)."""
    for n in range(20):
        moc.interp_fraction_a_fixed(n, 4, 20)
        moc.interp_fraction_b_fixed(n, 4, 20)
    with pytest.raises(ValueError, match="pivot > ext"):
        moc.interp_fractions(20, 4, "fixed")
    with pytest.raises(ValueError, match="pivot > ext"):
        coupling.JunctionCoupling(20, 4, 1e-4, 1e6, 0.01, 1.01, fraction_profile="fixed")
    with pytest.raises(ZeroDivisionError):  # D-4
        moc.interp_fractions(20, 4, "legacy")
    with pytest.raises(ZeroDivisionError):
        coupling.JunctionCoupling(20, 4, 1e-4, 1e6, 0.01, 1.01, fraction_profile="legacy")
    # pivot 5: no ramp cell, a 0 -> 1 step, valid on both paths
    fa, fb = fixed(20, 5)
    assert ramp_cells(fa)[0].size == 0 and fa[3] == 0.0 and fa[4] == 1.0
    assert fb[3] == 0.0 and fb[4] == 1.0


def test_display_profile_survives_pivot_4_on_both_paths(monkeypatch):
    frac_a, frac_b = geometry._interp_fractions_display(20, 4)
    assert frac_a.shape == (21,) and frac_b.shape == (20,)
    assert np.all(frac_b[:EXT] == 0) and frac_b[10] == 1.0


# ------------------------------------------------------------------ the solver flag


def test_fraction_profile_flag_reaches_the_coupling_and_the_trace():
    _id, force, kw = td.JC_SMALL[0]
    sig = inspect.signature(response.peak_response_jc).parameters["fraction_profile"]
    assert sig.kind is inspect.Parameter.KEYWORD_ONLY
    for profile in moc.FRACTION_PROFILES:
        res = response.peak_response_jc(
            force, **kw, trace_every=1, **dict(td.LEGACY_FLAGS, fraction_profile=profile)
        )
        fa, fb = moc.interp_fractions(res.trace.pipe_seg_qty, res.trace.pivot_seg_qty, profile)
        assert np.array_equal(res.trace.moving_fraction, interleave(fa, fb))
        assert res.trace.inputs["fraction_profile"] == profile


def test_fixed_profile_changes_a_fluid_coupled_run_and_nothing_else():
    """On a fluid-coupled MoC case the corrected profile changes the result; with no fluid
    (``dF = 0``) or in the short-pipe fallback it cannot act."""
    _id, force, kw = td.JC_SMALL[0]
    assert kw["fluid_area"] > 0
    base = response.peak_response_jc(force, **kw, **td.LEGACY_FLAGS).summary()
    f4 = response.peak_response_jc(
        force, **kw, **dict(td.LEGACY_FLAGS, fraction_profile="fixed")
    ).summary()
    assert not np.array_equal(base, f4)
    assert td._max_rel_change(f4, base) < 1e-1  # a correction, not a different answer
    for kw2 in (dict(kw, fluid_area=0.0), dict(kw, physical_length=1.0)):
        base = response.peak_response_jc(force, **kw2, **td.LEGACY_FLAGS).summary()
        f4 = response.peak_response_jc(
            force, **kw2, **dict(td.LEGACY_FLAGS, fraction_profile="fixed")
        ).summary()
        assert np.array_equal(base, f4)
