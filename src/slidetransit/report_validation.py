"""Internal consistency of unsigned stored measurements; not proof of provenance."""

from __future__ import annotations

import copy

from slidetransit.limits import DEFAULT_LIMITS, Limits
from slidetransit.manifest import validate
from slidetransit.models import JSON, TransitError, update_summary

CHANNEL_STATES = {"complete", "partial", "unavailable", "absent"}
RASTER_COMPARISONS = {
    "complete",
    "unavailable-different-page-size",
    "unavailable-unresolved-correspondence",
}


def validate_report_semantics(report: JSON, limits: Limits = DEFAULT_LIMITS) -> None:
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
            if role not in page or (page[role] is None) != all(
                channels[c] == "absent" for c in ["raster", "text", "geometry"]
            ):
                raise TransitError("report page presence conflicts with coverage")
            complete &= all(channels[c] == "complete" for c in ["raster", "text", "geometry"])
    derived = "complete" if complete else "incomplete"
    if report["analysisStatus"] != derived:
        raise TransitError("report analysisStatus conflicts with required-channel coverage")
    expected = copy.deepcopy(report)
    update_summary(expected)
    if report["summary"] != expected["summary"]:
        raise TransitError("report summary conflicts with evidence and coverage")
