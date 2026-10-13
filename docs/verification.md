# Verification of the experimental releases

For 0.1.1rc1, local frozen sync, Ruff, mypy (14 source modules), 116 tests, schema
generation and build passed on macOS 26.7.1 ARM64 / Python 3.13.7 / PDFium
145.0.7616.0. Separate installed wheel and sdist consumers each passed 45 contract
probes without development dependencies. The offline UI passed nine assertions
and produced 16 screenshots at 390/1024/1440 px in Chrome 155.0.8059.40.

[Release receipts](https://github.com/mikonyaa/slidetransit/releases/tag/v0.1.1rc1)
provide the exact release commit, successful CI run, artifact hashes and public
download checks. Check those records for remote platform evidence; the historical
0.1.0 measurements below are not measurements of the new prerelease.

Candidate reproduction (all output directories must be new):

```sh
uv sync --frozen --all-groups
uv run --frozen ruff check .
uv run --frozen mypy src
uv run --frozen pytest
uv run --frozen python scripts/create_schemas.py
uv run --frozen python -m build
uv run --frozen python scripts/verify_release.py --dist dist \
  --json-out release-consumer-results.json --consumer-root /absolute/new/consumers
uv run --frozen python scripts/verify_ui.py --help
uv run --frozen python scripts/verify_ui.py \
  --demo /absolute/new/consumers/wheel/demo-output --out /absolute/new/browser-qa \
  --cli /absolute/new/consumers/wheel/venv/bin/slidetransit \
  --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --incomplete /absolute/new/consumers/wheel/contracts/partial-review/report.html \
  --grid-report /absolute/new/consumers/wheel/contracts/fractional-239.9-150/report.html
```

Use only a browser executable actually available on that machine. The retained
wheel and sdist consumers contain runtime dependencies, with no editable checkout,
PYTHONPATH or development packages. Each consumer regenerates 17 own PDF pairs
using a standard-library writer, compares native grids at six DPIs, exercises
positive/negative review, checks exact JSON stdout and 0/1/2/3/130 exits, unchanged
input/asset hashes, sentinel preservation and owned-worker interruption. The
two-page partial fixture isolates one finding and a raster-only candidate page;
unchanged acceptance must remain exit 3. Invalid coverage, assets and identity
declarations must be rejected before commit. These synthetic probes are not an
Office export pipeline or independent real-deck review.

The UI verifier uses an owned temporary profile and direct `file://` reports with
network and persistent storage disabled. It keeps packaged demo JSON/HTML/assets
byte-for-byte unchanged; stress/malformed fixtures live in separate QA copies.
It checks 390/1024/1440 layouts, paired crops, keyboard/filter/overlay/zoom, real
downloaded decisions and installed-CLI application, unavailable channels after
acceptance and rejection of a malformed import with no success bundle.

See [migration](migration-0.1.1rc1.md) and the
[fresh export / independent pilot](external-pilot.md) for compatibility and the
external evidence still needed. Read the historical record below as historical.

Local gate checked on 2026-10-12: macOS 26.7.1 ARM64, MacBook Pro M4, Python 3.13.7.
The final release manifest supplies the immutable release source commit, successful
exact-commit CI run, build environment and published file hashes; use those actual
records for remote evidence. A local build alone does not constitute a verified release.

## Local checks

- Frozen uv sync, Ruff, strict mypy over all 12 source modules.
- 64 unit/integration tests plus one package-resource test (65 total).
- Genuine 15-export corpus with 14 declared comparisons and source/PDF SHA-256,
  commands, exporter version and environment. Repeat results are semantically stable
  across reruns and all input bytes remain unchanged.
- Deletion, visible page-edge clipping with retained text, CJK/wrap, open-font changes,
  changed small numeral, displacement, duplicate anchors, counts/aspect and faint noise.
- 0/90/180/270° plus shifted MediaBox/CropBox character-versus-ink canaries.
  These synthetic unit PDFs are explicitly separate from genuine export fixtures.
- Missing text layer yields incomplete exit 3, never a false missing-text fact or green;
  mismatched/reordered pages do not receive confident index comparisons.
- Old input/rule/renderer/region decisions become stale; accepted evidence remains.
  Bounded region suppression cannot hide structure or incomplete channels.
- Corrupted/encrypted PDFs, malformed/DTD XML, hostile ZIP paths, normalized duplicates,
  compression/entries/XML/output/character/pixel limits and an actual owned-worker timeout.
- Final wheel installed into a new venv outside checkout; final sdist builds a wheel in
  another outside builder venv, then installs into a separate consumer. Both exercise
  doctor/init/compare/demo/apply-review and package resources with no editable/PYTHONPATH.

## Browser and demo

Chromium 155.0.8059.39, separate owned temporary profile, 1440/1024/390px. Screenshots
were rendered and visually inspected; a selected-button color defect was fixed and
the suite repeated. Checks include paired/mobile-switch view, overlay/opacity, zoom,
filters, Tab/arrow/O navigation, required reason, real JSON download and CLI application,
bounded region application, 180 long Unicode findings, empty/error states and inert
hostile document strings. No page errors or remote requests for `file://` reports.

`docs/assets/demo.gif` is a 25-second sequence of actual screenshots: unchanged control,
genuinely clipped variant, overlay/crops and a fresh export of the actually fixed own
source. `documented-test-variant` is visible. It does not prove a PowerPoint/Keynote
regression. See paired desktop/tablet/mobile captures in `docs/assets`.

## Threshold and resource probes

The same-source repeat produced zero raster/text findings at 150 DPI and delta 16.
The own displacement fixture retains the measured 28pt shift; no alignment removes it.
The 12.5%→12.6% mutation has high-severity text evidence despite its small region.
The real faint-image-noise export produces no serious text finding; a separate explicit
unit pixel-noise test preserves a 25/255 delta hint and a single black meaningful pixel.
No area threshold discards a small numeral. Grouping reduces the clipping sample to
two raster regions while retaining a position finding and conditional clipping finding.

One local three-case demo measured 0.89s and 130,138,112 bytes max RSS. A separate
**synthetic resource unit probe**, two 1350×1350pt pages at 150 DPI (about 7.9M pixels/page),
measured 0.91s and 407,224,320 bytes max RSS. These are single machine measurements,
not generalized performance claims or hard memory guarantees. The pixel limit was
kept at 8M/page after this probe. Native allocation remains outside a hard RAM sandbox.

## Remote gates

Before release, both Python-3.13 OS jobs must pass on event push, main, exact selected
head SHA. That run builds/tests final wheel/sdist, preserves those bytes, and supplies
origin facts. Release assets are downloaded from that successful run, not rebuilt.
The release tag is verified against that commit. Anonymous public download checks
validate archive format, size and SHA-256 before a fresh installed consumer flow.

Pages is a separate static-sample deployment. Its actual environment deployment URL
is checked in a fresh browser context, including keyboard/mobile controls. Pages-only
failure would be reported separately; it would not be misrepresented as a successful
deployment. No PyPI, native Office parity, external-user feedback or physical-device
testing is claimed.
