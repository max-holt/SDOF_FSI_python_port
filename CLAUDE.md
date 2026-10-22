# surge_sdof — VBA → Python port

## What this is
Python port of an Excel VBA solver: 1-D MoC water hammer + SDOF pipe response with Coulomb friction, support gaps and MoC junction-coupling FSI. Source of truth for behaviour is `legacy/vba/` and the Excel-generated fixtures in `tests/fixtures/`.

## Stage discipline (read NOTES.md for the current stage)
- Stage 1 (literal port): preserve VBA semantics exactly — operation order, loop order, 1-based indices, `CLng` = round-half-to-even, the VBA `floor` (`max(CLng(x-0.5), CLng(x+0.5)-1)`), Integer/Long types. Do not simplify expressions. Do not fix apparent bugs; record them in DEVIATIONS.md with status "preserved".
- Stage 2+ (refactor): one behaviour-preserving change per commit; golden tests must stay green at the tolerance recorded in `tests/test_golden.py`. A deviation is only allowed with a DEVIATIONS.md row and a test that pins the new behaviour.

## Hard rules
- Never edit files under `tests/fixtures/` or `legacy/`.
- Never delete, skip or loosen a test to make it pass. Raise the failure in NOTES.md instead.
- Run `.venv/bin/python -m pytest -q` before every commit; run `.venv/bin/python -m pytest -q -m slow` before any commit touching `src/`.
- Do not add dependencies beyond numpy, pytest, ruff, hypothesis, numba, openpyxl, oletools (the last two are dev extras for fixture extraction only) without asking.
- When unsure of the VBA intent, stop and ask; do not guess.

## Commands
Invoke pytest as `.venv/bin/python -m pytest …` (the `pytest` on PATH is an isolated uv tool without numpy); `pytest` below is shorthand for that.
- Tests: `.venv/bin/python -m pytest -q`
- Lumped golden gate (before commits touching `src/`): `.venv/bin/python -m pytest -q -m slow`
- Golden suite only: `.venv/bin/python -m pytest -q tests/test_golden.py -m "slow or jc_slow"`
- Lint/format: `ruff check . && ruff format .`
- Pure-Python mode (no JIT): `NUMBA_DISABLE_JIT=1 .venv/bin/python -m pytest -q`
- Numba cache (`cache=True`) does not notice when a callee in another module changed: after editing `moc.py` or `structure.py`, a bare `pytest` can test a stale compiled `response._integrate_kernel`. Run `make test-both` (wipes `src/**/__pycache__/*.nb[ic]` first) or `make clean-cache` before trusting a result.
- Benchmark: `tools/bench.py` — run at the end of every Stage 4/5 session and commit docs/bench/.

## Known VBA gotchas
- `floor(x) = max(CLng(x - 0.5), CLng(x + 0.5) - 1)`: a true floor (fixed upstream in commit da022b8; the original `CLng(x - 0.5)` was one too low for odd integers). Port as `vba_floor`, transcribed literally; see DEVIATIONS.md D-1/D-2/D-11 (fixed). Excel fixtures must come from a workbook with the fixed `floor`.
- `ArrayStartOne` assigns to the wrong name and returns an empty array (dead/broken path).
- `interpFractionB` uses `n < 3` where `interpFractionA` uses `n < extQTY` (4).
- Friction clamp differs between the two MoC half-loops in `GetPressureResponse` (0.9 vs 0.9*rhoC).
- `On Error GoTo ErrFound` in `GetPeakResponseJC` swallows every runtime error.
- `stepQTY = 1` divides by zero (`k/(stepQTY-1)`).
- 2-D `forceHistory`/`valvePattern` inputs are flattened column-major (first index fastest).
- `GetPeakResponseJC` MoC parity index is `k + (totInd-1)*stepQTY` with each phase's own `k` range (phase 3 starts at `k = 1`), so the even/odd alternation can double-update a half-grid at phase boundaries; a single-loop refactor must keep the per-phase formula or prove the parity sequence equal (docs/port_review.md §2.5, DEVIATIONS D-19).

## Session end
Update NOTES.md (stage, done, open issues, next action) and commit.
