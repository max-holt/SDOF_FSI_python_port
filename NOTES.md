# NOTES — session handoff

Current stage, open issues and the next action. The session-by-session record that used to
live here (scope, plan and "done" sections of every stage) is in the git history of this file
up to the `v0.4-handover` tag; `docs/handover.md` is the orientation for a new reader.

## Current stage

Session R.9 (public API, plan group 6 with 3.7 and 3.10, 2026-11-25) **stopped at a green
commit** (ruling 75: the context ran long), after plan 6.3b. Rulings 67-84 in the charter;
`docs/review/public_interface.md` approved (option A with the answers of rulings 76-84) and its
§6 lists what a caller outside the repository changes so far.

Done, one change per commit, each gated (lint and the compiled fast suite before the commit,
the pure-Python suite before the next; snapshot and support exact in both modes):
`84ac732` rulings 67-75; `5d86458` `review_ab.py` sweep case `sweep_noise` (ruling 70);
`3ce6f9c` the proposal; `d6b2823` rulings 76-84 and the style / nomenclature entries;
`b79a89a` 6.1 `CouplingModel`, validated on construction (DEVIATIONS D-25, pinning test
`test_d25_unknown_flags_raise_on_every_path`); `edc7231` the input types; `8fb227b` 3.7;
`1a73b49` 6.2a, the kernel records the three histories (ruling 83: its own commit);
`48df391` 3.10 and 6.2b, the new entry points, callers moved through
`tools/fixture_cases.solver_inputs` / `history_of`, `output_type` and the old signatures
removed; 6.3a `PeakResponse` renames; 6.3b `Trace` renames and `ColumnTrace`.

A/B against the commit before (`tools/review_ab.py`, B/A over the eleven cases): 6.1
0.94-1.04 (3 rounds, host busy), 3.7 0.96-1.03, 6.2a 0.95-1.04 (5 rounds), 6.2b 0.97-1.04
(5 rounds), 6.3b 0.98-1.04 (three traced / lumped cases). Fast suite 955 + 24 compiled, 953 + 26
pure Python (six D-25 cases added); pure Python about 200 s per run (170 s at R.8's start: the
D-25 cases and a busier host, below a quarter longer).

Test assertions dropped (ruling 23: they asserted a property of the removed `output_type`
field itself): `res.output_type == output_type` in `test_differential._check_peak_response`
and `_check_peak_response_jc`, and `a.output_type == b.output_type` in
`test_trace._same_result`. Rename-forced restatements: the lumped `Trace` checks
`n_cells == 0`, `p_cells is None`, `v_cells is None`, `cell_position is None` are now
`column is None`; the signature-default checks read `CouplingModel` through the `coupling`
parameter.

Temporary until the schema bump: `export._schema_1_inputs` writes the grouped `Trace.inputs`
in the schema-1 flat form (`output_type` 0, as every exported trace had), so every exported
file stays byte-identical; `tools/review_ab.py` picks the worktree's call form
(`fixture_cases.solver_inputs` where it exists) so it can time across the signature change.

Viewer browser tests run here with `PLAYWRIGHT_BROWSERS_PATH` pointed at a scratch directory
whose `chromium-1243/chrome-linux/chrome` links to
`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome` (26 passed at the session start).

Session gates: `-m slow` 150 passed; `tools/bench.py --skip-full-python`
(`docs/bench/fb90eb2.json`): every digest equal to the literal port's; the compiled rows 0.94 to
1.07 of the previous row `662ea10` (another host; ruling 50), the pure-Python rows 1.05 to
1.08; peak RSS 153.6 / 153.8 MB with the three histories recorded.

**Next** (`docs/review/plan.md`, progress R.9): 6.3c `LoopLayout` renames; 6.4 `histories`
and `export.to_*_dict` signatures with the `History` fields (`SweepProvenance`); the
`RunSettings` → `KernelSettings` rename; 6.5 the schema bump (before it, list the re-exported
data files and the renamed CSV headers, and run the viewer tests on that commit, ruling 84;
remove `_schema_1_inputs`); 6.6 docstrings (module docstrings of `response` and `trace` still
describe the old signatures); 6.7; 6.8 lint limits; then remove the `review_ab.py` call-form
switch.

Previous: session R.8 (supporting modules and tools, plan group 5 with 3.11, 2026-11-24/25) **done**.
Rulings 62-66 in the charter (`f74bc81`): the kernel's 56 statements a `docs/style.md` §11
exception; C-07 open by decision; the R.7 bench-row subjects left as they are (sentence below
corrected); gates and the A/B as before; the plan wins.

Done, one plan item per commit, each gated (lint and 949 + 24 compiled before the commit,
947 + 26 pure Python before the next; snapshot and support exact in both modes): 5.1
`3efb921` (`tools/fixture_cases.py`: loaders, tolerances, cache dir, flag sets;
`test_golden` re-exports; pytest `pythonpath = ["tools"]`), 5.3 `59fd3cf`
(`trace.FRAME_COLUMN_TABLE`), 5.4 `d5cc631` (`export._SWEEP_COLUMN_TABLE`, `export.read_csv`),
5.5 `f50fb9b` (`trace.interleaved_grid`; `loop_layout` 8 -> 3 args), 3.11 `ff06097`
(`response.solver_setup` / `column_grid`), 5.6 `b46c513` + `d21bf1d` (tools ask the query;
`Trace.portal_frame_height`), 5.7 `7c24b47` (`moc.display_moving_fractions`), 5.8 `de177d8`,
5.9 `0478dc1`, 5.10 `5400421`, 5.11 `18a4d36` / `6454074` / `92a1da4` (`StepSpec`,
`tools/sweep_document.py`, `ReferenceCase`), 5.12 `d14af6e` / `aafe0b2` (`run_case` in parts
with `RunProvenance`; `sweep_grid.py`, `sweep_rows.py`, `sweep_report.py` behind
`sweep_jc.py`; the report and its four PNGs byte-identical before and after), 5.13 `7d9c8df`,
5.14 `78c0449` (the viewer page byte-identical to the committed one). **Not made:** 5.2 (the
only gated user of `git` / `cpu_model` / the table is `sweep_jc.py`; S-23 open). 5.15 was made
with group 1. A/B per commit on the cases the change runs through: 5.3 0.987 / 1.008, 5.5
1.002, 3.11 0.962-1.030 (`lumped_r20_traced` 1.062 in the first run, 0.999 on a 9-round
repeat), 5.6b 0.988 / 1.024. `review_ab.py` has no sweep case: the sweep commits move
Python bookkeeping around unchanged solver calls. Pure-Python fast suite 156-172 s per commit
(170 s at the session start).

Session gates: `-m slow` 150 passed; `tools/review_snapshot.py` 27 of 27, `tools/review_support.py`
21 of 21 (histories exact, kernel X86_V4); bench row `662ea10` (digests equal; the 12 results
equal the row of `6fa4507`); cumulative A/B `137bdb5` -> `662ea10`, 7 rounds: 0.958-1.021 on
the ten cases. Every `docs/handover.md` command of a changed tool ran as written (not the
full Tier 1 / Tier 2 runs: hours); none moved.

Metrics (`tools/review_baseline.py`), session start -> end. Supporting modules: 47 -> 55
functions; over 6 args 5 -> 4, complexity over 10 1 -> 0, longer than 40 lines 8 -> 7.
`export._sweep_value` complexity 14 -> 8 (statements 23 -> 12); `export.to_trace_dict` code
lines 54 -> 33; `geometry.loop_layout` args 8 -> 3; `layout_from_trace` code lines 37 -> 12;
`histories.step_noise` 74 -> 69 code lines, `step_sine` 55 -> 50, `step` 35 -> 26.
Tools: 134 -> 141 functions, the over-target counts unchanged (1 / 2 / 1 / 8 / 19: the
ungated tools); `sweep_jc.run_case` 5 args, complexity 7, 101 code lines -> `run_case` 2 args,
complexity 1, 8 lines (its largest part, `_case_columns`, 68 lines, is the row literal).

For the owner: (1) the shared fixture module lives in `tools/` with pytest's `pythonpath`,
not in the package (a library module would have to know the repository's `tests/fixtures`
path); (2) the sweep's parts are now in `sys.modules` when a test loads `sweep_jc` (the
`_load_tool` loaders kept the tools out to keep hypothesis's examples stable; the suite passes
in both modes); (3) `tests/test_review_support.py`'s adapter patches
`sweep_rows.case_history` now (adapter section only, charter rule 6).

Next: write `docs/review/public_interface.md` and stop for the owner (before group 6).

Session R.7 (the rest of plan group 4, 2026-11-24) **done**. Rulings 58-61 in the charter.
4.2 to 4.4 dropped: `moc.step` keeps its even / odd flag, a recorded exception in
`docs/style.md` §11; C-04 and C-05 closed. `tools/review_ab.py` committed: the interleaved
A/B of two revisions (`--rounds`, `--repeats`, `--only`; `HEAD HEAD` for the A/A spread).
Done, one commit each, gated (949 + 24 compiled, 947 + 26 pure Python, snapshot and support
exact in both modes) and A/B timed against the commit before: 4.7 (`8af0627`, the frame as
one `_record_frame` call per loop, row and column writers), 4.8 (`51c8a73`, the writers in
`trace.py`), 4.10 (`fee6c4d`, `_integrate` = `_kernel_inputs`, kernel, `_peak_response`),
4.12 (`6fa4507`, the flattening in `loads`; exact on 6000 random histories with the D-7 /
D-8 errors; compiled lumped 2-8 % faster). C-07 stays open (the two walks are kept: the
one-walk form cost about 20 % in R.4). Findings C-06, C-14, C-15, C-22 done. Session gates:
`-m slow` 150 passed; bench row `6fa4507` (digests equal; host-disturbed times); cumulative
A/B against the session start `1d3bb7a`: lumped 0.885 / 0.935, everything else within
noise on a repeat (0.972-1.021). Pure-Python fast suite 220-232 s per commit (226 s at the
session start). Three of this session's four bench-row commits (`b716bcb`, `3cbb504`, `0b38259`, the rows of
`8af0627`, `51c8a73`, `fee6c4d`) say "R.6" in their subject (a helper script's label); the
fourth (`fd722c4`, row `6fa4507`) says "R.7". The rows are this session's; the subjects are
left as they are (ruling 64).

Metrics, session start -> end: `_integrate_kernel` 6 args, complexity 10 -> 10, statements
59 -> 56, code lines 153 -> 140 (the statement target of 50 is still missed: the two
`_FrameLoads` blocks and two multi-line `moc.step` calls remain in the loops);
`_integrate` complexity 6 -> 3 (radon 18 -> 5), statements 33 -> 8, code lines 103 -> 28,
with `_kernel_inputs` (51 code lines) and `_peak_response` (26) split out.

Next: plan group 5 (supporting modules and tools; 3.11 joins it, ruling 48).

Session R.6 (the single substep, plan group 4, 2026-11-24) **done for this session**.
Rulings 47-57 in the charter; `docs/style.md` §4 has the per-sub-step argument rule (57).

Done: `coupling.fluid_column` for `JunctionCoupling` (`1eeb6d4`, ruling 49); step 0, the
kernel starts the junction force (`bfeb003`, 7 -> 6 arguments); design A's first form
(`6ea80ba`) was 1.1-2.0x slower compiled and reverted (`b1ce745`); option 1 (ruling 56):
4.9a / 4.9b (`256522a`, `0d1b15c`), the 4.9c simplifications (`1634342`, `2c239e4`,
`c6abb02`, `f0bade5`, `643fcbd`, `dea48c7`), 4.1 (`6a6d423`), 4.5 (`ec3bbfe`), the kernel
docstring. 4.6 absorbed by `_structure_substep`. Every commit gated (949 + 24 compiled,
947 + 26 pure Python, snapshot and support exact in both modes), A/B timed and benched; the
whole against `bfeb003`: 0.973-1.027 on ten cases. Kernel: 6 args, complexity 10 (was
23), 59 statements (89), 153 code lines (183). Session gates: `-m slow` 150 passed;
`tools/bench.py` row `ec3bbfe` (digests equal to the literal port; its times disturbed by
the host, which slowed ~15 % during the session). Pure-Python fast suite +6.5 % for 4.9
measured back to back (231 -> 246 s). Tables in `docs/review/substep_design.md`.

Open for the owner: 4.2-4.4 against ruling 57 (three options in `substep_design.md`,
"Group 4 after 4.9"). Next, in plan order: 4.7 (trace writers: one call per recorded
sub-step, which also brings the kernel under 50 statements), 4.8, 4.10, 4.12. The A/B
harness of this session is not committed (scratchpad: `child.py`, `ab.py`); it may be
worth adding under `tools/` in the supporting-modules session.

Session R.5 (parameter objects, plan group 3, 2026-11-24) **done**. Charter rulings 43-46
(speed judged by an A/B run on one host or relative to the literal port, 5 % limit on both
paths; plan 2.2 in this session; no SI conversion at the boundary, the R.4 proposal
declined; the plan wins over the brief, the groups go to `docs/review/parameter_objects.md`).

Plan 3.1 first, as the proof on one function (`2f1dce2`: `step_scalars` takes `SdofParams`,
the kernel receives it whole); A/B within noise; bench `a1c1724`. Then, as the plan asks,
stopped and wrote `docs/review/parameter_objects.md`; the owner approved it as proposed, and
it is built, one object per commit, innermost first: `moc.FluidColumn` (`moc.step` 15 -> 4;
`JunctionCoupling` holds `column`, `dt`, `d_f`; `moc.empty_column()` for the lumped run, the
same type); plan 2.2, `FluidColumn.is_fluid_coupled` in place of the kind code 0 / 1;
`trace.TraceBuffers` (the four frame buffers and the stride, from `allocate_frames`);
`response._Frame` (`_trace_frame` 23 -> 4); `response.RunSettings` (built by the entry
points; `_integrate` 9 -> 5); `response._ForceSchedule`; `response._KernelResult` (the
kernel 36 -> 7); `trace.TraceRequest` moved from `response`, `build_trace` 15 -> 6;
`moc.ColumnGrid` (returned by `grid_size`) and `coupling.FluidConstants`
(`JunctionCoupling` 8 -> 5); then four R0 commits applying the K names of
`docs/nomenclature.md` (ruling 21; the four local names that differ because of a clash with
a `moc` function are in its "Applied (session R.5)" table). The kernel keeps 7 arguments:
the junction force (an evolving scalar) and the response history (an output array) are not
grouped with an input tuple; the reason and the other functions still above 6 (entry
points, 3.7, 5.5, an ungated tool) are in `findings.md`.

Argument counts, before and after (`ruff` PLR0913 counting):

| function | before | after |
|---|---|---|
| `response._integrate_kernel` | 36 | 7 |
| `response._trace_frame` | 23 | 4 |
| `moc.step` | 15 | 4 |
| `trace.build_trace` | 15 | 6 |
| `structure.step_scalars` | 11 | 6 |
| `response._integrate` | 9 | 5 |
| `coupling.JunctionCoupling.__init__` | 8 | 5 |
| `trace.allocate_frames` | 2 | 3 |

Gates: every code commit `make lint` and the compiled fast suite (949 passed + 24 skipped)
before it was made, the pure-Python suite (947 + 26) on a worktree of it before the next;
the snapshot and support checks exact in both modes throughout; no test count changed.
Tests changed only in how they call (`moc.step` and `JunctionCoupling` with the new objects,
`jc.column.*` for the column arrays, `allocate_frames` with the stride). A/B timing against
the session base on this host after 3.1, 3.2, 3.3, 3.4, 3.5 and for the whole session (table
in `parameter_objects.md`): 0.97x-1.03x per case, within the A/A spread of the harness
(up to ±5 % on the 90 ms JC case); whole session 0.980x-1.016x. Session gates on `f2f11d5`:
`-m slow` 150 passed; `tools/bench.py --skip-full-python` (`docs/bench/f2f11d5.json`):
digests all equal to the literal port, results the same as `a1c1724`. Its ratios to the
literal port are worse than `a1c1724`'s (numba r20 0.121 against 0.091, JC r96 full 0.668
against 0.537) although the code paths A/B as equal: the host drifted during the run (the
literal JC case took 128 s against 106 s in the morning, and the pure-Python rows, whose
code barely changed, moved the same way). An interleaved A/B straight after the bench
(base `77ba687` against `f2f11d5`, 5 rounds) had both slower than in the morning and new /
old at 0.94x-1.03x. By ruling 43 the A/B decides; the bench row is kept as measured.

Next: the rest of group 3 (3.7 span / restraint / fluid objects for `lumped_params` /
`jc_params`, 3.10 entry-point extraction, 3.11 the set-up query), then write
`docs/review/substep_design.md` and stop for the owner before group 4. Observation for the
owner, not acted on: `JunctionCoupling` now holds only the column, `dt` (read by tests only)
and `d_f` (0.0 at entry, written back after the run and read by tests only); under ruling 2
it could become a function returning the `FluidColumn`.

Session R.4 (constants and control flow, plan group 2, 2026-11-24) **done**. Rulings 39-42
in the charter: gates before each commit, the pure-Python run of a commit green before the
next is made, push only when all are green (39); plan 2.2, the coupling kind as a plain
flag, moved to group 3 because it changes a kernel parameter's type (40); 2.15 approved
(41), then reverted (42).

Done, one constant or one refactoring per commit: the load-phase pair `loads.PHASE_TRANSIT`
/ `PHASE_FORCED`, re-exported by `trace` with `PHASE_FREE_DECAY` (2.1); in `structure`
`PERCENT`, `GRAVITY`, `FRICTION_DEAD_ZONE`, `NEWTON_RELATIVE_TOLERANCE`, `NEWTON_RELAXATION`,
`NEWTON_ITERATION_LIMIT`, `END_FIXITY_LAST_PASS` (2.4, 2.5); `response.FREE_DECAY_THRESHOLD`
(2.6); `moc.LEGACY_B_INACTIVE_START_CELL_COUNT` (2.7); supporting code (2.9): `MM_PER_M` and
`PA_PER_BAR` in `tools/cases.py`, `MM_PER_M` in `tools/sweep_jc.py` (`od / 2000` kept, with a
comment: one divisor, splitting it regroups), `STEP_TO_PEAK_RATIO`,
`DEFAULT_ENVELOPE_DECAY_CYCLES` / `_FRACTION` in `histories`, `BYTES_PER_MB` in
`tools/export.py`, the second `1.33` in `check_pipe_table`; the `rho_c == 0` guard as the
first statement of the `JunctionCoupling` constructor (2.10); the trace stride inside the one
optional `_TraceRequest` (2.11); `loads._next_position` for the four identical "next index,
wrapping to the next column" blocks of the forced phase (the advance block is the same rule)
and the predicate `_wraps_to_next_column` for the transit block (2.13); the two schedule
item shapes as `_TransitSample` / `_ForcedSample` (2.14). Each constant is the literal it
replaces, of the same type, in the same place; VBA quotations in comments keep the literal.

2.15 (one per-sample walk; `unbalance_force` subtracting the `elbow_forces` pair; the
cross-check removed) was made bit-identical and gated, then measured: the compiled lumped
path is about 20 % slower (golden r20, 0.177 s to 0.213 s, A/B on this host), because the
untraced run then builds both elbow-force lists. Reverted on the owner's word (two revert
commits, each gated); C-07 is open again, to be looked at with 4.12.

Where the brief and `plan.md` differ, the plan was followed: the friction `0.5` stays inline
with its derivation comment (plan 2.8, `docs/style.md` §6, ruling 14), not a constant;
`out_max * 2` named once (C-N08) is a rejected nit and was not made; splitting `_schedule`
into a phase-1 and a phase-2 function is R.2's optional SC-14, not part of the governing C-08,
and was not made.

Proposal for the owner (behaviour change, not made): convert inputs to SI once at the
boundary. In the solver core only `damping_percent / PERCENT` is left; moving it to the entry
(`damping_ratio = damping_percent / 100`, then `2 * sqrt(k m) * damping_ratio`) regroups the
damping product and changes `damping` by at most about one ulp (relative 1e-16), so the
results by rounding level (golden errors unchanged at their 1e-13 tolerance; every snapshot
and support document with damping would be rewritten). In the tools, the pipe table in mm
(`tools/sweep_jc.py`) could be held in metres: the pipe properties move in the last bits and
the stored sweep rows and `sweep_histories.txt` change at rounding level. Recommendation: not
worth a DEVIATIONS row for either; the named factors read clearly.

Gates: every commit `make lint` and the compiled fast suite (snapshot and support checks
included) before it was made, and the pure-Python suite on a worktree of it before the next
(949 passed + 24 skipped / 947 + 26 throughout; log of each commit in the session). The
container restarted once, during the pure-Python run of a674054; that run was repeated
(green) before the next commit. A fuzz of `unbalance_force` and `elbow_forces` (6000 random
histories and shapes, values and the D-7 / D-8 error positions compared exactly) against the
previous commit ran for 2.13, 2.13b, 2.14 and 2.15. Session gates on `213e3ef`: `-m slow` 150
passed; `tools/bench.py --skip-full-python` (`docs/bench/213e3ef.json`): digests all equal to
the literal port, results the same as `9dd2f4b`. The host changed with the restart (2.10 GHz
against 2.30 GHz: the unchanged literal port runs 1.26-1.34x the time of `9dd2f4b`); against
the literal reference no case is slower (numba lumped 0.100 to 0.098, JC full 0.608 to 0.572).

Next: plan group 3. Write `docs/review/parameter_objects.md` (the groups, with 2.2 and the
kernel-signature names of ruling 21) and stop for the owner before 3.1.

Session R.3, part 2 (the renames, 2026-11-23) **done**. The owner approved
`docs/nomenclature.md` with two changes and answered Q-N1 to Q-N8 (charter rulings 29-38;
the nomenclature records the answers). Then, one quantity or family per commit across
`src/`, `tests/` and `tools/`: the "For Ben to review" comment at the transit walk's column
bound (ruling 31); the `LoopLayout` elbow A / B docstring (ruling 34); every rename the
nomenclature marks R (internal names, module constants, NamedTuple fields, and every
non-entry-point function with its parameters, ruling 29): `SdofParams` fields,
`solve_quartic`, the set-up parameters of `structure`, `loads`, `moc`, the moving-fraction
functions, `column_at_rest`, `mean_velocity_divisor`, `end_pressure_decay_factor`, the two
`moc` constants and `moc.step` locals, the grid counts, the loads walk (transit delay,
positions, weights, elbow forces, bookkeeping), the load phases (`PHASE_FORCED`),
`substep_duration`, `substep_count`, `nominal_forced_sample_count`, the forced counts,
`grid_point_count`, the trace helpers and frame-column constants, the `response`, `export`,
`viz/geometry` and `histories` locals and helper parameters, and the gated tools
(`sweep_jc` constants, `Pipe`, `Case`, `run_case`; `cases.py`). Kernel-signature names wait
for plan group 3 (ruling 21); public keywords, returned dataclass fields and exported names
for the public API session. `docs/nomenclature.md` lists seven places where the code departs
from the table's wording (name clashes) and what was left on purpose; `docs/architecture.md`,
`findings.md` (done / partly done) and `plan.md` (progress) follow.

Two mistakes in this session, both caught by the gates before anything was pushed, and
taken out of the history (the branch was rebuilt locally by cherry-picking, so every commit
on it is green on its own): (a) the renaming tool also renamed a keyword argument, so
`PeakResponse(history=...)` became `response_history=` and every run with `output_type > 0`
or a trace raised `TypeError`; (b) one call site of `moc.decay_factor` in
`tests/test_differential.py` was missed. Since then every commit is prechecked (lint and the
compiled fast suite) before it is made, and the full gate runs on a worktree of the commit.

Gates: every commit `make lint` and the fast suite compiled and with `NUMBA_DISABLE_JIT=1`
after a cache wipe, run on a worktree of the commit (949 passed + 24 skipped / 947 + 26
throughout; no test count changed in part 2); session gates on the final tree: `-m slow`
150 passed; `tools/bench.py --skip-full-python` (`docs/bench/9dd2f4b.json`): digests all equal to
the literal port, results the same as `b92e840`, no case slower beyond noise (0.91x-1.49x;
the one 0.91x is the 92 ms JC case).

Session R.3 (renames session, part 1, 2026-11-23) **stopped at the rename table**, as the
brief asks: nothing is renamed yet. (1) The owner's rulings 13-28 are in the charter and
`docs/style.md`. (2) The two reviews reconciled (ruling 22): R.1 is again
`docs/review/findings.md` / `plan.md`, R.2 kept as `findings_r2.md` / `plan_r2.md`; brought
across from R.2: SP-15, SP-35, SP-36, SP-41 (accepted; SP-25 not, a tool no test runs),
possible defects 15-24 for the lead author, the order changes (group 0 removals first,
schedule clean-up 2.13-2.15, bench after every group-4 commit), the Numba rule (group 3) and
the early wrong-document fixes; C-13 closed by ruling 13. (3) Group 0, the ruling-2
removals, one commit each: `JunctionCoupling.coupling_force` and `column()` (3.0a), the
`Coupling` protocol and `NoCoupling` (3.0b: `_integrate` takes a `JunctionCoupling` or
`None`; the kernel still gets the kind 0 / 1 until plan 2.2), `structure.step` and `State`
(3.0c), `structure.restoring_force` (3.0d); `docs/architecture.md` follows. Dropped under
ruling 23, because they asserted the removed wrapper's own behaviour:
`test_differential.py::test_junction_coupling_reproduces_the_legacy_df_sequence` lost
`type(d_f) is float` (the wrapper's `float()` cast; `moc.step` returns `numpy.float64` in
pure Python) and `jc.d_f == d_fs[-1]` (the wrapper's write-back);
`test_differential.py::test_no_coupling_is_unchanged` (one assertion, `NoCoupling`'s return
value) was removed. Restated against `moc.step` through the test helper
`test_differential.advance_column`: the `dF` and column sequences, the exact positive zero
with no fluid area, the column moving with the mass, and the trace replay in
`test_trace.py`. (4) Wrong documents corrected (plan 0.2-0.5): the grid count covers the
whole column; the outlet leg is shorter on the legacy profile only; the `step_sine`
defaults; where `vav_denominator` is checked; the `decay_factor` half-life is `2 L / c`.
Comments (0.6, 0.7): the friction `0.5` (ruling 14) and `P_CAP_FACTOR` (ruling 27), for Ben
to confirm. (5) `docs/nomenclature.md` written (plan 0.1), with questions Q-N1 to Q-N8;
`docs/review/rename_table.md` points at it (ruling 10). Gates: every code commit `make lint`
and `make test-both` (949 passed + 24 skipped compiled / 947 + 26 pure Python after 3.0b,
one test fewer); documents-only commits `make lint` (no test reads the charter, style guide,
review files or nomenclature; the commits touching `docs/data_format.md`, which
`tests/test_export.py` parses, ran `make test-both`). Session gates on `b92e840`: `-m slow`
150 passed; `tools/bench.py --skip-full-python` (`docs/bench/b92e840.json`): digests all
equal to the literal port, results the same as `64b171d`, no case slower (0.72x-1.03x).

Session R.2 (second independent review, 2026-11-23) **done**: findings and plan only, no
code change. The R.1 lists are kept unchanged as `docs/review/findings_r1.md` and
`docs/review/plan_r1.md` (the charter's rulings cite their ids; the charter and the
references below still name `findings.md` / `plan.md` for them: owner's question R.2 Q-2).
Six blind reviewers (151 raw findings), merged to 71 Design/Readability findings, each
through its own verifier: 67 confirmed, 3 refuted, 1 unclear. `docs/review/findings.md`
(ids `SC-`, `SP-`, `N-`): 13 Design, 55 Readability, 24 Nits (unverified), constraints
K-1 to K-9, 15 possible defects, what to leave alone. `docs/review/plan.md`: groups 0-6,
five order changes, questions Q-1 to Q-11. Toy kernel (scratch, not committed): NamedTuple
parameters and compiled helpers bit-identical in both modes and as fast as flat scalars,
**except** a column NamedTuple passed two calls deep per substep (1.46x at 60 cells, 1.16x
at 300); the plan's parameter-object commits follow that rule. Gates not re-run (docs only).

Session R.1b (owner's decisions applied, 2026-11-23, branch
`claude/solver-review-charter-oe8gtr`, where the rest of the review now runs) **done**; no
refactoring. (1) The pressure solver is removed: `pressure.py` (with the
`get_pressure_response` alias), `_vba_semantics.py` (used by nothing else), their 107
differential tests, the seven snapshot documents `pressure_a..e`, `pressure_sweep`,
`tie_rules` (27 documents / 227 calls remain, unchanged), the two pressure bench cases and
every reference in tools and current documents; findings about it alone closed as
"removed" (10). Kept on purpose: `legacy_port.get_pressure_response` (frozen) with its
tests (the Example golden case, `test_smoke`, `test_structure`) and
`tools/extract_fixtures.py`, which writes the committed Example fixture that holds the
pressure case. (2) The JC-equals-lumped property test pins its 1.27e-12 counterexample as
an `@example` (force `-1428049.2002131606`, the full-precision value behind the recorded
digits) at rtol 5e-12, approved by the lead author on 17 Nov 2026. (3) The sweep-row check
runs on stored histories (`tests/review_support/sweep_histories.txt`) and is exact on
every host; the history check is exact on the stored `X86_V4` kernel and at 1e-12 elsewhere
and prints its mode in every run's summary; checked with `NPY_DISABLE_CPU_FEATURES=X86_V4`
and mutation S3. (4) The owner's rulings are in the charter ("Rulings", 1-12),
`docs/style.md`, `plan.md` (answers under each question; commits 3.0a-3.0d remove the
test-only interfaces; 2.2 makes the coupling a plain flag; group 7 holds the two edge-case
fixes) and `findings.md` (90 accepted, 40 rejected: the 39 Nits and S-17, 10 removed).
(5) "Proposed derivation, for Ben to confirm:" comments at every use of `12 EI / h^3`, the
end-fixity factor, `4 / 3`, `out_max * 2` and `4 * celerity * dt`. (6) A "For Ben to
review:" comment at the odd-substep junction force in `moc.step` and DEVIATIONS D-24.
Gates on the final tree: lint clean; `make test-both` 950 passed + 24 skipped (Numba) /
948 passed + 26 skipped (pure Python), down from 1063 / 1061 by the 107 differential tests
and 7 snapshot documents removed and up by one new support test; `-m slow` 150 passed;
`tools/bench.py --skip-full-python` (`docs/bench/64b171d.json`): digests all equal to the
literal port and results the same as `253210a`, the full JC golden cases 0.85-1.09 s.

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
     Answered (R.3, ruling 17): keyword-only arguments count; an entry point still over
     the limit after the public API session gets a recorded exception.
  4. Answered (R.1b, charter ruling 4): the user-facing entry points are the solver entry
     points of `response`, `histories.canonical` and the `export.to_*_dict` functions.
     Still open: whether `histories.step`, `step_sine`, `step_noise` count as well.
     Answered (R.3, ruling 18): every `histories` function a tool calls is user-facing
     (today `canonical`, `from_params`, `p_cap`); `step`, `step_sine`, `step_noise` are not.
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
     it needs is ruled, charter ruling 1) — written in R.3, awaiting approval;
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

**Group 2 of `docs/review/plan.md`** (constants, units, control flow): 2.1 the phase
constants defined once and imported (the bare 0 / 1 tags of `loads`), 2.2 the plain
`is_fluid_coupled` flag (ruling 16), 2.4 to 2.7 the core literals, 2.9 the supporting-code
conversions, 2.10, 2.11, then the schedule clean-up 2.13 to 2.15. Rules: one literal per
commit for 2.4 to 2.7; `make clean-cache` before tests whenever a compiled function or a
constant it reads changes. Then stop before group 3 and write
`docs/review/parameter_objects.md` (ruling 10); group 3 applies the kernel names fixed in
`docs/nomenclature.md`.

**Still open for the owner:** R.0b question 5 (the `docs/viz/data/` files and the viewer's
old schema at the bump) and 8 (lint rules for style §7-§9); for Ben: the derivation
comments (now including the friction `0.5`), `P_CAP_FACTOR`'s basis (now
`PEAK_TO_DESIGN_PRESSURE_RATIO`), the transit walk's column bound and D-24; for the lead
author: the suspected defects of `findings.md` (ruling 20).

**Stage 6** (unchanged), when the lead author wants it.

* Remove `legacy_port.py` / `vba_compat.py` when the reference is no longer wanted (the
  `tests/test_quirks.py` pins move to the live modules); any extension beyond the VBA needs the
  lead author's decision and a DEVIATIONS row.
* Optional: commit `docs/viz/data/tier2_sweep.json` (22.7 MB; `tools/export.py sweep --from-csv
  docs/sweep/tier2_3664dc7_f4b.csv --tier 2`) and add it to `SWEEP_FILES` in
  `tests/test_viewer.py` if the viewer should carry Tier 2 in the repository; `plot --mu` /
  `--amplitude` on the Tier 2 CSV select another friction and amplitude level for figures 1–3.
