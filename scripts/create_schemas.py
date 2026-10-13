"""Maintain the v1 JSON schemas without a runtime generator dependency."""

import json
from pathlib import Path

from slidetransit.limits import DEFAULT_LIMITS


def main():
    root = Path(__file__).resolve().parents[1] / "src/slidetransit/schemas"
    root.mkdir(parents=True, exist_ok=True)
    string = {"type": "string"}
    digest = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    box = {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4}
    object_ = {"type": "object"}
    integer = {"type": "integer", "minimum": 1}
    positive = {"type": "number", "exclusiveMinimum": 0}
    asset = {"type": "string", "pattern": r"^assets/[^/\\:\u0000]+\.png$"}
    channel = {"enum": ["complete", "partial", "unavailable", "absent"]}
    correspondence = {"enum": ["declared-order", "unresolved"]}

    def obj(properties, required=None, extra=False):
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": extra,
        }

    def schema(name, value):
        value = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://mikonyaa.github.io/slidetransit/schemas/{name}-1.0.json",
            **value,
        }
        (root / (name + ".schema.json")).write_text(json.dumps(value, indent=2) + "\n")

    source = obj({"path": string, "sha256": digest}, ["sha256"])
    export = obj(
        {
            "path": string,
            "sha256": digest,
            "source": source,
            "renderer": obj({"name": string, "version": string}),
            "provenanceAssurance": {
                "enum": ["user-declared", "captured-by-fixture-script", "unknown"]
            },
            "exportOptions": object_,
            "environment": object_,
            "capturedAt": string,
            "command": {"type": "array", "items": string},
        },
        ["path", "renderer", "provenanceAssurance", "exportOptions", "environment"],
    )
    schema(
        "manifest",
        obj(
            {
                "schemaVersion": {"const": "1.0"},
                "mode": {"enum": ["declared-same-source", "documented-test-variant", "unknown"]},
                "presentation": obj({"path": string, "sha256": digest}, ["path"]),
                "reference": export,
                "candidate": export,
                "scope": obj(
                    {
                        "slideRange": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 1},
                            "minItems": 2,
                            "maxItems": 2,
                        },
                        "pageOrder": {"const": "source-order"},
                        "kind": {"const": "slides"},
                        "includeHidden": {"type": "boolean"},
                    }
                ),
                "limitations": {"type": "array", "items": string},
                "config": obj(
                    {
                        "dpi": {"type": "integer", "minimum": 36, "maximum": 200},
                        "pixel_delta": {"type": "integer", "minimum": 1, "maximum": 254},
                        "displacement_pt": {"type": "number", "exclusiveMinimum": 0, "maximum": 72},
                        "size_pt": {"type": "number", "exclusiveMinimum": 0, "maximum": 72},
                        "fail_on": {"enum": ["info", "low", "medium", "high"]},
                    },
                    [],
                ),
            },
            [
                "schemaVersion",
                "mode",
                "presentation",
                "reference",
                "candidate",
                "scope",
                "limitations",
            ],
        ),
    )
    nullable_box = {"anyOf": [box, {"type": "null"}]}
    finding = obj(
        {
            "id": {"type": "string", "pattern": "^[0-9a-f]{24}$"},
            "regionHash": digest,
            "ruleId": string,
            "ruleVersion": string,
            "page": {"type": ["integer", "null"], "minimum": 1},
            "severity": {"enum": ["info", "low", "medium", "high"]},
            "title": string,
            "evidence": object_,
            "referenceBBox": nullable_box,
            "candidateBBox": nullable_box,
            "cropReferences": obj({"reference": string, "candidate": string}, []),
            "attribution": object_,
            "reviewState": {"enum": ["open", "accepted", "region-accepted"]},
        }
    )
    inputs = obj({"presentation": digest, "reference": digest, "candidate": digest})
    common = {
        "comparisonId": digest,
        "inputs": inputs,
        "rules": obj(
            {"version": string, "hash": digest, "implementationHash": digest, "parameters": object_}
        ),
        "renderer": object_,
    }
    base = {
        "type": {"enum": ["accept-difference", "ignore-region"]},
        "reason": {"type": "string", "minLength": 1, "maxLength": 2000},
        "timestamp": {"type": "string", "format": "date-time"},
        "author": {"type": "string", "minLength": 1, "maxLength": 100},
        "regionHash": digest,
    }
    accept = obj(
        {**base, "type": {"const": "accept-difference"}, "findingId": string},
        ["type", "reason", "timestamp", "regionHash", "findingId"],
    )
    region = obj(
        {
            **base,
            "type": {"const": "ignore-region"},
            "page": {"type": "integer", "minimum": 1},
            "region": box,
        },
        ["type", "reason", "timestamp", "regionHash", "page", "region"],
    )
    config = obj(
        {
            "dpi": {"type": "integer", "minimum": 36, "maximum": 200},
            "pixel_delta": {"type": "integer", "minimum": 1, "maximum": 254},
            "displacement_pt": {"type": "number", "exclusiveMinimum": 0, "maximum": 72},
            "size_pt": {"type": "number", "exclusiveMinimum": 0, "maximum": 72},
            "fail_on": {"enum": ["info", "low", "medium", "high"]},
        }
    )
    character = obj(
        {"text": string, "bbox": box, "size": positive, "horizontal": {"type": "boolean"}}
    )
    block = obj(
        {
            "text": string,
            "normalized": string,
            "bbox": box,
            "lines": {"type": "array", "items": string},
            "sizePt": positive,
            "characters": {
                "type": "array",
                "items": character,
                "maxItems": DEFAULT_LIMITS.characters_per_page,
            },
        }
    )
    image = obj(
        {
            "width": positive,
            "height": positive,
            "rotation": {"enum": [0, 90, 180, 270]},
            "mediaBox": box,
            "cropBox": box,
            "image": asset,
            "rasterSize": {"type": "array", "items": integer, "minItems": 2, "maxItems": 2},
            "textBlocks": {
                "type": "array",
                "items": block,
                "maxItems": DEFAULT_LIMITS.characters_per_page,
            },
        },
        ["width", "height", "rotation", "mediaBox", "cropBox", "image", "textBlocks"],
    )
    page = obj(
        {
            "page": integer,
            "sourceSlide": integer,
            "correspondence": correspondence,
            "reference": {"anyOf": [image, {"type": "null"}]},
            "candidate": {"anyOf": [image, {"type": "null"}]},
            "mask": asset,
        },
        ["page", "sourceSlide", "correspondence", "reference", "candidate"],
    )
    channels = obj(
        {"raster": channel, "text": channel, "geometry": channel, "characters": channel},
        ["raster", "text", "geometry"],
    )
    coverage = obj(
        {
            "page": integer,
            "correspondence": correspondence,
            "reference": channels,
            "candidate": channels,
            "rasterComparison": {
                "enum": [
                    "complete",
                    "unavailable-different-page-size",
                    "unavailable-different-raster-grid",
                    "unavailable-unresolved-correspondence",
                ]
            },
        },
        ["page", "correspondence", "reference", "candidate"],
    )
    decision_record = obj(
        {
            "decision": {"oneOf": [accept, region]},
            "state": {"enum": ["applied", "stale"]},
            "explanation": string,
            "affectedFindings": {
                "type": "array",
                "items": string,
                "maxItems": DEFAULT_LIMITS.findings,
            },
        },
        ["decision", "state", "explanation"],
    )
    count = {"type": "integer", "minimum": 0, "maximum": DEFAULT_LIMITS.findings}
    summary = obj(
        {
            "findings": count,
            "unhandledAtThreshold": count,
            "accepted": count,
            "regionAccepted": count,
            "staleDecisions": count,
            "exitCode": {"enum": [0, 1, 2, 3]},
            "result": {"enum": ["differences", "incomplete", "error", "checked-scope-clear"]},
        }
    )
    schema(
        "report",
        obj(
            {
                "schemaVersion": {"const": "1.0"},
                "tool": obj({"name": {"const": "SlideTransit"}, "version": string}),
                **common,
                "config": config,
                "provenance": obj(
                    {
                        "mode": {
                            "enum": ["declared-same-source", "documented-test-variant", "unknown"]
                        },
                        "scope": obj(
                            {
                                "slideRange": {
                                    "type": "array",
                                    "items": integer,
                                    "minItems": 2,
                                    "maxItems": 2,
                                },
                                "pageOrder": {"const": "source-order"},
                                "kind": {"const": "slides"},
                                "includeHidden": {"type": "boolean"},
                            }
                        ),
                        "exports": obj({"reference": object_, "candidate": object_}),
                        "statement": string,
                        "limitations": {"type": "array", "items": string},
                    }
                ),
                "coordinates": string,
                "analysisStatus": {"enum": ["complete", "incomplete", "error"]},
                "coverage": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": DEFAULT_LIMITS.pages,
                    "items": coverage,
                },
                "pages": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": DEFAULT_LIMITS.pages,
                    "items": page,
                },
                "findings": {
                    "type": "array",
                    "maxItems": DEFAULT_LIMITS.findings,
                    "items": finding,
                },
                "decisions": {
                    "type": "array",
                    "maxItems": DEFAULT_LIMITS.findings,
                    "items": decision_record,
                },
                "limits": obj({name: integer for name in DEFAULT_LIMITS.json()}),
                "limitations": {"type": "array", "items": string},
                "summary": summary,
            }
        ),
    )
    schema(
        "decisions",
        obj(
            {
                "schemaVersion": {"const": "1.0"},
                **common,
                "decisions": {
                    "type": "array",
                    "maxItems": 5000,
                    "items": {"oneOf": [accept, region]},
                },
            }
        ),
    )


if __name__ == "__main__":
    main()
