# NOTES — session handoff

## Current stage
Stage 4.2 (refactor, JC path) done 2026-10-21: `src/surge_sdof/moc.py`, `coupling.JunctionCoupling`,
`structure.jc_params`, `response.peak_response_jc` (shared `_integrate`), approved fixes F-1 and
F-2 applied flag-first and flipped to the defaults (`vav_denominator="fixed"`, `parity="running"`;
the legacy flags reproduce `legacy_port.get_peak_response_jc` bitwise), DEVIATIONS D-17/D-19 "fixed",
JC differential sweep (100/100 bitwise), bench `(g)` case and reference ratios. Finding: F-1 is
numerically inert for the outputs (rounding level; see "Stage 4.2 — F-1/F-2 before/after").
Stage 4.1 (refactor, first seam) done 2026-10-21: `src/surge_sdof/structure.py`, `loads.py`, `coupling.py` (`NoCoupling` only), `response.py` (lumped `peak_response`), `docs/architecture.md`, `tests/test_differential.py` (sweep + golden differential against the frozen `legacy_port.py`, 335 tests, all bitwise), DEVIATIONS D-23, bench `docs/bench/4ea09d2.json`. `legacy_port.py` is unchanged and remains the reference until Stage 6. Stage 4.0 (performance baseline of the literal port) done 2026-10-21: `tools/bench.py`, `docs/bench/1adaddd.json`, `docs/bench/README.md`. Stage 1 (literal port) complete and **verified against Excel for both peak solvers**: all 75 `GetPeakResponse` golden cases pass at RTOL 5e-12 (max observed 8.3e-13) and, since 2026-10-21, all 3 `GetPeakResponseJC` golden cases pass at RTOL 5e-12 (max observed 8.6e-13; first full run, 1 h 20 min in pure Python). `GetPressureResponse` has no golden case yet (the workbook's `Example` sheet exercises it only on a demo pattern with cached values; not extracted). `src/surge_sdof/legacy_port.py` holds the line-for-line transcription; `vba_compat.py` the VBA-semantics helpers.

## Stage 4.1 — scope and plan (recorded 2026-10-21 before touching `src/`)
Owner's instruction: refactor, first seam. Target layout for all of Stage 4 is in
`docs/architecture.md` (one line per module, responsibilities and what each must not know).
This session builds `structure.py`, `loads.py`, `coupling.py` (`NoCoupling` only) and the
lumped path of `response.py`; `moc.py`, the JC coupling and `pressure.py` are later sessions.
`legacy_port.py` is frozen and stays the reference until Stage 6.

Plan (one commit per module; fast + slow golden gates and the differential suite green before each):
1. `structure.py`: `solve_poly` (copied literally so the module survives the Stage 6 removal of
   `legacy_port`), `solve_portal_height`, `lumped_params`, `restoring_force(x, k, gap, ratio)`,
   `step(state, f_applied, params, dt)` on Python floats with the `minUnsigned` / `max(0, …)` /
   `sign` ladders inlined. Tests: `tests/test_differential.py` replays the legacy solver's
   per-sub-step `(f, x, v, a)` sequence (read through a `sys.settrace` probe, as
   `test_quirks.py` does; `legacy_port.py` untouched) through `step` and compares bitwise.
2. `loads.py`: `transit_delay`, `unbalance_force(history, sample_freq, length, celerity, step_qty)`
   yielding one list of per-sub-step `forceA − forceB` per sample, reproducing the delay phase
   (`forceA` held, mid-sample `Exit For`), the ramp phase with the `kOverlap` split and the
   column-major walk with the `jB > U2` clamp. Tested against the `(forceA − forceB)` sequence
   the literal port computes (same probe).
3. `response.py` + `coupling.py`: `peak_response(...)` = set-up (structure) + loads + one shared
   integration loop with `NoCoupling`; returns `PeakResponse`. Differential against
   `get_peak_response` for `outputType` 0–3 on the Example-sheet lumped case (fast), the 75
   curve cases (`slow`) and the seeded sweep.
4. `tools/bench.py`: two extra cases (`peak_response` on rows 20 and 80); run, commit `docs/bench/`,
   report the pure-Python speedup of the lumped cases. `port-reviewer` on the final diff.

Sweep design (`tests/test_differential.py`, 50 parameter sets, `random.Random(20261019)`, rtol 1e-12):
covers what the Excel oracle does not (port_review §4): `restrainFreqRatio` U(0.5, 4); `gap` =
U(0.1, 0.5) × the case's own gap-free `xMax`; `outputType` 0 always plus one of 1–3 per case;
1-D histories and 2-D with 2–3 columns (column-major); `stepQTY` ∈ {2, 7, 40}; `dynamicFric` ∈
{0, 0.005, 0.1}; `dampingPercent` U(0.5, 5) (phase 3 must terminate); `ω·dt` ≤ 0.03 so the
explicit scheme stays stable; piecewise-constant random force levels scaled to `F/k` ~ 0.05–1 so
the free-decay threshold `|x| > 0.1` is reachable; rows ≥ 2 × columns so the phase-1 walk cannot
hit D-8. Asserted: ≥ 1 case enters phase 3 (`free_decay_samples > 0`) and ≥ 1 engages the gap
(`max_displacement > gap`).

Judgement calls (flag if you disagree):
- `unbalance_force` yields per *sample* a list of the per-sub-step values rather than a flat
  per-sub-step stream, because the caller must act at sample boundaries (result history, the
  phase-1 `Exit For` truncates the last delay-phase sample). Flattened, it is exactly the
  per-sub-step sequence the test compares.
- `peak_response` runs on Python floats, so overflow no longer raises `FloatingPointError`
  mid-run as the numpy state did (D-14); it raises `FloatingPointError` at the end if the final
  state is not finite (nan/inf are absorbing in the update). Recorded as D-23 with a pin test.
- `NoCoupling` adds `0.0` to the unbalance force and supplies `0.0` in free decay: identical to
  the literal `(forceA − forceB)` / `−R` except for the sign of an exact zero.

## Stage 4.2 — scope and plan (recorded 2026-10-21 before touching `src/`)
Owner's instruction (this session): `moc.py`, `coupling.JunctionCoupling`, `response.peak_response_jc`
built from the same `_integrate` loop as `peak_response`; approved fixes F-1 and F-2 flag-first.
Amendments agreed at plan approval: (1) the `jc_slow` gate runs the new solver with the legacy
flags against the Excel fixture at the golden tolerance only (no re-run of
`legacy_port.get_peak_response_jc` on the full cases; bitwise-vs-legacy is established by the
small-grid sweep); (2) the golden before/after record is one fixed-flag run per case (F-2 is
provably zero there: `k_exit = 21` odd, phase 3 never entered).

Plan (one commit per step; fast suite before each commit, `-m slow` before each `src/` commit):
1. `moc.py`: set-up helpers called once per run (`grid_size`, `is_short_pipe`, `decay_factor`,
   `interp_fractions` as float64 arrays, literal copies of `interpFractionA/B` incl. D-4,
   `new_column`) and one kernel `step(even, a_dt, p_a, v_a, p_b, v_b, frac_a, frac_b, n_seg,
   pivot, rho_c, decay, vav_divisor, fluid_area, d_f) -> d_f` with scalar loop bodies over four
   contiguous 1-D arrays, VBA operation order, previous-cell values carried in locals; no Python
   objects (Stage 5 `@njit`s it whole). The dead `useUndamped` branch is not ported.
   Tests: fractions bitwise vs the legacy helpers; chained replay of the legacy MoC block
   (settrace probe: arrays, `d_f`, `a` per sub-step) on small grids, bitwise.
2. `coupling.py`: `JunctionCoupling` owning the column arrays and `dF`;
   `coupling_force(state, step_index)` = `moc.step(step_index % 2 == 0, a * dt, …)`, returns a
   Python float. Test: `dF` sequence vs the legacy's per-sub-step `d_f`.
3. `response.py` + `structure.jc_params` (VBA 726-729 literally; its own function, not a flag
   on `lumped_params`): `peak_response_jc(...)` with keyword-only `vav_denominator`
   ("legacy" 2N-1 | "fixed" 2N+1) and `parity` ("per_phase" | "running"), short-pipe fallback to
   `peak_response`, otherwise the shared `_integrate` under `np.errstate(raise)` (the MoC arrays
   are numpy; `rhoC = 0` and fluid overflow raise mid-run as the legacy does). Parity lives in the
   loop: with `parity="per_phase"` `_integrate` passes the VBA index `(totInd-1)*stepQTY + k`
   (phase 3 `+1`) as `step_index`; with `"running"` the running counter. Tests: Example JC case
   vs legacy (output types 0-3) at 1e-12 and vs Excel; fallback ≡ `peak_response` bitwise;
   three `jc_slow` tests (new solver, legacy flags, vs Excel at 5e-12).
4. Sweep: 50 JC parameter sets (`random.Random(20261019)`), fluidArea {0, 0.01, 0.05}, density
   1000, stepQTY {2, 7, 40}, ratio U(0.5, 4), engaged gaps, 1-D and 2-3 column histories,
   outputType 0 plus one of 1-3, fallback spans; asserted ≥ 1 phase-3 case, ≥ 1 fallback, ≥ 1
   MoC case with the gap engaged. Compared with explicit legacy flags at rtol 1e-12 (bitwise
   measured and recorded). Grids of ~20-40 cells so the fast suite grows by ~30 s.
5. Flag flip: defaults "fixed" / "running"; pin tests for the fixed behaviour on the new
   modules (the `test_quirks.py` pins on `legacy_port` stay as written); DEVIATIONS D-17 and
   D-19 → "fixed"; max relative change per sweep case (F-1 alone, F-2 alone, both) and per
   golden output recorded here and in the commit message.
6. Bench: `tools/bench.py` re-runs case (a) in-session as the reference and reports every case
   as seconds and as a ratio to (a); new case (g) `response.peak_response_jc` (legacy flags) on
   the truncated row 96 (digest must equal (c)); cell-updates/s for (c) and (g) (sub-steps ×
   pipeSegQTY / s); README rows carry the CPU model; rows go into the main table.
7. `-m jc_slow` once with the legacy flags (3 parallel single-case processes); per-case time and
   max relative error recorded. `port-reviewer` on the final diff; correctness findings only.
   Next action = Stage 4.3 (`pressure.py`).

## Stage 4.2 — done (2026-10-21)
- Modules (see `docs/architecture.md`): `moc.py` (grid set-up, tabulated interp fractions,
  four contiguous 1-D state arrays, one `step` kernel with scalar loop bodies; the dead
  `useUndamped` branch is not ported), `coupling.JunctionCoupling` (owns the column and `dF`;
  `coupling_force(state, step_index)` = `moc.step` on the half-grid `step_index % 2` selects),
  `structure.jc_params` (VBA 726-729 literally), `response.peak_response_jc` (JC set-up,
  short-pipe fallback to `peak_response`, the shared `_integrate` under `np.errstate(raise)`).
  The F-2 parity choice lives in `_integrate`: `step_index = n + off`, `off = 0` for the running
  counter, or the VBA per-phase offset fixed per sample (`(totInd-1)*s - n`, phase 3 `+1`).
- Differential suite (`tests/test_differential.py`, rtol 1e-12, legacy flags
  `vav_denominator="legacy", parity="per_phase"`): MoC replay on four small grids (5117 sub-steps,
  arrays and `dF` **bitwise**), `JunctionCoupling` `dF` sequence (bitwise), `peak_response_jc` on
  the small cases for output types 0-3 (16/16 bitwise), the Example JC case vs Excel (1e-12; it
  enters phase 3), the JC sweep (50 sets, seed 20261019; 10 fallback cases, 8 phase-3 cases of
  which 2 on the MoC path, 27 of 40 MoC cases with a discontinuous literal parity at 1→2):
  **100/100 comparisons bitwise** (summary and history). Fast suite 625 tests, 40 s (was 8 s:
  the JC sweep costs ~12 s, the flip pins ~14 s).
- Flag flip: defaults are now `vav_denominator="fixed"`, `parity="running"`; the legacy flags
  are pinned bitwise on the sweep (`test_legacy_flags_reproduce_legacy_bitwise`), the fixed
  behaviour by `test_fixed_vav_divides_by_the_number_of_terms`,
  `test_running_parity_is_continuous_across_phase_boundaries` (half-grid sequence recorded
  through `moc.step` on the D-19 case: strictly alternating; `"per_phase"` equals the legacy
  `modDbl` sequence) and `test_fixed_flags_change_only_where_expected`. DEVIATIONS D-17 and D-19
  are "fixed"; the `test_quirks.py` pins on `legacy_port` are untouched (the literal port keeps
  the quirks).
- Port review (Stage 4.2): `port-reviewer` on `git diff 5241908..293e507` (diff + VBA only):
  **no correctness findings**. It checked `moc.step` expression by expression against VBA
  795-847 (summation order of `vAv`, boundary order, sweep bounds and the `pb_prev` locals, the
  `dF` association), the tabulated fraction index ranges, `jc_params` association against VBA
  726-729, the `n + off` parity index for all three phases including the phase-1 `Exit For` and
  phase 3's `k = 1 To stepQTY`, the set-up/fallback order and the `dF + (forceA − forceB)`
  summation, and that no test was deleted, skipped or loosened and no fixture or legacy file is
  in the diff. One coverage note (not a finding): the bitwise pin of the legacy flags covers
  output type 0; histories are compared at rtol 1e-12 by the sweep fixture (observed bitwise).
- Bench (`docs/bench/293e507.json`, README row; `tools/bench.py --profile`, this container, pure
  Python, Intel Xeon @ 2.80 GHz, nothing else running). `tools/bench.py` now always re-runs the
  frozen legacy lumped case (a) in-session as the reference (also under `--only`) and reports
  every case in seconds and as a ratio to (a); JC cases also report cell-updates/s
  (sub-steps × pipeSegQTY / s); README rows carry the CPU model and are inserted into the main
  table (the stray 4ea09d2 row that had landed under the JC table was moved up).

  | case | median | × (a) | per sub-step | cells/s | result |
  |---|---|---|---|---|---|
  | (a) legacy lumped r20 | 3.195 s | 1.000 | 3.18 µs | - | same as 4ea09d2 |
  | (b) legacy lumped r80 | 3.132 s | 0.980 | 3.11 µs | - | same |
  | (e) `peak_response` r20 | 0.995 s | 0.312 | 0.99 µs | - | same |
  | (f) `peak_response` r80 | 0.933 s | 0.292 | 0.93 µs | - | same |
  | (c) legacy JC r96, 2000 samples (N 666) | 147.04 s | 46.0 | 1816 µs | 0.37 M | same |
  | (g) `peak_response_jc` r96, 2000 samples, legacy flags | 77.06 s | 24.1 | 952 µs | 0.70 M | digest equal to (c) |
  | (d) pressure example | 10.7 ms | 0.003 | - | - | same |

  **Truncated JC case (c) → (g): 1.91x from the restructure alone** (tabulated fractions, four
  1-D arrays with the previous cell carried in locals, hoisted `a·dt` and `2·rhoC`, Python-float
  SDOF state; no vectorisation, no JIT). Profile of (g): `moc.step` self 80.5 s of 81.3 s (99 %),
  `_integrate` 0.22 s, `structure.step` 0.23 s, `coupling_force` 0.17 s — the remaining cost is
  numpy element access and numpy-scalar arithmetic inside the cell sweeps, which is exactly what
  the Stage 5 `@njit` of `moc.step` removes. In the legacy (c) the two `interp_fraction` helpers
  alone were 25.5 s of 197.7 s profiled.

### Stage 4.2 — F-1/F-2 before/after
**Finding (not the expected 0.4 %): F-1 is numerically inert for the outputs.** `dF` is built
from pressures; pressures are built from velocity *differences* between neighbouring cells;
`vAv` is subtracted from every velocity of the column uniformly (end nodes included). The
divisor therefore cannot reach `dF` except through rounding: on the sweep F-1 alone changes
results by ≤ 3e-15 (0 on 31 cases), on the golden cases by ≤ 1e-14. The fix corrects the
column's mean-velocity bookkeeping (the velocities themselves do shift), not the force on the
structure. F-2 acts where the literal parity sequence is discontinuous on a fluid-coupled MoC
case: 2e-4 to 1e-2 on the sweep; provably zero on the golden cases (`k_exit = 21` odd with
`stepQTY = 40`, phase 3 never entered), confirmed by the fixed-flag runs below.

Golden JC cases, `peak_response_jc` with the defaults (F-1 and F-2 on) vs the Excel fixture
(= the legacy result to 8.6e-13), relative change per output
(static-eq. force / displacement / velocity / acceleration / applied force), one run per case:

| row | f (Hz) | N | time, fixed flags (s, 4 processes sharing 4 cores) | fixed flags vs Excel | legacy vs Excel (golden run 484b25e) | fixed vs legacy (cached `tests/.golden_cache`) |
|---|---|---|---|---|---|---|
| 96 | 3 | 666 | 975 | 7.4e-13 / 7.4e-13 / 8.6e-13 / 2.0e-13 / 0 | 7.5e-13 / 7.5e-13 / 8.6e-13 / 2.0e-13 / 0 | 1.2e-16 / 1.2e-16 / 9.5e-16 / 3.6e-16 / 0 |
| 97 | 7.5 | 592 | 876 | 2.1e-14 / 2.1e-14 / 1.9e-14 / 1.5e-14 / 0 | 2.1e-14 / 2.1e-14 / 1.8e-14 / 1.5e-14 / 0 | 0 / 0 / 3.7e-16 / 2.4e-16 / 0 |
| 98 | 22 | 546 | 799 | -8.6e-15 / -8.5e-15 / -2.5e-15 / -6.0e-15 / 0 | -8.4e-15 / -8.4e-15 / -2.7e-15 / -6.5e-15 / 0 | 1.9e-16 / 1.4e-16 / 1.8e-16 / 4.2e-16 / 0 |

Max relative change on the golden cases: **9.5e-16** (row 96, max velocity): F-2 is zero by
construction there and F-1 is rounding-level (see the finding above). All three stay inside
the golden tolerance 5e-12 with the defaults.

JC sweep, output type 0, max relative change over the five outputs vs the legacy flags
(F-1 alone = `("fixed", "per_phase")`, F-2 alone = `("legacy", "running")`, both = defaults):

| case | fluidArea | fallback | k_exit | 1→2 continuous | phase 3 | F-1 alone | F-2 alone | both |
|---|---|---|---|---|---|---|---|---|
| j00_q40_A0.05_N28 | 0.05 | - | 16 | no | - | 4.4e-16 | 2.2e-03 | 2.2e-03 |
| j01_q7_A0.05_N28 | 0.05 | - | 2 | yes | - | 3.5e-16 | 0 | 3.5e-16 |
| j02_q7_A0.01_N30 | 0.01 | - | 1 | no | - | 4.3e-16 | 1.7e-04 | 1.7e-04 |
| j03_q7_A0.05_N12 | 0.05 | yes | 1 | no | - | 0 | 0 | 0 |
| j04_q40_A0.0_N18 | 0.0 | - | 8 | no | - | 0 | 0 | 0 |
| j05_q7_A0.0_N32 | 0.0 | - | 3 | no | - | 0 | 0 | 0 |
| j06_q40_A0.01_N18 | 0.01 | - | 4 | no | - | 1.2e-16 | 7.9e-04 | 7.9e-04 |
| j07_q40_A0.0_N28 | 0.0 | - | 26 | no | yes | 0 | 0 | 0 |
| j08_q2_A0.0_N36 | 0.0 | - | 1 | yes | yes | 0 | 0 | 0 |
| j09_q40_A0.0_N22 | 0.0 | - | 6 | no | - | 0 | 0 | 0 |
| j10_q2_A0.0_N24 | 0.0 | - | 0 | no | - | 0 | 0 | 0 |
| j11_q40_A0.05_N28 | 0.05 | - | 7 | yes | - | 2.6e-16 | 0 | 2.6e-16 |
| j12_q7_A0.05_N36 | 0.05 | - | 4 | yes | - | 0 | 0 | 0 |
| j13_q40_A0.01_N20 | 0.01 | - | 7 | yes | - | 2.8e-15 | 0 | 2.8e-15 |
| j14_q7_A0.01_N34 | 0.01 | - | 5 | no | yes | 1.4e-16 | 4.7e-04 | 4.7e-04 |
| j15_q2_A0.0_N12 | 0.0 | yes | 1 | yes | - | 0 | 0 | 0 |
| j16_q40_A0.0_N20 | 0.0 | - | 4 | no | - | 0 | 0 | 0 |
| j17_q40_A0.0_N34 | 0.0 | - | 2 | no | yes | 0 | 0 | 0 |
| j18_q2_A0.01_N20 | 0.01 | - | 0 | no | - | 0 | 1.4e-03 | 1.4e-03 |
| j19_q2_A0.05_N14 | 0.05 | yes | 0 | no | - | 0 | 0 | 0 |
| j20_q40_A0.05_N18 | 0.05 | yes | 0 | no | - | 0 | 0 | 0 |
| j21_q2_A0.05_N16 | 0.05 | - | 1 | yes | - | 8.7e-16 | 0 | 8.7e-16 |
| j22_q7_A0.01_N32 | 0.01 | - | 0 | yes | - | 4.9e-16 | 0 | 4.9e-16 |
| j23_q7_A0.05_N26 | 0.05 | - | 4 | yes | - | 6.1e-16 | 0 | 6.1e-16 |
| j24_q40_A0.0_N38 | 0.0 | - | 30 | no | yes | 0 | 0 | 0 |
| j25_q40_A0.05_N22 | 0.05 | - | 16 | no | - | 2.1e-16 | 4.7e-03 | 4.7e-03 |
| j26_q40_A0.05_N40 | 0.05 | - | 22 | no | - | 0 | 9.6e-03 | 9.6e-03 |
| j27_q7_A0.0_N20 | 0.0 | yes | 0 | yes | - | 0 | 0 | 0 |
| j28_q40_A0.05_N26 | 0.05 | - | 21 | yes | yes | 3.7e-16 | 0 | 3.7e-16 |
| j29_q40_A0.0_N34 | 0.0 | - | 36 | no | - | 0 | 0 | 0 |
| j30_q2_A0.01_N18 | 0.01 | yes | 1 | yes | - | 0 | 0 | 0 |
| j31_q7_A0.0_N24 | 0.0 | - | 4 | yes | yes | 0 | 0 | 0 |
| j32_q40_A0.05_N16 | 0.05 | yes | 1 | yes | - | 0 | 0 | 0 |
| j33_q40_A0.01_N28 | 0.01 | - | 15 | yes | - | 0 | 0 | 0 |
| j34_q7_A0.01_N24 | 0.01 | - | 6 | yes | - | 2.0e-16 | 0 | 2.0e-16 |
| j35_q7_A0.0_N36 | 0.0 | - | 2 | yes | - | 0 | 0 | 0 |
| j36_q40_A0.0_N22 | 0.0 | - | 11 | yes | - | 0 | 0 | 0 |
| j37_q7_A0.05_N12 | 0.05 | yes | 1 | no | - | 0 | 0 | 0 |
| j38_q40_A0.05_N48 | 0.05 | - | 7 | yes | - | 0 | 0 | 0 |
| j39_q40_A0.01_N38 | 0.01 | - | 7 | yes | - | 5.6e-16 | 0 | 5.6e-16 |
| j40_q40_A0.01_N48 | 0.01 | - | 35 | yes | yes | 0 | 0 | 0 |
| j41_q2_A0.01_N28 | 0.01 | - | 0 | no | - | 3.6e-16 | 9.8e-04 | 9.8e-04 |
| j42_q2_A0.01_N12 | 0.01 | yes | 1 | yes | - | 0 | 0 | 0 |
| j43_q40_A0.05_N42 | 0.05 | - | 5 | yes | - | 9.9e-16 | 0 | 9.9e-16 |
| j44_q40_A0.0_N18 | 0.0 | - | 10 | no | - | 0 | 0 | 0 |
| j45_q2_A0.01_N32 | 0.01 | - | 0 | no | - | 0 | 5.1e-04 | 5.1e-04 |
| j46_q7_A0.01_N30 | 0.01 | - | 6 | yes | - | 0 | 0 | 0 |
| j47_q7_A0.01_N18 | 0.01 | - | 4 | yes | - | 3.9e-16 | 0 | 3.9e-16 |
| j48_q7_A0.0_N12 | 0.0 | yes | 0 | yes | - | 0 | 0 | 0 |
| j49_q7_A0.0_N24 | 0.0 | - | 3 | no | - | 0 | 0 | 0 |


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

## Stage 4.1 — done (2026-10-21)
- Modules (see `docs/architecture.md` for responsibilities and the fixed interfaces):
  `structure.py` (`solve_poly` literal copy, `solve_portal_height`, `lumped_params`,
  `effective_displacement` / `restoring_force`, `step` on Python floats with the `minUnsigned` /
  `max(0, |x| − gap)` / `sign` ladders inlined and `dt / 2` hoisted), `loads.py` (`transit_delay`,
  `overlap_substeps`, `unbalance_force` generator: one list of per-sub-step `forceA − forceB` per
  sample, ramp fractions tabulated once), `coupling.py` (`Coupling` protocol, `NoCoupling`),
  `response.py` (`PeakResponse` dataclass, `peak_response`, shared `_integrate` loop: sample loop,
  max trackers, 0-based result history, free decay, D-23 overflow checks).
- `tests/test_differential.py`: `sys.settrace` probe on `legacy_port.get_peak_response` (set-up
  constants, per-sub-step force / pre-state / post-state); seed 20261019, 50 parameter sets
  (`stepQTY` {2, 7, 40}, 1-D and 2-/3-column histories, `dynamicFric` {0, 0.005, 0.1}, ratio
  U(0.5, 4), gap 10-50 % of the gap-free `xMax`, damping U(0.5, 5) %, ω·dt ≤ 0.03); 20 cases enter
  phase 3, 49 engage the gap (both asserted ≥ 1). Each module is compared at rtol 1e-12:
  `step` replays every legacy sub-step (49,822 sub-steps), `unbalance_force` reproduces every
  per-sample sequence, `peak_response` matches for `outputType` 0 and one of 1-3 per case, the
  Example-sheet lumped case for 0-3 (and Excel at 1e-12), and the 75 curve cases (`slow`, 0 and
  Excel at 5e-12). **Measured: bitwise equal in every comparison** (summary 50/50, histories
  50/50, Example 4/4, step and loads sequences 50/50) — the rtol is the contract, bitwise the
  observation. Error paths pinned: D-7 (`stepQTY = 1`), D-8 (single-row history), D-23.
- Three gates run before each `src/` commit: fast suite (442 tests, ≈ 8 s), `-m slow` (75 golden
  + 75 differential curve cases, ≈ 10 min). All green.
- Bench (`docs/bench/4ea09d2.json`, README row): the lumped golden cases through
  `response.peak_response` vs the literal port, pure Python, same inputs, results `same`:
  row 20 3.235 s → 0.910 s (3.22 → 0.91 µs/sub-step, **3.55x**),
  row 80 3.107 s → 0.925 s (3.08 → 0.92 µs/sub-step, **3.36x**).
  That is the speed-up from the restructure alone (Python-float state, inlined helpers, hoisted
  constants; no vectorisation, no JIT). The remaining cost per sub-step is the `step` call, the
  `coupling_force` call, the generator and the four max trackers.
  Re-timed afterwards with nothing else running (`--only`, not written): 3.24 / 3.32 s vs
  0.95 / 0.93 s, same conclusion. Profile of `response_r20` (cProfile, one run, 1,005,523
  sub-steps): `_integrate` self 1.34 s (loop, trackers, calls), `step` self 1.09 s, `abs`
  0.81 s (7.25 M calls, 7.2 per sub-step), `unbalance_force` 0.56 s cumulative, `list.append`
  0.16 s, `NoCoupling.coupling_force` 0.10 s. Next lever (Stage 5) is the JIT; in pure Python
  the remaining per-sub-step cost is call overhead, not arithmetic.
- Port review (Stage 4.1): `port-reviewer` on `git diff 08515b3..HEAD` (diff + VBA only):
  **no correctness findings**. It checked the six exactness claims (half_dt, the inlined ladders,
  the tabulated ramp fractions incl. kOverlap ∈ {0, stepQTY}, the phase-1 Exit For / jB-iB
  re-base, phase 3, the static-equivalent force) against the VBA, fuzzed the ladders and the
  dt/2 rewrite bitwise (0 mismatches), and ran its own bitwise script over the sweep, the Example
  case and constructed kOverlap edge cases for output types 0-3 (0 mismatches). One
  non-correctness note (a stale docstring reference) was fixed in the follow-up commit.

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
- **F-1 to raise with the lead author**: the approved `vAv` divisor fix is numerically inert for
  the solver outputs (rounding level on the golden cases and the sweep) because `dF` depends on
  pressures, which depend on velocity differences only, and `vAv` shifts every velocity uniformly.
  The fix is applied as approved; whether the mean-velocity subtraction itself is the intended
  model (it only bookkeeps the column's mean velocity and never reaches the force) is a modelling
  question for the owner, not a port question.
- The fast suite is now 40 s (was 8 s before Stage 4.2): the JC sweep (~12 s) and the F-1/F-2
  pins, which run the sweep three more times (~14 s). If this matters, the pins can share the
  sweep's cached runs.
- `pytest -m jc_slow` now holds 6 tests: the 3 literal-port golden cases (80 min) and the 3
  `peak_response_jc` legacy-flag cases (~13-16 min each in pure Python).
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

Flag-first approach for this (owner's instruction, Stage 4.2 session): both fixes are built behind keyword flags defaulting to the VBA behaviour, the differential suite passes bitwise on the legacy flags, then the defaults flip; this supersedes the tolerance-only comparison note under F-2 above.

Bookkeeping when applied: F-1 changes DEVIATIONS D-17 and F-2 changes D-19 from "preserved" to "fixed" (with the pinning tests in `tests/test_quirks.py` re-pinned to the new behaviour); `legacy_port.py` itself stays literal.

## Next action
Stage 4.3: `pressure.py` — `get_pressure_response` (valve/pump MoC) as a standalone driver against
the interface row in `docs/architecture.md`; differential against `legacy_port.get_pressure_response`
on the Example-sheet case (Excel at 1e-12) and a seeded sweep covering what port_review §4 item 1
lists (fully-closed branch, pump ramp, the two friction clamps D-6, the `outMax` truncation,
multi-column patterns). Keep the two half-loops' asymmetry (0.9 vs 0.9·rhoC, D-6) literal. Gates
as before (`pytest -q`, `-m slow` before any `src/` commit). Not touching the JC path, so no
`jc_slow` re-run is needed unless `response._integrate` changes.

Previous next action (Stage 4.2, kept for the record): `moc.py` + the JC coupling +
`response.peak_response_jc` with F-1/F-2 flag-first — done, see "Stage 4.2 — done".

Previous next action (Stage 4.1, owner's instruction, 2026-10-20), kept for the record: Run `tools/bench.py` at the end of every Stage 4/5 session and commit `docs/bench/` (CLAUDE.md); compare the "result vs prev" column, which must read `same` for a behaviour-preserving commit. No document in the repo defines the Stage 4.1 scope; the only stage material beyond Stage 1 is the refactor map in `docs/port_review.md` §2 (Stage 4) and the Numba target (Stage 5), so record the 4.1 scope in this file at the start of that session before touching `src/`. Read `docs/port_review.md` §2 (refactor map, §2.5 parity hazard) and §4 (blind spots) first. Gate: `.venv/bin/python -m pytest -q` before every commit, `-m slow` (3.5 min) before any commit touching `src/`; `tests/test_quirks.py` must stay green as written (a change to a pinned quirk needs a DEVIATIONS.md row). The 3 JC cases have run once (1 h 20 min, all pass, tolerance 5e-12 measured); re-run them (`pytest -m jc_slow`, background) before any commit that touches the JC solver path, and before the Stage 5 Numba acceptance. If `GetPressureResponse` needs a golden case, add a UDF call with a committed valve pattern to the workbook and extend `tools/extract_fixtures.py`.
