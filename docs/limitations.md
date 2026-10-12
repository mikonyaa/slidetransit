# Limitations and resource boundary

This is an experimental first release, not a document sandbox or Office parity engine.

- Supply one deck's two exports with the same declared slide range and order.
  Different counts or a detected unique exact-text reorder make pages unpaired.
  Partial-text/visual reorderings can be undetectable; agreed order is a caller obligation.
- Only slide exports are supported. Notes, handouts and conflicting hidden-slide scope
  are not accepted. Export application metadata does not prove provenance.
- Horizontal text is supported. Rotated/mixed-direction text, poor Unicode maps and
  missing text layers make required channels partial/unavailable. No OCR fallback exists.
  Complete raster coverage alone does not yield a green result.
- PDF glyph boxes can include text outside the visible page. Clipping findings combine
  geometry/visible-ink evidence and are conditional; color/occlusion can have a similar
  effect. No font substitution cause is established from font names or pixels.
- Page sizes are not stretched, and no local image shift or elastic alignment hides
  displacement. Raster grouping is intentionally coarse; multiple independent findings
  may describe one visual defect. Fine antialiasing behavior is platform-dependent.
- PPTX attribution supports direct, unrotated, explicit text shapes. Duplicate/grouped/
  inherited anchors remain unattributed. A likely association is not confirmed identity.
- No automatic repair, cloud uploads, AI scoring, collaboration or native PPTX renderer.
  P2 distribution/adapters/batching are not part of this release.
- Python 3.13 is the chosen verified minor. Windows and other Python minors are unverified.
  Browser QA uses Chromium; physical mobile browsers are not verified.

| Limit | Default |
|---|---:|
| Each input file | 100 MiB |
| ZIP entries | 5,000 |
| Total expanded XML | 32 MiB |
| Total expanded ZIP data | 128 MiB |
| Large entry compression ratio | 200:1 |
| PPTX slides / PDF pages | 200 each |
| Raster pixels/page | 8,000,000 |
| Characters/page / document | 100,000 / 250,000 |
| Findings | 5,000 |
| Report JSON / offline HTML | 32 MiB / 64 MiB |
| Total output | 128 MiB |
| Worker deadline | 180 seconds |

Violations return controlled error, not silent truncation or PASS. Reduce scope/DPI.
PNG compression size is not a memory guarantee. Page rasters are stored on disk and
loaded one pair at a time; total character measurements are bounded. A native library
can still allocate internally before Python detects a bad input. The subprocess has
a lifetime boundary and detects native crashes, but no OS sandbox or hard RAM quota.

Reports can contain confidential document text and images. They are not anonymized.
External relationships, macros, PDF actions and V8/XFA are not executed. Input SHA-256
is checked before and after analysis. Outputs must be new directories; a filesystem
failure or process crash must never be described as a successful complete report.
