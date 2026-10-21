"""Pressure response at a closing valve: the 1-D Method-of-Characteristics water-hammer
driver (``GetPressureResponse``, ``legacy/vba/Existing Code.bas`` lines 155-307).

A single pipe runs from the valve (node 0) to the pump (node ``pipeSegQTY``). The valve
closes along a pattern spread evenly over ``closureTime``; each loop iteration advances
two time steps on a staggered grid (A nodes ``0..N`` and B half-cells ``0..N-1``, with
``B[N]`` holding the pump boundary): the valve boundary sets the A node 0 from the
velocity, the first half-loop updates the A nodes from the B cells, the pump boundary
sets ``B[N]`` from the velocity at the last A node, the second half-loop updates the B
cells from the A nodes. The result is the pressure at the valve after every iteration.

This module is a standalone driver: it knows nothing about the peak-response solvers,
and they know nothing about it (``docs/architecture.md``). The VBA semantics it relies on
come from ``vba_compat`` (``CLng``, ``floor``, ``modDbl``; frozen) and ``_vba_semantics``
(``vba_min``/``vba_max``, the VBA tie rule).

Differences from ``legacy_port.get_pressure_response`` (none numerical; proved bitwise on
the Example-sheet case and a 50-case seeded sweep by ``tests/test_differential.py``):

* The set-up constants are computed once into a ``PressureSetup`` and the column lives
  in four contiguous 1-D arrays (``p_a``, ``v_a``, ``p_b``, ``v_b``) instead of two
  ``(2, N + 1)`` arrays; ``sysMat(0 To 1)`` is two locals. Array elements are read as
  ``numpy.float64`` exactly as the legacy did, so every operation is the same IEEE
  double operation in the same order, and the run stays under ``np.errstate(raise)`` so
  ``rhoC = 0`` and overflow raise where they did.
* The pattern walk indexes a 0-based 2-D array (``loads.as_history_2d``) with ``[i - 1,
  j - 1]`` where the legacy indexed the padded 1-based copy with ``[i, j]``; the index
  arithmetic itself (``floor``, ``modDbl``, the clamps, D-10/D-11) is unchanged.
* The two half-loops keep their different friction clamps (``0.9`` vs ``0.9 * rhoC``,
  D-6) and the result keeps its ``outMax + 1`` samples at ``2 * timeStep`` spacing
  (D-22). The valve pattern's 0-based result array was already 0-based in the legacy.

``get_pressure_response`` is a thin alias with the legacy signature.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np

from surge_sdof import loads
from surge_sdof._vba_semantics import vba_max, vba_min
from surge_sdof.vba_compat import clng, mod_dbl, vba_floor

__all__ = [
    "PressureSetup",
    "grid_size",
    "setup",
    "initial_column",
    "valve_closure",
    "valve_boundary",
    "pump_boundary",
    "half_step_a_from_b",
    "half_step_b_from_a",
    "pressure_response",
    "get_pressure_response",
]


class PressureSetup(NamedTuple):
    """Run constants of ``GetPressureResponse`` (VBA lines 206-220)."""

    out_max: int
    """``CLng(closureTime / timeStep)``: the result has ``out_max + 1`` samples."""
    pipe_seg_qty: int
    """``N``: A nodes ``0..N``; the pump boundary sits at ``B[N]``."""
    factor: float
    """Pattern samples per time step (``UBound1 * UBound2 * timeStep / closureTime``)."""
    rho_c: float
    velocity_initial: float
    """Initial flow velocity, m/s, negative (flow towards the valve)."""
    valve_loss: float
    """Valve loss coefficient, Pa/(m/s)^2, fully open."""
    valve_dp_initial: float
    pipe_loss: float
    """Friction loss per half-cell, Pa."""


# VBA line 207
def grid_size(out_max: int, length_to_pump: float, celerity: float, time_step: float) -> int:
    """``pipeSegQTY = 1 + CLng(min(outMax, L / (c * dt)) / 2)``: the pipe is truncated to
    what a wave can traverse in ``closureTime`` (D-22)."""
    return 1 + clng(vba_min(out_max, length_to_pump / (celerity * time_step)) / 2)


# VBA lines 206-220
def setup(
    pattern_rows: int,
    pattern_cols: int,
    closure_time: float,
    celerity: float,
    density: float,
    time_step: float,
    pressure_drop_from_pump: float,
    flow_rate: float,
    pipe_area: float,
    valve_cv: float,
    length_to_pump: float,
) -> PressureSetup:
    """The run constants, in the VBA's expressions and units (m³/h, mm², bar → SI)."""
    out_max = clng(closure_time / time_step)
    pipe_seg_qty = grid_size(out_max, length_to_pump, celerity, time_step)
    factor = pattern_rows * pattern_cols * time_step / closure_time
    rho_c = density * celerity
    velocity_initial = -flow_rate * 1000000 / (pipe_area * 60 * 60)  # m/s
    valve_loss = (
        (density / 1000) * 100000 / (((valve_cv * 0.865 * 1000000) / (pipe_area * 60 * 60)) ** 2)
    )  # Pa/(m/s)^2
    valve_dp_initial = valve_loss * (velocity_initial**2)  # Pa
    pipe_loss = pressure_drop_from_pump * 100000 / (1 + pipe_seg_qty * 2)  # Pa/segment
    return PressureSetup(
        out_max,
        pipe_seg_qty,
        factor,
        rho_c,
        velocity_initial,
        valve_loss,
        valve_dp_initial,
        pipe_loss,
    )


# VBA lines 222-229
def initial_column(s: PressureSetup):
    """Steady-state column: pressures rising from the valve towards the pump by
    ``pipeLoss`` per half-cell, velocities falling with it. Returns ``(p_a, v_a, p_b,
    v_b, vel_at_pump)``; the arrays have ``N + 1`` elements (``B[N]`` is the pump
    boundary) and ``vel_at_pump`` is the initial ``B`` velocity there."""
    n = s.pipe_seg_qty
    p_a = np.zeros(n + 1)
    v_a = np.zeros(n + 1)
    p_b = np.zeros(n + 1)
    v_b = np.zeros(n + 1)
    for i in range(0, n + 1):
        p_a[i] = i * 2 * s.pipe_loss + s.valve_dp_initial
        p_b[i] = (1 + i * 2) * s.pipe_loss + s.valve_dp_initial
        v_a[i] = -i * 2 * s.pipe_loss / s.rho_c + s.velocity_initial
        v_b[i] = -(1 + i * 2) * s.pipe_loss / s.rho_c + s.velocity_initial
    vel_at_pump = v_b[n]
    return p_a, v_a, p_b, v_b, vel_at_pump


# VBA lines 244-265
def valve_closure(pattern: np.ndarray, tot_ind: int, factor: float) -> float:
    """Valve closure (0 open .. 1 closed) at loop iteration ``tot_ind``: the pattern,
    walked column-major (first index fastest), stretched evenly over ``closureTime`` and
    linearly interpolated between consecutive samples; held at its last value beyond
    the end. ``pattern`` is 0-based ``(rows, cols)``; the index arithmetic is the VBA's
    1-based one (``floor``, ``modDbl``, the ``i >= U1 And j < U2`` wrap, D-10)."""
    n1, n2 = pattern.shape
    position = tot_ind * factor * 2
    # VBA assigns a Double (modDbl + 1) to the Long i: implicit CLng.
    i = clng(mod_dbl(vba_floor(position), n1) + 1)
    j = vba_floor(position / n1) + 1
    if i >= n1 and j < n2:
        i = n1
        jmax = vba_min(j + 1, n2)
        imax = 1
    else:
        if i > n1:
            i = n1
        jmax = j
        imax = vba_min(i + 1, n1)
    if j > n2:
        return pattern[n1 - 1, n2 - 1]
    elif i == imax and j == jmax:
        return pattern[i - 1, j - 1]
    else:
        frac = ((i - 1) + (j - 1) * n1 - position) / (
            (i - 1) + (j - 1) * n1 - ((imax - 1) + (jmax - 1) * n1)
        )
        return pattern[i - 1, j - 1] * (1 - frac) + pattern[imax - 1, jmax - 1] * frac


# VBA lines 267-273
def valve_boundary(closure: float, p_a, v_a, p_b, v_b, s: PressureSetup) -> None:
    """A node 0 from the closure: open valve (``closure < 0.999999999``) - velocity from
    the characteristic, pressure the smaller of the valve loss at that velocity and the
    characteristic pressure (floored at the B cell); closed valve - zero velocity, pressure
    from the stopped B cell."""
    if closure < 0.999999999:
        v_a[0] = (v_a[0] + v_b[0]) / 2 + (p_a[0] - p_b[0]) / (2 * s.rho_c)
        p_a[0] = vba_min(
            ((s.valve_loss / (1 - closure)) * (v_a[0] ** 2)),
            vba_max(p_b[0], (p_a[0] + p_b[0]) / 2 - v_a[0] * s.rho_c),
        )
    else:
        v_a[0] = 0
        p_a[0] = vba_max(p_b[0], p_b[0] - v_b[0] * s.rho_c)


# VBA lines 275-285
def half_step_a_from_b(p_a, v_a, p_b, v_b, i_max: int, s: PressureSetup) -> None:
    """A nodes ``1..i_max`` from the neighbouring B cells (``i_max = min(N, totInd)``).
    Friction ``loss`` is clamped at ``0.9 * v`` (VBA quirk D-6: the other half-loop
    clamps at ``0.9 * rhoC * v``)."""
    rho_c = s.rho_c
    pipe_loss = s.pipe_loss
    for i in range(1, i_max + 1):
        v = (v_b[i - 1] + v_b[i]) / 2
        vel_init_local = i * 2 * pipe_loss / rho_c + s.velocity_initial
        loss = v * vba_min(0.9, abs(v) * pipe_loss / (rho_c * (vel_init_local**2)))

        sys0 = -loss - v_b[i - 1] - p_b[i - 1] / rho_c
        sys1 = loss - v_b[i] + p_b[i] / rho_c

        v_a[i] = -(sys0 + sys1) / 2
        p_a[i] = vba_max(0, -(sys0 - sys1) * rho_c / 2)


# VBA lines 287-288
def pump_boundary(
    p_a,
    v_a,
    p_b,
    v_b,
    vel_at_pump: float,
    pump_ramp_pressure: float,
    pressure_drop_from_pump: float,
    s: PressureSetup,
) -> None:
    """``B[N]`` from the velocity at the last A node: the pump pressure ramps from
    operating to shut-in as the (reverse-flow-clipped) velocity falls to zero."""
    n = s.pipe_seg_qty
    p_b[n] = vba_max(
        0,
        s.valve_dp_initial
        + 100000
        * (
            pressure_drop_from_pump
            + pump_ramp_pressure * (1 - (vba_min(0, v_a[n]) / vel_at_pump) ** 2)
        ),
    )
    v_b[n] = vba_min(0, v_a[n])


# VBA lines 290-300
def half_step_b_from_a(p_a, v_a, p_b, v_b, i_max: int, s: PressureSetup) -> None:
    """B cells ``0..i_max`` from the neighbouring A nodes (``i_max = min(N - 1, totInd)``).
    Friction ``loss`` is clamped at ``0.9 * rhoC * v`` (VBA quirk D-6)."""
    rho_c = s.rho_c
    pipe_loss = s.pipe_loss
    for i in range(0, i_max + 1):
        v = (v_a[i] + v_a[i + 1]) / 2
        vel_init_local = (1 + i * 2) * pipe_loss / rho_c + s.velocity_initial
        loss = v * vba_min(0.9 * rho_c, abs(v) * pipe_loss / (rho_c * (vel_init_local**2)))

        sys0 = -loss - v_a[i] - p_a[i] / rho_c
        sys1 = loss - v_a[i + 1] + p_a[i + 1] / rho_c

        v_b[i] = -(sys0 + sys1) / 2
        p_b[i] = vba_max(0, -(sys0 - sys1) * rho_c / 2)


def pressure_response(
    valve_pattern,
    closure_time: float,
    celerity: float,
    density: float,
    time_step: float,
    pressure_drop_from_pump: float,
    flow_rate: float,
    pipe_area: float,
    valve_cv: float,
    length_to_pump: float,
    pump_ramp_pressure: float,
) -> np.ndarray:
    """Pressure at the valve while it closes (``GetPressureResponse``).

    Parameters as ``legacy_port.get_pressure_response``: ``valve_pattern`` closure
    history 0 (open) to 1 (closed), 1-D or 2-D walked column-major, spread evenly over
    ``closure_time`` (s); ``celerity`` (m/s); ``density`` (kg/m³); ``time_step`` (s);
    ``pressure_drop_from_pump`` pump-to-valve drop at ``flow_rate`` (bar); ``flow_rate``
    (m³/h); ``pipe_area`` (mm²); ``valve_cv`` (US gpm basis); ``length_to_pump`` (m);
    ``pump_ramp_pressure`` operating-to-shut-in rise (bar).

    Returns the 0-based ``resultArray(0 To outMax)``: the valve pressure (Pa) after each
    loop iteration of two time steps, ``outMax + 1`` samples (D-22).
    """
    pattern = loads.as_history_2d(valve_pattern)
    with np.errstate(divide="raise", invalid="raise", over="raise"):
        s = setup(
            pattern.shape[0],
            pattern.shape[1],
            closure_time,
            celerity,
            density,
            time_step,
            pressure_drop_from_pump,
            flow_rate,
            pipe_area,
            valve_cv,
            length_to_pump,
        )
        p_a, v_a, p_b, v_b, vel_at_pump = initial_column(s)
        n = s.pipe_seg_qty
        result = np.zeros(s.out_max + 1)  # ReDim resultArray(0 To outMax)
        for tot_ind in range(0, s.out_max + 1):
            # every loop is 2 time steps
            closure = valve_closure(pattern, tot_ind, s.factor)
            # valve pressure is determined by the velocity
            valve_boundary(closure, p_a, v_a, p_b, v_b, s)
            # MoC
            half_step_a_from_b(p_a, v_a, p_b, v_b, vba_min(n, tot_ind), s)
            # pump pressure is determined by the velocity
            pump_boundary(
                p_a, v_a, p_b, v_b, vel_at_pump, pump_ramp_pressure, pressure_drop_from_pump, s
            )
            # MoC
            half_step_b_from_a(p_a, v_a, p_b, v_b, vba_min(n - 1, tot_ind), s)
            result[tot_ind] = p_a[0]
    return result


def get_pressure_response(
    valve_pattern,
    closure_time,
    celerity,
    density,
    time_step,
    pressure_drop_from_pump,
    flow_rate,
    pipe_area,
    valve_cv,
    length_to_pump,
    pump_ramp_pressure,
):
    """Legacy-signature alias of ``pressure_response`` (same arguments, same result)."""
    return pressure_response(
        valve_pattern,
        closure_time,
        celerity,
        density,
        time_step,
        pressure_drop_from_pump,
        flow_rate,
        pipe_area,
        valve_cv,
        length_to_pump,
        pump_ramp_pressure,
    )
