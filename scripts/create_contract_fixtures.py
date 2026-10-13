"""Deterministic own PDFs for mechanism probes; never labelled Office exports."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pdf(path, pages):
    """Write a minimal authored PDF using only the standard library."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Count {len(pages)} /Kids [{' '.join(f'{4 + 2 * i} 0 R' for i in range(len(pages)))}] >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, (width, draws) in enumerate(pages):
        content = [b"q 0 g"]
        for text, x, y, invisible in draws:
            escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            content.append(
                f"BT /F1 12 Tf {3 if invisible else 0} Tr {x} {y} Td ({escaped}) Tj ET".encode(
                    "ascii"
                )
            )
        content.append(b"30 30 60 20 re f Q")
        stream = b"\n".join(content) + b"\n"
        objects.extend(
            [
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width:.4f} 160] /Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * index} 0 R >>".encode(),
                f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream",
            ]
        )
    data = bytearray(b"%PDF-1.4\n% SlideTransit own synthetic contract fixture\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(data)


def create_fixtures(out, presentation):
    if out.exists():
        raise ValueError("fixture output already exists")
    out.mkdir(parents=True)
    shutil.copyfile(presentation, out / "source-context.pptx")
    normal = [
        (240, [("Anchor 123", 20, 110, False), ("Delete me", 20, 80, False)]),
        (240, [("Second page 456", 20, 110, False)]),
    ]
    pairs = {
        "repeat": (normal, normal, 150),
        "deletion": (normal, [(240, [("Anchor 123", 20, 110, False)]), normal[1]], 150),
        "shift": (
            normal,
            [(240, [("Anchor 123", 28, 110, False), ("Delete me", 28, 80, False)]), normal[1]],
            150,
        ),
        # Invisible text isolates exactly one geometry finding. Page 2 candidate has no text layer.
        "partial": (
            [
                (240, [("Geometry canary", 20, 110, True)]),
                (240, [("Text layer canary", 20, 110, True)]),
            ],
            [(240, [("Geometry canary", 28, 110, True)]), (240, [])],
            150,
        ),
        "physical-size": (normal, [(241, normal[0][1]), normal[1]], 150),
    }
    for dpi in [72, 144, 150, 151, 199, 200]:
        for width in [239.9, 240.1]:
            pairs[f"fractional-{width}-{dpi}"] = (normal, [(width, normal[0][1]), normal[1]], dpi)
    hashes = {}
    for name, (reference, candidate, dpi) in pairs.items():
        folder = out / name
        folder.mkdir()
        data = {
            "schemaVersion": "1.0",
            "mode": "unknown",
            "presentation": {
                "path": "../source-context.pptx",
                "sha256": digest(out / "source-context.pptx"),
            },
            "scope": {
                "slideRange": [1, 2],
                "pageOrder": "source-order",
                "kind": "slides",
                "includeHidden": False,
            },
            "config": {"dpi": dpi},
            "limitations": [
                "Own synthetic PDFs test mechanisms; not a fresh Office/LibreOffice export or independent pilot."
            ],
        }
        for role, pages in [("reference", reference), ("candidate", candidate)]:
            path = folder / (role + ".pdf")
            pdf(path, pages)
            data[role] = {
                "path": path.name,
                "sha256": digest(path),
                "renderer": {"name": "own stdlib PDF writer", "version": "1"},
                "provenanceAssurance": "unknown",
                "environment": {},
                "exportOptions": {},
            }
        (folder / "comparison.json").write_text(json.dumps(data, indent=2) + "\n")
    for path in sorted(out.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(out))] = digest(path)
    (out / "input-hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")
    return hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--presentation",
        type=Path,
        required=True,
        help="PPTX source context, never rendered by this script",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            {
                "result": "synthetic-fixtures-created",
                "hashes": create_fixtures(args.out, args.presentation),
            }
        )
    )


if __name__ == "__main__":
    main()
