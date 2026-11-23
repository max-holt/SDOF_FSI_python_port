# Clean-code review — refactor plan

Session R.1, 16 Nov 2026. Orders the findings of `docs/review/findings.md` into commits.
Nothing here has been started.

Every commit below is one refactoring, named in its message with its risk class, and is
gated as the charter says (`make lint`, `make test-both`; revert on red). Expressions move
verbatim. A session ends with `-m slow` and `tools/bench.py`. Ids are those of the
findings; "Q-n" refers to the questions at the end.

## The order, and where I would change it

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

## Before group 1

| # | commit | findings | risk |
|---|---|---|---|
| 0.1 | Write `docs/nomenclature.md`: symbol or name, meaning, unit, VBA name, for every kernel symbol kept and every name group 1 introduces | C-24 | R0 |
| 0.2 | Correct the two descriptions of what the grid count covers (`moc.py:108`, `docs/data_format.md:251`) | S-38 | R0 |

Needs Q-6. 0.2 is a docstring and a document line; it is here because group 1 names the
quantity.

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

Each row is one commit, or one per module where the rename crosses more than about ten
files. 1.7 and the `step_scalars` part of 1.1 touch compiled code: cache wipe, both modes.

## Group 2 — constants, units, control flow (R1, R2)

| # | commit | findings | risk |
|---|---|---|---|
| 2.1 | One named phase pair, used in `loads`, `response`, `trace`, the tests | C-09 | R1 |
| 2.2 | One named coupling-kind pair, module-level ints, used in `coupling` and the kernels | C-09 | R1 |
| 2.3 | ~~Unit factors in `pressure.setup` and `pump_boundary`~~: removed (R.1b) | C-33 | R1 |
| 2.4 | `/ 100` percent of critical in `structure` | C-33 | R1 |
| 2.5 | `9.81`; the friction dead band; the Newton tolerance, relaxation and pass counts | C-34 | R1 |
| 2.6 | Free-decay threshold `0.01`; the result capacity `out_max * 2` named once | C-34, C-N08 | R1 |
| 2.7 | Valve-closed threshold; the two friction clamps; the legacy `n < 3` limit | C-34 | R1 |
| 2.8 | Derivation comments for the pure-number coefficients | C-35 | R0 |
| 2.9 | Supporting code: conversions and convention values in gated expressions (`cases.py:59-62`, `sweep_jc.py:122-127`, `332`, `383`, `histories.py`) | S-45 | R1 |
| 2.10 | `rho_c == 0` guard to the first statement of the coupling constructor | C-19 | R2 |
| 2.11 | Trace request as one optional object in `_integrate` | C-23 | R2 |
| 2.12 | Small control-flow nits: `valve_closure`, `_schedule` attribute access, re-coercion | C-N03, C-N04, C-N06 | R2 |

2.6 and 2.8 need Q-4 (2.3 and Q-5 went with the pressure solver). The charter's mutation tests showed that a regrouped
set-up value can hide from a peak, so 2.3 to 2.7 are one literal per commit and the
snapshot runs in both modes each time.

## Group 3 — parameter objects (R3, R4)

Decide Q-2 first: whether `coupling_force`, the `Coupling` protocol, `structure.step`,
`State` and `restoring_force` stay as tested interfaces. The shape of the objects depends
on it.

| # | commit | findings | risk |
|---|---|---|---|
| 3.1 | `step_scalars` takes `SdofParams`; the kernel receives it whole | C-10, C-01 | R4 |
| 3.2 | Fluid-column NamedTuple (four state arrays, two weight arrays, counts, `rho_c`, decay factor, divisor, area) built by `JunctionCoupling`; `moc.step` and the kernel take it; a named constructor for the empty column with today's literal types | C-01, C-03, C-04, C-N07, C-N13 | R4 |
| 3.3 | Trace-buffers NamedTuple returned by `trace.allocate`, taken by the kernel and `trace.build` | C-01, C-15, S-08 | R4 |
| 3.4 | Run-settings NamedTuple (`dt`, sub-steps per sample, capacity, `output_type`, parity flag) | C-01 | R4 |
| 3.5 | NamedTuple return of the kernel | C-01 | R4 |
| 3.6 | Grid description passed to `trace.build` in place of the coupling object; annotate it | C-14, S-08 | R3 |
| 3.7 | Span, restraint and fluid objects for `lumped_params` / `jc_params`; shared return block | C-17 | R3 |
| 3.8 | Grid and fluid-constant objects for `JunctionCoupling.__init__` | C-18 | R3 |
| 3.9 | ~~`pressure` column NamedTuple~~: removed (R.1b) | C-16, C-N02 | R3 |
| 3.10 | Entry points: extract the sample grid and the trace wrapper; keyword arguments in the short-pipe fallback | C-11 | R3 |
| 3.11 | One set-up query in the core (sub-step, portal height, grid), used by `response` | S-06 (core half) | R3 |

3.1 to 3.5 are the commits the bench matters for. After each: cache wipe, both modes,
snapshot; `tools/bench.py` at the end of the session and a revert of the session's last
commit if the kernel rows move beyond noise. K-1 in the findings records the toy result
that makes this worth trying; it is not evidence for the real kernel.

## Group 4 — the single sub-step (R3, R4)

| # | commit | findings | risk |
|---|---|---|---|
| 4.1 | Compile `effective_displacement`; `step_scalars` calls it for the ladder | C-10 | R4 |
| 4.2 | Split `moc.step` into the two half-grid functions; the parity test stays at the callers | C-04, C-N22 | R4 |
| 4.3 | Junction-force functions out of the half-grid updates, into the coupling layer | C-05 | R4 |
| 4.4 | One compiled column advance (parity, half-grid update, junction force) called by the kernel twice and by `coupling_force` | C-03 | R4 |
| 4.5 | Friction and stick derivation as a compiled function beside `step_scalars` | C-14 | R3 |
| 4.6 | Peak trackers extracted | C-02 | R4 |
| 4.7 | Trace frame: scalar-row writer and column writer; the kernel's recording branch calls one function | C-15, C-02 | R4 |
| 4.8 | `_trace_frame` and its writers moved to `trace.py` | C-14 | R3 |
| 4.9 | The sub-step body as one function called from the forced loop and the free-decay loop; the `f_applied` forms stay in the loops | C-02 | R4 |
| 4.10 | `_integrate` split into prepare, run, build result | C-06 | R3 |
| 4.11 | `loads`: per-sample helpers shared by the two generators; `_schedule` items as NamedTuples; the three identical index blocks extracted | C-07, C-08 | R3 |
| 4.12 | Flattening of the schedule moved into `loads`; the run-time cross-check of the two walks removed | C-22, C-07 | R3 |
| 4.13 | ~~`pressure`: the shared characteristic solve~~: removed (R.1b) | C-N01 | R3 |

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
| 5.10 | `histories.py`: `_history` defaults, noise scaling extracted, per-kind functions behind `canonical` | S-17, S-18 | R3 |
| 5.11 | `tools/cases.py`: spec record for the step case; sweep-document helpers to their own tools module; `reference_block` record | S-10, S-29 | R3 |
| 5.12 | `tools/sweep_jc.py`: grid and pipe properties, row computation and report as three modules behind the same script; `run_case` parts; provenance tuple | S-03, S-15 | R3 |
| 5.13 | Remove the `sys.path` inserts and private loaders the earlier commits made unnecessary | S-02 | R3 |
| 5.14 | Dead code and small items: `estimate_bytes`, unused constants, `build_viewer.build` parameters, `review_snapshot.main` | S-30, S-34, S-N01, S-N12, S-N22 | R0-R3 |
| 5.15 | Ungated tools, if at all: `bench.py`, the plots and report, `extract_fixtures.py`, `golden_report.py`, `profile_delta.py` | S-13, S-14, S-19 to S-22, S-24, S-25, S-28 | R3 |
| 5.16 | `vba_compat` helpers copied into a live module with a pinning test; imports repointed (`_vba_semantics.py`, the module this row first named, was removed in R.1b) | C-13 | R3 |

5.3 and 5.4 are the preparation for the schema bump: with one table per document the bump
is an edit of two tables. 5.12 must keep `tools/sweep_jc.py` a runnable script and the
worker picklable (K-11). 5.16 needs Q-1 and is placed here only because it is independent
of everything else. S-11 and S-36 are not listed: they change output on edge inputs (Q-8).

## Group 6 — public API, data format, docstrings, lint limits

| # | commit | findings |
|---|---|---|
| 6.1 | Form of `output_type` and of the three junction-coupling flags; one validation at the entry; both flag paths kept | C-12, C-N05 |
| 6.2 | Keyword-only entry points; public keyword renames (the `get_pressure_response` alias went with the pressure solver, R.1b) | C-11, C-31, C-N21 |
| 6.3 | `PeakResponse` and `Trace` field renames; `Trace` column sub-record | C-26, C-43, S-08 |
| 6.4 | Public signatures of `histories` and `export`; `__all__` trimmed | S-17, S-33, C-N10, S-N02 |
| 6.5 | **The schema bump**, one commit: exported keys and CSV columns renamed through the two tables, viewer keys with them, `tests/review_support/` rewritten with `--write`, values shown unchanged | S-31, S-32, S-37 to S-43, S-46 to S-49, C-25, C-28, C-30 |
| 6.6 | Docstrings: numpy sections, units, shapes; VBA references and ids to Notes; first lines in model terms | C-40, C-41, S-49, S-50 |
| 6.7 | Annotations | C-42, S-51 |
| 6.8 | Lint limits in `pyproject.toml` (PLR0913 at 6, C901 at 10, the statement and nesting targets), with a one-line reason on each function that still misses | style 3 |

6.1 changes error behaviour on bad flag values (Q-3) and needs a `DEVIATIONS.md` row.

## Questions for the owner

* **Q-1.** `NOTES.md` and `CLAUDE.md` say Stage 6 removes `vba_compat.py` with
  `legacy_port.py`; `docs/architecture.md` lets live modules import `clng`, `vba_floor`,
  `mod_dbl` and `vba_2d` from it. Confirm the removal, so that C-13 (literal copies in a
  live module; `_vba_semantics` itself was removed in R.1b) is done in this review and not
  at Stage 6.
* **Q-2.** `JunctionCoupling.coupling_force`, the `Coupling` protocol, `structure.step`,
  `State` and `restoring_force` are called only by tests. Keep them as thin wrappers over
  the shared compiled functions, or remove them and re-point the tests?
* **Q-3.** An unknown `vav_denominator` is accepted on a short pipe and when `rho_c == 0`.
  May the public API session validate all flags at the entry, as a recorded deviation?
* **Q-4.** Derivations the code does not hold: the factor 2 in `out_max * 2`; the `0.5` in
  `0.5 * dynamic_fric * 9.81 * dt`; `4 / 3` on the portal-frame height; `12` and
  `0.5 + 1.5 * (...)` in the end-fixity formula; `4 * celerity * dt` in the grid size.
* **Q-5.** ~~In `60 * 60` (`pressure.py:177`, `179`), which factor is seconds per minute and
  which minutes per hour?~~ Moot: `pressure.py` was removed in R.1b.
* **Q-6.** Vocabulary for `docs/nomenclature.md`: elbows A / B as inlet / outlet or kept as
  A / B; "node" and "cell" for the two half-grids and one word for an interleaved entry;
  "transit" and "history" for the two forced phases; `sub_step` or `substep`.
* **Q-7.** The ungated tools (5.15): refactor without a gate, add characterisation checks
  first, or leave them as they are?
* **Q-8.** Two supporting fixes change output on edge inputs: `is_capped` taken from the
  kernel's count (differs for a stride above `step_qty`), and `size_in` no longer read from
  a directory name (a moved CSV exports a value where it exports null today). Wanted?
* **Q-9.** The charter allows only rename-forced edits in `tests/`. Groups 3 and 4 change
  call sites in tests that call `moc.step` and `jc_params` directly (`pressure.setup` and
  `initial_column` went in R.1b), and the test that patches `moc.step` to record the half-grid
  sequence. Are signature-forced edits covered?
* **Q-10.** `Trace` is returned to users. May its column fields move into a sub-record in
  the public API session, or must the flat attributes stay?
* **Q-11.** The fourteen suspected defects listed at the end of the findings: which, if
  any, should be looked into, and by whom?
