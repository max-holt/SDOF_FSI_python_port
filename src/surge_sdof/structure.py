"""The SDOF pipe proxy: portal-frame height, restraint with support gap, Coulomb
friction and the time-step kernel.

Behaviour is that of ``GetPeakResponse`` in ``legacy/vba/Existing Code.bas`` (VBA lines
384-392 for the set-up, 424-445 for the step); ``tests/test_differential.py`` proves each
function against ``legacy_port.py`` bitwise on the golden inputs and a seeded sweep.

This module knows nothing about force histories, transit delays, fluid coupling, sample
bookkeeping, max trackers or output types: ``step`` takes the already-summed applied
force and returns the new state. See ``docs/architecture.md``.

State and parameters
--------------------
``State = (x, v, a)`` is a plain tuple of Python floats; ``SdofParams`` is a named tuple
so the kernel can unpack it in one operation. Python floats (not numpy scalars) are used
on purpose: the arithmetic is IEEE double either way (``**`` calls C ``pow`` on both),
and the Stage 4.0 profile showed numpy-scalar overhead at about a third of the lumped
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

from typing import NamedTuple

__all__ = [
    "VBA_PI",
    "State",
    "SdofParams",
    "solve_poly",
    "solve_portal_height",
    "lumped_params",
    "jc_params",
    "effective_displacement",
    "restoring_force",
    "step",
]

# VBA ``Const pi = 3.14159265358979`` (15 digits; differs from math.pi by 3e-15 and a
# substitution would not be bit-preserving, port_review §1.1).
VBA_PI = 3.14159265358979

State = tuple[float, float, float]
"""``(x, v, a)``: displacement, velocity, acceleration at the end of a sub-step."""


class SdofParams(NamedTuple):
    """Constants of the SDOF update, in the order ``step`` unpacks them.

    Attributes
    ----------
    mass : float
        Modal mass of the proxy, kg (VBA ``mass``).
    stiffness : float
        Stiffness with the support gaps open, N/m (VBA ``stiffness``).
    damping : float
        Viscous damping coefficient, N·s/m (VBA ``damping``).
    fric_acc : float
        Coulomb friction velocity increment per sub-step, m/s (VBA ``fricAcc`` =
        ``0.5 * dynamicFric * 9.81 * dt``; the only quantity whose units are fixed to m
        and s by the VBA).
    gap : float
        Support gap, m (VBA ``gap``).
    ratio2 : float
        ``restrainFreqRatio ^ 2``, dimensionless: the stiffness beyond the gap relative
        to ``stiffness``.
    """

    mass: float
    stiffness: float
    damping: float
    fric_acc: float
    gap: float
    ratio2: float


# VBA line 137: Function solvePoly(varA As Double, varB As Double, varC As Double) As Double
def solve_poly(var_a: float, var_b: float, var_c: float) -> float:
    """Relaxed Newton solve of ``varA + varB * L^3 + varC * L^4 = 0`` for ``L``.

    Literal copy of ``legacy_port.solve_poly`` (VBA line 137) so that this module does
    not import the frozen legacy module.

    Parameters
    ----------
    var_a, var_b, var_c : float
        Polynomial coefficients. In the portal-frame use the root is a length in m and
        the coefficients carry the matching units (``var_a`` kg·m³, ``var_b`` kg,
        ``var_c`` kg/m).

    Returns
    -------
    float
        The root ``L`` after the last Newton update (m in the portal-frame use).

    Notes
    -----
    Seed ``(-varA / varB) ^ (1 / 3)``, relaxation 0.25, at most 100 iterations, stop
    when ``|error / varA| < 1e-6``; there is no convergence check at exit. VBA quirk
    D-12: a negative base makes the Python seed complex where VBA raises error 5.
    """
    relax = 0.25
    len_val = (-var_a / var_b) ** (1 / 3)
    for _i in range(1, 100 + 1):
        error_val = var_a + var_b * (len_val**3) + var_c * (len_val**4)
        if abs(error_val / var_a) < 0.000001:
            break
        grad = 3 * var_b * (len_val**2) + 4 * var_c * (len_val**3)
        len_val = len_val - relax * error_val / grad
    return len_val


# VBA lines 384-387
def solve_portal_height(
    physical_length: float, flexural_rigidity_ei: float, mass_per_unit_len: float, nat_freq: float
) -> float:
    """Leg height of the portal-frame proxy (VBA lines 384-387).

    The height ``h`` at which the frame stiffness ``12 EI (0.5 + 1.5 (h / (L + h))^2) / h^3``
    gives ``natFreq`` with the mass ``(L + 4h/3) * massPerUnitLen``: the seed
    ``solvePoly`` call plus the VBA's 11 refinement passes of the end-fixity factor.

    Parameters
    ----------
    physical_length : float
        Length between elbows, m.
    flexural_rigidity_ei : float
        Flexural rigidity ``E * I``, N·m².
    mass_per_unit_len : float
        Mass per unit length (pipe and contents), kg/m.
    nat_freq : float
        Natural frequency with the gaps open, Hz.

    Returns
    -------
    float
        ``portalFrameHeight``, m.
    """
    omega2 = (2 * VBA_PI * nat_freq) ** 2
    var_b = physical_length * mass_per_unit_len
    var_c = mass_per_unit_len * 4 / 3
    h = solve_poly(-12 * flexural_rigidity_ei / omega2, var_b, var_c)
    for _i in range(0, 10 + 1):
        h = solve_poly(
            -12 * flexural_rigidity_ei * (0.5 + 1.5 * ((h / (physical_length + h)) ** 2)) / omega2,
            var_b,
            var_c,
        )
    return h


# VBA lines 389-392
def lumped_params(
    physical_length: float,
    portal_frame_height: float,
    mass_per_unit_len: float,
    damping_percent: float,
    dynamic_fric: float,
    nat_freq: float,
    dt: float,
    gap: float,
    restrain_freq_ratio: float,
) -> SdofParams:
    """Mass, stiffness, damping and friction increment of the lumped proxy (VBA 389-392).

    Parameters
    ----------
    physical_length : float
        Length between elbows, m.
    portal_frame_height : float
        From ``solve_portal_height``, m.
    mass_per_unit_len : float
        Mass per unit length, kg/m.
    damping_percent : float
        Damping as a percentage of critical, %.
    dynamic_fric : float
        Coulomb friction coefficient, dimensionless (the VBA fixes m and s here).
    nat_freq : float
        Natural frequency with the gaps open, Hz.
    dt : float
        Sub-step, s (``1 / (sampleFreq * stepQTY)``).
    gap : float
        Support gap, m.
    restrain_freq_ratio : float
        Natural frequency with the gaps closed over that with them open, dimensionless.

    Returns
    -------
    SdofParams
        ``mass = (L + 4h/3) m'`` (kg), ``stiffness = (2 pi f)^2 mass`` (N/m),
        ``damping = 2 sqrt(k m) zeta / 100`` (N·s/m), ``fric_acc = 0.5 mu 9.81 dt``
        (m/s), ``gap`` (m), ``restrain_freq_ratio^2``.

    Notes
    -----
    ``jc_params`` is the ``GetPeakResponseJC`` variant (core fluid removed from the
    mass); the two are kept as separate functions, not a flag.
    """
    mass = (physical_length + portal_frame_height * 4 / 3) * mass_per_unit_len
    stiffness = ((nat_freq * 2 * VBA_PI) ** 2) * mass
    damping = 2 * ((stiffness * mass) ** 0.5) * damping_percent / 100
    fric_acc = 0.5 * dynamic_fric * 9.81 * dt
    return SdofParams(
        float(mass),
        float(stiffness),
        float(damping),
        float(fric_acc),
        float(gap),
        float(restrain_freq_ratio) ** 2,
    )


# VBA lines 726-729 (GetPeakResponseJC)
def jc_params(
    physical_length: float,
    portal_frame_height: float,
    mass_per_unit_len: float,
    fluid_densty: float,
    fluid_area: float,
    damping_percent: float,
    dynamic_fric: float,
    nat_freq: float,
    dt: float,
    gap: float,
    restrain_freq_ratio: float,
) -> SdofParams:
    """Mass, stiffness, damping and friction increment of the junction-coupling proxy
    (VBA lines 726-729).

    The core fluid is removed from the mass (rigid mass only) while stiffness, critical
    damping and the friction increment are scaled on the total mass, as the VBA does.

    Parameters
    ----------
    physical_length : float
        Length between elbows, m.
    portal_frame_height : float
        From ``solve_portal_height``, m.
    mass_per_unit_len : float
        Mass per unit length of pipe *and* fluid, kg/m.
    fluid_densty : float
        Fluid density, kg/m³ (VBA spelling kept).
    fluid_area : float
        Internal cross-sectional (pressure) area of the pipe, m².
    damping_percent : float
        Damping as a percentage of critical, %.
    dynamic_fric : float
        Coulomb friction coefficient, dimensionless (m and s fixed by the VBA).
    nat_freq : float
        Natural frequency with the gaps open, Hz (modelled with the fluid mass included).
    dt : float
        Sub-step, s.
    gap : float
        Support gap, m.
    restrain_freq_ratio : float
        Natural frequency with the gaps closed over that with them open, dimensionless.

    Returns
    -------
    SdofParams
        ``mass`` kg (rigid), ``stiffness`` N/m and ``damping`` N·s/m on the total mass,
        ``fric_acc`` m/s corrected by ``total mass / rigid mass``, ``gap`` m, ``ratio2``.

    Notes
    -----
    The expressions keep the VBA's left-to-right association, which differs from
    ``lumped_params`` (there ``stiffness = w2 * mass``; here ``w2 * (L + h * 4 / 3) * m'``).
    """
    mass = (portal_frame_height * 4 / 3) * mass_per_unit_len + physical_length * (
        mass_per_unit_len - fluid_densty * fluid_area
    )  # remove core fluid to get rigid mass
    stiffness = (
        ((nat_freq * 2 * VBA_PI) ** 2)
        * (physical_length + portal_frame_height * 4 / 3)
        * mass_per_unit_len
    )  # assume total mass has same bases as natural frequency (fluid is included in CAESAR)
    damping = (
        2
        * (
            (stiffness * ((physical_length + portal_frame_height * 4 / 3) * mass_per_unit_len))
            ** 0.5
        )
        * damping_percent
        / 100
    )  # assume critical damping is relative to total mass
    fric_acc = (
        0.5
        * dynamic_fric
        * 9.81
        * dt
        * ((physical_length + portal_frame_height * 4 / 3) * mass_per_unit_len)
        / mass
    )  # mass correction from frictional to inertial
    return SdofParams(
        float(mass),
        float(stiffness),
        float(damping),
        float(fric_acc),
        float(gap),
        float(restrain_freq_ratio) ** 2,
    )


# VBA line 424 (restoring term) and 611 (static-equivalent force)
def effective_displacement(x: float, gap: float, ratio2: float) -> float:
    """Displacement seen by the open-gap stiffness (VBA line 424 and 611).

    ``minUnsigned(gap, x) + max(0, |x| - gap) * sign(x) * ratio2``: ``x`` up to the
    support gap, then ``gap + (|x| - gap) * ratio2`` with the sign of ``x`` beyond it.

    Parameters
    ----------
    x : float
        Displacement, m.
    gap : float
        Support gap, m.
    ratio2 : float
        ``restrainFreqRatio ^ 2``, dimensionless.

    Returns
    -------
    float
        Effective displacement, m; ``restoring_force`` multiplies it by the stiffness.

    Notes
    -----
    The VBA helpers' ladders (``max`` lines 11-17, ``minUnsigned`` 19-33, ``sign``
    51-59) are written out branch for branch, including the ``gap = 0`` and ``x = 0``
    cases; ``step`` inlines the same code.
    """
    ax = abs(x)
    # minUnsigned(gap, x)
    if abs(gap) < ax:
        clamp = gap if x > 0 else -gap  # gap * sign(x); x != 0 here
    elif gap == 0:
        clamp = x
    else:
        clamp = x if gap > 0 else -x  # x * sign(gap)
    # max(0, Abs(x) - gap) * sign(x)
    excess = ax - gap
    if excess < 0:
        excess = 0.0
    if x > 0:
        beyond = excess
    elif x < 0:
        beyond = -excess
    else:
        beyond = excess * 0.0
    return clamp + beyond * ratio2


def restoring_force(x: float, k: float, gap: float, ratio: float) -> float:
    """Bilinear restraint force: stiffness ``k`` up to the support gap, ``k * ratio^2`` beyond.

    ``(minUnsigned(gap, x) + max(0, |x| - gap) * sign(x) * ratio^2) * k``.

    Parameters
    ----------
    x : float
        Displacement, m.
    k : float
        Stiffness with the gaps open, N/m.
    gap : float
        Support gap, m.
    ratio : float
        ``restrainFreqRatio`` (the square is taken here), dimensionless.

    Returns
    -------
    float
        Restoring force, N.
    """
    return effective_displacement(float(x), float(gap), float(ratio) ** 2) * float(k)


def step(state: State, f_applied: float, params: SdofParams, dt: float) -> State:
    """One VBA sub-step (lines 424-432) of the SDOF proxy.

    Explicit ``aNew`` from the old ``x`` and ``v``, trapezoidal ``v`` and ``x``, and
    stick (``|v| < fricAcc``) / slip Coulomb friction.

    Parameters
    ----------
    state : State
        ``(x, v, a)`` at the end of the previous sub-step: m, m/s, m/s².
    f_applied : float
        Everything the caller adds to the restoring and damping terms, N: ``forceA -
        forceB`` plus the coupling force ``dF``, or ``dF`` alone in free decay.
    params : SdofParams
        From ``lumped_params`` or ``jc_params``.
    dt : float
        Sub-step, s.

    Returns
    -------
    State
        ``(x, v, a)`` at the end of this sub-step: m, m/s, m/s².

    Notes
    -----
    * The scheme is explicit in the acceleration (not average-acceleration Newmark):
      with zero damping the amplitude grows about 2.5 % per cycle at ``omega dt`` of
      0.016 (NOTES.md "Findings worth knowing").
    * VBA quirk D-20 preserved: the slip branch uses ``sign(v, 0.000001)``, so for
      ``fricAcc <= |v| < 1e-6`` no friction is applied in that sub-step.
    * ``(a + aNew) * dt / 2`` is computed as ``(a + aNew) * half_dt``; scaling by a
      power of two commutes with rounding, so the doubles are identical to the VBA's.
    """
    x, v, a = state
    mass, stiffness, damping, fric_acc, gap, ratio2 = params
    half_dt = dt / 2

    # aNew = (F - (minUnsigned(gap, x) + max(0, Abs(x) - gap) * sign(x) * ratio^2)
    #             * stiffness - v * damping) / mass
    ax = abs(x)
    if abs(gap) < ax:
        clamp = gap if x > 0 else -gap
    elif gap == 0:
        clamp = x
    else:
        clamp = x if gap > 0 else -x
    excess = ax - gap
    if excess < 0:
        excess = 0.0
    if x > 0:
        beyond = excess
    elif x < 0:
        beyond = -excess
    else:
        beyond = excess * 0.0
    a_new = (f_applied - (clamp + beyond * ratio2) * stiffness - v * damping) / mass

    av = (a + a_new) * half_dt
    if abs(v) < fric_acc:
        v_new = av
    else:
        # vNew = v + (a + aNew) * dt / 2 - sign(v, 0.000001) * fricAcc
        v_new = v + av
        if v > 0.000001:
            v_new = v_new - fric_acc
        elif v < -0.000001:
            v_new = v_new + fric_acc
    x = x + (v + v_new) * half_dt
    return (x, v_new, a_new)
