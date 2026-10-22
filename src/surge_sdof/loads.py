"""Elbow-to-elbow unbalance force from a force history: transit delay and the VBA's
three-phase scheduling.

The force arrives at elbow A at sample ``t`` and at elbow B ``unballanceStepQTY =
L / (c / sampleFreq)`` samples later; the structure sees ``forceA - forceB``. The VBA
(``GetPeakResponse`` lines 394-567, identically in ``GetPeakResponseJC``) walks the
history column-major in three phases:

1. **delay** (``forceA`` held at the first sample, ``forceB`` ramps through the history)
   until ``(totInd - 1) * stepQTY + 1 + k > unballanceStepQTY * stepQTY``, which exits
   the last delay sample part way through (``Exit For``);
2. **ramp** (both forces interpolate; ``forceB`` runs ``kOverlap`` sub-steps ahead of
   the sample boundary, so each sample's sub-steps are split into
   ``stepQTY - kOverlap`` from one pair of samples and ``kOverlap`` from the next);
3. **free decay** has no unbalance force and is the caller's business.

``unbalance_force`` yields one ``list`` of Python floats per sample, holding exactly the
per-sub-step ``forceA - forceB`` values the VBA computes (``tests/test_differential.py``
compares them bitwise with the legacy solver's locals). ``elbow_forces`` (Session V.1)
yields the two forces apart, per sample with its phase, for the solver trace; both walk
the history through one private ``_schedule`` generator and differ only in their inner
``k`` loops. The linear ramp
``k / (stepQTY - 1)`` (D-7: ``stepQTY = 1`` divides by zero; D-18: the ramp spans
``stepQTY - 1`` sub-steps) is tabulated once per run; the table holds the same doubles.

This module knows nothing about the structure, stiffness, damping, fluid coupling, or
what the caller does at sample boundaries. See ``docs/architecture.md``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import NamedTuple

import numpy as np

from surge_sdof.vba_compat import clng, vba_2d, vba_floor

__all__ = [
    "as_history_2d",
    "transit_delay",
    "overlap_substeps",
    "unbalance_force",
    "elbow_forces",
]


def as_history_2d(history) -> np.ndarray:
    """The history as a 0-based 2-D float array ``(rows, cols)``.

    Parameters
    ----------
    history : array_like
        Force history, N, 1-D or 2-D (``pressure.py`` reuses this for the dimensionless
        valve pattern).

    Returns
    -------
    numpy.ndarray
        A 1-D input becomes one column (the VBA ``AddDimension(arr, 1, 1)`` path); a 2-D
        input is returned as is and walked column-major, first index fastest, by the
        callers (VBA quirk D-10, Excel range semantics).

    Raises
    ------
    ValueError
        For more than two dimensions.
    """
    arr = np.asarray(history, dtype=float)
    if arr.ndim < 2:
        return arr.reshape(-1, 1)
    if arr.ndim > 2:
        raise ValueError(f"force history must be 1-D or 2-D, got ndim={arr.ndim}")
    return arr


# VBA line 375
def transit_delay(physical_length: float, celerity: float, sample_freq: float) -> float:
    """``unballanceStepQTY`` (VBA line 375): the elbow-to-elbow transit time in samples.

    Parameters
    ----------
    physical_length : float
        Length between elbows, m.
    celerity : float
        Propagation speed of the force along the pipe, m/s.
    sample_freq : float
        Sample rate of the force history, Hz.

    Returns
    -------
    float
        ``physicalLength / (celerity / sampleFreq)``, samples (fractional).
    """
    return float(physical_length) / (float(celerity) / float(sample_freq))


# VBA line 380
def overlap_substeps(unballance_step_qty: float, step_qty: int) -> int:
    """``kOverlap`` (VBA line 380): the fractional part of the transit delay in sub-steps.

    Parameters
    ----------
    unballance_step_qty : float
        Transit delay from ``transit_delay``, samples.
    step_qty : int
        Sub-steps per sample.

    Returns
    -------
    int
        ``CLng((unballanceStepQTY - floor(unballanceStepQTY)) * stepQTY)``, 0 .. ``stepQTY``
        (``CLng`` rounds half to even; ``floor`` is the fixed VBA floor, D-1).
    """
    return clng((unballance_step_qty - vba_floor(unballance_step_qty)) * step_qty)


class _Run(NamedTuple):
    """Per-run constants of the walk, computed once by ``_run``."""

    fh: list  # fh[i][j] is the VBA forceHistory(i, j), 1-based (vba_2d)
    u1: int  # UBound(forceHistory, 1)
    u2: int  # UBound(forceHistory, 2)
    step_qty: int
    unb: float  # unballanceStepQTY, samples
    k_overlap: int
    unb_steps: float  # unballanceStepQTY * stepQTY, VBA line 446
    frac: list  # k / (stepQTY - 1), k = 0 .. stepQTY - 1 (D-7, D-18)
    one_minus: list  # 1 - k / (stepQTY - 1)


def _run(history, sample_freq, physical_length, celerity, step_qty) -> _Run:
    fh = vba_2d(as_history_2d(history)).tolist()
    step_qty = int(step_qty)
    unb = transit_delay(physical_length, celerity, sample_freq)
    k_overlap = overlap_substeps(unb, step_qty)
    # k / (stepQTY - 1) and 1 - k / (stepQTY - 1) for k = 0 .. stepQTY - 1 (D-7, D-18)
    frac = [k / (step_qty - 1) for k in range(step_qty)]
    one_minus = [1 - f for f in frac]
    return _Run(
        fh, len(fh) - 1, len(fh[0]) - 1, step_qty, unb, k_overlap, unb * step_qty, frac, one_minus
    )


def _schedule(run: _Run) -> Iterator[tuple]:
    """The VBA index walk, one item per sample, shared by ``unbalance_force`` and
    ``elbow_forces`` (which differ only in their inner ``k`` loops).

    Phase 1 (delay) items are ``(0, totInd, forceA, f_cur, f_nxt)``: ``forceA`` is held,
    ``forceB`` ramps from ``f_cur`` to ``f_nxt``; the consumer truncates the sample at the
    VBA ``Exit For`` (``base + k > unballanceStepQTY * stepQTY``). Phase 2 (ramp) items are
    ``(1, fa_cur, fa_nxt, fb_cur, fb_nxt, fb2_cur, fb2_nxt)``: ``forceA`` ramps between the
    first pair, ``forceB`` between the second pair for the first ``stepQTY - kOverlap``
    sub-steps and between the third pair for the remaining ``kOverlap``. The item is
    yielded after every index it needs is read, so a D-8 ``IndexError`` surfaces where the
    legacy raised it: at the first phase-2 sample, after every phase-1 sample."""
    fh, u1, u2, step_qty, unb, k_overlap, _unb_steps, _frac, _one_minus = run

    # ---------------------------------------------------------------- phase 1: delay
    force_a = fh[1][1]
    tot_ind = 0
    # For jB = 1 To 1 + CLng(unballanceStepQTY / UBound(forceHistory, 2))
    #     For iB = 1 To UBound(forceHistory, 1)
    # jB and iB are read after the loops and keep VBA's post-loop values.
    jb_to = 1 + clng(unb / u2)
    jb = 1
    while jb <= jb_to:
        ib = 1
        while ib <= u1:
            tot_ind = tot_ind + 1
            if jb > u2:
                j = u2
                i = u1
            else:
                j = jb
                i = ib
            if i + 1 > u1 and j < u2:
                jmax = min(j + 1, u2)
                imax = 1
            else:
                jmax = min(j, u2)
                imax = min(i + 1, u1)
            yield (0, tot_ind, force_a, fh[i][j], fh[imax][jmax])
            if tot_ind > unb:
                break
            ib = ib + 1
        if tot_ind > unb:
            break
        jb = jb + 1

    # VBA quirk D-8 preserved: if the loops complete without Exit For (single-row
    # history), iB is UBound(1) + 1 and fh[ib][jb] below raises IndexError.
    if jb > u2:
        jb = u2
        ib = u1

    # ----------------------------------------------------------------- phase 2: ramp
    for j in range(1, u2 + 1):
        for i in range(1, u1 + 1):
            if i + 1 > u1 and j < u2:
                jmax = min(j + 1, u2)
                imax = 1
            else:
                jmax = j
                imax = min(i + 1, u1)
            if ib + 1 > u1 and jb < u2:
                jbmax = min(jb + 1, u2)
                ibmax = 1
            else:
                jbmax = jb
                ibmax = min(ib + 1, u1)
            fa_cur = fh[i][j]
            fa_nxt = fh[imax][jmax]
            fb_cur = fh[ib][jb]
            fb_nxt = fh[ibmax][jbmax]
            # forceB for k = 0 To stepQTY - kOverlap - 1 comes from (fb_cur, fb_nxt); the
            # VBA then advances iB/jB and reads the pair for k = stepQTY - kOverlap To
            # stepQTY - 1 (the advance does not depend on the k loop)
            if ib + 1 > u1 and jb < u2:
                jb = min(jb + 1, u2)
                ib = 1
            else:
                ib = min(ib + 1, u1)
            if ib + 1 > u1 and jb < u2:
                jbmax = min(jb + 1, u2)
                ibmax = 1
            else:
                jbmax = jb
                ibmax = min(ib + 1, u1)
            yield (1, fa_cur, fa_nxt, fb_cur, fb_nxt, fh[ib][jb], fh[ibmax][jbmax])


def unbalance_force(
    history, sample_freq: float, physical_length: float, celerity: float, step_qty: int
) -> Iterator[list[float]]:
    """Yield, per sample, the list of per-sub-step ``forceA - forceB`` values.

    Parameters
    ----------
    history : array_like
        Force history at one location, N, 1-D or 2-D (column-major, D-10).
    sample_freq : float
        Sample rate of the history, Hz.
    physical_length : float
        Length between elbows, m.
    celerity : float
        Propagation speed of the force along the pipe, m/s.
    step_qty : int
        Sub-steps per sample.

    Yields
    ------
    list of float
        The unbalance force ``forceA - forceB``, N, for each sub-step of one sample.
        Phase 1 (delay) yields ``totInd`` samples, the last one truncated at the VBA
        ``Exit For``; phase 2 (ramp) yields one full sample per history element. Phase 3
        (free decay) has no unbalance force and is not yielded.

    Raises
    ------
    ZeroDivisionError
        ``step_qty = 1`` (VBA quirk D-7: the ramp ``k / (stepQTY - 1)``).
    IndexError
        A single-row history (VBA quirk D-8: ``iB`` is left one past ``UBound(1)``).

    Notes
    -----
    * VBA quirk D-18 preserved: the ramp reaches the next sample at ``k = stepQTY - 1``
      and the next sample's ``k = 0`` repeats it, so each sample value is held for two
      consecutive sub-steps.
    * The ramp fractions are tabulated once per run; the table holds the same doubles
      the per-step expression produced.
    * Session V.1: the index walk is ``_schedule``, shared with ``elbow_forces``; the
      inner ``k`` loops here are the Stage 4 ones (same operands, same operations).
    """
    run = _run(history, sample_freq, physical_length, celerity, step_qty)
    step_qty, k_overlap, unb_steps, frac, one_minus = (
        run.step_qty,
        run.k_overlap,
        run.unb_steps,
        run.frac,
        run.one_minus,
    )
    split = step_qty - k_overlap
    for item in _schedule(run):
        if item[0] == 0:
            _phase, tot_ind, force_a, f_cur, f_nxt = item
            base = (tot_ind - 1) * step_qty + 1
            sample = []
            for k in range(step_qty):
                force_b = f_cur * one_minus[k] + f_nxt * frac[k]
                sample.append(force_a - force_b)
                if base + k > unb_steps:
                    break
            yield sample
        else:
            _phase, fa_cur, fa_nxt, fb_cur, fb_nxt, fb2_cur, fb2_nxt = item
            sample = []
            # For k = 0 To stepQTY - kOverlap - 1: forceB at k + kOverlap
            for k in range(0, split):
                force_a = fa_cur * one_minus[k] + fa_nxt * frac[k]
                force_b = fb_cur * one_minus[k + k_overlap] + fb_nxt * frac[k + k_overlap]
                sample.append(force_a - force_b)
            # For k = stepQTY - kOverlap To stepQTY - 1: forceB at k - stepQTY + kOverlap
            for k in range(split, step_qty):
                m = k - step_qty + k_overlap
                force_a = fa_cur * one_minus[k] + fa_nxt * frac[k]
                force_b = fb2_cur * one_minus[m] + fb2_nxt * frac[m]
                sample.append(force_a - force_b)
            yield sample


def elbow_forces(
    history, sample_freq: float, physical_length: float, celerity: float, step_qty: int
) -> Iterator[tuple[int, list[float], list[float]]]:
    """Yield, per sample, ``(phase, forceA list, forceB list)`` for the trace (Session V.1).

    The same walk and the same per-sub-step values as ``unbalance_force``, kept apart
    before the subtraction: ``forceA[k] - forceB[k]`` of a sample is bitwise the
    corresponding ``unbalance_force`` value (same operands, same operation;
    ``tests/test_trace.py`` pins it on the sweep and the golden history).

    Parameters
    ----------
    history, sample_freq, physical_length, celerity, step_qty
        As ``unbalance_force``.

    Yields
    ------
    phase : int
        0 for the delay phase (``forceA`` held at the first sample while ``forceB``
        ramps; the trace's "transit"), 1 for the ramp phase (the trace's "history").
    force_a, force_b : list of float
        The force at elbow A and the delayed force at elbow B, N, per sub-step; the same
        lengths as the ``unbalance_force`` samples (the last delay sample truncated).

    Raises
    ------
    ZeroDivisionError, IndexError
        As ``unbalance_force`` (D-7, D-8).
    """
    run = _run(history, sample_freq, physical_length, celerity, step_qty)
    step_qty, k_overlap, unb_steps, frac, one_minus = (
        run.step_qty,
        run.k_overlap,
        run.unb_steps,
        run.frac,
        run.one_minus,
    )
    split = step_qty - k_overlap
    for item in _schedule(run):
        if item[0] == 0:
            _phase, tot_ind, force_a, f_cur, f_nxt = item
            base = (tot_ind - 1) * step_qty + 1
            fa = []
            fb = []
            for k in range(step_qty):
                fa.append(force_a)
                fb.append(f_cur * one_minus[k] + f_nxt * frac[k])
                if base + k > unb_steps:
                    break
            yield (0, fa, fb)
        else:
            _phase, fa_cur, fa_nxt, fb_cur, fb_nxt, fb2_cur, fb2_nxt = item
            fa = []
            fb = []
            for k in range(0, split):
                fa.append(fa_cur * one_minus[k] + fa_nxt * frac[k])
                fb.append(fb_cur * one_minus[k + k_overlap] + fb_nxt * frac[k + k_overlap])
            for k in range(split, step_qty):
                m = k - step_qty + k_overlap
                fa.append(fa_cur * one_minus[k] + fa_nxt * frac[k])
                fb.append(fb2_cur * one_minus[m] + fb2_nxt * frac[m])
            yield (1, fa, fb)
