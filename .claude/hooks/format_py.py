"""PostToolUse hook: run `ruff format` on an edited .py file.

Reads the hook payload from stdin. Always exits 0 so a formatter problem never breaks an
edit; ruff's own output is forwarded to stderr for visibility.

The formatter is the project venv's ruff (`.venv/bin/python -m ruff`), the one `make lint`
checks with, so the hook and the gate cannot disagree. Without the venv the hook formats
nothing and says so; it never falls back to a `ruff` on PATH, which can be another version.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    file_path = (payload.get("tool_input") or {}).get("file_path")
    if not file_path or not file_path.endswith(".py"):
        return 0
    path = Path(file_path)
    if not path.is_absolute():
        path = Path(payload.get("cwd") or ".") / path
    if not path.is_file():
        return 0
    if not VENV_PYTHON.is_file():
        sys.stderr.write(f"format hook: {VENV_PYTHON} not found, {path.name} left unformatted\n")
        return 0
    result = subprocess.run(
        [str(VENV_PYTHON), "-m", "ruff", "format", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
