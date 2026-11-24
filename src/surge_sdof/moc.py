"""The 1-D method-of-characteristics (MoC) fluid column of ``GetPeakResponseJC``.

Behaviour is that of the MoC block in ``legacy/vba/Existing Code.bas`` (lines 795-847,
byte-identical in its four copies: 920-972, 1016-1068, 1113-1165) and its set-up (lines
731-734, 742-757). ``tests/test_differential.py`` replays the legacy solver's MoC block
through ``step`` bitwise.

Grid
----
``pipeSegQTY = N`` cells of length ``2 c dt`` along the whole modelled column (the span,
both legs and the end cells, not only the span between the elbows), ``pivotSegQTY`` cells
from each end to the portal-frame pivot, ``extQTY = 4`` end cells that receive no mass
acceleration. Two staggered half-grids: the A nodes ``0 .. N`` (pressure ``p_a``,
velocity ``v_a``) and the B cells ``0 .. N-1`` (``p_b``, ``v_b``), the VBA
``arrayA(0 To 1, 0 To N)`` and ``arrayB(0 To 1, 0 To N-1)`` split into four contiguous
1-D float64 arrays. Even sub-steps update the A grid from B, odd sub-steps the B grid
from A; the structure's acceleration enters as ``a dt`` weighted by the moving-fraction
profiles, which depend only on the grid and are tabulated once per run.

``step`` is one function over the four arrays and scalars with scalar loop bodies: no
per-cell helper calls and no Python objects; Stage 5 compiles it whole with ``@njit`` (``cache=True``,
no fastmath; the same source runs as Python under ``NUMBA_DISABLE_JIT=1``). The
dead ``useUndamped`` branch (``Const useUndamped = False``, the AFT infinite-pipe boundary)
is not ported; only the live decaying boundary (``dacayFactor``) is.

Approved fix F-1 (NOTES.md): the mean velocity ``vAv`` sums ``2N + 1`` terms; the VBA
divides by ``2N - 1`` (D-17). ``mean_velocity_divisor`` returns either, selected by the caller's
``vav_denominator`` flag ("legacy" | "fixed").

Approved fix F-4 (NOTES.md, DEVIATIONS D-4): the lead author replaced ``interpFractionA`` and
``interpFractionB`` (``legacy/vba/interpFraction_fix_2026-10-26.bas``); F-4b
(``legacy/vba/interpFraction_fix_2026-10-27.bas``, confirmed by the lead author 29 Oct 2026)
moves the outlet side of both one node outward (``pipeSegQTY -> pipeSegQTY + 1`` in the two
outlet tests and the outlet ramp). ``moving_fractions`` tabulates either the original
profile (``fraction_profile="legacy"``: the ``n < 3`` test of ``interpFractionB`` and the
division by zero at ``pivotSegQTY = 4``) or the corrected one (``"fixed"``, the 27 Oct
text: both profiles start at exactly 0 at ``n = 3``, one strictly monotone squared ramp per
leg, both legs the same length, A mirror-symmetric about the column centre ``N / 2`` over
the called nodes ``1 .. N - 1`` (``A(n) = A(N - n)``) and B about ``(N - 1) / 2``
(``B(n) = B(N - 1 - n)``), equal fixed blocks of ``extQTY`` nodes / cells at both ends). The
mirror identities hold when the two legs do not overlap (``N >= 2 pivot - 4`` for A,
``2 pivot - 3`` for B; the If-chain gives the inlet branch precedence otherwise), which every
grid past the short-pipe fallback (``N >= 2 pivot + 3``) satisfies.

Exactness
---------
Every expression keeps the VBA's operation order. The sweeps carry the previous cell's
values in locals instead of re-reading them, which changes nothing numerically.
``a * dt * f`` is ``(a * dt) * f`` in VBA and here ``a_dt * f``. ``2 * rhoC`` is hoisted
(the same double). This module knows nothing about the structure proxy, the force
history or output types. See ``docs/architecture.md``.
"""

from __future__ import annotations

from typing import NamedTuple

import numba
import numpy as np

from surge_sdof.vba_compat import clng

__all__ = [
    "INACTIVE_END_CELL_COUNT",
    "JUNCTION_FORCE_FILTER_WEIGHT",
    "ColumnGrid",
    "grid_size",
    "is_short_pipe",
    "end_pressure_decay_factor",
    "FRACTION_PROFILES",
    "display_moving_fractions",
    "moving_fraction_a",
    "moving_fraction_b",
    "moving_fraction_a_fixed",
    "moving_fraction_b_fixed",
    "moving_fractions",
    "column_at_rest",
    "mean_velocity_divisor",
    "FluidColumn",
    "empty_column",
    "step",
]

INACTIVE_END_CELL_COUNT = 4
"""VBA ``Const extQTY = 4``: cells at each end that receive no mass acceleration."""

LEGACY_B_INACTIVE_START_CELL_COUNT = 3
"""VBA ``interpFractionB``'s first test ``n < 3`` (line 124): B cells at the start of the
column that receive no mass acceleration on the legacy profile. VBA quirk D-4 preserved:
``interpFractionA`` and the far end use ``extQTY`` (4) instead."""

JUNCTION_FORCE_FILTER_WEIGHT = 0.25
"""VBA ``Const dampingA = 0.25``: weight of the previous junction force ``dF`` in its first-order
low-pass filter (not a damping)."""

FRACTION_PROFILES = ("legacy", "fixed")
"""Values of the ``fraction_profile`` flag: the original ``interpFractionA/B`` (D-4
included) or the lead author's corrected functions (approved fix F-4)."""


# VBA lines 733-734
class ColumnGrid(NamedTuple):
    """The size of the MoC grid: ``N`` cells in the whole column (VBA ``pipeSegQTY``)
    and the cells from each end to the elbow at the foot of the leg (VBA ``pivotSegQTY``).
    """

    column_cell_count: int
    end_to_elbow_cell_count: int


def grid_size(
    span_length: float, portal_frame_height: float, celerity: float, substep_duration: float
) -> ColumnGrid:
    """``(pipeSegQTY, pivotSegQTY)`` of the MoC grid (VBA lines 733-734).

    Parameters
    ----------
    span_length : float
        Length between elbows, m.
    portal_frame_height : float
        From ``structure.solve_portal_height``, m.
    celerity : float
        Pressure-wave speed, m/s.
    substep_duration : float
        Sub-step, s; a cell is ``2 * celerity * dt`` long.

    Returns
    -------
    ColumnGrid
        ``pipeSegQTY`` (cells in the whole column: the span, about ``L / (2 c dt)`` cells,
        plus ``pivotSegQTY + 1`` cells at each end; even by construction) and
        ``pivotSegQTY`` (cells from each end to the pivot, ``extQTY`` + the rounded
        height in cells; ``CLng`` rounds half to even).
    """
    end_to_elbow_cell_count = INACTIVE_END_CELL_COUNT + clng(
        portal_frame_height / (2 * celerity * substep_duration)
    )
    # Proposed derivation, for Ben to confirm: a grid segment is 2 * celerity * dt long, and
    # the count is halved, rounded and doubled so the number of segments is even:
    # L / (4 c dt) is half the span's segment count.
    column_cell_count = (
        2 + clng(span_length / (4 * celerity * substep_duration) + end_to_elbow_cell_count) * 2
    )
    return ColumnGrid(column_cell_count, end_to_elbow_cell_count)


# VBA line 736
def is_short_pipe(column_cell_count: int, end_to_elbow_cell_count: int) -> bool:
    """``pipeSegQTY - 2 * pivotSegQTY <= 2`` (VBA line 736): the span cannot hold the MoC
    grid and ``GetPeakResponseJC`` falls back to the lumped solver.

    Parameters
    ----------
    column_cell_count, end_to_elbow_cell_count : int
        From ``grid_size``.

    Returns
    -------
    bool
    """
    return column_cell_count - 2 * end_to_elbow_cell_count <= 2


# VBA line 731
def end_pressure_decay_factor(
    celerity: float, substep_duration: float, span_length: float
) -> float:
    """``dacayFactor = 2 ^ ((celerity * dt) / physicalLength)`` (VBA line 731).

    Parameters
    ----------
    celerity : float
        Pressure-wave speed, m/s.
    substep_duration : float
        Sub-step, s.
    span_length : float
        Length between elbows, m.

    Returns
    -------
    float
        Dimensionless factor ``2 ** (c dt / L)`` by which the end-node pressure is divided
        at every even update, once every ``2 dt``. Compounded over ``L / (c dt)`` even
        updates, ``2 L / c`` seconds, it makes a factor of 2: a half-life of two transits
        of the length ``L``, not one.
    """
    return 2 ** ((celerity * substep_duration) / span_length)


# VBA line 105: Function interpFractionA(n As Long, pivotSegQTY As Long, pipeSegQTY As Long)
def moving_fraction_a(n: int, end_to_elbow_cell_count: int, column_cell_count: int) -> float:
    """Cell-centred weighting of the mass acceleration at A node ``n`` (VBA line 105).

    Literal copy of ``legacy_port.interp_fraction_a`` so this module does not import the
    frozen legacy module.

    Parameters
    ----------
    n : int
        A node index, ``0 .. pipeSegQTY``.
    end_to_elbow_cell_count, column_cell_count : int
        From ``grid_size``.

    Returns
    -------
    float
        0 in the ``extQTY`` end cells, a squared ramp up to the pivot, 1 between the
        pivots; dimensionless.
    """
    if n < INACTIVE_END_CELL_COUNT:
        return 0.0
    elif n < end_to_elbow_cell_count:
        return (
            (n - 0.5 - INACTIVE_END_CELL_COUNT)
            / (end_to_elbow_cell_count - INACTIVE_END_CELL_COUNT)
        ) ** 2
    elif n > column_cell_count - INACTIVE_END_CELL_COUNT:
        return 0.0
    elif n > column_cell_count - end_to_elbow_cell_count:
        return (
            (column_cell_count - 0.5 - INACTIVE_END_CELL_COUNT - n)
            / (end_to_elbow_cell_count - INACTIVE_END_CELL_COUNT)
        ) ** 2
    else:
        return 1.0


# VBA line 121: Function interpFractionB(n As Long, pivotSegQTY As Long, pipeSegQTY As Long)
def moving_fraction_b(n: int, end_to_elbow_cell_count: int, column_cell_count: int) -> float:
    """Node-centred weighting of the mass acceleration at B cell ``n`` (VBA line 121).

    Literal copy of ``legacy_port.interp_fraction_b``.

    Parameters
    ----------
    n : int
        B cell index, ``0 .. pipeSegQTY - 1``.
    end_to_elbow_cell_count, column_cell_count : int
        From ``grid_size``.

    Returns
    -------
    float
        Dimensionless weight, as ``moving_fraction_a`` but node-centred.

    Notes
    -----
    VBA quirk D-4 preserved: the first test is ``n < 3`` where ``moving_fraction_a`` uses
    ``n < extQTY`` (4), so ``n = 3`` takes the ramp branch and ``pivotSegQTY = 4``
    divides by zero.
    """
    if n < LEGACY_B_INACTIVE_START_CELL_COUNT:  # VBA quirk D-4 preserved
        return 0.0
    elif n < end_to_elbow_cell_count:
        return (
            (n - INACTIVE_END_CELL_COUNT) / (end_to_elbow_cell_count - INACTIVE_END_CELL_COUNT)
        ) ** 2
    elif n > column_cell_count - INACTIVE_END_CELL_COUNT:
        return 0.0
    elif n > column_cell_count - end_to_elbow_cell_count:
        return (
            (column_cell_count - 1 - INACTIVE_END_CELL_COUNT - n)
            / (end_to_elbow_cell_count - INACTIVE_END_CELL_COUNT)
        ) ** 2
    else:
        return 1.0


# interpFraction_fix_2026-10-27.bas: Function interpFractionA(n As Long, pivotSegQTY As Long, pipeSegQTY As Long)
def moving_fraction_a_fixed(n: int, end_to_elbow_cell_count: int, column_cell_count: int) -> float:
    """``moving_fraction_a`` as corrected by the lead author (approved fix F-4, outlet side
    moved one node outward by F-4b).

    Literal transcription of ``legacy/vba/interpFraction_fix_2026-10-27.bas``; the tests
    are on ``n + 1`` as written there.

    Parameters
    ----------
    n : int
        A node index, ``0 .. pipeSegQTY``.
    end_to_elbow_cell_count, column_cell_count : int
        From ``grid_size``.

    Returns
    -------
    float
        0 for ``n <= 3`` and ``n >= pipeSegQTY - 3``, the squared ramp
        ``((n + 0.5 - 4) / (pivot - 4))^2`` for ``4 <= n <= pivot - 2`` and its mirror
        ``A(N - n)`` on the outlet leg (``N - pivot + 2 <= n <= N - 4``), 1 between;
        dimensionless. At ``pivotSegQTY = 4`` the ramp branch is unreachable (the zero test
        covers it), so nothing divides by zero here.
    """
    if n + 1 < INACTIVE_END_CELL_COUNT + 0.5:
        return 0.0
    elif n + 1 < end_to_elbow_cell_count:
        return (
            (n + 0.5 - INACTIVE_END_CELL_COUNT)
            / (end_to_elbow_cell_count - INACTIVE_END_CELL_COUNT)
        ) ** 2
    elif n + 1 > column_cell_count + 1 - INACTIVE_END_CELL_COUNT + 0.5:
        return 0.0
    elif n + 1 > column_cell_count + 2 - end_to_elbow_cell_count:
        return (
            (column_cell_count + 1 - INACTIVE_END_CELL_COUNT - n - 0.5)
            / (end_to_elbow_cell_count - INACTIVE_END_CELL_COUNT)
        ) ** 2
    else:
        return 1.0


# interpFraction_fix_2026-10-27.bas: Function interpFractionB(n As Long, pivotSegQTY As Long, pipeSegQTY As Long)
def moving_fraction_b_fixed(n: int, end_to_elbow_cell_count: int, column_cell_count: int) -> float:
    """``moving_fraction_b`` as corrected by the lead author (approved fix F-4, outlet side
    moved one cell outward by F-4b).

    Literal transcription of ``legacy/vba/interpFraction_fix_2026-10-27.bas``. The first
    test is ``n + 1 < extQTY + 0.5`` as in the A profile, so ``n = 3`` is 0 (D-4 fixed).

    Parameters
    ----------
    n : int
        B cell index, ``0 .. pipeSegQTY - 1``.
    end_to_elbow_cell_count, column_cell_count : int
        From ``grid_size``.

    Returns
    -------
    float
        0 for ``n <= 3`` and ``n >= pipeSegQTY - 4``, the squared ramp
        ``((n + 1 - 4) / (pivot - 4))^2`` for ``4 <= n <= pivot - 2`` and its mirror
        ``B(N - 1 - n)`` on the outlet leg (``N - pivot + 1 <= n <= N - 5``), 1 between;
        dimensionless. As for the A profile the ramp is unreachable at ``pivotSegQTY = 4``.
    """
    if n + 1 < INACTIVE_END_CELL_COUNT + 0.5:
        return 0.0
    elif n + 1 < end_to_elbow_cell_count:
        return (
            (n + 1 - INACTIVE_END_CELL_COUNT) / (end_to_elbow_cell_count - INACTIVE_END_CELL_COUNT)
        ) ** 2
    elif n + 1 > column_cell_count + 1 - INACTIVE_END_CELL_COUNT - 0.5:
        return 0.0
    elif n + 1 > column_cell_count + 1.5 - end_to_elbow_cell_count:
        return (
            (column_cell_count + 1 - INACTIVE_END_CELL_COUNT - n - 1)
            / (end_to_elbow_cell_count - INACTIVE_END_CELL_COUNT)
        ) ** 2
    else:
        return 1.0


def moving_fractions(
    column_cell_count: int, end_to_elbow_cell_count: int, fraction_profile: str = "fixed"
) -> tuple[np.ndarray, np.ndarray]:
    """The two profiles tabulated once per grid.

    Parameters
    ----------
    column_cell_count, end_to_elbow_cell_count : int
        From ``grid_size``.
    fraction_profile : {"fixed", "legacy"}, optional
        ``"fixed"`` (default): the lead author's corrected functions (approved fix F-4,
        ``moving_fraction_a_fixed`` / ``moving_fraction_b_fixed``); ``"legacy"``: the VBA
        ``interpFractionA/B`` of ``Existing Code.bas`` (D-4 included).

    Returns
    -------
    fractions_a : numpy.ndarray
        Length ``N + 1``; ``fractions_a[n]`` for the A nodes ``n = 1 .. N-1`` (elements 0 and
        ``N`` are never used by ``step`` and are 0).
    fractions_b : numpy.ndarray
        Length ``N``; ``fractions_b[n]`` for the B cells ``n = 0 .. N-1``.

    Raises
    ------
    ValueError
        Unknown ``fraction_profile``; or, on the fixed profile, ``pivotSegQTY <= extQTY``
        (the portal-frame height rounds to no cell: the ramp needs ``pivot > ext``). This
        guard is an addition of the port: the corrected VBA expressions never reach the
        ramp at ``pivotSegQTY = 4`` and would return a 0 -> 1 step.
    ZeroDivisionError
        ``pivotSegQTY = 4`` on the legacy profile (D-4), here at set-up where the legacy
        solver raised it in its first MoC update.
    """
    if fraction_profile not in FRACTION_PROFILES:
        raise ValueError(
            f"fraction_profile must be one of {FRACTION_PROFILES}, got {fraction_profile!r}"
        )
    if fraction_profile == "fixed":
        if end_to_elbow_cell_count <= INACTIVE_END_CELL_COUNT:
            raise ValueError(
                f"pivotSegQTY = {end_to_elbow_cell_count} <= extQTY = {INACTIVE_END_CELL_COUNT}: "
                "the fixed fraction "
                "profile needs pivot > ext (the portal-frame height rounds to no MoC cell)"
            )
        profile_a, profile_b = moving_fraction_a_fixed, moving_fraction_b_fixed
    else:
        profile_a, profile_b = moving_fraction_a, moving_fraction_b
    fractions_a = np.zeros(column_cell_count + 1)
    fractions_b = np.zeros(column_cell_count)
    for n in range(1, column_cell_count):
        fractions_a[n] = profile_a(n, end_to_elbow_cell_count, column_cell_count)
    for n in range(0, column_cell_count):
        fractions_b[n] = profile_b(n, end_to_elbow_cell_count, column_cell_count)
    return fractions_a, fractions_b


def display_moving_fractions(
    column_cell_count: int, end_to_elbow_cell_count: int
) -> tuple[np.ndarray, np.ndarray]:
    """The moving fractions the loop picture shows for a grid (``viz.geometry``); display
    only, no solver uses them.

    ``moving_fractions`` with the solver's default profile; for a grid that profile refuses
    (``pivotSegQTY <= extQTY``: the portal-frame height rounds to no cell), the legacy
    profiles, B with the A profile's ``n < extQTY`` test in place of D-4's ``n < 3`` (the
    legacy B profile divides by zero there).

    Parameters
    ----------
    column_cell_count, end_to_elbow_cell_count : int
        From ``grid_size``.

    Returns
    -------
    fractions_a, fractions_b : numpy.ndarray
        As ``moving_fractions``.
    """
    if end_to_elbow_cell_count > INACTIVE_END_CELL_COUNT:
        return moving_fractions(column_cell_count, end_to_elbow_cell_count)
    moving_fraction_a_display = np.zeros(column_cell_count + 1)
    moving_fraction_b_display = np.zeros(column_cell_count)
    for n in range(1, column_cell_count):
        moving_fraction_a_display[n] = moving_fraction_a(
            n, end_to_elbow_cell_count, column_cell_count
        )
    for n in range(INACTIVE_END_CELL_COUNT, column_cell_count):
        moving_fraction_b_display[n] = moving_fraction_b(
            n, end_to_elbow_cell_count, column_cell_count
        )
    return moving_fraction_a_display, moving_fraction_b_display


def column_at_rest(column_cell_count: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """``(p_a, v_a, p_b, v_b)`` at rest.

    Parameters
    ----------
    column_cell_count : int
        ``N``.

    Returns
    -------
    tuple of numpy.ndarray
        The VBA ``arrayA(0 To 1, 0 To N)`` and ``arrayB(0 To 1, 0 To N-1)`` zeroed, as
        four contiguous float64 arrays: pressures in Pa (``rhoC * v``), velocities in m/s.
    """
    return (
        np.zeros(column_cell_count + 1),
        np.zeros(column_cell_count + 1),
        np.zeros(column_cell_count),
        np.zeros(column_cell_count),
    )


def mean_velocity_divisor(column_cell_count: int, vav_denominator: str) -> int:
    """Divisor of the mean-velocity sum (``2N + 1`` terms).

    Parameters
    ----------
    column_cell_count : int
        ``N``.
    vav_denominator : {"legacy", "fixed"}
        ``"legacy"``: ``2 * pipeSegQTY - 1`` (VBA line 802, quirk D-17); ``"fixed"``:
        ``2 * pipeSegQTY + 1`` (approved fix F-1).

    Returns
    -------
    int

    Raises
    ------
    ValueError
        Any other string.
    """
    if vav_denominator == "legacy":
        return 2 * column_cell_count - 1
    if vav_denominator == "fixed":
        return 2 * column_cell_count + 1
    raise ValueError(f"vav_denominator must be 'legacy' or 'fixed', got {vav_denominator!r}")


class FluidColumn(NamedTuple):
    """The MoC fluid column: its state arrays, grid and fluid constants.

    One object for both solvers, so the compiled loop has one type: a junction-coupling
    run passes the column ``coupling.fluid_column`` builds, the lumped run
    ``empty_column()``. The arrays are updated in place by ``step``; the junction force
    evolves and is passed alongside, not held here.

    Attributes
    ----------
    pressure_a, velocity_a : numpy.ndarray
        Pressure (Pa) and velocity (m/s) on the A nodes ``0 .. N``.
    pressure_b, velocity_b : numpy.ndarray
        Pressure (Pa) and velocity (m/s) on the B cells ``0 .. N-1``.
    moving_fraction_a, moving_fraction_b : numpy.ndarray
        From ``moving_fractions``, dimensionless.
    column_cell_count : int
        ``N`` (VBA ``pipeSegQTY``).
    end_to_elbow_cell_count : int
        Cells from each end to the elbow at the foot of the leg (VBA ``pivotSegQTY``).
    rho_c : float
        Characteristic impedance ``fluidDensty * celerity``, Pa·s/m.
    end_pressure_decay_factor : float
        From ``end_pressure_decay_factor``, dimensionless.
    mean_velocity_divisor : int
        From ``mean_velocity_divisor``.
    flow_area : float
        Internal cross-sectional area, m².
    is_fluid_coupled : bool
        Fluid coupling on (a junction-coupling run) or off (the empty column of a lumped
        run); the compiled loop advances the column and adds the junction force only when
        it is on.
    """

    pressure_a: np.ndarray
    velocity_a: np.ndarray
    pressure_b: np.ndarray
    velocity_b: np.ndarray
    moving_fraction_a: np.ndarray
    moving_fraction_b: np.ndarray
    column_cell_count: int
    end_to_elbow_cell_count: int
    rho_c: float
    end_pressure_decay_factor: float
    mean_velocity_divisor: int
    flow_area: float
    is_fluid_coupled: bool


def empty_column() -> FluidColumn:
    """The column of a run without fluid coupling: six empty arrays and placeholder values
    of the same types as a real column's, which the compiled loop never reads."""
    no_column = np.zeros(0)
    return FluidColumn(
        no_column,
        no_column,
        no_column,
        no_column,
        no_column,
        no_column,
        0,
        0,
        0.0,
        1.0,
        1,
        0.0,
        False,
    )


@numba.njit(cache=True)
def step(
    is_even_substep: bool,
    structure_velocity_step: float,
    column: FluidColumn,
    junction_force: float,
) -> float:
    """One MoC sub-step in place (VBA lines 795-847) and the new junction force ``dF``.

    Parameters
    ----------
    is_even_substep : bool
        Half-grid to update. Even sub-steps update the A nodes from the B cells
        (mean-velocity subtraction, decaying end nodes, then the B velocities receive
        the mass acceleration); odd sub-steps update the B cells from the A nodes (then
        the A velocities receive the mass acceleration).
    structure_velocity_step : float
        Structure acceleration times the sub-step, ``a * dt``, m/s.
    column : FluidColumn
        The column; its four state arrays are updated in place.
    junction_force : float
        Junction force after the previous sub-step, N.

    Returns
    -------
    float
        ``dampingA * dF + (1 - dampingA) * fluidArea * (pressure difference across the
        two pivots)``, N (Pa·m²).

    Notes
    -----
    * Every expression keeps the VBA's operation order; the previous cell's values are
      carried in locals, ``2 * rhoC`` is hoisted (the same double).
    * VBA quirk D-17: the divisor of the mean velocity is the column's ``mean_velocity_divisor``.
    * The dead ``useUndamped`` branch (VBA lines 803-818) is not ported.
    * Stage 5: compiled with ``numba.njit(cache=True)`` (no fastmath), body unchanged;
      with ``NUMBA_DISABLE_JIT=1`` it is this Python function. Inside the compiled
      function ``numpy.errstate`` does not apply: ``rho_c = 0`` is rejected by the
      caller's set-up (``response.peak_response_jc``, D-9) and an overflow propagates
      nan/inf to the structure state, where the end-of-run check raises (D-23).
    """
    pressure_a = column.pressure_a
    velocity_a = column.velocity_a
    pressure_b = column.pressure_b
    velocity_b = column.velocity_b
    fractions_a = column.moving_fraction_a
    fractions_b = column.moving_fraction_b
    column_cell_count = column.column_cell_count
    end_to_elbow_cell_count = column.end_to_elbow_cell_count
    rho_c = column.rho_c
    decay_factor = column.end_pressure_decay_factor
    velocity_divisor = column.mean_velocity_divisor
    flow_area = column.flow_area
    two_rho_c = 2 * rho_c
    if is_even_substep:
        # vAv = arrayA(1, N) + sum over n = 0 .. N-1 of arrayA(1, n) + arrayB(1, n)
        mean_velocity = velocity_a[column_cell_count]
        for n in range(0, column_cell_count):
            mean_velocity = mean_velocity + velocity_a[n]
            mean_velocity = mean_velocity + velocity_b[n]
        mean_velocity = mean_velocity / velocity_divisor
        # decaying boundary (the live branch; useUndamped is dead and not ported)
        pressure_a[0] = pressure_b[0] / decay_factor
        pressure_a[column_cell_count] = pressure_b[column_cell_count - 1] / decay_factor
        velocity_a[0] = velocity_b[0] - mean_velocity
        velocity_a[column_cell_count] = velocity_b[column_cell_count - 1] - mean_velocity
        # A nodes 1 .. N-1 from B cells n-1 and n
        pressure_b_lower = pressure_b[0]
        velocity_b_lower = velocity_b[0]
        for n in range(1, column_cell_count):
            pressure_b_upper = pressure_b[n]
            velocity_b_upper = velocity_b[n]
            pressure_a[n] = (pressure_b_lower + pressure_b_upper) / 2 + rho_c * (
                velocity_b_lower - velocity_b_upper
            ) / 2
            velocity_a[n] = (
                structure_velocity_step * fractions_a[n]
                - mean_velocity
                + (pressure_b_lower - pressure_b_upper) / two_rho_c
                + (velocity_b_lower + velocity_b_upper) / 2
            )
            pressure_b_lower = pressure_b_upper
            velocity_b_lower = velocity_b_upper
        # B velocities receive the mass acceleration and lose the mean velocity
        for n in range(0, column_cell_count):
            velocity_b[n] = structure_velocity_step * fractions_b[n] - mean_velocity + velocity_b[n]
        junction_force = (
            JUNCTION_FORCE_FILTER_WEIGHT * junction_force
            + (1 - JUNCTION_FORCE_FILTER_WEIGHT)
            * flow_area
            * (
                pressure_a[end_to_elbow_cell_count]
                + pressure_a[end_to_elbow_cell_count - 1]
                - pressure_a[column_cell_count - end_to_elbow_cell_count]
                - pressure_a[column_cell_count - end_to_elbow_cell_count + 1]
            )
            / 2
        )
    else:
        # B cells 0 .. N-1 from A nodes n and n+1
        pressure_a_lower = pressure_a[0]
        velocity_a_lower = velocity_a[0]
        for n in range(0, column_cell_count):
            pressure_a_upper = pressure_a[n + 1]
            velocity_a_upper = velocity_a[n + 1]
            pressure_b[n] = (pressure_a_lower + pressure_a_upper) / 2 + rho_c * (
                velocity_a_lower - velocity_a_upper
            ) / 2
            velocity_b[n] = (
                structure_velocity_step * fractions_b[n]
                + (pressure_a_lower - pressure_a_upper) / two_rho_c
                + (velocity_a_lower + velocity_a_upper) / 2
            )
            pressure_a_lower = pressure_a_upper
            velocity_a_lower = velocity_a_upper
        # A velocities receive the mass acceleration
        for n in range(1, column_cell_count):
            velocity_a[n] = structure_velocity_step * fractions_a[n] + velocity_a[n]
        # For Ben to review (pivot: end_to_elbow_cell_count, N: column_cell_count): in the odd MoC
        # substep the junction force reads B-grid pressures at pivot and N - pivot, while the even
        # substep reads the equivalent of pivot - 1 and N - pivot, so the odd-step inlet tap sits
        # one cell inward. Positions, in cells from the inlet end: A node n is at n, B cell n is at
        # n + 0.5. The even substep averages A nodes pivot - 1 and pivot (at pivot - 0.5, the
        # position of B cell pivot - 1) and A nodes N - pivot and N - pivot + 1 (at N - pivot + 0.5,
        # B cell N - pivot): taps at equal distances from the two ends. Example, N = 20, pivot = 6:
        # even taps at 5.5 and 14.5 (5.5 from each end); odd taps pressure_b[6] at 6.5 and
        # pressure_b[14] at 14.5, the inlet one cell nearer the centre. The one-index alternative is
        # pressure_b[pivot - 1] (at 5.5) in place of pressure_b[pivot]. Moving it to pivot - 1
        # changed the equivalent static force by at most 0.3 % over 16 cases (spans 6 to 48 m, 3 to
        # 22 Hz), largest on the 6 m span. The expression is the VBA's (lines 846, 971, 1067, 1164)
        # and stays; DEVIATIONS D-24.
        junction_force = JUNCTION_FORCE_FILTER_WEIGHT * junction_force + (
            1 - JUNCTION_FORCE_FILTER_WEIGHT
        ) * flow_area * (
            pressure_b[end_to_elbow_cell_count]
            - pressure_b[column_cell_count - end_to_elbow_cell_count]
        )
    return junction_force
