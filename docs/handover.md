# surge_sdof — handover

Written for the lead author at the `v0.4-handover` tag (the viewer's sweep mode and the Tier 2
sweep, 29 Oct 2026) and corrected in Session H.3 after an independent fresh-machine review. It
says what the repository contains, how to install and verify it, and what is not done. The
history of how it was built is in git; `NOTES.md` keeps a short summary.

## Terms used below

* **Literal port**: `legacy_port.py` and `vba_compat.py`, the line-for-line transcription of
  the VBA (Stage 1), frozen and kept as the reference the restructured solver is tested against.
* **Differential suite**: `tests/test_differential.py`, the restructured modules run against the
  literal port on seeded inputs and the golden inputs; the two must agree bitwise.
* **Golden cases**: the 81 Excel-cached results in `tests/fixtures/` (75 lumped and 3
  junction-coupling curve rows, 3 Example-sheet calls) that both layers reproduce at the
  tolerance recorded in `tests/test_golden.py` (5e-12 curve, 1e-12 Example).
* **Bitwise**: equal as IEEE doubles, every bit, not within a tolerance.
* **Numba / JIT / cache**: numba compiles the three inner loops to machine code on their first
  call (just in time) and keeps the result on disk under `src/surge_sdof/__pycache__`;
  `NUMBA_DISABLE_JIT=1` runs the same source as plain Python.
* **Hypothesis properties**: `tests/test_properties.py`, invariants checked on inputs the
  hypothesis library generates, as opposed to fixed cases.
* **Stage N**: the numbered steps of the port plan: 1 the literal port, 4 the restructure, 5
  Numba, 6 the removal of the literal port (not done); the numbering is the plan's, gaps included.
* **Sessions V / W / H**: the lettered work after the port: V the sub-step trace (V.1) and the
  retired plotly-python animation (V.2); W the data files (W.1), the viewer (W.2) and its sweep
  mode (W.3); H the handover sessions (H.1 retirement and this document, H.2 the Tier 2
  close-out, H.3 this review). Session 5b is the junction-coupling sweep.

## What the package is

`surge_sdof` is a Python port of the Excel VBA solver in `legacy/vba/Existing Code.bas`: a 1-D
method-of-characteristics (MoC) water-hammer model and a single-degree-of-freedom (SDOF)
pipe-response model with Coulomb friction, support gaps and MoC junction-coupling
fluid-structure interaction. It has two layers. `legacy_port.py` and `vba_compat.py` are the
frozen line-for-line transcription of the VBA, verified against Excel. `response.py`
and the modules behind it (`structure`, `loads`, `coupling`, `moc`, `histories`) are the
restructured solver, value-identical to the transcription when run with
the legacy flags (bitwise on the differential suite) and compiled with Numba (the three full
junction-coupling golden cases run in about a second each, down from 13–30 minutes). Runtime
dependencies are numpy and numba only. `docs/architecture.md` describes the modules.

## The two entry points

Both take the VBA arguments, by the VBA names in snake case, and return 0-based numpy results
(no 1-based pad). Units are consistent SI. The docstrings give the unit of every argument; the
common ones are inline below. The VBA's third function, `GetPressureResponse` (valve / pump
water hammer), was unused legacy code: its live port was removed in review session R.1b, and
only the frozen `legacy_port.get_pressure_response` keeps it.

* `surge_sdof.response.peak_response(force_history, sample_rate, *, span, restraint,
  integration)` is `GetPeakResponse`. `force_history` is the force-time history in N, 1-D or
  2-D; a 2-D history is walked column-major, first index fastest, exactly as Excel hands a range
  to VBA (D-10). `sample_rate` is its sample rate (Hz). The other arguments are frozen
  dataclasses of `response` (session R.9):

  * `PipeSpan(span_length, flexural_rigidity, mass_per_length, celerity)`: the span between
    the elbows (m), E·I (N·m²), the mass per length of pipe and contents (kg/m) and the
    pressure-wave speed (m/s), which is also the speed the force travels between the elbows;
  * `Restraint(natural_frequency, damping_percent, friction_coefficient, support_gap=0,
    closed_gap_frequency_ratio=1)`: the natural frequency with the gaps open (Hz), damping as a
    percentage of critical, the Coulomb coefficient, the support gap at the centre of mass (m)
    and the gaps-closed over gaps-open frequency ratio;
  * `Integration(substep_count, trace_every=0)`: substeps per sample and the trace stride.

  It returns a `PeakResponse` whose attributes are

  * `max_static_equivalent_force` (N), `max_displacement` (m), `max_velocity` (m/s),
    `max_acceleration` (m/s²), `max_unbalance_force` (N, the largest `|forceA − forceB|`): the
    five maxima of the VBA `resultArray(0 To 4)` (`summary()` returns them in that order);
  * `displacement_history` (m), `velocity_history` (m/s), `acceleration_history` (m/s²): the
    state at the end of each sample, 0-based, length `2 * outMax` (unfilled trailing elements
    0); the VBA returned one of them per call, by `outputType`;
  * `free_decay_sample_count` (the samples integrated in the free-decay phase) and `trace`
    (the substep trace when `trace_every > 0`, below, else `None`).
* `surge_sdof.response.peak_response_jc(force_history, sample_rate, *, span, restraint, fluid,
  integration, coupling=FIXED_COUPLING)` is `GetPeakResponseJC`: the same arguments plus
  `Fluid(fluid_density, flow_area)` (kg/m³; the internal pressure area of the pipe, m²) and
  `coupling`, a `CouplingModel` of three flags. Each flag has a value that reproduces the VBA
  bitwise and a value that applies an approved fix; **the fixes are the defaults**
  (`FIXED_COUPLING`); `VBA_COUPLING` holds the three legacy values. An unknown value raises
  when the `CouplingModel` is built (D-25).

  | flag | default (fix) | legacy value | what it selects |
  |---|---|---|---|
  | `mean_velocity_divisor` | `"fixed"` | `"legacy"` | F-1: the mean fluid velocity divides by the `2N + 1` terms summed; the VBA divides by `2N − 1` (DEVIATIONS D-17). Numerically inert for the outputs (rounding level). |
  | `parity` | `"running"` | `"per_phase"` | F-2: one running substep counter drives the even/odd MoC alternation for the whole run; the VBA restarts the index per phase and can update one half-grid twice at a phase boundary (D-19). |
  | `fraction_profile` | `"fixed"` | `"legacy"` | F-4/F-4b: your corrected `interpFractionA/B` of 27 Oct 2026 (`legacy/vba/interpFraction_fix_2026-10-27.bas`), symmetric about the pipe centre with equal legs; the VBA originals have the `n < 3` test and the pivot-4 division by zero (D-4). |

  With all three legacy values the result equals `legacy_port` bitwise and Excel to 8.6e-13.
  With the defaults the junction-coupling results differ from Excel by about 2e-3 on the golden
  cases (up to 4.5e-2 on the coarsest sweep case), almost entirely from the profile correction;
  the measured deltas are in DEVIATIONS D-4 and `docs/jc_sweep.md`.

`Integration(trace_every=k > 0)` on either peak solver also records every `k`-th substep
(state, elbow forces, friction force, and in `Trace.column` the MoC column) as
`PeakResponse.trace`; the other results are unchanged bitwise. The fixtures and
`legacy_port` keep the VBA argument names; `tools/fixture_cases.solver_inputs(kw)` turns such
a keyword dict into the arguments above.

## Install

Python 3.10 or later (developed on 3.13). From the repository root:

```
python -m venv .venv
.venv/bin/pip install -e ".[dev,plots]"
```

`dev` brings pytest, ruff, hypothesis, the fixture-extraction tools (openpyxl, oletools),
playwright for the viewer's browser tests and the plotly Python package, which is only the
source of the plotly.js bundle inlined into the viewer. `plots` brings matplotlib for the
sweep figures. This is the one install command of the project (the README and the `Makefile`
assume it; CI installs `[dev]` only because it never plots). Every command below uses
`.venv/bin/python`; the `Makefile` wraps the common ones. The compiled kernels build on first use (about a second) and are cached under
`src/surge_sdof/__pycache__`; `NUMBA_DISABLE_JIT=1` runs the same source as plain Python.

## Tests and gates

| tier | command | content | time |
|---|---|---|---|
| fast | `.venv/bin/python -m pytest -q` (`make test`; `make test-both` repeats it with the JIT off after a cache wipe) | VBA-semantics pins, every DEVIATIONS quirk, the differential suite (restructured modules against `legacy_port`, bitwise on seeded sweeps), hypothesis properties, the Example-sheet golden cases, the export and geometry tests, the viewer in headless Chromium (skipped without a browser) | see below |
| slow | `.venv/bin/python -m pytest -q -m slow` | the 75 lumped `GetPeakResponse` curve cases against Excel at 5e-12, through both layers | see below |
| jc_slow | `.venv/bin/python -m pytest -q -m jc_slow` | the 3 junction-coupling curve cases against Excel at 5e-12: `peak_response_jc` with the legacy flags (seconds) and the literal port (about an hour or more, pure Python) | see below |

Times are minutes; machine-dependent (fast suite ~3 min compiled / ~7 min pure Python, slow ~10 min, on a 4-core cloud container); the three literal-port junction-coupling cases took 73 min on one host.

The gates in `CLAUDE.md`: the fast suite before every commit, `-m slow` before any commit that
touches `src/`, `make test-both` after editing a compiled module (the Numba cache does not
notice a changed callee in another module), `make lint` (`ruff check` and `ruff format --check`
through the venv; a bare `ruff` on the PATH can be another version, and `ruff format .` rewrites
files, so format with `.venv/bin/python -m ruff format .` only when you mean to). `tools/bench.py`
records timings under `docs/bench/`; `docs/bench/README.md` has the series.

## Export a trace and watch it

```
.venv/bin/python tools/export.py trace --golden example_jc --out out/example_jc.json
.venv/bin/python tools/export.py trace --golden r096_jc_L24_f3 --out out/r096.json.gz
```

(`out/` is git-ignored; any path works.)

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
.venv/bin/python tools/sweep_jc.py run --tier 1 --limit 20 --out out --tag smoke   # smoke run, 20 cases
.venv/bin/python tools/sweep_jc.py run --tier 1 --jobs 4 --tag f4b
.venv/bin/python tools/sweep_jc.py run --tier 2 --jobs 8 --tag f4b
.venv/bin/python tools/sweep_jc.py plot docs/sweep/tier1_<sha>_f4b.csv --doc docs/jc_sweep.md
.venv/bin/python tools/sweep_jc.py plot docs/sweep/tier2_<sha>_f4b.csv --doc docs/jc_sweep_tier2.md
```

Every case runs both solvers on a canonical pressure history (`surge_sdof.histories`: step,
step plus sine, step plus band-limited noise, seeded and rebuildable from the CSV row). Tier 1
is 1600 cases (two sizes, five lengths, eight frequencies; about 75 s on four processes); Tier
2 is 24 300 (four sizes, the fifteen curve-sheet frequencies, three seeds, three amplitudes,
three frictions; about 77 min of solver CPU). `run --out` takes a directory (default
`docs/sweep/`); the CSV in it is named by tier, git sha and `--tag`, so a rerun never overwrites
an earlier file. `--limit N` runs the first N cases and `--subset f` a stratified fraction of the
tier (with `--subset-seed`), for smoke runs; `--history` restricts to one history type. `plot`
writes the PNGs and the markdown report.
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
Since the review's schema bump (session R.9) the documents are `trace` schema 2 and `sweep`
schema 3, with every key named as `docs/nomenclature.md` names it (the old-to-new table is
`docs/review/public_interface.md` §3.3); the viewer refuses older files, which are
re-exported with `tools/export.py`, and a sweep CSV written before the bump needs its header
line renamed (the rows are unchanged).

## The oracle and the frozen directories

The Excel source is `tests/fixtures/source/surge_force_data.xlsm`; `tools/extract_fixtures.py`
pulled its cached results into `tests/fixtures/` (81 golden cases: 75 lumped and 3
junction-coupling curve rows, the 3 Example-sheet calls). The VBA it ran is `legacy/vba/` with
your `floor` fix and the two `interpFraction` corrections. **`tests/fixtures/` and `legacy/`
are never edited.** The only guard is a Claude-Code-only hook (`.claude/hooks/protect_paths.py`,
wired in `.claude/settings.json`, active when Claude Code is started from the repository root);
nothing stops a human editor, so treat both directories as read-only by convention. Any new
fixture must come from a workbook with the fixed `floor`.

## Where Python differs from the VBA

`DEVIATIONS.md` lists every place the port departs from, or deliberately preserves a quirk of,
the VBA: 23 rows, each with the VBA and Python locations, both behaviours, the status
(preserved or fixed), the reason and the pinning test. Read it before relying on an edge case.
`docs/port_review.md` is the close-out review of the literal port.

## Model caveats to keep in mind

* **The free-decay threshold is absolute.** Phase 3 runs only while `x · x0 > 0.01`, i.e.
  `|x| > 0.1` in model units; metre-scale pipework never enters it, and with zero damping and
  friction it would not terminate (D-21, as in the VBA).
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
