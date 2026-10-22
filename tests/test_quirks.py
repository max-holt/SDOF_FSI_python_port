"""Pinning tests for the DEVIATIONS.md rows D-12 … D-21 that no other test covers.

Each test asserts the behaviour the port *has today* on a small synthetic input, so that a
later refactor cannot change it silently. Where the quirk lives in a local variable that
the VBA never exposes (`vAv`, the interpolated sub-step force) the test reads the local
through a ``sys.settrace`` probe on the solver's own frame rather than by adding hooks
to ``legacy_port.py``; where it lives in a call to a module-level helper (``modDbl``,
``sign``) the helper is wrapped with ``monkeypatch``. Neither touches the solver source.

These are not oracles; the Excel golden fixtures are.
"""

import inspect
import sys
from contextlib import contextmanager

import numpy as np
import pytest

from surge_sdof import legacy_port as lp
from surge_sdof.vba_compat import clng

PEAK_KW = {
    "step_qty": 10,
    "sample_freq": 100.0,  # Hz
    "physical_length": 10.0,  # m -> unballanceStepQTY = 1.0 sample
    "flexural_rigidity_ei": 2e5,  # N m^2
    "celerity": 1000.0,  # m/s
    "mass_per_unit_len": 10.0,  # kg/m
    "damping_percent": 2.0,
    "dynamic_fric": 0.3,
    "nat_freq": 5.0,  # Hz
}
JC_KW = dict(PEAK_KW, fluid_densty=1000.0, fluid_area=0.005)
LUMPED_ONLY = {k: v for k, v in JC_KW.items() if not k.startswith("fluid")}


def step_force(n=100, amplitude=1000.0):
    f = np.full((n, 1), amplitude)
    f[0, 0] = 0.0
    return f


def ramp_force(n=100, slope=1e6):
    """F = slope * t over n samples at 100 Hz: the unbalance F(t) - F(t - L/c) is then a
    sustained constant force, so x settles near a static deflection by the last sample."""
    return (np.arange(n, dtype=float) * slope / 100.0).reshape(n, 1)


@contextmanager
def probe_locals(func, arm_text, arm_names, record_text, record_names):
    """Read-only probe of ``func``'s locals via ``sys.settrace``.

    A 'line' event fires *before* its line executes. At every event on a line whose
    stripped source equals ``arm_text`` the ``arm_names`` locals are snapshotted (numpy
    arrays copied); the next event on a line equal to ``record_text`` appends
    ``(arm_snapshot, record_snapshot)`` and disarms. Duplicate line events inside
    multi-line statements are therefore harmless. Yields the list of records.
    """
    src_lines, start = inspect.getsourcelines(func)
    arm_lines = {start + i for i, s in enumerate(src_lines) if s.strip() == arm_text}
    record_lines = {start + i for i, s in enumerate(src_lines) if s.strip() == record_text}
    assert arm_lines and record_lines, "probe text not found in the function source"
    code = func.__code__
    records = []
    armed = []

    def snapshot(frame, names):
        loc = frame.f_locals
        return tuple(loc[n].copy() if isinstance(loc[n], np.ndarray) else loc[n] for n in names)

    def local_tracer(frame, event, arg):
        if event == "line":
            if frame.f_lineno in arm_lines:
                armed[:] = [snapshot(frame, arm_names)]
            elif frame.f_lineno in record_lines and armed:
                records.append((armed[0], snapshot(frame, record_names)))
                armed.clear()
        return local_tracer

    def global_tracer(frame, event, arg):
        return local_tracer if frame.f_code is code else None

    previous = sys.gettrace()
    sys.settrace(global_tracer)
    try:
        yield records
    finally:
        sys.settrace(previous)


# ------------------------------------------------------------------------------- D-12
def test_d12_negative_cube_root_seed_is_complex_not_an_error():
    # VBA: (-varA / varB) ^ (1 / 3) raises error 5 for a negative base.
    assert isinstance(lp.solve_poly(12.0, 1.0, 1.0), complex)


def test_d12_negative_ei_lumped_returns_real_cast_garbage_with_a_warning():
    # The complex portalFrameHeight propagates through mass/stiffness into the numpy
    # state; numpy casts the complex results to the float result array with a
    # ComplexWarning (imaginary parts discarded). VBA would have raised at solvePoly.
    with pytest.warns(np.exceptions.ComplexWarning):
        res = lp.get_peak_response(step_force(), **dict(PEAK_KW, flexural_rigidity_ei=-2e5))
    assert res.shape == (5,)
    assert res.dtype == np.float64


def test_d12_negative_ei_jc_raises_type_error_at_pivot_seg_qty():
    # clng(complex) -> float(complex) is a TypeError, before the integration starts.
    with pytest.raises(TypeError):
        lp.get_peak_response_jc(step_force(), **dict(JC_KW, flexural_rigidity_ei=-2e5))


# ------------------------------------------------------------------------------- D-13
def test_d13_clng_is_unbounded():
    # VBA CLng raises error 6 above 2^31 - 1.
    assert clng(2.0**31) == 2**31
    assert clng(2.0**40) == 2**40
    assert clng(-(2.0**31) - 1) == -(2**31) - 1


def test_d13_step_qty_above_integer_range_is_accepted():
    # VBA: stepQTY As Integer overflows (error 6) above 32767 at the call.
    res = lp.get_peak_response(
        np.array([[1000.0]]), **dict(PEAK_KW, step_qty=32768, physical_length=0.5)
    )
    assert res.shape == (5,)
    assert np.all(np.isfinite(res))


# ------------------------------------------------------------------------------- D-14
def test_d14_numpy_integration_state_raises_on_overflow():
    # forceA - forceB = 1e308 - (-1e308) overflows inside the np.errstate(over="raise")
    # region (VBA error 6, same place).
    force = np.array([[1e308], [-1e308], [1e308], [-1e308]])
    with pytest.raises(FloatingPointError):
        lp.get_peak_response(force, **PEAK_KW)


def test_d14_pure_python_setup_overflow_is_silent():
    # physicalLength * massPerUnitLen overflows to inf in Python (VBA error 6); the nan
    # it breeds in solvePoly/mass/stiffness propagates through the integration without
    # raising (quiet NaN inputs do not trip numpy's invalid/overflow checks) and the
    # summary is returned with nan in the static-equivalent slot and zero peaks.
    res = lp.get_peak_response(step_force(), **dict(PEAK_KW, mass_per_unit_len=1e308))
    assert np.isnan(res[0])
    assert np.all(res[1:4] == 0.0)
    assert res[4] == 1000.0


def test_d14_float_vs_numpy_overflow_semantics():
    with np.errstate(over="raise"):
        assert np.inf == 1e308 * 10.0  # Python float: inf, no exception
        with pytest.raises(FloatingPointError):
            np.float64(1e308) * 10.0  # numpy scalar: raises under errstate
        with pytest.raises(OverflowError):
            _ = 1e308**2  # Python float ** is the one operator that raises


# ------------------------------------------------------------------------------- D-17
def test_d17_jc_mean_fluid_velocity_sums_2n_plus_1_cells_over_2n_minus_1():
    # vAv seeds with arrayA(1, N) then adds arrayA(1, n) and arrayB(1, n) for
    # n = 0 … N-1 (2N + 1 terms) and divides by 2 * pipeSegQTY - 1.
    with probe_locals(
        lp.get_peak_response_jc,
        arm_text="v_av = array_a[1, pipe_seg_qty]",
        arm_names=("array_a", "array_b", "pipe_seg_qty"),
        record_text="if use_undamped:",
        record_names=("v_av",),
    ) as records:
        lp.get_peak_response_jc(step_force(12), **JC_KW)

    assert records, "no even-cell MoC step was traced"
    n_nonzero = 0
    for (array_a, array_b, n_cells), (v_av,) in records:
        total = array_a[1, n_cells]
        for n in range(0, n_cells):
            total = total + array_a[1, n]
            total = total + array_b[1, n]
        assert v_av == total / (2 * n_cells - 1)
        if total != 0.0:
            n_nonzero += 1
            assert v_av != total / (2 * n_cells + 1)
    assert n_nonzero > 0, "every traced sum was zero; the divisor is not exercised"


# ------------------------------------------------------------------------------- D-18
def test_d18_force_ramp_holds_each_sample_for_two_sub_steps():
    # stepQTY = 4: k / (stepQTY - 1) reaches the next sample at k = 3, and the next
    # sample's k = 0 repeats it, so the sub-step force sequence is
    # F0, ., ., F1, F1, ., ., F2, F2, …  (each sample value twice, no cumulative drift).
    s = 4
    force = (3.0 * np.arange(8)).reshape(8, 1)  # 0, 3, 6, … so the ramp steps by 1
    kw = dict(PEAK_KW, step_qty=s, physical_length=50.0)  # unballanceStepQTY = 5.0
    with probe_locals(
        lp.get_peak_response,
        arm_text="force_b = force_history[i, j] * (1 - k / (step_qty - 1)) + force_history[",
        arm_names=("i", "k"),
        record_text="a_new = (",
        record_names=("force_b",),
    ) as records:
        lp.get_peak_response(force, **kw)

    # the first (unbalance) block runs samples 1-5 in full and one sub-step of sample 6
    assert [(i, k) for (i, k), _ in records] == [(i, k) for i in range(1, 6) for k in range(s)] + [
        (6, 0)
    ]
    traced = [fb for _, (fb,) in records]
    expected = [
        force[i - 1, 0] * (1 - k / (s - 1)) + force[i, 0] * (k / (s - 1)) for (i, k), _ in records
    ]
    assert traced == expected
    assert traced[:9] == pytest.approx([0, 1, 2, 3, 3, 4, 5, 6, 6])
    for i in range(1, 5):
        assert traced[s * i - 1] == traced[s * i] == force[i, 0]  # the plateau


# ------------------------------------------------------------------------------- D-19
@pytest.mark.parametrize(
    "physical_length, k_exit, continuous_at_phase_2",
    [
        # unballanceStepQTY = 1.25: phase 1 exits at k = 2 (even); phase 2 restarts at
        # index 20 (even) -> the even half-grid is updated twice in a row
        (12.5, 2, False),
        # unballanceStepQTY = 1.35: exits at k = 3 (odd) -> alternation continuous
        (13.5, 3, True),
    ],
)
def test_d19_jc_parity_index_at_phase_boundaries(
    monkeypatch, physical_length, k_exit, continuous_at_phase_2
):
    s = PEAK_KW["step_qty"]
    n = 100
    indices = []
    original = lp.mod_dbl

    def recording_mod_dbl(num, div):
        indices.append(int(num))
        return original(num, div)

    monkeypatch.setattr(lp, "mod_dbl", recording_mod_dbl)
    kw = dict(JC_KW, physical_length=physical_length, dynamic_fric=0.0, damping_percent=10.0)
    # slope chosen so |x| at the end of phase 2 is > 0.1 and phase 3 (free decay) runs
    lp.get_peak_response_jc(ramp_force(n, slope=2.5e6), **kw, output_type=1)

    seq = np.array(indices)
    jumps = np.flatnonzero(np.diff(seq) != 1)
    assert len(jumps) == 2, "expected exactly the two phase boundaries"
    b1, b2 = jumps
    # phase 1 -> 2: last index s + k_exit, first phase-2 index 2 * s
    assert (seq[b1], seq[b1 + 1]) == (s + k_exit, 2 * s)
    assert (seq[b1] % 2 != seq[b1 + 1] % 2) == continuous_at_phase_2
    # phase 2 -> 3: phase 2 ends at T*s - 1 (T = n + 2 samples), phase 3 starts with
    # k = 1, index T*s + 1: same parity, the odd half-grid is updated twice in a row
    t = n + 2
    assert (seq[b2], seq[b2 + 1]) == (t * s - 1, t * s + 1)
    assert seq[b2] % 2 == seq[b2 + 1] % 2 == 1
    assert seq[-1] > t * s + s  # phase 3 ran for more than one sample


# ------------------------------------------------------------------------------- D-20
def test_d20_friction_dead_zone_between_fric_acc_and_1e_minus_6(monkeypatch):
    # For fricAcc <= |v| < 1e-6 the `Abs(v) < fricAcc` branch is not taken and
    # sign(v, 0.000001) returns 0, so the Coulomb term is dropped for that sub-step.
    calls = []
    original = lp.sign

    def recording_sign(val, lim=0.0):
        result = original(val, lim)
        calls.append((float(val), lim, result))
        return result

    monkeypatch.setattr(lp, "sign", recording_sign)
    kw = dict(PEAK_KW, dynamic_fric=1e-4)
    dt = 1 / (kw["sample_freq"] * kw["step_qty"])
    fric_acc = 0.5 * kw["dynamic_fric"] * 9.81 * dt
    assert fric_acc < 1e-6  # the dead zone exists only when fricAcc < the sign limit
    lp.get_peak_response(step_force(amplitude=0.1), **kw)

    friction_calls = [(v, r) for v, lim, r in calls if lim == 0.000001]
    in_window = [(v, r) for v, r in friction_calls if fric_acc <= abs(v) < 1e-6]
    assert len(in_window) >= 10
    assert all(r == 0.0 for _, r in in_window)
    assert all(r != 0.0 for v, r in friction_calls if abs(v) >= 1e-6)


# ------------------------------------------------------------------------------- D-21
@pytest.mark.parametrize("func", [lp.get_peak_response, lp.get_peak_response_jc])
def test_d21_phase_3_runs_only_while_x_squared_exceeds_0_01(func):
    kw = dict(JC_KW if func is lp.get_peak_response_jc else LUMPED_ONLY)
    kw.update(dynamic_fric=0.0, damping_percent=10.0)  # linear in the force
    n = 100
    end = n + 2  # totInd after phase 2 for unballanceStepQTY = 1.0
    probe = func(ramp_force(n, slope=1e6), **kw, output_type=1)
    assert probe.shape == (2 * (n + 1) + 1,)
    x_end = probe[end]
    assert 0 < abs(x_end) < 0.1
    assert np.all(probe[end + 1 :] == 0.0)  # phase 3 did not run

    for factor, runs in ((1 + 1e-3, True), (1 - 1e-3, False)):
        slope = 1e6 * factor * 0.1 / abs(x_end)
        hist = func(ramp_force(n, slope=slope), **kw, output_type=1)
        assert abs(hist[end]) == pytest.approx(0.1 * factor, rel=1e-6)
        assert (hist[end + 1] != 0.0) == runs
        assert np.any(hist[end + 1 :] != 0.0) == runs
