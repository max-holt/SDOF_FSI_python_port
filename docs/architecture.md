# Architecture — Stage 4 layout, as built (Stage 5: compiled kernels)

**Names (review session R.3).** The code names follow `docs/nomenclature.md`, which maps each
to its VBA name. Parts of this document predate the renames; where it quotes a kernel
parameter (`fric_acc`, `ratio2`, `tot_ind`, `out_max`, `p_a`, ...) or an exported key, that
name is still current: those change with the parameter objects (plan group 3) and at the
public API session.

One line per module: what it is responsible for, and what it must not know about.
The structure was fixed at the start of Stage 4 and filled in module by module (4.1:
`structure`, `loads`, `coupling` (then `NoCoupling` only), `response` lumped path; 4.2: `moc`, the
JC coupling; 4.3: `pressure`, `_vba_semantics` (both removed in review session R.1b with the unused `GetPressureResponse` port); 4.4: hygiene, no behaviour change; 5: the three
inner loops compiled with Numba, see "Stage 5 — compiled kernels"; Session V.1: the
sub-step trace for visualisation, see "Session V.1 — the trace"; W.1 / W.2: the data files and
the viewer; 5b: `histories`; F-4 / F-4b: the corrected moving-fraction profile). This document
describes the code as it stands at the handover (Session H.1). `legacy_port.py` stays the reference
implementation until Stage 6 and every new module is proved against it by
`tests/test_differential.py`. Every public function and dataclass of the live modules
carries a numpy-style docstring with the unit of each physical argument and return and the
DEVIATIONS id of each VBA quirk it preserves.

```
src/surge_sdof/
  vba_compat.py        # frozen (Stage 1 VBA runtime semantics; no edits)
  legacy_port.py       # frozen; reference implementation until Stage 6
  moc.py               # 1-D MoC fluid column: state arrays, half-step update, boundary conditions
  structure.py         # SDOF: portal-frame proxy, restoring force with gap, Coulomb friction, time-step kernel
  coupling.py          # coupling force from the moc state (moving fractions, low-pass dF)
  loads.py             # elbow-to-elbow unbalance force from a history: transit delay, phase scheduling
  response.py          # public API: peak_response(...) and peak_response_jc(...); returns a dataclass; one private _integrate loop
  trace.py             # Session V.1: the Trace dataclass of a traced run (trace_every > 0) and its allocation / assembly helpers
  viz/geometry.py      # Session W.1: the expansion-loop layout of a Trace (LoopLayout, loop_layout, lumped_grid, layout_from_trace); numpy only
  export.py            # Session W.1: the trace / sweep data documents for the JS viewer (docs/data_format.md) and their JSON / gzip writer; tools/export.py drives it
```

| module | responsibility | must not know about |
|---|---|---|
| `vba_compat.py` | VBA runtime semantics (`CLng`, `floor`, `modDbl`, `sign`, `min/maxUnsigned`, padded 1-based arrays). **Frozen**: no edits; new modules may import from it. | any solver quantity |
| `legacy_port.py` | Line-for-line Stage 1 transcription of the VBA; the oracle for the differential tests. Frozen (no edits, no imports *from* it in new modules except in tests). | the new modules |
| `structure.py` | The SDOF pipe proxy: `solve_portal_height` (seed + 11 `solve_quartic` passes), `lumped_params` (mass, stiffness, damping, `fricAcc`), `effective_displacement(x, support_gap, closed_gap_stiffness_ratio)` (bilinear support gap), and `step_scalars(x, v, a, f_applied, mass, stiffness, damping, fric_acc, gap, ratio2, dt)` — exactly the VBA update (explicit `aNew` from the old state, trapezoidal `v` and `x`, stick/slip Coulomb friction) on Python floats with the clamp/sign ladders inlined, compiled with `numba.njit(cache=True)` (Stage 5). One kernel, called from one loop. (`restoring_force`, `step` and `State`, wrappers only the tests called, were removed in review session R.3.) | where `f_applied` comes from (force histories, transit delay, fluid coupling), sample/phase bookkeeping, max trackers, output types |
| `loads.py` | The elbow-to-elbow unbalance force `forceA − forceB` from a force history: `transit_delay` (`unballanceStepQTY`), the `kOverlap` sub-sample offset and the three-phase scheduling (delay phase with `forceA` held, ramp phase with both forces interpolated, no force in free decay), walked column-major over 2-D histories exactly as the VBA. Yields one list of per-sub-step values per sample. The index walk is one private per-sample `_schedule` generator yielding `_TransitSample` / `_ForcedSample` records (the column-major step with column wrap is `_next_position`, review session R.4); `unbalance_force` (inner `k` loops unchanged) and `elbow_forces` (the two forces apart, with the sample's phase `PHASE_TRANSIT` / `PHASE_FORCED`, defined here and re-exported by `trace` with `PHASE_FREE_DECAY`) consume it. Their inner loops stay separate: deriving the unbalance from the elbow-force pair cost about 20 % on the compiled lumped path and was reverted (R.4, plan 2.15). | the structure state, stiffness or damping, fluid coupling, what the caller does with each sample (result histories, free decay) |
| `coupling.py` | The force the fluid column exerts on the structure. `fluid_column(grid, fluid, vav_denominator, fraction_profile)` builds the `moc.FluidColumn` of a JC run at rest (the column arrays, the tabulated moving fractions, the grid and fluid constants; it replaced the `JunctionCoupling` class in review session R.6, ruling 49); the lumped solver passes `moc.empty_column()`. `_integrate` starts the low-pass `dF` at 0.0; the compiled loop feeds the previous sub-step's acceleration (`a * dt`) into the moving cells, advances the column one sub-step with `moc.step` on the half-grid `step_index % 2` selects and keeps `dF` as a float. The parity source (running counter, F-2, or the VBA per-phase index) is the loop's choice. (The `Coupling` protocol, `NoCoupling`, `coupling_force` and `column()`, which only the tests called, were removed in review session R.3.) | the force history / unbalance schedule, output types, the SDOF update itself, phase boundaries |
| `moc.py` | The 1-D MoC fluid column (Stage 4.2): grid construction (`grid_size`: `pipeSegQTY`, `pivotSegQTY`, `extQTY`; `is_short_pipe`), the moving-fraction profiles tabulated once per grid (`moving_fractions`), the four contiguous state arrays (`column_at_rest`: `p_a`, `v_a` on the A nodes `0..N`, `p_b`, `v_b` on the B cells `0..N-1`), and one kernel `step(even, a_dt, arrays…, scalars…, d_f) -> d_f` with scalar loop bodies: the even/odd half-step update, the decaying end-node boundary (`dacayFactor`), the mean-velocity (`vAv`) subtraction and the low-pass `dF`. No per-cell helper calls, no Python objects: Stage 5 compiles it whole with `numba.njit(cache=True)`, body unchanged. The VBA's dead `useUndamped` branch (`Const useUndamped = False`, the AFT infinite-pipe boundary, lines 803-818) is **not ported**; only the live decaying boundary is. `mean_velocity_divisor(N, "legacy" \| "fixed")` selects `2N - 1` (VBA, D-17) or `2N + 1` (approved fix F-1). `moving_fractions(N, pivot, "fixed" \| "legacy")` tabulates the lead author's corrected profiles (approved fix F-4, `legacy/vba/interpFraction_fix_2026-10-26.bas`, with the F-4b outlet correction of `interpFraction_fix_2026-10-27.bas`, transcribed as `moving_fraction_a_fixed` / `moving_fraction_b_fixed`; default; A mirrors about the column centre `N / 2`, B about `(N - 1) / 2`) or the VBA originals (D-4); on the fixed profile `pivotSegQTY <= extQTY` is refused with `ValueError` (an added guard). Driven by the JC coupling. | the structure proxy, the force history, output types, the sub-step counter (it is told the parity) |
| `response.py` | Public API. `peak_response(...)` (lumped) and `peak_response_jc(...)` (Stage 4.2) each do their own set-up and pass a fluid column to one shared integration loop `_integrate` (Stage 5: the Python orchestrator of the compiled `_integrate_kernel`: sample loop, max trackers, result history through `_record_sample`, free-decay phase with the `_free_decay_product` overflow check; the static-equivalent force and the `PeakResponse` are built in Python). Returns a `PeakResponse` dataclass with 0-based histories (no VBA pad). The two set-ups are *not* merged into one function with flags. The JC set-up is `structure.jc_params` (rigid mass; stiffness, damping, `fricAcc` on the total mass, VBA 726-729), `moc.end_pressure_decay_factor`, `moc.grid_size` and the short-pipe fallback to `peak_response`; `rhoC = 0` is rejected at the set-up, by the first statement of `coupling.fluid_column` (D-9; `np.errstate` has no effect inside the compiled kernel). `peak_response_jc` carries the approved-fix flags `vav_denominator` ("legacy" \| "fixed", F-1) and `parity` ("per_phase" \| "running", F-2); the loop turns `parity` into the `step_index` it passes to the coupling (`n + off`, `off` fixed per sample). Session V.1: both solvers take `trace_every: int = 0`; with `k > 0` the kernel records every `k`-th sub-step into preallocated arrays and the result carries `PeakResponse.trace`. The entry points pass `_integrate` one optional `_TraceRequest` (stride, solver name, inputs, celerity, the `elbow_forces` generator); the kernel still takes the stride as an int (0 untraced). | the internals of `step`, the MoC arrays, how `loads` interpolates |
| `trace.py` | Session V.1. `Trace`, the frozen dataclass of a traced run (per-frame arrays `t, sub_step, sample, phase, x, v, a, f_a, f_b, f_unbalance, f_friction, stick, d_f`; JC only `p_cells`, `v_cells` and the column geometry; one-off `solver`, `trace_every`, `dt`, `step_qty`, `out_max`, `params`, `inputs`), the frame-array column constants the kernel writes (`F_*`, `I_*`), `capacity` (frames to allocate: the forced sub-steps plus free decay up to the history window), `check_memory` (`MAX_TRACE_VALUES`, `ValueError` naming the smallest stride that fits), `allocate`, `interleave` (the staggered grid as `A0 B0 A1 … AN`) and `build` (slices and copies the kernel arrays into a `Trace`). | the solver loop, `loads`, `moc.step` (it only lays out what the kernel copied) |
| `viz/geometry.py` | Session W.1 (code of V.2b / V.2c, moved). `LoopLayout`, `_segments`, `loop_layout`, `lumped_grid`, `layout_from_trace`: the expansion-loop layout of a trace's interleaved column (the rules under "The picture", pinned by `tests/test_geometry.py`), written into every trace file by the exporter; numpy only, no plotly. The plotly-python animation that once consumed it (`viz/animate.py`) was retired in Session H.1. | the solvers, plotly, the file format |
| `export.py` | Session W.1. `to_trace_dict(result, case_id)` (the `trace` document: meta with inputs as given, the resolved `SdofParams` + run scalars, the five maxima, provenance; the `LoopLayout` as `geometry`; the thirteen frame columns with the synthetic rest frame first, `sub_step = sample = -1`; JC `p` / `v` as row-major `{shape, data}` blocks), `to_sweep_dict(rows, ...)` (the `sweep` document: thirty fixed columns, regen template, reference block), `dumps` / `write_json` / `read_json` (compact JSON, floats via `repr`, `allow_nan=False`, UTF-8, LF, gzip by suffix). `docs/data_format.md` is the contract and `tests/test_export.py` parses it. Also `is_capped` (the run decayed past the traced window) and the rest-frame phase, moved here from the retired animation. Reads a `PeakResponse`; never runs a solver (`tools/export.py` does). | the solvers, the viewer, plotly |

**Named constants (review session R.4).** The literals with a meaning are module constants,
each with its meaning, unit and VBA source: `structure.PERCENT` (`/ 100` of the damping
percent), `GRAVITY` (9.81 m/s²), `FRICTION_DEAD_ZONE` (the `sign(v, 0.000001)` of D-20),
`NEWTON_RELATIVE_TOLERANCE`, `NEWTON_RELAXATION`, `NEWTON_ITERATION_LIMIT` (`solvePoly`) and
`END_FIXITY_LAST_PASS` (the portal-height refinement loop); `response.FREE_DECAY_THRESHOLD`
(0.01 m², D-21); `moc.LEGACY_B_INACTIVE_START_CELL_COUNT` (the `n < 3` of D-4);
`loads.PHASE_TRANSIT` / `PHASE_FORCED`. Each is the same literal as before, of the same type,
used where the literal stood. Pure-number coefficients of formulas (`4 / 3`, `12`, the
friction `0.5`) stay inline with derivation comments (`docs/style.md` §6).

## Data flow for one sub-step

**Lumped path** (`peak_response`). Set-up once per run: `loads.as_history_2d` shapes the
history, `loads.transit_delay` gives `unballanceStepQTY` (samples) and with it `outMax`,
`structure.solve_portal_height` and `structure.lumped_params` give the `SdofParams`
(mass kg, stiffness N/m, damping N·s/m, `friction_velocity_step` m/s, `support_gap` m,
`closed_gap_stiffness_ratio`), and
`loads.unbalance_force` is created as a generator. Per sample, `_integrate` pulls the next
`list` of per-sub-step `forceA − forceB` values (N) from the generator. Per sub-step it adds
`0.0` (no coupling) to the sub-step's unbalance value `f` and passes the sum as `f_applied`
to `structure.step_scalars(x, v, a, f_applied, *params, dt)`, which computes `aNew` from the *old* `(x, v)`, the trapezoidal `v_new` with the
stick/slip friction ladder, and the trapezoidal `x`. `_integrate` then updates the four max
trackers (`|a|`, `|v|`, `|x|`, `|f|`) and increments the running counter `n`. At the end of
the sample `_record_sample` stores `x`, `v` or `a` in the 0-based history for `output_type` 1-3.
When the generator is exhausted (phase 1 delay and phase 2 ramp both done) the free-decay
phase repeats the same sub-step with the coupling force alone as `f_applied`, `stepQTY`
sub-steps per sample, while `x * xZero > FREE_DECAY_THRESHOLD` (0.01 m², D-21). Finally the static-equivalent force is
`|structure.effective_displacement(xMax)| * stiffness` and the `PeakResponse` is built.

**JC path** (`peak_response_jc`). The same loop and the same `structure.step_scalars`; the set-up adds
`structure.jc_params` (rigid mass), `moc.end_pressure_decay_factor`, `moc.grid_size` (and the short-pipe
fallback, which returns `peak_response` outright), and `coupling.fluid_column`, whose
`FluidColumn` holds the four column arrays (`p_a`, `v_a` on the A nodes `0..N`, `p_b`, `v_b`
on the B cells `0..N-1`; Pa and m/s) and the tabulated moving fractions; the loop carries
`dF`, from 0.0. Per sub-step, before
`structure.step_scalars`, the loop takes the previous sub-step's acceleration `a`, forms
`a * dt` (m/s) and calls `moc.step(even=step_index % 2 == 0, …)` on the column's arrays,
which updates one half-grid in place. Even: the mean velocity `vAv` over the `2N + 1`
velocities divided by `vav_div` (2N+1 by default, 2N−1 with `vav_denominator="legacy"`,
D-17), the decaying end nodes (`p_b / dacayFactor`), the interior A nodes from the two
neighbouring B characteristics, then every B velocity gains `a dt · frac_b[n] − vAv`; `dF`
is formed from the A pressures on either side of the two pivots. Odd: the B cells from the
two neighbouring A characteristics, then the interior A velocities gain `a dt · frac_a[n]`;
`dF` from the B pressures at the pivots. In both, `dF ← 0.25 dF + 0.75 · fluidArea · Δp`
(N) is returned as a Python float, added to the sub-step's `f`, and `structure.step_scalars` runs
with the JC `SdofParams`. `step_index` is the running counter `n` (`parity="running"`, F-2)
or the VBA per-phase index `n + off` (`parity="per_phase"`, D-19); the coupling only reads
its parity. The loop runs under `np.errstate(raise)` so a zero `rhoC` or a fluid overflow
raises mid-run (D-9 as a raise).

## Interfaces

Interfaces fixed in Stage 4.1 so that later sessions write against them:

* The state `(x, v, a)` is a tuple of Python floats; `structure.SdofParams` named tuple
  `(mass, stiffness, damping, friction_velocity_step, support_gap, closed_gap_stiffness_ratio)`;
  `structure.step_scalars(x, v, a, f_applied, sdof_params, dt) -> (x, v, a)` (Stage 5,
  compiled; it takes `SdofParams` whole since review session R.5). `structure.State` and the wrapper `structure.step(state, f_applied, params, dt)`
  were removed in review session R.3.
* `loads.unbalance_force(history, sample_freq, physical_length, celerity, step_qty)` is a
  generator: one `list[float]` per sample (the per-sub-step `forceA − forceB` values, in
  order, the last delay-phase sample truncated at the VBA `Exit For`).
* `step_index`, whose parity selects the MoC half-grid, is a running sub-step counter over
  the whole run (0 at the first sub-step), or, with `peak_response_jc(parity="per_phase")`,
  the VBA per-phase index (D-19; Stage 4.2). `response._integrate` takes the
  `moc.FluidColumn` (`coupling.fluid_column`'s, or `moc.empty_column()`) and passes it to
  the compiled loop; fluid coupling on or off is the column's plain
  flag `is_fluid_coupled` (review session R.5; it was a kind code 1 / 0). (The
  `Coupling.coupling_force` protocol and `NoCoupling` were removed in review session R.3.)
* `moc.FluidColumn` (review session R.5): the column's four state arrays (`pressure_a`,
  `velocity_a`, `pressure_b`, `velocity_b`, updated in place), the two moving-fraction
  arrays, `column_cell_count`, `end_to_elbow_cell_count`, `rho_c`,
  `end_pressure_decay_factor`, `mean_velocity_divisor`, `flow_area` and `is_fluid_coupled`.
  `moc.grid_size` returns a `moc.ColumnGrid(column_cell_count, end_to_elbow_cell_count)`.
* `coupling.fluid_column(grid, fluid, vav_denominator="fixed", fraction_profile="fixed") ->
  FluidColumn` with `fluid` a `coupling.FluidConstants(characteristic_impedance, flow_area,
  end_pressure_decay_factor)` (review session R.6, ruling 49: it replaced the
  `JunctionCoupling` class of Stage 4.2, which held only the column, `dt` and `d_f`).
* `moc.step(is_even_substep, structure_velocity_step, column, junction_force) ->
  junction_force` (Stage 4.2; the column grouped in review session R.5): one MoC sub-step in
  place on the column's four arrays; `is_even_substep` is the half-grid to update,
  `structure_velocity_step` the structure acceleration times `dt`.
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
* `response.PeakResponse` fields: `max_static_equivalent_force`, `max_displacement`,
  `max_velocity`, `max_acceleration`, `max_applied_force`, `history` (None for
  `output_type = 0`; otherwise a 0-based array of length `outMax * 2`, element `t − 1` =
  state at the end of sample `t`), `output_type`, `free_decay_samples`, and (Session V.1,
  trailing, default None) `trace`.
* Private, not an interface (parameter objects since review session R.5,
  `docs/review/parameter_objects.md`): `response._integrate(unbalance_force_samples,
  sdof_params, settings, column, trace_request)` (the Python orchestrator;
  `settings` is a `response.RunSettings(substep_duration, substep_count,
  nominal_forced_sample_count, output_type, is_per_phase_parity)` built by the entry
  points, `trace_request` a `trace.TraceRequest` or `None`),
  `response._integrate_kernel(schedule, sdof_params, settings, response_history, column,
  junction_force, buffers) -> _KernelResult` (the compiled loop; `schedule` is a
  `response._ForceSchedule` of the per-sub-step forces, `buffers` a `trace.TraceBuffers`
  of the four frame buffers and the stride; `_KernelResult` holds the four maxima, the final
  state, `sample_number`, `forced_sample_count`, `junction_force` and `frame_count`),
  `response._trace_frame(buffers, frame_index, values, column)` (the compiled per-frame
  write; `values` a `response._Frame`), `response._record_sample(history, output_type,
  index, x, v, a)` (the per-sample history write, called once per sample),
  `response._free_decay_product(x, x_zero)` and `trace.build_trace(request, settings,
  params, buffers, n_frames, column)`.

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
* `0.0 + F` / `0.0 − R` with no coupling differ from `F` / `−R` only in the sign of an
  exact zero.
* Stage 4.4 (hygiene): the inlined `max(0, |x| − gap)` test is written `excess < 0` instead
  of the VBA-shaped `0 > excess` (ruff SIM300); the two are the same comparison for every
  double, NaN included (both false). The duplicated per-sample history write became
  `_record_sample`, one assignment of the same float. The differential suite stayed bitwise.

## Stage 5 — compiled kernels

Three functions carry `@numba.njit(cache=True)`: `structure.step_scalars`, `moc.step` and
`response._integrate_kernel`. No `fastmath`, never object-mode `@jit`. Their bodies are
the Stage 4 code; what changed is the calling convention:

* **Signatures take module-level NamedTuples of floats, ints, bools and numpy arrays**
  (review session R.5; Stage 5 passed every field as its own argument, 36 of them).
  `response._integrate` (plain Python) builds them once per run: the `loads.unbalance_force`
  per-sample lists are concatenated into one flat float64 array plus an int64 array of
  sample starts (sample `s` is `unbalance_force_by_substep[sample_start[s]:sample_start[s +
  1]]`, so the truncated last delay-phase sample keeps its length), held with the elbow
  forces of a traced run in a `_ForceSchedule`; `SdofParams` and the entry points'
  `RunSettings` pass whole; the coupling's `FluidColumn` passes whole, or for no coupling
  `moc.empty_column()`, the same type with empty arrays and placeholder values the kernel
  never reads, so the kernel compiles once for both solvers; the trace buffers pass as one
  `TraceBuffers`. Each compiled function unpacks a tuple into locals once at its top; the
  kernel passes the column one call deep per sub-step (to `moc.step`, and to `_trace_frame`
  on a traced sub-step) and nothing deeper (rule K-1, `docs/review/plan.md` group 3). The
  junction force is an argument and a return value, not a field (it evolves). The kernel
  returns a `_KernelResult`; `_integrate` (the column's arrays were updated in place)
  casts to Python floats and builds the `PeakResponse`.
  (The Python-level `Coupling.coupling_force` interface that stayed for the tests was
  removed in review session R.3.)
* **Both modes, one source.** With `NUMBA_DISABLE_JIT=1` `numba.njit` returns the
  undecorated function and the same code runs as Python. `float(unbalance_force_by_substep[i])` and
  `float(moc.step(...))` in the kernel are no-ops under Numba and keep the SDOF state on
  Python floats in Python mode, so the Stage 4 overflow semantics (D-23) are unchanged
  there. `make test-both` runs the fast suite in both modes after wiping the on-disk Numba
  cache, because `cache=True` does not notice when a callee in another module changed
  (`moc.step` or `step_scalars` inside `_integrate_kernel`).
* **Error semantics inside the kernel.** `numpy.errstate` has no effect in compiled code.
  `rhoC = 0` is therefore rejected once at the `peak_response_jc` set-up
  (`coupling.fluid_column`) with
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
* **Not compiled.** The set-up (`solve_portal_height`,
  `lumped_params` / `jc_params`, `grid_size`, `moving_fractions`, `end_pressure_decay_factor`) and
  `loads.unbalance_force`, which is now the dominant cost of a compiled lumped run (the
  generator is Python; Stage 5b candidate).

## The picture — the geometry and scaling rules the viewer draws

The two-panel animation of a traced run was designed in Sessions V.2–V.2f as a plotly-python
figure (`viz/animate.py`, retired in Session H.1) against the lead author's requirements (22
Oct 2026) and review rounds (23 and 25 Oct); the single-file viewer (`docs/viewer/`, Session
W.2) draws the same picture from the exported files by the same rules. Those rules are:

* **Geometry** (`viz/geometry.py`, written into every trace file as `geometry`). The column is
  an expansion loop: inlet pipe, leg down, run, return leg up, outlet pipe. Cells are mapped by
  their moving fraction (`_segments`): the fraction-1 block is the run (`y = 0`, `x = 0 ..
  run_length`); the last fraction-0 cell before it and the first after it are the upper elbows
  (F-4 profile: both ramps start at exactly 0 at B(3) / A(3), legs of `2 pivot - 10`
  interleaved cells each; legacy profile: the D-4 `n < 3` cell B(3) with fraction `1 / (pivot
  - 4)^2` is a moving cell on the horizontal inlet and the inlet leg is one cell longer); the
  cells before / after them are the horizontal inlet / outlet at the pipe height, extending
  left of leg 1 and right of leg 2; the cells between are the vertical legs. Spacing is uniform
  by `cell_position` along the whole centreline and the four elbows are sharp corners at the
  elbow cells (the model has no bends), so every inlet / outlet cell is at its pipe height,
  every run cell at `y = 0`, the legs vertical at `x = 0` and `x = run_length`, consecutive
  cells exactly one spacing apart (pinned by `tests/test_geometry.py`). The pipe height is the
  centreline length between the elbow cells; it differs from `h`
  (`structure.solve_portal_height`, printed in the panel). With the F-4b profile (the default)
  the two legs are equal and the fixed blocks at both ends are equal; with the legacy profile
  they differed by one cell because the VBA B profile ramps one cell longer on the inlet side
  (Example JC: 7.5 m and 6.0 m for `h = 7.69 m`; row 96: 4.03 m and 4.00 m for `h = 4.05 m`).
  A lumped run uses the layout of the grid it would have (`moc.grid_size`,
  `moc.moving_fractions` with the default profile; a `pivotSegQTY = 4` grid, refused by both
  profiles, gets the legacy B profile with the `n < extQTY` test, display only).
* **Frames.** Frame 0 is synthetic (`t = 0`, `x = 0`, the column at rest, no forces) so
  playback starts from rest; the V.1 convention (frame `i` = end of sub-step `i k`, so the first
  traced frame is at `t = dt`) is untouched. The viewer shows every `stride`-th frame with the
  last one always included; the automatic stride keeps at most 400 frames
  (`ceil((n_frames - 1) / 398)`), and `t_start` / `t_end` play a time window only while Panel 2
  keeps the whole run and shades the window: a 20 s run at 3 Hz cannot be followed at 400
  frames (0.05 s a frame, 0.15 of a period, several wave transits), so row 96 is watched in a
  window of about 1.5 s around its peak at stride 1 (24 ms a frame). Every animated frame
  updates trace data only (the circles, the cursor and a status text with the frame time and
  phase in Panel 1), never the layout, and lists all six traces (the static ones with an empty
  update) under `redraw: false`: a per-frame layout change forces a full redraw that flickers
  and drops the right-axis trace at speed, and under `redraw: false` plotly.js rebuilds each
  subplot's layers from the frame's listed traces and removes the rest, which emptied the
  friction subplot on the first frame until every trace was listed (V.2e diagnosis in
  `docs/viz/diagnosis.md`, fixed in V.2f). 1x playback is 40 ms a shown frame. The header
  prints `trace_every`, the stride, the frame count, the nominal circle size and "capped" when
  the run decayed past the traced window (`export.is_capped`: `forced_samples +
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
  fraction, and `p` / `v` for JC.
* **Panel 2.** `f_unbalance = F_A(t) - F_B(t - L/c)` on the left axis over `f_friction`
  (`Trace.f_friction`, the owner's definition) on the right, the friction drawn first, 1.5 px
  and translucent so it sits under the load line, both ranges symmetric (`±1.06 max|f|`) so
  the zero lines coincide, legend labels naming the axis; over the whole trace plus the
  `t = 0` row; the phase bands and the cursor on the primary axis (a band is labelled when it
  spans 6 % of the axis, the current phase is always in the status text), the time of peak
  `|x|` marked.
* **The built-in step** (`tools/cases.py`, `tools/export.py trace --step`). Zero force for
  `--lead-in` (0.1 s), then `--amplitude` bar on the fluid area (`--size` mm internal diameter
  or `--area` m²) for `--duration`; `docs/viz/data/example_jc_step.json` is this step with the
  Example-sheet parameters (1600 bar on 0.05 m² = 8 MN, the sheet's first level).

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
  the history's own cap: free decay is traced while `totInd <= outMax · 2` (the `_record_sample`
  guard), later sub-steps are integrated but not traced. `trace.frame_capacity` allocates once for
  `forced sub-steps + max(0, outMax · 2 − forced samples) · stepQTY` sub-steps at the stride; the
  kernel returns the frames written and `trace.build_trace` slices. `trace.check_memory` raises
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

## Session W.1 — the data files

`surge_sdof.export` writes what the single-file JS viewer (Session W.2) loads; the contract is
`docs/data_format.md` and `tests/test_export.py` parses its key tables, so the document and the
code cannot drift apart silently. Design points:

* **Two kinds.** `trace` (one traced run: `meta`, `geometry`, `frames`, JC `cells`) and `sweep`
  (Session 5b rows as columns plus a `reference` block with the Excel values of the three
  Example-sheet cases and the three JC golden rows, so the viewer can self-check on open). Both
  carry `kind` and `schema_version` (1).
* **Column-wise, repr floats, no NaN.** Every per-frame or per-row quantity is one flat array;
  2-D data is `{"shape", "data"}` row-major; floats are `float.__repr__` (the json module's
  default, shortest round-trip); `allow_nan=False` makes a non-finite value an error at write
  time, so a missing value is `null` and a failed sweep row has its message in `error`.
* **Whole run, rest frame first.** A trace file is the whole run at the solver's `trace_every`
  (the viewer windows live; `--t-start` / `--t-end` do not exist here) and frame 0 is the
  synthetic rest frame the animation also prepends (`t = 0`, `sub_step = sample = -1` so `t =
  (sub_step + 1) dt` holds everywhere, phase as `export._synthetic_phase`, zeros, a zero
  column); frame `i >= 1` is traced frame `i - 1`.
* **Geometry from one place.** The expansion-loop layout lives in `viz/geometry.py` (moved
  there from the animation in W.1); the file carries the `LoopLayout` (positions, kinds,
  fractions, segment indices, nominal circle centres, the two pipe heights, run length) so the
  viewer draws the picture without rebuilding it, and a lumped run gets the grid it would have.
* **Size.** About 20 bytes a float: row 96's 1333 cells cost 53 KB a frame, so `tools/export.py`
  picks the default stride as the 2000-frame stride (`tools/cases.TRACE_FRAMES`) or the coarser
  one that keeps the estimated JSON under 45 MB (`JSON_BUDGET_MB`, forced phases only); row 96 lands
  at 832 frames (24 ms a frame), 46.9 MB of JSON, 20.6 MB gzipped. `docs/data_format.md` names
  the binary variant (same header + float64 blobs) as the upgrade path.
* **Case loading.** `tools/cases.py` holds the `--golden` / `--step` case loading of
  `tools/export.py` (once shared with the retired `tools/animate.py`), plus the fixture readers
  for the sweep reference block and the `cases.csv` → sweep-row mapping.

## Session W.2 — the viewer

`docs/viewer/viewer.html` is the single-file JS viewer that plays a `trace` data file (W.1) as
the two-panel animation of "The picture" above, with the playback decisions (frame selection,
speed, window) made live in the page. `docs/viewer/README.md` is the user guide.
Design points:

* **One file, no requests.** plotly.js (4.1.1, the full bundle: the installed package ships no
  partial one; `tools/build_viewer.py --plotly` swaps a basic bundle in when one is available
  offline) and pako's inflate-only build (1.0.11, vendored in `tools/viewer/`, pinned by digest)
  are inlined by `tools/build_viewer.py` from `docs/viewer/viewer.src.html`, the hand-written
  source; a content-security policy in the page (`default-src 'none'`) refuses every fetch, so
  disk, SharePoint and a bucket URL behave identically. `tests/test_viewer.py` rebuilds the page
  and asserts byte equality with the committed one, and fails on any request beyond the page.
* **Loader.** File picker or drop; gzip by the magic bytes; `kind` / `schema_version` checked
  first with a readable refusal; the thirteen frame columns, the geometry arrays and the JC
  blocks checked for length. The JC blocks become `Float64Array`s (row `i` is a zero-copy
  `subarray`), the JSON arrays released.
* **Same picture.** The figure is the six traces of "The picture" in the order of the retired
  plotly figure (centreline 0, cells 1, friction 2 on the overlaying right axis, unbalance 3,
  cursor 4, status 5), the same 1200 x 900 layout, margins and subplot domains (0.62 / 0.38,
  spacing 0.14), the same scalings over the whole run (`exaggeration = 0.1 run / max|x|`, `k_p` for a 2x largest circle,
  floor 0.15x, `±max|v|`, nominal size `clip(1800 / n, 5, 12)` capped at 0.8 of the on-screen
  spacing and never below 3 px) and the same phase bands, peak line and window shade. The
  `plotly_white` look is reproduced as a `layout.template` (plotly.js has no named templates).
* **Playback mechanism (the V.2e lesson).** `newPlot` runs once per file. A frame is one
  `Plotly.animate` call with an inline frame that updates the cells (x, marker size and colour,
  customdata), the cursor x and the status text and lists all six traces, the static three with
  `{}`, under `redraw: false`, `mode: 'immediate'`, no transition: exactly the V.2f frame shape
  ("The picture", Frames), because under `redraw: false` plotly.js rebuilds each subplot's
  module layers from the listed traces and drops the rest. The static traces are never restyled during playback and the
  layout never touched; the window shade is one `relayout` per window change and the colour
  override one `restyle` of the cells' colour axis, both outside the loop. The loop is a
  `requestAnimationFrame` callback that computes the frame due from the elapsed wall time
  (`40 ms / speed` a shown frame, `stride` frames each, elapsed clamped at zero because the rAF
  timestamp can predate the `performance.now()` of the play press) and waits for the previous
  animate promise before issuing the next, so a slow render skips frames rather than slowing the
  clock and an interrupted animate never rejects unhandled.
* **Controls and settings.** Play / pause, typed speed and 0.25x–4x buttons, stride (auto =
  `ceil((n_frames - 1) / 398)`, at most 400 frames), `t_start` / `t_end` (Panel
  2 keeps the whole run), exaggeration and colour range overrides, jump to peak, a frame slider.
  Speed and the overrides persist in `localStorage` behind try/catch; the window is per file.
* **Test hook.** `window.viewer` exposes the playback state, the scalings and `show` / `play` /
  `stop` for `tests/test_viewer.py`; the tests otherwise drive the page through its controls.

## Lint policy

`pyproject.toml` selects `E, F, W, I, B, UP, NPY, SIM, C4`. `SIM` and `C4` were added in
Stage 4.4, when the Stage 1 "no simplification" rule ended; the two frozen modules
`legacy_port.py` and `vba_compat.py` are exempt from them (per-file ignores) so the literal
transcription stays as written. Any lint-driven edit to a live module must keep the
differential suite bitwise; a change that cannot is recorded in DEVIATIONS.md instead.
