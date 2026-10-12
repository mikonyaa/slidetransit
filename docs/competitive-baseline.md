# Current baseline and one own fixture comparison

Inspected 2026-10-12. README/license and the office2pdf/pptxdiff baseline preceded
the vertical slice; the PPTLint comparison/rules source follow-up was completed
during validation before publication. No competitor source was reused.

| Project / inspected commit | Existing workflow | License inspected |
|---|---|---|
| [office2pdf](https://github.com/developer0hye/office2pdf/tree/44f1cc05611b6528fc8584c74d5b6d4df179505e) | Rust conversion plus `scripts/compare_render.py`: native-export geometry, histogram, pixel differences, connected clusters and explicit cluster dispositions | Apache-2.0 |
| [pptxdiff](https://github.com/sugatoray/pptxdiff/tree/36b54ded488fb7591f0afdb6bbd15d0f3d6003c2) | PPTX-to-PPTX inspection/rendering, correspondence, reviewer approvals/history and standalone exports; inspected `src/pptxdiff/index.html` | Apache-2.0 |
| [PPTLint](https://github.com/kdnsna/pptlint/tree/d7672804fffb795c8c9e746376c0ea32e75898be) | Static delivery preflight, explicit cleanup/repair plans and comparison/recheck workflow; inspected rules/comparison source | MIT |
| [Anthropic skills](https://github.com/anthropics/skills/tree/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/pptx) | Render, inspect, correct and re-render slide workflow | pptx directory carries a separate restricted license; not reused or redistributed |

None of pixel diffs, HTML, bboxes or acceptance is a new invention. SlideTransit's
specific focus is an installable author path over **two actual supplied exports**,
paired local evidence, explicit provenance/coverage and revision-bound review.

## Recorded experiment

Own 720×405pt two-slide deck, genuinely exported using isolated LibreOfficeDev
26.8.0.0.alpha0 on macOS 26.7.1 ARM64. Baseline/repeat use the same source hash.
The clipping candidate's title was moved partly outside the slide in an own source
variant; its source hash differs and is documented. The PDF retains the full title's
text layer. Source/PDF hashes and export commands are in fixture manifests.

Ran the upstream script with the **same PDFs**, page 1, DPI 150, `--audit`,
`--cluster-report` and `--strict-clusters`. System Poppler and ImageMagick were
available; `mutool` was absent and upstream explicitly marked geometry approximate.
This is a comparison-script workflow test, not a benchmark of office2pdf's renderer.
Passing a LibreOffice export as that script's reference does not relabel it PowerPoint.

| Case | office2pdf result | SlideTransit result |
|---|---|---|
| Same-source repeat | exit 0, zero clusters | exit 0, complete scope, zero findings |
| Documented clipped variant | exit 1, 54 undispositioned clusters; 4/5 text lines matched, no >5pt shift among matched lines; raster/histogram detected change | exit 1, complete scope; retained title, 300pt displacement, possible clipping and two grouped raster regions; localized paired crops |

One warmed upstream invocation took 5.072s (repeat) and 4.941s (clipped) on this
machine. SlideTransit's whole three-case installed-style local demo took 0.89s with
130,138,112 bytes maximum RSS in one `/usr/bin/time -l` run. The workloads differ
(one upstream page versus three two-page comparisons, different rasterizers and
clustering); these measurements do **not** support a generalized speedup claim.

## Practical tradeoffs observed

SlideTransit preserves the retained text layer and page-edge glyph extent, supplies
a readable conditional clipping explanation and paired crops in one offline file,
and binds reviewer decisions to input/configuration/implementation/render records.
The upstream script also reliably flags this mutation and provides more granular
cluster enumeration, a histogram channel and a sophisticated exporter-disposition
workflow. SlideTransit has no histogram or native converter and does not establish
the true exporter cause. Its coarse grouped regions, supported horizontal extraction
and conservative page correspondence have documented limits.

No user demand, time saved, universal fidelity or superiority was measured. This
small technical experiment is the entire competitive-performance evidence in v0.1.0.
