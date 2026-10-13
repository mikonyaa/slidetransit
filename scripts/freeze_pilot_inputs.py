"""Freeze supplied fresh exports and declared context; this script does not export or attest them."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from slidetransit.limits import atomic_output, check_file, load_json, sha256
from slidetransit.manifest import load_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in [
        "source",
        "reference",
        "repeat",
        "candidate",
        "fixed-source",
        "fixed",
        "context",
        "out",
    ]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    inputs = [
        args.source,
        args.reference,
        args.repeat,
        args.candidate,
        args.fixed_source,
        args.fixed,
        args.context,
    ]
    for path in inputs:
        check_file(path)
    context = load_json(args.context)
    original_hashes = {str(p.absolute()): sha256(p) for p in inputs}
    with atomic_output(args.out, inputs) as stage:
        mapping = {
            "source.pptx": args.source,
            "reference.pdf": args.reference,
            "repeat.pdf": args.repeat,
            "candidate.pdf": args.candidate,
            "fixed-source.pptx": args.fixed_source,
            "fixed.pdf": args.fixed,
            "declared-context.json": args.context,
        }
        for name, source in mapping.items():
            shutil.copyfile(source, stage / name)
        hashes = {name: sha256(stage / name) for name in mapping}
        for case in ["repeat", "candidate", "fixed"]:
            variant = case == "fixed" and hashes["source.pptx"] != hashes["fixed-source.pptx"]
            manifest = {
                "schemaVersion": "1.0",
                "mode": "documented-test-variant" if variant else "declared-same-source",
                "presentation": {"path": "source.pptx", "sha256": hashes["source.pptx"]},
                "scope": context["scope"],
                "config": context.get("config", {}),
                "limitations": context["limitations"]
                + [
                    "Export context is user-declared; freezing bytes does not prove the export chain or an independent review."
                ],
            }
            for role, export in [("reference", "reference"), ("candidate", case)]:
                declaration = context["exports"][export]
                source_name = "fixed-source.pptx" if export == "fixed" else "source.pptx"
                manifest[role] = {
                    "path": export + ".pdf",
                    "sha256": hashes[export + ".pdf"],
                    "source": {"path": source_name, "sha256": hashes[source_name]},
                    "renderer": declaration["renderer"],
                    "environment": declaration["environment"],
                    "exportOptions": declaration["exportOptions"],
                    "provenanceAssurance": "user-declared",
                    "capturedAt": declaration.get("capturedAt", "unknown"),
                }
            path = stage / (case + ".json")
            path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
            load_manifest(path)
        if original_hashes != {str(p.absolute()): sha256(p) for p in inputs}:
            raise ValueError("input bytes changed while freezing")
        for path in sorted(stage.iterdir()):
            hashes[path.name] = sha256(path)
        (stage / "input-hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")
        for path in stage.iterdir():
            path.chmod(0o444)  # Only owned copies; supplied inputs stay untouched.
    print(
        json.dumps(
            {"result": "supplied-inputs-frozen", "hashes": hashes, "assurance": "user-declared"}
        )
    )


if __name__ == "__main__":
    main()
