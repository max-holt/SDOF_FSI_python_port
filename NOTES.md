# NOTES — session handoff

Current stage, open issues and the next action. The session-by-session record that used to
live here (scope, plan and "done" sections of every stage) is in the git history of this file
up to the `v0.4-handover` tag; `docs/handover.md` is the orientation for a new reader.

## Current stage

Session R.1 (independent review, 2026-11-16) **done**: findings and plan only, no code
change (`src/`, `tools/` and `tests/` are byte-identical to `6b31f71`). Six blind
`clean-code-reviewer` passes (architecture, functions, names and documentation; solver
core and supporting Python), each Design and Readability finding through its own
`finding-verifier` (118 checked, 1 refuted, most corrected), then reconciled with
`docs/architecture.md` and `DEVIATIONS.md`. `docs/review/findings.md`: 140 findings (31
Design, 65 Readability, 44 Nit), the recorded constraints K-1 to K-11, what to leave alone,
and 14 suspected defects that were not acted on. `docs/review/plan.md`: single-refactoring
commits in the charter's order, four changes to that order, and questions Q-1 to Q-11 for
the owner. A toy kernel (scratch, not committed) gave the same bits and the same time with
NamedTuple parameters and compiled helpers as with flat scalars, compiled and with
`NUMBA_DISABLE_JIT=1` (Numba 0.68.1): the Stage 5 flat signatures are a choice, not a
limit. `docs/nomenclature.md` is not written yet (plan step 0.1, needs Q-6).

Session R.0b (review set-up amended, 2026-11-16, branch `review/clean-code`) **done**: no
solver change (`src/` is byte-identical to `177c8b1`). The owner answered the R.0 conflicts
and widened the review. `docs/review/charter.md`: scope is the solver core plus the
supporting Python (`trace.py`, `export.py`, `histories.py`, `viz/geometry.py`, `tools/`);
the data format is in scope with one schema bump (public API session); the viewer only for
the keys it reads; rule 6 and a "renames" / "public API" session table. `docs/style.md`
carries the rulings (below). `.claude/hooks/format_py.py` formats with the venv's ruff.
New safety net `tests/test_review_support.py` + `tools/review_support.py` +
`tests/review_support/` (20 files, 1.85 MB): 16 sweep rows through `tools/sweep_jc.py`,
eight exported files byte for byte, ten history documents as `float.hex()` text; 5 s
compiled, under 1 s in pure Python; 16 mutations fail, three regroupings are recorded as
not visible (charter, "The supporting-code checks"). `docs/review/baseline.md` and
`tools/review_baseline.py` cover three groups: core 52 functions, supporting 45, `tools/`
129. Gates on the tree: lint clean; `make test-both` 1063 passed + 24 skipped (Numba) /
1061 passed + 26 skipped (pure Python; the 24 are the viewer's browser tests, the two more
are the sweep check and one existing skip); `-m slow` 150 passed; `tools/bench.py
--skip-full-python` (`docs/bench/253210a.json`): digests all equal to the literal port and to the previous row (`afead1d`), the full JC golden cases 1.0-1.2 s. The first commit of
the session (documents and the hook) was made after `make lint` only; `make test-both` ran
on the tree of the second commit onwards.

Session R.0 (clean-code review set-up, 2026-11-16, branch `review/clean-code`) **done**: no
solver change (`src/` is byte-identical to `177c8b1`). Added `docs/review/charter.md` (scope,
change rules, gates, findings scale, the mutation results), `docs/style.md` (the owner's style
guide, verbatim), the snapshot oracle (`tests/test_review_snapshot.py`,
`tools/review_snapshot.py`, `tests/review_snapshot/`: 34 documents, 245 solver calls, every
output as `float.hex()` text, exact equality, about 1 s compiled and 2 s in pure Python),
`docs/review/baseline.md` with `tools/review_baseline.py` (ruff and radon per function; radon
added to the `dev` extra with the owner's approval), the two reviewer agents
(`.claude/agents/clean-code-reviewer.md`, `finding-verifier.md`: Read, Grep, Glob only) and
the review section of `CLAUDE.md`, which on this branch moves the `-m slow` gate from every
commit touching `src/` to the end of every session. Mutation checks: the three required
operand swaps (`moc.step`, `structure.step_scalars`, `loads.unbalance_force`) fail 14 / 25 /
25 of 36 snapshot tests; four further mutations survived the first case set and the set was
extended until they fail (charter, "It bites"). Gates on the tree: lint clean; `make
test-both` 1041 passed + 24 skipped (Numba) / 1040 passed + 25 skipped (pure Python), the 24
being the viewer's browser tests (this container ships Chromium build 1243, the pinned
playwright 1.56.0 wants 1194); `-m slow` 150 passed; `tools/bench.py --skip-full-python`
(`docs/bench/afead1d.json`, the review's reference row): digests all equal to the literal
port, Numba / literal 0.097 on the Example lumped case, the full JC golden cases 1.0-1.2 s.

Session H.3 (handover fixes from an independent fresh-machine review, 2026-10-29) **done**:
docs only, no `src/` change. Tag names corrected to the pushed tags; the README entry-point
table lists `fraction_profile`; one install command (`pip install -e ".[dev,plots]"`); timing
claims made machine-dependent with the 4-core container figures; `out/` git-ignored; the
fixtures / legacy guard described as the Claude-Code-only hook it is; a glossary and the
`PeakResponse` attributes, units and the column-major rule in `docs/handover.md`; `sweep_jc.py
run --out` / `--limit` / `--subset` documented in `--help` and the handover; lint pointed at
`make lint`; the viewer's source comments cite `docs/architecture.md` "The picture" instead of
the retired `viz/animate.py` (page rebuilt). Gates: `make lint`, `make test`. Tag
`v0.4.1-handover` is the owner's.

Session H.2 (close-out for `v0.4-handover`, 2026-10-29) **done**: Tier 2 of the sweep is
committed by the owner (`3c70302`: `docs/sweep/tier2_3664dc7_f4b.csv`, 24 300 rows, none with
errors, ≈ 0.066 s lumped / 0.258 s JC a case, the four PNGs, `docs/jc_sweep_tier2.md`, and the
`3664dc7` bench row on an i5-13600KF in `docs/bench/README.md`: digests all equal, Numba /
literal 0.090 (a), full JC cases 0.7–0.8 s). `docs/viz/data/reference_sweep.json` re-exported at
`3c70302` (schema 2 as before; only `meta.git_sha` and `created_utc` change, the columns, regen
and reference blocks byte-identical). The viewer confirmed in headless Chromium 141 on the two
committed sweep files and on a Tier 2 export (`tools/export.py sweep --from-csv
docs/sweep/tier2_3664dc7_f4b.csv --tier 2`, 22.7 MB): each loads in under a second, the
reference badge is green / neutral / neutral, the Tier 2 defaults (step, mu 0.3, amplitude 1)
draw 40 curve traces, 300 effect points animated over three amplitudes and 80 collapse traces,
no page error, no request beyond the page. The Tier 2 viewer file is not committed (size;
the command is in `docs/handover.md`). `docs/handover.md` and this file updated for W.3 and
Tier 2. Gates on the tree: lint clean, `make test-both` 1029 passed (Numba) / 1028 passed +
1 skipped (pure Python), `-m slow` 150 passed; `src/` untouched, no bench. `main`
fast-forwarded to the branch; the `v0.4-handover` tag is the owner's (the tag push is refused
from the container).

Session W.3 (sweep mode in the viewer, 2026-10-29) **done**: `docs/viewer/viewer.src.html` opens
a `sweep` file at schema 2 (schema 1 is refused with the other unsupported files) in sweep mode
beside the untouched trace mode: three tabs against `nat_freq_hz` (curve families, `y` = `f_eq`
raw / `daf` / `f_eq_over_LD2`, one panel per size, one trace per length and per open varying
key, lumped hollow and JC filled at 0.55 opacity; JC effect, `ratio_f_eq` or `ratio_v_peak` as
circles sized by length and coloured by history type, animated over `amplitude_fraction` or `mu`
through the page's play / pause / speed / slider at 1 s a value; collapse, `f_eq_over_LD2` and
`daf` with all sizes and lengths on one panel per history type), dropdown filters on
`history_type`, `f_osc_hz`, `seed`, `mu`, `amplitude_fraction` (defaults: one history type, the
largest friction and amplitude), hover → the full 72-column row in a panel under the plot, a
"regenerate trace" button that formats the file's `regen.template` with the row and copies it,
and on open the `reference` block checked against the rows of the same `case_id` with the golden
rule `|row − excel| ≤ rtol |excel|` (green on `reference_sweep.json`: the three JC golden rows, 6
values; neutral on Tier 1, no reference case among its rows; red on a tampered copy).
`tests/test_viewer.py` replaces the W.2 placeholder pin with 10 sweep tests (both committed
sweep files, trace counts computed from the file for each tab and filter set, the animation,
hover and the regenerate command, mode switching, zero requests) and hardens the load wait
against the "loading …" notice; 26 viewer tests pass in headless Chromium 141. Colours and
symbols are the report's (`tools/sweep_jc.py`); the length palette passes the colour-blind
separation check with the symbol as the secondary encoding. `docs/viewer/README.md` ("Sweep
mode"), `docs/data_format.md`, `docs/handover.md` updated. No solver, exporter or data file
changed; `src/` untouched, so the `-m slow` gate was not required.

Session H.1 (handover, 2026-10-28) **done**: the plotly-python animation retired
(`viz/animate.py`, `tools/animate.py`, `tests/test_viz.py`, `tests/test_viz_motion.py` deleted;
the geometry pins moved to `tests/test_geometry.py`, `is_capped` and the rest-frame phase into
`export.py`, the viewer's browser fixture into `tests/test_viewer.py`; the `viz` extra gone,
plotly pinned in `dev` as the viewer's bundle source, pandas gone), `docs/handover.md` written,
this file compressed, `CLAUDE.md` trimmed to the post-port rules, `moc.py` docstring states the
F-4b confirmation. No solver behaviour changed. Gates on the handover tree: `make test-both`
1019 passed (Numba) / 1018 passed + 1 skipped (pure Python, 2.6 min, down from 12 with the
motion tests gone), `-m slow` 150 passed, `-m jc_slow` 6 passed (the three literal-port cases
73 min), lint clean; port-reviewer on the retirement commit: no correctness findings (one moved
test helper restored to its original stride, `028e399`); `tools/bench.py --skip-full-python`
(`docs/bench/028e399.json`): digests all equal, Numba / literal 0.097 (a) and 0.525 (r96 full)
against 0.097 / 0.572 and 0.074 / 0.444 on the two previous hosts, within the between-host
noise the bench README describes. `main` fast-forwarded to the branch; the `v0.3-handover`
tag was local only and never pushed (the published tags are `v0.1-literal-port`, `v0.2-numba`,
`v0.4-handover`).

## How we got here

* **Stage 1, literal port** (`v0.1-literal-port`, 20–21 Oct 2026): `legacy_port.py` and
  `vba_compat.py` transcribe `legacy/vba/Existing Code.bas` line for line with the lead
  author's fixed `floor`. Verified against the Excel-cached results of
  `tests/fixtures/source/surge_force_data.xlsm`: 75 lumped and 3 junction-coupling curve cases
  at 5e-12 (worst 8.3e-13 / 8.6e-13), 3 Example-sheet cases at 1e-12. Every quirk recorded in
  `DEVIATIONS.md` (D-1 … D-22) and pinned in `tests/test_quirks.py`; `docs/port_review.md` is
  the close-out review.
* **Stage 4, restructure** (4.0 baseline bench; 4.1 `structure`, `loads`, `coupling`,
  `response.peak_response`; 4.2 `moc`, `JunctionCoupling`, `peak_response_jc`; 4.3 `pressure`,
  `_vba_semantics`; 4.4 hygiene and docstrings): `docs/architecture.md` is the layout as built;
  `tests/test_differential.py` proves every module bitwise against `legacy_port` on seeded
  sweeps and the golden inputs (D-23 records the Python-float overflow semantics). The lead
  author's approved fixes F-1 (`vAv` divisor, D-17) and F-2 (running MoC parity, D-19) were
  built flag-first and flipped to the defaults in 4.2; F-1 is numerically inert for the outputs.
* **Stage 5, Numba** (`v0.2-numba`, 22 Oct): `structure.step_scalars`, `moc.step` and
  `response._integrate_kernel` compiled with `numba.njit(cache=True)`, no fastmath, one source
  for both modes; differential sweeps bitwise under Numba (216/216); the full JC golden cases
  in ~1 s each (were 13–30 min). `tools/bench.py` and `docs/bench/` record the series.
* **V.1 trace, W.1 data files, W.2 viewer** (22–26 Oct): `trace_every` on both peak solvers
  records every k-th sub-step (`trace.Trace`); `export.py` writes the `trace` / `sweep` JSON
  documents of `docs/data_format.md`; `docs/viewer/viewer.html` plays them with no network. The
  V.2 plotly-python animation (22–26 Oct, reviewed by the lead author in three rounds) defined
  the picture (`docs/architecture.md`, "The picture") and was retired in H.1 once the viewer
  reproduced it 1:1.
* **F-4 / F-4b, the corrected moving-fraction profile** (26–27 Oct; F-4b confirmed by the lead
  author 29 Oct 2026): the lead author's `interpFractionA/B` replacement, mirrored about the
  pipe centre, transcribed as `fraction_profile="fixed"` (default; D-4 "fixed"); `"legacy"`
  reproduces the VBA. Measured change vs the legacy flags: golden JC rows ≤ 2.1e-3, JC sweep
  max 4.5e-2 (coarsest grid), median 8e-4 (`tools/profile_delta.py`).
* **Session 5b, the junction-coupling sweep** (27 Oct): `histories.py` (canonical step / sine
  / noise pressure histories, seeded, rebuildable), `tools/sweep_jc.py`, Tier 1 (1600 cases,
  `docs/sweep/tier1_83d23ef_f4b.csv`) reported in `docs/jc_sweep.md`. Decision 16 (lead author,
  29 Oct 2026): the full MoC junction-coupling model is the paper's generating model; F-3 (a
  simplified coupling) is closed.
* **W.3, sweep mode** (29 Oct): the viewer plots a `sweep` file (three tabs, filters, hover row,
  regenerate command, reference badge), above.
* **Tier 2** (29 Oct, the owner's machine): 24 300 cases (four sizes, fifteen frequencies, three
  seeds, amplitudes and frictions) at the handover solver, `docs/jc_sweep_tier2.md`; the
  collapse spread and the negligible / essential bands extend the Tier 1 picture to 16 and
  18 in and to the mid friction and amplitude levels.

## Open issues

* **Review R.0b, the R.0 conflicts as answered** (owner, 16 Nov 2026; in `docs/style.md`):
  2 keyword-only arguments are for the user-facing Python entry points; compiled functions
  take positional parameter objects. 3 "public signature" is the user-facing entry points
  of `response` and `pressure`; kernels may use nomenclature symbols in signatures. 4 both
  junction-coupling flag paths keep working; the form of the flags and of `output_type` is
  redesigned in the public API session, untouched before. 5 VBA spellings go: internal
  names in the renames session; public keywords, the `get_pressure_response` alias and
  exported names in the public API session. 6 unit factors are named in place, never
  folded; pure-number coefficients stay inline with a derivation comment (ask the owner
  when none is found). 7 complexity is ruff's count, radon is reported only; the argument
  limit is 6, enforced in the public API session. 8 (in part) `vba_min` / `vba_max` stay
  untyped, a recorded exception. 9 done. 10 left for the reviewers to raise.
* **Review R.0b, open questions for the owner:**
  1. **Answered (owner; done in session R.1b): the CPU dependence.** The sweep-row check
     runs on stored histories (`tests/review_support/sweep_histories.txt`, the fourteen
     histories of its rows, 1.5 MB) and is exact on any host. The history check is exact
     where numpy's `sin` / `exp` kernel matches the stored files (`X86_V4`) and compares
     each float at 1e-12 elsewhere; it never skips, and the summary of every pytest run
     prints which mode ran. The exact checks are authoritative on the CI Linux runner and
     in this cloud environment (charter, "Reference platform"). Still true:
     `histories.from_params` rebuilds a row's history bitwise only on a host with the same
     kernel (the Tier 1 and Tier 2 files were made with different ones).
  2. **Answered (lead author, 17 Nov 2026; done in session R.1b).**
     `tests/test_properties.py::test_jc_without_fluid_area_equals_lumped` held at rtol 1e-12
     only by the choice of examples (hypothesis seeds its examples with the numeric
     constants of every imported project module, so a new literal anywhere moved them). The
     counterexample is now pinned with `@example` (force 17 zeros then 17 samples of
     `-1428049.2002131606` N, the value whose 15-digit rounding was recorded here; the
     other inputs as recorded: `step_qty` 6, `sample_freq` 184, `physical_length` 18,
     `flexural_rigidity_ei` 64601, `celerity` 576, `mass_per_unit_len` 84,
     `damping_percent` 1, `dynamic_fric` 0.005, `nat_freq` 4.891204503212263, ratio
     1.390625, gap fraction 0.8125, `output_type` 1; it differs by 1.265e-12 in one
     history sample), and that test's tolerance is 5e-12 (`JC_EQUALS_LUMPED_RTOL`), as
     approved by the lead author on 17 Nov 2026. Checked: at 1e-12 the pinned example
     fails, at 5e-12 it passes.
  3. Argument limit 6 as ruff counts it (PLR0913) includes keyword-only arguments:
     `peak_response` has 14 and `peak_response_jc` 19. Parameter objects for the
     entry points, or an exception for keyword-only arguments?
  4. Answered (R.1b, charter ruling 4): the user-facing entry points are the solver entry
     points of `response`, `histories.canonical` and the `export.to_*_dict` functions.
     Still open: whether `histories.step`, `step_sine`, `step_noise` count as well.
  5. The schema bump against the committed files: `docs/viz/data/` (five files, one of
     13.9 MB) and `docs/sweep/*.csv` (the Tier 2 file, 21.8 MB, from the owner's machine)
     carry today's names. Re-export and rewrite the headers by script, rerun, or leave the
     old files and keep a reader for schema 1 / 2? And should the viewer read the old
     schema as well as the new? The viewer tests do not run in this container (playwright
     1.56.0 wants Chromium build 1194, the container has 1243), so a change to the keys the
     viewer reads cannot be verified here.
     Answered in part (R.1b, ruling 12): the committed sweep CSVs get their headers renamed
     by a one-off script, every data row byte-identical. Still open: the `docs/viz/data/`
     files and whether the viewer reads the old schema too.
  6. Answered by R.1b: the alias, `pressure.py` and its tests were removed with the
     owner's approval (the pressure solver was unused legacy code).
  7. Tools without a check: `tools/sweep_jc.py plot` (plots and the report text),
     `tools/bench.py`, `tools/extract_fixtures.py`, `tools/golden_report.py`,
     `tools/profile_delta.py`. Reviewed by reading only, or first given a check
     (`extract_fixtures.py` could write to a temporary directory and be compared with
     `tests/fixtures/`; the report tables of `sweep_jc.py` are plain text)?
     Answered (R.1b, ruling 3): rename-only edits.
  8. Still open from R.0: `docs/nomenclature.md` does not exist (plan 0.1; the vocabulary
     it needs is ruled, charter ruling 1);
     nesting depth 3 against ruff's PLR1702, which is a preview rule with default 5
     (reported only, or `preview = true`?); nothing enforces §7 to §9 (no `D` or `ANN`
     rule, `E501` ignored): when, if at all, do they become lint rules?
  9. Readings made in this session, to confirm: the schema bump happens in the public API
     session; `tests/` stays "mechanical edits only"; the session is called R.0b.
     Superseded for `tests/` (R.1b, ruling 6): a test may change how it calls a function,
     never what it asserts.
  Notes for the renames session, not questions: the frame keys of a `trace` document are
  the `Trace` attribute names (`export._frames` uses `getattr(trace, name)` over
  `FRAME_COLUMNS`), `meta.inputs` echoes the public keywords, and the history columns of
  the sweep CSV are `histories.PARAM_KEYS`; renaming any of them before the bump needs a
  mapping in `export.py`, and the byte check fails without one.

* **W.1, for the lead author:** `docs/data_format.md` defines the sweep columns' semantics for
  the first time. `f_peak_lumped` / `f_peak_jc` are `max_applied_force`, which both solvers
  compute as `max |forceA − forceB|` without the junction force, so on one history they are
  equal; the `f_eq_over_LD2_*` normalisation (`f_eq / (L D²)`) and `daf_*` (`f_eq /
  history_peak`) are inferred. Session 5b's choices `f_ref = 4 Hz` for the noise envelope, the
  shared 0.04 s transit allowance and `m_total = (L + 4h/3) m'` for momentum / kinetic energy
  are recorded in `tools/sweep_jc.py`; change the constants and rerun if another convention is
  wanted.
* **F-1 to raise with the lead author:** the approved `vAv` divisor fix is numerically inert
  for the outputs because `dF` depends on pressures, which depend on velocity differences, and
  `vAv` shifts every velocity uniformly. Whether the mean-velocity subtraction itself is the
  intended model is a modelling question, not a port question.
* Port review of V.1 (pre-existing): `loads._schedule` reads `fh[ib][jb]` before the first
  phase-2 `k` loop where the VBA (line 491) reads it only inside the loop; in the D-8
  configuration with `kOverlap = stepQTY` the VBA runs on while the restructured modules raise
  `IndexError`. D-8's Python column says "Identical"; a sentence there is for the owner.
* `GetPressureResponse` survives only in the frozen `legacy_port` (the live port went in
  R.1b), checked against its one Excel golden case (the Example sheet) and by the smoke and
  structure tests. Rows 100–101 of `curve_10in` hold pasted numbers
  (no formula) and were not extracted.
* The viewer carries the full plotly.js 4.1.1 bundle (4.8 MB; no partial bundle ships with the
  package and nothing is fetched); `tools/build_viewer.py --plotly <file>` rebuilds at ~1 MB
  from an offline `plotly.js-basic-dist-min` (then `tests/test_viewer.py` needs the same
  switch). Tested in headless Chromium only. `docs/viz/data/golden_r096_jc.json.gz` is 13.9 MB.
* Sweep mode's regenerate command is the file's own `regen.template`: the Tier 1 file's reruns
  the whole tier (`python tools/sweep_jc.py run --tier 1`; its note says a single row is
  `sweep_jc.run_case` on its columns). A `tools/export.py trace` option that rebuilds one sweep
  row's history from its fifteen generator columns and traces it was not built; adding it means
  a new template in `tools/export.py sweep --from-csv` and a re-export of `tier1_sweep.json`.
  The hover label is compact (case, size, length, frequency, history, amplitude, friction, the
  plotted value); the full row is the panel under the plot, not the label.
* plotly.js 4.1.1 emits `plotly_hover` only for a real pointer event (`Plotly.Fx.hover` draws
  the label but fires no event), so the hover tests move the mouse onto a marker.
* The project hooks in `.claude/settings.json` load only when Claude Code is started from the
  repository root.

## Next action

**Owner:** answer Q-1 to Q-11 in `docs/review/plan.md` (Q-6, the vocabulary, and Q-2, the
test-only interfaces, block the first commits) and the R.0b questions above. **Then review
session R.2:** `docs/nomenclature.md` (plan 0.1), then group 1 of the plan (renames, R0),
one refactoring per commit. Rules and gates: `docs/review/charter.md`.

**Stage 6** (unchanged), when the lead author wants it.

* Remove `legacy_port.py` / `vba_compat.py` when the reference is no longer wanted (the
  `tests/test_quirks.py` pins move to the live modules); any extension beyond the VBA needs the
  lead author's decision and a DEVIATIONS row.
* Optional: commit `docs/viz/data/tier2_sweep.json` (22.7 MB; `tools/export.py sweep --from-csv
  docs/sweep/tier2_3664dc7_f4b.csv --tier 2`) and add it to `SWEEP_FILES` in
  `tests/test_viewer.py` if the viewer should carry Tier 2 in the repository; `plot --mu` /
  `--amplitude` on the Tier 2 CSV select another friction and amplitude level for figures 1–3.
