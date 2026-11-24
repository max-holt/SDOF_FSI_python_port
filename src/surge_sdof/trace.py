"""The solver trace for visualisation (Session V.1): ``Trace`` and its helpers.

``peak_response(..., trace_every=k)`` and ``peak_response_jc(..., trace_every=k)`` record
every ``k``-th sub-step into preallocated arrays inside ``response._integrate_kernel`` and
return the result as ``PeakResponse.trace``. With ``trace_every = 0`` (the default) the
kernel takes empty arrays and never enters the recording branch; the state arithmetic is
the same in both cases, so a traced run returns the same ``PeakResponse`` values bitwise
(``tests/test_trace.py``).

Frame convention
----------------
Frame ``i`` is the **end of sub-step** ``i * trace_every``, where ``sub_step`` is the
running 0-based counter ``n`` of the kernel (the index whose parity drives the MoC
half-grids). ``t = (sub_step + 1) * dt`` is the time at the end of that sub-step; ``x``,
``v``, ``a`` are the state after it; ``f_a``, ``f_b`` and ``f_unbalance`` the forces applied
during it (zero in free decay); ``d_f`` the junction force the sub-step used (``moc.step``
runs before the SDOF update; ``0.0`` for the lumped solver); ``p_cells`` / ``v_cells`` the
column after it. ``sample`` is the 0-based sample index (``totInd - 1``, the index into
``PeakResponse.history``); ``phase`` is 0 in the transit phase, 1 in the forced phase
and 2 in free decay. Frame 0 is the end of sub-step 0: a column at rest with
``a = 0`` is still bitwise the initial column there.

Free decay is traced for as long as the history records it (``totInd <= outMax * 2``, the
``_record_sample`` guard of the kernel); later free-decay sub-steps are integrated but not
traced, as the history drops them. The arrays are allocated once for that window
(``frame_capacity``) and sliced to the frames written.

``f_friction = mass * dv_friction / dt`` where ``dv_friction = v_new - (v_old + (a_old +
a_new) * (dt / 2))`` is the velocity the Coulomb branch of ``structure.step_scalars`` added
or removed in the sub-step, recomputed in the recording branch from the same doubles the
kernel formed (``half_dt = dt / 2``; ``v + trapezoid_velocity_change``): in slip it is
``-+fric_acc`` (``0.0`` exactly with ``dynamicFric = 0``; the D-20 dead zone gives ``0.0``
too), in stick (``|v_old| < fric_acc``) it is ``trapezoid_velocity_change - (v_old +
trapezoid_velocity_change)``, the momentum the stick removed, so ``f_friction`` there is the
holding force. ``stick`` is that test.

JC column layout
----------------
The staggered grid is stored **interleaved**: ``A0 B0 A1 B1 ... A(N-1) B(N-1) A(N)``,
``n_cells = 2N + 1`` (``cell_kind`` 0 = A node, 1 = B cell). ``cell_position`` is
``j * celerity * dt`` m from the first A node (a cell is ``2 c dt`` long; the column runs
``ext_qty`` end cells, the leg up to the pivot, the span between the pivots, the other leg
and ``ext_qty`` end cells, see ``moc.grid_size``). ``moving_fraction`` is ``frac_a`` /
``frac_b`` interleaved the same way, the values ``moc.step`` multiplies ``a dt`` by
(``frac_a[0]`` and ``frac_a[N]`` are the unused zeros of ``moc.moving_fractions``).
``p_cells`` and ``v_cells`` are copies of the four arrays exactly as the model stores them:
pressures in Pa, velocities in m/s relative to the pipe, after the acceleration injection
and the ``vAv`` subtraction of the sub-step.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from surge_sdof.loads import PHASE_FORCED, PHASE_TRANSIT
from surge_sdof.structure import SdofParams

__all__ = [
    "MAX_TRACE_VALUES",
    "PHASE_TRANSIT",
    "PHASE_FORCED",
    "PHASE_FREE_DECAY",
    "Trace",
    "frame_capacity",
    "check_memory",
    "allocate_frames",
    "interleave",
    "build_trace",
]

# PHASE_TRANSIT and PHASE_FORCED are produced by ``loads`` and re-exported here with the
# third code, which only the solver loop records.
PHASE_FREE_DECAY = 2  # no unbalance force; the structure rings down (VBA phase 3)

# Columns of the kernel's float64 frame array ``tr_f (capacity, FRAME_STATE_COLUMN_COUNT)``.
(
    COL_X,
    COL_V,
    COL_A,
    COL_ELBOW_A_FORCE,
    COL_ELBOW_B_FORCE,
    COL_UNBALANCE_FORCE,
    COL_FRICTION_FORCE,
    COL_JUNCTION_FORCE,
) = range(8)
FRAME_STATE_COLUMN_COUNT = 8
# Columns of the int64 frame array ``tr_i (capacity, FRAME_INDEX_COLUMN_COUNT)``.
COL_SUBSTEP_INDEX, COL_SAMPLE_INDEX, COL_LOAD_PHASE, COL_IS_STICKING = range(4)
FRAME_INDEX_COLUMN_COUNT = 4

MAX_TRACE_VALUES = 50_000_000
"""Memory guard: the largest number of 8-byte values (``frame_capacity * (float columns +
int columns + 2 * n_cells)``, 400 MB) a trace may allocate; ``check_memory`` raises
``ValueError`` above it and names the smallest stride that fits."""


@dataclass(frozen=True)
class Trace:
    """Every ``trace_every``-th sub-step of a peak-response run (see the module docstring).

    Attributes
    ----------
    solver : str
        ``"peak_response"`` or ``"peak_response_jc"``; a JC call that took the short-pipe
        fallback produces a ``"peak_response"`` trace (JC fields None).
    trace_every : int
        The stride in sub-steps.
    dt : float
        Sub-step, s.
    step_qty : int
        Sub-steps per sample.
    out_max : int
        The VBA ``outMax``; free decay is traced while ``sample < out_max * 2``.
    params : SdofParams
        ``(mass, stiffness, damping, friction_velocity_step, support_gap,
        closed_gap_stiffness_ratio)`` of the run (kg, N/m, N·s/m,
        m/s, m, dimensionless).
    inputs : dict
        The case inputs as the solver received them (``force_history`` as the 2-D array
        the walk used; the JC keyword flags included), so the trace is self-describing.
    t, sub_step, sample, phase : numpy.ndarray
        Per frame: time at the end of the sub-step (s), the 0-based sub-step index, the
        0-based sample index, the phase (0 transit, 1 forced, 2 free decay).
    x, v, a : numpy.ndarray
        State at the end of the sub-step: m, m/s, m/s².
    f_a, f_b, f_unbalance : numpy.ndarray
        Force at elbow A, delayed force at elbow B and ``f_a - f_b`` applied in the
        sub-step, N (zero in free decay).
    f_friction : numpy.ndarray
        ``mass * dv_friction / dt``, N (see the module docstring).
    stick : numpy.ndarray
        bool, ``|v_old| < fric_acc``: the sub-step took the stick branch.
    d_f : numpy.ndarray
        Junction force used in the sub-step, N (zeros for the lumped solver).
    n_cells, pivot_seg_qty, pipe_seg_qty, ext_qty : int
        JC grid: ``2N + 1``, ``pivotSegQTY``, ``pipeSegQTY``, ``extQTY`` (0 for lumped).
    p_cells, v_cells : numpy.ndarray or None
        JC only, ``(n_frames, n_cells)``: the interleaved column after the sub-step, Pa
        and m/s.
    cell_position, cell_kind, moving_fraction : numpy.ndarray or None
        JC only, length ``n_cells``: position along the column (m), 0 = A node / 1 = B
        cell, and the moving fraction of the cell (dimensionless).
    """

    solver: str
    trace_every: int
    dt: float
    step_qty: int
    out_max: int
    params: SdofParams
    inputs: dict
    t: np.ndarray
    sub_step: np.ndarray
    sample: np.ndarray
    phase: np.ndarray
    x: np.ndarray
    v: np.ndarray
    a: np.ndarray
    f_a: np.ndarray
    f_b: np.ndarray
    f_unbalance: np.ndarray
    f_friction: np.ndarray
    stick: np.ndarray
    d_f: np.ndarray
    n_cells: int = 0
    pivot_seg_qty: int = 0
    pipe_seg_qty: int = 0
    ext_qty: int = 0
    p_cells: np.ndarray | None = None
    v_cells: np.ndarray | None = None
    cell_position: np.ndarray | None = None
    cell_kind: np.ndarray | None = None
    moving_fraction: np.ndarray | None = None

    @property
    def n_frames(self) -> int:
        """Frames recorded."""
        return int(self.t.shape[0])


def frame_capacity(
    forced_substep_count: int,
    forced_sample_count: int,
    nominal_forced_sample_count: int,
    substep_count: int,
    trace_every: int,
) -> int:
    """Frames to allocate: the forced phases (``forced_substep_count`` sub-steps, known from the
    unbalance schedule) plus free decay up to the history window (``outMax * 2`` samples
    in all), every ``trace_every``-th sub-step; 0 when not tracing.

    Parameters
    ----------
    forced_substep_count : int
        Sub-steps of the transit and forced phases (the length of the flat unbalance array).
    forced_sample_count : int
        Samples of the transit and forced phases.
    nominal_forced_sample_count : int
        The VBA ``outMax``.
    substep_count : int
        Sub-steps per sample.
    trace_every : int
        Stride in sub-steps, 0 for no trace.

    Returns
    -------
    int
    """
    if trace_every <= 0:
        return 0
    # Proposed derivation, for Ben to confirm: the recorded history holds out_max * 2 samples,
    # the forced samples and an equal allowance for free decay; later free decay is integrated
    # but not recorded.
    decay_substeps = max(0, nominal_forced_sample_count * 2 - forced_sample_count) * substep_count
    return -(-(forced_substep_count + decay_substeps) // trace_every)  # ceil


def check_memory(
    forced_substep_count: int,
    forced_sample_count: int,
    nominal_forced_sample_count: int,
    substep_count: int,
    trace_every: int,
    grid_point_count: int,
) -> int:
    """The trace capacity, or ``ValueError`` when it would exceed ``MAX_TRACE_VALUES``.

    Parameters
    ----------
    forced_substep_count, forced_sample_count, nominal_forced_sample_count, substep_count,
    trace_every
        As ``frame_capacity``.
    grid_point_count : int
        ``2N + 1`` for a JC run, 0 for lumped.

    Returns
    -------
    int
        ``frame_capacity(...)``.

    Raises
    ------
    ValueError
        When ``frame_capacity * (FRAME_STATE_COLUMN_COUNT + FRAME_INDEX_COLUMN_COUNT + 2 *
        grid_point_count)`` exceeds ``MAX_TRACE_VALUES`` (this includes the ``n_frames *
        grid_point_count`` of each column array); the message names the smallest
        ``trace_every`` that fits.
    """
    values_per_frame = FRAME_STATE_COLUMN_COUNT + FRAME_INDEX_COLUMN_COUNT + 2 * grid_point_count
    needed_frames = frame_capacity(
        forced_substep_count,
        forced_sample_count,
        nominal_forced_sample_count,
        substep_count,
        trace_every,
    )
    if needed_frames * values_per_frame <= MAX_TRACE_VALUES:
        return needed_frames
    fitting_stride = max(
        trace_every + 1,
        math.ceil(needed_frames * trace_every * values_per_frame / MAX_TRACE_VALUES),
    )
    while frame_capacity(
        forced_substep_count,
        forced_sample_count,
        nominal_forced_sample_count,
        substep_count,
        fitting_stride,
    ) * values_per_frame > (MAX_TRACE_VALUES):
        fitting_stride += 1
    raise ValueError(
        f"trace_every={trace_every} would record {needed_frames} frames x "
        f"{values_per_frame} values "
        f"({needed_frames * values_per_frame:.3g} > {MAX_TRACE_VALUES:.3g} 8-byte values, "
        f"{needed_frames * grid_point_count:.3g} per column array); "
        f"use trace_every >= {fitting_stride}"
    )


def allocate_frames(
    frame_capacity: int, grid_point_count: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """``(tr_f, tr_i, tr_p, tr_v)`` zeroed for the kernel: ``(cap, FRAME_STATE_COLUMN_COUNT)``
    float64, ``(cap, FRAME_INDEX_COLUMN_COUNT)`` int64 and two ``(cap, grid_point_count)`` float64
    (``grid_point_count`` is 0 for lumped; both are ``(0, 0)`` when ``frame_capacity`` is 0).

    Parameters
    ----------
    frame_capacity : int
        From ``frame_capacity`` / ``check_memory``.
    grid_point_count : int
        ``2N + 1`` or 0.
    """
    allocated_grid_point_count = grid_point_count if frame_capacity > 0 else 0
    return (
        np.zeros((frame_capacity, FRAME_STATE_COLUMN_COUNT)),
        np.zeros((frame_capacity, FRAME_INDEX_COLUMN_COUNT), dtype=np.int64),
        np.zeros((frame_capacity, allocated_grid_point_count)),
        np.zeros((frame_capacity, allocated_grid_point_count)),
    )


def interleave(a_nodes: np.ndarray, b_cells: np.ndarray) -> np.ndarray:
    """``[a0, b0, a1, b1, ..., a(N-1), b(N-1), aN]`` of an A-node array (length ``N + 1``)
    and a B-cell array (length ``N``): the column layout of the trace.

    Parameters
    ----------
    a_nodes : numpy.ndarray
        Length ``N + 1``.
    b_cells : numpy.ndarray
        Length ``N``.

    Returns
    -------
    numpy.ndarray
        Length ``2N + 1``.
    """
    n = b_cells.shape[0]
    if a_nodes.shape[0] != n + 1:
        raise ValueError(f"A nodes must be one longer than B cells, got {a_nodes.shape[0]} and {n}")
    out = np.empty(2 * n + 1, dtype=np.result_type(a_nodes, b_cells))
    out[0::2] = a_nodes
    out[1::2] = b_cells
    return out


def build_trace(
    solver: str,
    inputs: dict,
    trace_every: int,
    substep_duration: float,
    substep_count: int,
    nominal_forced_sample_count: int,
    params: SdofParams,
    n_frames: int,
    tr_f: np.ndarray,
    tr_i: np.ndarray,
    tr_p: np.ndarray,
    tr_v: np.ndarray,
    jc=None,
    celerity: float = 0.0,
    inactive_end_cell_count: int = 0,
) -> Trace:
    """Assemble the ``Trace`` from the kernel's arrays, sliced to ``n_frames`` (copies, so
    the unused capacity is released).

    Parameters
    ----------
    solver, inputs, trace_every, substep_duration, substep_count, nominal_forced_sample_count,
    params
        The one-off fields.
    n_frames : int
        Frames the kernel wrote.
    tr_f, tr_i, tr_p, tr_v : numpy.ndarray
        From ``allocate_frames``, filled by the kernel.
    jc : coupling.JunctionCoupling or None
        The junction of a JC run (its grid and moving fractions), None for lumped.
    celerity : float
        Pressure-wave speed, m/s (cell positions); unused for lumped.
    inactive_end_cell_count : int
        ``moc.INACTIVE_END_CELL_COUNT`` for a JC run.
    """
    frame_state = tr_f[:n_frames]
    frame_index_columns = tr_i[:n_frames]
    sub_step = frame_index_columns[:, COL_SUBSTEP_INDEX].copy()
    fields = {
        "solver": solver,
        "trace_every": int(trace_every),
        "dt": float(substep_duration),
        "step_qty": int(substep_count),
        "out_max": int(nominal_forced_sample_count),
        "params": params,
        "inputs": inputs,
        "t": (sub_step + 1) * float(substep_duration),
        "sub_step": sub_step,
        "sample": frame_index_columns[:, COL_SAMPLE_INDEX].copy(),
        "phase": frame_index_columns[:, COL_LOAD_PHASE].copy(),
        "x": frame_state[:, COL_X].copy(),
        "v": frame_state[:, COL_V].copy(),
        "a": frame_state[:, COL_A].copy(),
        "f_a": frame_state[:, COL_ELBOW_A_FORCE].copy(),
        "f_b": frame_state[:, COL_ELBOW_B_FORCE].copy(),
        "f_unbalance": frame_state[:, COL_UNBALANCE_FORCE].copy(),
        "f_friction": frame_state[:, COL_FRICTION_FORCE].copy(),
        "stick": frame_index_columns[:, COL_IS_STICKING] != 0,
        "d_f": frame_state[:, COL_JUNCTION_FORCE].copy(),
    }
    if jc is not None:
        column_cell_count = int(jc.n_seg)
        grid_point_count = 2 * column_cell_count + 1
        fields.update(
            n_cells=grid_point_count,
            pivot_seg_qty=int(jc.pivot),
            pipe_seg_qty=column_cell_count,
            ext_qty=int(inactive_end_cell_count),
            p_cells=tr_p[:n_frames].copy(),
            v_cells=tr_v[:n_frames].copy(),
            cell_position=np.arange(grid_point_count, dtype=np.float64)
            * (float(celerity) * float(substep_duration)),
            cell_kind=np.arange(grid_point_count) % 2,
            moving_fraction=interleave(jc.frac_a, jc.frac_b),
        )
    return Trace(**fields)
