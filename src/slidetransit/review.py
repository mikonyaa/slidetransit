"""Revision-bound acceptance; stale decisions stay visible and never suppress."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from slidetransit.limits import DEFAULT_LIMITS, atomic_output, load_json
from slidetransit.manifest import validate
from slidetransit.models import JSON, BBox, TransitError, fingerprint, update_summary
from slidetransit.report_assets import asset_names, bundle_assets
from slidetransit.report_validation import validate_report_semantics


def binding(report: JSON) -> JSON:
    return {k: report[k] for k in ["comparisonId", "inputs", "rules", "renderer"]}


def apply_decisions(report: JSON, document: JSON) -> JSON:
    validate_report_semantics(report)
    validate(document, "decisions")
    result = copy.deepcopy(report)
    for item in result["findings"]:
        item["reviewState"] = "open"
    result["decisions"] = []
    current_binding = binding(report) == {key: document[key] for key in binding(report)}
    for decision in document["decisions"]:
        if not decision["reason"].strip():
            raise TransitError("every review decision requires a nonblank reason")
        state: JSON = {
            "decision": decision,
            "state": "stale",
            "explanation": "input, configuration, rule or renderer binding changed",
        }
        if current_binding:
            if decision["type"] == "accept-difference":
                match = next(
                    (
                        f
                        for f in result["findings"]
                        if f["id"] == decision["findingId"]
                        and f["regionHash"] == decision["regionHash"]
                    ),
                    None,
                )
                if match:
                    match["reviewState"] = "accepted"
                    state.update(
                        state="applied",
                        explanation="Reviewer accepted this measured difference; evidence retained.",
                    )
                else:
                    state["explanation"] = "finding or region is no longer current"
            else:
                page = next((p for p in report["pages"] if p["page"] == decision["page"]), None)
                box = BBox(*decision["region"])
                region_binding = {
                    "page": decision["page"],
                    "region": [f"{value:.4f}" for value in decision["region"]],
                }
                if decision["regionHash"] != fingerprint(region_binding):
                    state["explanation"] = "ignore region fingerprint changed"
                elif (
                    page is None
                    or page["correspondence"] != "declared-order"
                    or not page["reference"]
                    or not page["candidate"]
                ):
                    state["explanation"] = "page correspondence is unresolved"
                else:
                    for role in ["reference", "candidate"]:
                        whole = BBox(0, 0, page[role]["width"], page[role]["height"])
                        area = (box.x1 - box.x0) * (box.y1 - box.y0)
                        if (
                            not whole.contains(box)
                            or area <= 0
                            or area > whole.x1 * whole.y1 * 0.25
                        ):
                            raise TransitError(
                                "ignore region must be inside both pages and cover at most 25%"
                            )
                    affected = []
                    for item in result["findings"]:
                        if item["page"] != decision["page"] or item["ruleId"] in [
                            "page-correspondence-problem",
                            "page-geometry-change",
                        ]:
                            continue
                        boxes = [
                            BBox(*item[key])
                            for key in ["referenceBBox", "candidateBBox"]
                            if item[key]
                        ]
                        if boxes and all(box.contains(b) for b in boxes):
                            item["reviewState"] = "region-accepted"
                            affected.append(item["id"])
                    state.update(
                        state="applied",
                        explanation="Limited region accepted by reviewer; covered evidence retained.",
                        affectedFindings=affected,
                    )
        result["decisions"].append(state)
    update_summary(result)
    validate_report_semantics(result)
    return result


def apply_review(report_path: Path, decisions_path: Path, out: Path) -> JSON:
    from slidetransit.report import write_report

    report = load_json(report_path, DEFAULT_LIMITS.report_json_bytes)
    validate_report_semantics(report)
    result = apply_decisions(report, load_json(decisions_path))
    with atomic_output(out, [report_path, decisions_path]) as working:
        # Copy only referenced PNGs inside the original bundle. No arbitrary files.
        (working / "assets").mkdir()
        with bundle_assets(report_path.absolute().parent, DEFAULT_LIMITS) as assets:
            for name in sorted(asset_names(report)):
                (working / name).write_bytes(assets.read(name))
        write_report(result, working, DEFAULT_LIMITS)
        (working / "report.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        )
    return result
