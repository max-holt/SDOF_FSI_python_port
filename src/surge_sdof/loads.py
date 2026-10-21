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
compares them bitwise with the legacy solver's locals). The linear ramp
``k / (stepQTY - 1)`` (D-7: ``stepQTY = 1`` divides by zero; D-18: the ramp spans
``stepQTY - 1`` sub-steps) is tabulated once per run; the table holds the same doubles.

This module knows nothing about the structure, stiffness, damping, fluid coupling, or
what the caller does at sample boundaries. See ``docs/architecture.md``.
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from surge_sdof.vba_compat import clng, vba_2d, vba_floor

__all__ = ["as_history_2d", "transit_delay", "overlap_substeps", "unbalance_force"]


def as_history_2d(history) -> np.ndarray:
    """The force history as a 0-based 2-D float array ``(rows, cols)``.

    A 1-D input is one column (the VBA ``AddDimension(arr, 1, 1)`` path); a 2-D input is
    walked column-major (first index fastest, D-10) by ``unbalance_force``.
    """
    arr = np.asarray(history, dtype=float)
    if arr.ndim < 2:
        return arr.reshape(-1, 1)
    if arr.ndim > 2:
        raise ValueError(f"force history must be 1-D or 2-D, got ndim={arr.ndim}")
    return arr


# VBA line 375
def transit_delay(physical_length: float, celerity: float, sample_freq: float) -> float:
    """``unballanceStepQTY``: the elbow-to-elbow transit time in samples."""
    return float(physical_length) / (float(celerity) / float(sample_freq))


# VBA line 380
def overlap_substeps(unballance_step_qty: float, step_qty: int) -> int:
    """``kOverlap = CLng((unballanceStepQTY - floor(unballanceStepQTY)) * stepQTY)``:
    the fractional part of the delay in sub-steps, 0 .. ``stepQTY``."""
    return clng((unballance_step_qty - vba_floor(unballance_step_qty)) * step_qty)


def unbalance_force(
    history, sample_freq: float, physical_length: float, celerity: float, step_qty: int
) -> Iterator[list[float]]:
    """Yield, per sample, the list of per-sub-step ``forceA - forceB`` values.

    Phase 1 (delay) yields ``totInd`` samples, the last one truncated at the VBA
    ``Exit For``; phase 2 (ramp) yields one full sample per history element, in
    column-major order. Phase 3 (free decay) has no unbalance force and is not yielded.
    """
    fh = vba_2d(as_history_2d(history)).tolist()  # fh[i][j] is the VBA forceHistory(i, j)
    u1 = len(fh) - 1  # UBound(forceHistory, 1)
    u2 = len(fh[0]) - 1  # UBound(forceHistory, 2)
    step_qty = int(step_qty)

    unb = transit_delay(physical_length, celerity, sample_freq)
    k_overlap = overlap_substeps(unb, step_qty)
    unb_steps = unb * step_qty  # unballanceStepQTY * stepQTY, VBA line 446

    # k / (stepQTY - 1) and 1 - k / (stepQTY - 1) for k = 0 .. stepQTY - 1 (D-7, D-18)
    frac = [k / (step_qty - 1) for k in range(step_qty)]
    one_minus = [1 - f for f in frac]

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
            f_cur = fh[i][j]
            f_nxt = fh[imax][jmax]
            base = (tot_ind - 1) * step_qty + 1
            sample = []
            for k in range(step_qty):
                force_b = f_cur * one_minus[k] + f_nxt * frac[k]
                sample.append(force_a - force_b)
                if base + k > unb_steps:
                    break
            yield sample
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
    split = step_qty - k_overlap
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
            sample = []
            # For k = 0 To stepQTY - kOverlap - 1: forceB at k + kOverlap
            for k in range(0, split):
                force_a = fa_cur * one_minus[k] + fa_nxt * frac[k]
                force_b = fb_cur * one_minus[k + k_overlap] + fb_nxt * frac[k + k_overlap]
                sample.append(force_a - force_b)
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
            fb_cur = fh[ib][jb]
            fb_nxt = fh[ibmax][jbmax]
            # For k = stepQTY - kOverlap To stepQTY - 1: forceB at k - stepQTY + kOverlap
            for k in range(split, step_qty):
                m = k - step_qty + k_overlap
                force_a = fa_cur * one_minus[k] + fa_nxt * frac[k]
                force_b = fb_cur * one_minus[m] + fb_nxt * frac[m]
                sample.append(force_a - force_b)
            yield sample
