from dataclasses import replace

import numpy as np
import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfgen import canvas

from slidetransit.limits import DEFAULT_LIMITS
from slidetransit.models import TransitError
from slidetransit.pdf import inspect_pdf


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("cropped", [False, True])
def test_real_pixel_character_coordinate_canary(tmp_path, rotation, cropped):
    # Explicit synthetic unit fixture; never labelled an Office export.
    original = tmp_path / "synthetic.pdf"
    c = canvas.Canvas(str(original), pagesize=(240, 180))
    c.setFont("Helvetica", 24)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(64, 91, "HIM")
    c.save()
    reader = PdfReader(original)
    page = reader.pages[0]
    if cropped:
        page.mediabox = RectangleObject((10, 20, 250, 200))
        page.cropbox = RectangleObject((30, 40, 220, 170))
    page.rotate(rotation)
    modified = tmp_path / "rotated.pdf"
    writer = PdfWriter()
    writer.add_page(page)
    writer.write(modified)
    output = tmp_path / "raster"
    (output / "assets").mkdir(parents=True)
    result = inspect_pdf(modified, "canary", output, 150, DEFAULT_LIMITS)[0]
    from PIL import Image

    with Image.open(output / result.image_path) as image:
        ink = np.asarray(image.convert("RGB")).min(axis=2) < 100
        yy, xx = np.nonzero(ink)
        assert len(xx) > 100
        union = [
            min(ch["bbox"][0] for ch in result.characters),
            min(ch["bbox"][1] for ch in result.characters),
            max(ch["bbox"][2] for ch in result.characters),
            max(ch["bbox"][3] for ch in result.characters),
        ]
        scale = 150 / 72
        assert xx.min() >= union[0] * scale - 3
        assert xx.max() <= union[2] * scale + 3
        assert yy.min() >= union[1] * scale - 3
        assert yy.max() <= union[3] * scale + 3
        # A misplaced but overly broad box must also fail.
        assert union[2] - union[0] < 90
        assert union[3] - union[1] < 90
        for char in result.characters:
            x0, y0, x1, y1 = [round(v * scale) for v in char["bbox"]]
            assert (
                ink[
                    max(0, y0) : min(image.height, y1 + 1), max(0, x0) : min(image.width, x1 + 1)
                ].sum()
                > 20
            )
        expected = (190, 130) if cropped else (240, 180)
        if rotation in [90, 270]:
            expected = expected[::-1]
        assert (result.width, result.height) == expected


def test_no_text_layer_is_unavailable_not_visually_missing(tmp_path):
    c = canvas.Canvas(str(tmp_path / "outlined.pdf"), pagesize=(200, 150))
    c.rect(20, 30, 70, 40, fill=1)
    c.save()
    (tmp_path / "assets").mkdir()
    page = inspect_pdf(tmp_path / "outlined.pdf", "outline", tmp_path, 100, DEFAULT_LIMITS)[0]
    assert page.coverage["raster"] == "complete"
    assert page.coverage["text"] == "unavailable"


def test_pixel_limit_checked_before_render(tmp_path):
    c = canvas.Canvas(str(tmp_path / "large.pdf"), pagesize=(1200, 1200))
    c.drawString(10, 10, "large")
    c.save()
    (tmp_path / "assets").mkdir()
    with pytest.raises(TransitError, match="pixel limit"):
        inspect_pdf(
            tmp_path / "large.pdf",
            "large",
            tmp_path,
            150,
            replace(DEFAULT_LIMITS, page_pixels=1000),
        )
