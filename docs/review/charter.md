# Clean-code review of the solver — charter

Set up on 16 Nov 2026 on branch `review/clean-code`. From session R.1b (23 Nov 2026) the
rest of the review works on branch `claude/solver-review-charter-oe8gtr`, which carries the
whole history of `review/clean-code`. The solver is verified against the VBA
but hard to read; later sessions review and refactor it. Every refactoring leaves the
results bit-identical. `docs/style.md` is the target; `docs/review/baseline.md` is where
the code started.

## Scope

Widened on 16 Nov 2026 (session R.0b) from the solver modules to two areas.

* **The solver core:** `moc.py`, `structure.py`, `coupling.py`, `loads.py`, `response.py`.
  `pressure.py` and `_vba_semantics.py` were in scope until session R.1b removed them with
  the unused `GetPressureResponse` port.
* **The supporting Python:** `trace.py`, `export.py`, `histories.py`, `viz/geometry.py` and
  `tools/`.
* **The data format** (`docs/data_format.md`: the `trace` and `sweep` documents and the
  sweep CSV columns) is in scope. Names in exported files change once, in a single schema
  bump late in the review (the public API session, below); until then every exported file
  stays byte-identical.
* **The viewer** (`docs/viewer/viewer.src.html`) is in scope only for the keys it reads from
  a data file. Its JavaScript structure is not reviewed.
* **`tests/`:** a test may change how it calls a function, never what it asserts (ruling,
  R.1b; it widens the R.0 "mechanical edits only, the ones a rename forces"). A test whose
  subject is removed goes only with the owner's word (as for the pressure solver, R.1b).
* **Untouched:** `legacy_port.py`, `vba_compat.py`, `legacy/`, `tests/fixtures/`.

Two sessions are fixed points for the rulings in `docs/style.md`:

| session | what changes there, and not before |
|---|---|
| renames | internal names, the VBA spellings among them |
| public API | public keywords, the form of the junction-coupling flags and of `output_type`, the names in exported files (the schema bump), and the 6-argument limit becomes enforced |

## Change rules

1. One refactoring per commit, named in the commit message (with its risk class).
2. No arithmetic change of any kind inside a structural commit: operand order, grouping,
   literal type (`2` versus `2.0`), `x**2` versus `x*x`, hoisting, summation order.
   Expressions move verbatim.
3. If a gate fails, revert the commit. Do not debug forward.
4. Behaviour changes are out of scope. They go to `NOTES.md` as questions for the owner.
   The owner has approved three, each to be made as a recorded deviation (a DEVIATIONS.md
   row and a test that pins it), never inside a refactoring commit: flag validation at the
   entry (public API session), and the two edge-case output fixes after the refactoring
   ("Rulings" below).
5. `tests/review_snapshot/` is never regenerated to make a refactoring pass; only an
   approved behaviour change (a DEVIATIONS.md row) rewrites it. A rename is absorbed in the
   adapter of `tests/test_review_snapshot.py` (`run_solver` and its field tables), nowhere
   else in that file.
6. `tests/review_support/` follows the same rule, with one planned rewrite: the schema bump
   changes the names inside the exported files and the CSV header, and that commit
   rewrites the stored exports and the stored CSV with `tools/review_support.py --write`.
   The values must not change in it: the history documents stay untouched, and the commit
   shows that the stored CSV differs in its header line only. A rename before the bump is
   absorbed in the adapter section of `tests/test_review_support.py`.

## Rulings (owner, recorded in session R.1b, 23 Nov 2026)

The answers to the questions of `docs/review/plan.md` and of `NOTES.md` (R.0b). They bind
the rest of the review; `docs/style.md` carries the ones about the code.

1. **Vocabulary.** The two staggered half-grids stay A and B (`pressure_a`, `velocity_b`);
   the elbows are A and B; the load phases are *transit*, *forced* and *free decay*;
   "substep" is one word (`substep`, `substep_count`). `docs/nomenclature.md` is written
   from this before any rename.
2. **Readability over abstraction.** No protocol, base class, enum or wrapper layer unless
   it has two real users today. The `Coupling` protocol, `coupling_force` (with
   `NoCoupling` and the unused `JunctionCoupling.column`) and the other wrappers that only
   tests call (`structure.step`, `State`, `restoring_force`) are removed; their tests are
   pointed at the code that actually runs (`moc.step`, `structure.step_scalars`,
   `structure.effective_displacement`, the solver entry points) with their assertions
   unchanged. Fluid coupling on or off is a plain flag, not a kind code. Parameter objects
   (NamedTuples, `docs/style.md` §3, §4) are not a layer in this sense.
3. **The plan's order is accepted** (`docs/review/plan.md`, "The order"): the nomenclature
   before any rename; kernel-signature names change with the parameter objects; the phase
   and kind constants open the constants group; tools without a check get rename-only
   edits.
4. **User-facing entry points** (for the keyword-only and the symbol rules) are the solver
   entry points of `response`, `histories.canonical` and the `export.to_*_dict` functions.
5. **Flags are validated at the entry** in the public API session, as a recorded deviation
   (an unknown flag value then raises on every path, the short pipe and `rho_c == 0`
   included, where today it is accepted silently there).
6. **Tests** may change how they call a function, never what they assert (scope, above).
7. **`Trace`** may gain a column sub-record in the public API session.
8. **Findings.** Every Design and Readability finding is accepted, except one whose
   proposed fix adds an abstraction layer that ruling 2 forbids: those are rejected with
   that reason. Every Nit is rejected. Applied in `docs/review/findings.md` (S-17 rejected).
9. **Reference platform.** The exact-equality checks (the snapshot, the supporting-code
   checks, the bitwise differential tests) are authoritative on the CI Linux runner and in
   this cloud environment. A failure on another machine with no code change is not
   evidence against a refactor.
10. **Approvals in files.** Where a later session is told to stop and show the owner
    something (the rename table, the parameter-object groups, the substep designs, the
    public interface), it also writes it to a file under `docs/review/`, so it can be
    reviewed outside the session.
11. **Two edge-case output fixes approved**, as recorded behaviour changes made after the
    refactoring: `is_capped` from the kernel's forced-sample count (S-11), and `size_in`
    no longer read from a directory name (S-36).
12. **Committed sweep CSVs at the schema bump** (`docs/sweep/*.csv`): the headers are
    renamed by a one-off script and every data row stays byte-identical.

## Rulings (owner, recorded in session R.3, 23 Nov 2026)

The renames session. The owner's answers to `NOTES.md` (R.2) and to the questions of the
second review (`docs/review/plan_r2.md`). They bind the rest of the review alongside 1-12.

13. **`vba_compat`.** `vba_compat.py` stays frozen and is imported as it is until Stage 6.
    Nothing replaces `_vba_semantics.py` (R.1 Q-1; C-13 is closed without a change).
14. **The friction `0.5`.** The `0.5` in the friction velocity step
    (`0.5 * dynamic_fric * 9.81 * dt`) is the share of the pipe's weight carried on the
    moving part. It goes into the derivation comments, for Ben to confirm (R.1 Q-4).
15. **Grid point.** An entry of the interleaved display grid (A node, B cell, A node, ...)
    is a "grid point" (the open half of R.1 Q-6). Node stays A, cell stays B.
16. **Fluid coupling** on or off is a plain boolean flag, as planned in `plan.md` 2.2. The
    load phase labels are still named constants (2.1).
17. **The 6-argument limit.** Keyword-only arguments count towards it. A user-facing entry
    point that still exceeds it after the public API session gets a recorded exception
    (`docs/style.md` §11).
18. **`histories.py`.** Every function in `histories.py` that a tool calls is a user-facing
    entry point (extends ruling 4).
19. **Pressure remnants.** The legacy port's own pressure tests and the pressure part of
    `tools/extract_fixtures.py` stay until Stage 6.
20. **Suspected defects.** The remaining suspected defects are not investigated in this
    review. The list stays in `docs/review/findings.md`, for the lead author.
21. **Kernel-signature names.** Where `plan.md` moves kernel-signature names to the
    parameter-objects group, `plan.md` is followed: `docs/nomenclature.md` proposes those
    names now, and they are applied then.
22. **The two reviews.** The independent review was run a second time by mistake (R.2).
    The first (R.1) stays the governing list: `docs/review/findings.md` and
    `docs/review/plan.md`. R.2 is kept as `findings_r2.md` and `plan_r2.md`; only what R.1
    lacks is brought across (its confirmed Design and Readability findings with no R.1
    match, unless the fix adds an abstraction layer or concerns a tool no test runs; the
    wrong-documentation fixes, done early; three order changes; the Numba rule for the
    parameter-object commits; the possible defects not in `DEVIATIONS.md`).
23. **Orphaned assertions.** The assertions orphaned by removing `coupling_force` are
    restated against `moc.step`. One that only asserts a property of the removed wrapper
    itself is dropped and listed in `NOTES.md` (extends ruling 6).
24. **Ungated tools** stay rename-only, and their findings stay open (ruling 3 confirmed).
25. **Exact integer products.** Precomputing an exact integer product such as
    `out_max * 2` is not an expression change. Rule 2 and `docs/style.md` §5 are about
    floating point.
26. **Elbow A** is the one the pressure wave reaches first: force A is applied at once and
    force B after the transit delay. It is the inlet side of the run.
27. **`P_CAP_FACTOR = 1.33`** is the sweep's peak pressure as a multiple of design
    pressure, set by the lead author on 22 Oct 2026. A comment asks Ben to confirm its
    basis.
28. **Units** stay "SI unless suffixed", in code and in exported names.

## Rulings (owner, on the rename table, session R.3, 23 Nov 2026)

`docs/nomenclature.md` is approved with the changes and answers below.

29. **Public, for the renames.** "Public" means the user-facing entry points only, as
    `docs/style.md` §2 defines them (rulings 4 and 18). Every other function without a
    leading underscore, and its parameters, is renamed in the renames session (Q-N1).
30. **`pivotSegQTY`** counts the cells from each end of the column to the elbow between leg
    and span: the portal-frame pivot is that elbow. `end_to_elbow_cell_count` (Q-N2).
31. **`jb_to`** is `transit_last_column`, with a "For Ben to review:" comment that the bound
    divides the transit delay in samples by the number of columns and that the walk exits
    earlier in every tested case. Nothing else changes (Q-N3).
32. **`outMax`** is `nominal_forced_sample_count` (Q-N4).
33. **The forced sample count in the kernel.** The first local (`n_samples`) becomes
    `forced_sample_count`; the second (`forced_samples`) stays as it is until plan group 4
    removes it (Q-N5).
34. **Elbows on the drawn loop.** Elbow A is the `run_start` corner, elbow B the `run_end`
    corner; the `LoopLayout` docstring says so (Q-N6).
35. **`history_type`** everywhere, for `kind` of a history (Q-N7).
36. **`celerity`** stays (Q-N8).
37. **`applied_force`**, not `external_force`, for `f_applied`: it includes the junction
    force, which is not external to the model.
38. **The two long exported column names** (`daf_*`, `f_eq_over_LD2_*`) are undecided and
    settled in the public API session; "DAF" is the paper's own term.

## Rulings (owner, session R.4, 24 Nov 2026)

The constants and control-flow session (plan group 2).

39. **Gate timing.** In the renames session commits were made while their gates were still
    running in the background, and the branch was pushed with half of them unfinished; two
    bad commits had to be rebuilt. From now on `make lint` and the compiled fast suite,
    the snapshot tests included, run and pass before each commit is made, and the
    pure-Python run (`NUMBA_DISABLE_JIT=1`) of a commit passes before the next commit is
    made. The branch is pushed only when every commit's gates are green.
40. **Plan 2.2 deferred.** The coupling kind as a plain flag changes the type of a kernel
    parameter (`_integrate_kernel`, `_trace_frame`), which is a kernel-signature change
    (R4). It moves to group 3, where the kernel signatures change anyway.
41. **Plan 2.15 approved** for session R.4 (R3: one schedule walk, the run-time
    cross-check of the two walks removed).
42. **Plan 2.15 reverted.** Made bit-identical in R.4, it slowed the compiled lumped path by
    about 20 % (golden r20, 0.177 s to 0.213 s on one host: the untraced run then builds
    both elbow-force lists and subtracts them). The owner chose to revert it and its
    cross-check removal; C-07 stays open.

## Gates

| when | gate |
|---|---|
| every commit | `make lint` |
| every commit | `make test-both` (cache wipe, fast suite compiled and with `NUMBA_DISABLE_JIT=1`) |
| every commit | the snapshot test; `make test-both` runs it in both modes. Alone: `make clean-cache && .venv/bin/python -m pytest -q tests/test_review_snapshot.py`, then the same with `NUMBA_DISABLE_JIT=1` (2 s each) |
| every commit | the supporting-code checks, `tests/test_review_support.py`; `make test-both` runs them in both modes (the sweep rows compiled only). `tools/review_support.py` lists the files that differ |
| every session | `.venv/bin/python -m pytest -q -m slow` |
| every session | `tools/bench.py`, with `docs/bench/` committed |

## Findings scale

Severity: **Design** (wrong boundary or responsibility; fixing it moves code between
functions or modules), **Readability** (a reader is slowed or misled: a name, a long
function, a repeated block), **Nit** (cosmetic).

Risk class of the fix: **R0** rename; **R1** named constant; **R2** control flow; **R3**
function extraction; **R4** kernel signature or loop structure.

## The snapshot oracle

`tests/test_review_snapshot.py` runs 27 documents (227 solver calls) through today's code
and compares every output as `float.hex()` text with `tests/review_snapshot/` (2.0 MB):
lumped and junction-coupling cases at `output_type` 0 to 3, with the default and the
legacy flags; a short-pipe fallback; traced runs of both solvers; seeded sweeps per solver;
and two targeted documents (friction dead zone D-20, a `-0.0` force). Until session R.1b
it also held the valve-closure cases of `pressure_response`, a pressure sweep and the VBA
`min` / `max` tie rules (34 documents, 245 calls); they went with the pressure solver, and
the counts in "It bites" below are of that set. `tools/review_snapshot.py` checks the files and,
with `--write`, rewrites them.

### It bites (16 Nov 2026)

Each mutation swaps two operands in one line; then `make clean-cache`, the snapshot test,
`git checkout` of the file. Failed tests of 36, the same compiled and in pure Python:

| # | file:line | mutation | result |
|---|---|---|---|
| 1 | `moc.py:487` (`step`) | `… + (pb_prev - pb) / two_rho_c + (vb_prev + vb) / 2`: the last two terms swapped | **14 failed** (every junction-coupling document) |
| 2 | `structure.py:484` (`step_scalars`) | `f_applied - (…) * stiffness - v * damping` → `f_applied - v * damping - (…) * stiffness` | **25 failed** |
| 3 | `loads.py:302` (`unbalance_force`) | `fb_cur` and `fb_nxt` swapped in the `forceB` interpolation | **25 failed** |

Four further mutations survived the first case set: `0.5 * mu * dt * 9.81` and
`L * fs / c` (a last-bit change in a set-up value is absorbed before it reaches a peak),
`v > 0.0` for the D-20 tolerance and `f` for `0.0 + f` (no case). The set was extended
until all four fail: sweep runs carry a one-frame trace that pins `SdofParams`, `dt`, the
grid and the fractions; the adapter pins the transit delay, portal-frame height and decay
factor; the targeted documents. Nineteen other regroupings across the scope fail too.

Not visible to it: commutative swaps (`h * 4 / 3` → `4 * h / 3`) and `x**2` → `x * x` gave
the same bits on every case. Rule 2 forbids them all the same; equal bits here is no proof.

## The supporting-code checks

Added on 16 Nov 2026 (session R.0b) with the wider scope. `tests/test_review_support.py`
compares three things with `tests/review_support/` (20 files, 1.85 MB), each exactly; the
cases are fixed command lines and the numbers in `tests/review_support_cases.json`.
`tools/review_support.py` checks the files and, with `--write`, rewrites them. Session R.1b
added a 21st file, `sweep_histories.txt` (1.5 MB): the fourteen pressure histories of the
sweep rows, which (a) is now fed instead of generating them.

| | what runs | compared with | how |
|---|---|---|---|
| (a) sweep rows | `tools/sweep_jc.py run --tier 1 --subset 0.01 --jobs 1`: 16 cases, every level of every Tier 1 dimension, both solvers, on the stored histories of `sweep_histories.txt` (the adapter replaces `sweep_jc.case_history` and runs the tool's process pool with the fork start method so the workers see it) | `sweep_tier1_subset1.csv` | every cell as text, except the four columns that record the run (`t_lumped_s`, `t_jc_s`, `cpu`, `git_sha`); the CSV prints floats with `repr`, so equal text is equal bits |
| (b) exports | `tools/export.py trace` on six cases (two Example-sheet cases, a round-number step and a step with no round number in it, lumped and junction coupling, with the default stride, the budget stride and an explicit one) and `tools/export.py sweep` on the golden case table and on the stored CSV | eight `.json` files | byte for byte, with `meta.git_sha` and `meta.created_utc` held fixed |
| (c) histories | every generator of `histories.py` (`canonical` for the three kinds, `step`, `step_sine`, `step_noise`, `from_params`, and `p_cap` / `decay_rate` / `envelope` on their own), and the sweep's fourteen histories through `sweep_jc.case_history` | ten `.txt` documents and `sweep_histories.txt` | every parameter, statistic and array element as `float.hex()` text: exactly where numpy uses the stored `sin` / `exp` kernel, elsewhere each float at the relative tolerance 1e-12 (`history_rtol`) and every other line exactly |

Added time: 5 s compiled (3 s of it the sweep), under 1 s in pure Python. The 16 stored
rows equal the same cases of the committed Tier 1 file `docs/sweep/tier1_83d23ef_f4b.csv`
in every column but the run columns and `subset`.

Limits, each stated by the test when it applies:

* **(a) runs compiled only.** One sweep case takes 25 to 105 s in pure Python. The sweep
  tool holds no compiled code, and the snapshot test proves the solvers equal in both modes.
* **(c) depends on the host's CPU; (a) no longer does** (session R.1b, the owner's
  ruling). numpy picks its `sin` / `exp` kernel by CPU, and the AVX-512 kernel (`X86_V4`,
  this container, where the files were stored) rounds differently from the others: with
  `NPY_DISABLE_CPU_FEATURES=X86_V4` (kernel `X86_V3`) 214 lines of the history documents
  differ in the last bits, with no code change. (a) runs on the stored histories and is
  exact on every host. (c) is exact where the kernel matches and compares at 1e-12
  elsewhere; neither skips, and the run's summary prints which mode ran (`review support:
  ...` lines, from `tests/conftest.py`); `tools/review_support.py` prints the same. In the
  tolerance mode a last-bit regrouping in `histories.py` (H1 to H6 below) can pass: the
  exact mode on a reference platform is the one that decides. `--write` refuses on another
  kernel. (b) and the solver snapshot do not depend on the kernel. Checked in R.1b: the
  sweep rows equal the stored CSV in both modes, and mutation S3 fails in both.
* **Not covered:** the plots and the report of `tools/sweep_jc.py plot`, `tools/bench.py`,
  `tools/extract_fixtures.py`, `tools/golden_report.py`, `tools/profile_delta.py` (no test
  runs them), and gzip output (its header carries the time). `tools/build_viewer.py` is
  pinned by `tests/test_viewer.py`, which needs a browser.

### It bites (16 Nov 2026)

One line changed per mutation; then `make clean-cache`, `tests/test_review_support.py`
compiled and in pure Python, `git checkout` of the file. Failed tests of 22 (in pure Python
the sweep check is skipped, so one fewer where it is among the failures):

| # | file:line | mutation | result |
|---|---|---|---|
| S1 | `tools/sweep_jc.py:332` (`run_case`) | `(L + h * 4 / 3) * m` → `L * m + h * 4 / 3 * m` | **1 failed** (the sweep rows) |
| S2 | `tools/sweep_jc.py:127` (`pipe`) | `2 * (t / 1000) * S / (od / 1000)` → `2 * (t / 1000) * (S / (od / 1000))` | **1 failed** (the sweep rows) |
| S3 | `tools/sweep_jc.py:395` (`run_case`) | `f_eq / (L * d2)` → `f_eq / L / d2` | **1 failed** (the sweep rows) |
| E1 | `export.py:197` (`array_block`) | `arr.ravel()` → `arr.ravel(order="F")` | **4 failed** (every junction-coupling trace) |
| E2 | `export.py:158` | `"stick"` taken out of the integer frame columns | **7 failed** (every trace) |
| E3b | `viz/geometry.py:167` (`loop_layout`) | `height1 - (s[leg1] - s1)` → `height1 - s[leg1] + s1` | **2 failed** |
| E4 | `viz/geometry.py:250` (`lumped_grid`) | `arange(n) * (c * dt)` → `arange(n) * c * dt` | **1 failed** |
| E5 | `tools/cases.py:62` (`step_case`) | `amplitude * 1e5 * area` → `amplitude * area * 1e5` | **2 failed** |
| E7 | `trace.py:363` (`build`) | `arange(n) * (c * dt)` → `arange(n) * c * dt` | **1 failed** |
| E8 | `tools/cases.py:94` (`forced_substeps`) | `int(unb * step_qty)` → `int(unb) * step_qty` | **1 failed** |
| H1 | `histories.py:310` (`_sine_shape`) | `2.0 * np.pi * f_osc * tau` → `2.0 * np.pi * tau * f_osc` | **1 failed** |
| H2 | `histories.py:189` (`decay_rate`) | `… * f / decay_cycles` → `… / decay_cycles * f` | **1 failed** |
| H3 | `histories.py:470` (`step_noise`) | `w * ((p_cap - p_step) / w_max)` → `w * (p_cap - p_step) / w_max` | **4 failed** (three histories, the sweep rows) |
| H4 | `histories.py:207` (`_duration`) | the four duration terms summed in reverse order | **6 failed** |
| H5 | `histories.py:170` (`p_cap`) | `fraction * 1.33 * p_design` → `1.33 * p_design * fraction` | **2 failed** |
| H6 | `histories.py:218` (`_axis`) | `arange(n) / sample_freq` → `arange(n) * (1.0 / sample_freq)` | **10 failed** |

Eight of these survived the first case set (S1 and S2 as first written, E4, E5, E7, E8, H2,
H5 on round numbers: a cell spacing of exactly 1.5 m, amplitudes that are powers of two, a
stride that a `ceil` did not move). The set was extended until they fail: the step with no
round number in it, `p_cap` and `decay_rate` on six further argument sets, a stride chosen
so that the transit term moves it. S1 and S2 were rewritten because their first forms
(`h / 3 * 4`, the factors of a product swapped around an exact factor of 2) give the same
bits for every input.

Still not visible, and recorded as such:

* `viz/geometry.py:170`, `run_length + (s[outlet] - s4)` → `(run_length + s[outlet]) - s4`:
  the same bits on every stored trace (the outlet arm is seven cells).
* `tools/export.py:73`, the stride that fits the size budget: neither regrouping
  `(budget - 20 * n_samples) / per_frame` nor dropping the sample term moves the integer
  stride of the one budget case. The stride itself is pinned, its arithmetic is not.
* `0.5 * mass_total * v**2` → `0.5 * v**2 * mass_total` (`tools/sweep_jc.py:391`), and the
  like: equal bits by construction, forbidden all the same (rule 2).

## Rulings (owner, session R.5, 24 Nov 2026)

The parameter-objects session (plan group 3).

43. **Speed comparisons.** Speed is judged by an A/B run of the old code against the new on
    the same host in the same session, or by time relative to the literal port measured in
    the same run. Raw times from different sessions are not comparable: the host changes
    between sessions. The 5 % limit applies to that comparison, on the lumped and on the
    junction-coupling path alike.
44. **Plan 2.2 in group 3.** The coupling kind as a plain boolean flag is made in this
    session, with the kernel signatures it changes (ruling 40).
45. **No SI conversion at the boundary.** The proposal in `NOTES.md` (R.4) to convert inputs
    to SI once at the entry is declined; the named factors stay where they are.
46. **The brief and the plan.** Where `docs/review/plan.md` and a session brief differ, the
    plan wins. The parameter-object groups are written to
    `docs/review/parameter_objects.md` (ruling 10) and shown to the owner in full.

## Rulings (owner, session R.6, 24 Nov 2026)

The single-substep session (plan group 4).

47. **Plan 3.7 and 3.10 to the public API session.** The span, restraint and fluid objects
    for the set-up functions (3.7) and the entry-point extraction (3.10) move to the public
    API session, which designs the input groups; made now, those groups would be designed
    twice.
48. **Plan 3.11 to the supporting-modules session.** The single set-up query moves to group
    5, because the tools are its main users.
49. **`JunctionCoupling` replaced by a function.** It holds only the `FluidColumn` and two
    values that only tests read (`dt`, and `d_f`, which is 0.0 at entry). It becomes a
    function that returns the `FluidColumn`, as its own commit before the substep work;
    the tests are pointed at the values they actually check.
50. **Benchmark rows and host drift.** The `tools/bench.py` row is recorded as measured,
    but a host that drifts during a session decides nothing: the interleaved A/B run of the
    old code against the new on the same host does (ruling 43). Where `plan.md` and the
    session brief differ, `plan.md` wins (ruling 46).

51. **Substep design A approved** (`docs/review/substep_design.md`). The shared function is
    named for all it does (`_structure_substep`: it steps the structure, writes the trace
    frame and tracks the maxima), with a first docstring line listing the three jobs.
52. **Plan 4.9 ahead of 4.1 to 4.8** (Q-R6-1). After it the rest of group 4 follows in plan
    order; 4.6 is dropped where design A has absorbed it. A long session stops at a green
    commit and says where.
53. **Step 0 approved** (Q-R6-2): the kernel starts the junction force at 0.0 and no longer
    returns it.
54. **The 5 % limit applies to the compiled paths.** The pure-Python change is recorded in
    the bench notes; the owner is told if the pure-Python fast suite, a per-commit gate,
    takes more than about a quarter longer.
55. **Trace depth.** If the A/B shows that the column reaching `_trace_frame` two calls deep
    costs more than noise on a traced run, the session stops and reports; it does not
    restructure on its own.
56. **Option 1, once** (after the revert of `6ea80ba`). A small
    `_structure_substep(state, applied_force, sdof_params, dt)` steps the structure, updates
    the maxima and counts the substep; it takes no schedule, buffers or column, and the trace
    write stays in each loop as one call behind `if record_frame:`. Two commits (forced loop,
    then free decay), each gated and A/B timed against the commit before. If any compiled
    case is more than 5 % slower after either, that commit is reverted and the session goes
    to option 3 (two loops kept, 4.6 and 4.7 made, and `findings.md` records that the
    duplicated substep stays because sharing it costs speed); no Design B, no third variant.
    Then the rest of group 4 in plan order, and the session gates.
57. **Per-substep arguments** (`docs/style.md` §4): a function called on every substep takes
    only scalars and small tuples of scalars; arrays go only to functions called once per run
    or that loop over them internally.

## Rulings (owner, session R.7, 24 Nov 2026)

The rest of plan group 4.

58. **Plan 4.2 to 4.4 dropped** (option c of `substep_design.md`). `moc.step` stays one
    function with its even / odd flag, a recorded exception in `docs/style.md` §11:
    splitting it either adds branches to the kernel loops or passes the column two calls
    deep per substep. C-04 and C-05 are closed with that reason.
59. **The A/B harness is committed** as `tools/review_ab.py`, with a short usage note: it
    decides the speed gate (rulings 43, 50, 54).
60. **Kernel targets.** A kernel complexity of 10 meets the target; statements above 50 are
    accepted until 4.7.
61. **Plan 4.12** (the schedule flattened in `loads`; it reopens C-07). The A/B is reported
    either way, the compiled lumped path being dominated by the schedule generator. Every
    per-substep force and the D-7 and D-8 error positions stay exact, checked on 6000
    random histories as in session R.4. If 4.12 cannot be made exact and no slower, it is
    reverted and C-07 stays open with the reason; no second variant.

## Rulings (owner, session R.8, 24 Nov 2026)

The supporting-modules session (plan group 5, with 3.11 moved there by ruling 48).

62. **The kernel stays at 56 statements.** `response._integrate_kernel` is a recorded
    exception in `docs/style.md` §11: what is left above the target of 50 is the two
    frame-label blocks and the two `moc.step` calls, and shortening them further would hide
    the substep sequence.
63. **C-07 stays open by decision.** The one-walk schedule cost about 20 % on the compiled
    lumped path (rulings 42, 61); the two walks are kept.
64. **Mislabelled bench-row subjects.** The bench-row commits of session R.7 whose subject
    says "R.6" are left as they are; `NOTES.md` states which they are.
65. **Gates as before** (ruling 39): `make lint` and the compiled fast suite pass before
    each commit, the pure-Python run of a commit passes before the next, and the branch is
    pushed only when every commit is green. A change to code the solvers or the sweep run
    through is timed with `tools/review_ab.py` against the commit before; the 5 % limit
    applies (rulings 43, 54).
66. **The plan wins** where `docs/review/plan.md` and the session brief differ (rulings 46,
    50).

## Rulings (owner, session R.9, 25 Nov 2026)

The public API session (plan group 6, with 3.7 and 3.10).

67. **`tools/fixture_cases.py` stays in `tools/`.**
68. **Sweep modules in `sys.modules`.** That the sweep modules enter `sys.modules` when a test
    loads the sweep tool is accepted. If a property test turns red because its generated
    examples moved, the session stops and reports it; the test is not loosened.
69. **The adapter change in `tests/test_review_support.py`** is allowed under rule 6.
70. **A sweep case in the A/B harness.** `tools/review_ab.py` gets one small sweep case
    (`sweep_noise`, one Tier 1 case through `sweep_rows.run_case`), so that a change on the
    sweep path can be timed.
71. **Plan 3.7 and 3.10 belong to this session**, as part of the public interface work
    (confirms ruling 47).
72. **Gates as before** (rulings 39, 65): `make lint` and the compiled fast suite before each
    commit, the pure-Python run of a commit before the next, the branch pushed only when every
    commit is green, and `tools/review_ab.py` against the commit before for anything on the
    solver or sweep path, with the 5 % limit. Where `plan.md` and the session brief differ,
    `plan.md` wins.
73. **The proposal in a file.** The public interface of step 1 is written to
    `docs/review/public_interface.md` and shown to the owner in full, with the old-to-new
    table of exported key names (the schema bump) in the same file (ruling 10).
74. **Viewer tests.** No exported key and no viewer key changes unless the viewer's browser
    tests run. Without a working browser the session makes the input types, the entry points,
    the docstrings and the lint limits with the exported keys left exactly as they are, stops
    at a green commit and reports that the schema bump waits for a machine with one. (In this
    environment they run: `PLAYWRIGHT_BROWSERS_PATH` pointed at a directory whose
    `chromium-1243/chrome-linux/chrome` links to the installed
    `/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`; 26 passed.)
75. **Long session.** If the context runs long, the session stops at a green commit and says
    where.

## Rulings (owner, on the public interface, session R.9, 25 Nov 2026)

`docs/review/public_interface.md` is approved, option A (grouped inputs), with these answers.

76. **Sample rate beside the history** (Q-PI-1): `peak_response(force_history, sample_rate,
    *, span, restraint, integration)`. It describes the data, not how the data is
    integrated; a caller who changes the integration settings cannot mis-state the
    history's rate. `Integration` holds `substep_count` and `trace_every`. The
    junction-coupling entry has 7 parameters: a `docs/style.md` §11 exception.
77. **`output_type` removed** (Q-PI-2); the three histories are always recorded.
78. **Names kept** (Q-PI-3): `peak_response`, `peak_response_jc` and the trace's `solver`
    values.
79. **The five duration terms keep `_s`** (Q-PI-4), a `docs/style.md` exception: the bare
    words would be ambiguous with the sample counts.
80. **`daf_lumped`, `daf_jc` kept** (Q-PI-5): DAF is the standard term in piping design and
    in the paper, an accepted abbreviation in `docs/nomenclature.md`. The other pair is
    `force_per_length_diameter_squared_*`.
81. **S-31 and S-47 left out of the bump** (Q-PI-6).
82. **Old signatures removed, no wrappers** (Q-PI-7).
83. **Step 4 split.** First a commit that always records the three histories while the old
    signature still takes `output_type` and returns the matching one as `history` (the
    kernel change, A/B timed on its own); then the commit that introduces the new entry
    points, moves the callers and removes `output_type`.
84. **Before the schema bump** the report lists every committed data file re-exported and
    every file whose header is renamed, and confirms the viewer's browser tests ran and
    passed on that commit.
