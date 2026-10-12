"""Sequential PDFium rendering and pdfplumber character measurements."""

from __future__ import annotations

import math
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
import pypdfium2.raw as raw
from PIL import Image

from slidetransit.coordinates import char_bbox
from slidetransit.limits import Limits, check_file
from slidetransit.models import JSON, BBox, TextBlock, TransitError


@dataclass
class Page:
    width: float
    height: float
    rotation: int
    crop_box: list[float]
    media_box: list[float]
    blocks: list[TextBlock]
    characters: list[JSON]
    coverage: JSON
    image: Image.Image
    image_path: str


def versions() -> JSON:
    return {
        "pdfium": str(pdfium.PDFIUM_INFO),
        "pypdfium2": version("pypdfium2"),
        "pdfplumber": version("pdfplumber"),
        "pdfminer.six": version("pdfminer.six"),
        "Pillow": version("Pillow"),
        "numpy": version("numpy"),
        "render": {
            "background": [255, 255, 255, 255],
            "annotations": False,
            "forms": False,
            "grayscale": False,
            "alignment": "none",
            "normalization": "none",
        },
    }


def blocks_from_chars(chars: list[JSON]) -> list[TextBlock]:
    horizontal = [c for c in chars if c["horizontal"] and c["text"]]
    rows: list[list[JSON]] = []
    for char in sorted(horizontal, key=lambda c: (c["bbox"][1], c["bbox"][0])):
        selected = next(
            (row for row in rows[-6:] if abs(row[0]["bbox"][1] - char["bbox"][1]) <= 2), None
        )
        if selected is None:
            rows.append([char])
        else:
            selected.append(char)
    lines: list[TextBlock] = []
    for row in rows:
        segments: list[list[JSON]] = [[]]
        for char in sorted(row, key=lambda c: c["bbox"][0]):
            previous = segments[-1][-1] if segments[-1] else None
            if previous and char["bbox"][0] - previous["bbox"][2] > max(12, char["size"] * 1.2):
                segments.append([])
            segments[-1].append(char)
        for segment in segments:
            box = BBox(*segment[0]["bbox"])
            text = ""
            previous = None
            for char in segment:
                if (
                    previous
                    and char["bbox"][0] - previous["bbox"][2] > char["size"] * 0.18
                    and not text.endswith(" ")
                    and not char["text"].startswith(" ")
                ):
                    text += " "
                text += char["text"]
                box = box.union(BBox(*char["bbox"]))
                previous = char
            if text.strip():
                lines.append(
                    TextBlock(
                        text.strip(),
                        box,
                        [text.strip()],
                        sum(c["size"] for c in segment) / len(segment),
                        segment,
                    )
                )
    blocks: list[TextBlock] = []
    for line in sorted(lines, key=lambda b: (b.bbox.y0, b.bbox.x0)):
        candidate = next(
            (
                b
                for b in reversed(blocks)
                if abs(b.bbox.x0 - line.bbox.x0) < 5
                and 0 <= line.bbox.y0 - b.bbox.y1 <= max(line.size, b.size) * 0.8
                and abs(line.size - b.size) < 2
            ),
            None,
        )
        if candidate is None:
            blocks.append(line)
        else:
            candidate.text += "\n" + line.text
            candidate.lines += line.lines
            candidate.chars += line.chars
            candidate.bbox = candidate.bbox.union(line.bbox)
    return blocks


def inspect_pdf(path: Path, prefix: str, out: Path, dpi: int, limits: Limits) -> list[Page]:
    check_file(path, limits.file_bytes)
    with path.open("rb") as stream:
        if not stream.read(1024).lstrip().startswith(b"%PDF-"):
            raise TransitError("not a PDF: " + path.name)
    scale = dpi / 72
    pages: list[Page] = []
    total_characters = 0
    document = None
    try:
        document = pdfium.PdfDocument(str(path))
        if raw.FPDF_GetSecurityHandlerRevision(document) >= 0:
            raise TransitError("encrypted PDFs are unsupported")
        if not 0 < len(document) <= limits.pages:
            raise TransitError("PDF has no pages or exceeds page limit")
        with pdfplumber.open(path) as text_document:
            if len(text_document.pages) != len(document):
                raise TransitError("PDF parsers disagree on page count")
            for index in range(len(document)):
                page = document[index]
                bitmap = None
                try:
                    width, height = page.get_size()
                    if not all(math.isfinite(v) and v > 0 for v in [width, height]):
                        raise TransitError("invalid PDF page dimensions")
                    if math.ceil(width * scale) * math.ceil(height * scale) > limits.page_pixels:
                        raise TransitError("PDF page exceeds pixel limit; lower DPI")
                    bitmap = page.render(
                        scale=scale,
                        fill_color=(255, 255, 255, 255),
                        draw_annots=False,
                        may_draw_forms=False,
                    )
                    image = bitmap.to_pil().convert("RGB").copy()
                    image_path = f"assets/{prefix}-{index + 1}.png"
                    image.save(out / image_path, optimize=True)
                    text_page = text_document.pages[index]
                    media = [float(v) for v in text_page.page_obj.mediabox]
                    crop = [float(v) for v in text_page.page_obj.cropbox]
                    rotation = text_page.rotation
                    if rotation not in [0, 90, 180, 270]:
                        raise TransitError("unsupported PDF page rotation")
                    posconv = bitmap.get_posconv(page)
                    characters: list[JSON] = []
                    extracted = text_page.chars
                    total_characters += len(extracted)
                    if len(extracted) > limits.characters_per_page:
                        raise TransitError("PDF page exceeds character limit")
                    if total_characters > limits.characters_per_document:
                        raise TransitError("PDF exceeds total character limit")
                    for char in extracted:
                        box = char_bbox(
                            char, media, rotation, float(text_page.mediabox[0]), posconv, scale
                        )
                        matrix = char.get("matrix", (1, 0, 0, 1, 0, 0))
                        horizontal = (
                            abs(matrix[1]) < 0.001
                            and abs(matrix[2]) < 0.001
                            and matrix[0] > 0
                            and matrix[3] > 0
                        )
                        characters.append(
                            {
                                "text": char["text"],
                                "bbox": box.values(),
                                "size": float(char["size"]),
                                "horizontal": horizontal,
                            }
                        )
                    coverage: JSON = {
                        "raster": "complete",
                        "characters": "complete",
                        "text": "complete",
                        "geometry": "complete",
                    }
                    if not characters:
                        coverage.update(text="unavailable", geometry="unavailable")
                    elif any(not c["horizontal"] for c in characters):
                        coverage.update(text="partial", geometry="partial")
                    if any("(cid:" in c["text"] or "\ufffd" in c["text"] for c in characters):
                        coverage.update(text="partial", geometry="partial")
                    pages.append(
                        Page(
                            width,
                            height,
                            rotation,
                            crop,
                            media,
                            blocks_from_chars(characters),
                            characters,
                            coverage,
                            image,
                            image_path,
                        )
                    )
                    image.close()  # Keep only measurements on disk between page pairs.
                    text_page.close()
                finally:
                    if bitmap is not None:
                        bitmap.close()
                    page.close()
    except TransitError:
        raise
    except Exception as exc:
        # A parser error must not produce an empty PASS. Never render exception paths.
        raise TransitError("PDF parser/render failed: " + type(exc).__name__) from exc
    finally:
        if document is not None:
            document.close()
    return pages
