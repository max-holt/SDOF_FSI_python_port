"""The solver trace for visualisation (Session V.1): ``Trace`` and its helpers.

``peak_response(..., trace_every=k)`` and ``peak_response_jc(..., trace_every=k)`` record
every ``k``-th sub-step into preallocated arrays inside ``response._integrate_kernel`` and
return the result as ``PeakResponse.trace``. With ``trace_every = 0`` (the default) the
kernel takes empty arrays and never enters the recording branch; the state arithmetic is
the same in both cases, so a traced run returns the same ``PeakResponse`` values bitwise
(``tests/test_trace.py``).

The kernel writes each frame through the two compiled writers here (``write_frame_row``,
the scalars of a ``FrameRow``; ``write_frame_column``, the interleaved column), called by
``response._record_frame`` on recorded sub-steps only (review session R.7, plan 4.8).

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
kernel formed (``structure.substep_friction``, ``half_dt = dt / 2``): in slip it is
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
and ``ext_qty`` end cells, see ``moc.grid_size``). ``moving_fraction`` is the column's
``moving_fraction_a`` / ``moving_fraction_b`` interleaved the same way, the values
``moc.step`` multiplies ``a dt`` by (``moving_fraction_a[0]`` and ``moving_fraction_a[N]``
are the unused zeros of ``moc.moving_fractions``).
``p_cells`` and ``v_cells`` are copies of the four arrays exactly as the model stores them:
pressures in Pa, velocities in m/s relative to the pipe, after the acceleration injection
and the ``vAv`` subtraction of the sub-step.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

import numba
import numpy as np

from surge_sdof import moc
from surge_sdof.loads import PHASE_FORCED, PHASE_TRANSIT
from surge_sdof.structure import SdofParams

if TYPE_CHECKING:
    from surge_sdof.response import RunSettings

__all__ = [
    "MAX_TRACE_VALUES",
    "FRAME_COLUMNS",
    "INT_FRAME_COLUMNS",
    "PHASE_TRANSIT",
    "PHASE_FORCED",
    "PHASE_FREE_DECAY",
    "Trace",
    "frame_capacity",
    "check_memory",
    "TraceRequest",
    "TraceBuffers",
    "allocate_frames",
    "interleave",
    "InterleavedGrid",
    "interleaved_grid",
    "build_trace",
    "FrameRow",
    "write_frame_row",
    "write_frame_column",
]

# PHASE_TRANSIT and PHASE_FORCED are produced by ``loads`` and re-exported here with the
# third code, which only the solver loop records.
PHASE_FREE_DECAY = 2  # no unbalance force; the structure rings down (VBA phase 3)

# Columns of the kernel's float64 frame array ``frame_state (capacity, FRAME_STATE_COLUMN_COUNT)``.
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
# Columns of the int64 frame array ``frame_index_columns (capacity, FRAME_INDEX_COLUMN_COUNT)``.
COL_SUBSTEP_INDEX, COL_SAMPLE_INDEX, COL_LOAD_PHASE, COL_IS_STICKING = range(4)

_STATE = "state"  # a column of ``TraceBuffers.frame_state`` (float64)
_INDEX = "index"  # a column of ``TraceBuffers.frame_index_columns`` (int64)
FRAME_COLUMN_TABLE = (
    # (Trace field and trace-document column, kernel array, kernel column), in the document's
    # order. ``t`` is derived from ``sub_step`` and ``dt``; ``stick`` is the int column != 0.
    ("t", None, None),
    ("sub_step", _INDEX, COL_SUBSTEP_INDEX),
    ("sample", _INDEX, COL_SAMPLE_INDEX),
    ("phase", _INDEX, COL_LOAD_PHASE),
    ("x", _STATE, COL_X),
    ("v", _STATE, COL_V),
    ("a", _STATE, COL_A),
    ("f_a", _STATE, COL_ELBOW_A_FORCE),
    ("f_b", _STATE, COL_ELBOW_B_FORCE),
    ("f_unbalance", _STATE, COL_UNBALANCE_FORCE),
    ("f_friction", _STATE, COL_FRICTION_FORCE),
    ("stick", _INDEX, COL_IS_STICKING),
    ("d_f", _STATE, COL_JUNCTION_FORCE),
)
FRAME_COLUMNS = tuple(name for name, _, _ in FRAME_COLUMN_TABLE)
"""The per-frame fields of ``Trace``: the ``trace.frames`` columns, in the document's order."""
INT_FRAME_COLUMNS = frozenset(name for name, array, _ in FRAME_COLUMN_TABLE if array == _INDEX)
"""The frame columns written as integers (the int64 kernel columns)."""
FRAME_STATE_COLUMN_COUNT = sum(array == _STATE for _, array, _ in FRAME_COLUMN_TABLE)
FRAME_INDEX_COLUMN_COUNT = sum(array == _INDEX for _, array, _ in FRAME_COLUMN_TABLE)

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
    portal_frame_height : float
        Leg height of the portal-frame proxy of the run (``response.solver_setup``), m.
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
    portal_frame_height: float
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


class TraceRequest(NamedTuple):
    """A traced run: the stride and what ``response._integrate`` needs beyond the kernel
    arrays to build a ``Trace``. Built by the solver entry points when ``trace_every > 0``.
    """

    stride: int  # trace_every > 0: record every stride-th sub-step
    solver: str
    inputs: dict
    celerity: float
    portal_frame_height: float  # m, of the run's set-up (response.solver_setup)
    elbow_force_samples: object  # the loads.elbow_forces generator


class TraceBuffers(NamedTuple):
    """The frame buffers the compiled loop fills, and the stride it fills them at.

    One type for every run: an untraced run passes zero-row buffers and a stride of 0. The
    four buffers come first, so ``buffers[2]`` is the pressure buffer.

    Attributes
    ----------
    frame_state : numpy.ndarray
        ``(capacity, FRAME_STATE_COLUMN_COUNT)`` float64: the columns ``COL_X`` ..
        ``COL_JUNCTION_FORCE`` per frame.
    frame_index_columns : numpy.ndarray
        ``(capacity, FRAME_INDEX_COLUMN_COUNT)`` int64: ``COL_SUBSTEP_INDEX`` ..
        ``COL_IS_STICKING`` per frame.
    frame_pressure, frame_velocity : numpy.ndarray
        ``(capacity, grid_point_count)`` float64: the column interleaved ``A0 B0 A1 ... AN``
        per frame, Pa and m/s (no columns for a lumped run).
    trace_every : int
        Record every ``trace_every``-th sub-step; 0 records nothing.
    """

    frame_state: np.ndarray
    frame_index_columns: np.ndarray
    frame_pressure: np.ndarray
    frame_velocity: np.ndarray
    trace_every: int


class FrameRow(NamedTuple):
    """One recorded sub-step: the values ``write_frame_row`` writes into a frame row.

    Built by ``response._record_frame``. Units: forces in N, ``x`` / ``v`` / ``a`` in m, m/s, m/s².
    """

    substep_index: int  # running 0-based sub-step counter
    sample_index: int  # 0-based sample index
    load_phase: int  # PHASE_TRANSIT, PHASE_FORCED or PHASE_FREE_DECAY
    x: float
    v: float
    a: float
    elbow_a_force: float
    elbow_b_force: float
    unbalance_force: float
    friction_force: float  # recomputed from the velocity change, as the trace defines it
    is_sticking: bool  # |v before the sub-step| < the friction velocity step
    junction_force: float  # 0.0 without fluid coupling


@numba.njit(cache=True)
def write_frame_row(buffers: TraceBuffers, frame_index: int, values: FrameRow) -> None:
    """Write the scalars of one trace frame (Session V.1): ``values`` into row
    ``frame_index`` of ``buffers.frame_state`` and ``buffers.frame_index_columns``
    (columns ``COL_*``)."""
    frame_state = buffers.frame_state
    frame_index_columns = buffers.frame_index_columns
    frame_state[frame_index, COL_X] = values.x
    frame_state[frame_index, COL_V] = values.v
    frame_state[frame_index, COL_A] = values.a
    frame_state[frame_index, COL_ELBOW_A_FORCE] = values.elbow_a_force
    frame_state[frame_index, COL_ELBOW_B_FORCE] = values.elbow_b_force
    frame_state[frame_index, COL_UNBALANCE_FORCE] = values.unbalance_force
    frame_state[frame_index, COL_FRICTION_FORCE] = values.friction_force
    frame_state[frame_index, COL_JUNCTION_FORCE] = values.junction_force
    frame_index_columns[frame_index, COL_SUBSTEP_INDEX] = values.substep_index
    frame_index_columns[frame_index, COL_SAMPLE_INDEX] = values.sample_index
    frame_index_columns[frame_index, COL_LOAD_PHASE] = values.load_phase
    frame_index_columns[frame_index, COL_IS_STICKING] = 1 if values.is_sticking else 0


@numba.njit(cache=True)
def write_frame_column(buffers: TraceBuffers, frame_index: int, column: moc.FluidColumn) -> None:
    """Write the fluid column of one trace frame: pressure and velocity interleaved ``A0 B0
    A1 ... A(N)`` into row ``frame_index`` of ``buffers.frame_pressure`` /
    ``buffers.frame_velocity``. Reads the column only."""
    frame_pressure = buffers.frame_pressure
    frame_velocity = buffers.frame_velocity
    pressure_a = column.pressure_a
    velocity_a = column.velocity_a
    pressure_b = column.pressure_b
    velocity_b = column.velocity_b
    column_cell_count = column.column_cell_count
    for c in range(column_cell_count):
        frame_pressure[frame_index, 2 * c] = pressure_a[c]
        frame_pressure[frame_index, 2 * c + 1] = pressure_b[c]
        frame_velocity[frame_index, 2 * c] = velocity_a[c]
        frame_velocity[frame_index, 2 * c + 1] = velocity_b[c]
    frame_pressure[frame_index, 2 * column_cell_count] = pressure_a[column_cell_count]
    frame_velocity[frame_index, 2 * column_cell_count] = velocity_a[column_cell_count]


def allocate_frames(frame_capacity: int, grid_point_count: int, trace_every: int) -> TraceBuffers:
    """``TraceBuffers`` zeroed for the kernel: ``(cap, FRAME_STATE_COLUMN_COUNT)``
    float64, ``(cap, FRAME_INDEX_COLUMN_COUNT)`` int64 and two ``(cap, grid_point_count)`` float64
    (``grid_point_count`` is 0 for lumped; both are ``(0, 0)`` when ``frame_capacity`` is 0).

    Parameters
    ----------
    frame_capacity : int
        From ``frame_capacity`` / ``check_memory``.
    grid_point_count : int
        ``2N + 1`` or 0.
    trace_every : int
        The stride, 0 when not tracing.
    """
    allocated_grid_point_count = grid_point_count if frame_capacity > 0 else 0
    return TraceBuffers(
        np.zeros((frame_capacity, FRAME_STATE_COLUMN_COUNT)),
        np.zeros((frame_capacity, FRAME_INDEX_COLUMN_COUNT), dtype=np.int64),
        np.zeros((frame_capacity, allocated_grid_point_count)),
        np.zeros((frame_capacity, allocated_grid_point_count)),
        trace_every,
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


class InterleavedGrid(NamedTuple):
    """The fluid column's grid as the trace lays it out: ``A0 B0 A1 ... A(N)``.

    Attributes
    ----------
    position : numpy.ndarray
        ``2N + 1`` float64: distance of each grid point from the first A node, m.
    kind : numpy.ndarray
        ``2N + 1`` ints: 0 for an A node, 1 for a B cell.
    moving_fraction : numpy.ndarray
        ``2N + 1``: the moving fractions of the A nodes and B cells, interleaved.
    column_cell_count : int
        ``N``, the cells of the column (``moc.grid_size``).
    end_to_elbow_cell_count : int
        Cells from each end of the column to the elbow between leg and span.
    """

    position: np.ndarray
    kind: np.ndarray
    moving_fraction: np.ndarray
    column_cell_count: int
    end_to_elbow_cell_count: int


def interleaved_grid(
    column_cell_count: int,
    end_to_elbow_cell_count: int,
    moving_fraction_a: np.ndarray,
    moving_fraction_b: np.ndarray,
    celerity: float,
    substep_duration: float,
) -> InterleavedGrid:
    """The ``InterleavedGrid`` of a column of ``column_cell_count`` cells: grid points
    ``celerity * substep_duration`` apart (half a cell), A nodes and B cells alternating.

    Parameters
    ----------
    column_cell_count, end_to_elbow_cell_count : int
        The grid (``moc.grid_size``).
    moving_fraction_a, moving_fraction_b : numpy.ndarray
        Length ``N + 1`` and ``N`` (``moc.moving_fractions``).
    celerity : float
        m/s.
    substep_duration : float
        s.
    """
    grid_point_count = 2 * column_cell_count + 1
    return InterleavedGrid(
        position=np.arange(grid_point_count, dtype=np.float64)
        * (float(celerity) * float(substep_duration)),
        kind=np.arange(grid_point_count) % 2,
        moving_fraction=interleave(moving_fraction_a, moving_fraction_b),
        column_cell_count=column_cell_count,
        end_to_elbow_cell_count=end_to_elbow_cell_count,
    )


def build_trace(
    request: TraceRequest,
    settings: RunSettings,
    params: SdofParams,
    buffers: TraceBuffers,
    n_frames: int,
    column: moc.FluidColumn,
) -> Trace:
    """Assemble the ``Trace`` from the kernel's arrays, sliced to ``n_frames`` (copies, so
    the unused capacity is released).

    Parameters
    ----------
    request : TraceRequest
        The solver name, its inputs and the celerity (m/s, for the cell positions).
    settings : response.RunSettings
        The sub-step, sub-steps per sample and ``outMax`` of the run.
    params : SdofParams
        The run's SDOF constants.
    buffers : TraceBuffers
        From ``allocate_frames``, filled by the kernel (its ``trace_every`` is the stride).
    n_frames : int
        Frames the kernel wrote.
    column : moc.FluidColumn
        The run's column: its grid and moving fractions with fluid coupling; the empty
        column of a lumped run adds no column fields.
    """
    solver = request.solver
    inputs = request.inputs
    celerity = request.celerity
    substep_duration = settings.substep_duration
    substep_count = settings.substep_count
    nominal_forced_sample_count = settings.nominal_forced_sample_count
    kernel_arrays = {
        _STATE: buffers.frame_state[:n_frames],
        _INDEX: buffers.frame_index_columns[:n_frames],
    }
    fields = {
        "solver": solver,
        "trace_every": int(buffers.trace_every),
        "dt": float(substep_duration),
        "step_qty": int(substep_count),
        "out_max": int(nominal_forced_sample_count),
        "portal_frame_height": float(request.portal_frame_height),
        "params": params,
        "inputs": inputs,
    }
    for name, array, column_index in FRAME_COLUMN_TABLE:
        if array is not None:
            fields[name] = kernel_arrays[array][:, column_index].copy()
    fields["t"] = (fields["sub_step"] + 1) * float(substep_duration)
    fields["stick"] = fields["stick"] != 0
    if column.is_fluid_coupled:
        grid = interleaved_grid(
            int(column.column_cell_count),
            int(column.end_to_elbow_cell_count),
            column.moving_fraction_a,
            column.moving_fraction_b,
            celerity,
            substep_duration,
        )
        fields.update(
            n_cells=int(grid.position.shape[0]),
            pivot_seg_qty=grid.end_to_elbow_cell_count,
            pipe_seg_qty=grid.column_cell_count,
            ext_qty=int(moc.INACTIVE_END_CELL_COUNT),
            p_cells=buffers.frame_pressure[:n_frames].copy(),
            v_cells=buffers.frame_velocity[:n_frames].copy(),
            cell_position=grid.position,
            cell_kind=grid.kind,
            moving_fraction=grid.moving_fraction,
        )
    return Trace(**fields)
