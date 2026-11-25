"""Check or write the review's supporting-code snapshot (``tests/review_support/``).

The cases, the adapter and the comparisons live in ``tests/test_review_support.py``; this
script only renders the files and compares or stores them, so the test and the generator
cannot disagree.

    .venv/bin/python tools/review_support.py            # compare, exit 1 on a difference
    .venv/bin/python tools/review_support.py --write    # (re)write every file

``--write`` is for an approved change of behaviour or of the data format only, never to
make a refactoring pass: see ``docs/review/charter.md``. Neither mode runs with the JIT
disabled (the sweep takes an hour in pure Python and the stored files come from the
compiled path). The comparison runs on any host: the sweep runs on the stored histories,
and the history documents are compared exactly on the stored files' ``sin`` / ``exp``
kernel (``test_review_support.STORED_KERNEL``) and at ``history_rtol`` elsewhere, as the
test does; the report says which. ``--write`` refuses on another kernel (the histories it
would store differ there in the last bit). Write from a clean tree: the sweep CSV records the checkout's sha, with ``-dirty`` appended
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
    """Replace every stored file under ``tests/review_support/``.

    Parameters
    ----------
    sweep_csv : Path
        The sweep CSV just run, stored first (the sweep export reads it).
    tmp : Path
        A scratch directory for the exports.

    Returns
    -------
    str
        The one-line report.
    """
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
    text = support.render_sweep_histories(support.generated_sweep_histories())
    (stored / support.SWEEP_HISTORIES).write_text(text, encoding="utf-8", newline="\n")
    sizes = [path.stat().st_size for path in stored.iterdir()]
    return f"wrote {len(sizes)} files, {sum(sizes) / 1e6:.2f} MB, to {stored}"


def differing(sweep_csv: Path, tmp: Path) -> tuple[list[str], int]:
    """The stored files today's code does not reproduce.

    Parameters
    ----------
    sweep_csv : Path
        The sweep CSV just run on the stored histories.
    tmp : Path
        A scratch directory for the exports.

    Returns
    -------
    tuple
        ``(names, count)``: the files that differ and the number compared.
    """
    stored = support.SUPPORT_DIR
    equal = {
        support.SWEEP_CSV: support.sweep_cells(sweep_csv)
        == support.sweep_cells(stored / support.SWEEP_CSV)
    }
    for name in support.EXPORT_ARGV:
        equal[name] = support.export_bytes(name, tmp) == (stored / name).read_bytes()
    for name in support.HISTORY_DOCUMENTS:
        path = stored / f"{name}.txt"
        expected = path.read_text(encoding="utf-8")
        equal[path.name] = not support.history_difference(
            name, expected, support.render_history(name)
        )
    path = stored / support.SWEEP_HISTORIES
    generated = support.render_sweep_histories(support.generated_sweep_histories())
    expected = path.read_text(encoding="utf-8")
    equal[path.name] = not support.history_difference(path.name, expected, generated)
    return [name for name, same in equal.items() if not same], len(equal)


def main() -> int:
    """Compare the stored files with today's code, or write them with ``--write``
    (compiled path, the stored numpy kernel); the exit status, 1 when a file differs."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="write the files")
    args = parser.parse_args()
    if os.environ.get("NUMBA_DISABLE_JIT", "0") not in ("", "0"):
        print("refusing to run with NUMBA_DISABLE_JIT set: the sweep needs the compiled path")
        return 2
    if args.write and support.numpy_kernel() != support.STORED_KERNEL:
        print(
            f"refusing to write: numpy uses its {support.numpy_kernel()} kernel for sin / exp "
            f"here, the stored files come from {support.STORED_KERNEL}"
        )
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if args.write:
            # the stored CSV is what the generators give: the run that writes it does not
            # read the stored histories it is about to replace
            sweep_csv = support.run_sweep(tmp / "sweep", stored_histories=False)
            print(write(sweep_csv, tmp))
            return 0
        sweep_csv = support.run_sweep(tmp / "sweep")
        how = "exactly" if support.history_mode() == "exact" else "at history_rtol"
        print(
            f"histories compared {how} (numpy kernel {support.numpy_kernel()}, stored "
            f"{support.STORED_KERNEL}); the sweep runs on the stored histories"
        )
        changed, n_files = differing(sweep_csv, tmp)
    print(f"{n_files - len(changed)} of {n_files} files equal the stored ones")
    for name in changed:
        print(f"  differs: {name}")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
