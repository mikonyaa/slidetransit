"""Measurement types and deterministic fingerprints, separate from presentation."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any

JSON = dict[str, Any]
RULE_VERSION = "1.0"
SEVERITIES = {"info": 0, "low": 1, "medium": 2, "high": 3}


class TransitError(ValueError):
    """An actionable input or resource error, safe to display without traceback."""


def fingerprint(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def normalize(text: str) -> str:
    """NFC and whitespace only: retain numbers, punctuation, case and CJK."""
    return " ".join(unicodedata.normalize("NFC", text).split())


@dataclass(frozen=True)
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if (
            not all(math.isfinite(v) for v in self.values())
            or self.x1 < self.x0
            or self.y1 < self.y0
        ):
            raise TransitError("invalid bounding box")

    def values(self) -> list[float]:
        return [round(self.x0, 4), round(self.y0, 4), round(self.x1, 4), round(self.y1, 4)]

    def union(self, other: BBox) -> BBox:
        return BBox(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )

    def contains(self, other: BBox, margin: float = 0) -> bool:
        return (
            self.x0 - margin <= other.x0
            and self.y0 - margin <= other.y0
            and self.x1 + margin >= other.x1
            and self.y1 + margin >= other.y1
        )

    def intersects(self, other: BBox) -> bool:
        return (
            self.x0 < other.x1 and other.x0 < self.x1 and self.y0 < other.y1 and other.y0 < self.y1
        )


@dataclass(frozen=True)
class Config:
    dpi: int = 150
    pixel_delta: int = 16
    displacement_pt: float = 2.0
    size_pt: float = 1.5
    fail_on: str = "medium"

    def __post_init__(self) -> None:
        if not 36 <= self.dpi <= 200 or not 1 <= self.pixel_delta <= 254:
            raise TransitError("DPI must be 36..200 and pixelDelta must be 1..254")
        if not all(math.isfinite(v) and 0 < v <= 72 for v in [self.displacement_pt, self.size_pt]):
            raise TransitError("geometry thresholds must be finite and in (0, 72] points")
        if self.fail_on not in SEVERITIES:
            raise TransitError("unknown severity threshold")

    def json(self) -> JSON:
        return asdict(self)


@dataclass
class TextBlock:
    text: str
    bbox: BBox
    lines: list[str]
    size: float
    chars: list[JSON]

    @property
    def normalized(self) -> str:
        return normalize(self.text)


def finding(
    rule: str,
    page: int | None,
    severity: str,
    title: str,
    evidence: JSON,
    reference: BBox | None = None,
    candidate: BBox | None = None,
) -> JSON:
    region = {
        "referenceBBox": reference.values() if reference else None,
        "candidateBBox": candidate.values() if candidate else None,
    }
    basis = {
        "ruleId": rule,
        "ruleVersion": RULE_VERSION,
        "page": page,
        **region,
        "evidence": evidence,
    }
    return {
        "id": fingerprint(basis)[:24],
        "regionHash": fingerprint(region),
        "severity": severity,
        "title": title,
        **basis,
        "cropReferences": {},
        "attribution": {"status": "unattributed", "confidence": "none"},
        "reviewState": "open",
    }


def update_summary(report: JSON) -> int:
    threshold = SEVERITIES[report["config"]["fail_on"]]
    findings = report["findings"]
    pending = [
        f for f in findings if f["reviewState"] == "open" and SEVERITIES[f["severity"]] >= threshold
    ]
    status = report["analysisStatus"]
    code = 2 if status == "error" else 1 if pending else 3 if status == "incomplete" else 0
    report["summary"] = {
        "findings": len(findings),
        "unhandledAtThreshold": len(pending),
        "accepted": sum(f["reviewState"] == "accepted" for f in findings),
        "regionAccepted": sum(f["reviewState"] == "region-accepted" for f in findings),
        "staleDecisions": sum(d["state"] == "stale" for d in report["decisions"]),
        "exitCode": code,
        "result": "differences"
        if code == 1
        else "incomplete"
        if code == 3
        else "error"
        if code == 2
        else "checked-scope-clear",
    }
    return code
