"""Validate declarations while keeping provenance assurance explicit."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import jsonschema

from slidetransit.limits import check_file, load_json, sha256
from slidetransit.models import JSON, Config, TransitError


def validate(value: JSON, schema_name: str) -> None:
    import json

    schema = json.loads(
        files("slidetransit").joinpath("schemas", schema_name + ".schema.json").read_text()
    )
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(
            value
        )
    except jsonschema.ValidationError as exc:
        location = ".".join(str(p) for p in exc.absolute_path) or "root"
        raise TransitError(f"invalid {schema_name} at {location}: {exc.validator}") from exc


@dataclass
class Manifest:
    data: JSON
    presentation: Path
    reference: Path
    candidate: Path
    hashes: JSON
    provenance: JSON
    config: Config

    @property
    def inputs(self) -> list[Path]:
        return [self.presentation, self.reference, self.candidate]


def load_manifest(path: Path, overrides: dict[str, Any] | None = None) -> Manifest:
    data = load_json(path)
    validate(data, "manifest")
    root = path.resolve().parent
    paths: list[Path] = []
    hashes: JSON = {}
    for role in ["presentation", "reference", "candidate"]:
        entry = data[role]
        document = (root / entry["path"]).resolve()
        check_file(document)
        digest = sha256(document)
        if entry.get("sha256") and digest != entry["sha256"]:
            raise TransitError("SHA-256 mismatch: " + role)
        paths.append(document)
        hashes[role] = digest
    for role in ["reference", "candidate"]:
        entry = data[role]
        source = entry.get("source", {})
        digest = source.get("sha256")
        if source.get("path"):
            source_path = (root / source["path"]).resolve()
            check_file(source_path)
            if not digest or sha256(source_path) != digest:
                raise TransitError("export source SHA-256 mismatch: " + role)
        if data["mode"] == "declared-same-source" and digest and digest != hashes["presentation"]:
            raise TransitError("declared-same-source hash conflicts with presentation: " + role)
        if data["mode"] == "documented-test-variant" and not digest:
            raise TransitError("test variants require both actual source hashes")
    config_values = dict(data.get("config", {}))
    config_values.update(overrides or {})
    config = Config(**config_values)
    # Deliberately omit filesystem paths from public-facing data.
    exports: JSON = {}
    for role in ["reference", "candidate"]:
        entry = data[role]
        exports[role] = {
            k: entry[k]
            for k in [
                "renderer",
                "provenanceAssurance",
                "exportOptions",
                "environment",
                "capturedAt",
                "command",
            ]
            if k in entry
        }
        exports[role]["sourceSha256"] = entry.get("source", {}).get("sha256")
    provenance = {
        "mode": data["mode"],
        "exports": exports,
        "statement": "Export declarations are not cryptographic proof of the export chain.",
        "scope": data["scope"],
        "limitations": data["limitations"],
    }
    return Manifest(data, paths[0], paths[1], paths[2], hashes, provenance, config)
