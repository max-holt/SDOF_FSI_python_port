# Clean-code review — findings

Session R.1, 16 Nov 2026. Independent review against `docs/style.md`; no code was changed.
`docs/review/plan.md` orders the fixes.

Session R.1b (23 Nov 2026) removed the pressure solver (`pressure.py`, `_vba_semantics.py`):
findings about it alone have the status **removed**, and the rows that also name other
modules say which part went. Line numbers stay those of the R.1 tree.

**Renames session R.3 (23 Nov 2026).** The status column says "done (R.3)" where a finding
is closed, or what R.3 did and what remains (kernel names with the parameter objects, group 3;
exported and public names at the public API session).

**Constants and control-flow session R.4 (24 Nov 2026).** The status column says "done
(R.4)" or "partly done (R.4)" for plan group 2 (2.1, 2.4 to 2.7, 2.9 to 2.11, 2.13, 2.14; 2.15 made and reverted).

**Parameter-objects session R.5 (24 Nov 2026).** The status column says "done (R.5)" or
"partly done (R.5)" for plan group 3 (3.1 to 3.6, 3.8, with 2.2); the groups are in
`docs/review/parameter_objects.md`.

**Reconciled with the second review in session R.3 (23 Nov 2026; charter ruling 22).** The
independent review was run a second time by mistake (R.2, `docs/review/findings_r2.md`,
`docs/review/plan_r2.md`, ids `SC-`, `SP-`, `N-`). This list stays the governing one: its
findings are already accepted or rejected and the charter cites its ids. From R.2 only what
this list lacked is brought across: five confirmed findings that R.2's cross-reference shows
no R.1 match for, four of them accepted ("Brought across from R.2", below; SP-25 concerns a
tool no test runs and is not brought across); the wrong-documentation fixes, scheduled early
(`plan.md`, "Before group 1"); and the possible defects that are neither here nor in
`DEVIATIONS.md` (nos. 15 to 24 under "Suspected defects"). R.2's order changes and its Numba
rule are in `plan.md`.

**Disposition (owner's rulings, recorded in R.1b; `docs/review/charter.md`, "Rulings").**
Every Design and Readability finding is **accepted**, except one whose proposed fix adds an
abstraction layer that the readability rule forbids (no protocol, base class, enum or
wrapper layer unless it has two real users today): **S-17**, **rejected**. Every Nit is
**rejected**. The notes column records where a ruling narrows an accepted fix (C-03, C-09,
C-10: the test-only interfaces go; the ungated tools: renames only). Of the 140 findings:
90 accepted, 40 rejected (39 Nits and S-17), 10 removed with the pressure solver. Since
R.3: C-13 is closed without a change (ruling 13: `vba_compat` stays imported as it is until
Stage 6), and four findings brought across from R.2 are accepted (144 in all: 93 accepted,
1 closed by ruling, 40 rejected, 10 removed).

## How this list was made

1. **Blind pass.** Six reviewers (architecture, functions, names and documentation; once on
   the solver core, once on the supporting Python) read the code and `docs/style.md` only.
   They did not read `docs/architecture.md`, `NOTES.md`, `docs/port_review.md`,
   `DEVIATIONS.md` or the git history.
2. **Verification.** Each Design and Readability finding went to its own verifier, which
   tried to refute it from the code: 118 findings, 1 refuted and dropped (the pointer to
   another document in the `viz/geometry.py` docstring: the rules are already stated in the
   same file), 117 confirmed. Most came back with corrections; the rows below carry the
   corrected facts, and sub-claims that did not hold were removed. Nits were not verified.
3. **Reconciliation.** `docs/architecture.md` and `DEVIATIONS.md` were read afterwards. A
   recorded constraint is noted in the last column and explained under "Recorded
   constraints"; it explains the code and does not close the finding.

Overlapping findings from different lenses are merged into one row. Line numbers are those
of the tree at the start of this session.

| severity | solver core | supporting Python | total |
|---|---|---|---|
| Design | 14 | 17 | 31 |
| Readability | 31 | 34 | 65 |
| Nit | 22 | 22 | 44 |
| total | 67 | 73 | 140 |

Risk classes are the charter's: R0 rename, R1 named constant, R2 control flow, R3 function
extraction, R4 kernel signature or loop structure. "bump" means the name is in an exported
file or is a public keyword and changes only in the public API session.

## Solver core — Design

| id | file:line | finding | proposed refactoring | sev | risk | status | notes |
|---|---|---|---|---|---|---|---|
| C-01 | `response.py:747-976` | `_integrate_kernel` takes 36 positional parameters and returns a bare 11-tuple; stepping, peak tracking, history recording and trace recording share one 230-line body (about 23 as ruff counts complexity). A reader cannot tell run constants from state, evolving scalars and trace buffers. | Introduce Parameter Object: `SdofParams` whole, a fluid-column tuple, a trace-buffers tuple, a run-settings tuple; a NamedTuple return. | Design | R4 | accepted; done (R.5): `SdofParams` whole (3.1), `FluidColumn` (3.2), `RunSettings` (3.4), `_ForceSchedule`, `TraceBuffers` (3.3), `_KernelResult` return (3.5); 36 -> 7 arguments. The kernel keeps 7: the junction force is an evolving scalar (passed in and returned, `docs/style.md` §4) and the response history an output array filled in place; folding either into a parameter tuple would group by type, not by meaning (see "Parameter objects, R.5" below). The shared 230-line body is group 4 | K-1 |
| C-02 | `response.py:827-895`, `904-974` | The forced and free-decay sub-step bodies are the same 57 lines written twice. The real differences (the `f_applied` form, the `f_max` tracker, the trace phase and forces, `tot_ind <= out_max * 2`, the `x_zero` reset, the parity offset) are found only by diffing. | Extract Function: column advance returning `d_f`, peak trackers, trace-frame writer. The four `f_applied` forms stay at the call sites (`d_f + 0.0` is not `d_f` for `-0.0`). | Design | R4 | accepted; **done (R.6, plan 4.9, option 1 of `substep_design.md`)**: both loops call `_structure_substep(state, applied_force, sdof_params, dt)` (step, maxima, count); the applied-force forms, the column advance and the trace write stay in the loops; the unbalance maximum once per run (`_largest_magnitude`); `_parity_offset`, `_is_frame_due`, `_decay_reference`. A first form that also took the schedule, buffers and column (`6ea80ba`) was 1.1-2.0x slower and reverted | K-1, K-5 |
| C-03 | `coupling.py:165-198`; `response.py:832-854`, `911-933`, `664-673`, `704-705` | The 15-argument `moc.step` call is written three times. `JunctionCoupling.coupling_force` and the `Coupling` protocol are called by tests only; the solver reads the object's slots, runs its own copy behind `kind == 1`, and writes `d_f` back. `NoCoupling` is seven placeholder values. | One compiled column-advance function that the kernel and `coupling_force` both call; the fluid-column tuple of C-01 built by the coupling object. | Design | R4 | accepted; partly done (R.5): the 15-argument `moc.step` call is `moc.step(parity, a * dt, column, junction_force)` in both loops; the one compiled column advance (4.4) is **dropped (R.7, ruling 58)**: the kernel calls `moc.step` directly in both loops | K-1, K-2, Q-2; accepted without `coupling_force`: the readability ruling removes it and the `Coupling` protocol; the column advance is called by the kernel's two loops |
| C-04 | `moc.py:400-515` | `step` takes 15 parameters and a boolean `even` that selects one of two bodies sharing only `two_rho_c`; `decay` and `vav_div` are unused in the odd body. `pressure.py` had the split as two named functions (removed in R.1b). | Replace Flag Argument with Explicit Functions (one per half-grid); column and fluid-constant parameter objects. The parity test moves to the callers unchanged. | Design | R4 | accepted; partly done (R.5): `moc.step` takes the `FluidColumn` (15 -> 4); **closed (R.7, ruling 58)**: the split (4.2) is dropped; `moc.step` keeps its flag as a recorded exception (`docs/style.md` §11): splitting it either adds branches to the kernel loops or passes the column two calls deep per substep | K-1, K-3; tests patch `moc.step` |
| C-05 | `moc.py:493-499`, `514` | The MoC step also computes the low-pass-filtered force on the structure, which `coupling.py:1` names as its own subject. The force reads only the updated pressures; nothing in the column update reads `d_f`. | Extract Function: two junction-force functions (the expressions differ), owned by the coupling layer, with `DAMPING_A`. | Design | R4 | accepted; **closed (R.7, ruling 58)** without the change: the junction force stays inside `moc.step`; separate per-substep functions would pass the column two calls deep per substep or add kernel branches (`docs/style.md` §4, §11) | K-1 |
| C-06 | `response.py:600-743` | `_integrate` contains no integration: it flattens the forces, allocates, sets up the trace, unpacks the coupling by `KIND` (tested four times), calls the kernel, writes back, validates and builds the result. The no-coupling placeholder `(0, 0, 0.0, 1.0, 1, 0.0, 0.0)` can be read only by position. | Split Phase: prepare kernel inputs, run, build result. The placeholder becomes a named constructor that keeps the literal types. | Design | R3 | accepted; **done (R.7, plan 4.10)**: `_integrate` is `_kernel_inputs`, the kernel, `_peak_response`; the placeholder became `moc.empty_column()` in R.5 |  |
| C-07 | `loads.py:233-310`, `313-374`; `response.py:646-648` | `unbalance_force` and `elbow_forces` are one function written twice (identical 9-line set-up, the same interpolations). A traced run walks the schedule twice and compares the two walks' sample lengths with an `AssertionError`. | Extract Function: per-sample helpers returning `(force_a, force_b)`; `unbalance_force` forms the one subtraction from the pair. Keep both generators lazy. | Design | R3 | accepted; open: made in R.4 (plan 2.15) and reverted by the owner: bit-identical, but the untraced lumped run then builds both elbow-force lists and subtracts them, about 20 % slower on the compiled lumped path (golden r20, 0.177 s to 0.213 s). The run-time cross-check stays with the two walks; still open after R.7: plan 4.12 moved the flattening into `loads` but kept the two walks, the only form shown exact and no slower (the one-walk form of R.4 cost about 20 % on the compiled lumped path); the cross-check now compares the two sample-start arrays; open by decision (R.8, ruling 63) | K-5, K-6 |
| C-08 | `loads.py:145-230` | `_schedule` yields tuples of two shapes behind a 0 / 1 tag, documented only in prose; the "next index with column wrap" block is written three times (200-205, 206-211, 224-229). | Two NamedTuples for the items; Extract Function for the three identical blocks only (177-182 and 219-223 differ in text and stay). | Design | R3 | accepted; done (R.4): `_next_position` for the four identical blocks (the advance block is the same rule), `_wraps_to_next_column` for the transit block, two NamedTuples | K-6 |
| C-09 | `loads.py:183`, `230`, `286`, `352`, `362`, `374`; `response.py:590`, `656`, `832`, `876`, `911`, `955`; `trace.py:72-74` | The load phase is a bare 0 / 1 in `loads`, `PHASE_*` in `trace`, and re-derived in the kernel from `delay_substeps`. The coupling kind is `JunctionCoupling.KIND` in `_integrate` and the literal `1` in compiled code. | Replace Magic Literal with Named Constant: one phase pair and one kind pair, module-level ints, defined where `loads` can import them without importing `structure`. | Design | R1 | accepted; done (R.4, R.5): the phase pair (2.1); the coupling kind is `FluidColumn.is_fluid_coupled`, a plain flag (2.2, R.5) | phase pair accepted; the coupling kind becomes a plain flag (readability ruling), not a constant pair |
| C-10 | `structure.py:343-360`, `468-483`, `388-441` | The gap restraint ladder is written twice (16 lines). `step_scalars` takes 11 loose scalars, six of them `SdofParams` field by field. `step`, `State` and `restoring_force` have test callers only. | `step_scalars` calls a compiled `effective_displacement`; it takes `SdofParams` positionally. Compiling `effective_displacement` is its own commit. | Design | R4 | accepted; partly done (R.5): `step_scalars` takes `SdofParams` (3.1); compiling `effective_displacement` for the ladder: **done (R.6, plan 4.1)** | K-1, K-5, Q-2; `step`, `State`, `restoring_force` removed (readability ruling); their tests point at `step_scalars` / `effective_displacement`, assertions unchanged |
| C-11 | `response.py:241-253` / `396-410`, `270-291` / `466-492`, `431-448` | The two entry points repeat coercion, the sample grid and the trace echo; the short-pipe fallback re-passes 14 positional arguments and repeats the set-up, the portal-height solve included. | Extract Function for the trace wrapper and the sample grid; keyword arguments in the fallback call. Each `inputs` dict literal stays (its key order reaches exported bytes). No reordering of the set-up. | Design | R3 | accepted; R.9 done (plan 3.10: `_sample_grid`, `_trace_request`, keyword fallback) | K-4, K-7 |
| C-12 | `response.py:174`, `323-325`, `390-395`, `501`, `536-545`, `637`, `739`, `894`, `973`; `moc.py:328`, `392-396` | `output_type` reaches a compiled helper as a raw code and decides what `PeakResponse.history` means. The three string flags are validated in three places (`fraction_profile` twice, `vav_denominator` only after the short-pipe return). | Reported only: the form belongs to the public API session. A single entry check is a behaviour change on error paths (Q-3). | Design | R4 | accepted; R.9 done (plan 6.1: `CouplingModel`, D-25; `output_type` removed, plan 6.2) | bump; D-17, D-19; flags validated once at the entry in the public API session, as a recorded deviation (ruling) |
| C-13 | `moc.py:58`, `loads.py:37`, `response.py:97`, `pressure.py:45`; `_vba_semantics.py:3-5` | VBA rounding has two homes: every live module imports `clng`, `vba_floor`, `mod_dbl` or `vba_2d` from the frozen `vba_compat`, while `vba_min` / `vba_max` live in `_vba_semantics`. | Move Function: literal copies into `_vba_semantics` with a test pinning them to `vba_compat`; repoint 11 call sites. | Design | R3 | closed (ruling 13) | K-8, Q-1; the `_vba_semantics` and `pressure.py` parts removed (R.1b); **closed without a change (R.3, ruling 13)**: `vba_compat.py` stays frozen and imported as it is until Stage 6; nothing replaces `_vba_semantics.py` |
| C-14 | `response.py:79-96`, `548-597`, `874-875`, `953-954`; `trace.py:268-290`, `306`, `355` | The frame writer lives in `response`, its column layout and cell order in `trace`. The kernel rebuilds the friction force and the stick flag from values `step_scalars` computes and drops. `trace.build` takes the coupling object untyped. | Move Function `_trace_frame` to `trace.py`; Extract Function for the friction and stick derivation next to `step_scalars`, verbatim; pass `build` a grid description. | Design | R3 | accepted; partly done (R.5): `trace.build_trace` takes the typed `FluidColumn` in place of the coupling object (3.6); the friction / stick derivation: **done (R.6, plan 4.5, `structure.substep_friction`)**; moving `_trace_frame` to `trace.py` is 4.8; **done (R.7, plan 4.8)**: the writers live in `trace.py` (`FrameRow`, `write_frame_row`, `write_frame_column`) | K-9; makes `trace.py` a Numba module |

## Solver core — Readability

| id | file:line | finding | proposed refactoring | sev | risk | status | notes |
|---|---|---|---|---|---|---|---|
| C-15 | `response.py:549-597` | `_trace_frame` takes 23 parameters; eight are used only under `if kind == 1`. Both call sites are 25-line argument lists. | Split into a scalar-row writer and a column writer; trace-buffers and column tuples. | Readability | R4 | accepted; partly done (R.5): `_trace_frame(buffers, frame_index, values, column)`, 23 -> 4 (`TraceBuffers`, `_Frame`); the split into a scalar-row and a column writer is 4.7; **done (R.7, plan 4.7)**: `trace.write_frame_row` and `trace.write_frame_column`; each loop's recording branch is one `_record_frame` call | K-1 |
| C-16 | `pressure.py:129-141`, `196-225`, `283`, `315`, `347-356`, `388`, `515-541` | `p_a, v_a, p_b, v_b` travel as a clump through five functions; `pump_boundary` takes 8 parameters, never uses `p_a`, and takes two bar-valued run constants beside the `PressureSetup` made for run constants; the alias is unannotated. | Column NamedTuple; carry the run constants on `PressureSetup`. The three 11-parameter signatures are public (bump). | Readability | R3 | removed | K-10; tests call `setup`, `initial_column`; pressure solver removed (R.1b) |
| C-17 | `structure.py:165-175`, `226-238`, `215-222`, `306-313` | `lumped_params` (9) and `jc_params` (11) take span, fluid and restraint as loose scalars and end in the same 8-line return; six positional call sites. | Parameter objects for span, restraint, fluid; Extract Function for the return block (`float(restrain_freq_ratio) ** 2` verbatim). The two mass expressions are not merged. | Readability | R3 | accepted; R.9 done (plan 3.7: `PipeSpan` / `Restraint` / `Fluid`, `_sdof_params`) |  |
| C-18 | `coupling.py:143-153` | `JunctionCoupling.__init__` takes 8 parameters, mixing grid size, fluid constants and two string flags. | Parameter objects for grid and fluid constants; the two flag keywords and defaults stay (tests pin them). | Readability | R3 | accepted; done (R.5): `JunctionCoupling(grid, substep_duration, fluid, vav_denominator, fraction_profile)` with `moc.ColumnGrid` and `coupling.FluidConstants` (8 -> 5) |  |
| C-19 | `moc.py:463-465`; `response.py:449-454`; `coupling.py:154-163` | `moc.step` divides by `2 * rho_c`; the zero check is two modules up, and `JunctionCoupling(rho_c=0)` builds without complaint. Lower modules name their callers in docstrings. | Move the guard to the first statement of the coupling constructor (before `interp_fractions`, so error order is unchanged); stop naming callers. | Readability | R2 | accepted; partly done (R.4): the guard is the constructor's first statement (2.10); "stop naming callers" is docstring work, 6.6 | D-9 |
| C-20 | `pressure.py:43`, `480`; `loads.py:48-74` | `pressure` imports the force-schedule module for one array helper; a bad valve pattern is reported as a "force history". | Move Function `as_history_2d` to a neutral module; the message text stays. | Readability | R3 | removed | its only cross-module user, `pressure`, removed (R.1b) |
| C-21 | `moc.py:89`, `364-369`; `pressure.py:105`, `215-218` | Two functions named `grid_size` with different arguments and returns; `p_b`, `v_b` have N elements in `moc` and N + 1 in `pressure` under the same names. | Rename the `pressure` side (one call site). | Readability | R0 | removed | D-22: both grids use cells of `2 c dt`; the `pressure` side removed (R.1b); one `grid_size` remains |
| C-22 | `response.py:250`, `269`, `290`, `630-636`, `646-655`; `loads.py:133` | The force history passes through four representations (2-D array, 1-based nested lists, per-sample lists, flat array with offsets), converted partly in `loads` and partly in `response`; `as_history_2d` runs two to four times a run. | Move the flattening next to the schedule in `loads`, built where `list(forces)` runs today. | Readability | R3 | accepted; **done (R.7, plan 4.12)**: the flattening lives in `loads` (`flatten_unbalance_force`, `flatten_elbow_forces`), consuming the generators where `list()` ran; exact on 6000 random histories, D-7 / D-8 included; compiled lumped path 2-8 % faster | K-6 |
| C-23 | `response.py:515-521`, `609-610`, `643-645` | `trace_every` and `meta` are parallel optionals; the `TypeError` that guards them cannot be reached; `_TraceMeta.elbows` is typed `object`. | One optional trace-request tuple carrying the stride; the kernel still receives an int. | Readability | R2 | accepted; done (R.4): one optional `_TraceRequest` with the stride; the typing of `elbow_force_samples` waits for 6.7 |  |
| C-24 | `docs/style.md:14`, `19` | `docs/nomenclature.md`, on which the style guide's symbol rule and its VBA mapping rest, does not exist. No kernel symbol is licensed today. | Write it before any rename: symbol, meaning, unit, VBA name. | Readability | R0 | done (R.3: docs/nomenclature.md, approved) | prerequisite of C-25 to C-45 |
| C-25 | `loads.py:160`, `291`, `355-356`; `moc.py:80`, `338`, `403-408`; `response.py:80`, `561-562`, `580-581` | The suffix `_a` / `_b` means elbow A / B, the two staggered half-grids, and (as `F_A`) acceleration; `fa`, `fb` are force lists in one module and functions in another. | Rename the internal names; the grid arrays and `flat_a/b` are kernel symbols (list them or rename with C-01); `f_a`, `f_b` are exported. | Readability | R0 | accepted; R.3: elbow names done; R.5: kernel grid arrays done; f_a / f_b at the bump; R.9 done (plan 6.5, the schema bump) | bump for `f_a`, `f_b`; Q-6 |
| C-26 | `response.py:118-119`, `827`, `892-893`; `structure.py:400-402` | `max_applied_force` is the peak of the unbalance force in the forced phases; `f_applied` is unbalance plus junction force. The same unbalance force is also `f`, `f_u`, `forces`, `flat`. | Rename the internal names to one word; `max_applied_force` is public, exported and a fixture column. | Readability | R0 | accepted; R.3: unbalance-force names outside the kernel done; f_applied (applied_force) group 3, max_applied_force at the bump; R.9: `PeakResponse.max_unbalance_force` done; exported key at the bump; R.9: the exported key at the bump done (plan 6.5) | bump |
| C-27 | `loads.py:99-141`, `277`, `293`; `response.py:251`, `408`, `642`, `656` | The transit delay is `transit_delay`, `unballance_step_qty`, `unb`, `unb_steps`; `delay_substeps` looks like `unb_steps` and is a different number (an int count against a float threshold). | Rename to the style guide's own example and a distinct count name. | Readability | R0 | done (R.3) |  |
| C-28 | `moc.py:112-113`, `409-410`; `coupling.py:127-128`; `response.py:641`, `649`, `813`; `pressure.py:72-101`, `214` | Counts are `_qty`, `n_`, bare plurals or prose `N`; the same count changes name at each call boundary (`pipe_seg_qty` to `n_seg`, `pivot_seg_qty` to `pivot`); "cell", "half-cell" and "segment" are mixed. | Rename to `_count`; one word per grid concept. `step_qty`, `free_decay_samples` are public; `n_cells`, `n_frames`, the `_seg_qty` columns are exported. | Readability | R0 | accepted; R.3: internal counts done; R.5: kernel parameters done; exported keys at the bump; R.9 done (plan 6.5, the schema bump) | bump for those; Q-6; `pressure` part removed (R.1b) |
| C-29 | `loads.py:161-184`; `response.py:252`, `637`, `812-823`, `906`, `973`; `pressure.py:67`, `173`, `229`, `498` | `tot_ind` is a 1-based running sample number in `loads` and `response` and a 0-based iteration in `pressure`; `out_max` is two different counts; the factor 2 in `out_max * 2` is explained nowhere. | Rename the internal uses; a why-comment for the factor 2 once the owner states it. | Readability | R0 | accepted; R.3: tot_ind in loads, out_max outside the kernel done; kernel group 3 | `out_max` exported; Q-4; `pressure` part removed (R.1b); derivation comment for `out_max * 2` added in R.1b |
| C-30 | `structure.py:70-86`, `214`, `298`, `364`, `437-439`; `response.py:682-684`, `753-755` | `fric_acc` reads as an acceleration and is a velocity step per sub-step; `ratio2` says how it was computed. Both are the style guide's own counter-examples. | Rename Field (`friction_velocity_step`, `closed_gap_stiffness_ratio`); the exported keys stay until the bump, through the snapshot adapter. | Readability | R0 | done (R.3: fields; exported keys at the bump); R.9 done (plan 6.5, the schema bump) | bump for the keys |
| C-31 | `structure.py:230-231`; `moc.py:100`, `414`; `loads.py:85`; `pressure.py:134-138`, `151`; `response.py:255`, `412` | `fluid_densty` against `density`; `fluid_area` (m²) against `pipe_area` (mm²); `dt` against `time_step`; `celerity` described three ways; `h` for the portal-frame height. | Rename the internal parameters and locals; one celerity description. | Readability | R0 | done (R.3: internal; public keywords at the bump) | bump for the public keywords; `pressure` part removed (R.1b) |
| C-32 | `pressure.py:136-139`, `353-354`, `425-430` | Bar, m³/h, mm² and US gpm quantities carry no unit in their names; `setup` and `pump_boundary` mix bar and Pa in one expression. | Unit suffixes. All five are public keywords and fixture keys; only `pump_boundary` can change before the bump. | Readability | R0 | removed | bump; pressure solver removed (R.1b) |
| C-33 | `pressure.py:177`, `179`, `182`, `378`; `structure.py:213`, `296` | Unit conversions are bare literals: `1000000`, `60 * 60`, `100000`, `0.865`, `/ 100`; `1000` in `density / 1000` is a reference density. | Replace Magic Literal with Named Constant, in place, same literal type, never folded. | Readability | R1 | accepted; done (R.4): `PERCENT` (the `pressure` part went in R.1b) | Q-5; `pressure` part removed (R.1b): `structure.py:213`, `296` remain |
| C-34 | `structure.py:114`, `116`, `118`, `155`, `214`, `301`, `492`, `494`; `response.py:900`, `971`; `pressure.py:303`, `337`, `410`; `moc.py:212` | `9.81`, the friction dead band and the Newton tolerance (both `0.000001`), `0.25`, `100 + 1`, `10 + 1`, the free-decay threshold `0.01` (m²), `0.999999999`, `0.9`, `n < 3`. | Named constants with meaning, unit and source; forms such as `NAME + 1` and `NAME * rho_c` kept. | Readability | R1 | accepted; done (R.4): one constant per literal (`GRAVITY`, `FRICTION_DEAD_ZONE`, `NEWTON_*`, `END_FIXITY_LAST_PASS`, `FREE_DECAY_THRESHOLD`, `LEGACY_B_INACTIVE_START_CELL_COUNT`) | D-4, D-6, D-20, D-21 give sources; `pressure` part removed (R.1b) |
| C-35 | `structure.py:131-132`, `153-157`, `211`, `214`, `299`; `moc.py:113` | `4 / 3`, `12`, `0.5 + 1.5 * (...)`, the friction `0.5` and `4 * celerity * dt` have no derivation anywhere in the code. | A derivation comment at each site; the coefficient stays inline. | Readability | R0 | accepted; R.3: every derivation comment written (friction 0.5 added) | Q-4; derivation comments added in R.1b for `12`, `0.5 + 1.5 (...)`, `4 / 3`, `4 * celerity * dt`; the friction `0.5` answered in R.3 (ruling 14: the share of the pipe's weight carried on the moving part), its comment is `plan.md` 0.6 |
| C-36 | `response.py:550-553`, `748`, `780-783`, `810-828`, `905`; `moc.py:401` | Kernel locals are type-coded or single letters at function scope: `tr_f`, `tr_i`, `flat`, `n` (155 lines), `off`, `rec`, `cap`, `i`; booleans `rec`, `stick`, `legacy_parity`, `even` are not predicates. | Rename, together with the parameter objects of C-01 so each name changes once. | Readability | R0 | accepted; done (R.5): applied as parameter-object fields and kernel locals (ruling 21); `forced_samples` stays until group 4 (ruling 33) |  |
| C-37 | `loads.py:121-129`, `157-229`, `284-306` | The index walk keeps `fh`, `u1`, `u2`, `ib`, `jb`, `ibmax`, `jbmax`, `fb2_cur`; each needs its trailing comment or the VBA. | Rename; `_Run` is built positionally, so field order stays. | Readability | R0 | done (R.3) |  |
| C-38 | `structure.py:90`, `114-121`, `151`, `343`, `468`, `486` | `var_a..c`, `len_val`, `error_val`; `ax` is `abs(x)` while `av` is the trapezoidal velocity increment. | Rename (five of them inside the compiled `step_scalars`). | Readability | R0 | done (R.3) |  |
| C-39 | `pressure.py:73`, `175`, `337-340`, `410-413` | `sys0` / `sys1` hide the two characteristics; `loss` is a velocity here, a pressure per half-cell in `pipe_loss` and a coefficient in `valve_loss`; `factor`. | Rename; the test's name map against the legacy locals follows. | Readability | R0 | removed | pressure solver removed (R.1b) |
| C-40 | all seven modules; e.g. `moc.py:20-42`, `92`, `119`, `136`; `structure.py:389`; `response.py:4-33` | First lines are VBA identifiers; `# VBA line N` comments repeat the docstring; stage, session and fix labels stand where the physics should. The `moc` module docstring never says why the mean velocity is subtracted. | VBA references and ids to Notes; first lines in model terms. Why-comments and the comments that record VBA operand order are kept. | Readability | R0 | accepted; done (R.10, plan 6.6: first lines in model terms, VBA names, line references and ids in Notes, in every module; the module docstrings of `response` and `trace` in R.9) | `pressure` and `_vba_semantics` removed (R.1b): five modules remain |
| C-41 | `response.py:574-577`, `612-628`, `785-802`; `loads.py:132`, `146-156` | The internals with the most arguments have prose-only docstrings: no units, shapes or dtypes for 36 and 23 parameters; `_run` has none. | Numpy sections, after the signatures have settled. | Readability | R0 | accepted; done (R.10, plan 6.6: numpy sections with units, shapes and dtypes for the `response` internals, `_integrate`, `_kernel_inputs`, `_integrate_kernel` among them, and the `loads` walk helpers) |  |
| C-42 | `loads.py:48`, `132`, `145`; `response.py:162`, `306`, `507`, `521`, `601`, `784`; `pressure.py:196`, `283`, `315`, `348-351`, `388`, `515-527` | Missing parameter or return annotations. | Add them. | Readability | R0 | accepted; done (R.10, plan 6.7: `loads`, `response`; `force_history` is `ArrayLike`, the substep samples `Iterable[list[float]]`) | `pressure` part removed (R.1b) |
| C-43 | `response.py:120`, `139`, `250`, `637`; `moc.py:158`, `190`, `341-342`, `412`; `loads.py:128` | `history` is the input force history and the output response history; `decay` is a boundary factor and a phase; `frac` is three different weights. | Rename the internal names; reword the two profile glosses. | Readability | R0 | accepted; R.3: history, decay, frac done outside the kernel; PeakResponse.history at the bump; R.9 done (plan 6.2 / 6.3: the three histories, `force_history`) | bump for `PeakResponse.history`; `pressure` part removed (R.1b) |
| C-44 | `loads.py:9-12`, `159`, `197`, `331-332`; `response.py:93-94`, `821`, `898` | The two forced phases are "delay / ramp" in `loads` and "transit / history" in `response`, with a sentence translating between them. | One pair everywhere. | Readability | R0 | done (R.3) | Q-6 |
| C-45 | `moc.py:80`, `372`, `402`, `413-415`; `coupling.py:4`, `79`, `110` | `d_f` is described three ways; `DAMPING_A` is a filter weight, not damping; "divisor" and "denominator" for one number. | Rename the internal names. | Readability | R0 | accepted; R.3: DAMPING_A, vav_divisor done; d_f / vav_div group 3, keys at the bump | bump for `d_f`, `vav_denominator` |

## Solver core — Nits

| id | file:line | finding | proposed refactoring | risk | status |
|---|---|---|---|---|---|
| C-N01 | `pressure.py:339-343`, `412-416` | The characteristic solve is the same four statements in both half-steps. | Extract Function for those four only. | R3 | removed (R.1b) |
| C-N02 | `pressure.py:348` | `pump_boundary` accepts `p_a` and never reads it. | Remove Parameter (with C-16). | R3 | removed (R.1b) |
| C-N03 | `pressure.py:262-279` | `valve_closure` does index pair and interpolation in one nested body. | Extract Function for 257-270; no reordering. | R2 | removed (R.1b) |
| C-N04 | `loads.py:157` | `_schedule` unpacks nine `_Run` fields and discards three. | Attribute access. | R3 | rejected |
| C-N05 | `response.py:894`, `973`, `540-545` | `output_type > 0` is tested before `_record`, which is a no-op for 0. | Reported only (flag form). | R2 | rejected |
| C-N06 | `response.py:629`, `686-697` | `_integrate` re-coerces values its callers coerced. | Coerce at one level. | R3 | rejected |
| C-N07 | `moc.py:350-369`; `pressure.py:225` | Columns are returned as bare 4- and 5-tuples. (`pressure` part removed, R.1b) | Resolved by the column tuples. | R3 | rejected |
| C-N08 | `response.py:637`, `906`, `973` | `out_max * 2` is spelled three times. | Pass the capacity. | R1 | rejected |
| C-N09 | `response.py:75`, `78` | `structure` imported as a module and `step_scalars` by name. | One convention. | R0 | rejected |
| C-N10 | `moc.py:60-75`; `structure.py:37-49`; `pressure.py:47-59` | `__all__` lists every helper beside the entry points. (`pressure` part removed, R.1b) | Trim in the public API session. | R0 | rejected |
| C-N11 | `pressure.py:515-541` | `get_pressure_response` is a second public name. | Reported only (bump). | R0 | removed (R.1b) |
| C-N12 | `response.py:102-146`; `pressure.py:62-101` | Fields are documented twice, in `Attributes` and in field strings. (`pressure` part removed, R.1b) | Keep `Attributes`. | R0 | rejected |
| C-N13 | `coupling.py:135`, `158`, `200-204` | `JunctionCoupling.column()` has no caller; `.dt` is a second source of `dt`. | Remove with C-03. | R0 | rejected |
| C-N14 | `response.py:524-531`, `707-708` | The overflow contract has two mechanisms. | Document as one rule. | R3 | rejected |
| C-N15 | `structure.py:165`, `226`; `response.py:665`, `729` | `jc` abbreviation and `_params` suffix. | Rename. | R0 | rejected |
| C-N16 | `response.py:507` | `trace_every` is called a stride by its validator. | One word (bump). | R0 | rejected |
| C-N17 | `loads.py:99`; `response.py:91`, `642` | "sub-step" is `substep` and `sub_step`. | One spelling. | R0 | rejected |
| C-N18 | `pressure.py:177`, `181`, `499-509`; `response.py:814` | Comments that restate the line below. (`pressure` part removed, R.1b) | Delete. | R0 | rejected |
| C-N19 | `_vba_semantics.py:16-17`; `loads.py:178-229` | The docstring says the solvers write `min(...)`; `loads` uses the builtin `min` where `pressure` uses `vba_min`. | Correct the sentence; state the difference. | R0 | removed (`_vba_semantics` removed, R.1b) |
| C-N20 | `response.py:354`; `moc.py:229`, `265` | Two different source files are cited for the fixed profile. | One reference, in Notes. | R0 | rejected |
| C-N21 | `response.py:166-172`, `310-318` | `flexural_rigidity_ei`, `mass_per_unit_len`, `nat_freq`, `dynamic_fric`, `restrain_freq_ratio`. | Reported only (bump). | R0 | rejected |
| C-N22 | `moc.py:400`; `structure.py:388`, `429` | `step` in two modules for different things. | Rename with C-04. | R0 | rejected |

## Supporting Python — Design

| id | file:line | finding | proposed refactoring | sev | risk | status | notes |
|---|---|---|---|---|---|---|---|
| S-01 | `tools/cases.py:28-30`; `tools/bench.py:100-102`; `tools/profile_delta.py:41-45`; `tools/review_snapshot.py:24-26`; `tools/review_support.py:29-31` | Five tools put `tests/` on `sys.path` and import pytest modules for fixture loaders, tolerances and case tables; the `rtol` values in exported files come from a test file. `golden_report` and `sweep_jc` read the same fixtures with their own paths. | Extract Module: loaders, tolerances and the shared flag sets in one non-test module imported by tests and tools. | Design | R3 | accepted; done for the gated code (R.8, plan 5.1): `tools/fixture_cases.py` holds the loaders, tolerances, the golden cache directory and the two flag sets; `tests/test_golden.py` re-exports them; the ungated `bench.py`, `golden_report.py` and `profile_delta.py` keep their own copies (ruling 24); `review_ab.py` and `test_review_snapshot.py` keep a literal `LEGACY_FLAGS` (older revisions; charter rule 5) | multiplier order and dict key order move verbatim |
| S-02 | `tools/export.py:35-37`; `tools/sweep_jc.py:45-48`; `tests/test_export.py:33-45`; `tests/test_review_support.py:54-69`, `182-189`; `tests/test_sweep_jc.py:16-20` | `tools/` is glued by nine `sys.path` inserts and three private loaders; `tools/export.py` shadows the package's `export`. | Move the importable parts into the package or one shared module; keep `tools/x.py` as thin scripts. | Design | R3 | accepted; done (R.8, plan 5.13): pytest `pythonpath = ["tools"]`; the inserts of `tools/export.py`, `test_export.py`, `test_review_support.py`, `test_viewer.py` and the loader of `test_sweep_jc.py` removed; kept with a reason: `review_snapshot.py` / `review_support.py` (they import test modules), `sweep_jc.py`'s `src` insert, the ungated tools, the `_load_tool` loaders (they keep tools out of `sys.modules`) | K-11 |
| S-03 | `tools/sweep_jc.py:52-155`, `161-238`, `244-401`, `407-503`, `509-1069`, `1075-1137` | One 1137-line file holds the pipe table, the case grid, the row computation, the run, 560 lines of plots and report, and the CLI. The plot half uses only `read_csv` from the rest. `run(args)` and `plot(args)` take the argparse namespace. | Extract Module (grid and pipe properties; row computation; report), then Split Phase on `run` and `plot`. | Design | R3 | accepted; done (R.8, plan 5.12): `sweep_grid.py`, `sweep_rows.py`, `sweep_report.py` behind `sweep_jc.py`; the report moved verbatim (ungated; its output byte-identical before and after); `run(args)` / `plot(args)` still take the namespace | K-11; the report half has no gate (Q-7); the report half is ungated: rename-only edits there (ruling) |
| S-04 | `export.py:75-156`, `405-433`; `tools/sweep_jc.py:244-261`, `285-292`, `388-396`, `524-542`; `tools/cases.py:179-180`, `265-282`; `tools/profile_delta.py:184-214` | The sweep schema is in five places: the 72 names in the package, 18 of them filled through f-strings in a tool, column types decided four times, CSV cells coerced twice, three CSV readers. | One column table (name, type, unit, per-solver stem) from which the type sets and names derive; one raw reader with typing as a separate step. | Design | R3 | accepted; done (R.8, plan 5.4): `export._SWEEP_COLUMN_TABLE` (name, type; `{solver}` names), the names and type sets derived; one raw reader `export.read_csv`; no unit column (units are in the names until the bump) | order of the 72 names is pinned; prerequisite of the bump |
| S-05 | `trace.py:77-81`, `143-155`, `330-351`; `export.py:58-72`, `158`; `viewer.src.html:289-290` | The frame columns are listed six times (kernel indices and counts, dataclass, `build`, export tuple, int set, viewer) with nothing tying them together. | One table in `trace.py` in document order; keep the literal `F_X, ... = range(8)` line and derive the counts, the `build` mapping, `FRAME_COLUMNS` and the int set. | Design | R3 | accepted; done (R.8, plan 5.3): `trace.FRAME_COLUMN_TABLE`; `FRAME_COLUMNS`, `INT_FRAME_COLUMNS`, the counts and `build_trace` derive from it | `t` is derived, `stick` transforms |
| S-06 | `viz/geometry.py:239-247`, `276-281`; `tools/export.py:51-56`; `tools/bench.py:162-176`; `tools/sweep_jc.py:327-331`; `tools/cases.py:91-94` | The solver's set-up (sub-step, portal height, grid size) is retyped in three tools and in the geometry; the forced sub-step count has three names and two formulas. `Trace` carries no portal height, so the layout solves for it again. | Extract Function in the core: one set-up query (expressions moved out of `response` verbatim); add the height to `Trace` in its own commit. The sub-step count stays a tools helper. | Design | R3 | accepted; done (R.8, plan 3.11 and 5.6): `response.solver_setup` / `column_grid`, called by both entry points, `tools/export.py`, `sweep_rows.run_case` and the geometry; `Trace.portal_frame_height` | no closed form exists in the core |
| S-07 | `trace.py:76-86`, `89-169`, `172-265`, `353-366`; `viz/geometry.py:237`, `249-254` | `trace.py` holds the kernel's array layout, the result type and the display grid; the interleaved grid is assembled twice from the same four expressions. | Extract Function `interleaved_grid` in `trace.py`, called by both; the module split is a later, separate commit. | Design | R3 | accepted; done (R.8, plan 5.5): `trace.interleaved_grid` called by `build_trace` and `lumped_grid`; the module split is not made |  |
| S-08 | `trace.py:156-164`, `293-309`, `353-366`; `export.py:357`; `viz/geometry.py:275` | `Trace` is one record for two shapes, told apart by `p_cells is not None`; nine fields are zero or None for a lumped run. `build` has 15 parameters; `jc` is unannotated. | Parameter object for the grid description and annotation now; the column sub-record changes `PeakResponse.trace` and waits for the public API session. | Design | R3 | accepted; partly done (R.5): `build_trace` takes the request, settings, buffers and column (15 -> 6) and is annotated; the column sub-record of `Trace` is the public API session's; R.9 done (plan 6.3b: `Trace.column`, `ColumnTrace`) | Q-10; the column sub-record approved for the public API session (ruling) |
| S-09 | `export.py:12-13`, `27`, `164-186`, `327-328`, `391-392`, `445-446`, `498-500` | The docstring says nothing here touches a solver; `to_trace_dict` runs set-up functions through the layout, and both document builders by default spawn `git` and read the clock behind `sha: str | None | bool = True`. | Make the provenance explicit arguments resolved in one helper that stays in `export.py`; `TYPE_CHECKING` import; correct the docstring. | accepted | R3 | done (R.8, plan 5.8): `_provenance`, `TYPE_CHECKING` imports, the docstring corrected | the gate patches `export.git_sha` |
| S-10 | `tools/cases.py:39-106`, `109-148`, `159-259`, `265-282` | One module does case construction, CLI options, the content of the sweep document and CSV layout detection; `step_case(args)` needs an argparse namespace; building the parser reads a fixture. | Split Phase (namespace to a spec record); Move Function for the sweep-document helpers to a tools module. | Design | R3 | accepted; done (R.8, plan 5.11): `cases.StepSpec`; the sweep-document helpers in `tools/sweep_document.py` | lines 59-62 and the name format reach exported bytes |
| S-11 | `export.py:276-290`; `trace.py:23-26`, `198` | `is_capped` infers the forced sample count from the smallest traced decay sample although the kernel returns it. | Carry the fact on `Trace`. | Design | R3 | accepted | the two can differ for a stride above `step_qty` (Q-8); approved as a recorded behaviour change after the refactoring (ruling) |
| S-12 | `viz/geometry.py:199-213` | A third fraction profile (the legacy pair, B from `EXT_QTY`) lives in a display module and is selected by catching the solver's validation errors. | Move Function into `moc` as a separate display function; Replace Exception with Test. | Design | R3 | accepted; done (R.8, plan 5.7): `moc.display_moving_fractions`, the exception replaced by the `pivot <= ext` test | D-4; not a `FRACTION_PROFILES` value |
| S-13 | `tools/bench.py:111-129`, `179-311`, `370-455`, `461-531`, `537-719` | Case table, timing harness, worker protocol and README writer in one 794-line file; the Example pressure case is transcribed although the fixture holds it; `LEGACY_FLAGS` is a third copy. | Extract Module for reporting; read the fixture; a case record. | Design | R3 | accepted | ungated (Q-7); the transcribed Example pressure case removed (R.1b); ungated tool: rename-only edits, the restructuring is not done (ruling) |
| S-14 | `tools/extract_fixtures.py:267-403`, `201-264` | `extract_curve_10in` is four functions under banner comments: 137 lines, 73 statements, 13 exits, with a 5-line copy of `read_params` that lacks its numeric check. | Split Phase. | Design | R3 | accepted | ungated; writes `tests/fixtures/` (Q-7); ungated tool: rename-only edits, the restructuring is not done (ruling) |
| S-15 | `tools/sweep_jc.py:321-401`, `448-450` | `run_case` re-derives the solver set-up, fills a 34-keyword row, runs both solvers and post-processes; four of its five parameters are run provenance. | Extract Function for the row parts; a module-level provenance tuple. | Design | R3 | accepted; done (R.8, plan 5.12): `run_case` = `_case_columns`, `_solver_results`, `_result_columns`; `RunProvenance` | `dict.fromkeys(COLUMNS)` fixes key order |
| S-16 | `viz/geometry.py:116-125`, `216-218`, `251-258`, `292-293` | `loop_layout` takes eight loose arguments; `lumped_grid` returns the same things as a 6-tuple with the two counts in the other order, swapped by hand at the call. | Parameter object for the column grid (the object S-07 returns). | Design | R3 | accepted; done (R.8, plan 5.5): `loop_layout(grid, cell_length, portal_frame_height)` takes `trace.InterleavedGrid`; `lumped_grid` returns the grid |  |
| S-17 | `histories.py:501-579`, `582-620` | `canonical` (14 parameters) and `from_params` select a generator by string; arguments are valid only for some kinds. | Explicit functions per kind behind `canonical`; its wide signature and the pinned "needs" checks stay. | Design | R3 | rejected | public signatures (bump); rejected: the per-kind functions behind `canonical` would be a wrapper layer with one user each (readability ruling: no wrapper layer without two real users today) |

## Supporting Python — Readability

| id | file:line | finding | proposed refactoring | sev | risk | status | notes |
|---|---|---|---|---|---|---|---|
| S-18 | `histories.py:282-302`, `358-378`, `446-495` | Each generator ends in a 21-line `_history(...)` call with up to nine `None` placeholders; `step_noise` is 104 lines doing seven things. | Default the kind-specific keys in `_history`; Extract Function for the noise scaling (462-470 verbatim). | Readability | R3 | accepted; done (R.8, plan 5.10): `_history` defaults `_KIND_SPECIFIC_PARAMS`; `_scaled_to_peak` |  |
| S-19 | `tools/sweep_jc.py:616-686`, `689-774`, `777-844` | The three plot functions nest to depth 6, 5 and 4 and repeat the row selection three times. | Extract Function per panel and for the selection. | Readability | R3 | accepted | ungated (Q-7); ungated tool: rename-only edits, the restructuring is not done (ruling) |
| S-20 | `tools/bench.py:179-311` | `build_cases` is 133 lines with three nested functions; a case is a 10-key dict holding two lambdas. | A case record; module-level factories. | Readability | R3 | accepted | ungated; ungated tool: rename-only edits, the restructuring is not done (ruling) |
| S-21 | `tools/bench.py:461-507` | `worker_main` is three workers selected by a string tested seven times. | Extract Function per worker; early-return dispatch. | Readability | R3 | accepted | ungated; ungated tool: rename-only edits, the restructuring is not done (ruling) |
| S-22 | `tools/bench.py:563-624`, `656-709`, `746-790` | `main`, `print_table` and `readme_section` each mix collection, arithmetic and formatting. | Split Phase. | Readability | R3 | accepted | ungated; ungated tool: rename-only edits, the restructuring is not done (ruling) |
| S-23 | `tools/sweep_jc.py:407-431`; `tools/bench.py:325-342`, `603-608`; `tools/golden_report.py:77-82` | `git` and `cpu_model` have identical bodies in two tools; the text-table printer is copied. | One shared tools module. `export.git_sha` has a different contract and stays. | Readability | R3 | accepted; open: not made in R.8 (plan 5.2): the only gated user is `sweep_jc.py`; the other copies are in the ungated `bench.py` and `golden_report.py` (ruling 24), and a shared module with one user would be a layer (ruling 2) |  |
| S-24 | `tools/sweep_jc.py:562-576`, `862-964` | The markdown tables nest five deep and rebuild their inputs inside the loops; `_select` steers two loops with a flag. | Extract Function; early returns. | Readability | R3 | accepted | ungated; ungated tool: rename-only edits, the restructuring is not done (ruling) |
| S-25 | `tools/sweep_jc.py:967-1028` | `write_doc` is one 47-line list literal that restates named constants as text literals. | Extract Function per section; format the constants (`:g`). | Readability | R3 | accepted | ungated; ungated tool: rename-only edits, the restructuring is not done (ruling) |
| S-26 | `export.py:323-399`, `445-446`, `498-500` | `to_trace_dict` is one 38-line literal; the provenance resolution is written twice. | Extract Function for `meta.params`, `meta.outputs` and the provenance pair. | Readability | R3 | accepted; done (R.8, plan 5.8): `_meta_params`, `_meta_outputs`, `_provenance` | key order is byte-gated |
| S-27 | `export.py:405-433`, `206-228` | `_sweep_value` interleaves string, int and float columns in one ladder (about 15 as ruff counts). | Decompose Conditional, keeping the order of checks and the two pinned messages. | Readability | R3 | accepted; done (R.8, plan 5.9): `_sweep_string`, `_sweep_int`, `_sweep_float` |  |
| S-28 | `tools/golden_report.py:36-91`; `tools/profile_delta.py:72-121`, `124-181`, `217-280` | The numbers cannot be had without the printing; the JSON is written in two places. | Split Phase: rows, then render. | Readability | R3 | accepted | ungated; ungated tool: rename-only edits, the restructuring is not done (ruling) |
| S-29 | `tools/cases.py:220-259` | `reference_block` writes the same seven-key record in two loops. | Extract Function for the record. | Readability | R3 | accepted; done (R.8, plan 5.11): `sweep_document.ReferenceCase` | key order is byte-gated |
| S-30 | `tools/export.py:59-61` | `estimate_bytes` has no caller. | Remove; correct the docstring at 42. | Readability | R0 | accepted; done (R.8, plan 5.14) |  |
| S-31 | `export.py:164-180`, `391`, `498`, `503`; `tools/sweep_jc.py:416-420`; `tools/bench.py:354-356`; `tools/cases.py:234`, `252` | `git_sha` is a full sha or null in one document, a short tag with `-dirty` or `nogit` in the CSV, and either in `sweep.meta`; `source` is a string in one place and an object in another. | One format per key, at the bump. | Readability | R0 | accepted | bump |
| S-32 | `tools/sweep_jc.py:244-261`; `histories.py:69-85` | Four of the fifteen column / parameter pairs differ only in spelling (`history_type` / `kind`, three `_hz`). | One word on both sides; the tuple stays for order and selection. | Readability | R0 | accepted; R.9 done (plan 6.4a / 6.5: `PARAM_KEYS`, `History` fields and the columns one vocabulary) | bump for the columns |
| S-33 | `export.py:486-491`; `tools/cases.py:186-195` | The package holds a default `tools/` command line that the tool repeats. | One constant; the default goes when the signature is reviewed. | Readability | R3 | accepted; R.9 done (plan 6.4b: `regen` required, the tool passes its template) | six tests rely on the default |
| S-34 | `tools/build_viewer.py:68-74`, `107-121` | `build` takes its inputs as bytes but reads the licence file and the package version itself. | Parameters with defaults. | Readability | R3 | accepted; done (R.8, plan 5.14): `licence` and `plotly_package_version` parameters with defaults; the built page byte-identical | built page must stay byte-identical |
| S-35 | `trace.py:142`; `response.py:272`, `468`; `viz/geometry.py:239-247`, `273-281`; `export.py:365` | `Trace.inputs` is an untyped dict that `geometry` reads by key to redo the set-up. | After S-06 the dict serves only the `meta.inputs` echo. | Readability | R3 | accepted; done (R.8, plan 5.6): the geometry reads the height from `Trace` and only the span and celerity from `Trace.inputs` | follows S-06 |
| S-36 | `tools/cases.py:154-156`, `277-278` | The exported `size_in` is parsed from the name of the directory the CSV sits in. | Take the set name from the caller. | Readability | R3 | accepted | Q-8 (changes what a moved file exports); approved as a recorded behaviour change after the refactoring (ruling) |
| S-37 | `trace.py:102-107`, `126`, `139-140`, `157-159`; `export.py:117-118`, `249-251`, `370-376`; `tools/cases.py:36-177`; `tools/sweep_jc.py:66`, `361-362` | VBA spellings in fields, locals and exported keys: `step_qty`, `out_max`, `ext_qty`, `pipe_seg_qty`, `fric_acc`, `ratio2`, `fluid_densty`. | Internal names with the core's renames; keys and columns at the bump. | Readability | R0 | accepted; R.3: internal names done; keys and columns at the bump; R.9 done (plan 6.5, the schema bump) | bump |
| S-38 | `trace.py:38-42`, `156`, `355`; `viz/geometry.py:45-46`, `76-78`, `98`; `tools/bench.py:208`; `moc.py:108`; `docs/data_format.md:107`, `251` | "cell" is an interleaved entry and a B cell; "segment" is a MoC cell and a loop piece; the grid count has five names. `moc.py:108` and `data_format.md:251` say the count is "between the elbows"; the code counts the whole column. | One word per concept; correct the two descriptions. | Readability | R0 | done (R.3: the two descriptions corrected; exported keys at the bump); R.9 done (plan 6.5, the schema bump) | Q-6; bump for keys |
| S-39 | `trace.py:12`, `19-20`, `72-74`, `181-184`; `export.py:294-295`, `389`; `response.py:622`, `897`; `tools/bench.py:52` | Frame 0 is the first traced sub-step in the object and the synthetic rest frame in the file, so `n_frames` differs by one; phases are numbered 0-2 by the constants and 1-3 in docstrings. | Name phases by constant; distinguish the two counts. | Readability | R0 | accepted; R.3: phases named by constant; meta.n_frames at the bump; R.9 done (plan 6.5, the schema bump) | bump for `meta.n_frames` |
| S-40 | `trace.py:78-81`, `144-145`, `167`, `173`, `198`; `viz/geometry.py:79-82`; `histories.py:147`, `215` | Indices and counts do not follow `_index` / `_count`; `sub_step` and `substeps` both occur. | Rename; unify on the style guide's spelling. | Readability | R0 | accepted; R.3: internal done; exported keys at the bump; R.9 done (plan 6.5, the schema bump) | bump for exported keys |
| S-41 | `export.py:120-142`, `380-386`; `tools/sweep_jc.py:364-366`, `388-394`; `tools/cases.py:179-180`; `histories.py:148-151` | The same peaks are `max_velocity` in the trace document and `v_peak_*` in the sweep; `history_peak` is a force and `p_peak_bar` a pressure. | One stem across both documents. | Readability | R0 | accepted; R.9 done (plan 6.5, the schema bump) | bump |
| S-42 | `trace.py:77-80`, `150-155`, `328-329`; `export.py:59-71`, `315` | Symbol and type-coded names outside a kernel, also as JSON keys: `t`, `x`, `v`, `a`, `d_f`, `cells.p`, `cells.v`; `frames.v` and `cells.v` are different velocities. | Internal names now; keys at the bump (the viewer validates all thirteen). | Readability | R0 | accepted; R.9 done (plan 6.5, the schema bump) | bump |
| S-43 | `export.py:82-144`, `246-265`, `367-373`; `histories.py:132-140`; `tools/sweep_jc.py:64`, `110-115` | SI quantities carry a unit suffix in some names and not in others; `BAR = 1e5` does not say which way it converts. | Decide one rule for exported names at the bump; name the constant. | Readability | R0 | accepted; R.9 done (plan 6.5, the schema bump) | bump |
| S-44 | `tools/bench.py:114-125`; `tools/cases.py:59-62`, `122-123`; `tools/sweep_jc.py:125-126`, `137-138`, `1118` | Bar and mm values under unit-less names; `size` is inches in one tool and millimetres in the next; `mass` holds kg/m. | Rename variables and argparse `dest` only; the flag strings are pinned. | Readability | R0 | done (R.3: variables and dest names) |  |
| S-45 | `tools/cases.py:59`, `62`; `tools/sweep_jc.py:122-127`, `142`, `332`, `383`, `635-636`, `885-886`; `histories.py:320-321`, `397-398`, `510-512`, `561`, `569`; `tools/export.py:73` | Bare conversions (`/ 1000`, `* 1e5`, `1e6`) and convention values (`1.33`, `0.5 * cap`, `10.0`, `0.8`, the 0.05 and 0.8 report thresholds in four places). | Named constants in place, as divisors of the same literal type. | Readability | R1 | accepted; partly done (R.4): gated conversions and convention values named; `od / 2000` kept with a comment (one divisor; splitting it regroups); the report thresholds of the ungated plots and report stay (ruling 24) | about half are in gated expressions; the basis of `1.33` answered in R.3 (ruling 27), its comment is `plan.md` 0.7 |
| S-46 | `trace.py:122`, `154`; `export.py:119`, `357`, `377`, `521`; `tools/bench.py:213-214` | Booleans that are not predicates: `stick`, `capped`, `jc_short_pipe`, `jc`, `gzip`. | Rename the internal ones. | Readability | R0 | accepted; R.3: export locals done; the three keys at the bump; R.9 done (plan 6.5, the schema bump) | bump for three keys |
| S-47 | `trace.py:232`, `306`; `export.py:55-56`, `357-358`; `histories.py:70`, `549`; `tools/sweep_jc.py:323-324`, `378` | `jc`, `cap`, `kind`, `solver`, `p`, `h` each name unrelated things; `solver` has two value sets in one document family. | Rename; one value set at the bump. | Readability | R0 | done (R.3: internal; solver values at the bump) | bump for `solver` values |
| S-48 | `tools/sweep_jc.py:110-111`, `383-384`, `395`; `export.py:113-114`, `125-142`; `viz/geometry.py:84-88`, `155-165`; `tools/profile_delta.py:133-152` | Computation names and abbreviations: `d2`, `p_peak_a`, `f_eq_over_LD2_*`, `ratio_f_eq`, `daf_*`, `thk_mm`, `leg_height_2`, `height1`, `s1..s4`. | Rename; exported columns at the bump. | Readability | R0 | accepted; R.3: internal done; columns at the bump; R.9 done (plan 6.5, the schema bump) | bump |
| S-49 | `trace.py:1`, `32`, `105`; `export.py:1`, `54`; `histories.py:1`, `59`; `viz/geometry.py:1`, `10-11`, `200-203`; `tools/cases.py:192-193`, `209`; `tools/sweep_jc.py:978-986` | Docstrings define things by session label, fix id or VBA name; two session labels reach exported files. | Physical meaning first; ids in Notes; the exported strings at the bump. | Readability | R0 | accepted; R.9 done (plan 6.5, the schema bump) | bump for two strings |
| S-50 | `trace.py:192-195`, `214-215`, `315-316`; `histories.py:155-195`, `535-536`; `export.py:164-192`; most functions in `tools/` | Docstrings without Parameters / Returns, units, shapes or dtypes; many tool functions have none. | Numpy sections, last. | Readability | R0 | accepted; done (R.10, plan 6.6) for the supporting modules and the gated tools; the tools no test runs keep their docstrings (rename-only, ruling 24) |  |
| S-51 | `trace.py:306`; `export.py:192`, `206`, `405`, `436`, `515-535`; `histories.py:192`, `210`, `230`; `tools/bench.py:157-746`; `tools/sweep_jc.py:312-1126` | Signatures without annotations. | Add them; untyped dicts of solver inputs need the parameter objects first. | Readability | R0 | accepted; done (R.10, plan 6.7) for `trace`, `export`, `histories` and the gated tools; `bench.py` and the report half of the old `sweep_jc.py` (now `sweep_report.py`) are ungated and stay unannotated (ruling 24) |  |

## Brought across from R.2 (session R.3, ruling 22)

Confirmed Design and Readability findings of the second review (`findings_r2.md`) that its
cross-reference table matches with no R.1 finding. Ids and line numbers are R.2's (tree
`83471ec`). Accepted under ruling 8; none of the four fixes adds an abstraction layer.
Not brought across: **SP-25** (`tools/review_baseline.py`, `collect` at complexity 12),
which concerns a tool no test runs.

| id | file:line | finding | proposed refactoring | sev | risk | status | notes |
|---|---|---|---|---|---|---|---|
| SP-15 | `trace.py:250-268`, `296-312`; `response.py:666`, `719-735` | `trace.build` takes 15 parameters, four of them the buffers `allocate` returned, plus an untyped `jc=None`; `celerity` and `ext_qty` mean something only with `jc`. | Introduce Parameter Object: the buffers (returned by `allocate`; a NamedTuple keeps the tests' positional indexing), the run fields, the JC grid (`None` for lumped). Passing the buffers whole to the kernel is C-01 (R4). | Readability | R3 | accepted; done (R.5): the buffers are `TraceBuffers` (returned by `allocate_frames`, positional indexing kept), the run fields `TraceRequest` and `RunSettings`, the JC grid the `FluidColumn` (the empty column for lumped) | with `plan.md` 3.3 and 3.6 (C-14, C-15, S-08) |
| SP-35 | `viz/geometry.py:7`, `52-67`, `87-88`, `157-170`, `185-190`; `export.py:261-262`; `docs/data_format.md:112-125`; viewer `:365`, `489` | The layout describes four drawn corners and legs 1 / 2; nothing says which corner is elbow A (where `f_a` acts) or B. The field name `leg_height_2` does not say outlet (the docstrings do). | State the elbow A / B mapping in the `LoopLayout` docstring; rename the leg heights to inlet / outlet at the bump. | Readability | R0 | done (R.3: docstring; field names at the bump); R.9 done (plan 6.5, the schema bump) | elbow A answered in R.3 (ruling 26: the one the pressure wave reaches first, the inlet side of the run); docstring `plan.md` 1.16; field names: bump |
| SP-36 | `trace.py:42-44`, `131-133`, `325`, `368`; `viz/geometry.py:42`, `199-213`; `moc.py:160-298`; `docs/data_format.md:104` | One per-cell value is "moving fraction" (the exported key), "interp fraction" (the docstrings describing that key) and "weighting of the mass acceleration" (`moc.py:161`, `193`); "interp" names the computation and is the VBA spelling. | Use "moving fraction" throughout; `frac_a` / `frac_b` to the nomenclature's names; `interp_fraction_*` renamed (kernel parameters with the parameter objects, ruling 21). `fraction_profile` is a related concept and a public flag (bump). | Readability | R0 | accepted; R.3: prose and functions done; kernel parameters group 3, fraction_profile at the bump; R.9 done (plan 6.5, the schema bump) | `plan.md` 1.15; `legacy_port.interp_fraction_*` frozen |
| SP-41 | `docs/data_format.md:113`; `histories.py:338-340` | `data_format.md:113` says the outlet leg is "one cell shorter" without qualification; with the default profile both legs are equal (pinned by `test_geometry.py:117`); only the legacy profile shortens it. The `step_sine` docstring's "(default 0.2)" sits where `decay_fraction`'s default (0.8) would go. | Correct `data_format.md:113`; reword the docstring. | Readability | R0 | done (R.3) | wrong documentation: `plan.md` 0.3, done early |

## Supporting Python — Nits

| id | file:line | finding | proposed refactoring | risk | status |
|---|---|---|---|---|---|
| S-N01 | `tools/profile_delta.py:51`; `tools/extract_fixtures.py:64` | `OUTPUTS` and `FORCE_SHEET_COL` are defined and unused while their values are written out. | Use or delete. | R1 | rejected |
| S-N02 | `histories.py:41-57`, `69` | `PARAM_KEYS` is used by a tool and missing from `__all__`. | Add. | R0 | rejected |
| S-N03 | `viz/geometry.py:83`, `185-190` | `elbow_pairs` is computed for every export and read by a test only. | Decide at the bump. | R0 | rejected |
| S-N04 | `export.py:249-251`, `265` | Four geometry keys are written that the viewer does not read. | Decide at the bump. | R0 | rejected |
| S-N05 | `tools/sweep_jc.py:263` | `COLUMNS` is a second name for `export.SWEEP_COLUMNS`. | Inline. | R0 | rejected |
| S-N06 | `export.py:18-19`, `521`; `tools/bench.py:82`, `172` | `_dt`, `_gzip` aliases forced by a parameter name; `import datetime as dt` shadowed by the time step. | Rename the parameter and the import. | R0 | rejected |
| S-N07 | `tools/review_baseline.py:35`, `191-194` | The file list is globbed at import; the summary hard-codes the targets `TARGETS` holds. | Compute in `main`; format from `TARGETS`. | R1 | rejected |
| S-N08 | `tools/sweep_jc.py:509-514`, `847-852` | Colours and band edges inline; `1e9` as "no upper bound". | Move with S-03. | R1 | rejected |
| S-N09 | `tools/sweep_jc.py:579-590` | `_series(envelope="max")`: `"min"` is never used. | Remove Flag Argument. | R2 | rejected |
| S-N10 | `tools/sweep_jc.py:131-155` | `check_pipe_table(verbose)` asserts and prints. | Two functions. | R3 | rejected |
| S-N11 | `tools/export.py:75`; `tools/cases.py:52`, `281` | Helpers that other tools import end the process with `SystemExit`. | Raise `ValueError`; convert in `main`. | R2 | rejected |
| S-N12 | `tools/review_snapshot.py:29-59` | `main` holds compare and write; its twin has them as two functions. | Extract to the same names. | R3 | rejected |
| S-N13 | `trace.py:202-244` | `check_memory` returns the capacity, raises the guard and searches for a stride. | Extract the search. | R3 | rejected |
| S-N14 | `export.py:214-215`, `236-237`, `317-318` | Three finite-value checks with two message wordings. | One helper, messages unchanged. | R3 | rejected |
| S-N15 | `export.py:51`, `53` | `SCHEMA_VERSION` beside `SWEEP_SCHEMA_VERSION`. | `TRACE_SCHEMA_VERSION`. | R0 | rejected |
| S-N16 | `tools/extract_fixtures.py:173`; `tools/profile_delta.py:60`, `68`; `tools/bench.py:145`, `755` | `fmt`, `COLUMNS`, `rel`, `run` mean different things in different tools. | Rename. | R0 | rejected |
| S-N17 | `tools/extract_fixtures.py:271`, `287`, `291`, `312`, `330`, `372` | Banner comments and comments that translate a column number. | Go with S-14 and S-45. | R0 | rejected |
| S-N18 | `histories.py:66-67` | The docstring of `P_CAP_FACTOR` names a `P_CAP` that does not exist and gives no source for 1.33. | Correct; state the source. | R0 | rejected |
| S-N19 | `tools/sweep_jc.py:77-93`, `161-169`, `197-203` | `TIERS` keys and `Case` fields use different words for the same dimensions. | One word. | R0 | rejected |
| S-N20 | `tools/export.py:39`; `tools/cases.py`; `tools/bench.py:467` | A tool module named `export` beside the package's; `cases` is a module and a local. | Rename the tool modules with S-02. | R0 | rejected |
| S-N21 | `tools/golden_report.py:22`, `41-47`; `tools/profile_delta.py:57`, `77-78`; `tests/test_golden.py:118` | The golden cache record that two tools read is defined only inside the tests. | Writer and reader beside the loaders of S-01. | R3 | rejected |
| S-N22 | `tools/sweep_jc.py:513` | `SOLVER_INK` is defined and unused. | Delete. | R0 | rejected |

## Parameter objects, R.5: functions still above 6 arguments

After plan group 3 (session R.5; `ruff check --select PLR0913` with `max-args = 6`, keyword-only
arguments counted, ruling 17):

| function | arguments | why it is still above 6 |
|---|---|---|
| `response._integrate_kernel` | 7 | Kept on purpose. `schedule`, `sdof_params`, `settings`, `column` and `buffers` are the five things a reader names; the other two are the junction force (an evolving scalar, passed in and returned, `docs/style.md` §4) and the response history (an output array filled in place, sized by `_integrate`). Folding either into one of the five tuples would group by type, not by meaning (C-01). |
| `response.peak_response` (14), `peak_response_jc` (19) | | User-facing entry points: their keywords are the public API session's (6.2, style §11). |
| `histories.step_sine` (9), `step_noise` (12), `canonical` (14); `export.to_sweep_dict` (9) | | User-facing (rulings 4, 18): the public API session (6.4). |
| `structure.lumped_params` (9), `jc_params` (11) | | Plan 3.7 (C-17), not in session R.5. |
| `viz.geometry.loop_layout` (8) | | Plan 5.5 (S-16, the column-grid object for `loop_layout`). |
| `tools/bench.py` `build_cases.peak_case` (8) | | An ungated tool: rename-only (ruling 24). |

## Recorded constraints

What `docs/architecture.md` and `DEVIATIONS.md` say about the code behind the findings.

* **K-1, Numba signatures.** "Stage 5" states that compiled signatures take floats, ints,
  bools and 1-D float64 arrays only. This explains C-01, C-03, C-04, C-10 and C-15. It is a
  choice, not a limit of Numba 0.68.1: a toy kernel written both ways (a NamedTuple of
  arrays and scalars updated in place, a NamedTuple of constants, two compiled helpers,
  against flat scalars and inlined bodies) gave the same `float.hex()` results compiled and
  with `NUMBA_DISABLE_JIT=1`, and the same time (7.4 ms against 7.7 ms for 200 000 steps of
  a 200-cell column). The toy is not the solver; the snapshot and `tools/bench.py` decide
  each real commit. Keyword-only parameters remain unavailable between compiled functions
  (style section 3).
* **K-2, the coupling interface.** "The Python-level `Coupling.coupling_force` interface
  stays for callers and tests" (Stage 5). There are no callers outside the tests.
  Superseded by the readability ruling (R.1b): the protocol and `coupling_force` go.
* **K-3, per-cell helpers.** `moc.step` is described as having "no per-cell helper calls".
  The extractions proposed in C-04 and C-05 are per sub-step.
* **K-4, the two set-ups.** "The two set-ups are *not* merged into one function with
  flags." C-11 extracts shared helpers and leaves two set-ups.
* **K-5, exactness.** "Exactness notes" record that the gap ladder is inlined branch for
  branch, that `half_dt = dt / 2` and the ramp tables hold the same doubles, and that
  `0.0 + F` differs from `F` in the sign of an exact zero. These fix how C-02, C-07 and
  C-10 must move code; they do not require the duplication.
* **K-6, laziness and D-8.** The schedule generators run only when `_integrate` consumes
  them, after every set-up check; D-8's `IndexError` must surface at the first ramp sample.
  A schedule built earlier or in one pass would change which exception wins on bad input.
* **K-7, set-up order.** The JC set-up follows the VBA order and D-9 / D-12 fix which error
  a degenerate input raises; `jc_params` and `decay_factor` stay ahead of the short-pipe
  test.
* **K-8, `vba_compat`.** The module table says new modules may import from the frozen
  `vba_compat` and that only a semantic it lacks goes to `_vba_semantics`. `CLAUDE.md` says
  Stage 6 removes both frozen modules.
* **K-9, the traced friction.** "Session V.1" says the friction force is recomputed in the
  recording branch "so `structure.py` is untouched". That was the session's constraint.
* **K-10, `pressure` is not compiled** and keeps numpy-scalar `errstate` semantics; a
  column tuple or an extracted solve must keep passing numpy scalars. (Void since R.1b:
  `pressure.py` was removed.)
* **K-11, tool names are data.** Command lines such as `python tools/export.py trace ...`
  are stored in exported files and asserted by tests; the process pool pickles its worker
  under the module name `sweep_jc`; `tests/test_review_support.py` keeps tools out of
  `sys.modules` because hypothesis seeds examples from module constants. `tools/x.py` must
  keep working as a script path.

`docs/architecture.md` itself is out of step with the code in places (the data flow still
shows `_integrate` calling `coupling_force` under `np.errstate`; the sweep document has
"thirty fixed columns"). It is not in the review scope; it will need a pass after the
refactoring.

## What is good and should be left alone

* **The flags never enter compiled code as strings.** `vav_denominator` becomes an int and
  `fraction_profile` two arrays at set-up (`coupling.py:156-162`, `moc.py:295-347`).
* **The module graph.** No import cycles; `structure` imports nothing internal; `moc` knows
  nothing of the structure; `trace` imports `structure` only; nothing in `src/` imports
  `tools/` or `tests/`.
* **Small pure set-up functions:** `moc.grid_size`, `is_short_pipe`, `decay_factor`,
  `vav_divisor`; `loads.transit_delay`, `overlap_substeps`; `structure.solve_poly`,
  `solve_portal_height`, `effective_displacement`.
* **The four `interp_fraction_*` functions** (`moc.py:157-292`): four flat ladders, not one
  function with a flag. Merging them would mean parameterising expressions.
* **`SdofParams`** as a module-level NamedTuple with a unit per field.
* **The single index walk** `loads._schedule` shared by both generators.
* **`_decay_test`, `_record`, `_trace_stride`**: small single-purpose helpers. The trace
  recording only reads solver state.
* **Serialisation in one place:** `array_block`, `_jsonable`, `dumps`, `write_json`,
  `read_json`; non-finite values refused centrally.
* **`trace.capacity`, `check_memory`, `allocate`, `interleave`**; `viz/geometry._segments`
  and `loop_layout` on plain arrays.
* **`histories.py` building blocks** (`decay_rate`, `_duration`, `_axis`, `_sine_shape`,
  `_lowpass`) and the `params()` / `from_params` round trip.
* **Constants already done right:** `structure.VBA_PI`; `trace.MAX_TRACE_VALUES`; the pipe
  and material constants at `tools/sweep_jc.py:52-63`; the pins in `tools/build_viewer.py`.
* **`tools/review_snapshot.py`, `tools/review_support.py`, `tools/review_baseline.py`**
  beyond the nits; the declared workbook layout in `tools/extract_fixtures.py:68-161`.
* **Every expression in the charter's mutation tables.** The names around them change; the
  expressions do not.

## Suspected defects (not acted on)

Raised by the reviewers as possible numerical or logic defects. None was investigated
beyond reading, and none is part of the refactoring. Each is a question for the owner.

**Ruling 20 (R.3):** the remaining suspected defects are not investigated in this review;
the list stays here for the lead author. Nos. 15 to 24 were found by the second review
(`findings_r2.md`, "Possible defects", its number in brackets; line numbers of `83471ec`)
and are neither in this list nor in `DEVIATIONS.md`. R.2's other items are here already
(its 1, 3, 11 are nos. 3, 1, 11), are recorded (its 9 is D-24), or are decided: its 8, the
`decay_factor` half-life, is a wrong docstring and is corrected to the formula (`plan.md`
0.5).

1. `response.py:431-448`: an unknown `vav_denominator` is accepted silently on a short pipe
   and when `rho_c == 0`; the docstring promises `ValueError`. Confirmed by reading.
2. `moc.py:514` against `497`: on odd sub-steps the junction force reads `p_b[pivot]` and
   `p_b[n_seg - pivot]`; the mirror of cell `pivot` is `n_seg - 1 - pivot`, so the inlet
   tap moves one cell between parities. Not in `DEVIATIONS.md`.
3. `response.py:828`, `895` against `906`, `973`: the forced phase has no
   `tot_ind <= out_max * 2` bound on the trace or the history write.
4. Removed with the pressure solver (R.1b): `pressure.py:336`, `409` against `222-223`, the
   sign of the local initial velocity in the friction clamp. The same expression lives on
   in the frozen `legacy_port.get_pressure_response`.
5. `structure.py:214`, `299`: the factor `0.5` in the friction velocity step has no stated
   derivation.
6. `response.py:874`, `953`: the traced friction force is scaled by the rigid mass on the
   junction-coupling path, while `fric_acc` is scaled by total over rigid mass.
7. `response.py:529`: `_decay_test` raises only on `+inf`.
8. `response.py:704-705`: if the kernel raises, the junction's arrays have advanced and
   `d_f` has not been written back.
9. `export.py:289-290`: `is_capped` uses the smallest traced decay sample index; with a
   stride above `step_qty` it can differ from the kernel's forced sample count.
10. `tools/export.py:121` against `docs/data_format.md:187`: for a CSV with no uniform
    `git_sha` the exporter stamps its own HEAD where the document says null.
11. `tools/sweep_jc.py:468`, `460`, `494-499`, `990`: the CSV name omits `--history`;
    subsets below 0.5 % are all `subset0`; division by zero and `max()` of an empty list
    when no row is selected or every row failed.
12. `tools/cases.py:59`, `85`: `--area 0` is treated as "not given".
13. `tools/bench.py:162-166` against `tools/cases.py:91-94`: the forced sub-step count is
    computed by two expressions; `tools/bench.py:21-22` gives a reason for the transcribed
    Example constants that no longer holds.
14. `histories.py:352`, `459`: a zero frequency raises `ZeroDivisionError` before the
    documented `ValueError`.
15. (R.2 2) `response.py:247`, `404`, `540-545`: `output_type` above 3 returns an all-zero
    history and a negative value returns `None`, silently.
16. (R.2 4) `structure.py:297-299`, `320`: the JC rigid mass `L (m' - rho A) + ...` is zero or
    negative when `rho A >= m'`; nothing guards it before it divides.
17. (R.2 5) `response.py:902-903`: if `x` is exactly 0 at the end of the forced phase, free
    decay runs no samples whatever the velocity (`x * xZero = 0`). Related to D-21, not
    recorded there.
18. (R.2 6) `structure.py:361` / `368`, `485` / `491`: the clamp test uses `abs(gap)` while
    `excess = ax - gap` uses the signed gap; a negative gap takes inconsistent branches.
19. (R.2 7) `structure.py:118`: `error_val / var_a` divides by zero when EI = 0.
20. (R.2 10) `tools/golden_report.py:62-66`: `next(...)` without a default raises
    `StopIteration` when a case fails on a NaN.
21. (R.2 12) `tools/sweep_jc.py:858-862`: `_band` files `f <= 0` under "> 16 Hz".
22. (R.2 13) `export.py:418`: an int column whose CSV text is `"10.0"` raises, though the
    float `10.0` is accepted.
23. (R.2 14) `tools/build_viewer.py:77-79`: the provenance comment names the installed plotly
    version even when `--plotly` supplies another bundle.
24. (R.2 15) `tools/cases.py:94`, `tools/bench.py:143`: the forced-substep estimate is not
    checked against the length of the `loads` schedule (which uses the `CLng` overlap);
    possibly off by one at a rounding boundary.
