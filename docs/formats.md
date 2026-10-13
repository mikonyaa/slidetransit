# Formats v1.0

The 0.1.1rc1 prerelease keeps version 1.0 and tightens imported report semantics.
See [migration notes](migration-0.1.1rc1.md) for valid historical reports, explicit
native grid coverage, unchanged decision identity and rejection behavior.

Machine schemas live in `src/slidetransit/schemas` and are shipped in wheel resources:
`manifest.schema.json`, `report.schema.json`, `decisions.schema.json`. They use JSON
Schema 2020-12, finite JSON numbers, a version field and bounded decision arrays.
The CLI validates them and additional semantic invariants, such as hashes, ranges,
finite boxes, bounded regions and reasons containing non-whitespace characters.

## Comparison manifest

```json
{
  "schemaVersion": "1.0",
  "mode": "declared-same-source",
  "presentation": { "path": "deck.pptx" },
  "reference": {
    "path": "reference.pdf",
    "renderer": { "name": "unknown", "version": "unknown" },
    "provenanceAssurance": "user-declared",
    "exportOptions": {},
    "environment": {}
  },
  "candidate": {
    "path": "candidate.pdf",
    "renderer": { "name": "unknown", "version": "unknown" },
    "provenanceAssurance": "unknown",
    "exportOptions": {},
    "environment": {}
  },
  "scope": {
    "slideRange": [1, 2],
    "pageOrder": "source-order",
    "kind": "slides",
    "includeHidden": false
  },
  "limitations": ["Export history is user-declared; renderer versions are unknown."]
}
```

`presentation.sha256` and PDF `sha256` may be supplied; they are recomputed and checked.
An export's optional `source` has `sha256` and optionally `path`. Every declared-same-
source export hash must agree with the presentation; a source path is verified against
its digest. `documented-test-variant` requires both actual source hashes and must never
be described as one unchanged source. `unknown` preserves missing origin knowledge.
The three assurance labels are unknown, user-declared and captured-by-fixture-script.
The last label is a fixture recorder's assertion, not a cryptographic attestation.

Relative paths resolve from the manifest file. Source paths are not copied into
reports. Optional commands/environments are declarations; avoid putting personal
paths or sensitive metadata in those fields. Documents remain local and read-only.
Config keys are `dpi`, `pixel_delta`, `displacement_pt`, `size_pt`, `fail_on`.

## Report and bundle

`report.json` includes tool/version, comparisonId, input SHA-256, config/rule hash,
implementation hash/parameters, renderer/extraction versions, displayed-page
coordinate declaration, coverage, localized findings, decisions, limitations and
summary. Findings separate observed data and conditional explanation. Bboxes are
`[x0,y0,x1,y1]` in display points or null when that side is absent/unlocalized.
`analysisStatus` is complete, incomplete or error independently of open findings.
Summary `exitCode` follows the documented precedence: error > findings > incomplete.

The generated HTML embeds safe JSON, all PNGs, fonts, CSS and JS, with no adjacent
JSON fetch. `report.json` references only sibling `assets/*.png`. To apply decisions
later, keep that JSON and its asset folder together. Each report uses a new output
directory committed by atomic rename; old output is never replaced.

## Review decisions

Copy the report's `comparisonId`, `inputs`, `rules`, `renderer` into a v1 decisions
document and add its `decisions` array. The offline viewer does this when downloading.
An accept-difference has findingId, regionHash, reason, timestamp and optional author.
An ignore-region has page, region, regionHash, reason, timestamp and optional author.
The original binding must be retained; do not copy old decisions into a new binding.
CLI output retains applied/stale decision records and the original measured findings.

## Release origin

GitHub assets include final wheel/sdist, an own standalone example/report ZIP,
`SHA256SUMS`, and `release-manifest.json`. The manifest's file list records artifact
size/hash; the checksum file also covers the manifest and excludes itself. The manifest
does not hash itself. `sourceCommit` is generated after build rather than committed
self-referentially. A successful exact-commit CI artifact is downloaded and published
without rebuilding its wheel/sdist. Public archive bytes are checked again anonymously.
