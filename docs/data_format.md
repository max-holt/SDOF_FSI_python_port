# Results data format (Session W.1)

The data files the single-file JS viewer (Session W.2 trace mode, Session W.3 sweep mode) loads. A file is written once by
`tools/export.py` (`surge_sdof.export`) and read by the viewer from disk, a SharePoint folder or
an OCI bucket with no Python on the viewing machine: the viewer controls playback, speed and the
time window live, so nothing about the presentation is baked into the file. This document is the
contract; `tests/test_export.py` parses the key tables below (every `### <block>` heading and the
`` `key` `` column of its table), so a key is part of the format exactly when it is listed here.

Two kinds of file, each with `kind` and `schema_version` (`trace` 1; `sweep` 2 since Session 5b):

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
| `inputs` | object | The solver's keyword arguments exactly as received (`Trace.inputs`), free-form; `force_history` is an array block (the 2-D history the walk used, `(n_samples, n_columns)`); the JC flags `vav_denominator` / `parity` / `fraction_profile` are present for a JC run |
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
| `capped` | int (0/1) | 1 when the run decayed past the traced history window, so the trace ends before the run did (`export.is_capped`) |

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
| `schema_version` | int | `2` (`export.SWEEP_SCHEMA_VERSION`; 1 was the thirty-column W.1 layout) |
| `meta` | object | `sweep.meta` |
| `columns` | object | `sweep.columns`: one flat array per column, all of length `meta.n_rows` |
| `regen` | object | `sweep.regen`: how to reproduce any row's trace with `tools/export.py` |
| `reference` | object | `sweep.reference`: the Excel-verified cases the viewer self-checks on open |

### sweep.meta

| key | type | meaning |
|---|---|---|
| `git_sha` | string or null | Checkout that produced the rows (null when converting a CSV that does not record it) |
| `tier` | string or null | The sweep tier (`"1"`, `"2"`; from the rows' `tier` column for a 5b CSV); null when unknown |
| `created_utc` | string | ISO 8601 UTC of the export |
| `cpu` | string or null | CPU the rows were timed on; null when unknown |
| `histories_version` | string or null | Version of the 5b history generator (`histories.py`); null for rows without one (the golden CSV) |
| `source` | string | What the rows came from (the CSV path, or the sweep run) |
| `n_rows` | int | Rows; every column has this length |

### sweep.columns

Seventy-two columns, fixed names, every column the same length: the columns of the Session 5b
sweep CSV (`tools/sweep_jc.py run`, `sweep_jc.COLUMNS is export.SWEEP_COLUMNS`). Numeric columns
are floats (or `null`); `tier`, `size_in`, `seed`, `n_samples`, `pipe_seg_qty`, `pivot_seg_qty`
and `jc_short_pipe` are ints (or `null`); `case_id`, `subset`, `history_type`,
`histories_version`, `cpu`, `git_sha` and `error` are strings (or `null`). The fifteen generator
columns (`history_type` … `p_cap`, SI values exactly as the generator received them) rebuild the
row's pressure history bitwise through `surge_sdof.histories.from_params`
(`sweep_jc.history_from_row`; `tests/test_sweep_jc.py` pins the round trip). Schema 1 (Session
W.1) had thirty columns with the same names where both exist, plus `ratio_f_peak`, which is gone
(`f_peak` is an input property and is not ratioed).

| key | type | meaning |
|---|---|---|
| `case_id` | string | `s<size>_L<length>_f<natFreq>_<step \| sine<f_osc> \| noise<seed>>_a<amplitude>_mu<mu>` |
| `tier` | int | The sweep tier (1 or 2) |
| `subset` | string | `subset<pct>` for a stratified subset run, empty for a full tier |
| `size_in` | int | Nominal pipe size, in |
| `od_mm` | float | Outside diameter, mm (`curve_10in!J7:M7`) |
| `thk_mm` | float | Wall thickness, mm (`curve_10in!J8:M8`) |
| `length_m` | float | `physicalLength`, m |
| `nat_freq_hz` | float | `natFreq`, Hz (with the contained fluid, as the solvers model it) |
| `history_type` | string | Generator kind: `step`, `step_sine`, `step_noise` |
| `f_osc_hz` | float | Sine frequency, Hz; empty otherwise |
| `seed` | int | Noise RNG seed; empty otherwise |
| `amplitude_fraction` | float | Peak as a fraction of the cap `1.33 p_design` |
| `mu` | float | `dynamicFric`, the Coulomb coefficient (the VBA uses `0.5 mu 9.81 dt` directly) |
| `p_design_bar` | float | `2 t S / OD` with `S = 138` MPa, bar |
| `p_cap_bar` | float | `amplitude_fraction × 1.33 × p_design`, bar |
| `p_peak_bar` | float | `max(p)` of the history, bar (equals `p_cap_bar` to rounding) |
| `p_mean_bar` | float | Mean of the pressure history over its whole length (lead-in included), bar |
| `p_rms_bar` | float | RMS of the pressure history over its whole length, bar |
| `noise_rms_bar` | float | `step_noise` only: RMS of the scaled noise component over the active window (after the lead-in), bar |
| `sample_freq` | float | Generator: sample rate, Hz |
| `lead_in_s` | float | Generator: zero lead-in, s |
| `transit_s` | float | Generator: transit allowance in the duration, s (the tier's longest span, `48 / 1237`, rounded up to 0.04, so one history serves every length) |
| `tail_s` | float | Generator: tail after the decay, s |
| `decay_s` | float | `decay_cycles / f_osc` (sine), `decay_cycles / f_ref` (noise), 0 (step), s |
| `duration_s` | float | `lead_in_s + transit_s + decay_s + tail_s`, s |
| `n_samples` | int | `round(duration_s × sample_freq)` |
| `p_step` | float | Generator: held step, Pa (the cap for `step`, half the cap otherwise) |
| `p_osc` | float | Generator: sine amplitude, Pa (set so the first positive peak of the enveloped sine is the cap); empty otherwise |
| `p_noise_rms` | float | Generator: requested white-noise RMS, Pa (inert: the noise is rescaled to the cap); empty otherwise |
| `f_cut_hz` | float | Generator: noise low-pass cut-off, Hz (the Nyquist frequency when unfiltered); empty otherwise |
| `f_ref_hz` | float | Generator: envelope reference frequency of the noise, Hz; empty otherwise |
| `decay_cycles` | float | Generator: cycles after which the envelope is `1 − decay_fraction`; empty for `step` |
| `decay_fraction` | float | Generator: the envelope's decay over `decay_cycles`; empty for `step` |
| `p_cap` | float | Generator: the noise's peak target, Pa; empty otherwise (`p_cap_bar` carries the cap for every row) |
| `histories_version` | string | `surge_sdof.histories.HISTORIES_VERSION` |
| `fluid_area_m2` | float | `π ((OD/2 − t)/1000)²`, m² (`curve_10in!H13`) |
| `mass_per_unit_len` | float | Pipe plus contents, kg/m (`curve_10in!H11`, steel 7800, water 1000) |
| `ei` | float | `E I`, N·m² (`curve_10in!J15`, `E = 195e9`) |
| `rho_c` | float | `fluidDensity × celerity`, Pa·s/m |
| `portal_height_m` | float | `structure.solve_portal_height` of the case, m |
| `mass_total_kg` | float | `(L + 4h/3) × massPerUnitLen`: the mass the natural frequency is modelled on (pipe and contents, VBA 727), used for the momentum and kinetic energy of both solvers; the MoC column's fluid momentum is not added |
| `pipe_seg_qty` | int | `moc.grid_size`: MoC cells between the elbows |
| `pivot_seg_qty` | int | `moc.grid_size`: cells from each end to the pivot |
| `jc_short_pipe` | int | 1 when `moc.is_short_pipe` holds and the JC call fell back to the lumped solver (none in Tier 1) |
| `history_peak` | float | `max \|F\|` of the force history `p × A`, N |
| `history_mean` | float | Mean of the force history, N |
| `history_rms` | float | RMS of the force history, N |
| `f_eq_lumped` | float | `max_static_equivalent_force`, lumped, N |
| `f_eq_jc` | float | The same, JC |
| `ratio_f_eq` | float | `f_eq_jc / f_eq_lumped`: the flexibility measure |
| `v_peak_lumped` | float | `max_velocity`, lumped, m/s |
| `v_peak_jc` | float | The same, JC |
| `ratio_v_peak` | float | `v_peak_jc / v_peak_lumped`: the support-design measure (the lead author's peak local force at impact is derived from the velocity, Stage 6) |
| `momentum_lumped` | float | `mass_total_kg × v_peak_lumped`, kg·m/s |
| `momentum_jc` | float | The same, JC |
| `ke_peak_lumped` | float | `0.5 × mass_total_kg × v_peak_lumped²`, J |
| `ke_peak_jc` | float | The same, JC |
| `x_peak_lumped` | float | `max_displacement`, lumped, m |
| `x_peak_jc` | float | The same, JC |
| `a_peak_lumped` | float | `max_acceleration`, lumped, m/s² |
| `a_peak_jc` | float | The same, JC |
| `f_peak_lumped` | float | `max_applied_force`: the VBA `FMax`, the peak applied unbalance, an input property; not ratioed |
| `f_peak_jc` | float | The same, JC (equal to `f_peak_lumped` on one history) |
| `f_eq_over_LD2_lumped` | float | `f_eq_lumped / (L d²)`, `d` = OD, N/m³ |
| `f_eq_over_LD2_jc` | float | The same, JC |
| `daf_lumped` | float | `f_eq_lumped / (p_peak A)`, the effective DAF |
| `daf_jc` | float | The same, JC |
| `t_lumped_s` | float | Wall-clock seconds of the lumped call (history generation excluded) |
| `t_jc_s` | float | Wall-clock seconds of the JC call |
| `cpu` | string | CPU model the row was timed on |
| `git_sha` | string | Short sha of the checkout (`-dirty` when `src`, `tests` or `tools` had uncommitted changes) |
| `error` | string | Empty for a good row; `lumped: …` and / or `jc: …` with the exception for a failed run |

A `curve_10in` golden row (`tests/fixtures/curve_10in/cases.csv`, converted by `tools/export.py
sweep --from-csv`) fills `case_id`, `size_in = 10`, `length_m`, `nat_freq_hz`, `history_type =
"golden"`, `mu`, `rho_c`, and `f_eq_*` / `f_peak_*` for its own solver only (the other solver's
columns and `ratio_*` are null: the 75 lumped and 3 JC rows are different cases). Everything the
sheet does not record is null.

### sweep.regen

| key | type | meaning |
|---|---|---|
| `template` | string | A `str.format` template over the column names of one row, giving the `tools/export.py` command that writes that row's trace file |
| `columns_used` | string[] | The placeholders the template uses |
| `note` | string or null | Caveats (for the golden CSV: `--golden {case_id}` reproduces the row; for a 5b CSV: the template reruns the tier, one row is `sweep_jc.run_case` on its columns) |

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

## sweep CSV (Session 5b)

`tools/sweep_jc.py run` writes `docs/sweep/tier<N>[_subset<pct>]_<sha>[_<tag>].csv`: one row per
case, both solvers, exactly the `sweep.columns` above in that order (`--tag` suffixes a rerun,
e.g. after a profile correction, so that it never overwrites an earlier file). Floats are written
with `repr`; an empty cell is null; a failed run has its message in `error` and its result
columns empty, never a skipped row. It is the record of the junction-coupling assessment
(`docs/jc_sweep.md`). `tools/export.py sweep --from-csv <csv> --out <json>` converts it to the
`sweep` document (`meta.tier`, `cpu`, `histories_version` and `git_sha` taken from the rows
unless given), e.g. `docs/viz/data/tier1_sweep.json` from the Tier 1 CSV.
`docs/viz/data/reference_sweep.json` is the conversion of the golden `cases.csv` (78 rows, the
reference block's three JC golden rows among them), re-exported at schema 2 in Session H.2.

The viewer's sweep mode (Session W.3, `docs/viewer/README.md`) reads schema 2 only. It plots the
columns against `nat_freq_hz`, filters on `history_type`, `f_osc_hz`, `seed`, `mu` and
`amplitude_fraction`, formats `regen.template` with a row's columns as `str.format` would
(`{name}`; a null is the empty string) and, on open, checks every `reference` entry whose
`case_id` is among the rows: the entry's `output_names` map to the columns `f_eq`, `x_peak`,
`v_peak`, `a_peak`, `f_peak` of its solver and each non-null one must satisfy `|row − excel| ≤
rtol |excel|`.

## Size expectations

JSON at full `repr` costs about 20 bytes a float (`-1525123.4567891234,`) and 2–10 bytes an
integer. A trace file is therefore roughly

    bytes ≈ 20 × n_frames × (13 + 2 × n_cells) + inputs (force history: 20 × n_samples)

* Example-sheet cases (37 cells, ~500 frames): about 1 MB for JC, 0.15 MB for lumped.
* Row 96 of `curve_10in` (1333 cells): 53 KB a frame, so the 2000 frames the default stride
  targets (`tools/cases.TRACE_FRAMES`) would be ~107 MB. `tools/export.py` therefore picks its default `--trace-every` as the
  2000-frame stride **or the coarser stride that keeps the estimated file under 45 MB**
  (estimated over the forced phases; free decay adds frames), and prints the size written. The
  committed `docs/viz/data/golden_r096_jc.json.gz` is that default: stride 1212, 832 frames (24 ms a
  frame), 46.9 MB of JSON, 20.6 MB gzipped; `--trace-every` overrides it in either direction.
  gzip roughly halves decimal floats. Measured on the committed files: `example_jc_step.json`
  1.80 MB (1124 frames, 37 cells), `example_lumped_step.json` 0.14 MB (1004 frames),
  `reference_sweep.json` 0.02 MB (78 rows).
* A sweep file is small: 72 columns × rows (the 1600-row Tier 1 file is ~1.5 MB) plus the
  reference block (~10 KB).

**Upgrade path.** When 45 MB of JSON is too coarse (a long run at a fine stride, or many cells),
the binary variant is the same header (`kind`, `schema_version`, `meta`, `geometry`, and for a
sweep `columns` metadata) as JSON followed by float64 little-endian blobs for the frame columns
and the cell arrays, 8 bytes a value with no parsing; the viewer's loader would branch on the
container, not on the schema. Not built in W.1.
