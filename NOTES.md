# NOTES — session handoff

## Current stage
Stage 5 (speed: Numba) done 2026-10-22: `structure.step_scalars`, `moc.step` and
`response._integrate_kernel` compiled with `numba.njit(cache=True)` (no fastmath), same source in
both modes (`make test-both`), differential sweeps **bitwise** under Numba (216/216), the three
full JC golden cases in ~1 s each (were 13-30 min), hypothesis properties, three-mode bench; see
"Stage 5 — done". Next: Stage 5b.
Stage 4.4 (hygiene, no behaviour change) done 2026-10-22: SIM/C4 lint rules, numpy-style docstrings
with units and DEVIATIONS ids on the six live modules, `docs/architecture.md` as built with the
per-sub-step data flow, `README.md`, DEVIATIONS legacy-only markers; differential suite bitwise
throughout; see "Stage 4.4 — done". Next: Stage 5 (Numba).
Stage 4.3 (refactor, pressure driver) done 2026-10-21: `src/surge_sdof/pressure.py` (`pressure_response`, `get_pressure_response` alias) and `_vba_semantics.py`, differential sweep 49/50 bitwise + 1 identical raise, Example case bitwise and at 1e-12 vs Excel; see "Stage 4.3 — done" (bench row and port review recorded there).
Stage 4.2 (refactor, JC path) done 2026-10-21: `src/surge_sdof/moc.py`, `coupling.JunctionCoupling`,
`structure.jc_params`, `response.peak_response_jc` (shared `_integrate`), approved fixes F-1 and
F-2 applied flag-first and flipped to the defaults (`vav_denominator="fixed"`, `parity="running"`;
the legacy flags reproduce `legacy_port.get_peak_response_jc` bitwise), DEVIATIONS D-17/D-19 "fixed",
JC differential sweep (100/100 bitwise), bench `(g)` case and reference ratios. Finding: F-1 is
numerically inert for the outputs (rounding level; see "Stage 4.2 — F-1/F-2 before/after").
Stage 4.1 (refactor, first seam) done 2026-10-21: `src/surge_sdof/structure.py`, `loads.py`, `coupling.py` (`NoCoupling` only), `response.py` (lumped `peak_response`), `docs/architecture.md`, `tests/test_differential.py` (sweep + golden differential against the frozen `legacy_port.py`, 335 tests, all bitwise), DEVIATIONS D-23, bench `docs/bench/4ea09d2.json`. `legacy_port.py` is unchanged and remains the reference until Stage 6. Stage 4.0 (performance baseline of the literal port) done 2026-10-21: `tools/bench.py`, `docs/bench/1adaddd.json`, `docs/bench/README.md`. Stage 1 (literal port) complete and **verified against Excel for both peak solvers**: all 75 `GetPeakResponse` golden cases pass at RTOL 5e-12 (max observed 8.3e-13) and, since 2026-10-21, all 3 `GetPeakResponseJC` golden cases pass at RTOL 5e-12 (max observed 8.6e-13; first full run, 1 h 20 min in pure Python). `GetPressureResponse` has no golden case yet (the workbook's `Example` sheet exercises it only on a demo pattern with cached values; not extracted). `src/surge_sdof/legacy_port.py` holds the line-for-line transcription; `vba_compat.py` the VBA-semantics helpers.

## Stage 5 — scope and plan (recorded 2026-10-22 before touching `src/`)
Owner's instruction: speed (Numba). Step 0 done first: `tools/bench.py --profile` on the pure-Python
Stage 4.4 code (`docs/bench/b5fc5c7.json`, commit 3948a7f) so the latest bench entry is the
pre-Numba profile. Approved at plan review (decisions A-D and amendments, 2026-10-22):

1. `numba` in `pyproject` dependencies, `hypothesis` in `dev`. `@numba.njit(cache=True)` (no
   fastmath, never object-mode `@jit`) on: `structure.step_scalars(x, v, a, f_applied, mass,
   stiffness, damping, fric_acc, gap, ratio2, dt) -> (x, v, a)` with `structure.step(state,
   f_applied, params, dt)` kept as the interface as a one-line unpacking wrapper (**C**);
   `moc.step` whole, body unchanged; `response._integrate_kernel` (sample loop, max trackers,
   `_record`, `_decay_test`, free decay) with `_integrate` as the Python orchestrator: it
   concatenates the `loads.unbalance_force` per-sample lists once into a flat float64 array plus
   int64 sample offsets, unpacks `SdofParams` and the coupling (kind 0 = none with empty arrays,
   kind 1 = junction with its arrays and scalars), calls the kernel, writes `d_f` back, casts the
   maxima to Python floats, builds `PeakResponse`. Kernel signatures take floats, ints, bools and
   numpy arrays only. The Python-level `Coupling` interface (`NoCoupling`, `JunctionCoupling
   .coupling_force`, `column()`) stays for callers. `f = float(flat[i])` and `d_f =
   float(moc.step(...))` keep the SDOF state on Python floats under `NUMBA_DISABLE_JIT=1`
   (no-ops under Numba). `pressure.py` stays un-JIT'd (milliseconds; not a bottleneck).
   **A**: `numpy.errstate` has no effect in compiled code and `rhoC = 0` would raise
   `ZeroDivisionError` under Numba but `FloatingPointError` in Python mode under the Stage 4
   `errstate` block (which is removed with the kernel; without it Python mode would give `inf`
   and a numpy `RuntimeWarning`), so `peak_response_jc` checks `rho_c == 0` once at set-up and
   raises `FloatingPointError` there (precedent D-4); a
   fluid overflow under Numba propagates nan/inf and the end-of-run finiteness check raises
   (D-23 style). D-9 / D-14 / D-23 wording updated.
   **B**: `test_running_parity_is_continuous_across_phase_boundaries` monkeypatches `moc.step`,
   which a compiled loop cannot see; the probe is changed to run the pure-Python form of the
   same kernel (`_integrate_kernel.py_func`, or the function itself with JIT disabled), every
   assertion unchanged, one docstring line saying so and why.
2. Both modes green: `pytest -q` and `NUMBA_DISABLE_JIT=1 pytest -q`. `Makefile` targets `test`,
   `test-nojit`, `test-both` (numba cache wipe first: `cache=True` does not track callee changes
   in other modules), `slow`, `lint`, `bench`, `clean-cache`. **D**: minimal
   `.github/workflows/ci.yml`: lint + fast suite in both modes with the cache wipe; slow/jc_slow
   stay manual.
3. Differential tolerance: measure the max relative Numba-vs-`legacy_port` difference on the
   lumped sweep, the JC sweep (legacy flags), the small JC replays and the Example cases before
   touching any tolerance; rtol 1e-12 stays if <= 1e-13, otherwise stop and show the expression
   and both values (no arithmetic restructuring, no fastmath). Note: none of the three JIT'd
   functions contains `**` (powers live in the set-up, which stays Python), so the D-15 lowering
   concern does not apply to them; FMA contraction (LLVM does not contract without fastmath) and
   `x / 2` -> `x * 0.5` (exact) are what remain to watch.
4. Golden: `pytest -m "slow or jc_slow" --durations=0` under Numba for the Numba-affected set
   only (75 lumped golden, 75 lumped differential, 3 `peak_response_jc` golden); the 3
   literal-port JC cases are unchanged pure Python with recorded results and are not re-run
   (owner amendment, saves 80 min). Report time per case and max relative error; same stop rule.
5. Bench: `tools/bench.py` as a driver: literal cases in-process; refactored cases in a child
   with a fresh `NUMBA_CACHE_DIR` (first call = true compile time, reported separately from the
   steady-state median) and a child with `NUMBA_DISABLE_JIT=1`; a child running `outputType=1` on
   the full history (lumped r20, JC r96) reporting peak RSS; the 3 full JC golden cases via
   `peak_response_jc` (legacy flags) added to the case set; numba and llvmlite versions in the
   JSON; README gets per run a three-row table literal / refactored (pure Python) / Numba in
   seconds and ratios to the in-session (a), compile times and peak RSS; the pre-Stage-5 history
   table stays above. Print the local command and the files to commit for the owner's reference
   run.
6. `tests/test_properties.py` (hypothesis, `derandomize=True`, `deadline=None`, ~30 examples,
   small cases): gap 1e9 == gap 0 with ratio 1 bitwise; linear scaling with `dynamicFric = 0` and
   the gap never engaged (power-of-two factor: bitwise over the samples both runs compute, and
   the summary when `free_decay_samples` agree; arbitrary factor: forced-phase history at rtol
   1e-9; the absolute D-21 threshold makes phase-3 length amplitude-dependent); all maxima finite
   and >= 0, history finite; JC with `fluidArea = 0` equals lumped within 1e-12.
7. `port-reviewer` on the final diff; `docs/architecture.md` Stage 5 section (kernel signature,
   modes, cache, pressure.py un-JIT'd with the reason); README install and `make` targets;
   DEVIATIONS rows; NOTES done section; next action Stage 5b.
Commits: scope (this), one per module (structure, moc, response+coupling), Makefile/CI, bench,
properties, docs. Gates: fast suite in both modes before each commit, `-m slow` under Numba before
each `src/` commit, `-m slow` under `NUMBA_DISABLE_JIT=1` once at the end. Untouched: `legacy/`,
`tests/fixtures/`, `legacy_port.py`, `vba_compat.py`; no test deleted, skipped or loosened.

## Stage 5 — done (2026-10-22)
Commits: `3948a7f` (step 0 bench baseline `b5fc5c7.json`), `83d12d1` (scope, numba dependency,
hypothesis dev extra), `8789870` (`structure.step_scalars`), `eb35a9e` (`moc.step` compiled;
`rhoC = 0` at the set-up, D-9), `b6e8a51` (`response._integrate_kernel`, coupling `KIND`, test
probe B, D-14/D-23), `f771210` (Makefile, CI), then bench, properties, docs (see git log).
`legacy/`, `tests/fixtures/`, `legacy_port.py`, `vba_compat.py` untouched; no test deleted,
skipped or loosened (the one test edit is the probe mechanism of
`test_running_parity_is_continuous_across_phase_boundaries`, assertions unchanged, decision B).
- Environment: numba 0.68.0, llvmlite 0.50.0, hypothesis 6.170.5 (`uv pip install --python
  .venv/bin/python -e ".[dev]"`); numpy 2.5.4, Python 3.13.16.
- Kernels: `structure.step_scalars(x, v, a, f, mass, k, c, fric_acc, gap, ratio2, dt)` (the old
  `step` body; `step` is the unpacking wrapper), `moc.step` (body unchanged),
  `response._integrate_kernel` (the old `_integrate` loop on a flat float64 unbalance array +
  int64 sample offsets, `SdofParams` as six floats, coupling as `KIND` + arrays + scalars;
  `float()` casts keep Python-float state in `NUMBA_DISABLE_JIT=1` mode). `_integrate` is the
  Python orchestrator. `pressure.py` not compiled (milliseconds). Kernel compile (fresh cache,
  first call of the Example lumped case) about 1.0-1.4 s in this container; `cache=True` makes
  later processes load it.
- Error semantics (decision A): `rhoC = 0` → `FloatingPointError` at the `peak_response_jc`
  set-up (after the fallback decision; a short pipe with `rhoC = 0` still takes the lumped path
  as in VBA); fluid overflow → nan/inf propagate, `FloatingPointError` at the end of the run
  (D-23). The `np.errstate` block around the JC loop is gone (no effect in compiled code).
  DEVIATIONS D-9, D-14, D-23 reworded.
- **Step 3, differential tolerance: measured max relative difference Numba vs `legacy_port` = 0.**
  Scratch script over the lumped sweep (50 cases × {type 0, history type} = 100), the JC sweep
  (50 × 2 = 100, legacy flags), the four JC small cases × types 0-3 (16) and the two Example
  cases (types 0-3): **216/216 comparisons bitwise**; Example vs Excel 2.8e-14 (lumped) and
  2.6e-15 (JC) as before. rtol 1e-12 unchanged. Reason: none of the three kernels contains `**`
  (D-15 does not arise), LLVM does not form FMAs without fastmath, `x / 2` → `x * 0.5` is exact.
- **Step 4, golden under Numba** (`pytest -m "slow or jc_slow" --durations=0`, the three
  literal-port JC cases deselected per the owner's amendment): **153 passed in 5 min 33 s**. The
  three full JC cases through `peak_response_jc` (legacy flags) vs Excel:

  | row | f (Hz) | N | time (s), Numba | time (s), pure Python (293e507) | max rel err | per output (static-eq / x / v / a / F) |
  |---|---|---|---|---|---|---|
  | 96 | 3 | 666 | 1.19 (incl. compile) | 969 | 8.6e-13 | 7.5e-13 / 7.5e-13 / 8.6e-13 / 2.0e-13 / 0 |
  | 97 | 7.5 | 592 | 0.88 | 856 | 2.1e-14 | 2.1e-14 / 2.1e-14 / 1.8e-14 / 1.5e-14 / 0 |
  | 98 | 22 | 546 | 0.93 | 800 | 8.4e-15 | 8.4e-15 / 8.4e-15 / 2.7e-15 / 6.5e-15 / 0 |

  Errors identical to the recorded pure-Python values, as the bitwise sweep predicts. The rest of
  the 5.5 min is the legacy pure-Python side of the lumped golden and differential cases (75
  `legacy_port` golden runs 155 s, 75 differential pairs 173 s); the 75 `peak_response` runs
  under Numba are ~0.2 s each, almost all of it the Python `loads.unbalance_force` generator.
- Suites: fast suite 738 passed under Numba (26 s) and under `NUMBA_DISABLE_JIT=1` (34 s); `-m
  slow` under Numba 150 passed before each `src/` commit; `-m slow` under `NUMBA_DISABLE_JIT=1` once at the end: **150 passed** in 11 min 32 s (this container; the pure-Python kernel reads the flat unbalance array per sub-step, so the refactored lumped cases are ~1.3 s each instead of 0.7 s in Stage 4, see the bench row).
- Properties (`tests/test_properties.py`, hypothesis, derandomized, 30 examples each, 1-2 s in
  both modes): huge gap ≡ gap 0 with ratio 1 bitwise (both solvers, all output types);
  power-of-two load scaling bitwise over the common samples and the summary when the phase-3
  lengths agree; arbitrary scaling linear over the forced phase at 1e-9; maxima finite and ≥ 0,
  histories finite, gaps engaged in ~65 % of examples; JC with `fluidArea = 0` ≡ lumped within
  1e-12 (summary, history, `free_decay_samples`), MoC path in ~85 % of examples. Two model facts
  the properties surfaced and record as events rather than failures: (1) when the transit delay
  is below half a sub-step (`CLng(unb · stepQTY) = 0`, `kOverlap = 0`) `forceA ≡ forceB` and the
  response is identically zero (quantised delay, VBA behaviour); (2) the free-decay length is
  amplitude-dependent through the absolute D-21 threshold `x · xZero > 0.01`, so the summary
  maxima of a scaled load are only bitwise-scaled when both runs integrate the same number of
  phase-3 samples (14 % of examples differ).
- Bench (`tools/bench.py --profile --skip-full-python`, three modes, `docs/bench/b9597a3.json`,
  README "Stage 5 runs" section). The container was restarted mid-stage (a first full run was
  lost in the python-mode full JC case; its literal and Numba medians, at 2.10 GHz, are quoted
  in brackets below), and the new container is a slower Intel Xeon @ 2.80 GHz: every pure-Python
  case runs at ~0.55x of `b5fc5c7`, so only the in-session ratios are comparable. Digests: all
  eight refactored/literal pairs equal in both modes, every case `same` as `b5fc5c7`.

  | implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | (d) pressure | jc r96 full | jc r97 full | jc r98 full |
  |---|---|---|---|---|---|---|---|
  | literal | 3.839 s [1.00] (2.20) | 3.877 s [1.01] | 178.4 s [46.5] (100.0) | 11.5 ms | - | - | - |
  | refactored, pure Python | 1.332 s [0.35] (0.73) | 1.237 s [0.32] | 99.1 s [25.8] (51.8) | 8.3 ms | - (skipped; ~15 min each) | - | - |
  | Numba, steady state | 0.309 s [0.081] (0.200) | 0.344 s [0.090] | **0.179 s [0.047]** (0.083) | 8.5 ms | 2.13 s [0.56] (1.23) | 2.08 s (1.07) | 1.94 s (0.80) |

  Speed-ups vs the literal port: lumped 12x (3.8x vs the pure-Python refactor), truncated JC
  **1000x** (550x vs the refactor); MoC cell-updates/s 0.30 M → 0.54 M → **300 M**. Full JC golden
  cases ~2 s each (969 / 856 / 800 s in pure Python at 293e507), max rel err vs Excel 8.6e-13 /
  2.1e-14 / 8.4e-15 (unchanged). Compile: 3.36 s for `_integrate_kernel` + callees in a fresh
  `NUMBA_CACHE_DIR` (1.25 s on the 2.10 GHz container); first calls per case 0.17-2.2 s (cache
  warm in the process). Peak RSS of an `outputType = 1` run on the full history under Numba:
  lumped r20 210 MB, JC r96 191 MB (includes the compiler's footprint). Profile (python mode):
  `moc.step` is 99 % of (g); in Numba mode the lumped case is ~75 % `loads.unbalance_force`
  (Python generator), see Next action. A full run including the pure-Python full JC cases is
  appended to the README if it completes (see the end of this section).
- Port review (`port-reviewer` on `git diff b5fc5c7`, diff + VBA only, ran concurrently with the
  first part of the bench): **no correctness findings**. It checked `_integrate_kernel`
  operation-for-operation against the Stage 4 loop (coupling before the step with the previous
  `a`, `d_f + f` order, the `n + off` parity in all three phases incl. the phase-3 `+ 1`, the
  trackers, `_record`, the `tot_ind <= out_max * 2` guard, `x_zero = 0.0` vs the old int `0`),
  `step_scalars` as the old `step` body verbatim, `moc.step` decorator-only, the flattening
  (truncated last delay sample kept; D-7/D-8 still raised, now inside `list(forces)`), per-file
  `def test_` counts identical to the baseline, no fixture / legacy / frozen-module change, the
  D-9/D-14/D-23 wording, and ran its own short bitwise check (random JC case with the legacy
  flags and a lumped case, output types 0-3, two gap/ratio settings, a 2-D history) in both
  modes: all bitwise. Three non-correctness notes, applied: (1) the decision-A sentence in the
  plan above now says the Python-mode `FloatingPointError` came from the Stage 4 `errstate`
  block; (2) D-14/D-23 now say a fluid overflow *normally* reaches the structure state and raises
  at the end (an overflow at a far node in a run that ends before it reaches the pivots would
  return finite values silently, where Stage 4 raised at the first overflowing op; non-physical
  inputs only); (3) a bare `pytest` after editing `moc.py` can test a stale compiled
  `_integrate_kernel` (Numba's documented cache limitation): `make test-both` wipes the cache,
  README and architecture.md say so; a CLAUDE.md line is for the owner to add.

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

## Stage 4.4 — scope and plan (recorded 2026-10-22 before touching `src/`)
Owner's instruction: hygiene, no behaviour changes. (1) dead code in the Stage 4 modules; (2)
numpy-style docstrings with units and DEVIATIONS ids; (3) `docs/architecture.md` as built with a
data-flow paragraph per path; (4) `README.md`; (5) DEVIATIONS sorted, pinning tests checked,
legacy-only rows marked; (6) ruff with SIM and C4. Gates before each commit: fast suite, `-m slow`,
differential bitwise; `port-reviewer` on the final diff; next action Stage 5.
Plan as executed: one commit per item in the order 6+1 (lint rules and the one duplication), 2,
3, 4, 5, then bench, review, NOTES.

## Stage 4.4 — done (2026-10-22)
- Dead-code census (every public and private name of `structure`, `loads`, `coupling`, `moc`,
  `response`, `pressure` grepped over src, tests, tools): **nothing uncalled**.
  `structure.restoring_force`, `JunctionCoupling.column()` and the `pressure.get_pressure_response`
  alias are used only by the suite or the bench but are part of the fixed interfaces (the alias was
  an owner amendment in 4.3) and stay. No duplicated phase exists in the new modules; the one
  duplication, the per-sample history-write switch repeated in the forced and free-decay phases
  of `response._integrate`, is now `_record` (called once per sample, so no bench cost).
- Lint: `pyproject.toml` selects SIM and C4; `legacy_port.py` and `vba_compat.py` are exempt
  (per-file ignores). Findings fixed: SIM300 in `structure.py` (`0 > excess` → `excess < 0`,
  identical for every double incl. NaN), SIM300 in `test_quirks.py`, 17 C408 `dict()` literals in
  tests and `tools/bench.py`. `ruff check . && ruff format --check .` clean.
- Docstrings: numpy-style on every public function and dataclass of the six modules (43
  docstrings replaced or added by an AST-positioned script; the code AST with docstrings stripped
  is identical before and after). Units on every physical argument and return (m, s, N, kg/m,
  Pa, Pa·s/m, m³/h, mm², bar, …); each preserved quirk names its DEVIATIONS id.
- `docs/architecture.md`: title "as built", `response.py` row names `_integrate` / `_record` /
  `_decay_test`, new "Data flow for one sub-step" (lumped, JC, and a line for pressure), private
  helpers listed as non-interfaces, Stage 4.4 exactness note, lint policy section.
- `README.md`: package, install, the three entry points with units, the Example-sheet lumped
  worked example (Python vs Excel: 2.5e-14 / 2.5e-14 / 2.8e-14 / 2.5e-14 / 0), the fast / slow /
  jc_slow suites, `tools/bench.py`, pointers to DEVIATIONS.md, docs/port_review.md,
  docs/architecture.md, NOTES.md.
- DEVIATIONS.md: already sorted (D-1 .. D-23); every pinning-test reference resolves to a
  collected test (checked by script against `pytest --collect-only` over all markers, 0 missing).
  Rows whose VBA behaviour is now reachable only through `legacy_port.py` are marked in the
  Python-location column: D-3, D-5, D-12 (lumped garbage array), D-14 (mid-run raise of the
  lumped numpy state) and D-16. D-17 / D-19 stay reachable through the legacy flags.
- Gates: fast suite 732 passed and `-m slow` 150 passed before each `src/` commit; the
  differential suite (part of both) stayed bitwise.
- Bench (`tools/bench.py`, this container): `docs/bench/3912479.json`, README row (Intel Xeon @ 2.10 GHz, pure Python; a port-review agent was reading files concurrently, so timings are indicative only). Every case's result digest reads `same` and the four refactored/literal digest pairs are equal (exit 0). Medians: (a) lumped r20 2.055 s, (b) 2.131 s, (e) `peak_response` r20 0.740 s [0.36 of (a)], (f) 0.679 s [0.33], (c) legacy JC n2000 98.3 s, (g) `peak_response_jc` 51.1 s [1.05 M cells/s], (d) pressure 6.20 ms, (h) 4.55 ms. Within noise of 6fa4595 (0.90x-1.18x vs prev), as expected for a no-behaviour-change session.
- Port review (`port-reviewer` on the Stage 4.4 diff, diff + VBA only): **no correctness findings**. It verified the `excess < 0` rewrite against VBA lines 11-17 for every double incl. NaN and signed zero, `_record` against the base version and the VBA guards (450, 597-598), that no test, fixture or frozen module changed (per-file `def test_` counts and skip/xfail/tolerance marker counts identical), that every `dict()` literal conversion kept key order (the seeded sweeps are unchanged), that the README example reproduces digit for digit, and the VBA line references and D-ids of the new docstrings. One documentation note: the `effective_displacement` Notes had the VBA line labels of `max`/`minUnsigned`/`sign` swapped; fixed in the follow-up commit (`max` 11-17, `minUnsigned` 19-33, `sign` 51-59).

## Stage 4.3 — scope and plan (recorded 2026-10-21 before touching `src/`)
Owner's instruction: `pressure.py` as a standalone driver against the architecture row; differential
against `legacy_port.get_pressure_response` on the Example-sheet case (Excel at 1e-12) and a seeded
sweep covering port_review §4 item 1; the two half-loops' clamp asymmetry (0.9 vs 0.9·rhoC, D-6)
stays literal. Amendments at plan approval ("go", 2026-10-21): (1) the public function is
`pressure_response(...)` to match `response.py`; `get_pressure_response` stays as a thin alias so
legacy-signature callers and the bench case (d) keep working; the architecture row is updated;
(2) sweep ranges as proposed (below); (3) the VBA `min`/`max` tie semantics (`If a < b Then a Else
b`: ties and NaN return the second argument) live in one place that survives the Stage 6 removal
of `legacy_port.py`: a new `src/surge_sdof/_vba_semantics.py` (`vba_min`, `vba_max`), not in
`pressure.py`; `docs/architecture.md` notes that `vba_compat.py` is frozen and `_vba_semantics.py`
is the live home for VBA tie/NaN semantics. (The plan text itself was lost with a worker restart;
this section is its reconstruction from the owner's amendments, the Stage 4.2 pattern and the
Next action recorded below.)

Plan (fast suite before each commit, `-m slow` before the `src/` commit):
1. `_vba_semantics.py`: `vba_min`, `vba_max` (literal `legacy_port.min/max`). Tests: ties and NaN
   return the second argument, `-0.0`/`0.0` tie, equality with `lp.min/max` on a seeded sweep.
2. `pressure.py`: set-up once per run (`setup` → `PressureSetup`: `outMax`, `pipeSegQTY`
   (`grid_size`, VBA 207, D-22 truncation), `factor`, `rhoC`, `velocityInitial`, `valveLoss`,
   `valveDPInitial`, `pipeLoss`; `initial_column` → four contiguous arrays `p_a, v_a, p_b, v_b`
   of length `N + 1`, VBA 222-227, and `velAtPump`), `valve_closure` (the column-major pattern
   walk with the `jB > U2` clamp and linear interpolation, VBA 244-265, on the 0-based 2-D pattern
   from `loads.as_history_2d`), `valve_boundary` (VBA 267-273, the fully-closed branch at
   `closure >= 0.999999999`), `pump_boundary` (VBA 287-288), `half_step_a_from_b` (VBA 275-285,
   clamp `0.9`) and `half_step_b_from_a` (VBA 290-300, clamp `0.9 * rhoC`): scalar loop bodies
   over the arrays, `sysMat` as two locals, VBA operation order; `pressure_response` drives them
   under `np.errstate(raise)` (the arrays are numpy, as in the legacy, so `rhoC = 0` and overflow
   raise as before) and returns the 0-based `resultArray(0 To outMax)` unchanged.
   `get_pressure_response(...)` forwards to it.
3. Differential tests (`tests/test_differential.py`, new section): set-up constants vs the legacy
   locals (settrace probe at the main loop), `pressure_response` vs legacy on the Example case
   (and vs Excel at 1e-12), on a 50-case seeded sweep (`random.Random(20261019)`, rtol 1e-12,
   bitwise expected and recorded), 1-D ≡ column, alias identity.
   Sweep ranges: closureTime U(0.2, 3) s with 20-300 result steps (`timeStep = closureTime /
   steps`); celerity U(900, 1500); density {850, 1000, 1100}; pressureDropFromPump 0 (1 in 5)
   or U(0.01, 2) bar; flowRate 10^U(0.3, 3.3) m³/h (low flows make the `0.9` clamp saturate);
   pipe ID U(50, 600) mm (`pipeArea = pi·ID²/4`); valveCv U(100, 5000); lengthToPump U(5, 2000) m
   (long pipes trigger the `outMax` truncation); pumpRampPressure 0 (3 in 10) or U(0.5, 5) bar;
   valve patterns of 3-40 samples, 1 column (1 in 2) or 2-3 columns (column-major), shapes
   linear / smoothstep / early-close-then-plateau / stepped, end value exactly 1.0 (1 in 2, the
   fully-closed branch) or U(0.3, 0.99). Asserted coverage: fully-closed steps, `outMax`
   truncation, zero and non-zero pump ramp, zero pipe loss, 1-D and 2-D patterns, saturation of
   the `0.9` clamp (counted through the probe); the `0.9·rhoC` clamp is expected never to
   saturate (port_review §1.4) and the count is recorded, not asserted.
4. Bench: case (h) `response_pressure_example` (`pressure.pressure_response`, digest must equal
   (d)); README column added, earlier rows get `-`. `docs/architecture.md` (pressure and
   `_vba_semantics` rows, interface, exactness note), DEVIATIONS D-6/D-22 Python locations.
5. `port-reviewer` on the final diff; NOTES done section; next action.

## Stage 4.3 — done (2026-10-21)
Commits `bbc8f6a` (scope), `5df78fd` (`pressure.py`, `_vba_semantics.py`, tests), `6fa4595` (docs, bench
case (h)). `legacy_port.py`, `vba_compat.py`, `tests/fixtures/`, `legacy/` untouched.
- `pressure.pressure_response(...)`: the valve/pump MoC driver from the Stage 4 layout; `get_pressure_response`
  is a thin legacy-signature alias (bench case (d) and any legacy caller keep working). D-6 clamp asymmetry
  and D-22 truncation kept literal. `_vba_semantics.vba_min/vba_max` hold the VBA tie rule (second argument on
  ties and NaN) in one place that survives the Stage 6 removal of `legacy_port.py`.
- Differential results (`tests/test_differential.py`, pressure section, 50 seeded cases + Example): set-up
  constants identical to the legacy locals in all 50 cases; `pressure_response` **bitwise identical** to
  `legacy_port.get_pressure_response` in 49 of 50 sweep cases and on the Example case (which also matches
  Excel at 1e-12); the 50th case (`p24_c2_smooth_closed`) overflows inside the legacy MoC (`FloatingPointError`
  under `np.errstate(raise)`, second half-loop) and the refactor raises the same exception, asserted as such.
  Sweep coverage: 20 cases take the fully-closed valve branch, 10 hit the `outMax` pipe truncation, 12 have
  zero pump ramp, 9 zero pipe loss, patterns with 1-3 columns. Lumped golden gate (`-m slow`) run before the
  `src/` commit: 75 pass. Fast suite 732 passed (≈ 33 s).
- Finding (recorded in DEVIATIONS D-6): **both** friction clamps saturate in the sweep. The `0.9` clamp bites
  at low flow (12 cases, 8141 cell updates). The `0.9·rhoC` clamp, which port_review §1.4 expected to be
  effectively absent, bites in 2 cases (1095 cell updates): the loss term is `|v|·pipeLoss / (rhoC·velInitLocal²)`
  and `velInitLocal = (1 + 2i)·pipeLoss/rhoC + velocityInitial` passes through zero along the pipe when the
  pressure drop is large relative to the flow, making the friction term singular there. A modelling quirk of
  the VBA (preserved); worth raising with the lead author alongside D-17/D-18.
- Port review (`port-reviewer`, diff `bbc8f6a..6fa4595`, diff + VBA only): **no correctness findings**; it
  independently confirmed bitwise equality on the 49 non-raising sweep cases and the Example case. Its two
  notes were applied: the `pressure.py` docstring now says the suite pins rtol 1e-12 and bitwise is the
  measured result; `tools/bench.py` now checks the paired digests in-run (`DIGEST_PAIRS`, exit 1 on mismatch).
- Bench (`tools/bench.py` on `6fa4595`, `docs/bench/6fa4595.json`, README row): every previous case's digest
  reads `same`; new case (h) `response_pressure_example` 4.70 ms vs (d) `pressure_example` 6.18 ms (0.76x, ratio
  to (a) 0.003 for both), digests of all four refactored/literal pairs identical. Run time 8 min.
- Judgement calls: the sweep's one overflowing case is kept as a "raises identically" differential rather than
  tuned away; `pressure_response` returns the plain 0-based array (no dataclass) because the legacy result was
  already 0-based and the bench/golden consumers index it directly.

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
- JC golden gate (`pytest -m jc_slow -k peak_response_jc_matches_excel_on_the_golden_curve`,
  the new solver with the legacy flags against the Excel fixture at 5e-12, three single-case
  processes in parallel on 4 cores, pure Python; the literal-port golden tests were not re-run,
  owner's decision): 3/3 pass.

  | row | f (Hz) | N | time (s) | max rel err | per output (static-eq / x / v / a / F) |
  |---|---|---|---|---|---|
  | 96 | 3 | 666 | 969 | 8.6e-13 | 7.5e-13 / 7.5e-13 / 8.6e-13 / 2.0e-13 / 0 |
  | 97 | 7.5 | 592 | 856 | 2.1e-14 | 2.1e-14 / 2.1e-14 / 1.8e-14 / 1.5e-14 / 0 |
  | 98 | 22 | 546 | 800 | 8.4e-15 | 8.4e-15 / 8.4e-15 / 2.7e-15 / 6.5e-15 / 0 |

  The errors are the literal port's to the digits shown (484b25e: 8.6e-13 / 2.1e-14 / 8.4e-15),
  as the bitwise sweep predicts. Legacy times for comparison, sequential: 1827 / 1565 / 1412 s.

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
**Stage 5b.** (1) Owner's reference bench on local hardware (the absolute row for the paper):
`.venv/bin/python tools/bench.py --profile` from the repository root on a quiet machine (about an
hour; `--skip-full-python` leaves the three full JC cases out of the pure-Python mode and brings it
to ~10 min, at the cost of that row), then commit `docs/bench/<sha>.json` and `docs/bench/README.md`.
(2) F-3, JC fidelity (full vs simplified) sweep; `coupling.py` is the only module the decision may
touch (approved-fixes note). (3) Speed, next lever: `loads.unbalance_force` is now ~75 % of a
compiled lumped run (0.55 s of 0.62 s profiled on row 20; the kernel itself is tens of ms) and the
flat-array hand-off would let a compiled walk write straight into the array; the set-up and
`pressure.py` are milliseconds and not worth compiling. (4) Optional: a `cache=True` staleness guard
in CI beyond the wipe (`make clean-cache`), and the `jc_slow` marker text in `pyproject.toml` still
says "hours each in pure Python" (true for the literal-port cases only).

Previous next action (Stage 4.4 → 5, kept for the record):
**Stage 5 (Numba).** `moc.step` and the `pressure.py` half-loops are already scalar loops over
contiguous float64 arrays with no Python objects, written for `@njit`; `structure.step` and
`response._integrate` are Python-float code that can follow. Judge `**` vs C `pow` (D-15: Numba
lowers integer-literal `**` to multiplication) against the recorded tolerances (golden 5e-12,
Example 1e-12) rather than expecting bit-identity, and record any last-bit change in
DEVIATIONS.md with a pinning test. Acceptance: the three `jc_slow` cases (5e-12), `-m slow`,
the fast suite, and `tools/bench.py` with `docs/bench/` committed. Keep `NUMBA_DISABLE_JIT=1`
runs green (CLAUDE.md). numba is permitted but not yet in `pyproject.toml`; add it as an
optional dependency when Stage 5 starts.

Previous next action (Stage 4.3 → 4.4, kept for the record): Stage 4.3 is done; Stage 4 now covers every entry point (`response.peak_response`, `response.peak_response_jc`,
`pressure.pressure_response`) with `legacy_port.py` still the frozen reference. Owner to name the next stage:
the candidates recorded so far are Stage 4.4 (owner's label for applying approved fixes; F-1/F-2 were already
applied in 4.2, so 4.4 would be whatever the owner adds, e.g. the D-6 clamp question and the `velInitLocal`
singularity found by the pressure sweep, raised with the lead author), Stage 5 (Numba: `moc.step` and the
pressure half-loops are written as scalar loops over contiguous arrays for `@njit`; `**` vs `pow`, D-15, to be
judged against the recorded tolerances; the three `jc_slow` cases are the acceptance test), Stage 5b (F-3 JC
fidelity sweep, `coupling.py` only) and Stage 6 (remove `legacy_port.py`; `tests/test_quirks.py` pins move to
the new modules). Gates unchanged: `.venv/bin/python -m pytest -q` before every commit, `-m slow` before any
`src/` commit, `tools/bench.py` at the end of every Stage 4/5 session with `docs/bench/` committed.

Previous next action (Stage 4.2, kept for the record): `moc.py` + the JC coupling +
`response.peak_response_jc` with F-1/F-2 flag-first — done, see "Stage 4.2 — done".

Previous next action (Stage 4.1, owner's instruction, 2026-10-20), kept for the record: Run `tools/bench.py` at the end of every Stage 4/5 session and commit `docs/bench/` (CLAUDE.md); compare the "result vs prev" column, which must read `same` for a behaviour-preserving commit. No document in the repo defines the Stage 4.1 scope; the only stage material beyond Stage 1 is the refactor map in `docs/port_review.md` §2 (Stage 4) and the Numba target (Stage 5), so record the 4.1 scope in this file at the start of that session before touching `src/`. Read `docs/port_review.md` §2 (refactor map, §2.5 parity hazard) and §4 (blind spots) first. Gate: `.venv/bin/python -m pytest -q` before every commit, `-m slow` (3.5 min) before any commit touching `src/`; `tests/test_quirks.py` must stay green as written (a change to a pinned quirk needs a DEVIATIONS.md row). The 3 JC cases have run once (1 h 20 min, all pass, tolerance 5e-12 measured); re-run them (`pytest -m jc_slow`, background) before any commit that touches the JC solver path, and before the Stage 5 Numba acceptance. If `GetPressureResponse` needs a golden case, add a UDF call with a committed valve pattern to the workbook and extend `tools/extract_fixtures.py`.
