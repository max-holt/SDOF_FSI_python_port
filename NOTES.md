# NOTES — session handoff

## Current stage
Stage 4.0 (performance baseline of the literal port) done 2026-10-21: `tools/bench.py`, `docs/bench/1adaddd.json`, `docs/bench/README.md`. No solver changes. Stage 1 (literal port) complete and **verified against Excel for both peak solvers**: all 75 `GetPeakResponse` golden cases pass at RTOL 5e-12 (max observed 8.3e-13) and, since 2026-10-21, all 3 `GetPeakResponseJC` golden cases pass at RTOL 5e-12 (max observed 8.6e-13; first full run, 1 h 20 min in pure Python). `GetPressureResponse` has no golden case yet (the workbook's `Example` sheet exercises it only on a demo pattern with cached values; not extracted). `src/surge_sdof/legacy_port.py` holds the line-for-line transcription; `vba_compat.py` the VBA-semantics helpers.

## Done
- `vba_compat.py`: `clng` (half-to-even), `vba_floor` (literal transcription of the fixed VBA `max(CLng(val - 0.5), CLng(val + 0.5) - 1)`, pinned against `math.floor`), `mod_dbl` (ordinary floored modulo now), `sign`, `min_unsigned`, `max_unsigned`, plus `ubound`/`vba_2d` for the padded 1-based array convention. `tests/test_vba_compat.py` pins them against the VBA definitions.
- Upstream `floor` fix applied: `main` merged, `vba_floor`/`mod_dbl` updated, the tests that pinned the old bug (mod_dbl table, parity test, D-11 multi-column pressure test, D-8 trigger condition) re-pinned to the fixed behaviour. DEVIATIONS D-1, D-2, D-11 are status "fixed" with the reason "source corrected upstream".
- `legacy_port.py`: `min`, `max` (shadow the built-ins on purpose, VBA tie semantics), `get_dimension`, `add_dimension`, `array_start_one` (D-3), `interp_fraction_a`, `interp_fraction_b` (D-4), `solve_poly`, `get_pressure_response` (D-6, D-11), `get_peak_response` (D-7, D-8), `get_peak_response_jc` (D-9, dead `useUndamped` branch kept behind `use_undamped = False`, short-pipe fallback). Conventions are documented in the module header.
- Tests (178 passing, `pytest -q` ≈ 5 s; run with the `.venv` interpreter, the `pytest` on PATH lacks numpy): `test_vba_compat.py`, `test_helpers.py`, `test_quirks.py` (pins for DEVIATIONS D-12 … D-21 on small synthetic inputs; reads solver locals `v_av` and the sub-step `force_b` through a `sys.settrace` probe on the solver frame, and records `mod_dbl`/`sign` calls via `monkeypatch`, so `legacy_port.py` is untouched), `test_smoke.py` (each entry point on a 100-sample step force, stepQTY = 10, all output types, 1-D and 2-D inputs, fallback, raised error paths), `test_structure.py` (gap = 0 & ratio = 1 ≡ gap = 1e9 bitwise on both peak solvers; undamped constant-force midline = F/k within 1 % on the lumped solver; JC with fluidArea = 0 ≡ lumped bitwise; column-major flattening identity on all three entry points).
- DEVIATIONS.md rows D-1 … D-11: D-1, D-2, D-11 "fixed" (upstream source fix), the rest "preserved". Rows D-12 … D-22 added from `docs/port_review.md` §3 (owner's decision, 2026-10-20): §3.1 a-e as "fixed" (Python-vs-VBA differences: complex `solvePoly` seed, no Integer/Long overflow, mixed float overflow, `pow` runtime, return-array convention), §3.2 a-f as "preserved" (`vAv` divisor, force-ramp plateau, parity discontinuity, friction dead zone, phase-3 threshold, `GetPressureResponse` 2x closure time). Every row D-12 … D-21 now has a pinning test in `tests/test_quirks.py` (D-15 golden suite, D-16/D-22 smoke tests as before). D-12 was corrected while pinning it: with numpy 2.5 the lumped solver does *not* raise for `EI < 0`; it returns a real-cast garbage array under `ComplexWarning` (only the JC path raises, a `TypeError` at `clng(complex)` in `pivotSegQTY`). §3.1-a of the review assumed a `TypeError` on both paths.
- Port review: `port-reviewer` subagent ran on `git diff 125e73e..HEAD` (diff + VBA only): **no correctness findings**. Its two non-blocking notes were applied: D-11 wording now states the even-row-count condition; the `solve_poly` complex-root edge case is listed below.
- Stage 1 close-out review (2026-10-20): `docs/port_review.md`. Two passes: the `port-reviewer` subagent on `git diff 125e73e HEAD` (no correctness findings; 4 observations) and a line-by-line read of `legacy_port.py` against the VBA. The document holds (1) the table of every VBA constant with role and unit-dependence, (2) the duplicated-code map for Stage 4 with VBA and Python line ranges (SDOF step x8, force interpolation x6, index walk x6, JC MoC block x4 byte-identical, pressure half-loops x2, shared set-up), (3) five documented-but-unrecorded port/VBA differences (complex `solvePoly` seed, Long/Integer overflow, mixed float-overflow semantics, `^` vs `**`, return-array pad) and six preserved VBA behaviours not yet in DEVIATIONS.md (`vAv` divisor 2N-1 over 2N+1 terms, force ramp over stepQTY-1 sub-steps, MoC parity index jumps at phase boundaries, `sign(v, 1e-6)` dead-zone, `x^2 > 0.01` phase-3 threshold, 2*closureTime pressure horizon), (4) the golden blind-spot list. No code changed.
- Golden fixtures (2026-10-20): the owner committed the source workbook `tests/fixtures/source/surge_force_data.xlsm`. `tools/extract_fixtures.py` (needs openpyxl, a `dev` extra) writes `tests/fixtures/curve_10in/{force_history.csv, params.json, cases.csv}` from the Excel-cached values: full `Sheet1` extent (25303 rows), `n_samples = 25135`, 78 cases with `source_row` and `solver` columns (75 lumped rows 20-94, 3 JC rows 96-98). The workbook's `Module1` was decompressed and its 16 ported procedures are byte-identical to `legacy/vba/Existing Code.bas` (fixed `floor` included), so the cached results come from the same code the port transcribes.
- Example-sheet fixtures (2026-10-21): `tools/extract_fixtures.py` also writes `tests/fixtures/example/cases.json` (three self-contained cases: `example_pressure` from B3:B7 / J33:J42 / C3:C123 with `pipeArea = PI()*(J39^2/4)` and Excel `PI()` = IEEE double pi, `example_lumped` from E3:E27 / J6:J14 / F3:F7, `example_jc` from E3:E27 / J19:J29 / G3:G7) and `tests/fixtures/manifest.json` listing both fixture sets. `test_golden.py` reads the manifest; the Example cases are unmarked fast tests (`test_golden_example`, milliseconds) at RTOL 1e-12 (owner's decision); measured 1.2e-14 / 2.8e-14 / 2.6e-15. `GetPressureResponse` thereby has its first golden case.
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
- JC, full set (2026-10-21, `pytest -m jc_slow --durations=0`, sequential, pure Python): 3/3 pass at the provisional 1e-12.

  | row | f (Hz) | N | time | max rel err | worst output |
  |---|---|---|---|---|---|
  | 96 | 3 | 666 | 1826.8 s (30.4 min) | 8.6e-13 | max velocity |
  | 97 | 7.5 | 592 | 1564.5 s (26.1 min) | 2.1e-14 | max displacement |
  | 98 | 22 | 546 | 1411.5 s (23.5 min) | 8.4e-15 | max static equivalent force |

  Total 1 h 20 min; the Stage 4.0 extrapolation (29/26/24 min) was within 5 %. Max applied force exact in all three. JC tolerance in `test_golden.py` set to 5e-12 by the lumped rule (5x the worst 8.6e-13 = 4.3e-12, rounded up to one significant figure). Row 96 (lowest frequency, largest displacement) is the only case near the lumped worst; the other two are at 1e-14, so the MoC block, `dF`, `dacayFactor`, `vAv` and the fluid-corrected set-up (port_review §4 item 2) are now pinned by Excel.
- JC case geometry (rows 96-98, L = 24 m, stepQTY 40, 25135 samples, unballanceStepQTY = 24.546): f = 3 Hz: portalFrameHeight 4.047 m, pivotSegQTY 87, pipeSegQTY 666; f = 7.5 Hz: 2.232 m, 50, 592; f = 22 Hz: 1.104 m, 27, 546. Each case runs 1,006,382 sub-steps over pipeSegQTY cells ≈ 5.5e8-6.7e8 cell updates; measured wall times above.

## Stage 4.0 — performance baseline (2026-10-21, this container, pure Python, numba absent)
`tools/bench.py --profile` (median of 3; Intel Xeon @ 2.80 GHz, Python 3.13.16, numpy 2.5.4; full numbers and the top-15 cProfile tables in `docs/bench/1adaddd.json`):

| case | median | per sub-step | note |
|---|---|---|---|
| (a) lumped row 20 (L 3 m, f 2 Hz) | 3.09 s | 3.07 µs | golden rel err 3.4e-13 |
| (b) lumped row 80 (L 48 m, f 2 Hz) | 3.12 s | 3.10 µs | golden rel err 8.4e-14 |
| (c) JC row 96 (L 24 m, f 3 Hz, N = 666), first 2000 samples | 141.5 s | 1747 µs | 80,982 sub-steps; not a golden value |
| (d) Example-sheet `GetPressureResponse` (121 outputs) | 9.3 ms | - | matches Excel's cached `Example!C3:C123` to 1.2e-14 (now the golden case `example_pressure`) |

Sub-step count = `n·stepQTY + floor(unb·stepQTY) + 1` (verified by counting `min_unsigned` / `mod_dbl` calls). Per-sub-step cost does not depend on `n`, so the full JC golden cases extrapolate to ≈ 29 min (row 96, N 666), ≈ 26 min (row 97, N 592), ≈ 24 min (row 98, N 546) each in pure Python; confirmed by the actual run (30.4 / 26.1 / 23.5 min, see Golden results).

**Top 5 hotspots, measured (cProfile share of profiled time; real time in brackets):**
1. JC: the `get_peak_response_jc` body itself, 87 % (166 of 190 s profiled; 141.5 s real). This is the inline MoC sweeps: per sub-step ≈ 9,000 numpy element reads/writes (`array_a[m, n]`, 0.08-0.12 µs each) and ≈ 10,000 numpy-scalar arithmetic operations over N = 666 cells, plus the `vAv` reduction (2N+1 element reads and adds on even steps, ≈ 14 % of an even step). Nothing here is a function call, so cProfile cannot split it further; the split above is inferred from per-operation timings, not measured.
2. JC: `interp_fraction_a` + `interp_fraction_b`, 12 % profiled (53.9 M calls each, one per cell per sub-step; 0.14 µs/call unprofiled → ≈ 190 of 1747 µs per sub-step, 11 %). Precomputing them once per `n` (port_review §2.5) buys at most that.
3. Lumped: the `get_peak_response` body, 64 % profiled (4.6 of 7.2 s; 3.09 s real): SDOF arithmetic on numpy scalars. Experiment (bench-free, same solver, `vba_2d` monkeypatched so `force_history[i, j]` returns a Python float and the whole state stays `float`): 2.99 s → 2.01 s, 1.49x, results bitwise equal. So numpy-scalar state costs ≈ 1/3 of lumped wall time.
4. Lumped: `abs` 15 % (8.26 M calls = 8.2 per sub-step; `abs(np.float64)` is 0.13 µs vs 0.04 µs for `float`), `min_unsigned` 18 % cumulative (1 call per sub-step, 0.9 µs self), `sign` 6 % (2.9 per sub-step), `max` 2 %. Together the per-sub-step helper calls are of the same order as the numpy-scalar overhead.
5. Everything else is < 1 %: `mod_dbl`/`vba_floor`/`clng` 0.2 % of JC, `ubound` 0.7 % of lumped (`ubound(force_history, …)` is re-evaluated every sub-step), `solve_poly` 12 calls, `get_pressure_response` 9 ms total.

**Verdict on the expectation** ("`interp_fraction_a/b` and numpy-scalar arithmetic dominate"): half right. In the JC kernel the inline MoC sweeps dominate (≈ 87 %); `interp_fraction_a/b` are the only named functions that register but at ≈ 12 % they are a secondary target. Numpy-scalar arithmetic is real in both kernels (1.49x on lumped by experiment; in JC it is combined with numpy element indexing, which is of similar cost), but in the lumped kernel the call overhead of `min_unsigned`/`sign`/`max`/`abs` (≈ 13 calls per sub-step) is just as large. Any Stage 4 rewrite of these helpers must stay bit-identical (D-12 … D-21 pins in `tests/test_quirks.py`); the bench's "result vs prev" column flags a digest change.

## Findings worth knowing (all preserved, see DEVIATIONS.md)
- D-1/D-2/D-11 (historical, now fixed upstream): the original `CLng(val - 0.5)` floor made the JC MoC even-cell update run 1 step in 4 and made multi-column valve patterns extrapolate the closure at some positions. With the fixed floor the MoC alternates every step and multi-column patterns equal their column-major flattening exactly. Any Excel fixtures must be generated with the *fixed* VBA module.
- D-8: a single-row (horizontal) `forceHistory` leaves `iB = UBound(1) + 1` after the first block and fails with subscript out of range (swallowed into `#VALUE!` by JC). With the fixed floor an integer delay no longer escapes this (`kOverlap = 0`).
- The SDOF integrator evaluates `aNew` from the old `x`, `v` (explicit, not average-acceleration Newmark); with zero damping its amplitude grows ≈ 2.5 % per cycle at ω·dt ≈ 0.016 (stepQTY = 10, 5 Hz, 100 Hz samples). The cycle time-mean stays at F/k. This is why the static-deflection structure test integrates with stepQTY = 100.
- The free-decay `Do While x * xZero > 0.01` loop only runs when |x| > 0.1 (model units); for typical metre-scale displacements it never executes. If it does run with zero damping and friction it does not terminate (same in VBA).
- JC with a negligible portal-frame height (pivotSegQTY = 4) divides by zero in `interpFractionB(3)` (D-4) and the VBA returns `#VALUE!`; Python raises.
- D-12: `EI < 0` (or `L * massPerUnitLen < 0`) makes `solvePoly`'s seed complex; the lumped solver then returns a garbage real array with only a `ComplexWarning` (VBA: error 5). Non-physical input, but silent. A Stage 2+ input check would be a new behaviour and needs the owner's decision.
- D-14: `massPerUnitLen = 1e308` overflows in pure-Python set-up arithmetic and the lumped solver returns `[nan, 0, 0, 0, FMax]` without raising (VBA: error 6); overflow inside the numpy integration state raises `FloatingPointError`.

## Judgement calls made (flag if you disagree)
- Python inputs are 2-D numpy arrays with 1-based meaning (padded by `vba_2d`); 1-D arrays take the `AddDimension` path; the broken `ArrayStartOne` path is unreachable.
- VBA runtime errors: numpy arithmetic in the entry points runs under `np.errstate(divide/invalid/over = "raise")` so it raises where VBA raised; pure-Python float overflow (→ inf) and Integer/Long overflow are not emulated. `On Error GoTo ErrFound` re-raises (D-9) instead of returning an empty array.
- The implicit Double→Long assignment at VBA line 244 (`i = modDbl(...) + 1`) is written as an explicit `clng`.
- `^` is `**`: for integer exponents both call C `pow`; last-bit differences against Excel's runtime are possible and should be absorbed by the golden tolerance. `(-varA / varB) ^ (1 / 3)` would be complex in Python where VBA raises error 5; only reachable with non-physical inputs.
- Loops whose control variable is read after the loop (`jB`, `iB`) are while loops; all other `For` loops are `range` loops.

## Open issues
- Two of the §3.2 items are to be raised with the lead author as more than a DEVIATIONS row (owner to name which two; the note naming them did not reach this session). §3.1-d (now D-15): Numba/LLVM lowers integer-literal `**` to multiplication, which measurably differs from C `pow` (used by both Python and numpy `**`); Stage 5 must judge this against the golden tolerance rather than expect bit-identity.
- Rows 100-101 of `curve_10in` hold pasted numbers (no formula) and were skipped by the extractor; if they are meant to be cases they need live formulas in the workbook.
- Performance: pure Python; measured baseline in the Stage 4.0 section (JC cases 23-30 min each, 1 h 20 min for `pytest -m jc_slow`). Stage 5 (Numba) target; the JC golden run is its acceptance test and now has a measured tolerance (5e-12).
- `GetPressureResponse` has a single golden case (Example sheet, 5-value pattern, single column); multi-column valve patterns and the pump/friction branches at other operating points are still unexercised by Excel data.
- Marker interpretation: "whole curve set slow" was implemented as `slow` on the 75 lumped cases and `jc_slow` (only) on the 3 JC cases, so that `pytest -m slow` excludes JC as requested.
- numba and hypothesis are permitted by `CLAUDE.md` but not added to `pyproject.toml`. oletools is a `dev` extra (approved) but no tool uses it yet; the VBA-module identity check in this session used an ad-hoc MS-OVBA decompressor that is not in the repo (`olevba` would do the same).
- The project hooks in `.claude/settings.json` load only when Claude Code is started from the repository root.

## Approved fixes (lead author, 21 Oct 2026)
Apply in the Stage 4.4 session, or earlier if Stage 4.2 builds the running step counter directly (it should: building the per-phase index only to replace it is wasted work).

Approved fixes (lead author, 21 Oct 2026):
F-1 vAv denominator: 2N+1 (number of terms), was 2N-1. port_review §3.2a.
F-2 MoC parity: continuous even/odd alternation for the whole run via a single running step counter in the refactored JC solver; the literal port keeps the per-phase index. Intent: alternation never double-steps a half-grid at a phase boundary. port_review §2.5, §3.2c. Differential tests vs legacy_port.py for JC must therefore compare with a tolerance only on cases where the literal port's parity sequence is continuous (phase 3 not entered and phase-1 exit k odd); for the others, assert the refactored result against a legacy run patched to a running counter, and record the before/after difference.
F-3 JC fidelity (full vs simplified) deferred to Stage 5b sweep. coupling.py is the only module the decision may touch.

Bookkeeping when applied: F-1 changes DEVIATIONS D-17 and F-2 changes D-19 from "preserved" to "fixed" (with the pinning tests in `tests/test_quirks.py` re-pinned to the new behaviour); `legacy_port.py` itself stays literal.

## Next action
Stage 4.1 (owner's instruction, 2026-10-20). Run `tools/bench.py` at the end of every Stage 4/5 session and commit `docs/bench/` (CLAUDE.md); compare the "result vs prev" column, which must read `same` for a behaviour-preserving commit. No document in the repo defines the Stage 4.1 scope; the only stage material beyond Stage 1 is the refactor map in `docs/port_review.md` §2 (Stage 4) and the Numba target (Stage 5), so record the 4.1 scope in this file at the start of that session before touching `src/`. Read `docs/port_review.md` §2 (refactor map, §2.5 parity hazard) and §4 (blind spots) first. Gate: `.venv/bin/python -m pytest -q` before every commit, `-m slow` (3.5 min) before any commit touching `src/`; `tests/test_quirks.py` must stay green as written (a change to a pinned quirk needs a DEVIATIONS.md row). The 3 JC cases have run once (1 h 20 min, all pass, tolerance 5e-12 measured); re-run them (`pytest -m jc_slow`, background) before any commit that touches the JC solver path, and before the Stage 5 Numba acceptance. If `GetPressureResponse` needs a golden case, add a UDF call with a committed valve pattern to the workbook and extend `tools/extract_fixtures.py`.
