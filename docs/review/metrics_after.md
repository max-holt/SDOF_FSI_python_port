# Review metrics — after (session R.12, 25 Nov 2026)

Measured on `7e726e0` with ruff 0.17.5 and radon 6.0.1, by the commands of
`docs/review/baseline.md` with one addition: `--ignore-noqa` on the ruff command.
Since session R.10 the recorded `docs/style.md` §11 exceptions carry targeted `noqa`
comments, and ruff then reports nothing for that rule even under `--isolated`:
`tools/review_baseline.py` as committed prints 0 for `peak_response_jc`'s parameters,
`_integrate_kernel`'s statements, the nesting of the two loads walks and the parameters of
the three history generators. The baseline was measured before any `noqa` existed, so the
flag changes nothing on the before side. These numbers are indicators (`docs/style.md` §1).

"code lines" is the function's length minus its docstring: comments and the lines that
`ruff format` wraps count. Columns as in `baseline.md`; bold is over target.

## Before and after, solver core and supporting modules

Renamed functions are matched by hand (`docs/nomenclature.md`); "=" is an unchanged name.
cc is ruff's count (the target's).

| before | after | args | cc | stmts | nest | code lines |
|---|---|---|---|---|---|---|
| `moc.grid_size` | = | 4 | 1 | 3 | 0 | 6 → 13 |
| `moc.is_short_pipe` | = | 2 | 1 | 1 | 0 | 2 |
| `moc.decay_factor` | `moc.end_pressure_decay_factor` | 3 | 1 | 1 | 0 | 2 → 4 |
| `moc.interp_fraction_a` | `moc.moving_fraction_a` | 3 | 5 | 6 | 1 | 11 → 17 |
| `moc.interp_fraction_b` | `moc.moving_fraction_b` | 3 | 5 | 6 | 1 | 11 → 16 |
| `moc.interp_fraction_a_fixed` | `moc.moving_fraction_a_fixed` | 3 | 5 | 6 | 1 | 11 → 17 |
| `moc.interp_fraction_b_fixed` | `moc.moving_fraction_b_fixed` | 3 | 5 | 6 | 1 | 11 → 16 |
| `moc.interp_fractions` | `moc.moving_fractions` | 3 | 6 | 13 | 2 | 23 → 24 |
| `moc.new_column` | `moc.column_at_rest` | 1 | 1 | 1 | 0 | 6 |
| `moc.vav_divisor` | `moc.mean_velocity_divisor` | 2 | 3 | 4 | 1 | 6 |
| `moc.step` | = | **15** → 4 | 7 | 32 → 44 | 2 | **66** → **103** |
| `structure.solve_poly` | `structure.solve_quartic` | 3 | 3 | 8 → 7 | 2 | 10 → 13 |
| `structure.solve_portal_height` | = | 4 | 2 | 6 | 1 | 14 → 28 |
| `structure.lumped_params` | = | **9** → 4 | 1 | 5 → 7 | 0 | 22 → 16 |
| `structure.jc_params` | = | **11** → 5 | 1 | 5 → 8 | 0 | **45** → 40 |
| `structure.effective_displacement` | = | 3 | 6 | 17 | 1 | 20 → 22 |
| `structure.restoring_force` | removed (R.3, test-only wrapper) | 4 | 1 | 1 | 0 | 2 |
| `structure.step` | removed (R.3, test-only wrapper) | 4 | 1 | 3 | 0 | 4 |
| `structure.step_scalars` | = | **11** → 6 | 9 → 4 | 29 → 19 | 2 | **47** → 36 |
| `coupling.Coupling.coupling_force` | removed (R.3, protocol) | 2 | 1 | 2 | 0 | 2 |
| `coupling.NoCoupling.coupling_force` | removed (R.3) | 2 | 1 | 1 | 0 | 2 |
| `coupling.JunctionCoupling.__init__` | `coupling.fluid_column` | **8** → 4 | 1 → 2 | 10 → 11 | 0 → 1 | 21 → 35 |
| `coupling.JunctionCoupling.coupling_force` | removed (R.3) | 2 | 1 | 3 | 0 | 20 |
| `coupling.JunctionCoupling.column` | removed (R.3) | 0 | 1 | 1 | 0 | 2 |
| `loads.as_history_2d` | = | 1 | 3 | 5 | 1 | 7 |
| `loads.transit_delay` | = | 3 | 1 | 1 | 0 | 2 |
| `loads.overlap_substeps` | = | 2 | 1 | 1 | 0 | 2 |
| `loads._run` | `loads._walk_constants` | 5 | 1 | 6 → 7 | 0 | 10 → 24 |
| `loads._schedule` | = | 1 | **14** → 10 | **60** → 41 | 3 | **75** → **92** |
| `loads.unbalance_force` | = | 5 | 7 | 24 | **4** | 38 → **70** |
| `loads.elbow_forces` | = | 5 | 7 | 24 | **4** | 36 → **68** |
| `response.PeakResponse.summary` | = | 0 | 1 | 1 | 0 | 8 |
| `response.peak_response` | = | **14** → 5 | 2 → 1 | 19 → 10 | 1 → 0 | **77** → 38 |
| `response.peak_response_jc` | = | **19** → **7** | 6 → 2 | 32 → 16 | 1 | **136** → **62** |
| `response._trace_stride` | = | 1 | 2 | 4 | 1 | 5 |
| `response._decay_test` | `response._free_decay_product` | 2 | 2 | 4 | 1 | 5 |
| `response._record` | `response._record_sample` | 6 → 5 | 4 → 1 | 7 → 4 | 1 → 0 | 9 → 4 |
| `response._trace_frame` | `response._record_frame` | **23** → 6 | 3 → 2 | 20 → 5 | 2 → 1 | **45** → 32 |
| `response._integrate` | = | **10** → 5 | 10 → 3 | 44 → 8 | 2 → 1 | **126** → 26 |
| `response._integrate_kernel` | = | **36** → 6 | **23** → 10 | **75** → **55** | 3 | **212** → **137** |
| `trace.Trace.n_frames` | `trace.Trace.frame_count` | 0 | 1 | 1 | 0 | 2 |
| `trace.capacity` | `trace.frame_capacity` | 5 | 2 | 3 | 1 | 7 → 14 |
| `trace.check_memory` | = | 6 | 3 | 8 | 1 | 21 → 36 |
| `trace.allocate` | `trace.allocate_frames` | 2 → 3 | 1 | 2 | 0 | 7 → 8 |
| `trace.interleave` | = | 2 | 2 | 7 | 1 | 8 |
| `trace.build` | `trace.build_trace` | **15** → 6 | 2 → 4 | 9 → 17 | 1 → 2 | **57** → **55** |
| `export.git_sha` | = | 1 | 2 | 6 | 1 | 15 |
| `export.created_utc` | = | 1 | 1 | 2 | 0 | 3 |
| `export.array_block` | = | 1 | 2 | 4 | 1 | 5 |
| `export._finite` | = | 2 | 2 | 2 → 3 | 1 | 4 |
| `export._jsonable` | = | 2 | 10 | 14 | 3 | 21 |
| `export._column` | = | 2 | 3 | 5 | 1 | 7 |
| `export._geometry` | = | 1 | 1 | 0 → 1 | 0 | 22 |
| `export._synthetic_phase` | = | 1 | 2 | 2 | 1 | 4 |
| `export.is_capped` | = | 1 | 2 → 1 | 5 → 2 | 1 → 0 | 7 → 4 |
| `export._frames` | = | 1 | 2 | 6 | 1 | 14 |
| `export._cells` | `export._grid_points` | 1 | 3 | 7 → 8 | 2 | 10 → 13 |
| `export.to_trace_dict` | = | 4 | 3 | 10 | 1 | **54** → 33 |
| `export._sweep_value` | = | 3 | **14** → 8 | 23 → 12 | 3 → 2 | 29 → 17 |
| `export.to_sweep_dict` | = | **9** → 4 | 6 → 5 | 11 → 10 | 2 | **43** → 33 |
| `export.dumps` | = | 1 | 1 | 1 | 0 | 2 |
| `export.write_json` | = | 3 | 2 | 9 | 2 | 10 |
| `export.read_json` | = | 1 | 2 | 7 | 2 | 8 |
| `histories.History.params` | = | 0 | 1 | 1 | 0 | 2 |
| `histories.History.force` | = | 1 | 1 | 1 | 0 | 2 |
| `histories.p_cap` | `histories.peak_pressure_target` | 2 | 1 | 1 | 0 | 2 |
| `histories.decay_rate` | = | 3 | 3 | 8 | 1 | 9 → 13 |
| `histories.envelope` | = | 4 | 1 | 1 | 0 | 2 → 9 |
| `histories._duration` | = | 4 | 3 | 2 → 3 | 2 | 10 |
| `histories._axis` | = | 3 | 3 | 7 | 1 | 8 |
| `histories._stats` | = | 1 | 1 | 0 → 1 | 0 | 6 |
| `histories._history` | = | 6 | 1 | 1 → 3 | 0 | 15 → 24 |
| `histories.step` | = | 5 | 1 | 8 | 0 | 35 → 26 |
| `histories._sine_shape` | = | 5 | 1 | 4 | 0 | 7 → 15 |
| `histories.step_sine` | = | **9** | 1 | 11 | 0 | **42** → **50** |
| `histories._lowpass` | = | 3 | 2 | 5 | 1 | 7 |
| `histories.step_noise` | = | **12** | 3 → 2 | 24 → 21 | 1 | **64** → **72** |
| `histories.canonical` | = | **14** | 6 | 14 | 2 | **48** → **62** |
| `histories.from_params` | = | 1 | 5 | 11 | 1 | 31 → **44** |
| `viz.geometry.LoopLayout.n_cells` | `viz.geometry.LoopLayout.grid_point_count` | 0 | 1 | 0 → 1 | 0 | 2 |
| `viz.geometry._segments` | = | 1 | 3 | 9 | 1 | 10 → 14 |
| `viz.geometry.loop_layout` | = | **8** → 3 | 1 | 21 | 0 | **55** → **75** |
| `viz.geometry._interp_fractions_display` | `moc.display_moving_fractions` | 2 | 4 | 7 → 6 | 2 → 1 | 11 → 16 |
| `viz.geometry.lumped_grid` | = | 2 → 1 | 1 | 7 → 5 | 0 | 24 → 14 |
| `viz.geometry.layout_from_trace` | = | 1 | 2 | 6 → 5 | 1 | 22 → 13 |
| (new) | `moc.empty_column` | 0 | 1 | 2 | 0 | 16 |
| (new) | `structure._sdof_params` | 5 | 1 | 1 | 0 | 14 |
| (new) | `structure.substep_friction` | 6 | 1 | 4 | 0 | 7 |
| (new) | `loads._wraps_to_next_column` | 4 | 1 | 1 | 0 | 2 |
| (new) | `loads._next_position` | 4 | 2 | 2 | 1 | 4 |
| (new) | `loads.flatten_unbalance_force` | 1 | 2 | 5 | 1 | 7 |
| (new) | `loads.flatten_elbow_forces` | 1 | 3 | 10 | 2 | 18 |
| (new) | `response.CouplingModel.__post_init__` | 0 | 4 | 7 | 1 | 12 |
| (new) | `response._coerced_span` | 1 | 1 | 1 | 0 | 6 |
| (new) | `response._sample_grid` | 3 | 1 | 4 | 0 | 9 |
| (new) | `response._trace_request` | 5 | 2 | 2 | 1 | 17 |
| (new) | `response._checked_integration` | 1 | 1 | 1 | 0 | 2 |
| (new) | `response.solver_setup` | 4 | 1 | 3 | 0 | 8 |
| (new) | `response.column_grid` | 2 | 1 | 1 | 0 | 3 |
| (new) | `response._is_frame_due` | 5 | 1 | 1 | 0 | 12 |
| (new) | `response._parity_offset` | 5 | 2 | 2 | 1 | 10 |
| (new) | `response._largest_magnitude` | 1 | 3 | 5 | 2 | 7 |
| (new) | `response._decay_reference` | 2 | 2 | 2 | 1 | 4 |
| (new) | `response._structure_substep` | 4 | 4 | 11 | 1 | 14 |
| (new) | `response._kernel_inputs` | 4 | 3 | 20 | 2 | **55** |
| (new) | `response._peak_response` | 4 | 1 | 2 | 0 | 26 |
| (new) | `trace.ColumnTrace.grid_point_count` | 0 | 1 | 1 | 0 | 2 |
| (new) | `trace.write_frame_row` | 3 | 1 | 15 | 0 | 15 |
| (new) | `trace.write_frame_column` | 3 | 2 | 14 | 1 | 15 |
| (new) | `trace.interleaved_grid` | 6 | 1 | 2 | 0 | 16 |
| (new) | `export._provenance` | 2 | 1 | 1 | 0 | 4 |
| (new) | `export._meta_params` | 1 | 1 | 3 | 0 | 19 |
| (new) | `export._meta_outputs` | 1 | 1 | 1 | 0 | 10 |
| (new) | `export._sweep_string` | 2 | 2 | 3 | 1 | 4 |
| (new) | `export._sweep_int` | 3 | 4 | 7 | 2 | 8 |
| (new) | `export._sweep_float` | 2 | 3 | 5 | 1 | 6 |
| (new) | `export.read_csv` | 1 | 1 | 5 | 1 | 6 |
| (new) | `histories._scaled_to_peak` | 3 | 2 | 4 | 1 | 7 |

## tools/ (aggregate)

Before (R.0b): 128 functions; over target: 1 with more than 6 arguments, 2 with complexity
over 10, 1 with more than 50 statements, 7 nested deeper than 3, 17 longer than 40 lines.
After: 145 functions (`sweep_jc.py` split into `sweep_grid`, `sweep_rows`, `sweep_report`;
`cases`, `fixture_cases`, `sweep_document`, `review_ab` added); over target: 1, 2, 1, 7
and 21. Every function over target is in a tool that no test runs or in the review's own
harnesses (`review_ab`, `review_baseline`), all exempt from the lint limits
(`pyproject.toml`, rulings 24 and 87), except `cases.add_source_arguments`,
`sweep_document.reference_block`, `sweep_jc.run`, `sweep_jc.parse_args` and
`sweep_rows._case_columns`, which are over the 40-line mark only (an argparse table, a
record builder, the pool driver, a column dict).

## Full output

### The solver core

56 functions; over target: 1 with more than 6 arguments, 0 with complexity over 10, 1 with more than 50 statements, 2 nested deeper than 3, 7 longer than 40 lines after the docstring.

| function | line | args | cc (ruff) | cc (radon) | branches | statements | nesting | length | code lines |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `moc.grid_size` | 111 | 4 | 1 | 1 | 0 | 3 | 0 | 39 | 13 |
| `moc.is_short_pipe` | 153 | 2 | 1 | 1 | 0 | 1 | 0 | 19 | 2 |
| `moc.end_pressure_decay_factor` | 175 | 3 | 1 | 1 | 0 | 1 | 0 | 27 | 4 |
| `moc.moving_fraction_a` | 205 | 3 | 5 | 5 | 5 | 6 | 1 | 39 | 17 |
| `moc.moving_fraction_b` | 247 | 3 | 5 | 5 | 5 | 6 | 1 | 38 | 16 |
| `moc.moving_fraction_a_fixed` | 288 | 3 | 5 | 5 | 5 | 6 | 1 | 43 | 17 |
| `moc.moving_fraction_b_fixed` | 334 | 3 | 5 | 5 | 5 | 6 | 1 | 41 | 16 |
| `moc.moving_fractions` | 377 | 3 | 6 | 6 | 6 | 13 | 2 | 55 | 24 |
| `moc.display_moving_fractions` | 434 | 2 | 4 | 4 | 3 | 6 | 1 | 34 | 16 |
| `moc.column_at_rest` | 470 | 1 | 1 | 1 | 0 | 1 | 0 | 24 | 6 |
| `moc.mean_velocity_divisor` | 497 | 2 | 3 | 3 | 2 | 4 | 1 | 26 | 6 |
| `moc.empty_column` | 577 | 0 | 1 | 1 | 0 | 2 | 0 | 24 | 16 |
| `moc.step` (njit) | 605 | 4 | 7 | 7 | 7 | 44 | 2 | 140 | **103** |
| `structure.solve_quartic` | 116 | 3 | 3 | 3 | 2 | 7 | 2 | 35 | 13 |
| `structure.solve_portal_height` | 154 | 4 | 2 | 2 | 1 | 6 | 1 | 54 | 28 |
| `structure.lumped_params` | 211 | 4 | 1 | 1 | 0 | 7 | 0 | 43 | 16 |
| `structure.jc_params` | 257 | 5 | 1 | 1 | 0 | 8 | 0 | 72 | 40 |
| `structure._sdof_params` | 331 | 5 | 1 | 1 | 0 | 1 | 0 | 34 | 14 |
| `structure.effective_displacement` (njit) | 370 | 3 | 6 | 8 | 7 | 17 | 1 | 51 | 22 |
| `structure.step_scalars` (njit) | 424 | 6 | 4 | 4 | 4 | 19 | 2 | 72 | 36 |
| `structure.substep_friction` (njit) | 499 | 6 | 1 | 1 | 0 | 4 | 0 | 32 | 7 |
| `coupling.fluid_column` | 52 | 4 | 2 | 2 | 1 | 11 | 1 | 80 | 35 |
| `loads.as_history_2d` | 62 | 1 | 3 | 3 | 2 | 5 | 1 | 27 | 7 |
| `loads.transit_delay` | 92 | 3 | 1 | 1 | 0 | 1 | 0 | 22 | 2 |
| `loads.overlap_substeps` | 117 | 2 | 1 | 1 | 0 | 1 | 0 | 22 | 2 |
| `loads._walk_constants` | 155 | 5 | 1 | 3 | 0 | 7 | 0 | 38 | 24 |
| `loads._wraps_to_next_column` | 219 | 4 | 1 | 2 | 0 | 1 | 0 | 16 | 2 |
| `loads._next_position` | 237 | 4 | 2 | 2 | 1 | 2 | 1 | 20 | 4 |
| `loads._schedule` | 259 | 1 | 10 | 10 | 11 | 41 | 3 | 113 | **92** |
| `loads.unbalance_force` | 375 | 5 | 7 | 7 | 7 | 24 | **4** | 110 | **70** |
| `loads.elbow_forces` | 487 | 5 | 7 | 7 | 7 | 24 | **4** | 99 | **68** |
| `loads.flatten_unbalance_force` | 588 | 1 | 2 | 2 | 1 | 5 | 1 | 24 | 7 |
| `loads.flatten_elbow_forces` | 614 | 1 | 3 | 3 | 2 | 10 | 2 | 36 | 18 |
| `response.CouplingModel.__post_init__` | 247 | 0 | 4 | 4 | 3 | 7 | 1 | 13 | 12 |
| `response.PeakResponse.summary` | 313 | 0 | 1 | 1 | 0 | 1 | 0 | 9 | 8 |
| `response.peak_response` | 326 | 5 | 1 | 1 | 0 | 10 | 0 | 87 | 38 |
| `response.peak_response_jc` | 416 | **7** | 2 | 2 | 1 | 16 | 1 | 116 | **62** |
| `response._coerced_span` | 534 | 1 | 1 | 1 | 0 | 1 | 0 | 7 | 6 |
| `response._sample_grid` | 544 | 3 | 1 | 1 | 0 | 4 | 0 | 31 | 9 |
| `response._trace_request` | 577 | 5 | 2 | 2 | 1 | 2 | 1 | 40 | 17 |
| `response._checked_integration` | 621 | 1 | 1 | 1 | 0 | 1 | 0 | 4 | 2 |
| `response._trace_stride` | 627 | 1 | 2 | 2 | 1 | 4 | 1 | 7 | 5 |
| `response.solver_setup` | 653 | 4 | 1 | 1 | 0 | 3 | 0 | 26 | 8 |
| `response.column_grid` | 681 | 2 | 1 | 1 | 0 | 1 | 0 | 17 | 3 |
| `response._free_decay_product` (njit) | 785 | 2 | 2 | 2 | 1 | 4 | 1 | 13 | 5 |
| `response._is_frame_due` (njit) | 801 | 5 | 1 | 4 | 0 | 1 | 0 | 15 | 12 |
| `response._parity_offset` (njit) | 820 | 5 | 2 | 2 | 1 | 2 | 1 | 18 | 10 |
| `response._largest_magnitude` (njit) | 841 | 1 | 3 | 3 | 2 | 5 | 2 | 9 | 7 |
| `response._decay_reference` (njit) | 853 | 2 | 2 | 2 | 1 | 2 | 1 | 13 | 4 |
| `response._record_sample` (njit) | 888 | 5 | 1 | 1 | 0 | 4 | 0 | 7 | 4 |
| `response._structure_substep` (njit) | 914 | 4 | 4 | 4 | 3 | 11 | 1 | 20 | 14 |
| `response._record_frame` (njit) | 958 | 6 | 2 | 2 | 1 | 5 | 1 | 61 | 32 |
| `response._integrate` | 1021 | 5 | 3 | 5 | 2 | 8 | 1 | 60 | 26 |
| `response._kernel_inputs` | 1083 | 4 | 3 | 5 | 3 | 20 | 2 | 79 | **55** |
| `response._peak_response` | 1164 | 4 | 1 | 1 | 0 | 2 | 0 | 29 | 26 |
| `response._integrate_kernel` (njit) | 1197 | 6 | 10 | 11 | 11 | **55** | 3 | 182 | **137** |

### The supporting modules

56 functions; over target: 3 with more than 6 arguments, 0 with complexity over 10, 0 with more than 50 statements, 0 nested deeper than 3, 6 longer than 40 lines after the docstring.

| function | line | args | cc (ruff) | cc (radon) | branches | statements | nesting | length | code lines |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `trace.ColumnTrace.grid_point_count` | 191 | 0 | 1 | 1 | 0 | 1 | 0 | 3 | 2 |
| `trace.Trace.frame_count` | 269 | 0 | 1 | 1 | 0 | 1 | 0 | 3 | 2 |
| `trace.frame_capacity` | 274 | 5 | 2 | 2 | 1 | 3 | 1 | 40 | 14 |
| `trace.check_memory` | 316 | 6 | 3 | 3 | 2 | 8 | 1 | 59 | 36 |
| `trace.write_frame_row` (njit) | 441 | 3 | 1 | 2 | 0 | 15 | 0 | 18 | 15 |
| `trace.write_frame_column` (njit) | 462 | 3 | 2 | 2 | 1 | 14 | 1 | 18 | 15 |
| `trace.allocate_frames` | 482 | 3 | 1 | 2 | 0 | 2 | 0 | 25 | 8 |
| `trace.interleave` | 510 | 2 | 2 | 2 | 1 | 7 | 1 | 23 | 8 |
| `trace.interleaved_grid` | 559 | 6 | 1 | 1 | 0 | 2 | 0 | 35 | 16 |
| `trace.build_trace` | 597 | 6 | 4 | 4 | 3 | 17 | 2 | 79 | **55** |
| `export.git_sha` | 164 | 1 | 2 | 4 | 1 | 6 | 1 | 27 | 15 |
| `export.created_utc` | 193 | 1 | 1 | 2 | 0 | 2 | 0 | 15 | 3 |
| `export._provenance` | 210 | 2 | 1 | 3 | 0 | 1 | 0 | 6 | 4 |
| `export.array_block` | 222 | 1 | 2 | 2 | 1 | 4 | 1 | 22 | 5 |
| `export._finite` | 246 | 2 | 2 | 2 | 1 | 3 | 1 | 5 | 4 |
| `export._jsonable` | 253 | 2 | 10 | 15 | 9 | 14 | 3 | 23 | 21 |
| `export._column` | 278 | 2 | 3 | 3 | 2 | 5 | 1 | 8 | 7 |
| `export._geometry` | 291 | 1 | 1 | 1 | 0 | 1 | 0 | 24 | 22 |
| `export._synthetic_phase` | 318 | 1 | 2 | 4 | 1 | 2 | 1 | 5 | 4 |
| `export.is_capped` | 325 | 1 | 1 | 1 | 0 | 2 | 0 | 24 | 4 |
| `export._frames` | 352 | 1 | 2 | 2 | 1 | 6 | 1 | 16 | 14 |
| `export._grid_points` | 370 | 1 | 3 | 3 | 2 | 8 | 2 | 15 | 13 |
| `export._meta_params` | 387 | 1 | 1 | 1 | 0 | 3 | 0 | 21 | 19 |
| `export._meta_outputs` | 411 | 1 | 1 | 1 | 0 | 1 | 0 | 11 | 10 |
| `export.to_trace_dict` | 425 | 4 | 3 | 4 | 2 | 10 | 1 | 56 | 33 |
| `export._sweep_string` | 486 | 2 | 2 | 3 | 1 | 3 | 1 | 5 | 4 |
| `export._sweep_int` | 493 | 3 | 4 | 4 | 3 | 7 | 2 | 9 | 8 |
| `export._sweep_float` | 504 | 2 | 3 | 3 | 2 | 5 | 1 | 7 | 6 |
| `export._sweep_value` | 513 | 3 | 8 | 9 | 7 | 12 | 2 | 19 | 17 |
| `export.to_sweep_dict` | 558 | 4 | 5 | 6 | 4 | 10 | 2 | 58 | 33 |
| `export.dumps` | 622 | 1 | 1 | 1 | 0 | 1 | 0 | 19 | 2 |
| `export.write_json` | 643 | 3 | 2 | 3 | 2 | 9 | 2 | 26 | 10 |
| `export.read_json` | 671 | 1 | 2 | 2 | 2 | 7 | 2 | 20 | 8 |
| `export.read_csv` | 693 | 1 | 1 | 2 | 0 | 5 | 1 | 23 | 6 |
| `histories.History.params` | 181 | 0 | 1 | 2 | 0 | 1 | 0 | 10 | 2 |
| `histories.History.force` | 192 | 1 | 1 | 1 | 0 | 1 | 0 | 14 | 2 |
| `histories.peak_pressure_target` | 211 | 2 | 1 | 1 | 0 | 1 | 0 | 17 | 2 |
| `histories.decay_rate` | 230 | 3 | 3 | 4 | 2 | 8 | 1 | 36 | 13 |
| `histories.envelope` | 268 | 4 | 1 | 1 | 0 | 1 | 0 | 25 | 9 |
| `histories._duration` | 296 | 4 | 3 | 3 | 2 | 3 | 2 | 12 | 10 |
| `histories._axis` | 310 | 3 | 3 | 3 | 2 | 7 | 1 | 16 | 8 |
| `histories._stats` | 328 | 1 | 1 | 1 | 0 | 1 | 0 | 7 | 6 |
| `histories._history` | 352 | 6 | 1 | 1 | 0 | 3 | 0 | 26 | 24 |
| `histories.step` | 384 | 5 | 1 | 1 | 0 | 8 | 0 | 42 | 26 |
| `histories._sine_shape` | 429 | 5 | 1 | 1 | 0 | 4 | 0 | 18 | 15 |
| `histories.step_sine` | 449 | **9** | 1 | 1 | 0 | 11 | 0 | 71 | **50** |
| `histories._lowpass` | 523 | 3 | 2 | 2 | 1 | 5 | 1 | 9 | 7 |
| `histories._scaled_to_peak` | 534 | 3 | 2 | 2 | 1 | 4 | 1 | 15 | 7 |
| `histories.step_noise` | 551 | **12** | 2 | 3 | 1 | 21 | 1 | 114 | **72** |
| `histories.canonical` | 671 | **14** | 6 | 7 | 5 | 14 | 2 | 96 | **62** |
| `histories.from_params` | 769 | 1 | 5 | 10 | 4 | 11 | 1 | 61 | **44** |
| `viz.geometry.LoopLayout.grid_point_count` | 98 | 0 | 1 | 1 | 0 | 1 | 0 | 3 | 2 |
| `viz.geometry._segments` | 106 | 1 | 3 | 4 | 2 | 9 | 1 | 21 | 14 |
| `viz.geometry.loop_layout` | 130 | 3 | 1 | 2 | 0 | 21 | 0 | 100 | **75** |
| `viz.geometry.lumped_grid` | 233 | 1 | 1 | 1 | 0 | 5 | 0 | 27 | 14 |
| `viz.geometry.layout_from_trace` | 263 | 1 | 2 | 2 | 1 | 5 | 1 | 25 | 13 |

### `tools/`

157 functions; over target: 1 with more than 6 arguments, 3 with complexity over 10, 1 with more than 50 statements, 7 nested deeper than 3, 21 longer than 40 lines after the docstring.

| function | line | args | cc (ruff) | cc (radon) | branches | statements | nesting | length | code lines |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `tools/bench.log` | 135 | 1 | 1 | 2 | 0 | 2 | 0 | 3 | 2 |
| `tools/bench.substep_count` | 140 | 2 | 1 | 1 | 0 | 3 | 0 | 5 | 4 |
| `tools/bench.pipe_seg_qty` | 147 | 1 | 1 | 1 | 0 | 3 | 0 | 8 | 6 |
| `tools/bench.build_cases` | 157 | 0 | 6 | 3 | 1 | 19 | 1 | 106 | **105** |
| `tools/bench.build_cases.peak_case` | 163 | **8** | 3 | 14 | 2 | 9 | 1 | 34 | 34 |
| `tools/bench.build_cases.peak_response_summary` | 199 | 1 | 1 | 1 | 0 | 0 | 0 | 2 | 2 |
| `tools/bench.example_lumped_call` | 265 | 0 | 1 | 3 | 0 | 3 | 0 | 6 | 4 |
| `tools/bench.git` | 276 | 0 | 2 | 2 | 1 | 2 | 1 | 7 | 7 |
| `tools/bench.cpu_model` | 285 | 0 | 4 | 6 | 3 | 5 | **4** | 9 | 9 |
| `tools/bench._version` | 296 | 1 | 2 | 2 | 1 | 2 | 1 | 5 | 5 |
| `tools/bench.environment` | 303 | 0 | 1 | 1 | 0 | 0 | 0 | 12 | 12 |
| `tools/bench.time_case` | 321 | 2 | 2 | 2 | 1 | 5 | 1 | 8 | 8 |
| `tools/bench.rel_path` | 331 | 1 | 2 | 2 | 1 | 2 | 1 | 5 | 5 |
| `tools/bench.profile_case` | 338 | 1 | 2 | 2 | 1 | 10 | 1 | 21 | 21 |
| `tools/bench.run_cases` | 361 | 5 | 5 | 9 | 4 | 22 | 2 | 37 | 36 |
| `tools/bench.select` | 400 | 4 | 3 | 10 | 2 | 5 | 1 | 7 | 7 |
| `tools/bench.worker_main` | 412 | 1 | 5 | 11 | 5 | 25 | 2 | 47 | **45** |
| `tools/bench.spawn_worker` | 461 | 4 | 5 | 6 | 4 | 12 | 1 | 22 | 22 |
| `tools/bench.previous_run` | 488 | 1 | 5 | 6 | 4 | 11 | 3 | 14 | 13 |
| `tools/bench.case_key` | 504 | 1 | 1 | 3 | 0 | 2 | 0 | 4 | 3 |
| `tools/bench.fmt_time` | 510 | 1 | 1 | 2 | 0 | 0 | 0 | 2 | 2 |
| `tools/bench.print_table` | 514 | 2 | 10 | 22 | 10 | 28 | 3 | 61 | **61** |
| `tools/bench.check_digest_pairs` | 578 | 1 | 4 | 7 | 3 | 8 | 3 | 13 | 11 |
| `tools/bench.fmt_cell` | 603 | 1 | 1 | 2 | 0 | 0 | 0 | 2 | 2 |
| `tools/bench.readme_section` | 607 | 1 | 7 | 24 | 6 | 21 | 2 | 54 | **54** |
| `tools/bench.append_readme` | 663 | 1 | 2 | 3 | 1 | 6 | 1 | 8 | 6 |
| `tools/bench.parse_args` | 676 | 1 | 1 | 1 | 0 | 7 | 0 | 19 | 19 |
| `tools/bench.main` | 697 | 1 | 7 | 12 | 6 | 32 | 2 | 45 | **45** |
| `tools/build_viewer.plotly_bundle_path` | 39 | 0 | 1 | 1 | 0 | 2 | 0 | 5 | 4 |
| `tools/build_viewer.plotly_version` | 46 | 1 | 2 | 2 | 1 | 4 | 1 | 7 | 5 |
| `tools/build_viewer.pako_version` | 55 | 1 | 2 | 2 | 1 | 4 | 1 | 7 | 5 |
| `tools/build_viewer._script` | 64 | 2 | 2 | 2 | 1 | 3 | 1 | 6 | 4 |
| `tools/build_viewer.build` | 72 | 6 | 5 | 5 | 4 | 15 | 2 | 64 | 38 |
| `tools/build_viewer.main` | 138 | 1 | 1 | 3 | 0 | 13 | 0 | 30 | 28 |
| `tools/cases.golden_case` | 37 | 1 | 5 | 6 | 4 | 5 | 2 | 32 | 13 |
| `tools/cases.step_spec` | 93 | 1 | 1 | 2 | 0 | 1 | 0 | 4 | 2 |
| `tools/cases.step_case` | 99 | 1 | 1 | 2 | 0 | 8 | 0 | 42 | 27 |
| `tools/cases.step_name` | 143 | 1 | 1 | 2 | 0 | 1 | 0 | 8 | 6 |
| `tools/cases.forced_substep_count` | 154 | 2 | 1 | 1 | 0 | 2 | 0 | 20 | 5 |
| `tools/cases.default_trace_every` | 176 | 3 | 1 | 1 | 0 | 1 | 0 | 4 | 2 |
| `tools/cases.run` | 182 | 4 | 2 | 4 | 1 | 3 | 1 | 22 | 5 |
| `tools/cases.add_source_arguments` | 206 | 1 | 1 | 1 | 0 | 24 | 0 | 46 | **44** |
| `tools/cases.case_from_args` | 254 | 1 | 2 | 4 | 1 | 5 | 1 | 15 | 7 |
| `tools/export.estimated_cells` | 53 | 2 | 2 | 3 | 1 | 5 | 1 | 27 | 12 |
| `tools/export.export_trace_every` | 83 | 5 | 2 | 2 | 1 | 9 | 1 | 40 | 14 |
| `tools/export.main_trace` | 125 | 1 | 1 | 4 | 0 | 11 | 0 | 22 | 20 |
| `tools/export.main_sweep` | 150 | 1 | 1 | 8 | 0 | 8 | 0 | 34 | 32 |
| `tools/export.parse_args` | 187 | 1 | 1 | 1 | 0 | 13 | 0 | 20 | 19 |
| `tools/export.main` | 209 | 1 | 2 | 2 | 2 | 6 | 1 | 7 | 6 |
| `tools/extract_fixtures.match_case` | 164 | 1 | 3 | 3 | 2 | 3 | 2 | 7 | 6 |
| `tools/extract_fixtures.fmt` | 173 | 1 | 1 | 2 | 0 | 0 | 0 | 2 | 2 |
| `tools/extract_fixtures.cell_range_values` | 177 | 4 | 3 | 3 | 2 | 6 | 2 | 9 | 8 |
| `tools/extract_fixtures.read_params` | 188 | 4 | 4 | 4 | 3 | 8 | 2 | 11 | 11 |
| `tools/extract_fixtures.extract_example` | 201 | 3 | 6 | 11 | 6 | 35 | 2 | 63 | **62** |
| `tools/extract_fixtures.extract_curve_10in` | 267 | 4 | **23** | 35 | 22 | **73** | 2 | 136 | **135** |
| `tools/extract_fixtures.main` | 406 | 1 | 1 | 1 | 0 | 13 | 1 | 26 | 26 |
| `tools/fixture_cases.load_params` | 61 | 0 | 1 | 1 | 0 | 2 | 1 | 5 | 3 |
| `tools/fixture_cases.load_cases` | 68 | 0 | 1 | 1 | 0 | 2 | 1 | 5 | 3 |
| `tools/fixture_cases.load_force` | 75 | 1 | 2 | 3 | 1 | 7 | 1 | 22 | 9 |
| `tools/fixture_cases.load_example_cases` | 99 | 0 | 1 | 1 | 0 | 2 | 1 | 5 | 3 |
| `tools/fixture_cases.case_params` | 106 | 2 | 2 | 3 | 1 | 5 | 1 | 39 | 23 |
| `tools/fixture_cases.solver_inputs` | 170 | 1 | 4 | 4 | 3 | 11 | 2 | 63 | 35 |
| `tools/fixture_cases.history_of` | 235 | 2 | 1 | 1 | 0 | 1 | 0 | 22 | 7 |
| `tools/golden_report.load_case_ids` | 25 | 0 | 1 | 2 | 0 | 7 | 1 | 9 | 9 |
| `tools/golden_report.main` | 36 | 0 | 6 | 15 | 5 | 26 | 2 | 56 | **56** |
| `tools/profile_delta.rel` | 61 | 2 | 1 | 1 | 0 | 4 | 0 | 6 | 5 |
| `tools/profile_delta.fmt` | 69 | 1 | 1 | 2 | 0 | 0 | 0 | 2 | 2 |
| `tools/profile_delta.run_golden` | 73 | 0 | 4 | 12 | 3 | 16 | 2 | 50 | **50** |
| `tools/profile_delta.run_sweep` | 125 | 0 | 5 | 11 | 2 | 19 | 1 | 60 | **60** |
| `tools/profile_delta.run_sweep.cell` | 173 | 2 | 2 | 3 | 1 | 1 | 1 | 4 | 4 |
| `tools/profile_delta._read_csv` | 215 | 1 | 1 | 2 | 0 | 2 | 1 | 5 | 5 |
| `tools/profile_delta.run_tier_csv` | 222 | 2 | 3 | 10 | 2 | 19 | 1 | 36 | 36 |
| `tools/profile_delta.main` | 260 | 1 | 7 | 10 | 6 | 20 | 2 | 26 | 26 |
| `tools/review_ab._cases` | 53 | 0 | 2 | 6 | 0 | 16 | 0 | 38 | 37 |
| `tools/review_ab._cases.kw` | 68 | 1 | 1 | 1 | 0 | 0 | 0 | 2 | 2 |
| `tools/review_ab.worker` | 94 | 3 | 4 | 6 | 3 | 12 | 2 | 16 | 15 |
| `tools/review_ab._git` | 112 | 0 | 1 | 1 | 0 | 0 | 0 | 3 | 3 |
| `tools/review_ab._run_worker` | 118 | 3 | 2 | 2 | 1 | 5 | 1 | 8 | 8 |
| `tools/review_ab.main` | 128 | 0 | 8 | 12 | 8 | 32 | **4** | 42 | **42** |
| `tools/review_baseline._functions` | 72 | 1 | 5 | 1 | 0 | 14 | 0 | 33 | 32 |
| `tools/review_baseline._functions.visit` | 77 | 2 | 4 | 9 | 3 | 9 | 2 | 25 | 25 |
| `tools/review_baseline._run_json` | 107 | 2 | 1 | 1 | 0 | 1 | 0 | 3 | 3 |
| `tools/review_baseline._label` | 112 | 1 | 2 | 2 | 1 | 2 | 1 | 5 | 4 |
| `tools/review_baseline.collect` | 119 | 1 | **12** | 12 | 9 | 23 | 3 | 36 | 36 |
| `tools/review_baseline.collect.owner` | 124 | 2 | 1 | 5 | 0 | 1 | 0 | 3 | 3 |
| `tools/review_baseline.collect.radon_blocks` | 137 | 1 | 2 | 2 | 1 | 3 | 1 | 5 | 5 |
| `tools/review_baseline._cell` | 157 | 2 | 1 | 3 | 0 | 1 | 0 | 3 | 3 |
| `tools/review_baseline.table` | 162 | 1 | 2 | 3 | 1 | 4 | 1 | 22 | 22 |
| `tools/review_baseline.summary` | 186 | 1 | 2 | 1 | 0 | 1 | 0 | 8 | 8 |
| `tools/review_baseline.summary.over` | 187 | 1 | 1 | 2 | 0 | 0 | 0 | 2 | 2 |
| `tools/review_baseline.main` | 198 | 0 | 4 | 11 | 3 | 16 | 2 | 21 | 21 |
| `tools/review_snapshot.main` | 29 | 0 | 9 | 11 | 8 | 22 | 3 | 33 | 31 |
| `tools/review_support.write` | 36 | 2 | 4 | 5 | 3 | 11 | 1 | 30 | 16 |
| `tools/review_support.differing` | 68 | 2 | 3 | 5 | 2 | 11 | 1 | 33 | 19 |
| `tools/review_support.main` | 103 | 0 | 5 | 8 | 4 | 19 | 2 | 34 | 32 |
| `tools/sweep_document._nominal_size_in` | 25 | 1 | 1 | 2 | 0 | 2 | 0 | 5 | 3 |
| `tools/sweep_document.golden_sweep_rows` | 32 | 3 | 2 | 4 | 1 | 8 | 1 | 43 | 24 |
| `tools/sweep_document.golden_regen` | 77 | 0 | 1 | 1 | 0 | 1 | 0 | 8 | 6 |
| `tools/sweep_document.sweep_regen` | 91 | 0 | 1 | 1 | 0 | 1 | 0 | 9 | 6 |
| `tools/sweep_document.uniform_value` | 107 | 2 | 1 | 3 | 0 | 2 | 0 | 5 | 3 |
| `tools/sweep_document._output_names` | 131 | 1 | 1 | 2 | 0 | 1 | 0 | 3 | 2 |
| `tools/sweep_document._grouped_inputs` | 136 | 3 | 3 | 3 | 2 | 5 | 2 | 24 | 7 |
| `tools/sweep_document.reference_block` | 162 | 0 | 6 | 9 | 5 | 16 | 2 | 50 | **42** |
| `tools/sweep_document.sweep_rows_from_csv` | 217 | 2 | 3 | 6 | 2 | 7 | 1 | 39 | 10 |
| `tools/sweep_grid.curve_sheet_nat_freqs` | 73 | 0 | 1 | 3 | 0 | 2 | 0 | 4 | 3 |
| `tools/sweep_grid.pipe` | 96 | 1 | 1 | 1 | 0 | 8 | 0 | 32 | 20 |
| `tools/sweep_grid.check_pipe_table` | 131 | 1 | 5 | 7 | 4 | 11 | 2 | 35 | 22 |
| `tools/sweep_grid.Case.history_key` | 187 | 0 | 1 | 1 | 0 | 1 | 0 | 3 | 2 |
| `tools/sweep_grid.Case.case_id` | 192 | 0 | 3 | 3 | 3 | 7 | 1 | 11 | 10 |
| `tools/sweep_grid.tier_cases` | 206 | 1 | 1 | 10 | 0 | 6 | 0 | 15 | 14 |
| `tools/sweep_grid.stratified_subset` | 234 | 3 | 7 | 13 | 6 | 17 | 3 | 41 | 21 |
| `tools/sweep_grid.coverage` | 277 | 1 | 1 | 3 | 0 | 1 | 0 | 3 | 2 |
| `tools/sweep_jc.git` | 66 | 0 | 2 | 2 | 1 | 3 | 1 | 9 | 7 |
| `tools/sweep_jc.git_sha_tag` | 77 | 0 | 2 | 3 | 1 | 4 | 1 | 7 | 5 |
| `tools/sweep_jc.cpu_model` | 86 | 0 | 3 | 7 | 2 | 7 | 2 | 11 | 9 |
| `tools/sweep_jc._worker` | 99 | 1 | 1 | 1 | 0 | 2 | 0 | 4 | 3 |
| `tools/sweep_jc.run` | 105 | 1 | 8 | 22 | 7 | 37 | 3 | 65 | **52** |
| `tools/sweep_jc.plot` | 172 | 1 | 1 | 5 | 0 | 19 | 0 | 41 | 39 |
| `tools/sweep_jc.parse_args` | 218 | 1 | 1 | 2 | 0 | 20 | 0 | 52 | **51** |
| `tools/sweep_jc.main` | 272 | 1 | 3 | 3 | 3 | 8 | 1 | 9 | 8 |
| `tools/sweep_report._f` | 27 | 1 | 1 | 2 | 0 | 0 | 0 | 2 | 2 |
| `tools/sweep_report._load` | 31 | 1 | 3 | 4 | 2 | 4 | 2 | 23 | 23 |
| `tools/sweep_report._history_variants` | 56 | 1 | 3 | 5 | 2 | 6 | 2 | 12 | 11 |
| `tools/sweep_report._variant_label` | 70 | 1 | 1 | 2 | 0 | 1 | 0 | 3 | 3 |
| `tools/sweep_report._select` | 75 | 1 | 7 | 9 | 6 | 11 | 3 | 17 | 17 |
| `tools/sweep_report._series` | 94 | 3 | 3 | 5 | 2 | 7 | 2 | 12 | 9 |
| `tools/sweep_report._style_axes` | 108 | 1 | 3 | 3 | 2 | 7 | 1 | 10 | 10 |
| `tools/sweep_report._freq_ticks` | 120 | 2 | 1 | 2 | 0 | 7 | 0 | 9 | 9 |
| `tools/sweep_report.plot_ratio` | 131 | 6 | 10 | 15 | 9 | 34 | **4** | 71 | **69** |
| `tools/sweep_report.plot_daf` | 204 | 3 | 9 | 16 | 8 | 30 | **6** | 86 | **83** |
| `tools/sweep_report.plot_collapse` | 292 | 4 | 8 | 13 | 7 | 28 | **5** | 68 | **66** |
| `tools/sweep_report._band` | 370 | 1 | 3 | 3 | 2 | 1 | 2 | 5 | 5 |
| `tools/sweep_report.ratio_table` | 377 | 3 | 5 | 14 | 4 | 18 | **4** | 37 | 34 |
| `tools/sweep_report.amplitude_table` | 416 | 2 | 9 | 15 | 9 | 24 | **5** | 45 | **42** |
| `tools/sweep_report.collapse_spread` | 463 | 3 | 4 | 10 | 3 | 12 | 3 | 31 | 29 |
| `tools/sweep_report.write_doc` | 496 | 6 | 2 | 13 | 1 | 15 | 1 | 62 | **62** |
| `tools/sweep_rows.case_history` | 65 | 2 | 1 | 2 | 0 | 1 | 0 | 27 | 12 |
| `tools/sweep_rows.history_from_row` | 95 | 1 | 5 | 5 | 5 | 11 | 2 | 25 | 13 |
| `tools/sweep_rows.solver_inputs` | 122 | 2 | 1 | 1 | 0 | 1 | 0 | 27 | 12 |
| `tools/sweep_rows._timed` | 152 | 1 | 2 | 2 | 1 | 5 | 1 | 11 | 9 |
| `tools/sweep_rows.run_case` | 174 | 2 | 1 | 1 | 0 | 7 | 0 | 22 | 8 |
| `tools/sweep_rows._case_columns` | 198 | 5 | 2 | 3 | 1 | 10 | 1 | 90 | **69** |
| `tools/sweep_rows._solver_results` | 290 | 4 | 3 | 4 | 2 | 10 | 1 | 39 | 20 |
| `tools/sweep_rows._result_columns` | 331 | 5 | 4 | 5 | 3 | 19 | 2 | 46 | 30 |
| `tools/sweep_rows.write_csv` | 379 | 2 | 2 | 4 | 1 | 6 | 2 | 9 | 7 |

