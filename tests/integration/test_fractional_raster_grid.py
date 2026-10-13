"""Native PDFium grids on both sides of a fractional point rounding boundary."""

import json

import pytest
from PIL import Image
from reportlab.pdfgen import canvas

from slidetransit.compare import run_comparison
from slidetransit.limits import sha256
from slidetransit.manifest import load_manifest


def fractional_manifest(real, tmp_path, width, dpi, shift=0):
    for role, size in [("reference", 240.0), ("candidate", width)]:
        pdf = tmp_path / (role + ".pdf")
        drawing = canvas.Canvas(str(pdf), pagesize=(size, 160), invariant=1)
        drawing.drawString(20 + (shift if role == "candidate" else 0), 100, "Same content 123")
        drawing.save()
    data = json.loads((real / "repeat.json").read_text())
    data["mode"] = "unknown"
    data["scope"]["slideRange"] = [1, 1]
    data["presentation"] = {"path": str(real / "baseline.pptx")}
    data["config"] = {"dpi": dpi}
    data["limitations"] = ["Own synthetic PDFs; no fresh exporter compatibility claim."]
    for role in ["reference", "candidate"]:
        pdf = tmp_path / (role + ".pdf")
        data[role] = {
            "path": str(pdf),
            "sha256": sha256(pdf),
            "renderer": {"name": "reportlab synthetic", "version": "4.4.4"},
            "provenanceAssurance": "unknown",
            "exportOptions": {},
            "environment": {},
        }
    manifest = tmp_path / "comparison.json"
    manifest.write_text(json.dumps(data))
    return load_manifest(manifest)


@pytest.mark.parametrize("dpi", [72, 144, 150, 151, 199, 200])
@pytest.mark.parametrize("width", [239.9, 240.1])
def test_fractional_sizes_always_commit_honest_channel_coverage(real, tmp_path, dpi, width):
    report = run_comparison(fractional_manifest(real, tmp_path, width, dpi), tmp_path / "report")
    sizes = []
    for role in ["reference", "candidate"]:
        page = report["pages"][0][role]
        with Image.open(tmp_path / "report" / page["image"]) as image:
            sizes.append(image.size)
        assert page["rasterSize"] == list(sizes[-1])
        assert report["coverage"][0][role] == {
            "raster": "complete",
            "characters": "complete",
            "text": "complete",
            "geometry": "complete",
        }
    coverage = report["coverage"][0]["rasterComparison"]
    if sizes[0] == sizes[1]:
        assert coverage == "complete"
        assert report["analysisStatus"] == "complete"
        assert report["summary"]["exitCode"] in [0, 1]
        assert report["pages"][0]["mask"]
    else:
        assert coverage == "unavailable-different-raster-grid"
        assert report["analysisStatus"] == "incomplete"
        assert report["summary"]["exitCode"] == 3
        assert "mask" not in report["pages"][0]
        assert any("native raster grids" in message for message in report["limitations"])


def test_unavailable_raster_retains_text_geometry_findings_and_crops(real, tmp_path):
    report = run_comparison(
        fractional_manifest(real, tmp_path, 239.9, 150, shift=8), tmp_path / "report"
    )
    assert report["coverage"][0]["rasterComparison"] == "unavailable-different-raster-grid"
    assert report["analysisStatus"] == "incomplete" and report["summary"]["exitCode"] == 1
    item = next(f for f in report["findings"] if f["ruleId"] == "displacement")
    assert set(item["cropReferences"]) == {"reference", "candidate"}
    assert not any(f["ruleId"] == "raster-region-change" for f in report["findings"])
