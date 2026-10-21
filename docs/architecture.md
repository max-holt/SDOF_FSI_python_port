# Architecture — Stage 4 target layout

One line per module: what it is responsible for, and what it must not know about.
The target structure is fixed for the whole of Stage 4; sessions fill it in module by
module (4.1: `structure`, `loads`, `coupling` (`NoCoupling` only), `response` lumped
path; 4.2: `moc`, the JC coupling; 4.3: `pressure`, `_vba_semantics`). `legacy_port.py` stays the reference
implementation until Stage 6 and every new module is proved against it by
`tests/test_differential.py`.

```
src/surge_sdof/
  vba_compat.py        # frozen (Stage 1 VBA runtime semantics; no edits)
  _vba_semantics.py    # live home for VBA tie/NaN comparison semantics (vba_min, vba_max)
  legacy_port.py       # frozen; reference implementation until Stage 6
  moc.py               # 1-D MoC fluid column: state arrays, half-step update, boundary conditions
  structure.py         # SDOF: portal-frame proxy, restoring force with gap, Coulomb friction, time-step kernel
  coupling.py          # coupling force from the moc state (interp fractions, low-pass dF)
  loads.py             # elbow-to-elbow unbalance force from a history: transit delay, phase scheduling
  response.py          # public API: peak_response(...) and peak_response_jc(...); returns a dataclass
  pressure.py          # pressure_response (valve/pump MoC) as a standalone driver; get_pressure_response is a thin alias
```

| module | responsibility | must not know about |
|---|---|---|
| `vba_compat.py` | VBA runtime semantics (`CLng`, `floor`, `modDbl`, `sign`, `min/maxUnsigned`, padded 1-based arrays). **Frozen**: no edits; new modules may import from it, but any VBA semantic it lacks goes into `_vba_semantics.py`. | any solver quantity |
| `_vba_semantics.py` | The live home for VBA comparison semantics: `vba_min`/`vba_max` (the module-level VBA `min`/`max`, lines 3-17: on a tie or with NaN the **second** argument is returned, with its type and sign of zero; Python's built-ins return the first). One copy, used by `pressure.py`, surviving the Stage 6 removal of `legacy_port.py` (whose `min`/`max` are the same functions). | any solver quantity |
| `legacy_port.py` | Line-for-line Stage 1 transcription of the VBA; the oracle for the differential tests. Frozen (no edits, no imports *from* it in new modules except in tests). | the new modules |
| `structure.py` | The SDOF pipe proxy: `solve_portal_height` (seed + 11 `solve_poly` passes), `lumped_params` (mass, stiffness, damping, `fricAcc`), `restoring_force(x, k, gap, ratio)` (bilinear support gap), and `step(state, f_applied, params, dt)` — exactly the VBA update (explicit `aNew` from the old state, trapezoidal `v` and `x`, stick/slip Coulomb friction) on Python floats with the clamp/sign ladders inlined. One function, called from one loop. | where `f_applied` comes from (force histories, transit delay, fluid coupling), sample/phase bookkeeping, max trackers, output types |
| `loads.py` | The elbow-to-elbow unbalance force `forceA − forceB` from a force history: `transit_delay` (`unballanceStepQTY`), the `kOverlap` sub-sample offset and the three-phase scheduling (delay phase with `forceA` held, ramp phase with both forces interpolated, no force in free decay), walked column-major over 2-D histories exactly as the VBA. Yields one list of per-sub-step values per sample. | the structure state, stiffness or damping, fluid coupling, what the caller does with each sample (result histories, free decay) |
| `coupling.py` | The force the fluid column exerts on the structure: `Coupling.coupling_force(state, step_index) -> float`. `NoCoupling` returns `0.0`. `JunctionCoupling` (Stage 4.2) owns the column arrays, the tabulated interp fractions and the low-pass `dF`: each call feeds the state's acceleration (`a * dt`) into the moving cells, advances the column one sub-step with `moc.step` on the half-grid `step_index % 2` selects, and returns the new `dF` as a Python float. The parity source (running counter, F-2, or the VBA per-phase index) is the loop's choice; the coupling only takes `step_index % 2`. | the force history / unbalance schedule, output types, the SDOF update itself, phase boundaries |
| `moc.py` | The 1-D MoC fluid column (Stage 4.2): grid construction (`grid_size`: `pipeSegQTY`, `pivotSegQTY`, `extQTY`; `is_short_pipe`), the interp-fraction profiles tabulated once per grid (`interp_fractions`), the four contiguous state arrays (`new_column`: `p_a`, `v_a` on the A nodes `0..N`, `p_b`, `v_b` on the B cells `0..N-1`), and one kernel `step(even, a_dt, arrays…, scalars…, d_f) -> d_f` with scalar loop bodies: the even/odd half-step update, the decaying end-node boundary (`dacayFactor`), the mean-velocity (`vAv`) subtraction and the low-pass `dF`. No per-cell helper calls, no Python objects: Stage 5 `@njit`s it whole. The VBA's dead `useUndamped` branch (`Const useUndamped = False`, the AFT infinite-pipe boundary, lines 803-818) is **not ported**; only the live decaying boundary is. `vav_divisor(N, "legacy" \| "fixed")` selects `2N - 1` (VBA, D-17) or `2N + 1` (approved fix F-1). Driven by the JC coupling. | the structure proxy, the force history, output types, the sub-step counter (it is told the parity) |
| `response.py` | Public API. `peak_response(...)` (lumped) and `peak_response_jc(...)` (Stage 4.2) each do their own set-up and pass a coupling object to one shared integration loop (sample loop, max trackers, result history, free-decay phase, output-type switch). Returns a `PeakResponse` dataclass with 0-based histories (no VBA pad). The two set-ups are *not* merged into one function with flags. The JC set-up is `structure.jc_params` (rigid mass; stiffness, damping, `fricAcc` on the total mass, VBA 726-729), `moc.grid_size` and the short-pipe fallback to `peak_response`; the loop runs under `np.errstate(raise)` because the MoC arrays are numpy. `peak_response_jc` carries the approved-fix flags `vav_denominator` ("legacy" \| "fixed", F-1) and `parity` ("per_phase" \| "running", F-2); the loop turns `parity` into the `step_index` it passes to the coupling (`n + off`, `off` fixed per sample). | the internals of `step`, the MoC arrays, how `loads` interpolates |
| `pressure.py` | `pressure_response(...)` (Stage 4.3): the valve/pump water-hammer MoC (`GetPressureResponse`) as a standalone driver. `setup` computes the run constants once (`PressureSetup`: `outMax`, `pipeSegQTY` via `grid_size` with the `outMax` truncation D-22, `factor`, `rhoC`, `velocityInitial`, `valveLoss`, `valveDPInitial`, `pipeLoss`); `initial_column` builds the steady column in four contiguous arrays `p_a, v_a, p_b, v_b` (length `N + 1`, `B[N]` is the pump boundary) and `velAtPump`; per iteration (two time steps) `valve_closure` walks the pattern column-major with linear interpolation (D-10), `valve_boundary` (open / fully-closed at `closure >= 0.999999999`), `half_step_a_from_b` (clamp `0.9`), `pump_boundary` (ramp on the reverse-flow-clipped velocity), `half_step_b_from_a` (clamp `0.9 * rhoC`): the two half-loops keep their D-6 asymmetry literally. Scalar loop bodies over the arrays, `sysMat` as two locals, numpy element reads as in the legacy, the run under `np.errstate(raise)`. Returns the 0-based `resultArray(0 To outMax)` unchanged. `get_pressure_response(...)` is a thin alias with the legacy signature (bench case (d), legacy callers). | the peak-response solvers, `structure`, `loads` beyond `as_history_2d`, `coupling`, `moc` |

Interfaces fixed in Stage 4.1 so that later sessions write against them:

* `structure.State = (x, v, a)` tuple of Python floats; `structure.SdofParams` named tuple
  `(mass, stiffness, damping, fric_acc, gap, ratio2)`; `structure.step(state, f_applied,
  params, dt) -> State`.
* `loads.unbalance_force(history, sample_freq, physical_length, celerity, step_qty)` is a
  generator: one `list[float]` per sample (the per-sub-step `forceA − forceB` values, in
  order, the last delay-phase sample truncated at the VBA `Exit For`).
* `coupling.Coupling.coupling_force(state, step_index) -> float`; `step_index` is a
  running sub-step counter over the whole run (0 at the first sub-step), or, with
  `peak_response_jc(parity="per_phase")`, the VBA per-phase index (D-19; Stage 4.2).
* `coupling.JunctionCoupling(pipe_seg_qty, pivot_seg_qty, dt, rho_c, fluid_area, decay,
  vav_denominator)` (Stage 4.2).
* `moc.step(even, a_dt, p_a, v_a, p_b, v_b, frac_a, frac_b, n_seg, pivot, rho_c, decay,
  vav_div, fluid_area, d_f) -> d_f` (Stage 4.2): one MoC sub-step in place on the four
  arrays; `even` is the half-grid to update, `a_dt` the structure acceleration times `dt`.
* `structure.jc_params(physical_length, portal_frame_height, mass_per_unit_len,
  fluid_densty, fluid_area, damping_percent, dynamic_fric, nat_freq, dt, gap,
  restrain_freq_ratio) -> SdofParams` (Stage 4.2).
* `response.peak_response_jc(..., *, vav_denominator, parity) -> PeakResponse` (Stage 4.2).
* `pressure.pressure_response(valve_pattern, closure_time, celerity, density, time_step,
  pressure_drop_from_pump, flow_rate, pipe_area, valve_cv, length_to_pump,
  pump_ramp_pressure) -> np.ndarray` (Stage 4.3): the 0-based valve pressure history,
  `outMax + 1` samples at `2 * timeStep`, identical to `legacy_port.get_pressure_response`;
  `pressure.get_pressure_response` is the alias. Set-up pieces: `pressure.setup(...) ->
  PressureSetup`, `pressure.initial_column(setup) -> (p_a, v_a, p_b, v_b, vel_at_pump)`,
  `pressure.valve_closure(pattern_2d, tot_ind, factor) -> float`, and the four in-place
  updates `valve_boundary`, `half_step_a_from_b`, `pump_boundary`, `half_step_b_from_a`.
* `response.PeakResponse` fields: `max_static_equivalent_force`, `max_displacement`,
  `max_velocity`, `max_acceleration`, `max_applied_force`, `history` (None for
  `output_type = 0`; otherwise a 0-based array of length `outMax * 2`, element `t − 1` =
  state at the end of sample `t`), `output_type`, `free_decay_samples`.

Exactness notes (why the restructure is behaviour-preserving; proved by the differential
suite at rtol 1e-12, observed bitwise):

* Python-float vs numpy-scalar arithmetic: both are IEEE double; `**` calls C `pow` on
  both (port_review §3.1-d). The Stage 4.0 experiment already showed bitwise equality.
* `(a + aNew) * dt / 2` → `(a + aNew) * half_dt` with `half_dt = dt / 2`: scaling by a
  power of two commutes with rounding (no subnormals), so the results are identical.
* `k / (stepQTY − 1)` and `1 − k / (stepQTY − 1)` are tabulated once per run; the table
  holds the same doubles the per-step expression produced.
* `max(0, |x| − gap) * sign(x)` and the `minUnsigned` ladder are inlined branch for
  branch, including the `* ±1.0` products (exact) and the int-0 → `0.0` case.
* `0.0 + F` / `0.0 − R` from `NoCoupling` differ from `F` / `−R` only in the sign of an
  exact zero.
* `pressure.py` (Stage 4.3): the column arrays are numpy and every element read is a
  `numpy.float64`, as in the legacy's `(2, N + 1)` arrays, so each operation is the same
  IEEE double operation in the same order; `sysMat(0)`/`sysMat(1)` as two locals hold the
  same doubles; `vba_min`/`vba_max` keep the VBA tie rule (second argument) that the legacy's
  `min`/`max` had, including `max(0, x)` returning the int `0` that becomes `0.0` in the
  array and `min(0, v) / velAtPump` giving `-0.0`. Proved bitwise on the Example case and 49
  of 50 sweep cases; the 50th overflows identically (`FloatingPointError` under
  `np.errstate(raise)`) in both.
