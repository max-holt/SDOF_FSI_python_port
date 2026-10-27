"""Browser tests of the single-file results viewer ``docs/viewer/viewer.html`` (Session W.2),
on the Playwright / headless Chromium harness of ``tests/test_viz_motion.py`` (same browser
fixture and skip rules: no ``playwright`` package or no browser skips the module).

Every page the tests open records each request the browser makes; anything but the page's own
``file:`` URL fails the test (the viewer makes no network request of any kind). The W.1
data files in ``docs/viz/data/`` are loaded through the file input; the three trace files
must render the six traces of ``viz/animate.py`` on the two panels with the scalings the file
implies, the sweep file must show the W.3 message. Playback is exercised (friction trace and
its SVG group survive 2 s of play; a time window keeps every shown frame inside it; 4x advances
more frames than 1x over the same wall time), a ``schema_version: 99`` file must be rejected
with a readable message, settings must persist and the page must work with storage blocked.
``test_build_reproduces_committed_page`` needs no browser: the committed page is byte-identical
to ``tools/build_viewer.py``'s output with the installed plotly bundle.

Screenshots of the viewer at the peak-|x| frame go to ``tests/.artifacts/`` (not committed)
for the owner's review; no pixel comparison is made. (Until Session F-4b the matching plotly
page under ``docs/viz/`` was screenshotted alongside; those pages are deleted.)
"""

from __future__ import annotations

import gzip
import json
import pathlib
import sys

import pytest

pytest.importorskip("playwright.sync_api")
plotly = pytest.importorskip("plotly")

import test_viz_motion as motion  # noqa: E402  (the harness: browser fixture, page loader)

browser = motion.browser  # the module-scoped fixture, re-exported so pytest finds it here

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_viewer  # noqa: E402

VIEWER = ROOT / "docs" / "viewer" / "viewer.html"
VIEWER_SRC = ROOT / "docs" / "viewer" / "viewer.src.html"
DATA = ROOT / "docs" / "viz" / "data"
ARTIFACTS = motion.ARTIFACTS
TRACE_FILES = ["example_jc_step.json", "example_lumped_step.json", "golden_r096_jc.json.gz"]
SWEEP_FILE = "reference_sweep.json"
# the two JC trace files, screenshotted at their peak
SCREENSHOT_FILES = ["example_jc_step.json", "golden_r096_jc.json.gz"]
N_TRACES = 6
CENTRELINE, CELLS, FRICTION, UNBALANCE, CURSOR, STATUS = 0, 1, 2, 3, 4, 5
PLAY_MS = 2000
LOAD_TIMEOUT_MS = 180_000  # the gzipped row 96 file inflates to 47 MB of JSON

READY_JS = "() => !!(window.viewer && window.Plotly && window.pako)"
# a load has finished when the trace is open and drawn, or a message (error / sweep) is shown
LOADED_JS = """
() => (!!window.viewer.data() && document.querySelectorAll('#plot g.trace').length > 0)
      || document.getElementById('message').className !== ''
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


@pytest.mark.parametrize("name", TRACE_FILES + [SWEEP_FILE])
def test_loads_each_data_file(browser, name):
    """Each W.1 data file through the file input: a trace file renders the six traces of the
    plotly pages on the two panels (the friction on the right axis) with the scalings the file
    implies; the sweep file shows the W.3 message and no plot; no request leaves the page."""
    page, requests, errors = open_viewer(browser)
    snap = load(page, DATA / name)
    doc = read_data(name)
    print(f"{name}: {snap['n_data']} traces, groups {snap['groups']}, subplots {snap['subplots']}")
    print(f"  message: {snap['message'][:200]!r}")
    page.close()
    assert_no_network(requests, errors)
    if doc["kind"] == "sweep":
        assert snap["n_data"] == 0 and snap["groups"] == 0
        assert snap["message_class"] == "info" and "Session W.3" in snap["message"]
        assert str(doc["meta"]["n_rows"]) in snap["message"]
        return
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
    # the scalings, as animate.build_figure computes them over the whole run
    x = doc["frames"]["x"]
    i_peak = max(range(n), key=lambda i: abs(x[i]))
    run = doc["geometry"]["run_length_m"]
    sc = snap["scaling"]
    assert sc["iPeak"] == i_peak and sc["tPeak"] == doc["frames"]["t"][i_peak]
    assert sc["exag"] == pytest.approx(0.1 * run / abs(x[i_peak]), rel=1e-12)
    st = snap["state"]
    assert (st["iStart"], st["iEnd"]) == (0, n - 1)  # whole run by default
    assert st["stride"] == max(1, -(-(n - 1) // 398))  # select_frames' stride
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


@pytest.mark.parametrize("bad", [{"schema_version": 99}, {"kind": "surge"}])
def test_rejects_unknown_schema_or_kind(browser, tmp_path, bad):
    """A file with an unknown ``schema_version`` or ``kind`` is refused with a message that names
    what was found and what the viewer reads; nothing is plotted."""
    doc = read_data("example_lumped_step.json")
    doc.update(bad)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    page, requests, errors = open_viewer(browser)
    snap = load(page, path)
    print(f"{bad}: {snap['message']!r}")
    page.close()
    assert_no_network(requests, errors)
    assert snap["message_class"] == "error" and snap["n_data"] == 0
    ((key, value),) = bad.items()
    assert f"{key} {json.dumps(value)}" in snap["message"]
    assert 'reads kind "trace" or "sweep" at schema_version 1' in snap["message"]


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
