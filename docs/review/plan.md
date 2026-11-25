# Clean-code review — refactor plan

Session R.1, 16 Nov 2026. Orders the findings of `docs/review/findings.md` into commits.
Nothing here has been started.

**Updated in session R.1b (23 Nov 2026) to the owner's rulings** (`docs/review/charter.md`,
"Rulings"): the order below is accepted; the pressure solver is gone (its rows are struck
through); the test-only interfaces are removed (group 3 opens with that); the coupling is a
plain flag; the ungated tools get rename-only edits; Nits are rejected, so a nit id below is
a reference only and its fix is not a commit of its own; S-17 is rejected; the two edge-case
fixes are group 7. The answers are under each question at the end.

**Progress (session R.3, 23 Nov 2026).** Done: group 0 (3.0a to 3.0d), "Before group 1"
(0.1 to 0.7) and group 1 (1.1 to 1.16) for every name the nomenclature marks R. Left for
group 3: the kernel-signature names (ruling 21); for the public API session: public keywords,
returned dataclass fields and exported names. Next: group 2.

**Progress (session R.4, 24 Nov 2026).** Group 2 done: 2.1, 2.4 to 2.7, 2.9 to 2.11, 2.13,
2.14, one constant or one refactoring per commit. 2.2 moved to group 3 (ruling 40: it
changes a kernel parameter's type). 2.15 was approved for R.4 (ruling 41), made, and
reverted by the owner (ruling 42: about 20 % slower on the compiled lumped path); C-07 is
open, to be looked at again with 4.12 (the schedule flattened in `loads`). The `out_max * 2` half
of 2.6 is C-N08, a rejected nit, and was not made. The friction `0.5` stays inline with its
derivation comment (2.8, `docs/style.md` §6, ruling 14). Next: write
`docs/review/parameter_objects.md` and stop for the owner (before 3.1).

**Progress (session R.5, 24 Nov 2026).** Rulings 43-46 recorded. 3.1 done (`step_scalars`
takes `SdofParams`; the kernel receives it whole), as the proof on one function: snapshot
exact in both modes, A/B timing within noise. The groups for 3.2 to 3.8, with 2.2, are
proposed in `docs/review/parameter_objects.md` (names, fields, which functions take each,
the commit order); stopped there for the owner, as this plan asks before group 3 is built.
The owner approved it in the session, and it is built: 3.2 (`FluidColumn`), 2.2 (the flag on
the column), 3.3 (`TraceBuffers`, `_Frame`), 3.4 (`RunSettings`, `_ForceSchedule`), 3.5
(`_KernelResult`), 3.6 (`build_trace` takes the request, settings and column;
`TraceRequest` moved to `trace`), 3.8 (`ColumnGrid`, `FluidConstants`), then the K names of
the nomenclature (four R0 commits). Every function of the group takes at most 6 arguments
except the kernel (7, the reason in `findings.md`). Left in group 3: 3.7, 3.10, 3.11. Next:
those, then `docs/review/substep_design.md` before group 4.

**Progress (session R.6, 24 Nov 2026).** Rulings 47-50 recorded: 3.7 and 3.10 move to the
public API session (group 6), 3.11 to the supporting-modules session (group 5);
`JunctionCoupling` is replaced by `coupling.fluid_column` (ruling 49, `1eeb6d4`). The two
substep designs are in `docs/review/substep_design.md` and summarised under group 4;
stopped there for the owner before any change to the kernel.

**Progress (session R.6, continued).** Design A approved (ruling 51), its first form
reverted for speed, option 1 made (ruling 56): 4.9 done as `_structure_substep(state,
applied_force, sdof_params, dt)` called by both loops, with 4.9c's simplifications; 4.6 is
absorbed (the maxima live in `_structure_substep`); 4.1 and 4.5 done. **Held for the owner:**
4.2 to 4.4 (see `substep_design.md`, "Group 4 after 4.9"). Not started: 4.7, 4.8, 4.10, 4.12.

**Progress (session R.7, 24 Nov 2026).** Rulings 58-61. 4.2 to 4.4 dropped (ruling 58,
`moc.step` a recorded exception in `docs/style.md` §11); `tools/review_ab.py` committed
(ruling 59); 4.7, 4.8, 4.10, 4.12 done, one commit each, gated and A/B timed. Group 4 is
complete except 4.13 (removed in R.1b). Next: group 5 (supporting modules and tools, with
3.11 moved there by ruling 48).

**Progress (session R.8, 24-25 Nov 2026).** Rulings 62-66 (the kernel's 56 statements a
style §11 exception; C-07 open by decision; gates and the A/B as before; the plan wins).
Group 5 done, one plan item per commit (5.6, 5.11 and 5.12 in two or three), each gated and,
where the solvers run through it, A/B timed: 5.1 (`tools/fixture_cases.py`), 5.3 (the frame
table), 5.4 (the sweep table and `export.read_csv`), 5.5 (`interleaved_grid`), 3.11
(`response.solver_setup` / `column_grid`), 5.6 (the tools ask the query; the height on
`Trace`), 5.7 (`moc.display_moving_fractions`), 5.8, 5.9, 5.10, 5.11 (`StepSpec`,
`tools/sweep_document.py`, `ReferenceCase`), 5.12 (`run_case` in parts with `RunProvenance`;
`sweep_grid.py`, `sweep_rows.py`, `sweep_report.py`), 5.13, 5.14. **Not made:** 5.2 (its only
gated user is `sweep_jc.py`; S-23 open, see `findings.md`). 5.15 was made with group 1 (R.3);
nothing further. Next: `docs/review/public_interface.md` and stop for the owner (before
group 6).

**Updated in session R.3 (23 Nov 2026) to the reconciliation with the second review**
(charter ruling 22; `docs/review/plan_r2.md`). This plan stays the governing one. Brought
across from R.2: its order changes (the ruling-2 removals as group 0, before the renames;
the schedule clean-up in the control-flow group, 2.13 to 2.15; `tools/bench.py` after every
commit of group 4), its Numba rule for the parameter-object commits (group 3), the
wrong-documentation fixes done early (0.2 to 0.5), and rows for the four findings brought
across (SP-15, SP-35, SP-36, SP-41). Rulings 13 to 28 answer Q-1, the friction half of Q-4,
the rest of Q-6 and Q-11; 5.16 is dropped (ruling 13).

**Approvals in files (ruling 10).** Where a session is to stop and show the owner
something, it also writes it under `docs/review/`: the rename table
(`docs/review/rename_table.md`, before group 1), the parameter-object groups
(`docs/review/parameter_objects.md`, before group 3), the substep designs
(`docs/review/substep_design.md`, before group 4) and the public interface
(`docs/review/public_interface.md`, before group 6).

Every commit below is one refactoring, named in its message with its risk class, and is
gated as the charter says (`make lint`, `make test-both`; revert on red). Expressions move
verbatim. A session ends with `-m slow` and `tools/bench.py`. Ids are those of the
findings; "Q-n" refers to the questions at the end.

## The order, and where I would change it (accepted by the owner, R.1b)

The charter's order is kept: names; constants, units and control flow; parameter objects;
the single sub-step; supporting modules and tools; public API, data format, docstrings and
lint limits. Four changes inside it:

1. **Kernel-signature names move from group 1 to group 3.** `tr_f`, `flat`, `flat_a`,
   `p_a`, `n_seg`, `pivot`, `off`, `rec` and the other names in the 36-parameter signature
   (C-36, parts of C-25 and C-28) are replaced by parameter-object fields in group 3.
   Renaming them first means every one changes twice, in the riskiest file, for no reader.
   Group 1 renames concepts (fields, locals, functions outside the kernel signatures);
   group 3 names each kernel parameter once, as a field.
2. **`docs/nomenclature.md` comes before group 1** (C-24). It is the word list every rename
   draws from, and it needs the owner's rulings on vocabulary (Q-6) before the first
   rename, not after.
3. **The phase and kind constants (C-09) open group 2**, ahead of the unit constants. The
   parameter objects and the sub-step extraction both lean on them.
4. **The ungated tools go last in group 5, or not at all** (Q-7). The plots and report of
   `sweep_jc`, `bench.py`, `extract_fixtures.py`, `golden_report.py` and `profile_delta.py`
   have no test; a refactoring there cannot be shown to preserve anything. The gated
   supporting code goes first.

Two things I would not move although it is tempting: docstrings stay last (rewriting the
docstring of a function that is about to be split is wasted), and the exported names stay
in the single schema bump.

## Group 0 — the ruling-2 removals (from R.2's order; before the renames)

Moved here from the head of group 3 (R.3, ruling 22): group 1 would otherwise rename
`coupling_force`, `State` and `restoring_force` only for group 3 to delete them. The one
structural change of the renames session. One commit each; the tests that called the
removed code are pointed at the code that runs, assertions unchanged, except those that
asserted a property of the removed wrapper itself (ruling 23: dropped and listed in
`NOTES.md`).

| # | commit | findings | risk |
|---|---|---|---|
| 3.0a | Remove `JunctionCoupling.coupling_force` and `column()`; the tests that call them drive `moc.step` on the coupling's arrays | C-03, C-N13 | R3 |
| 3.0b | Remove the `Coupling` protocol and `NoCoupling`; `_integrate` takes `JunctionCoupling` or `None` and passes the kernel its kind as `int(coupling is not None)`, so the kernel is unchanged until the plain flag of 2.2 | C-03 | R3 |
| 3.0c | Remove `structure.step` and `State`; their tests call `step_scalars` | C-10 | R3 |
| 3.0d | Remove `structure.restoring_force`; its tests call `effective_displacement` | C-10 | R3 |

## Before group 1

| # | commit | findings | risk |
|---|---|---|---|
| 0.1 | Write `docs/nomenclature.md`: symbol or name, meaning, unit, VBA name, for every kernel symbol kept and every name group 1 introduces | C-24 | R0 |
| 0.2 | Correct the two descriptions of what the grid count covers (`moc.py:108`, `docs/data_format.md:251`) | S-38 | R0 |
| 0.3 | Correct `docs/data_format.md:113` (the outlet leg is one cell shorter on the legacy profile only) and the `step_sine` docstring's defaults | SP-41 | R0 |
| 0.4 | `peak_response_jc` docstring: an unknown `vav_denominator` raises only where the MoC grid is built (not on a short pipe); the entry check is 6.1 | C-12 | R0 |
| 0.5 | `moc.decay_factor` docstring to its formula: applied once per even update (every `2 dt`), it halves the end-node pressure over `2 L / c` | R.2 defect 8 | R0 |
| 0.6 | Derivation comment for the friction `0.5`: the share of the pipe's weight carried on the moving part (ruling 14), for Ben to confirm | C-35 | R0 |
| 0.7 | `P_CAP_FACTOR` comment: the sweep's peak pressure as a multiple of design pressure, set by the lead author on 22 Oct 2026 (ruling 27); Ben to confirm its basis | S-45 | R0 |

Q-6 is answered (rulings 1, 15). 0.2 to 0.5 are docstrings and document lines that state
something the code does not do (R.2's order change: wrong documentation is corrected now,
not in 6.6; a doc-only commit cannot move a bit). 0.6 and 0.7 are comments.

## Group 1 — names (R0)

Internal names only. Public keywords, the alias, exported keys and CSV columns do not
change; the snapshot and support adapters absorb the renamed attributes.

| # | commit | findings |
|---|---|---|
| 1.1 | `SdofParams.fric_acc` to `friction_velocity_step`, `ratio2` to `closed_gap_stiffness_ratio` (attribute side; exported keys stay) | C-30, S-37 |
| 1.2 | Transit delay: `unb`, `unballance_step_qty`, `unb_steps`, `k_overlap` in `loads`, `response` and the tools | C-27, S-06 (names) |
| 1.3 | `loads` index walk and `_Run` fields | C-37 |
| 1.4 | Forced-phase vocabulary: one pair for delay / ramp and transit / history, in names and docstrings | C-44, S-39 |
| 1.5 | Unbalance force: `f`, `f_u`, `forces` outside the kernel signature; `f_applied` | C-26 |
| 1.6 | Elbow forces in `loads` (`force_a`, `fa`, `fb`); `F_A` to an acceleration name; `moc.py:338` `fa, fb` | C-25 |
| 1.7 | `structure` solver locals (`var_a..c`, `len_val`, `error_val`, `ax`, `av`) | C-38 |
| 1.8 | ~~`pressure` locals and `PressureSetup` fields~~: removed with the pressure solver (R.1b) | C-39 |
| 1.9 | ~~`pressure.grid_size` renamed; `tot_ind` and `out_max` inside `pressure`~~: removed (R.1b); the `loads` / `response` part of C-29 is 1.13 | C-21, C-29 |
| 1.10 | Internal `fluid_densty`, `h`, `time_step` / `dt` in `structure`, `moc`, `coupling` | C-31 |
| 1.11 | `d_f` descriptions, `DAMPING_A`, `vav_div` / `vav_divisor` (internal) | C-45 |
| 1.12 | `history` (response history against force history), `decay`, `frac` in `loads` | C-43 |
| 1.13 | Counts and indices outside kernel signatures: `_count`, `_index`, one spelling of sub-step | C-28, S-40, C-N17 |
| 1.14 | Supporting code: `jc`, `cap`, `p`, `h`, `kind` reused; booleans as predicates; computation names in `sweep_jc`, `geometry`, `profile_delta`; tool argparse `dest` names | S-44, S-46, S-47, S-48, C-N15 |
| 1.15 | "Moving fraction" for the per-cell weight: prose, `frac_a` / `frac_b` outside the kernel signature, the `interp_fraction_*` set-up functions (the kernel parameters with group 3, ruling 21) | SP-36 |
| 1.16 | `LoopLayout` docstring: which drawn corner is elbow A (ruling 26) | SP-35 |

Each row is one commit, or one per module where the rename crosses more than about ten
files. 1.7 and the `step_scalars` part of 1.1 touch compiled code: cache wipe, both modes.

## Group 2 — constants, units, control flow (R1, R2, R3)

| # | commit | findings | risk |
|---|---|---|---|
| 2.1 | One named phase pair, used in `loads`, `response`, `trace`, the tests | C-09 | R1 |
| 2.2 | **Moved to group 3 (ruling 40).** The coupling kind as a plain flag (fluid coupling on or off, a bool) in place of `KIND` 0 / 1 and the literal `1` in the kernels (ruling 2, in place of a constant pair) | C-09 | R2 |
| 2.3 | ~~Unit factors in `pressure.setup` and `pump_boundary`~~: removed (R.1b) | C-33 | R1 |
| 2.4 | `/ 100` percent of critical in `structure` | C-33 | R1 |
| 2.5 | `9.81`; the friction dead band; the Newton tolerance, relaxation and pass counts | C-34 | R1 |
| 2.6 | Free-decay threshold `0.01`; the result capacity `out_max * 2` named once | C-34, C-N08 | R1 |
| 2.7 | The legacy `n < 3` limit (the valve-closed threshold and the two friction clamps went with the pressure solver) | C-34 | R1 |
| 2.8 | Derivation comments for the pure-number coefficients: **done in R.1b** for `12`, `0.5 + 1.5 (...)`, `4 / 3`, `out_max * 2` and `4 * celerity * dt` ("Proposed derivation, for Ben to confirm"); the friction `0.5` still needs one (Q-4) | C-35 | R0 |
| 2.9 | Supporting code: conversions and convention values in gated expressions (`cases.py:59-62`, `sweep_jc.py:122-127`, `332`, `383`, `histories.py`) | S-45 | R1 |
| 2.10 | `rho_c == 0` guard to the first statement of the coupling constructor | C-19 | R2 |
| 2.11 | Trace request as one optional object in `_integrate` | C-23 | R2 |
| 2.12 | ~~Small control-flow nits~~: Nits rejected (ruling 8) | C-N03, C-N04, C-N06 | R2 |
| 2.13 | `loads._schedule`: the three identical "next index with column wrap" blocks extracted (integer only) | C-08 | R3 |
| 2.14 | `_schedule` items as two NamedTuples | C-08 | R1 |
| 2.15 | One schedule walk: per-sample helpers shared by `unbalance_force` and `elbow_forces` (`unbalance_force` forms the one subtraction from the pair); the run-time cross-check of the two walks removed | C-07 | R3 |

2.6 needs Q-4 only for its comment, now written; the friction `0.5` of 2.8 still needs it
(2.3 and Q-5 went with the pressure solver). The charter's mutation tests showed that a
regrouped set-up value can hide from a peak, so 2.4 to 2.7 are one literal per commit and the
snapshot runs in both modes each time.

2.13 to 2.15 are the schedule clean-up, moved here from 4.11 / 4.12 (R.2's order change,
ruling 22): control flow in pure Python, gated by the snapshot, and they remove the double
walk before 4.10 splits `_integrate`. K-6 holds throughout: both generators stay lazy and
D-8's `IndexError` surfaces at the first ramp sample.

## Group 3 — parameter objects (R3, R4)

Q-2 is answered (ruling 2): the test-only interfaces are removed first, one per commit,
their tests pointed at the code that actually runs with the assertions unchanged (now group
0). Before 3.1, write `docs/review/parameter_objects.md` (the groups) and stop for the owner.

**Numba rule (from R.2, its constraint K-1).** Unpack a NamedTuple column once per kernel
call, or pass it at most one call deep per substep. On R.2's toy kernel every other pattern
was as fast as the flat signatures, but the column tuple passed on from the per-substep
function into a further call cost 1.46x (60 cells) and 1.16x (300 cells). The kernel-signature
names change here, as fields, under the names `docs/nomenclature.md` proposes (ruling 21).

| # | commit | findings | risk |
|---|---|---|---|
| 3.0a-d | Moved to group 0 (R.3) | | |
| 2.2 | Moved here from group 2 (ruling 40): the coupling kind as a plain bool flag in place of `kind` 0 / 1 in `_integrate_kernel` and `_trace_frame`, with the column object of 3.2 | C-09 | R4 |
| 3.1 | `step_scalars` takes `SdofParams`; the kernel receives it whole | C-10, C-01 | R4 |
| 3.2 | Fluid-column NamedTuple (four state arrays, two weight arrays, counts, `rho_c`, decay factor, divisor, area) built by `JunctionCoupling`; `moc.step` and the kernel take it; a named constructor for the empty column with today's literal types | C-01, C-03, C-04, C-N07, C-N13 | R4 |
| 3.3 | Trace-buffers NamedTuple returned by `trace.allocate`, taken by the kernel and `trace.build` | C-01, C-15, S-08, SP-15 | R4 |
| 3.4 | Run-settings NamedTuple (`dt`, sub-steps per sample, capacity, `output_type`, parity flag) | C-01 | R4 |
| 3.5 | NamedTuple return of the kernel | C-01 | R4 |
| 3.6 | Grid description passed to `trace.build` in place of the coupling object, and its run fields as one object; annotate it | C-14, S-08, SP-15 | R3 |
| 3.7 | Span, restraint and fluid objects for `lumped_params` / `jc_params`; shared return block. **Moved to the public API session (ruling 47)**, which designs the input groups | C-17 | R3 |
| 3.8 | Grid and fluid-constant objects for `JunctionCoupling.__init__` | C-18 | R3 |
| 3.9 | ~~`pressure` column NamedTuple~~: removed (R.1b) | C-16, C-N02 | R3 |
| 3.10 | Entry points: extract the sample grid and the trace wrapper; keyword arguments in the short-pipe fallback. **Moved to the public API session (ruling 47)** | C-11 | R3 |
| 3.11 | One set-up query in the core (sub-step, portal height, grid), used by `response`. **Moved to the supporting-modules session (ruling 48)**, whose tools are its main users | S-06 (core half) | R3 |
| 3.12 | `JunctionCoupling` replaced by `coupling.fluid_column(grid, fluid, vav_denominator, fraction_profile) -> FluidColumn` (ruling 49); done in R.6, `1eeb6d4` | C-03, C-N13 | R3 |

3.1 to 3.5 are the commits the bench matters for. After each: cache wipe, both modes,
snapshot; `tools/bench.py` at the end of the session and a revert of the session's last
commit if the kernel rows move beyond noise. K-1 in the findings records the toy result
that makes this worth trying; it is not evidence for the real kernel.

## Group 4 — the single sub-step (R3, R4)

| # | commit | findings | risk |
|---|---|---|---|
| 4.1 | **Done (R.6).** Compile `effective_displacement`; `step_scalars` calls it for the ladder | C-10 | R4 |
| 4.2 | **Dropped (R.7, ruling 58).** Split `moc.step` into the two half-grid functions; the parity test stays at the callers | C-04, C-N22 | R4 |
| 4.3 | **Dropped (R.7, ruling 58).** Junction-force functions out of the half-grid updates, into the coupling layer | C-05 | R4 |
| 4.4 | **Dropped (R.7, ruling 58).** One compiled column advance (parity, half-grid update, junction force) called by the kernel twice (`coupling_force` is gone, 3.0a) | C-03 | R4 |
| 4.5 | **Done (R.6).** Friction and stick derivation as a compiled function beside `step_scalars` | C-14 | R3 |
| 4.6 | **Absorbed by 4.9 (R.6).** Peak trackers extracted | C-02 | R4 |
| 4.7 | **Done (R.7).** Trace frame: scalar-row writer and column writer; the kernel's recording branch calls one function | C-15, C-02 | R4 |
| 4.8 | **Done (R.7).** `_trace_frame` and its writers moved to `trace.py` | C-14 | R3 |
| 4.9 | **Done (R.6, option 1).** The sub-step body as one function called from the forced loop and the free-decay loop; the `f_applied` forms stay in the loops | C-02 | R4 |
| 4.10 | **Done (R.7).** `_integrate` split into prepare, run, build result | C-06 | R3 |
| 4.11 | Moved to group 2 (2.13 to 2.15, R.3) | C-07, C-08 | |
| 4.12 | **Done (R.7); C-07 stays open.** Flattening of the schedule moved into `loads` (the cross-check went with 2.15) | C-22 | R3 |
| 4.13 | ~~`pressure`: the shared characteristic solve~~: removed (R.1b) | C-N01 | R3 |

Before 4.1, write `docs/review/substep_design.md` (the substep designs) and stop for the
owner.

**The two designs (session R.6; in full, with the loop bodies, in
`docs/review/substep_design.md`).** Common to both: each loop computes its own applied
force, verbatim and never merged, and therefore also advances the column first (the force
needs the junction force the advance returns); the unbalance-force maximum is taken once
over the schedule by `_largest_magnitude` (same comparisons, same order); the free-decay
re-test stays in its loop.

* **A (recommended): one substep function.**
  `_advance_structure(state: _RunState, applied_force, junction_force, sample_index,
  is_in_record_window, inputs: _SubstepInputs) -> _RunState`: the SDOF step, the trace frame
  if one is due (`_trace_frame`, with the frame's phase and elbow forces read from the
  schedule at `substep_index`, which equals the forced loop's `i`), the three maxima, the
  counters. `_RunState` = `x, v, a, x_max, v_max, a_max, substep_index, frame_count`,
  returned (§4); `_SubstepInputs` = `sdof_params, substep_duration, schedule, buffers,
  column`. Each loop body: the unbalance force (forced only), the column advance, the
  applied force, one call. Kernel complexity about 8.
* **B: two short loops sharing per-concern helpers** (4.6 and 4.7 without 4.9).
  `_track_peaks(peaks, x, v, a)` on a three-element array updated in place;
  `_record_frame(recorder, frame_count, key, before, after, junction_force) -> frame_count`.
  Each loop body: force lines, `step_scalars`, `_record_frame`, `_track_peaks`, the counter.
  Kernel complexity about 8; the substep sequence is still written twice, as calls.

Open for the owner: the order (4.9 now, ahead of 4.1 to 4.8, or the plan's order: Q-R6-1)
and step 0 (the kernel starts the junction force at 0.0 itself: Q-R6-2).

`tools/bench.py` runs after every commit of this group, not only at the session end (R.2's
order change): the extracted helpers create exactly the call depth the Numba rule of group
3 warns about, and a session-end bench would not show which commit did it.

4.2 and 4.4 change tests that patch or replay `moc.step` (Q-9). 4.11 can slow the untraced
lumped path, where the Python generator is already the dominant cost: bench it on its own.
4.9 is the commit the review exists for; if it will not stay bit-identical or costs time,
4.6 and 4.7 alone already leave the two loops short enough to compare by eye.

## Group 5 — supporting modules and tools

Gated code first.

| # | commit | findings | risk |
|---|---|---|---|
| 5.1 | Shared non-test module for fixture loaders, tolerances and flag sets; tests and tools import it | S-01, S-N21 | R3 |
| 5.2 | Shared tools module for `git`, `cpu_model`, the text table | S-23 | R3 |
| 5.3 | Frame-column table in `trace.py`; derive counts, `build` mapping, `FRAME_COLUMNS`, the int set | S-05 | R3 |
| 5.4 | Sweep-column table; derive type sets and per-solver names; one raw CSV reader | S-04 | R3 |
| 5.5 | `interleaved_grid` shared by `trace.build` and `lumped_grid`; column-grid object for `loop_layout` | S-07, S-16 | R3 |
| 5.6 | Tools and geometry call the core set-up query of 3.11; portal height on `Trace` (own commit) | S-06, S-35 | R3 |
| 5.7 | Display fraction profile moved into `moc`; exception replaced by a test | S-12 | R3 |
| 5.8 | `export.py`: provenance helper, `meta.params` / `meta.outputs` extracted, `TYPE_CHECKING` import, docstring corrected | S-09, S-26 | R3 |
| 5.9 | `_sweep_value` decomposed | S-27 | R3 |
| 5.10 | `histories.py`: `_history` defaults, noise scaling extracted (the per-kind functions behind `canonical` are not made: S-17 rejected) | S-18 | R3 |
| 5.11 | `tools/cases.py`: spec record for the step case; sweep-document helpers to their own tools module; `reference_block` record | S-10, S-29 | R3 |
| 5.12 | `tools/sweep_jc.py`: grid and pipe properties, row computation and report as three modules behind the same script; `run_case` parts; provenance tuple | S-03, S-15 | R3 |
| 5.13 | Remove the `sys.path` inserts and private loaders the earlier commits made unnecessary | S-02 | R3 |
| 5.14 | Dead code and small items: `estimate_bytes`, unused constants, `build_viewer.build` parameters, `review_snapshot.main` | S-30, S-34, S-N01, S-N12, S-N22 | R0-R3 |
| 5.15 | Ungated tools (`bench.py`, the plots and report of `sweep_jc.py`, `extract_fixtures.py`, `golden_report.py`, `profile_delta.py`): **rename-only edits** (ruling 3, Q-7), made with the renames of group 1; no restructuring | S-13, S-14, S-19 to S-22, S-24, S-25, S-28 | R0 |
| 5.16 | ~~`vba_compat` helpers copied into a live module~~: dropped (ruling 13: `vba_compat.py` stays frozen and imported as it is until Stage 6) | C-13 | |

5.3 and 5.4 are the preparation for the schema bump: with one table per document the bump
is an edit of two tables. 5.12 must keep `tools/sweep_jc.py` a runnable script and the
worker picklable (K-11). 5.16 needs Q-1 and is placed here only because it is independent
of everything else (dropped in R.3). S-11 and S-36 are group 7: they change output on edge inputs (Q-8).

## Group 6 — public API, data format, docstrings, lint limits

| # | commit | findings |
|---|---|---|
| 6.1 | Form of `output_type` and of the three junction-coupling flags; one validation at the entry, as a recorded deviation (ruling 5); both flag paths kept | C-12 |
| 6.2 | Keyword-only entry points; public keyword renames (the `get_pressure_response` alias went with the pressure solver, R.1b) | C-11, C-31, C-N21 |
| 6.3 | `PeakResponse` and `Trace` field renames; `Trace` column sub-record (approved, ruling 7) | C-26, C-43, S-08 |
| 6.4 | Public signatures of `histories.canonical` and `export.to_*_dict` (user-facing entry points, ruling 4: keyword-only, no symbols) | S-33 |
| 6.5 | **The schema bump**, one commit: exported keys and CSV columns renamed through the two tables, viewer keys with them, `tests/review_support/` rewritten with `--write`, values shown unchanged; the committed sweep CSVs (`docs/sweep/*.csv`) get their headers renamed by a one-off script, every data row byte-identical (ruling 12); units stay "SI unless suffixed" (ruling 28) | S-31, S-32, S-37 to S-43, S-46 to S-49, C-25, C-28, C-30, SP-35 (leg heights), SP-36 (`fraction_profile`) |
| 6.6 | Docstrings: numpy sections, units, shapes; VBA references and ids to Notes; first lines in model terms | C-40, C-41, S-49, S-50 |
| 6.7 | Annotations | C-42, S-51 |
| 6.8 | Lint limits in `pyproject.toml` (PLR0913 at 6, C901 at 10, the statement and nesting targets), with a one-line reason on each function that still misses | style 3 |

Before 6.1, write `docs/review/public_interface.md` (the public interface) and stop for the
owner. 6.1 changes error behaviour on bad flag values (Q-3, approved) and needs a
`DEVIATIONS.md` row and a pinning test.

## Group 7 — the approved edge-case fixes (after the refactoring)

Behaviour changes, approved by the owner (ruling 11): each its own commit with a
`DEVIATIONS.md` row and a test that pins the new value; a stored file it changes is
rewritten in that commit only.

| # | commit | findings |
|---|---|---|
| 7.1 | `is_capped` from the kernel's forced-sample count, carried on `Trace` | S-11 |
| 7.2 | `size_in` taken from the caller, not read from the CSV's directory name | S-36 |

## Questions for the owner

* **Q-1.** `NOTES.md` and `CLAUDE.md` say Stage 6 removes `vba_compat.py` with
  `legacy_port.py`; `docs/architecture.md` lets live modules import `clng`, `vba_floor`,
  `mod_dbl` and `vba_2d` from it. Confirm the removal, so that C-13 (literal copies in a
  live module; `_vba_semantics` itself was removed in R.1b) is done in this review and not
  at Stage 6.
  **Answer (R.1b):** open; not answered in R.1b.
  **Answer (R.3):** `vba_compat.py` stays frozen and imported as it is until Stage 6; nothing replaces `_vba_semantics.py` (ruling 13). C-13 is closed and 5.16 dropped.
* **Q-2.** `JunctionCoupling.coupling_force`, the `Coupling` protocol, `structure.step`,
  `State` and `restoring_force` are called only by tests. Keep them as thin wrappers over
  the shared compiled functions, or remove them and re-point the tests?
  **Answer (R.1b):** remove them and re-point the tests at the code that actually runs, assertions unchanged (ruling 2); commits 3.0a to 3.0d.
* **Q-3.** An unknown `vav_denominator` is accepted on a short pipe and when `rho_c == 0`.
  May the public API session validate all flags at the entry, as a recorded deviation?
  **Answer (R.1b):** yes, in the public API session, as a recorded deviation (ruling 5).
* **Q-4.** Derivations the code does not hold: the factor 2 in `out_max * 2`; the `0.5` in
  `0.5 * dynamic_fric * 9.81 * dt`; `4 / 3` on the portal-frame height; `12` and
  `0.5 + 1.5 * (...)` in the end-fixity formula; `4 * celerity * dt` in the grid size.
  **Answer (R.1b):** the owner's proposed derivations of `12`, `0.5 + 1.5 (...)`, `4 / 3`, `out_max * 2` and `4 * celerity * dt` are written at each site as "Proposed derivation, for Ben to confirm:" comments (R.1b); the friction `0.5` is still open.
  **Answer (R.3):** the friction `0.5` is the share of the pipe's weight carried on the moving part (ruling 14); its comment is 0.6.
* **Q-5.** ~~In `60 * 60` (`pressure.py:177`, `179`), which factor is seconds per minute and
  which minutes per hour?~~ Moot: `pressure.py` was removed in R.1b.
  **Answer (R.1b):** moot.
* **Q-6.** Vocabulary for `docs/nomenclature.md`: elbows A / B as inlet / outlet or kept as
  A / B; "node" and "cell" for the two half-grids and one word for an interleaved entry;
  "transit" and "history" for the two forced phases; `sub_step` or `substep`.
  **Answer (R.1b):** the grids stay A and B (`pressure_a`, `velocity_b`); the elbows are A and B; the phases are transit, forced and free decay; `substep` is one word (ruling 1). One word for an interleaved entry of the display grid is not yet ruled.
  **Answer (R.3):** an entry of the interleaved display grid is a "grid point" (ruling 15); elbow A is the one the pressure wave reaches first, the inlet side of the run (ruling 26).
* **Q-7.** The ungated tools (5.15): refactor without a gate, add characterisation checks
  first, or leave them as they are?
  **Answer (R.1b):** rename-only edits (ruling 3); 5.15.
* **Q-8.** Two supporting fixes change output on edge inputs: `is_capped` taken from the
  kernel's count (differs for a stride above `step_qty`), and `size_in` no longer read from
  a directory name (a moved CSV exports a value where it exports null today). Wanted?
  **Answer (R.1b):** both wanted, as recorded behaviour changes after the refactoring (ruling 11); group 7.
* **Q-9.** The charter allows only rename-forced edits in `tests/`. Groups 3 and 4 change
  call sites in tests that call `moc.step` and `jc_params` directly (`pressure.setup` and
  `initial_column` went in R.1b), and the test that patches `moc.step` to record the half-grid
  sequence. Are signature-forced edits covered?
  **Answer (R.1b):** tests may change how they call a function, never what they assert (ruling 6).
* **Q-10.** `Trace` is returned to users. May its column fields move into a sub-record in
  the public API session, or must the flat attributes stay?
  **Answer (R.1b):** yes, in the public API session (ruling 7).
* **Q-11.** The fourteen suspected defects listed at the end of the findings: which, if
  any, should be looked into, and by whom?
  **Answer (R.1b):** open, except no. 2 (the odd-substep junction tap: a "For Ben to review" comment in `moc.step` and DEVIATIONS D-24, R.1b), no. 1 (Q-3) and no. 9 (S-11, group 7); no. 4 went with the pressure solver.
  **Answer (R.3):** the remaining suspected defects are not investigated in this review; the list stays in `findings.md` for the lead author (ruling 20).
