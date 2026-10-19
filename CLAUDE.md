# surge_sdof — VBA → Python port

## What this is
Python port of an Excel VBA solver: 1-D MoC water hammer + SDOF pipe response with Coulomb friction, support gaps and MoC junction-coupling FSI. Source of truth for behaviour is `legacy/vba/` and the Excel-generated fixtures in `tests/fixtures/`.

## Stage discipline (read NOTES.md for the current stage)
- Stage 1 (literal port): preserve VBA semantics exactly — operation order, loop order, 1-based indices, `CLng` = round-half-to-even, the `CLng(x-0.5)` floor idiom, Integer/Long types. Do not simplify expressions. Do not fix apparent bugs; record them in DEVIATIONS.md with status "preserved".
- Stage 2+ (refactor): one behaviour-preserving change per commit; golden tests must stay green at the tolerance recorded in `tests/test_golden.py`. A deviation is only allowed with a DEVIATIONS.md row and a test that pins the new behaviour.

## Hard rules
- Never edit files under `tests/fixtures/` or `legacy/`.
- Never delete, skip or loosen a test to make it pass. Raise the failure in NOTES.md instead.
- Run `pytest -q` before every commit.
- Do not add dependencies beyond numpy, pytest, ruff, hypothesis, numba without asking.
- When unsure of the VBA intent, stop and ask; do not guess.

## Commands
- Tests: `pytest -q`
- Golden suite only: `pytest -q tests/test_golden.py`
- Lint/format: `ruff check . && ruff format .`
- Pure-Python mode (no JIT): `NUMBA_DISABLE_JIT=1 pytest -q`

## Known VBA gotchas
- `floor(x) = CLng(x - 0.5)`: wrong for odd integers (floor(5.0) = 4). Port as `vba_floor`; see DEVIATIONS.md.
- `ArrayStartOne` assigns to the wrong name and returns an empty array (dead/broken path).
- `interpFractionB` uses `n < 3` where `interpFractionA` uses `n < extQTY` (4).
- Friction clamp differs between the two MoC half-loops in `GetPressureResponse` (0.9 vs 0.9*rhoC).
- `On Error GoTo ErrFound` in `GetPeakResponseJC` swallows every runtime error.
- `stepQTY = 1` divides by zero (`k/(stepQTY-1)`).
- 2-D `forceHistory`/`valvePattern` inputs are flattened column-major (first index fastest).

## Session end
Update NOTES.md (stage, done, open issues, next action) and commit.
