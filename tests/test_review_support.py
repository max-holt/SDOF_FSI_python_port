"""Review safety net for the supporting Python: sweep rows, exported files and histories.

The clean-code review (``docs/review/charter.md``) also covers ``trace.py``, ``export.py``,
``histories.py``, ``viz/geometry.py`` and ``tools/``. ``tests/test_review_snapshot.py`` pins
the solver's outputs; this file pins what the supporting code makes of them, against files
under ``tests/review_support/`` that ``tools/review_support.py --write`` stored from the
code as it stood before the review. Every comparison is exact:

* **sweep rows**: ``tools/sweep_jc.py run --tier 1 --subset 0.01`` (16 cases, every level
  of every dimension, both solvers) writes a CSV whose cells equal the stored CSV's as
  text, except the four columns that record the run and not the case (the two timings, the
  CPU and the git sha). The CSV writer prints a float with ``repr``, which round-trips, so
  equal text is equal bits. Compiled runs only: one case takes 25 to 105 s in pure Python,
  and the sweep tool itself contains no compiled code.
* **exports**: ``tools/export.py trace`` on fixed cases and ``tools/export.py sweep`` on
  the golden case table and on the stored sweep CSV write files that are byte-identical to
  the stored ones, with ``meta.git_sha`` and ``meta.created_utc`` held fixed.
* **histories**: the generators of ``surge_sdof.histories`` reproduce the stored arrays
  and statistics as ``float.hex()`` text.

The histories, and the sweep rows computed from them, depend on the host: numpy picks its
``sin`` / ``exp`` kernel by CPU, and the AVX-512 kernel (``X86_V4``, the one the files were
stored with) rounds differently from the others in the last bit. On a host where numpy
picks another kernel those two checks skip with that reason; the exports do not depend on
it and always run. ``NPY_DISABLE_CPU_FEATURES=X86_V4`` reproduces such a host.

Every call into the code under review goes through the adapter section, the one place a
later rename is absorbed (the stored files keep their names and, until the schema bump the
charter schedules, their content). The files are rewritten only for an approved change of
behaviour or of the data format, never to make a refactoring pass.
"""

from __future__ import annotations

import contextlib
import csv
import functools
import importlib.util
import io
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
from numpy.lib import introspect
from test_review_snapshot import _value_lines

from surge_sdof import export, histories

REPO = Path(__file__).resolve().parents[1]
SUPPORT_DIR = Path(__file__).parent / "review_support"
sys.path.insert(0, str(REPO / "tools"))  # tools/export.py imports tools/cases.py


def _load_tool(name: str):
    """A ``tools/`` script as a module that is not entered in ``sys.modules``, as the other
    tests load them: hypothesis seeds its examples with the numeric constants of every
    project module it finds there, so registering a tool would change the examples of
    ``tests/test_properties.py``."""
    spec = importlib.util.spec_from_file_location(name, REPO / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


export_cli = _load_tool("export")
sweep_jc = _load_tool("sweep_jc")

PURE_PYTHON = os.environ.get("NUMBA_DISABLE_JIT", "0") not in ("", "0")

STORED_KERNEL = "X86_V4"
"""numpy's kernel for ``sin`` and ``exp`` of float64 on the host that stored the files."""


def numpy_kernel() -> str:
    """The kernel numpy dispatches float64 ``sin`` and ``exp`` to on this host."""
    info = introspect.opt_func_info(func_name="^(sin|exp)$", signature="float64")
    current = {
        target["current"] for by_signature in info.values() for target in by_signature.values()
    }
    return "/".join(sorted(current))


other_kernel = pytest.mark.skipif(
    numpy_kernel() != STORED_KERNEL,
    reason=(
        f"numpy uses its {numpy_kernel()} kernel for sin / exp here and the stored histories "
        f"come from {STORED_KERNEL}: the last bits differ whatever the code does"
    ),
)

FIXED_SHA = "0" * 40
FIXED_CREATED = "2026-11-16T00:00:00Z"

# ------------------------------------------------------------------ the adapter

SWEEP_CSV = "sweep_tier1_subset1.csv"
SWEEP_ARGV = ("run", "--tier", "1", "--subset", "0.01", "--jobs", "1")
# Columns that record the run (timings, machine, checkout), not the case.
RUN_COLUMNS = ("t_lumped_s", "t_jc_s", "cpu", "git_sha")

# A plain step on a short pipe: 24 samples of 80 sub-steps.
_STEP = (
    "trace --step --amplitude 1600 --area 0.05 --length 6 --nat-freq 2 --sample-freq 10 "
    "--step-qty 80 --celerity 1200 --mass-per-len 100 --ei 1e7 --duration 2.4"
)
# The same with no round number in it, so that a regrouped product changes a bit: the cell
# spacing ``celerity * dt`` of the first step is 1.5 m exactly.
_ODD_STEP = (
    "trace --step --amplitude 1341.7 --length 7.3 --nat-freq 2.3 --sample-freq 13 "
    "--step-qty 200 --celerity 1237 --mass-per-len 93.7 --ei 1.13e7 --duration 1.9 "
    "--lead-in 0.17 --damping 0.7 --density 998.2"
)
# Stored file -> the tools/export.py command that writes it (``--out`` is appended).
EXPORT_ARGV = {
    "trace_step_lumped.json": f"{_STEP} --solver lumped --mu 0.3 --trace-frames 148",
    "trace_odd_step_lumped.json": f"{_ODD_STEP} --solver lumped --mu 0.07 --trace-frames 102",
    "trace_odd_step_jc.json": f"{_ODD_STEP} --solver jc --mu 0.07 --area 0.0523 --trace-every 96",
    "trace_step_jc.json": f"{_STEP} --solver jc --mu 0.0001 --budget-mb 0.25",
    "trace_step_jc_named.json": f"{_STEP} --solver jc --mu 0.3 --trace-every 64 --name review",
    "trace_example_lumped.json": "trace --golden example_lumped --trace-every 40",
    "trace_example_jc.json": "trace --golden example_jc --trace-every 40",
    "sweep_golden.json": "sweep --from-csv tests/fixtures/curve_10in/cases.csv",
    "sweep_tier1_subset1.json": (
        f"sweep --from-csv tests/review_support/{SWEEP_CSV} --cpu review --tier 1"
    ),
}

# The history cases are data (``tests/review_support_cases.json``), not literals in this
# module: hypothesis seeds its examples with the numeric constants of every project module
# that is imported, so a float written here would change the examples of
# ``tests/test_properties.py`` (derandomised or not).
CASES = json.loads((Path(__file__).parent / "review_support_cases.json").read_text("utf-8"))
# Stored document -> [generator, positional arguments, keyword arguments]. The first four
# are histories of the sweep (``sweep_jc.case_history``); the rest leave every default.
HISTORY_CALLS = CASES["history_calls"]
# Snapshot key -> attribute of today's ``History``.
_HISTORY_FIELDS = {key: key for key in histories.PARAM_KEYS} | {
    "decay_s": "decay_s",
    "duration_s": "duration_s",
    "n_samples": "n_samples",
    "peak": "peak",
    "p_min": "p_min",
    "mean": "mean",
    "rms": "rms",
    "noise_rms": "noise_rms",
    "version": "version",
    "time": "time",
    "pressure": "pressure",
}


@contextlib.contextmanager
def _fixed_provenance():
    """Hold ``meta.git_sha`` and ``meta.created_utc`` of every exported document fixed."""
    saved = export.git_sha, export.created_utc
    export.git_sha = lambda cwd=None: FIXED_SHA
    export.created_utc = lambda now=None: FIXED_CREATED
    try:
        yield
    finally:
        export.git_sha, export.created_utc = saved


@contextlib.contextmanager
def _in_repo():
    """Run with the repository as the working directory (``meta.source`` is the path as
    given on the command line) and the tool's progress text swallowed."""
    before = Path.cwd()
    os.chdir(REPO)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            yield
    finally:
        os.chdir(before)


def run_sweep(out_dir: Path) -> Path:
    """Run the small sweep through the tool's command line; the CSV it wrote."""
    # the tool's process pool pickles its worker by module name, so the module is
    # importable for the duration of the run and no longer
    sys.modules["sweep_jc"] = sweep_jc
    try:
        with _in_repo():
            sweep_jc.main([*SWEEP_ARGV, "--out", str(out_dir)])
    finally:
        del sys.modules["sweep_jc"]
    (path,) = Path(out_dir).glob("*.csv")
    return path


def export_bytes(name: str, out_dir: Path) -> bytes:
    """Run the ``tools/export.py`` command of stored file ``name``; the bytes it wrote."""
    out = Path(out_dir) / name
    with _in_repo(), _fixed_provenance():
        export_cli.main([*EXPORT_ARGV[name].split(), "--out", str(out)])
    return out.read_bytes()


def history_values(name: str) -> dict:
    """The generated history of document ``name`` under the snapshot's own keys."""
    generator, args, kwargs = HISTORY_CALLS[name]
    history = getattr(histories, generator)(*args, **kwargs)
    values = {key: getattr(history, attr) for key, attr in _HISTORY_FIELDS.items()}
    values["force"] = history.force(CASES["fluid_area"])  # m²
    return values


def rebuilt_pressure(name: str) -> np.ndarray:
    """The pressure of document ``name`` rebuilt from the history's own parameters."""
    generator, args, kwargs = HISTORY_CALLS[name]
    history = getattr(histories, generator)(*args, **kwargs)
    return histories.from_params(history.params()).pressure


def building_block_values() -> dict:
    """``p_cap``, ``decay_rate`` and ``envelope`` on fixed arguments."""
    tau = np.arange(CASES["envelope_tau"]["count"]) / CASES["envelope_tau"]["sample_freq"]
    values = {
        f"p_cap({p_design!r}, {fraction!r})": histories.p_cap(p_design, fraction)
        for p_design, fraction in CASES["p_cap"]
    }
    for f, cycles, fraction in CASES["envelope"]:
        label = f"({f!r}, {cycles!r}, {fraction!r})"
        values[f"decay_rate{label}"] = histories.decay_rate(f, cycles, fraction)
        values[f"envelope{label}"] = histories.envelope(tau, f, cycles, fraction)
    return values


# ------------------------------------------------------------------ rendering

HISTORY_DOCUMENTS = (*HISTORY_CALLS, "history_building_blocks")


def _lines(key: str, value) -> list[str]:
    if value is None or isinstance(value, str):
        return [f"{key} = {value!r}"]
    return _value_lines(key, value)


def render_history(name: str) -> str:
    """Document ``name`` as text: floats as ``float.hex()``, one array element a line."""
    values = building_block_values() if name == "history_building_blocks" else history_values(name)
    lines = [f"# review support snapshot: {name}"]
    for key, value in values.items():
        lines.extend(_lines(key, value))
    return "\n".join(lines) + "\n"


def sweep_cells(path: Path) -> list[list[str]]:
    """The CSV's cells as text, header first, without the ``RUN_COLUMNS``."""
    with Path(path).open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    keep = [i for i, name in enumerate(rows[0]) if name not in RUN_COLUMNS]
    return [[row[i] for i in keep] for row in rows]


@functools.cache
def _stored_sweep() -> list[list[str]]:
    return sweep_cells(SUPPORT_DIR / SWEEP_CSV)


# ------------------------------------------------------------------ the tests


@other_kernel
@pytest.mark.skipif(PURE_PYTHON, reason="a sweep case takes 25 to 105 s in pure Python")
def test_sweep_rows_equal_the_stored_csv(tmp_path):
    stored = _stored_sweep()
    cells = sweep_cells(run_sweep(tmp_path))
    assert cells[0] == stored[0], "the CSV header changed"
    assert [row[0] for row in cells] == [row[0] for row in stored], "the subset changed"
    differing = [
        f"{row[0]}.{name}: {ours} != stored {theirs}"
        for row, stored_row in zip(cells[1:], stored[1:], strict=True)
        for name, ours, theirs in zip(cells[0], row, stored_row, strict=True)
        if ours != theirs
    ]
    assert not differing, f"{len(differing)} cells differ, first: {differing[:5]}"


@pytest.mark.parametrize("name", list(EXPORT_ARGV))
def test_export_is_byte_identical_to_the_stored_file(name, tmp_path):
    written = export_bytes(name, tmp_path)
    stored = (SUPPORT_DIR / name).read_bytes()
    if written != stored:
        at = next(
            (i for i, (a, b) in enumerate(zip(written, stored, strict=False)) if a != b),
            min(len(written), len(stored)),
        )
        pytest.fail(
            f"{name}: {len(written)} bytes written, {len(stored)} stored, first difference at "
            f"byte {at}: {written[at - 40 : at + 40]!r} != stored {stored[at - 40 : at + 40]!r}"
        )


@other_kernel
@pytest.mark.parametrize("name", HISTORY_DOCUMENTS)
def test_history_equals_the_stored_document(name):
    stored = (SUPPORT_DIR / f"{name}.txt").read_text(encoding="utf-8")
    actual = render_history(name)
    if actual != stored:
        ours, theirs = actual.splitlines(), stored.splitlines()
        at = next(
            (i for i, (a, b) in enumerate(zip(ours, theirs, strict=False)) if a != b),
            min(len(ours), len(theirs)),
        )
        pytest.fail(
            f"{name}: line {at + 1} is {ours[at : at + 1]} and the stored document has "
            f"{theirs[at : at + 1]}"
        )


def test_the_stored_files_are_the_documents_and_nothing_else():
    expected = {SWEEP_CSV, *EXPORT_ARGV, *(f"{name}.txt" for name in HISTORY_DOCUMENTS)}
    assert {path.name for path in SUPPORT_DIR.iterdir()} == expected


def test_the_cases_exercise_what_they_claim():
    """The stored files are not trivially equal: the sweep rows cover every level of
    Tier 1 with no failed run, the traces have a moving column and both friction states,
    the low-pass really filters and the round trip through ``params`` is exact."""
    stored = _stored_sweep()
    header = stored[0]
    rows = [dict(zip(header, row, strict=True)) for row in stored[1:]]
    assert len(rows) == 16
    assert all(row["error"] == "" and row["jc_short_pipe"] == "0" for row in rows)
    assert all(row["f_eq_lumped"] != row["f_eq_jc"] for row in rows)
    tier = sweep_jc.TIERS[1]
    assert {float(row["length_m"]) for row in rows} == set(tier["lengths"])
    assert {float(row["nat_freq_hz"]) for row in rows} == set(tier["nat_freqs"])
    assert {row["history_type"] for row in rows} == set(histories.KINDS)

    jc = export.read_json(SUPPORT_DIR / "trace_step_jc.json")
    assert jc["meta"]["n_cells"] > 0 and any(v != 0.0 for v in jc["cells"]["p"]["data"])
    odd = export.read_json(SUPPORT_DIR / "trace_odd_step_jc.json")
    assert odd["meta"]["n_cells"] > 0 and any(v != 0.0 for v in odd["cells"]["p"]["data"])
    assert not float(odd["geometry"]["spacing_m"] * 8).is_integer()
    lumped = export.read_json(SUPPORT_DIR / "trace_step_lumped.json")
    assert lumped["meta"]["n_cells"] == 0 and "cells" not in lumped
    assert set(lumped["frames"]["stick"]) == {0, 1}
    for doc in (jc, lumped):
        assert doc["meta"]["git_sha"] == FIXED_SHA
        assert doc["meta"]["created_utc"] == FIXED_CREATED
    passthrough = export.read_json(SUPPORT_DIR / "sweep_tier1_subset1.json")
    assert passthrough["meta"]["n_rows"] == 16
    assert passthrough["columns"]["case_id"] == [row["case_id"] for row in rows]

    white = history_values("history_noise0")
    assert white["f_cut"] == white["sample_freq"] / 2  # no filtering
    filtered = history_values("history_noise_lowpass")
    assert filtered["f_cut"] < filtered["sample_freq"] / 2
    for name in HISTORY_CALLS:
        assert np.array_equal(rebuilt_pressure(name), history_values(name)["pressure"])
