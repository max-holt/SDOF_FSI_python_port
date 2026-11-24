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
  equal text is equal bits. The run takes its pressure histories from the stored document
  ``sweep_histories.txt`` instead of generating them, so the check does not depend on
  numpy's ``sin`` / ``exp`` kernels; the generators themselves are pinned by the history
  documents. Compiled runs only: one case takes 25 to 105 s in pure Python, and the sweep
  tool itself contains no compiled code.
* **exports**: ``tools/export.py trace`` on fixed cases and ``tools/export.py sweep`` on
  the golden case table and on the stored sweep CSV write files that are byte-identical to
  the stored ones, with ``meta.git_sha`` and ``meta.created_utc`` held fixed.
* **histories**: the generators of ``surge_sdof.histories`` reproduce the stored arrays
  and statistics as ``float.hex()`` text.

The generated histories depend on the host: numpy picks its ``sin`` / ``exp`` kernel by
CPU, and the AVX-512 kernel (``X86_V4``, the one the files were stored with) rounds
differently from the others in the last bit. Where numpy uses the stored kernel the history
documents are compared exactly; elsewhere every float in them is compared at the relative
tolerance ``history_rtol`` of ``tests/review_support_cases.json`` (1e-12) and every other
line exactly. Neither mode skips: the run's summary says which one ran. The exact checks
are authoritative on the reference platforms (the CI Linux runner and the cloud
environment, charter "Reference platform"). ``NPY_DISABLE_CPU_FEATURES=X86_V4`` reproduces
a host without the stored kernel.

Every call into the code under review goes through the adapter section, the one place a
later rename is absorbed (the stored files keep their names and, until the schema bump the
charter schedules, their content). The files are rewritten only for an approved change of
behaviour or of the data format, never to make a refactoring pass.
"""

from __future__ import annotations

import ast
import contextlib
import csv
import dataclasses
import functools
import importlib.util
import io
import json
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
from numpy.lib import introspect
from test_review_snapshot import _value_lines

from surge_sdof import export, histories

REPO = Path(__file__).resolve().parents[1]
SUPPORT_DIR = Path(__file__).parent / "review_support"


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
# sweep_jc's own modules, entered in sys.modules by its imports (review session R.8, plan 5.12)
sweep_grid = sys.modules["sweep_grid"]
sweep_rows = sys.modules["sweep_rows"]

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


def history_mode() -> str:
    """How the history documents are compared on this host: ``"exact"`` with the stored
    kernel, ``"tolerance"`` with any other."""
    return "exact" if numpy_kernel() == STORED_KERNEL else "tolerance"


REPORT: list[str] = []
"""Lines for the run's summary (``tests/conftest.py`` prints them): which mode ran."""
if PURE_PYTHON:
    REPORT.append("sweep rows: not run with NUMBA_DISABLE_JIT (a case takes 25 to 105 s)")

FIXED_SHA = "0" * 40
FIXED_CREATED = "2026-11-16T00:00:00Z"

# ------------------------------------------------------------------ the adapter

SWEEP_CSV = "sweep_tier1_subset1.csv"
# The pressure histories the sweep run is fed, one per distinct history of its rows.
SWEEP_HISTORIES = "sweep_histories.txt"
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
# are histories of the sweep (``sweep_rows.case_history``); the rest leave every default.
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


def _history_key(size_in, history_type, f_osc_hz, seed, amplitude_fraction) -> tuple:
    """What a sweep case's pressure history depends on (the design pressure follows from
    the size)."""
    return (int(size_in), history_type, f_osc_hz, seed, float(amplitude_fraction))


def _key_of_row(row: dict) -> tuple:
    """The history key of a stored CSV row (cells as text)."""
    return _history_key(
        row["size_in"],
        row["history_type"],
        float(row["f_osc_hz"]) if row["f_osc_hz"] else None,
        int(row["seed"]) if row["seed"] else None,
        row["amplitude_fraction"],
    )


def _label(key: tuple) -> str:
    size_in, history_type, f_osc_hz, seed, amplitude_fraction = key
    return f"size {size_in} {history_type} f_osc {f_osc_hz!r} seed {seed!r} amplitude {amplitude_fraction!r}"


def generated_sweep_histories() -> dict:
    """Each distinct history of the stored sweep rows, from the generators (host-dependent:
    written with ``--write`` on the stored kernel only)."""
    keys = dict.fromkeys(_key_of_row(row) for row in _stored_sweep_rows())
    out = {}
    for key in keys:
        size_in, history_type, f_osc_hz, seed, amplitude_fraction = key
        case = sweep_grid.Case(
            size_in, None, None, history_type, f_osc_hz, seed, amplitude_fraction, None
        )
        out[key] = sweep_rows.case_history(case, sweep_grid.pipe(size_in).design_pressure)
    return out


def render_sweep_histories(by_key: dict) -> str:
    """The sweep's histories as text: every ``History`` field, floats as ``float.hex()``,
    the pressure one element a line (``time`` is not stored: no sweep column reads it)."""
    lines = ["# review support snapshot: the pressure histories the sweep check runs on"]
    for key, history in by_key.items():
        lines.append(f"## {_label(key)}")
        for field in dataclasses.fields(history):
            if field.name != "time":
                lines.extend(_lines(field.name, getattr(history, field.name)))
    return "\n".join(lines) + "\n"


def _parse_scalar(text: str):
    if text == "None":
        return None
    if text.startswith("'"):
        return ast.literal_eval(text)
    if text.lstrip("-").startswith(("0x", "inf", "nan")):
        return float.fromhex(text)
    return int(text)


@functools.cache
def stored_sweep_histories() -> dict:
    """The stored sweep histories as ``History`` objects, keyed like the rows."""
    labels = {_label(key): key for key in dict.fromkeys(map(_key_of_row, _stored_sweep_rows()))}
    text = (SUPPORT_DIR / SWEEP_HISTORIES).read_text(encoding="utf-8").splitlines()[1:]
    out, fields, lines = {}, None, iter(text)
    for line in lines:
        if line.startswith("## "):
            fields = {}
            out[labels[line[3:]]] = fields
        elif " : " in line:
            name, spec = line.split(" : ")
            count = int(spec.split("(")[1].rstrip(",)"))
            fields[name] = np.array([float.fromhex(next(lines)) for _ in range(count)])
        else:
            name, value = line.split(" = ", 1)
            fields[name] = _parse_scalar(value)
    histories_ = {}
    for key, fields in out.items():
        # ``time`` is rebuilt as the generators build it; nothing in a sweep row reads it
        fields["time"] = np.arange(fields["n_samples"]) / fields["sample_freq"]
        histories_[key] = histories.History(**fields)
    return histories_


def _stored_history(case, p_design: float) -> histories.History:
    """``sweep_rows.case_history`` replaced: the stored history of the case (``p_design``
    follows from ``case.size_in``, which is part of the key)."""
    return stored_sweep_histories()[
        _history_key(
            case.size_in, case.history_type, case.f_osc_hz, case.seed, case.amplitude_fraction
        )
    ]


def _pool(max_workers: int):
    """The tool's process pool with the fork start method, so that the workers inherit the
    stored histories; a thread pool where the platform cannot fork."""
    if "fork" in multiprocessing.get_all_start_methods():
        return ProcessPoolExecutor(max_workers, mp_context=multiprocessing.get_context("fork"))
    return ThreadPoolExecutor(max_workers)


def run_sweep(out_dir: Path, stored_histories: bool = True) -> Path:
    """Run the small sweep through the tool's command line; the CSV it wrote. With
    ``stored_histories`` the cases take their pressure histories from
    ``SWEEP_HISTORIES`` instead of the generators."""
    # the tool's process pool pickles its worker by module name, so the module is
    # importable for the duration of the run and no longer
    sys.modules["sweep_jc"] = sweep_jc
    # run_case and case_history live in tools/sweep_rows.py since review session R.8
    saved = sweep_rows.case_history, sweep_jc.ProcessPoolExecutor
    if stored_histories:
        stored_sweep_histories()  # parsed once, before the workers fork
        sweep_rows.case_history, sweep_jc.ProcessPoolExecutor = _stored_history, _pool
    try:
        with _in_repo():
            sweep_jc.main([*SWEEP_ARGV, "--out", str(out_dir)])
    finally:
        sweep_rows.case_history, sweep_jc.ProcessPoolExecutor = saved
        del sys.modules["sweep_jc"]
    (path,) = Path(out_dir).glob("*.csv")
    return path


def export_bytes(name: str, out_dir: Path) -> bytes:
    """Run the ``tools/export.py`` command of stored file ``name``; the bytes it wrote."""
    out = Path(out_dir) / name
    with _in_repo(), _fixed_provenance():
        export_cli.main([*EXPORT_ARGV[name].split(), "--out", str(out)])
    return out.read_bytes()


# Keyword of a stored generator call -> today's keyword of the generators ``step``,
# ``step_sine``, ``step_noise`` (renamed in R.3; ``canonical`` and ``from_params`` keep theirs
# until the public API session).
_GENERATOR_KEYWORDS = {
    "sample_freq": "sample_rate",
    "f_ref": "envelope_reference_frequency",
    "p_cap": "peak_pressure_target",
}


def _generate(name: str) -> histories.History:
    """Call the generator of document ``name`` with today's keywords."""
    generator, args, kwargs = HISTORY_CALLS[name]
    if generator not in ("canonical", "from_params"):
        kwargs = {_GENERATOR_KEYWORDS.get(key, key): value for key, value in kwargs.items()}
    return getattr(histories, generator)(*args, **kwargs)


def history_values(name: str) -> dict:
    """The generated history of document ``name`` under the snapshot's own keys."""
    history = _generate(name)
    values = {key: getattr(history, attr) for key, attr in _HISTORY_FIELDS.items()}
    values["force"] = history.force(CASES["fluid_area"])  # m²
    return values


def rebuilt_pressure(name: str) -> np.ndarray:
    """The pressure of document ``name`` rebuilt from the history's own parameters."""
    history = _generate(name)
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


def _stored_sweep_rows() -> list[dict]:
    header, *rows = _stored_sweep()
    return [dict(zip(header, row, strict=True)) for row in rows]


def history_difference(name: str, expected: str, actual: str) -> str | None:
    """Where history document ``name`` differs from the stored text, or None. In the
    ``"tolerance"`` mode a float line passes within ``history_rtol``."""
    if actual == expected:
        return None
    ours, theirs = actual.splitlines(), expected.splitlines()
    if len(ours) != len(theirs):
        return f"{name}: {len(ours)} lines, the stored document has {len(theirs)}"
    rtol = CASES["history_rtol"]
    for at, (a, b) in enumerate(zip(ours, theirs, strict=True)):
        if a == b:
            continue
        if history_mode() == "tolerance":
            left, right = a.rpartition(" = ")[2], b.rpartition(" = ")[2]
            if a[: len(a) - len(left)] == b[: len(b) - len(right)]:
                try:
                    x, y = float.fromhex(left), float.fromhex(right)
                except ValueError:
                    pass
                else:
                    if abs(x - y) <= rtol * abs(y):
                        continue
        return f"{name}: line {at + 1} is {a!r} and the stored document has {b!r}"
    return None


# ------------------------------------------------------------------ the tests


@pytest.mark.skipif(PURE_PYTHON, reason="a sweep case takes 25 to 105 s in pure Python")
def test_sweep_rows_equal_the_stored_csv(tmp_path):
    REPORT.append("sweep rows: run on the stored histories, compared exactly")
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


@pytest.mark.parametrize("name", HISTORY_DOCUMENTS)
def test_history_equals_the_stored_document(name):
    line = (
        f"histories: {history_mode()} comparison (numpy uses its {numpy_kernel()} kernel for "
        f"sin / exp here, the stored documents come from {STORED_KERNEL})"
    )
    if line not in REPORT:
        REPORT.append(line)
    stored = (SUPPORT_DIR / f"{name}.txt").read_text(encoding="utf-8")
    difference = history_difference(name, stored, render_history(name))
    if difference:
        pytest.fail(difference)


def test_stored_sweep_histories_are_the_generators_output():
    """The histories the sweep check is fed are what ``tools/sweep_jc.py`` generates for its
    rows, compared like the history documents (exactly on the stored kernel)."""
    stored = (SUPPORT_DIR / SWEEP_HISTORIES).read_text(encoding="utf-8")
    generated = render_sweep_histories(generated_sweep_histories())
    difference = history_difference(SWEEP_HISTORIES, stored, generated)
    if difference:
        pytest.fail(difference)
    assert set(stored_sweep_histories()) == {_key_of_row(row) for row in _stored_sweep_rows()}


def test_the_stored_files_are_the_documents_and_nothing_else():
    expected = {
        SWEEP_CSV,
        SWEEP_HISTORIES,
        *EXPORT_ARGV,
        *(f"{name}.txt" for name in HISTORY_DOCUMENTS),
    }
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
    assert {row["history_type"] for row in rows} == set(histories.HISTORY_TYPES)

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
