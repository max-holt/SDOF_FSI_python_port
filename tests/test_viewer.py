"""Browser tests of the single-file results viewer ``docs/viewer/viewer.html`` (Session W.2
trace mode, Session W.3 sweep mode), in Playwright / headless Chromium (no ``playwright``
package, no ``plotly`` package or no browser skips the module).

Every page the tests open records each request the browser makes; anything but the page's own
``file:`` URL fails the test (the viewer makes no network request of any kind). The data files
in ``docs/viz/data/`` are loaded through the file input; the three trace files must render the
six traces of the two-panel picture (``docs/architecture.md``, "The picture") with the scalings
the file implies. Playback is exercised (friction trace and its SVG group survive 2 s of play; a
time window keeps every shown frame inside it; 4x advances more frames than 1x over the same
wall time), a ``schema_version: 99`` file must be rejected with a readable message, settings
must persist and the page must work with storage blocked.

Sweep mode (W.3) is tested on the two committed ``sweep`` files: the reference check badge is
green for ``reference_sweep.json`` (the Excel values of the three junction-coupling golden rows
are among its rows), neutral for ``tier1_sweep.json`` (no reference case among the rows) and
red for a tampered copy; each of the three tabs renders the trace count the file's columns and
the default filters imply (computed here from the file); a filter change moves the counts; the
JC-effect animation advances over the amplitude values through the page's play button; hovering
a point fills the row panel with all 72 columns and the regenerate button formats the file's
template; the modes switch cleanly. ``test_build_reproduces_committed_page`` needs no browser:
the committed page is byte-identical to ``tools/build_viewer.py``'s output with the installed
plotly bundle.

Requirements: the ``playwright`` package (``uv pip install playwright``, no ``playwright
install``: the browser is read from ``/opt/pw-browsers`` or ``PLAYWRIGHT_BROWSERS_PATH``) and
the ``plotly`` Python package (the source of the inlined plotly.js bundle; both in the ``dev``
extra). Screenshots of the viewer at the peak-|x| frame go to ``tests/.artifacts/`` (not
committed) for the owner's review; no pixel comparison is made.
"""

from __future__ import annotations

import glob
import gzip
import json
import os
import pathlib
import sys
from decimal import Decimal

import pytest

pytest.importorskip("playwright.sync_api")
plotly = pytest.importorskip("plotly")

from playwright.sync_api import Error as PlaywrightError  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_viewer  # noqa: E402

VIEWER = ROOT / "docs" / "viewer" / "viewer.html"
VIEWER_SRC = ROOT / "docs" / "viewer" / "viewer.src.html"
DATA = ROOT / "docs" / "viz" / "data"
ARTIFACTS = pathlib.Path(__file__).parent / ".artifacts"
BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
CHROMIUM = sorted(glob.glob(f"{BROWSERS}/chromium-*/chrome-linux/chrome"))
TRACE_FILES = ["example_jc_step.json", "example_lumped_step.json", "golden_r096_jc.json.gz"]
SWEEP_FILES = ["reference_sweep.json", "tier1_sweep.json"]
SWEEP_TABS = ["curves", "effect", "collapse"]
FILTER_COLS = ["history_type", "f_osc_hz", "seed", "mu", "amplitude_fraction"]
HISTORY_ORDER = ["step", "step_sine", "step_noise", "golden"]
Y1_STEMS = {"f_eq": "f_eq", "daf": "daf", "f_eq_over_LD2": "f_eq_over_LD2"}
SWEEP_FRAME_MS = 1000
# the two JC trace files, screenshotted at their peak
SCREENSHOT_FILES = ["example_jc_step.json", "golden_r096_jc.json.gz"]
N_TRACES = 6
CENTRELINE, CELLS, FRICTION, UNBALANCE, CURSOR, STATUS = 0, 1, 2, 3, 4, 5
PLAY_MS = 2000
LOAD_TIMEOUT_MS = 180_000  # the gzipped row 96 file inflates to 47 MB of JSON

READY_JS = "() => !!(window.viewer && window.Plotly && window.pako)"
# a load has finished when the trace is open and drawn, a sweep is open, or a message other
# than the "loading …" notice is shown
LOADED_JS = """
() => (!!window.viewer.data() && document.querySelectorAll('#plot g.trace').length > 0)
      || !!window.viewer.sweep()
      || (document.getElementById('message').className !== ''
          && !document.getElementById('message').textContent.startsWith('loading '))
"""
SWEEP_SNAPSHOT_JS = """
() => {
  const gd = document.getElementById('splot');
  const sw = window.viewer.sweep();
  const data = (gd.data || []).filter(t => t.name !== 'status');
  const sel = {};
  for (const s of document.querySelectorAll('#filter-selects select'))
    sel[s.dataset.col] = {value: s.value, disabled: s.disabled,
                          options: Array.from(s.options).map(o => o.value)};
  return {
    open: !!sw, tab: sw ? sw.tab : null, counts: sw ? sw.counts : null, filters: sw ? sw.filters : null,
    n_data: data.length, n_points: data.reduce((n, t) => n + t.x.length, 0),
    names: data.map(t => t.name), axes: data.map(t => (t.xaxis || 'x') + (t.yaxis || 'y')),
    groups: gd.querySelectorAll('g.trace.scatter').length,
    trace_plot_traces: (document.getElementById('plot').data || []).length,
    badge_class: document.getElementById('badge').className,
    badge: document.getElementById('badge').textContent,
    badge_detail: document.getElementById('badge-detail').textContent,
    hint: document.getElementById('sweep-hint').textContent,
    message: document.getElementById('message').textContent,
    message_class: document.getElementById('message').className,
    meta: document.getElementById('meta').textContent,
    body_class: document.body.className, sweep_class: document.getElementById('sweep').className,
    controls_class: document.getElementById('controls').className,
    readout: document.getElementById('readout').textContent,
    slider_max: document.getElementById('slider').max,
    anim: {cur: window.viewer.anim.cur, n: window.viewer.anim.n, values: window.viewer.anim.values},
    selects: sel, row_title: document.getElementById('row-title').textContent,
    row_names: Array.from(document.querySelectorAll('#row-list dt')).map(d => d.textContent),
    row_values: Array.from(document.querySelectorAll('#row-list dd')).map(d => d.textContent),
    regen_cmd: document.getElementById('regen-cmd').textContent,
    regen_note: document.getElementById('regen-note').textContent,
  };
}
"""
SNAPSHOT_JS = """
() => {
  const gd = document.getElementById('plot');
  const data = gd.data || [];
  return {
    n_data: data.length,
    names: data.map(t => t.name),
    axes: data.map(t => (t.xaxis || 'x') + (t.yaxis || 'y')),
    n_points: data.map(t => (t.x ? t.x.length : null)),
    groups: document.querySelectorAll('#plot g.trace.scatter').length,
    subplots: Array.from(document.querySelectorAll('#plot .subplot')).map(s => s.getAttribute('class')),
    colorbar_title: (data[1] && data[1].marker && data[1].marker.colorbar) ? data[1].marker.colorbar.title.text : null,
    message: document.getElementById('message').textContent,
    message_class: document.getElementById('message').className,
    meta: document.getElementById('meta').textContent,
    state: window.viewer.state,
    scaling: window.viewer.scaling(),
  };
}
"""
FRICTION_GROUPS_JS = """
() => {
  const gd = document.getElementById('plot');
  const uid = gd._fullData[FRICTION].uid;
  const groups = gd.querySelectorAll('g.trace.scatter.trace' + uid);
  return {groups: groups.length,
          g_inside: Array.from(groups).reduce((n, g) => n + g.querySelectorAll('g').length, 0),
          lines: Array.from(groups).reduce((n, g) => n + g.querySelectorAll('path.js-line').length, 0)};
}
""".replace("FRICTION", str(FRICTION))


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        kw = {"executable_path": CHROMIUM[-1]} if CHROMIUM else {}
        try:
            b = p.chromium.launch(**kw)
        except PlaywrightError as exc:  # no browser in this environment
            pytest.skip(f"headless Chromium not available: {exc}")
        yield b
        b.close()


def read_data(name: str) -> dict:
    path = DATA / name
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw)


def open_viewer(browser, init_script: str | None = None):
    """Open the viewer. Returns ``(page, requests, errors)``: every request URL the page makes
    and every page error, both appended to as the test goes on."""
    page = browser.new_page(viewport={"width": 1300, "height": 1000})
    if init_script:
        page.add_init_script(init_script)
    requests: list[str] = []
    errors: list[str] = []
    page.on("request", lambda r: requests.append(r.url))
    page.on("pageerror", lambda e: errors.append(str(e)))

    def gate(route):  # belt and braces: nothing but the page itself may even be attempted
        if route.request.url == VIEWER.as_uri():
            route.continue_()
        else:
            route.abort()

    page.route("**/*", gate)
    page.goto(VIEWER.as_uri())
    page.wait_for_function(READY_JS, timeout=60_000)
    return page, requests, errors


def load(page, path: pathlib.Path):
    page.set_input_files("#file", str(path))
    page.wait_for_function(LOADED_JS, timeout=LOAD_TIMEOUT_MS)
    page.wait_for_timeout(300)
    return page.evaluate(SNAPSHOT_JS)


def assert_no_network(requests, errors):
    assert requests == [VIEWER.as_uri()], f"the viewer made requests beyond itself: {requests}"
    assert not errors, f"page errors: {errors}"


def set_value(page, selector: str, value: str):
    page.fill(selector, value)
    page.dispatch_event(selector, "change")


# ------------------------------------------------------------------ sweep-mode helpers


def load_sweep(page, path: pathlib.Path) -> dict:
    page.set_input_files("#file", str(path))
    page.wait_for_function(LOADED_JS, timeout=LOAD_TIMEOUT_MS)
    page.wait_for_timeout(400)
    return page.evaluate(SWEEP_SNAPSHOT_JS)


def sweep_snapshot(page) -> dict:
    page.wait_for_timeout(400)
    return page.evaluate(SWEEP_SNAPSHOT_JS)


def click_tab(page, tab: str) -> dict:
    page.click(f'#tabs button[data-tab="{tab}"]')
    return sweep_snapshot(page)


def select_filter(page, col: str, value: str) -> dict:
    page.select_option(f"#f-{col}", value)
    return sweep_snapshot(page)


def hover_first_point(page) -> dict:
    """Move the mouse onto the first marker of the sweep plot (a real pointer event: plotly's
    ``plotly_hover`` fires only for one) and return the snapshot."""
    pt = page.locator("#splot g.trace.scatter .points path").first
    pt.scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    bb = pt.bounding_box()
    page.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
    return sweep_snapshot(page)


def js_key(v) -> str:
    """The viewer's ``valueKey``: ``String(v)`` of a JSON value, ``'null'`` for null. A JS
    number prints its shortest round-trip digits (Python's ``repr``) in plain decimal unless the
    exponent is below -7 or at least 21 (``1e-7``, ``1e+21``; Python: ``1e-07``, ``1e+21``)."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, float):
        if v.is_integer() and abs(v) < 1e21:
            return str(int(v))
        r = repr(v)
        if "e" not in r:
            return r
        d = Decimal(r)
        if -7 < d.adjusted() < 21:
            return format(d, "f")
        mant, e = r.split("e")
        return f"{mant}e{'+' if int(e) >= 0 else '-'}{abs(int(e))}"
    return str(v)


def distinct(cols: dict, name: str, rows=None) -> list:
    vals = {}
    for i in rows if rows is not None else range(len(cols[name])):
        vals.setdefault(js_key(cols[name][i]), cols[name][i])
    out = list(vals.values())
    nums = sorted(v for v in out if isinstance(v, (int, float)))
    strs = sorted(v for v in out if isinstance(v, str))
    return nums + strs + ([None] if None in out else [])


def default_filters(doc: dict) -> dict:
    """The viewer's default dropdown values: one history type (the first of step, step_sine,
    step_noise, golden present), the largest friction and amplitude when the column has 2..6
    distinct values, everything else open."""
    cols = doc["columns"]
    out = {}
    for col in FILTER_COLS:
        vals = distinct(cols, col)
        if col == "history_type":
            first = [h for h in HISTORY_ORDER if h in vals]
            out[col] = js_key(first[0] if first else vals[0])
        elif col in ("mu", "amplitude_fraction") and 2 <= len(vals) <= 6:
            nums = [v for v in vals if isinstance(v, (int, float))]
            out[col] = js_key(nums[-1]) if nums else "all"
        else:
            out[col] = "all"
    return out


def filtered_rows(doc: dict, filters: dict, open_cols=()) -> list[int]:
    cols = doc["columns"]
    rows = []
    for i in range(doc["meta"]["n_rows"]):
        ok = True
        for col in FILTER_COLS:
            f = "all" if col in open_cols else filters[col]
            if f != "all" and js_key(cols[col][i]) != f:
                ok = False
                break
        if ok:
            rows.append(i)
    return rows


def expected_counts(
    doc: dict, tab: str, filters: dict, y1="f_eq", ratio="ratio_f_eq", anim="amplitude_fraction"
):
    """The (traces, points) the viewer draws for a tab: the curve tabs give one lines+markers
    trace per (panel, series, open varying key, solver) that has a non-null value; the
    JC-effect tab one marker trace per history type (points of the first animation frame)."""
    cols = doc["columns"]
    rows = filtered_rows(doc, filters, open_cols=(anim,) if tab == "effect" else ())
    if tab == "effect":
        hist = distinct(cols, "history_type", rows)
        values = distinct(cols, anim, rows)
        first = values[0] if values else None
        pts = [
            i for i in rows if cols[ratio][i] is not None and js_key(cols[anim][i]) == js_key(first)
        ]
        return len([h for h in hist if h is not None]), len(pts)
    varying = [c for c in FILTER_COLS if filters[c] == "all" and len(distinct(cols, c, rows)) > 1]
    if tab == "collapse":
        varying = [c for c in varying if c != "history_type"]
        stems = ["f_eq_over_LD2", "daf"]
        panel_key = lambda i: (cols["history_type"][i], cols["size_in"][i], cols["length_m"][i])  # noqa: E731
    else:
        stems = [Y1_STEMS[y1]]
        panel_key = lambda i: (cols["size_in"][i], cols["length_m"][i])  # noqa: E731
    traces, points = 0, 0
    for stem in stems:
        for solver in ("lumped", "jc"):
            groups: dict[tuple, int] = {}
            for i in rows:
                if cols[f"{stem}_{solver}"][i] is None:
                    continue
                key = panel_key(i) + tuple(js_key(cols[c][i]) for c in varying)
                groups[key] = groups.get(key, 0) + 1
            traces += len(groups)
            points += sum(groups.values())
    return traces, points


def format_template(template: str, cols: dict, i: int) -> str:
    """The viewer's ``regenCommand``: ``{name}`` -> the row's value (null -> empty)."""
    import re

    def sub(m):
        if m.group(0) == "{{":
            return "{"
        if m.group(0) == "}}":
            return "}"
        v = cols[m.group(1)][i]
        return "" if v is None else js_key(v)

    return re.sub(r"\{\{|\}\}|\{([A-Za-z_]\w*)\}", sub, template)


# ------------------------------------------------------------------ no browser needed


def test_build_reproduces_committed_page():
    """The committed page is exactly what ``tools/build_viewer.py`` writes from the source page
    and the installed plotly bundle; the bundle is inlined verbatim with its version recorded."""
    plotly_js = build_viewer.plotly_bundle_path().read_bytes()
    pako_js = build_viewer.PAKO.read_bytes()
    built = build_viewer.build(
        VIEWER_SRC.read_bytes(), plotly_js, pako_js, "plotly/package_data/plotly.min.js"
    )
    committed = VIEWER.read_bytes()
    version = build_viewer.plotly_version(plotly_js)
    print(f"viewer.html {len(committed)} bytes, plotly.js v{version} {len(plotly_js)} bytes")
    assert built == committed, "docs/viewer/viewer.html is not the build of viewer.src.html"
    assert plotly_js.rstrip(b"\n") in committed
    assert f"plotly.js v{version} ".encode() in committed
    assert b"pako " + build_viewer.PAKO_VERSION.encode() in committed
    assert b"(The MIT License)" in committed  # pako's licence


def test_source_has_no_external_reference():
    """The source page (what is not the two libraries) names no external resource, and the
    content-security policy that blocks every fetch is present."""
    src = VIEWER_SRC.read_text(encoding="utf-8")
    assert 'http-equiv="Content-Security-Policy"' in src and "default-src 'none'" in src
    for needle in (
        'src="http',
        "src='http",
        'href="http',
        "href='http",
        "@import",
        "url(http",
        "fetch(",
        "XMLHttpRequest",
    ):
        assert needle not in src, needle
    assert src.count("<!-- @inline plotly -->") == 1 and src.count("<!-- @inline pako -->") == 1


# ------------------------------------------------------------------ loading


@pytest.mark.parametrize("name", TRACE_FILES)
def test_loads_each_data_file(browser, name):
    """Each trace file through the file input renders the six traces of the two-panel picture
    (the friction on the right axis) with the scalings the file implies; no request leaves the
    page. The sweep files are ``test_sweep_*`` below."""
    page, requests, errors = open_viewer(browser)
    snap = load(page, DATA / name)
    doc = read_data(name)
    print(f"{name}: {snap['n_data']} traces, groups {snap['groups']}, subplots {snap['subplots']}")
    print(f"  message: {snap['message'][:200]!r}")
    page.close()
    assert_no_network(requests, errors)
    assert snap["message"] == ""
    assert snap["n_data"] == N_TRACES and snap["groups"] == N_TRACES
    assert snap["names"][FRICTION].startswith("friction force")
    assert snap["axes"][FRICTION] == "x2y3" and snap["axes"][UNBALANCE] == "x2y2"
    assert snap["axes"][CELLS] == "xy" and snap["axes"][CURSOR] == "x2y2"
    assert {"subplot xy", "subplot x2y2", "subplot x2y3"} <= set(snap["subplots"])
    n = doc["meta"]["n_frames"]
    assert snap["n_points"][CELLS] == len(doc["geometry"]["x_nominal_m"])
    assert snap["n_points"][FRICTION] == snap["n_points"][UNBALANCE] == n
    # the header
    meta = doc["meta"]
    for needle in (
        meta["case_id"],
        meta["solver"],
        meta["git_sha"],
        f"trace_every = {meta['params']['trace_every']}",
    ):
        assert needle in snap["meta"], needle
    # the scalings, computed over the whole run (docs/architecture.md, "The picture")
    x = doc["frames"]["x"]
    i_peak = max(range(n), key=lambda i: abs(x[i]))
    run = doc["geometry"]["run_length_m"]
    sc = snap["scaling"]
    assert sc["iPeak"] == i_peak and sc["tPeak"] == doc["frames"]["t"][i_peak]
    assert sc["exag"] == pytest.approx(0.1 * run / abs(x[i_peak]), rel=1e-12)
    st = snap["state"]
    assert (st["iStart"], st["iEnd"]) == (0, n - 1)  # whole run by default
    assert st["stride"] == max(1, -(-(n - 1) // 398))  # the automatic stride (400 frames)
    if "cells" in doc:
        p = doc["cells"]["p"]["data"]
        v = doc["cells"]["v"]["data"]
        p_scale, p_rise = max(abs(q) for q in p), max(p)
        assert sc["pScale"] == pytest.approx(p_scale, rel=1e-12)
        assert sc["kP"] == pytest.approx(p_scale / p_rise, rel=1e-12)
        assert sc["vScale"] == pytest.approx(max(abs(q) for q in v), rel=1e-12)
        assert snap["colorbar_title"] == "relative fluid velocity (JC arrays)"
    else:
        assert sc["kP"] == 1.0 and sc["vScale"] == 1.0 and snap["colorbar_title"] is None


@pytest.mark.parametrize(
    ("base", "bad"),
    [
        ("example_lumped_step.json", {"schema_version": 99}),
        ("example_lumped_step.json", {"kind": "surge"}),
        ("reference_sweep.json", {"schema_version": 1}),  # the thirty-column W.1 layout
    ],
)
def test_rejects_unknown_schema_or_kind(browser, tmp_path, base, bad):
    """A file with an unknown ``schema_version`` or ``kind`` (a sweep at the W.1 schema 1
    included) is refused with a message that names what was found and what the viewer reads;
    nothing is plotted."""
    doc = read_data(base)
    doc.update(bad)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    page, requests, errors = open_viewer(browser)
    snap = load(page, path)
    sweep = page.evaluate(SWEEP_SNAPSHOT_JS)
    print(f"{bad}: {snap['message']!r}")
    page.close()
    assert_no_network(requests, errors)
    assert snap["message_class"] == "error" and snap["n_data"] == 0
    assert not sweep["open"] and sweep["sweep_class"] == ""
    ((key, value),) = bad.items()
    assert f"{key} {json.dumps(value)}" in snap["message"]
    assert (
        'reads kind "trace" at schema_version 1 and kind "sweep" at schema_version 2'
        in (snap["message"])
    )


# ------------------------------------------------------------------ playback


@pytest.mark.parametrize("name", ["example_jc_step.json", "golden_r096_jc.json.gz"])
def test_play_keeps_friction_trace_and_svg_group(browser, name):
    """2 s of play: the frame index advances, the data model keeps its six traces, and the
    friction trace's SVG group (its ``g.trace``, the ``g`` elements inside, its line path) is
    the same before and after and non-zero (the V.2e failure mode)."""
    page, requests, errors = open_viewer(browser)
    before = load(page, DATA / name)
    groups0 = page.evaluate(FRICTION_GROUPS_JS)
    page.click("#play")
    page.wait_for_timeout(PLAY_MS)
    page.click("#pause")
    page.wait_for_timeout(200)
    after = page.evaluate(SNAPSHOT_JS)
    groups1 = page.evaluate(FRICTION_GROUPS_JS)
    page.close()
    print(
        f"{name}: frame {before['state']['cur']} -> {after['state']['cur']}, "
        f"{after['state']['shown']} frames shown; friction groups {groups0} -> {groups1}"
    )
    assert_no_network(requests, errors)
    assert after["state"]["cur"] > before["state"]["cur"], "the animation did not run"
    assert after["n_data"] == before["n_data"] == N_TRACES
    assert after["names"][FRICTION] == before["names"][FRICTION]
    assert after["n_points"][FRICTION] == before["n_points"][FRICTION]
    assert groups0["groups"] == 1 and groups0["lines"] == 1, groups0
    assert groups1 == groups0, f"friction SVG groups changed on play: {groups0} -> {groups1}"


def test_window_keeps_frames_inside(browser):
    """A ``t_start`` / ``t_end`` window: the frame range follows it, the window shade appears on
    Panel 2 (which keeps the whole run), and every frame shown while playing lies inside."""
    page, requests, errors = open_viewer(browser)
    snap = load(page, DATA / "example_jc_step.json")
    t = read_data("example_jc_step.json")["frames"]["t"]
    t0, t1 = 0.5, 1.0
    set_value(page, "#t0", str(t0))
    set_value(page, "#t1", str(t1))
    page.wait_for_timeout(200)
    st = page.evaluate("() => window.viewer.state")
    shade = page.evaluate(
        "() => { const gd = document.getElementById('plot'); const s = gd.layout.shapes[window.viewer.scaling().windowShape];"
        " return [s.visible, s.x0, s.x1, gd.layout.xaxis2.range]; }"
    )
    page.click("#play")
    page.wait_for_timeout(1500)
    page.click("#pause")
    page.wait_for_timeout(200)
    after = page.evaluate("() => window.viewer.state")
    page.close()
    shown = after["shownT"]
    print(
        f"window {t0}..{t1}: frames {st['iStart']}..{st['iEnd']}, shade {shade}, {len(shown)} frames shown, t = {shown[:3]} .. {shown[-3:]}"
    )
    assert_no_network(requests, errors)
    assert t[st["iStart"]] >= t0 > t[st["iStart"] - 1]
    assert t[st["iEnd"]] <= t1 < t[st["iEnd"] + 1]
    assert shade[0] is True and shade[1] == t[st["iStart"]] and shade[2] == t[st["iEnd"]]
    assert shade[3] == [t[0], t[-1]]  # Panel 2 keeps the whole run
    assert len(shown) >= 5 and all(t0 <= tt <= t1 for tt in shown), shown
    assert snap["state"]["iEnd"] == len(t) - 1  # was the whole run before the window


def test_speed_4x_advances_more_frames_than_1x(browser):
    """Over the same wall time, 4x advances the frame index further than 1x (at least twice as
    far: the loop computes the frame due from the elapsed time, so a slow render skips frames
    rather than slowing the clock)."""
    page, requests, errors = open_viewer(browser)
    load(page, DATA / "example_jc_step.json")
    set_value(page, "#stride", "1")

    def advance(speed_button: str) -> int:
        page.evaluate("() => window.viewer.show(0)")
        page.wait_for_timeout(200)
        page.click(f'#speed-buttons button[data-speed="{speed_button}"]')
        page.click("#play")
        page.wait_for_timeout(1500)
        page.click("#pause")
        page.wait_for_timeout(100)
        return page.evaluate("() => window.viewer.state.cur")

    d1 = advance("1")
    d4 = advance("4")
    speed_box = page.input_value("#speed")
    page.close()
    print(f"frames advanced in 1.5 s: 1x {d1}, 4x {d4}; speed box {speed_box}")
    assert_no_network(requests, errors)
    assert speed_box == "4"
    assert 20 <= d1 <= 60, d1  # 1.5 s at 40 ms a frame, stride 1, with timing slack
    assert d4 > d1 and d4 >= 2 * d1, (d1, d4)


# ------------------------------------------------------------------ settings


def test_settings_persist_across_reload(browser):
    """The speed and the overrides typed into the page come back after a reload."""
    page, requests, errors = open_viewer(browser)
    load(page, DATA / "example_lumped_step.json")  # the controls show once a file is open
    page.click('#speed-buttons button[data-speed="2"]')
    set_value(page, "#exag", "1.5")
    page.reload()
    page.wait_for_function(READY_JS, timeout=60_000)
    values = (page.input_value("#speed"), page.input_value("#exag"), page.inner_text("#store-note"))
    page.evaluate("() => window.localStorage.clear()")
    page.close()
    print(f"after reload: speed {values[0]}, exaggeration {values[1]}, note {values[2]!r}")
    assert values[:2] == ("2", "1.5")
    assert values[2] == "settings remembered in this browser"


def test_works_with_storage_blocked(browser):
    """With ``localStorage`` throwing on every access the page still loads and plays a file."""
    block = """
    Object.defineProperty(window, 'localStorage', {get() { throw new Error('storage blocked'); }});
    """
    page, requests, errors = open_viewer(browser, init_script=block)
    note = page.inner_text("#store-note")
    snap = load(page, DATA / "example_lumped_step.json")
    page.click('#speed-buttons button[data-speed="2"]')
    page.click("#play")
    page.wait_for_timeout(800)
    page.click("#pause")
    cur = page.evaluate("() => window.viewer.state.cur")
    page.close()
    print(f"storage blocked: note {note!r}, {snap['n_data']} traces, frame {cur} after play")
    assert_no_network(requests, errors)
    assert note == "settings not remembered (storage unavailable)"
    assert snap["n_data"] == N_TRACES and cur > 0


# ------------------------------------------------------------------ sweep mode (W.3)


@pytest.mark.parametrize("name", SWEEP_FILES)
def test_sweep_opens_with_reference_badge(browser, name):
    """A sweep file opens in sweep mode (the trace plot empty, the sweep section shown, the
    meta listing rows, source and git sha), the five filters carry the file's distinct values
    with the documented defaults, and the badge is green for the reference file (the three
    JC golden rows reproduce their Excel values: 6 values within rtol) and neutral for Tier 1
    (none of the six reference cases is among its rows)."""
    page, requests, errors = open_viewer(browser)
    snap = load_sweep(page, DATA / name)
    page.close()
    assert_no_network(requests, errors)
    doc = read_data(name)
    cols = doc["columns"]
    print(
        f"{name}: badge {snap['badge_class']!r} {snap['badge']!r}\n  {snap['badge_detail'][:300]!r}"
    )
    assert snap["open"] and snap["message"] == "" and snap["trace_plot_traces"] == 0
    assert snap["body_class"] == "sweep" and snap["sweep_class"] == "on"
    for needle in (
        str(doc["meta"]["n_rows"]),
        doc["meta"]["source"],
        doc["meta"]["git_sha"],
        doc["regen"]["template"],
    ):
        assert needle in snap["meta"], needle
    # the filters
    assert set(snap["selects"]) == set(FILTER_COLS)
    for col in FILTER_COLS:
        assert snap["selects"][col]["options"] == ["all"] + [
            js_key(v) for v in distinct(cols, col)
        ], col
    assert snap["filters"] == default_filters(doc)
    # the badge: the entries that have a row of the same case_id, column by column
    ref = doc["reference"]["example_cases"] + doc["reference"]["jc_golden_rows"]
    present = [e for e in ref if e["case_id"] in cols["case_id"]]
    if name == "reference_sweep.json":
        assert [e["case_id"] for e in present] == [
            "r096_jc_L24_f3",
            "r097_jc_L24_f7.5",
            "r098_jc_L24_f22",
        ]
        assert snap["badge_class"] == "badge green"
        assert (
            f"{len(present)} of {len(ref)} reference cases among the rows, 6 values within tolerance"
            in snap["badge"]
        )
        for e in present:
            assert f"{e['case_id']} (pass)" in snap["badge_detail"]
        assert (
            "not among the rows: example_pressure, example_lumped, example_jc"
            in snap["badge_detail"]
        )
    else:
        assert present == []
        assert snap["badge_class"] == "badge neutral"
        assert f"none of the {len(ref)} reference cases is among the rows" in snap["badge"]


def test_sweep_badge_red_on_tampered_reference(browser, tmp_path):
    """One Excel value of the reference block moved by 1e-6 relative (rtol is 5e-12): the badge
    turns red and names the case, the column and the relative error."""
    doc = read_data("reference_sweep.json")
    entry = doc["reference"]["jc_golden_rows"][0]
    entry["excel_values"][0] *= 1 + 1e-6
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    page, requests, errors = open_viewer(browser)
    snap = load_sweep(page, path)
    page.close()
    assert_no_network(requests, errors)
    print(f"tampered: {snap['badge']!r} / {snap['badge_detail']!r}")
    assert snap["badge_class"] == "badge red"
    assert "NOT reproduced: 1 of 6 values outside tolerance" in snap["badge"]
    assert f"{entry['case_id']} f_eq_jc (rel 1.0e-6 > rtol)" in snap["badge_detail"]
    assert "reference NOT reproduced" in snap["meta"]


@pytest.mark.parametrize("name", SWEEP_FILES)
def test_sweep_tabs_render(browser, name):
    """Each tab draws exactly the traces and points the file's columns and the default filters
    imply (``expected_counts`` replicates the grouping: curve families one trace per size panel,
    length and solver; collapse the same per history panel for the two normalisations; JC
    effect one trace per history type), with no page error. For the reference file only the
    raw ``f_eq`` tab has values (its normalised and ratio columns are null) and the other tabs
    say so."""
    page, requests, errors = open_viewer(browser)
    load_sweep(page, DATA / name)
    doc = read_data(name)
    filters = default_filters(doc)
    snaps = {tab: click_tab(page, tab) for tab in SWEEP_TABS}
    ARTIFACTS.mkdir(exist_ok=True)
    stem = name.split(".")[0]
    for tab in SWEEP_TABS:
        click_tab(page, tab)
        page.screenshot(path=str(ARTIFACTS / f"viewer_{stem}_{tab}.png"), full_page=True)
    page.close()
    assert_no_network(requests, errors)
    for tab, snap in snaps.items():
        exp = expected_counts(doc, tab, filters)
        print(
            f"{name} {tab}: {snap['n_data']} traces, {snap['n_points']} points (expected {exp}); {snap['hint']!r}"
        )
        assert snap["tab"] == tab and snap["message"] == ""
        assert (snap["n_data"], snap["n_points"]) == exp
        # an SVG group per drawn trace (plotly draws none for an empty one) plus, on the
        # JC-effect tab, the status text
        assert snap["n_data"] * (exp[1] > 0) <= snap["groups"] <= snap["n_data"] + (tab == "effect")
        assert (snap["counts"]["traces"], snap["counts"]["points"]) == exp
        assert snap["counts"]["rows"] == len(
            filtered_rows(
                doc, filters, open_cols=("amplitude_fraction",) if tab == "effect" else ()
            )
        )
        assert (
            f"{snap['counts']['rows']} of {doc['meta']['n_rows']} rows pass the filters"
            in snap["hint"]
        )
        assert ("nothing to plot" in snap["hint"]) == (exp[1] == 0)
        assert (snap["controls_class"] == "on") == (tab == "effect")
    if name == "tier1_sweep.json":
        assert all(snap["n_points"] > 0 for snap in snaps.values())
        assert (
            snaps["curves"]["n_data"] == 20 and snaps["collapse"]["n_data"] == 40
        )  # 2 sizes x 5 lengths x 2 solvers (x 2 rows)
        assert set(snaps["curves"]["axes"]) == {"xy", "x2y2"}  # one panel per size
        assert len(set(snaps["collapse"]["axes"])) == 2  # one history type x two rows
        assert sum(n.endswith(" JC") for n in snaps["curves"]["names"]) == 10
    else:
        assert (
            snaps["curves"]["n_data"] == 5 and snaps["curves"]["n_points"] == 75
        )  # the lumped golden rows
        assert snaps["effect"]["n_points"] == 0 and snaps["collapse"]["n_data"] == 0


def test_sweep_filters_change_trace_counts(browser):
    """Tier 1: opening ``history_type`` multiplies the collapse panels and the JC-effect series;
    on the curve tab a sine-frequency filter cuts the per-length families; every count matches
    ``expected_counts`` for the filters set."""
    page, requests, errors = open_viewer(browser)
    load_sweep(page, DATA / "tier1_sweep.json")
    doc = read_data("tier1_sweep.json")
    f = default_filters(doc)
    seen = []

    def check(tab, snap, **kw):
        exp = expected_counts(doc, tab, f, **kw)
        seen.append((tab, dict(f), snap["n_data"], snap["n_points"], exp))
        assert (snap["n_data"], snap["n_points"]) == exp, seen[-1]
        return snap["n_data"]

    click_tab(page, "collapse")
    c_step = check("collapse", sweep_snapshot(page))
    f["history_type"] = "all"
    c_all = check("collapse", select_filter(page, "history_type", "all"))
    assert (
        c_all > c_step and len(set(sweep_snapshot(page)["axes"])) == 6
    )  # 3 history panels x 2 rows
    click_tab(page, "effect")
    e_all = check("effect", sweep_snapshot(page))
    f["history_type"] = "step"
    e_step = check("effect", select_filter(page, "history_type", "step"))
    assert e_all == 3 and e_step == 1
    click_tab(page, "curves")
    f["history_type"] = "step_sine"
    k_sine = check("curves", select_filter(page, "history_type", "step_sine"))
    f["f_osc_hz"] = "4"
    k_sine4 = check("curves", select_filter(page, "f_osc_hz", "4"))
    assert k_sine == 3 * k_sine4 == 60  # the three sine frequencies were separate families
    page.select_option("#y1", "daf")
    k_daf = check("curves", sweep_snapshot(page), y1="daf")
    assert k_daf == k_sine4
    f["f_osc_hz"] = "16"
    f["history_type"] = "step"
    select_filter(page, "f_osc_hz", "16")
    empty = select_filter(page, "history_type", "step")  # no step row has a sine frequency
    check("curves", empty, y1="daf")
    page.close()
    assert_no_network(requests, errors)
    for row in seen:
        print(row)
    assert empty["n_data"] == 0 and "nothing to plot" in empty["hint"]


def test_sweep_effect_animation(browser):
    """The JC-effect tab animates over the amplitude fractions through the page's play button:
    two frames (0.25, 1), the slider spans them, play advances to the last one within its
    1 s period and shows the rows of that amplitude; switching the animated variable to ``mu``
    re-frames over the frictions and opens the ``mu`` filter while locking it."""
    page, requests, errors = open_viewer(browser)
    load_sweep(page, DATA / "tier1_sweep.json")
    doc = read_data("tier1_sweep.json")
    cols = doc["columns"]
    snap0 = click_tab(page, "effect")
    page.click('#speed-buttons button[data-speed="1"]')
    page.click("#play")
    page.wait_for_timeout(SWEEP_FRAME_MS + 600)
    snap1 = sweep_snapshot(page)
    pts1 = page.evaluate("() => document.getElementById('splot').data[0].customdata.length")
    page.select_option("#anim", "mu")
    snap_mu = sweep_snapshot(page)
    page.close()
    assert_no_network(requests, errors)
    print(
        f"frames {snap0['anim']} -> {snap1['anim']}; readout {snap1['readout']!r}; mu {snap_mu['anim']}"
    )
    assert snap0["anim"] == {"cur": 0, "n": 2, "values": [0.25, 1]} and snap0["slider_max"] == "1"
    assert "amplitude_fraction = 0.25" in snap0["readout"]
    assert (
        snap0["selects"]["amplitude_fraction"]["disabled"]
        and not snap0["selects"]["mu"]["disabled"]
    )
    assert snap1["anim"]["cur"] == 1 and "amplitude_fraction = 1" in snap1["readout"]
    f = default_filters(doc)
    f["amplitude_fraction"] = "1"
    rows_a1 = [i for i in filtered_rows(doc, f) if cols["ratio_f_eq"][i] is not None]
    assert pts1 == len(rows_a1) == 80
    assert snap_mu["anim"]["values"] == [0.0001, 0.3] and snap_mu["anim"]["cur"] == 0
    assert "mu = 0.0001" in snap_mu["readout"]
    assert (
        snap_mu["selects"]["mu"]["disabled"]
        and not snap_mu["selects"]["amplitude_fraction"]["disabled"]
    )
    assert (snap_mu["n_data"], snap_mu["n_points"]) == expected_counts(
        doc, "effect", default_filters(doc), anim="mu"
    )


@pytest.mark.parametrize("name", SWEEP_FILES)
def test_sweep_hover_fills_row_and_regen_command(browser, name):
    """Hovering a point fills the row panel with every column of that row (72 names, the values
    as the file holds them, nulls marked) and the regenerate button shows the file's template
    formatted with the row (the reference file's ``--golden {case_id}`` command; Tier 1's
    whole-tier rerun, as its note says)."""
    page, requests, errors = open_viewer(browser)
    load_sweep(page, DATA / name)
    doc = read_data(name)
    cols = doc["columns"]
    before = sweep_snapshot(page)
    page.click("#regen")
    no_row = sweep_snapshot(page)
    snap = hover_first_point(page)
    page.click("#regen")
    after = sweep_snapshot(page)
    i = page.evaluate("() => window.viewer.sweep().row")
    page.close()
    assert_no_network(requests, errors)
    print(
        f"{name}: hovered row {i} {cols['case_id'][i]}; command {after['regen_cmd']!r}; note {after['regen_note'][:60]!r}"
    )
    assert before["row_names"] == [] and no_row["regen_note"] == "hover a point first"
    assert i >= 0 and snap["row_title"] == f"row {i}: {cols['case_id'][i]}"
    assert snap["row_names"] == list(cols)
    assert snap["row_values"] == [
        "null" if cols[c][i] is None else js_key(cols[c][i]) for c in cols
    ]
    assert after["regen_cmd"] == format_template(doc["regen"]["template"], cols, i)
    assert after["regen_note"].startswith(
        ("copied to the clipboard. ", "select the command to copy it. ")
    )
    assert after["regen_note"].endswith(doc["regen"]["note"])
    if name == "reference_sweep.json":
        assert (
            after["regen_cmd"]
            == f"python tools/export.py trace --golden {cols['case_id'][i]} --out {cols['case_id'][i]}.json"
        )
    else:
        assert after["regen_cmd"] == "python tools/sweep_jc.py run --tier 1"


def test_sweep_and_trace_modes_switch(browser):
    """A sweep file after a trace file and a trace file after a sweep file: each mode closes the
    other (the trace plot's six traces go and come back, the sweep section and the body class
    with it, the play controls serve the mode open)."""
    page, requests, errors = open_viewer(browser)
    trace1 = load(page, DATA / "example_lumped_step.json")
    sweep = load_sweep(page, DATA / "reference_sweep.json")
    click_tab(page, "effect")
    trace2 = load(page, DATA / "example_lumped_step.json")
    closed = page.evaluate(SWEEP_SNAPSHOT_JS)
    page.click("#play")
    page.wait_for_timeout(500)
    page.click("#pause")
    cur = page.evaluate("() => window.viewer.state.cur")
    page.close()
    assert_no_network(requests, errors)
    print(
        f"trace {trace1['n_data']} -> sweep {sweep['n_data']} -> trace {trace2['n_data']}; frame {cur} after play"
    )
    assert trace1["n_data"] == N_TRACES and trace2["n_data"] == N_TRACES
    assert sweep["open"] and sweep["trace_plot_traces"] == 0 and sweep["body_class"] == "sweep"
    assert not closed["open"] and closed["sweep_class"] == "" and closed["body_class"] == ""
    assert closed["n_data"] == 0 and closed["controls_class"] == "on"
    assert cur > 0


# ------------------------------------------------------------------ screenshots for review


@pytest.mark.parametrize("name", SCREENSHOT_FILES)
def test_screenshots_at_peak(browser, name):
    """For the owner's review (no pixel check): the viewer at the frame of peak |x| ("jump to
    peak"), full-page, in ``tests/.artifacts/``."""
    ARTIFACTS.mkdir(exist_ok=True)
    stem = name.split(".")[0]
    page, requests, errors = open_viewer(browser)
    load(page, DATA / name)
    page.click("#peak")
    page.wait_for_timeout(500)
    st = page.evaluate("() => [window.viewer.state.cur, window.viewer.scaling().tPeak]")
    page.screenshot(path=str(ARTIFACTS / f"viewer_{stem}_peak.png"), full_page=True)
    page.close()
    assert_no_network(requests, errors)
    print(
        f"{name}: viewer frame {st[0]} at the peak t = {st[1]:.4f} s -> "
        f"{ARTIFACTS / f'viewer_{stem}_peak.png'}"
    )
    assert st[1] > 0.0
