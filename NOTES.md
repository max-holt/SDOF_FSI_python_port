# NOTES — session handoff

## Current stage
Stage 1 (literal port) complete and **verified against Excel for the lumped solver**: all 75 `GetPeakResponse` golden cases from the `curve_10in` case table pass at RTOL 5e-12 (max observed 8.3e-13). The 3 `GetPeakResponseJC` golden cases exist in the suite but have never been run (hours each in pure Python); they are the acceptance test for the Numba version (Stage 5). `GetPressureResponse` has no golden case yet (the workbook's `Example` sheet exercises it only on a demo pattern with cached values; not extracted). `src/surge_sdof/legacy_port.py` holds the line-for-line transcription; `vba_compat.py` the VBA-semantics helpers.

## Done
- `vba_compat.py`: `clng` (half-to-even), `vba_floor` (literal transcription of the fixed VBA `max(CLng(val - 0.5), CLng(val + 0.5) - 1)`, pinned against `math.floor`), `mod_dbl` (ordinary floored modulo now), `sign`, `min_unsigned`, `max_unsigned`, plus `ubound`/`vba_2d` for the padded 1-based array convention. `tests/test_vba_compat.py` pins them against the VBA definitions.
- Upstream `floor` fix applied: `main` merged, `vba_floor`/`mod_dbl` updated, the tests that pinned the old bug (mod_dbl table, parity test, D-11 multi-column pressure test, D-8 trigger condition) re-pinned to the fixed behaviour. DEVIATIONS D-1, D-2, D-11 are status "fixed" with the reason "source corrected upstream".
- `legacy_port.py`: `min`, `max` (shadow the built-ins on purpose, VBA tie semantics), `get_dimension`, `add_dimension`, `array_start_one` (D-3), `interp_fraction_a`, `interp_fraction_b` (D-4), `solve_poly`, `get_pressure_response` (D-6, D-11), `get_peak_response` (D-7, D-8), `get_peak_response_jc` (D-9, dead `useUndamped` branch kept behind `use_undamped = False`, short-pipe fallback). Conventions are documented in the module header.
- Tests (151 passing, `pytest -q` ≈ 3 s): `test_vba_compat.py`, `test_helpers.py`, `test_smoke.py` (each entry point on a 100-sample step force, stepQTY = 10, all output types, 1-D and 2-D inputs, fallback, raised error paths), `test_structure.py` (gap = 0 & ratio = 1 ≡ gap = 1e9 bitwise on both peak solvers; undamped constant-force midline = F/k within 1 % on the lumped solver; JC with fluidArea = 0 ≡ lumped bitwise; column-major flattening identity on all three entry points).
- DEVIATIONS.md rows D-1 … D-11: D-1, D-2, D-11 "fixed" (upstream source fix), the rest "preserved".
- Port review: `port-reviewer` subagent ran on `git diff 125e73e..HEAD` (diff + VBA only): **no correctness findings**. Its two non-blocking notes were applied: D-11 wording now states the even-row-count condition; the `solve_poly` complex-root edge case is listed below.
- Golden fixtures (2026-10-20): the owner committed the source workbook `tests/fixtures/source/surge_force_data.xlsm`. `tools/extract_fixtures.py` (needs openpyxl, a `dev` extra) writes `tests/fixtures/curve_10in/{force_history.csv, params.json, cases.csv}` from the Excel-cached values: full `Sheet1` extent (25303 rows), `n_samples = 25135`, 78 cases with `source_row` and `solver` columns (75 lumped rows 20-94, 3 JC rows 96-98). The workbook's `Module1` was decompressed and its 16 ported procedures are byte-identical to `legacy/vba/Existing Code.bas` (fixed `floor` included), so the cached results come from the same code the port transcribes.
- `tests/test_golden.py` + `tools/golden_report.py` + markers `slow` (75 lumped) / `jc_slow` (3 JC), both excluded by default (`addopts`). `pytest -m slow` = lumped only (3 min 34 s), `pytest -m "slow or jc_slow"` = everything; `/golden` runs the latter with the 3 JC cases `--deselect`ed unless invoked as `/golden --jc`. Results are cached in `tests/.golden_cache/` (git-ignored) for `/golden`.

## Golden results (2026-10-20, this container, pure Python)
- Lumped, 5 timed cases (first of each span; Excel vs Python, outputType 0):

  | row | L (m) | f (Hz) | time (s) | max rel err |
  |---|---|---|---|---|
  | 20 | 3 | 2 | 2.85 | 3.4e-13 |
  | 35 | 6 | 2 | 2.87 | 9.5e-14 |
  | 50 | 12 | 2 | 2.64 | 1.2e-13 |
  | 65 | 24 | 2 | 2.74 | 1.9e-13 |
  | 80 | 48 | 2 | 2.79 | 8.4e-14 |

- Lumped, full set: 75/75 pass, 213.7 s, max rel err 8.3e-13 (row 66, max displacement), median per-case max 1.0e-13, max applied force exact everywhere. Tolerance recorded in `test_golden.py`: 5e-12 (owner's decision, ~6x margin over the observed worst).
- JC baseline for Stage 5 (rows 96-98, L = 24 m, stepQTY 40, 25135 samples, unballanceStepQTY = 24.546): f = 3 Hz: portalFrameHeight 4.047 m, pivotSegQTY 87, pipeSegQTY 666; f = 7.5 Hz: 2.232 m, 50, 592; f = 22 Hz: 1.104 m, 27, 546. Each case runs ≈ 1,006,400 MoC steps (25160 samples × 40) over pipeSegQTY cells ≈ 5.5e8-6.7e8 cell updates, i.e. hours in pure Python. A background JC run started in the previous session was killed by the worker restart before its elapsed time could be recorded; no wall-clock baseline exists. The JC tolerance in `test_golden.py` is 1e-12, unmeasured; it may be relaxed only with evidence from an actual run.

## Findings worth knowing (all preserved, see DEVIATIONS.md)
- D-1/D-2/D-11 (historical, now fixed upstream): the original `CLng(val - 0.5)` floor made the JC MoC even-cell update run 1 step in 4 and made multi-column valve patterns extrapolate the closure at some positions. With the fixed floor the MoC alternates every step and multi-column patterns equal their column-major flattening exactly. Any Excel fixtures must be generated with the *fixed* VBA module.
- D-8: a single-row (horizontal) `forceHistory` leaves `iB = UBound(1) + 1` after the first block and fails with subscript out of range (swallowed into `#VALUE!` by JC). With the fixed floor an integer delay no longer escapes this (`kOverlap = 0`).
- The SDOF integrator evaluates `aNew` from the old `x`, `v` (explicit, not average-acceleration Newmark); with zero damping its amplitude grows ≈ 2.5 % per cycle at ω·dt ≈ 0.016 (stepQTY = 10, 5 Hz, 100 Hz samples). The cycle time-mean stays at F/k. This is why the static-deflection structure test integrates with stepQTY = 100.
- The free-decay `Do While x * xZero > 0.01` loop only runs when |x| > 0.1 (model units); for typical metre-scale displacements it never executes. If it does run with zero damping and friction it does not terminate (same in VBA).
- JC with a negligible portal-frame height (pivotSegQTY = 4) divides by zero in `interpFractionB(3)` (D-4) and the VBA returns `#VALUE!`; Python raises.

## Judgement calls made (flag if you disagree)
- Python inputs are 2-D numpy arrays with 1-based meaning (padded by `vba_2d`); 1-D arrays take the `AddDimension` path; the broken `ArrayStartOne` path is unreachable.
- VBA runtime errors: numpy arithmetic in the entry points runs under `np.errstate(divide/invalid/over = "raise")` so it raises where VBA raised; pure-Python float overflow (→ inf) and Integer/Long overflow are not emulated. `On Error GoTo ErrFound` re-raises (D-9) instead of returning an empty array.
- The implicit Double→Long assignment at VBA line 244 (`i = modDbl(...) + 1`) is written as an explicit `clng`.
- `^` is `**`: for integer exponents both call C `pow`; last-bit differences against Excel's runtime are possible and should be absorbed by the golden tolerance. `(-varA / varB) ^ (1 / 3)` would be complex in Python where VBA raises error 5; only reachable with non-physical inputs.
- Loops whose control variable is read after the loop (`jB`, `iB`) are while loops; all other `For` loops are `range` loops.

## Open issues
- JC golden cases never run; `GetPressureResponse` has no golden case (would need a UDF call with a committed valve pattern in the workbook).
- Rows 100-101 of `curve_10in` hold pasted numbers (no formula) and were skipped by the extractor; if they are meant to be cases they need live formulas in the workbook.
- Performance: pure Python; JC cases are hours each (see baseline above). Stage 5 (Numba) target.
- CLAUDE.md's dependency rule still names only numpy, pytest, ruff, hypothesis, numba; the owner approved openpyxl and oletools as `dev` extras (2026-10-20). The rule's wording was left to the owner.
- Marker interpretation: "whole curve set slow" was implemented as `slow` on the 75 lumped cases and `jc_slow` (only) on the 3 JC cases, so that `pytest -m slow` excludes JC as requested.
- numba and hypothesis are permitted by `CLAUDE.md` but not added to `pyproject.toml`. oletools is a `dev` extra (approved) but no tool uses it yet; the VBA-module identity check in this session used an ad-hoc MS-OVBA decompressor that is not in the repo (`olevba` would do the same).
- The project hooks in `.claude/settings.json` load only when Claude Code is started from the repository root.

## Next action
Stage 2 (behaviour-preserving refactor) may begin with `pytest -m slow` as the gate (3.5 min; run before each refactor commit, `pytest -q` for the fast suite). Keep the 3 JC cases unrun until Stage 5 (Numba), where their first full run and a measured JC tolerance are deliverables. If `GetPressureResponse` needs a golden case, add a UDF call with a committed valve pattern to the workbook and extend `tools/extract_fixtures.py`.
