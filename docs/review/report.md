# Clean-code review — close-out report (session R.12, 25 Nov 2026)

Branch `claude/solver-review-charter-oe8gtr`: 264 commits from the branch point `177c8b1` to
`6fe7b50`, then this session's. R.12 changed no code: one test comment (`7e726e0`) and docs.

## Summary
* **Results are identical.** All gates green on `7e726e0`, the three JC golden cases included;
  the frozen reference byte-identical to the branch point; every stored-file change of an
  expected kind; no floating-point expression change in 184 code commits outside the recorded
  ones. D-26 / D-27 change output on edge inputs only and touched no stored file.
* **The code is much easier to follow.** Kernel: 36 parameters and 212 code lines → 6 and
  137; every core function meets the targets or has a recorded exception. Can an engineer
  follow one substep from the entry point to the state update without the VBA? Three cold
  readers said "mostly yes", one "partly"; they stall at stale docstrings, the parity index
  and the grid's VBA vocabulary.
* **What is left.** 132 findings checked, 125 confirmed, none a defect. Twelve are
  documentation wrong today (including the public `peak_response_jc` docstring and the data
  contract); about ten Design findings are boundaries the refactor itself drew.
* **Speed.** Compiled paths 3-22 % faster than at the branch point (against the literal port,
  one host); the pure-Python lumped path is about 1.8x slower.

## What changed
Plan groups 0-7 (R.3-R.11): names (`docs/nomenclature.md`) and named constants; parameter
objects (`SdofParams`, `FluidColumn`, `TraceBuffers`, `KernelSettings`) and one structure
substep for both loops; the trace writers in `trace.py`; the tools split (`fixture_cases`,
`sweep_grid` / `sweep_rows` / `sweep_report`, `sweep_document`); the public interface
(`PipeSpan`, `Restraint`, `Fluid`, `Integration`, `CouplingModel`; `output_type` gone; trace
schema 2, sweep schema 3); docstrings, annotations, lint limits; the approved fixes D-25 (flag
validation), D-26 (`is_capped`), D-27 (`size_in`). The pressure solver went in R.1b; the
handover now opens with the current layout.

## Evidence that results are identical
| check (`7e726e0`, after `make clean-cache`) | result |
|---|---|
| `make lint`; `make test-both` (compiled / pure Python) | pass; 966 + 24 skipped / 964 + 26 skipped |
| snapshot test alone, compiled / pure Python; supporting-code checks | 29 / 29 passed; 23 passed (exact) |
| `-m slow`; golden `slow or jc_slow` (75 lumped; 3 JC cases through the literal port) | 150 passed; 75 + 3 passed (JC 27, 24, 22 min) |
| `test_differential -m jc_slow` (refactored JC vs Excel, legacy flags) | 3 passed |
| `tools/bench.py --skip-full-python` (row `da0c855`) | every digest equal to the literal port |

**Frozen paths:** same git tree at `177c8b1` and `HEAD`; no commit touches them.

**Stored files.** Six commits touch `tests/review_snapshot/` or `tests/review_support/`:
`d2af940` and `d4f510d` create them; `253210a` rewrites the stored CSV from a clean tree (only
the run columns and `git_sha` differ); `5530447` deletes the seven pressure documents;
`37d1d75` adds `sweep_histories.txt`; `9d2d2c3` (the schema bump) rewrites nine files.
Compared leaf by leaf with keys ignored, its CSV differs in the header only, and its JSON in
`schema_version`, one `output_names` entry (`max_applied_force` → `max_unbalance_force`) and
the `inputs` echo (now grouped, no `output_type`, `trace_every` and the restraint defaults
written out). No stored result value changed.

**Commits that do not name a single refactoring.** For each of the 184 commits touching
`src/` or `tools/` I compared the multiset of arithmetic expressions with identifiers blanked,
so renames cancel out, and read all 58 where it differs. They hold only the review harnesses,
the pressure-solver removal, removed test-only wrappers, literals replaced by constants of the
same value and literal type (`PERCENT = 100`, sweep `MM_PER_M = 1000`, cases `MM_PER_M =
1000.0`), duplicates collapsed into one identical body (`effective_displacement`,
`substep_friction`, `interleaved_grid`, `solver_setup`), integer index arithmetic, `X | None`
annotations, one printed message, and two revert pairs that restore the tree (2.15, 4.9a).
The multi-change commits (`88dd1d9`, `9520d1d`, `2f1dce2`, `a212356`, `c6abb02`, `48df391`,
`78c0449`, `7c24b47`, `b79a89a`, `9d2d2c3`) contain nothing more. One tolerance was loosened
on the branch: property 4 of `test_properties.py`, from 1e-12 to 5e-12. The lead author
approved it in R.0b for a counterexample at 1.27e-12 that predates every refactoring.

## Metrics (every function: `metrics_after.md`)
Commands of `baseline.md` plus `--ignore-noqa` (K14). Ruff counts, before → after:

| function | args | cc | stmts | nest | code lines |
|---|---|---|---|---|---|
| `response._integrate_kernel` | 36 → 6 | 23 → 10 | 75 → 55 | 3 | 212 → 137 |
| `response._integrate` | 10 → 5 | 10 → 3 | 44 → 8 | 2 → 1 | 126 → 26 |
| `response.peak_response_jc` / `peak_response` | 19 / 14 → 7 / 5 | 6 / 2 → 2 / 1 | 32 / 19 → 16 / 10 | 1 / 1 → 1 / 0 | 136 / 77 → 62 / 38 |
| `moc.step` | 15 → 4 | 7 | 32 → 44 | 2 | 66 → 103 |
| `structure.step_scalars` | 11 → 6 | 9 → 4 | 29 → 19 | 2 | 47 → 36 |
| `loads._schedule` | 1 | 14 → 10 | 60 → 41 | 3 | 75 → 92 |
| `loads.unbalance_force` / `elbow_forces` | 5 | 7 | 24 | 4 | 38 / 36 → 70 / 68 |
| `viz.geometry.loop_layout` | 8 → 3 | 1 | 21 | 0 | 55 → 75 |

Over target (args / cc / statements / nesting / > 40 lines): core 10/2/2/2/9 → 1/0/1/2/7;
supporting 6/1/0/0/7 → 3/0/0/0/6; `tools/` 1/2/1/7/17 → 1/2/1/7/21, all in ungated tools or
the review harnesses except five functions over the line mark only.

**These numbers are indicators.** They improved without the code getting easier where the
committed `review_baseline.py` honours R.10's targeted `noqa` and prints 0 in exactly the §11
exception columns (K14); where grouping cut parameter counts into objects with two jobs
(`TraceRequest`, T3; `build_trace` taking a private result for two integers, R2); and where
`_schedule` met its complexity target by extracting `_next_position` while the transit phase
still writes the rule out inline (L3). The other way, line counts grew where longer names wrap
(`unbalance_force` 36 → 68 lines at 24 statements throughout); that reads better, not worse.

## Speed
A/B per session (`review_ab.py` or its predecessor; rulings 43, 50), new / old:

| session | R.5 | R.6 | R.7 | R.8 | R.9 | R.10 | R.11 |
|---|---|---|---|---|---|---|---|
| range | 0.980-1.016 | 0.973-1.027 | lumped 0.885 / 0.935, rest 0.972-1.021 | 0.958-1.021 | 0.926-1.032 | 0.984-1.027 | 0.970-1.015 |

Outliers (R.9 1.054, R.10 1.050) did not repeat; the one-walk schedule (R.4, +20 %) and design
A's substep (R.6, 1.1-2.0x) were reverted. Before and after on this host: `tools/bench.py
--skip-full-python` at `177c8b1` (worktree; `r12_bench_branch_point_177c8b1.json`) and at
`da0c855`, back to back; each time over the unchanged literal lumped r20 of the same run:

| case | 177c8b1 | da0c855 | after / before |
|---|---|---|---|
| Numba lumped r20 / r80 | 0.1026 / 0.0982 | 0.0798 / 0.0837 | 0.78 / 0.85 |
| Numba JC r96 n2000 | 0.0441 | 0.0410 | 0.93 |
| Numba JC r96 / r97 / r98 full | 0.592 / 0.503 / 0.471 | 0.537 / 0.488 / 0.455 | 0.91 / 0.97 / 0.97 |
| pure Python lumped r20 / r80; JC r96 n2000 | 0.340 / 0.350; 29.79 | 0.629 / 0.619; 27.13 | 1.85 / 1.77; 0.91 |

Compiled: 3-22 % faster. Pure Python (the test mode) is about 1.8x slower on the lumped cases;
the cause was not investigated. The pure-Python fast suite took 207 s (156-246 s across the
sessions), inside ruling 54's limit.

## Remaining findings and recommendations
The full list with verdicts is in `findings_r12.md`. Refuted: L4, T11, T12 and W6. Unclear:
the session labels in docstrings, which no style rule covers; the owner decides.

**Original findings (`findings.md`).** Of the 93 accepted, 74 are closed in code, 4 by
ruling (C-04, C-05, C-13, the 4.4 half of C-03), 11 open by ruling (C-07, S-23, nine
ungated-tool findings); S-31 is out of the bump. **Closed on paper only:** C-36 (the kernel's
`forced_samples` is still there, R6); C-23 (`elbow_force_samples` still typed `object`, T3);
C-40 / S-50 (VBA names still the primary definitions, four module docstrings wrong: R7, C1,
T8, M5); C-19 (callers still named, moc.py:645); C-45 (`vav_denominator` survives, M3); S-47
(marked done, its bump half left out by ruling 81); C-11 (repetition down from ~60 lines to
25, R3, not removed).

**Introduced by the refactor:** R1 (trace walk fed from the export echo), R2/T4 (trace
imports a private response type), T3 (`TraceRequest` two jobs), T2 (the grid in three forms),
C1 (`coupling.py` a factory under a docstring about other modules), S1 (structure typed by
response's input classes), M1 (display profile in moc), M3 (one name for a choice, an int and
a function), R5/T1 (the record window in four places), K14 (metrics read 0 for exceptions).

| recommendation | findings |
|---|---|
| **fix now** (docstring, comment, tool flag; R0, gates only) | R7, R8, R9, T8, R16, R24, C1 and S1/S2 docstrings, S6, M3 (moc.py:28), T3 docstring and annotation, E4, H5, data_format.md:205, K14 |
| **defer to Stage 6** (structural; gates and an A/B) | R1+R3, R2/T4, T1/R5, T2, the T3 split, the S1 / M1 / C1 moves, G1, L1-L3, R4, R6, K1, K2, W1, E3, the confirmed renames |
| **leave** | refuted; Nits (ruling 8); ungated tools (K3, K4, W2); keys for a later schema bump (E9, E10, E15, `regen.note`); G3 (approved interface); session labels (owner) |

## Deviations from `docs/style.md` to record in §11
* `response._record_frame`: called per recorded substep with arrays (§4; ruling 56; R19).
* Restate two reasons: the loads walks' nesting of 4 comes from the phase dispatch, not
  the two walks (L1); `histories.canonical`'s reason fits only `step_sine` / `step_noise` (H4).
* `_integrate_kernel`: §11 says 56 statements, ruff counts 55.
* §3's one-line reason is missing on all eleven functions over 40 code lines (`moc.step`,
  `_schedule`, the two walks, `peak_response_jc`, `_kernel_inputs`, `build_trace`,
  `loop_layout`, three generators).
* `review_ab.py` / `review_baseline.py` are exempt as "tools no test runs" but are the gates.
