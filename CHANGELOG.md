# Changelog

## 0.1.1rc1 — local candidate, not published

- Reject asset symlinks at every path component; verify bounded regular PNGs and copy unchanged bytes through anchored descriptors.
- Validate report page/coverage completeness, channel states, findings/assets/decision references and derived status/summary before rendering or applying review.
- Preserve native raster grids for fractional page dimensions; expose unavailable raster comparison while retaining text/geometry evidence and crops.
- Show unavailable channels beside previews and disable incompatible overlay. Preserve incomplete status after acceptance.
- Verify negative review cases in separate wheel/sdist consumers without dev dependencies; add immutable-input external export/review runbook.
- Emit JSON exit 130 for interruption, terminate only the owned worker and preserve replacement staging directories during rollback.
- Keep schemaVersion 1.0, Python 3.13 and pinned dependencies; see migration-0.1.1rc1.md.

## 0.1.0 - 2026-10-12

First experimental release. Compare one PPTX and two supplied real PDF exports;
retain independent text, position, wrapping, raster and possible-clipping evidence.
Ship a portable offline reviewer, revision-bound acceptance, explicit coverage,
bounded subprocess analysis, JSON schemas and genuine own export fixtures.

No native PowerPoint renderer, automatic fixes, OCR, cloud processing or Office parity.
