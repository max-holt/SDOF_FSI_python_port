"""The SDOF pipe proxy: portal-frame height, restraint with support gap, Coulomb
friction and the time-step kernel.

Behaviour is that of the structure in ``GetPeakResponse`` and ``GetPeakResponseJC``
(``legacy/vba/Existing Code.bas``: VBA lines 384-392 for the lumped set-up, 726-729 for the
junction-coupling set-up, 424-445 for the step); ``tests/test_differential.py`` proves each
function against ``legacy_port.py`` bitwise on the golden inputs and a seeded sweep.

This module knows nothing about force histories, transit delays, the MoC column, sample
bookkeeping or peak trackers. Of the fluid it knows only what the junction-coupling set-up
needs: ``jc_params`` reads the fluid density and flow area to take the core fluid out of
the rigid mass. The set-up functions take ``response``'s ``PipeSpan``, ``Restraint`` and
``Fluid`` (imported for the annotations only). ``step_scalars`` takes the already-summed
applied force and returns the new state. See ``docs/architecture.md``.

State and parameters
--------------------
The state ``(x, v, a)`` is a plain tuple of Python floats; ``SdofParams`` is a named
tuple. Python floats (not numpy scalars) are used on purpose: the arithmetic is IEEE double either way (``**`` calls C ``pow`` on both),
and a profile of the lumped solver showed numpy-scalar overhead at about a third of its
wall time.

Exactness
---------
* ``(a + aNew) * dt / 2`` is written ``(a + aNew) * half_dt`` with ``half_dt = dt / 2``:
  scaling by a power of two commutes with rounding (no subnormals here), so the doubles
  are identical.
* ``minUnsigned(gap, x)``, ``max(0, |x| - gap)`` and ``sign(...)`` are inlined branch for
  branch (VBA lines 19-60); the ``* sign(...)`` products are ``* +-1.0`` and are written
  as negations, which is exact. ``sign(v, 0.000001) * fricAcc`` with ``sign = 0`` is
  ``v + s - 0.0``, i.e. ``v + s``, so that branch adds nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import numba

if TYPE_CHECKING:
    from surge_sdof.response import Fluid, PipeSpan, Restraint

__all__ = [
    "VBA_PI",
    "SdofParams",
    "solve_quartic",
    "solve_portal_height",
    "lumped_params",
    "jc_params",
    "effective_displacement",
    "step_scalars",
    "substep_friction",
]

# VBA ``Const pi = 3.14159265358979`` (15 digits; differs from math.pi by 3e-15 and a
# substitution would not be bit-preserving, port_review §1.1).
VBA_PI = 3.14159265358979

# Percent per unit fraction: ``damping_percent / PERCENT`` is the damping ratio (fraction of
# critical), dimensionless. Unit conversion of the input (VBA lines 391 and 728).
PERCENT = 100

# Gravitational acceleration, m/s², as the VBA writes it (lines 392 and 729). The only
# constant that fixes the model's units to metres and seconds.
GRAVITY = 9.81

# Velocity below which the slip branch applies no friction, m/s: the VBA's
# ``sign(v, 0.000001)`` (lines 428 and 856). VBA quirk D-20 preserved: for
# ``fricAcc <= |v| < FRICTION_DEAD_ZONE`` no friction acts in that sub-step.
FRICTION_DEAD_ZONE = 0.000001

# Convergence test of ``solve_quartic``: stop when ``|residual / c0| <`` this, dimensionless
# (VBA ``solvePoly``, line 146).
NEWTON_RELATIVE_TOLERANCE = 0.000001

# Relaxation of each Newton update of ``solve_quartic``, dimensionless (VBA ``solvePoly``
# ``Const relax = 0.25``, line 138).
NEWTON_RELAXATION = 0.25

# Iteration limit of ``solve_quartic`` (VBA ``For i = 1 To 100``, line 144); there is no
# convergence check at exit.
NEWTON_ITERATION_LIMIT = 100

# Last index of the end-fixity refinement loop of ``solve_portal_height`` (VBA
# ``For i = 0 To 10``, line 385): 11 passes after the seed solve.
END_FIXITY_LAST_PASS = 10


class SdofParams(NamedTuple):
    """Constants of the SDOF update; ``step_scalars`` and the compiled loop take them whole.

    Attributes
    ----------
    mass : float
        Modal mass of the proxy, kg (VBA ``mass``).
    stiffness : float
        Stiffness with the support gaps open, N/m (VBA ``stiffness``).
    damping : float
        Viscous damping coefficient, N·s/m (VBA ``damping``).
    friction_velocity_step : float
        Velocity Coulomb friction removes per substep, m/s (VBA ``fricAcc`` =
        ``0.5 * dynamicFric * 9.81 * dt``; the only quantity whose units are fixed to m
        and s by the VBA).
    support_gap : float
        Support gap, m (VBA ``gap``).
    closed_gap_stiffness_ratio : float
        ``restrainFreqRatio ^ 2``, dimensionless: the stiffness beyond the gap relative
        to ``stiffness``.
    """

    mass: float
    stiffness: float
    damping: float
    friction_velocity_step: float
    support_gap: float
    closed_gap_stiffness_ratio: float


# VBA line 137: Function solvePoly(varA As Double, varB As Double, varC As Double) As Double
def solve_quartic(
    quartic_constant: float, cubic_coefficient: float, quartic_coefficient: float
) -> float:
    """The root ``L`` of ``c0 + c3 L^3 + c4 L^4 = 0``, by relaxed Newton iteration.

    Parameters
    ----------
    quartic_constant, cubic_coefficient, quartic_coefficient : float
        The coefficients ``c0``, ``c3``, ``c4`` of ``c0 + c3 L^3 + c4 L^4`` (VBA ``varA``,
        ``varB``, ``varC``). In the portal-frame use the root is a length in m and the
        coefficients carry the matching units (kg·m³, kg, kg/m).

    Returns
    -------
    float
        The root ``L`` after the last Newton update (m in the portal-frame use).

    Notes
    -----
    VBA ``solvePoly`` (line 137); a literal copy of ``legacy_port.solve_poly`` so that this
    module does not import the frozen legacy module.
    Seed ``(-varA / varB) ^ (1 / 3)``, relaxation 0.25, at most 100 iterations, stop
    when ``|error / varA| < 1e-6``; there is no convergence check at exit. VBA quirk
    D-12: a negative base makes the Python seed complex where VBA raises error 5.
    """
    root = (-quartic_constant / cubic_coefficient) ** (1 / 3)
    for _i in range(1, NEWTON_ITERATION_LIMIT + 1):
        residual = (
            quartic_constant + cubic_coefficient * (root**3) + quartic_coefficient * (root**4)
        )
        if abs(residual / quartic_constant) < NEWTON_RELATIVE_TOLERANCE:
            break
        slope = 3 * cubic_coefficient * (root**2) + 4 * quartic_coefficient * (root**3)
        root = root - NEWTON_RELAXATION * residual / slope
    return root


# VBA lines 384-387
def solve_portal_height(
    span_length: float, flexural_rigidity: float, mass_per_length: float, natural_frequency: float
) -> float:
    """The leg height of the portal-frame proxy that gives the span its natural frequency.

    The height ``h`` at which the frame stiffness ``12 EI (0.5 + 1.5 (h / (L + h))^2) / h^3``
    gives the natural frequency with the mass ``(L + 4h/3) m'``: the seed
    ``solve_quartic`` call plus 11 refinement passes of the end-fixity factor.

    Parameters
    ----------
    span_length : float
        Length between elbows, m.
    flexural_rigidity : float
        Flexural rigidity ``E * I``, N·m².
    mass_per_length : float
        Mass per unit length (pipe and contents), kg/m.
    natural_frequency : float
        Natural frequency with the gaps open, Hz.

    Returns
    -------
    float
        Leg height, m.

    Notes
    -----
    VBA lines 384-387 (``portalFrameHeight``; the seed is VBA ``solvePoly``).
    """
    omega_squared = (2 * VBA_PI * natural_frequency) ** 2
    cubic_coefficient = span_length * mass_per_length
    # Proposed derivation, for Ben to confirm: the 4 / 3 is the span's full mass plus two
    # thirds of each leg's mass taking part in the motion, (L + 2 * (2/3) h) m' = (L + 4h/3) m'.
    # Written for the single expansion-loop shape.
    quartic_coefficient = mass_per_length * 4 / 3
    # Proposed derivation, for Ben to confirm: 12 * EI / h^3 is the lateral stiffness of a leg
    # of height h fixed against rotation at both ends.
    portal_frame_height = solve_quartic(
        -12 * flexural_rigidity / omega_squared, cubic_coefficient, quartic_coefficient
    )
    for _i in range(0, END_FIXITY_LAST_PASS + 1):
        # Proposed derivation, for Ben to confirm: 0.5 + 1.5 * (h / (L + h))^2 is a factor on that
        # stiffness, running from 0.5 when the legs are short against the span (two legs acting as
        # cantilevers, 2 * 3EI/h^3) to 2 when they are long (two legs fixed at both ends,
        # 2 * 12EI/h^3). The squared ratio is an interpolation between the two.
        portal_frame_height = solve_quartic(
            -12
            * flexural_rigidity
            * (0.5 + 1.5 * ((portal_frame_height / (span_length + portal_frame_height)) ** 2))
            / omega_squared,
            cubic_coefficient,
            quartic_coefficient,
        )
    return portal_frame_height


# VBA lines 389-392
def lumped_params(
    span: PipeSpan, restraint: Restraint, portal_frame_height: float, substep_duration: float
) -> SdofParams:
    """Mass, stiffness, damping and friction increment of the lumped proxy.

    Parameters
    ----------
    span : response.PipeSpan
        The span: its length (m) and mass per length (kg/m) are read.
    restraint : response.Restraint
        Natural frequency (Hz), damping (% of critical), friction coefficient, support gap
        (m) and closed-gap frequency ratio.
    portal_frame_height : float
        From ``solve_portal_height``, m.
    substep_duration : float
        Substep, s (``1 / (sample_rate * substep_count)``).

    Returns
    -------
    SdofParams
        ``mass = (L + 4h/3) m'`` (kg), ``stiffness = (2 pi f)^2 mass`` (N/m),
        ``damping = 2 sqrt(k m) zeta / 100`` (N·s/m), ``friction_velocity_step = 0.5 mu 9.81 dt``
        (m/s), ``support_gap`` (m), ``closed_gap_frequency_ratio^2``.

    Notes
    -----
    VBA lines 389-392 (``GetPeakResponse``). ``jc_params`` is the ``GetPeakResponseJC``
    variant (core fluid removed from the mass); the two are kept as separate functions,
    not a flag.
    """
    # Proposed derivation, for Ben to confirm: the 4 / 3 is the span's full mass plus two
    # thirds of each leg's mass taking part in the motion, (L + 2 * (2/3) h) m' = (L + 4h/3) m'.
    # Written for the single expansion-loop shape.
    span_length = span.span_length
    mass_per_length = span.mass_per_length
    mass = (span_length + portal_frame_height * 4 / 3) * mass_per_length
    stiffness = ((restraint.natural_frequency * 2 * VBA_PI) ** 2) * mass
    damping = 2 * ((stiffness * mass) ** 0.5) * restraint.damping_percent / PERCENT
    # Proposed derivation, for Ben to confirm: the 0.5 is the share of the pipe's weight carried
    # on the moving part, so the Coulomb force is 0.5 * mu * m * g and its velocity step per
    # substep 0.5 * mu * g * dt.
    friction_velocity_step = 0.5 * restraint.friction_coefficient * GRAVITY * substep_duration
    return _sdof_params(mass, stiffness, damping, friction_velocity_step, restraint)


# VBA lines 726-729 (GetPeakResponseJC)
def jc_params(
    span: PipeSpan,
    restraint: Restraint,
    fluid: Fluid,
    portal_frame_height: float,
    substep_duration: float,
) -> SdofParams:
    """Mass, stiffness, damping and friction increment of the junction-coupling proxy.

    The core fluid is removed from the mass (rigid mass only) while stiffness, critical
    damping and the friction increment are scaled on the total mass, as the VBA does.

    Parameters
    ----------
    span : response.PipeSpan
        The span: its length (m) and mass per length of pipe *and* fluid (kg/m) are read.
    restraint : response.Restraint
        As ``lumped_params``; the natural frequency (Hz) is modelled with the fluid mass
        included.
    fluid : response.Fluid
        Fluid density (kg/m³) and flow area (m²): the core fluid removed from the mass.
    portal_frame_height : float
        From ``solve_portal_height``, m.
    substep_duration : float
        Substep, s.

    Returns
    -------
    SdofParams
        ``mass`` kg (rigid), ``stiffness`` N/m and ``damping`` N·s/m on the total mass,
        ``friction_velocity_step`` m/s corrected by ``total mass / rigid mass``,
        ``support_gap`` m, ``closed_gap_stiffness_ratio``.

    Notes
    -----
    VBA lines 726-729 (``GetPeakResponseJC``). The expressions keep the VBA's left-to-right
    association, which differs from
    ``lumped_params`` (there ``stiffness = w2 * mass``; here ``w2 * (L + h * 4 / 3) * m'``).
    """
    # Proposed derivation, for Ben to confirm: the 4 / 3 is the span's full mass plus two
    # thirds of each leg's mass taking part in the motion, (L + 2 * (2/3) h) m' = (L + 4h/3) m'.
    # Written for the single expansion-loop shape.
    # The same factor in the three total-mass terms below.
    span_length = span.span_length
    mass_per_length = span.mass_per_length
    natural_frequency = restraint.natural_frequency
    mass = (portal_frame_height * 4 / 3) * mass_per_length + span_length * (
        mass_per_length - fluid.fluid_density * fluid.flow_area
    )  # remove core fluid to get rigid mass
    stiffness = (
        ((natural_frequency * 2 * VBA_PI) ** 2)
        * (span_length + portal_frame_height * 4 / 3)
        * mass_per_length
    )  # assume total mass has same bases as natural frequency (fluid is included in CAESAR)
    damping = (
        2
        * ((stiffness * ((span_length + portal_frame_height * 4 / 3) * mass_per_length)) ** 0.5)
        * restraint.damping_percent
        / PERCENT
    )  # assume critical damping is relative to total mass
    # Proposed derivation, for Ben to confirm: the 0.5 is the share of the pipe's weight carried
    # on the moving part (as in lumped_params). The weight is that of the total mass (pipe and
    # contents) while the velocity step acts on the rigid mass, hence total mass / rigid mass.
    friction_velocity_step = (
        0.5
        * restraint.friction_coefficient
        * GRAVITY
        * substep_duration
        * ((span_length + portal_frame_height * 4 / 3) * mass_per_length)
        / mass
    )  # mass correction from frictional to inertial
    return _sdof_params(mass, stiffness, damping, friction_velocity_step, restraint)


def _sdof_params(
    mass: float,
    stiffness: float,
    damping: float,
    friction_velocity_step: float,
    restraint: Restraint,
) -> SdofParams:
    """The ``SdofParams`` of a set-up, every field a Python float.

    Parameters
    ----------
    mass : float
        Modal mass, kg.
    stiffness : float
        Stiffness with the gaps open, N/m.
    damping : float
        Viscous damping coefficient, N·s/m.
    friction_velocity_step : float
        Velocity Coulomb friction removes per substep, m/s.
    restraint : response.Restraint
        Its support gap (m) and closed-gap frequency ratio (dimensionless) are read.

    Returns
    -------
    SdofParams
        With ``closed_gap_stiffness_ratio`` the square of the closed-gap frequency ratio.
    """
    return SdofParams(
        float(mass),
        float(stiffness),
        float(damping),
        float(friction_velocity_step),
        float(restraint.support_gap),
        float(restraint.closed_gap_frequency_ratio) ** 2,
    )


# VBA line 424 (restoring term) and 611 (static-equivalent force)
@numba.njit(cache=True)
def effective_displacement(
    x: float, support_gap: float, closed_gap_stiffness_ratio: float
) -> float:
    """The displacement seen by the open-gap stiffness, with the support gap closed
    beyond it.

    ``minUnsigned(gap, x) + max(0, |x| - gap) * sign(x) * ratio^2``: ``x`` up to the
    support gap, then ``gap + (|x| - gap) * closed_gap_stiffness_ratio`` with the sign of
    ``x`` beyond it.

    Parameters
    ----------
    x : float
        Displacement, m.
    support_gap : float
        Support gap, m.
    closed_gap_stiffness_ratio : float
        ``restrainFreqRatio ^ 2``, dimensionless.

    Returns
    -------
    float
        Effective displacement, m; times the stiffness it is the restoring force.

    Notes
    -----
    VBA line 424 (restoring term) and 611 (static-equivalent force). The VBA helpers'
    ladders (``max`` lines 11-17, ``minUnsigned`` 19-33, ``sign`` 51-59) are written out
    branch for branch, including the ``gap = 0`` and ``x = 0`` cases. Compiled
    (``numba.njit(cache=True)``, scalars only): ``step_scalars`` calls it for the restoring
    term, ``response._peak_response`` for the static-equivalent force.
    """
    x_magnitude = abs(x)
    # minUnsigned(gap, x)
    if abs(support_gap) < x_magnitude:
        x_within_gap = support_gap if x > 0 else -support_gap  # support_gap * sign(x); x != 0 here
    elif support_gap == 0:
        x_within_gap = x
    else:
        x_within_gap = x if support_gap > 0 else -x  # x * sign(gap)
    # max(0, Abs(x) - gap) * sign(x)
    x_excess_magnitude = x_magnitude - support_gap
    if x_excess_magnitude < 0:
        x_excess_magnitude = 0.0
    if x > 0:
        x_beyond_gap = x_excess_magnitude
    elif x < 0:
        x_beyond_gap = -x_excess_magnitude
    else:
        x_beyond_gap = x_excess_magnitude * 0.0
    return x_within_gap + x_beyond_gap * closed_gap_stiffness_ratio


@numba.njit(cache=True)
def step_scalars(
    x: float,
    v: float,
    a: float,
    f_applied: float,
    sdof_params: SdofParams,
    dt: float,
) -> tuple[float, float, float]:
    """Advance the SDOF proxy by one substep: displacement, velocity and acceleration.

    Explicit new acceleration from the old ``x`` and ``v``, trapezoidal ``v`` and ``x``,
    and stick (``|v| < friction_velocity_step``) / slip Coulomb friction. Compiled with
    ``numba.njit(cache=True)`` (no fastmath); with ``NUMBA_DISABLE_JIT=1`` it is
    this Python function. Called per substep from ``response._integrate_kernel``.

    Parameters
    ----------
    x, v, a : float
        State at the end of the previous substep: m, m/s, m/s².
    f_applied : float
        Everything the caller adds to the restoring and damping terms, N: the unbalance
        force plus the junction force, or the junction force alone in free decay.
    sdof_params : SdofParams
        Mass (kg), stiffness (N/m), damping (N·s/m), friction velocity step (m/s), support
        gap (m) and closed-gap stiffness ratio (dimensionless).
    dt : float
        Substep, s.

    Returns
    -------
    tuple of float
        ``(x, v, a)`` at the end of this substep: m, m/s, m/s².

    Notes
    -----
    * VBA lines 424-432 (``aNew``, ``fricAcc``, ``forceA - forceB``, ``dF``).
    * The scheme is explicit in the acceleration (not average-acceleration Newmark):
      with zero damping the amplitude grows about 2.5 % per cycle at ``omega dt`` of
      0.016 (NOTES.md "Findings worth knowing").
    * VBA quirk D-20 preserved: the slip branch uses ``sign(v, 0.000001)``, so for
      ``fricAcc <= |v| < 1e-6`` no friction is applied in that substep.
    * ``(a + aNew) * dt / 2`` is computed as ``(a + aNew) * half_dt``; scaling by a
      power of two commutes with rounding, so the doubles are identical to the VBA's.
    """
    mass = sdof_params.mass
    stiffness = sdof_params.stiffness
    damping = sdof_params.damping
    friction_velocity_step = sdof_params.friction_velocity_step
    support_gap = sdof_params.support_gap
    closed_gap_stiffness_ratio = sdof_params.closed_gap_stiffness_ratio
    half_dt = dt / 2

    # aNew = (F - (minUnsigned(gap, x) + max(0, Abs(x) - gap) * sign(x) * ratio^2)
    #             * stiffness - v * damping) / mass
    a_new = (
        f_applied
        - effective_displacement(x, support_gap, closed_gap_stiffness_ratio) * stiffness
        - v * damping
    ) / mass

    trapezoid_velocity_change = (a + a_new) * half_dt
    if abs(v) < friction_velocity_step:
        v_new = trapezoid_velocity_change
    else:
        # vNew = v + (a + aNew) * dt / 2 - sign(v, 0.000001) * fricAcc
        v_new = v + trapezoid_velocity_change
        if v > FRICTION_DEAD_ZONE:
            v_new = v_new - friction_velocity_step
        elif v < -FRICTION_DEAD_ZONE:
            v_new = v_new + friction_velocity_step
    x = x + (v + v_new) * half_dt
    return (x, v_new, a_new)


@numba.njit(cache=True)
def substep_friction(
    sdof_params: SdofParams, v_before: float, a_before: float, v: float, a: float, dt: float
) -> tuple[float, bool]:
    """The friction force of one ``step_scalars`` substep, as the trace records it, and
    whether the substep stuck.

    The friction force is what the trapezoidal velocity change misses: ``mass * (v -
    (v_before + (a_before + a) * half_dt)) / dt``, with the same ``half_dt = dt / 2`` as
    ``step_scalars``. Scalars only.

    Parameters
    ----------
    sdof_params : SdofParams
        Its mass (kg) and friction velocity step (m/s) are read.
    v_before, a_before : float
        Velocity (m/s) and acceleration (m/s²) before the substep.
    v, a : float
        Velocity (m/s) and acceleration (m/s²) after it.
    dt : float
        Substep, s.

    Returns
    -------
    friction_force : float
        N.
    is_sticking : bool
        ``|v_before| < friction_velocity_step``.
    """
    half_dt = dt / 2
    friction_force = sdof_params.mass * (v - (v_before + (a_before + a) * half_dt)) / dt
    is_sticking = abs(v_before) < sdof_params.friction_velocity_step
    return friction_force, is_sticking
