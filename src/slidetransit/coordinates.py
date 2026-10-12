"""A single display transform for text and PDFium page images.

pdfminer applies its MediaBox/Rotate CTM before pdfplumber exposes chars.
We invert that CTM, then use the actual bitmap's PDFium page-to-device
conversion. Display coordinates are pixels divided by scale, top-left points.
"""

from __future__ import annotations

from typing import Any

from slidetransit.models import BBox


def undo_miner(x: float, y: float, media: list[float], rotation: int) -> tuple[float, float]:
    x0, y0, x1, y1 = media
    if rotation == 90:
        return x1 - y, x + y0
    if rotation == 180:
        return x1 - x, y1 - y
    if rotation == 270:
        return y + x0, y1 - x
    return x + x0, y + y0


def char_bbox(
    char: dict[str, Any],
    media: list[float],
    rotation: int,
    plumber_offset: float,
    posconv: Any,
    scale: float,
) -> BBox:
    points = []
    for x in [float(char["x0"]) - plumber_offset, float(char["x1"]) - plumber_offset]:
        for y in [float(char["y0"]), float(char["y1"])]:
            px, py = undo_miner(x, y, media, rotation)
            bx, by = posconv.to_bitmap(px, py)
            points.append((bx / scale, by / scale))
    return BBox(
        min(p[0] for p in points),
        min(p[1] for p in points),
        max(p[0] for p in points),
        max(p[1] for p in points),
    )
