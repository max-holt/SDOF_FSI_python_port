# surge_sdof — VBA → Python port

## What this is
Python port of an Excel VBA solver: 1-D MoC water hammer + SDOF pipe response with Coulomb friction, support gaps and MoC junction-coupling FSI. Source of truth for behaviour is `legacy/vba/` and the Excel-generated fixtures in `tests/fixtures/`. New sessions: read `docs/handover.md` first (entry points, flags, tiers, viewer, sweep, caveats, what is not done), then NOTES.md for the current stage.

## Change discipline
- One behaviour-preserving change per commit; the golden tests must stay green at the tolerance recorded in `tests/test_golden.py` and the differential suite bitwise against `legacy_port.py`. A deviation is only allowed with a DEVIATIONS.md row and a test that pins the new behaviour.
- `legacy_port.py` and `vba_compat.py` are frozen (the literal transcription, the reference until Stage 6 removes them); do not edit them.
- Flags: `peak_response_jc` carries `vav_denominator`, `parity` and `fraction_profile`, defaulting to the approved fixes F-1 / F-2 / F-4b; the values `"legacy"` / `"per_phase"` / `"legacy"` reproduce the VBA bitwise and are what the Excel acceptance tests (`jc_slow`) run with. Keep both paths green.

## Hard rules
- Never edit files under `tests/fixtures/` or `legacy/`.
- Never delete, skip or loosen a test to make it pass. Raise the failure in NOTES.md instead.
- Run `.venv/bin/python -m pytest -q` before every commit; run `.venv/bin/python -m pytest -q -m slow` before any commit touching `src/`.
- Do not add dependencies beyond numpy, pytest, ruff, hypothesis, numba, openpyxl, oletools, playwright, plotly (the last four are dev extras: fixture extraction and the viewer build / tests) and matplotlib (the `plots` extra) without asking.
- When unsure of the VBA intent, stop and ask; do not guess.

## Commands
Invoke pytest as `.venv/bin/python -m pytest …` (the `pytest` on PATH is an isolated uv tool without numpy); `pytest` below is shorthand for that.
- Tests: `.venv/bin/python -m pytest -q`
- Lumped golden gate (before commits touching `src/`): `.venv/bin/python -m pytest -q -m slow`
- Golden suite only: `.venv/bin/python -m pytest -q tests/test_golden.py -m "slow or jc_slow"`
- Lint: `make lint` (`ruff check` + `ruff format --check` through the venv; a bare `ruff` on PATH can differ from the venv's, and `ruff format .` rewrites files: format with `.venv/bin/python -m ruff format .` only when you mean to)
- Pure-Python mode (no JIT): `NUMBA_DISABLE_JIT=1 .venv/bin/python -m pytest -q`
- Numba cache (`cache=True`) does not notice when a callee in another module changed: after editing `moc.py`, `structure.py` or `trace.py`, a bare `pytest` can test a stale compiled `response._integrate_kernel`. Run `make test-both` (wipes `src/**/__pycache__/*.nb[ic]` first) or `make clean-cache` before trusting a result.
- Benchmark: `tools/bench.py` — run at the end of every session that touches the solver path and commit docs/bench/.
- Viewer: edit `docs/viewer/viewer.src.html`, rebuild with `tools/build_viewer.py`; `tests/test_viewer.py` pins the committed page to the build.

## Known VBA gotchas
- `floor(x) = max(CLng(x - 0.5), CLng(x + 0.5) - 1)`: a true floor (fixed upstream in commit da022b8; the original `CLng(x - 0.5)` was one too low for odd integers). Ported as `vba_floor`, transcribed literally; see DEVIATIONS.md D-1/D-2/D-11 (fixed). Excel fixtures must come from a workbook with the fixed `floor`.
- `CLng` is round-half-to-even; VBA `min`/`max` return the second argument on a tie or NaN (`_vba_semantics.vba_min/max`).
- `ArrayStartOne` assigns to the wrong name and returns an empty array (dead/broken path).
- `interpFractionB` uses `n < 3` where `interpFractionA` uses `n < extQTY` (4) — the legacy profile; the fixed profile is the lead author's 27 Oct 2026 text.
- Friction clamp differs between the two MoC half-loops in `GetPressureResponse` (0.9 vs 0.9*rhoC).
- `On Error GoTo ErrFound` in `GetPeakResponseJC` swallows every runtime error.
- `stepQTY = 1` divides by zero (`k/(stepQTY-1)`).
- 2-D `forceHistory`/`valvePattern` inputs are flattened column-major (first index fastest).
- `GetPeakResponseJC` MoC parity index is `k + (totInd-1)*stepQTY` with each phase's own `k` range (phase 3 starts at `k = 1`), so the even/odd alternation can double-update a half-grid at phase boundaries; the restructured solver keeps this behind `parity="per_phase"` (docs/port_review.md §2.5, DEVIATIONS D-19).

## Session end
Update NOTES.md (stage, open issues, next action) and commit.
