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
