"""Elbow-to-elbow unbalance force from a force history: transit delay and the VBA's
three-phase scheduling.

The force arrives at elbow A at sample ``t`` and at elbow B ``unballanceStepQTY =
L / (c / sampleFreq)`` samples later; the structure sees ``forceA - forceB``. The VBA
(``GetPeakResponse`` lines 394-567, identically in ``GetPeakResponseJC``) walks the
history column-major in three phases:

1. **transit** (``forceA`` held at the first sample, ``forceB`` ramps through the
   history) until ``(totInd - 1) * stepQTY + 1 + k > unballanceStepQTY * stepQTY``, which
   exits the last transit sample part way through (``Exit For``);
2. **forced** (both forces interpolate; ``forceB`` runs ``kOverlap`` sub-steps ahead of
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

# The load phases this module produces, as recorded in the trace (``trace.PHASE_*``, the
# integer codes of the exported ``phase`` column; docs/data_format.md). The third phase,
# free decay, has no unbalance force and is defined with its consumers (``trace``).
PHASE_TRANSIT = 0  # force A held at the first sample while force B ramps (VBA phase 1)
PHASE_FORCED = 1  # both elbow forces interpolate through the history (VBA phase 2)

__all__ = [
    "PHASE_TRANSIT",
    "PHASE_FORCED",
    "as_history_2d",
    "transit_delay",
    "overlap_substeps",
    "unbalance_force",
    "elbow_forces",
]


def as_history_2d(force_history) -> np.ndarray:
    """The history as a 0-based 2-D float array ``(rows, cols)``.

    Parameters
    ----------
    force_history : array_like
        Force history, N, 1-D or 2-D.

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
    arr = np.asarray(force_history, dtype=float)
    if arr.ndim < 2:
        return arr.reshape(-1, 1)
    if arr.ndim > 2:
        raise ValueError(f"force history must be 1-D or 2-D, got ndim={arr.ndim}")
    return arr


# VBA line 375
def transit_delay(span_length: float, celerity: float, sample_rate: float) -> float:
    """``unballanceStepQTY`` (VBA line 375): the elbow-to-elbow transit time in samples.

    Parameters
    ----------
    span_length : float
        Length between elbows, m.
    celerity : float
        Propagation speed of the force along the pipe, m/s.
    sample_rate : float
        Sample rate of the force history, Hz.

    Returns
    -------
    float
        ``physicalLength / (celerity / sampleFreq)``, samples (fractional).
    """
    return float(span_length) / (float(celerity) / float(sample_rate))


# VBA line 380
def overlap_substeps(transit_delay_samples: float, substep_count: int) -> int:
    """``kOverlap`` (VBA line 380): the fractional part of the transit delay in sub-steps.

    Parameters
    ----------
    transit_delay_samples : float
        Transit delay from ``transit_delay``, samples.
    substep_count : int
        Sub-steps per sample.

    Returns
    -------
    int
        ``CLng((unballanceStepQTY - floor(unballanceStepQTY)) * stepQTY)``, 0 .. ``stepQTY``
        (``CLng`` rounds half to even; ``floor`` is the fixed VBA floor, D-1).
    """
    return clng((transit_delay_samples - vba_floor(transit_delay_samples)) * substep_count)


class _Run(NamedTuple):
    """Per-run constants of the walk, computed once by ``_walk_constants``."""

    force_history_one_based: list  # [i][j] is the VBA forceHistory(i, j), 1-based (vba_2d)
    history_row_count: int  # UBound(forceHistory, 1)
    history_column_count: int  # UBound(forceHistory, 2)
    substep_count: int
    transit_delay_samples: float  # unballanceStepQTY, samples
    overlap_substep_count: int  # kOverlap
    transit_delay_substeps: float  # unballanceStepQTY * stepQTY, VBA line 446
    next_sample_weight: list  # k / (stepQTY - 1), k = 0 .. stepQTY - 1 (D-7, D-18)
    current_sample_weight: list  # 1 - k / (stepQTY - 1)


def _walk_constants(force_history, sample_rate, span_length, celerity, substep_count) -> _Run:
    force_history_one_based = vba_2d(as_history_2d(force_history)).tolist()
    substep_count = int(substep_count)
    transit_delay_samples = transit_delay(span_length, celerity, sample_rate)
    overlap_substep_count = overlap_substeps(transit_delay_samples, substep_count)
    # k / (stepQTY - 1) and 1 - k / (stepQTY - 1) for k = 0 .. stepQTY - 1 (D-7, D-18)
    next_sample_weight = [k / (substep_count - 1) for k in range(substep_count)]
    current_sample_weight = [1 - f for f in next_sample_weight]
    return _Run(
        force_history_one_based,
        len(force_history_one_based) - 1,
        len(force_history_one_based[0]) - 1,
        substep_count,
        transit_delay_samples,
        overlap_substep_count,
        transit_delay_samples * substep_count,
        next_sample_weight,
        current_sample_weight,
    )


def _next_position(row: int, column: int, row_count: int, column_count: int) -> tuple[int, int]:
    """The 1-based ``(row, column)`` after ``(row, column)`` in the column-major walk of the
    history: one row down, or the top of the next column from the last row of any column but
    the last; the last element is its own successor. Integer only."""
    if row + 1 > row_count and column < column_count:
        return 1, min(column + 1, column_count)
    return min(row + 1, row_count), column


def _schedule(walk: _Run) -> Iterator[tuple]:
    """The VBA index walk, one item per sample, shared by ``unbalance_force`` and
    ``elbow_forces`` (which differ only in their inner ``k`` loops).

    Transit-phase items are ``(PHASE_TRANSIT, totInd, elbow_a_force, elbow_b_force_current,
    elbow_b_force_next)``: the force at elbow A is held, the force at elbow B ramps between
    the pair; the consumer truncates the sample at the VBA ``Exit For``
    (``first_substep_number + k > unballanceStepQTY * stepQTY``). Forced-phase items are
    ``(PHASE_FORCED, elbow_a_force_current,
    elbow_a_force_next, elbow_b_force_current, elbow_b_force_next,
    elbow_b_force_advanced_current, elbow_b_force_advanced_next)``: elbow A ramps between the
    first pair, elbow B between the second pair for the first ``stepQTY - kOverlap``
    sub-steps and between the third pair (after it advances) for the remaining
    ``kOverlap``. The item is yielded after every index it needs is read, so a D-8
    ``IndexError`` surfaces where the legacy raised it: at the first forced sample, after
    every transit sample."""
    (
        force_history_one_based,
        history_row_count,
        history_column_count,
        substep_count,
        transit_delay_samples,
        overlap_substep_count,
        _transit_delay_substeps,
        _next_sample_weight,
        _current_sample_weight,
    ) = walk

    # ------------------------------------------------------------------- transit phase
    elbow_a_force = force_history_one_based[1][1]
    sample_number = 0
    # For jB = 1 To 1 + CLng(unballanceStepQTY / UBound(forceHistory, 2))
    #     For iB = 1 To UBound(forceHistory, 1)
    # jB and iB are read after the loops and keep VBA's post-loop values.
    # For Ben to review: the bound divides the transit delay in samples by the number of
    # history columns (UBound(forceHistory, 2)), where the samples per column are the rows.
    # The walk exits earlier, on totInd > unballanceStepQTY, in every tested case, so the
    # bound has not been seen to matter. The expression is the VBA's and stays.
    transit_last_column = 1 + clng(transit_delay_samples / history_column_count)
    elbow_b_column = 1
    while elbow_b_column <= transit_last_column:
        elbow_b_row = 1
        while elbow_b_row <= history_row_count:
            sample_number = sample_number + 1
            if elbow_b_column > history_column_count:
                history_column = history_column_count
                history_row = history_row_count
            else:
                history_column = elbow_b_column
                history_row = elbow_b_row
            if history_row + 1 > history_row_count and history_column < history_column_count:
                next_history_column = min(history_column + 1, history_column_count)
                next_history_row = 1
            else:
                next_history_column = min(history_column, history_column_count)
                next_history_row = min(history_row + 1, history_row_count)
            yield (
                PHASE_TRANSIT,
                sample_number,
                elbow_a_force,
                force_history_one_based[history_row][history_column],
                force_history_one_based[next_history_row][next_history_column],
            )
            if sample_number > transit_delay_samples:
                break
            elbow_b_row = elbow_b_row + 1
        if sample_number > transit_delay_samples:
            break
        elbow_b_column = elbow_b_column + 1

    # VBA quirk D-8 preserved: if the loops complete without Exit For (single-row
    # history), iB is UBound(1) + 1 and the read at [elbow_b_row][elbow_b_column] below
    # raises IndexError.
    if elbow_b_column > history_column_count:
        elbow_b_column = history_column_count
        elbow_b_row = history_row_count

    # -------------------------------------------------------------------- forced phase
    for history_column in range(1, history_column_count + 1):
        for history_row in range(1, history_row_count + 1):
            next_history_row, next_history_column = _next_position(
                history_row, history_column, history_row_count, history_column_count
            )
            elbow_b_next_row, elbow_b_next_column = _next_position(
                elbow_b_row, elbow_b_column, history_row_count, history_column_count
            )
            elbow_a_force_current = force_history_one_based[history_row][history_column]
            elbow_a_force_next = force_history_one_based[next_history_row][next_history_column]
            elbow_b_force_current = force_history_one_based[elbow_b_row][elbow_b_column]
            elbow_b_force_next = force_history_one_based[elbow_b_next_row][elbow_b_next_column]
            # forceB for k = 0 To stepQTY - kOverlap - 1 comes from the current / next pair; the
            # VBA then advances iB/jB and reads the pair for k = stepQTY - kOverlap To
            # stepQTY - 1 (the advance does not depend on the k loop)
            elbow_b_row, elbow_b_column = _next_position(
                elbow_b_row, elbow_b_column, history_row_count, history_column_count
            )
            elbow_b_next_row, elbow_b_next_column = _next_position(
                elbow_b_row, elbow_b_column, history_row_count, history_column_count
            )
            yield (
                PHASE_FORCED,
                elbow_a_force_current,
                elbow_a_force_next,
                elbow_b_force_current,
                elbow_b_force_next,
                force_history_one_based[elbow_b_row][elbow_b_column],
                force_history_one_based[elbow_b_next_row][elbow_b_next_column],
            )


def unbalance_force(
    force_history, sample_rate: float, span_length: float, celerity: float, substep_count: int
) -> Iterator[list[float]]:
    """Yield, per sample, the list of per-sub-step ``forceA - forceB`` values.

    Parameters
    ----------
    force_history : array_like
        Force history at one location, N, 1-D or 2-D (column-major, D-10).
    sample_rate : float
        Sample rate of the history, Hz.
    span_length : float
        Length between elbows, m.
    celerity : float
        Propagation speed of the force along the pipe, m/s.
    substep_count : int
        Sub-steps per sample.

    Yields
    ------
    list of float
        The unbalance force ``forceA - forceB``, N, for each sub-step of one sample.
        The transit phase yields ``totInd`` samples, the last one truncated at the VBA
        ``Exit For``; the forced phase yields one full sample per history element. Free
        decay has no unbalance force and is not yielded.

    Raises
    ------
    ZeroDivisionError
        ``substep_count = 1`` (VBA quirk D-7: the ramp ``k / (stepQTY - 1)``).
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
    walk = _walk_constants(force_history, sample_rate, span_length, celerity, substep_count)
    (
        substep_count,
        overlap_substep_count,
        transit_delay_substeps,
        next_sample_weight,
        current_sample_weight,
    ) = (
        walk.substep_count,
        walk.overlap_substep_count,
        walk.transit_delay_substeps,
        walk.next_sample_weight,
        walk.current_sample_weight,
    )
    pre_advance_substep_count = substep_count - overlap_substep_count
    for item in _schedule(walk):
        if item[0] == PHASE_TRANSIT:
            _phase, sample_number, elbow_a_force, elbow_b_force_current, elbow_b_force_next = item
            first_substep_number = (sample_number - 1) * substep_count + 1
            sample_forces = []
            for k in range(substep_count):
                elbow_b_force = (
                    elbow_b_force_current * current_sample_weight[k]
                    + elbow_b_force_next * next_sample_weight[k]
                )
                sample_forces.append(elbow_a_force - elbow_b_force)
                if first_substep_number + k > transit_delay_substeps:
                    break
            yield sample_forces
        else:
            (
                _phase,
                elbow_a_force_current,
                elbow_a_force_next,
                elbow_b_force_current,
                elbow_b_force_next,
                elbow_b_force_advanced_current,
                elbow_b_force_advanced_next,
            ) = item
            sample_forces = []
            # For k = 0 To stepQTY - kOverlap - 1: forceB at k + kOverlap
            for k in range(0, pre_advance_substep_count):
                elbow_a_force = (
                    elbow_a_force_current * current_sample_weight[k]
                    + elbow_a_force_next * next_sample_weight[k]
                )
                elbow_b_force = (
                    elbow_b_force_current * current_sample_weight[k + overlap_substep_count]
                    + elbow_b_force_next * next_sample_weight[k + overlap_substep_count]
                )
                sample_forces.append(elbow_a_force - elbow_b_force)
            # For k = stepQTY - kOverlap To stepQTY - 1: forceB at k - stepQTY + kOverlap
            for k in range(pre_advance_substep_count, substep_count):
                advanced_ramp_index = k - substep_count + overlap_substep_count
                elbow_a_force = (
                    elbow_a_force_current * current_sample_weight[k]
                    + elbow_a_force_next * next_sample_weight[k]
                )
                elbow_b_force = (
                    elbow_b_force_advanced_current * current_sample_weight[advanced_ramp_index]
                    + elbow_b_force_advanced_next * next_sample_weight[advanced_ramp_index]
                )
                sample_forces.append(elbow_a_force - elbow_b_force)
            yield sample_forces


def elbow_forces(
    force_history, sample_rate: float, span_length: float, celerity: float, substep_count: int
) -> Iterator[tuple[int, list[float], list[float]]]:
    """Yield, per sample, ``(phase, forceA list, forceB list)`` for the trace (Session V.1).

    The same walk and the same per-sub-step values as ``unbalance_force``, kept apart
    before the subtraction: ``forceA[k] - forceB[k]`` of a sample is bitwise the
    corresponding ``unbalance_force`` value (same operands, same operation;
    ``tests/test_trace.py`` pins it on the sweep and the golden history).

    Parameters
    ----------
    force_history, sample_rate, span_length, celerity, substep_count
        As ``unbalance_force``.

    Yields
    ------
    phase : int
        ``PHASE_TRANSIT`` (0: ``forceA`` held at the first sample while ``forceB``
        ramps) or ``PHASE_FORCED`` (1: both ramp).
    elbow_a_force, elbow_b_force : list of float
        The force at elbow A and the delayed force at elbow B, N, per sub-step; the same
        lengths as the ``unbalance_force`` samples (the last delay sample truncated).

    Raises
    ------
    ZeroDivisionError, IndexError
        As ``unbalance_force`` (D-7, D-8).
    """
    walk = _walk_constants(force_history, sample_rate, span_length, celerity, substep_count)
    (
        substep_count,
        overlap_substep_count,
        transit_delay_substeps,
        next_sample_weight,
        current_sample_weight,
    ) = (
        walk.substep_count,
        walk.overlap_substep_count,
        walk.transit_delay_substeps,
        walk.next_sample_weight,
        walk.current_sample_weight,
    )
    pre_advance_substep_count = substep_count - overlap_substep_count
    for item in _schedule(walk):
        if item[0] == PHASE_TRANSIT:
            _phase, sample_number, elbow_a_force, elbow_b_force_current, elbow_b_force_next = item
            first_substep_number = (sample_number - 1) * substep_count + 1
            elbow_a_forces = []
            elbow_b_forces = []
            for k in range(substep_count):
                elbow_a_forces.append(elbow_a_force)
                elbow_b_forces.append(
                    elbow_b_force_current * current_sample_weight[k]
                    + elbow_b_force_next * next_sample_weight[k]
                )
                if first_substep_number + k > transit_delay_substeps:
                    break
            yield (PHASE_TRANSIT, elbow_a_forces, elbow_b_forces)
        else:
            (
                _phase,
                elbow_a_force_current,
                elbow_a_force_next,
                elbow_b_force_current,
                elbow_b_force_next,
                elbow_b_force_advanced_current,
                elbow_b_force_advanced_next,
            ) = item
            elbow_a_forces = []
            elbow_b_forces = []
            for k in range(0, pre_advance_substep_count):
                elbow_a_forces.append(
                    elbow_a_force_current * current_sample_weight[k]
                    + elbow_a_force_next * next_sample_weight[k]
                )
                elbow_b_forces.append(
                    elbow_b_force_current * current_sample_weight[k + overlap_substep_count]
                    + elbow_b_force_next * next_sample_weight[k + overlap_substep_count]
                )
            for k in range(pre_advance_substep_count, substep_count):
                advanced_ramp_index = k - substep_count + overlap_substep_count
                elbow_a_forces.append(
                    elbow_a_force_current * current_sample_weight[k]
                    + elbow_a_force_next * next_sample_weight[k]
                )
                elbow_b_forces.append(
                    elbow_b_force_advanced_current * current_sample_weight[advanced_ramp_index]
                    + elbow_b_force_advanced_next * next_sample_weight[advanced_ramp_index]
                )
            yield (PHASE_FORCED, elbow_a_forces, elbow_b_forces)
