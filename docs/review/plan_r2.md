# Clean-code review — refactor plan (R.2)

Session R.2, 23 Nov 2026. Orders the findings of `docs/review/findings.md` into
single-refactoring commits. Nothing here has been started. The R.1 plan is kept as
`docs/review/plan_r1.md`; the charter's ruling 3 accepted *its* order, which this plan follows
except where "Where I would change the order" says otherwise.

Every commit: one refactoring, named with its risk class; expressions move verbatim (charter
rule 2); `make lint` and `make test-both` (snapshot and supporting-code checks in both
modes); revert on red. Every session: `-m slow` and `tools/bench.py`. After any edit to
`moc.py`, `structure.py` or `trace.py`, wipe the Numba cache before trusting a result.

"Stop" marks a point where the charter (ruling 10) asks the session to write the proposal to
a file under `docs/review/` and wait for the owner.

## 0. Removals that ruling 2 already decided (proposed first; see "order")

| # | commit | finding | risk |
|---|---|---|---|
| 0.1 | Remove `structure.restoring_force`, `structure.step`, `structure.State`; point their tests at `effective_displacement` / `step_scalars`, assertions unchanged | SC-01 | R3 |
| 0.2 | Remove `JunctionCoupling.column()` (no caller) | SC-01 | R0 |
| 0.3 | Remove `Coupling` protocol and `coupling_force` (both classes); point the tests at `moc.step` — **stop** for Q-1 (three assertions with no counterpart) | SC-01 | R3 |
| 0.4 | Remove the dead `jc.d_f` write-back (`response.py:707-708`) | SC-01 | R2 |

`NoCoupling` and `KIND` stay until 3.4: they still select the kernel path.

## 1. Names

| # | commit | finding | risk |
|---|---|---|---|
| 1.0 | Write `docs/nomenclature.md` (every code name: meaning, SI unit, VBA name) and the rename table `docs/review/renames.md` — **stop** | SC-18 | — |
| 1.1 | Load phases: `PHASE_HISTORY` → `PHASE_FORCED`; prose to transit / forced / free decay, phases by name not number (`loads`, `response`, `trace`, `coupling`) | SC-12 (R0 part) | R0 |
| 1.2 | "substep" one word, internal names and prose (`step_index`, `unb_steps`, `I_SUB_STEP`, docstrings); `step_qty` keyword and `sub_step` key wait for the bump | SC-21 | R0 |
| 1.3 | `SdofParams` fields `fric_acc`, `ratio2`; `moc.DAMPING_A`; internal `d_f` outside kernel signatures | SC-19 | R0 |
| 1.4 | Unbalance force vs applied force: one name each (internal) | SC-22 | R0 |
| 1.5 | "history": input force history, recorded response, recording window (internal locals and prose) | SC-23 | R0 |
| 1.6 | `loads` locals: `fh`, `u1`, `u2`, `ib`, `jb`, `imax`, `jbmax`, `jb_to`, `unb`, `frac`, `one_minus`, `split`, `base`, `m` | SC-24 | R0 |
| 1.7 | `structure` locals and `solve_poly` (`var_a..c`, `len_val`, `error_val`); `response` locals (`h`, `p`, `flat`, `offsets`, `scalars`, `rec`, `off`, `tot_ind`, `out_max`) | SC-24 | R0 |
| 1.8 | Counts and indices: `_count` / `_index` (internal; `pivot` as count vs index) | SC-25 | R0 |
| 1.9 | Moving fraction: "interp fraction" → "moving fraction" in prose; `interp_fraction_*` functions (not kernel parameters) | SP-36 | R0 |
| 1.10 | Grid vocabulary: node / cell / grid point in prose; correct the `moc.grid_size` docstring on `pipe_seg_qty` | SP-34 (internal part) | R0 |
| 1.11 | Trace frame arrays and constants in `trace.py` (`tr_f`, `F_FU`, `N_FLOAT_COLUMNS`…), kernel parameters renamed positionally | SP-42 | R0 |
| 1.12 | `sweep_jc.run_case` locals (`p`, `h`, `d2`, `p_peak_a`, `mass`) | SP-37 | R0 |

Renames in `tests/test_review_snapshot.py` and `tests/test_review_support.py` go into their
adapter sections only (charter rules 5 and 6).

## 2. Constants, units and control flow

| # | commit | finding | risk |
|---|---|---|---|
| 2.1 | Phase constants defined once and imported (loads' tags, `response.py:659`) | SC-12 | R1 |
| 2.2 | Core constants: gravity, percent, friction dead zone (D-20), `solve_poly` relaxation / iterations / tolerance, refinement passes, free-decay threshold (D-21), `n < 3` (D-4); one commit per module | SC-20 | R1 |
| 2.3 | `histories` default constants (`decay_cycles`, `decay_fraction`, step fraction of cap); comment on `p_noise_rms` | SP-40 | R1 |
| 2.4 | Tool constants: comments for `sweep_jc` inputs; `P_CAP_FACTOR` basis (Q-8); unit factors named in place, one name per meaning | SP-39, SP-38 | R1 |
| 2.5 | `_schedule`: Extract Function `_next_index` | SC-14 | R3 |
| 2.6 | `_schedule` items as two NamedTuples | SC-15 | R1 |
| 2.7 | One schedule walk: `unbalance_force` = `fa - fb` of the elbow generator; drop the double walk and the length check | SC-08 | R3 |
| 2.8 | `portal_frame_mass` for the four identically grouped sites | SC-11 | R3 |

## 3. Parameter objects

**Stop** before 3.1: write the parameter-object groups to `docs/review/parameter_objects.md`
(ruling 10). Rule from the toy test (findings K-1): unpack the column tuple once per kernel
call, or pass it at most one call deep per substep. Kernel-signature names change here
(ruling 3), with 1.x having renamed everything else.

| # | commit | finding | risk |
|---|---|---|---|
| 3.1 | `effective_displacement` compiled and called from `step_scalars` | SC-10 | R3 |
| 3.2 | `step_scalars` takes `SdofParams` whole; the kernel takes it whole | SC-02 | R4 |
| 3.3 | Column NamedTuple built by a `moc` set-up function, replacing `JunctionCoupling`; `moc.step` takes it; `trace.build` reads it | SC-02, SC-01 (rest), N-06 | R4 |
| 3.4 | `is_fluid_coupled` bool replaces `KIND`; the empty column built once; `NoCoupling` goes | SC-04 | R4 |
| 3.5 | Trace-buffer NamedTuple returned by `allocate`, passed to the kernel and `build` | SC-02, SP-15 | R4 |
| 3.6 | `trace.build`: run-field and JC-grid parameter objects | SP-15 | R3 |
| 3.7 | Set-up parameter objects for `lumped_params` / `jc_params`; one `SdofParams` builder | SC-17 | R3 |
| 3.8 | Shared entry-point prefix (NamedTuple) and trace-meta builder (key order kept) | SC-06 | R3 |
| 3.9 | Split `_integrate`: flatten, prepare trace, column arguments, result | SC-05 | R3 |
| 3.10 | Core set-up helpers for the tools and `geometry` (two layers, casts as the solver) — Q-5 | SP-01 | R3 |
| 3.11 | Forced-substep count in `loads`, used by `cases` and `bench` | SP-07 | R3 |

## 4. The single substep

**Stop** before 4.1: write the substep design to `docs/review/substep.md`.

| # | commit | finding | risk |
|---|---|---|---|
| 4.1 | `moc.step` split into two compiled halves (and the mean-velocity sum); `step` keeps the dispatch | SC-16 | R3 |
| 4.2 | Extract the column-advance helper (with its `float(...)` cast) | SC-03 | R3 |
| 4.3 | Extract the peak-tracker helper | SC-03 | R3 |
| 4.4 | Extract the frame-record helper (friction expression verbatim; arguments grouped) | SC-03 | R3 |
| 4.5 | Recording window as one named limit — after Q-3 | SC-09 | R4 |

Each loop keeps its own `f_applied` line, `rec` test, `f_max` update and `x_zero` reset.
`tools/bench.py` after each of 4.1-4.4, not only at the session end: this is where the toy's
slow pattern would appear.

## 5. Supporting modules and tools

Gated (the support checks run them):

| # | commit | finding | risk |
|---|---|---|---|
| 5.1 | `estimate_bytes` removed; docstring corrected | SP-21 | R0 |
| 5.2 | Shared `git` / `cpu_model` tools module | SP-06 | R3 |
| 5.3 | Fixture loaders out of `tests/test_golden.py` (tolerances stay there unless Q-11 says otherwise) | SP-03 | R3 |
| 5.4 | `step_case` / `step_name` take a step-case object built by `case_from_args` | SP-29 | R3 |
| 5.5 | `sweep_jc.run_case` Split Phase | SP-08 | R3 |
| 5.6 | `sweep_jc.run` Extract Function per job | SP-09 | R3 |
| 5.7 | `histories`: `_history` defaults; `_sampled_axis(decay_s)` | SP-19 | R3 |
| 5.8 | `geometry.loop_layout`: keyword arguments; then grid NamedTuple; then `_nominal_centreline` | SP-20 | R2, R3, R3 |
| 5.9 | `trace.check_memory`: extract the stride search | SP-16 | R3 |
| 5.10 | `export.to_trace_dict`: params and outputs blocks; provenance helpers | SP-17 | R3 |
| 5.11 | `export._sweep_value`: guard-clause dispatch | SP-18 | R3 |

Ungated (no test runs them). Charter ruling 3 allows **renames only** here, so these stay
open unless the owner lifts the ruling or a check is added (Q-4): SP-10, SP-11, SP-12,
SP-13, SP-14, SP-22, SP-23, SP-24, SP-25, SP-26, SP-27, SP-28. If lifted, each is one
commit in the order listed in findings, with a by-hand before/after diff of the output.

## 6. Public API, data format, docstrings, lint limits

**Stop** before 6.1: write the public interface to `docs/review/public_api.md`.

| # | commit | finding | risk |
|---|---|---|---|
| 6.1 | Flag validation at the entry, a recorded deviation (DEVIATIONS row, pinning test) | SC-27, ruling 5 | — |
| 6.2 | Form of the junction-coupling flags and of `output_type` | SC-27, SC-28 | R4 |
| 6.3 | Public keywords (`fluid_densty`, `step_qty`, `nat_freq`, …), `PeakResponse.history`, `max_applied_force` | SC-29, SC-21, SC-22, SC-23 | R0 |
| 6.4 | `to_*_dict` take `sha` / `created` as values; the regen template owned by `tools/cases.py` | SP-05 | R3 |
| 6.5 | `Trace` records portal height and celerity (ruling 7); `geometry` reads them | SP-02 | R3 |
| 6.6 | Schema bump: one name per quantity, suffix policy (Q-7), counts, `segments`, leg heights, `d_f`, `sub_step`, `fric_acc`, `ratio2`; viewer, `data_format.md`, stored exports rewritten, CSV header only (rule 6); committed sweep CSVs by script (ruling 12) | SP-30, SP-31, SP-34, SP-35, SC-19, SC-21, SC-25 | R0 |
| 6.7 | Docstrings: module boundaries and history labels; first lines in model terms; pointers and session tags | SC-13, SC-26, SP-33 | R0 |
| 6.8 | Enforce the 6-argument limit and the lint settings | style §3 | — |

After the refactoring: the two approved output fixes (ruling 11).

## Where I would change the order, and why

1. **Ruling-2 removals first (group 0), before the nomenclature.** Group 1 would otherwise
   rename `coupling_force`, `State`, `restoring_force` and the `d_f` write-back only for
   group 3 to delete them. The removals are decided (ruling 2) and small; done first, they
   shrink the surface the nomenclature and the rename table must cover. Only 0.3 waits on
   the owner (Q-1).
2. **Wrong documentation now, not in 6.7.** `data_format.md:113` (SP-41), `data_format.md:251`
   and `moc.py:108` (SP-34), `response.py:366` (SC-27) and possibly the `decay_factor`
   half-life (defect 8) state things the code does not do. Doc-only R0 commits cannot move
   a bit; leaving them wrong through four groups of refactoring is the larger risk. The
   style rewrite of docstrings stays in 6.7.
3. **`effective_displacement` (3.1) is independent** of the parameter objects and could go at
   the end of group 2; it is listed first in group 3 because it changes `step_scalars`, which
   3.2 changes again.
4. **The schedule refactorings (2.5-2.7) in group 2,** not group 5: they are control flow in
   pure Python, gated by the snapshot, and they remove the double walk before 3.9 splits
   `_integrate`, which would otherwise have to carry it.
5. **Bench inside group 4, per commit.** The toy shows the one parameter-object pattern that
   costs time (the column tuple passed two calls deep); in group 4 the helpers create
   exactly that call depth. A session-end bench would not show which commit did it.

## Questions for the owner

* **Q-1.** Removing `coupling_force` (0.3) leaves three assertions with no counterpart:
  `test_differential.py:783` (`type(d_f) is float`), `:802` (no negative zero), `:807`
  (`NoCoupling` returns `0.0`). Drop them (the charter needs your word), or restate them
  against `moc.step` / the kernel?
* **Q-2.** The R.1 lists are kept as `findings_r1.md` / `plan_r1.md`. The charter (rulings 3
  and 8) and `NOTES.md` still cite `findings.md` / `plan.md` for R.1's ids. Update those
  references to the `_r1` names, or do you want R.2 merged into the R.1 files instead?
* **Q-3.** SC-09 / 4.5 passes `out_max * 2`, an exact integer product, into the kernel
  precomputed. Does hoisting an exact integer count as an expression change under style §5?
* **Q-4.** Ruling 3 limits ungated tools to renames. Twelve readability findings (bench,
  profile_delta, golden_report, review_baseline, extract_fixtures, the sweep plots and
  report) need more. Lift the ruling for them with a by-hand output diff, add checks first,
  or leave them open?
* **Q-5.** `tools/export.py:51` writes `1.0 / (...)` where the solver writes `1 / (...)`.
  The two give the same bits for these inputs. May SP-01 switch it to the solver's form?
* **Q-6.** Which drawn corner of the expansion loop is elbow A (where `f_a` acts)? The inlet
  side run corner is the likely one; the code does not say (SP-35).
* **Q-7.** Unit suffixes at the schema bump: keep "SI unless suffixed", or "every
  dimensional key carries its unit" (SP-31, unclear)?
* **Q-8.** What is the basis of `P_CAP_FACTOR = 1.33` (a code allowance, a test-pressure
  ratio)? Style §6 asks for the source (SP-39).
* **Q-9.** `example_pressure` in the sweep reference block is reproduced only by the frozen
  `legacy_port.get_pressure_response`. Keep it after Stage 6 removes `legacy_port.py`?
* **Q-10.** Do you accept the order changes above (especially group 0 first and the early
  doc fixes)?
* **Q-11.** SP-03: may the golden tolerances move to the new loader module with a
  re-export from `tests/test_golden.py`, or must they stay defined there (`CLAUDE.md`)?
