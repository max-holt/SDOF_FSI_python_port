"""Results data files for the JS viewer (Session W.1): ``docs/data_format.md`` is the contract.

``to_trace_dict(result, case_id)`` turns a traced ``PeakResponse`` into the ``trace`` document
(meta, the loop geometry of ``viz.geometry``, the per-frame columns with the synthetic rest
frame first, the JC column arrays as row-major blocks); ``to_sweep_dict(rows, ...)`` turns
sweep rows into the ``sweep`` document (the 5b sweep CSV columns, ``schema_version`` 2,
regen template, reference block);
``write_json`` / ``read_json`` serialise them under the document's rules: column-wise arrays,
floats via ``repr`` (the json module's default), no NaN (``allow_nan=False`` raises), UTF-8,
LF, compact separators, optional gzip.

Nothing here runs a solver or touches one: the module reads a ``PeakResponse`` and plain
rows. ``tools/export.py`` is the CLI.
"""

from __future__ import annotations

import datetime as _dt
import gzip as _gzip
import json
import math
import subprocess
from pathlib import Path

import numpy as np

from surge_sdof.response import PeakResponse
from surge_sdof.trace import PHASE_FREE_DECAY, PHASE_TRANSIT, Trace
from surge_sdof.viz.geometry import LoopLayout, layout_from_trace

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
]

SCHEMA_VERSION = 1
"""``schema_version`` of a ``trace`` document."""
SWEEP_SCHEMA_VERSION = 2
"""``schema_version`` of a ``sweep`` document (2 since Session 5b: the sweep CSV columns)."""
KIND_TRACE = "trace"
KIND_SWEEP = "sweep"

FRAME_COLUMNS = (
    "t",
    "sub_step",
    "sample",
    "phase",
    "x",
    "v",
    "a",
    "f_a",
    "f_b",
    "f_unbalance",
    "f_friction",
    "stick",
    "d_f",
)
"""``trace.frames`` columns, in the document's order."""

SWEEP_COLUMNS = (
    "case_id",
    "tier",
    "subset",
    "size_in",
    "od_mm",
    "thk_mm",
    "length_m",
    "nat_freq_hz",
    "history_type",
    "f_osc_hz",
    "seed",
    "amplitude_fraction",
    "mu",
    "p_design_bar",
    "p_cap_bar",
    "p_peak_bar",
    "p_mean_bar",
    "p_rms_bar",
    "noise_rms_bar",
    "sample_freq",
    "lead_in_s",
    "transit_s",
    "tail_s",
    "decay_s",
    "duration_s",
    "n_samples",
    "p_step",
    "p_osc",
    "p_noise_rms",
    "f_cut_hz",
    "f_ref_hz",
    "decay_cycles",
    "decay_fraction",
    "p_cap",
    "histories_version",
    "fluid_area_m2",
    "mass_per_unit_len",
    "ei",
    "rho_c",
    "portal_height_m",
    "mass_total_kg",
    "pipe_seg_qty",
    "pivot_seg_qty",
    "jc_short_pipe",
    "history_peak",
    "history_mean",
    "history_rms",
    "f_eq_lumped",
    "f_eq_jc",
    "ratio_f_eq",
    "v_peak_lumped",
    "v_peak_jc",
    "ratio_v_peak",
    "momentum_lumped",
    "momentum_jc",
    "ke_peak_lumped",
    "ke_peak_jc",
    "x_peak_lumped",
    "x_peak_jc",
    "a_peak_lumped",
    "a_peak_jc",
    "f_peak_lumped",
    "f_peak_jc",
    "f_eq_over_LD2_lumped",
    "f_eq_over_LD2_jc",
    "daf_lumped",
    "daf_jc",
    "t_lumped_s",
    "t_jc_s",
    "cpu",
    "git_sha",
    "error",
)
"""``sweep.columns`` names, in the document's order: the Session 5b sweep CSV columns
(``tools/sweep_jc.py``), sweep ``schema_version`` 2 (the W.1 schema 1 had thirty)."""
SWEEP_STRING_COLUMNS = frozenset(
    {"case_id", "subset", "history_type", "histories_version", "cpu", "git_sha", "error"}
)
SWEEP_INT_COLUMNS = frozenset(
    {"tier", "size_in", "seed", "n_samples", "pipe_seg_qty", "pivot_seg_qty", "jc_short_pipe"}
)

_INT_FRAME_COLUMNS = frozenset({"sub_step", "sample", "phase", "stick"})


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
    if name in _INT_FRAME_COLUMNS:
        return np.asarray(a).astype(np.int64).tolist()
    arr = np.asarray(a, dtype=np.float64)
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"frames.{name}: non-finite value (the format has no NaN)")
    return arr.tolist()


# ------------------------------------------------------------------ trace


def _geometry(layout: LoopLayout) -> dict:
    return {
        "cell_position_m": layout.cell_position.astype(np.float64).tolist(),
        "cell_kind": np.asarray(layout.cell_kind).astype(np.int64).tolist(),
        "moving_fraction": layout.moving_fraction.astype(np.float64).tolist(),
        "ext_qty": int(layout.ext_qty),
        "pivot_seg_qty": int(layout.pivot_seg_qty),
        "pipe_seg_qty": int(layout.pipe_seg_qty),
        "segments": {
            "inlet_end": int(layout.inlet_end),
            "run_start": int(layout.run_start),
            "run_end": int(layout.run_end),
            "outlet_start": int(layout.outlet_start),
        },
        "x_nominal_m": layout.x_nominal.astype(np.float64).tolist(),
        "y_nominal_m": layout.y_nominal.astype(np.float64).tolist(),
        "run_length_m": float(layout.run_length),
        "leg_height_m": float(layout.leg_height),
        "leg_height_2_m": float(layout.leg_height_2),
        "portal_height_m": float(layout.portal_height),
        "spacing_m": float(layout.spacing),
        "cell_length_m": float(layout.cell_length),
    }


def _synthetic_phase(trace: Trace) -> int:
    """Phase of the ``t = 0`` rest frame: transit, unless the run has no transit sub-step."""
    if trace.n_frames and trace.sub_step[0] == 0 and trace.phase[0] != PHASE_TRANSIT:
        return int(trace.phase[0])
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
    decay = trace.phase == PHASE_FREE_DECAY
    if not decay.any():
        return False
    forced_samples = int(trace.sample[decay].min())
    return forced_samples + int(result.free_decay_samples) > 2 * int(trace.out_max)


def _frames(trace: Trace) -> dict:
    """The thirteen columns with the synthetic rest frame first (``t = 0``, ``sub_step =
    sample = -1``, the rest phase, zeros)."""
    rest = {
        "t": 0.0,
        "sub_step": -1,
        "sample": -1,
        "phase": _synthetic_phase(trace),
        "stick": 0,
    }
    out = {}
    for name in FRAME_COLUMNS:
        traced = getattr(trace, name)
        first = rest.get(name, 0.0)
        out[name] = _column(np.concatenate([[first], traced]), name)
    return out


def _cells(trace: Trace) -> dict:
    n_cells = int(trace.p_cells.shape[1])
    rest = np.zeros((1, n_cells))
    blocks = {}
    for name, arr in (("p", trace.p_cells), ("v", trace.v_cells)):
        full = np.concatenate([rest, arr], axis=0)
        if not np.all(np.isfinite(full)):
            raise ValueError(f"cells.{name}: non-finite value (the format has no NaN)")
        blocks[name] = array_block(full)
    return blocks


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
    jc = trace.p_cells is not None
    p = trace.params
    doc = {
        "kind": KIND_TRACE,
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "case_id": str(case_id),
            "solver": str(trace.solver),
            "inputs": _jsonable(dict(trace.inputs), "inputs"),
            "params": {
                "mass": _finite(float(p.mass), "params.mass"),
                "stiffness": _finite(float(p.stiffness), "params.stiffness"),
                "damping": _finite(float(p.damping), "params.damping"),
                "fric_acc": _finite(float(p.fric_acc), "params.fric_acc"),
                "gap": _finite(float(p.gap), "params.gap"),
                "ratio2": _finite(float(p.ratio2), "params.ratio2"),
                "dt": _finite(float(trace.dt), "params.dt"),
                "step_qty": int(trace.step_qty),
                "out_max": int(trace.out_max),
                "trace_every": int(trace.trace_every),
                "capped": int(bool(is_capped(result))),
            },
            "outputs": {
                "max_static_equivalent_force": _finite(
                    float(result.max_static_equivalent_force), "outputs"
                ),
                "max_displacement": _finite(float(result.max_displacement), "outputs"),
                "max_velocity": _finite(float(result.max_velocity), "outputs"),
                "max_acceleration": _finite(float(result.max_acceleration), "outputs"),
                "max_applied_force": _finite(float(result.max_applied_force), "outputs"),
                "free_decay_samples": int(result.free_decay_samples),
            },
            "n_frames": int(trace.n_frames) + 1,
            "n_cells": int(trace.n_cells) if jc else 0,
            "git_sha": git_sha() if sha is True else sha,
            "created_utc": created if created is not None else created_utc(),
        },
        "geometry": _geometry(layout),
        "frames": _frames(trace),
    }
    if jc:
        doc["cells"] = _cells(trace)
    return doc


# ------------------------------------------------------------------ sweep


def _sweep_value(name: str, value, row: int):
    where = f"columns.{name}[{row}]"
    if value is None:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if name in SWEEP_STRING_COLUMNS:
        if isinstance(value, str):
            return value or None  # an empty CSV cell is null
        raise TypeError(f"{where}: expected a string or None, got {type(value).__name__}")
    if isinstance(value, str):
        if value == "":
            return None
        value = float(value) if name not in SWEEP_INT_COLUMNS else int(value)
    if isinstance(value, bool):
        raise TypeError(f"{where}: a bool is not a sweep value")
    if name in SWEEP_INT_COLUMNS:
        if isinstance(value, float):
            if not value.is_integer():
                raise ValueError(f"{where}: {name} must be an integer, got {value!r}")
            value = int(value)
        if not isinstance(value, int):
            raise TypeError(f"{where}: expected an int or None, got {type(value).__name__}")
        return value
    if isinstance(value, int):
        value = float(value)
    if not isinstance(value, float):
        raise TypeError(f"{where}: expected a number or None, got {type(value).__name__}")
    return _finite(value, where)


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
    return {
        "kind": KIND_SWEEP,
        "schema_version": SWEEP_SCHEMA_VERSION,
        "meta": {
            "git_sha": git_sha() if sha is True else sha,
            "tier": tier,
            "created_utc": created if created is not None else created_utc(),
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
