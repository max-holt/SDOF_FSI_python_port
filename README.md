# surge_sdof

Python port of an Excel VBA solver for pipework surge loads: a 1-D method-of-characteristics
(MoC) water-hammer model and a single-degree-of-freedom (SDOF) pipe-response model with Coulomb
friction, support gaps and MoC junction-coupling fluid-structure interaction. The behavioural
source of truth is the VBA module in `legacy/vba/` and the Excel-generated fixtures in
`tests/fixtures/`; every solver is proved against them.

The package has two layers:

* `surge_sdof.legacy_port` and `surge_sdof.vba_compat`: the frozen line-for-line Stage 1
  transcription of the VBA. It is the reference the refactored modules are tested against
  (`tests/test_differential.py`) and will be removed in Stage 6.
* `surge_sdof.response`, `surge_sdof.pressure` and the modules behind them (`structure`, `loads`,
  `coupling`, `moc`, `_vba_semantics`): the Stage 4 restructure, value-identical to the
  transcription (bitwise on the differential suite) and 1.3-3.5x faster in pure Python
  (`docs/bench/README.md`). New code uses this layer. `docs/architecture.md` describes it.

## Install

Python 3.10 or later and numpy. From the repository root:

```
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

The `dev` extra adds pytest and ruff (and openpyxl / oletools, used only by
`tools/extract_fixtures.py` to regenerate the fixtures from the source workbook). The project's
commands invoke the interpreter as `.venv/bin/python`; adapt the path if your environment differs.

## Entry points

| Python | VBA | What it returns |
|---|---|---|
| `surge_sdof.response.peak_response(force_history, step_qty, sample_freq, physical_length, flexural_rigidity_ei, celerity, mass_per_unit_len, damping_percent, dynamic_fric, nat_freq, restrain_freq_ratio=1, gap=0, output_type=0)` | `GetPeakResponse` | `PeakResponse`: the five maxima (static-equivalent force N, displacement m, velocity m/s, acceleration m/s², applied force N) and, for `output_type` 1-3, the per-sample history |
| `surge_sdof.response.peak_response_jc(..., fluid_densty, fluid_area, ..., *, vav_denominator="fixed", parity="running")` | `GetPeakResponseJC` | `PeakResponse`, with the MoC fluid column coupled to the mass; the keyword flags select the two approved fixes (DEVIATIONS D-17, D-19); the values `"legacy"` / `"per_phase"` reproduce the VBA bitwise |
| `surge_sdof.pressure.pressure_response(valve_pattern, closure_time, celerity, density, time_step, pressure_drop_from_pump, flow_rate, pipe_area, valve_cv, length_to_pump, pump_ramp_pressure)` | `GetPressureResponse` | 0-based array of the valve pressure (Pa) after each loop iteration of two time steps |

Units are consistent SI for the two peak solvers (the VBA fixes m and s only through the
friction term); `pressure_response` keeps the VBA's mixed units (s, m/s, kg/m³, bar, m³/h, mm²,
Cv in US gpm). The docstrings give the unit of every argument. A 2-D `force_history` or
`valve_pattern` is walked column-major, first index fastest, exactly as Excel hands a range to
VBA (D-10). `legacy_port.get_peak_response`, `get_peak_response_jc` and `get_pressure_response`
take the same arguments and return the VBA arrays (1-based pad included, D-16).

## Worked example: the `Example` sheet lumped case

`tests/fixtures/example/cases.json` holds the three UDF calls of the workbook's `Example` sheet
with Excel's cached results. This reproduces `=GetPeakResponse(E3:E27, J6, ..., J14)` (a 25-sample
step force, 8 MN then 16 MN at 10 Hz, 80 sub-steps per sample, a 6 m span at 2 Hz) and prints the
five outputs next to Excel's:

```python
import json

import numpy as np

from surge_sdof.response import peak_response

case = next(
    c
    for c in json.load(open("tests/fixtures/example/cases.json"))
    if c["case_id"] == "example_lumped"
)
force = np.array(case["force_history"], dtype=float)  # 25 samples, N, as Excel's (25, 1) range
result = peak_response(force, **case["kwargs"])
for name, excel in zip(case["output_names"], case["expected"], strict=True):
    python = getattr(result, name)
    print(f"{name:28s} {python:22.15g} {excel:22.15g} {abs(python - excel) / abs(excel):8.1e}")
```

Output (name, Python, Excel, relative difference):

```
max_static_equivalent_force        489534.336282591       489534.336282603  2.5e-14
max_displacement                   1.90706021492509       1.90706021492514  2.5e-14
max_velocity                       24.0694597364374       24.0694597364381  2.8e-14
max_acceleration                   301.170333328046       301.170333328053  2.5e-14
max_applied_force                  405063.291139243       405063.291139243  0.0e+00
```

The `kwargs` of that case are `step_qty=80, sample_freq=10, physical_length=6,
flexural_rigidity_ei=1e7, celerity=1200, mass_per_unit_len=100, damping_percent=0.5,
dynamic_fric=0.01, nat_freq=2`; the VBA defaults `restrain_freq_ratio=1, gap=0, output_type=0`
apply. The same file holds `example_jc` (for `peak_response_jc`) and `example_pressure` (for
`pressure_response`, whose `valve_pattern` and 121 expected pressures are included).
`tests/test_golden.py::test_golden_example` runs all three at a relative tolerance of 1e-12.

## Tests

Invoke pytest through the project interpreter (`.venv/bin/python -m pytest`); a `pytest` on the
PATH may be an isolated tool without numpy. Golden curve cases are excluded by default through
`addopts` in `pyproject.toml`.

| Suite | Command | Content | Time (pure Python) |
|---|---|---|---|
| fast | `.venv/bin/python -m pytest -q` | VBA-semantics pins, quirk pins (DEVIATIONS), smoke, structure, the Example-sheet golden cases, the differential suite (new modules vs `legacy_port`, bitwise on seeded sweeps) | about 35 s |
| slow | `.venv/bin/python -m pytest -q -m slow` | the 75 lumped `GetPeakResponse` curve cases against Excel at 5e-12, through `legacy_port` and through `response.peak_response` | about 4-10 min |
| jc_slow | `.venv/bin/python -m pytest -q -m jc_slow` | the 3 junction-coupling curve cases against Excel at 5e-12 (literal port and `peak_response_jc` with the legacy flags) | 13-30 min per case |
| golden only | `.venv/bin/python -m pytest -q tests/test_golden.py -m "slow or jc_slow"` | the Excel comparisons alone; `tools/golden_report.py` tabulates the cached errors | |

Run the fast suite before every commit and `-m slow` before any commit touching `src/`
(CLAUDE.md). Lint and format: `ruff check . && ruff format .`.

## Benchmark

```
.venv/bin/python tools/bench.py            # 3 timed runs per case
.venv/bin/python tools/bench.py --profile  # plus one cProfile run per case
.venv/bin/python tools/bench.py --only response_r20 --only response_pressure_example  # subset, nothing written
```

Eight fixed cases from the golden fixtures (two lumped rows, a truncated JC row and the
Example-sheet pressure call, each through the literal port and through the Stage 4 modules).
It writes `docs/bench/<sha>.json` and appends a row to `docs/bench/README.md`; the paired
cases must produce identical result digests or the exit code is 1. Run it at the end of every
Stage 4/5 session and commit `docs/bench/`. Expect about 8 minutes.

## Where the behaviour is documented

* `DEVIATIONS.md`: every place the Python differs from, or deliberately preserves a quirk of,
  the VBA (ids D-1 .. D-23), each with its pinning test. Read it before relying on an edge case.
* `docs/port_review.md`: the Stage 1 close-out review: the table of VBA constants, the
  duplicated-code map the Stage 4 restructure followed, the blind spots of the Excel golden
  suite.
* `docs/architecture.md`: the Stage 4 module layout, fixed interfaces, exactness arguments and
  the data flow of one sub-step.
* `NOTES.md`: session hand-off (current stage, results, open issues, next action).
* `CLAUDE.md`: the working rules (stage discipline, hard rules, commands).

## Repository layout

```
src/surge_sdof/      the package (see above)
legacy/vba/          the VBA source of truth (never edited)
tests/               pytest suites; tests/fixtures/ holds the Excel-generated data (never edited)
tools/               bench.py, golden_report.py, extract_fixtures.py
docs/                architecture.md, port_review.md, bench/
```
