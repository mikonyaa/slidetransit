"""Bounded standalone HTML with safely embedded data and image bytes."""

from __future__ import annotations

import base64
import json
from importlib.resources import files
from pathlib import Path

from slidetransit.limits import Limits
from slidetransit.models import JSON, TransitError
from slidetransit.report_assets import asset_names, bundle_assets
from slidetransit.report_validation import validate_asset_sizes, validate_report_semantics


def write_report(report: JSON, out: Path, limits: Limits) -> None:
    resources = files("slidetransit").joinpath("assets")
    report_bytes = len(json.dumps(report, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    if report_bytes > limits.report_json_bytes:
        raise TransitError("report JSON exceeds size limit; reduce declared scope")
    validate_report_semantics(report, limits)
    images = {}
    with bundle_assets(out, limits) as assets:
        for name in sorted(asset_names(report)):
            data = assets.read(name)
            if report_bytes + assets.total * 4 / 3 + 2 * 1024 * 1024 > limits.html_bytes:
                raise TransitError("standalone HTML exceeds size limit; reduce scope or DPI")
            images[name] = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
        validate_asset_sizes(report, assets.sizes)
    fonts = {}
    for name in ["NotoSans-Regular.ttf", "LiberationSerif-Regular.ttf"]:
        fonts[name] = "data:font/ttf;base64," + base64.b64encode(
            resources.joinpath(name).read_bytes()
        ).decode("ascii")
    font_licenses = {
        name: files("slidetransit").joinpath("licenses", name).read_text()
        for name in ["Noto-OFL.txt", "Liberation-OFL.txt"]
    }
    payload = (
        json.dumps(
            {"report": report, "images": images, "fontLicenses": font_licenses},
            ensure_ascii=False,
            allow_nan=False,
        )
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    css = resources.joinpath("viewer.css").read_text()
    js = resources.joinpath("viewer.js").read_text()
    font_css = "\n".join(
        f"@font-face{{font-family:'{family}';src:url('{fonts[name]}') format('truetype');font-display:swap}}"
        for name, family in [
            ("NotoSans-Regular.ttf", "Transit Sans"),
            ("LiberationSerif-Regular.ttf", "Transit Serif"),
        ]
    )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>SlideTransit · Export review</title><style>{font_css}\n{css}</style></head>
<body><a class="skip" href="#inspection">Skip to inspection</a>
<header class="masthead"><div class="brand">SlideTransit<span> / EXPORT REVIEW</span></div><button id="download">Download decisions</button></header>
<section class="intro"><div><p class="eyebrow">COMPARE / LOCATE / REVIEW</p><h1 id="headline">Presentation export review.</h1><p id="subline"></p></div><div class="run-status"><span id="status"></span><strong id="count"></strong><small id="mode"></small></div></section>
<div class="workbench"><aside class="rail"><h2>Slides</h2><nav id="slides" aria-label="Slide list"></nav><div class="filters"><h2>Filter evidence</h2><label>Severity<select id="severity"><option value="all">All severities</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option><option value="info">Info</option></select></label><label>Review state<select id="state"><option value="all">All states</option><option value="open">Open</option><option value="accepted">Accepted</option><option value="region-accepted">Region accepted</option></select></label></div><p class="local">Local report.<br>No document upload.<br>Decisions retain evidence.</p></aside>
<main id="inspection" tabindex="-1"><div class="toolbar"><strong id="page-label"></strong><div class="tools"><button id="overlay" aria-pressed="false">Overlay</button><label class="opacity" hidden>Candidate opacity<input id="opacity" type="range" min="0" max="100" value="50"></label><label>Zoom<select id="zoom"><option value="1">Fit</option><option value="1.5">150%</option><option value="2">200%</option><option value="3">300%</option></select></label><label class="mobile-side">View<select id="side"><option value="reference">Reference</option><option value="candidate">Candidate</option></select></label></div></div>
<p id="correspondence" class="notice" hidden></p><div id="pages" class="pages"></div>
<section class="evidence"><div class="finding-list"><div class="section-label"><h2>Findings</h2><span id="visible-count"></span></div><div id="findings"></div></div><article class="detail" aria-live="polite" id="detail"></article></section>
<details class="technical"><summary>Provenance, coverage & limitations</summary><div id="technical"></div></details></main></div>
<footer><span>SlideTransit · <span id="version"></span> · Evidence, with its limits.</span><span id="comparison"></span></footer>
<div id="toast" role="status" aria-live="polite"></div>
<script type="application/json" id="transit-data">{payload}</script><script>{js}</script></body></html>"""
    encoded = html.encode("utf-8")
    if len(encoded) > limits.html_bytes:
        raise TransitError("standalone HTML exceeds size limit; reduce scope or DPI")
    (out / "report.html").write_bytes(encoded)
