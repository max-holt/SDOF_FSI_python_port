"""The fixed inputs, the pipe table and the case grid of the junction-coupling sweep.

Part of ``tools/sweep_jc.py`` (review session R.8, plan 5.12): the inputs every case shares,
the pipe properties of each size (``pipe``, ``check_pipe_table``) and the tiers' cases
(``tier_cases``, ``stratified_subset``, ``coverage``).
"""

from __future__ import annotations

import math
import random
from collections import Counter
from pathlib import Path
from typing import NamedTuple

import fixture_cases  # tools/fixture_cases.py: the fixture loaders

from surge_sdof import histories

REPO = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ fixed inputs

PIPES = {
    # size_in: (od_mm, thk_mm) — tests/fixtures/source/surge_force_data.xlsm, curve_10in!J7:M8
    10: (273.1, 7.8),
    12: (307.1, 8.382),
    16: (406.4, 9.525),
    18: (457.0, 12.7),
}
FLUID_DENSITY = 1000.0  # kg/m³ (curve_10in!H9)
PIPE_DENSITY = 7800.0  # kg/m³ (curve_10in!H10)
YOUNGS_MODULUS = 195e9  # Pa (curve_10in!H14)
ALLOWABLE_STRESS = 138e6  # Pa, A106 Gr B (owner)
P_DESIGN_EXPECTED_BAR = {10: 78.8, 12: 75.3, 16: 64.7, 18: 76.7}  # owner's figures, ±0.1 bar
PA_PER_BAR = 1e5  # Pa per bar: a pressure in bar times this is in Pa
MM_PER_M = 1000  # mm per m: the pipe table gives diameters and wall thicknesses in mm

SUBSTEP_COUNT = 40
SAMPLE_RATE = 1000.0
CELERITY = 1237.0
DAMPING_PERCENT = 0.5
CLOSED_GAP_FREQUENCY_RATIO = 1.0
SUPPORT_GAP = 0.0
NOISE_REFERENCE_FREQUENCY = (
    4.0  # Hz: the envelope reference of step_noise (the middle Tier 1 f_osc)
)
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
    values = {float(r["nat_freq"]) for r in fixture_cases.load_cases() if r["solver"] == "lumped"}
    return tuple(sorted(values))


# ------------------------------------------------------------------ pipe properties


class Pipe(NamedTuple):
    """The properties of one pipe size: nominal size (in), outside diameter and wall
    thickness (mm), flow area (m²), mass per length of pipe and contents (kg/m), flexural
    rigidity (N·m²) and design pressure (Pa)."""

    size_in: int
    outside_diameter_mm: float
    wall_thickness_mm: float
    flow_area: float  # m²
    mass_per_length: float  # kg/m, pipe + contents
    flexural_rigidity: float  # N·m²
    design_pressure: float  # Pa


def pipe(size_in: int) -> Pipe:
    """The properties of one pipe size: the ``curve_10in`` sheet's formulas (H11, H13,
    H15, J15) and the hoop-stress design pressure ``2 t S / OD``.

    Parameters
    ----------
    size_in : int
        Nominal size, in; a key of ``PIPES``.

    Returns
    -------
    Pipe
    """
    od_mm, thk_mm = PIPES[size_in]
    inside_radius = (od_mm / 2 - thk_mm) / MM_PER_M
    # od / 2000: the halving and the mm-to-m conversion as one divisor; kept as written,
    # since two divisions would round differently.
    outside_radius = od_mm / 2000
    flow_area = math.pi * inside_radius**2
    mass_per_length = math.pi * (
        inside_radius**2 * FLUID_DENSITY + (outside_radius**2 - inside_radius**2) * PIPE_DENSITY
    )
    second_moment_of_area = (math.pi / 4) * (outside_radius**4 - inside_radius**4)
    design_pressure = 2 * (thk_mm / MM_PER_M) * ALLOWABLE_STRESS / (od_mm / MM_PER_M)
    return Pipe(
        size_in,
        od_mm,
        thk_mm,
        flow_area,
        mass_per_length,
        YOUNGS_MODULUS * second_moment_of_area,
        design_pressure,
    )


def check_pipe_table(verbose: bool = True) -> None:
    """Check the pipe table: the design pressures against the owner's figures (within 0.1
    bar) and the 10 in properties against ``tests/fixtures/curve_10in/params.json``.

    Parameters
    ----------
    verbose : bool
        Print the table and the result.

    Raises
    ------
    AssertionError
        A value off.
    """
    import json

    for size, expected in P_DESIGN_EXPECTED_BAR.items():
        got = pipe(size).design_pressure / PA_PER_BAR
        assert abs(got - expected) <= 0.1, f"{size} in: p_design {got:.2f} bar, expected {expected}"
        if verbose:
            print(
                f"{size:>2} in  OD {PIPES[size][0]:6.1f} mm  t {PIPES[size][1]:6.3f} mm  "
                f"p_design {got:6.2f} bar (owner {expected})  cap {histories.PEAK_TO_DESIGN_PRESSURE_RATIO * got:6.2f} bar"
            )
    params = json.loads((REPO / "tests/fixtures/curve_10in/params.json").read_text())
    p10 = pipe(10)
    for mine, key in (
        (p10.flow_area, "fluid_area"),
        (p10.mass_per_length, "mass_per_unit_len"),
        (p10.flexural_rigidity, "flexural_rigidity_ei"),
    ):
        assert math.isclose(mine, params[key], rel_tol=1e-9), (key, mine, params[key])
    if verbose:
        print(
            "10 in fluid area, mass/length and EI reproduce tests/fixtures/curve_10in/params.json"
        )


# ------------------------------------------------------------------ cases


class Case(NamedTuple):
    """One case of the sweep grid: pipe size (in), span length (m), natural frequency
    (Hz), history type with its sine frequency (Hz) or noise seed, the amplitude as a
    fraction of the common peak, and the friction coefficient."""

    size_in: int
    length_m: float
    natural_frequency: float  # Hz
    history_type: str  # "step" | "step_sine" | "step_noise"
    f_osc_hz: float | None
    seed: int | None
    amplitude_fraction: float
    friction_coefficient: float

    @property
    def history_key(self) -> tuple:
        """``(history_type, f_osc_hz, seed)``: the cases that share one history."""
        return (self.history_type, self.f_osc_hz, self.seed)

    @property
    def case_id(self) -> str:
        """The case's id in the sweep CSV, such as ``s10_L12_f3_sine4_a1_mu0.15``."""
        if self.history_type == "step":
            h = "step"
        elif self.history_type == "step_sine":
            h = f"sine{self.f_osc_hz:g}"
        else:
            h = f"noise{self.seed}"
        return (
            f"s{self.size_in}_L{self.length_m:g}_f{self.natural_frequency:g}_{h}"
            f"_a{self.amplitude_fraction:g}_mu{self.friction_coefficient:g}"
        )


def tier_cases(tier: int) -> list[Case]:
    """Every case of a tier (a key of ``TIERS``), in grid order."""
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


DIMENSIONS = (
    "size_in",
    "length_m",
    "natural_frequency",
    "history_key",
    "amplitude_fraction",
    "friction_coefficient",
)


def stratified_subset(cases: list[Case], fraction: float, seed: int = 0) -> list[Case]:
    """About ``fraction`` of the cases, every level of every dimension represented and
    balanced.

    A seeded shuffle, accepting a case while no level of any dimension exceeds its quota
    ``ceil(n_target / n_levels)``, then filled from the remainder if the quotas deadlock.

    Parameters
    ----------
    cases : list of Case
        The tier's cases.
    fraction : float
        The share to keep, ``(0, 1]``.
    seed : int, optional
        Seed of the shuffle (default 0).

    Returns
    -------
    list of Case
        In grid order.
    """
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
    """How many of ``cases`` each level of each dimension (``DIMENSIONS``) has."""
    return {d: dict(Counter(getattr(c, d) for c in cases)) for d in DIMENSIONS}
