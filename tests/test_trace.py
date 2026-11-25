"""Session V.1: the solver trace (``trace_every``) and ``loads.elbow_forces``.

The trace must not change what the solvers compute: every test here that runs a solver
compares the traced ``PeakResponse`` with the untraced one bitwise, and the untraced path
itself stays pinned to ``legacy_port`` by ``tests/test_differential.py``.
"""

from __future__ import annotations

import fixture_cases as fc
import numpy as np
import pytest
import test_differential as td
import test_golden as tg

from surge_sdof import loads

# ------------------------------------------------------------------ loads.elbow_forces


def _loads_args(kw):
    return (kw["sample_freq"], kw["physical_length"], kw["celerity"], kw["step_qty"])


def _check_elbow_forces(force, kw):
    """``elbow_forces`` and ``unbalance_force`` walk the same samples; ``fa - fb`` is the
    unbalance value bitwise; the phase flips once, after the truncated delay sample."""
    unbalance = list(loads.unbalance_force(force, *_loads_args(kw)))
    elbows = list(loads.elbow_forces(force, *_loads_args(kw)))
    assert len(elbows) == len(unbalance)
    phases = []
    for (phase, fa, fb), u in zip(elbows, unbalance, strict=True):
        assert len(fa) == len(fb) == len(u)
        assert all(type(a) is float and type(b) is float for a, b in zip(fa, fb, strict=True))
        assert [a - b for a, b in zip(fa, fb, strict=True)] == u
        phases.append(phase)
    n_elements = int(np.size(force))
    n_delay = len(unbalance) - n_elements
    assert phases == [0] * n_delay + [1] * n_elements
    # the delay phase holds forceA at the first history sample
    first = float(np.asarray(force, dtype=float).reshape(-1, order="F")[0])
    assert all(a == first for _phase, fa, _fb in elbows[:n_delay] for a in fa)
    return elbows


@pytest.mark.parametrize("idx", range(td.N_CASES), ids=td.SWEEP_IDS)
def test_elbow_forces_split_the_unbalance_force_on_the_sweep(idx):
    case = td.sweep_cases()[idx]
    _check_elbow_forces(case.force, case.kw)


def test_elbow_forces_split_the_unbalance_force_on_the_example_case():
    case = next(c for c in tg.EXAMPLE_CASES if c["solver"] == "lumped")
    force = np.asarray(case["force_history"], dtype=float)
    _check_elbow_forces(force, case["kwargs"])


def test_elbow_forces_split_the_unbalance_force_on_the_golden_history():
    case = next(c for c in tg.CASES if c["solver"] == "lumped")
    _check_elbow_forces(tg.load_force(tg.PARAMS), tg.case_params(case, tg.PARAMS))


def test_elbow_forces_raise_as_unbalance_force_does():
    case = td.sweep_cases()[0]
    kw = dict(case.kw, step_qty=1)
    with pytest.raises(ZeroDivisionError):  # D-7
        next(loads.elbow_forces(case.force, *_loads_args(kw)))
    with pytest.raises(IndexError):  # D-8, the single-row history of test_differential
        list(loads.elbow_forces(np.ones((1, 10)), 100.0, 100.0, 1000.0, 10))


# ------------------------------------------------------------------ the trace itself

from surge_sdof import coupling, moc, response, structure  # noqa: E402
from surge_sdof import trace as tracing  # noqa: E402
from surge_sdof.vba_compat import clng  # noqa: E402

LUMPED_IDX = [8, 19, 26, 33]  # sweep cases that enter free decay (q2 / q7 / q2 / q40)
LUMPED_IDS = [td.SWEEP_IDS[i] for i in LUMPED_IDX]
STRIDES = [1, 3, 7]

# A 6-sample step at 1 Hz natural frequency: free decay (44 / 47 samples) outruns the
# history window (outMax * 2 - forced = 6 samples), so the trace is capped like the history.
CAPPED_KW = dict(td.JC_SMALL_KW, damping_percent=1.0, dynamic_fric=0.0, nat_freq=1.0)
CAPPED_FORCE = td._step_force(n=6, amplitude=1e6)


def _lumped_case(idx):
    case = td.sweep_cases()[idx]
    return case.force, case.kw, case.history_type


def _jc_case(idx):
    _id, force, kw = td.JC_SMALL[idx]
    return force, kw


def _lumped_kw(kw):
    return {k: v for k, v in kw.items() if not k.startswith("fluid")}


def _same_result(a: response.PeakResponse, b: response.PeakResponse, output_type: int):
    assert np.array_equal(a.summary(), b.summary())
    assert a.free_decay_sample_count == b.free_decay_sample_count
    if fc.history_of(a, output_type) is None:
        assert fc.history_of(b, output_type) is None
    else:
        assert np.array_equal(fc.history_of(a, output_type), fc.history_of(b, output_type))


def _schedule(force, kw):
    """(flat unbalance, sample offsets, delay sub-steps, outMax) of a case."""
    samples = list(loads.unbalance_force(force, *_loads_args(kw)))
    elbows = list(loads.elbow_forces(force, *_loads_args(kw)))
    flat = np.array([f for s in samples for f in s])
    offsets = np.cumsum([0] + [len(s) for s in samples])
    delay_substeps = sum(len(fa) for ph, fa, _fb in elbows if ph == tracing.PHASE_TRANSIT)
    unb = loads.transit_delay(kw["physical_length"], kw["celerity"], kw["sample_freq"])
    out_max = int(np.size(force)) + clng(unb)
    return flat, offsets, delay_substeps, out_max


def _check_frames(res: response.PeakResponse, force, kw, stride):
    """Length, stride, time, sample and phase arithmetic of a trace against the
    unbalance schedule and the run's ``free_decay_samples``."""
    tr = res.trace
    assert isinstance(tr, tracing.Trace)
    assert tr.trace_every == stride
    flat, offsets, delay_substeps, out_max = _schedule(force, kw)
    forced_substeps = len(flat)
    forced_samples = len(offsets) - 1
    step_qty = kw["step_qty"]
    assert tr.nominal_forced_sample_count == out_max and tr.substep_count == step_qty
    assert tr.substep_duration == 1 / (kw["sample_freq"] * step_qty)
    traced_decay = min(res.free_decay_sample_count, out_max * 2 - forced_samples)
    total = forced_substeps + traced_decay * step_qty
    n_frames = -(-total // stride)
    assert tr.frame_count == n_frames
    for name in (
        "time", "substep_index", "sample_index", "load_phase", "displacement", "velocity",
        "acceleration", "elbow_a_force", "elbow_b_force", "unbalance_force", "friction_force",
        "is_sticking", "junction_force",
    ):  # fmt: skip
        assert getattr(tr, name).shape == (n_frames,), name
    assert np.array_equal(tr.substep_index, stride * np.arange(n_frames))
    assert np.array_equal(tr.time, (tr.substep_index + 1) * tr.substep_duration)
    # sample index: from the offsets in the forced phases, stepQTY per sample after
    forced = tr.substep_index < forced_substeps
    assert np.array_equal(
        tr.sample_index[forced],
        np.searchsorted(offsets, tr.substep_index[forced], side="right") - 1,
    )
    decay = tr.substep_index[~forced]
    assert np.array_equal(
        tr.sample_index[~forced], forced_samples + (decay - forced_substeps) // step_qty
    )
    assert np.all(tr.sample_index < out_max * 2)
    # phase labels: transit while the delay samples last, history to the end of the
    # schedule, free decay after
    expected_phase = np.where(
        tr.substep_index < delay_substeps,
        tracing.PHASE_TRANSIT,
        np.where(forced, tracing.PHASE_FORCED, tracing.PHASE_FREE_DECAY),
    )
    assert np.array_equal(tr.load_phase, expected_phase)
    assert delay_substeps > 0 and np.any(tr.load_phase == tracing.PHASE_TRANSIT)
    assert np.any(tr.load_phase == tracing.PHASE_FORCED)
    assert np.any(tr.load_phase == tracing.PHASE_FREE_DECAY) == (traced_decay > 0)
    # forces: the loads sequence at the traced sub-steps, zero in free decay
    assert np.array_equal(tr.unbalance_force[forced], flat[tr.substep_index[forced]])
    assert np.array_equal(tr.elbow_a_force - tr.elbow_b_force, tr.unbalance_force)
    assert not np.any(tr.elbow_a_force[~forced]) and not np.any(tr.elbow_b_force[~forced])
    assert np.all(np.isfinite(tr.displacement)) and np.all(np.isfinite(tr.friction_force))
    return tr


def test_trace_every_is_validated():
    force, kw, _ht = _lumped_case(LUMPED_IDX[0])
    with pytest.raises(ValueError, match="trace_every"):
        response.peak_response(force, **fc.solver_inputs(kw, trace_every=-1))
    with pytest.raises(TypeError):
        response.peak_response(force, **fc.solver_inputs(kw, trace_every=2.5))
    jc_force, jc_kw = _jc_case(0)
    with pytest.raises(ValueError, match="trace_every"):
        response.peak_response_jc(jc_force, **fc.solver_inputs(jc_kw, trace_every=-1))
    assert response.peak_response(force, **fc.solver_inputs(kw)).trace is None
    assert response.peak_response(force, **fc.solver_inputs(kw, trace_every=0)).trace is None
    assert response.peak_response_jc(jc_force, **fc.solver_inputs(jc_kw)).trace is None


@pytest.mark.parametrize("stride", STRIDES)
@pytest.mark.parametrize("idx", LUMPED_IDX, ids=LUMPED_IDS)
def test_lumped_trace_leaves_the_result_bitwise_and_follows_the_stride(idx, stride):
    force, kw, history_type = _lumped_case(idx)
    for output_type in (0, history_type):
        base = response.peak_response(force, **fc.solver_inputs(kw, output_type=output_type))
        res = response.peak_response(
            force, **fc.solver_inputs(kw, output_type=output_type, trace_every=stride)
        )
        _same_result(base, res, output_type)
        tr = _check_frames(res, force, kw, stride)
        assert tr.solver == "peak_response"
        assert not np.any(tr.junction_force) and tr.column is None
        assert tr.sdof_params == structure.lumped_params(
            response.PipeSpan(
                kw["physical_length"], kw["flexural_rigidity_ei"], kw["mass_per_unit_len"], 0.0
            ),
            response.Restraint(
                kw["nat_freq"],
                kw["damping_percent"],
                kw["dynamic_fric"],
                kw["gap"],
                kw["restrain_freq_ratio"],
            ),
            structure.solve_portal_height(
                kw["physical_length"],
                kw["flexural_rigidity_ei"],
                kw["mass_per_unit_len"],
                kw["nat_freq"],
            ),
            tr.substep_duration,
        )


@pytest.mark.parametrize("stride", STRIDES)
@pytest.mark.parametrize("idx", range(len(td.JC_SMALL)), ids=td.JC_SMALL_IDS)
def test_jc_trace_leaves_the_result_bitwise_and_follows_the_stride(idx, stride):
    force, kw = _jc_case(idx)
    for output_type in (0, 3):
        base = response.peak_response_jc(force, **fc.solver_inputs(kw, output_type=output_type))
        res = response.peak_response_jc(
            force, **fc.solver_inputs(kw, output_type=output_type, trace_every=stride)
        )
        _same_result(base, res, output_type)
        tr = _check_frames(res, force, kw, stride)
        assert tr.solver == "peak_response_jc"
        assert (
            tr.column.grid_point_pressure.shape
            == tr.column.grid_point_velocity.shape
            == (tr.frame_count, tr.column.grid_point_count)
        )
        assert np.any(tr.junction_force)


@pytest.mark.parametrize("flags", [td.LEGACY_FLAGS, td.FIXED_FLAGS], ids=["legacy", "fixed"])
def test_jc_trace_is_bitwise_under_both_flag_sets(flags):
    force, kw = _jc_case(1)
    base = response.peak_response_jc(force, **fc.solver_inputs(kw, output_type=1, **flags))
    res = response.peak_response_jc(
        force, **fc.solver_inputs(kw, output_type=1, trace_every=2, **flags)
    )
    _same_result(base, res, 1)
    assert res.trace.inputs["coupling"]["parity"] == flags["parity"]
    assert res.trace.inputs["coupling"]["fraction_profile"] == flags["fraction_profile"]


@pytest.mark.parametrize("stride", [1, 5])
@pytest.mark.parametrize("solver", ["lumped", "jc"])
def test_free_decay_is_traced_only_inside_the_history_window(solver, stride):
    if solver == "jc":
        run, kw = response.peak_response_jc, CAPPED_KW
    else:
        run, kw = response.peak_response, _lumped_kw(CAPPED_KW)
    base = run(CAPPED_FORCE, **fc.solver_inputs(kw, output_type=1))
    res = run(CAPPED_FORCE, **fc.solver_inputs(kw, output_type=1, trace_every=stride))
    _same_result(base, res, 1)
    tr = _check_frames(res, CAPPED_FORCE, kw, stride)
    _flat, offsets, _delay, out_max = _schedule(CAPPED_FORCE, kw)
    assert res.free_decay_sample_count > out_max * 2 - (len(offsets) - 1)  # the cap is hit
    assert tr.sample_index[-1] == out_max * 2 - 1
    assert np.sum(tr.load_phase == tracing.PHASE_FREE_DECAY) > 0
    # the frames at sample ends agree with the history (the truncated delay sample
    # shifts the sample boundaries off the multiples of stepQTY)
    step_qty = kw["step_qty"]
    ends = np.concatenate([offsets[1:] - 1, offsets[-1] + step_qty * np.arange(1, out_max * 2) - 1])
    last = np.isin(tr.substep_index, ends)
    assert last.sum() > 0
    assert np.array_equal(tr.displacement[last], base.displacement_history[tr.sample_index[last]])


def test_f_friction_is_zero_without_friction():
    for idx in (10, 19, 24):  # dynamic_fric = 0 sweep cases that enter free decay
        force, kw, _ht = _lumped_case(idx)
        assert kw["dynamic_fric"] == 0
        tr = response.peak_response(force, **fc.solver_inputs(kw, trace_every=1)).trace
        assert tr.sdof_params.friction_velocity_step == 0
        assert not np.any(tr.friction_force) and not np.any(tr.is_sticking)


@pytest.mark.parametrize("idx", [8, 26], ids=[td.SWEEP_IDS[8], td.SWEEP_IDS[26]])
def test_f_friction_and_stick_follow_the_coulomb_branch(idx):
    force, kw, _ht = _lumped_case(idx)
    assert kw["dynamic_fric"] > 0
    tr = response.peak_response(force, **fc.solver_inputs(kw, trace_every=1)).trace
    mass, fric_acc, dt = (
        tr.sdof_params.mass,
        tr.sdof_params.friction_velocity_step,
        tr.substep_duration,
    )
    v_old = np.concatenate([[0.0], tr.velocity[:-1]])
    a_old = np.concatenate([[0.0], tr.acceleration[:-1]])
    assert np.array_equal(tr.is_sticking, np.abs(v_old) < fric_acc)
    assert tr.is_sticking.any() and (~tr.is_sticking).any()
    # definition: mass * (v_new - (v_old + (a_old + a_new) dt / 2)) / dt, the same doubles
    dv = tr.velocity - (v_old + (a_old + tr.acceleration) * (dt / 2))
    assert np.array_equal(tr.friction_force, mass * dv / dt)
    # slip: -+ fric_acc against the velocity; stick: the momentum removed, v_old
    slip_pos = ~tr.is_sticking & (v_old > 0.000001)
    slip_neg = ~tr.is_sticking & (v_old < -0.000001)
    assert slip_pos.any() and slip_neg.any()
    np.testing.assert_allclose(tr.friction_force[slip_pos], -mass * fric_acc / dt, rtol=1e-9)
    np.testing.assert_allclose(tr.friction_force[slip_neg], mass * fric_acc / dt, rtol=1e-9)
    np.testing.assert_allclose(
        tr.friction_force[tr.is_sticking], -mass * v_old[tr.is_sticking] / dt, rtol=1e-6
    )


def test_jc_trace_geometry():
    force, kw = _jc_case(3)  # example_jc
    tr = response.peak_response_jc(force, **fc.solver_inputs(kw, trace_every=4)).trace
    dt = 1 / (kw["sample_freq"] * kw["step_qty"])
    h = structure.solve_portal_height(
        kw["physical_length"], kw["flexural_rigidity_ei"], kw["mass_per_unit_len"], kw["nat_freq"]
    )
    pipe_seg_qty, pivot_seg_qty = moc.grid_size(kw["physical_length"], h, kw["celerity"], dt)
    assert (
        tr.column.column_cell_count,
        tr.column.end_to_elbow_cell_count,
        tr.column.inactive_end_cell_count,
    ) == (
        pipe_seg_qty,
        pivot_seg_qty,
        moc.INACTIVE_END_CELL_COUNT,
    )
    assert tr.column.grid_point_count == 2 * pipe_seg_qty + 1
    assert np.array_equal(tr.column.grid_point_kind, np.arange(tr.column.grid_point_count) % 2)
    assert np.array_equal(
        tr.column.grid_point_position, np.arange(tr.column.grid_point_count) * (kw["celerity"] * dt)
    )
    frac_a, frac_b = moc.moving_fractions(pipe_seg_qty, pivot_seg_qty)
    assert np.array_equal(tr.column.grid_point_moving_fraction[0::2], frac_a)
    assert np.array_equal(tr.column.grid_point_moving_fraction[1::2], frac_b)
    assert np.array_equal(tr.column.grid_point_moving_fraction, tracing.interleave(frac_a, frac_b))
    assert tr.sdof_params == structure.jc_params(
        response.PipeSpan(kw["physical_length"], 0.0, kw["mass_per_unit_len"], 0.0),
        response.Restraint(kw["nat_freq"], kw["damping_percent"], kw["dynamic_fric"], 0, 1),
        response.Fluid(kw["fluid_densty"], kw["fluid_area"]),
        h,
        dt,
    )
    # every argument of the call is echoed, grouped as it was passed
    assert set(tr.inputs) == set(fc.solver_inputs(kw)) | {"force_history"}
    assert np.array_equal(tr.inputs["force_history"], loads.as_history_2d(force))


def test_interleave():
    assert np.array_equal(
        tracing.interleave(np.array([1, 2, 3]), np.array([10, 20])), [1, 10, 2, 20, 3]
    )
    with pytest.raises(ValueError):
        tracing.interleave(np.zeros(3), np.zeros(3))


@pytest.mark.parametrize("stride", [1, 6])
def test_jc_column_at_frame_0_is_the_initial_column(stride):
    force, kw = _jc_case(0)
    tr = response.peak_response_jc(force, **fc.solver_inputs(kw, trace_every=stride)).trace
    p_a, v_a, p_b, v_b = moc.column_at_rest(tr.column.column_cell_count)
    assert np.array_equal(tr.column.grid_point_pressure[0], tracing.interleave(p_a, p_b))
    assert np.array_equal(tr.column.grid_point_velocity[0], tracing.interleave(v_a, v_b))
    assert tr.junction_force[0] == 0.0
    assert np.any(tr.column.grid_point_pressure[-1]) and np.any(tr.column.grid_point_velocity[-1])


@pytest.mark.parametrize("idx", [0, 3], ids=[td.JC_SMALL_IDS[0], td.JC_SMALL_IDS[3]])
def test_jc_trace_reproduces_the_coupling_sequence(idx):
    """At stride 1 ``moc.step`` on a fresh ``coupling.fluid_column``, driven with the
    traced acceleration of the previous sub-step and the running index, reproduces ``d_f``
    and the column bitwise."""
    force, kw = _jc_case(idx)
    res = response.peak_response_jc(force, **fc.solver_inputs(kw, trace_every=1))
    tr = res.trace
    dt = tr.substep_duration
    column = coupling.fluid_column(
        moc.ColumnGrid(tr.column.column_cell_count, tr.column.end_to_elbow_cell_count),
        coupling.FluidConstants(
            kw["fluid_densty"] * kw["celerity"],
            kw["fluid_area"],
            moc.end_pressure_decay_factor(kw["celerity"], dt, kw["physical_length"]),
        ),
        "fixed",
    )
    a_prev = 0.0
    d_f = 0.0
    for i in range(tr.frame_count):
        d_f = td.advance_column(column, dt, int(tr.substep_index[i]), a_prev, d_f)
        assert d_f == tr.junction_force[i]
        assert np.array_equal(
            tr.column.grid_point_pressure[i],
            tracing.interleave(column.pressure_a, column.pressure_b),
        )
        assert np.array_equal(
            tr.column.grid_point_velocity[i],
            tracing.interleave(column.velocity_a, column.velocity_b),
        )
        a_prev = float(tr.acceleration[i])
    assert tr.frame_count > 100


def test_memory_guard_names_a_stride_that_fits(monkeypatch):
    force, kw = _jc_case(1)
    monkeypatch.setattr(tracing, "MAX_TRACE_VALUES", 20_000)
    with pytest.raises(ValueError, match="trace_every >= ") as info:
        response.peak_response_jc(force, **fc.solver_inputs(kw, trace_every=1))
    stride = int(str(info.value).rsplit(">= ", 1)[1])
    assert stride > 1
    res = response.peak_response_jc(force, **fc.solver_inputs(kw, trace_every=stride))
    per_frame = (
        tracing.FRAME_STATE_COLUMN_COUNT
        + tracing.FRAME_INDEX_COLUMN_COUNT
        + 2 * res.trace.column.grid_point_count
    )
    assert res.trace.frame_count * per_frame <= 20_000
    with pytest.raises(ValueError):
        response.peak_response_jc(force, **fc.solver_inputs(kw, trace_every=stride - 1))
    # the lumped path is guarded too (per-frame scalars only)
    monkeypatch.setattr(tracing, "MAX_TRACE_VALUES", 100)
    with pytest.raises(ValueError, match="trace_every >= "):
        response.peak_response(force, **fc.solver_inputs(_lumped_kw(kw), trace_every=1))


def test_capacity_arithmetic():
    assert tracing.frame_capacity(100, 10, 12, 5, 0) == 0
    # forced 100 sub-steps + (24 - 10) samples x 5 = 170 sub-steps
    assert tracing.frame_capacity(100, 10, 12, 5, 1) == 170
    assert tracing.frame_capacity(100, 10, 12, 5, 7) == -(-170 // 7) == 25
    assert tracing.frame_capacity(100, 30, 12, 5, 1) == 100  # window already spent
    assert tracing.allocate_frames(0, 9, 0)[2].shape == (0, 0)
    assert tracing.allocate_frames(3, 9, 1)[2].shape == (3, 9) and tracing.allocate_frames(3, 0, 1)[
        3
    ].shape == (3, 0)


def test_jc_short_pipe_fallback_trace_is_lumped():
    force = td._step_force()
    kw = dict(td.JC_SMALL_KW, physical_length=1.0)
    res = response.peak_response_jc(force, **fc.solver_inputs(kw, output_type=1, trace_every=2))
    lumped = response.peak_response(
        force, **fc.solver_inputs(_lumped_kw(kw), output_type=1, trace_every=2)
    )
    _same_result(res, lumped, 1)
    assert res.trace.solver == "peak_response" and res.trace.column is None
    assert "fluid" not in res.trace.inputs
    assert np.array_equal(res.trace.displacement, lumped.trace.displacement)
    assert np.array_equal(res.trace.friction_force, lumped.trace.friction_force)
