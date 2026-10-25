# Architecture — Stage 4 layout, as built (Stage 5: compiled kernels)

One line per module: what it is responsible for, and what it must not know about.
The structure was fixed at the start of Stage 4 and filled in module by module (4.1:
`structure`, `loads`, `coupling` (`NoCoupling` only), `response` lumped path; 4.2: `moc`, the
JC coupling; 4.3: `pressure`, `_vba_semantics`; 4.4: hygiene, no behaviour change; 5: the three
inner loops compiled with Numba, see "Stage 5 — compiled kernels"; Session V.1: the
sub-step trace for visualisation, see "Session V.1 — the trace"). This document describes
the code as it stands after Session V.1. `legacy_port.py` stays the reference
implementation until Stage 6 and every new module is proved against it by
`tests/test_differential.py`. Every public function and dataclass of the six live modules
carries a numpy-style docstring with the unit of each physical argument and return and the
DEVIATIONS id of each VBA quirk it preserves.

```
src/surge_sdof/
  vba_compat.py        # frozen (Stage 1 VBA runtime semantics; no edits)
  _vba_semantics.py    # live home for VBA tie/NaN comparison semantics (vba_min, vba_max)
  legacy_port.py       # frozen; reference implementation until Stage 6
  moc.py               # 1-D MoC fluid column: state arrays, half-step update, boundary conditions
  structure.py         # SDOF: portal-frame proxy, restoring force with gap, Coulomb friction, time-step kernel
  coupling.py          # coupling force from the moc state (interp fractions, low-pass dF)
  loads.py             # elbow-to-elbow unbalance force from a history: transit delay, phase scheduling
  response.py          # public API: peak_response(...) and peak_response_jc(...); returns a dataclass; one private _integrate loop
  trace.py             # Session V.1: the Trace dataclass of a traced run (trace_every > 0) and its allocation / assembly helpers
  viz/animate.py       # Session V.2: the two-panel plotly animation of a Trace (optional `viz` extra: plotly, pandas); tools/animate.py drives it
  pressure.py          # pressure_response (valve/pump MoC) as a standalone driver; get_pressure_response is a thin alias
```

| module | responsibility | must not know about |
|---|---|---|
| `vba_compat.py` | VBA runtime semantics (`CLng`, `floor`, `modDbl`, `sign`, `min/maxUnsigned`, padded 1-based arrays). **Frozen**: no edits; new modules may import from it, but any VBA semantic it lacks goes into `_vba_semantics.py`. | any solver quantity |
| `_vba_semantics.py` | The live home for VBA comparison semantics: `vba_min`/`vba_max` (the module-level VBA `min`/`max`, lines 3-17: on a tie or with NaN the **second** argument is returned, with its type and sign of zero; Python's built-ins return the first). One copy, used by `pressure.py`, surviving the Stage 6 removal of `legacy_port.py` (whose `min`/`max` are the same functions). | any solver quantity |
| `legacy_port.py` | Line-for-line Stage 1 transcription of the VBA; the oracle for the differential tests. Frozen (no edits, no imports *from* it in new modules except in tests). | the new modules |
| `structure.py` | The SDOF pipe proxy: `solve_portal_height` (seed + 11 `solve_poly` passes), `lumped_params` (mass, stiffness, damping, `fricAcc`), `restoring_force(x, k, gap, ratio)` (bilinear support gap), and `step(state, f_applied, params, dt)` — exactly the VBA update (explicit `aNew` from the old state, trapezoidal `v` and `x`, stick/slip Coulomb friction) on Python floats with the clamp/sign ladders inlined. Stage 5: the arithmetic is `step_scalars(x, v, a, f_applied, mass, stiffness, damping, fric_acc, gap, ratio2, dt)`, compiled with `numba.njit(cache=True)`; `step` unpacks the tuple and the `SdofParams` for it. One kernel, called from one loop. | where `f_applied` comes from (force histories, transit delay, fluid coupling), sample/phase bookkeeping, max trackers, output types |
| `loads.py` | The elbow-to-elbow unbalance force `forceA − forceB` from a force history: `transit_delay` (`unballanceStepQTY`), the `kOverlap` sub-sample offset and the three-phase scheduling (delay phase with `forceA` held, ramp phase with both forces interpolated, no force in free decay), walked column-major over 2-D histories exactly as the VBA. Yields one list of per-sub-step values per sample. Session V.1: the index walk is one private per-sample `_schedule` generator; `unbalance_force` (inner `k` loops unchanged) and `elbow_forces` (the two forces apart, with the sample's phase, for the trace) consume it. | the structure state, stiffness or damping, fluid coupling, what the caller does with each sample (result histories, free decay) |
| `coupling.py` | The force the fluid column exerts on the structure: `Coupling.coupling_force(state, step_index) -> float`. `NoCoupling` returns `0.0`. `JunctionCoupling` (Stage 4.2) owns the column arrays, the tabulated interp fractions and the low-pass `dF`: each call feeds the state's acceleration (`a * dt`) into the moving cells, advances the column one sub-step with `moc.step` on the half-grid `step_index % 2` selects, and returns the new `dF` as a Python float. The parity source (running counter, F-2, or the VBA per-phase index) is the loop's choice; the coupling only takes `step_index % 2`. Stage 5: `coupling_force` is the Python-level interface; the compiled loop reads `KIND` (0 / 1) and the junction's arrays and scalars instead and performs the same update, `_integrate` writes `d_f` back. | the force history / unbalance schedule, output types, the SDOF update itself, phase boundaries |
| `moc.py` | The 1-D MoC fluid column (Stage 4.2): grid construction (`grid_size`: `pipeSegQTY`, `pivotSegQTY`, `extQTY`; `is_short_pipe`), the interp-fraction profiles tabulated once per grid (`interp_fractions`), the four contiguous state arrays (`new_column`: `p_a`, `v_a` on the A nodes `0..N`, `p_b`, `v_b` on the B cells `0..N-1`), and one kernel `step(even, a_dt, arrays…, scalars…, d_f) -> d_f` with scalar loop bodies: the even/odd half-step update, the decaying end-node boundary (`dacayFactor`), the mean-velocity (`vAv`) subtraction and the low-pass `dF`. No per-cell helper calls, no Python objects: Stage 5 compiles it whole with `numba.njit(cache=True)`, body unchanged. The VBA's dead `useUndamped` branch (`Const useUndamped = False`, the AFT infinite-pipe boundary, lines 803-818) is **not ported**; only the live decaying boundary is. `vav_divisor(N, "legacy" \| "fixed")` selects `2N - 1` (VBA, D-17) or `2N + 1` (approved fix F-1). Driven by the JC coupling. | the structure proxy, the force history, output types, the sub-step counter (it is told the parity) |
| `response.py` | Public API. `peak_response(...)` (lumped) and `peak_response_jc(...)` (Stage 4.2) each do their own set-up and pass a coupling object to one shared integration loop `_integrate` (Stage 5: the Python orchestrator of the compiled `_integrate_kernel`: sample loop, max trackers, result history through `_record`, free-decay phase with the `_decay_test` overflow check; the static-equivalent force and the `PeakResponse` are built in Python). Returns a `PeakResponse` dataclass with 0-based histories (no VBA pad). The two set-ups are *not* merged into one function with flags. The JC set-up is `structure.jc_params` (rigid mass; stiffness, damping, `fricAcc` on the total mass, VBA 726-729), `moc.decay_factor`, `moc.grid_size` and the short-pipe fallback to `peak_response`; `rhoC = 0` is rejected at the set-up (D-9; `np.errstate` has no effect inside the compiled kernel). `peak_response_jc` carries the approved-fix flags `vav_denominator` ("legacy" \| "fixed", F-1) and `parity` ("per_phase" \| "running", F-2); the loop turns `parity` into the `step_index` it passes to the coupling (`n + off`, `off` fixed per sample). Session V.1: both solvers take `trace_every: int = 0`; with `k > 0` the kernel records every `k`-th sub-step into preallocated arrays and the result carries `PeakResponse.trace`. | the internals of `step`, the MoC arrays, how `loads` interpolates |
| `trace.py` | Session V.1. `Trace`, the frozen dataclass of a traced run (per-frame arrays `t, sub_step, sample, phase, x, v, a, f_a, f_b, f_unbalance, f_friction, stick, d_f`; JC only `p_cells`, `v_cells` and the column geometry; one-off `solver`, `trace_every`, `dt`, `step_qty`, `out_max`, `params`, `inputs`), the frame-array column constants the kernel writes (`F_*`, `I_*`), `capacity` (frames to allocate: the forced sub-steps plus free decay up to the history window), `check_memory` (`MAX_TRACE_VALUES`, `ValueError` naming the smallest stride that fits), `allocate`, `interleave` (the staggered grid as `A0 B0 A1 … AN`) and `build` (slices and copies the kernel arrays into a `Trace`). | the solver loop, `loads`, `moc.step` (it only lays out what the kernel copied) |
| `viz/animate.py` | Session V.2 / V.2b. The model animation of a traced run, read-only on a `PeakResponse`: `loop_layout` (the interleaved column on the expansion loop, mapped by moving fraction: fraction-0 cells at each end are the horizontal inlet / outlet, the ramp cells the vertical legs, fraction-1 cells the run along `y = 0`; uniform spacing by `cell_position` along the centreline, sharp elbows; a lumped run rebuilds the grid it would have with `moc.grid_size` / `moc.interp_fractions`), `select_frames` (the frame stride for at most `max_frames` frames, the last traced frame kept), `scalars_table` (pandas, the per-frame scalars with a synthetic `t = 0` row), `is_capped`, `build_figure` (Panel 1: circles offset by `x(t) * moving_fraction * exaggeration`, sized by pressure, coloured by velocity; Panel 2: `f_unbalance` on the left axis over `f_friction` on the right (drawn first, translucent), both symmetric so the zero lines coincide, phase bands, peak-`\|x\|` marker, cursor; plotly frames that change trace data only (no redraw), slider, play / pause; `t_start` / `t_end` animate a window, shaded on Panel 2) and `write_html` (CDN page with a typed playback speed). Imports plotly / pandas lazily. | the solvers (it never runs one; `tools/animate.py` does), `moc.step`, `loads` |
| `pressure.py` | `pressure_response(...)` (Stage 4.3): the valve/pump water-hammer MoC (`GetPressureResponse`) as a standalone driver. `setup` computes the run constants once (`PressureSetup`: `outMax`, `pipeSegQTY` via `grid_size` with the `outMax` truncation D-22, `factor`, `rhoC`, `velocityInitial`, `valveLoss`, `valveDPInitial`, `pipeLoss`); `initial_column` builds the steady column in four contiguous arrays `p_a, v_a, p_b, v_b` (length `N + 1`, `B[N]` is the pump boundary) and `velAtPump`; per iteration (two time steps) `valve_closure` walks the pattern column-major with linear interpolation (D-10), `valve_boundary` (open / fully-closed at `closure >= 0.999999999`), `half_step_a_from_b` (clamp `0.9`), `pump_boundary` (ramp on the reverse-flow-clipped velocity), `half_step_b_from_a` (clamp `0.9 * rhoC`): the two half-loops keep their D-6 asymmetry literally. Scalar loop bodies over the arrays, `sysMat` as two locals, numpy element reads as in the legacy, the run under `np.errstate(raise)`. Not compiled in Stage 5: a run is milliseconds (bench case (h): about 5 ms), so it is not a bottleneck and keeps its numpy-scalar `errstate` semantics. Returns the 0-based `resultArray(0 To outMax)` unchanged. `get_pressure_response(...)` is a thin alias with the legacy signature (bench case (d), legacy callers). | the peak-response solvers, `structure`, `loads` beyond `as_history_2d`, `coupling`, `moc` |

## Data flow for one sub-step

**Lumped path** (`peak_response`). Set-up once per run: `loads.as_history_2d` shapes the
history, `loads.transit_delay` gives `unballanceStepQTY` (samples) and with it `outMax`,
`structure.solve_portal_height` and `structure.lumped_params` give the `SdofParams`
(mass kg, stiffness N/m, damping N·s/m, `fric_acc` m/s, gap m, `ratio2`), and
`loads.unbalance_force` is created as a generator. Per sample, `_integrate` pulls the next
`list` of per-sub-step `forceA − forceB` values (N) from the generator. Per sub-step it calls
`coupling.coupling_force(state, n + off)` first (`NoCoupling`: `0.0`), adds the sub-step's
unbalance value `f`, and passes the sum as `f_applied` to `structure.step(state, f_applied,
params, dt)`, which computes `aNew` from the *old* `(x, v)`, the trapezoidal `v_new` with the
stick/slip friction ladder, and the trapezoidal `x`. `_integrate` then updates the four max
trackers (`|a|`, `|v|`, `|x|`, `|f|`) and increments the running counter `n`. At the end of
the sample `_record` stores `x`, `v` or `a` in the 0-based history for `output_type` 1-3.
When the generator is exhausted (phase 1 delay and phase 2 ramp both done) the free-decay
phase repeats the same sub-step with `f_applied = coupling_force(...)` alone, `stepQTY`
sub-steps per sample, while `x * xZero > 0.01` (D-21). Finally the static-equivalent force is
`|structure.effective_displacement(xMax)| * stiffness` and the `PeakResponse` is built.

**JC path** (`peak_response_jc`). The same loop and the same `structure.step`; the set-up adds
`structure.jc_params` (rigid mass), `moc.decay_factor`, `moc.grid_size` (and the short-pipe
fallback, which returns `peak_response` outright), and a `JunctionCoupling` that owns the
four column arrays (`p_a`, `v_a` on the A nodes `0..N`, `p_b`, `v_b` on the B cells `0..N-1`;
Pa and m/s), the tabulated interp fractions and `dF`. Per sub-step, before `structure.step`,
`JunctionCoupling.coupling_force(state, step_index)` takes the previous sub-step's
acceleration `a`, forms `a * dt` (m/s) and calls `moc.step(even=step_index % 2 == 0, …)`,
which updates one half-grid in place. Even: the mean velocity `vAv` over the `2N + 1`
velocities divided by `vav_div` (2N+1 by default, 2N−1 with `vav_denominator="legacy"`,
D-17), the decaying end nodes (`p_b / dacayFactor`), the interior A nodes from the two
neighbouring B characteristics, then every B velocity gains `a dt · frac_b[n] − vAv`; `dF`
is formed from the A pressures on either side of the two pivots. Odd: the B cells from the
two neighbouring A characteristics, then the interior A velocities gain `a dt · frac_a[n]`;
`dF` from the B pressures at the pivots. In both, `dF ← 0.25 dF + 0.75 · fluidArea · Δp`
(N) is returned as a Python float, added to the sub-step's `f`, and `structure.step` runs
with the JC `SdofParams`. `step_index` is the running counter `n` (`parity="running"`, F-2)
or the VBA per-phase index `n + off` (`parity="per_phase"`, D-19); the coupling only reads
its parity. The loop runs under `np.errstate(raise)` so a zero `rhoC` or a fluid overflow
raises mid-run (D-9 as a raise).

**Pressure path** (`pressure_response`, for completeness). Independent of the above: `setup`
once, `initial_column` once, then per loop iteration (two time steps) `valve_closure` →
`valve_boundary` → `half_step_a_from_b` → `pump_boundary` → `half_step_b_from_a`, and
`p_a[0]` is the sample (Pa). The module docstring of `pressure.py` has the detail.

## Interfaces

Interfaces fixed in Stage 4.1 so that later sessions write against them:

* `structure.State = (x, v, a)` tuple of Python floats; `structure.SdofParams` named tuple
  `(mass, stiffness, damping, fric_acc, gap, ratio2)`; `structure.step(state, f_applied,
  params, dt) -> State`; `structure.step_scalars(x, v, a, f_applied, mass, stiffness,
  damping, fric_acc, gap, ratio2, dt) -> (x, v, a)` (Stage 5, the compiled kernel `step`
  wraps).
* `loads.unbalance_force(history, sample_freq, physical_length, celerity, step_qty)` is a
  generator: one `list[float]` per sample (the per-sub-step `forceA − forceB` values, in
  order, the last delay-phase sample truncated at the VBA `Exit For`).
* `coupling.Coupling.coupling_force(state, step_index) -> float`; `step_index` is a
  running sub-step counter over the whole run (0 at the first sub-step), or, with
  `peak_response_jc(parity="per_phase")`, the VBA per-phase index (D-19; Stage 4.2).
  `Coupling.KIND` (Stage 5): 0 for `NoCoupling`, 1 for `JunctionCoupling`, read by
  `response._integrate` to unpack the coupling for the compiled loop.
* `coupling.JunctionCoupling(pipe_seg_qty, pivot_seg_qty, dt, rho_c, fluid_area, decay,
  vav_denominator)` (Stage 4.2).
* `moc.step(even, a_dt, p_a, v_a, p_b, v_b, frac_a, frac_b, n_seg, pivot, rho_c, decay,
  vav_div, fluid_area, d_f) -> d_f` (Stage 4.2): one MoC sub-step in place on the four
  arrays; `even` is the half-grid to update, `a_dt` the structure acceleration times `dt`.
* `structure.jc_params(physical_length, portal_frame_height, mass_per_unit_len,
  fluid_densty, fluid_area, damping_percent, dynamic_fric, nat_freq, dt, gap,
  restrain_freq_ratio) -> SdofParams` (Stage 4.2).
* `response.peak_response_jc(..., *, vav_denominator, parity) -> PeakResponse` (Stage 4.2).
* `response.peak_response(..., trace_every=0)` and `response.peak_response_jc(...,
  trace_every=0, *, ...)` (Session V.1): `trace_every` is a non-negative int (`operator
  .index`); `k > 0` records every `k`-th sub-step as `PeakResponse.trace`, a `trace.Trace`
  (see "Session V.1 — the trace"); 0 leaves `trace` None. The `PeakResponse` values are the
  same bitwise either way.
* `loads.elbow_forces(history, sample_freq, physical_length, celerity, step_qty)` (Session
  V.1) is a generator like `unbalance_force`: one `(phase, forceA list, forceB list)` per
  sample, `phase` 0 for the delay samples and 1 for the ramp samples, `forceA[k] -
  forceB[k]` bitwise the `unbalance_force` value.
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
  state at the end of sample `t`), `output_type`, `free_decay_samples`, and (Session V.1,
  trailing, default None) `trace`.
* Private, not an interface: `response._integrate(forces, params, dt, step_qty, coupling,
  out_max, output_type, legacy_parity=False)` (the Python orchestrator),
  `response._integrate_kernel(flat, offsets, mass, stiffness, damping, fric_acc, gap,
  ratio2, dt, step_qty, out_max, output_type, legacy_parity, history, kind, p_a, v_a, p_b,
  v_b, frac_a, frac_b, n_seg, pivot, rho_c, decay, vav_div, fluid_area, d_f, trace_every,
  flat_a, flat_b, delay_substeps, tr_f, tr_i, tr_p, tr_v) -> (x_max, v_max, a_max, f_max,
  x, v, a, tot_ind, forced_samples, d_f, n_frames)` (the compiled loop; the last eight
  arguments and `n_frames` are Session V.1), `response._trace_frame(...)` (the compiled
  per-frame write), `response._record(history, output_type, index, x, v, a)` (the
  per-sample history write, called once per sample) and `response._decay_test(x, x_zero)`.

## Exactness notes

Why the restructure is behaviour-preserving; proved by the differential suite at rtol 1e-12,
observed bitwise:

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
* Stage 4.4 (hygiene): the inlined `max(0, |x| − gap)` test is written `excess < 0` instead
  of the VBA-shaped `0 > excess` (ruff SIM300); the two are the same comparison for every
  double, NaN included (both false). The duplicated per-sample history write became
  `_record`, one assignment of the same float. The differential suite stayed bitwise.

## Stage 5 — compiled kernels

Three functions carry `@numba.njit(cache=True)`: `structure.step_scalars`, `moc.step` and
`response._integrate_kernel`. No `fastmath`, never object-mode `@jit`. Their bodies are
the Stage 4 code; what changed is the calling convention:

* **Signatures take floats, ints, bools and 1-D float64 arrays only.** `response._integrate`
  (plain Python) does the unpacking once per run: the `loads.unbalance_force` per-sample
  lists are concatenated into one flat float64 array plus an int64 offsets array (sample
  `s` is `flat[offsets[s]:offsets[s + 1]]`, so the truncated last delay-phase sample keeps
  its length); `SdofParams` becomes six floats; the coupling becomes `KIND` plus, for the
  junction, its six arrays and seven scalars (`NoCoupling` passes empty arrays and zeros
  that the kernel never reads). The kernel returns the four maxima, the final state,
  `tot_ind`, the forced-sample count and `dF`; `_integrate` writes `dF` back to the
  `JunctionCoupling` (its arrays were updated in place), casts to Python floats and builds
  the `PeakResponse`. The Python-level `Coupling.coupling_force` interface stays for
  callers and tests.
* **Both modes, one source.** With `NUMBA_DISABLE_JIT=1` `numba.njit` returns the
  undecorated function and the same code runs as Python. `float(flat[i])` and
  `float(moc.step(...))` in the kernel are no-ops under Numba and keep the SDOF state on
  Python floats in Python mode, so the Stage 4 overflow semantics (D-23) are unchanged
  there. `make test-both` runs the fast suite in both modes after wiping the on-disk Numba
  cache, because `cache=True` does not notice when a callee in another module changed
  (`moc.step` or `step_scalars` inside `_integrate_kernel`).
* **Error semantics inside the kernel.** `numpy.errstate` has no effect in compiled code.
  `rhoC = 0` is therefore rejected once at the `peak_response_jc` set-up with
  `FloatingPointError` (D-9; it used to raise from the first MoC update); a fluid overflow
  normally propagates nan/inf into the structure state and the end-of-run finiteness check
  raises `FloatingPointError` (D-23, as the lumped path already did; an overflow confined to
  far nodes until the run ends would pass silently, non-physical inputs only). `mass = 0` raises
  `ZeroDivisionError` in both modes (Numba's Python error model).
* **Exactness.** None of the three kernels contains `**` (the powers live in the set-up,
  which stays Python), so the D-15 lowering of integer-literal powers does not arise. LLVM
  does not contract multiply-adds into FMAs without fastmath, and `x / 2` as `x * 0.5`
  is exact. Measured on the full differential sweep under Numba (lumped sweep 100
  comparisons, JC sweep 100, JC small 16, Example cases): 216/216 bitwise equal to
  `legacy_port`; the differential rtol 1e-12 is unchanged (NOTES.md "Stage 5 — done").
* **Not compiled.** `pressure.pressure_response` (milliseconds per run, not a bottleneck;
  it keeps its numpy-scalar `errstate` semantics), the set-up (`solve_portal_height`,
  `lumped_params` / `jc_params`, `grid_size`, `interp_fractions`, `decay_factor`) and
  `loads.unbalance_force`, which is now the dominant cost of a compiled lumped run (the
  generator is Python; Stage 5b candidate).

## Session V.2 / V.2b / V.2c / V.2d — the animation

`surge_sdof.viz.animate.build_figure(result, case_name, max_frames=400, t_start=0)` turns a
traced `PeakResponse` into a two-panel plotly figure (`tools/animate.py --golden <case_id> |
--step … --out docs/viz/<name>.html` drives it; `docs/viz/` holds four CDN pages). The lead
author's requirements (22 Oct 2026) and the review rounds (V.2b and V.2c, 23 Oct; V.2d, 25 Oct) are
met as follows.

* **Geometry (V.2b).** The column is an expansion loop: inlet pipe, leg down, run, return leg
  up, outlet pipe. Cells are mapped by their moving fraction (`_segments`): the fraction-1
  block is the run (`y = 0`, `x = 0 .. run_length`); the last fraction-0 cell before it and the
  first after it are the upper elbows (the node-centred B ramp starts at exactly 0 at `n =
  extQTY`; the D-4 `n < 3` cell with fraction 0.111 sits one place earlier, on the inlet);
  the cells before / after them are the horizontal inlet / outlet at the pipe height, extending
  left of leg 1 and right of leg 2; the cells between are the vertical legs. Spacing is uniform
  by `cell_position` along the whole centreline and the four elbows are sharp corners at the
  elbow cells (V.2c: the model has no bends; the V.2b arcs were removed), so every inlet /
  outlet cell is at its pipe height, every run cell at `y = 0`, the legs vertical at `x = 0`
  and `x = run_length`, consecutive cells exactly one spacing apart (pinned by
  `tests/test_viz.py`). The pipe height is the centreline length between the elbow cells; it
  differs from `h` (`structure.solve_portal_height`, printed in the panel) and the two legs
  differ by one cell because the VBA B profile ramps one cell longer on the inlet side
  (Example JC: 7.5 m and 6.0 m for `h = 7.69 m`; row 96: 4.03 m and 4.00 m for `h = 4.05 m`).
  A lumped run uses the layout of the grid it would have (`moc.grid_size`,
  `moc.interp_fractions`; a `pivotSegQTY = 4` grid, D-4, gets the B profile with the `n <
  extQTY` test, display only).
* **Frames.** Frame 0 is synthetic (`t = 0`, `x = 0`, the column at rest, no forces) so playback
  starts from rest; the V.1 convention (frame `i` = end of sub-step `i k`, so the first traced
  frame is at `t = dt`) is untouched. The animation shows every `frame_stride`-th traced frame
  with the last one always included, at most `max_frames` (400) frames; `t_start` / `t_end`
  (V.2d) animate a time window only (`t_start > 0` drops the rest frame), the frame
  count and stride then counted inside the window, while Panel 2 keeps the whole run and shades
  the window: a 20 s run at 3 Hz cannot be followed at 150 or 400 frames (0.14 s or 0.05 s a
  frame, 0.42 or 0.15 of a period, several wave transits), so the committed row 96 page is
  the window 6.0–7.5 s around the peak at 151 frames of 10 ms (0.03 period, half a transit). A frame changes trace data only (the circles,
  the cursor and a status text with the frame time and phase in Panel 1), never the layout, and
  every animate call uses `redraw: false`: a per-frame layout change forces a full redraw,
  which made the lines flicker and drop the right-axis trace at high speed (V.2c). The figure
  carries plotly play (1x = 40 ms a frame) / pause buttons; the written page replaces them with
  a typed playback speed (any positive multiplier), play and pause under the slider
  (`SPEED_CONTROL_JS`, run after the plot is made). The title prints
  `trace_every`, the stride, the frame count, the nominal circle size and "trace capped by the
  history window" when the run decayed past the traced window (`is_capped`: `forced_samples +
  free_decay_samples > 2 outMax`).
* **Panel 1.** `x_circle = x_nominal + x(t) * moving_fraction * exaggeration` with
  `exaggeration = 0.1 * run_length / max|x|` (printed); `size = nominal * (1 + k_p (p - p_ref) /
  p_scale)` with `p_ref = 0` (the initial column), `p_scale = max|p - p_ref|` over the trace and
  `k_p` such that the largest circle of the run is exactly 2x nominal (floor 0.15x); the nominal
  diameter (`clip(1800 / n_cells, 5, 12)` px) is capped at 0.8 of the on-screen cell spacing
  (estimated from the fixed 1200 x 900 px figure) but not below 3 px, so a 1333-cell column
  draws as a 3 px tube. Colour is `v_cells` exactly as held (relative fluid velocity) on a
  blue–grey–red diverging scale with `cmin = -max|v|`, `cmax = +max|v|` (the same picture as
  `v / max|v|` centred at zero), colour bar "relative fluid velocity (JC arrays)" in m/s. Lumped:
  constant nominal size and the grey midpoint. Hover: cell index, kind, segment, position,
  fraction, and `p` / `v` for JC. The per-frame arrays are float32 (plotly typed arrays) to keep
  the HTML small; `docs/viz/golden_r096_jc.html` is a 1.5 s window (`--t-start 6 --t-end 7.5
  --max-frames 160`, 151 frames, 4.9 MB; 400 frames of 1333 cells is ~10 MB).
* **Panel 2.** `f_unbalance = F_A(t) - F_B(t - L/c)` on the left axis over `f_friction`
  (`Trace.f_friction`, the owner's definition) on the right, the friction drawn first, 1.5 px
  and translucent so it sits under the load line, both ranges symmetric (`±1.06 max|f|`) so
  the zero lines coincide, legend labels naming the axis; over the whole trace plus
  the `t = 0` row (`scalars_table`); the phase bands and the cursor on the primary axis (a band
  is labelled when it spans 6 % of the axis, the current phase is always in the title), the
  time of peak `|x|` marked.
* **`--step` (tools/animate.py).** Zero force for `--lead-in` (0.1 s), then `--amplitude` bar on
  the fluid area (`--size` mm internal diameter or `--area` m²) for `--duration`;
  `docs/viz/example_jc_step.html` is this step with the Example-sheet parameters (1600 bar on
  0.05 m² = 8 MN, the sheet's first level), `example_jc_sheet.html` the untrimmed sheet history.

## Session V.1 — the trace

`peak_response(..., trace_every=k)` and `peak_response_jc(..., trace_every=k)` with `k > 0`
return a `PeakResponse` whose `trace` is a `trace.Trace`: every `k`-th sub-step of the run,
recorded inside `_integrate_kernel` and meant for visualisation (Session V.2). The module
docstring of `trace.py` is the reference; the design points:

* **Frame convention.** Frame `i` is the end of sub-step `i * k`, `sub_step` being the
  kernel's running counter `n` (the index whose parity drives the MoC half-grids). `t = (sub_step
  + 1) * dt`; `x, v, a` the state after the sub-step; `f_a`, `f_b`, `f_unbalance = f_a − f_b`
  the forces applied during it (zero in free decay); `d_f` the junction force the sub-step used
  (`moc.step` runs before the SDOF update; zeros for lumped); `p_cells`, `v_cells` the column
  after it. `sample` is `totInd − 1` (the `history` index); `phase` is 0 while the delay samples
  of `loads.elbow_forces` last (transit), 1 to the end of the schedule (history), 2 in free
  decay. Frame 0 is the end of sub-step 0, where a column at rest with `a = 0` is still the
  initial column bitwise.
* **`f_friction` and `stick`.** `f_friction = mass · dv_friction / dt` with `dv_friction = v_new
  − (v_old + (a_old + a_new) · dt / 2)`: the velocity the Coulomb branch of `step_scalars`
  added or removed, recomputed in the recording branch from the same doubles the kernel formed
  (`half_dt = dt / 2`, `v + av`), so `structure.py` is untouched. Slip gives `∓fric_acc`
  (exactly `0.0` with `dynamicFric = 0`, and in the D-20 dead zone), stick (`|v_old| <
  fric_acc`, the `stick` flag) gives the momentum the stick removed, the holding force.
* **Window and capacity.** Phase 3's length is unknown before the run, so the trace follows
  the history's own cap: free decay is traced while `totInd <= outMax · 2` (the `_record`
  guard), later sub-steps are integrated but not traced. `trace.capacity` allocates once for
  `forced sub-steps + max(0, outMax · 2 − forced samples) · stepQTY` sub-steps at the stride; the
  kernel returns the frames written and `trace.build` slices. `trace.check_memory` raises
  `ValueError` before allocating when `capacity · (8 float columns + 4 int columns + 2 ·
  n_cells)` 8-byte values would exceed `MAX_TRACE_VALUES` (50e6, 400 MB; this contains the
  `n_frames · n_cells` of each column array), naming the smallest stride that fits.
* **Kernel hook.** `_integrate` flattens `loads.elbow_forces` like the unbalance values
  (`flat_a`, `flat_b`, and `delay_substeps` for the phase label), allocates `tr_f (cap, 8)`
  float64, `tr_i (cap, 4)` int64 and `tr_p`, `tr_v (cap, n_cells)` (column layout
  interleaved `A0 B0 A1 … AN`, `n_cells = 2N + 1`; `(0, 0)` for lumped or untraced). Per
  sub-step the kernel tests `rec = trace_every > 0 and n % trace_every == 0 and frame < cap`
  (phase 3 also `tot_ind <= out_max · 2`), saves `v_old, a_old` before `step_scalars` when
  `rec`, and calls the compiled `_trace_frame` after it, which writes the row and, for `kind`
  1, copies the four column arrays. The recording reads the state and writes the trace arrays
  only; the state arithmetic is the same whether or not it runs, so the traced run's
  `PeakResponse` equals the untraced one bitwise (`tests/test_trace.py`, both solvers, strides
  1 / 3 / 7, output types, both flag sets). With `trace_every == 0` the branch is never entered
  and the arrays are empty; the untraced path costs one predictable branch per sub-step (bench
  `docs/bench/`, Session V.1 row: within noise of `b9597a3`). Works under
  `NUMBA_DISABLE_JIT=1` (plain Python; the one extra boolean test per sub-step).
* **One-off fields** make a `Trace` self-describing: `solver`, `trace_every`, `dt`, `step_qty`,
  `out_max`, `params` (`SdofParams`), `inputs` (the case inputs as received, `force_history`
  as the 2-D array, the JC flags), and for JC `pipe_seg_qty`, `pivot_seg_qty`, `ext_qty`,
  `n_cells`, `cell_kind` (0 = A node, 1 = B cell), `cell_position` (`j · c · dt` m from the
  first A node; a cell is `2 c dt` long and the column runs `extQTY` end cells, the leg to
  the pivot, the span, the other leg, `extQTY` end cells, `moc.grid_size`) and
  `moving_fraction` (`frac_a` / `frac_b` interleaved, the weights `moc.step` applies to
  `a dt`). A JC call that takes the short-pipe fallback returns a lumped trace (`solver ==
  "peak_response"`, JC fields None).
* **Numba cache.** `_trace_frame` and the `trace.F_* / I_*` constants are compiled into
  `_integrate_kernel`; after editing `trace.py` run `make clean-cache` (the `cache=True`
  staleness note above applies).

## Lint policy

`pyproject.toml` selects `E, F, W, I, B, UP, NPY, SIM, C4`. `SIM` and `C4` were added in
Stage 4.4, when the Stage 1 "no simplification" rule ended; the two frozen modules
`legacy_port.py` and `vba_compat.py` are exempt from them (per-file ignores) so the literal
transcription stays as written. Any lint-driven edit to a live module must keep the
differential suite bitwise; a change that cannot is recorded in DEVIATIONS.md instead.
