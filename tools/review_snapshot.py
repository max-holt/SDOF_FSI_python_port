"""Check or write the review snapshot (``tests/review_snapshot/``).

The cases, the solver adapter and the text format live in
``tests/test_review_snapshot.py``; this script only renders the documents and compares or
stores them, so the test and the generator cannot disagree.

    .venv/bin/python tools/review_snapshot.py            # compare, exit 1 on a difference
    .venv/bin/python tools/review_snapshot.py --write    # (re)write every document

``--write`` is for an approved behaviour change only (a DEVIATIONS.md row), never to make
a refactoring pass: see ``docs/review/charter.md``. It refuses to run with the JIT
disabled so the stored files always come from the compiled path; the test then proves the
pure-Python path equal to them.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tests"))

import test_review_snapshot as snapshot  # noqa: E402


def main() -> int:
    """Compare the snapshot documents with today's code, or write them with ``--write``
    (compiled path only); the exit status, 1 when a document differs."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="write the documents")
    args = parser.parse_args()

    names = list(snapshot.documents())
    if not args.write:
        changed = []
        for name in names:
            path = snapshot.SNAPSHOT_DIR / f"{name}.txt"
            if not path.is_file() or path.read_text(encoding="utf-8") != snapshot.render(name):
                changed.append(name)
        print(f"{len(names) - len(changed)} of {len(names)} documents equal the snapshot")
        for name in changed:
            print(f"  differs: {name}")
        return 1 if changed else 0

    if os.environ.get("NUMBA_DISABLE_JIT", "0") not in ("", "0"):
        print("refusing to write with NUMBA_DISABLE_JIT set: write from the compiled path")
        return 2
    snapshot.SNAPSHOT_DIR.mkdir(exist_ok=True)
    for stale in snapshot.SNAPSHOT_DIR.glob("*.txt"):
        if stale.stem not in names:
            stale.unlink()
    total = 0
    for name in names:
        text = snapshot.render(name)
        (snapshot.SNAPSHOT_DIR / f"{name}.txt").write_text(text, encoding="utf-8", newline="\n")
        total += len(text)
    print(f"wrote {len(names)} documents, {total / 1e6:.2f} MB, to {snapshot.SNAPSHOT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
