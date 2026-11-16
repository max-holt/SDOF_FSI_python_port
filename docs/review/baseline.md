# Review baseline — metrics before the clean-code review

Measured with ruff 0.17.5 and radon 6.0.1 from the project venv, on branch
`review/clean-code`. The solver core was measured in session R.0 (sources identical to
`177c8b1`); the supporting modules and `tools/` were added in session R.0b, when the scope
was widened, on sources that are still identical to `177c8b1` under `src/` (`tools/` as of
the commit that adds this text, the review's own three scripts included).
`docs/review/charter.md` says what the review may change; `docs/style.md` §3 gives the
targets. The last review session reruns this and puts the tables side by side.

## How to reproduce

```bash
.venv/bin/pip install -e ".[dev,plots]"                   # radon is in the dev extra
.venv/bin/python tools/review_baseline.py                 # the three sections below
.venv/bin/python tools/review_baseline.py --group core    # one of core, supporting, tools
```

`tools/review_baseline.py` runs exactly two commands (`--commands` prints them with the
file list of the groups asked for) and joins their JSON by function:

```bash
.venv/bin/python -m ruff check --preview --isolated --no-cache --output-format json --select C901,PLR0912,PLR0913,PLR0915,PLR1702 --config 'lint.mccabe.max-complexity = 0' --config 'lint.pylint.max-args = 0' --config 'lint.pylint.max-branches = 0' --config 'lint.pylint.max-statements = 0' --config 'lint.pylint.max-nested-blocks = 0' <files>
.venv/bin/python -m radon cc --json --show-closures <files>
```

`<files>` is, by group: **core** `src/surge_sdof/` `moc.py`, `structure.py`, `coupling.py`,
`loads.py`, `response.py`, `pressure.py`, `_vba_semantics.py`; **supporting**
`src/surge_sdof/` `trace.py`, `export.py`, `histories.py`, `viz/geometry.py`; **tools**
every `tools/*.py`.

Ruff reports a function only above a threshold, so the five thresholds are set to 0 on the
command line and `--isolated` keeps `pyproject.toml` out of it; the lint settings of the
project are unchanged.

## Columns

| column | source | meaning |
|---|---|---|
| args | ruff PLR0913 | parameters of the signature (`self` not counted; keyword-only ones are counted) |
| cc (ruff) | ruff C901 | McCabe complexity; boolean operators and comprehensions are not counted. **The count the style guide's target refers to** |
| cc (radon) | `radon cc` | McCabe complexity counting each `and` / `or` and comprehension. Reported only |
| branches | ruff PLR0912 | branch statements |
| statements | ruff PLR0915 | statements |
| nesting | ruff PLR1702 (`--preview`) | deepest nesting of blocks inside the function |
| length | radon `lineno` .. `endline` | lines from `def` to the last line, signature and docstring included |
| code lines | `ast` in the script | length minus the docstring's lines |

Bold marks a value over its target in `docs/style.md` §3: 6 parameters, complexity 10
(ruff's count), 50 statements, nesting 3, and 40 lines after the docstring. `(njit)` marks
the compiled kernels. A function nested in another is listed under `outer.inner`: ruff
counts its branches into the outer function as well, radon (`--show-closures`) does not, so
for an outer function radon's complexity can be the lower one (`tools/bench.build_cases`:
7 against 3).

## The solver core

52 functions; over target: 14 with more than 6 arguments, 2 with complexity over 10, 2 with more than 50 statements, 2 nested deeper than 3, 10 longer than 40 lines after the docstring.

| function | line | args | cc (ruff) | cc (radon) | branches | statements | nesting | length | code lines |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `moc.grid_size` | 89 | 4 | 1 | 1 | 0 | 3 | 0 | 26 | 6 |
| `moc.is_short_pipe` | 118 | 2 | 1 | 1 | 0 | 1 | 0 | 14 | 2 |
| `moc.decay_factor` | 135 | 3 | 1 | 1 | 0 | 1 | 0 | 19 | 2 |
| `moc.interp_fraction_a` | 157 | 3 | 5 | 5 | 5 | 6 | 1 | 29 | 11 |
| `moc.interp_fraction_b` | 189 | 3 | 5 | 5 | 5 | 6 | 1 | 33 | 11 |
| `moc.interp_fraction_a_fixed` | 225 | 3 | 5 | 5 | 5 | 6 | 1 | 33 | 11 |
| `moc.interp_fraction_b_fixed` | 261 | 3 | 5 | 5 | 5 | 6 | 1 | 32 | 11 |
| `moc.interp_fractions` | 295 | 3 | 6 | 6 | 6 | 13 | 2 | 53 | 23 |
| `moc.new_column` | 350 | 1 | 1 | 1 | 0 | 1 | 0 | 19 | 6 |
| `moc.vav_divisor` | 372 | 2 | 3 | 3 | 2 | 4 | 1 | 25 | 6 |
| `moc.step` (njit) | 400 | **15** | 7 | 7 | 7 | 32 | 2 | 116 | **66** |
| `structure.solve_poly` | 90 | 3 | 3 | 3 | 2 | 8 | 2 | 33 | 10 |
| `structure.solve_portal_height` | 126 | 4 | 2 | 2 | 1 | 6 | 1 | 36 | 14 |
| `structure.lumped_params` | 165 | **9** | 1 | 1 | 0 | 5 | 0 | 57 | 22 |
| `structure.jc_params` | 226 | **11** | 1 | 1 | 0 | 5 | 0 | 87 | **45** |
| `structure.effective_displacement` | 317 | 3 | 6 | 8 | 7 | 17 | 1 | 45 | 20 |
| `structure.restoring_force` | 364 | 4 | 1 | 1 | 0 | 1 | 0 | 22 | 2 |
| `structure.step` | 388 | 4 | 1 | 1 | 0 | 3 | 0 | 38 | 4 |
| `structure.step_scalars` (njit) | 429 | **11** | 9 | 11 | 11 | 29 | 2 | 69 | **47** |
| `coupling.Coupling.coupling_force` | 44 | 2 | 1 | 1 | 0 | 2 | 0 | 16 | 2 |
| `coupling.NoCoupling.coupling_force` | 68 | 2 | 1 | 1 | 0 | 1 | 0 | 5 | 2 |
| `coupling.JunctionCoupling.__init__` | 143 | **8** | 1 | 1 | 0 | 10 | 0 | 21 | 21 |
| `coupling.JunctionCoupling.coupling_force` | 165 | 2 | 1 | 1 | 0 | 3 | 0 | 34 | 20 |
| `coupling.JunctionCoupling.column` | 200 | 0 | 1 | 1 | 0 | 1 | 0 | 5 | 2 |
| `loads.as_history_2d` | 48 | 1 | 3 | 3 | 2 | 5 | 1 | 27 | 7 |
| `loads.transit_delay` | 78 | 3 | 1 | 1 | 0 | 1 | 0 | 18 | 2 |
| `loads.overlap_substeps` | 99 | 2 | 1 | 1 | 0 | 1 | 0 | 17 | 2 |
| `loads._run` | 132 | 5 | 1 | 3 | 0 | 6 | 0 | 10 | 10 |
| `loads._schedule` | 145 | 1 | **14** | 19 | 19 | **60** | 3 | 86 | **75** |
| `loads.unbalance_force` | 233 | 5 | 7 | 7 | 7 | 24 | **4** | 78 | 38 |
| `loads.elbow_forces` | 313 | 5 | 7 | 7 | 7 | 24 | **4** | 62 | 36 |
| `response.PeakResponse.summary` | 148 | 0 | 1 | 1 | 0 | 1 | 0 | 9 | 8 |
| `response.peak_response` | 161 | **14** | 2 | 2 | 1 | 19 | 1 | 141 | **77** |
| `response.peak_response_jc` | 305 | **19** | 6 | 6 | 5 | 32 | 1 | 199 | **136** |
| `response._trace_stride` | 507 | 1 | 2 | 2 | 1 | 4 | 1 | 6 | 5 |
| `response._decay_test` (njit) | 525 | 2 | 2 | 2 | 1 | 4 | 1 | 7 | 5 |
| `response._record` (njit) | 535 | 6 | 4 | 4 | 3 | 7 | 1 | 11 | 9 |
| `response._trace_frame` (njit) | 549 | **23** | 3 | 4 | 2 | 20 | 2 | 49 | **45** |
| `response._integrate` | 600 | **10** | 10 | 22 | 11 | 44 | 2 | 143 | **126** |
| `response._integrate_kernel` (njit) | 747 | **36** | **23** | 32 | 24 | **75** | 3 | 230 | **212** |
| `pressure.grid_size` | 105 | 4 | 1 | 1 | 0 | 1 | 0 | 21 | 2 |
| `pressure.setup` | 129 | **11** | 1 | 1 | 0 | 9 | 0 | 63 | 32 |
| `pressure.initial_column` | 196 | 1 | 2 | 2 | 1 | 11 | 1 | 30 | 13 |
| `pressure.valve_closure` | 229 | 3 | 5 | 7 | 6 | 18 | 2 | 51 | 24 |
| `pressure.valve_boundary` | 283 | 6 | 2 | 2 | 2 | 7 | 1 | 29 | 10 |
| `pressure.half_step_a_from_b` | 315 | 6 | 2 | 2 | 1 | 10 | 1 | 29 | 13 |
| `pressure.pump_boundary` | 347 | **8** | 1 | 1 | 0 | 4 | 0 | 38 | 21 |
| `pressure.half_step_b_from_a` | 388 | 6 | 2 | 2 | 1 | 10 | 1 | 29 | 13 |
| `pressure.pressure_response` | 419 | **11** | 2 | 2 | 1 | 13 | 2 | 94 | **46** |
| `pressure.get_pressure_response` | 515 | **11** | 1 | 1 | 0 | 1 | 0 | 26 | 25 |
| `_vba_semantics.vba_min` | 25 | 2 | 2 | 2 | 2 | 3 | 1 | 6 | 5 |
| `_vba_semantics.vba_max` | 33 | 2 | 2 | 2 | 2 | 3 | 1 | 6 | 5 |

### The five furthest from the targets

Ranked by targets missed, then by how far.

1. `response._integrate_kernel`: 36 parameters, complexity 23 (radon 32), 75 statements,
   212 code lines; the forced-response and free-decay loops repeat one 60-line time-step
   block. The only function that misses every target but nesting.
2. `loads._schedule`: complexity 14 (radon 19), 60 statements, 75 code lines; the VBA index
   walk with its post-loop index values, written as two hand-rolled `while` loops, with the next-index
   rule repeated five times in small variations.
3. `response._integrate`: 10 parameters, complexity 10 (radon 22), 126 code lines; flattens
   the schedule, sets the trace up, unpacks the coupling, calls the kernel and builds the
   result in one function.
4. `response.peak_response_jc`: 19 parameters, 136 code lines, of which about 60 repeat
   `peak_response` (conversions, set-up, the trace `inputs` echo).
5. `moc.step`: 15 parameters, 66 code lines; one function holding both half-grid updates
   behind a boolean.

Next in line: `response._trace_frame` (23 parameters), `structure.step_scalars` (11
parameters, radon complexity 11, the gap ladder inlined a second time),
`loads.unbalance_force` / `loads.elbow_forces` (nesting 4, and near copies of each other)
and the 9- to 14-parameter set-up functions.

## The supporting modules

`trace.py` was listed with the solver in R.0 and moves here unchanged (the kernel writes
only to the arrays of `trace.allocate`, through `response._trace_frame`).

45 functions; over target: 6 with more than 6 arguments, 1 with complexity over 10, 0 with more than 50 statements, 0 nested deeper than 3, 7 longer than 40 lines after the docstring.

| function | line | args | cc (ruff) | cc (radon) | branches | statements | nesting | length | code lines |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `trace.Trace.n_frames` | 167 | 0 | 1 | 1 | 0 | 1 | 0 | 3 | 2 |
| `trace.capacity` | 172 | 5 | 2 | 2 | 1 | 3 | 1 | 28 | 7 |
| `trace.check_memory` | 202 | 6 | 3 | 3 | 2 | 8 | 1 | 42 | 21 |
| `trace.allocate` | 247 | 2 | 1 | 2 | 0 | 2 | 0 | 18 | 7 |
| `trace.interleave` | 268 | 2 | 2 | 2 | 1 | 7 | 1 | 23 | 8 |
| `trace.build` | 293 | **15** | 2 | 2 | 1 | 9 | 1 | 75 | **57** |
| `export.git_sha` | 164 | 1 | 2 | 4 | 1 | 6 | 1 | 17 | 15 |
| `export.created_utc` | 183 | 1 | 1 | 2 | 0 | 2 | 0 | 4 | 3 |
| `export.array_block` | 192 | 1 | 2 | 2 | 1 | 4 | 1 | 6 | 5 |
| `export._finite` | 200 | 2 | 2 | 2 | 1 | 2 | 1 | 4 | 4 |
| `export._jsonable` | 206 | 2 | 10 | 15 | 9 | 14 | 3 | 23 | 21 |
| `export._column` | 231 | 2 | 3 | 3 | 2 | 5 | 1 | 8 | 7 |
| `export._geometry` | 244 | 1 | 1 | 1 | 0 | 0 | 0 | 22 | 22 |
| `export._synthetic_phase` | 269 | 1 | 2 | 4 | 1 | 2 | 1 | 5 | 4 |
| `export.is_capped` | 276 | 1 | 2 | 2 | 1 | 5 | 1 | 15 | 7 |
| `export._frames` | 293 | 1 | 2 | 2 | 1 | 6 | 1 | 16 | 14 |
| `export._cells` | 311 | 1 | 3 | 3 | 2 | 7 | 2 | 10 | 10 |
| `export.to_trace_dict` | 323 | 4 | 3 | 6 | 2 | 10 | 1 | 77 | **54** |
| `export._sweep_value` | 405 | 3 | **14** | 16 | 13 | 23 | 3 | 29 | 29 |
| `export.to_sweep_dict` | 436 | **9** | 6 | 9 | 5 | 11 | 2 | 73 | **43** |
| `export.dumps` | 515 | 1 | 1 | 1 | 0 | 1 | 0 | 4 | 2 |
| `export.write_json` | 521 | 3 | 2 | 3 | 2 | 9 | 2 | 12 | 10 |
| `export.read_json` | 535 | 1 | 2 | 2 | 2 | 7 | 2 | 9 | 8 |
| `histories.History.params` | 155 | 0 | 1 | 2 | 0 | 1 | 0 | 4 | 2 |
| `histories.History.force` | 160 | 1 | 1 | 1 | 0 | 1 | 0 | 3 | 2 |
| `histories.p_cap` | 168 | 2 | 1 | 1 | 0 | 1 | 0 | 3 | 2 |
| `histories.decay_rate` | 173 | 3 | 3 | 4 | 2 | 8 | 1 | 17 | 9 |
| `histories.envelope` | 192 | 4 | 1 | 1 | 0 | 1 | 0 | 4 | 2 |
| `histories._duration` | 198 | 4 | 3 | 3 | 2 | 2 | 2 | 10 | 10 |
| `histories._axis` | 210 | 3 | 3 | 3 | 2 | 7 | 1 | 9 | 8 |
| `histories._stats` | 221 | 1 | 1 | 1 | 0 | 0 | 0 | 6 | 6 |
| `histories._history` | 230 | 6 | 1 | 1 | 0 | 1 | 0 | 15 | 15 |
| `histories.step` | 251 | 5 | 1 | 1 | 0 | 8 | 0 | 51 | 35 |
| `histories._sine_shape` | 305 | 5 | 1 | 1 | 0 | 4 | 0 | 9 | 7 |
| `histories.step_sine` | 316 | **9** | 1 | 1 | 0 | 11 | 0 | 62 | **42** |
| `histories._lowpass` | 381 | 3 | 2 | 2 | 1 | 5 | 1 | 9 | 7 |
| `histories.step_noise` | 392 | **12** | 3 | 4 | 2 | 24 | 1 | 103 | **64** |
| `histories.canonical` | 501 | **14** | 6 | 7 | 5 | 14 | 2 | 79 | **48** |
| `histories.from_params` | 582 | 1 | 5 | 10 | 4 | 11 | 1 | 39 | 31 |
| `viz.geometry.LoopLayout.n_cells` | 91 | 0 | 1 | 1 | 0 | 0 | 0 | 2 | 2 |
| `viz.geometry._segments` | 98 | 1 | 3 | 4 | 2 | 9 | 1 | 16 | 10 |
| `viz.geometry.loop_layout` | 116 | **8** | 1 | 2 | 0 | 21 | 0 | 80 | **55** |
| `viz.geometry._interp_fractions_display` | 199 | 2 | 4 | 4 | 3 | 7 | 2 | 15 | 11 |
| `viz.geometry.lumped_grid` | 216 | 2 | 1 | 1 | 0 | 7 | 0 | 42 | 24 |
| `viz.geometry.layout_from_trace` | 261 | 1 | 2 | 2 | 1 | 6 | 1 | 33 | 22 |

### Furthest from the targets

1. `export._sweep_value`: complexity 14 (radon 16) in 29 lines; one function decides null,
   string, integer and float cells by a ladder of `isinstance` tests on the column's kind.
2. `histories.step_noise` (12 parameters, 64 code lines), `histories.canonical` (14
   parameters) and `histories.step_sine` (9 parameters): the four duration and sampling
   arguments travel through every generator, and each generator ends in a 20-line
   `_history(...)` call that spells out all fifteen parameter keys.
3. `trace.build`: 15 parameters, 57 code lines; the keyword list of a run, taken apart and
   put back into a `Trace`.
4. `viz.geometry.loop_layout`: 8 parameters, 55 code lines; the layout arithmetic and the
   construction of the 19-field `LoopLayout` in one function.
5. `export.to_trace_dict` (54 code lines) and `export.to_sweep_dict` (9 parameters, 43 code
   lines): each builds its whole document, `meta` block included, in one literal.

## `tools/`

All `tools/*.py`, the three scripts of the review among them (`review_baseline.py`,
`review_snapshot.py`, `review_support.py`).

129 functions; over target: 1 with more than 6 arguments, 2 with complexity over 10, 1 with more than 50 statements, 7 nested deeper than 3, 17 longer than 40 lines after the docstring.

| function | line | args | cc (ruff) | cc (radon) | branches | statements | nesting | length | code lines |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `tools/bench.log` | 157 | 1 | 1 | 2 | 0 | 2 | 0 | 3 | 2 |
| `tools/bench.substep_count` | 162 | 2 | 1 | 1 | 0 | 3 | 0 | 5 | 4 |
| `tools/bench.pipe_seg_qty` | 169 | 1 | 1 | 1 | 0 | 3 | 0 | 8 | 6 |
| `tools/bench.build_cases` | 179 | 0 | 7 | 3 | 1 | 19 | 1 | 133 | **132** |
| `tools/bench.build_cases.peak_case` | 185 | **8** | 3 | 13 | 2 | 8 | 1 | 30 | 30 |
| `tools/bench.build_cases.peak_response_summary` | 217 | 1 | 1 | 1 | 0 | 0 | 0 | 2 | 2 |
| `tools/bench.build_cases.pressure_case` | 220 | 4 | 1 | 1 | 0 | 0 | 0 | 17 | 17 |
| `tools/bench.example_lumped_call` | 314 | 0 | 1 | 3 | 0 | 3 | 0 | 6 | 4 |
| `tools/bench.git` | 325 | 0 | 2 | 2 | 1 | 2 | 1 | 7 | 7 |
| `tools/bench.cpu_model` | 334 | 0 | 4 | 6 | 3 | 5 | **4** | 9 | 9 |
| `tools/bench._version` | 345 | 1 | 2 | 2 | 1 | 2 | 1 | 5 | 5 |
| `tools/bench.environment` | 352 | 0 | 1 | 1 | 0 | 0 | 0 | 12 | 12 |
| `tools/bench.time_case` | 370 | 2 | 2 | 2 | 1 | 5 | 1 | 8 | 8 |
| `tools/bench.rel_path` | 380 | 1 | 2 | 2 | 1 | 2 | 1 | 5 | 5 |
| `tools/bench.profile_case` | 387 | 1 | 2 | 2 | 1 | 10 | 1 | 21 | 21 |
| `tools/bench.run_cases` | 410 | 5 | 5 | 9 | 4 | 22 | 2 | 37 | 36 |
| `tools/bench.select` | 449 | 4 | 3 | 10 | 2 | 5 | 1 | 7 | 7 |
| `tools/bench.worker_main` | 461 | 1 | 5 | 11 | 5 | 25 | 2 | 47 | **45** |
| `tools/bench.spawn_worker` | 510 | 4 | 5 | 6 | 4 | 12 | 1 | 22 | 22 |
| `tools/bench.previous_run` | 537 | 1 | 5 | 6 | 4 | 11 | 3 | 14 | 13 |
| `tools/bench.case_key` | 553 | 1 | 1 | 3 | 0 | 2 | 0 | 4 | 3 |
| `tools/bench.fmt_time` | 559 | 1 | 1 | 2 | 0 | 0 | 0 | 2 | 2 |
| `tools/bench.print_table` | 563 | 2 | 10 | 22 | 10 | 28 | 3 | 61 | **61** |
| `tools/bench.check_digest_pairs` | 627 | 1 | 4 | 7 | 3 | 8 | 3 | 13 | 11 |
| `tools/bench.fmt_cell` | 652 | 1 | 1 | 2 | 0 | 0 | 0 | 2 | 2 |
| `tools/bench.readme_section` | 656 | 1 | 7 | 24 | 6 | 21 | 2 | 54 | **54** |
| `tools/bench.append_readme` | 712 | 1 | 2 | 3 | 1 | 6 | 1 | 8 | 6 |
| `tools/bench.parse_args` | 725 | 1 | 1 | 1 | 0 | 7 | 0 | 19 | 19 |
| `tools/bench.main` | 746 | 1 | 7 | 12 | 6 | 32 | 2 | 45 | **45** |
| `tools/build_viewer.plotly_bundle_path` | 39 | 0 | 1 | 1 | 0 | 2 | 0 | 5 | 4 |
| `tools/build_viewer.plotly_version` | 46 | 1 | 2 | 2 | 1 | 4 | 1 | 6 | 5 |
| `tools/build_viewer.pako_version` | 54 | 1 | 2 | 2 | 1 | 4 | 1 | 6 | 5 |
| `tools/build_viewer._script` | 62 | 2 | 2 | 2 | 1 | 2 | 1 | 4 | 4 |
| `tools/build_viewer.build` | 68 | 4 | 3 | 3 | 2 | 11 | 2 | 28 | 27 |
| `tools/build_viewer.main` | 98 | 1 | 1 | 3 | 0 | 12 | 0 | 28 | 28 |
| `tools/cases.golden_case` | 39 | 1 | 5 | 6 | 4 | 5 | 2 | 14 | 13 |
| `tools/cases.step_case` | 55 | 1 | 1 | 2 | 0 | 8 | 0 | 25 | 23 |
| `tools/cases.step_name` | 82 | 1 | 1 | 2 | 0 | 0 | 0 | 6 | 6 |
| `tools/cases.forced_substeps` | 91 | 2 | 1 | 1 | 0 | 2 | 0 | 4 | 3 |
| `tools/cases.default_trace_every` | 97 | 3 | 1 | 1 | 0 | 1 | 0 | 3 | 2 |
| `tools/cases.run` | 102 | 4 | 2 | 4 | 1 | 2 | 1 | 5 | 5 |
| `tools/cases.add_source_arguments` | 109 | 1 | 1 | 1 | 0 | 24 | 0 | 31 | 30 |
| `tools/cases.case_from_args` | 142 | 1 | 2 | 4 | 1 | 4 | 1 | 7 | 6 |
| `tools/cases._nominal_size_in` | 154 | 1 | 1 | 2 | 0 | 1 | 0 | 3 | 3 |
| `tools/cases.golden_sweep_rows` | 159 | 3 | 2 | 4 | 1 | 8 | 1 | 25 | 22 |
| `tools/cases.golden_regen` | 186 | 0 | 1 | 1 | 0 | 0 | 0 | 6 | 6 |
| `tools/cases.sweep_regen` | 198 | 0 | 1 | 1 | 0 | 1 | 0 | 9 | 6 |
| `tools/cases.uniform_value` | 214 | 2 | 1 | 3 | 0 | 2 | 0 | 4 | 3 |
| `tools/cases.reference_block` | 220 | 0 | 6 | 9 | 5 | 16 | 2 | 40 | 39 |
| `tools/cases.sweep_rows_from_csv` | 265 | 1 | 3 | 7 | 2 | 11 | 1 | 18 | 14 |
| `tools/export.estimated_cells` | 47 | 2 | 2 | 3 | 1 | 5 | 1 | 10 | 9 |
| `tools/export.estimate_bytes` | 59 | 3 | 1 | 1 | 0 | 1 | 0 | 3 | 2 |
| `tools/export.export_trace_every` | 64 | 5 | 2 | 2 | 1 | 9 | 1 | 13 | 10 |
| `tools/export.main_trace` | 79 | 1 | 1 | 4 | 0 | 10 | 0 | 20 | 20 |
| `tools/export.main_sweep` | 102 | 1 | 1 | 8 | 0 | 6 | 0 | 26 | 26 |
| `tools/export.parse_args` | 131 | 1 | 1 | 1 | 0 | 12 | 0 | 19 | 19 |
| `tools/export.main` | 152 | 1 | 2 | 2 | 2 | 5 | 1 | 6 | 6 |
| `tools/extract_fixtures.match_case` | 164 | 1 | 3 | 3 | 2 | 3 | 2 | 7 | 6 |
| `tools/extract_fixtures.fmt` | 173 | 1 | 1 | 2 | 0 | 0 | 0 | 2 | 2 |
| `tools/extract_fixtures.cell_range_values` | 177 | 4 | 3 | 3 | 2 | 6 | 2 | 9 | 8 |
| `tools/extract_fixtures.read_params` | 188 | 4 | 4 | 4 | 3 | 8 | 2 | 11 | 11 |
| `tools/extract_fixtures.extract_example` | 201 | 3 | 6 | 11 | 6 | 35 | 2 | 63 | **62** |
| `tools/extract_fixtures.extract_curve_10in` | 267 | 4 | **23** | 35 | 22 | **73** | 2 | 136 | **135** |
| `tools/extract_fixtures.main` | 406 | 1 | 1 | 1 | 0 | 13 | 1 | 26 | 26 |
| `tools/golden_report.load_case_ids` | 25 | 0 | 1 | 2 | 0 | 7 | 1 | 9 | 9 |
| `tools/golden_report.main` | 36 | 0 | 6 | 15 | 5 | 26 | 2 | 56 | **56** |
| `tools/profile_delta.rel` | 60 | 2 | 1 | 1 | 0 | 4 | 0 | 6 | 5 |
| `tools/profile_delta.fmt` | 68 | 1 | 1 | 2 | 0 | 0 | 0 | 2 | 2 |
| `tools/profile_delta.run_golden` | 72 | 0 | 4 | 12 | 3 | 16 | 2 | 50 | **50** |
| `tools/profile_delta.run_sweep` | 124 | 0 | 5 | 11 | 2 | 19 | 1 | 58 | **58** |
| `tools/profile_delta.run_sweep.cell` | 170 | 2 | 2 | 3 | 1 | 1 | 1 | 4 | 4 |
| `tools/profile_delta._read_csv` | 210 | 1 | 1 | 2 | 0 | 2 | 1 | 5 | 5 |
| `tools/profile_delta.run_tier_csv` | 217 | 2 | 3 | 10 | 2 | 19 | 1 | 36 | 36 |
| `tools/profile_delta.main` | 255 | 1 | 7 | 10 | 6 | 20 | 2 | 26 | 26 |
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
| `tools/review_snapshot.main` | 29 | 0 | 9 | 11 | 8 | 21 | 3 | 31 | 31 |
| `tools/review_support.write` | 34 | 2 | 4 | 5 | 3 | 9 | 1 | 15 | 14 |
| `tools/review_support.differing` | 51 | 2 | 3 | 5 | 2 | 6 | 1 | 13 | 12 |
| `tools/review_support.main` | 66 | 0 | 5 | 6 | 4 | 15 | 2 | 24 | 24 |
| `tools/sweep_jc.curve_sheet_nat_freqs` | 97 | 0 | 1 | 3 | 0 | 4 | 1 | 6 | 5 |
| `tools/sweep_jc.pipe` | 118 | 1 | 1 | 1 | 0 | 8 | 0 | 11 | 9 |
| `tools/sweep_jc.check_pipe_table` | 131 | 1 | 5 | 7 | 4 | 11 | 2 | 24 | 22 |
| `tools/sweep_jc.Case.history_key` | 172 | 0 | 1 | 1 | 0 | 0 | 0 | 2 | 2 |
| `tools/sweep_jc.Case.case_id` | 176 | 0 | 3 | 3 | 3 | 6 | 1 | 10 | 10 |
| `tools/sweep_jc.tier_cases` | 189 | 1 | 1 | 10 | 0 | 6 | 0 | 15 | 14 |
| `tools/sweep_jc.stratified_subset` | 210 | 3 | 7 | 13 | 6 | 17 | 3 | 25 | 21 |
| `tools/sweep_jc.coverage` | 237 | 1 | 1 | 3 | 0 | 0 | 0 | 2 | 2 |
| `tools/sweep_jc.case_history` | 267 | 2 | 1 | 2 | 0 | 0 | 0 | 10 | 10 |
| `tools/sweep_jc.history_from_row` | 280 | 1 | 5 | 5 | 5 | 11 | 2 | 14 | 13 |
| `tools/sweep_jc.solver_kwargs` | 296 | 2 | 1 | 1 | 0 | 0 | 0 | 13 | 13 |
| `tools/sweep_jc._timed` | 312 | 1 | 2 | 2 | 1 | 4 | 1 | 7 | 7 |
| `tools/sweep_jc.run_case` | 321 | 5 | 7 | 10 | 6 | 37 | 2 | 81 | **80** |
| `tools/sweep_jc.git` | 407 | 0 | 2 | 2 | 1 | 2 | 1 | 7 | 7 |
| `tools/sweep_jc.git_sha_tag` | 416 | 0 | 2 | 3 | 1 | 3 | 1 | 5 | 5 |
| `tools/sweep_jc.cpu_model` | 423 | 0 | 4 | 6 | 3 | 5 | **4** | 9 | 9 |
| `tools/sweep_jc.write_csv` | 434 | 2 | 2 | 4 | 1 | 5 | 2 | 7 | 7 |
| `tools/sweep_jc.read_csv` | 443 | 1 | 1 | 1 | 0 | 1 | 1 | 3 | 3 |
| `tools/sweep_jc._worker` | 448 | 1 | 1 | 1 | 0 | 1 | 0 | 3 | 3 |
| `tools/sweep_jc.run` | 453 | 1 | 8 | 22 | 7 | 35 | 3 | 51 | **51** |
| `tools/sweep_jc._f` | 517 | 1 | 1 | 2 | 0 | 0 | 0 | 2 | 2 |
| `tools/sweep_jc._load` | 521 | 1 | 3 | 4 | 2 | 4 | 2 | 23 | 23 |
| `tools/sweep_jc._history_variants` | 546 | 1 | 3 | 5 | 2 | 6 | 2 | 9 | 8 |
| `tools/sweep_jc._variant_label` | 557 | 1 | 1 | 2 | 0 | 1 | 0 | 3 | 3 |
| `tools/sweep_jc._select` | 562 | 1 | 7 | 9 | 6 | 11 | 3 | 15 | 15 |
| `tools/sweep_jc._series` | 579 | 3 | 3 | 5 | 2 | 7 | 2 | 12 | 9 |
| `tools/sweep_jc._style_axes` | 593 | 1 | 3 | 3 | 2 | 7 | 1 | 10 | 10 |
| `tools/sweep_jc._freq_ticks` | 605 | 2 | 1 | 2 | 0 | 7 | 0 | 9 | 9 |
| `tools/sweep_jc.plot_ratio` | 616 | 6 | 10 | 15 | 9 | 34 | **4** | 71 | **69** |
| `tools/sweep_jc.plot_daf` | 689 | 3 | 9 | 16 | 8 | 30 | **6** | 86 | **83** |
| `tools/sweep_jc.plot_collapse` | 777 | 4 | 8 | 13 | 7 | 28 | **5** | 68 | **66** |
| `tools/sweep_jc._band` | 855 | 1 | 3 | 3 | 2 | 1 | 2 | 5 | 5 |
| `tools/sweep_jc.ratio_table` | 862 | 3 | 5 | 14 | 4 | 18 | **4** | 31 | 28 |
| `tools/sweep_jc.amplitude_table` | 895 | 2 | 9 | 15 | 9 | 24 | **5** | 41 | 38 |
| `tools/sweep_jc.collapse_spread` | 938 | 3 | 4 | 10 | 3 | 12 | 3 | 27 | 25 |
| `tools/sweep_jc.write_doc` | 967 | 6 | 2 | 13 | 1 | 15 | 1 | 62 | **62** |
| `tools/sweep_jc.plot` | 1031 | 1 | 1 | 5 | 0 | 18 | 0 | 39 | 39 |
| `tools/sweep_jc.parse_args` | 1075 | 1 | 1 | 2 | 0 | 19 | 0 | 49 | **49** |
| `tools/sweep_jc.main` | 1126 | 1 | 3 | 3 | 3 | 7 | 1 | 8 | 8 |

### Furthest from the targets

1. `tools/extract_fixtures.extract_curve_10in`: complexity 23 (radon 35), 73 statements,
   135 code lines; reads the sheet, checks it and writes the three fixture files in one function. It
   needs the workbook and is run by hand only.
2. The plotting half of `tools/sweep_jc.py`: `plot_daf` (nesting 6, 83 code lines),
   `plot_collapse` (nesting 5), `plot_ratio` (nesting 4, 69 code lines), `amplitude_table`
   (nesting 5) and `ratio_table` (nesting 4): loops over size, length, history and
   amplitude nested inside one another, repeated from plot to plot.
3. `tools/sweep_jc.run_case` (80 code lines): pipe properties, the history, both solver
   runs and the 72-column row in one function; `tools/sweep_jc.run` (radon 22) mixes the
   case selection, the file name, the pool and the progress report.
4. `tools/bench.py`: `build_cases` (132 code lines, a closure with 8 parameters inside),
   `print_table` and `readme_section` (radon 22 and 24, 61 and 54 code lines).
5. `tools/review_baseline.collect` (complexity 12): the review's own script joins the two
   tools' output in one function with two nested helpers.
