"""Internal consistency of unsigned stored measurements; not proof of provenance."""

from __future__ import annotations

import json

from slidetransit.limits import DEFAULT_LIMITS, Limits
from slidetransit.manifest import validate
from slidetransit.models import JSON, BBox, TransitError, fingerprint, normalize, update_summary
from slidetransit.report_assets import asset_names

CHANNEL_STATES = {"complete", "partial", "unavailable", "absent"}
RASTER_COMPARISONS = {
    "complete",
    "unavailable-different-page-size",
    "unavailable-different-raster-grid",
    "unavailable-unresolved-correspondence",
}


def validate_asset_sizes(report: JSON, sizes: dict[str, tuple[int, int]]) -> None:
    coverage = {row["page"]: row for row in report["coverage"]}
    for page in report["pages"]:
        for role in ["reference", "candidate"]:
            image = page[role]
            if (
                image is not None
                and "rasterSize" in image
                and list(sizes[image["image"]]) != image["rasterSize"]
            ):
                raise TransitError("report rasterSize conflicts with PNG asset dimensions")
        state = coverage[page["page"]].get("rasterComparison")
        if state in ["complete", "unavailable-different-raster-grid"]:
            left, right = (sizes[page[role]["image"]] for role in ["reference", "candidate"])
            if (left == right) != (state == "complete"):
                raise TransitError(
                    "report raster comparison coverage conflicts with PNG asset grids"
                )
            if state == "complete" and sizes[page["mask"]] != left:
                raise TransitError("report mask dimensions conflict with PNG asset grid")


def region_findings(report: JSON, decision: JSON) -> list[str]:
    """Validate an applied bounded region and derive its actual affected findings."""
    box = BBox(*decision["region"])
    page = next((p for p in report["pages"] if p["page"] == decision["page"]), None)
    if (
        page is None
        or page["correspondence"] != "declared-order"
        or not all(page[role] is not None for role in ["reference", "candidate"])
    ):
        raise TransitError("applied review decision has unresolved page correspondence")
    if decision["regionHash"] != fingerprint(
        {
            "page": decision["page"],
            "region": [f"{v:.4f}" for v in decision["region"]],
        }
    ):
        raise TransitError("applied review decision has an invalid region fingerprint")
    for role in ["reference", "candidate"]:
        whole = BBox(0, 0, page[role]["width"], page[role]["height"])
        area = (box.x1 - box.x0) * (box.y1 - box.y0)
        if not whole.contains(box) or not 0 < area <= whole.x1 * whole.y1 * 0.25:
            raise TransitError("ignore region must be inside both pages and cover at most 25%")
    affected: list[str] = []
    for item in report["findings"]:
        if item["page"] != decision["page"] or item["ruleId"] in [
            "page-correspondence-problem",
            "page-geometry-change",
        ]:
            continue
        boxes = [BBox(*item[key]) for key in ["referenceBBox", "candidateBBox"] if item[key]]
        if boxes and all(box.contains(b) for b in boxes):
            affected.append(item["id"])
    return affected


def _findings_and_decisions(report: JSON, coverage: dict[int, JSON]) -> None:
    pages = {p["page"]: p for p in report["pages"]}
    by_id: dict[str, JSON] = {}
    for item in report["findings"]:
        if item["id"] in by_id:
            raise TransitError("duplicate report finding identity")
        by_id[item["id"]] = item
        page_number = item["page"]
        if page_number is None:
            if (
                item["ruleId"] != "page-correspondence-problem"
                or item["cropReferences"]
                or any(item[k] is not None for k in ["referenceBBox", "candidateBBox"])
            ):
                raise TransitError("invalid unlocalized report finding")
        elif page_number not in pages or pages[page_number]["correspondence"] != "declared-order":
            raise TransitError("report finding references an absent or unresolved page")
        for role in ["reference", "candidate"]:
            box = item[role + "BBox"]
            if box is not None:
                BBox(*box)
            if (box is not None or role in item["cropReferences"]) and (
                page_number is None or pages[page_number][role] is None
            ):
                raise TransitError("report finding references an absent page asset")
        channel = item["evidence"].get("channel")
        if channel is not None and channel not in [
            "text",
            "geometry",
            "raster",
            "raster+text",
            "structure",
        ]:
            raise TransitError("unknown report finding channel")
        if channel in ["raster", "raster+text"] and (
            page_number is None or coverage[page_number].get("rasterComparison") != "complete"
        ):
            raise TransitError("raster finding conflicts with unavailable comparison coverage")
        region = {key: item[key] for key in ["referenceBBox", "candidateBBox"]}
        basis = {key: item[key] for key in ["ruleId", "ruleVersion", "page", "evidence"]}
        if (
            item["regionHash"] != fingerprint(region)
            or item["id"] != fingerprint({**basis, **region})[:24]
        ):
            raise TransitError("report finding identity conflicts with its measured evidence")
    states = dict.fromkeys(by_id, "open")
    for record in report["decisions"]:
        decision = record["decision"]
        if not decision["reason"].strip() or (
            "author" in decision and not decision["author"].strip()
        ):
            raise TransitError("review decision reason and supplied author must be nonblank")
        if decision["type"] == "ignore-region":
            BBox(*decision["region"])
        if record["state"] == "stale":
            if "affectedFindings" in record:
                raise TransitError("stale review decision cannot suppress findings")
            continue  # Historical stale references deliberately remain visible.
        if decision["type"] == "accept-difference":
            item = by_id.get(decision["findingId"])
            if (
                item is None
                or item["regionHash"] != decision["regionHash"]
                or "affectedFindings" in record
            ):
                raise TransitError(
                    "applied review decision has a dangling finding or region reference"
                )
            states[item["id"]] = "accepted"
        else:
            affected = region_findings(report, decision)
            if record.get("affectedFindings") != affected:
                raise TransitError("applied region decision has inconsistent finding references")
            for identity in affected:
                states[identity] = "region-accepted"
    if any(item["reviewState"] != states[item["id"]] for item in report["findings"]):
        raise TransitError("report review state is not supported by applied decisions")


def validate_report_semantics(report: JSON, limits: Limits = DEFAULT_LIMITS) -> None:
    try:
        encoded = json.dumps(report, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TransitError("report must contain finite JSON values") from exc
    if len(encoded) > limits.report_json_bytes:
        raise TransitError("report JSON exceeds size limit; reduce declared scope")
    validate(report, "report")
    pages, coverage = report["pages"], report["coverage"]
    if len(pages) > limits.pages or len(report["findings"]) > limits.findings:
        raise TransitError("report exceeds page or finding limit")
    if any(not isinstance(row.get("page"), int) for row in pages + coverage):
        raise TransitError("invalid report page or coverage index")
    page_ids = [row["page"] for row in pages]
    coverage_ids = [row["page"] for row in coverage]
    if (
        page_ids != list(range(1, len(pages) + 1))
        or len(set(coverage_ids)) != len(coverage_ids)
        or set(coverage_ids) != set(page_ids)
    ):
        raise TransitError("report pages and coverage must correspond exactly once")
    by_page = {row["page"]: row for row in coverage}
    scope = report["provenance"]["scope"]["slideRange"]
    if not 1 <= scope[0] <= scope[1] <= limits.pages:
        raise TransitError("invalid report source slide range")
    if any(p["correspondence"] == "declared-order" for p in pages):
        if len(pages) != scope[1] - scope[0] + 1 or any(
            p["correspondence"] != "declared-order" or p["sourceSlide"] != scope[0] + p["page"] - 1
            for p in pages
        ):
            raise TransitError("declared page correspondence conflicts with source scope")
    complete = True
    for page in pages:
        row = by_page[page["page"]]
        correspondence = page.get("correspondence")
        if (
            correspondence not in ["declared-order", "unresolved"]
            or row.get("correspondence") != correspondence
        ):
            raise TransitError("invalid or inconsistent report coverage correspondence")
        raster = row.get("rasterComparison")
        # Historical 1.0 producers omitted this field only on unresolved pages.
        if raster is None and correspondence == "unresolved":
            raster = "unavailable-unresolved-correspondence"
        if raster not in RASTER_COMPARISONS:
            raise TransitError("unknown or missing report coverage rasterComparison")
        complete &= correspondence == "declared-order" and raster == "complete"
        if correspondence == "unresolved":
            if raster != "unavailable-unresolved-correspondence" or page.get("mask"):
                raise TransitError("unresolved correspondence cannot assert paired raster coverage")
        else:
            left, right = page["reference"], page["candidate"]
            if left is None or right is None:
                raise TransitError("declared-order coverage requires both pages")
            physical_equal = (
                abs(left["width"] - right["width"]) <= 0.25
                and abs(left["height"] - right["height"]) <= 0.25
            )
            if not physical_equal:
                expected_raster = "unavailable-different-page-size"
            elif "rasterSize" in left and "rasterSize" in right:
                expected_raster = (
                    "complete"
                    if left["rasterSize"] == right["rasterSize"]
                    else "unavailable-different-raster-grid"
                )
            else:
                expected_raster = "complete"  # Historical paired 1.0 reports.
            if raster != expected_raster or bool(page.get("mask")) != (raster == "complete"):
                raise TransitError(
                    "raster comparison coverage conflicts with page/grid geometry or mask"
                )
        for role in ["reference", "candidate"]:
            channels = row.get(role)
            if not isinstance(channels, dict) or set(channels) - {
                "raster",
                "text",
                "geometry",
                "characters",
            }:
                raise TransitError("unknown report coverage channel")
            if not {"raster", "text", "geometry"} <= channels.keys() or any(
                state not in CHANNEL_STATES for state in channels.values()
            ):
                raise TransitError("unknown or missing report coverage channel state")
            if (page[role] is None and any(state != "absent" for state in channels.values())) or (
                page[role] is not None
                and ("absent" in channels.values() or channels["raster"] != "complete")
            ):
                raise TransitError("report page presence conflicts with coverage")
            complete &= all(channels[c] == "complete" for c in ["raster", "text", "geometry"])
            if page[role] is not None:
                image = page[role]
                for key in ["mediaBox", "cropBox"]:
                    BBox(*image[key])
                if (
                    image.get("rasterSize")
                    and image["rasterSize"][0] * image["rasterSize"][1] > limits.page_pixels
                ):
                    raise TransitError("report page exceeds pixel limit")
                characters = 0
                for block in image["textBlocks"]:
                    BBox(*block["bbox"])
                    if block["normalized"] != normalize(block["text"]):
                        raise TransitError("report text normalization conflicts with observed text")
                    characters += len(block["characters"])
                    for char in block["characters"]:
                        BBox(*char["bbox"])
                if characters > limits.characters_per_page:
                    raise TransitError("report page exceeds character limit")
    for role in ["reference", "candidate"]:
        if (
            sum(len(b["characters"]) for p in pages if p[role] for b in p[role]["textBlocks"])
            > limits.characters_per_document
        ):
            raise TransitError("report exceeds total character limit")
    asset_names(report)
    _findings_and_decisions(report, by_page)
    derived = "complete" if complete else "incomplete"
    if report["analysisStatus"] != derived:
        raise TransitError("report analysisStatus conflicts with required-channel coverage")
    expected = report.copy()
    update_summary(expected)
    if report["summary"] != expected["summary"]:
        raise TransitError("report summary conflicts with evidence and coverage")
