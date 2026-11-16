# Clean-code review of the solver — charter

Set up on 16 Nov 2026 on branch `review/clean-code`. The solver is verified against the VBA
but hard to read; later sessions review and refactor it. Every refactoring leaves the
results bit-identical. `docs/style.md` is the target; `docs/review/baseline.md` is where
the code started.

## Scope

Widened on 16 Nov 2026 (session R.0b) from the solver modules to two areas.

* **The solver core:** `moc.py`, `structure.py`, `coupling.py`, `loads.py`, `response.py`,
  `pressure.py`, `_vba_semantics.py`.
* **The supporting Python:** `trace.py`, `export.py`, `histories.py`, `viz/geometry.py` and
  `tools/`.
* **The data format** (`docs/data_format.md`: the `trace` and `sweep` documents and the
  sweep CSV columns) is in scope. Names in exported files change once, in a single schema
  bump late in the review (the public API session, below); until then every exported file
  stays byte-identical.
* **The viewer** (`docs/viewer/viewer.src.html`) is in scope only for the keys it reads from
  a data file. Its JavaScript structure is not reviewed.
* **Mechanical edits only**, the ones a rename forces: `tests/`.
* **Untouched:** `legacy_port.py`, `vba_compat.py`, `legacy/`, `tests/fixtures/`.

Two sessions are fixed points for the rulings in `docs/style.md`:

| session | what changes there, and not before |
|---|---|
| renames | internal names, the VBA spellings among them |
| public API | public keywords, the `get_pressure_response` alias, the form of the junction-coupling flags and of `output_type`, the names in exported files (the schema bump), and the 6-argument limit becomes enforced |

## Change rules

1. One refactoring per commit, named in the commit message (with its risk class).
2. No arithmetic change of any kind inside a structural commit: operand order, grouping,
   literal type (`2` versus `2.0`), `x**2` versus `x*x`, hoisting, summation order.
   Expressions move verbatim.
3. If a gate fails, revert the commit. Do not debug forward.
4. Behaviour changes are out of scope. They go to `NOTES.md` as questions for the owner.
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

`tests/test_review_snapshot.py` runs 34 documents (245 solver calls) through today's code
and compares every output as `float.hex()` text with `tests/review_snapshot/` (2.0 MB):
lumped and junction-coupling cases at `output_type` 0 to 3, with the default and the
legacy flags; a short-pipe fallback; traced runs of both solvers; valve-closure cases;
seeded sweeps per solver; and three targeted documents (friction dead zone D-20, a `-0.0`
force, the VBA `min` / `max` tie rules). `tools/review_snapshot.py` checks the files and,
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
`tools/review_support.py` checks the files and, with `--write`, rewrites them.

| | what runs | compared with | how |
|---|---|---|---|
| (a) sweep rows | `tools/sweep_jc.py run --tier 1 --subset 0.01 --jobs 1`: 16 cases, every level of every Tier 1 dimension, both solvers | `sweep_tier1_subset1.csv` | every cell as text, except the four columns that record the run (`t_lumped_s`, `t_jc_s`, `cpu`, `git_sha`); the CSV prints floats with `repr`, so equal text is equal bits |
| (b) exports | `tools/export.py trace` on six cases (two Example-sheet cases, a round-number step and a step with no round number in it, lumped and junction coupling, with the default stride, the budget stride and an explicit one) and `tools/export.py sweep` on the golden case table and on the stored CSV | eight `.json` files | byte for byte, with `meta.git_sha` and `meta.created_utc` held fixed |
| (c) histories | every generator of `histories.py` (`canonical` for the three kinds, `step`, `step_sine`, `step_noise`, `from_params`, and `p_cap` / `decay_rate` / `envelope` on their own) | ten `.txt` documents | every parameter, statistic and array element as `float.hex()` text |

Added time: 5 s compiled (3 s of it the sweep), under 1 s in pure Python. The 16 stored
rows equal the same cases of the committed Tier 1 file `docs/sweep/tier1_83d23ef_f4b.csv`
in every column but the run columns and `subset`.

Limits, each stated by the test when it applies:

* **(a) runs compiled only.** One sweep case takes 25 to 105 s in pure Python. The sweep
  tool holds no compiled code, and the snapshot test proves the solvers equal in both modes.
* **(a) and (c) depend on the host's CPU.** numpy picks its `sin` / `exp` kernel by CPU,
  and the AVX-512 kernel (`X86_V4`, this container, where the files were stored) rounds
  differently from the others: with `NPY_DISABLE_CPU_FEATURES=X86_V4` eight of the ten
  history documents and the sweep rows differ, with no code change. On such a host those
  two checks skip, with that reason, and `--write` refuses. (b) and the solver snapshot do
  not depend on it: they pass unchanged with the kernel switched off. Open question for the
  owner in `NOTES.md`.
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
