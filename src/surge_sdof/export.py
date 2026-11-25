"""Results data files for the JS viewer (Session W.1): ``docs/data_format.md`` is the contract.

``to_trace_dict(result, case_id)`` turns a traced ``PeakResponse`` into the ``trace`` document
(meta, the loop geometry of ``viz.geometry``, the per-frame columns with the synthetic rest
frame first, the JC column arrays as row-major blocks); ``to_sweep_dict(rows, ...)`` turns
sweep rows into the ``sweep`` document (the 5b sweep CSV columns, ``schema_version`` 2,
regen template, reference block);
``write_json`` / ``read_json`` serialise them under the document's rules: column-wise arrays,
floats via ``repr`` (the json module's default), no NaN (``allow_nan=False`` raises), UTF-8,
LF, compact separators, optional gzip.

Nothing here runs a solver: the module reads a ``PeakResponse`` and plain rows. Two
things reach outside it: the loop geometry (``viz.geometry``) asks the solver's set-up for
the grid a lumped trace would have, and both document builders, unless given the
provenance, ask git for the checkout's sha and stamp the current time (``_provenance``).
``tools/export.py`` is the CLI.
"""

from __future__ import annotations

import csv
import datetime as _dt
import gzip as _gzip
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from surge_sdof.trace import (
    FRAME_COLUMNS,
    FRAME_FIELDS,
    INT_FRAME_COLUMNS,
    PHASE_FREE_DECAY,
    PHASE_TRANSIT,
)
from surge_sdof.viz.geometry import layout_from_trace

if TYPE_CHECKING:
    from surge_sdof.response import PeakResponse
    from surge_sdof.trace import Trace
    from surge_sdof.viz.geometry import LoopLayout

__all__ = [
    "SCHEMA_VERSION",
    "SWEEP_SCHEMA_VERSION",
    "KIND_TRACE",
    "KIND_SWEEP",
    "FRAME_COLUMNS",
    "SWEEP_COLUMNS",
    "SWEEP_STRING_COLUMNS",
    "SWEEP_INT_COLUMNS",
    "git_sha",
    "created_utc",
    "array_block",
    "is_capped",
    "to_trace_dict",
    "to_sweep_dict",
    "SweepProvenance",
    "dumps",
    "write_json",
    "read_json",
    "read_csv",
]

SCHEMA_VERSION = 2
"""``schema_version`` of a ``trace`` document (2 since the schema bump of the review, R.9)."""
SWEEP_SCHEMA_VERSION = 3
"""``schema_version`` of a ``sweep`` document (2 since Session 5b: the sweep CSV columns; 3
since the schema bump of the review, R.9: the column names)."""
KIND_TRACE = "trace"
KIND_SWEEP = "sweep"


SWEEP_SOLVERS = ("lumped", "jc")
"""The two solvers of a sweep row, in column order (``{solver}`` in ``_SWEEP_COLUMN_TABLE``)."""
_SWEEP_COLUMN_TABLE = (
    # (column, type of its JSON value), in the document's order; a name with ``{solver}`` is
    # one column per entry of SWEEP_SOLVERS, in that order. Units are in the names.
    ("case_id", str),
    ("tier", int),
    ("subset", str),
    ("size_in", int),
    ("outside_diameter_mm", float),
    ("wall_thickness_mm", float),
    ("span_length", float),
    ("natural_frequency", float),
    ("history_type", str),
    ("oscillation_frequency", float),
    ("noise_seed", int),
    ("amplitude_fraction", float),
    ("friction_coefficient", float),
    ("design_pressure_bar", float),
    ("peak_pressure_target_bar", float),
    ("pressure_max_bar", float),
    ("pressure_mean_bar", float),
    ("pressure_rms_bar", float),
    ("scaled_noise_rms_bar", float),
    ("sample_rate", float),
    ("lead_in_s", float),
    ("transit_s", float),
    ("tail_s", float),
    ("decay_s", float),
    ("duration_s", float),
    ("sample_count", int),
    ("step_pressure", float),
    ("oscillation_amplitude", float),
    ("requested_noise_rms", float),
    ("noise_cutoff_frequency", float),
    ("envelope_reference_frequency", float),
    ("envelope_decay_cycles", float),
    ("envelope_decay_fraction", float),
    ("peak_pressure_target", float),
    ("histories_version", str),
    ("flow_area", float),
    ("mass_per_length", float),
    ("flexural_rigidity", float),
    ("characteristic_impedance", float),
    ("portal_frame_height", float),
    ("total_mass", float),
    ("column_cell_count", int),
    ("end_to_elbow_cell_count", int),
    ("is_short_pipe", int),
    ("force_history_max", float),
    ("force_history_mean", float),
    ("force_history_rms", float),
    ("max_static_equivalent_force_{solver}", float),
    ("max_static_equivalent_force_ratio", float),
    ("max_velocity_{solver}", float),
    ("max_velocity_ratio", float),
    ("max_momentum_{solver}", float),
    ("max_kinetic_energy_{solver}", float),
    ("max_displacement_{solver}", float),
    ("max_acceleration_{solver}", float),
    ("max_unbalance_force_{solver}", float),
    ("force_per_length_diameter_squared_{solver}", float),
    ("daf_{solver}", float),
    ("wall_time_{solver}", float),
    ("cpu", str),
    ("git_sha", str),
    ("error", str),
)
_SWEEP_COLUMN_TYPES = {
    name.format(solver=solver): column_type
    for name, column_type in _SWEEP_COLUMN_TABLE
    for solver in (SWEEP_SOLVERS if "{solver}" in name else (None,))
}
SWEEP_COLUMNS = tuple(_SWEEP_COLUMN_TYPES)
"""``sweep.columns`` names, in the document's order: the Session 5b sweep CSV columns
(``tools/sweep_jc.py``), sweep ``schema_version`` 3 (the W.1 schema 1 had thirty)."""
SWEEP_STRING_COLUMNS = frozenset(n for n, t in _SWEEP_COLUMN_TYPES.items() if t is str)
SWEEP_INT_COLUMNS = frozenset(n for n, t in _SWEEP_COLUMN_TYPES.items() if t is int)


# ------------------------------------------------------------------ provenance


def git_sha(cwd: str | Path | None = None) -> str | None:
    """``git rev-parse HEAD`` of ``cwd`` (default: this package's checkout), or None when
    git or a repository is not there."""
    where = Path(cwd) if cwd is not None else Path(__file__).resolve().parent
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=where,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha or None


def created_utc(now: _dt.datetime | None = None) -> str:
    """ISO 8601 UTC to the second, ``YYYY-MM-DDTHH:MM:SSZ``."""
    now = now if now is not None else _dt.datetime.now(_dt.timezone.utc)
    return now.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _provenance(sha: str | None | bool, created: str | None) -> tuple[str | None, str]:
    """``(meta.git_sha, meta.created_utc)`` of a document: ``sha`` True asks git for the
    checkout's HEAD (``git_sha``), ``created`` None stamps now (``created_utc``)."""
    return (
        git_sha() if sha is True else sha,
        created if created is not None else created_utc(),
    )


# ------------------------------------------------------------------ values


def array_block(a) -> dict:
    """A 2-D array as ``{"shape": [n_rows, n_cols], "data": flat row-major}``."""
    arr = np.ascontiguousarray(a)
    if arr.ndim != 2:
        raise ValueError(f"an array block needs a 2-D array, got shape {arr.shape}")
    return {"shape": [int(arr.shape[0]), int(arr.shape[1])], "data": arr.ravel().tolist()}


def _finite(value: float, where: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{where}: non-finite value {value!r} (the format has no NaN)")
    return value


def _jsonable(value, where: str = "value"):
    """Python scalars and lists for numpy input; 2-D arrays become array blocks, 1-D arrays
    plain lists; strings, None and bools pass; NaN / inf raise."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, np.ndarray):
        if value.ndim == 2:
            block = array_block(value)
            if value.dtype.kind == "f" and not np.all(np.isfinite(value)):
                raise ValueError(f"{where}: non-finite value in the array")
            return block
        return [_jsonable(v, where) for v in value.tolist()]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return _finite(value, where)
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v, where) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v, f"{where}.{k}") for k, v in value.items()}
    raise TypeError(f"{where}: cannot serialise {type(value).__name__}")


def _column(a: np.ndarray, name: str) -> list:
    """A frame column as a JSON list: ints for the int columns, floats otherwise."""
    if name in INT_FRAME_COLUMNS:
        return np.asarray(a).astype(np.int64).tolist()
    arr = np.asarray(a, dtype=np.float64)
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"frames.{name}: non-finite value (the format has no NaN)")
    return arr.tolist()


# ------------------------------------------------------------------ trace


def _geometry(layout: LoopLayout) -> dict:
    return {
        "grid_point_position": layout.grid_point_position.astype(np.float64).tolist(),
        "grid_point_kind": np.asarray(layout.grid_point_kind).astype(np.int64).tolist(),
        "grid_point_moving_fraction": layout.grid_point_moving_fraction.astype(np.float64).tolist(),
        "inactive_end_cell_count": int(layout.inactive_end_cell_count),
        "end_to_elbow_cell_count": int(layout.end_to_elbow_cell_count),
        "column_cell_count": int(layout.column_cell_count),
        "segments": {
            "inlet_elbow_index": int(layout.inlet_elbow_index),
            "run_start_index": int(layout.run_start_index),
            "run_end_index": int(layout.run_end_index),
            "outlet_elbow_index": int(layout.outlet_elbow_index),
        },
        "x_at_rest": layout.x_at_rest.astype(np.float64).tolist(),
        "y_at_rest": layout.y_at_rest.astype(np.float64).tolist(),
        "run_length": float(layout.run_length),
        "inlet_leg_height": float(layout.inlet_leg_height),
        "outlet_leg_height": float(layout.outlet_leg_height),
        "portal_frame_height": float(layout.portal_frame_height),
        "grid_point_spacing": float(layout.grid_point_spacing),
        "cell_length": float(layout.cell_length),
    }


def _synthetic_phase(trace: Trace) -> int:
    """Phase of the ``t = 0`` rest frame: transit, unless the run has no transit sub-step."""
    if trace.frame_count and trace.substep_index[0] == 0 and trace.load_phase[0] != PHASE_TRANSIT:
        return int(trace.load_phase[0])
    return PHASE_TRANSIT


def is_capped(result: PeakResponse) -> bool:
    """True when the run decayed past the traced history window (``trace.py``: free decay
    is traced while ``sample < 2 * out_max``), so the trace ends before the run did.

    Parameters
    ----------
    result : PeakResponse
        With a trace.
    """
    trace = result.trace
    in_free_decay = trace.load_phase == PHASE_FREE_DECAY
    if not in_free_decay.any():
        return False
    forced_sample_count = int(trace.sample_index[in_free_decay].min())
    return forced_sample_count + int(result.free_decay_sample_count) > 2 * int(
        trace.nominal_forced_sample_count
    )


def _frames(trace: Trace) -> dict:
    """The thirteen columns with the synthetic rest frame first (``time = 0``,
    ``substep_index = sample_index = -1``, the rest phase, zeros)."""
    rest_frame = {
        "time": 0.0,
        "substep_index": -1,
        "sample_index": -1,
        "load_phase": _synthetic_phase(trace),
        "is_sticking": 0,
    }
    out = {}
    for name, field_name in zip(FRAME_COLUMNS, FRAME_FIELDS, strict=True):
        frame_values = getattr(trace, field_name)
        rest_value = rest_frame.get(name, 0.0)
        out[name] = _column(np.concatenate([[rest_value], frame_values]), name)
    return out


def _grid_points(trace: Trace) -> dict:
    grid_point_count = int(trace.column.grid_point_pressure.shape[1])
    rest_frame = np.zeros((1, grid_point_count))
    blocks = {}
    for name, arr in (
        ("pressure", trace.column.grid_point_pressure),
        ("velocity", trace.column.grid_point_velocity),
    ):
        frame_values = np.concatenate([rest_frame, arr], axis=0)
        if not np.all(np.isfinite(frame_values)):
            raise ValueError(f"grid_points.{name}: non-finite value (the format has no NaN)")
        blocks[name] = array_block(frame_values)
    return blocks


def _meta_params(result: PeakResponse) -> dict:
    """``meta.params`` of a trace document: the SDOF constants, the sub-step and the run's
    trace settings."""
    trace = result.trace
    sdof_params = trace.sdof_params
    return {
        "mass": _finite(float(sdof_params.mass), "params.mass"),
        "stiffness": _finite(float(sdof_params.stiffness), "params.stiffness"),
        "damping": _finite(float(sdof_params.damping), "params.damping"),
        "friction_velocity_step": _finite(
            float(sdof_params.friction_velocity_step), "params.friction_velocity_step"
        ),
        "support_gap": _finite(float(sdof_params.support_gap), "params.support_gap"),
        "closed_gap_stiffness_ratio": _finite(
            float(sdof_params.closed_gap_stiffness_ratio), "params.closed_gap_stiffness_ratio"
        ),
        "substep_duration": _finite(float(trace.substep_duration), "params.substep_duration"),
        "substep_count": int(trace.substep_count),
        "nominal_forced_sample_count": int(trace.nominal_forced_sample_count),
        "trace_every": int(trace.trace_every),
        "is_capped": int(bool(is_capped(result))),
    }


def _meta_outputs(result: PeakResponse) -> dict:
    """``meta.outputs`` of a trace document: the run's five maxima and its free-decay samples."""
    return {
        "max_static_equivalent_force": _finite(
            float(result.max_static_equivalent_force), "outputs"
        ),
        "max_displacement": _finite(float(result.max_displacement), "outputs"),
        "max_velocity": _finite(float(result.max_velocity), "outputs"),
        "max_acceleration": _finite(float(result.max_acceleration), "outputs"),
        "max_unbalance_force": _finite(float(result.max_unbalance_force), "outputs"),
        "free_decay_sample_count": int(result.free_decay_sample_count),
    }


def to_trace_dict(
    result: PeakResponse,
    case_id: str,
    *,
    git_sha: str | None | bool = True,
    created_utc: str | None = None,
) -> dict:
    """The ``trace`` document of a traced run (``docs/data_format.md``).

    Parameters
    ----------
    result : PeakResponse
        From ``peak_response`` / ``peak_response_jc`` with ``trace_every > 0``.
    case_id : str
        ``meta.case_id``.
    git_sha : str, None or True
        ``meta.git_sha``; True (default) asks git for the checkout's HEAD.
    created_utc : str or None
        ``meta.created_utc``; None stamps now.

    Returns
    -------
    dict
        JSON-ready (plain Python scalars, lists and dicts; no numpy).

    Raises
    ------
    ValueError
        The result has no trace, or a value is not finite.
    """
    trace = result.trace
    if trace is None:
        raise ValueError("the result has no trace; run the solver with trace_every > 0")
    layout = layout_from_trace(trace)
    is_junction_coupled = trace.column is not None
    git_sha_value, created_utc_value = _provenance(git_sha, created_utc)
    doc = {
        "kind": KIND_TRACE,
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "case_id": str(case_id),
            "solver": str(trace.solver),
            "inputs": _jsonable(trace.inputs, "inputs"),
            "params": _meta_params(result),
            "outputs": _meta_outputs(result),
            "frame_count": int(trace.frame_count) + 1,
            "grid_point_count": int(trace.column.grid_point_count) if is_junction_coupled else 0,
            "git_sha": git_sha_value,
            "created_utc": created_utc_value,
        },
        "geometry": _geometry(layout),
        "frames": _frames(trace),
    }
    if is_junction_coupled:
        doc["grid_points"] = _grid_points(trace)
    return doc


# ------------------------------------------------------------------ sweep


def _sweep_string(value, where: str) -> str | None:
    """A string column's value: the string, or None for an empty one (an empty CSV cell)."""
    if isinstance(value, str):
        return value or None  # an empty CSV cell is null
    raise TypeError(f"{where}: expected a string or None, got {type(value).__name__}")


def _sweep_int(name: str, value, where: str) -> int:
    """An int column's value: an int, or a float with no fractional part."""
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{where}: {name} must be an integer, got {value!r}")
        value = int(value)
    if not isinstance(value, int):
        raise TypeError(f"{where}: expected an int or None, got {type(value).__name__}")
    return value


def _sweep_float(value, where: str) -> float:
    """A float column's value: a finite float (an int is converted)."""
    if isinstance(value, int):
        value = float(value)
    if not isinstance(value, float):
        raise TypeError(f"{where}: expected a number or None, got {type(value).__name__}")
    return _finite(value, where)


def _sweep_value(name: str, value, row: int):
    """The JSON value of one sweep cell: None, or the column's type (``_SWEEP_COLUMN_TABLE``);
    a CSV cell's text is parsed first. The checks run in this order."""
    where = f"columns.{name}[{row}]"
    if value is None:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if name in SWEEP_STRING_COLUMNS:
        return _sweep_string(value, where)
    if isinstance(value, str):
        if value == "":
            return None
        value = float(value) if name not in SWEEP_INT_COLUMNS else int(value)
    if isinstance(value, bool):
        raise TypeError(f"{where}: a bool is not a sweep value")
    if name in SWEEP_INT_COLUMNS:
        return _sweep_int(name, value, where)
    return _sweep_float(value, where)


@dataclass(frozen=True)
class SweepProvenance:
    """Where a sweep document's rows come from: its ``meta`` fields other than ``n_rows``.

    Attributes
    ----------
    source : str
        ``meta.source``: the file the rows were read from, as given.
    tier, cpu, histories_version : str or None
        ``meta`` fields; None when unknown.
    git_sha : str, None or True
        ``meta.git_sha``; True (default) asks git for the checkout's HEAD.
    created_utc : str or None
        ``meta.created_utc``; None (default) stamps now.
    """

    source: str
    tier: str | None = None
    cpu: str | None = None
    histories_version: str | None = None
    git_sha: str | None | bool = True
    created_utc: str | None = None


def to_sweep_dict(
    rows,
    *,
    provenance: SweepProvenance,
    regen: dict,
    reference: dict | None = None,
) -> dict:
    """The ``sweep`` document of a list of rows (``docs/data_format.md``).

    Parameters
    ----------
    rows : iterable of dict
        One dict per row, keyed by ``SWEEP_COLUMNS`` names; a missing column is null, an
        unknown key raises. Values are numbers (``seed`` an int), strings for the string
        columns, None, or numeric strings (a CSV cell; ``""`` is null).
    provenance : SweepProvenance
        The ``meta`` fields.
    regen : dict
        ``{"template", "columns_used", "note"}``: how a row is reproduced (the tool's
        templates are ``tools/sweep_document.golden_regen`` and ``sweep_regen``).
    reference : dict or None
        ``{"example_cases": [...], "jc_golden_rows": [...]}``; None gives two empty lists.

    Returns
    -------
    dict

    Raises
    ------
    ValueError, TypeError
        An unknown column, a non-finite number, a wrongly typed value.
    """
    rows = list(rows)
    columns = {name: [] for name in SWEEP_COLUMNS}
    for i, row in enumerate(rows):
        unknown = set(row) - set(SWEEP_COLUMNS)
        if unknown:
            raise ValueError(f"row {i}: unknown sweep columns {sorted(unknown)}")
        for name in SWEEP_COLUMNS:
            columns[name].append(_sweep_value(name, row.get(name), i))
    if reference is None:
        reference = {"example_cases": [], "jc_golden_rows": []}
    git_sha_value, created_utc_value = _provenance(provenance.git_sha, provenance.created_utc)
    return {
        "kind": KIND_SWEEP,
        "schema_version": SWEEP_SCHEMA_VERSION,
        "meta": {
            "git_sha": git_sha_value,
            "tier": provenance.tier,
            "created_utc": created_utc_value,
            "cpu": provenance.cpu,
            "histories_version": provenance.histories_version,
            "source": str(provenance.source),
            "n_rows": len(rows),
        },
        "columns": columns,
        "regen": _jsonable(regen, "regen"),
        "reference": _jsonable(reference, "reference"),
    }


# ------------------------------------------------------------------ files


def dumps(obj) -> str:
    """The document as text: compact separators, UTF-8 characters as they are, floats via
    ``repr``, no NaN (``ValueError``), one trailing LF."""
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"


def write_json(path: str | Path, obj, gzip: bool = False) -> int:
    """Write ``obj`` as ``dumps`` to ``path`` (gzipped when ``gzip`` is True or the suffix is
    ``.gz``); returns the number of JSON bytes before compression."""
    path = Path(path)
    text = dumps(obj).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if gzip or path.suffix == ".gz":
        with _gzip.open(path, "wb", compresslevel=6) as fh:
            fh.write(text)
    else:
        path.write_bytes(text)
    return len(text)


def read_json(path: str | Path):
    """Read a document written by ``write_json`` (gzip by the ``.gz`` suffix)."""
    path = Path(path)
    if path.suffix == ".gz":
        with _gzip.open(path, "rb") as fh:
            raw = fh.read()
    else:
        raw = path.read_bytes()
    return json.loads(raw.decode("utf-8"))


def read_csv(path: str | Path) -> tuple[tuple[str, ...], list[dict]]:
    """The header and the rows of a CSV file, every cell as its text (``""`` when empty).

    The one reader of the sweep CSVs and of the golden case table; it does no typing:
    ``to_sweep_dict`` types the cells of a sweep row.
    """
    with Path(path).open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = tuple(reader.fieldnames or ())
        rows = list(reader)
    return header, rows
