"""The 1-D method-of-characteristics (MoC) fluid column of ``GetPeakResponseJC``.

Behaviour is that of the MoC block in ``legacy/vba/Existing Code.bas`` (lines 795-847,
byte-identical in its four copies: 920-972, 1016-1068, 1113-1165) and its set-up (lines
731-734, 742-757). ``tests/test_differential.py`` replays the legacy solver's MoC block
through ``step`` bitwise.

Grid
----
``pipeSegQTY = N`` cells of length ``2 c dt`` between the elbows, ``pivotSegQTY`` cells
from each end to the portal-frame pivot, ``extQTY = 4`` end cells that receive no mass
acceleration. Two staggered half-grids: the A nodes ``0 .. N`` (pressure ``p_a``,
velocity ``v_a``) and the B cells ``0 .. N-1`` (``p_b``, ``v_b``), the VBA
``arrayA(0 To 1, 0 To N)`` and ``arrayB(0 To 1, 0 To N-1)`` split into four contiguous
1-D float64 arrays. Even sub-steps update the A grid from B, odd sub-steps the B grid
from A; the structure's acceleration enters as ``a dt`` weighted by the interp-fraction
profiles, which depend only on the grid and are tabulated once per run.

``step`` is one function over the four arrays and scalars with scalar loop bodies: no
per-cell helper calls and no Python objects; Stage 5 compiles it whole with ``@njit`` (``cache=True``,
no fastmath; the same source runs as Python under ``NUMBA_DISABLE_JIT=1``). The
dead ``useUndamped`` branch (``Const useUndamped = False``, the AFT infinite-pipe boundary)
is not ported; only the live decaying boundary (``dacayFactor``) is.

Approved fix F-1 (NOTES.md): the mean velocity ``vAv`` sums ``2N + 1`` terms; the VBA
divides by ``2N - 1`` (D-17). ``vav_divisor`` returns either, selected by the caller's
``vav_denominator`` flag ("legacy" | "fixed").

Approved fix F-4 (NOTES.md, DEVIATIONS D-4): the lead author replaced ``interpFractionA`` and
``interpFractionB`` (``legacy/vba/interpFraction_fix_2026-10-26.bas``); F-4b
(``legacy/vba/interpFraction_fix_2026-10-27.bas``, pending the lead author's confirmation)
moves the outlet side of both one node outward (``pipeSegQTY -> pipeSegQTY + 1`` in the two
outlet tests and the outlet ramp). ``interp_fractions`` tabulates either the original
profile (``fraction_profile="legacy"``: the ``n < 3`` test of ``interpFractionB`` and the
division by zero at ``pivotSegQTY = 4``) or the corrected one (``"fixed"``, the 27 Oct
text: both profiles start at exactly 0 at ``n = 3``, one strictly monotone squared ramp per
leg, both legs the same length, A mirror-symmetric about the column centre ``N / 2`` over
the called nodes ``1 .. N - 1`` (``A(n) = A(N - n)``) and B about ``(N - 1) / 2``
(``B(n) = B(N - 1 - n)``), equal fixed blocks of ``extQTY`` nodes / cells at both ends).

Exactness
---------
Every expression keeps the VBA's operation order. The sweeps carry the previous cell's
values in locals instead of re-reading them, which changes nothing numerically.
``a * dt * f`` is ``(a * dt) * f`` in VBA and here ``a_dt * f``. ``2 * rhoC`` is hoisted
(the same double). This module knows nothing about the structure proxy, the force
history or output types. See ``docs/architecture.md``.
"""

from __future__ import annotations

import numba
import numpy as np

from surge_sdof.vba_compat import clng

__all__ = [
    "EXT_QTY",
    "DAMPING_A",
    "grid_size",
    "is_short_pipe",
    "decay_factor",
    "FRACTION_PROFILES",
    "interp_fraction_a",
    "interp_fraction_b",
    "interp_fraction_a_fixed",
    "interp_fraction_b_fixed",
    "interp_fractions",
    "new_column",
    "vav_divisor",
    "step",
]

EXT_QTY = 4
"""VBA ``Const extQTY = 4``: cells at each end that receive no mass acceleration."""

DAMPING_A = 0.25
"""VBA ``Const dampingA = 0.25``: first-order low-pass on the junction force ``dF``."""

FRACTION_PROFILES = ("legacy", "fixed")
"""Values of the ``fraction_profile`` flag: the original ``interpFractionA/B`` (D-4
included) or the lead author's corrected functions (approved fix F-4)."""


# VBA lines 733-734
def grid_size(
    physical_length: float, portal_frame_height: float, celerity: float, dt: float
) -> tuple[int, int]:
    """``(pipeSegQTY, pivotSegQTY)`` of the MoC grid (VBA lines 733-734).

    Parameters
    ----------
    physical_length : float
        Length between elbows, m.
    portal_frame_height : float
        From ``structure.solve_portal_height``, m.
    celerity : float
        Pressure-wave speed, m/s.
    dt : float
        Sub-step, s; a cell is ``2 * celerity * dt`` long.

    Returns
    -------
    tuple of int
        ``pipeSegQTY`` (cells between the elbows, even by construction) and
        ``pivotSegQTY`` (cells from each end to the pivot, ``extQTY`` + the rounded
        height in cells; ``CLng`` rounds half to even).
    """
    pivot_seg_qty = EXT_QTY + clng(portal_frame_height / (2 * celerity * dt))
    pipe_seg_qty = 2 + clng(physical_length / (4 * celerity * dt) + pivot_seg_qty) * 2
    return pipe_seg_qty, pivot_seg_qty


# VBA line 736
def is_short_pipe(pipe_seg_qty: int, pivot_seg_qty: int) -> bool:
    """``pipeSegQTY - 2 * pivotSegQTY <= 2`` (VBA line 736): the span cannot hold the MoC
    grid and ``GetPeakResponseJC`` falls back to the lumped solver.

    Parameters
    ----------
    pipe_seg_qty, pivot_seg_qty : int
        From ``grid_size``.

    Returns
    -------
    bool
    """
    return pipe_seg_qty - 2 * pivot_seg_qty <= 2


# VBA line 731
def decay_factor(celerity: float, dt: float, physical_length: float) -> float:
    """``dacayFactor = 2 ^ ((celerity * dt) / physicalLength)`` (VBA line 731).

    Parameters
    ----------
    celerity : float
        Pressure-wave speed, m/s.
    dt : float
        Sub-step, s.
    physical_length : float
        Length between elbows, m.

    Returns
    -------
    float
        Dimensionless factor by which the end-node pressure decays per even update (a
        half-life of one pipe transit).
    """
    return 2 ** ((celerity * dt) / physical_length)


# VBA line 105: Function interpFractionA(n As Long, pivotSegQTY As Long, pipeSegQTY As Long)
def interp_fraction_a(n: int, pivot_seg_qty: int, pipe_seg_qty: int) -> float:
    """Cell-centred weighting of the mass acceleration at A node ``n`` (VBA line 105).

    Literal copy of ``legacy_port.interp_fraction_a`` so this module does not import the
    frozen legacy module.

    Parameters
    ----------
    n : int
        A node index, ``0 .. pipeSegQTY``.
    pivot_seg_qty, pipe_seg_qty : int
        From ``grid_size``.

    Returns
    -------
    float
        0 in the ``extQTY`` end cells, a squared ramp up to the pivot, 1 between the
        pivots; dimensionless.
    """
    if n < EXT_QTY:
        return 0.0
    elif n < pivot_seg_qty:
        return ((n - 0.5 - EXT_QTY) / (pivot_seg_qty - EXT_QTY)) ** 2
    elif n > pipe_seg_qty - EXT_QTY:
        return 0.0
    elif n > pipe_seg_qty - pivot_seg_qty:
        return ((pipe_seg_qty - 0.5 - EXT_QTY - n) / (pivot_seg_qty - EXT_QTY)) ** 2
    else:
        return 1.0


# VBA line 121: Function interpFractionB(n As Long, pivotSegQTY As Long, pipeSegQTY As Long)
def interp_fraction_b(n: int, pivot_seg_qty: int, pipe_seg_qty: int) -> float:
    """Node-centred weighting of the mass acceleration at B cell ``n`` (VBA line 121).

    Literal copy of ``legacy_port.interp_fraction_b``.

    Parameters
    ----------
    n : int
        B cell index, ``0 .. pipeSegQTY - 1``.
    pivot_seg_qty, pipe_seg_qty : int
        From ``grid_size``.

    Returns
    -------
    float
        Dimensionless weight, as ``interp_fraction_a`` but node-centred.

    Notes
    -----
    VBA quirk D-4 preserved: the first test is ``n < 3`` where ``interp_fraction_a`` uses
    ``n < extQTY`` (4), so ``n = 3`` takes the ramp branch and ``pivotSegQTY = 4``
    divides by zero.
    """
    if n < 3:  # VBA quirk D-4 preserved
        return 0.0
    elif n < pivot_seg_qty:
        return ((n - EXT_QTY) / (pivot_seg_qty - EXT_QTY)) ** 2
    elif n > pipe_seg_qty - EXT_QTY:
        return 0.0
    elif n > pipe_seg_qty - pivot_seg_qty:
        return ((pipe_seg_qty - 1 - EXT_QTY - n) / (pivot_seg_qty - EXT_QTY)) ** 2
    else:
        return 1.0


# interpFraction_fix_2026-10-27.bas: Function interpFractionA(n As Long, pivotSegQTY As Long, pipeSegQTY As Long)
def interp_fraction_a_fixed(n: int, pivot_seg_qty: int, pipe_seg_qty: int) -> float:
    """``interp_fraction_a`` as corrected by the lead author (approved fix F-4, outlet side
    moved one node outward by F-4b).

    Literal transcription of ``legacy/vba/interpFraction_fix_2026-10-27.bas``; the tests
    are on ``n + 1`` as written there.

    Parameters
    ----------
    n : int
        A node index, ``0 .. pipeSegQTY``.
    pivot_seg_qty, pipe_seg_qty : int
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
    if n + 1 < EXT_QTY + 0.5:
        return 0.0
    elif n + 1 < pivot_seg_qty:
        return ((n + 0.5 - EXT_QTY) / (pivot_seg_qty - EXT_QTY)) ** 2
    elif n + 1 > pipe_seg_qty + 1 - EXT_QTY + 0.5:
        return 0.0
    elif n + 1 > pipe_seg_qty + 2 - pivot_seg_qty:
        return ((pipe_seg_qty + 1 - EXT_QTY - n - 0.5) / (pivot_seg_qty - EXT_QTY)) ** 2
    else:
        return 1.0


# interpFraction_fix_2026-10-27.bas: Function interpFractionB(n As Long, pivotSegQTY As Long, pipeSegQTY As Long)
def interp_fraction_b_fixed(n: int, pivot_seg_qty: int, pipe_seg_qty: int) -> float:
    """``interp_fraction_b`` as corrected by the lead author (approved fix F-4, outlet side
    moved one cell outward by F-4b).

    Literal transcription of ``legacy/vba/interpFraction_fix_2026-10-27.bas``. The first
    test is ``n + 1 < extQTY + 0.5`` as in the A profile, so ``n = 3`` is 0 (D-4 fixed).

    Parameters
    ----------
    n : int
        B cell index, ``0 .. pipeSegQTY - 1``.
    pivot_seg_qty, pipe_seg_qty : int
        From ``grid_size``.

    Returns
    -------
    float
        0 for ``n <= 3`` and ``n >= pipeSegQTY - 4``, the squared ramp
        ``((n + 1 - 4) / (pivot - 4))^2`` for ``4 <= n <= pivot - 2`` and its mirror
        ``B(N - 1 - n)`` on the outlet leg (``N - pivot + 1 <= n <= N - 5``), 1 between;
        dimensionless. As for the A profile the ramp is unreachable at ``pivotSegQTY = 4``.
    """
    if n + 1 < EXT_QTY + 0.5:
        return 0.0
    elif n + 1 < pivot_seg_qty:
        return ((n + 1 - EXT_QTY) / (pivot_seg_qty - EXT_QTY)) ** 2
    elif n + 1 > pipe_seg_qty + 1 - EXT_QTY - 0.5:
        return 0.0
    elif n + 1 > pipe_seg_qty + 1.5 - pivot_seg_qty:
        return ((pipe_seg_qty + 1 - EXT_QTY - n - 1) / (pivot_seg_qty - EXT_QTY)) ** 2
    else:
        return 1.0


def interp_fractions(
    pipe_seg_qty: int, pivot_seg_qty: int, fraction_profile: str = "fixed"
) -> tuple[np.ndarray, np.ndarray]:
    """The two profiles tabulated once per grid.

    Parameters
    ----------
    pipe_seg_qty, pivot_seg_qty : int
        From ``grid_size``.
    fraction_profile : {"fixed", "legacy"}, optional
        ``"fixed"`` (default): the lead author's corrected functions (approved fix F-4,
        ``interp_fraction_a_fixed`` / ``interp_fraction_b_fixed``); ``"legacy"``: the VBA
        ``interpFractionA/B`` of ``Existing Code.bas`` (D-4 included).

    Returns
    -------
    frac_a : numpy.ndarray
        Length ``N + 1``; ``frac_a[n]`` for the A nodes ``n = 1 .. N-1`` (elements 0 and
        ``N`` are never used by ``step`` and are 0).
    frac_b : numpy.ndarray
        Length ``N``; ``frac_b[n]`` for the B cells ``n = 0 .. N-1``.

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
        if pivot_seg_qty <= EXT_QTY:
            raise ValueError(
                f"pivotSegQTY = {pivot_seg_qty} <= extQTY = {EXT_QTY}: the fixed fraction "
                "profile needs pivot > ext (the portal-frame height rounds to no MoC cell)"
            )
        fa, fb = interp_fraction_a_fixed, interp_fraction_b_fixed
    else:
        fa, fb = interp_fraction_a, interp_fraction_b
    frac_a = np.zeros(pipe_seg_qty + 1)
    frac_b = np.zeros(pipe_seg_qty)
    for n in range(1, pipe_seg_qty):
        frac_a[n] = fa(n, pivot_seg_qty, pipe_seg_qty)
    for n in range(0, pipe_seg_qty):
        frac_b[n] = fb(n, pivot_seg_qty, pipe_seg_qty)
    return frac_a, frac_b


def new_column(pipe_seg_qty: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """``(p_a, v_a, p_b, v_b)`` at rest.

    Parameters
    ----------
    pipe_seg_qty : int
        ``N``.

    Returns
    -------
    tuple of numpy.ndarray
        The VBA ``arrayA(0 To 1, 0 To N)`` and ``arrayB(0 To 1, 0 To N-1)`` zeroed, as
        four contiguous float64 arrays: pressures in Pa (``rhoC * v``), velocities in m/s.
    """
    return (
        np.zeros(pipe_seg_qty + 1),
        np.zeros(pipe_seg_qty + 1),
        np.zeros(pipe_seg_qty),
        np.zeros(pipe_seg_qty),
    )


def vav_divisor(pipe_seg_qty: int, vav_denominator: str) -> int:
    """Divisor of the mean-velocity sum (``2N + 1`` terms).

    Parameters
    ----------
    pipe_seg_qty : int
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
        return 2 * pipe_seg_qty - 1
    if vav_denominator == "fixed":
        return 2 * pipe_seg_qty + 1
    raise ValueError(f"vav_denominator must be 'legacy' or 'fixed', got {vav_denominator!r}")


@numba.njit(cache=True)
def step(
    even: bool,
    a_dt: float,
    p_a: np.ndarray,
    v_a: np.ndarray,
    p_b: np.ndarray,
    v_b: np.ndarray,
    frac_a: np.ndarray,
    frac_b: np.ndarray,
    n_seg: int,
    pivot: int,
    rho_c: float,
    decay: float,
    vav_div: int,
    fluid_area: float,
    d_f: float,
) -> float:
    """One MoC sub-step in place (VBA lines 795-847) and the new junction force ``dF``.

    Parameters
    ----------
    even : bool
        Half-grid to update. Even sub-steps update the A nodes from the B cells
        (mean-velocity subtraction, decaying end nodes, then the B velocities receive
        the mass acceleration); odd sub-steps update the B cells from the A nodes (then
        the A velocities receive the mass acceleration).
    a_dt : float
        Structure acceleration times the sub-step, ``a * dt``, m/s.
    p_a, v_a : numpy.ndarray
        Pressure (Pa) and velocity (m/s) on the A nodes ``0 .. N``; updated in place.
    p_b, v_b : numpy.ndarray
        Pressure (Pa) and velocity (m/s) on the B cells ``0 .. N-1``; updated in place.
    frac_a, frac_b : numpy.ndarray
        From ``interp_fractions``, dimensionless.
    n_seg : int
        ``pipeSegQTY``.
    pivot : int
        ``pivotSegQTY``.
    rho_c : float
        ``fluidDensty * celerity``, Pa·s/m.
    decay : float
        ``dacayFactor``, dimensionless.
    vav_div : int
        From ``vav_divisor``.
    fluid_area : float
        Internal cross-sectional area, m².
    d_f : float
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
    * VBA quirk D-17: the divisor of the mean velocity is the caller's ``vav_div``.
    * The dead ``useUndamped`` branch (VBA lines 803-818) is not ported.
    * Stage 5: compiled with ``numba.njit(cache=True)`` (no fastmath), body unchanged;
      with ``NUMBA_DISABLE_JIT=1`` it is this Python function. Inside the compiled
      function ``numpy.errstate`` does not apply: ``rho_c = 0`` is rejected by the
      caller's set-up (``response.peak_response_jc``, D-9) and an overflow propagates
      nan/inf to the structure state, where the end-of-run check raises (D-23).
    """
    two_rho_c = 2 * rho_c
    if even:
        # vAv = arrayA(1, N) + sum over n = 0 .. N-1 of arrayA(1, n) + arrayB(1, n)
        v_av = v_a[n_seg]
        for n in range(0, n_seg):
            v_av = v_av + v_a[n]
            v_av = v_av + v_b[n]
        v_av = v_av / vav_div
        # decaying boundary (the live branch; useUndamped is dead and not ported)
        p_a[0] = p_b[0] / decay
        p_a[n_seg] = p_b[n_seg - 1] / decay
        v_a[0] = v_b[0] - v_av
        v_a[n_seg] = v_b[n_seg - 1] - v_av
        # A nodes 1 .. N-1 from B cells n-1 and n
        pb_prev = p_b[0]
        vb_prev = v_b[0]
        for n in range(1, n_seg):
            pb = p_b[n]
            vb = v_b[n]
            p_a[n] = (pb_prev + pb) / 2 + rho_c * (vb_prev - vb) / 2
            v_a[n] = a_dt * frac_a[n] - v_av + (pb_prev - pb) / two_rho_c + (vb_prev + vb) / 2
            pb_prev = pb
            vb_prev = vb
        # B velocities receive the mass acceleration and lose the mean velocity
        for n in range(0, n_seg):
            v_b[n] = a_dt * frac_b[n] - v_av + v_b[n]
        d_f = (
            DAMPING_A * d_f
            + (1 - DAMPING_A)
            * fluid_area
            * (p_a[pivot] + p_a[pivot - 1] - p_a[n_seg - pivot] - p_a[n_seg - pivot + 1])
            / 2
        )
    else:
        # B cells 0 .. N-1 from A nodes n and n+1
        pa_prev = p_a[0]
        va_prev = v_a[0]
        for n in range(0, n_seg):
            pa = p_a[n + 1]
            va = v_a[n + 1]
            p_b[n] = (pa_prev + pa) / 2 + rho_c * (va_prev - va) / 2
            v_b[n] = a_dt * frac_b[n] + (pa_prev - pa) / two_rho_c + (va_prev + va) / 2
            pa_prev = pa
            va_prev = va
        # A velocities receive the mass acceleration
        for n in range(1, n_seg):
            v_a[n] = a_dt * frac_a[n] + v_a[n]
        d_f = DAMPING_A * d_f + (1 - DAMPING_A) * fluid_area * (p_b[pivot] - p_b[n_seg - pivot])
    return d_f
