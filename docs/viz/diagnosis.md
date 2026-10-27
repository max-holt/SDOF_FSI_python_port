# Animation pages: browser diagnosis (Session V.2e, 2026-10-26)

*Session F-4b (2026-10-27): the four pages this document names were deleted from `docs/viz/`
(the viewer `docs/viewer/` replaces them); `tests/test_viz_motion.py` now builds the two it
drives into a temporary directory with the same arguments. The text below is unchanged.*

**Status (Session V.2f, 2026-10-26): fixed with candidate 1 below.** Every frame lists all six
traces, `{}` for the static ones (`viz/animate.py`); the four pages are regenerated and
`tests/test_viz_motion.py` is green (the two V.2e tests unchanged, plus a friction group count
before / after 2 s of play on two pages). The `pageerror: undefined` of §2 is the rejected
promise of a `Plotly.animate` interrupted by pause, present on every page; see NOTES.md V.2f.
The text below is the V.2e diagnosis as written.

Diagnosis only; no page, `src/` or tool file was changed. The evidence comes from
`tests/test_viz_motion.py` (Playwright, headless Chromium 141, plotly.js 4.1.1 served from the
installed `plotly` package in place of the CDN tag the pages carry) and from the browser
experiments recorded below. Screenshots: `tests/.artifacts/example_jc_step_before_play.png` /
`_after_play.png` (written by the test, not committed).

## 1. The friction line vanishes on play (`example_jc_step.html`)

**What the lead author sees is real, and it is not a data overwrite.** After the first animated
frame the friction trace is still in the figure's data model, unchanged, but its SVG group has
been removed from the page; nothing draws it again until a full replot.

Trace table before and after 2 s of play (play button injected by `write_html`, 1x = 40 ms a
frame; the slider reached frame 40):

| i | name (gd.data) | y-axis | visible | points | drawn in SVG, before | drawn in SVG, after |
|---|---|---|---|---|---|---|
| 0 | centreline | y | true | 37 | yes (subplot xy) | yes |
| 1 | cells | y | true | 37 | yes (subplot xy) | yes |
| 2 | friction force, right axis | y3 (overlays y2) | true | 1124 | yes (subplot x2y2, overplot group x2y3) | **no** |
| 3 | F_A(t) - F_B(t - L/c), left axis | y2 | true | 1124 | yes (subplot x2y2) | yes |
| 4 | current time (cursor) | y2 | true | 2 | yes (subplot x2y2) | yes |
| 5 | status | y | true | 1 | yes (subplot xy) | yes |

`len(gd.data)` is 6 before and after; every name, axis, `visible` and array length is
identical before and after. The 376 frames all carry `traces = [1, 4, 5]` with three data
entries each (circles, cursor, status), so frame data and trace indices agree: no frame lists
trace 2, no frame lists trace 3, and nothing overwrites either. The question "which frame
index overwrote which trace" has the answer: none. The overplot group of subplot `x2y2`
reads `x2y2: scatterlayer`, `x2y3: scatterlayer` before play and `x2y2: scatterlayer`,
`x2y3: (empty)` after.

**Which frame does it.** The first one. A single `Plotly.animate(gd, ['1'], {frame: {duration:
0, redraw: false}, mode: 'immediate'})` (the exact options of every slider step and of the
page's buttons) removes trace 2's group and empties the `x2y3` layer
(`test_first_animated_frame_keeps_every_trace_group`); so does a slider step to any other
frame. The loss therefore happens on the first slider move or play, at any speed.

**Mechanism (plotly.js 4.1.1, cartesian `plotOne`).** `Plotly.animate` with `redraw: false`
runs `Plots.transition`, which calls the cartesian `plot(gd, transitionedTraces, ...)` with
the frame's `traces` (`[1, 4, 5]`). That function iterates every cartesian subplot (`xy`,
`x2y2`, `x2y3`), builds each subplot's module-layer list only from the listed traces that
belong to it, and joins it to the subplot's existing `g.mlayer` groups with
`exit().remove()` (minified: `f.length && h.push(...)` then
`t.plot.selectAll("g.mlayer").data(h, className)` … `x.exit().remove()`). Subplot `xy` keeps
its scatter layer (traces 1 and 5 are listed), `x2y2` keeps its (trace 4), but the overlaying
subplot `x2y3`, home of the friction trace since V.2b put friction on the secondary axis, has
no listed trace, so its only layer is removed together with the friction `g.trace` inside it.
The unbalance trace (3) is not listed either but survives because it shares the `x2y2` layer
with the cursor; within a layer, a transition never removes exiting traces.

Browser experiments that pin this (same page, same options):

| animate call | friction group | unbalance group | overplot layers |
|---|---|---|---|
| fresh page | present | present | x2y2: scatterlayer; x2y3: scatterlayer |
| frame `'5'` (`traces [1, 4, 5]`) | removed | present | x2y2: scatterlayer; x2y3: empty |
| synthetic frame `traces [2]`, data `[{}]` | restored | **removed** | x2y2: empty; x2y3: scatterlayer |
| frame `'7'` with `redraw: true` | present | present | both present (full replot) |
| frame `'8'` (`redraw: false`) | removed | present | x2y3 empty again |
| synthetic frame `traces [1, 2, 4, 5]`, `{}` for trace 2 | present | present | both present |

**History.** V.2b moved friction to the overlaying axis and used `redraw: true`; each frame's
transition removed the `x2y3` layer and the redraw that followed rebuilt it, which is the
intermittent "vanishing right-axis line at speed" of the second review. V.2c removed the
per-frame layout change and switched every animate call to `redraw: false`, which stopped
the flicker and also removed the only thing that was putting the line back; the V.2c note
records that this was not verified in a browser. `tests/test_viz.py` cannot see it: it checks
the figure object, and the figure object is correct.

**Fix candidates (not applied; owner to choose).** Any of these keeps a transitioning trace in
subplot `x2y3`, which is what the layer join needs:
1. List every trace in each frame's `traces` with an empty `{}` data entry for the static ones
   (the experiment above with `[1, 2, 4, 5]` shows the layers survive). Cost: the listed
   traces are re-plotted each frame (the force traces are 1124 / 1998 points, small next to
   the 1333 circles of row 96).
2. Add a second cursor trace on the right axis (`secondary_y=True`, `±ff_lim`) and animate it
   with the primary one: every subplot then has a transitioning trace, frames stay three or
   four small traces. Predicted by the mechanism, not tried.
3. `redraw: true` again: restores the line but brings back the V.2b flicker.
4. Take friction off the overlaying axis (scale it onto the left axis, or a second row): a
   figure-design change.
Whichever is chosen, `tests/test_viz_motion.py` is the test that must go green.

## 2. `golden_r096_jc.html`: frames versus trace span

Read from the page in the browser (`test_golden_r096_frames_inside_window`, which passes):

| quantity | value |
|---|---|
| title window | `animated window t = 6.006 to 7.499 s`, `frame stride 1`, `trace_every = 504`, `dt = 1.98e-05 s` |
| frames | 151, t = 6.0056 s to 7.4995 s (span 1.4939 s) |
| frame spacing | 9.9597 ms, uniform (min = max to float32), = one traced sample (504 x 19.763 µs); stride 1 |
| Panel 2 trace (unbalance / friction x) | 1998 points, t = 0 to 19.879 s (the whole run) |
| frames outside [6, 7.5] s | none |

So the page is what V.2d intended: the slider and the frames cover only the 1.5 s window at
full trace resolution (10 ms a frame, 0.03 of the 3 Hz period), while Panel 2 and its time
axis keep the 19.9 s run with the window shaded. No frame lies outside `--t-start 6
--t-end 7.5`. (The title's `dt` is printed to three significant figures; the true `dt` is
`1 / (1265 x 40)` = 19.763 µs.)

The same friction-line loss occurs on this page on play (checked once by hand with the same
probe: trace 2 absent from the SVG from the first frame, slider at frame 34-47 after 2 s,
i.e. 45-60 ms a frame delivered for 1333 cells at the 40 ms setting). One run of the
hand probe on this page logged a `pageerror: undefined` from the browser; the test run
logged none, and it was not chased.

## 3. Test notes

- `tests/test_viz_motion.py` needs the `playwright` Python package (installed into `.venv`
  with `uv pip install playwright==1.56.0`, the version matching `chromium-1194` under
  `/opt/pw-browsers`; not added to `pyproject.toml`, the owner's call) and skips without it or
  without a Chromium executable (`PLAYWRIGHT_BROWSERS_PATH`, default `/opt/pw-browsers`).
- The pages load plotly.js from the CDN. The test intercepts that request and serves the
  `plotly.min.js` bundled with the installed `plotly` package after asserting the versions
  match (both 4.1.1), so the test is offline and runs against a known plotly.js. The CDN is
  unreachable from this sandbox, so the pages themselves could not be checked against the
  live CDN copy.
- Expected state until the fix: `test_play_keeps_friction_trace` and
  `test_first_animated_frame_keeps_every_trace_group` fail; `test_golden_r096_frames_inside_window`
  passes. The rest of the suite is unaffected (nothing under `src/` changed).
