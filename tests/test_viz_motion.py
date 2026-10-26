"""Browser-level diagnosis of the animation pages under ``docs/viz/`` (Playwright, headless
Chromium): what the page does when it is actually played, which ``tests/test_viz.py`` cannot
see (it checks the figure object, not plotly.js).

Session V.2e (2026-10-25, diagnosis only): the lead author reports the friction line (Panel
2, right axis) vanishing when the page is played. ``test_play_keeps_friction_trace`` presses
the page's injected play button and compares the trace table (``gd.data``, the frames'
``traces`` lists) and the rendered SVG before and after 2 s of playback;
``test_first_animated_frame_keeps_every_trace_group`` pins which frame removes which trace
group; ``test_golden_r096_frames_inside_window`` reports the row 96 page's frame span against
its trace span and the time window it was written with.

Requirements: the ``playwright`` package (``uv pip install playwright``, no ``playwright
install``: the browser is read from ``/opt/pw-browsers`` or ``PLAYWRIGHT_BROWSERS_PATH``) and
the ``viz`` extra. The pages load plotly.js from the CDN; the test serves the copy bundled
with the installed ``plotly`` package instead (same version the page names), so it runs
offline and against a known plotly.js. Screenshots go to ``tests/.artifacts/`` (not
committed).
"""

from __future__ import annotations

import glob
import os
import pathlib
import re

import pytest

pytest.importorskip("playwright.sync_api")
plotly = pytest.importorskip("plotly")  # the ``viz`` extra, also the source of plotly.min.js

from playwright.sync_api import Error as PlaywrightError  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
VIZ = ROOT / "docs" / "viz"
ARTIFACTS = pathlib.Path(__file__).parent / ".artifacts"
PLOTLY_JS = pathlib.Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
CHROMIUM = sorted(glob.glob(f"{BROWSERS}/chromium-*/chrome-linux/chrome"))
PLAY_MS = 2000
# trace indices written by ``animate.build_figure`` (``fig._surge_sdof_animation``)
CENTRELINE, CIRCLES, FRICTION, UNBALANCE, CURSOR, STATUS = 0, 1, 2, 3, 4, 5
NAMES = ["centreline", "cells", "friction", "unbalance", "cursor", "status"]

# One snapshot of the live figure: the data model (``gd.data``), the frames and the SVG.
# plotly.py writes numeric arrays as base64 typed arrays (``{dtype, bdata}``), decoded here.
SNAPSHOT_JS = """
() => {
  const gd = document.querySelector('.plotly-graph-div');
  const dec = (a) => {
    if (!a) return null;
    if (Array.isArray(a) || ArrayBuffer.isView(a)) return Array.from(a);
    if (a.bdata) {
      const u = Uint8Array.from(atob(a.bdata), c => c.charCodeAt(0));
      const T = {f4: Float32Array, f8: Float64Array, i4: Int32Array, i2: Int16Array,
                 i1: Int8Array, u1: Uint8Array}[a.dtype];
      return Array.from(new T(u.buffer));
    }
    return null;
  };
  const frames = (gd._transitionData && gd._transitionData._frames) || [];
  const t_unb = dec(gd.data[UNBALANCE].x);
  return {
    n_data: gd.data.length,
    traces: gd.data.map((t, i) => {
      const full = gd._fullData[i];
      const g = full ? gd.querySelector('g.trace.scatter.trace' + full.uid) : null;
      const x = dec(t.x);
      return {index: i, name: t.name, yaxis: t.yaxis || 'y', xaxis: t.xaxis || 'x',
              visible: t.visible === undefined ? true : t.visible,
              n_points: x ? x.length : null, in_dom: !!g,
              layer: g ? g.closest('.subplot').getAttribute('class') : null};
    }),
    n_frames: frames.length,
    frame_traces: frames.map(f => f.traces),
    frame_names: frames.map(f => f.name),
    frame_t: frames.map(f => dec(f.data[1].x)[0]),
    slider_active: gd.layout.sliders ? gd.layout.sliders[0].active : null,
    trace_t: t_unb ? [t_unb[0], t_unb[t_unb.length - 1], t_unb.length] : null,
    trace_gap: t_unb ? t_unb[2] - t_unb[1] : null,  // one traced sample (after the t = 0 row)
    overplot: Array.from(gd.querySelectorAll('.subplot.x2y2 .overplot > g')).map(
      g => g.getAttribute('class') + ': ' + (g.children.length
        ? Array.from(g.children).map(c => c.getAttribute('class')).join(', ') : '(empty)')),
    title: gd.layout.title && gd.layout.title.text,
  };
}
""".replace("UNBALANCE", str(UNBALANCE))

FRAMES_READY_JS = """
() => { const gd = document.querySelector('.plotly-graph-div');
        return !!(gd && gd._transitionData && gd._transitionData._frames
                  && gd._transitionData._frames.length > 0); }
"""
ANIMATE_JS = "(a) => Plotly.animate(document.querySelector('.plotly-graph-div'), a[0], a[1])"
# the options every slider step and the page's buttons use (``animate.py``)
STEP_OPTS = {
    "frame": {"duration": 0, "redraw": False},
    "mode": "immediate",
    "transition": {"duration": 0},
}


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


def load_page(browser, name):
    """Open ``docs/viz/<name>`` with plotly.js served from the installed package, and wait for
    the frames to be registered.  Returns ``(page, page_errors)``."""
    path = VIZ / name
    html = path.read_text(encoding="utf-8")
    cdn = re.search(r'src="(https://cdn\.plot\.ly/plotly-([\d.]+)\.min\.js)"', html)
    assert cdn, f"{name}: no plotly CDN script tag"
    bundled = re.search(rb"plotly\.js v([\d.]+)", PLOTLY_JS.read_bytes()[:400])
    assert bundled and bundled.group(1).decode() == cdn.group(2), (
        f"{name} names plotly.js {cdn.group(2)}, the installed package bundles "
        f"{bundled and bundled.group(1).decode()}"
    )
    page = browser.new_page(viewport={"width": 1300, "height": 1000})
    page.route(
        "https://cdn.plot.ly/**",
        lambda route: route.fulfill(path=str(PLOTLY_JS), content_type="application/javascript"),
    )
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(path.as_uri())
    page.wait_for_function(FRAMES_READY_JS, timeout=60_000)
    return page, errors


def snapshot(page):
    return page.evaluate(SNAPSHOT_JS)


def trace_table(before, after):
    """The before / after trace table as text (printed, and part of the failure message)."""
    head = f"{'i':>2} {'name':<44} {'axis':<6} {'visible':<8} {'points':<7} {'in SVG':<7} layer"
    rows = [head, "-" * len(head)]
    for tag, snap in (("before play", before), ("after play", after)):
        rows.append(
            f"{tag}: len(gd.data) = {snap['n_data']}, slider at frame {snap['slider_active']}"
        )
        for t in snap["traces"]:
            rows.append(
                f"{t['index']:>2} {t['name'][:44]:<44} {t['yaxis']:<6} {str(t['visible']):<8} "
                f"{str(t['n_points']):<7} {str(t['in_dom']):<7} {t['layer']}"
            )
        rows.append(f"   overplot layers: {snap['overplot']}")
    return "\n".join(rows)


def frame_report(snap):
    distinct = sorted({tuple(tr) for tr in snap["frame_traces"]})
    lines = [f"{snap['n_frames']} frames; distinct `traces` lists: {distinct}"]
    for i in range(snap["n_data"]):
        listing = [k for k, tr in enumerate(snap["frame_traces"]) if i in tr]
        lines.append(
            f"  trace {i} ({NAMES[i] if i < len(NAMES) else '?'}): listed by "
            + (
                f"{len(listing)} frames"
                if len(listing) in (0, snap["n_frames"])
                else f"frames {listing[:5]}..."
            )
        )
    return "\n".join(lines)


def test_play_keeps_friction_trace(browser):
    """Press the page's play button, wait 2 s, and compare the trace table and the rendered
    SVG with the loaded state. The friction trace must still be there: same name, same
    length, visible, and drawn."""
    ARTIFACTS.mkdir(exist_ok=True)
    page, errors = load_page(browser, "example_jc_step.html")
    before = snapshot(page)
    page.screenshot(path=str(ARTIFACTS / "example_jc_step_before_play.png"))
    page.click('button[id$="-play"]')
    page.wait_for_timeout(PLAY_MS)
    after = snapshot(page)
    page.screenshot(path=str(ARTIFACTS / "example_jc_step_after_play.png"))
    page.click('button[id$="-pause"]')
    report = trace_table(before, after) + "\n" + frame_report(before) + f"\npage errors: {errors}"
    print(report)
    page.close()

    assert after["slider_active"] > before["slider_active"], "the animation did not run"
    assert after["n_data"] == before["n_data"] == 6
    fr0, fr1 = before["traces"][FRICTION], after["traces"][FRICTION]
    assert fr0["name"].startswith("friction force") and fr0["in_dom"], fr0
    # the data model: unchanged by playback
    assert (fr1["name"], fr1["n_points"], fr1["visible"]) == (
        fr0["name"],
        fr0["n_points"],
        True,
    ), report
    # the rendered figure: the friction line must still be drawn
    assert fr1["in_dom"], "friction trace no longer drawn after play:\n" + report


def test_first_animated_frame_keeps_every_trace_group(browser):
    """One slider step (frame '1', the options every step and button uses) must leave each
    trace's SVG group in place; the report names the trace groups and overlay layers a
    single frame removes."""
    page, errors = load_page(browser, "example_jc_step.html")
    before = snapshot(page)
    page.evaluate(ANIMATE_JS, [["1"], STEP_OPTS])
    page.wait_for_timeout(300)
    after = snapshot(page)
    page.close()
    removed = [
        f"trace {t['index']} ({t['name'][:30]}, {t['yaxis']}) from {t0['layer']}"
        for t0, t in zip(before["traces"], after["traces"], strict=True)
        if t0["in_dom"] and not t["in_dom"]
    ]
    report = (
        f"frame '1' lists traces {before['frame_traces'][1]}; removed from the SVG: {removed}\n"
        f"overplot layers before: {before['overplot']}\nafter:  {after['overplot']}"
    )
    print(report)
    assert after["slider_active"] == 1
    assert not removed, report


def test_golden_r096_frames_inside_window(browser):
    """The row 96 page was written with ``--t-start 6 --t-end 7.5``: every frame lies in the
    window, the frames are one traced sample apart (stride 1), and Panel 2 keeps the whole
    run; the spans are printed."""
    page, errors = load_page(browser, "golden_r096_jc.html")
    snap = snapshot(page)
    page.close()
    title = re.sub(r"<[^>]+>", "", snap["title"])
    window = re.search(r"animated window t = ([\d.]+) to ([\d.]+) s", title)
    stride = int(re.search(r"frame stride (\d+)", title).group(1))
    trace_every = int(re.search(r"trace_every = (\d+)", title).group(1))
    dt = float(re.search(r"dt = ([\d.e+-]+) s", title).group(1))
    ft = snap["frame_t"]
    gaps = [b - a for a, b in zip(ft[:-1], ft[1:], strict=True)]
    t0, t1, n_trace = snap["trace_t"]
    trace_gap = snap["trace_gap"]
    report = "\n".join(
        [
            f"title window: {window.group(0) if window else 'none'}; frame stride {stride}; "
            f"trace_every {trace_every}; dt {dt:g} s (title, 3 s.f.); one traced sample = {trace_gap:.6g} s",
            f"frames: {snap['n_frames']}, t = {ft[0]:.4f} .. {ft[-1]:.4f} s "
            f"(span {ft[-1] - ft[0]:.4f} s), gap min {min(gaps):.5f} max {max(gaps):.5f} s",
            f"trace (Panel 2 unbalance x): {n_trace} points, t = {t0:.4f} .. {t1:.4f} s "
            f"(span {t1 - t0:.4f} s)",
            f"frames outside [6, 7.5] s: {[t for t in ft if not 6.0 <= t <= 7.5]}",
            f"page errors: {errors}",
        ]
    )
    print(report)
    assert window and (float(window.group(1)), float(window.group(2))) == (
        round(ft[0], 3),
        round(ft[-1], 3),
    ), report
    assert all(6.0 <= t <= 7.5 for t in ft), report
    # the cursor x arrays (frame t) are float32, the trace t float64
    assert stride == 1 and max(gaps) == pytest.approx(trace_gap, rel=1e-3), report
    assert trace_gap == pytest.approx(trace_every * dt, rel=5e-3), report  # title dt is rounded
    assert t0 == 0.0 and t1 > 7.5, report  # Panel 2 keeps the whole run
