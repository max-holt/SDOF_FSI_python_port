"""Stage 1 literal port of ``legacy/vba/Existing Code.bas``.

Every VBA ``Function`` appears here in the same order and under the same name
(snake_case). The body of each function is a line-for-line transcription of the VBA:
operation order, loop order, loop bounds and index values are kept as written, and
nothing is vectorised, merged or simplified. Readability is not a goal in this stage;
numerical equivalence with the VBA is. Helpers that emulate VBA runtime semantics
(``CLng``, the ``CLng(x - 0.5)`` floor idiom, ``modDbl``, ``sign``, ``minUnsigned``,
``maxUnsigned``) live in ``vba_compat.py`` and are imported into their VBA slot below.

Array conventions
-----------------
* A VBA array declared ``(0 To n)`` is a numpy array of length ``n + 1`` indexed
  exactly as the VBA does: ``arrayA(0 To 1, 0 To pipeSegQTY)`` becomes
  ``np.zeros((2, pipe_seg_qty + 1))`` and ``arrayA(1, i)`` becomes ``array_a[1, i]``.
* A VBA array declared ``(1 To n)`` is a numpy array of length ``n + 1`` whose index 0
  is unused (left at 0.0). VBA index values are used unchanged in the loops.
  ``resultArray(1 To outMax * 2)`` therefore becomes ``np.zeros(out_max * 2 + 1)`` and
  is returned as such: callers must ignore element 0.
* The 2-D inputs ``valvePattern`` and ``forceHistory`` arrive as 2-D numpy arrays whose
  ``[i, j]`` has VBA's 1-based meaning (``arr[0, 0]`` is VBA ``(1, 1)``). They are passed
  through ``vba_compat.vba_2d`` which pads a leading unused row and column, so the body
  indexes ``force_history[i, j]`` exactly as the VBA. ``ubound(arr, dim)`` returns the VBA
  ``UBound`` of such a padded array. A 1-D input is accepted and takes the VBA
  ``AddDimension`` path. 2-D ``forceHistory``/``valvePattern`` are walked column-major
  (first index fastest), as in the VBA.
* Arrays with negative lower bounds (``contA0``, ``contAN`` in ``GetPeakResponseJC``)
  are stored with an offset that is documented at the declaration.

Loop conventions
----------------
* ``For v = a To b`` becomes ``for v in range(a, b + 1)``; the bound is evaluated once,
  as in VBA. ``Exit For`` becomes ``break``.
* Where the VBA reads a loop variable *after* its loop (``jB``, ``iB`` in the two peak
  functions) the loop is written as a ``while`` with an explicit increment, so that the
  variable holds VBA's post-loop value (``b + 1`` after normal completion, the current
  value after ``Exit For``).

Operators and types
-------------------
* VBA ``/`` is floating-point division; it is written ``/``. ``^`` becomes ``**``.
  ``Abs`` becomes ``abs``. Constants (e.g. ``pi``) use the VBA literals, not ``math.pi``.
* ``Dim`` initialises numerics to 0; every such variable is initialised explicitly here.
* Where VBA assigns a Double expression to a Long variable the implicit ``CLng`` is made
  explicit with ``clng``.
* VBA raises a runtime error on division by zero and on floating overflow. Python floats
  raise on division by zero but produce ``inf`` on overflow, and numpy scalars do neither
  by default. The three entry points therefore run under
  ``np.errstate(divide="raise", invalid="raise", over="raise")`` so that numpy arithmetic
  raises ``FloatingPointError`` where the VBA would have raised. Pure-Python float
  overflow is not emulated.
* Integer/Long overflow (VBA error 6) is not emulated.
* ``On Error GoTo ErrFound`` in ``GetPeakResponseJC`` is translated as a ``try`` that
  re-raises (see DEVIATIONS.md D-9): the VBA returned an uninitialised array instead.

Quirks that are preserved on purpose are marked ``# VBA quirk D-n preserved`` and
listed in DEVIATIONS.md.
"""

import numpy as np

from surge_sdof.vba_compat import (
    clng,
    max_unsigned,
    min_unsigned,
    mod_dbl,
    sign,
    ubound,
    vba_2d,
    vba_floor,
)

__all__ = [
    "min",
    "max",
    "min_unsigned",
    "max_unsigned",
    "sign",
    "get_dimension",
    "add_dimension",
    "array_start_one",
    "vba_floor",
    "mod_dbl",
    "interp_fraction_a",
    "interp_fraction_b",
    "solve_poly",
    "get_pressure_response",
    "get_peak_response",
]


# ---------------------------------------------------------------------------
# VBA line 3: Function min(valueA As Variant, valueB As Variant) As Variant
#
# NOTE: this and ``max`` intentionally shadow the Python built-ins inside this module.
# They carry the VBA tie semantics (a tie returns valueB) so that every ``min(``/``max(``
# in the solver bodies reads exactly as the VBA line.
# ---------------------------------------------------------------------------
def min(value_a, value_b):
    """VBA ``min``: ``valueA`` if ``valueA < valueB`` else ``valueB``."""
    if value_a < value_b:
        return value_a
    else:
        return value_b


# VBA line 11: Function max(valueA As Variant, valueB As Variant) As Variant
def max(value_a, value_b):
    """VBA ``max``: ``valueA`` if ``valueA > valueB`` else ``valueB``."""
    if value_a > value_b:
        return value_a
    else:
        return value_b


# VBA line 19: Function minUnsigned  -> vba_compat.min_unsigned
# VBA line 35: Function maxUnsigned  -> vba_compat.max_unsigned
# VBA line 51: Function sign         -> vba_compat.sign


# VBA line 61: Function getDimension(var As Variant) As Long
def get_dimension(var):
    """VBA ``getDimension``: number of dimensions of ``var``.

    The VBA probes ``UBound(var, i)`` for increasing ``i`` until it errors and returns
    ``i - 1``. numpy exposes the same quantity directly.
    """
    return np.ndim(var)


# VBA line 74: Function AddDimension(arr As Variant, newLBound As Long, newUBound As Long) As Double()
def add_dimension(arr, new_lbound, new_ubound):
    """VBA ``AddDimension``: turn a 1-D array into a 2-D ``(1 To n, newLBound To newUBound)``.

    The input is a 1-D numpy array, i.e. ``LBound = 0`` and ``UBound = len - 1``. The
    result follows the padded 1-based convention (row 0 and column 0 unused), so
    ``new_lbound`` must be >= 0 (the VBA only ever calls this with ``(1, 1)``).
    """
    arr = np.asarray(arr, dtype=float)
    lbound_arr = 0
    ubound_arr = arr.shape[0] - 1
    # VBA: ReDim arrOut(1 To UBound(arr) + LBound(arr) + 1, newLBound To newUBound)
    # The row count UBound + LBound + 1 is only the element count when LBound = 0.
    # VBA quirk D-5 preserved
    arr_out = np.zeros((ubound_arr + lbound_arr + 1 + 1, new_ubound + 1))
    for i in range(lbound_arr, ubound_arr + 1):
        arr_out[i - lbound_arr + 1, new_lbound] = arr[i]
    return arr_out


# VBA line 84: Function ArrayStartOne(arr As Variant) As Double()
def array_start_one(arr):
    """VBA ``ArrayStartOne``: re-base a 2-D array to ``(1 To n1, 1 To n2)``.

    The VBA builds ``arrOut`` and then assigns it to ``AddDimension`` instead of to
    ``ArrayStartOne``, so the function's own return value is never set and an empty
    ``Double()`` array is returned. Reproduced: the loop runs, the result is discarded,
    and an empty array is returned. Unreachable from the Python entry points, whose 2-D
    inputs are always re-based by ``vba_2d``.
    """
    arr = np.asarray(arr, dtype=float)
    lbound_1 = 0
    ubound_1 = arr.shape[0] - 1
    lbound_2 = 0
    ubound_2 = arr.shape[1] - 1
    # VBA: ReDim arrOut(1 To UBound(arr,1)+LBound(arr,1)+1, 1 To UBound(arr,2)+LBound(arr,2)+1)
    arr_out = np.zeros((ubound_1 + lbound_1 + 1 + 1, ubound_2 + lbound_2 + 1 + 1))
    for i in range(lbound_1, ubound_1 + 1):
        for j in range(lbound_2, ubound_2 + 1):
            arr_out[i - lbound_1 + 1, j - lbound_2 + 1] = arr[i, j]
    # VBA: AddDimension = arrOut   (wrong name; ArrayStartOne itself is never assigned)
    # VBA quirk D-3 preserved
    del arr_out
    return np.zeros((0, 0))


# VBA line 97:  Function floor(val As Variant) As Long   -> vba_compat.vba_floor
# VBA line 101: Function modDbl(num As Variant, div As Variant) As Double -> vba_compat.mod_dbl


# VBA line 105: Function interpFractionA(n As Long, pivotSegQTY As Long, pipeSegQTY As Long) As Double
def interp_fraction_a(n, pivot_seg_qty, pipe_seg_qty):
    """VBA ``interpFractionA``: cell-centred weighting of the mass acceleration along the pipe.

    ``For n = 0 To pipeSegQTY - 1``. ``extQTY = 4`` cells at each end are not active.
    """
    ext_qty = 4  # QTY at each end are not active
    if n < ext_qty:
        return 0.0
    elif n < pivot_seg_qty:
        return ((n - 0.5 - ext_qty) / (pivot_seg_qty - ext_qty)) ** 2
    elif n > pipe_seg_qty - ext_qty:
        return 0.0
    elif n > pipe_seg_qty - pivot_seg_qty:
        return ((pipe_seg_qty - 0.5 - ext_qty - n) / (pivot_seg_qty - ext_qty)) ** 2
    else:
        return 1.0


# VBA line 121: Function interpFractionB(n As Long, pivotSegQTY As Long, pipeSegQTY As Long) As Double
def interp_fraction_b(n, pivot_seg_qty, pipe_seg_qty):
    """VBA ``interpFractionB``: node-centred weighting of the mass acceleration along the pipe.

    ``For n = 0 To pipeSegQTY - 1``. ``extQTY = 4`` cells at each end are not active,
    but the first test uses the literal ``3`` rather than ``extQTY``.
    """
    ext_qty = 4  # QTY at each end are not active
    if n < 3:  # VBA quirk D-4 preserved (interpFractionA uses n < extQTY)
        return 0.0
    elif n < pivot_seg_qty:
        return ((n - ext_qty) / (pivot_seg_qty - ext_qty)) ** 2
    elif n > pipe_seg_qty - ext_qty:
        return 0.0
    elif n > pipe_seg_qty - pivot_seg_qty:
        return ((pipe_seg_qty - 1 - ext_qty - n) / (pivot_seg_qty - ext_qty)) ** 2
    else:
        return 1.0


# VBA line 137: Function solvePoly(varA As Double, varB As Double, varC As Double) As Double
def solve_poly(var_a, var_b, var_c):
    """VBA ``solvePoly``: relaxed Newton solve of ``varA + varB*L^3 + varC*L^4 = 0`` for ``L``.

    Starts from ``(-varA / varB) ^ (1 / 3)``, relaxation 0.25, at most 100 iterations,
    stops when ``|error / varA| < 1e-6``.
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


# VBA line 155: Function GetPressureResponse(valvePattern As Variant, closureTime As Double, celerity As Double, density As Double, timeStep As Double, pressureDropFromPump As Double, flowRate As Double, pipeArea As Double, valveCv As Double, lengthToPump As Double, pumpRampPressure As Double) As Double()
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
    """Returns the pressure response at valve.

    Parameters
    ----------
    valve_pattern : array_like
        (No VBA comment.) Valve closure history, 0 = open to 1 = closed, spread evenly
        over ``closure_time``. A 2-D array is walked column-major (first index fastest);
        a 1-D array is treated as a single column.
    closure_time : float
        valve closure time (sec)
    celerity : float
        fluid/pipe effective pressure wave speed (m/sec)
    density : float
        fluid density (kg/m3)
    time_step : float
        simulation time step (sec)
    pressure_drop_from_pump : float
        total pressure drop from pump to valve (bar) @ flowRate
    flow_rate : float
        simulation initial flowrate (m3/h)
    pipe_area : float
        pipe flowing cress-sectional area (mm^2)
    valve_cv : float
        (flowRate in US gallons per minute)*(SG/pressure drop over valve in psi)^0.5
    length_to_pump : float
        length of pipe to the pump (m)
    pump_ramp_pressure : float
        difference in pressure between operating and shut-in (bar)

    Returns
    -------
    numpy.ndarray
        ``resultArray(0 To outMax)``, 0-based: valve pressure (Pa, gauge relative to the
        pump shut-in datum used by the VBA) at every ``2 * time_step``
        (``outMax = CLng(closure_time / time_step)``).
    """
    with np.errstate(divide="raise", invalid="raise", over="raise"):
        # VBA 196-204: Range -> .Value; 1-D -> AddDimension(…, 1, 1); otherwise the array
        # is re-based to (1, 1). For numpy input the last case is served by vba_2d (the
        # VBA ArrayStartOne path, D-3, is never taken).
        if get_dimension(valve_pattern) < 2:
            valve_pattern = add_dimension(valve_pattern, 1, 1)
        else:
            valve_pattern = vba_2d(valve_pattern)

        out_max = clng(closure_time / time_step)
        pipe_seg_qty = 1 + clng(min(out_max, length_to_pump / (celerity * time_step)) / 2)

        result_array = np.zeros(out_max + 1)  # ReDim resultArray(0 To outMax)
        array_a = np.zeros((2, pipe_seg_qty + 1))  # ReDim arrayA(0 To 1, 0 To pipeSegQTY)
        array_b = np.zeros((2, pipe_seg_qty + 1))  # ReDim arrayB(0 To 1, 0 To pipeSegQTY)
        sys_mat = np.zeros(2)  # Dim sysMat(0 To 1)

        factor = ubound(valve_pattern, 1) * ubound(valve_pattern, 2) * time_step / closure_time

        rho_c = density * celerity

        velocity_initial = -flow_rate * 1000000 / (pipe_area * 60 * 60)  # m/s
        valve_loss = (
            (density / 1000)
            * 100000
            / (((valve_cv * 0.865 * 1000000) / (pipe_area * 60 * 60)) ** 2)
        )  # Pa/(m/s)^2
        valve_dp_initial = valve_loss * (velocity_initial**2)  # Pa
        pipe_loss = pressure_drop_from_pump * 100000 / (1 + pipe_seg_qty * 2)  # Pa/segment

        for i in range(0, pipe_seg_qty + 1):
            array_a[0, i] = i * 2 * pipe_loss + valve_dp_initial
            array_b[0, i] = (1 + i * 2) * pipe_loss + valve_dp_initial
            array_a[1, i] = -i * 2 * pipe_loss / rho_c + velocity_initial
            array_b[1, i] = -(1 + i * 2) * pipe_loss / rho_c + velocity_initial

        vel_at_pump = array_b[1, pipe_seg_qty]

        # 'pipeLoss = pipeLoss / (velocityInitial ^ 2) 'Pa/(m/s)^2
        #
        # 'self.mocMat = self.invertMatrix([[-1.0,-1.0/self.rhoC],
        # '                                 [-1.0,+1.0/self.rhoC]])
        #
        # 'self.mocMat = [[-0.5,-0.5],
        # '               [-self.rhoC/2,+self.rhoC/2]]
        #
        # '        mat = [[loss-vL-pL/self.rhoC],
        # '               [loss-vR+pR/self.rhoC]]

        for tot_ind in range(0, out_max + 1):
            # every loop is 2 time steps
            # VBA assigns a Double (modDbl + 1) to the Long i: implicit CLng.
            # modDbl carries D-2: an exact odd multiple of UBound gives i = UBound + 1,
            # which the clamp below folds back to UBound.
            i = clng(mod_dbl(vba_floor(tot_ind * factor * 2), ubound(valve_pattern, 1)) + 1)
            j = vba_floor(tot_ind * factor * 2 / ubound(valve_pattern, 1)) + 1
            if i >= ubound(valve_pattern, 1) and j < ubound(valve_pattern, 2):
                i = ubound(valve_pattern, 1)
                jmax = min(j + 1, ubound(valve_pattern, 2))
                imax = 1
            else:
                if i > ubound(valve_pattern, 1):
                    i = ubound(valve_pattern, 1)
                jmax = j
                imax = min(i + 1, ubound(valve_pattern, 1))
            # get valve position
            if j > ubound(valve_pattern, 2):
                closure = valve_pattern[ubound(valve_pattern, 1), ubound(valve_pattern, 2)]
            elif i == imax and j == jmax:
                closure = valve_pattern[i, j]
            else:
                frac = ((i - 1) + (j - 1) * ubound(valve_pattern, 1) - tot_ind * factor * 2) / (
                    (i - 1)
                    + (j - 1) * ubound(valve_pattern, 1)
                    - ((imax - 1) + (jmax - 1) * ubound(valve_pattern, 1))
                )
                closure = valve_pattern[i, j] * (1 - frac) + valve_pattern[imax, jmax] * frac
            # valve pressure is determined by the velocity
            if closure < 0.999999999:
                array_a[1, 0] = (array_a[1, 0] + array_b[1, 0]) / 2 + (
                    array_a[0, 0] - array_b[0, 0]
                ) / (2 * rho_c)
                array_a[0, 0] = min(
                    ((valve_loss / (1 - closure)) * (array_a[1, 0] ** 2)),
                    max(
                        array_b[0, 0],
                        (array_a[0, 0] + array_b[0, 0]) / 2 - array_a[1, 0] * rho_c,
                    ),
                )
            else:
                array_a[1, 0] = 0
                array_a[0, 0] = max(array_b[0, 0], array_b[0, 0] - array_b[1, 0] * rho_c)
            # MoC
            for i in range(1, min(pipe_seg_qty, tot_ind) + 1):
                v = (array_b[1, i - 1] + array_b[1, i]) / 2
                vel_init_local = i * 2 * pipe_loss / rho_c + velocity_initial
                # VBA quirk D-6 preserved: clamp is 0.9 here, 0.9 * rhoC in the second half-loop
                loss = v * min(0.9, abs(v) * pipe_loss / (rho_c * (vel_init_local**2)))

                sys_mat[0] = -loss - array_b[1, i - 1] - array_b[0, i - 1] / rho_c
                sys_mat[1] = loss - array_b[1, i] + array_b[0, i] / rho_c

                array_a[1, i] = -(sys_mat[0] + sys_mat[1]) / 2
                array_a[0, i] = max(0, -(sys_mat[0] - sys_mat[1]) * rho_c / 2)
            # pump pressure is determined by the velocity
            array_b[0, pipe_seg_qty] = max(
                0,
                valve_dp_initial
                + 100000
                * (
                    pressure_drop_from_pump
                    + pump_ramp_pressure
                    * (1 - (min(0, array_a[1, pipe_seg_qty]) / vel_at_pump) ** 2)
                ),
            )
            array_b[1, pipe_seg_qty] = min(0, array_a[1, pipe_seg_qty])
            # MoC
            for i in range(0, min(pipe_seg_qty - 1, tot_ind) + 1):
                v = (array_a[1, i] + array_a[1, i + 1]) / 2
                vel_init_local = (1 + i * 2) * pipe_loss / rho_c + velocity_initial
                # VBA quirk D-6 preserved: clamp is 0.9 * rhoC here, 0.9 in the first half-loop
                loss = v * min(0.9 * rho_c, abs(v) * pipe_loss / (rho_c * (vel_init_local**2)))

                sys_mat[0] = -loss - array_a[1, i] - array_a[0, i] / rho_c
                sys_mat[1] = loss - array_a[1, i + 1] + array_a[0, i + 1] / rho_c

                array_b[1, i] = -(sys_mat[0] + sys_mat[1]) / 2
                array_b[0, i] = max(0, -(sys_mat[0] - sys_mat[1]) * rho_c / 2)

            result_array[tot_ind] = array_a[0, 0]

        return result_array


# VBA line 309: Function GetPeakResponse(forceHistory As Variant, stepQTY As Integer, sampleFreq As Double, physicalLength As Double, flexuralRigidityEI As Double, celerity As Double, massPerUnitLen As Double, dampingPercent As Double, dynamicFric As Double, natFreq As Double, Optional restrainFreqRatio As Double = 1, Optional gap As Double = 0, Optional outputType As Integer = 0) As Double()
def get_peak_response(
    force_history,
    step_qty,
    sample_freq,
    physical_length,
    flexural_rigidity_ei,
    celerity,
    mass_per_unit_len,
    damping_percent,
    dynamic_fric,
    nat_freq,
    restrain_freq_ratio=1,
    gap=0,
    output_type=0,
):
    """Returns the peak displacement response (consistent unites except dynamicFric).

    Parameters
    ----------
    force_history : array_like
        force-time history at one location. A 2-D array is walked column-major (first
        index fastest); a 1-D array is treated as a single column.
    step_qty : int
        simulation frequency (steps per sample)
    sample_freq : float
        frequency of time values for data in forceHistory
    physical_length : float
        length between elbows
    flexural_rigidity_ei : float
        E * I
    celerity : float
        effective progression speed of force History
    mass_per_unit_len : float
        mass / physicalLength
    damping_percent : float
        percent critical damping
    dynamic_fric : float
        friction acting on mass to resist movement (assumes units are m,sec)
    nat_freq : float
        sqrt(k/m)
    restrain_freq_ratio : float, optional
        ratio of natural frequency when support gaps are closed to when support gaps are
        open (default 1)
    gap : float, optional
        support gaps (measured effective gap at center of mass or equivalently mode
        maximum displacement) (default 0)
    output_type : int, optional
        (No VBA comment.) 0: peak summary; 1: displacement history; 2: velocity history;
        3: acceleration history (default 0).

    Returns
    -------
    numpy.ndarray
        For ``output_type == 0`` the 0-based ``resultArray(0 To 4)``:
        ``[max static equivalent force, max displacement, max velocity,
        max acceleration, max applied force]``.
        Otherwise the 1-based ``resultArray(1 To outMax * 2)`` returned as an array of
        length ``outMax * 2 + 1`` whose element 0 is unused; element ``totInd`` holds the
        state at the end of sample ``totInd`` (unfilled trailing elements stay 0).
    """
    pi = 3.14159265358979

    with np.errstate(divide="raise", invalid="raise", over="raise"):
        # VBA 365-373: Range -> .Value; 1-D -> AddDimension(…, 1, 1); otherwise the array
        # is re-based to (1, 1). For numpy input the last case is served by vba_2d (the
        # VBA ArrayStartOne path, D-3, is never taken).
        if get_dimension(force_history) < 2:
            force_history = add_dimension(force_history, 1, 1)
        else:
            force_history = vba_2d(force_history)

        unballance_step_qty = physical_length / (celerity / sample_freq)

        out_max = ubound(force_history, 1) * ubound(force_history, 2) + clng(unballance_step_qty)
        result_array = np.zeros(out_max * 2 + 1)  # ReDim resultArray(1 To outMax * 2); [0] unused

        k_overlap = clng((unballance_step_qty - vba_floor(unballance_step_qty)) * step_qty)

        dt = 1 / (sample_freq * step_qty)

        portal_frame_height = solve_poly(
            -12 * flexural_rigidity_ei / ((2 * pi * nat_freq) ** 2),
            physical_length * mass_per_unit_len,
            mass_per_unit_len * 4 / 3,
        )
        for _i in range(0, 10 + 1):
            portal_frame_height = solve_poly(
                -12
                * flexural_rigidity_ei
                * (
                    0.5
                    + 1.5 * ((portal_frame_height / (physical_length + portal_frame_height)) ** 2)
                )
                / ((2 * pi * nat_freq) ** 2),
                physical_length * mass_per_unit_len,
                mass_per_unit_len * 4 / 3,
            )

        mass = (physical_length + portal_frame_height * 4 / 3) * mass_per_unit_len
        stiffness = ((nat_freq * 2 * pi) ** 2) * mass
        damping = 2 * ((stiffness * mass) ** 0.5) * damping_percent / 100
        fric_acc = 0.5 * dynamic_fric * 9.81 * dt

        x = 0.0
        x_max = 0.0
        v = 0.0
        v_max = 0.0
        a = 0.0
        a_max = 0.0
        f_max = 0.0  # Dim FMax As Double: never explicitly initialised in the VBA
        x_zero = 0.0  # Dim default
        v_new = 0.0  # Dim default
        a_new = 0.0  # Dim default

        force_a = force_history[1, 1]

        tot_ind = 0
        # VBA: For jB = 1 To 1 + CLng(unballanceStepQTY / UBound(forceHistory, 2))
        #          For iB = 1 To UBound(forceHistory, 1)
        # Written as while loops: jB and iB are read after the loops (VBA 468-471, 483+)
        # and must hold VBA's post-loop values (bound + 1 after normal completion, the
        # current value after Exit For).
        jb_to = 1 + clng(unballance_step_qty / ubound(force_history, 2))
        jb = 1
        while jb <= jb_to:
            ib_to = ubound(force_history, 1)
            ib = 1
            while ib <= ib_to:
                tot_ind = tot_ind + 1
                if jb > ubound(force_history, 2):
                    j = ubound(force_history, 2)
                    i = ubound(force_history, 1)
                else:
                    j = jb
                    i = ib
                if i + 1 > ubound(force_history, 1) and j < ubound(force_history, 2):
                    jmax = min(j + 1, ubound(force_history, 2))
                    imax = 1
                else:
                    jmax = min(j, ubound(force_history, 2))
                    imax = min(i + 1, ubound(force_history, 1))
                for k in range(0, step_qty - 1 + 1):
                    # VBA quirk D-7 preserved: stepQTY = 1 divides by zero here
                    force_b = force_history[i, j] * (1 - k / (step_qty - 1)) + force_history[
                        imax, jmax
                    ] * (k / (step_qty - 1))

                    a_new = (
                        (force_a - force_b)
                        - (
                            min_unsigned(gap, x)
                            + max(0, abs(x) - gap) * sign(x) * (restrain_freq_ratio**2)
                        )
                        * stiffness
                        - v * damping
                    ) / mass
                    if abs(v) < fric_acc:
                        v_new = (a + a_new) * dt / 2
                    else:
                        v_new = v + (a + a_new) * dt / 2 - sign(v, 0.000001) * fric_acc
                    x = x + (v + v_new) * dt / 2
                    v = v_new
                    a = a_new

                    if abs(a) > a_max:
                        a_max = abs(a)
                    if abs(v) > v_max:
                        v_max = abs(v)
                    if abs(x) > x_max:
                        x_max = abs(x)
                    if abs(force_a - force_b) > f_max:
                        f_max = abs(force_a - force_b)
                    if (tot_ind - 1) * step_qty + 1 + k > unballance_step_qty * step_qty:
                        break
                if output_type > 0:
                    if output_type == 1:
                        result_array[tot_ind] = x
                    elif output_type == 2:
                        result_array[tot_ind] = v
                    elif output_type == 3:
                        result_array[tot_ind] = a
                if tot_ind > unballance_step_qty:
                    break  # Exit For (iB keeps its current value)
                ib = ib + 1
            if tot_ind > unballance_step_qty:
                break  # Exit For (jB keeps its current value)
            jb = jb + 1

        # VBA quirk D-8 preserved: if the loops above complete without Exit For and
        # jB <= UBound(2) (possible for a single-row forceHistory), iB is UBound(1) + 1
        # and the first forceHistory(iB, jB) below is out of range (VBA error 9,
        # Python IndexError).
        if jb > ubound(force_history, 2):
            jb = ubound(force_history, 2)
            ib = ubound(force_history, 1)

        for j in range(1, ubound(force_history, 2) + 1):
            for i in range(1, ubound(force_history, 1) + 1):
                tot_ind = tot_ind + 1
                if i + 1 > ubound(force_history, 1) and j < ubound(force_history, 2):
                    jmax = min(j + 1, ubound(force_history, 2))
                    imax = 1
                else:
                    jmax = j
                    imax = min(i + 1, ubound(force_history, 1))
                if ib + 1 > ubound(force_history, 1) and jb < ubound(force_history, 2):
                    jbmax = min(jb + 1, ubound(force_history, 2))
                    ibmax = 1
                else:
                    jbmax = jb
                    ibmax = min(ib + 1, ubound(force_history, 1))
                for k in range(0, step_qty - k_overlap - 1 + 1):
                    force_a = force_history[i, j] * (1 - k / (step_qty - 1)) + force_history[
                        imax, jmax
                    ] * (k / (step_qty - 1))
                    force_b = force_history[ib, jb] * (
                        1 - (k + k_overlap) / (step_qty - 1)
                    ) + force_history[ibmax, jbmax] * ((k + k_overlap) / (step_qty - 1))

                    a_new = (
                        (force_a - force_b)
                        - (
                            min_unsigned(gap, x)
                            + max(0, abs(x) - gap) * sign(x) * (restrain_freq_ratio**2)
                        )
                        * stiffness
                        - v * damping
                    ) / mass
                    if abs(v) < fric_acc:
                        v_new = (a + a_new) * dt / 2
                    else:
                        v_new = v + (a + a_new) * dt / 2 - sign(v, 0.000001) * fric_acc
                    x = x + (v + v_new) * dt / 2
                    v = v_new
                    a = a_new

                    if abs(a) > a_max:
                        a_max = abs(a)
                    if abs(v) > v_max:
                        v_max = abs(v)
                    if abs(x) > x_max:
                        x_max = abs(x)
                    if abs(force_a - force_b) > f_max:
                        f_max = abs(force_a - force_b)
                if ib + 1 > ubound(force_history, 1) and jb < ubound(force_history, 2):
                    jb = min(jb + 1, ubound(force_history, 2))
                    ib = 1
                else:
                    ib = min(ib + 1, ubound(force_history, 1))
                if ib + 1 > ubound(force_history, 1) and jb < ubound(force_history, 2):
                    jbmax = min(jb + 1, ubound(force_history, 2))
                    ibmax = 1
                else:
                    jbmax = jb
                    ibmax = min(ib + 1, ubound(force_history, 1))
                for k in range(step_qty - k_overlap, step_qty - 1 + 1):
                    force_a = force_history[i, j] * (1 - k / (step_qty - 1)) + force_history[
                        imax, jmax
                    ] * (k / (step_qty - 1))
                    force_b = force_history[ib, jb] * (
                        1 - (k - step_qty + k_overlap) / (step_qty - 1)
                    ) + force_history[ibmax, jbmax] * ((k - step_qty + k_overlap) / (step_qty - 1))

                    a_new = (
                        (force_a - force_b)
                        - (
                            min_unsigned(gap, x)
                            + max(0, abs(x) - gap) * sign(x) * (restrain_freq_ratio**2)
                        )
                        * stiffness
                        - v * damping
                    ) / mass
                    if abs(v) < fric_acc:
                        v_new = (a + a_new) * dt / 2
                    else:
                        v_new = v + (a + a_new) * dt / 2 - sign(v, 0.000001) * fric_acc
                    x = x + (v + v_new) * dt / 2
                    v = v_new
                    a = a_new

                    if abs(a) > a_max:
                        a_max = abs(a)
                    if abs(v) > v_max:
                        v_max = abs(v)
                    if abs(x) > x_max:
                        x_max = abs(x)
                    if abs(force_a - force_b) > f_max:
                        f_max = abs(force_a - force_b)
                if output_type > 0:
                    if output_type == 1:
                        result_array[tot_ind] = x
                    elif output_type == 2:
                        result_array[tot_ind] = v
                    elif output_type == 3:
                        result_array[tot_ind] = a
        x_zero = x
        while x * x_zero > 0.01:
            tot_ind = tot_ind + 1
            for _k in range(1, step_qty + 1):  # VBA: For k = 1 To stepQTY (k unused)
                a_new = (
                    -(
                        min_unsigned(gap, x)
                        + max(0, abs(x) - gap) * sign(x) * (restrain_freq_ratio**2)
                    )
                    * stiffness
                    - v * damping
                ) / mass
                if abs(v) < fric_acc:
                    v_new = (a + a_new) * dt / 2
                else:
                    v_new = v + (a + a_new) * dt / 2 - sign(v, 0.000001) * fric_acc
                x = x + (v + v_new) * dt / 2
                v = v_new
                a = a_new

                if abs(a) > a_max:
                    a_max = abs(a)
                if abs(v) > v_max:
                    v_max = abs(v)
                if abs(x) > x_max:
                    x_max = abs(x)

                if x * x_zero <= 0.01:
                    x_zero = 0
            if output_type > 0:
                if tot_ind <= out_max * 2:
                    if output_type == 1:
                        result_array[tot_ind] = x
                    elif output_type == 2:
                        result_array[tot_ind] = v
                    elif output_type == 3:
                        result_array[tot_ind] = a

        if output_type == 0:
            result_array = np.zeros(4 + 1)  # ReDim resultArray(0 To 4)
            result_array[0] = (
                abs(
                    min_unsigned(gap, x_max)
                    + max(0, abs(x_max) - gap) * sign(x_max) * (restrain_freq_ratio**2)
                )
                * stiffness
            )  # max static equivalent
            result_array[1] = x_max  # max displacement
            result_array[2] = v_max  # max velocity
            result_array[3] = a_max  # max acceloration
            result_array[4] = f_max  # max applied force

        return result_array
