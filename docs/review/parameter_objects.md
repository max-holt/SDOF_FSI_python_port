# Parameter objects — proposal (plan group 3)

Session R.5, 24 Nov 2026. Written before any group is built, as `docs/review/plan.md`
(group 3) and charter rulings 10 and 46 ask. **Status: proposed, not approved.** Plan 3.1
is made (`structure.step_scalars` takes `SdofParams`, commit `2f1dce2`) as the proof on one
function; nothing below is.

## Rules the proposal follows

* `docs/style.md` §3 and §4: at most 6 parameters (keyword-only ones count, ruling 17);
  each object named for the thing it describes; compiled functions take positional
  module-level NamedTuples; arrays inside are updated in place; scalars that evolve (the
  junction force) are passed in and returned. No jitclass, StructRef or typed containers.
* Numba rule K-1 (plan group 3): a tuple is unpacked into locals once at the top of the
  function that receives it, or passed at most one call deep per substep. Every object
  below is built in Python once per run and passed to the kernel; the kernel passes the
  fluid column to `moc.step` (every substep) and to `_trace_frame` (traced substeps), one
  call deep, and nothing further.
* One type per object for both solvers: the lumped run passes the same NamedTuple types
  as the junction-coupling run (empty arrays, today's literal values and types), so the
  kernel compiles once per type.
* The kernel-signature names are applied as the field names, from `docs/nomenclature.md`
  (ruling 21). The objects' bodies unpack into today's local names first; one R0 commit per
  function then renames the locals to the nomenclature, so each name changes once.
* No arithmetic moves (charter rule 2): fields are unpacked into locals; the expressions
  that use them stay as they are.

## The objects

### 1. `moc.FluidColumn` — the MoC fluid column (plan 3.2, with 2.2)

| field | today | type |
|---|---|---|
| `pressure_a`, `velocity_a` | `p_a`, `v_a` | float64 arrays `N + 1`, updated in place |
| `pressure_b`, `velocity_b` | `p_b`, `v_b` | float64 arrays `N`, updated in place |
| `moving_fraction_a`, `moving_fraction_b` | `frac_a`, `frac_b` | float64 arrays `N + 1`, `N` |
| `column_cell_count` | `n_seg` | int |
| `end_to_elbow_cell_count` | `pivot` | int |
| `rho_c` | `rho_c` | float, Pa·s/m (kernel symbol) |
| `end_pressure_decay_factor` | `decay` | float |
| `mean_velocity_divisor` | `vav_div` | int |
| `flow_area` | `fluid_area` | float, m² |
| `is_fluid_coupled` | `kind` 0 / 1 (plan 2.2, its own commit after 3.2) | bool |

Built by `JunctionCoupling` (its attribute `column`, replacing the twelve column slots);
the lumped run passes `moc.empty_column()`, the named constructor with today's values
(six empty arrays, `0, 0, 0.0, 1.0, 1, 0.0`, and `False`). Taken by `moc.step`,
`response._integrate_kernel`, `response._trace_frame` and `trace.build_trace` (in place of
the coupling object, plan 3.6). The junction force is not a field: it evolves, and stays
an argument and a return value of `moc.step` and the kernel.

`moc.step(is_even_substep, structure_velocity_step, column, junction_force)`: 15 → 4.

The coupling flag sits on the column, not on the run settings, because plan 2.2 puts it
"with the column object of 3.2" and the column is what it describes: the empty column is
the uncoupled one, so the two cannot disagree.

### 2. `trace.TraceBuffers` — the trace frame buffers (plan 3.3)

| field | today | type |
|---|---|---|
| `frame_state` | `tr_f` | float64 `capacity × 8` |
| `frame_index_columns` | `tr_i` | int64 `capacity × 4` |
| `frame_pressure` | `tr_p` | float64 `capacity × grid points` |
| `frame_velocity` | `tr_v` | float64 `capacity × grid points` |
| `trace_every` | `trace_every` (kernel argument) | int, 0 when not tracing |

Returned by `trace.allocate_frames(frame_capacity, grid_point_count, trace_every)`; taken
by the kernel, `_trace_frame` and `trace.build_trace`. The four buffers come first, so
positional indexing (`allocate_frames(...)[2]`) still finds the same array.

The stride is a field here rather than of the run settings (the brief's suggestion)
because plan 2.11 made it part of the one optional trace request: the run settings are
built by the entry points, the buffers by `_integrate` from the request, so with the stride
on the settings two independent values would again have to agree (C-23).

### 3. `response._Frame` — one recorded substep (part of plan 3.3; C-15)

| field | today (`_trace_frame` parameter) |
|---|---|
| `substep_index` | `n` |
| `sample_index` | `sample` |
| `load_phase` | `phase` |
| `x`, `v`, `a` | the same (kernel symbols) |
| `elbow_a_force`, `elbow_b_force` | `f_a`, `f_b` |
| `unbalance_force` | `f_u` |
| `friction_force` | `f_fric` |
| `is_sticking` | `stick` |
| `junction_force` | `d_f` |

Built by the kernel only on a traced substep, from the same expressions as today (they
move verbatim into the constructor call). `_trace_frame(buffers, frame_index, frame,
column)`: 23 → 4. Plan 4.7 later splits the writer into a scalar-row and a column writer.

### 4. `response.RunSettings` — the run settings (plan 3.4)

| field | today | type |
|---|---|---|
| `substep_duration` | `dt` (kernel), `substep_duration` (`_integrate`) | float, s |
| `substep_count` | `step_qty` | int |
| `nominal_forced_sample_count` | `out_max` | int (the history holds twice this) |
| `output_type` | `output_type` | int; its form is the public API session's |
| `is_per_phase_parity` | `legacy_parity` | bool |

Built by the two entry points (from the values they already hold, so `_integrate` no
longer receives them one by one); taken by `_integrate`, the kernel and
`trace.build_trace`. The kernel unpacks `dt = settings.substep_duration` at its top.

### 5. `response._ForceSchedule` — the forces per substep (C-01)

| field | today | type |
|---|---|---|
| `unbalance_force_by_substep` | `flat` | float64, one value per forced substep |
| `sample_start` | `offsets` | int64, samples + 1 |
| `elbow_a_force_by_substep`, `elbow_b_force_by_substep` | `flat_a`, `flat_b` | float64 (empty when not tracing) |
| `transit_substep_count` | `delay_substeps` | int |

Built by `_integrate` from the `loads` generators (plan 4.12 later moves the flattening
into `loads`); taken by the kernel.

### 6. `response._KernelResult` — what the kernel returns (plan 3.5)

`x_max`, `v_max`, `a_max`, `unbalance_force_max` (today `f_max`), `x`, `v`, `a`,
`sample_number` (`tot_ind`), `forced_sample_count` (`forced_samples`), `junction_force`
(`d_f`), `frame_count` (`n_frames`), in today's order. Replaces the bare 11-tuple.

### 7. `trace.TraceRequest` — moved from `response._TraceRequest` (plan 3.6)

The fields stay (`stride`, `solver`, `inputs`, `celerity`, `elbow_force_samples`). It
moves to `trace.py` because `trace.build_trace` then takes it whole in place of `solver`,
`inputs`, `trace_every` and `celerity`. `build_trace(request, settings, sdof_params,
buffers, frame_count, column)`: 15 → 6; `inactive_end_cell_count` is read from
`moc.INACTIVE_END_CELL_COUNT` inside `trace` (the only value ever passed).

### 8. `moc.ColumnGrid` and `coupling.FluidConstants` — the coupling's inputs (plan 3.8, C-18)

* `ColumnGrid(column_cell_count, end_to_elbow_cell_count)`: returned by `moc.grid_size`
  (today a bare pair; unpacking callers are unaffected) and taken by `moc.is_short_pipe`'s
  callers as now. Plan 3.11 (the set-up query) and the tools can use it later.
* `FluidConstants(characteristic_impedance, flow_area, end_pressure_decay_factor)`.
* `JunctionCoupling(grid, substep_duration, fluid, vav_denominator="fixed",
  fraction_profile="fixed")`: 8 → 5. The two flag keywords and their defaults stay (C-18;
  their form is the public API session's).

## Signatures after

| function | today | after |
|---|---|---|
| `structure.step_scalars` | 11 | 6 (done, 3.1) |
| `moc.step` | 15 | 4 |
| `response._trace_frame` | 23 | 4 |
| `response._integrate_kernel` | 36 (31 after 3.1) | 7 |
| `response._integrate` | 9 | 5 |
| `trace.build_trace` | 15 | 6 |
| `trace.allocate_frames` | 2 | 3 |
| `coupling.JunctionCoupling.__init__` | 8 | 5 |

`_integrate_kernel(schedule, sdof_params, settings, column, junction_force,
response_history, buffers)` stays at 7. The two that do not fit a group are the junction
force (an evolving scalar, kept explicit by the brief) and the response history (an output
array filled in place, a different thing from any input group and from the trace
buffers). Folding either into a tuple would group by type, not by meaning; the reason goes
into `findings.md` (C-01).

## Commits, innermost first

1. 3.2 `FluidColumn`: `moc.step` and the kernel take it; `JunctionCoupling` builds it;
   `moc.empty_column()` for the lumped run.
2. 2.2 `is_fluid_coupled` on the column; `kind` leaves the kernel and `_trace_frame`.
3. 3.3 `TraceBuffers` from `allocate_frames`, taken by the kernel, `_trace_frame`,
   `build_trace`.
4. 3.3 `_Frame`, and `_trace_frame` takes the column.
5. 3.4 `RunSettings`, built by the entry points.
6. `_ForceSchedule`.
7. 3.5 `_KernelResult`.
8. 3.6 `TraceRequest` to `trace`; `build_trace` takes the request, settings and column.
9. 3.8 `ColumnGrid`, `FluidConstants`, `JunctionCoupling(grid, ...)`.
10. R0, one per function: the remaining kernel locals of `moc.step`, `_trace_frame` and
    `_integrate_kernel` renamed to `docs/nomenclature.md`.

After each: `make clean-cache`, lint, the compiled fast suite before the commit, the
pure-Python suite before the next; an A/B timing against the session's base on this host
(ruling 43) after commits 1, 2, 5, 6 and 7, which touch the substep loop.

Not in this session: 3.7 (span, restraint and fluid objects for `lumped_params` /
`jc_params`), 3.10 (entry-point extraction) and 3.11 (the set-up query).
