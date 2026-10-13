"""Independent text, position, wrapping, clipping hints and raster regions."""

from __future__ import annotations

import json
import math
from collections import Counter, deque
from importlib.resources import files
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from slidetransit import __version__
from slidetransit.limits import DEFAULT_LIMITS, Limits, atomic_output, sha256
from slidetransit.manifest import Manifest
from slidetransit.matching import match_blocks
from slidetransit.models import (
    JSON,
    RULE_VERSION,
    SEVERITIES,
    BBox,
    Config,
    TransitError,
    finding,
    fingerprint,
    update_summary,
)
from slidetransit.pdf import Page, inspect_pdf, versions
from slidetransit.pptx import Deck, attribute, read_deck
from slidetransit.report_validation import validate_report_semantics


def raster_regions(
    left: Image.Image, right: Image.Image, config: Config
) -> tuple[list[JSON], Image.Image]:
    delta = np.max(
        np.abs(np.asarray(left, dtype=np.int16) - np.asarray(right, dtype=np.int16)), axis=2
    )
    mask = delta >= config.pixel_delta
    image = Image.fromarray((mask * 255).astype(np.uint8))
    # Group nearby differing pixels on an 8px grid. No image shift or alignment.
    tile = 8
    h, w = mask.shape
    padded = np.pad(mask, ((0, (-h) % tile), (0, (-w) % tile)))
    grid = padded.reshape(padded.shape[0] // tile, tile, padded.shape[1] // tile, tile).any(
        axis=(1, 3)
    )
    # Dilation groups nearby mask components only; input rasters are unchanged.
    grid = (
        np.asarray(Image.fromarray((grid * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5)))
        > 0
    )
    seen = np.zeros(grid.shape, dtype=np.bool_)
    regions: list[JSON] = []
    for sy, sx in np.argwhere(grid):
        if seen[sy, sx]:
            continue
        queue = deque([(int(sy), int(sx))])
        seen[sy, sx] = True
        xs, ys = [], []
        while queue:
            y, x = queue.popleft()
            xs.append(x)
            ys.append(y)
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    ny, nx = y + dy, x + dx
                    if (
                        0 <= ny < grid.shape[0]
                        and 0 <= nx < grid.shape[1]
                        and grid[ny, nx]
                        and not seen[ny, nx]
                    ):
                        seen[ny, nx] = True
                        queue.append((ny, nx))
        x0, y0, x1, y1 = (
            min(xs) * tile,
            min(ys) * tile,
            min(w, (max(xs) + 1) * tile),
            min(h, (max(ys) + 1) * tile),
        )
        actual = mask[y0:y1, x0:x1]
        coordinates = np.argwhere(actual)
        if not len(coordinates):
            continue
        x0t, y0t = x0 + int(coordinates[:, 1].min()), y0 + int(coordinates[:, 0].min())
        x1t, y1t = x0 + int(coordinates[:, 1].max()) + 1, y0 + int(coordinates[:, 0].max()) + 1
        values = delta[y0:y1, x0:x1][actual]
        regions.append(
            {
                "pixelBox": [x0t, y0t, x1t, y1t],
                "changedPixels": int(actual.sum()),
                "maxDelta": int(values.max()),
                "meanDelta": round(float(values.mean()), 2),
            }
        )
    return sorted(regions, key=lambda r: (r["pixelBox"][1], r["pixelBox"][0])), image


def text_findings(
    reference: Page, candidate: Page, page: int, config: Config, deck: Deck, source_page: int
) -> list[JSON]:
    output: list[JSON] = []
    anchor_counts = Counter(b.normalized for b in reference.blocks)
    pairs, removed, added = match_blocks(reference.blocks, candidate.blocks)
    both_complete = reference.coverage["text"] == candidate.coverage["text"] == "complete"
    for left, right, match_basis in pairs:
        evidence: JSON = {
            "observed": {"referenceText": left.text, "candidateText": right.text},
            "matchBasis": match_basis,
            "channel": "text",
            "probableExplanation": None,
        }
        if left.normalized != right.normalized:
            output.append(
                finding(
                    "extracted-text-change",
                    page,
                    "high",
                    "Extracted text changed",
                    evidence,
                    left.bbox,
                    right.bbox,
                )
            )
        else:
            if left.lines != right.lines:
                output.append(
                    finding(
                        "line-wrap-change",
                        page,
                        "medium",
                        "Line wrapping changed",
                        {**evidence, "referenceLines": left.lines, "candidateLines": right.lines},
                        left.bbox,
                        right.bbox,
                    )
                )
            dx, dy = right.bbox.x0 - left.bbox.x0, right.bbox.y0 - left.bbox.y0
            if max(abs(dx), abs(dy)) > config.displacement_pt:
                output.append(
                    finding(
                        "displacement",
                        page,
                        "medium",
                        "Text position changed",
                        {
                            **evidence,
                            "dxPt": round(dx, 4),
                            "dyPt": round(dy, 4),
                            "thresholdPt": config.displacement_pt,
                            "channel": "geometry",
                        },
                        left.bbox,
                        right.bbox,
                    )
                )
            if abs(left.size - right.size) > config.size_pt:
                output.append(
                    finding(
                        "text-size-change",
                        page,
                        "medium",
                        "Extracted glyph size changed",
                        {
                            **evidence,
                            "referenceSizePt": left.size,
                            "candidateSizePt": right.size,
                            "channel": "geometry",
                        },
                        left.bbox,
                        right.bbox,
                    )
                )
        # Text layer may retain glyphs extending outside the visible page.
        page_box = BBox(0, 0, candidate.width, candidate.height)
        if not page_box.contains(right.bbox, margin=0.5) and BBox(
            0, 0, reference.width, reference.height
        ).contains(left.bbox, margin=0.5):
            output.append(
                finding(
                    "possible-clipping",
                    page,
                    "high",
                    "Possible clipping at page edge",
                    {
                        **evidence,
                        "observedGeometry": "candidate extracted glyph box extends beyond displayed page",
                        "probableExplanation": "Part of the text may be clipped; inspect the raster crop.",
                        "confidence": "conditional",
                    },
                    left.bbox,
                    right.bbox,
                )
            )
        for item in output:
            if item["referenceBBox"] == left.bbox.values() and anchor_counts[left.normalized] == 1:
                item["attribution"] = attribute(
                    deck,
                    source_page,
                    left.normalized,
                    left.bbox,
                    (reference.width, reference.height),
                )
    if both_complete:
        for block, role in [(b, "reference") for b in removed] + [(b, "candidate") for b in added]:
            box = block.bbox
            item = finding(
                "extracted-text-change",
                page,
                "high",
                "Extracted text unmatched",
                {
                    "observed": {"text": block.text, "side": role},
                    "channel": "text",
                    "probableExplanation": "Content change or ambiguous block matching; inspect raster evidence.",
                    "confidence": "conditional",
                },
                box if role == "reference" else None,
                box if role == "candidate" else None,
            )
            if role == "reference":
                item["attribution"] = attribute(
                    deck, source_page, block.normalized, box, (reference.width, reference.height)
                )
            output.append(item)
    return output


def save_crops(item: JSON, reference: Page, candidate: Page, out: Path, dpi: int) -> None:
    scale = dpi / 72
    boxes = [BBox(*item[role]) for role in ["referenceBBox", "candidateBBox"] if item[role]]
    if not boxes:
        return
    region = boxes[0]
    for box in boxes[1:]:
        region = region.union(box)
    for role, page in [("reference", reference), ("candidate", candidate)]:
        local = BBox(*item[role + "BBox"]) if item[role + "BBox"] else region
        pixel_box = (
            max(0, math.floor((local.x0 - 8) * scale)),
            max(0, math.floor((local.y0 - 8) * scale)),
            min(page.image.width, math.ceil((local.x1 + 8) * scale)),
            min(page.image.height, math.ceil((local.y1 + 8) * scale)),
        )
        if pixel_box[2] <= pixel_box[0] or pixel_box[3] <= pixel_box[1]:
            continue
        path = f"assets/crop-{item['id']}-{role}.png"
        page.image.crop(pixel_box).save(out / path, optimize=True)
        item["cropReferences"][role] = path


def run_comparison(manifest: Manifest, out: Path, limits: Limits = DEFAULT_LIMITS) -> JSON:
    from slidetransit.report import write_report

    config = manifest.config
    deck = read_deck(manifest.presentation, limits)
    start, end = manifest.data["scope"]["slideRange"]
    if not 1 <= start <= end <= len(deck.slides):
        raise TransitError("declared slide range is outside PPTX")
    if (
        deck.hidden
        and not manifest.data["scope"]["includeHidden"]
        and any(start <= h <= end for h in deck.hidden)
    ):
        raise TransitError("hidden slides in declared range need explicit concordant export scope")
    renderer_metadata = versions()
    renderer_metadata["exporters"] = {
        role: manifest.data[role]["renderer"] for role in ["reference", "candidate"]
    }
    identity_settings = {
        "config": config.json(),
        "ruleVersion": RULE_VERSION,
        "scope": manifest.data["scope"],
        "mode": manifest.data["mode"],
        "versions": renderer_metadata,
        "provenance": manifest.provenance,
        "implementationHash": fingerprint(
            {
                **{
                    name: fingerprint(files("slidetransit").joinpath(name + ".py").read_text())
                    for name in ["compare", "coordinates", "matching", "pdf", "pptx", "models", "limits", "report_validation", "report_assets"]
                },
                **{
                    name + ".schema.json": fingerprint(files("slidetransit").joinpath("schemas", name + ".schema.json").read_text())
                    for name in ["manifest", "report", "decisions"]
                },
            }
        ),
        "parameters": {
            "pageSizeTolerancePt": 0.25,
            "rasterGridPolicy": "native-grid-no-resampling",
            "rasterTilePixels": 8,
            "rasterGroupingDilationTiles": 5,
            "lineYtolerancePt": 2,
            "sourceContainmentMarginPt": 3,
            "inkLossRatioHint": 0.45,
            "intensityHintMaxDelta": 32,
        },
    }
    comparison_id = fingerprint({"inputs": manifest.hashes, **identity_settings})
    report: JSON = {
        "schemaVersion": "1.0",
        "tool": {"name": "SlideTransit", "version": __version__},
        "comparisonId": comparison_id,
        "inputs": manifest.hashes,
        "config": config.json(),
        "rules": {
            "version": RULE_VERSION,
            "hash": fingerprint(identity_settings),
            "implementationHash": identity_settings["implementationHash"],
            "parameters": identity_settings["parameters"],
        },
        "renderer": renderer_metadata,
        "provenance": manifest.provenance,
        "coordinates": "displayed page; top-left origin; x right/y down; points (1/72 inch)",
        "analysisStatus": "complete",
        "coverage": [],
        "pages": [],
        "findings": [],
        "decisions": [],
        "limits": limits.json(),
        "limitations": list(manifest.data["limitations"])
        + [
            "No OCR, automatic page realignment or confirmed source-object identity.",
            "Small raster-only differences remain hints; review meaningful symbols.",
        ],
    }
    with atomic_output(out, manifest.inputs, limits) as working:
        (working / "assets").mkdir()
        reference = inspect_pdf(manifest.reference, "reference", working, config.dpi, limits)
        candidate = inspect_pdf(manifest.candidate, "candidate", working, config.dpi, limits)
        expected = end - start + 1
        corresponds = len(reference) == len(candidate) == expected
        reference_signatures = [
            fingerprint([b.normalized for b in page.blocks]) for page in reference
        ]
        candidate_signatures = [
            fingerprint([b.normalized for b in page.blocks]) for page in candidate
        ]
        order_conflicts = []
        if corresponds:
            for index, signature in enumerate(reference_signatures):
                matches = [i for i, other in enumerate(candidate_signatures) if other == signature]
                if len(matches) == 1 and matches[0] != index and reference[index].blocks:
                    order_conflicts.append(
                        {"referencePage": index + 1, "exactTextAnchorCandidatePage": matches[0] + 1}
                    )
            if order_conflicts:
                corresponds = False
        if not corresponds:
            report["analysisStatus"] = "incomplete"
            report["findings"].append(
                finding(
                    "page-correspondence-problem",
                    None,
                    "high",
                    "Page correspondence is unresolved",
                    {
                        "observed": {
                            "referencePages": len(reference),
                            "candidatePages": len(candidate),
                            "declaredSlides": expected,
                            "orderConflicts": order_conflicts,
                        },
                        "channel": "structure",
                        "probableExplanation": None,
                    },
                )
            )
            report["limitations"].append(
                "Page counts differ; indexed visual previews are unpaired and no per-page comparison is asserted."
            )
        for index in range(max(len(reference), len(candidate))):
            left = reference[index] if index < len(reference) else None
            right = candidate[index] if index < len(candidate) else None
            page_number = index + 1
            record: JSON = {
                "page": page_number,
                "sourceSlide": start + index,
                "correspondence": "declared-order" if corresponds else "unresolved",
            }
            coverage: JSON = {
                "page": page_number,
                "correspondence": record["correspondence"],
                "rasterComparison": "unavailable-unresolved-correspondence",
            }
            for role, page in [("reference", left), ("candidate", right)]:
                if page is None:
                    record[role], coverage[role] = (
                        None,
                        {"raster": "absent", "text": "absent", "geometry": "absent"},
                    )
                else:
                    record[role] = {
                        "width": page.width,
                        "height": page.height,
                        "rotation": page.rotation,
                        "mediaBox": page.media_box,
                        "cropBox": page.crop_box,
                        "image": page.image_path,
                        "rasterSize": list(page.image.size),
                        "textBlocks": [
                            {
                                "text": b.text,
                                "normalized": b.normalized,
                                "bbox": b.bbox.values(),
                                "lines": b.lines,
                                "sizePt": b.size,
                                "characters": b.chars,
                            }
                            for b in page.blocks
                        ],
                    }
                    coverage[role] = page.coverage
                    if (
                        page.coverage["text"] != "complete"
                        or page.coverage["geometry"] != "complete"
                    ):
                        report["analysisStatus"] = "incomplete"
                        report["limitations"].append(
                            f"Page {page_number} {role}: text/geometry channel {page.coverage['text']}; absent text layer is not proof of missing visible text."
                        )
            report["pages"].append(record)
            report["coverage"].append(coverage)
            if not corresponds or left is None or right is None:
                continue
            items = text_findings(left, right, page_number, config, deck, start + index)
            left.image = Image.open(working / left.image_path).convert("RGB")
            right.image = Image.open(working / right.image_path).convert("RGB")
            geometry_equal = (
                abs(left.width - right.width) <= 0.25 and abs(left.height - right.height) <= 0.25
            )
            if not geometry_equal:
                report["findings"].append(
                    finding(
                        "page-geometry-change",
                        page_number,
                        "high",
                        "Displayed page size changed",
                        {
                            "observed": {
                                "referenceSizePt": [left.width, left.height],
                                "candidateSizePt": [right.width, right.height],
                            },
                            "channel": "geometry",
                            "probableExplanation": None,
                        },
                    )
                )
                coverage["rasterComparison"] = "unavailable-different-page-size"
                report["analysisStatus"] = "incomplete"
                report["limitations"].append(
                    "Different page sizes are not stretched; raster comparison is unavailable on this page."
                )
            elif left.image.size != right.image.size:
                coverage["rasterComparison"] = "unavailable-different-raster-grid"
                report["analysisStatus"] = "incomplete"
                report["limitations"].append(
                    f"Page {page_number}: native raster grids {left.image.size} and {right.image.size} differ at {config.dpi} DPI within the 0.25 pt page-size tolerance; raster comparison is unavailable. No resampling or alignment was applied."
                )
            else:
                regions, mask = raster_regions(left.image, right.image, config)
                mask_path = f"assets/mask-{page_number}.png"
                mask.save(working / mask_path)
                record["mask"] = mask_path
                coverage["rasterComparison"] = "complete"
                # Low intensity regions are visible hints, never an override of text findings.
                for region in regions:
                    box = BBox(*(p / (config.dpi / 72) for p in region["pixelBox"]))
                    intensity_hint = region["maxDelta"] <= 32
                    item = finding(
                        "raster-region-change",
                        page_number,
                        "low" if intensity_hint else "medium",
                        "Raster region changed",
                        {
                            "observed": region,
                            "channel": "raster",
                            "threshold": config.pixel_delta,
                            "confidence": "low" if intensity_hint else "measured-difference",
                            "probableExplanation": "Low intensity raster-only difference; antialiasing is one possible explanation."
                            if intensity_hint
                            else "Content, geometry or rendering change; cause is not established.",
                        },
                        box,
                        box,
                    )
                    items.append(item)
                # Clipping can be suggested when extracted glyphs have far less ink.
                for left_block, right_block, _ in match_blocks(left.blocks, right.blocks)[0]:
                    if left_block.normalized != right_block.normalized:
                        continue

                    def ink(page: Page, box: BBox) -> int:
                        scale = config.dpi / 72
                        bounds = (
                            max(0, int(box.x0 * scale)),
                            max(0, int(box.y0 * scale)),
                            min(page.image.width, math.ceil(box.x1 * scale)),
                            min(page.image.height, math.ceil(box.y1 * scale)),
                        )
                        if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
                            return 0
                        return int((np.asarray(page.image.crop(bounds)).min(axis=2) < 160).sum())

                    ref_ink, cand_ink = ink(left, left_block.bbox), ink(right, right_block.bbox)
                    if (
                        ref_ink >= 40
                        and cand_ink < ref_ink * 0.45
                        and not any(
                            f["ruleId"] == "possible-clipping"
                            and f["referenceBBox"] == left_block.bbox.values()
                            for f in items
                        )
                    ):
                        items.append(
                            finding(
                                "possible-clipping",
                                page_number,
                                "high",
                                "Possible clipping or lost visible ink",
                                {
                                    "observed": {
                                        "referenceInkPixels": ref_ink,
                                        "candidateInkPixels": cand_ink,
                                        "textRetained": left_block.text,
                                    },
                                    "channel": "raster+text",
                                    "probableExplanation": "Visible ink reduced despite retained text; clipping, color or occlusion may explain it.",
                                    "confidence": "conditional",
                                },
                                left_block.bbox,
                                right_block.bbox,
                            )
                        )
            for item in items:
                save_crops(item, left, right, working, config.dpi)
            report["findings"].extend(items)
            left.image.close()
            right.image.close()
            if len(report["findings"]) > limits.findings:
                raise TransitError("finding limit exceeded")
            if (
                sum(p.stat().st_size for p in working.rglob("*") if p.is_file())
                > limits.output_bytes / 2
            ):
                raise TransitError("rendered assets exceed output budget")
        # Inputs are checked again before committing the result.
        if any(
            sha256(p) != manifest.hashes[role]
            for role, p in zip(
                ["presentation", "reference", "candidate"], manifest.inputs, strict=True
            )
        ):
            raise TransitError("input bytes changed during analysis")
        report["findings"].sort(
            key=lambda f: (
                f["page"] or 0,
                -SEVERITIES[f["severity"]],
                0 if f["ruleId"] == "possible-clipping" else 1,
                f["id"],
            )
        )
        update_summary(report)
        validate_report_semantics(report, limits)
        write_report(report, working, limits)
        (working / "report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        )
        for page in reference + candidate:
            page.image.close()
    return report
