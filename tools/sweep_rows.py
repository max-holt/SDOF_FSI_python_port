"""One case of the junction-coupling sweep to its CSV row.

Part of ``tools/sweep_jc.py`` (review session R.8, plan 5.12): the case's pressure history
(``case_history``, rebuilt from a row by ``history_from_row``), both solvers on it and the
row (``run_case``), and the CSV writer.
"""

from __future__ import annotations

import csv
import math
import time
from pathlib import Path
from typing import NamedTuple

import numpy as np
from sweep_grid import (
    CELERITY,
    CLOSED_GAP_FREQUENCY_RATIO,
    DAMPING_PERCENT,
    FLUID_DENSITY,
    MM_PER_M,
    NOISE_REFERENCE_FREQUENCY,
    PA_PER_BAR,
    SAMPLE_RATE,
    SUBSTEP_COUNT,
    SUPPORT_GAP,
    TRANSIT_ALLOWANCE_S,
    Case,
    Pipe,
    pipe,
)

from surge_sdof import export, histories, moc, response

# ------------------------------------------------------------------ one case


HISTORY_PARAM_COLUMNS = (
    # CSV column -> histories.PARAM_KEYS entry; SI values exactly as the generator received them
    ("history_type", "kind"),
    ("sample_freq", "sample_freq"),
    ("lead_in_s", "lead_in_s"),
    ("transit_s", "transit_s"),
    ("tail_s", "tail_s"),
    ("p_step", "p_step"),
    ("p_osc", "p_osc"),
    ("f_osc_hz", "f_osc"),
    ("p_noise_rms", "p_noise_rms"),
    ("f_cut_hz", "f_cut"),
    ("f_ref_hz", "f_ref"),
    ("seed", "seed"),
    ("decay_cycles", "decay_cycles"),
    ("decay_fraction", "decay_fraction"),
    ("p_cap", "p_cap"),
)

COLUMNS = export.SWEEP_COLUMNS
"""The CSV columns: the ``sweep`` document's columns (``docs/data_format.md``, schema 2)."""


def case_history(case: Case, p_design: float) -> histories.History:
    return histories.canonical(
        case.history_type,
        p_design,
        case.amplitude_fraction,
        f_osc=case.f_osc_hz,
        seed=case.seed,
        f_ref=NOISE_REFERENCE_FREQUENCY if case.history_type == "step_noise" else None,
        sample_freq=SAMPLE_RATE,
        transit_s=TRANSIT_ALLOWANCE_S,
    )


def history_from_row(row: dict) -> histories.History:
    """Rebuild a CSV row's history bitwise from its generator columns."""
    params = {}
    for column, key in HISTORY_PARAM_COLUMNS:
        value = row[column]
        if value in ("", None):
            params[key] = None
        elif key == "kind":
            params[key] = value
        elif key == "seed":
            params[key] = int(value)
        else:
            params[key] = float(value)
    return histories.from_params(params)


def solver_kwargs(case: Case, p: Pipe) -> dict:
    return {
        "step_qty": SUBSTEP_COUNT,
        "sample_freq": SAMPLE_RATE,
        "physical_length": case.length_m,
        "flexural_rigidity_ei": p.flexural_rigidity,
        "celerity": CELERITY,
        "mass_per_unit_len": p.mass_per_length,
        "damping_percent": DAMPING_PERCENT,
        "dynamic_fric": case.friction_coefficient,
        "nat_freq": case.natural_frequency,
        "restrain_freq_ratio": CLOSED_GAP_FREQUENCY_RATIO,
        "gap": SUPPORT_GAP,
    }


def _timed(fn, *args, **kwargs):
    t0 = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:  # recorded in the row, never skipped silently
        return None, time.perf_counter() - t0, f"{type(exc).__name__}: {exc}"
    return result, time.perf_counter() - t0, None


class RunProvenance(NamedTuple):
    """What a sweep row records about the run rather than the case."""

    tier: int
    subset: str  # "" or "subset<pct>"
    cpu: str
    sha: str  # short sha, "-dirty" appended for uncommitted changes, or "nogit"


def run_case(case: Case, provenance: RunProvenance) -> dict:
    """Both solvers on one case; the CSV row."""
    pipe_properties = pipe(case.size_in)
    pressure_history = case_history(case, pipe_properties.design_pressure)
    force_history = pressure_history.force(pipe_properties.flow_area)
    row = _case_columns(case, pipe_properties, pressure_history, force_history, provenance)
    lumped_result, jc_result = _solver_results(row, case, pipe_properties, force_history)
    _result_columns(row, case, pipe_properties, pressure_history, (lumped_result, jc_result))
    return row


def _case_columns(
    case: Case,
    pipe_properties: Pipe,
    pressure_history: histories.History,
    force_history: np.ndarray,
    provenance: RunProvenance,
) -> dict:
    """The row with every column that does not need a solver: the case, the pipe, the set-up,
    the history and its generator parameters, the provenance."""
    setup = response.solver_setup(
        SUBSTEP_COUNT,
        SAMPLE_RATE,
        case.length_m,
        pipe_properties.flexural_rigidity,
        pipe_properties.mass_per_length,
        case.natural_frequency,
    )
    portal_frame_height = setup.portal_frame_height
    column_cell_count, end_to_elbow_cell_count = response.column_grid(
        setup, case.length_m, CELERITY
    )
    # Proposed derivation, for Ben to confirm: the 4 / 3 is the span's full mass plus two
    # thirds of each leg's mass taking part in the motion, (L + 2 * (2/3) h) m' = (L + 4h/3) m'.
    # Written for the single expansion-loop shape.
    total_mass = (case.length_m + portal_frame_height * 4 / 3) * pipe_properties.mass_per_length
    row = dict.fromkeys(COLUMNS)
    row.update(
        case_id=case.case_id,
        tier=provenance.tier,
        subset=provenance.subset,
        size_in=case.size_in,
        od_mm=pipe_properties.outside_diameter_mm,
        thk_mm=pipe_properties.wall_thickness_mm,
        length_m=case.length_m,
        nat_freq_hz=case.natural_frequency,
        amplitude_fraction=case.amplitude_fraction,
        mu=case.friction_coefficient,
        p_design_bar=pipe_properties.design_pressure / PA_PER_BAR,
        p_cap_bar=histories.p_cap(pipe_properties.design_pressure, case.amplitude_fraction)
        / PA_PER_BAR,
        p_peak_bar=pressure_history.peak / PA_PER_BAR,
        p_mean_bar=pressure_history.mean / PA_PER_BAR,
        p_rms_bar=pressure_history.rms / PA_PER_BAR,
        noise_rms_bar=None
        if pressure_history.noise_rms is None
        else pressure_history.noise_rms / PA_PER_BAR,
        decay_s=pressure_history.decay_s,
        duration_s=pressure_history.duration_s,
        n_samples=pressure_history.n_samples,
        histories_version=pressure_history.version,
        fluid_area_m2=pipe_properties.flow_area,
        mass_per_unit_len=pipe_properties.mass_per_length,
        ei=pipe_properties.flexural_rigidity,
        rho_c=FLUID_DENSITY * CELERITY,
        portal_height_m=portal_frame_height,
        mass_total_kg=total_mass,
        pipe_seg_qty=column_cell_count,
        pivot_seg_qty=end_to_elbow_cell_count,
        jc_short_pipe=int(moc.is_short_pipe(column_cell_count, end_to_elbow_cell_count)),
        history_peak=float(np.abs(force_history).max()),
        history_mean=float(force_history.mean()),
        history_rms=float(math.sqrt(float(np.mean(force_history * force_history)))),
        cpu=provenance.cpu,
        git_sha=provenance.sha,
    )
    params = pressure_history.params()
    for column, key in HISTORY_PARAM_COLUMNS:
        row[column] = params[key]

    return row


def _solver_results(
    row: dict, case: Case, pipe_properties: Pipe, force_history: np.ndarray
) -> tuple:
    """``(lumped, jc)``: both solvers run on the case, each timed into ``row``; a failure is
    recorded in ``row["error"]`` and gives None, never skipped silently."""
    solver_arguments = solver_kwargs(case, pipe_properties)
    errors = []
    lumped_result, row["t_lumped_s"], err = _timed(
        response.peak_response, force_history, **solver_arguments
    )
    if err:
        errors.append(f"lumped: {err}")
    jc_result, row["t_jc_s"], err = _timed(
        response.peak_response_jc,
        force_history,
        fluid_densty=FLUID_DENSITY,
        fluid_area=pipe_properties.flow_area,
        **solver_arguments,
    )
    if err:
        errors.append(f"jc: {err}")
    row["error"] = "; ".join(errors) if errors else None
    return lumped_result, jc_result


def _result_columns(
    row: dict,
    case: Case,
    pipe_properties: Pipe,
    pressure_history: histories.History,
    results: tuple,
) -> None:
    """The result columns of each solver that ran, and the JC / lumped ratios, into ``row``."""
    lumped_result, jc_result = results
    total_mass = row["mass_total_kg"]
    outside_diameter_squared = (pipe_properties.outside_diameter_mm / MM_PER_M) ** 2
    peak_pressure_force = pressure_history.peak * pipe_properties.flow_area
    for name, result in (("lumped", lumped_result), ("jc", jc_result)):
        if result is None:
            continue
        row[f"f_eq_{name}"] = result.max_static_equivalent_force
        row[f"v_peak_{name}"] = result.max_velocity
        row[f"momentum_{name}"] = total_mass * result.max_velocity
        row[f"ke_peak_{name}"] = 0.5 * total_mass * result.max_velocity**2
        row[f"x_peak_{name}"] = result.max_displacement
        row[f"a_peak_{name}"] = result.max_acceleration
        row[f"f_peak_{name}"] = result.max_applied_force
        row[f"f_eq_over_LD2_{name}"] = result.max_static_equivalent_force / (
            case.length_m * outside_diameter_squared
        )
        row[f"daf_{name}"] = result.max_static_equivalent_force / peak_pressure_force
    if lumped_result is not None and jc_result is not None:
        row["ratio_f_eq"] = (
            jc_result.max_static_equivalent_force / lumped_result.max_static_equivalent_force
        )
        row["ratio_v_peak"] = jc_result.max_velocity / lumped_result.max_velocity


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: ("" if v is None else v) for k, v in row.items()})
