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
  transcription (bitwise on the differential suite, under Numba as well), 1.3-3.5x faster in pure
  Python and far faster compiled (`docs/bench/README.md`). New code uses this layer.
  `docs/architecture.md` describes it.

## Install

Python 3.10 or later, numpy and numba. From the repository root:

```
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

The `dev` extra adds pytest, ruff and hypothesis (and openpyxl / oletools, used only by
`tools/extract_fixtures.py` to regenerate the fixtures from the source workbook). The `viz` extra
(`pip install -e ".[viz]"`: plotly, pandas) is needed only for the model animation
(`surge_sdof.viz`, `tools/animate.py`). The project's
commands invoke the interpreter as `.venv/bin/python`; adapt the path if your environment differs.

The inner loops (`structure.step_scalars`, `moc.step`, `response._integrate_kernel`) are
compiled with `numba.njit(cache=True)` on first use (about a second; the compiled code is cached
under `src/surge_sdof/__pycache__`). Set `NUMBA_DISABLE_JIT=1` to run the same source as plain
Python. The `Makefile` wraps the common commands: `make test`, `make test-nojit`, `make test-both`
(both modes after a Numba cache wipe), `make slow`, `make golden`, `make lint`, `make bench`,
`make clean-cache`.

## Entry points

| Python | VBA | What it returns |
|---|---|---|
| `surge_sdof.response.peak_response(force_history, step_qty, sample_freq, physical_length, flexural_rigidity_ei, celerity, mass_per_unit_len, damping_percent, dynamic_fric, nat_freq, restrain_freq_ratio=1, gap=0, output_type=0, trace_every=0)` | `GetPeakResponse` | `PeakResponse`: the five maxima (static-equivalent force N, displacement m, velocity m/s, acceleration m/s², applied force N) and, for `output_type` 1-3, the per-sample history; with `trace_every=k > 0` also `.trace`, a `surge_sdof.trace.Trace` of every `k`-th sub-step (state, elbow forces, friction force, stick flag; the maxima and history are unchanged bitwise) |
| `surge_sdof.response.peak_response_jc(..., fluid_densty, fluid_area, ..., trace_every=0, *, vav_denominator="fixed", parity="running")` | `GetPeakResponseJC` | `PeakResponse`, with the MoC fluid column coupled to the mass; the keyword flags select the two approved fixes (DEVIATIONS D-17, D-19); the values `"legacy"` / `"per_phase"` reproduce the VBA bitwise; a JC trace adds the junction force and the interleaved pressure / velocity column per frame with the grid geometry |
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
| fast | `.venv/bin/python -m pytest -q` (`make test`; `make test-both` adds the `NUMBA_DISABLE_JIT=1` run) | VBA-semantics pins, quirk pins (DEVIATIONS), smoke, structure, the Example-sheet golden cases, the differential suite (new modules vs `legacy_port`, bitwise on seeded sweeps), the hypothesis properties (`tests/test_properties.py`) | about 30 s per mode |
| slow | `.venv/bin/python -m pytest -q -m slow` | the 75 lumped `GetPeakResponse` curve cases against Excel at 5e-12, through `legacy_port` and through `response.peak_response` | about 4-10 min |
| jc_slow | `.venv/bin/python -m pytest -q -m jc_slow` | the 3 junction-coupling curve cases against Excel at 5e-12 (literal port, 23-30 min per case in pure Python; and `peak_response_jc` with the legacy flags, seconds under Numba) | see left |
| golden only | `.venv/bin/python -m pytest -q tests/test_golden.py -m "slow or jc_slow"` | the Excel comparisons alone; `tools/golden_report.py` tabulates the cached errors | |

Run the fast suite before every commit and `-m slow` before any commit touching `src/`
(CLAUDE.md). Lint and format: `ruff check . && ruff format .`.

## Benchmark

```
.venv/bin/python tools/bench.py            # 3 timed runs per case, three modes (literal / Python / Numba)
.venv/bin/python tools/bench.py --profile  # plus one cProfile run per pure-Python case
.venv/bin/python tools/bench.py --skip-full-python  # leave the full JC cases out of the pure-Python mode
.venv/bin/python tools/bench.py --only response_r20 --only response_pressure_example  # subset, nothing written
```

Fixed cases from the golden fixtures (two lumped rows, a truncated JC row and the Example-sheet
pressure call through the literal port and through the Stage 4 modules, plus the three full JC
golden rows through `peak_response_jc`), each refactored case timed twice in child processes:
as plain Python (`NUMBA_DISABLE_JIT=1`) and compiled (fresh `NUMBA_CACHE_DIR`, so the compile
time and the first call are measured separately from the steady state). Two more children record
the peak RSS of an `outputType = 1` run on the full history. It writes `docs/bench/<sha>.json`
and appends a three-row section (literal / refactored / Numba, in seconds and as ratios to the
in-session literal lumped case) to `docs/bench/README.md`; the paired cases must produce
identical result digests or the exit code is 1. Run it at the end of every Stage 4/5 session
and commit `docs/bench/`. Expect about an hour (the full JC cases in pure Python are ~15 min
each; `--skip-full-python` leaves them out and brings the run to about 10 minutes).

## Animation

```
.venv/bin/python tools/animate.py --golden example_jc --out docs/viz/example_jc_sheet.html
.venv/bin/python tools/animate.py --golden r096_jc_L24_f3 --t-start 6 --t-end 7.5 --max-frames 160 --out docs/viz/golden_r096_jc.html
.venv/bin/python tools/animate.py --step --amplitude 1600 --area 0.05 --length 6 --nat-freq 2 --mu 0.0001 \
    --sample-freq 10 --step-qty 80 --celerity 1200 --mass-per-len 100 --ei 1e7 --duration 2.4 --solver jc \
    --out docs/viz/example_jc_step.html
```

Session V.2 / V.2b: `surge_sdof.viz.animate.build_figure(result)` (the `viz` extra) turns a run
made with `trace_every > 0` into a two-panel plotly animation: the fluid column on the expansion
loop (inlet, leg, run, return leg, outlet; cells mapped by their moving fraction, sharp elbows)
with every cell a circle displaced by the mass motion times its moving fraction, sized by
its pressure and coloured by its velocity (constant for the lumped model), and the applied
unbalance `F_A(t) - F_B(t - L/c)` (left axis) over the friction force (right axis, zero lines
aligned) against time, phases shaded, a cursor at the frame time; slider, a typed playback
speed with play and pause on the page. `tools/animate.py` reruns a fixture case (`--golden`, a `curve_10in` case id
or `example_lumped` / `example_jc`) or a plain step (`--step`: zero for `--lead-in` 0.1 s, then
`--amplitude` bar on the area of a `--size` mm pipe or `--area` m²) and writes a standalone page
with plotly.js from the CDN (`--max-frames`, default 400, caps the frames; `--t-start` / `--t-end` animate a time window
at full resolution, shaded on the whole-run force panel; the stride and every scaling are
printed and put in the title). `docs/viz/` holds four such
pages; the full-library HTML is never committed. `docs/architecture.md` "Session V.2 / V.2b / V.2c / V.2d — the
animation" has the geometry and scaling rules.

## Data files for the JS viewer

```
.venv/bin/python tools/export.py trace --golden example_lumped --out docs/viz/data/example_lumped_step.json
.venv/bin/python tools/export.py trace --golden r096_jc_L24_f3 --out docs/viz/data/golden_r096_jc.json.gz
.venv/bin/python tools/export.py trace --step --amplitude 1600 --area 0.05 --length 6 --nat-freq 2 --mu 0.0001 \
    --sample-freq 10 --step-qty 80 --celerity 1200 --mass-per-len 100 --ei 1e7 --duration 2.4 --solver jc \
    --out docs/viz/data/example_jc_step.json
.venv/bin/python tools/export.py sweep --from-csv tests/fixtures/curve_10in/cases.csv --out docs/viz/data/reference_sweep.json
```

Session W.1: `surge_sdof.export` writes the data the single-file JS viewer (Session W.2) loads
and plays back live, from disk or a SharePoint / OCI bucket with no Python on the viewing
machine. `docs/data_format.md` is the contract (`tests/test_export.py` parses it): a `trace` file
holds one whole run at the trace stride (meta, the loop geometry, thirteen per-frame columns with
the rest frame first, the JC column arrays as row-major blocks), a `sweep` file holds Session 5b
rows as columns plus the Excel reference values the viewer self-checks against. Column-wise
arrays, floats via `repr`, no NaN, optional gzip by the `.gz` suffix. The default `--trace-every`
is the 2000-frame stride or the coarser one that keeps the JSON under 45 MB (row 96: 832 frames,
46.9 MB, 20.6 MB gzipped); the size written is printed. `docs/viz/data/` holds the four committed
files.

## The results viewer

```
.venv/bin/python tools/build_viewer.py      # docs/viewer/viewer.src.html -> docs/viewer/viewer.html
```

Session W.2: `docs/viewer/viewer.html` is one self-contained page (plotly.js 4.1.1 and pako's
inflate inlined, no network request of any kind) that opens a `trace` data file from the picker
or by drag-and-drop (`.json` or `.json.gz`) and plays the two-panel animation of `viz/animate.py`
with live controls: play / pause, speed (typed or 0.25x–4x), frame stride, `t_start` / `t_end`
window, exaggeration and colour range overrides, jump to peak; the header shows the file's meta
and the scaling in use; settings persist in the browser. Publish it by copying the one file.
`docs/viewer/README.md` is the user guide (opening, loading, publishing, browsers tested);
`tests/test_viewer.py` drives it in headless Chromium (skipped without a browser). Sweep mode
is Session W.3.

## Where the behaviour is documented

* `DEVIATIONS.md`: every place the Python differs from, or deliberately preserves a quirk of,
  the VBA (ids D-1 .. D-23), each with its pinning test. Read it before relying on an edge case.
* `docs/port_review.md`: the Stage 1 close-out review: the table of VBA constants, the
  duplicated-code map the Stage 4 restructure followed, the blind spots of the Excel golden
  suite.
* `docs/architecture.md`: the Stage 4 module layout, fixed interfaces, exactness arguments,
  the data flow of one sub-step, the Stage 5 kernels, the Session V.1 trace, the Session V.2 animation
  and the Session W.1 data files.
* `docs/data_format.md`: the contract of the viewer's `trace` and `sweep` data files.
* `docs/viewer/README.md`: the single-file results viewer (how to open, load, publish; browsers tested).
* `NOTES.md`: session hand-off (current stage, results, open issues, next action).
* `CLAUDE.md`: the working rules (stage discipline, hard rules, commands).

## Repository layout

```
src/surge_sdof/      the package (see above)
legacy/vba/          the VBA source of truth (never edited)
tests/               pytest suites; tests/fixtures/ holds the Excel-generated data (never edited)
tools/               bench.py, golden_report.py, extract_fixtures.py, animate.py, export.py, cases.py (shared case loading), build_viewer.py, viewer/ (vendored pako)
docs/                architecture.md, port_review.md, data_format.md, bench/, viz/ (animation pages), viz/data/ (viewer data files), viewer/ (the single-file viewer, its source and README)
```
