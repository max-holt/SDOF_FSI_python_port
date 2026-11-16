# Review baseline — solver metrics before the clean-code review

Measured on the tree of the commit that adds this file (branch `review/clean-code`, solver
sources identical to `177c8b1`), with ruff 0.17.5 and radon 6.0.1 from the project venv.
`docs/review/charter.md` says what the review may change; `docs/style.md` §3 gives the
targets. The last review session reruns this and puts the two tables side by side.

## How to reproduce

```bash
.venv/bin/pip install -e ".[dev,plots]"      # radon is in the dev extra
.venv/bin/python tools/review_baseline.py    # the summary line and the table below
```

`tools/review_baseline.py` runs exactly these two commands (`--commands` prints them) and
joins their JSON by function:

```bash
.venv/bin/python -m ruff check --preview --isolated --no-cache --output-format json --select C901,PLR0912,PLR0913,PLR0915,PLR1702 --config 'lint.mccabe.max-complexity = 0' --config 'lint.pylint.max-args = 0' --config 'lint.pylint.max-branches = 0' --config 'lint.pylint.max-statements = 0' --config 'lint.pylint.max-nested-blocks = 0' src/surge_sdof/moc.py src/surge_sdof/structure.py src/surge_sdof/coupling.py src/surge_sdof/loads.py src/surge_sdof/response.py src/surge_sdof/pressure.py src/surge_sdof/_vba_semantics.py src/surge_sdof/trace.py
.venv/bin/python -m radon cc --json --show-closures src/surge_sdof/moc.py src/surge_sdof/structure.py src/surge_sdof/coupling.py src/surge_sdof/loads.py src/surge_sdof/response.py src/surge_sdof/pressure.py src/surge_sdof/_vba_semantics.py src/surge_sdof/trace.py
```

Ruff reports a function only above a threshold, so the five thresholds are set to 0 on the
command line and `--isolated` keeps `pyproject.toml` out of it; the lint settings of the
project are unchanged.

## Columns

| column | source | meaning |
|---|---|---|
| args | ruff PLR0913 | parameters of the signature (`self` not counted) |
| cc (ruff) | ruff C901 | McCabe complexity; boolean operators and comprehensions are not counted |
| cc (radon) | `radon cc` | McCabe complexity counting each `and` / `or` and comprehension, so never lower than ruff's |
| branches | ruff PLR0912 | branch statements |
| statements | ruff PLR0915 | statements |
| nesting | ruff PLR1702 (`--preview`) | deepest nesting of blocks inside the function |
| length | radon `lineno` .. `endline` | lines from `def` to the last line, signature and docstring included |
| code lines | `ast` in the script | length minus the docstring's lines |

Bold marks a value over its target in `docs/style.md` §3: 6 parameters (the guide sets this
for private functions; it is applied to all here as an indicator), complexity 10 (ruff's
count), 50 statements, nesting 3, and 40 lines after the docstring. `(njit)` marks the
compiled kernels. `trace.py` is listed whole; the kernel writes only to the arrays of
`trace.allocate`, through `response._trace_frame`.

## Baseline

58 functions; over target: 15 with more than 6 arguments, 2 with complexity over 10, 2 with more than 50 statements, 2 nested deeper than 3, 11 longer than 40 lines after the docstring.

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
| `trace.Trace.n_frames` | 167 | 0 | 1 | 1 | 0 | 1 | 0 | 3 | 2 |
| `trace.capacity` | 172 | 5 | 2 | 2 | 1 | 3 | 1 | 28 | 7 |
| `trace.check_memory` | 202 | 6 | 3 | 3 | 2 | 8 | 1 | 42 | 21 |
| `trace.allocate` | 247 | 2 | 1 | 2 | 0 | 2 | 0 | 18 | 7 |
| `trace.interleave` | 268 | 2 | 2 | 2 | 1 | 7 | 1 | 23 | 8 |
| `trace.build` | 293 | **15** | 2 | 2 | 1 | 9 | 1 | 75 | **57** |

## The five furthest from the targets

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
`loads.unbalance_force` / `loads.elbow_forces` (nesting 4, and near copies of each other),
`trace.build` (15 parameters) and the 9- to 14-parameter set-up functions.
