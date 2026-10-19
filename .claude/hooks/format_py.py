"""PostToolUse hook: run `ruff format` on an edited .py file.

Reads the hook payload from stdin. Always exits 0 so a formatter problem never breaks an
edit; ruff's own output is forwarded to stderr for visibility.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path


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
    ruff = shutil.which("ruff")
    if ruff is None:
        return 0
    result = subprocess.run([ruff, "format", str(path)], capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
