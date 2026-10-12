"""Conservative slide-part-local source attribution; no presentation rendering."""

from __future__ import annotations

import posixpath
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from defusedxml import ElementTree

from slidetransit.limits import Limits, read_pptx
from slidetransit.models import JSON, BBox, TransitError, normalize

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


@dataclass
class Deck:
    width: float
    height: float
    slides: list[list[JSON]]
    hidden: list[int]
    anchor_counts: list[dict[str, int]]


def read_deck(path: Path, limits: Limits) -> Deck:
    parts = read_pptx(path, limits)
    presentation = ElementTree.fromstring(parts["ppt/presentation.xml"])
    size = presentation.find("p:sldSz", NS)
    if size is None:
        raise TransitError("PPTX has no slide dimensions")
    width, height = int(size.attrib["cx"]) / 12700, int(size.attrib["cy"]) / 12700
    BBox(0, 0, width, height)
    if width <= 0 or height <= 0:
        raise TransitError("invalid PPTX dimensions")
    try:
        relationships = ElementTree.fromstring(parts["ppt/_rels/presentation.xml.rels"])
        targets = {
            r.attrib["Id"]: posixpath.normpath("ppt/" + r.attrib["Target"])
            for r in relationships
            if r.attrib.get("TargetMode") != "External"
        }
        ordered = [
            targets[s.attrib["{" + NS["r"] + "}id"]]
            for s in presentation.findall("p:sldIdLst/p:sldId", NS)
        ]
    except KeyError as exc:
        raise TransitError("PPTX slide relationships are incomplete") from exc
    if not ordered or len(ordered) > limits.pages:
        raise TransitError("PPTX has no slides or exceeds slide limit")
    slides, hidden, anchor_counts = [], [], []
    for index, part in enumerate(ordered, 1):
        if part not in parts:
            raise TransitError("missing PPTX slide part")
        slide = ElementTree.fromstring(parts[part])
        if slide.attrib.get("show", "1") in ["0", "false"]:
            hidden.append(index)
        objects = []
        all_texts = []
        for shape in slide.findall(".//p:sp", NS):
            all_texts.append(
                normalize(
                    " ".join(
                        "".join(t.text or "" for t in paragraph.findall(".//a:t", NS))
                        for paragraph in shape.findall("p:txBody/a:p", NS)
                    )
                )
            )
        anchor_counts.append(dict(Counter(all_texts)))
        # Direct children only: groups and inherited transforms never receive an ID.
        for shape in slide.findall("p:cSld/p:spTree/p:sp", NS):
            paragraphs = []
            for paragraph in shape.findall("p:txBody/a:p", NS):
                paragraphs.append("".join(t.text or "" for t in paragraph.findall(".//a:t", NS)))
            text = normalize(" ".join(paragraphs))
            xfrm = shape.find("p:spPr/a:xfrm", NS)
            identity = shape.find("p:nvSpPr/p:cNvPr", NS)
            placeholder = shape.find("p:nvSpPr/p:nvPr/p:ph", NS)
            if not text or xfrm is None or identity is None or placeholder is not None:
                continue
            if any(
                xfrm.attrib.get(key, "0") not in ["0", "false"] for key in ["rot", "flipH", "flipV"]
            ):
                continue
            off, ext = xfrm.find("a:off", NS), xfrm.find("a:ext", NS)
            if off is None or ext is None:
                continue
            x, y = int(off.attrib["x"]) / 12700, int(off.attrib["y"]) / 12700
            w, h = int(ext.attrib["cx"]) / 12700, int(ext.attrib["cy"]) / 12700
            objects.append(
                {
                    "slidePart": part,
                    "shapeId": identity.attrib["id"],
                    "text": text,
                    "bbox": BBox(x, y, x + w, y + h).values(),
                }
            )
        slides.append(objects)
    return Deck(width, height, slides, hidden, anchor_counts)


def attribute(
    deck: Deck, source_page: int, text: str, bbox: BBox | None, page_size: tuple[float, float]
) -> JSON:
    unknown = {"status": "unattributed", "confidence": "none"}
    if not bbox or not 1 <= source_page <= len(deck.slides):
        return unknown
    if abs(deck.width - page_size[0]) > 1 or abs(deck.height - page_size[1]) > 1:
        return unknown
    if deck.anchor_counts[source_page - 1].get(normalize(text)) != 1:
        return unknown
    matching = [s for s in deck.slides[source_page - 1] if s["text"] == normalize(text)]
    if len(matching) != 1 or not BBox(*matching[0]["bbox"]).contains(bbox, margin=3):
        return unknown
    obj = matching[0]
    return {
        "status": "likely",
        "confidence": "conditional",
        "label": "Likely source object",
        "slidePart": obj["slidePart"],
        "shapeId": obj["shapeId"],
        "basis": [
            "unique exact normalized text anchor",
            "supported direct transform",
            "reference glyph box fits source shape",
            "one candidate",
        ],
        "limitation": "A heuristic association; no confirmed object identity.",
    }
