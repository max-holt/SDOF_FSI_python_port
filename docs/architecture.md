# Architecture — Stage 4 target layout

One line per module: what it is responsible for, and what it must not know about.
The target structure is fixed for the whole of Stage 4; sessions fill it in module by
module (4.1: `structure`, `loads`, `coupling` (`NoCoupling` only), `response` lumped
path; later: `moc`, the JC coupling, `pressure`). `legacy_port.py` stays the reference
implementation until Stage 6 and every new module is proved against it by
`tests/test_differential.py`.

```
src/surge_sdof/
  vba_compat.py        # unchanged
  legacy_port.py       # frozen; reference implementation until Stage 6
  moc.py               # 1-D MoC fluid column: state arrays, half-step update, boundary conditions
  structure.py         # SDOF: portal-frame proxy, restoring force with gap, Coulomb friction, time-step kernel
  coupling.py          # coupling force from the moc state (interp fractions, low-pass dF)
  loads.py             # elbow-to-elbow unbalance force from a history: transit delay, phase scheduling
  response.py          # public API: peak_response(...) and peak_response_jc(...); returns a dataclass
  pressure.py          # get_pressure_response (valve/pump MoC) as a standalone driver
```

| module | responsibility | must not know about |
|---|---|---|
| `vba_compat.py` | VBA runtime semantics (`CLng`, `floor`, `modDbl`, `sign`, `min/maxUnsigned`, padded 1-based arrays). Unchanged. | any solver quantity |
| `legacy_port.py` | Line-for-line Stage 1 transcription of the VBA; the oracle for the differential tests. Frozen (no edits, no imports *from* it in new modules except in tests). | the new modules |
| `structure.py` | The SDOF pipe proxy: `solve_portal_height` (seed + 11 `solve_poly` passes), `lumped_params` (mass, stiffness, damping, `fricAcc`), `restoring_force(x, k, gap, ratio)` (bilinear support gap), and `step(state, f_applied, params, dt)` — exactly the VBA update (explicit `aNew` from the old state, trapezoidal `v` and `x`, stick/slip Coulomb friction) on Python floats with the clamp/sign ladders inlined. One function, called from one loop. | where `f_applied` comes from (force histories, transit delay, fluid coupling), sample/phase bookkeeping, max trackers, output types |
| `loads.py` | The elbow-to-elbow unbalance force `forceA − forceB` from a force history: `transit_delay` (`unballanceStepQTY`), the `kOverlap` sub-sample offset and the three-phase scheduling (delay phase with `forceA` held, ramp phase with both forces interpolated, no force in free decay), walked column-major over 2-D histories exactly as the VBA. Yields one list of per-sub-step values per sample. | the structure state, stiffness or damping, fluid coupling, what the caller does with each sample (result histories, free decay) |
| `coupling.py` | The force the fluid column exerts on the structure: `Coupling.coupling_force(state, step_index) -> float`. `NoCoupling` returns `0.0`. `JunctionCoupling` (Stage 4.2) owns the column arrays, the tabulated interp fractions and the low-pass `dF`: each call feeds the state's acceleration (`a * dt`) into the moving cells, advances the column one sub-step with `moc.step` on the half-grid `step_index % 2` selects, and returns the new `dF` as a Python float. The parity source (running counter, F-2, or the VBA per-phase index) is the loop's choice; the coupling only takes `step_index % 2`. | the force history / unbalance schedule, output types, the SDOF update itself, phase boundaries |
| `moc.py` | The 1-D MoC fluid column (Stage 4.2): grid construction (`grid_size`: `pipeSegQTY`, `pivotSegQTY`, `extQTY`; `is_short_pipe`), the interp-fraction profiles tabulated once per grid (`interp_fractions`), the four contiguous state arrays (`new_column`: `p_a`, `v_a` on the A nodes `0..N`, `p_b`, `v_b` on the B cells `0..N-1`), and one kernel `step(even, a_dt, arrays…, scalars…, d_f) -> d_f` with scalar loop bodies: the even/odd half-step update, the decaying end-node boundary (`dacayFactor`), the mean-velocity (`vAv`) subtraction and the low-pass `dF`. No per-cell helper calls, no Python objects: Stage 5 `@njit`s it whole. The VBA's dead `useUndamped` branch (`Const useUndamped = False`, the AFT infinite-pipe boundary, lines 803-818) is **not ported**; only the live decaying boundary is. `vav_divisor(N, "legacy" \| "fixed")` selects `2N - 1` (VBA, D-17) or `2N + 1` (approved fix F-1). Driven by the JC coupling. | the structure proxy, the force history, output types, the sub-step counter (it is told the parity) |
| `response.py` | Public API. `peak_response(...)` (lumped) and `peak_response_jc(...)` (later) each do their own set-up and pass a coupling object to one shared integration loop (sample loop, max trackers, result history, free-decay phase, output-type switch). Returns a `PeakResponse` dataclass with 0-based histories (no VBA pad). The two set-ups are *not* merged into one function with flags. | the internals of `step`, the MoC arrays, how `loads` interpolates |
| `pressure.py` | `get_pressure_response` (valve/pump MoC) as a standalone driver (later session). | the peak-response solvers |

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
