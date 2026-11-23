# Clean-code review — findings (second independent review, R.2)

Session R.2, 23 Nov 2026, on the tree at `83471ec`. Independent review of the solver core and
the supporting Python against `docs/style.md`; no code was changed. `docs/review/plan.md`
orders the fixes. The first review (R.1, 16 Nov 2026) and its plan, which the charter's
rulings cite (for example S-17, S-11, S-36), are kept unchanged as
`docs/review/findings_r1.md` and `docs/review/plan_r1.md`. Ids here are new (`SC-`, `SP-`,
`N-`) so they cannot be confused with R.1's (`C-`, `S-`, `K-`).

## How this list was made

1. **Blind pass.** Six `clean-code-reviewer` agents, three on the solver core (`moc`,
   `structure`, `coupling`, `loads`, `response`) and three on the supporting Python (`trace`,
   `export`, `histories`, `viz/geometry`, `tools/`, the data format and the viewer's keys),
   one lens each: architecture; functions; names and documentation. They read
   `docs/style.md` and the charter only, not `docs/architecture.md`, `NOTES.md`,
   `docs/port_review.md`, `DEVIATIONS.md`, the R.1 findings or the git history. (One
   reviewer's grep returned a few lines of `docs/architecture.md` and the R.1 findings; it
   did not open them and says so.) Raw output: 151 findings, 23 Design, 86 Readability,
   42 Nit.
2. **Merge.** Findings that several lenses made about the same code were merged: 71 Design
   and Readability findings, 42 Nits.
3. **Verify.** Each of the 71 went to its own `finding-verifier` agent, which tried to
   refute it from the code: **67 confirmed, 3 refuted (dropped, listed below), 1 unclear
   (kept, marked)**. Most confirmations came back with corrections (line numbers, a wrong
   risk class, missed call sites, a sub-claim that did not hold); the rows carry the
   corrected version. Nits were not verified; overlapping Nits were folded into their
   finding, leaving 24.
4. **Reconcile.** `docs/architecture.md` ("Exactness notes", "Stage 5", "Session V.1") and
   `DEVIATIONS.md` were read afterwards. A recorded constraint is named in the `constraint`
   column (keys under "Recorded constraints"); it explains the code and does not close the
   finding. The claim that Numba forces the flat-scalar kernel signatures was tested on a toy
   kernel (K-1).

| severity | solver core | supporting Python | total |
|---|---|---|---|
| Design | 7 | 6 | 13 |
| Readability | 21 | 34 (1 unclear) | 55 |
| Nit (unverified) | 7 | 17 | 24 |
| total | 35 | 57 | 92 |

Risk classes are the charter's: R0 rename, R1 named constant, R2 control flow, R3 function
extraction, R4 kernel signature or loop structure. **bump** = the name is in an exported
file or is a public keyword and changes only in the public API session (schema bump). Line
numbers are those of `83471ec`. Every finding has status **open**. The `R.1` column names
the R.1 finding that covered roughly the same ground (matched by title; approximate), or
`new`.

## Solver core — Design

| id | file:line | finding | proposed refactoring | sev | risk | status | constraint / notes | R.1 |
|---|---|---|---|---|---|---|---|---|
| SC-01 | `coupling.py:38-72`, `165-204`; `structure.py:55-56`, `380-441`; `response.py:707-708` | Layers that ruling 2 removes are still there: the `Coupling` protocol, `NoCoupling`, `coupling_force` (a third copy of the 15-argument `moc.step` call, `coupling.py:180`), `column()`, `structure.State`, `restoring_force`, `structure.step`. Nothing in `src/` or `tools/` calls them; only tests do (`test_differential.py:312, 335, 782-807`; `test_trace.py:367-369`). The `jc.d_f = float(d_f)` write-back is dead: nothing reads it, tests included. | Remove Dead Code per ruling 2; point the tests at `moc.step`, `step_scalars`, `effective_displacement`. `NoCoupling`/`KIND` still drive the kernel dispatch, so they go with SC-04, not here. | Design | R3 | open | K-2 (superseded by ruling 2). Three assertions have no counterpart once the wrapper goes (`test_differential.py:783` `type(d_f) is float`, `:802` signbit, `:807` `== 0.0`): owner's word needed (charter scope). Other test call sites: `test_fraction_profile.py:66, 225, 229`; `test_differential.py:769, 797, 1107`; `test_trace.py:356`. | C-03, C-N13 |
| SC-02 | `response.py:750-787` (36 params), `549-573` (23); `moc.py:403-419` (15); `structure.py:445-457` (11); `response.py:669-674`, `682-687`, `695-696` | Compiled kernels take flat positional lists. `SdofParams` exists as a NamedTuple but is spread into six scalars; the MoC column travels as six arrays plus seven scalars (`*column, *scalars`); the trace buffers as four arrays; the 15-name `moc.step` list is written three times (`response.py:837, 919`; `coupling.py:180`). | Introduce Parameter Object: `SdofParams` whole; a module-level column NamedTuple (arrays updated in place, `d_f` passed in and returned); a trace-buffer NamedTuple returned by `trace.allocate`. | Design | R4 | open | K-1: possible and bit-identical; unpack the column once per kernel call or pass it at most one call deep per substep, or it costs 14-47 % (toy). `JunctionCoupling` is a `__slots__` class, not a NamedTuple. Test call sites: `test_differential.py:709, 1127`. | C-01, C-10, C-15 |
| SC-03 | `response.py:829-896` vs `907-976` | The forced and free-decay loops of `_integrate_kernel` repeat one ~45-line substep body: the `moc.step` block, the 25-line `_trace_frame` call with the friction-force expression, the three max trackers. The real differences: `f_applied` (`d_f + f` / `0.0 + f` vs `d_f` / `0.0`), the `rec` condition, phase code and elbow forces, `f_max`, and the `x_zero` reset at 977-978. | Extract Function into small `@njit` helpers (advance column, update peaks, record frame); each loop keeps its own `f_applied` line, `rec` test, `f_max` update and `x_zero` reset verbatim. Group the record helper's arguments separately (it would exceed 6 parameters). | Design | R3 | open | K-4: `0.0 + F` vs `F` differ in the sign of an exact zero, so the `f_applied` lines must not be merged; `float(moc.step(...))` and `float(flat[i])` keep Python floats in pure mode (D-23) and must move with the call. | C-02 |
| SC-04 | `response.py:641, 644, 667-676, 694, 707, 732, 835, 879, 917, 961`; `_trace_frame` `567, 590`; `coupling.py:66, 125` | Fluid coupling on/off is an integer kind code branching in two compiled functions, with seven unnamed placeholder scalars `(0, 0, 0.0, 1.0, 1, 0.0, 0.0)` for the lumped run and an unreachable `raise TypeError` (only 0 and 1 ever reach it). | Replace with a plain boolean (ruling 2); build the empty column once in a named place, keeping each placeholder's literal type; drop the unreachable branch. Keep `0.0 + f`, `0.0`, `d_f if ... else 0.0` as written. | Design | R4 | open | K-1 (kernel signature). Docstrings to update: `response.py:26, 575, 617, 791-793`; `coupling.py:11-12`. | C-06 |
| SC-05 | `response.py:600-746` | `_integrate` (10 params, ~126 lines) flattens forces, sizes the history, sets up and cross-checks the trace, unpacks the coupling by kind, calls the kernel, writes back, checks finiteness, computes the static-equivalent force, builds the trace and the result. | Split Phase / Extract Function: flatten, prepare trace, column arguments, result. The elbow flattening needs a projected iterable and must stay after the length check (650-651); the write-back (or its removal, SC-01) stays with the caller. | Design | R3 | open | — | C-06 |
| SC-06 | `response.py:241-257` vs `396-414`; `272-291` vs `468-492`; `433-448` | The two entry points repeat ~15 lines of set-up (casts, history, transit delay, `out_max`, `dt`, portal height) and the `meta.inputs` echo (13 and 18 keys); the short-pipe fallback passes all raw arguments again to `peak_response`, which re-derives them. | Extract Function for the shared prefix returning a NamedTuple; Extract Function for the trace meta. The JC echo has the fluid keys in the middle (478-479): splice, keep key order byte for byte. The fallback keeps calling `peak_response` (solver name, exception order). | Design | R3 | open | K-3 (not merged with flags: this extracts helpers, it does not merge); K-6 (set-up order: `jc_params` before the short-pipe test). | C-11 |
| SC-08 | `loads.py:232-309` vs `312-373`; `response.py:649-651` | `unbalance_force` and `elbow_forces` are one function written twice (same unpacking, dispatch and ramp expressions, nesting 4); a traced run walks the schedule twice and cross-checks only the lengths. | One per-sample generator yielding the two elbow-force lists; the unbalance is `fa - fb` in the consumer (same operands, same operation: bit-identical, verified). `unbalance_force` stays callable (tests, D-7/D-8). | Design | R3 | open | K-5 (laziness: D-8's `IndexError` must still surface at the same point). | C-07 |

## Solver core — Readability

| id | file:line | finding | proposed refactoring | sev | risk | status | constraint / notes | R.1 |
|---|---|---|---|---|---|---|---|---|
| SC-09 | `response.py:637-640, 908-913, 979-983`; `trace.py:198-201`; `export.py:290` | The recording window `out_max * 2` is written at five sites with one three-line "for Ben to confirm" comment pasted four times. (The forced phase needs no guard: it has at most `out_max + 1` samples.) | One named limit, documented once; one comment per derivation. Passing a precomputed limit into the kernel is R4 and hoists an exact integer product: needs the owner's ruling on §5. | Readability | R4 | open | Q-3. | C-N08 |
| SC-10 | `structure.py:359-377` vs `484-499` | `step_scalars` re-inlines the 16-line restoring-force ladder of `effective_displacement`; the docstring (357, naming `step`) admits it. | Compile `effective_displacement` and call it in place of `(clamp + beyond * ratio2)` in line 500: same operands, same grouping, bit-identical (verified); Python callers (`response.py:715`, `structure.py:401`) go through the dispatcher. | Readability | R3 | open | K-4 (ladder inlined branch for branch: still branch for branch inside the helper). | C-10 |
| SC-11 | `structure.py:223, 308, 319`; `tools/sweep_jc.py:335` | The portal-frame participating mass `(L + h * 4 / 3) * m'` is written four times with identical grouping, plus the same derivation comment at `structure.py:153, 220, 293` and `sweep_jc.py:332`. `structure.py:297` and `300-303` group differently and stay as written. | Extract Function `portal_frame_mass(...)`, used only at the four identically grouped sites. | Readability | R3 | open | S1 mutation guards the sweep site. Rule fit is weak (a one-line repeat); a single-definition improvement. | C-35 (part) |
| SC-12 | `loads.py:9-15, 148-158, 182, 229, 285, 351, 361, 373`; `response.py:612-622, 659, 824, 870, 900`; `trace.py:19-20, 72-74, 113-114, 182-184`; `coupling.py:7`; `data_format.md:141`; viewer `PHASE_NAMES` | Load phases have three vocabularies (delay/transit, ramp/history, forced), 0-based codes against 1-based prose ("phases 1-2"), and `loads` yields bare 0/1 whose meaning only `trace.py` defines; `response.py:659` relies on the two coinciding. "Ramp" also names the force interpolation. | Define the phase constants once and import them (R1); `PHASE_HISTORY` → `PHASE_FORCED` and the prose to transit / forced / free decay (R0, renames). Codes 0/1/2 stay; labels in the viewer and `data_format.md` at the bump. | Readability | R1 | open | `PHASE_FREE_DECAY` is never produced by `loads`; it belongs with the consumers. Imports in `export.py:28`, `test_trace.py:160-166, 257`, `test_export.py:29, 173, 470-478`. | C-09, C-44 |
| SC-13 | `structure.py:8-10, 17, 410, 433, 458`; `coupling.py:3-24, 120`; `response.py:12, 23-39, 57, 130-131, 146, 385-387`; `loads.py:19, 272-273, 315`; `moc.py:20, 25, 29` | Module docstrings claim boundaries the code does not keep (`structure` "knows nothing about fluid coupling" yet `jc_params` removes the core fluid mass; `coupling`'s docstring describes `response`'s kernel) and lean on "Stage 5", "Session V.1" and NOTES.md section titles instead of stating the model. | Rewrite to the actual boundary; drop stage/session labels; state facts in Notes. Keep the before/after magnitudes at `response.py:385-387` with a source other than NOTES.md. | Readability | R0 | open | Rests on style §1.2 (the guide has no module-boundary rule). | C-40 (part) |
| SC-14 | `loads.py:144-229` (rule at 176-181, 199-204, 205-210, 218-222, 223-228; breaks 183, 186) | `_schedule` (complexity ~14) writes one index-advance-with-column-wrap rule five times; the `min(j, u2)` vs `j` difference never matters because `j <= u2` holds at every copy (verified). | Extract Function `_next_index(i, j, u1, u2)` (integer only); optionally split into two walks that return the post-loop `(ib, jb)`, including the no-break case and the `jb > u2` clamp. | Readability | R3 | open | K-5, D-8. | C-08 |
| SC-15 | `loads.py:144, 182, 229`; consumers `284-296`, `350-363` | `_schedule` yields tuples of 5 and 7 slots told apart by `item[0] == 0`; slot meanings live only in the docstring. | Two NamedTuples (one per item kind). Splitting the walk instead carries D-8 state across and is R2. | Readability | R1 | open | K-5, D-8 (`test_trace.py:62-68` pins the error ordering). | C-08 |
| SC-16 | `moc.py:403-530` (even 471-502, odd 503-529) | `moc.step` is two different half-grid updates behind a bool; the even half alone does five things; 15 parameters, ~66 lines. | Extract Function into two `@njit` halves (and the mean-velocity sum, loop moved verbatim); `step` keeps the dispatch. The two `d_f` lines differ (different taps) and stay verbatim in their halves. | Readability | R3 | open | K-1 (helpers: same speed). Calling the halves from the kernel directly would be R4 and break the parity probe that patches `moc.step` (`test_differential.py:1148-1166`). D-24 (odd tap). | C-04, C-05 |
| SC-17 | `structure.py:174-184`, `238-250`, `227-234` / `322-329`; `coupling.py:143-153`; calls `response.py:258-268, 416-428, 455-464` | `lumped_params` (9) and `jc_params` (11) share nine parameters, called positionally; the 8-line `SdofParams(float(...), ...)` return is written twice; `JunctionCoupling.__init__` takes 8. | Introduce Parameter Object (span; supports) and Extract Function for the `SdofParams` build. Plain field access only: no "total mass" property (`jc_params` groups the mass three ways). `JunctionCoupling` needs its own grouping, and its two flags wait for the public API session. | Readability | R3 | open | Test call sites: `test_differential.py:276, 769, 797, 819, 1107-1109`; `test_trace.py:201, 318, 356`; `test_fraction_profile.py:225, 229`. | C-17, C-18 |
| SC-18 | `docs/style.md:14, 20`; charter ruling 1; kernel signatures | `docs/nomenclature.md`, on which the symbol rule and the code-to-VBA map rest, does not exist; no kernel symbol is licensed, and the rename sessions have no table to work from. | Write `docs/nomenclature.md`: every code name (not only kernel symbols and exported keys) with meaning, SI unit and VBA name. | Readability | R0 | open | Charter rulings 1 and 3: before any rename. | C-24 |
| SC-19 | `structure.py:70-86`; `moc.py:80-81, 449-450, 496-502`; `response.py:778`; `trace.py:16-17, 31-34, 77, 107, 123-125, 155`; `export.py:71, 370, 372`; `data_format.md:73, 75, 150`; viewer `:290` | Four misleading names: `fric_acc` is a velocity step (m/s), not an acceleration; `ratio2` is the style guide's own counter-example; `DAMPING_A` is a low-pass filter weight, and its `_A` collides with half-grid A; `d_f` is the full junction force, not an increment. | Rename Field / Variable (internal: renames session; kernel parameters with the parameter objects; `meta.params` keys and the `d_f` frame column at the bump, with the viewer). | Readability | R0 | open | — | C-30, C-45 |
| SC-20 | `structure.py:114-118, 160, 225-226, 312, 317, 508, 510`; `response.py:590, 835, 879, 903, 917, 961, 977`; `moc.py:215`; `loads.py:182, 229, 285, 351` | Bare literals with meaning: `9.81`, `/ 100`, the `0.000001` friction dead zone, the `solve_poly` relaxation/iterations/tolerance, the 10 refinement passes, the `0.01` free-decay threshold, `n < 3`, `kind == 1`, phase tags 0/1. | Replace Magic Literal with module-level constants of the same literal type, named in place, each citing its source (D-20, D-21, D-4). Bit-identical in both modes (verified); in compiled code use a module-level int, not a class attribute. | Readability | R1 | open | D-4, D-20, D-21 (preserved quirks: the constant names them, the value stays). Cross-module constants need `make clean-cache`. | C-34 |
| SC-21 | `structure.py:56, 405`; `moc.py:15, 420`; `trace.py:12-16, 80, 91, 101-103, 144, 333`; `export.py:60, 158, 271-298, 374`; `response.py:16, 130, 163, 187`; `coupling.py:16, 44`; `loads.py:12-24, 126` | "substep" is spelled `sub_step`, "sub-step" and `substep`; bare "step" also means substep (`step_qty` counts substeps per sample, `step_index` indexes substeps). | Rename to `substep`… (internal: renames session; `step_qty` keyword, `params.step_qty` and `frames.sub_step` keys: bump, with the viewer). | Readability | R0 | open | 26 test references. | C-N17 |
| SC-22 | `structure.py:416-418, 449`; `response.py:118-119, 269, 583, 601, 630, 634, 830, 855-857, 937-941`; `trace.py:15, 77, 351` | "Applied" names three things: `f_applied` (unbalance plus junction force), `max_applied_force` (peak of the unbalance alone), and the trace's "forces applied". The unbalance force has six names (`forces`, `samples`, `flat`, `f`, `f_u`, `F_FU`). | One name for the unbalance force, another for the sum (internal: renames; `max_applied_force`, `f_unbalance`: bump). | Readability | R0 | open | `max_applied_force` is a key in the frozen `tests/fixtures/`: any mapping must keep them readable. | C-26 |
| SC-23 | `response.py:139, 250, 407, 536-545, 640, 764`; `trace.py:19, 23, 73`; `export.py:120-122, 277`; `tools/sweep_jc.py:367-369`; `histories.py:1-6` | "history" is the input force history, the recorded response, a load phase, the recording window, and in the sweep columns `history_peak/_mean/_rms` (forces in N, next to pressure columns from the same history). | Rename the locals (renames); `PeakResponse.history` and the sweep columns at the bump; "recording window" in prose. | Readability | R0 | open | `data_format.md:254-256` already says `history_*` are forces. | C-43 |
| SC-24 | `loads.py:120-128, 164-227, 283-305`; `response.py:251, 255, 408, 412, 528, 631-674, 814-831`; `moc.py:160-298, 375, 405`; `structure.py:90, 115-122` | Names that say how a value was computed or what the VBA called it: `unb`, `fh`, `u1`, `u2`, `ib`, `jb`, `jbmax`, `frac`, `one_minus`, `split`, `base`, `m`, `a_dt`, `interp_fraction*`, `vav_divisor`, `solve_poly`, `var_a..c`, `len_val`, `error_val`, `flat`, `offsets`, `scalars`, `rec`, `off`, `tot_ind`, `out_max`, `h` (18 lines in the JC entry). | Rename per the nomenclature (renames session; kernel parameters with the parameter objects; `ratio2` key at the bump). `column` is a good name and stays. | Readability | R0 | open | Viewer reads `D.frac` (`viewer.src.html:403, 418`). ~58 test references. | C-27, C-36, C-37, C-38 |
| SC-25 | `moc.py:77, 412-413, 480, 500, 529`; `response.py:644, 652, 744, 816, 901`; `trace.py:126-127, 139-140, 156-159`; `export.py:101, 117-118, 155, 249-251, 374-375, 387-390`; `geometry.py:43-44` | Counts use `_qty`, `n_` or bare plurals, never `_count`; `pivot` is a cell count in `grid_size` and a node index in `step`; `n_cells` counts A nodes plus B cells. | Rename to `_count` / `_index` (internal: renames; exported keys and sweep columns: bump, with the viewer). | Readability | R0 | open | Snapshot adapter maps (`test_review_snapshot.py:119-124`) absorb internal renames. | C-28 |
| SC-26 | `moc.py:92, 122, 139, 386-388, 437-444, 455`; `loads.py:78, 99, 117-131`; `structure.py:91`; `response.py:122, 141, 526`; `trace.py:19, 23, 47, 105, 127, 176, 186`; `data_format.md:78, 86, 105-106, 140, 161, 216-222, 271` | First lines and field descriptions give VBA names or expressions (`pipeSegQTY`, `dacayFactor`, `unballanceStepQTY`, `outMax`, `totInd`, `vAv`) instead of the model quantity and its unit; `out_max` is never described as a quantity anywhere. | Rewrite first lines in model terms with units; VBA names and line numbers to Notes. In `data_format.md` only the meaning column changes (tests parse the key column and headings). | Readability | R0 | open | — | C-40, C-41 |
| SC-27 | `response.py:344-355, 366, 390-395, 431-448, 501`; `moc.py:331-334, 395-399`; `coupling.py:156, 162` | **Report only.** The junction-coupling flags are validated at three layers: `fraction_profile` twice with the same message, `parity` at the entry, `vav_denominator` only inside `vav_divisor`, which the short-pipe path never reaches; the docstring (366) says it raises. | None now: public API session (ruling 5, flag validation at the entry as a recorded deviation). | Readability | R0 | open | Ruling 5. | C-12 |
| SC-28 | `response.py:120-124, 534-545, 640, 742, 897-898, 982-983` | **Report only.** `output_type` selects the return shape and the unit of `PeakResponse.history` (m, m/s or m/s²); values above 3 give an all-zero history, negative values `None`, silently. | None now: public API session. | Readability | R0 | open | — | C-12 |
| SC-29 | `response.py:161-176, 272-288, 305-326, 468-489`; `structure.py:242`; `tools/cases.py:36, 76, 138, 166`; `tools/sweep_jc.py:382` | **Report only.** Public keywords and the `meta.inputs` echo use VBA or abbreviated spellings (`fluid_densty`, `nat_freq`, `dynamic_fric`, `step_qty`, `restrain_freq_ratio`). | Change Function Declaration in the public API session; internal `jc_params` names in the renames session. | Readability | R0 | open | `fluid_densty` is a key of the frozen fixtures (`extract_fixtures.py:72, 154`). | C-31, C-N21 |

## Supporting Python — Design

| id | file:line | finding | proposed refactoring | sev | risk | status | constraint / notes | R.1 |
|---|---|---|---|---|---|---|---|---|
| SP-01 | `geometry.py:239-247, 276-281`; `tools/export.py:51-56`; `tools/bench.py:149-153`; `tools/sweep_jc.py:327-331, 366` | The solver's set-up (`dt`, portal height, grid, short-pipe test) is re-derived in five places outside the solver, with raw uncast keyword values; `tools/export.py` writes `1.0 /` where the solver writes `1 /` (same bits, different text). | Extract Function in the core, in two layers so no call is added or reordered: `dt` + height; then grid + short-pipe (after `jc_params` / `decay_factor`). `peak_response` never calls `grid_size` and must not start to. Cast as the solver does. | Design | R3 | open | K-6 (set-up order, D-9/D-12). Q-5 (`1.0` vs `1`). Test copies (`test_review_snapshot.py:136-140` may be meant as an independent check). | S-06 |
| SP-02 | `geometry.py:239-250, 274-281`; `trace.py:136-164`; `export.py:12-13, 29, 356` | `Trace` does not record the portal height or celerity it ran with, so `geometry` re-runs the solver's set-up from `trace.inputs["physical_length"]` etc., and `export` (whose docstring says it touches no solver) reaches set-up code through it. A keyword rename breaks it loudly (KeyError, tests), not silently. | Record portal height and celerity in `Trace` (ruling 7, public API session); correct the `export` docstring either way. | Design | R3 | open | `test_trace.py:322` pins the `inputs` key set. | S-35, S-09 |
| SP-03 | `tools/cases.py:27-30`; `tools/bench.py:93-96`; `tools/profile_delta.py:41-45`; `tools/golden_report.py:21-33`; `tools/sweep_jc.py:99, 144` | Two tools import `tests/test_golden.py` for the fixture loaders (and `profile_delta` imports `test_differential` for flags); two more read the fixture files with their own paths. A refactoring of a test module can break a tool. | Move Function: the loaders to a non-test module that tests and tools import. | Design | R3 | open | `CLAUDE.md`: the golden tolerance is recorded in `tests/test_golden.py`, so `RTOL` stays there (or is re-exported with the owner's agreement). No style rule requires this; a design judgement. | S-01 |
| SP-05 | `export.py:164-186, 323-328, 391-392, 436-446, 486-491, 498-500`; `tools/cases.py:186-195` | `to_trace_dict` / `to_sweep_dict` run `git` in a subprocess and read the clock by default; `sha` is `True` / `None` / `str` with three behaviours; the package holds a default `tools/export.py` command line that `tools/cases.py` repeats (with a different `note`). | Split Phase: the builders take `sha` and `created` as values; the tool resolves them. Public API session (ruling 4). | Design | R3 | open | `test_review_support.py:173-180` patches `export.git_sha` / `export.created_utc` by module attribute: the tool must keep calling them that way. | S-09, S-33 |
| SP-06 | `tools/bench.py:271-288, 302`; `tools/sweep_jc.py:410-434` | `git`, `cpu_model` (nesting 4) and the dirty test are token-for-token copies in two tools. | Extract Function into one shared tools module (two real users). `export.git_sha` is a different contract (full sha / `None`, timeout) and stays out. | Design | R3 | open | K-8 (tools are run as scripts; the module must import via the `tools/` path). | S-23 |
| SP-07 | `tools/cases.py:91-94`; `tools/bench.py:139-143` | The forced substep count is computed in two tools by two formulas (`int` vs `math.floor`, `np.size` vs `shape[0]`, bench inlines `transit_delay`), though the solver counts the flattened array. Equal for every input used today (verified). | Extract Function in `loads`, keeping `int(unb * step_qty)` verbatim (mutation E8); bench calls `transit_delay`. | Design | R3 | open | — | S-06 |

## Supporting Python — Readability

| id | file:line | finding | proposed refactoring | sev | risk | status | constraint / notes | R.1 |
|---|---|---|---|---|---|---|---|---|
| SP-08 | `tools/sweep_jc.py:321-404` | `run_case` (84 lines) does pipe and history set-up, solver set-up, 35 row keys, both timed runs and the derived columns. | Split Phase: case columns, solver runs, result columns. Pass `mass_total`, `d2`, `p_peak_a` on, do not recompute. Column order is fixed by `dict.fromkeys(COLUMNS)`. | Readability | R3 | open | Mutations S1 (335), S3 (398). | S-15 |
| SP-09 | `tools/sweep_jc.py:456-506` | `run` mixes case selection, file naming (471), the coverage print, the process pool with progress, the CSV write and the summary. | Extract Function per job. `ProcessPoolExecutor` stays a module-global lookup (`test_review_support.py:307` swaps it); `_worker` stays module-level; the file name is reproduced character for character. | Readability | R3 | open | K-8. | S-03 (part) |
| SP-10 | `tools/sweep_jc.py:619-689, 692-777, 780-847` | The three plot functions repeat the `_select` / `_series` block (8 lines), panel labels and the figure finish; nesting 6 / 5 / 4. Only the select block and `savefig`/`close` are verbatim; the rest differs in arguments. | Extract Function for the select block and the figure finish, with the style and layout passed in. | Readability | R3 | open | Ungated (no test runs `plot`): ruling 3 allows renames only (Q-4). | S-19 |
| SP-11 | `tools/sweep_jc.py:879-892, 912-929` | `amplitude_table` (depth 5) rebuilds two row selections inside the band and solver loops though they depend only on `variant`; `ratio_table` is depth 4. | Hoist the two selections (`_select` is pure and order-preserving: R2), then Extract Function for the pair matching (R3, own commit). | Readability | R2 | open | `write_doc` output is ungated (Q-4). | S-24 |
| SP-12 | `tools/bench.py:156-257` | `build_cases` is 102 lines around an 8-parameter closure and seven near-identical keyword calls. | Module-level table of case specs; Extract Function for the description string. Case order, ids and description strings must stay identical. | Readability | R3 | open | Ungated (Q-4). | S-20 |
| SP-13 | `tools/bench.py:407-453`, `694-695` | `worker_main` selects the RSS or the timing job by `args.worker`, tested again five times inside. | Replace Flag Argument with Explicit Functions; the shared header stays in the dispatcher; the mode label still reaches `run_cases`. | Readability | R3 | open | Ungated (Q-4). | S-21 |
| SP-14 | `tools/bench.py:509-570, 602-655`; `tools/golden_report.py:77-82` | `print_table` (62 lines) and `readme_section` (54) mix building and printing; the 6-line column printer is in two tools (blank-line placement differs). | Extract Function; one shared `print_columns(header, rows)`, blank lines left to callers; README bytes unchanged. | Readability | R3 | open | Ungated (Q-4). | S-22, S-23 |
| SP-15 | `trace.py:250-268, 296-312`; `response.py:666, 719-735` | `trace.build` takes 15 parameters, four of them the buffers `allocate` returned, plus an untyped `jc=None`; `celerity` and `ext_qty` mean something only with `jc`. | Introduce Parameter Object: buffers (returned by `allocate`; a NamedTuple keeps the tests' positional indexing), run fields, JC grid (`None` for lumped). Passing the buffers whole to the kernel is SC-02 (R4). | Readability | R3 | open | — | new |
| SP-16 | `trace.py:205-247` | `check_memory` checks the limit and also searches for the smallest fitting stride, only to word the error. | Extract Function for the search (238-242 verbatim). (The parameter-object half of the original finding was dropped: 5 and 6 parameters are within the limit.) | Readability | R3 | open | — | S-N13 |
| SP-17 | `export.py:359-396, 391-392, 498-500` | `to_trace_dict`'s 38-line literal mixes run parameters, outputs and provenance; all five outputs are checked under the one label `"outputs"`. | Extract Function for the params and outputs blocks (key order and check order kept). Provenance: two one-line helpers, because the sweep keys are not adjacent (`git_sha`, `tier`, `created_utc`). Per-output labels change an error message: own commit. | Readability | R3 | open | — | S-26 |
| SP-18 | `export.py:405-433` | `_sweep_value` (complexity ~14 by ruff's count) interleaves the int and float paths through one shared string branch. | Shared prelude, then guard-clause dispatch to string / int / float helpers, each keeping today's check order and messages. | Readability | R3 | open | — | S-27 |
| SP-19 | `histories.py:276-302, 350-378, 452-495` | Each generator ends in a 21-line `_history(...)` call listing all 15 keys, most `None`; the four-line prelude repeats. | Give `_history` `None` defaults; Extract Function `_sampled_axis(..., decay_s)` taking `decay_s` (in `step_noise` it comes from `f_ref`, and the `p_cap` guard must stay ahead). `_held_step` is optional (2 lines). | Readability | R3 | open | Mutations H1-H6. `canonical` untouched before the public API session. | S-18 |
| SP-20 | `geometry.py:116-196, 245, 251-258, 282-293` | `loop_layout` takes 8 positional parameters (five only copied into the result); `lumped_grid` returns `(pipe, pivot)` and the caller swaps them by hand into `loop_layout(pivot, pipe)`. | Keyword arguments at both calls (R0/R2), then a grid NamedTuple and Split Phase for the centreline (151-170 verbatim, E3b). | Readability | R3 | open | `LoopLayout` fields are exported: unchanged. | S-16 |
| SP-21 | `tools/export.py:42, 59-61` | `estimate_bytes` has no caller anywhere; the `JSON_BUDGET_MB` docstring points the reader at it. | Remove Dead Code; point the docstring at `export_trace_every`. | Readability | R0 | open | — | S-30 |
| SP-22 | `tools/profile_delta.py:72-121, 124-181, 217-252, 269-280` | The `run_*` functions compute and print Markdown in one body; `main` writes the JSON on two paths; `cell(x, signed)` duplicates `fmt`. | Split Phase: compute rows, then print; one JSON write (a small R2 in `main`). | Readability | R3 | open | Ungated (Q-4): compare output by hand. | S-28 |
| SP-23 | `tools/profile_delta.py:50, 51, 94-97, 114, 144, 184-207` | The three JC golden ids are hand-listed (bench uses row numbers, cases a filter); `summary()` is indexed by position (`[1]`, `[2]`); column lists are hand-written subsets of `SWEEP_COLUMNS`; `OUTPUTS` is unused. | Use `PeakResponse` field names; take the ids from the fixtures; delete `OUTPUTS`. Deriving the column lists by suffix does not reproduce them (`f_peak_jc`, `ratio_*`, order): keep explicit lists or accept the reorder. | Readability | R1 | open | Ungated (Q-4). | S-N01 |
| SP-24 | `tools/golden_report.py:36-91` | `main` loads the cache, builds rows, finds the first failure and prints. | Extract Function (row, first failure, shared printer from SP-14). | Readability | R3 | open | Ungated (Q-4). | S-28 |
| SP-25 | `tools/review_baseline.py:119-154` | `collect` has complexity 12 (ruff) with two nested helpers and no stated reason. | Extract Function for the ruff and radon passes; module-level helpers (`owner` takes `rows`). | Readability | R3 | open | Ungated (Q-4). | new |
| SP-26 | `tools/extract_fixtures.py:267-403`, `273-277` | `extract_curve_10in`: 135 lines, complexity 23, 73 statements, four banner-commented phases; its parameter loop repeats `read_params` without the numeric check. | Split Phase into read / validate / write helpers. Reusing `read_params` adds a check on the failure path: keep the loop with a one-line reason, or accept it. Check with a scratch `--out`, never `tests/fixtures`. | Readability | R3 | open | Ungated (Q-4). | S-14 |
| SP-27 | `tools/extract_fixtures.py:201-264` | `extract_example` validates, builds the case (testing `solver == "pressure"` twice) and writes in one loop. | Extract Function for the case record; write and manifest stay in the caller. The pressure branch is live (SP-32). | Readability | R3 | open | Ungated (Q-4). | S-14 |
| SP-28 | `tools/sweep_jc.py:12-13, 142, 986-990` | The generated report text and a verbose print hard-code the run constants (`stepQTY = 40`, 1237 m/s, 0.5 %, 195 GPa, 1000 Hz, `restrainFreqRatio = 1`, `gap = 0`, `1.33`) that are module constants or `histories.P_CAP_FACTOR`. | Format the constants (`:g` to keep the text; a named Pa→GPa factor). The module docstring stays literal. | Readability | R1 | open | Ungated (Q-4): compare `docs/jc_sweep.md` by hand. | S-25 |
| SP-29 | `tools/cases.py:55-106, 142-148`; `tools/sweep_jc.py:296-309, 381-383`; `tests/test_golden.py:139-162` | `step_case(args)` and `step_name(args)` take the argparse Namespace; the solver keyword dict is built three ways, each handling the fluid keys differently. | `case_from_args` (already there) builds a step-case NamedTuple that `step_case` / `step_name` take. One kwargs builder waits for the public API session. | Readability | R3 | open | — | S-10 |
| SP-30 | `export.py:123-138, 379-387`; `tools/sweep_jc.py:244-261, 296-309`; viewer `:795-798, 856-860`; `data_format.md:57, 312`; `trace.py:335` | One quantity, several keys: the five maxima are `max_*` in the trace and `f_eq_*`, `x_peak_*`… in the sweep (the viewer keeps a mapping table); generator parameters are `f_osc_hz` in the CSV and `f_osc` in `histories`; the solver is `"peak_response"` in `meta.solver` and `"lumped"` elsewhere. | One name per quantity at the bump; keep the viewer's `stem + '_' + solver` pattern. The reference block's names come from the frozen fixtures, so the translation moves into `tools/cases.py`; it cannot vanish. | Readability | R0 | open | Bump; ruling 12. | S-32, S-41 |
| SP-31 | `export.py:84-112`; `trace.py:162`; `histories.py:101-111`; `data_format.md:32` | **unclear.** Unit suffixes are uneven: `sample_freq` beside `f_osc_hz`, `p_cap` (Pa) beside `p_cap_bar`, `mass_per_unit_len` beside `fluid_area_m2`. Every unsuffixed key is SI, which style §2 and `data_format.md:32` allow; a stricter rule is a policy choice. The suffix list at `data_format.md:32` lacks `_m2` and `_kg` (a doc fix either way). | If the owner wants "every dimensional key carries its unit": rename at the bump. | Readability | R0 | open (unclear) | Q-7. `mass_per_unit_len` is a key of the frozen fixtures. | S-43 |
| SP-33 | `geometry.py:1, 10-13, 101-104, 200-203`; `trace.py:1, 32`; `export.py:1, 6, 54, 149`; `histories.py:1`; `tools/sweep_jc.py:2, 11`; `tools/export.py:1, 20`; `tools/cases.py:1, 10, 199, 267`; `tools/build_viewer.py:13`; `tools/profile_delta.py:1, 24`; `data_format.md:33-34, 96` | Docstrings and docs carry session tags and pointers to `docs/architecture.md` / NOTES.md, and put deviation ids in summaries. The content is already stated in place in most cases: the fix is to remove pointers and tags. | Drop session tags and pointers; ids to Notes. Leave out generated report text (`sweep_jc.py:981, 986`) and argparse help (`cases.py:192`, `profile_delta.py:263`). | Readability | R0 | open | — | S-49 |
| SP-34 | `trace.py:38-44, 131-133`; `geometry.py:45-50`; `export.py:252-257`; `moc.py:108, 113-116`; `data_format.md:251` | "cell" is both the B cell and every interleaved grid point (cells `2 c dt` long, "consecutive cells" `c dt` apart); "segment" is a MoC cell (`_seg_qty`) and a loop piece (`geometry.segments`). **`data_format.md:251` and the `moc.grid_size` docstring (`moc.py:108`) are wrong:** `pipe_seg_qty` is the whole column (ends, legs, span), not "cells between the elbows". | A distinct word for the interleaved grid point; node for A, cell for B; `_seg_qty` → cell counts; correct the two docstrings now (R0); exported keys (`segments`, `n_cells`, `*_seg_qty`) at the bump. | Readability | R0 | open | Viewer reads `g.segments`, `meta.n_cells`. | S-38 |
| SP-35 | `geometry.py:7, 52-67, 87-88, 157-170, 185-190`; `export.py:261-262`; `data_format.md:112-125`; viewer `:365, 489` | The layout describes four drawn corners and legs 1/2; nothing says which corner is elbow A (where `f_a` acts) or B. The field name `leg_height_2` does not say outlet (the docstrings do). | State the elbow A/B mapping in the `LoopLayout` docstring once confirmed; rename the leg heights to inlet/outlet at the bump. | Readability | R0 | open | Q-6. | new |
| SP-36 | `trace.py:42-44, 131-133, 325, 368`; `geometry.py:42, 199-213`; `moc.py:160-298`; `data_format.md:104` | One per-cell value is "moving fraction" (the exported key), "interp fraction" (the docstrings describing that key) and "weighting of the mass acceleration" (`moc.py:161, 193`); "interp" names the computation and is the VBA spelling. | Use "moving fraction" throughout; `frac_a/_b` → `moving_fraction_a/_b`; `interp_fraction_*` renamed (kernel parameters with the parameter objects). `fraction_profile` is a related concept (and a public flag). | Readability | R0 | open | `legacy_port.interp_fraction_*` frozen. | new |
| SP-37 | `tools/sweep_jc.py:125, 323-326, 386-387, 398-399` | `run_case` keeps `p` and `h` (a `History`, where elsewhere `h` is the portal height) live for ~65 lines; `p_peak_a` is a force (pressure × area) that reads as "pressure at elbow A"; `mass` (125) is a mass per unit length. | Rename Variable (e.g. `pipe_props`, `pressure_history`, `peak_pressure_force`, `mass_per_unit_len`); keep `(p.od_mm / 1000) ** 2` verbatim. | Readability | R0 | open | — | S-47 |
| SP-38 | `tools/cases.py:59, 62`; `tools/sweep_jc.py:64, 122-127, 386`; `tools/export.py:73, 91, 97-98, 127`; `tools/bench.py:424, 506, 531-532, 630`; `tools/review_snapshot.py:58`; `tools/review_support.py:52` | Unit factors are bare (`/ 1000`, `1e5`, `1e6` for three different conversions, `/ 1024`); `cases.py:62` writes `1e5` though `sweep_jc.py:64` names `BAR` (without a comment). | Replace Magic Literal in place, same literal type, one name per meaning; `od_mm / 2000` stays one literal with a comment; `1e5` keeps its position in `cases.py:62` (E5). | Readability | R1 | open | Bench and review tools ungated (Q-4: constants are not renames). | S-44, S-45 |
| SP-39 | `tools/sweep_jc.py:64-71`; `histories.py:63-67` | Fixed-input constants have no meaning/unit/source comment (`CELERITY = 1237.0`, `STEP_QTY = 40`…); `P_CAP_FACTOR = 1.33` gives "the owner's convention" but no basis; `1.33` is also bare at `sweep_jc.py:142, 989`. | Add the comments; ask the owner for the basis of 1.33 (style §6). | Readability | R1 | open | Q-8. | S-45, S-N18 |
| SP-40 | `histories.py:320-321, 397-398, 510-512, 561, 569` | `decay_cycles = 10.0`, `decay_fraction = 0.8` are repeated in three signatures and `0.5 * cap` twice; sibling defaults are already named. | Named constants with the same values (`canonical`'s visible defaults are unchanged). `p_noise_rms = 1.0` is a placeholder without effect: a comment, not a constant. | Readability | R1 | open | — | S-45 |
| SP-41 | `data_format.md:113`; `histories.py:338-340` | `data_format.md:113` says the outlet leg is "one cell shorter" without qualification; with the default profile both legs are equal (pinned by `test_geometry.py:117`); only the legacy profile shortens it. The `step_sine` docstring's "(default 0.2)" sits where `decay_fraction`'s default (0.8) would go (ambiguous, not wrong). | Correct `data_format.md:113`; reword the docstring. | Readability | R0 | open | — | new |
| SP-42 | `trace.py:76-81, 230-234, 250-253, 305-308, 331-332, 351`; `response.py:85-91, 550-597, 666, 701-704, 728-731, 783-786, 819`; `test_trace.py:384` | Frame arrays and their constants are named for their dtype (`tr_f`, `tr_i`, `N_FLOAT_COLUMNS`, `f`, `ints`); `F_FU`, `F_FFRIC`, `F_DF` are decoded only by the mapping in `build`. | Rename to what they hold; the kernel parameters are renamed positionally (R0), grouped with SC-02 (R4). | Readability | R0 | open | `make clean-cache` after (trace constants compile into the kernel). | C-36, S-42 |

## Nits (not verified)

| id | file:line | finding | proposed refactoring | risk | status |
|---|---|---|---|---|---|
| N-01 | `moc.py:179-188, 215-224, 251-260, 286-295` | `elif` after `return` in the four profile ladders. | Plain `if`. | R2 | open |
| N-02 | `moc.py:335-343` | The `pivot <= EXT_QTY` guard is nested inside the profile choice. | Guard first. | R2 | open |
| N-03 | `response.py:813-817`; `structure.py:360, 367, 482-483, 506`; `moc.py:472` | Comments that restate the line or stand in for a name. | Delete or rename. | R0 | open |
| N-04 | `response.py:120-131`, `139-146` | `PeakResponse` fields documented twice, differently. | Keep `Attributes`. | R0 | open |
| N-05 | `moc.py:101`; `loads.py:85`; `response.py:195` | `celerity` described two ways. | One description. | R0 | open |
| N-06 | `response.py:734`; `trace.py:311` | `trace.build` receives the module constant `moc.EXT_QTY` as an argument. | With the column object (SC-02). | R0 | open |
| N-07 | `geometry.py:204-213`; `moc.py:344-350` | `geometry` repeats the tabulation loop of `interp_fractions` to bypass its guard. | Split validation from tabulation. | R3 | open |
| N-08 | `geometry.py:237` | `interleave` imported inside a function though the module imports from `trace`. | Top-level import. | R0 | open |
| N-09 | `tools/review_snapshot.py:29-59` | Compare and write modes share `main`; its twin has two functions. | Extract. | R3 | open |
| N-10 | `tools/build_viewer.py:70-79, 115-121` | `build` reads files and the plotly version itself; `main` reads the bundle twice. | Pass inputs in; read once. | R3 | open |
| N-11 | `tools/export.py:108-121` | "Option overrides the CSV value" written four ways. | One helper. | R3 | open |
| N-12 | `tools/cases.py:132` | `add_source_arguments` reads the fixtures while building the parser. | Pass defaults in. | R3 | open |
| N-13 | `tools/review_support.py:64-73` | The history comparison is written twice. | One helper. | R3 | open |
| N-14 | `export.py:200-202, 214-215, 236-237, 317-318` | Four non-finite checks with their own messages. | One helper, messages kept. | R3 | open |
| N-15 | `tools/cases.py:220-259` | `reference_block` builds near-identical 7-key records in two loops. | One record helper. | R3 | open |
| N-16 | `data_format.md:60` | `meta.outputs` is "for the viewer's self-check", but the viewer reads no `meta.outputs` key. | Correct the text. | R0 | open |
| N-17 | `tools/bench.py:108`; `tests/test_differential.py:812`; `tests/test_review_snapshot.py:46` | `LEGACY_FLAGS` defined three times. | With the flag redesign. | R1 | open |
| N-18 | `tools/cases.py:52, 281`; `tools/export.py:75` | Library helpers end the process with `SystemExit`. | Raise; convert in `main`. | R2 | open |
| N-19 | `export.py:51` | `SCHEMA_VERSION` beside `SWEEP_SCHEMA_VERSION`. | `TRACE_SCHEMA_VERSION`. | R0 | open |
| N-20 | `histories.py:148-151` | `peak`, `p_min`, `mean`, `rms`: one carries a `p_` prefix. | One convention. | R0 | open |
| N-21 | `export.py:357, 377` | `jc` and the key `"capped"` are not predicates. | `is_…` (key at the bump). | R0 | open |
| N-22 | `export.py:80-81, 130-142` | Column abbreviations `od_mm`, `thk_mm`, `ke_peak_*`, `daf_*`, `f_eq_over_LD2_*` (mixed case). | Bump. | R0 | open |
| N-23 | `export.py:358`; `histories.py:173, 464-470, 594` | One-letter names (`p`, `w`, `f`) over wide scopes. | Rename. | R0 | open |
| N-24 | `data_format.md:188, 211` | `tier` is a string in `meta` and an int in the columns. | Bump. | R0 | open |

Charter ruling 8 (R.1b) rejects every Nit; they are listed for completeness and keep the
status open only because this list asks the owner nothing about them.

## Refuted (dropped)

| merged id | finding | why it fell |
|---|---|---|
| SC-07 | "The trace frame layout is defined in several modules; a reader cannot learn it from one." | `trace.py:10-47` and the constants at 76-81 define the whole format in one place. The A/B interleave is written twice (a compiled loop in `_trace_frame`, a slice in `trace.interleave`) and the 2-line position/kind rule twice (`trace.build`, `geometry.lumped_grid`); both under the 5-line rule. |
| SP-04 | "The sweep CSV format is split and its four readers type cells by their own rules." | For every cell the writer produces, every reader gets the same value; `tools/cases.py` already types through `export._sweep_value`; `sweep_jc.COLUMNS is export.SWEEP_COLUMNS` is test-pinned. Routing the plotting reader through `_sweep_value` would change behaviour (non-finite cells, all 72 columns typed). |
| SP-32 | "The format carries a pressure solver that no longer exists." | `legacy_port.get_pressure_response` reproduces `example_pressure` in the default golden suite (`test_golden.py:70, 175, 185, 245-246`); `test_export.py:312-330` pins the entry. It becomes dead only when Stage 6 removes `legacy_port.py` (Q-9). |

## Recorded constraints

What `docs/architecture.md` and `DEVIATIONS.md` say about the code behind the findings. A
constraint explains the code; it does not close the finding.

* **K-1, the kernel signatures.** Architecture "Stage 5": "Signatures take floats, ints,
  bools and 1-D float64 arrays only", and `moc.step` has "no per-cell helper calls ...
  compiled whole". Tested on a toy kernel shaped like `_integrate_kernel` (SDOF step with
  the gap ladder and friction, a MoC-like column of four arrays updated in place, `d_f`
  passed in and returned; 400 000 substeps; Numba 0.68.1; scratch scripts, not committed):
  * **Exactness.** Every variant (NamedTuple `SdofParams`, NamedTuple column, compiled
    helpers for the gap ladder, the friction, the peak tracker and the two half-grid
    updates) gave the same `float.hex()` results, the same history bytes and the same final
    arrays as the flat version, compiled and with `NUMBA_DISABLE_JIT=1`, on four cases
    including a zero, a negative and a huge gap.
  * **Speed** (min of 25 interleaved runs, 60 / 300 cells): flat 26.1 / 77.1 ms; flat
    arguments with compiled helpers 0.99x / 0.99x; NamedTuples unpacked once at the top of
    the kernel 0.99x / 1.00x; the column NamedTuple passed to the per-substep column
    function and read by attribute there 0.99x / 0.99x. **Slower:** the column NamedTuple
    passed on from the per-substep function into a further call (unpacked inside it and its
    arrays forwarded, or handed to two half-grid helpers): **1.46x / 1.16x**. The cost is per
    call, so it shrinks with the column length but does not vanish.
  * So the flat signatures are a choice, not something Numba forces, with one rule for the
    parameter-object commits: unpack the column tuple once per kernel call, or pass it at
    most one call deep per substep. The toy is not the solver; `tools/bench.py` and the
    snapshot decide each real commit. Keyword-only parameters stay unavailable between
    compiled functions (style §3).
* **K-2, the coupling interface.** "The Python-level `Coupling.coupling_force` interface
  stays for callers and tests" (Stage 5). There are no callers outside the tests; ruling 2
  supersedes it (SC-01).
* **K-3, the two set-ups.** "The two set-ups are *not* merged into one function with flags"
  (module table, `response.py`). SC-06 and SP-01 extract shared helpers and keep two set-ups.
* **K-4, exactness.** "Exactness notes": `0.0 + F` / `0.0 − R` differ from `F` / `−R` in the
  sign of an exact zero; the gap ladder is inlined branch for branch; `half_dt = dt / 2`;
  the ramp tables hold the same doubles. "Stage 5": `float(flat[i])` and
  `float(moc.step(...))` keep the state on Python floats in pure mode (D-23 overflow
  semantics). These fix how SC-03, SC-04, SC-08 and SC-10 must move code; none requires the
  duplication.
* **K-5, laziness and D-8 / D-19.** The schedule generators run only as `_integrate`
  consumes them; D-8's `IndexError` must surface at the first ramp sample, after every
  phase-1 sample (`test_trace.py:62-68`). D-19's per-phase parity is an offset fixed per
  sample. SC-08, SC-14 and SC-15 must keep both.
* **K-6, set-up order.** The JC set-up runs `jc_params` and `decay_factor` before
  `grid_size` and the short-pipe test; D-9 (`rhoC = 0` rejected at the set-up) and D-12
  (complex seed raises `TypeError` at the set-up) fix which error a degenerate input
  raises. SP-01 and SC-06 must not add or reorder calls.
* **K-7, recorded quirks behind literals.** `0.000001` is D-20, `0.01` (on `x * xZero`, m²)
  is D-21, `n < 3` is D-4, the `2N - 1` divisor is D-17, the odd-substep tap is D-24. SC-20
  names them; it does not change them.
* **K-8, tools are scripts.** The process pool pickles its worker under the module name
  `sweep_jc`; `test_review_support.py` swaps `sweep_jc.ProcessPoolExecutor` and patches
  `export.git_sha` / `export.created_utc` by attribute; tools share code by putting
  `tools/` on `sys.path`.
* **K-9, frozen fixtures.** `tests/fixtures/` holds `max_applied_force`, `fluid_densty`,
  `mass_per_unit_len` and the reference `solver` / `output_names` values; any rename at the
  bump keeps a mapping that reads them.

`docs/architecture.md` is out of step with the code in places (the data flow still shows
`_integrate` calling `coupling_force` under `np.errstate`; the module table still lists
`restoring_force` and `structure.step` as the interface). It is outside the review scope and
needs a pass after the refactoring.

## Possible defects (for the owner, not acted on)

Reported by the reviewers and verifiers; not part of this review and not acted on.

1. `response.py:897-898` and `831`: the forced-phase `_record` and trace `rec` have no
   `tot_ind <= out_max * 2` guard, and compiled Numba does not bounds-check. The SC-09
   verifier argues the forced phase has at most `out_max + 1` samples, so this cannot
   overrun; worth an assertion?
2. `response.py:247, 404, 540-545`: `output_type` above 3 returns an all-zero history and a
   negative value returns `None`, silently (SC-28).
3. `response.py:366, 431-448`: an invalid `vav_denominator` is accepted on the short-pipe
   path, though the docstring says it raises (ruling 5 covers the fix).
4. `structure.py:297-299, 320`: the JC rigid mass `L·(m' − ρA) + …` is zero or negative when
   `ρA ≥ m'`; nothing guards it before it divides.
5. `response.py:902-903`: if `x` is exactly 0 at the end of the forced phase, free decay runs
   no samples whatever the velocity (`x * xZero = 0`). Related to D-21, not recorded there.
6. `structure.py:361/368`, `485/491`: the clamp test uses `abs(gap)` while `excess = ax - gap`
   uses the signed gap; a negative gap takes inconsistent branches. Not in DEVIATIONS.md.
7. `structure.py:118`: `error_val / var_a` divides by zero when EI = 0.
8. `moc.py:153-154`: `decay_factor` is said to give "a half-life of one pipe transit", but it
   is applied once per even update (every `2 dt`): by the formula the half-life is
   `2 L / c`, two transits of length `L`. Docstring or intent?
9. `moc.py:529`: the odd-substep junction tap sits one cell inward (recorded as D-24).
10. `tools/golden_report.py:62-66`: `next(...)` without a default raises `StopIteration` when
    a case fails on a NaN.
11. `tools/sweep_jc.py:502`, `993-994`: an empty case selection divides by zero; a CSV where
    every lumped run failed makes `max([])` raise.
12. `tools/sweep_jc.py:858-862`: `_band` files `f <= 0` under "> 16 Hz".
13. `export.py:418`: an int column whose CSV text is `"10.0"` raises, though the float `10.0`
    is accepted.
14. `tools/build_viewer.py:77-79`: the provenance comment names the installed plotly version
    even when `--plotly` supplies another bundle.
15. `tools/cases.py:94`, `tools/bench.py:143`: the forced-substep estimate is not checked
    against the length of the `loads` schedule (which uses the `CLng` overlap); possibly off
    by one at a rounding boundary.

## What is good and should be left alone

* **The module graph.** No import cycles; `structure` imports nothing internal; `moc` knows
  nothing of the structure; nothing in `src/` imports `tools/` or `tests/`.
* **Small pure set-up functions:** `moc.grid_size`, `is_short_pipe`, `decay_factor`,
  `new_column`, `vav_divisor`; `loads.transit_delay`, `overlap_substeps`, `as_history_2d`;
  `structure.solve_poly`, `solve_portal_height`, `effective_displacement`;
  `response._trace_stride`, `_decay_test`, `_record`. Clean under the functions lens.
* **String flags never enter compiled code.** `vav_denominator` becomes an int and
  `fraction_profile` two arrays at set-up; `parity` a bool.
* **The exactness devices.** `float(...)` casts in the kernel, `half_dt`, the tabulated
  ramp, `0.0 + f`, the branch-for-branch ladder, quirk comments at the line (`n < 3  # D-4`).
  They look redundant and are not; refactorings carry them verbatim.
* **`trace.py`'s module docstring** states the frame convention, column layout, positions
  and the friction formula in one place (SC-07 fell on it).
* **The data-format contract.** `docs/data_format.md` is parsed by `tests/test_export.py`;
  `sweep_jc.COLUMNS is export.SWEEP_COLUMNS`; rows start as `dict.fromkeys(COLUMNS)`, so
  column order cannot drift.
* **The gate tools** (`tools/review_snapshot.py`, `review_support.py`, `golden_report.py`)
  and `tools/extract_fixtures.py`'s names, which copy workbook labels on purpose, are clean
  under the names lens.
