"""Per-function metrics of the solver modules under review (``docs/review/charter.md``).

Runs ruff and radon on the modules in scope and prints one markdown table: argument
count (ruff PLR0913), cyclomatic complexity (ruff C901 and radon cc), branches (ruff
PLR0912), statements (ruff PLR0915), maximum nesting depth (ruff PLR1702, preview), and
length in lines (radon's ``lineno`` .. ``endline``, signature and docstring included, with
the lines left after the docstring beside it).

Ruff only reports a function that exceeds a threshold, so every threshold is set to 0 on
the command line; ``pyproject.toml`` is not touched. The commands are printed with
``--commands`` and recorded in ``docs/review/baseline.md``.

    .venv/bin/python tools/review_baseline.py > table.md
    .venv/bin/python tools/review_baseline.py --commands
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODULES = (
    "moc",
    "structure",
    "coupling",
    "loads",
    "response",
    "pressure",
    "_vba_semantics",
    "trace",
)
FILES = [f"src/surge_sdof/{name}.py" for name in MODULES]

RUFF = [
    sys.executable,
    "-m",
    "ruff",
    "check",
    "--preview",
    "--isolated",
    "--no-cache",
    "--output-format",
    "json",
    "--select",
    "C901,PLR0912,PLR0913,PLR0915,PLR1702",
    "--config",
    "lint.mccabe.max-complexity = 0",
    "--config",
    "lint.pylint.max-args = 0",
    "--config",
    "lint.pylint.max-branches = 0",
    "--config",
    "lint.pylint.max-statements = 0",
    "--config",
    "lint.pylint.max-nested-blocks = 0",
]
RADON = [sys.executable, "-m", "radon", "cc", "--json", "--show-closures"]

COLUMN_OF = {"PLR0913": "args", "C901": "cc", "PLR0912": "branches", "PLR0915": "statements"}
TARGETS = {"args": 6, "cc": 10, "statements": 50, "nesting": 3, "code": 40}


def _functions(path: str) -> list[dict]:
    """Every function and method of ``path`` with its line span and docstring length."""
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    found = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                first = child.body[0]
                has_doc = (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                )
                doc_lines = first.end_lineno - first.lineno + 1 if has_doc else 0
                start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                found.append(
                    {
                        "file": path,
                        "name": prefix + child.name,
                        "def_line": child.lineno,
                        "start": start,
                        "end": child.end_lineno,
                        "doc_lines": doc_lines,
                        "compiled": any("njit" in ast.unparse(d) for d in child.decorator_list),
                    }
                )
                visit(child, prefix + child.name + ".")
            elif isinstance(child, ast.ClassDef):
                visit(child, prefix + child.name + ".")

    visit(tree, "")
    return found


def _run_json(command: list[str]) -> object:
    done = subprocess.run(command + FILES, cwd=REPO, capture_output=True, text=True, check=False)
    return json.loads(done.stdout)


def collect() -> list[dict]:
    rows = [row for path in FILES for row in _functions(path)]
    for row in rows:
        row.update(args=0, cc=1, branches=0, statements=0, nesting=0, radon_cc=None)

    def owner(path: str, line: int) -> dict | None:
        inside = [r for r in rows if r["file"] == path and r["start"] <= line <= r["end"]]
        return max(inside, key=lambda r: r["start"]) if inside else None

    for item in _run_json(RUFF):
        path = str(Path(item["filename"]).relative_to(REPO))
        row = owner(path, item["location"]["row"])
        value = int(re.search(r"\((\d+) > 0\)", item["message"]).group(1))
        if item["code"] == "PLR1702":
            row["nesting"] = max(row["nesting"], value)
        else:
            row[COLUMN_OF[item["code"]]] = value

    def radon_blocks(blocks: list[dict]):
        for block in blocks:
            yield block
            yield from radon_blocks(block.get("methods", []))
            yield from radon_blocks(block.get("closures", []))

    for path, blocks in _run_json(RADON).items():
        for block in radon_blocks(blocks):
            if block["type"] == "class":
                continue
            row = owner(path, block["lineno"])
            if row is not None and row["def_line"] == block["lineno"]:
                row["radon_cc"] = block["complexity"]
                row["length"] = block["endline"] - block["lineno"] + 1
    for row in rows:
        row.setdefault("length", row["end"] - row["def_line"] + 1)
        row["code"] = row["length"] - row["doc_lines"]
    return rows


def _cell(row: dict, key: str) -> str:
    value = row[key]
    return f"**{value}**" if key in TARGETS and value > TARGETS[key] else str(value)


def table(rows: list[dict]) -> str:
    lines = [
        "| function | line | args | cc (ruff) | cc (radon) | branches | statements | nesting"
        " | length | code lines |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        module = Path(row["file"]).stem
        name = f"`{module}.{row['name']}`" + (" (njit)" if row["compiled"] else "")
        cells = [
            name,
            str(row["def_line"]),
            _cell(row, "args"),
            _cell(row, "cc"),
            str(row["radon_cc"]),
            str(row["branches"]),
            _cell(row, "statements"),
            _cell(row, "nesting"),
            str(row["length"]),
            _cell(row, "code"),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def summary(rows: list[dict]) -> str:
    def over(key: str) -> int:
        return sum(row[key] > TARGETS[key] for row in rows)

    return (
        f"{len(rows)} functions; over target: {over('args')} with more than 6 arguments, "
        f"{over('cc')} with complexity over 10, {over('statements')} with more than 50 "
        f"statements, {over('nesting')} nested deeper than 3, {over('code')} longer than 40 "
        "lines after the docstring."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--commands", action="store_true", help="print the two commands")
    args = parser.parse_args()
    if args.commands:
        for command in (RUFF, RADON):
            shown = [".venv/bin/python" if part == sys.executable else part for part in command]
            print(" ".join(f"'{p}'" if " " in p else p for p in shown + FILES))
        return 0
    rows = collect()
    print(summary(rows))
    print()
    print(table(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
