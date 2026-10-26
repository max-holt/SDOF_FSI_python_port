"""Build the single-file results viewer: ``tools/build_viewer.py [--out docs/viewer/viewer.html]``.

``docs/viewer/viewer.src.html`` is the hand-written page (all CSS and JS inline). It carries two
markers, ``<!-- @inline plotly -->`` and ``<!-- @inline pako -->``; this script replaces each with
a ``<script>`` element holding the library verbatim, preceded by a comment that records the
library, its version and where the bytes came from, and writes the self-contained page. Nothing
is fetched: plotly.js is read from the installed ``plotly`` Python package
(``plotly/package_data/plotly.min.js``, the same file the motion tests serve in place of the
CDN) and pako's inflate-only build from the copy vendored in ``tools/viewer/`` (MIT, licence
file beside it). ``tests/test_viewer.py`` rebuilds the page and asserts it is byte-identical to
the committed ``docs/viewer/viewer.html``, so the two cannot drift apart.

Session W.2 note: the installed package ships the *full* plotly.js bundle only (4.8 MB); when a
copy of the ``basic`` partial bundle of the same version is available offline, pass it with
``--plotly`` and the page shrinks to about 1 MB with no other change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "viewer" / "viewer.src.html"
OUT = ROOT / "docs" / "viewer" / "viewer.html"
PAKO = ROOT / "tools" / "viewer" / "pako_inflate.min.js"
PAKO_LICENSE = ROOT / "tools" / "viewer" / "pako_LICENSE"
# The vendored pako build carries no version header (the minified file strips it); the version
# is pinned here against the file's digest (pako 1.0.11, dist/pako_inflate.min.js, unmodified).
PAKO_VERSION = "1.0.11"
PAKO_SHA256 = "2ca27e9a8dae569cdeac42752ed1aed1afeff7f19282d3cc12c0aaa54a08bc04"
MARKER = "<!-- @inline {name} -->"


def plotly_bundle_path() -> Path:
    """The plotly.js bundle shipped with the installed ``plotly`` package."""
    import plotly

    return Path(plotly.__file__).parent / "package_data" / "plotly.min.js"


def plotly_version(bundle: bytes) -> str:
    """The ``plotly.js vX.Y.Z`` header of a bundle (``ValueError`` when absent)."""
    m = re.search(rb"plotly\.js v([\d.]+)", bundle[:400])
    if not m:
        raise ValueError("the plotly bundle has no 'plotly.js vX.Y.Z' header")
    return m.group(1).decode()


def pako_version(bundle: bytes) -> str:
    """``PAKO_VERSION`` when ``bundle`` is the pinned file (``ValueError`` otherwise)."""
    digest = hashlib.sha256(bundle).hexdigest()
    if digest != PAKO_SHA256:
        raise ValueError(f"pako bundle sha256 {digest} is not the pinned {PAKO_SHA256}")
    return PAKO_VERSION


def _script(comment: str, body: bytes) -> bytes:
    if b"</script" in body.lower():
        raise ValueError("a library contains '</script' and cannot be inlined")
    return b"<script>\n/* " + comment.encode() + b" */\n" + body.rstrip(b"\n") + b"\n</script>"


def build(src: bytes, plotly_js: bytes, pako_js: bytes, plotly_origin: str) -> bytes:
    """The page bytes: ``src`` with the two markers replaced (each must occur exactly once)."""
    import plotly

    pv = plotly_version(plotly_js)
    kv = pako_version(pako_js)
    licence = PAKO_LICENSE.read_text(encoding="utf-8").strip()
    parts = {
        "plotly": _script(
            f"plotly.js v{pv} (MIT, Copyright 2012-2026 Plotly, Inc.), {len(plotly_js)} bytes, "
            f"copied by tools/build_viewer.py from {plotly_origin} (the plotly Python package "
            f"{plotly.__version__}); never loaded from the network",
            plotly_js,
        ),
        "pako": _script(
            f"pako {kv} inflate-only build (nodeca/pako), {len(pako_js)} bytes, vendored in "
            f"tools/viewer/pako_inflate.min.js; used to inflate .json.gz files in the page.\n"
            + licence,
            pako_js,
        ),
    }
    out = src
    for name, block in parts.items():
        marker = MARKER.format(name=name).encode()
        if out.count(marker) != 1:
            raise ValueError(f"viewer.src.html must contain {marker!r} exactly once")
        out = out.replace(marker, block)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument(
        "--plotly",
        type=Path,
        help="plotly.js bundle to inline (default: the installed plotly package's plotly.min.js)",
    )
    ap.add_argument("--pako", type=Path, default=PAKO)
    args = ap.parse_args(argv)
    plotly_path = args.plotly or plotly_bundle_path()
    origin = (
        "plotly/package_data/plotly.min.js"
        if args.plotly is None
        else f"--plotly {plotly_path.name}"
    )
    page = build(args.src.read_bytes(), plotly_path.read_bytes(), args.pako.read_bytes(), origin)
    args.out.write_bytes(page)
    info = {
        "out": str(args.out),
        "bytes": len(page),
        "plotly": str(plotly_path),
        "plotly_version": plotly_version(plotly_path.read_bytes()),
        "pako": str(args.pako),
    }
    print(json.dumps(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
