# NOTES — session handoff

## Current stage
Stage 0: repository bootstrap complete. Stage 1 (literal port) has not started. No solver code exists yet.

## Done
- Project skeleton: `pyproject.toml` (setuptools, `src/` layout), `src/surge_sdof/` (version only), `tests/` (smoke test, `conftest.py` with `FIXTURES_DIR`), empty `tests/fixtures/`, empty `docs/`, `legacy/` untouched.
- Dev tooling: pytest, numpy, ruff (lint + format) via `pip install -e ".[dev]"`.
- Governance: `CLAUDE.md`, `DEVIATIONS.md` (header only), this file.
- Claude Code scaffolding: `.claude/agents/port-reviewer.md`, `.claude/skills/golden/SKILL.md`, `.claude/settings.json` with a PostToolUse `ruff format` hook and a PreToolUse hook blocking Edit/Write under `tests/fixtures/` and `legacy/` (scripts in `.claude/hooks/`).

## Open issues
- `tests/test_golden.py` and `tools/golden_report.py` are referenced by `CLAUDE.md` and `/golden` but do not exist yet; they belong to the fixture-generation stage.
- `tests/fixtures/` is empty. Excel golden fixtures are needed for `GetPressureResponse`, `GetPeakResponse` and `GetPeakResponseJC` (including the short-pipe fallback path) before Stage 1 can be verified.
- The project hooks in `.claude/settings.json` load only when Claude Code is started from the repository root.
- numba and hypothesis are permitted by `CLAUDE.md` but not yet added to `pyproject.toml`.

## Next action
Generate Excel golden fixtures for the three entry points, then begin Stage 1 with the helper functions (`vba_floor`, `minUnsigned`, `maxUnsigned`, `sign`, `modDbl`, `interpFractionA/B`, `solvePoly`) and their unit tests.
