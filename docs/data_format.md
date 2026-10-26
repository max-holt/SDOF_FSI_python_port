# Results data format (Session W.1)

The data files the single-file JS viewer (Session W.2) loads. A file is written once by
`tools/export.py` (`surge_sdof.export`) and read by the viewer from disk, a SharePoint folder or
an OCI bucket with no Python on the viewing machine: the viewer controls playback, speed and the
time window live, so nothing about the presentation is baked into the file. This document is the
contract; `tests/test_export.py` parses the key tables below (every `### <block>` heading and the
`` `key` `` column of its table), so a key is part of the format exactly when it is listed here.

Two kinds of file, each with `kind` and `schema_version` (currently `1`):

* **`trace`** — one traced run (`PeakResponse.trace`, Session V.1): meta, the loop geometry the
  animation draws, the per-frame scalars and, for a junction-coupling run, the column arrays.
* **`sweep`** — a parameter sweep (Session 5b) as columns, plus the reference cases the viewer
  self-checks against on open.

## Common rules

* **Column-wise arrays only.** A per-frame or per-row quantity is one flat JSON array; there are
  no arrays of records. A 2-D array is an *array block* `{"shape": [n_rows, n_cols], "data":
  [...]}` with `data` flat, row-major (`data[i * n_cols + j]`), `len(data) == n_rows * n_cols`.
* **Floats via `repr`.** Every float is Python's `float.__repr__` (the shortest string that
  round-trips the double), never rounded or formatted; `JSON.parse` returns the same double.
  Integers are JSON integers. Booleans in frame columns are `0` / `1` so every frame column is
  numeric. Strings are UTF-8.
* **No `NaN`, no `Infinity`.** A value that is unknown or not applicable is `null`; a sweep row
  whose run failed has `null` in its result columns and the message in its `error` column. The
  writer refuses to serialise a non-finite float.
* **Encoding and layout.** UTF-8, LF, compact separators (no indentation: a 2000-frame JC trace
  is millions of values), one trailing newline. A `.json.gz` file is the same bytes gzipped
  (the viewer inflates it; the exporter reads either back identically).
* **Units** are SI (m, s, N, Pa, kg) unless the key carries a suffix (`_m`, `_s`, `_mm`, `_bar`,
  `_hz`, `_in`). The frame convention is Session V.1's (`docs/architecture.md`, "Session V.1 —
  the trace"): frame `i >= 1` of a trace file is traced frame `i - 1`, the end of sub-step
  `sub_step`, `t = (sub_step + 1) * dt`; frame 0 is synthetic (below).
* `inputs` and `source` objects are **free-form**: their keys are whatever the solver received
  or the fixture recorded. Every other object has exactly the keys listed here.

## trace

### trace

| key | type | meaning |
|---|---|---|
| `kind` | string | `"trace"` |
| `schema_version` | int | `1` |
| `meta` | object | `trace.meta` |
| `geometry` | object | `trace.geometry`: the expansion-loop layout the animation draws |
| `frames` | object | `trace.frames`: the per-frame scalar columns |
| `cells` | object | `trace.cells`, **JC runs only**; the key is absent for a lumped run |

### trace.meta

| key | type | meaning |
|---|---|---|
| `case_id` | string | The case as the CLI named it: a fixture id (`r096_jc_L24_f3`, `example_jc`) or the `--step` description |
| `solver` | string | `Trace.solver`: `"peak_response"` (lumped) or `"peak_response_jc"`; a JC call that took the short-pipe fallback reports `"peak_response"` and has no `cells` |
| `inputs` | object | The solver's keyword arguments exactly as received (`Trace.inputs`), free-form; `force_history` is an array block (the 2-D history the walk used, `(n_samples, n_columns)`); the JC flags `vav_denominator` / `parity` are present for a JC run |
| `params` | object | `trace.meta.params`: what the set-up resolved |
| `outputs` | object | `trace.meta.outputs`: the `PeakResponse` maxima, for the viewer's self-check against the reference values |
| `n_frames` | int | Frames in the file, the rest frame included (`Trace.n_frames + 1`) |
| `n_cells` | int | `2N + 1` interleaved cells of a JC run; `0` for lumped (the geometry still has the grid the case would have, below) |
| `git_sha` | string or null | `git rev-parse HEAD` of the exporting checkout, null outside a repository |
| `created_utc` | string | ISO 8601 UTC, `YYYY-MM-DDTHH:MM:SSZ` |

### trace.meta.params

| key | type | meaning |
|---|---|---|
| `mass` | float | Modal mass, kg (`SdofParams.mass`) |
| `stiffness` | float | Stiffness with the gaps open, N/m |
| `damping` | float | Viscous damping coefficient, N·s/m |
| `fric_acc` | float | Coulomb friction velocity increment per sub-step, m/s (`0.5 dynamicFric 9.81 dt`) |
| `gap` | float | Support gap, m |
| `ratio2` | float | `restrainFreqRatio²` |
| `dt` | float | Sub-step, s (`1 / (sampleFreq stepQTY)`) |
| `step_qty` | int | Sub-steps per sample |
| `out_max` | int | The VBA `outMax`; free decay is traced while `sample < 2 out_max` |
| `trace_every` | int | The trace stride in sub-steps: frame `i >= 1` is the end of sub-step `(i - 1) trace_every` |
| `capped` | int (0/1) | 1 when the run decayed past the traced history window, so the trace ends before the run did (`viz.animate.is_capped`) |

### trace.meta.outputs

| key | type | meaning |
|---|---|---|
| `max_static_equivalent_force` | float | N (VBA `resultArray(0)`) |
| `max_displacement` | float | m |
| `max_velocity` | float | m/s |
| `max_acceleration` | float | m/s² |
| `max_applied_force` | float | N, the largest `abs(forceA - forceB)` |
| `free_decay_samples` | int | Samples integrated in free decay |

### trace.geometry

The `LoopLayout` of `surge_sdof.viz.geometry.layout_from_trace` (the rules are in
`docs/architecture.md`, "the animation", Geometry): a JC run's own grid; for a lumped run the grid
the case would have (`moc.grid_size`, `moc.interp_fractions`). Arrays are length `n` = the number
of cells of that grid (equal to `meta.n_cells` for a JC run).

| key | type | meaning |
|---|---|---|
| `cell_position_m` | float[n] | Position along the column from the first A node, m (`j c dt`; a cell is `2 c dt`) |
| `cell_kind` | int[n] | `0` = A node, `1` = B cell (interleaved `A0 B0 A1 … AN`) |
| `moving_fraction` | float[n] | The interp fraction the cell's velocity is corrected by (0 fixed … 1 moving with the mass) |
| `ext_qty` | int | `extQTY`, the fixed end cells |
| `pivot_seg_qty` | int | `pivotSegQTY` |
| `pipe_seg_qty` | int | `N`; `n = 2N + 1` |
| `segments` | object | `trace.geometry.segments`: the cell indices where the five segments meet |
| `x_nominal_m` | float[n] | Circle centres at rest on the loop, m: the run along `y = 0` from `x = 0` to `x = run_length_m`, legs vertical, inlet / outlet horizontal |
| `y_nominal_m` | float[n] | As above |
| `run_length_m` | float | `cell_position_m[run_end] - cell_position_m[run_start]` |
| `leg_height_m` | float | Height of the inlet pipe above the run (centreline length between the inlet elbow cells), m |
| `leg_height_2_m` | float | The same for the outlet side (one cell shorter: the VBA B profile ramps one cell longer on the inlet side) |
| `portal_height_m` | float | `structure.solve_portal_height` of the case, m (printed, not used for the layout) |
| `spacing_m` | float | Distance between consecutive cells along the centreline, m (`c dt`) |
| `cell_length_m` | float | `2 c dt`, m |

### trace.geometry.segments

| key | type | meaning |
|---|---|---|
| `inlet_end` | int | The last fraction-0 cell of the inlet (the inlet / leg elbow cell, at `(0, leg_height_m)`) |
| `run_start` | int | The first fraction-1 cell (the leg / run elbow, at `(0, 0)`) |
| `run_end` | int | The last fraction-1 cell (at `(run_length_m, 0)`) |
| `outlet_start` | int | The first fraction-0 cell of the outlet (at `(run_length_m, leg_height_2_m)`) |

### trace.frames

Thirteen flat columns, each of length `meta.n_frames`. **Frame 0 is the synthetic rest frame**
(`t = 0`, the column at rest, no forces; the viewer never has to build it): `t = 0.0`,
`sub_step = -1` and `sample = -1` (so `t = (sub_step + 1) dt` holds for every frame), `phase` =
transit unless the run has no transit sub-step (then the phase of the first traced frame), every
other column `0`. Frame `i >= 1` is traced frame `i - 1`. The whole run is exported at the trace
stride; a file is never windowed (the viewer windows).

| key | type | meaning |
|---|---|---|
| `t` | float | Time at the end of the sub-step, s |
| `sub_step` | int | The kernel's 0-based sub-step counter (`-1` for the rest frame) |
| `sample` | int | 0-based sample index, `totInd - 1` (`-1` for the rest frame) |
| `phase` | int | `0` transit (delay), `1` history (ramp), `2` free decay |
| `x` | float | Displacement after the sub-step, m |
| `v` | float | Velocity, m/s |
| `a` | float | Acceleration, m/s² |
| `f_a` | float | Force at elbow A applied in the sub-step, N (0 in free decay) |
| `f_b` | float | Delayed force at elbow B, N |
| `f_unbalance` | float | `f_a - f_b`, N |
| `f_friction` | float | `mass dv_friction / dt`, N: the Coulomb force of the sub-step (holding force in stick) |
| `stick` | int (0/1) | 1 when the sub-step took the stick branch (`abs(v_old) < fric_acc`) |
| `d_f` | float | Junction force the sub-step used, N (0 for lumped) |

### trace.cells

Present for a JC run only. Each value is an array block of shape `[n_frames, n_cells]` (row 0
the rest frame, zeros: `moc.new_column`), the interleaved column `A0 B0 A1 … AN` after the
sub-step, exactly as the model stores it.

| key | type | meaning |
|---|---|---|
| `p` | array block | Pressures, Pa (`rhoC v`) |
| `v` | array block | Velocities relative to the pipe, m/s (after the acceleration injection and the `vAv` subtraction) |

### array block

| key | type | meaning |
|---|---|---|
| `shape` | int[2] | `[n_rows, n_cols]` |
| `data` | float[] | Flat, row-major, `n_rows * n_cols` values |

## sweep

### sweep

| key | type | meaning |
|---|---|---|
| `kind` | string | `"sweep"` |
| `schema_version` | int | `1` |
| `meta` | object | `sweep.meta` |
| `columns` | object | `sweep.columns`: one flat array per column, all of length `meta.n_rows` |
| `regen` | object | `sweep.regen`: how to reproduce any row's trace with `tools/export.py` |
| `reference` | object | `sweep.reference`: the Excel-verified cases the viewer self-checks on open |

### sweep.meta

| key | type | meaning |
|---|---|---|
| `git_sha` | string or null | Checkout that produced the rows (null when converting a CSV that does not record it) |
| `tier` | string or null | The sweep tier (Session 5b's name for the grid size); null when unknown |
| `created_utc` | string | ISO 8601 UTC of the export |
| `cpu` | string or null | CPU the rows were timed on; null when unknown |
| `histories_version` | string or null | Version of the 5b history generator (`histories.py`); null for rows without one (the golden CSV) |
| `source` | string | What the rows came from (the CSV path, or the sweep run) |
| `n_rows` | int | Rows; every column has this length |

### sweep.columns

Thirty columns, fixed names, every column the same length. Numeric columns are floats (or `null`),
`seed` is an int (or `null`), `case_id`, `history_type` and `error` are strings (or `null`). The
definitions are the contract Session 5b's sweep writes to; where a definition is marked
*inferred* the owner has not yet confirmed it (see NOTES.md, Session W.1 open issues).

| key | type | meaning |
|---|---|---|
| `case_id` | string | Identifies the row for `regen`: a fixture case id for golden rows, the 5b run id otherwise |
| `size_in` | float | Nominal pipe size, in (`10` for `curve_10in`) |
| `od_mm` | float | Outside diameter, mm |
| `thk_mm` | float | Wall thickness, mm |
| `length_m` | float | Span between the elbows (`physicalLength`), m |
| `nat_freq_hz` | float | `natFreq`, Hz |
| `history_type` | string | The 5b history generator (`"step"`, `"sine"`, `"random"`, …); `"golden"` for a `curve_10in` row (the Excel sheet's history) |
| `f_osc_hz` | float | Oscillation frequency of a periodic history, Hz; null otherwise |
| `seed` | int | RNG seed of a random history; null otherwise |
| `amplitude_fraction` | float | History amplitude as a fraction of `p_design_bar` |
| `p_design_bar` | float | Design pressure, bar |
| `p_peak_bar` | float | Peak pressure of the history, bar |
| `mu` | float | `dynamicFric` |
| `history_peak` | float | `max(abs(F))` of the applied force history, N |
| `history_mean` | float | Mean of the force history, N |
| `history_rms` | float | RMS of the force history, N |
| `f_eq_lumped` | float | `max_static_equivalent_force` of the lumped solver, N |
| `f_eq_jc` | float | The same, JC solver |
| `f_peak_lumped` | float | `max_applied_force` of the lumped solver, N (*inferred*; `FMax` excludes the junction force in both solvers, VBA 443 / 871, so on one history it equals `f_peak_jc`) |
| `f_peak_jc` | float | The same, JC solver |
| `ratio_f_eq` | float | `f_eq_jc / f_eq_lumped` |
| `ratio_f_peak` | float | `f_peak_jc / f_peak_lumped` (identically 1 under the inferred `f_peak`) |
| `f_eq_over_LD2_lumped` | float | `f_eq_lumped / (length_m (od_mm / 1000)²)`, N/m³ (*inferred* normalisation) |
| `f_eq_over_LD2_jc` | float | The same, JC |
| `daf_lumped` | float | Dynamic amplification factor `f_eq_lumped / history_peak` (*inferred*) |
| `daf_jc` | float | The same, JC |
| `rho_c` | float | `fluidDensity celerity`, Pa·s/m (the junction impedance) |
| `t_lumped_s` | float | Wall-clock seconds of the lumped run |
| `t_jc_s` | float | Wall-clock seconds of the JC run |
| `error` | string | null for a good row; the exception message of a failed run (its result columns null) |

A `curve_10in` golden row (`tests/fixtures/curve_10in/cases.csv`, converted by `tools/export.py
sweep --from-csv`) fills `case_id`, `size_in = 10`, `length_m`, `nat_freq_hz`, `history_type =
"golden"`, `mu`, `rho_c`, and `f_eq_*` / `f_peak_*` for its own solver only (the other solver's
columns and the ratios are null: the 75 lumped and 3 JC rows are different cases). Everything the
sheet does not record is null.

### sweep.regen

| key | type | meaning |
|---|---|---|
| `template` | string | A `str.format` template over the column names of one row, giving the `tools/export.py` command that writes that row's trace file |
| `columns_used` | string[] | The placeholders the template uses |
| `note` | string or null | Caveats (for the golden CSV: `--golden {case_id}` reproduces the row; 5b rows get their own template once the history options exist) |

### sweep.reference

The viewer's self-check: the Excel values the port is verified against (`tests/test_golden.py`,
tolerance record there). Two lists of `reference entry`.

| key | type | meaning |
|---|---|---|
| `example_cases` | entry[] | The three `Example`-sheet cases (`example_pressure`, `example_lumped`, `example_jc`; RTOL 1e-12) |
| `jc_golden_rows` | entry[] | The three `GetPeakResponseJC` rows of `curve_10in` (96, 97, 98; RTOL 5e-12) |

### reference entry

| key | type | meaning |
|---|---|---|
| `case_id` | string | Fixture case id |
| `solver` | string | `"pressure"`, `"lumped"` or `"jc"` |
| `source` | object | Free-form: the fixture's provenance (sheet and cell, or `source_row`) |
| `inputs` | object | Free-form: the solver keyword arguments of the case (a golden row's are its row values merged with `params.json`); 2-D inputs as array blocks |
| `output_names` | string[] or null | Names of `excel_values` (the five maxima); null for the pressure case (a time series) |
| `excel_values` | float[] | The Excel-computed values exactly as cached in the workbook |
| `rtol` | float | The relative tolerance the golden test holds the port to |

## Size expectations

JSON at full `repr` costs about 20 bytes a float (`-1525123.4567891234,`) and 2–10 bytes an
integer. A trace file is therefore roughly

    bytes ≈ 20 × n_frames × (13 + 2 × n_cells) + inputs (force history: 20 × n_samples)

* Example-sheet cases (37 cells, ~500 frames): about 1 MB for JC, 0.15 MB for lumped.
* Row 96 of `curve_10in` (1333 cells): 53 KB a frame, so the 2000 frames `tools/animate.py`
  targets would be ~107 MB. `tools/export.py` therefore picks its default `--trace-every` as the
  2000-frame stride **or the coarser stride that keeps the estimated file under 45 MB**
  (estimated over the forced phases; free decay adds frames), and prints the size written. The
  committed `docs/viz/data/golden_r096_jc.json.gz` is that default; `--trace-every` overrides it
  in either direction. gzip roughly halves decimal floats.
* A sweep file is small: 30 columns × rows (a 1000-row sweep is ~0.5 MB) plus the reference block
  (~10 KB).

**Upgrade path.** When 45 MB of JSON is too coarse (a long run at a fine stride, or many cells),
the binary variant is the same header (`kind`, `schema_version`, `meta`, `geometry`, and for a
sweep `columns` metadata) as JSON followed by float64 little-endian blobs for the frame columns
and the cell arrays, 8 bytes a value with no parsing; the viewer's loader would branch on the
container, not on the schema. Not built in W.1.
