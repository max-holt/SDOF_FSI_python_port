# NOTES — session handoff

## Current stage
Stage 1 (literal port): code complete and aligned with the lead author's upstream `floor` fix (`legacy/vba` commit da022b8; D-1, D-2, D-11 now "fixed"), unverified against Excel. `src/surge_sdof/legacy_port.py` holds a line-for-line transcription of every VBA function in VBA order; `src/surge_sdof/vba_compat.py` holds the VBA-semantics helpers. No golden fixtures exist yet, so numerical equivalence with Excel is **not** established; only helper semantics, smoke and structural sanity checks are in place.

## Done
- `vba_compat.py`: `clng` (half-to-even), `vba_floor` (literal transcription of the fixed VBA `max(CLng(val - 0.5), CLng(val + 0.5) - 1)`, pinned against `math.floor`), `mod_dbl` (ordinary floored modulo now), `sign`, `min_unsigned`, `max_unsigned`, plus `ubound`/`vba_2d` for the padded 1-based array convention. `tests/test_vba_compat.py` pins them against the VBA definitions.
- Upstream `floor` fix applied: `main` merged, `vba_floor`/`mod_dbl` updated, the tests that pinned the old bug (mod_dbl table, parity test, D-11 multi-column pressure test, D-8 trigger condition) re-pinned to the fixed behaviour. DEVIATIONS D-1, D-2, D-11 are status "fixed" with the reason "source corrected upstream".
- `legacy_port.py`: `min`, `max` (shadow the built-ins on purpose, VBA tie semantics), `get_dimension`, `add_dimension`, `array_start_one` (D-3), `interp_fraction_a`, `interp_fraction_b` (D-4), `solve_poly`, `get_pressure_response` (D-6, D-11), `get_peak_response` (D-7, D-8), `get_peak_response_jc` (D-9, dead `useUndamped` branch kept behind `use_undamped = False`, short-pipe fallback). Conventions are documented in the module header.
- Tests (151 passing, `pytest -q` ≈ 3 s): `test_vba_compat.py`, `test_helpers.py`, `test_smoke.py` (each entry point on a 100-sample step force, stepQTY = 10, all output types, 1-D and 2-D inputs, fallback, raised error paths), `test_structure.py` (gap = 0 & ratio = 1 ≡ gap = 1e9 bitwise on both peak solvers; undamped constant-force midline = F/k within 1 % on the lumped solver; JC with fluidArea = 0 ≡ lumped bitwise; column-major flattening identity on all three entry points).
- DEVIATIONS.md rows D-1 … D-11: D-1, D-2, D-11 "fixed" (upstream source fix), the rest "preserved".
- Port review: `port-reviewer` subagent ran on `git diff 125e73e..HEAD` (diff + VBA only): **no correctness findings**. Its two non-blocking notes were applied: D-11 wording now states the even-row-count condition; the `solve_poly` complex-root edge case is listed below.

## Findings worth knowing (all preserved, see DEVIATIONS.md)
- D-1/D-2/D-11 (historical, now fixed upstream): the original `CLng(val - 0.5)` floor made the JC MoC even-cell update run 1 step in 4 and made multi-column valve patterns extrapolate the closure at some positions. With the fixed floor the MoC alternates every step and multi-column patterns equal their column-major flattening exactly. Any Excel fixtures must be generated with the *fixed* VBA module.
- D-8: a single-row (horizontal) `forceHistory` leaves `iB = UBound(1) + 1` after the first block and fails with subscript out of range (swallowed into `#VALUE!` by JC). With the fixed floor an integer delay no longer escapes this (`kOverlap = 0`).
- The SDOF integrator evaluates `aNew` from the old `x`, `v` (explicit, not average-acceleration Newmark); with zero damping its amplitude grows ≈ 2.5 % per cycle at ω·dt ≈ 0.016 (stepQTY = 10, 5 Hz, 100 Hz samples). The cycle time-mean stays at F/k. This is why the static-deflection structure test integrates with stepQTY = 100.
- The free-decay `Do While x * xZero > 0.01` loop only runs when |x| > 0.1 (model units); for typical metre-scale displacements it never executes. If it does run with zero damping and friction it does not terminate (same in VBA).
- JC with a negligible portal-frame height (pivotSegQTY = 4) divides by zero in `interpFractionB(3)` (D-4) and the VBA returns `#VALUE!`; Python raises.

## Judgement calls made (flag if you disagree)
- Python inputs are 2-D numpy arrays with 1-based meaning (padded by `vba_2d`); 1-D arrays take the `AddDimension` path; the broken `ArrayStartOne` path is unreachable.
- VBA runtime errors: numpy arithmetic in the entry points runs under `np.errstate(divide/invalid/over = "raise")` so it raises where VBA raised; pure-Python float overflow (→ inf) and Integer/Long overflow are not emulated. `On Error GoTo ErrFound` re-raises (D-9) instead of returning an empty array.
- The implicit Double→Long assignment at VBA line 244 (`i = modDbl(...) + 1`) is written as an explicit `clng`.
- `^` is `**`: for integer exponents both call C `pow`; last-bit differences against Excel's runtime are possible and should be absorbed by the golden tolerance. `(-varA / varB) ^ (1 / 3)` would be complex in Python where VBA raises error 5; only reachable with non-physical inputs.
- Loops whose control variable is read after the loop (`jB`, `iB`) are while loops; all other `For` loops are `range` loops.

## Open issues
- No Excel golden fixtures yet (`tests/fixtures/` empty); `tests/test_golden.py` and `tools/golden_report.py` do not exist. Equivalence with Excel is unverified.
- Performance: pure Python; JC with long spans is slow (cells ∝ unballanceStepQTY × stepQTY / 2). Not a Stage 1 concern.
- numba and hypothesis are permitted by `CLAUDE.md` but not added to `pyproject.toml`.
- `CLAUDE.md` "Known VBA gotchas" still lists the original `floor(x) = CLng(x - 0.5)` bug; it is fixed in the source now. Left for the owner to reword.
- The project hooks in `.claude/settings.json` load only when Claude Code is started from the repository root.

## Next action
Generate Excel golden fixtures for the three entry points **with the fixed `floor` in the workbook module** (include: a multi-column valve pattern to exercise D-11, a 2-D force history, the JC short-pipe fallback, stepQTY = 10 and a non-integer unballanceStepQTY), write `tests/test_golden.py` with the tolerance recorded there, and run `/golden`. Only then start Stage 2.
