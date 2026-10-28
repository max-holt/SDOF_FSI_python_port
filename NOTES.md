# NOTES — session handoff

Current stage, open issues and the next action. The session-by-session record that used to
live here (scope, plan and "done" sections of every stage) is in the git history of this file
up to the `v0.3-handover` tag; `docs/handover.md` is the orientation for a new reader.

## Current stage

Session H.1 (handover, 2026-10-28) **done**: the plotly-python animation retired
(`viz/animate.py`, `tools/animate.py`, `tests/test_viz.py`, `tests/test_viz_motion.py` deleted;
the geometry pins moved to `tests/test_geometry.py`, `is_capped` and the rest-frame phase into
`export.py`, the viewer's browser fixture into `tests/test_viewer.py`; the `viz` extra gone,
plotly pinned in `dev` as the viewer's bundle source, pandas gone), `docs/handover.md` written,
this file compressed, `CLAUDE.md` trimmed to the post-port rules, `moc.py` docstring states the
F-4b confirmation. No solver behaviour changed: `make test-both`, `-m slow`, `-m jc_slow` and
lint green, port-reviewer no findings, bench within noise (`docs/bench/`). `main` fast-forwarded
to the branch and tagged `v0.3-handover`.

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

## Open issues

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
* `GetPressureResponse` has one Excel golden case (the Example sheet); multi-column valve
  patterns and the pump / friction branches at other operating points are covered only by the
  differential sweep against the literal port. Rows 100–101 of `curve_10in` hold pasted numbers
  (no formula) and were not extracted.
* The viewer carries the full plotly.js 4.1.1 bundle (4.8 MB; no partial bundle ships with the
  package and nothing is fetched); `tools/build_viewer.py --plotly <file>` rebuilds at ~1 MB
  from an offline `plotly.js-basic-dist-min` (then `tests/test_viewer.py` needs the same
  switch). Tested in headless Chromium only. `docs/viz/data/golden_r096_jc.json.gz` is 13.9 MB.
* The project hooks in `.claude/settings.json` load only when Claude Code is started from the
  repository root.

## Next action

**Tier 2 locally (the lead author or owner), then W.3, then Stage 6.**

* Tier 2: `.venv/bin/python tools/sweep_jc.py run --tier 2 --jobs <cores> --tag f4b` (≈ 77 min
  of solver CPU, ≈ 10 min wall on 8 cores), then `.venv/bin/python tools/sweep_jc.py plot
  docs/sweep/tier2_<sha>_f4b.csv --doc docs/jc_sweep_tier2.md`; commit the CSV, the PNGs under
  `docs/sweep/png/` and the report. `plot --mu` / `--amplitude` select the friction and
  amplitude level of figures 1–3; the noise envelope over the three seeds is taken pointwise.
* W.3: sweep mode in the viewer (`docs/viewer/viewer.src.html`, rebuild with
  `tools/build_viewer.py`, extend `tests/test_viewer.py`): load a `sweep` file at
  `schema_version` 2 (`docs/viz/data/tier1_sweep.json`), a table / scatter of the columns with a
  row's `regen` command, the self-check of the `reference` block against the port's values.
* Stage 6: remove `legacy_port.py` / `vba_compat.py` when the reference is no longer wanted
  (the `tests/test_quirks.py` pins move to the live modules); any extension beyond the VBA
  needs the lead author's decision and a DEVIATIONS row.
