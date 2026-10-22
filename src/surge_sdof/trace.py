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
``PeakResponse.history``); ``phase`` is 0 in the transit (delay) phase, 1 in the history
(ramp) phase and 2 in free decay. Frame 0 is the end of sub-step 0: a column at rest with
``a = 0`` is still bitwise the initial column there.

Free decay is traced for as long as the history records it (``totInd <= outMax * 2``, the
``_record`` guard of the kernel); later free-decay sub-steps are integrated but not traced,
as the history drops them. The arrays are allocated once for that window (``capacity``)
and sliced to the frames written.

``f_friction = mass * dv_friction / dt`` where ``dv_friction = v_new - (v_old + (a_old +
a_new) * (dt / 2))`` is the velocity the Coulomb branch of ``structure.step_scalars`` added
or removed in the sub-step, recomputed in the recording branch from the same doubles the
kernel formed (``half_dt = dt / 2``; ``v + av``): in slip it is ``-+fric_acc`` (``0.0``
exactly with ``dynamicFric = 0``; the D-20 dead zone gives ``0.0`` too), in stick
(``|v_old| < fric_acc``) it is ``av - (v_old + av)``, the momentum the stick removed, so
``f_friction`` there is the holding force. ``stick`` is that test.

JC column layout
----------------
The staggered grid is stored **interleaved**: ``A0 B0 A1 B1 ... A(N-1) B(N-1) A(N)``,
``n_cells = 2N + 1`` (``cell_kind`` 0 = A node, 1 = B cell). ``cell_position`` is
``j * celerity * dt`` m from the first A node (a cell is ``2 c dt`` long; the column runs
``ext_qty`` end cells, the leg up to the pivot, the span between the pivots, the other leg
and ``ext_qty`` end cells, see ``moc.grid_size``). ``moving_fraction`` is ``frac_a`` /
``frac_b`` interleaved the same way, the values ``moc.step`` multiplies ``a dt`` by
(``frac_a[0]`` and ``frac_a[N]`` are the unused zeros of ``moc.interp_fractions``).
``p_cells`` and ``v_cells`` are copies of the four arrays exactly as the model stores them:
pressures in Pa, velocities in m/s relative to the pipe, after the acceleration injection
and the ``vAv`` subtraction of the sub-step.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from surge_sdof.structure import SdofParams

__all__ = [
    "MAX_TRACE_VALUES",
    "PHASE_TRANSIT",
    "PHASE_HISTORY",
    "PHASE_FREE_DECAY",
    "Trace",
    "capacity",
    "check_memory",
    "allocate",
    "interleave",
    "build",
]

PHASE_TRANSIT = 0
PHASE_HISTORY = 1
PHASE_FREE_DECAY = 2

# Columns of the kernel's float64 frame array ``tr_f (capacity, N_FLOAT_COLUMNS)``.
F_X, F_V, F_A, F_FA, F_FB, F_FU, F_FFRIC, F_DF = range(8)
N_FLOAT_COLUMNS = 8
# Columns of the int64 frame array ``tr_i (capacity, N_INT_COLUMNS)``.
I_SUB_STEP, I_SAMPLE, I_PHASE, I_STICK = range(4)
N_INT_COLUMNS = 4

MAX_TRACE_VALUES = 50_000_000
"""Memory guard: the largest number of 8-byte values (``capacity * (float columns + int
columns + 2 * n_cells)``, 400 MB) a trace may allocate; ``check_memory`` raises
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
        ``(mass, stiffness, damping, fric_acc, gap, ratio2)`` of the run (kg, N/m, N·s/m,
        m/s, m, dimensionless).
    inputs : dict
        The case inputs as the solver received them (``force_history`` as the 2-D array
        the walk used; the JC keyword flags included), so the trace is self-describing.
    t, sub_step, sample, phase : numpy.ndarray
        Per frame: time at the end of the sub-step (s), the 0-based sub-step index, the
        0-based sample index, the phase (0 transit, 1 history, 2 free decay).
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
        cell, and the interp fraction of the cell (dimensionless).
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


def capacity(
    forced_substeps: int, forced_samples: int, out_max: int, step_qty: int, trace_every: int
) -> int:
    """Frames to allocate: the forced phases (``forced_substeps`` sub-steps, known from the
    unbalance schedule) plus free decay up to the history window (``outMax * 2`` samples
    in all), every ``trace_every``-th sub-step; 0 when not tracing.

    Parameters
    ----------
    forced_substeps : int
        Sub-steps of phases 1-2 (the length of the flat unbalance array).
    forced_samples : int
        Samples of phases 1-2.
    out_max : int
        The VBA ``outMax``.
    step_qty : int
        Sub-steps per sample.
    trace_every : int
        Stride in sub-steps, 0 for no trace.

    Returns
    -------
    int
    """
    if trace_every <= 0:
        return 0
    decay_substeps = max(0, out_max * 2 - forced_samples) * step_qty
    return -(-(forced_substeps + decay_substeps) // trace_every)  # ceil


def check_memory(
    forced_substeps: int,
    forced_samples: int,
    out_max: int,
    step_qty: int,
    trace_every: int,
    n_cells: int,
) -> int:
    """The trace capacity, or ``ValueError`` when it would exceed ``MAX_TRACE_VALUES``.

    Parameters
    ----------
    forced_substeps, forced_samples, out_max, step_qty, trace_every
        As ``capacity``.
    n_cells : int
        ``2N + 1`` for a JC run, 0 for lumped.

    Returns
    -------
    int
        ``capacity(...)``.

    Raises
    ------
    ValueError
        When ``capacity * (N_FLOAT_COLUMNS + N_INT_COLUMNS + 2 * n_cells)`` exceeds
        ``MAX_TRACE_VALUES`` (this includes the ``n_frames * n_cells`` of each column
        array); the message names the smallest ``trace_every`` that fits.
    """
    per_frame = N_FLOAT_COLUMNS + N_INT_COLUMNS + 2 * n_cells
    cap = capacity(forced_substeps, forced_samples, out_max, step_qty, trace_every)
    if cap * per_frame <= MAX_TRACE_VALUES:
        return cap
    stride = max(trace_every + 1, math.ceil(cap * trace_every * per_frame / MAX_TRACE_VALUES))
    while capacity(forced_substeps, forced_samples, out_max, step_qty, stride) * per_frame > (
        MAX_TRACE_VALUES
    ):
        stride += 1
    raise ValueError(
        f"trace_every={trace_every} would record {cap} frames x {per_frame} values "
        f"({cap * per_frame:.3g} > {MAX_TRACE_VALUES:.3g} 8-byte values, "
        f"{cap * n_cells:.3g} per column array); use trace_every >= {stride}"
    )


def allocate(cap: int, n_cells: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """``(tr_f, tr_i, tr_p, tr_v)`` zeroed for the kernel: ``(cap, N_FLOAT_COLUMNS)``
    float64, ``(cap, N_INT_COLUMNS)`` int64 and two ``(cap, n_cells)`` float64 (``n_cells``
    is 0 for lumped; both are ``(0, 0)`` when ``cap`` is 0).

    Parameters
    ----------
    cap : int
        From ``capacity`` / ``check_memory``.
    n_cells : int
        ``2N + 1`` or 0.
    """
    cells = n_cells if cap > 0 else 0
    return (
        np.zeros((cap, N_FLOAT_COLUMNS)),
        np.zeros((cap, N_INT_COLUMNS), dtype=np.int64),
        np.zeros((cap, cells)),
        np.zeros((cap, cells)),
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


def build(
    solver: str,
    inputs: dict,
    trace_every: int,
    dt: float,
    step_qty: int,
    out_max: int,
    params: SdofParams,
    n_frames: int,
    tr_f: np.ndarray,
    tr_i: np.ndarray,
    tr_p: np.ndarray,
    tr_v: np.ndarray,
    jc=None,
    celerity: float = 0.0,
    ext_qty: int = 0,
) -> Trace:
    """Assemble the ``Trace`` from the kernel's arrays, sliced to ``n_frames`` (copies, so
    the unused capacity is released).

    Parameters
    ----------
    solver, inputs, trace_every, dt, step_qty, out_max, params
        The one-off fields.
    n_frames : int
        Frames the kernel wrote.
    tr_f, tr_i, tr_p, tr_v : numpy.ndarray
        From ``allocate``, filled by the kernel.
    jc : coupling.JunctionCoupling or None
        The junction of a JC run (its grid and interp fractions), None for lumped.
    celerity : float
        Pressure-wave speed, m/s (cell positions); unused for lumped.
    ext_qty : int
        ``moc.EXT_QTY`` for a JC run.
    """
    f = tr_f[:n_frames]
    ints = tr_i[:n_frames]
    sub_step = ints[:, I_SUB_STEP].copy()
    fields = {
        "solver": solver,
        "trace_every": int(trace_every),
        "dt": float(dt),
        "step_qty": int(step_qty),
        "out_max": int(out_max),
        "params": params,
        "inputs": inputs,
        "t": (sub_step + 1) * float(dt),
        "sub_step": sub_step,
        "sample": ints[:, I_SAMPLE].copy(),
        "phase": ints[:, I_PHASE].copy(),
        "x": f[:, F_X].copy(),
        "v": f[:, F_V].copy(),
        "a": f[:, F_A].copy(),
        "f_a": f[:, F_FA].copy(),
        "f_b": f[:, F_FB].copy(),
        "f_unbalance": f[:, F_FU].copy(),
        "f_friction": f[:, F_FFRIC].copy(),
        "stick": ints[:, I_STICK] != 0,
        "d_f": f[:, F_DF].copy(),
    }
    if jc is not None:
        n_seg = int(jc.n_seg)
        n_cells = 2 * n_seg + 1
        fields.update(
            n_cells=n_cells,
            pivot_seg_qty=int(jc.pivot),
            pipe_seg_qty=n_seg,
            ext_qty=int(ext_qty),
            p_cells=tr_p[:n_frames].copy(),
            v_cells=tr_v[:n_frames].copy(),
            cell_position=np.arange(n_cells, dtype=np.float64) * (float(celerity) * float(dt)),
            cell_kind=np.arange(n_cells) % 2,
            moving_fraction=interleave(jc.frac_a, jc.frac_b),
        )
    return Trace(**fields)
