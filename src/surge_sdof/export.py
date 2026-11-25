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
    "dumps",
    "write_json",
    "read_json",
    "read_csv",
]

SCHEMA_VERSION = 1
"""``schema_version`` of a ``trace`` document."""
SWEEP_SCHEMA_VERSION = 2
"""``schema_version`` of a ``sweep`` document (2 since Session 5b: the sweep CSV columns)."""
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
    ("od_mm", float),
    ("thk_mm", float),
    ("length_m", float),
    ("nat_freq_hz", float),
    ("history_type", str),
    ("f_osc_hz", float),
    ("seed", int),
    ("amplitude_fraction", float),
    ("mu", float),
    ("p_design_bar", float),
    ("p_cap_bar", float),
    ("p_peak_bar", float),
    ("p_mean_bar", float),
    ("p_rms_bar", float),
    ("noise_rms_bar", float),
    ("sample_freq", float),
    ("lead_in_s", float),
    ("transit_s", float),
    ("tail_s", float),
    ("decay_s", float),
    ("duration_s", float),
    ("n_samples", int),
    ("p_step", float),
    ("p_osc", float),
    ("p_noise_rms", float),
    ("f_cut_hz", float),
    ("f_ref_hz", float),
    ("decay_cycles", float),
    ("decay_fraction", float),
    ("p_cap", float),
    ("histories_version", str),
    ("fluid_area_m2", float),
    ("mass_per_unit_len", float),
    ("ei", float),
    ("rho_c", float),
    ("portal_height_m", float),
    ("mass_total_kg", float),
    ("pipe_seg_qty", int),
    ("pivot_seg_qty", int),
    ("jc_short_pipe", int),
    ("history_peak", float),
    ("history_mean", float),
    ("history_rms", float),
    ("f_eq_{solver}", float),
    ("ratio_f_eq", float),
    ("v_peak_{solver}", float),
    ("ratio_v_peak", float),
    ("momentum_{solver}", float),
    ("ke_peak_{solver}", float),
    ("x_peak_{solver}", float),
    ("a_peak_{solver}", float),
    ("f_peak_{solver}", float),
    ("f_eq_over_LD2_{solver}", float),
    ("daf_{solver}", float),
    ("t_{solver}_s", float),
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
(``tools/sweep_jc.py``), sweep ``schema_version`` 2 (the W.1 schema 1 had thirty)."""
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
        "cell_position_m": layout.grid_point_position.astype(np.float64).tolist(),
        "cell_kind": np.asarray(layout.grid_point_kind).astype(np.int64).tolist(),
        "moving_fraction": layout.grid_point_moving_fraction.astype(np.float64).tolist(),
        "ext_qty": int(layout.inactive_end_cell_count),
        "pivot_seg_qty": int(layout.end_to_elbow_cell_count),
        "pipe_seg_qty": int(layout.column_cell_count),
        "segments": {
            "inlet_end": int(layout.inlet_elbow_index),
            "run_start": int(layout.run_start_index),
            "run_end": int(layout.run_end_index),
            "outlet_start": int(layout.outlet_elbow_index),
        },
        "x_nominal_m": layout.x_at_rest.astype(np.float64).tolist(),
        "y_nominal_m": layout.y_at_rest.astype(np.float64).tolist(),
        "run_length_m": float(layout.run_length),
        "leg_height_m": float(layout.inlet_leg_height),
        "leg_height_2_m": float(layout.outlet_leg_height),
        "portal_height_m": float(layout.portal_frame_height),
        "spacing_m": float(layout.grid_point_spacing),
        "cell_length_m": float(layout.cell_length),
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
    """The thirteen columns with the synthetic rest frame first (``t = 0``, ``sub_step =
    sample = -1``, the rest phase, zeros)."""
    rest_frame = {
        "t": 0.0,
        "sub_step": -1,
        "sample": -1,
        "phase": _synthetic_phase(trace),
        "stick": 0,
    }
    out = {}
    for name, field_name in zip(FRAME_COLUMNS, FRAME_FIELDS, strict=True):
        frame_values = getattr(trace, field_name)
        rest_value = rest_frame.get(name, 0.0)
        out[name] = _column(np.concatenate([[rest_value], frame_values]), name)
    return out


def _cells(trace: Trace) -> dict:
    grid_point_count = int(trace.column.grid_point_pressure.shape[1])
    rest_frame = np.zeros((1, grid_point_count))
    blocks = {}
    for name, arr in (
        ("p", trace.column.grid_point_pressure),
        ("v", trace.column.grid_point_velocity),
    ):
        frame_values = np.concatenate([rest_frame, arr], axis=0)
        if not np.all(np.isfinite(frame_values)):
            raise ValueError(f"cells.{name}: non-finite value (the format has no NaN)")
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
        "fric_acc": _finite(float(sdof_params.friction_velocity_step), "params.fric_acc"),
        "gap": _finite(float(sdof_params.support_gap), "params.gap"),
        "ratio2": _finite(float(sdof_params.closed_gap_stiffness_ratio), "params.ratio2"),
        "dt": _finite(float(trace.substep_duration), "params.dt"),
        "step_qty": int(trace.substep_count),
        "out_max": int(trace.nominal_forced_sample_count),
        "trace_every": int(trace.trace_every),
        "capped": int(bool(is_capped(result))),
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
        "max_applied_force": _finite(float(result.max_unbalance_force), "outputs"),
        "free_decay_samples": int(result.free_decay_sample_count),
    }


def _schema_1_inputs(inputs: dict) -> dict:
    """The solver's grouped ``Trace.inputs`` in the flat form and the order trace schema 1
    stores them: the keyword arguments of the entry points before the public API session,
    ``output_type`` 0 (every exported trace was run with it). Temporary: the schema bump
    (plan 6.5) exports the grouped form and removes this."""
    span, restraint, integration = inputs["span"], inputs["restraint"], inputs["integration"]
    flat = {
        "force_history": inputs["force_history"],
        "step_qty": integration["substep_count"],
        "sample_freq": inputs["sample_rate"],
        "physical_length": span["span_length"],
        "flexural_rigidity_ei": span["flexural_rigidity"],
        "celerity": span["celerity"],
        "mass_per_unit_len": span["mass_per_length"],
    }
    if "fluid" in inputs:
        flat["fluid_densty"] = inputs["fluid"]["fluid_density"]
        flat["fluid_area"] = inputs["fluid"]["flow_area"]
    flat.update(
        damping_percent=restraint["damping_percent"],
        dynamic_fric=restraint["friction_coefficient"],
        nat_freq=restraint["natural_frequency"],
        restrain_freq_ratio=restraint["closed_gap_frequency_ratio"],
        gap=restraint["support_gap"],
        output_type=0,
    )
    if "coupling" in inputs:
        flat["vav_denominator"] = inputs["coupling"]["mean_velocity_divisor"]
        flat["parity"] = inputs["coupling"]["parity"]
        flat["fraction_profile"] = inputs["coupling"]["fraction_profile"]
    return flat


def to_trace_dict(
    result: PeakResponse,
    case_id: str,
    *,
    sha: str | None | bool = True,
    created: str | None = None,
) -> dict:
    """The ``trace`` document of a traced run (``docs/data_format.md``).

    Parameters
    ----------
    result : PeakResponse
        From ``peak_response`` / ``peak_response_jc`` with ``trace_every > 0``.
    case_id : str
        ``meta.case_id``.
    sha : str, None or True
        ``meta.git_sha``; True (default) asks git for the checkout's HEAD.
    created : str or None
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
    git_sha_value, created_utc_value = _provenance(sha, created)
    doc = {
        "kind": KIND_TRACE,
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "case_id": str(case_id),
            "solver": str(trace.solver),
            "inputs": _jsonable(_schema_1_inputs(trace.inputs), "inputs"),
            "params": _meta_params(result),
            "outputs": _meta_outputs(result),
            "n_frames": int(trace.frame_count) + 1,
            "n_cells": int(trace.column.grid_point_count) if is_junction_coupled else 0,
            "git_sha": git_sha_value,
            "created_utc": created_utc_value,
        },
        "geometry": _geometry(layout),
        "frames": _frames(trace),
    }
    if is_junction_coupled:
        doc["cells"] = _cells(trace)
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


def to_sweep_dict(
    rows,
    *,
    source: str,
    tier: str | None = None,
    cpu: str | None = None,
    histories_version: str | None = None,
    regen: dict | None = None,
    reference: dict | None = None,
    sha: str | None | bool = True,
    created: str | None = None,
) -> dict:
    """The ``sweep`` document of a list of rows (``docs/data_format.md``).

    Parameters
    ----------
    rows : iterable of dict
        One dict per row, keyed by ``SWEEP_COLUMNS`` names; a missing column is null, an
        unknown key raises. Values are numbers (``seed`` an int), strings for the string
        columns, None, or numeric strings (a CSV cell; ``""`` is null).
    source : str
        ``meta.source``.
    tier, cpu, histories_version : str or None
        ``meta`` fields; None when unknown.
    regen : dict or None
        ``{"template", "columns_used", "note"}``; None gives the ``--golden {case_id}`` template.
    reference : dict or None
        ``{"example_cases": [...], "jc_golden_rows": [...]}``; None gives two empty lists.
    sha : str, None or True
        ``meta.git_sha``; True asks git.
    created : str or None
        ``meta.created_utc``; None stamps now.

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
    if regen is None:
        regen = {
            "template": "python tools/export.py trace --golden {case_id} --out {case_id}.json",
            "columns_used": ["case_id"],
            "note": None,
        }
    if reference is None:
        reference = {"example_cases": [], "jc_golden_rows": []}
    git_sha_value, created_utc_value = _provenance(sha, created)
    return {
        "kind": KIND_SWEEP,
        "schema_version": SWEEP_SCHEMA_VERSION,
        "meta": {
            "git_sha": git_sha_value,
            "tier": tier,
            "created_utc": created_utc_value,
            "cpu": cpu,
            "histories_version": histories_version,
            "source": str(source),
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
