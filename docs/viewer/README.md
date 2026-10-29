# The results viewer (`docs/viewer/viewer.html`)

One self-contained HTML file that plays a `trace` results file (`tools/export.py`,
`docs/data_format.md`) as a two-panel animation (`docs/architecture.md`, "The picture"), with
playback, speed, frame stride, time window, exaggeration and colour range controlled live in
the page, and that plots a `sweep` results file (Session 5b's junction-coupling sweep) as three
filterable tabs with a self-check of the Excel reference values. Nothing is
downloaded at runtime: plotly.js and the gzip inflater are inside the file, and a
content-security policy in the page blocks every network request, so the page behaves the same
opened from disk, from a SharePoint download or from an object-storage URL. Session W.2 built
trace mode, Session W.3 sweep mode; the file's `kind` picks the mode.

## Opening

Double-click `viewer.html` (or open it from a browser's File menu). No server, no Python, no
network. The page is ~4.9 MB because it carries the full plotly.js bundle (see "Build").

## Loading a results file

Use the file picker or drop a file anywhere on the page. `.json` and `.json.gz` are both read
(gzip is detected by the file's own magic bytes, not its name). A file whose `kind` is not
`trace` at `schema_version` 1 or `sweep` at `schema_version` 2 (the Session 5b layout; the
thirty-column W.1 sweep is not read) is refused with a message that names what was found. The
committed examples are in `docs/viz/data/`: `example_jc_step.json` (1.8 MB),
`example_lumped_step.json` (0.14 MB), `golden_r096_jc.json.gz` (13.9 MB, inflates to 47 MB and
takes a few seconds to parse), `reference_sweep.json` (the 78 `curve_10in` golden rows) and
`tier1_sweep.json` (the 1600 Tier 1 rows).

The header shows the file's meta (case id, solver, `dt`, `trace_every`, frame and cell counts,
the capped flag, git sha, created time) and the scaling in use (exaggeration, the size rule, the
colour range, the nominal circle size, the stride and the frames in the window, the 1x frame
period), so a screenshot carries its own provenance.

## The picture

Two panels, drawn by the rules of `docs/architecture.md`, "The picture" (the constants at the
top of the page's script name them; the rules came from the plotly-python animation the
viewer replaced, retired in Session H.1):

* **Panel 1, expansion loop.** Inlet pipe, leg, run, return leg, outlet from the file's
  `geometry` (the nominal circle centres the exporter wrote). Each cell is a circle at
  `x_nominal + x(t) * moving_fraction * exaggeration` with `exaggeration = 0.1 * run_length /
  max|x|`, sized `nominal * (1 + k_p (p - 0) / max|p|)` with `k_p` such that the largest circle
  of the run is 2x nominal (floor 0.15x), coloured by the cell velocity `v` on the blue–grey–red
  diverging scale, `±max|v|`, colour bar "relative fluid velocity (JC arrays)". A lumped run has
  constant size and the grey midpoint. Hover gives the cell, its kind, segment, position,
  fraction and, for JC, `p` and `v`.
* **Panel 2.** The applied unbalance `F_A(t) - F_B(t - L/c)` on the left axis over the friction
  force on the right axis (drawn first, translucent), symmetric ranges so the zeros coincide,
  phase bands, the time of peak `|x|` marked, the animated window shaded when it is not the
  whole run, and a cursor at the frame time. Panel 2 always shows the whole run.

## Controls

* **play / pause** (the space bar toggles), **jump to peak** (the frame of peak `|x|` over the
  whole run; if it lies outside the window, play restarts from `t_start`).
* **speed**: a typed multiplier or the 0.25x … 4x buttons; 1x is 40 ms a shown frame. The loop computes the frame due from the elapsed wall time, so when a frame
  takes longer to draw than the period (row 96's 1333 cells at 4x) frames are skipped and the
  speed holds.
* **stride**: animation frames advanced per shown frame; blank is automatic, the stride that
  shows at most 400 frames of the file (`ceil((n_frames - 1) / 398)`). Stride 1 shows every
  frame of the file.
* **t_start / t_end**: the window played (default the whole run); Panel 2 shades it.
* **exaggeration**: overrides the automatic multiplier (blank = automatic).
* **colour range**: overrides `±max|v|` in m/s (blank = automatic; JC files only).
* The frame slider scrubs; the readout gives the frame, its time and phase.

Speed and the three overrides are remembered in the browser's `localStorage` (per origin: a
file opened from disk and the same file on SharePoint keep separate settings). The window is per
file and not remembered. Without storage (private windows, a locked-down viewer) the page says
so in the control bar and works the same.

## Sweep mode

A `sweep` file (`docs/data_format.md`, "sweep": one flat array per column, a `regen` template,
the `reference` block) opens in sweep mode: the header lists the file's meta (rows and columns,
tier, source, created time, git sha, CPU, histories version, the regen template, the reference
check), and below it three tabs, a filter row, the plot and the row panel. Every quantity is
drawn against `nat_freq_hz`, the absolute natural frequency of the lumped model, as in
`docs/jc_sweep.md`; the colours and symbols are those of the report's PNGs (`tools/sweep_jc.py`:
colour by span length, symbol by length or size).

* **curve families.** `y` is `f_eq` raw (N), `daf` (`F_eq / (p_peak A)`) or `f_eq_over_LD2`
  (`F_eq / (L d²)`), lumped and JC overlaid: hollow markers and a thin line for lumped, filled
  markers and a thicker line at 0.55 opacity for JC. One panel per pipe size (the y axes
  matched), one trace per span length; when a filter left open still varies among the rows
  (several sine frequencies, seeds, amplitudes or frictions), each value is its own family,
  named in the legend and distinguished by the line dash.
* **JC effect.** `ratio_f_eq` (or `ratio_v_peak`; the schema-2 columns, `ratio_f_peak` of the
  W.1 layout no longer exists because `f_peak` is an input property) as circles sized by span
  length, coloured by history type, opacity 0.6, with the report's ±5 % band at 1 and the
  dashed 0.8 line. The tab animates over `amplitude_fraction` or `mu`: the frames are the
  distinct values of that column among the filtered rows (its own dropdown is opened and
  locked while it animates), and the page's play / pause, speed buttons, slider and the space
  bar drive it, at 1 s per value at 1x (the trace controls that do not apply are hidden). The
  status text in the plot and the readout under the slider give the current value.
* **collapse.** `f_eq_over_LD2` (top row) and `daf` (bottom row) with all sizes and lengths on
  one panel per history type: colour by length, symbol by size, lumped hollow and JC filled as
  above. The y axes of a row are matched across the panels.

**Filters.** `history_type`, `f_osc_hz`, `seed`, `mu` and `amplitude_fraction`, each with `all`
and the column's distinct values (`(none)` for null). On open the defaults follow the report:
one history type (the first of step, step + sine, step + noise, golden that the file has), the
largest friction and amplitude when the column has two to six values, sine frequency and seed
open. The hint beside the filters counts the rows, traces and points drawn and says when the
selected columns are null for every row that passes (the reference file has no normalised or
ratio columns, so only its `f_eq` raw families plot).

**Hover and the row.** The hover label gives the case id, size, length, frequency, history,
amplitude, friction and the plotted value; the row panel under the plot fills with the full row
(all 72 columns, nulls marked) of the last point hovered. **regenerate trace** formats the
file's `regen.template` with that row's columns (`{name}` placeholders, as `str.format`) and
copies the command to the clipboard (or asks to select it when the browser refuses), with the
template's note after it. The reference file's template is `tools/export.py trace --golden
<case_id>`; the Tier 1 file's reruns the whole tier, as its note says (a single-row trace
command is not among the exporter's options).

**The reference badge.** On open every entry of the file's `reference` block is looked up among
the rows by `case_id`; where the row exists, each of the entry's `output_names` that has a
column (`f_eq`, `x_peak`, `v_peak`, `a_peak`, `f_peak` of the entry's solver) and a non-null
value is compared with the Excel value under the golden tests' rule `|row − excel| ≤ rtol
|excel|` (`tests/test_golden.py`; `rtol` is in the entry). The badge is green when every
compared value holds (the detail names the cases and the worst relative error), red when one
fails (naming the case, column and error), and neutral when no reference case is among the rows
(Tier 1: its cases are the sweep's, not the fixtures'). `reference_sweep.json` carries the three
JC golden rows and is green; the Example-sheet cases have no row in any file and are listed as
absent.

## Publishing

Copy the one file. There is nothing else to deploy: put `viewer.html` next to the data files in
a SharePoint folder or an object-storage bucket, or send it by mail. Readers download the page and
a data file and open the page locally, or open the page from the bucket URL and pick the data
file from their disk (a page served from a URL cannot read a data file from another URL: the
loader is the file picker / drop, by design, so the page never requests anything).

## Build

`docs/viewer/viewer.src.html` is the hand-written source (all CSS and JS inline, two markers);
`tools/build_viewer.py` inlines plotly.js from the installed `plotly` Python package and pako's
inflate-only build from `tools/viewer/pako_inflate.min.js` (1.0.11, MIT, licence beside it,
pinned by digest) and writes `viewer.html`, recording both versions in comments at the top of
each `<script>`. `tests/test_viewer.py` rebuilds the page and asserts it equals the committed one.

    .venv/bin/python tools/build_viewer.py            # after editing viewer.src.html

plotly.js is **4.1.1, the full bundle** (4.8 MB): the installed package ships no partial bundle
and the build never fetches. When a copy of `plotly.js-basic-dist-min` 4.1.1 is available
offline, `tools/build_viewer.py --plotly <file>` swaps it in (about 1 MB) with no other change.

## Browsers tested

* Headless Chromium 141 (Playwright 1.56.0, `chromium-1194`), on Linux, by `tests/test_viewer.py`:
  the five data files, playback, windowing, speed, settings, blocked storage, the schema check,
  sweep mode (the badge on both sweep files and on a tampered copy, the three tabs' trace
  counts, filters, the animation, hover and the regenerate command, mode switching) and zero
  requests beyond the page itself.
* Not tested in this session: Edge, Chrome with a visible window, Firefox, Safari. The page uses
  only `file.arrayBuffer()`, `TextDecoder`, `requestAnimationFrame`, `localStorage` and plotly.js
  4.1.1's own requirements (any browser since 2020 has them), but the owner should open it once
  in the browser the readers use and note the result here.

## Tests

`.venv/bin/python -m pytest -q tests/test_viewer.py -s` (needs the `dev` extra's `playwright`
and `plotly` and a browser; otherwise the module skips). Screenshots of the viewer at the peak
frame and of the three sweep tabs of each sweep file are written to `tests/.artifacts/` (not
committed) for review.
