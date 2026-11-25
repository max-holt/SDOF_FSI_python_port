# Results data format (Session W.1)

The data files the single-file JS viewer (Session W.2 trace mode, Session W.3 sweep mode) loads. A file is written once by
`tools/export.py` (`surge_sdof.export`) and read by the viewer from disk, a SharePoint folder or
an OCI bucket with no Python on the viewing machine: the viewer controls playback, speed and the
time window live, so nothing about the presentation is baked into the file. This document is the
contract; `tests/test_export.py` parses the key tables below (every `### <block>` heading and the
`` `key` `` column of its table), so a key is part of the format exactly when it is listed here.

Two kinds of file, each with `kind` and `schema_version` (`trace` 2, `sweep` 3, since the schema
bump of the clean-code review, session R.9; the names follow `docs/nomenclature.md`). The
viewer reads only these versions. Before the bump, `trace` 1 had the same blocks under VBA-era
keys (`n_frames`, `cells.p`, `x_nominal_m`, flat `inputs`, ...) and `sweep` 2 the same 72
columns under the old names (`length_m`, `mu`, `f_eq_jc`, ...); `sweep` 1 was the thirty-column
W.1 layout. The old-to-new key table is `docs/review/public_interface.md` §3.3.

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
* **Units** are SI (m, s, N, Pa, kg) unless the key carries a suffix for a non-SI unit (`_mm`,
  `_bar`, `_in`); the five history duration terms keep `_s` (`lead_in_s`, `transit_s`, `tail_s`,
  `decay_s`, `duration_s`). The frame convention is Session V.1's (`docs/architecture.md`, "Session V.1 —
  the trace"): frame `i >= 1` of a trace file is traced frame `i - 1`, the end of substep
  `substep_index`, `time = (substep_index + 1) * substep_duration`; frame 0 is synthetic (below).
* `inputs` and `source` objects are **free-form**: their keys are whatever the solver received
  or the fixture recorded. Every other object has exactly the keys listed here.

## trace

### trace

| key | type | meaning |
|---|---|---|
| `kind` | string | `"trace"` |
| `schema_version` | int | `2` |
| `meta` | object | `trace.meta` |
| `geometry` | object | `trace.geometry`: the expansion-loop layout the animation draws |
| `frames` | object | `trace.frames`: the per-frame scalar columns |
| `grid_points` | object | `trace.grid_points`, **JC runs only**; the key is absent for a lumped run |

### trace.meta

| key | type | meaning |
|---|---|---|
| `case_id` | string | The case as the CLI named it: a fixture id (`r096_jc_L24_f3`, `example_jc`) or the `--step` description |
| `solver` | string | `Trace.solver`: `"peak_response"` (lumped) or `"peak_response_jc"`; a JC call that took the short-pipe fallback reports `"peak_response"` and has no `grid_points` |
| `inputs` | object | The solver's arguments as received, grouped as the call (`Trace.inputs`), free-form: `force_history` (an array block, the 2-D history the walk used, `(n_samples, n_columns)`), `sample_rate`, `span`, `restraint`, `integration`, and for a JC run `fluid` and `coupling` (`mean_velocity_divisor`, `parity`, `fraction_profile`) |
| `params` | object | `trace.meta.params`: what the set-up resolved |
| `outputs` | object | `trace.meta.outputs`: the `PeakResponse` maxima, for the viewer's self-check against the reference values |
| `frame_count` | int | Frames in the file, the rest frame included (`Trace.frame_count + 1`) |
| `grid_point_count` | int | `2N + 1` interleaved grid points of a JC run; `0` for lumped (the geometry still has the grid the case would have, below) |
| `git_sha` | string or null | `git rev-parse HEAD` of the exporting checkout, null outside a repository |
| `created_utc` | string | ISO 8601 UTC, `YYYY-MM-DDTHH:MM:SSZ` |

### trace.meta.params

| key | type | meaning |
|---|---|---|
| `mass` | float | Modal mass, kg (`SdofParams.mass`) |
| `stiffness` | float | Stiffness with the gaps open, N/m |
| `damping` | float | Viscous damping coefficient, N·s/m |
| `friction_velocity_step` | float | Coulomb friction velocity increment per sub-step, m/s (`0.5 dynamicFric 9.81 dt`) |
| `support_gap` | float | Support gap, m |
| `closed_gap_stiffness_ratio` | float | `restrainFreqRatio²` |
| `substep_duration` | float | Sub-step, s (`1 / (sampleFreq stepQTY)`) |
| `substep_count` | int | Sub-steps per sample |
| `nominal_forced_sample_count` | int | The VBA `outMax`; free decay is traced while `sample < 2 out_max` |
| `trace_every` | int | The trace stride in sub-steps: frame `i >= 1` is the end of sub-step `(i - 1) trace_every` |
| `is_capped` | int (0/1) | 1 when the run decayed past the traced history window, so the trace ends before the run did (`export.is_capped`) |

### trace.meta.outputs

| key | type | meaning |
|---|---|---|
| `max_static_equivalent_force` | float | N (VBA `resultArray(0)`) |
| `max_displacement` | float | m |
| `max_velocity` | float | m/s |
| `max_acceleration` | float | m/s² |
| `max_unbalance_force` | float | N, the largest `abs(forceA - forceB)` |
| `free_decay_sample_count` | int | Samples integrated in free decay |

### trace.geometry

The `LoopLayout` of `surge_sdof.viz.geometry.layout_from_trace` (the rules are in
`docs/architecture.md`, "the animation", Geometry): a JC run's own grid; for a lumped run the grid
the case would have (`moc.grid_size`, `moc.moving_fractions`). Arrays are length `n` = the number
of grid points of that grid (equal to `meta.grid_point_count` for a JC run).

| key | type | meaning |
|---|---|---|
| `grid_point_position` | float[n] | Position along the column from the first A node, m (`j c dt`; a cell is `2 c dt`) |
| `grid_point_kind` | int[n] | `0` = A node, `1` = B cell (interleaved `A0 B0 A1 … AN`) |
| `grid_point_moving_fraction` | float[n] | The moving fraction the cell's velocity is corrected by (0 fixed … 1 moving with the mass) |
| `inactive_end_cell_count` | int | `extQTY`, the fixed end cells |
| `end_to_elbow_cell_count` | int | `pivotSegQTY` |
| `column_cell_count` | int | `N`; `n = 2N + 1` |
| `segments` | object | `trace.geometry.segments`: the cell indices where the five segments meet |
| `x_at_rest` | float[n] | Circle centres at rest on the loop, m: the run along `y = 0` from `x = 0` to `x = run_length_m`, legs vertical, inlet / outlet horizontal |
| `y_at_rest` | float[n] | As above |
| `run_length` | float | `cell_position_m[run_end] - cell_position_m[run_start]` |
| `inlet_leg_height` | float | Height of the inlet pipe above the run (centreline length between the inlet elbow cells), m |
| `outlet_leg_height` | float | The same for the outlet side (equal to `inlet_leg_height` with the default fraction profile; one cell shorter with `fraction_profile="legacy"`, whose B profile ramps one cell longer on the inlet side) |
| `portal_frame_height` | float | `structure.solve_portal_height` of the case, m (printed, not used for the layout) |
| `grid_point_spacing` | float | Distance between consecutive cells along the centreline, m (`c dt`) |
| `cell_length` | float | `2 c dt`, m |

### trace.geometry.segments

| key | type | meaning |
|---|---|---|
| `inlet_elbow_index` | int | The last fraction-0 cell of the inlet (the inlet / leg elbow cell, at `(0, leg_height_m)`) |
| `run_start_index` | int | The first fraction-1 cell (the leg / run elbow, at `(0, 0)`) |
| `run_end_index` | int | The last fraction-1 cell (at `(run_length_m, 0)`) |
| `outlet_elbow_index` | int | The first fraction-0 cell of the outlet (at `(run_length_m, leg_height_2_m)`) |

### trace.frames

Thirteen flat columns, each of length `meta.frame_count`. **Frame 0 is the synthetic rest frame**
(`time = 0`, the column at rest, no forces; the viewer never has to build it): `time = 0.0`,
`substep_index = -1` and `sample_index = -1` (so `time = (substep_index + 1) substep_duration`
holds for every frame), `load_phase` =
transit unless the run has no transit sub-step (then the phase of the first traced frame), every
other column `0`. Frame `i >= 1` is traced frame `i - 1`. The whole run is exported at the trace
stride; a file is never windowed (the viewer windows).

| key | type | meaning |
|---|---|---|
| `time` | float | Time at the end of the sub-step, s |
| `substep_index` | int | The kernel's 0-based sub-step counter (`-1` for the rest frame) |
| `sample_index` | int | 0-based sample index, `totInd - 1` (`-1` for the rest frame) |
| `load_phase` | int | `0` transit, `1` forced, `2` free decay |
| `displacement` | float | Displacement after the sub-step, m |
| `velocity` | float | Velocity, m/s |
| `acceleration` | float | Acceleration, m/s² |
| `elbow_a_force` | float | Force at elbow A applied in the sub-step, N (0 in free decay) |
| `elbow_b_force` | float | Delayed force at elbow B, N |
| `unbalance_force` | float | `f_a - f_b`, N |
| `friction_force` | float | `mass dv_friction / dt`, N: the Coulomb force of the sub-step (holding force in stick) |
| `is_sticking` | int (0/1) | 1 when the sub-step took the stick branch (`abs(v_old) < fric_acc`) |
| `junction_force` | float | Junction force the sub-step used, N (0 for lumped) |

### trace.grid_points

Present for a JC run only. Each value is an array block of shape `[frame_count, grid_point_count]` (row 0
the rest frame, zeros: `moc.column_at_rest`), the interleaved column `A0 B0 A1 … AN` after the
sub-step, exactly as the model stores it.

| key | type | meaning |
|---|---|---|
| `pressure` | array block | Pressures, Pa (`rhoC v`) |
| `velocity` | array block | Velocities relative to the pipe, m/s (after the acceleration injection and the `vAv` subtraction) |

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
| `schema_version` | int | `3` (`export.SWEEP_SCHEMA_VERSION`; 2 had the same columns under the names before the R.9 bump, 1 was the thirty-column W.1 layout) |
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
are floats (or `null`); `tier`, `size_in`, `noise_seed`, `sample_count`, `column_cell_count`, `end_to_elbow_cell_count`
and `is_short_pipe` are ints (or `null`); `case_id`, `subset`, `history_type`,
`histories_version`, `cpu`, `git_sha` and `error` are strings (or `null`). The fifteen generator
columns (`history_type` … `peak_pressure_target`, SI values exactly as the generator received them) rebuild the
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
| `outside_diameter_mm` | float | Outside diameter, mm (`curve_10in!J7:M7`) |
| `wall_thickness_mm` | float | Wall thickness, mm (`curve_10in!J8:M8`) |
| `span_length` | float | `physicalLength`, m |
| `natural_frequency` | float | `natFreq`, Hz (with the contained fluid, as the solvers model it) |
| `history_type` | string | Generator kind: `step`, `step_sine`, `step_noise` |
| `oscillation_frequency` | float | Sine frequency, Hz; empty otherwise |
| `noise_seed` | int | Noise RNG seed; empty otherwise |
| `amplitude_fraction` | float | Peak as a fraction of the cap `1.33 p_design` |
| `friction_coefficient` | float | `dynamicFric`, the Coulomb coefficient (the VBA uses `0.5 mu 9.81 dt` directly) |
| `design_pressure_bar` | float | `2 t S / OD` with `S = 138` MPa, bar |
| `peak_pressure_target_bar` | float | `amplitude_fraction × 1.33 × p_design`, bar |
| `pressure_max_bar` | float | `max(p)` of the history, bar (equals `peak_pressure_target_bar` to rounding) |
| `pressure_mean_bar` | float | Mean of the pressure history over its whole length (lead-in included), bar |
| `pressure_rms_bar` | float | RMS of the pressure history over its whole length, bar |
| `scaled_noise_rms_bar` | float | `step_noise` only: RMS of the scaled noise component over the active window (after the lead-in), bar |
| `sample_rate` | float | Generator: sample rate, Hz |
| `lead_in_s` | float | Generator: zero lead-in, s |
| `transit_s` | float | Generator: transit allowance in the duration, s (the tier's longest span, `48 / 1237`, rounded up to 0.04, so one history serves every length) |
| `tail_s` | float | Generator: tail after the decay, s |
| `decay_s` | float | `decay_cycles / f_osc` (sine), `decay_cycles / f_ref` (noise), 0 (step), s |
| `duration_s` | float | `lead_in_s + transit_s + decay_s + tail_s`, s |
| `sample_count` | int | `round(duration_s × sample_freq)` |
| `step_pressure` | float | Generator: held step, Pa (the cap for `step`, half the cap otherwise) |
| `oscillation_amplitude` | float | Generator: sine amplitude, Pa (set so the first positive peak of the enveloped sine is the cap); empty otherwise |
| `requested_noise_rms` | float | Generator: requested white-noise RMS, Pa (inert: the noise is rescaled to the cap); empty otherwise |
| `noise_cutoff_frequency` | float | Generator: noise low-pass cut-off, Hz (the Nyquist frequency when unfiltered); empty otherwise |
| `envelope_reference_frequency` | float | Generator: envelope reference frequency of the noise, Hz; empty otherwise |
| `envelope_decay_cycles` | float | Generator: cycles after which the envelope is `1 − decay_fraction`; empty for `step` |
| `envelope_decay_fraction` | float | Generator: the envelope's decay over `envelope_decay_cycles`; empty for `step` |
| `peak_pressure_target` | float | Generator: the noise's peak target, Pa; empty otherwise (`peak_pressure_target_bar` carries the cap for every row) |
| `histories_version` | string | `surge_sdof.histories.HISTORIES_VERSION` |
| `flow_area` | float | `π ((OD/2 − t)/1000)²`, m² (`curve_10in!H13`) |
| `mass_per_length` | float | Pipe plus contents, kg/m (`curve_10in!H11`, steel 7800, water 1000) |
| `flexural_rigidity` | float | `E I`, N·m² (`curve_10in!J15`, `E = 195e9`) |
| `characteristic_impedance` | float | `fluidDensity × celerity`, Pa·s/m |
| `portal_frame_height` | float | `structure.solve_portal_height` of the case, m |
| `total_mass` | float | `(L + 4h/3) × massPerUnitLen`: the mass the natural frequency is modelled on (pipe and contents, VBA 727), used for the momentum and kinetic energy of both solvers; the MoC column's fluid momentum is not added |
| `column_cell_count` | int | `moc.grid_size`: MoC cells in the whole column (the span, about `L / (2 c dt)` cells, plus `end_to_elbow_cell_count + 1` cells at each end), not only between the elbows |
| `end_to_elbow_cell_count` | int | `moc.grid_size`: cells from each end to the pivot |
| `is_short_pipe` | int | 1 when `moc.is_short_pipe` holds and the JC call fell back to the lumped solver (none in Tier 1) |
| `force_history_max` | float | `max \|F\|` of the force history `p × A`, N |
| `force_history_mean` | float | Mean of the force history, N |
| `force_history_rms` | float | RMS of the force history, N |
| `max_static_equivalent_force_lumped` | float | `max_static_equivalent_force`, lumped, N |
| `max_static_equivalent_force_jc` | float | The same, JC |
| `max_static_equivalent_force_ratio` | float | `max_static_equivalent_force_jc / max_static_equivalent_force_lumped`: the flexibility measure |
| `max_velocity_lumped` | float | `max_velocity`, lumped, m/s |
| `max_velocity_jc` | float | The same, JC |
| `max_velocity_ratio` | float | `v_peak_jc / v_peak_lumped`: the support-design measure (the lead author's peak local force at impact is derived from the velocity, Stage 6) |
| `max_momentum_lumped` | float | `mass_total_kg × v_peak_lumped`, kg·m/s |
| `max_momentum_jc` | float | The same, JC |
| `max_kinetic_energy_lumped` | float | `0.5 × mass_total_kg × v_peak_lumped²`, J |
| `max_kinetic_energy_jc` | float | The same, JC |
| `max_displacement_lumped` | float | `max_displacement`, lumped, m |
| `max_displacement_jc` | float | The same, JC |
| `max_acceleration_lumped` | float | `max_acceleration`, lumped, m/s² |
| `max_acceleration_jc` | float | The same, JC |
| `max_unbalance_force_lumped` | float | `max_unbalance_force`: the VBA `FMax`, the peak applied unbalance, an input property; not ratioed |
| `max_unbalance_force_jc` | float | The same, JC (equal to `max_unbalance_force_lumped` on one history) |
| `force_per_length_diameter_squared_lumped` | float | `max_static_equivalent_force_lumped / (L d²)`, `d` = OD, N/m³ |
| `force_per_length_diameter_squared_jc` | float | The same, JC |
| `daf_lumped` | float | `max_static_equivalent_force_lumped / (pressure_max A)`, the effective DAF |
| `daf_jc` | float | The same, JC |
| `wall_time_lumped` | float | Wall-clock seconds of the lumped call (history generation excluded) |
| `wall_time_jc` | float | Wall-clock seconds of the JC call |
| `cpu` | string | CPU model the row was timed on |
| `git_sha` | string | Short sha of the checkout (`-dirty` when `src`, `tests` or `tools` had uncommitted changes) |
| `error` | string | Empty for a good row; `lumped: …` and / or `jc: …` with the exception for a failed run |

A `curve_10in` golden row (`tests/fixtures/curve_10in/cases.csv`, converted by `tools/export.py
sweep --from-csv`) fills `case_id`, `size_in = 10`, `span_length`, `natural_frequency`, `history_type =
"golden"`, `friction_coefficient`, `characteristic_impedance`, and `max_static_equivalent_force_*` / `max_unbalance_force_*` for its own solver only (the other solver's
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
reference block's three JC golden rows among them), re-exported at schema 2 in Session H.2 and at schema 3 in the R.9 schema bump.

The viewer's sweep mode (Session W.3, `docs/viewer/README.md`) reads schema 3 only. It plots the
columns against `natural_frequency`, filters on `history_type`, `oscillation_frequency`, `noise_seed`, `friction_coefficient` and
`amplitude_fraction`, formats `regen.template` with a row's columns as `str.format` would
(`{name}`; a null is the empty string) and, on open, checks every `reference` entry whose
`case_id` is among the rows: the entry's `output_names` (the five `PeakResponse` maxima) name the column stems of its
solver (`max_static_equivalent_force_<solver>`, ...) and each non-null one must satisfy `|row − excel| ≤
rtol |excel|`.

## Size expectations

JSON at full `repr` costs about 20 bytes a float (`-1525123.4567891234,`) and 2–10 bytes an
integer. A trace file is therefore roughly

    bytes ≈ 20 × frame_count × (13 + 2 × grid_point_count) + inputs (force history: 20 × n_samples)

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
