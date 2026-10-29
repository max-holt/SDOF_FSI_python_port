# surge_sdof — handover

Written for the lead author at the `v0.3-handover` tag and brought up to date at `v0.4-sweep`
(the viewer's sweep mode and the Tier 2 sweep, 29 Oct 2026). It says what the repository
contains, how to install and verify it, and what is not done. The history of how it was built
is in git; `NOTES.md` keeps a short summary.

## What the package is

`surge_sdof` is a Python port of the Excel VBA solver in `legacy/vba/Existing Code.bas`: a 1-D
method-of-characteristics (MoC) water-hammer model and a single-degree-of-freedom (SDOF)
pipe-response model with Coulomb friction, support gaps and MoC junction-coupling
fluid-structure interaction. It has two layers. `legacy_port.py` and `vba_compat.py` are the
frozen line-for-line transcription of the VBA, verified against Excel. `response.py`,
`pressure.py` and the modules behind them (`structure`, `loads`, `coupling`, `moc`,
`histories`) are the restructured solver, value-identical to the transcription when run with
the legacy flags (bitwise on the differential suite) and compiled with Numba (the three full
junction-coupling golden cases run in about a second each, down from 13–30 minutes). Runtime
dependencies are numpy and numba only. `docs/architecture.md` describes the modules.

## The three entry points

All three take the VBA arguments, by the VBA names in snake case, and return 0-based numpy
results (no 1-based pad). Units are consistent SI for the two peak solvers; `pressure_response`
keeps the VBA's mixed units. The docstrings give the unit of every argument.

* `surge_sdof.response.peak_response(force_history, step_qty, sample_freq, physical_length,
  flexural_rigidity_ei, celerity, mass_per_unit_len, damping_percent, dynamic_fric, nat_freq,
  restrain_freq_ratio=1, gap=0, output_type=0, trace_every=0)` is `GetPeakResponse`. It returns a
  `PeakResponse` with the five maxima and, for `output_type` 1–3, the per-sample history.
* `surge_sdof.response.peak_response_jc(...)` is `GetPeakResponseJC`: the same arguments plus
  `fluid_densty` and `fluid_area`, and three keyword-only flags. Each flag has a value that
  reproduces the VBA bitwise and a value that applies an approved fix; **the fixes are the
  defaults**.

  | flag | default (fix) | legacy value | what it selects |
  |---|---|---|---|
  | `vav_denominator` | `"fixed"` | `"legacy"` | F-1: the mean fluid velocity divides by the `2N + 1` terms summed; the VBA divides by `2N − 1` (DEVIATIONS D-17). Numerically inert for the outputs (rounding level). |
  | `parity` | `"running"` | `"per_phase"` | F-2: one running sub-step counter drives the even/odd MoC alternation for the whole run; the VBA restarts the index per phase and can update one half-grid twice at a phase boundary (D-19). |
  | `fraction_profile` | `"fixed"` | `"legacy"` | F-4/F-4b: your corrected `interpFractionA/B` of 27 Oct 2026 (`legacy/vba/interpFraction_fix_2026-10-27.bas`), symmetric about the pipe centre with equal legs; the VBA originals have the `n < 3` test and the pivot-4 division by zero (D-4). |

  With all three legacy values the result equals `legacy_port` bitwise and Excel to 8.6e-13.
  With the defaults the junction-coupling results differ from Excel by about 2e-3 on the golden
  cases (up to 4.5e-2 on the coarsest sweep case), almost entirely from the profile correction;
  the measured deltas are in DEVIATIONS D-4 and `docs/jc_sweep.md`.
* `surge_sdof.pressure.pressure_response(valve_pattern, closure_time, celerity, density,
  time_step, pressure_drop_from_pump, flow_rate, pipe_area, valve_cv, length_to_pump,
  pump_ramp_pressure)` is `GetPressureResponse`: the valve pressure after each loop iteration of
  two time steps. No flags; it preserves the VBA as found.

`trace_every=k > 0` on either peak solver also records every `k`-th sub-step (state, elbow
forces, friction force, the MoC column) as `PeakResponse.trace`; the maxima are unchanged.

## Install

Python 3.10 or later (developed on 3.13). From the repository root:

```
python -m venv .venv
.venv/bin/pip install -e ".[dev,plots]"
```

`dev` brings pytest, ruff, hypothesis, the fixture-extraction tools (openpyxl, oletools),
playwright for the viewer's browser tests and the plotly Python package, which is only the
source of the plotly.js bundle inlined into the viewer. `plots` brings matplotlib for the
sweep figures. Every command below uses `.venv/bin/python`; the `Makefile` wraps the common
ones. The compiled kernels build on first use (about a second) and are cached under
`src/surge_sdof/__pycache__`; `NUMBA_DISABLE_JIT=1` runs the same source as plain Python.

## Tests and gates

| tier | command | content | time |
|---|---|---|---|
| fast | `.venv/bin/python -m pytest -q` (`make test`; `make test-both` repeats it with the JIT off after a cache wipe) | VBA-semantics pins, every DEVIATIONS quirk, the differential suite (restructured modules against `legacy_port`, bitwise on seeded sweeps), hypothesis properties, the Example-sheet golden cases, the export and geometry tests, the viewer in headless Chromium (skipped without a browser) | about 1.5 min compiled, 3 min pure Python |
| slow | `.venv/bin/python -m pytest -q -m slow` | the 75 lumped `GetPeakResponse` curve cases against Excel at 5e-12, through both layers | about 5 min |
| jc_slow | `.venv/bin/python -m pytest -q -m jc_slow` | the 3 junction-coupling curve cases against Excel at 5e-12: `peak_response_jc` with the legacy flags (seconds) and the literal port (about 80 min, pure Python) | see left |

The gates in `CLAUDE.md`: the fast suite before every commit, `-m slow` before any commit that
touches `src/`, `make test-both` after editing a compiled module (the Numba cache does not
notice a changed callee in another module), `ruff check . && ruff format .`. `tools/bench.py`
records timings under `docs/bench/`; `docs/bench/README.md` has the series.

## Export a trace and watch it

```
.venv/bin/python tools/export.py trace --golden example_jc --out out/example_jc.json
.venv/bin/python tools/export.py trace --golden r096_jc_L24_f3 --out out/r096.json.gz
```

Then open `docs/viewer/viewer.html` in a browser (double-click; no server, no network: the
page carries plotly.js and a gzip inflater and refuses every request) and load the file with
the picker or by drag-and-drop. Panel 1 is the MoC column on the expansion loop (circles
displaced by `x(t)` times the cell's moving fraction, sized by pressure, coloured by velocity);
Panel 2 is the unbalance force over the friction force with a cursor. Play, speed, stride, a
time window, exaggeration and colour range are live controls. `docs/viewer/README.md` is the
user guide; `docs/viz/data/` holds five committed files, including the Example-sheet cases and
golden row 96. A `--step` option builds a plain step history instead of a fixture case.

The same page opens a `sweep` file (`docs/viz/data/tier1_sweep.json`, or `tools/export.py sweep
--from-csv` of any sweep CSV) in sweep mode: three tabs against the natural frequency (curve
families per size and length with lumped and JC overlaid; the JC / lumped ratio as circles
animated over amplitude or friction; the mass-collapse panels per history type), dropdown
filters, the full row of a hovered point with its regenerate command, and a badge that reports
whether the Excel reference values of the file's `reference` block are reproduced by the rows
of the same case (green on `reference_sweep.json`; Tier 1 has no reference case among its rows).
The Tier 2 file is not committed (22.7 MB for 24 300 rows); build it with

```
.venv/bin/python tools/export.py sweep --from-csv docs/sweep/tier2_3664dc7_f4b.csv --tier 2 --out out/tier2_sweep.json
```

and open it like the others: it loads in under a second in headless Chromium, the default
filters show one history type at the largest friction and amplitude, and the `all` filters
split each family by seed, amplitude and friction.

## Run and plot the sweep

```
.venv/bin/python tools/sweep_jc.py check                        # pipe table vs the design pressures
.venv/bin/python tools/sweep_jc.py run --tier 1 --jobs 4 --tag f4b
.venv/bin/python tools/sweep_jc.py run --tier 2 --jobs 8 --tag f4b
.venv/bin/python tools/sweep_jc.py plot docs/sweep/tier1_<sha>_f4b.csv --doc docs/jc_sweep.md
.venv/bin/python tools/sweep_jc.py plot docs/sweep/tier2_<sha>_f4b.csv --doc docs/jc_sweep_tier2.md
```

Every case runs both solvers on a canonical pressure history (`surge_sdof.histories`: step,
step plus sine, step plus band-limited noise, seeded and rebuildable from the CSV row). Tier 1
is 1600 cases (two sizes, five lengths, eight frequencies; about 75 s on four processes); Tier
2 is 24 300 (four sizes, the fifteen curve-sheet frequencies, three seeds, three amplitudes,
three frictions; about 77 min of solver CPU). The CSV is named by tier, git sha and `--tag`,
so a rerun never overwrites an earlier file; `plot` writes the PNGs and the markdown report.
`docs/jc_sweep.md` is the Tier 1 report at the current profile; `docs/jc_sweep_tier2.md` is the
Tier 2 report (`docs/sweep/tier2_3664dc7_f4b.csv`, 24 300 rows, none with errors, run on 29 Oct
2026 at the handover solver). The same run's host also added the `3664dc7` row to
`docs/bench/README.md`: digests all equal to the literal port, Numba against literal 0.090 on
the Example lumped case, the full JC golden cases 0.7–0.8 s each.

## The data format

`docs/data_format.md` is the contract of the two JSON documents the viewer reads, `trace` and
`sweep`, and of the sweep CSV; `tests/test_export.py` parses the document so code and contract
cannot drift. Arrays are column-wise, floats are `repr` (shortest round-trip), there is no NaN,
and `.gz` gzips. Every file carries `meta.git_sha` of the solver that wrote it: the viewer
shows it, and `tests/test_export.py` fails if a committed file predates the current profile
commit, so a stale export cannot sit unnoticed next to a changed solver.

## The oracle and the frozen directories

The Excel source is `tests/fixtures/source/surge_force_data.xlsm`; `tools/extract_fixtures.py`
pulled its cached results into `tests/fixtures/` (81 golden cases: 75 lumped and 3
junction-coupling curve rows, the 3 Example-sheet calls). The VBA it ran is `legacy/vba/` with
your `floor` fix and the two `interpFraction` corrections. **`tests/fixtures/` and `legacy/`
are never edited**; a hook blocks it, and any new fixture must come from a workbook with the
fixed `floor`.

## Where Python differs from the VBA

`DEVIATIONS.md` lists every place the port departs from, or deliberately preserves a quirk of,
the VBA: 23 rows, each with the VBA and Python locations, both behaviours, the status
(preserved or fixed), the reason and the pinning test. Read it before relying on an edge case.
`docs/port_review.md` is the close-out review of the literal port.

## Model caveats to keep in mind

* **The free-decay threshold is absolute.** Phase 3 runs only while `x · x0 > 0.01`, i.e.
  `|x| > 0.1` in model units; metre-scale pipework never enters it, and with zero damping and
  friction it would not terminate (D-21, as in the VBA).
* **The pressure solver's friction clamps differ between its two half-loops** (`0.9` and
  `0.9 · ρc`, D-6) and both saturate in a sweep: the first at low flow, the second where the
  local initial velocity passes through zero. Intent unknown; preserved.
* **A frame mixes the two half-grids.** Each MoC sub-step updates one staggered half-grid, so
  the interleaved column in a trace frame holds the half-grid just updated beside the other one
  from the sub-step before; the two are half a step apart in time. The structure state is the
  end of the sub-step; `d_f` is the junction force that sub-step used.
* **The viewer floors the circle size at 3 px.** The nominal diameter is capped at 0.8 of the
  on-screen cell spacing but never below 3 px, so a 1333-cell column draws as a tube and the
  pressure sizing is visible only on short columns.
* The F-1 divisor fix is numerically inert for the outputs: the mean-velocity subtraction
  bookkeeps the column's mean velocity and never reaches the force.

## What is not done

* **Stage 6**: removing `legacy_port.py` and `vba_compat.py` once they are no longer wanted as
  the reference (the quirk pins in `tests/test_quirks.py` would move to the live modules), and
  any model extension beyond the VBA (input validation for non-physical inputs, a compiled force
  schedule, the binary data variant named in `docs/data_format.md`).
* The Tier 2 viewer file (`tier2_sweep.json`) is not committed; the export command is above.
* The viewer is tested in headless Chromium only. A sweep row's regenerate command is the
  file's own template: the Tier 1 file's reruns the whole tier (`tools/sweep_jc.py run --tier
  1`); a single-row trace option in `tools/export.py` was not built.
