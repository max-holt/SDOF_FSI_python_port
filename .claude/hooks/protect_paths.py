"""PreToolUse hook: block Edit/Write/NotebookEdit under tests/fixtures/ and legacy/.

Reads the hook payload from stdin. Exits 2 (block) with a reason on stderr when the
target file lies under a protected directory; exits 0 otherwise. The repository root is
derived from this script's location so the check does not depend on $CLAUDE_PROJECT_DIR.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTECTED = ("tests/fixtures", "legacy")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not file_path:
        return 0
    path = Path(file_path)
    if not path.is_absolute():
        path = Path(payload.get("cwd") or REPO_ROOT) / path
    path = path.resolve()
    for rel in PROTECTED:
        protected_dir = (REPO_ROOT / rel).resolve()
        if path == protected_dir or protected_dir in path.parents:
            sys.stderr.write(
                f"Blocked: {path} is under protected directory {rel}/ "
                "(see CLAUDE.md hard rules). Never edit fixtures or legacy VBA.\n"
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
