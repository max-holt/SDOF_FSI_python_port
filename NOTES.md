# NOTES — session handoff

## Current stage
Session V.2c (second review round) done 2026-10-23: sharp elbows (arcs removed), friction drawn
under the load line and translucent, frames that never touch the layout (no flicker, no vanishing
right-axis line at speed), typed playback speed on the page; pages regenerated; see "Session
V.2c — done". Next: the owner's local bench reference run, then Session 5b.
Session V.2b (animation fixes from the lead author's review) done 2026-10-23: expansion-loop
layout mapped by moving fraction with elbow arcs, friction on a right axis with aligned zero
lines, speed buttons, `--t-start` / `--lead-in`, four regenerated pages; only `viz/`, the tool,
tests and docs changed; see "Session V.2b — done" (elbow-cell report there). Next: the owner's
local bench reference run, then Session 5b.
Session V.2 (the model animation) done 2026-10-22: `src/surge_sdof/viz/animate.py` (plotly two-panel
animation of a `Trace`, `viz` extra), `tools/animate.py` (`--golden` / `--step`), `tests/test_viz.py`
(22 tests, both modes), `docs/viz/` (three CDN pages: Example lumped / JC, golden row 96); no
solver file touched; see "Session V.2 — done". Next: the owner's local bench reference run, then
Session 5b.
Session V.1 (trace hook for visualisation) done 2026-10-22: `trace_every` on both peak solvers,
`PeakResponse.trace` (`trace.Trace`), `loads.elbow_forces`; untraced path bitwise (differential
suite, bench within noise), traced run bitwise equal to the untraced one; see "Session V.1 —
done". Next: V.2.
Stage 5 (speed: Numba) done 2026-10-22: `structure.step_scalars`, `moc.step` and
`response._integrate_kernel` compiled with `numba.njit(cache=True)` (no fastmath), same source in
both modes (`make test-both`), differential sweeps **bitwise** under Numba (216/216), the three
full JC golden cases in ~1 s each (were 13-30 min), hypothesis properties, three-mode bench; see
"Stage 5 — done". Next: Stage 5b.
Stage 4.4 (hygiene, no behaviour change) done 2026-10-22: SIM/C4 lint rules, numpy-style docstrings
with units and DEVIATIONS ids on the six live modules, `docs/architecture.md` as built with the
per-sub-step data flow, `README.md`, DEVIATIONS legacy-only markers; differential suite bitwise
throughout; see "Stage 4.4 — done". Next: Stage 5 (Numba).
Stage 4.3 (refactor, pressure driver) done 2026-10-21: `src/surge_sdof/pressure.py` (`pressure_response`, `get_pressure_response` alias) and `_vba_semantics.py`, differential sweep 49/50 bitwise + 1 identical raise, Example case bitwise and at 1e-12 vs Excel; see "Stage 4.3 — done" (bench row and port review recorded there).
Stage 4.2 (refactor, JC path) done 2026-10-21: `src/surge_sdof/moc.py`, `coupling.JunctionCoupling`,
`structure.jc_params`, `response.peak_response_jc` (shared `_integrate`), approved fixes F-1 and
F-2 applied flag-first and flipped to the defaults (`vav_denominator="fixed"`, `parity="running"`;
the legacy flags reproduce `legacy_port.get_peak_response_jc` bitwise), DEVIATIONS D-17/D-19 "fixed",
JC differential sweep (100/100 bitwise), bench `(g)` case and reference ratios. Finding: F-1 is
numerically inert for the outputs (rounding level; see "Stage 4.2 — F-1/F-2 before/after").
Stage 4.1 (refactor, first seam) done 2026-10-21: `src/surge_sdof/structure.py`, `loads.py`, `coupling.py` (`NoCoupling` only), `response.py` (lumped `peak_response`), `docs/architecture.md`, `tests/test_differential.py` (sweep + golden differential against the frozen `legacy_port.py`, 335 tests, all bitwise), DEVIATIONS D-23, bench `docs/bench/4ea09d2.json`. `legacy_port.py` is unchanged and remains the reference until Stage 6. Stage 4.0 (performance baseline of the literal port) done 2026-10-21: `tools/bench.py`, `docs/bench/1adaddd.json`, `docs/bench/README.md`. Stage 1 (literal port) complete and **verified against Excel for both peak solvers**: all 75 `GetPeakResponse` golden cases pass at RTOL 5e-12 (max observed 8.3e-13) and, since 2026-10-21, all 3 `GetPeakResponseJC` golden cases pass at RTOL 5e-12 (max observed 8.6e-13; first full run, 1 h 20 min in pure Python). `GetPressureResponse` has no golden case yet (the workbook's `Example` sheet exercises it only on a demo pattern with cached values; not extracted). `src/surge_sdof/legacy_port.py` holds the line-for-line transcription; `vba_compat.py` the VBA-semantics helpers.

## Session V.2c — done (2026-10-23)
Lead author's second review (five items), all applied; only `viz/animate.py`, `tests/test_viz.py`,
the pages and docs changed.
1. Friction under the load line: the friction trace is added first (drawn below), 1.5 px,
   `rgba(235, 104, 52, 0.55)`; the unbalance stays 2 px opaque on top. Pinned (`test_zero_lines_coincide`).
2 / 3. Flashing and the vanishing friction line at speeds above 1x had one cause: every frame
   carried a `layout.title` change (the frame time and phase), and a layout change in a frame
   makes plotly relayout and redraw the whole figure per frame (the `redraw: True` the buttons
   used as well). Frames now change trace data only: the circles, the cursor, and a new status
   text trace in Panel 1 (top right) that shows `t` and the phase; every animate call (slider
   steps, play, the page's buttons) uses `redraw: false`. The title keeps the static scalings.
   Pinned: no frame has a layout, every slider step has `redraw: False`. (Not verified in a
   browser from this session: headless Chromium takes a static screenshot only; the mechanism
   is plotly's documented one, frames without layout + `redraw: false` = no redraw.)
4. Sharp elbows: the V.2b arcs are removed; the inlet elbow cell sits at `(0, leg_height)`, leg
   1 is `x = 0`, the run elbow cells at `(0, 0)` / `(run_length, 0)`, leg 2 `x = run_length`,
   the outlet elbow cell at `(run_length, leg_height_2)`; consecutive cells are exactly one
   spacing apart everywhere, the two cells across an elbow one spacing from each other along
   the two segments. `corner_radius` is gone from `LoopLayout`. Pipe heights are now the plain
   centreline lengths between elbow cells: Example 7.5 / 6.0 m (h = 7.69), row 96 4.03 / 4.00 m
   (h = 4.05). The 0.8-spacing size cap stays (3 px floor).
5. Typed speed: plotly has no text input, so `write_html` adds a control row under the figure
   with `post_script` JS: `playback speed ×[number input]`, play, pause; play calls
   `Plotly.animate(gd, null, {frame: {duration: base / speed, redraw: false}, fromcurrent,
   mode: 'immediate'})`, so retyping and pressing play changes the speed mid-run; the figure's
   own plotly buttons (play 1x / pause, kept for `fig.show()` in a notebook) are removed from
   the written copy. Pinned (`test_play_pause_and_typed_speed`).
- Tests 28 in both modes (4 s / 31 s); fast suite 862 passed; `-m slow` 150 passed (10 min)
  before the `src/` commit. Pages regenerated
  (`example_jc_sheet`, `example_jc_step`, `example_lumped_step`, `golden_r096_jc`).
- Judgement call: the per-frame time / phase moved from the title to a text trace inside Panel
  1 (the only way to update it without a layout change).

## Session V.2b — done (2026-10-23)
Lead author's review items 1-5, all applied; `src/` outside `viz/` untouched, no solver change,
no test deleted, skipped or loosened, no new dependency.
- **Elbow-cell report (item 4, printed before any change, Example JC case, frame of peak |x|:
  frame 1108, t = 1.38625 s, x = -1.7229 m).** The V.2 corners were the pivot A nodes with their
  neighbours: B6 (idx 13, s = 19.5 m, fraction 0.444, p = -1.525e6 Pa, v = +0.119 m/s), A7 (idx
  14, 21.0 m, 1.0, -1.320e6, +0.115), B7 (idx 15, 22.5 m, 1.0, -1.020e6, +0.365) and B10 (idx 21,
  31.5 m, 1.0, +8.07e5, +0.362), A11 (idx 22, 33.0 m, 1.0, +1.109e6, +0.111), B11 (idx 23, 34.5 m,
  1.0, +1.409e6, +0.361). The four elbows of the loop mapping: inlet/leg B4 (idx 9, 13.5 m,
  fraction 0, p = -1.501e6, v = -0.068) | A5 (idx 10, 15.0 m, 0.028, -1.554e6, -0.015); leg/run
  B6 | A7 (above); run/leg B11 (idx 23, 34.5 m, 1.0, +1.409e6, +0.361) | A12 (idx 24, 36.0 m,
  0.25, +1.570e6, +0.002); leg/outlet A13 (idx 26, 39.0 m, 0.028, +1.538e6, -0.025) | B13 (idx
  27, 40.5 m, 0, +1.483e6, -0.079). **Every pair is two distinct cells at distinct positions
  (1.5 m apart along the column), with distinct fractions, pressures and velocities**, so the
  arc was drawn as instructed (pinned by `test_example_jc_elbow_cells_are_distinct`). Two
  profile facts the mapping exposes, for the owner: (a) the node-centred B ramp starts at exactly
  0 at `n = extQTY` (B4 / B13 are the elbow cells) while D-4's `n < 3` test gives B3 (idx 7) the
  fraction 0.111 one place *before* that zero, so B3 and A4 (0.028) are drawn on the inlet tail;
  (b) the B ramp is one cell longer on the inlet side (B6 = 0.444 has no mirror: B11 = 1.0), so
  the legs differ by one cell: pipe heights 5.54 / 4.04 m for the Example grid (h = 7.69 m) and
  3.99 / 3.97 m for row 96 (h = 4.05 m).
- Item 1: `f_friction` on a secondary y-axis (right), `f_unbalance` on the left, both ranges
  `±1.06 max|f|` so the zero lines coincide (test `test_zero_lines_coincide`); legend labels
  "…, left axis" / "…, right axis"; phase bands and cursor stay on the primary.
- Item 2: `loop_layout` replaces `u_layout` (`LoopLayout` replaces `ULayout`): segments from
  the fraction profile (`_segments`: the fraction-1 block is the run, the last fraction-0 cell
  before it and the first after it the upper elbows), uniform spacing by `cell_position` along
  the centreline, inlet leftwards / outlet rightwards at the pipe height, legs vertical, panel
  title "Expansion loop: inlet, leg, run, return leg, outlet"; a light centreline is drawn under
  the circles (trace 0; the circles are trace 1, the cursor trace 4). Pinned: every fraction-0
  cell at its pipe height and every fraction-1 cell at `y = 0`, exactly, for the lumped golden,
  JC golden and Example JC layouts (`test_loop_layout_geometry`).
- Item 3: speed buttons 0.25x / 0.5x / 1x / 2x / 4x (1x = 40 ms a frame) plus pause, the slider
  below; `--max-frames` (default 400) was already there and stays.
- Item 4: quarter arcs of radius 1.5 spacings at the four elbows, arc-length parametrised, each
  starting or ending exactly at an elbow cell so the straights keep their cells (the Example leg
  2 is short, so the radius drops to 1.72 m there: `0.45 x leg / (pi / 2)`); the nominal circle
  is capped at 0.8 of the on-screen cell spacing, estimated from the now fixed 1200 x 900 px
  figure, with a 3 px floor (row 96's spacing is ~0.8 px on screen, so its page is a 3 px tube;
  the cap only bites there). Elbow pairs at distinct 2-D positions pinned for all three layouts.
- Item 5: `build_figure(..., t_start)` and `--t-start` drop the traced frames before `t_start`
  (and the synthetic rest frame; the time axis starts at `t_start`); `--step` has `--lead-in`
  (0.1 s of zero samples, at least one) and `--area` (m², overrides `--size`).
  `docs/viz/example_jc_step.html` is now the built-in step with the Example-sheet parameters
  (`--amplitude 1600 --area 0.05`, i.e. 8 MN, the sheet's first level, at t = 0.1 s, 2.4 s hold:
  peak |x| 1.742 m at t = 0.186 s); `example_jc_sheet.html` is the untrimmed sheet history
  (as the old `example_jc_step.html` was); `example_lumped_step.html` (sheet history, lumped)
  and `golden_r096_jc.html` (150 frames, 4.75 MB) regenerated with the new layout.
- Tests: `tests/test_viz.py` 28 tests (22 kept, the U geometry test replaced by the loop
  test x 3 layouts, plus elbow cells, zero lines, speed buttons, `t_start`), green under Numba
  and `NUMBA_DISABLE_JIT=1` (5 s / 31 s); fast suite 862 passed; `-m slow` 150 passed (10 min)
  before the `src/` commit. Visual
  check: headless Chromium screenshots of the Example JC and row 96 pages at the peak frame.
- Judgement calls to flag: (1) the arc starts/ends at the elbow cell rather than being centred
  on it, so the elbow cell itself keeps `y = pipe height` / `y = 0` (the owner's assertion) and
  the leg is `leg length - (pi - 2) r` tall; (2) the size cap is an estimate (plotly sizes
  markers in px, the axis scale depends on the fixed figure size); (3) `example_lumped_step.html`
  keeps the sheet history (the instruction named only the JC page); (4) with `t_start > 0`
  there is no rest frame, the first frame is the first kept traced frame.

## Session V.2 — done (2026-10-22)
Commits: `c9d1e11` (scope and plan), then the module / CLI / tests / extra, the three pages with
the docs, and this note. `src/surge_sdof/` solver modules, `legacy/`, `tests/fixtures/` untouched;
no test deleted, skipped or loosened; the only new dependencies are the owner's `viz` extra
(plotly 7.1.0, pandas 3.0.6, installed in `.venv` with `uv pip install`), imported lazily inside
`surge_sdof.viz` so the solver package stays numpy + numba.
- Built as planned (plan section below, all eight items). `build_figure(result, case_name,
  max_frames=400, nominal_size=None)` returns `(fig, AnimationInfo)`; the info carries every
  scaling the title prints (`exaggeration`, `p_ref`, `p_scale`, `k_p`, `v_scale`, `frame_stride`,
  `n_frames`, `capped`, the `ULayout`). `write_html` is the only writer and uses the CDN.
- Checked visually (headless Chromium screenshots of the Example JC / lumped and row 96 pages at
  rest and at the peak frame): the U with the ext cells above the dashed `h` mark, the legs
  bending with the ramp fractions, circle sizes following the pressure, the colour bar in m/s,
  the two force lines with the phase bands, the peak marker and the cursor, slider labels in s.
- Tests: `tests/test_viz.py`, 22 tests: the figure builds for `r020_lumped_L3_f2` (full history,
  stride 5000) and `r096_jc_L24_f3` (first 500 samples of its history, stride 100, the same
  1333-cell grid) with 12 frames; frame-0 offsets exactly zero (circles at `x_nominal`, size
  nominal, colour 0, `p = p_ref`); lumped size and colour constant across frames while the circles
  move; JC sizes inside `[0.15, 2] x nominal`, the largest over the trace exactly 2x; frame count
  <= cap for `max_frames` 3 / 7 / 12 / 50 / 400 with the last traced frame always kept; the last
  frame's cursor `t` == the last traced `t` (and the slider's last label, the time-axis end); the
  exaggeration draws the peak as 10 % of the run and the peak frame's offsets are `x * fraction *
  exaggeration`; U geometry (pivots at the corners, run `(N - 2 piv) 2 c dt`, leg `piv 2 c dt`,
  anchors at the top, uniform spacing on the run, `h` from `solve_portal_height`); the lumped
  layout is the grid the case would have; the D-4 display fallback; the scalar table and phase
  bands; `is_capped`; the CDN page is under 1 MB; no trace raises. Green under Numba (3 s) and
  `NUMBA_DISABLE_JIT=1` (24 s); fast suite 856 passed; `-m slow` 150 passed (8 min 27 s) before
  the `src/` commit.
- Pages: `docs/viz/example_jc_step.html` (0.65 MB, 350 frames, trace_every 2) and
  `example_lumped_step.html` (0.35 MB, 336 frames) from the Example-sheet inputs via `--golden`;
  `golden_r096_jc.html` from row 96 at `--max-frames 150` (4.7 MB; 400 frames would be 10.5 MB
  with 1333 cells x 4 float32 arrays per frame). Row 96 facts the page shows: peak |x| 3.62 mm at
  t = 6.66 s, exaggeration x665, p_scale 12.4 kPa, max |v| 2.59 mm/s, N = 666, pivot 87, run
  24.05 m, leg 4.25 m (h = 4.05 m), never enters free decay.
- Judgement calls to flag: (1) the U is 1 m per m of `cell_position` with no per-segment
  rescaling, so the drawn leg is `pivotSegQTY` cells (the rounded `h` plus the `extQTY` fixed
  cells above the anchor) and the run is `N - 2 pivotSegQTY` cells (about `L` plus two cells);
  the owner's "leg length = portal-frame height" is shown as the dashed `h` mark rather than by
  stretching the leg, so cell spacing stays uniform. (2) Colour is `v_cells` with `cmin/cmax =
  -+max|v|` rather than the normalised `v / max|v|`: the same picture, and the hover and colour
  bar then read in m/s. (3) `k_p = p_scale / max(p - p_ref)` makes the largest circle exactly 2x
  nominal; a size floor of 0.15x nominal keeps deep troughs visible (the Example JC case reaches
  it). (4) `--step` takes `--size` as the internal diameter in mm (area `pi d^2 / 4`) and defaults
  every other input to the `curve_10in` parameters (10-inch pipe: EI, mass per length, celerity,
  1265 Hz, 40 sub-steps), since the repository has no pipe-schedule table; `histories.py` in 5b
  can replace it. (5) The CLI's default `trace_every` targets about 2000 traced frames (Panel 2
  resolution inside the memory guard); `--trace-every` overrides. (6) The synthetic `t = 0`
  frame is labelled transit unless the run has no transit sub-step. (7) `is_capped` reads the
  first free-decay sample from the trace and compares `forced + free_decay_samples` with
  `2 outMax`; a run whose decay is shorter than one stride is reported uncapped.

## Session V.2 — scope and plan (recorded 2026-10-22 before touching `src/`)
Owner's instruction: the model animation that consumes `trace.Trace` (two panels, shared slider,
standalone CDN HTML). No solver change: `src/surge_sdof/viz/animate.py` only reads a
`PeakResponse` (its `trace` and `free_decay_samples`); the fast suite, `-m slow` and the
differential suite are untouched by construction (nothing under `response`, `moc`, `loads`,
`structure`, `trace` is edited). Decisions taken here (flag if you disagree):

1. **Dependencies.** `viz = ["plotly", "pandas"]` optional extra in `pyproject.toml` (owner's
   list); installed in `.venv` with `uv pip install`. `surge_sdof.viz` imports them lazily so the
   solver package stays numpy + numba only; `tests/test_viz.py` uses `pytest.importorskip("plotly")`
   (the extra, not a failing test, is what would skip it).
2. **Geometry (`u_layout`).** The column is laid on a U at 1 m per m of `cell_position`, no
   per-segment rescaling: leg 1 is `x = 0`, `y = s1 - s` for `s <= s1` (anchor end at the top,
   pivot A node `2 * pivotSegQTY` at the corner `y = 0`), the run is `y = 0`, `x = s - s1` up to
   the second pivot `s2 = (N - pivotSegQTY) * 2 c dt`, leg 2 is `x = s2 - s1`, `y = s - s2`. So
   the drawn leg is `pivotSegQTY * 2 c dt` = the cell-rounded portal-frame height plus the
   `extQTY` fixed cells, which continue the leg above the anchor; a dashed line at `y = h`
   (`structure.solve_portal_height`) marks the height from the case set-up, and the run is
   `(N - 2 pivotSegQTY) * 2 c dt`, about `L` plus two cells (`moc.grid_size`). JC runs use the
   trace's own `cell_position` / `cell_kind` / `moving_fraction` / `pivot_seg_qty`; lumped runs
   rebuild the same grid from the case inputs (`solve_portal_height`, `moc.grid_size`,
   `moc.interp_fractions`) with `dt = 1 / (sample_freq * step_qty)`. A lumped case whose grid
   has `pivotSegQTY = 4` (D-4 divide by zero in `interp_fraction_b`) gets `frac_b` with the
   `n < extQTY` test instead, display only; a short-pipe grid is drawn as it is.
3. **Frames.** Frame 0 is synthetic, `t = 0`: `x = 0`, `p = 0` (the column at rest,
   `moc.new_column`), `v = 0`, forces 0, phase transit. Then every `frame_stride`-th traced
   frame with the last traced frame always included: `frame_stride = ceil(n_trace / (max_frames
   - 2))`, so `1 + ceil(n_trace / frame_stride) + 1 <= max_frames` (default 400); the stride is
   printed and put in the title with `trace_every`. The figure title says "trace capped by the
   history window" when `forced_samples + free_decay_samples > 2 * out_max` (the run decayed
   past the traced window).
4. **Panel 1 scalings.** `exaggeration = 0.1 * run_length / max|x|` over the trace (1 when
   `max|x| = 0`), printed in the title; `x_circle = x_nominal + x(t) * moving_fraction *
   exaggeration`. `p_ref = 0` (initial pressure), `p_scale = max|p - p_ref|` over the trace,
   `k_p = p_scale / max(p - p_ref)` so the largest circle over the run is exactly `2 x` nominal
   (`k_p = 1` when no pressure rises above `p_ref`), size floor `0.15 x` nominal so a deep
   trough does not vanish. Colour `v / max|v|` on a blue–grey–red diverging scale with `cmin =
   -1`, `cmax = 1`, colour bar "relative fluid velocity (JC arrays)" with the tick labels in m/s.
   Lumped: constant nominal size and the scale's grey midpoint, no colour bar. Hover: cell index,
   kind (A node / B cell), position (m), fraction, and p (Pa) / v (m/s) for JC. Display arrays
   are float32 (plotly typed arrays; the HTML is 5.3 bytes per value instead of ~18 as text).
5. **Panel 2.** `f_unbalance` and `f_friction` (`Trace.f_friction`, owner's definition) against
   `t` over every traced frame plus the `t = 0` row (a pandas table `scalars_table` holds the
   per-frame scalars), 2 px lines, a legend; the cursor is a two-point trace updated per frame;
   phase bands are `vrect` shapes from the phase changes in `t` (transit / history / free
   decay), the time of peak `|x|` a `vline` with its value; the frame's `t` and phase go in the
   title (frames carry a `layout.title`). Shared slider and play / pause (`updatemenus`).
6. **CLI `tools/animate.py`.** `--golden <case_id>` reruns a fixture case (curve ids such as
   `r096_jc_L24_f3`, or the Example ids `example_lumped` / `example_jc`) through the Stage 4
   solver with `trace_every` (default: the stride that gives about 2000 traced frames so Panel 2
   keeps its resolution inside the memory guard; `--trace-every` overrides); `--step` builds a
   plain step history: `--amplitude` bar on the fluid area of `--size` (internal diameter, mm),
   `--length` m, `--nat-freq` Hz, `--mu` (dynamicFric), `--solver lumped|jc`, the other inputs
   defaulting to the `curve_10in` parameters (`--sample-freq`, `--step-qty`, `--duration`,
   `--celerity`, `--mass-per-len`, `--ei`, `--density` override); the first sample is 0 so the
   step is a step. `--out docs/viz/<name>.html`, `--max-frames`. `write_html(include_plotlyjs=
   "cdn")` only; the full-library HTML is never written by the tool.
7. **Tests (`tests/test_viz.py`).** The figure builds for `r020_lumped_L3_f2` and
   `r096_jc_L24_f3` (traced at a coarse stride, `max_frames` small); offsets at the synthetic
   frame 0 are exactly zero; size and colour constant across lumped frames; the frame count
   respects the cap for several `max_frames`; the last frame's cursor `t` equals the last traced
   `t`; the U layout puts the pivots at the corners and the run length at `(N - 2 piv) 2 c dt`.
8. **Deliverables.** `docs/viz/example_jc_step.html`, `docs/viz/example_lumped_step.html`
   (Example-sheet inputs via `--golden`), `docs/viz/golden_r096_jc.html` (row 96; a lower
   `--max-frames` if the 1333-cell column makes the file too large to commit, the choice
   recorded), `docs/architecture.md` row for `viz/animate.py`, README section, NOTES.

## Session V.1 — done (2026-10-22)
Commits: `ab398a6` (scope), `e8314da` (`loads.py`: shared `_schedule`, `elbow_forces`), `2b0d105`
(`trace.py`, `response.py` hook, `tests/test_trace.py`), `f2f4211` (docs), then bench and this
note. `legacy/`, `tests/fixtures/`, `legacy_port.py`, `vba_compat.py`, `structure.py`, `moc.py`
untouched; no test deleted, skipped or loosened; no new dependency.
- API as planned: `peak_response(..., trace_every=0)`, `peak_response_jc(..., trace_every=0, *,
  ...)`, `PeakResponse.trace: Trace | None = None` (trailing, defaulted). `trace.Trace` fields
  and the frame convention are in `trace.py`'s module docstring and `docs/architecture.md`
  "Session V.1 — the trace". Two naming drifts from the plan, both non-numeric: the guard
  constant is `trace.MAX_TRACE_VALUES` (not `MAX_TRACE_FLOATS`) because it counts int64 columns
  too; the kernel's per-frame arrays are `tr_f (cap, 8)`, `tr_i (cap, 4)`, `tr_p`, `tr_v`.
- Decision 5 measured: the shared per-sample `_schedule` generator costs nothing measurable on
  the untraced lumped case (`bench --only response_r20 --repeats 5`, before → after: Numba
  0.285 → 0.258 s, Python 1.038 → 1.038 s), so `elbow_forces` shares the walk (no duplication).
- Tests: `tests/test_trace.py`, 96 tests (53 `elbow_forces` + 43 trace), green under Numba and
  `NUMBA_DISABLE_JIT=1`; fast suite 834 passed in both modes; `-m slow` under Numba 150 passed
  before each of the two `src/` commits. Pinned: traced == untraced bitwise (4 lumped sweep
  cases × strides 1/3/7 × output types 0 + history type; 4 JC small cases × 3 strides × types
  0/3; both flag sets), stride / length / time / sample / phase arithmetic against the
  `elbow_forces` schedule and `free_decay_samples`, the free-decay cap (a 6-sample step at 1 Hz:
  decay 44/47 samples against a 6-sample window; frames at sample ends equal the history),
  `f_unbalance == flat[sub_step]` and `f_a - f_b == f_unbalance` bitwise, `f_friction == 0` and
  no stick with `dynamicFric = 0`, `stick == (|v_prev| < fric_acc)` and the slip value
  `-+ mass fric_acc / dt` (rtol 1e-9) at stride 1, JC geometry vs `moc.grid_size` /
  `interp_fractions`, frame 0 column == `moc.new_column`, a fresh `JunctionCoupling` driven with
  the traced `a` reproduces `d_f` and both column rows bitwise at every frame (stride 1,
  running parity), the memory guard (constant monkeypatched small: raises, the named stride
  runs, one less raises; lumped guarded too), the short-pipe fallback trace is lumped.
- Port review (`port-reviewer`, `git diff 8d0f363`, diff + VBA only): **no correctness
  findings**. It checked `_schedule` against VBA 394-567 and the pre-diff walk (phase-1
  `Exit For`, D-8 post-loop `iB`/`jB`, the phase-2 advance between the two `k` loops), the
  kernel's untouched state updates / parity / trackers / `_record` / decay test, the
  recording branch (reads only; `frame < cap` guards every unchecked write), the capacity
  arithmetic, `f_friction` against `step_scalars` 464/486/491, the interleave, and ran the
  differential fast set after a recompile (550 passed). One pre-existing note, recorded under
  Open issues (D-8 wording).
- Bench (`tools/bench.py --skip-full-python`, `docs/bench/f2f4211.json`, README "Stage 5 runs"
  section; Intel Xeon @ 2.80 GHz, in-session (a) 3.235 s): ratios to (a) vs `b9597a3` — Numba
  (e) 0.090 (was 0.081), (f) 0.082 (0.090), (g) 0.044 (0.047), full JC 0.554 / 0.510 / 0.476
  (0.555 / 0.541 / 0.505); pure Python (e) 0.342 (0.347), (f) 0.345 (0.322), (g) 23.9 (25.8).
  Every change is inside the run-to-run spread of the two records (the lumped Numba cases move
  ±10 % between runs; e/f swapped sign), so the untraced path has no measurable cost. All eight
  digest pairs equal, every case `same` as `b9597a3`, full JC vs Excel 8.6e-13 / 2.1e-14 /
  8.4e-15 unchanged, compile 2.86 s, peak RSS 191 MB.
- Judgement calls to flag: (1) frame = end of sub-step `i * k` (not the state before it), so
  frame 0 is at `t = dt`, not 0; (2) the JC column is interleaved `A0 B0 A1 … AN` with
  `cell_kind`, rather than four separate per-grid arrays; (3) free decay is traced only inside
  the history window (`totInd <= outMax * 2`), as the history is; (4) `inputs` of a fallback
  trace are the lumped call's (the `fluid_*` keys are absent) and `solver` says
  `"peak_response"`.

## Session V.1 — scope and plan (recorded 2026-10-22 before touching `src/`)
Owner's instruction: a trace hook in the two peak solvers for visualisation. No behaviour
change: the untraced path stays bitwise (differential suite), the traced path returns the same
`PeakResponse` values bitwise (pinned by a test), and the untraced cost is checked with
`tools/bench.py`. Decisions taken here (flag if you disagree):

1. **API.** `peak_response(..., trace_every: int = 0)` and `peak_response_jc(..., trace_every=0)`
   (keyword, validated `int >= 0`). `PeakResponse` gains a trailing defaulted field
   `trace: Trace | None = None` (frozen dataclass, existing callers unchanged). The JC short-pipe
   fallback passes `trace_every` through, so such a trace is a lumped trace (`trace.solver ==
   "peak_response"`, JC fields None).
2. **`trace.py`** (new module) holds the `Trace` dataclass and the one-off geometry helpers.
   Frame convention: frame `i` is the **end of sub-step `i * trace_every`** (`sub_step` is the
   running 0-based counter `n` of `_integrate_kernel`, the same index whose parity drives the
   MoC); `t = (sub_step + 1) * dt`; `x, v, a` are the state after that sub-step; `f_a`, `f_b`,
   `f_unbalance` the forces applied during it (0 in free decay); `d_f` the junction force the
   sub-step used (`moc.step` runs before the SDOF step; 0.0 for lumped); `p_cells`/`v_cells`
   the column after the sub-step. `sample` is the 0-based sample index (`totInd - 1`, the
   history index); `phase` 0 = transit (delay, phase 1 of the VBA), 1 = history (ramp), 2 =
   free decay. Frame 0 is therefore the end of sub-step 0, where a column at rest with `a = 0`
   is still bitwise the initial column.
   `f_friction = mass * dv_friction / dt` with `dv_friction = v_new - (v_old + (a_old + a_new)
   * (dt / 2))`, recomputed in the trace branch from the same doubles `step_scalars` formed
   (`half_dt = dt / 2`, `v + av`), so `structure.step_scalars` is untouched: slip gives
   `-+fric_acc` (0.0 exactly with `dynamicFric = 0`), stick (`|v_old| < fric_acc`, D-20 dead
   zone excluded) gives the holding value `av - (v_old + av)`, i.e. the momentum the stick
   removed; `stick` is that test. Column layout for the JC fields: the staggered grid
   **interleaved** `A0 B0 A1 B1 … A(N)`, `n_cells = 2N + 1`, with `cell_kind` (0 = A node, 1 = B
   cell), `cell_position = j * celerity * dt` (m from the first A node; a cell is `2 c dt` long
   and the column runs ext cells, leg to the pivot, span, leg, ext cells, `moc.grid_size`) and
   `moving_fraction` = `frac_a` / `frac_b` interleaved the same way (the values `moc.step`
   uses; `frac_a[0]` and `frac_a[N]` are the unused zeros). One-off fields: `solver`,
   `trace_every`, `dt`, `step_qty`, `out_max`, `params` (`SdofParams`), `inputs` (the case
   inputs as the solver received them, `force_history` as the 2-D array), `pivot_seg_qty`,
   `pipe_seg_qty`, `ext_qty`, `n_cells` (None / 0 for lumped).
3. **Capacity and the free-decay cap.** Phase 3's length is unknown before the run, so the
   trace follows the history's own cap: sub-steps are traced while `totInd <= outMax * 2` (the
   `_record` guard); later free-decay sub-steps are integrated but not traced, as the history
   drops them. Capacity = `ceil((forced_substeps + max(0, outMax*2 - forced_samples) *
   stepQTY) / trace_every)` frames, allocated once; the kernel returns the frames written and
   the orchestrator slices. Memory guard before allocation: `ValueError` when `capacity *
   (8 scalar columns + 2 * n_cells)` floats would exceed `MAX_TRACE_FLOATS = 50e6`, the message
   naming the smallest stride that fits (this is the owner's `n_frames * n_cells` guard plus the
   per-frame scalars, so the lumped path is guarded too).
4. **Kernel.** `_integrate_kernel` takes `trace_every`, `flat_a`, `flat_b` (per-sub-step
   elbow forces, empty when untraced), `delay_substeps` (phase 0 -> 1 boundary), and four
   preallocated arrays: `tr_f (cap, 8) float64` (x, v, a, f_a, f_b, f_unbalance, f_friction,
   d_f), `tr_i (cap, 4) int64` (sub_step, sample, phase, stick), `tr_p`, `tr_v` `(cap, n_cells)`
   (`(0, 0)` when untraced or lumped). Per sub-step one test `rec = trace_every > 0 and n %
   trace_every == 0`; `rec` saves `v_old, a_old` before `step_scalars` and calls the `njit`
   helper `_trace_frame` after it. With `trace_every == 0` the branch is never entered; the
   state arithmetic is untouched in both cases. Returns `n_frames` as an 11th element. Works
   under `NUMBA_DISABLE_JIT=1` (plain Python, one extra boolean test per sub-step there).
5. **`loads.py`.** The index walk becomes a private per-sample schedule generator shared by
   `unbalance_force` (inner `k` loops and the yielded lists unchanged, so bitwise by
   construction: same operands, same operations) and the new `elbow_forces(...)`, which yields
   `(phase, force_a_list, force_b_list)` per sample for the trace; `fa - fb` of its lists equals
   `unbalance_force` bitwise (test on the sweep, the Example case and the golden history). The
   per-sample generator hop is the only cost to the untraced lumped path; measured with
   `tools/bench.py --only response_r20` before and after. If it is measurable (outside the
   run-to-run noise of the two medians), `elbow_forces` duplicates the walk instead and the
   equality test is the guard.
6. **Tests** (`tests/test_trace.py`): `trace_every` validation; length and stride arithmetic
   (`n_frames == ceil(T / k)`, `sub_step == k * arange`, `t == (sub_step + 1) * dt`, `sample`
   vs the offsets) for several strides and both solvers incl. a case that enters free decay and
   one that hits the cap; the `PeakResponse` of a traced run bitwise equal to the untraced one
   (summary, history, `free_decay_samples`; strides 1, 3, 7, both solvers, output types 0-3);
   phase labels change exactly at the sub-steps `elbow_forces` says; `f_unbalance == flat[sub_step]`
   and `f_a - f_b == f_unbalance` bitwise, 0 in free decay; `f_friction == 0` and `stick` all
   False with `dynamicFric = 0`, `stick == (|v_prev| < fric_acc)` and the slip value `-+mass *
   fric_acc / dt` at stride 1 with friction; `d_f == 0` for lumped; JC: `p_cells[0]`/`v_cells[0]`
   equal the interleaved `moc.new_column`; at stride 1 a fresh `JunctionCoupling` driven with
   `(0, 0, a[i-1])` and `step_index = i` reproduces `d_f` and both column rows bitwise at every
   frame (`parity="running"`); geometry fields (`n_cells`, `cell_kind`, positions, fractions vs
   `moc.interp_fractions`); memory guard (`MAX_TRACE_FLOATS` monkeypatched small: raises,
   message names a stride that then runs); the fallback trace is lumped. Both modes.
7. **Docs, bench, review.** `docs/architecture.md`: `trace.py` row, interface lines, a "Trace"
   section; README entry-point table mentions `trace_every`. `tools/bench.py --skip-full-python`
   after the `src/` commits, `docs/bench/<sha>.json` + README section committed; the check is
   the ratio of every refactored case to the in-session (a) against `b9597a3` within noise.
   `port-reviewer` on `git diff 8d0f363`, findings applied. NOTES done section, next action V.2.
Commits: this scope; `loads.py`; `trace.py` + `response.py` + tests; docs; bench; review fixes if
any; NOTES. Gates: `make test-both` before every commit, `-m slow` under Numba before each
`src/` commit. Untouched: `legacy/`, `tests/fixtures/`, `legacy_port.py`, `vba_compat.py`,
`structure.py`, `moc.py`; no test deleted, skipped or loosened; no new dependency.

## Stage 5 — scope and plan (recorded 2026-10-22 before touching `src/`)
Owner's instruction: speed (Numba). Step 0 done first: `tools/bench.py --profile` on the pure-Python
Stage 4.4 code (`docs/bench/b5fc5c7.json`, commit 3948a7f) so the latest bench entry is the
pre-Numba profile. Approved at plan review (decisions A-D and amendments, 2026-10-22):

1. `numba` in `pyproject` dependencies, `hypothesis` in `dev`. `@numba.njit(cache=True)` (no
   fastmath, never object-mode `@jit`) on: `structure.step_scalars(x, v, a, f_applied, mass,
   stiffness, damping, fric_acc, gap, ratio2, dt) -> (x, v, a)` with `structure.step(state,
   f_applied, params, dt)` kept as the interface as a one-line unpacking wrapper (**C**);
   `moc.step` whole, body unchanged; `response._integrate_kernel` (sample loop, max trackers,
   `_record`, `_decay_test`, free decay) with `_integrate` as the Python orchestrator: it
   concatenates the `loads.unbalance_force` per-sample lists once into a flat float64 array plus
   int64 sample offsets, unpacks `SdofParams` and the coupling (kind 0 = none with empty arrays,
   kind 1 = junction with its arrays and scalars), calls the kernel, writes `d_f` back, casts the
   maxima to Python floats, builds `PeakResponse`. Kernel signatures take floats, ints, bools and
   numpy arrays only. The Python-level `Coupling` interface (`NoCoupling`, `JunctionCoupling
   .coupling_force`, `column()`) stays for callers. `f = float(flat[i])` and `d_f =
   float(moc.step(...))` keep the SDOF state on Python floats under `NUMBA_DISABLE_JIT=1`
   (no-ops under Numba). `pressure.py` stays un-JIT'd (milliseconds; not a bottleneck).
   **A**: `numpy.errstate` has no effect in compiled code and `rhoC = 0` would raise
   `ZeroDivisionError` under Numba but `FloatingPointError` in Python mode under the Stage 4
   `errstate` block (which is removed with the kernel; without it Python mode would give `inf`
   and a numpy `RuntimeWarning`), so `peak_response_jc` checks `rho_c == 0` once at set-up and
   raises `FloatingPointError` there (precedent D-4); a
   fluid overflow under Numba propagates nan/inf and the end-of-run finiteness check raises
   (D-23 style). D-9 / D-14 / D-23 wording updated.
   **B**: `test_running_parity_is_continuous_across_phase_boundaries` monkeypatches `moc.step`,
   which a compiled loop cannot see; the probe is changed to run the pure-Python form of the
   same kernel (`_integrate_kernel.py_func`, or the function itself with JIT disabled), every
   assertion unchanged, one docstring line saying so and why.
2. Both modes green: `pytest -q` and `NUMBA_DISABLE_JIT=1 pytest -q`. `Makefile` targets `test`,
   `test-nojit`, `test-both` (numba cache wipe first: `cache=True` does not track callee changes
   in other modules), `slow`, `lint`, `bench`, `clean-cache`. **D**: minimal
   `.github/workflows/ci.yml`: lint + fast suite in both modes with the cache wipe; slow/jc_slow
   stay manual.
3. Differential tolerance: measure the max relative Numba-vs-`legacy_port` difference on the
   lumped sweep, the JC sweep (legacy flags), the small JC replays and the Example cases before
   touching any tolerance; rtol 1e-12 stays if <= 1e-13, otherwise stop and show the expression
   and both values (no arithmetic restructuring, no fastmath). Note: none of the three JIT'd
   functions contains `**` (powers live in the set-up, which stays Python), so the D-15 lowering
   concern does not apply to them; FMA contraction (LLVM does not contract without fastmath) and
   `x / 2` -> `x * 0.5` (exact) are what remain to watch.
4. Golden: `pytest -m "slow or jc_slow" --durations=0` under Numba for the Numba-affected set
   only (75 lumped golden, 75 lumped differential, 3 `peak_response_jc` golden); the 3
   literal-port JC cases are unchanged pure Python with recorded results and are not re-run
   (owner amendment, saves 80 min). Report time per case and max relative error; same stop rule.
5. Bench: `tools/bench.py` as a driver: literal cases in-process; refactored cases in a child
   with a fresh `NUMBA_CACHE_DIR` (first call = true compile time, reported separately from the
   steady-state median) and a child with `NUMBA_DISABLE_JIT=1`; a child running `outputType=1` on
   the full history (lumped r20, JC r96) reporting peak RSS; the 3 full JC golden cases via
   `peak_response_jc` (legacy flags) added to the case set; numba and llvmlite versions in the
   JSON; README gets per run a three-row table literal / refactored (pure Python) / Numba in
   seconds and ratios to the in-session (a), compile times and peak RSS; the pre-Stage-5 history
   table stays above. Print the local command and the files to commit for the owner's reference
   run.
6. `tests/test_properties.py` (hypothesis, `derandomize=True`, `deadline=None`, ~30 examples,
   small cases): gap 1e9 == gap 0 with ratio 1 bitwise; linear scaling with `dynamicFric = 0` and
   the gap never engaged (power-of-two factor: bitwise over the samples both runs compute, and
   the summary when `free_decay_samples` agree; arbitrary factor: forced-phase history at rtol
   1e-9; the absolute D-21 threshold makes phase-3 length amplitude-dependent); all maxima finite
   and >= 0, history finite; JC with `fluidArea = 0` equals lumped within 1e-12.
7. `port-reviewer` on the final diff; `docs/architecture.md` Stage 5 section (kernel signature,
   modes, cache, pressure.py un-JIT'd with the reason); README install and `make` targets;
   DEVIATIONS rows; NOTES done section; next action Stage 5b.
Commits: scope (this), one per module (structure, moc, response+coupling), Makefile/CI, bench,
properties, docs. Gates: fast suite in both modes before each commit, `-m slow` under Numba before
each `src/` commit, `-m slow` under `NUMBA_DISABLE_JIT=1` once at the end. Untouched: `legacy/`,
`tests/fixtures/`, `legacy_port.py`, `vba_compat.py`; no test deleted, skipped or loosened.

## Stage 5 — done (2026-10-22)
Commits: `3948a7f` (step 0 bench baseline `b5fc5c7.json`), `83d12d1` (scope, numba dependency,
hypothesis dev extra), `8789870` (`structure.step_scalars`), `eb35a9e` (`moc.step` compiled;
`rhoC = 0` at the set-up, D-9), `b6e8a51` (`response._integrate_kernel`, coupling `KIND`, test
probe B, D-14/D-23), `f771210` (Makefile, CI), then bench, properties, docs (see git log).
`legacy/`, `tests/fixtures/`, `legacy_port.py`, `vba_compat.py` untouched; no test deleted,
skipped or loosened (the one test edit is the probe mechanism of
`test_running_parity_is_continuous_across_phase_boundaries`, assertions unchanged, decision B).
- Environment: numba 0.68.0, llvmlite 0.50.0, hypothesis 6.170.5 (`uv pip install --python
  .venv/bin/python -e ".[dev]"`); numpy 2.5.4, Python 3.13.16.
- Kernels: `structure.step_scalars(x, v, a, f, mass, k, c, fric_acc, gap, ratio2, dt)` (the old
  `step` body; `step` is the unpacking wrapper), `moc.step` (body unchanged),
  `response._integrate_kernel` (the old `_integrate` loop on a flat float64 unbalance array +
  int64 sample offsets, `SdofParams` as six floats, coupling as `KIND` + arrays + scalars;
  `float()` casts keep Python-float state in `NUMBA_DISABLE_JIT=1` mode). `_integrate` is the
  Python orchestrator. `pressure.py` not compiled (milliseconds). Kernel compile (fresh cache,
  first call of the Example lumped case) about 1.0-1.4 s in this container; `cache=True` makes
  later processes load it.
- Error semantics (decision A): `rhoC = 0` → `FloatingPointError` at the `peak_response_jc`
  set-up (after the fallback decision; a short pipe with `rhoC = 0` still takes the lumped path
  as in VBA); fluid overflow → nan/inf propagate, `FloatingPointError` at the end of the run
  (D-23). The `np.errstate` block around the JC loop is gone (no effect in compiled code).
  DEVIATIONS D-9, D-14, D-23 reworded.
- **Step 3, differential tolerance: measured max relative difference Numba vs `legacy_port` = 0.**
  Scratch script over the lumped sweep (50 cases × {type 0, history type} = 100), the JC sweep
  (50 × 2 = 100, legacy flags), the four JC small cases × types 0-3 (16) and the two Example
  cases (types 0-3): **216/216 comparisons bitwise**; Example vs Excel 2.8e-14 (lumped) and
  2.6e-15 (JC) as before. rtol 1e-12 unchanged. Reason: none of the three kernels contains `**`
  (D-15 does not arise), LLVM does not form FMAs without fastmath, `x / 2` → `x * 0.5` is exact.
- **Step 4, golden under Numba** (`pytest -m "slow or jc_slow" --durations=0`, the three
  literal-port JC cases deselected per the owner's amendment): **153 passed in 5 min 33 s**. The
  three full JC cases through `peak_response_jc` (legacy flags) vs Excel:

  | row | f (Hz) | N | time (s), Numba | time (s), pure Python (293e507) | max rel err | per output (static-eq / x / v / a / F) |
  |---|---|---|---|---|---|---|
  | 96 | 3 | 666 | 1.19 (incl. compile) | 969 | 8.6e-13 | 7.5e-13 / 7.5e-13 / 8.6e-13 / 2.0e-13 / 0 |
  | 97 | 7.5 | 592 | 0.88 | 856 | 2.1e-14 | 2.1e-14 / 2.1e-14 / 1.8e-14 / 1.5e-14 / 0 |
  | 98 | 22 | 546 | 0.93 | 800 | 8.4e-15 | 8.4e-15 / 8.4e-15 / 2.7e-15 / 6.5e-15 / 0 |

  Errors identical to the recorded pure-Python values, as the bitwise sweep predicts. The rest of
  the 5.5 min is the legacy pure-Python side of the lumped golden and differential cases (75
  `legacy_port` golden runs 155 s, 75 differential pairs 173 s); the 75 `peak_response` runs
  under Numba are ~0.2 s each, almost all of it the Python `loads.unbalance_force` generator.
- Suites: fast suite 738 passed under Numba (26 s) and under `NUMBA_DISABLE_JIT=1` (34 s); `-m
  slow` under Numba 150 passed before each `src/` commit; `-m slow` under `NUMBA_DISABLE_JIT=1` once at the end: **150 passed** in 11 min 32 s (this container; the pure-Python kernel reads the flat unbalance array per sub-step, so the refactored lumped cases are ~1.3 s each instead of 0.7 s in Stage 4, see the bench row).
- Properties (`tests/test_properties.py`, hypothesis, derandomized, 30 examples each, 1-2 s in
  both modes): huge gap ≡ gap 0 with ratio 1 bitwise (both solvers, all output types);
  power-of-two load scaling bitwise over the common samples and the summary when the phase-3
  lengths agree; arbitrary scaling linear over the forced phase at 1e-9; maxima finite and ≥ 0,
  histories finite, gaps engaged in ~65 % of examples; JC with `fluidArea = 0` ≡ lumped within
  1e-12 (summary, history, `free_decay_samples`), MoC path in ~85 % of examples. Two model facts
  the properties surfaced and record as events rather than failures: (1) when the transit delay
  is below half a sub-step (`CLng(unb · stepQTY) = 0`, `kOverlap = 0`) `forceA ≡ forceB` and the
  response is identically zero (quantised delay, VBA behaviour); (2) the free-decay length is
  amplitude-dependent through the absolute D-21 threshold `x · xZero > 0.01`, so the summary
  maxima of a scaled load are only bitwise-scaled when both runs integrate the same number of
  phase-3 samples (14 % of examples differ).
- Bench (`tools/bench.py --profile --skip-full-python`, three modes, `docs/bench/b9597a3.json`,
  README "Stage 5 runs" section). The container was restarted mid-stage (a first full run was
  lost in the python-mode full JC case; its literal and Numba medians, at 2.10 GHz, are quoted
  in brackets below), and the new container is a slower Intel Xeon @ 2.80 GHz: every pure-Python
  case runs at ~0.55x of `b5fc5c7`, so only the in-session ratios are comparable. Digests: all
  eight refactored/literal pairs equal in both modes, every case `same` as `b5fc5c7`.

  | implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | (d) pressure | jc r96 full | jc r97 full | jc r98 full |
  |---|---|---|---|---|---|---|---|
  | literal | 3.839 s [1.00] (2.20) | 3.877 s [1.01] | 178.4 s [46.5] (100.0) | 11.5 ms | - | - | - |
  | refactored, pure Python | 1.332 s [0.35] (0.73) | 1.237 s [0.32] | 99.1 s [25.8] (51.8) | 8.3 ms | - (skipped; ~15 min each) | - | - |
  | Numba, steady state | 0.309 s [0.081] (0.200) | 0.344 s [0.090] | **0.179 s [0.047]** (0.083) | 8.5 ms | 2.13 s [0.56] (1.23) | 2.08 s (1.07) | 1.94 s (0.80) |

  Speed-ups vs the literal port: lumped 12x (3.8x vs the pure-Python refactor), truncated JC
  **1000x** (550x vs the refactor); MoC cell-updates/s 0.30 M → 0.54 M → **300 M**. Full JC golden
  cases ~2 s each (969 / 856 / 800 s in pure Python at 293e507), max rel err vs Excel 8.6e-13 /
  2.1e-14 / 8.4e-15 (unchanged). Compile: 3.36 s for `_integrate_kernel` + callees in a fresh
  `NUMBA_CACHE_DIR` (1.25 s on the 2.10 GHz container); first calls per case 0.17-2.2 s (cache
  warm in the process). Peak RSS of an `outputType = 1` run on the full history under Numba:
  lumped r20 210 MB, JC r96 191 MB (includes the compiler's footprint). Profile (python mode):
  `moc.step` is 99 % of (g); in Numba mode the lumped case is ~75 % `loads.unbalance_force`
  (Python generator), see Next action. **The full run (pure-Python full JC cases included) was
  attempted twice and lost twice to container restarts, both times inside the python-mode full
  JC case (~15 min each); nothing of it is written until the end.** The two partial logs agree
  with the committed record to within noise (literal (c) 173-178 s, Numba (g) 0.166-0.179 s, full
  JC 1.8-2.2 s). The pure-Python full-JC row therefore comes from the owner's local reference
  run; the Stage 4.2 measurement of the same cases (969 / 856 / 800 s at 2.80 GHz, sequential
  in parallel processes) is in the JC golden table of `docs/bench/README.md`. Stage 5b item: let
  the bench write partial JSON per worker so a killed run keeps its finished sections.
- Port review (`port-reviewer` on `git diff b5fc5c7`, diff + VBA only, ran concurrently with the
  first part of the bench): **no correctness findings**. It checked `_integrate_kernel`
  operation-for-operation against the Stage 4 loop (coupling before the step with the previous
  `a`, `d_f + f` order, the `n + off` parity in all three phases incl. the phase-3 `+ 1`, the
  trackers, `_record`, the `tot_ind <= out_max * 2` guard, `x_zero = 0.0` vs the old int `0`),
  `step_scalars` as the old `step` body verbatim, `moc.step` decorator-only, the flattening
  (truncated last delay sample kept; D-7/D-8 still raised, now inside `list(forces)`), per-file
  `def test_` counts identical to the baseline, no fixture / legacy / frozen-module change, the
  D-9/D-14/D-23 wording, and ran its own short bitwise check (random JC case with the legacy
  flags and a lumped case, output types 0-3, two gap/ratio settings, a 2-D history) in both
  modes: all bitwise. Three non-correctness notes, applied: (1) the decision-A sentence in the
  plan above now says the Python-mode `FloatingPointError` came from the Stage 4 `errstate`
  block; (2) D-14/D-23 now say a fluid overflow *normally* reaches the structure state and raises
  at the end (an overflow at a far node in a run that ends before it reaches the pivots would
  return finite values silently, where Stage 4 raised at the first overflowing op; non-physical
  inputs only); (3) a bare `pytest` after editing `moc.py` can test a stale compiled
  `_integrate_kernel` (Numba's documented cache limitation): `make test-both` wipes the cache,
  README and architecture.md say so; a CLAUDE.md line is for the owner to add.

## Stage 4.1 — scope and plan (recorded 2026-10-21 before touching `src/`)
Owner's instruction: refactor, first seam. Target layout for all of Stage 4 is in
`docs/architecture.md` (one line per module, responsibilities and what each must not know).
This session builds `structure.py`, `loads.py`, `coupling.py` (`NoCoupling` only) and the
lumped path of `response.py`; `moc.py`, the JC coupling and `pressure.py` are later sessions.
`legacy_port.py` is frozen and stays the reference until Stage 6.

Plan (one commit per module; fast + slow golden gates and the differential suite green before each):
1. `structure.py`: `solve_poly` (copied literally so the module survives the Stage 6 removal of
   `legacy_port`), `solve_portal_height`, `lumped_params`, `restoring_force(x, k, gap, ratio)`,
   `step(state, f_applied, params, dt)` on Python floats with the `minUnsigned` / `max(0, …)` /
   `sign` ladders inlined. Tests: `tests/test_differential.py` replays the legacy solver's
   per-sub-step `(f, x, v, a)` sequence (read through a `sys.settrace` probe, as
   `test_quirks.py` does; `legacy_port.py` untouched) through `step` and compares bitwise.
2. `loads.py`: `transit_delay`, `unbalance_force(history, sample_freq, length, celerity, step_qty)`
   yielding one list of per-sub-step `forceA − forceB` per sample, reproducing the delay phase
   (`forceA` held, mid-sample `Exit For`), the ramp phase with the `kOverlap` split and the
   column-major walk with the `jB > U2` clamp. Tested against the `(forceA − forceB)` sequence
   the literal port computes (same probe).
3. `response.py` + `coupling.py`: `peak_response(...)` = set-up (structure) + loads + one shared
   integration loop with `NoCoupling`; returns `PeakResponse`. Differential against
   `get_peak_response` for `outputType` 0–3 on the Example-sheet lumped case (fast), the 75
   curve cases (`slow`) and the seeded sweep.
4. `tools/bench.py`: two extra cases (`peak_response` on rows 20 and 80); run, commit `docs/bench/`,
   report the pure-Python speedup of the lumped cases. `port-reviewer` on the final diff.

Sweep design (`tests/test_differential.py`, 50 parameter sets, `random.Random(20261019)`, rtol 1e-12):
covers what the Excel oracle does not (port_review §4): `restrainFreqRatio` U(0.5, 4); `gap` =
U(0.1, 0.5) × the case's own gap-free `xMax`; `outputType` 0 always plus one of 1–3 per case;
1-D histories and 2-D with 2–3 columns (column-major); `stepQTY` ∈ {2, 7, 40}; `dynamicFric` ∈
{0, 0.005, 0.1}; `dampingPercent` U(0.5, 5) (phase 3 must terminate); `ω·dt` ≤ 0.03 so the
explicit scheme stays stable; piecewise-constant random force levels scaled to `F/k` ~ 0.05–1 so
the free-decay threshold `|x| > 0.1` is reachable; rows ≥ 2 × columns so the phase-1 walk cannot
hit D-8. Asserted: ≥ 1 case enters phase 3 (`free_decay_samples > 0`) and ≥ 1 engages the gap
(`max_displacement > gap`).

Judgement calls (flag if you disagree):
- `unbalance_force` yields per *sample* a list of the per-sub-step values rather than a flat
  per-sub-step stream, because the caller must act at sample boundaries (result history, the
  phase-1 `Exit For` truncates the last delay-phase sample). Flattened, it is exactly the
  per-sub-step sequence the test compares.
- `peak_response` runs on Python floats, so overflow no longer raises `FloatingPointError`
  mid-run as the numpy state did (D-14); it raises `FloatingPointError` at the end if the final
  state is not finite (nan/inf are absorbing in the update). Recorded as D-23 with a pin test.
- `NoCoupling` adds `0.0` to the unbalance force and supplies `0.0` in free decay: identical to
  the literal `(forceA − forceB)` / `−R` except for the sign of an exact zero.

## Stage 4.4 — scope and plan (recorded 2026-10-22 before touching `src/`)
Owner's instruction: hygiene, no behaviour changes. (1) dead code in the Stage 4 modules; (2)
numpy-style docstrings with units and DEVIATIONS ids; (3) `docs/architecture.md` as built with a
data-flow paragraph per path; (4) `README.md`; (5) DEVIATIONS sorted, pinning tests checked,
legacy-only rows marked; (6) ruff with SIM and C4. Gates before each commit: fast suite, `-m slow`,
differential bitwise; `port-reviewer` on the final diff; next action Stage 5.
Plan as executed: one commit per item in the order 6+1 (lint rules and the one duplication), 2,
3, 4, 5, then bench, review, NOTES.

## Stage 4.4 — done (2026-10-22)
- Dead-code census (every public and private name of `structure`, `loads`, `coupling`, `moc`,
  `response`, `pressure` grepped over src, tests, tools): **nothing uncalled**.
  `structure.restoring_force`, `JunctionCoupling.column()` and the `pressure.get_pressure_response`
  alias are used only by the suite or the bench but are part of the fixed interfaces (the alias was
  an owner amendment in 4.3) and stay. No duplicated phase exists in the new modules; the one
  duplication, the per-sample history-write switch repeated in the forced and free-decay phases
  of `response._integrate`, is now `_record` (called once per sample, so no bench cost).
- Lint: `pyproject.toml` selects SIM and C4; `legacy_port.py` and `vba_compat.py` are exempt
  (per-file ignores). Findings fixed: SIM300 in `structure.py` (`0 > excess` → `excess < 0`,
  identical for every double incl. NaN), SIM300 in `test_quirks.py`, 17 C408 `dict()` literals in
  tests and `tools/bench.py`. `ruff check . && ruff format --check .` clean.
- Docstrings: numpy-style on every public function and dataclass of the six modules (43
  docstrings replaced or added by an AST-positioned script; the code AST with docstrings stripped
  is identical before and after). Units on every physical argument and return (m, s, N, kg/m,
  Pa, Pa·s/m, m³/h, mm², bar, …); each preserved quirk names its DEVIATIONS id.
- `docs/architecture.md`: title "as built", `response.py` row names `_integrate` / `_record` /
  `_decay_test`, new "Data flow for one sub-step" (lumped, JC, and a line for pressure), private
  helpers listed as non-interfaces, Stage 4.4 exactness note, lint policy section.
- `README.md`: package, install, the three entry points with units, the Example-sheet lumped
  worked example (Python vs Excel: 2.5e-14 / 2.5e-14 / 2.8e-14 / 2.5e-14 / 0), the fast / slow /
  jc_slow suites, `tools/bench.py`, pointers to DEVIATIONS.md, docs/port_review.md,
  docs/architecture.md, NOTES.md.
- DEVIATIONS.md: already sorted (D-1 .. D-23); every pinning-test reference resolves to a
  collected test (checked by script against `pytest --collect-only` over all markers, 0 missing).
  Rows whose VBA behaviour is now reachable only through `legacy_port.py` are marked in the
  Python-location column: D-3, D-5, D-12 (lumped garbage array), D-14 (mid-run raise of the
  lumped numpy state) and D-16. D-17 / D-19 stay reachable through the legacy flags.
- Gates: fast suite 732 passed and `-m slow` 150 passed before each `src/` commit; the
  differential suite (part of both) stayed bitwise.
- Bench (`tools/bench.py`, this container): `docs/bench/3912479.json`, README row (Intel Xeon @ 2.10 GHz, pure Python; a port-review agent was reading files concurrently, so timings are indicative only). Every case's result digest reads `same` and the four refactored/literal digest pairs are equal (exit 0). Medians: (a) lumped r20 2.055 s, (b) 2.131 s, (e) `peak_response` r20 0.740 s [0.36 of (a)], (f) 0.679 s [0.33], (c) legacy JC n2000 98.3 s, (g) `peak_response_jc` 51.1 s [1.05 M cells/s], (d) pressure 6.20 ms, (h) 4.55 ms. Within noise of 6fa4595 (0.90x-1.18x vs prev), as expected for a no-behaviour-change session.
- Port review (`port-reviewer` on the Stage 4.4 diff, diff + VBA only): **no correctness findings**. It verified the `excess < 0` rewrite against VBA lines 11-17 for every double incl. NaN and signed zero, `_record` against the base version and the VBA guards (450, 597-598), that no test, fixture or frozen module changed (per-file `def test_` counts and skip/xfail/tolerance marker counts identical), that every `dict()` literal conversion kept key order (the seeded sweeps are unchanged), that the README example reproduces digit for digit, and the VBA line references and D-ids of the new docstrings. One documentation note: the `effective_displacement` Notes had the VBA line labels of `max`/`minUnsigned`/`sign` swapped; fixed in the follow-up commit (`max` 11-17, `minUnsigned` 19-33, `sign` 51-59).

## Stage 4.3 — scope and plan (recorded 2026-10-21 before touching `src/`)
Owner's instruction: `pressure.py` as a standalone driver against the architecture row; differential
against `legacy_port.get_pressure_response` on the Example-sheet case (Excel at 1e-12) and a seeded
sweep covering port_review §4 item 1; the two half-loops' clamp asymmetry (0.9 vs 0.9·rhoC, D-6)
stays literal. Amendments at plan approval ("go", 2026-10-21): (1) the public function is
`pressure_response(...)` to match `response.py`; `get_pressure_response` stays as a thin alias so
legacy-signature callers and the bench case (d) keep working; the architecture row is updated;
(2) sweep ranges as proposed (below); (3) the VBA `min`/`max` tie semantics (`If a < b Then a Else
b`: ties and NaN return the second argument) live in one place that survives the Stage 6 removal
of `legacy_port.py`: a new `src/surge_sdof/_vba_semantics.py` (`vba_min`, `vba_max`), not in
`pressure.py`; `docs/architecture.md` notes that `vba_compat.py` is frozen and `_vba_semantics.py`
is the live home for VBA tie/NaN semantics. (The plan text itself was lost with a worker restart;
this section is its reconstruction from the owner's amendments, the Stage 4.2 pattern and the
Next action recorded below.)

Plan (fast suite before each commit, `-m slow` before the `src/` commit):
1. `_vba_semantics.py`: `vba_min`, `vba_max` (literal `legacy_port.min/max`). Tests: ties and NaN
   return the second argument, `-0.0`/`0.0` tie, equality with `lp.min/max` on a seeded sweep.
2. `pressure.py`: set-up once per run (`setup` → `PressureSetup`: `outMax`, `pipeSegQTY`
   (`grid_size`, VBA 207, D-22 truncation), `factor`, `rhoC`, `velocityInitial`, `valveLoss`,
   `valveDPInitial`, `pipeLoss`; `initial_column` → four contiguous arrays `p_a, v_a, p_b, v_b`
   of length `N + 1`, VBA 222-227, and `velAtPump`), `valve_closure` (the column-major pattern
   walk with the `jB > U2` clamp and linear interpolation, VBA 244-265, on the 0-based 2-D pattern
   from `loads.as_history_2d`), `valve_boundary` (VBA 267-273, the fully-closed branch at
   `closure >= 0.999999999`), `pump_boundary` (VBA 287-288), `half_step_a_from_b` (VBA 275-285,
   clamp `0.9`) and `half_step_b_from_a` (VBA 290-300, clamp `0.9 * rhoC`): scalar loop bodies
   over the arrays, `sysMat` as two locals, VBA operation order; `pressure_response` drives them
   under `np.errstate(raise)` (the arrays are numpy, as in the legacy, so `rhoC = 0` and overflow
   raise as before) and returns the 0-based `resultArray(0 To outMax)` unchanged.
   `get_pressure_response(...)` forwards to it.
3. Differential tests (`tests/test_differential.py`, new section): set-up constants vs the legacy
   locals (settrace probe at the main loop), `pressure_response` vs legacy on the Example case
   (and vs Excel at 1e-12), on a 50-case seeded sweep (`random.Random(20261019)`, rtol 1e-12,
   bitwise expected and recorded), 1-D ≡ column, alias identity.
   Sweep ranges: closureTime U(0.2, 3) s with 20-300 result steps (`timeStep = closureTime /
   steps`); celerity U(900, 1500); density {850, 1000, 1100}; pressureDropFromPump 0 (1 in 5)
   or U(0.01, 2) bar; flowRate 10^U(0.3, 3.3) m³/h (low flows make the `0.9` clamp saturate);
   pipe ID U(50, 600) mm (`pipeArea = pi·ID²/4`); valveCv U(100, 5000); lengthToPump U(5, 2000) m
   (long pipes trigger the `outMax` truncation); pumpRampPressure 0 (3 in 10) or U(0.5, 5) bar;
   valve patterns of 3-40 samples, 1 column (1 in 2) or 2-3 columns (column-major), shapes
   linear / smoothstep / early-close-then-plateau / stepped, end value exactly 1.0 (1 in 2, the
   fully-closed branch) or U(0.3, 0.99). Asserted coverage: fully-closed steps, `outMax`
   truncation, zero and non-zero pump ramp, zero pipe loss, 1-D and 2-D patterns, saturation of
   the `0.9` clamp (counted through the probe); the `0.9·rhoC` clamp is expected never to
   saturate (port_review §1.4) and the count is recorded, not asserted.
4. Bench: case (h) `response_pressure_example` (`pressure.pressure_response`, digest must equal
   (d)); README column added, earlier rows get `-`. `docs/architecture.md` (pressure and
   `_vba_semantics` rows, interface, exactness note), DEVIATIONS D-6/D-22 Python locations.
5. `port-reviewer` on the final diff; NOTES done section; next action.

## Stage 4.3 — done (2026-10-21)
Commits `bbc8f6a` (scope), `5df78fd` (`pressure.py`, `_vba_semantics.py`, tests), `6fa4595` (docs, bench
case (h)). `legacy_port.py`, `vba_compat.py`, `tests/fixtures/`, `legacy/` untouched.
- `pressure.pressure_response(...)`: the valve/pump MoC driver from the Stage 4 layout; `get_pressure_response`
  is a thin legacy-signature alias (bench case (d) and any legacy caller keep working). D-6 clamp asymmetry
  and D-22 truncation kept literal. `_vba_semantics.vba_min/vba_max` hold the VBA tie rule (second argument on
  ties and NaN) in one place that survives the Stage 6 removal of `legacy_port.py`.
- Differential results (`tests/test_differential.py`, pressure section, 50 seeded cases + Example): set-up
  constants identical to the legacy locals in all 50 cases; `pressure_response` **bitwise identical** to
  `legacy_port.get_pressure_response` in 49 of 50 sweep cases and on the Example case (which also matches
  Excel at 1e-12); the 50th case (`p24_c2_smooth_closed`) overflows inside the legacy MoC (`FloatingPointError`
  under `np.errstate(raise)`, second half-loop) and the refactor raises the same exception, asserted as such.
  Sweep coverage: 20 cases take the fully-closed valve branch, 10 hit the `outMax` pipe truncation, 12 have
  zero pump ramp, 9 zero pipe loss, patterns with 1-3 columns. Lumped golden gate (`-m slow`) run before the
  `src/` commit: 75 pass. Fast suite 732 passed (≈ 33 s).
- Finding (recorded in DEVIATIONS D-6): **both** friction clamps saturate in the sweep. The `0.9` clamp bites
  at low flow (12 cases, 8141 cell updates). The `0.9·rhoC` clamp, which port_review §1.4 expected to be
  effectively absent, bites in 2 cases (1095 cell updates): the loss term is `|v|·pipeLoss / (rhoC·velInitLocal²)`
  and `velInitLocal = (1 + 2i)·pipeLoss/rhoC + velocityInitial` passes through zero along the pipe when the
  pressure drop is large relative to the flow, making the friction term singular there. A modelling quirk of
  the VBA (preserved); worth raising with the lead author alongside D-17/D-18.
- Port review (`port-reviewer`, diff `bbc8f6a..6fa4595`, diff + VBA only): **no correctness findings**; it
  independently confirmed bitwise equality on the 49 non-raising sweep cases and the Example case. Its two
  notes were applied: the `pressure.py` docstring now says the suite pins rtol 1e-12 and bitwise is the
  measured result; `tools/bench.py` now checks the paired digests in-run (`DIGEST_PAIRS`, exit 1 on mismatch).
- Bench (`tools/bench.py` on `6fa4595`, `docs/bench/6fa4595.json`, README row): every previous case's digest
  reads `same`; new case (h) `response_pressure_example` 4.70 ms vs (d) `pressure_example` 6.18 ms (0.76x, ratio
  to (a) 0.003 for both), digests of all four refactored/literal pairs identical. Run time 8 min.
- Judgement calls: the sweep's one overflowing case is kept as a "raises identically" differential rather than
  tuned away; `pressure_response` returns the plain 0-based array (no dataclass) because the legacy result was
  already 0-based and the bench/golden consumers index it directly.

## Stage 4.2 — scope and plan (recorded 2026-10-21 before touching `src/`)
Owner's instruction (this session): `moc.py`, `coupling.JunctionCoupling`, `response.peak_response_jc`
built from the same `_integrate` loop as `peak_response`; approved fixes F-1 and F-2 flag-first.
Amendments agreed at plan approval: (1) the `jc_slow` gate runs the new solver with the legacy
flags against the Excel fixture at the golden tolerance only (no re-run of
`legacy_port.get_peak_response_jc` on the full cases; bitwise-vs-legacy is established by the
small-grid sweep); (2) the golden before/after record is one fixed-flag run per case (F-2 is
provably zero there: `k_exit = 21` odd, phase 3 never entered).

Plan (one commit per step; fast suite before each commit, `-m slow` before each `src/` commit):
1. `moc.py`: set-up helpers called once per run (`grid_size`, `is_short_pipe`, `decay_factor`,
   `interp_fractions` as float64 arrays, literal copies of `interpFractionA/B` incl. D-4,
   `new_column`) and one kernel `step(even, a_dt, p_a, v_a, p_b, v_b, frac_a, frac_b, n_seg,
   pivot, rho_c, decay, vav_divisor, fluid_area, d_f) -> d_f` with scalar loop bodies over four
   contiguous 1-D arrays, VBA operation order, previous-cell values carried in locals; no Python
   objects (Stage 5 `@njit`s it whole). The dead `useUndamped` branch is not ported.
   Tests: fractions bitwise vs the legacy helpers; chained replay of the legacy MoC block
   (settrace probe: arrays, `d_f`, `a` per sub-step) on small grids, bitwise.
2. `coupling.py`: `JunctionCoupling` owning the column arrays and `dF`;
   `coupling_force(state, step_index)` = `moc.step(step_index % 2 == 0, a * dt, …)`, returns a
   Python float. Test: `dF` sequence vs the legacy's per-sub-step `d_f`.
3. `response.py` + `structure.jc_params` (VBA 726-729 literally; its own function, not a flag
   on `lumped_params`): `peak_response_jc(...)` with keyword-only `vav_denominator`
   ("legacy" 2N-1 | "fixed" 2N+1) and `parity` ("per_phase" | "running"), short-pipe fallback to
   `peak_response`, otherwise the shared `_integrate` under `np.errstate(raise)` (the MoC arrays
   are numpy; `rhoC = 0` and fluid overflow raise mid-run as the legacy does). Parity lives in the
   loop: with `parity="per_phase"` `_integrate` passes the VBA index `(totInd-1)*stepQTY + k`
   (phase 3 `+1`) as `step_index`; with `"running"` the running counter. Tests: Example JC case
   vs legacy (output types 0-3) at 1e-12 and vs Excel; fallback ≡ `peak_response` bitwise;
   three `jc_slow` tests (new solver, legacy flags, vs Excel at 5e-12).
4. Sweep: 50 JC parameter sets (`random.Random(20261019)`), fluidArea {0, 0.01, 0.05}, density
   1000, stepQTY {2, 7, 40}, ratio U(0.5, 4), engaged gaps, 1-D and 2-3 column histories,
   outputType 0 plus one of 1-3, fallback spans; asserted ≥ 1 phase-3 case, ≥ 1 fallback, ≥ 1
   MoC case with the gap engaged. Compared with explicit legacy flags at rtol 1e-12 (bitwise
   measured and recorded). Grids of ~20-40 cells so the fast suite grows by ~30 s.
5. Flag flip: defaults "fixed" / "running"; pin tests for the fixed behaviour on the new
   modules (the `test_quirks.py` pins on `legacy_port` stay as written); DEVIATIONS D-17 and
   D-19 → "fixed"; max relative change per sweep case (F-1 alone, F-2 alone, both) and per
   golden output recorded here and in the commit message.
6. Bench: `tools/bench.py` re-runs case (a) in-session as the reference and reports every case
   as seconds and as a ratio to (a); new case (g) `response.peak_response_jc` (legacy flags) on
   the truncated row 96 (digest must equal (c)); cell-updates/s for (c) and (g) (sub-steps ×
   pipeSegQTY / s); README rows carry the CPU model; rows go into the main table.
7. `-m jc_slow` once with the legacy flags (3 parallel single-case processes); per-case time and
   max relative error recorded. `port-reviewer` on the final diff; correctness findings only.
   Next action = Stage 4.3 (`pressure.py`).

## Stage 4.2 — done (2026-10-21)
- Modules (see `docs/architecture.md`): `moc.py` (grid set-up, tabulated interp fractions,
  four contiguous 1-D state arrays, one `step` kernel with scalar loop bodies; the dead
  `useUndamped` branch is not ported), `coupling.JunctionCoupling` (owns the column and `dF`;
  `coupling_force(state, step_index)` = `moc.step` on the half-grid `step_index % 2` selects),
  `structure.jc_params` (VBA 726-729 literally), `response.peak_response_jc` (JC set-up,
  short-pipe fallback to `peak_response`, the shared `_integrate` under `np.errstate(raise)`).
  The F-2 parity choice lives in `_integrate`: `step_index = n + off`, `off = 0` for the running
  counter, or the VBA per-phase offset fixed per sample (`(totInd-1)*s - n`, phase 3 `+1`).
- Differential suite (`tests/test_differential.py`, rtol 1e-12, legacy flags
  `vav_denominator="legacy", parity="per_phase"`): MoC replay on four small grids (5117 sub-steps,
  arrays and `dF` **bitwise**), `JunctionCoupling` `dF` sequence (bitwise), `peak_response_jc` on
  the small cases for output types 0-3 (16/16 bitwise), the Example JC case vs Excel (1e-12; it
  enters phase 3), the JC sweep (50 sets, seed 20261019; 10 fallback cases, 8 phase-3 cases of
  which 2 on the MoC path, 27 of 40 MoC cases with a discontinuous literal parity at 1→2):
  **100/100 comparisons bitwise** (summary and history). Fast suite 625 tests, 40 s (was 8 s:
  the JC sweep costs ~12 s, the flip pins ~14 s).
- Flag flip: defaults are now `vav_denominator="fixed"`, `parity="running"`; the legacy flags
  are pinned bitwise on the sweep (`test_legacy_flags_reproduce_legacy_bitwise`), the fixed
  behaviour by `test_fixed_vav_divides_by_the_number_of_terms`,
  `test_running_parity_is_continuous_across_phase_boundaries` (half-grid sequence recorded
  through `moc.step` on the D-19 case: strictly alternating; `"per_phase"` equals the legacy
  `modDbl` sequence) and `test_fixed_flags_change_only_where_expected`. DEVIATIONS D-17 and D-19
  are "fixed"; the `test_quirks.py` pins on `legacy_port` are untouched (the literal port keeps
  the quirks).
- Port review (Stage 4.2): `port-reviewer` on `git diff 5241908..293e507` (diff + VBA only):
  **no correctness findings**. It checked `moc.step` expression by expression against VBA
  795-847 (summation order of `vAv`, boundary order, sweep bounds and the `pb_prev` locals, the
  `dF` association), the tabulated fraction index ranges, `jc_params` association against VBA
  726-729, the `n + off` parity index for all three phases including the phase-1 `Exit For` and
  phase 3's `k = 1 To stepQTY`, the set-up/fallback order and the `dF + (forceA − forceB)`
  summation, and that no test was deleted, skipped or loosened and no fixture or legacy file is
  in the diff. One coverage note (not a finding): the bitwise pin of the legacy flags covers
  output type 0; histories are compared at rtol 1e-12 by the sweep fixture (observed bitwise).
- Bench (`docs/bench/293e507.json`, README row; `tools/bench.py --profile`, this container, pure
  Python, Intel Xeon @ 2.80 GHz, nothing else running). `tools/bench.py` now always re-runs the
  frozen legacy lumped case (a) in-session as the reference (also under `--only`) and reports
  every case in seconds and as a ratio to (a); JC cases also report cell-updates/s
  (sub-steps × pipeSegQTY / s); README rows carry the CPU model and are inserted into the main
  table (the stray 4ea09d2 row that had landed under the JC table was moved up).

  | case | median | × (a) | per sub-step | cells/s | result |
  |---|---|---|---|---|---|
  | (a) legacy lumped r20 | 3.195 s | 1.000 | 3.18 µs | - | same as 4ea09d2 |
  | (b) legacy lumped r80 | 3.132 s | 0.980 | 3.11 µs | - | same |
  | (e) `peak_response` r20 | 0.995 s | 0.312 | 0.99 µs | - | same |
  | (f) `peak_response` r80 | 0.933 s | 0.292 | 0.93 µs | - | same |
  | (c) legacy JC r96, 2000 samples (N 666) | 147.04 s | 46.0 | 1816 µs | 0.37 M | same |
  | (g) `peak_response_jc` r96, 2000 samples, legacy flags | 77.06 s | 24.1 | 952 µs | 0.70 M | digest equal to (c) |
  | (d) pressure example | 10.7 ms | 0.003 | - | - | same |

  **Truncated JC case (c) → (g): 1.91x from the restructure alone** (tabulated fractions, four
  1-D arrays with the previous cell carried in locals, hoisted `a·dt` and `2·rhoC`, Python-float
  SDOF state; no vectorisation, no JIT). Profile of (g): `moc.step` self 80.5 s of 81.3 s (99 %),
  `_integrate` 0.22 s, `structure.step` 0.23 s, `coupling_force` 0.17 s — the remaining cost is
  numpy element access and numpy-scalar arithmetic inside the cell sweeps, which is exactly what
  the Stage 5 `@njit` of `moc.step` removes. In the legacy (c) the two `interp_fraction` helpers
  alone were 25.5 s of 197.7 s profiled.
- JC golden gate (`pytest -m jc_slow -k peak_response_jc_matches_excel_on_the_golden_curve`,
  the new solver with the legacy flags against the Excel fixture at 5e-12, three single-case
  processes in parallel on 4 cores, pure Python; the literal-port golden tests were not re-run,
  owner's decision): 3/3 pass.

  | row | f (Hz) | N | time (s) | max rel err | per output (static-eq / x / v / a / F) |
  |---|---|---|---|---|---|
  | 96 | 3 | 666 | 969 | 8.6e-13 | 7.5e-13 / 7.5e-13 / 8.6e-13 / 2.0e-13 / 0 |
  | 97 | 7.5 | 592 | 856 | 2.1e-14 | 2.1e-14 / 2.1e-14 / 1.8e-14 / 1.5e-14 / 0 |
  | 98 | 22 | 546 | 800 | 8.4e-15 | 8.4e-15 / 8.4e-15 / 2.7e-15 / 6.5e-15 / 0 |

  The errors are the literal port's to the digits shown (484b25e: 8.6e-13 / 2.1e-14 / 8.4e-15),
  as the bitwise sweep predicts. Legacy times for comparison, sequential: 1827 / 1565 / 1412 s.

### Stage 4.2 — F-1/F-2 before/after
**Finding (not the expected 0.4 %): F-1 is numerically inert for the outputs.** `dF` is built
from pressures; pressures are built from velocity *differences* between neighbouring cells;
`vAv` is subtracted from every velocity of the column uniformly (end nodes included). The
divisor therefore cannot reach `dF` except through rounding: on the sweep F-1 alone changes
results by ≤ 3e-15 (0 on 31 cases), on the golden cases by ≤ 1e-14. The fix corrects the
column's mean-velocity bookkeeping (the velocities themselves do shift), not the force on the
structure. F-2 acts where the literal parity sequence is discontinuous on a fluid-coupled MoC
case: 2e-4 to 1e-2 on the sweep; provably zero on the golden cases (`k_exit = 21` odd with
`stepQTY = 40`, phase 3 never entered), confirmed by the fixed-flag runs below.

Golden JC cases, `peak_response_jc` with the defaults (F-1 and F-2 on) vs the Excel fixture
(= the legacy result to 8.6e-13), relative change per output
(static-eq. force / displacement / velocity / acceleration / applied force), one run per case:

| row | f (Hz) | N | time, fixed flags (s, 4 processes sharing 4 cores) | fixed flags vs Excel | legacy vs Excel (golden run 484b25e) | fixed vs legacy (cached `tests/.golden_cache`) |
|---|---|---|---|---|---|---|
| 96 | 3 | 666 | 975 | 7.4e-13 / 7.4e-13 / 8.6e-13 / 2.0e-13 / 0 | 7.5e-13 / 7.5e-13 / 8.6e-13 / 2.0e-13 / 0 | 1.2e-16 / 1.2e-16 / 9.5e-16 / 3.6e-16 / 0 |
| 97 | 7.5 | 592 | 876 | 2.1e-14 / 2.1e-14 / 1.9e-14 / 1.5e-14 / 0 | 2.1e-14 / 2.1e-14 / 1.8e-14 / 1.5e-14 / 0 | 0 / 0 / 3.7e-16 / 2.4e-16 / 0 |
| 98 | 22 | 546 | 799 | -8.6e-15 / -8.5e-15 / -2.5e-15 / -6.0e-15 / 0 | -8.4e-15 / -8.4e-15 / -2.7e-15 / -6.5e-15 / 0 | 1.9e-16 / 1.4e-16 / 1.8e-16 / 4.2e-16 / 0 |

Max relative change on the golden cases: **9.5e-16** (row 96, max velocity): F-2 is zero by
construction there and F-1 is rounding-level (see the finding above). All three stay inside
the golden tolerance 5e-12 with the defaults.

JC sweep, output type 0, max relative change over the five outputs vs the legacy flags
(F-1 alone = `("fixed", "per_phase")`, F-2 alone = `("legacy", "running")`, both = defaults):

| case | fluidArea | fallback | k_exit | 1→2 continuous | phase 3 | F-1 alone | F-2 alone | both |
|---|---|---|---|---|---|---|---|---|
| j00_q40_A0.05_N28 | 0.05 | - | 16 | no | - | 4.4e-16 | 2.2e-03 | 2.2e-03 |
| j01_q7_A0.05_N28 | 0.05 | - | 2 | yes | - | 3.5e-16 | 0 | 3.5e-16 |
| j02_q7_A0.01_N30 | 0.01 | - | 1 | no | - | 4.3e-16 | 1.7e-04 | 1.7e-04 |
| j03_q7_A0.05_N12 | 0.05 | yes | 1 | no | - | 0 | 0 | 0 |
| j04_q40_A0.0_N18 | 0.0 | - | 8 | no | - | 0 | 0 | 0 |
| j05_q7_A0.0_N32 | 0.0 | - | 3 | no | - | 0 | 0 | 0 |
| j06_q40_A0.01_N18 | 0.01 | - | 4 | no | - | 1.2e-16 | 7.9e-04 | 7.9e-04 |
| j07_q40_A0.0_N28 | 0.0 | - | 26 | no | yes | 0 | 0 | 0 |
| j08_q2_A0.0_N36 | 0.0 | - | 1 | yes | yes | 0 | 0 | 0 |
| j09_q40_A0.0_N22 | 0.0 | - | 6 | no | - | 0 | 0 | 0 |
| j10_q2_A0.0_N24 | 0.0 | - | 0 | no | - | 0 | 0 | 0 |
| j11_q40_A0.05_N28 | 0.05 | - | 7 | yes | - | 2.6e-16 | 0 | 2.6e-16 |
| j12_q7_A0.05_N36 | 0.05 | - | 4 | yes | - | 0 | 0 | 0 |
| j13_q40_A0.01_N20 | 0.01 | - | 7 | yes | - | 2.8e-15 | 0 | 2.8e-15 |
| j14_q7_A0.01_N34 | 0.01 | - | 5 | no | yes | 1.4e-16 | 4.7e-04 | 4.7e-04 |
| j15_q2_A0.0_N12 | 0.0 | yes | 1 | yes | - | 0 | 0 | 0 |
| j16_q40_A0.0_N20 | 0.0 | - | 4 | no | - | 0 | 0 | 0 |
| j17_q40_A0.0_N34 | 0.0 | - | 2 | no | yes | 0 | 0 | 0 |
| j18_q2_A0.01_N20 | 0.01 | - | 0 | no | - | 0 | 1.4e-03 | 1.4e-03 |
| j19_q2_A0.05_N14 | 0.05 | yes | 0 | no | - | 0 | 0 | 0 |
| j20_q40_A0.05_N18 | 0.05 | yes | 0 | no | - | 0 | 0 | 0 |
| j21_q2_A0.05_N16 | 0.05 | - | 1 | yes | - | 8.7e-16 | 0 | 8.7e-16 |
| j22_q7_A0.01_N32 | 0.01 | - | 0 | yes | - | 4.9e-16 | 0 | 4.9e-16 |
| j23_q7_A0.05_N26 | 0.05 | - | 4 | yes | - | 6.1e-16 | 0 | 6.1e-16 |
| j24_q40_A0.0_N38 | 0.0 | - | 30 | no | yes | 0 | 0 | 0 |
| j25_q40_A0.05_N22 | 0.05 | - | 16 | no | - | 2.1e-16 | 4.7e-03 | 4.7e-03 |
| j26_q40_A0.05_N40 | 0.05 | - | 22 | no | - | 0 | 9.6e-03 | 9.6e-03 |
| j27_q7_A0.0_N20 | 0.0 | yes | 0 | yes | - | 0 | 0 | 0 |
| j28_q40_A0.05_N26 | 0.05 | - | 21 | yes | yes | 3.7e-16 | 0 | 3.7e-16 |
| j29_q40_A0.0_N34 | 0.0 | - | 36 | no | - | 0 | 0 | 0 |
| j30_q2_A0.01_N18 | 0.01 | yes | 1 | yes | - | 0 | 0 | 0 |
| j31_q7_A0.0_N24 | 0.0 | - | 4 | yes | yes | 0 | 0 | 0 |
| j32_q40_A0.05_N16 | 0.05 | yes | 1 | yes | - | 0 | 0 | 0 |
| j33_q40_A0.01_N28 | 0.01 | - | 15 | yes | - | 0 | 0 | 0 |
| j34_q7_A0.01_N24 | 0.01 | - | 6 | yes | - | 2.0e-16 | 0 | 2.0e-16 |
| j35_q7_A0.0_N36 | 0.0 | - | 2 | yes | - | 0 | 0 | 0 |
| j36_q40_A0.0_N22 | 0.0 | - | 11 | yes | - | 0 | 0 | 0 |
| j37_q7_A0.05_N12 | 0.05 | yes | 1 | no | - | 0 | 0 | 0 |
| j38_q40_A0.05_N48 | 0.05 | - | 7 | yes | - | 0 | 0 | 0 |
| j39_q40_A0.01_N38 | 0.01 | - | 7 | yes | - | 5.6e-16 | 0 | 5.6e-16 |
| j40_q40_A0.01_N48 | 0.01 | - | 35 | yes | yes | 0 | 0 | 0 |
| j41_q2_A0.01_N28 | 0.01 | - | 0 | no | - | 3.6e-16 | 9.8e-04 | 9.8e-04 |
| j42_q2_A0.01_N12 | 0.01 | yes | 1 | yes | - | 0 | 0 | 0 |
| j43_q40_A0.05_N42 | 0.05 | - | 5 | yes | - | 9.9e-16 | 0 | 9.9e-16 |
| j44_q40_A0.0_N18 | 0.0 | - | 10 | no | - | 0 | 0 | 0 |
| j45_q2_A0.01_N32 | 0.01 | - | 0 | no | - | 0 | 5.1e-04 | 5.1e-04 |
| j46_q7_A0.01_N30 | 0.01 | - | 6 | yes | - | 0 | 0 | 0 |
| j47_q7_A0.01_N18 | 0.01 | - | 4 | yes | - | 3.9e-16 | 0 | 3.9e-16 |
| j48_q7_A0.0_N12 | 0.0 | yes | 0 | yes | - | 0 | 0 | 0 |
| j49_q7_A0.0_N24 | 0.0 | - | 3 | no | - | 0 | 0 | 0 |


## Done
- `vba_compat.py`: `clng` (half-to-even), `vba_floor` (literal transcription of the fixed VBA `max(CLng(val - 0.5), CLng(val + 0.5) - 1)`, pinned against `math.floor`), `mod_dbl` (ordinary floored modulo now), `sign`, `min_unsigned`, `max_unsigned`, plus `ubound`/`vba_2d` for the padded 1-based array convention. `tests/test_vba_compat.py` pins them against the VBA definitions.
- Upstream `floor` fix applied: `main` merged, `vba_floor`/`mod_dbl` updated, the tests that pinned the old bug (mod_dbl table, parity test, D-11 multi-column pressure test, D-8 trigger condition) re-pinned to the fixed behaviour. DEVIATIONS D-1, D-2, D-11 are status "fixed" with the reason "source corrected upstream".
- `legacy_port.py`: `min`, `max` (shadow the built-ins on purpose, VBA tie semantics), `get_dimension`, `add_dimension`, `array_start_one` (D-3), `interp_fraction_a`, `interp_fraction_b` (D-4), `solve_poly`, `get_pressure_response` (D-6, D-11), `get_peak_response` (D-7, D-8), `get_peak_response_jc` (D-9, dead `useUndamped` branch kept behind `use_undamped = False`, short-pipe fallback). Conventions are documented in the module header.
- Tests (178 passing, `pytest -q` ≈ 5 s; run with the `.venv` interpreter, the `pytest` on PATH lacks numpy): `test_vba_compat.py`, `test_helpers.py`, `test_quirks.py` (pins for DEVIATIONS D-12 … D-21 on small synthetic inputs; reads solver locals `v_av` and the sub-step `force_b` through a `sys.settrace` probe on the solver frame, and records `mod_dbl`/`sign` calls via `monkeypatch`, so `legacy_port.py` is untouched), `test_smoke.py` (each entry point on a 100-sample step force, stepQTY = 10, all output types, 1-D and 2-D inputs, fallback, raised error paths), `test_structure.py` (gap = 0 & ratio = 1 ≡ gap = 1e9 bitwise on both peak solvers; undamped constant-force midline = F/k within 1 % on the lumped solver; JC with fluidArea = 0 ≡ lumped bitwise; column-major flattening identity on all three entry points).
- DEVIATIONS.md rows D-1 … D-11: D-1, D-2, D-11 "fixed" (upstream source fix), the rest "preserved". Rows D-12 … D-22 added from `docs/port_review.md` §3 (owner's decision, 2026-10-20): §3.1 a-e as "fixed" (Python-vs-VBA differences: complex `solvePoly` seed, no Integer/Long overflow, mixed float overflow, `pow` runtime, return-array convention), §3.2 a-f as "preserved" (`vAv` divisor, force-ramp plateau, parity discontinuity, friction dead zone, phase-3 threshold, `GetPressureResponse` 2x closure time). Every row D-12 … D-21 now has a pinning test in `tests/test_quirks.py` (D-15 golden suite, D-16/D-22 smoke tests as before). D-12 was corrected while pinning it: with numpy 2.5 the lumped solver does *not* raise for `EI < 0`; it returns a real-cast garbage array under `ComplexWarning` (only the JC path raises, a `TypeError` at `clng(complex)` in `pivotSegQTY`). §3.1-a of the review assumed a `TypeError` on both paths.
- Port review: `port-reviewer` subagent ran on `git diff 125e73e..HEAD` (diff + VBA only): **no correctness findings**. Its two non-blocking notes were applied: D-11 wording now states the even-row-count condition; the `solve_poly` complex-root edge case is listed below.
- Stage 1 close-out review (2026-10-20): `docs/port_review.md`. Two passes: the `port-reviewer` subagent on `git diff 125e73e HEAD` (no correctness findings; 4 observations) and a line-by-line read of `legacy_port.py` against the VBA. The document holds (1) the table of every VBA constant with role and unit-dependence, (2) the duplicated-code map for Stage 4 with VBA and Python line ranges (SDOF step x8, force interpolation x6, index walk x6, JC MoC block x4 byte-identical, pressure half-loops x2, shared set-up), (3) five documented-but-unrecorded port/VBA differences (complex `solvePoly` seed, Long/Integer overflow, mixed float-overflow semantics, `^` vs `**`, return-array pad) and six preserved VBA behaviours not yet in DEVIATIONS.md (`vAv` divisor 2N-1 over 2N+1 terms, force ramp over stepQTY-1 sub-steps, MoC parity index jumps at phase boundaries, `sign(v, 1e-6)` dead-zone, `x^2 > 0.01` phase-3 threshold, 2*closureTime pressure horizon), (4) the golden blind-spot list. No code changed.
- Golden fixtures (2026-10-20): the owner committed the source workbook `tests/fixtures/source/surge_force_data.xlsm`. `tools/extract_fixtures.py` (needs openpyxl, a `dev` extra) writes `tests/fixtures/curve_10in/{force_history.csv, params.json, cases.csv}` from the Excel-cached values: full `Sheet1` extent (25303 rows), `n_samples = 25135`, 78 cases with `source_row` and `solver` columns (75 lumped rows 20-94, 3 JC rows 96-98). The workbook's `Module1` was decompressed and its 16 ported procedures are byte-identical to `legacy/vba/Existing Code.bas` (fixed `floor` included), so the cached results come from the same code the port transcribes.
- Example-sheet fixtures (2026-10-21): `tools/extract_fixtures.py` also writes `tests/fixtures/example/cases.json` (three self-contained cases: `example_pressure` from B3:B7 / J33:J42 / C3:C123 with `pipeArea = PI()*(J39^2/4)` and Excel `PI()` = IEEE double pi, `example_lumped` from E3:E27 / J6:J14 / F3:F7, `example_jc` from E3:E27 / J19:J29 / G3:G7) and `tests/fixtures/manifest.json` listing both fixture sets. `test_golden.py` reads the manifest; the Example cases are unmarked fast tests (`test_golden_example`, milliseconds) at RTOL 1e-12 (owner's decision); measured 1.2e-14 / 2.8e-14 / 2.6e-15. `GetPressureResponse` thereby has its first golden case.
- `tests/test_golden.py` + `tools/golden_report.py` + markers `slow` (75 lumped) / `jc_slow` (3 JC), both excluded by default (`addopts`). `pytest -m slow` = lumped only (3 min 34 s), `pytest -m "slow or jc_slow"` = everything; `/golden` runs the latter with the 3 JC cases `--deselect`ed unless invoked as `/golden --jc`. Results are cached in `tests/.golden_cache/` (git-ignored) for `/golden`.

## Stage 4.1 — done (2026-10-21)
- Modules (see `docs/architecture.md` for responsibilities and the fixed interfaces):
  `structure.py` (`solve_poly` literal copy, `solve_portal_height`, `lumped_params`,
  `effective_displacement` / `restoring_force`, `step` on Python floats with the `minUnsigned` /
  `max(0, |x| − gap)` / `sign` ladders inlined and `dt / 2` hoisted), `loads.py` (`transit_delay`,
  `overlap_substeps`, `unbalance_force` generator: one list of per-sub-step `forceA − forceB` per
  sample, ramp fractions tabulated once), `coupling.py` (`Coupling` protocol, `NoCoupling`),
  `response.py` (`PeakResponse` dataclass, `peak_response`, shared `_integrate` loop: sample loop,
  max trackers, 0-based result history, free decay, D-23 overflow checks).
- `tests/test_differential.py`: `sys.settrace` probe on `legacy_port.get_peak_response` (set-up
  constants, per-sub-step force / pre-state / post-state); seed 20261019, 50 parameter sets
  (`stepQTY` {2, 7, 40}, 1-D and 2-/3-column histories, `dynamicFric` {0, 0.005, 0.1}, ratio
  U(0.5, 4), gap 10-50 % of the gap-free `xMax`, damping U(0.5, 5) %, ω·dt ≤ 0.03); 20 cases enter
  phase 3, 49 engage the gap (both asserted ≥ 1). Each module is compared at rtol 1e-12:
  `step` replays every legacy sub-step (49,822 sub-steps), `unbalance_force` reproduces every
  per-sample sequence, `peak_response` matches for `outputType` 0 and one of 1-3 per case, the
  Example-sheet lumped case for 0-3 (and Excel at 1e-12), and the 75 curve cases (`slow`, 0 and
  Excel at 5e-12). **Measured: bitwise equal in every comparison** (summary 50/50, histories
  50/50, Example 4/4, step and loads sequences 50/50) — the rtol is the contract, bitwise the
  observation. Error paths pinned: D-7 (`stepQTY = 1`), D-8 (single-row history), D-23.
- Three gates run before each `src/` commit: fast suite (442 tests, ≈ 8 s), `-m slow` (75 golden
  + 75 differential curve cases, ≈ 10 min). All green.
- Bench (`docs/bench/4ea09d2.json`, README row): the lumped golden cases through
  `response.peak_response` vs the literal port, pure Python, same inputs, results `same`:
  row 20 3.235 s → 0.910 s (3.22 → 0.91 µs/sub-step, **3.55x**),
  row 80 3.107 s → 0.925 s (3.08 → 0.92 µs/sub-step, **3.36x**).
  That is the speed-up from the restructure alone (Python-float state, inlined helpers, hoisted
  constants; no vectorisation, no JIT). The remaining cost per sub-step is the `step` call, the
  `coupling_force` call, the generator and the four max trackers.
  Re-timed afterwards with nothing else running (`--only`, not written): 3.24 / 3.32 s vs
  0.95 / 0.93 s, same conclusion. Profile of `response_r20` (cProfile, one run, 1,005,523
  sub-steps): `_integrate` self 1.34 s (loop, trackers, calls), `step` self 1.09 s, `abs`
  0.81 s (7.25 M calls, 7.2 per sub-step), `unbalance_force` 0.56 s cumulative, `list.append`
  0.16 s, `NoCoupling.coupling_force` 0.10 s. Next lever (Stage 5) is the JIT; in pure Python
  the remaining per-sub-step cost is call overhead, not arithmetic.
- Port review (Stage 4.1): `port-reviewer` on `git diff 08515b3..HEAD` (diff + VBA only):
  **no correctness findings**. It checked the six exactness claims (half_dt, the inlined ladders,
  the tabulated ramp fractions incl. kOverlap ∈ {0, stepQTY}, the phase-1 Exit For / jB-iB
  re-base, phase 3, the static-equivalent force) against the VBA, fuzzed the ladders and the
  dt/2 rewrite bitwise (0 mismatches), and ran its own bitwise script over the sweep, the Example
  case and constructed kOverlap edge cases for output types 0-3 (0 mismatches). One
  non-correctness note (a stale docstring reference) was fixed in the follow-up commit.

## Golden results (2026-10-20, this container, pure Python)
- Lumped, 5 timed cases (first of each span; Excel vs Python, outputType 0):

  | row | L (m) | f (Hz) | time (s) | max rel err |
  |---|---|---|---|---|
  | 20 | 3 | 2 | 2.85 | 3.4e-13 |
  | 35 | 6 | 2 | 2.87 | 9.5e-14 |
  | 50 | 12 | 2 | 2.64 | 1.2e-13 |
  | 65 | 24 | 2 | 2.74 | 1.9e-13 |
  | 80 | 48 | 2 | 2.79 | 8.4e-14 |

- Lumped, full set: 75/75 pass, 213.7 s, max rel err 8.3e-13 (row 66, max displacement), median per-case max 1.0e-13, max applied force exact everywhere. Tolerance recorded in `test_golden.py`: 5e-12 (owner's decision, ~6x margin over the observed worst).
- JC, full set (2026-10-21, `pytest -m jc_slow --durations=0`, sequential, pure Python): 3/3 pass at the provisional 1e-12.

  | row | f (Hz) | N | time | max rel err | worst output |
  |---|---|---|---|---|---|
  | 96 | 3 | 666 | 1826.8 s (30.4 min) | 8.6e-13 | max velocity |
  | 97 | 7.5 | 592 | 1564.5 s (26.1 min) | 2.1e-14 | max displacement |
  | 98 | 22 | 546 | 1411.5 s (23.5 min) | 8.4e-15 | max static equivalent force |

  Total 1 h 20 min; the Stage 4.0 extrapolation (29/26/24 min) was within 5 %. Max applied force exact in all three. JC tolerance in `test_golden.py` set to 5e-12 by the lumped rule (5x the worst 8.6e-13 = 4.3e-12, rounded up to one significant figure). Row 96 (lowest frequency, largest displacement) is the only case near the lumped worst; the other two are at 1e-14, so the MoC block, `dF`, `dacayFactor`, `vAv` and the fluid-corrected set-up (port_review §4 item 2) are now pinned by Excel.
- JC case geometry (rows 96-98, L = 24 m, stepQTY 40, 25135 samples, unballanceStepQTY = 24.546): f = 3 Hz: portalFrameHeight 4.047 m, pivotSegQTY 87, pipeSegQTY 666; f = 7.5 Hz: 2.232 m, 50, 592; f = 22 Hz: 1.104 m, 27, 546. Each case runs 1,006,382 sub-steps over pipeSegQTY cells ≈ 5.5e8-6.7e8 cell updates; measured wall times above.

## Stage 4.0 — performance baseline (2026-10-21, this container, pure Python, numba absent)
`tools/bench.py --profile` (median of 3; Intel Xeon @ 2.80 GHz, Python 3.13.16, numpy 2.5.4; full numbers and the top-15 cProfile tables in `docs/bench/1adaddd.json`):

| case | median | per sub-step | note |
|---|---|---|---|
| (a) lumped row 20 (L 3 m, f 2 Hz) | 3.09 s | 3.07 µs | golden rel err 3.4e-13 |
| (b) lumped row 80 (L 48 m, f 2 Hz) | 3.12 s | 3.10 µs | golden rel err 8.4e-14 |
| (c) JC row 96 (L 24 m, f 3 Hz, N = 666), first 2000 samples | 141.5 s | 1747 µs | 80,982 sub-steps; not a golden value |
| (d) Example-sheet `GetPressureResponse` (121 outputs) | 9.3 ms | - | matches Excel's cached `Example!C3:C123` to 1.2e-14 (now the golden case `example_pressure`) |

Sub-step count = `n·stepQTY + floor(unb·stepQTY) + 1` (verified by counting `min_unsigned` / `mod_dbl` calls). Per-sub-step cost does not depend on `n`, so the full JC golden cases extrapolate to ≈ 29 min (row 96, N 666), ≈ 26 min (row 97, N 592), ≈ 24 min (row 98, N 546) each in pure Python; confirmed by the actual run (30.4 / 26.1 / 23.5 min, see Golden results).

**Top 5 hotspots, measured (cProfile share of profiled time; real time in brackets):**
1. JC: the `get_peak_response_jc` body itself, 87 % (166 of 190 s profiled; 141.5 s real). This is the inline MoC sweeps: per sub-step ≈ 9,000 numpy element reads/writes (`array_a[m, n]`, 0.08-0.12 µs each) and ≈ 10,000 numpy-scalar arithmetic operations over N = 666 cells, plus the `vAv` reduction (2N+1 element reads and adds on even steps, ≈ 14 % of an even step). Nothing here is a function call, so cProfile cannot split it further; the split above is inferred from per-operation timings, not measured.
2. JC: `interp_fraction_a` + `interp_fraction_b`, 12 % profiled (53.9 M calls each, one per cell per sub-step; 0.14 µs/call unprofiled → ≈ 190 of 1747 µs per sub-step, 11 %). Precomputing them once per `n` (port_review §2.5) buys at most that.
3. Lumped: the `get_peak_response` body, 64 % profiled (4.6 of 7.2 s; 3.09 s real): SDOF arithmetic on numpy scalars. Experiment (bench-free, same solver, `vba_2d` monkeypatched so `force_history[i, j]` returns a Python float and the whole state stays `float`): 2.99 s → 2.01 s, 1.49x, results bitwise equal. So numpy-scalar state costs ≈ 1/3 of lumped wall time.
4. Lumped: `abs` 15 % (8.26 M calls = 8.2 per sub-step; `abs(np.float64)` is 0.13 µs vs 0.04 µs for `float`), `min_unsigned` 18 % cumulative (1 call per sub-step, 0.9 µs self), `sign` 6 % (2.9 per sub-step), `max` 2 %. Together the per-sub-step helper calls are of the same order as the numpy-scalar overhead.
5. Everything else is < 1 %: `mod_dbl`/`vba_floor`/`clng` 0.2 % of JC, `ubound` 0.7 % of lumped (`ubound(force_history, …)` is re-evaluated every sub-step), `solve_poly` 12 calls, `get_pressure_response` 9 ms total.

**Verdict on the expectation** ("`interp_fraction_a/b` and numpy-scalar arithmetic dominate"): half right. In the JC kernel the inline MoC sweeps dominate (≈ 87 %); `interp_fraction_a/b` are the only named functions that register but at ≈ 12 % they are a secondary target. Numpy-scalar arithmetic is real in both kernels (1.49x on lumped by experiment; in JC it is combined with numpy element indexing, which is of similar cost), but in the lumped kernel the call overhead of `min_unsigned`/`sign`/`max`/`abs` (≈ 13 calls per sub-step) is just as large. Any Stage 4 rewrite of these helpers must stay bit-identical (D-12 … D-21 pins in `tests/test_quirks.py`); the bench's "result vs prev" column flags a digest change.

## Findings worth knowing (all preserved, see DEVIATIONS.md)
- D-1/D-2/D-11 (historical, now fixed upstream): the original `CLng(val - 0.5)` floor made the JC MoC even-cell update run 1 step in 4 and made multi-column valve patterns extrapolate the closure at some positions. With the fixed floor the MoC alternates every step and multi-column patterns equal their column-major flattening exactly. Any Excel fixtures must be generated with the *fixed* VBA module.
- D-8: a single-row (horizontal) `forceHistory` leaves `iB = UBound(1) + 1` after the first block and fails with subscript out of range (swallowed into `#VALUE!` by JC). With the fixed floor an integer delay no longer escapes this (`kOverlap = 0`).
- The SDOF integrator evaluates `aNew` from the old `x`, `v` (explicit, not average-acceleration Newmark); with zero damping its amplitude grows ≈ 2.5 % per cycle at ω·dt ≈ 0.016 (stepQTY = 10, 5 Hz, 100 Hz samples). The cycle time-mean stays at F/k. This is why the static-deflection structure test integrates with stepQTY = 100.
- The free-decay `Do While x * xZero > 0.01` loop only runs when |x| > 0.1 (model units); for typical metre-scale displacements it never executes. If it does run with zero damping and friction it does not terminate (same in VBA).
- JC with a negligible portal-frame height (pivotSegQTY = 4) divides by zero in `interpFractionB(3)` (D-4) and the VBA returns `#VALUE!`; Python raises.
- D-12: `EI < 0` (or `L * massPerUnitLen < 0`) makes `solvePoly`'s seed complex; the lumped solver then returns a garbage real array with only a `ComplexWarning` (VBA: error 5). Non-physical input, but silent. A Stage 2+ input check would be a new behaviour and needs the owner's decision.
- D-14: `massPerUnitLen = 1e308` overflows in pure-Python set-up arithmetic and the lumped solver returns `[nan, 0, 0, 0, FMax]` without raising (VBA: error 6); overflow inside the numpy integration state raises `FloatingPointError`.

## Judgement calls made (flag if you disagree)
- Python inputs are 2-D numpy arrays with 1-based meaning (padded by `vba_2d`); 1-D arrays take the `AddDimension` path; the broken `ArrayStartOne` path is unreachable.
- VBA runtime errors: numpy arithmetic in the entry points runs under `np.errstate(divide/invalid/over = "raise")` so it raises where VBA raised; pure-Python float overflow (→ inf) and Integer/Long overflow are not emulated. `On Error GoTo ErrFound` re-raises (D-9) instead of returning an empty array.
- The implicit Double→Long assignment at VBA line 244 (`i = modDbl(...) + 1`) is written as an explicit `clng`.
- `^` is `**`: for integer exponents both call C `pow`; last-bit differences against Excel's runtime are possible and should be absorbed by the golden tolerance. `(-varA / varB) ^ (1 / 3)` would be complex in Python where VBA raises error 5; only reachable with non-physical inputs.
- Loops whose control variable is read after the loop (`jB`, `iB`) are while loops; all other `For` loops are `range` loops.

## Open issues
- Port review of V.1 (pre-existing, not introduced): `loads._schedule` (as the Stage 4
  `unbalance_force` did) reads `fh[ib][jb]` before the first phase-2 `k` loop, where the VBA
  (line 491) and `legacy_port.py` 639 only read `forceHistory(iB, jB)` inside that loop. In the
  D-8 configuration with `kOverlap = stepQTY` (first loop skipped) the VBA runs on after the
  clamped advance while the Stage 4 modules raise `IndexError`. DEVIATIONS D-8 describes the
  edge in prose but its Python column says "Identical"; a sentence there is for the owner.
- **F-1 to raise with the lead author**: the approved `vAv` divisor fix is numerically inert for
  the solver outputs (rounding level on the golden cases and the sweep) because `dF` depends on
  pressures, which depend on velocity differences only, and `vAv` shifts every velocity uniformly.
  The fix is applied as approved; whether the mean-velocity subtraction itself is the intended
  model (it only bookkeeps the column's mean velocity and never reaches the force) is a modelling
  question for the owner, not a port question.
- The fast suite is now 40 s (was 8 s before Stage 4.2): the JC sweep (~12 s) and the F-1/F-2
  pins, which run the sweep three more times (~14 s). If this matters, the pins can share the
  sweep's cached runs.
- `pytest -m jc_slow` now holds 6 tests: the 3 literal-port golden cases (80 min) and the 3
  `peak_response_jc` legacy-flag cases (~13-16 min each in pure Python).
- Two of the §3.2 items are to be raised with the lead author as more than a DEVIATIONS row (owner to name which two; the note naming them did not reach this session). §3.1-d (now D-15): Numba/LLVM lowers integer-literal `**` to multiplication, which measurably differs from C `pow` (used by both Python and numpy `**`); Stage 5 must judge this against the golden tolerance rather than expect bit-identity.
- Rows 100-101 of `curve_10in` hold pasted numbers (no formula) and were skipped by the extractor; if they are meant to be cases they need live formulas in the workbook.
- Performance: pure Python; measured baseline in the Stage 4.0 section (JC cases 23-30 min each, 1 h 20 min for `pytest -m jc_slow`). Stage 5 (Numba) target; the JC golden run is its acceptance test and now has a measured tolerance (5e-12).
- `GetPressureResponse` has a single golden case (Example sheet, 5-value pattern, single column); multi-column valve patterns and the pump/friction branches at other operating points are still unexercised by Excel data.
- Marker interpretation: "whole curve set slow" was implemented as `slow` on the 75 lumped cases and `jc_slow` (only) on the 3 JC cases, so that `pytest -m slow` excludes JC as requested.
- numba and hypothesis are permitted by `CLAUDE.md` but not added to `pyproject.toml`. oletools is a `dev` extra (approved) but no tool uses it yet; the VBA-module identity check in this session used an ad-hoc MS-OVBA decompressor that is not in the repo (`olevba` would do the same).
- The project hooks in `.claude/settings.json` load only when Claude Code is started from the repository root.

## Approved fixes (lead author, 21 Oct 2026)
Apply in the Stage 4.4 session, or earlier if Stage 4.2 builds the running step counter directly (it should: building the per-phase index only to replace it is wasted work).

Approved fixes (lead author, 21 Oct 2026):
F-1 vAv denominator: 2N+1 (number of terms), was 2N-1. port_review §3.2a.
F-2 MoC parity: continuous even/odd alternation for the whole run via a single running step counter in the refactored JC solver; the literal port keeps the per-phase index. Intent: alternation never double-steps a half-grid at a phase boundary. port_review §2.5, §3.2c. Differential tests vs legacy_port.py for JC must therefore compare with a tolerance only on cases where the literal port's parity sequence is continuous (phase 3 not entered and phase-1 exit k odd); for the others, assert the refactored result against a legacy run patched to a running counter, and record the before/after difference.
F-3 JC fidelity (full vs simplified) deferred to Stage 5b sweep. coupling.py is the only module the decision may touch.

Flag-first approach for this (owner's instruction, Stage 4.2 session): both fixes are built behind keyword flags defaulting to the VBA behaviour, the differential suite passes bitwise on the legacy flags, then the defaults flip; this supersedes the tolerance-only comparison note under F-2 above.

Bookkeeping when applied: F-1 changes DEVIATIONS D-17 and F-2 changes D-19 from "preserved" to "fixed" (with the pinning tests in `tests/test_quirks.py` re-pinned to the new behaviour); `legacy_port.py` itself stays literal.

## Next action
**Local bench reference run, then Session 5b.** (unchanged by V.2b) (1) The owner's reference bench on local
hardware (the absolute row for the paper): `.venv/bin/python tools/bench.py --profile` from the
repository root on a quiet machine (about an hour; `--skip-full-python` brings it to ~10 min at
the cost of the full-JC pure-Python row), then commit `docs/bench/<sha>.json` and
`docs/bench/README.md`. No bench was run in V.2: nothing on the solver path changed (the viz
package is read-only on a `PeakResponse`). (2) Session 5b as queued below: `histories.py` (which
replaces the `--step` stand-in of `tools/animate.py`), F-3, the `unbalance_force` speed lever,
the cache guard. V.2 leaves the owner three things to look at: the judgement calls in "Session
V.2 — done" (the U geometry above all), the `docs/viz/golden_r096_jc.html` frame cap (150; a
400-frame page is 10.5 MB), and whether `docs/viz/` pages should be regenerated by a target
(`make viz`) rather than by hand.

Previous next action (V.1 → V.2, kept for the record):
**Session V.2 (owner to specify: the visualiser that consumes `trace.Trace`).** V.1 hands it a
self-describing `Trace` per run (`PeakResponse.trace`): per frame `t, sub_step, sample, phase,
x, v, a, f_a, f_b, f_unbalance, f_friction, stick, d_f`, JC `p_cells` / `v_cells` on the
interleaved staggered grid with `cell_position` / `cell_kind` / `moving_fraction`, and the
one-off `params`, `inputs`, grid sizes. Open points for V.2 to decide against its needs: the
frame convention (end of sub-step `i * k`, `t = (sub_step + 1) dt`), the interleaved column
layout, and the free-decay window cap (frames stop where the history stops). The Stage 5b
items below stay queued.

Previous next action (Stage 5 → 5b, kept for the record):
**Stage 5b.** (1) Owner's reference bench on local hardware (the absolute row for the paper):
`.venv/bin/python tools/bench.py --profile` from the repository root on a quiet machine (about an
hour; `--skip-full-python` leaves the three full JC cases out of the pure-Python mode and brings it
to ~10 min, at the cost of that row), then commit `docs/bench/<sha>.json` and `docs/bench/README.md`.
(2) F-3, JC fidelity (full vs simplified) sweep; `coupling.py` is the only module the decision may
touch (approved-fixes note). (3) Speed, next lever: `loads.unbalance_force` is now ~75 % of a
compiled lumped run (0.55 s of 0.62 s profiled on row 20; the kernel itself is tens of ms) and the
flat-array hand-off would let a compiled walk write straight into the array; the set-up and
`pressure.py` are milliseconds and not worth compiling. (4) Optional: a `cache=True` staleness guard
in CI beyond the wipe (`make clean-cache`), and the `jc_slow` marker text in `pyproject.toml` still
says "hours each in pure Python" (true for the literal-port cases only).

Previous next action (Stage 4.4 → 5, kept for the record):
**Stage 5 (Numba).** `moc.step` and the `pressure.py` half-loops are already scalar loops over
contiguous float64 arrays with no Python objects, written for `@njit`; `structure.step` and
`response._integrate` are Python-float code that can follow. Judge `**` vs C `pow` (D-15: Numba
lowers integer-literal `**` to multiplication) against the recorded tolerances (golden 5e-12,
Example 1e-12) rather than expecting bit-identity, and record any last-bit change in
DEVIATIONS.md with a pinning test. Acceptance: the three `jc_slow` cases (5e-12), `-m slow`,
the fast suite, and `tools/bench.py` with `docs/bench/` committed. Keep `NUMBA_DISABLE_JIT=1`
runs green (CLAUDE.md). numba is permitted but not yet in `pyproject.toml`; add it as an
optional dependency when Stage 5 starts.

Previous next action (Stage 4.3 → 4.4, kept for the record): Stage 4.3 is done; Stage 4 now covers every entry point (`response.peak_response`, `response.peak_response_jc`,
`pressure.pressure_response`) with `legacy_port.py` still the frozen reference. Owner to name the next stage:
the candidates recorded so far are Stage 4.4 (owner's label for applying approved fixes; F-1/F-2 were already
applied in 4.2, so 4.4 would be whatever the owner adds, e.g. the D-6 clamp question and the `velInitLocal`
singularity found by the pressure sweep, raised with the lead author), Stage 5 (Numba: `moc.step` and the
pressure half-loops are written as scalar loops over contiguous arrays for `@njit`; `**` vs `pow`, D-15, to be
judged against the recorded tolerances; the three `jc_slow` cases are the acceptance test), Stage 5b (F-3 JC
fidelity sweep, `coupling.py` only) and Stage 6 (remove `legacy_port.py`; `tests/test_quirks.py` pins move to
the new modules). Gates unchanged: `.venv/bin/python -m pytest -q` before every commit, `-m slow` before any
`src/` commit, `tools/bench.py` at the end of every Stage 4/5 session with `docs/bench/` committed.

Previous next action (Stage 4.2, kept for the record): `moc.py` + the JC coupling +
`response.peak_response_jc` with F-1/F-2 flag-first — done, see "Stage 4.2 — done".

Previous next action (Stage 4.1, owner's instruction, 2026-10-20), kept for the record: Run `tools/bench.py` at the end of every Stage 4/5 session and commit `docs/bench/` (CLAUDE.md); compare the "result vs prev" column, which must read `same` for a behaviour-preserving commit. No document in the repo defines the Stage 4.1 scope; the only stage material beyond Stage 1 is the refactor map in `docs/port_review.md` §2 (Stage 4) and the Numba target (Stage 5), so record the 4.1 scope in this file at the start of that session before touching `src/`. Read `docs/port_review.md` §2 (refactor map, §2.5 parity hazard) and §4 (blind spots) first. Gate: `.venv/bin/python -m pytest -q` before every commit, `-m slow` (3.5 min) before any commit touching `src/`; `tests/test_quirks.py` must stay green as written (a change to a pinned quirk needs a DEVIATIONS.md row). The 3 JC cases have run once (1 h 20 min, all pass, tolerance 5e-12 measured); re-run them (`pytest -m jc_slow`, background) before any commit that touches the JC solver path, and before the Stage 5 Numba acceptance. If `GetPressureResponse` needs a golden case, add a UDF call with a committed valve pattern to the workbook and extend `tools/extract_fixtures.py`.
