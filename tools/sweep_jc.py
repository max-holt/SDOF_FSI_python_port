#!/usr/bin/env python
"""Session 5b: quantify the junction-coupling effect with canonical load histories.

    .venv/bin/python tools/sweep_jc.py check                  # pipe table vs the owner's figures
    .venv/bin/python tools/sweep_jc.py run --tier 1 --subset 0.1   # stratified 10 % of Tier 1
    .venv/bin/python tools/sweep_jc.py run --tier 1               # full Tier 1
    .venv/bin/python tools/sweep_jc.py run --tier 2 --jobs 8      # Tier 2 (the owner, locally)
    .venv/bin/python tools/sweep_jc.py plot docs/sweep/<csv>      # PNGs + docs/jc_sweep.md

Every case runs both solvers, ``response.peak_response`` (lumped) and
``response.peak_response_jc`` (junction coupling, the fixed-path defaults F-1 / F-2 / F-4 on),
with ``restrainFreqRatio = 1``, ``gap = 0`` (inert at ratio 1), ``stepQTY = 40``, celerity
1237 m/s, damping 0.5 %, ``E = 195e9`` Pa. The force history is a ``surge_sdof.histories``
pressure history (``canonical``) times the size's fluid area. Pipe OD / thickness come from the
workbook's ``curve_10in!J7:M8`` table (``PIPES``) and mass, EI and fluid area from the sheet's
formulas (H11, H13, H15, J15); ``p_design = 2 t S / OD`` with ``S = 138`` MPa.

The CSV (``docs/sweep/tier<N>[_subset<pct>]_<sha>[_<tag>].csv``, the ``export.SWEEP_COLUMNS``,
documented in ``docs/data_format.md`` "sweep.columns"; ``tools/export.py sweep --from-csv``
converts it to the ``sweep`` JSON document) carries every parameter of a row's history
(``surge_sdof.histories.from_params`` rebuilds it bitwise through ``history_from_row``), the
results of both solvers, the JC / lumped ratios, the normalised forces, timings, CPU and git
sha. A failed solver run is recorded in ``error`` with its result columns empty; the sweep never
skips a case silently.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import platform
import random
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import NamedTuple

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from surge_sdof import export, histories, moc, response, structure  # noqa: E402

# ------------------------------------------------------------------ fixed inputs

PIPES = {
    # size_in: (od_mm, thk_mm) — tests/fixtures/source/surge_force_data.xlsm, curve_10in!J7:M8
    10: (273.1, 7.8),
    12: (307.1, 8.382),
    16: (406.4, 9.525),
    18: (457.0, 12.7),
}
RHO_FLUID = 1000.0  # kg/m³ (curve_10in!H9)
RHO_PIPE = 7800.0  # kg/m³ (curve_10in!H10)
YOUNGS_MODULUS = 195e9  # Pa (curve_10in!H14)
ALLOWABLE_STRESS = 138e6  # Pa, A106 Gr B (owner)
P_DESIGN_EXPECTED_BAR = {10: 78.8, 12: 75.3, 16: 64.7, 18: 76.7}  # owner's figures, ±0.1 bar
BAR = 1e5

STEP_QTY = 40
SAMPLE_FREQ = 1000.0
CELERITY = 1237.0
DAMPING_PERCENT = 0.5
RESTRAIN_FREQ_RATIO = 1.0
GAP = 0.0
F_REF_NOISE = 4.0  # Hz: the envelope reference of step_noise (the middle Tier 1 f_osc)
TRANSIT_ALLOWANCE_S = 0.04  # >= 48 m / 1237 m/s, the tier's longest span; one history per type

TIERS = {
    1: {
        "sizes": (10, 18),
        "lengths": (3.0, 6.0, 12.0, 24.0, 48.0),
        "nat_freqs": (2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0),
        "f_osc": (1.0, 4.0, 16.0),
        "seeds": (0,),
        "amplitudes": (0.25, 1.0),
        "frictions": (0.3, 1e-4),
    },
    2: {
        "sizes": (10, 12, 16, 18),
        "lengths": (3.0, 6.0, 12.0, 24.0, 48.0),
        "nat_freqs": None,  # the 15 curve-sheet values, read from the fixture
        "f_osc": (1.0, 2.0, 4.0, 8.0, 16.0),
        "seeds": (0, 1, 2),
        "amplitudes": (0.25, 0.5, 1.0),
        "frictions": (0.3, 0.15, 1e-4),
    },
}


def curve_sheet_nat_freqs() -> tuple[float, ...]:
    """The natural frequencies of the ``curve_10in`` lumped rows (15 values)."""
    path = REPO / "tests" / "fixtures" / "curve_10in" / "cases.csv"
    with path.open(newline="") as fh:
        values = {float(r["nat_freq"]) for r in csv.DictReader(fh) if r["solver"] == "lumped"}
    return tuple(sorted(values))


# ------------------------------------------------------------------ pipe properties


class Pipe(NamedTuple):
    size_in: int
    od_mm: float
    thk_mm: float
    fluid_area: float  # m²
    mass_per_unit_len: float  # kg/m, pipe + contents
    ei: float  # N·m²
    p_design: float  # Pa


def pipe(size_in: int) -> Pipe:
    """The curve_10in sheet's formulas for one size (H11, H13, H15, J15) and the hoop-stress
    design pressure ``2 t S / OD``."""
    od_mm, thk_mm = PIPES[size_in]
    r_in = (od_mm / 2 - thk_mm) / 1000
    r_out = od_mm / 2000
    fluid_area = math.pi * r_in**2
    mass = math.pi * (r_in**2 * RHO_FLUID + (r_out**2 - r_in**2) * RHO_PIPE)
    inertia = (math.pi / 4) * (r_out**4 - r_in**4)
    p_design = 2 * (thk_mm / 1000) * ALLOWABLE_STRESS / (od_mm / 1000)
    return Pipe(size_in, od_mm, thk_mm, fluid_area, mass, YOUNGS_MODULUS * inertia, p_design)


def check_pipe_table(verbose: bool = True) -> None:
    """Assert the design pressures against the owner's figures (0.1 bar) and the 10 in
    properties against ``tests/fixtures/curve_10in/params.json``."""
    import json

    for size, expected in P_DESIGN_EXPECTED_BAR.items():
        got = pipe(size).p_design / BAR
        assert abs(got - expected) <= 0.1, f"{size} in: p_design {got:.2f} bar, expected {expected}"
        if verbose:
            print(
                f"{size:>2} in  OD {PIPES[size][0]:6.1f} mm  t {PIPES[size][1]:6.3f} mm  "
                f"p_design {got:6.2f} bar (owner {expected})  cap {1.33 * got:6.2f} bar"
            )
    params = json.loads((REPO / "tests/fixtures/curve_10in/params.json").read_text())
    p10 = pipe(10)
    for mine, key in (
        (p10.fluid_area, "fluid_area"),
        (p10.mass_per_unit_len, "mass_per_unit_len"),
        (p10.ei, "flexural_rigidity_ei"),
    ):
        assert math.isclose(mine, params[key], rel_tol=1e-9), (key, mine, params[key])
    if verbose:
        print(
            "10 in fluid area, mass/length and EI reproduce tests/fixtures/curve_10in/params.json"
        )


# ------------------------------------------------------------------ cases


class Case(NamedTuple):
    size_in: int
    length_m: float
    nat_freq_hz: float
    history_type: str  # "step" | "step_sine" | "step_noise"
    f_osc_hz: float | None
    seed: int | None
    amplitude_fraction: float
    mu: float

    @property
    def history_key(self) -> tuple:
        return (self.history_type, self.f_osc_hz, self.seed)

    @property
    def case_id(self) -> str:
        if self.history_type == "step":
            h = "step"
        elif self.history_type == "step_sine":
            h = f"sine{self.f_osc_hz:g}"
        else:
            h = f"noise{self.seed}"
        return (
            f"s{self.size_in}_L{self.length_m:g}_f{self.nat_freq_hz:g}_{h}"
            f"_a{self.amplitude_fraction:g}_mu{self.mu:g}"
        )


def tier_cases(tier: int) -> list[Case]:
    """Every case of the tier, in grid order."""
    t = TIERS[tier]
    nat_freqs = t["nat_freqs"] or curve_sheet_nat_freqs()
    variants = [("step", None, None)]
    variants += [("step_sine", f, None) for f in t["f_osc"]]
    variants += [("step_noise", None, s) for s in t["seeds"]]
    return [
        Case(size, L, f, kind, f_osc, seed, amp, mu)
        for size in t["sizes"]
        for L in t["lengths"]
        for f in nat_freqs
        for kind, f_osc, seed in variants
        for amp in t["amplitudes"]
        for mu in t["frictions"]
    ]


DIMENSIONS = ("size_in", "length_m", "nat_freq_hz", "history_key", "amplitude_fraction", "mu")


def stratified_subset(cases: list[Case], fraction: float, seed: int = 0) -> list[Case]:
    """About ``fraction`` of the cases, every level of every dimension represented and
    balanced: a seeded shuffle, accepting a case while no level of any dimension exceeds
    its quota ``ceil(n_target / n_levels)``, then filled from the remainder if the quotas
    deadlock. Returned in grid order."""
    n_target = max(1, math.ceil(len(cases) * fraction))
    levels = {d: sorted({getattr(c, d) for c in cases}, key=repr) for d in DIMENSIONS}
    quota = {d: math.ceil(n_target / len(levels[d])) for d in DIMENSIONS}
    counts = {d: Counter() for d in DIMENSIONS}
    order = list(range(len(cases)))
    random.Random(seed).shuffle(order)
    chosen: set[int] = set()
    for i in order:
        c = cases[i]
        if all(counts[d][getattr(c, d)] < quota[d] for d in DIMENSIONS):
            chosen.add(i)
            for d in DIMENSIONS:
                counts[d][getattr(c, d)] += 1
            if len(chosen) >= n_target:
                break
    for i in order:
        if len(chosen) >= n_target:
            break
        chosen.add(i)
    return [cases[i] for i in sorted(chosen)]


def coverage(cases: list[Case]) -> dict[str, dict]:
    return {d: dict(Counter(getattr(c, d) for c in cases)) for d in DIMENSIONS}


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
        f_ref=F_REF_NOISE if case.history_type == "step_noise" else None,
        sample_freq=SAMPLE_FREQ,
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
        "step_qty": STEP_QTY,
        "sample_freq": SAMPLE_FREQ,
        "physical_length": case.length_m,
        "flexural_rigidity_ei": p.ei,
        "celerity": CELERITY,
        "mass_per_unit_len": p.mass_per_unit_len,
        "damping_percent": DAMPING_PERCENT,
        "dynamic_fric": case.mu,
        "nat_freq": case.nat_freq_hz,
        "restrain_freq_ratio": RESTRAIN_FREQ_RATIO,
        "gap": GAP,
    }


def _timed(fn, *args, **kwargs):
    t0 = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:  # recorded in the row, never skipped silently
        return None, time.perf_counter() - t0, f"{type(exc).__name__}: {exc}"
    return result, time.perf_counter() - t0, None


def run_case(case: Case, tier: int, subset: str, cpu: str, sha: str) -> dict:
    """Both solvers on one case; the CSV row."""
    p = pipe(case.size_in)
    h = case_history(case, p.p_design)
    force = h.force(p.fluid_area)
    kw = solver_kwargs(case, p)
    height = structure.solve_portal_height(
        case.length_m, p.ei, p.mass_per_unit_len, case.nat_freq_hz
    )
    dt = 1 / (SAMPLE_FREQ * STEP_QTY)
    n_seg, pivot = moc.grid_size(case.length_m, height, CELERITY, dt)
    mass_total = (case.length_m + height * 4 / 3) * p.mass_per_unit_len
    row = dict.fromkeys(COLUMNS)
    row.update(
        case_id=case.case_id,
        tier=tier,
        subset=subset,
        size_in=case.size_in,
        od_mm=p.od_mm,
        thk_mm=p.thk_mm,
        length_m=case.length_m,
        nat_freq_hz=case.nat_freq_hz,
        amplitude_fraction=case.amplitude_fraction,
        mu=case.mu,
        p_design_bar=p.p_design / BAR,
        p_cap_bar=histories.p_cap(p.p_design, case.amplitude_fraction) / BAR,
        p_peak_bar=h.peak / BAR,
        p_mean_bar=h.mean / BAR,
        p_rms_bar=h.rms / BAR,
        noise_rms_bar=None if h.noise_rms is None else h.noise_rms / BAR,
        decay_s=h.decay_s,
        duration_s=h.duration_s,
        n_samples=h.n_samples,
        histories_version=h.version,
        fluid_area_m2=p.fluid_area,
        mass_per_unit_len=p.mass_per_unit_len,
        ei=p.ei,
        rho_c=RHO_FLUID * CELERITY,
        portal_height_m=height,
        mass_total_kg=mass_total,
        pipe_seg_qty=n_seg,
        pivot_seg_qty=pivot,
        jc_short_pipe=int(moc.is_short_pipe(n_seg, pivot)),
        history_peak=float(np.abs(force).max()),
        history_mean=float(force.mean()),
        history_rms=float(math.sqrt(float(np.mean(force * force)))),
        cpu=cpu,
        git_sha=sha,
    )
    params = h.params()
    for column, key in HISTORY_PARAM_COLUMNS:
        row[column] = params[key]

    errors = []
    lumped, row["t_lumped_s"], err = _timed(response.peak_response, force, **kw)
    if err:
        errors.append(f"lumped: {err}")
    jc, row["t_jc_s"], err = _timed(
        response.peak_response_jc, force, fluid_densty=RHO_FLUID, fluid_area=p.fluid_area, **kw
    )
    if err:
        errors.append(f"jc: {err}")
    d2 = (p.od_mm / 1000) ** 2
    p_peak_a = h.peak * p.fluid_area
    for name, r in (("lumped", lumped), ("jc", jc)):
        if r is None:
            continue
        row[f"f_eq_{name}"] = r.max_static_equivalent_force
        row[f"v_peak_{name}"] = r.max_velocity
        row[f"momentum_{name}"] = mass_total * r.max_velocity
        row[f"ke_peak_{name}"] = 0.5 * mass_total * r.max_velocity**2
        row[f"x_peak_{name}"] = r.max_displacement
        row[f"a_peak_{name}"] = r.max_acceleration
        row[f"f_peak_{name}"] = r.max_applied_force
        row[f"f_eq_over_LD2_{name}"] = r.max_static_equivalent_force / (case.length_m * d2)
        row[f"daf_{name}"] = r.max_static_equivalent_force / p_peak_a
    if lumped is not None and jc is not None:
        row["ratio_f_eq"] = jc.max_static_equivalent_force / lumped.max_static_equivalent_force
        row["ratio_v_peak"] = jc.max_velocity / lumped.max_velocity
    row["error"] = "; ".join(errors) if errors else None
    return row


# ------------------------------------------------------------------ the run


def git(*args) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def git_sha_tag() -> str:
    sha = git("rev-parse", "--short", "HEAD") or "nogit"
    if git("status", "--porcelain", "--", "src", "tests", "tools"):
        sha += "-dirty"
    return sha


def cpu_model() -> str:
    try:
        with open("/proc/cpuinfo") as fh:
            for line in fh:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine() or "unknown"


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: ("" if v is None else v) for k, v in row.items()})


def read_csv(path: Path) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _worker(args):
    case, tier, subset, cpu, sha = args
    return run_case(case, tier, subset, cpu, sha)


def run(args) -> Path:
    check_pipe_table(verbose=False)
    tier = args.tier
    cases = tier_cases(tier)
    subset = ""
    if args.subset:
        cases = stratified_subset(cases, args.subset, args.subset_seed)
        subset = f"subset{round(args.subset * 100):g}"
    if args.limit:
        cases = cases[: args.limit]
    if args.history:
        cases = [c for c in cases if c.history_type == args.history]
    cpu = cpu_model()
    sha = git_sha_tag()
    tag = f"_{args.tag}" if args.tag else ""
    name = f"tier{tier}{'_' + subset if subset else ''}{'_limit' + str(args.limit) if args.limit else ''}_{sha}{tag}.csv"
    out = Path(args.out) / name
    print(f"tier {tier}: {len(cases)} cases, {args.jobs} jobs, cpu {cpu}, sha {sha}")
    for d, c in coverage(cases).items():
        print(
            f"  {d}: "
            + ", ".join(f"{k!r}: {v}" for k, v in sorted(c.items(), key=lambda kv: repr(kv[0])))
        )
    t_start = time.perf_counter()
    rows = []
    jobs = [(c, tier, subset, cpu, sha) for c in cases]
    done = 0
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for row in pool.map(_worker, jobs, chunksize=1):
            rows.append(row)
            done += 1
            if done % args.progress == 0 or done == len(cases):
                elapsed = time.perf_counter() - t_start
                print(
                    f"  {done}/{len(cases)} in {elapsed:.0f} s "
                    f"({elapsed / done:.2f} s/case wall, {len(cases) * elapsed / done - elapsed:.0f} s left)",
                    flush=True,
                )
    wall = time.perf_counter() - t_start
    write_csv(out, rows)
    errors = [r for r in rows if r["error"]]
    t_l = sum(r["t_lumped_s"] or 0 for r in rows)
    t_j = sum(r["t_jc_s"] or 0 for r in rows)
    print(
        f"wrote {out} ({len(rows)} rows, {len(errors)} with errors); wall {wall:.0f} s; "
        f"solver CPU: lumped {t_l:.0f} s, jc {t_j:.0f} s "
        f"(mean {t_l / len(rows):.3f} / {t_j / len(rows):.3f} s per case)"
    )
    for r in errors:
        print(f"  {r['case_id']}: {r['error']}")
    return out


# ------------------------------------------------------------------ plots


LENGTH_COLOURS = {3.0: "#2a78d6", 6.0: "#eb6834", 12.0: "#1baf7a", 24.0: "#eda100", 48.0: "#e87ba4"}
LENGTH_MARKERS = {3.0: "o", 6.0: "s", 12.0: "^", 24.0: "D", 48.0: "v"}
SIZE_MARKERS = {10: "o", 12: "s", 16: "^", 18: "D"}
AMP_STYLES = {0.25: ":", 0.5: "--", 1.0: "-"}
SOLVER_INK = {"lumped": "#52514e", "jc": "#0b0b0b"}
HISTORY_LABELS = {"step": "step", "step_sine": "step + sine", "step_noise": "step + noise"}


def _f(v):
    return None if v in ("", None) else float(v)


def _load(path: Path) -> list[dict]:
    rows = read_csv(path)
    for r in rows:
        for k in (
            "size_in",
            "length_m",
            "nat_freq_hz",
            "f_osc_hz",
            "amplitude_fraction",
            "mu",
            "ratio_f_eq",
            "ratio_v_peak",
            "daf_lumped",
            "daf_jc",
            "f_eq_over_LD2_lumped",
            "f_eq_over_LD2_jc",
            "t_lumped_s",
            "t_jc_s",
        ):
            r[k] = _f(r[k])
        r["seed"] = int(r["seed"]) if r["seed"] else None
        r["size_in"] = int(r["size_in"])
    return rows


def _history_variants(rows):
    """(history_type, f_osc) panels: the noise seeds are folded into one variant."""
    seen = []
    for r in rows:
        key = (r["history_type"], r["f_osc_hz"] if r["history_type"] == "step_sine" else None)
        if key not in seen:
            seen.append(key)
    order = {"step": 0, "step_sine": 1, "step_noise": 2}
    return sorted(seen, key=lambda k: (order[k[0]], k[1] or 0))


def _variant_label(key):
    kind, f_osc = key
    return f"{HISTORY_LABELS[kind]} {f_osc:g} Hz" if kind == "step_sine" else HISTORY_LABELS[kind]


def _select(rows, **match):
    out = []
    for r in rows:
        ok = True
        for k, v in match.items():
            if k == "variant":
                kind, f_osc = v
                ok = r["history_type"] == kind and (kind != "step_sine" or r["f_osc_hz"] == f_osc)
            elif r[k] != v:
                ok = False
            if not ok:
                break
        if ok:
            out.append(r)
    return out


def _series(rows, column, envelope="max"):
    """``(freqs, values)`` of ``column`` vs natFreq; several rows at one frequency (noise seeds)
    are reduced by ``envelope`` (the pointwise max over seeds, the owner's envelope) or
    ``min``."""
    by_f = {}
    for r in rows:
        if r[column] is None:
            continue
        by_f.setdefault(r["nat_freq_hz"], []).append(r[column])
    freqs = sorted(by_f)
    red = max if envelope == "max" else min
    return freqs, [red(by_f[f]) for f in freqs]


def _style_axes(ax):
    ax.set_xscale("log")
    ax.grid(True, which="major", color="#e6e5e1", linewidth=0.6)
    ax.grid(True, which="minor", color="#f1f0ec", linewidth=0.4)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#c3c2b7")
    ax.tick_params(colors="#52514e", labelsize=8)


def _freq_ticks(ax, freqs):
    from matplotlib.ticker import FixedLocator, NullFormatter, ScalarFormatter

    ticks = sorted(set(freqs))
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(ScalarFormatter())
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{t:g}" for t in ticks], fontsize=7)


def plot_ratio(rows, column, ylabel, out_png: Path, title: str, mu_on: float):
    """Figure 1: JC / lumped ratio vs natFreq, one line per length, one panel per (size,
    history variant, amplitude), friction on (``mu_on``)."""
    import matplotlib.pyplot as plt

    sizes = sorted({r["size_in"] for r in rows})
    amps = sorted({r["amplitude_fraction"] for r in rows})
    variants = _history_variants(rows)
    ncol = len(variants)
    nrow = len(sizes) * len(amps)
    fig, axes = plt.subplots(
        nrow, ncol, figsize=(3.2 * ncol, 2.6 * nrow), squeeze=False, sharey=True
    )
    all_freqs = sorted({r["nat_freq_hz"] for r in rows})
    for i, (size, amp) in enumerate((s, a) for s in sizes for a in amps):
        for j, variant in enumerate(variants):
            ax = axes[i][j]
            _style_axes(ax)
            ax.axhline(1.0, color="#c3c2b7", linewidth=0.8)
            ax.axhspan(0.95, 1.05, color="#e6e5e1", alpha=0.5, linewidth=0)
            ax.axhline(0.8, color="#c3c2b7", linewidth=0.6, linestyle="--")
            for L in sorted(LENGTH_COLOURS):
                sel = _select(
                    rows,
                    size_in=size,
                    amplitude_fraction=amp,
                    variant=variant,
                    length_m=L,
                    mu=mu_on,
                )
                freqs, vals = _series(sel, column)
                if not freqs:
                    continue
                ax.plot(
                    freqs,
                    vals,
                    color=LENGTH_COLOURS[L],
                    marker=LENGTH_MARKERS[L],
                    markersize=4,
                    linewidth=1.6,
                    label=f"L = {L:g} m",
                )
            _freq_ticks(ax, all_freqs)
            ax.set_title(
                f"{size} in · {_variant_label(variant)} · amplitude {amp:g}",
                fontsize=8,
                color="#0b0b0b",
            )
            if j == 0:
                ax.set_ylabel(ylabel, fontsize=8, color="#52514e")
            if i == nrow - 1:
                ax.set_xlabel("natural frequency, Hz", fontsize=8, color="#52514e")
    handles, labels = axes[0][0].get_legend_handles_labels()
    for row_axes in axes:
        for ax in row_axes:
            h, lab = ax.get_legend_handles_labels()
            if len(lab) > len(labels):
                handles, labels = h, lab
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=len(labels),
        fontsize=8,
        frameon=False,
        bbox_to_anchor=(0.5, -0.01),
    )
    fig.suptitle(f"{title} (mu = {mu_on:g}; band ±5 %, dashed 0.8)", fontsize=10, color="#0b0b0b")
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(out_png, dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


def plot_daf(rows, out_png: Path, mu_on: float):
    """Figure 2: effective DAF ``F / (p_peak A)`` of both solvers vs natFreq, one line per
    length (colour), amplitude as line style, lumped hollow / JC filled markers, one panel
    per (size, history variant), friction on."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    sizes = sorted({r["size_in"] for r in rows})
    amps = sorted({r["amplitude_fraction"] for r in rows})
    variants = _history_variants(rows)
    fig, axes = plt.subplots(
        len(sizes),
        len(variants),
        figsize=(3.2 * len(variants), 2.8 * len(sizes)),
        squeeze=False,
        sharey=True,
    )
    all_freqs = sorted({r["nat_freq_hz"] for r in rows})
    for i, size in enumerate(sizes):
        for j, variant in enumerate(variants):
            ax = axes[i][j]
            _style_axes(ax)
            ax.axhline(2.0, color="#c3c2b7", linewidth=0.8, linestyle="--")
            for L in sorted(LENGTH_COLOURS):
                for amp in amps:
                    sel = _select(
                        rows,
                        size_in=size,
                        amplitude_fraction=amp,
                        variant=variant,
                        length_m=L,
                        mu=mu_on,
                    )
                    for solver, fill in (("lumped", "none"), ("jc", LENGTH_COLOURS[L])):
                        freqs, vals = _series(sel, f"daf_{solver}")
                        if not freqs:
                            continue
                        ax.plot(
                            freqs,
                            vals,
                            color=LENGTH_COLOURS[L],
                            linestyle=AMP_STYLES.get(amp, "-"),
                            marker=LENGTH_MARKERS[L],
                            markersize=4,
                            markerfacecolor=fill,
                            linewidth=1.2 if solver == "jc" else 0.9,
                            alpha=1.0 if solver == "jc" else 0.7,
                        )
            _freq_ticks(ax, all_freqs)
            ax.set_title(f"{size} in · {_variant_label(variant)}", fontsize=8, color="#0b0b0b")
            if j == 0:
                ax.set_ylabel("F_eq / (p_peak A)", fontsize=8, color="#52514e")
            if i == len(sizes) - 1:
                ax.set_xlabel("natural frequency, Hz", fontsize=8, color="#52514e")
    handles = [
        Line2D([], [], color=LENGTH_COLOURS[L], marker=LENGTH_MARKERS[L], label=f"L = {L:g} m")
        for L in sorted(LENGTH_COLOURS)
    ]
    handles += [
        Line2D([], [], color="#52514e", linestyle=AMP_STYLES.get(a, "-"), label=f"amplitude {a:g}")
        for a in amps
    ]
    handles += [
        Line2D(
            [],
            [],
            color="#52514e",
            marker="o",
            markerfacecolor="none",
            linestyle="",
            label="lumped",
        ),
        Line2D([], [], color="#52514e", marker="o", linestyle="", label="JC"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=min(len(handles), 6),
        fontsize=8,
        frameon=False,
        bbox_to_anchor=(0.5, -0.01),
    )
    fig.suptitle(f"Effective DAF of both solvers (mu = {mu_on:g}; dashed: DAF = 2)", fontsize=10)
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    fig.savefig(out_png, dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


def plot_collapse(rows, out_png: Path, mu_on: float, amp: float):
    """Figure 3: ``F_eq / (L d²)`` vs natFreq for every size and length on one panel per
    history variant (colour = length, marker = size, lumped hollow / JC filled)."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    variants = _history_variants(rows)
    sizes = sorted({r["size_in"] for r in rows})
    fig, axes = plt.subplots(
        2, len(variants), figsize=(3.2 * len(variants), 5.6), squeeze=False, sharey=True
    )
    all_freqs = sorted({r["nat_freq_hz"] for r in rows})
    for k, solver in enumerate(("lumped", "jc")):
        for j, variant in enumerate(variants):
            ax = axes[k][j]
            _style_axes(ax)
            ax.set_yscale("log")
            for size in sizes:
                for L in sorted(LENGTH_COLOURS):
                    sel = _select(
                        rows,
                        size_in=size,
                        amplitude_fraction=amp,
                        variant=variant,
                        length_m=L,
                        mu=mu_on,
                    )
                    freqs, vals = _series(sel, f"f_eq_over_LD2_{solver}")
                    if not freqs:
                        continue
                    ax.plot(
                        freqs,
                        vals,
                        color=LENGTH_COLOURS[L],
                        marker=SIZE_MARKERS[size],
                        markersize=4,
                        markerfacecolor=LENGTH_COLOURS[L] if solver == "jc" else "none",
                        linewidth=1.0,
                    )
            _freq_ticks(ax, all_freqs)
            ax.set_title(f"{solver} · {_variant_label(variant)} · amplitude {amp:g}", fontsize=8)
            if j == 0:
                ax.set_ylabel("F_eq / (L d²), N/m³", fontsize=8, color="#52514e")
            if k == 1:
                ax.set_xlabel("natural frequency, Hz", fontsize=8, color="#52514e")
    handles = [
        Line2D([], [], color=LENGTH_COLOURS[L], label=f"L = {L:g} m")
        for L in sorted(LENGTH_COLOURS)
    ]
    handles += [
        Line2D([], [], color="#52514e", marker=SIZE_MARKERS[s], linestyle="", label=f"{s} in")
        for s in sizes
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=min(len(handles), 7),
        fontsize=8,
        frameon=False,
        bbox_to_anchor=(0.5, -0.01),
    )
    fig.suptitle(
        f"Mass-collapse test: F_eq / (L d²) (mu = {mu_on:g}, amplitude {amp:g}; d = OD)",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    fig.savefig(out_png, dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


FREQ_BANDS = (
    (0.0, 4.0, "≤ 4 Hz"),
    (4.0, 8.0, "4 – 8 Hz"),
    (8.0, 16.0, "8 – 16 Hz"),
    (16.0, 1e9, "> 16 Hz"),
)


def _band(f):
    for lo, hi, name in FREQ_BANDS:
        if lo < f <= hi:
            return name
    return "> 16 Hz"


def ratio_table(rows, column, mu_on: float) -> list[str]:
    """Markdown: per history type, by frequency band × length, the count of cases with the
    ratio within 5 % of 1 (negligible) / below 0.8 (essential) / the rest, friction on, all
    sizes and amplitudes pooled."""
    lines = []
    for variant in _history_variants(rows):
        sel = [r for r in _select(rows, variant=variant, mu=mu_on) if r[column] is not None]
        lengths = sorted({r["length_m"] for r in sel})
        lines.append(
            f"**{_variant_label(variant)}** — `{column}`, mu = {mu_on:g}; cell = negligible (|r − 1| ≤ 5 %) / essential (r < 0.8) / other, of n cases; min r"
        )
        lines.append("")
        lines.append("| band | " + " | ".join(f"L = {L:g} m" for L in lengths) + " |")
        lines.append("|---|" + "---|" * len(lengths))
        for _lo, _hi, band in FREQ_BANDS:
            cells = []
            for L in lengths:
                vals = [
                    r[column] for r in sel if r["length_m"] == L and _band(r["nat_freq_hz"]) == band
                ]
                if not vals:
                    cells.append("–")
                    continue
                neg = sum(abs(v - 1) <= 0.05 for v in vals)
                ess = sum(v < 0.8 for v in vals)
                cells.append(
                    f"{neg} / {ess} / {len(vals) - neg - ess} of {len(vals)}; min {min(vals):.2f}"
                )
            lines.append(f"| {band} | " + " | ".join(cells) + " |")
        lines.append("")
    return lines


def amplitude_table(rows, mu_on: float) -> list[str]:
    """Markdown: the friction (amplitude) dependence as the ratio of the low-amplitude to the
    high-amplitude effective DAF, per history type and solver, by frequency band (all sizes
    and lengths pooled: median and range)."""
    amps = sorted({r["amplitude_fraction"] for r in rows})
    if len(amps) < 2:
        return ["(one amplitude only: no amplitude dependence to report)", ""]
    lo_amp, hi_amp = amps[0], amps[-1]
    lines = [
        f"**Amplitude dependence** — DAF(amplitude {lo_amp:g}) / DAF(amplitude {hi_amp:g}), mu = {mu_on:g}, median [min – max] over sizes and lengths (n pairs)",
        "",
    ]
    lines.append("| history | solver | " + " | ".join(b[2] for b in FREQ_BANDS) + " |")
    lines.append("|---|---|" + "---|" * len(FREQ_BANDS))
    for variant in _history_variants(rows):
        for solver in ("lumped", "jc"):
            cells = []
            for _lo, _hi, band in FREQ_BANDS:
                pairs = []
                low = _select(rows, variant=variant, mu=mu_on, amplitude_fraction=lo_amp)
                high = {
                    (r["size_in"], r["length_m"], r["nat_freq_hz"], r["seed"]): r
                    for r in _select(rows, variant=variant, mu=mu_on, amplitude_fraction=hi_amp)
                }
                for r in low:
                    key = (r["size_in"], r["length_m"], r["nat_freq_hz"], r["seed"])
                    other = high.get(key)
                    if other is None or _band(r["nat_freq_hz"]) != band:
                        continue
                    a, b = r[f"daf_{solver}"], other[f"daf_{solver}"]
                    if a is not None and b is not None and b:
                        pairs.append(a / b)
                if pairs:
                    cells.append(
                        f"{float(np.median(pairs)):.2f} [{min(pairs):.2f} – {max(pairs):.2f}] ({len(pairs)})"
                    )
                else:
                    cells.append("–")
            lines.append(f"| {_variant_label(variant)} | {solver} | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def collapse_spread(rows, mu_on: float, amp: float) -> list[str]:
    """Markdown: per history variant and solver, the spread of ``F_eq / (L d²)`` across sizes
    and lengths at each natural frequency (max / min), the visual collapse stated as numbers."""
    lines = [
        f"**Collapse spread** — max / min of F_eq / (L d²) over sizes and lengths at one natural frequency, mu = {mu_on:g}, amplitude {amp:g} (median over frequencies [max])",
        "",
    ]
    lines.append("| history | lumped | JC |")
    lines.append("|---|---|---|")
    for variant in _history_variants(rows):
        cells = []
        for solver in ("lumped", "jc"):
            sel = [
                r
                for r in _select(rows, variant=variant, mu=mu_on, amplitude_fraction=amp)
                if r[f"f_eq_over_LD2_{solver}"] is not None
            ]
            by_f = {}
            for r in sel:
                by_f.setdefault(r["nat_freq_hz"], []).append(r[f"f_eq_over_LD2_{solver}"])
            spreads = [max(v) / min(v) for v in by_f.values() if len(v) > 1 and min(v) > 0]
            cells.append(
                f"{float(np.median(spreads)):.2f} [{max(spreads):.2f}]" if spreads else "–"
            )
        lines.append(f"| {_variant_label(variant)} | {cells[0]} | {cells[1]} |")
    lines.append("")
    return lines


def write_doc(rows, csv_path: Path, pngs: dict, doc_path: Path, mu_on: float, amp: float) -> None:
    n_err = sum(1 for r in rows if r["error"])
    sizes = sorted({r["size_in"] for r in rows})
    tier = rows[0]["tier"]
    subset = rows[0]["subset"]
    sha = rows[0]["git_sha"]
    cpu = rows[0]["cpu"]
    t_l = [r["t_lumped_s"] for r in rows if r["t_lumped_s"] is not None]
    t_j = [r["t_jc_s"] for r in rows if r["t_jc_s"] is not None]
    rel = lambda p: os.path.relpath(p, doc_path.parent)  # noqa: E731
    lines = [
        "# Junction-coupling sweep (Session 5b)",
        "",
        f"Source: `{rel(csv_path)}` — tier {tier}{' (' + subset + ')' if subset else ''}, {len(rows)} rows "
        f"({n_err} with errors), sizes {', '.join(f'{s} in' for s in sizes)}, git `{sha}`, CPU {cpu}. "
        f"Generated by `tools/sweep_jc.py plot`; the column definitions are in `docs/data_format.md` "
        f'("sweep CSV (Session 5b)"). Both solvers run with the fixed-path defaults (F-1, F-2, F-4), '
        f"`restrainFreqRatio = 1`, `gap = 0`, `stepQTY = 40`, celerity 1237 m/s, damping 0.5 %, "
        f"E = 195 GPa; the pressure histories are `surge_sdof.histories.canonical` at 1000 Hz, peak "
        f"`amplitude_fraction × 1.33 × p_design`. Frequency axes are the absolute natural frequency "
        f"(the lumped `natFreq`, modelled with the contained fluid). Where several noise seeds exist, "
        f"a plotted point is the pointwise max over seeds (the envelope); the per-seed rows stay in the CSV.",
        "",
        f"Run time per solver (this CSV): lumped mean {np.mean(t_l):.3f} s (max {max(t_l):.3f} s), "
        f"JC mean {np.mean(t_j):.3f} s (max {max(t_j):.3f} s), {len(rows)} cases.",
        "",
        "## 1. JC / lumped ratio of the equivalent static force and of the peak velocity",
        "",
        f"One line per span length, one panel per (size, history type, amplitude), friction on (mu = {mu_on:g}). "
        "The grey band is ±5 % of 1; the dashed line is 0.8.",
        "",
        f"![ratio_f_eq]({rel(pngs['ratio_f_eq'])})",
        "",
        f"![ratio_v_peak]({rel(pngs['ratio_v_peak'])})",
        "",
        "## 2. Effective DAF F_eq / (p_peak A), lumped and JC",
        "",
        f"One panel per (size, history type), colour = length, line style = amplitude, hollow markers lumped and filled JC, mu = {mu_on:g}. The dashed line is DAF = 2.",
        "",
        f"![daf]({rel(pngs['daf'])})",
        "",
        "## 3. Mass-collapse test: F_eq / (L d²)",
        "",
        f"All sizes and lengths on one panel per history type (top row lumped, bottom row JC), amplitude {amp:g}, mu = {mu_on:g}, d = OD. "
        "The spread table below states numerically what the panels show: a ratio near 1 means the curves of the different sizes and lengths fall on one line.",
        "",
        f"![collapse]({rel(pngs['collapse'])})",
        "",
        *collapse_spread(rows, mu_on, amp),
        "## 4. Where JC is negligible and where it is essential",
        "",
        "Counts of cases per frequency band and span length (sizes and amplitudes pooled; noise seeds counted separately).",
        "",
        *ratio_table(rows, "ratio_f_eq", mu_on),
        *ratio_table(rows, "ratio_v_peak", mu_on),
        *amplitude_table(rows, mu_on),
    ]
    if n_err:
        lines += ["## Errors", "", "| case | error |", "|---|---|"]
        lines += [f"| {r['case_id']} | {r['error']} |" for r in rows if r["error"]]
        lines.append("")
    doc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot(args) -> None:
    import matplotlib

    matplotlib.use("Agg")
    csv_path = Path(args.csv)
    rows = _load(csv_path)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    mus = sorted({r["mu"] for r in rows})
    mu_on = args.mu if args.mu is not None else max(mus)
    amps = sorted({r["amplitude_fraction"] for r in rows})
    amp = args.amplitude if args.amplitude is not None else max(amps)
    stem = csv_path.stem
    pngs = {
        "ratio_f_eq": out_dir / f"{stem}_ratio_f_eq.png",
        "ratio_v_peak": out_dir / f"{stem}_ratio_v_peak.png",
        "daf": out_dir / f"{stem}_daf.png",
        "collapse": out_dir / f"{stem}_collapse.png",
    }
    plot_ratio(
        rows,
        "ratio_f_eq",
        "F_eq JC / lumped",
        pngs["ratio_f_eq"],
        "JC / lumped equivalent static force",
        mu_on,
    )
    plot_ratio(
        rows,
        "ratio_v_peak",
        "v_peak JC / lumped",
        pngs["ratio_v_peak"],
        "JC / lumped peak velocity",
        mu_on,
    )
    plot_daf(rows, pngs["daf"], mu_on)
    plot_collapse(rows, pngs["collapse"], mu_on, amp)
    write_doc(rows, csv_path, pngs, Path(args.doc), mu_on, amp)
    print("wrote", Path(args.doc), *pngs.values(), sep="\n  ")


# ------------------------------------------------------------------ CLI


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="assert the pipe table against the owner's design pressures")
    r = sub.add_parser(
        "run",
        help="run a tier (or --limit / --subset of it for a smoke run) and write the CSV into --out",
    )
    r.add_argument("--tier", type=int, choices=sorted(TIERS), required=True)
    r.add_argument(
        "--subset",
        type=float,
        default=0.0,
        help="fraction of the tier (0 < f <= 1), stratified over every dimension (smoke run)",
    )
    r.add_argument("--subset-seed", type=int, default=0)
    r.add_argument("--limit", type=int, default=0, help="first N cases only (smoke test)")
    r.add_argument("--history", choices=histories.KINDS, default=None, help="one history type only")
    r.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    r.add_argument("--progress", type=int, default=25, help="print progress every N cases")
    r.add_argument(
        "--out",
        default=str(REPO / "docs" / "sweep"),
        help="directory the CSV is written into (default docs/sweep); the file is named by tier, git sha and --tag",
    )
    r.add_argument(
        "--tag",
        default="",
        help="suffix of the CSV name after the sha (a rerun, e.g. after the F-4b profile correction, must not overwrite an earlier file)",
    )
    p = sub.add_parser("plot", help="PNGs and docs/jc_sweep.md from a sweep CSV")
    p.add_argument("csv")
    p.add_argument("--out", default=str(REPO / "docs" / "sweep" / "png"))
    p.add_argument("--doc", default=str(REPO / "docs" / "jc_sweep.md"))
    p.add_argument(
        "--mu",
        type=float,
        default=None,
        help="friction level to plot (default: the largest in the CSV)",
    )
    p.add_argument(
        "--amplitude",
        type=float,
        default=None,
        help="amplitude for the collapse panel (default: the largest)",
    )
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.command == "check":
        check_pipe_table()
    elif args.command == "run":
        run(args)
    else:
        plot(args)


if __name__ == "__main__":
    main()
