# The results viewer (`docs/viewer/viewer.html`)

One self-contained HTML file that plays a `trace` results file (`tools/export.py`,
`docs/data_format.md`) as the two-panel animation of `viz/animate.py`, with playback, speed, frame
stride, time window, exaggeration and colour range controlled live in the page. Nothing is
downloaded at runtime: plotly.js and the gzip inflater are inside the file, and a
content-security policy in the page blocks every network request, so the page behaves the same
opened from disk, from a SharePoint download or from an object-storage URL. Session W.2 covers
trace mode; sweep mode (a `sweep` file) is Session W.3.

## Opening

Double-click `viewer.html` (or open it from a browser's File menu). No server, no Python, no
network. The page is ~4.9 MB because it carries the full plotly.js bundle (see "Build").

## Loading a results file

Use the file picker or drop a file anywhere on the page. `.json` and `.json.gz` are both read
(gzip is detected by the file's own magic bytes, not its name). A file whose `kind` is not
`trace` / `sweep` or whose `schema_version` is not `1` is refused with a message that names
what was found; a `sweep` file is recognised and its meta shown, with a note that sweep mode is
W.3. The committed examples are in `docs/viz/data/`: `example_jc_step.json` (1.8 MB),
`example_lumped_step.json` (0.14 MB), `golden_r096_jc.json.gz` (20.6 MB, inflates to 47 MB and
takes a few seconds to parse), `reference_sweep.json`.

The header shows the file's meta (case id, solver, `dt`, `trace_every`, frame and cell counts,
the capped flag, git sha, created time) and the scaling in use (exaggeration, the size rule, the
colour range, the nominal circle size, the stride and the frames in the window, the 1x frame
period), so a screenshot carries its own provenance.

## The picture

The same two panels as the plotly pages in `docs/viz/`, drawn with the same rules so the two
can be compared side by side (the rules are in `docs/architecture.md`, "the animation", and the
constants at the top of the page's script name the `viz/animate.py` constants they copy):

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
* **speed**: a typed multiplier or the 0.25x … 4x buttons; 1x is 40 ms a shown frame, the plotly
  pages' rate. The loop computes the frame due from the elapsed wall time, so when a frame
  takes longer to draw than the period (row 96's 1333 cells at 4x) frames are skipped and the
  speed holds.
* **stride**: animation frames advanced per shown frame; blank is automatic, the stride
  `tools/animate.py` would pick for the file (`ceil((n_frames - 1) / 398)`), so 1x at the
  automatic stride is the plotly page's pace. Stride 1 shows every frame of the file.
* **t_start / t_end**: the window played (default the whole run); Panel 2 shades it.
* **exaggeration**: overrides the automatic multiplier (blank = automatic).
* **colour range**: overrides `±max|v|` in m/s (blank = automatic; JC files only).
* The frame slider scrubs; the readout gives the frame, its time and phase.

Speed and the three overrides are remembered in the browser's `localStorage` (per origin: a
file opened from disk and the same file on SharePoint keep separate settings). The window is per
file and not remembered. Without storage (private windows, a locked-down viewer) the page says
so in the control bar and works the same.

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
  the four data files, playback, windowing, speed, settings, blocked storage, the schema check,
  and zero requests beyond the page itself.
* Not tested in this session: Edge, Chrome with a visible window, Firefox, Safari. The page uses
  only `file.arrayBuffer()`, `TextDecoder`, `requestAnimationFrame`, `localStorage` and plotly.js
  4.1.1's own requirements (any browser since 2020 has them), but the owner should open it once
  in the browser the readers use and note the result here.

## Tests

`.venv/bin/python -m pytest -q tests/test_viewer.py -s` (needs the `dev` extra's `playwright`
and a browser; otherwise the module skips). Screenshots of the viewer at the peak frame and of
the matching plotly page at its frame nearest that time are written to `tests/.artifacts/`
(not committed) for review.
