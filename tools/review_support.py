"""Check or write the review's supporting-code snapshot (``tests/review_support/``).

The cases, the adapter and the comparisons live in ``tests/test_review_support.py``; this
script only renders the files and compares or stores them, so the test and the generator
cannot disagree.

    .venv/bin/python tools/review_support.py            # compare, exit 1 on a difference
    .venv/bin/python tools/review_support.py --write    # (re)write every file

``--write`` is for an approved change of behaviour or of the data format only, never to
make a refactoring pass: see ``docs/review/charter.md``. It refuses to run with the JIT
disabled (the sweep takes an hour in pure Python and the stored files come from the
compiled path) or on a host whose numpy does not use the stored files' ``sin`` / ``exp``
kernel (``test_review_support.STORED_KERNEL``; the histories differ there in the last bit).
Write from a clean tree: the sweep CSV records the checkout's sha, with ``-dirty`` appended
when ``src``, ``tests`` or ``tools`` have uncommitted changes.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tests"))

import test_review_support as support  # noqa: E402


def write(sweep_csv: Path, tmp: Path) -> str:
    """Replace every stored file; the one-line report."""
    stored = support.SUPPORT_DIR
    stored.mkdir(exist_ok=True)
    for stale in stored.iterdir():
        stale.unlink()
    # the sweep export reads the stored CSV, so the CSV goes first
    shutil.copyfile(sweep_csv, stored / support.SWEEP_CSV)
    for name in support.EXPORT_ARGV:
        (stored / name).write_bytes(support.export_bytes(name, tmp))
    for name in support.HISTORY_DOCUMENTS:
        text = support.render_history(name)
        (stored / f"{name}.txt").write_text(text, encoding="utf-8", newline="\n")
    sizes = [path.stat().st_size for path in stored.iterdir()]
    return f"wrote {len(sizes)} files, {sum(sizes) / 1e6:.2f} MB, to {stored}"


def differing(sweep_csv: Path, tmp: Path) -> tuple[list[str], int]:
    """The stored files today's code does not reproduce, and the number compared."""
    stored = support.SUPPORT_DIR
    equal = {
        support.SWEEP_CSV: support.sweep_cells(sweep_csv)
        == support.sweep_cells(stored / support.SWEEP_CSV)
    }
    for name in support.EXPORT_ARGV:
        equal[name] = support.export_bytes(name, tmp) == (stored / name).read_bytes()
    for name in support.HISTORY_DOCUMENTS:
        path = stored / f"{name}.txt"
        equal[path.name] = path.read_text(encoding="utf-8") == support.render_history(name)
    return [name for name, same in equal.items() if not same], len(equal)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="write the files")
    args = parser.parse_args()
    if os.environ.get("NUMBA_DISABLE_JIT", "0") not in ("", "0"):
        print("refusing to run with NUMBA_DISABLE_JIT set: the sweep needs the compiled path")
        return 2
    if support.numpy_kernel() != support.STORED_KERNEL:
        print(
            f"refusing to run: numpy uses its {support.numpy_kernel()} kernel for sin / exp "
            f"here, the stored files come from {support.STORED_KERNEL}"
        )
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sweep_csv = support.run_sweep(tmp / "sweep")
        if args.write:
            print(write(sweep_csv, tmp))
            return 0
        changed, n_files = differing(sweep_csv, tmp)
    print(f"{n_files - len(changed)} of {n_files} files equal the stored ones")
    for name in changed:
        print(f"  differs: {name}")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
