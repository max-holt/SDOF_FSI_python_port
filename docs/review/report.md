# Clean-code review — close-out report (session R.12, 25 Nov 2026)

Branch `claude/solver-review-charter-oe8gtr`, 264 commits from the branch point `177c8b1`
(main) to `6fe7b50`, plus this session's three. Session R.12 changed no solver code: one
comment in `tests/test_export.py` (`7e726e0`), the docs below.

## Summary

* **Results are identical.** Every gate is green on `7e726e0`; the frozen reference
  (`tests/fixtures/`, `legacy/`, `legacy_port.py`, `vba_compat.py`) is byte-identical to the
  branch point; every change to the stored snapshot and support files is one of the expected
  kinds; a scan of all 184 code commits finds no floating-point expression change outside the
  recorded ones. Two recorded behaviour changes (D-26, D-27) change output on edge inputs only,
  and touched no stored file.
* **The code is much easier to follow.** The kernel went from 36 parameters and 212 code lines
  to 6 and 137; every core function now meets the parameter, complexity and nesting targets or
  carries a recorded exception. A fresh reader can follow one substep from the entry point to
  the state update; all four cold readers said so, and named where they stall.
* **What is left.** A fresh cold read confirmed 125 of 132 findings, almost all Readability
  and none a defect. Eleven are documentation that is wrong today (four on public entry points
  or the data contract); they are docstring-only and should be fixed first. About ten Design
  findings are boundaries the refactor itself drew (parameter objects that carry two jobs, a
  private type crossing modules, a computation fed from the export echo). They are worth one
  more session, not a blocker.
* **Speed:** _see "Speed" below_.

## What changed

Groups 0-7 of `plan.md` were made across R.3-R.11: names (`docs/nomenclature.md`), named
constants, parameter objects (`SdofParams`, `FluidColumn`, `TraceBuffers`, `KernelSettings`),
one structure substep shared by both loops (`_structure_substep`), the trace writers moved to
`trace.py`, the supporting modules split (`fixture_cases`, `sweep_grid` / `sweep_rows` /
`sweep_report`, `sweep_document`), the public interface (`PipeSpan`, `Restraint`, `Fluid`,
`Integration`, `CouplingModel`; `output_type` removed; trace schema 2, sweep schema 3),
docstrings and annotations, lint limits in `pyproject.toml`, and the approved fixes D-25
(flag validation), D-26 (`is_capped`), D-27 (`size_in`). The pressure solver was removed
(R.1b). `docs/handover.md` now opens with the current layout.

## Evidence that results are identical

| check (on `7e726e0`, after `make clean-cache`) | result |
|---|---|
| `make lint` | pass |
| `make test-both` (fast suite compiled / `NUMBA_DISABLE_JIT=1`) | 966 + 24 skipped / 964 + 26 skipped |
| snapshot test alone, compiled / pure Python | 29 / 29 passed |
| supporting-code checks (sweep rows exact, histories exact on X86_V4) | 23 passed |
| `-m slow` (75 lumped golden cases, both layers) | 150 passed (415 s) |
| golden `slow or jc_slow` incl. the 3 JC cases through the literal port | _pending_ |
| `test_differential -m jc_slow` (refactored JC vs Excel, legacy flags) | _pending_ |
| `tools/bench.py` digests | _pending_ |

**Frozen paths.** `git rev-parse` gives the same tree for `tests/fixtures`, `legacy`,
`legacy_port.py` and `vba_compat.py` at `177c8b1` and `HEAD`; no commit touches them.

**Stored files.** Five commits change `tests/review_snapshot/` or `tests/review_support/`,
all expected: `d2af940` / `d4f510d` create them; `253210a` rewrites the stored sweep CSV from a
clean tree (only `git_sha`, `t_lumped_s`, `t_jc_s` differ: run columns); `5530447` deletes
the seven pressure documents; `37d1d75` adds `sweep_histories.txt`; `9d2d2c3` (schema bump)
rewrites nine files. In it, compared leaf by leaf with keys ignored: the CSV header is renamed
and every data cell is equal; the JSON values are equal except `schema_version`, the
`output_names` entry `max_applied_force` → `max_unbalance_force`, and the `inputs` echo, now
grouped (`span`, `restraint`, …), without `output_type` and with `trace_every` and the
restraint defaults written out. No stored result value changed. The group 7 fixes (`6165f87`,
`032a3cc`) change no stored file (the stored cases do not reach their edge inputs).

**Commits that do not name a single refactoring.** 184 commits touch code under `src/` or
`tools/`. I compared, per commit, the multiset of arithmetic expressions with identifiers
blanked (so renames cancel) and read every commit where it differs (58): the review
infrastructure (R.0, R.0b, R.1b, R.7's `review_ab.py`), the pressure-solver removal, removals of
test-only wrappers, literal → named constant with the same value and literal type (`PERCENT =
100`, sweep `MM_PER_M = 1000`, cases `MM_PER_M = 1000.0`, `GRAVITY = 9.81`, …), duplicated
expressions collapsed into one copy (`effective_displacement`, `substep_friction`,
`interleaved_grid`, `solver_setup`: identical bodies), integer index arithmetic (parity
offset, sample starts), annotations (`X | None`), a printed message, and two revert pairs
(2.15: `loads.py` identical after `848adb8`; 4.9a: tree identical after `b1ce745`). Commits
whose message names several changes (e.g. `88dd1d9`, `9520d1d`, `2f1dce2`, `a212356`, `c6abb02`,
`48df391`, `78c0449`, `7c24b47`, `b79a89a`, `9d2d2c3`) contain no other arithmetic change.
One test tolerance was loosened on the branch: property 4 of `test_properties.py`, 1e-12 →
5e-12, approved by the lead author on 17 Nov (R.0b) for a counterexample at 1.27e-12 that
predates every refactoring.

## Metrics (`docs/review/metrics_after.md` has every function)

Commands of `baseline.md` plus `--ignore-noqa` (see K14 below). Before → after, ruff counts:

| function | args | cc | statements | nesting | code lines |
|---|---|---|---|---|---|
| `response._integrate_kernel` | 36 → 6 | 23 → 10 | 75 → 55 | 3 | 212 → 137 |
| `response._integrate` | 10 → 5 | 10 → 3 | 44 → 8 | 2 → 1 | 126 → 26 |
| `response.peak_response_jc` | 19 → 7 | 6 → 2 | 32 → 16 | 1 | 136 → 62 |
| `response.peak_response` | 14 → 5 | 2 → 1 | 19 → 10 | 1 → 0 | 77 → 38 |
| `response._trace_frame` → `_record_frame` | 23 → 6 | 3 → 2 | 20 → 5 | 2 → 1 | 45 → 32 |
| `moc.step` | 15 → 4 | 7 | 32 → 44 | 2 | 66 → 103 |
| `structure.step_scalars` | 11 → 6 | 9 → 4 | 29 → 19 | 2 | 47 → 36 |
| `loads._schedule` | 1 | 14 → 10 | 60 → 41 | 3 | 75 → 92 |
| `loads.unbalance_force` / `elbow_forces` | 5 | 7 | 24 | 4 | 38 / 36 → 70 / 68 |
| `trace.build` → `build_trace` | 15 → 6 | 2 → 4 | 9 → 17 | 1 → 2 | 57 → 55 |
| `export._sweep_value` | 3 | 14 → 8 | 23 → 12 | 3 → 2 | 29 → 17 |
| `viz.geometry.loop_layout` | 8 → 3 | 1 | 21 | 0 | 55 → 75 |
| `histories.canonical` / `step_noise` | 14 / 12 | 6 / 3 → 2 | 14 / 24 → 21 | 2 / 1 | 48 / 64 → 62 / 72 |

Over target, core: 10 / 2 / 2 / 2 / 9 (args / cc / statements / nesting / > 40 lines) → 1 / 0 /
1 / 2 / 7, the four the §11 exceptions; supporting: 6 / 1 / 0 / 0 / 7 → 3 / 0 / 0 / 0 / 6
(the three history generators); `tools/`: 1 / 2 / 1 / 7 / 17 → 1 / 2 / 1 / 7 / 21, all in
ungated tools or the review's harnesses except five over the 40-line mark only.

**These are indicators.** Where they improved without the code getting easier to read:
* The committed `tools/review_baseline.py` honours the targeted `noqa` comments of R.10 and so
  prints 0 for the parameters of `peak_response_jc`, the kernel's statements, the loads
  nesting and the generators' parameters: the exceptions vanish from the table (K14).
* Parameter counts fell by grouping (kernel 36 → 6, `build_trace` 15 → 6). The groups mostly
  help, but two now carry two jobs: `TraceRequest` holds the kernel's elbow-force generator
  and `build_trace`'s inputs (T3), and `build_trace` takes response's private `_KernelResult`
  for two integers (R2).
* `loads._schedule` met the complexity target by extracting `_next_position`, yet the transit
  phase still writes that rule out inline (L3).
* The other way: code lines grew where names got longer and `ruff format` wraps (`unbalance_force`
  36 → 68 lines at an unchanged 24 statements; `moc.step` gained its derivation comments). That
  growth reads better, not worse.

## Speed

_pending_

## Remaining findings and recommendations

Full list with verdicts: `docs/review/findings_r12.md`. 132 checked, 125 confirmed, 4 refuted,
1 split, 2 unclear (session labels in docstrings: no style rule says, owner to decide).

**Original findings (`findings.md`).** Of the 93 accepted, 74 are closed in the code, 4 closed
by ruling (C-04, C-05, C-13, the 4.4 half of C-03), 11 open by ruling (C-07; S-23; the nine
ungated-tool findings) and S-31 left out of the bump (ruling 81). **Closed on paper only:**
C-36 says done but the kernel's `forced_samples` (kept "until group 4") is still there (R6);
C-23's typing of `elbow_force_samples` "with 6.7" is still `object` (T3); C-40 / S-50 say every
docstring has its VBA names in Notes, but Parameters / Returns still define quantities by VBA
name and four module docstrings are wrong (R7, C1, T8, M5); C-19's "stop naming callers" is
not done (moc.py:645, R16); C-45's divisor / denominator pair survives as `vav_denominator`
(M3); S-47 says done though its bump half was left out by ruling 81; C-11 is reduced (about
60 → 25 repeated lines, R3), not removed.

**Introduced by the refactor.** R1 (the trace walk fed from the export echo), R2/T4 (trace
depends on response's private result), T3 (`TraceRequest` two jobs), T2 (the grid in three
forms), C1 (`coupling.py` a factory under a docstring about other modules), S1 (structure
typed by response's input classes), M1 (a display profile in the solver module), M3 (one name
for a choice, an int and a function), R5/T1 (the record window in four places), K14.

| recommendation | findings |
|---|---|
| **fix now** (docstring / comment / tool flag, R0; gates only) | R7, R8, R9, T8, R16, C1 docstring, S1/S2 docstring, M3 (moc.py:28), T3 docstring and annotation, E4, H5, R24, S6, W11 (data_format.md:205), K14 |
| **defer to Stage 6** (structure; gates and A/B) | R1+R3, R2/T4, T1/R5, T2, T3 split, S1 move, M1, C1 move, G1, L1-L3, R4, R6, K1, K2, W1, E3 and the confirmed Readability renames |
| **leave** | refuted (L4, T11, T12, W6); Nits (ruling 8); ungated tools (K3, K4, W2); next-schema-bump keys (E9, E10, E15, W11 notes); G3 (approved interface); session labels (owner) |

## Deviations from `docs/style.md` to record in §11

* `response._record_frame`: called per recorded substep with the buffers and the column, a
  §4 departure kept by ruling 56 (R19).
* `loads.unbalance_force` / `elbow_forces`: keep the line but restate its reason; the fourth
  level is the phase dispatch, not the two walks (L1). Same for `histories.canonical`, whose
  reason fits `step_sine` / `step_noise` only (H4).
* `_integrate_kernel`: the line says 56 statements; ruff counts 55 (54 once R6 is made).
* §3's "a function that misses a target carries a one-line reason": none of the eleven
  functions over 40 code lines carries one (`moc.step` 103, `loads._schedule` 92, the walks,
  `peak_response_jc`, `_kernel_inputs`, `build_trace`, `loop_layout`, three generators).
* `tools/review_ab.py` and `review_baseline.py` are exempt from the limits in `pyproject.toml`
  as "tools no test runs", though they are the review's gates; `review_ab.main` nests 4.
