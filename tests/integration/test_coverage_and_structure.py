import json
import zipfile
from dataclasses import replace

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from slidetransit.compare import run_comparison
from slidetransit.limits import DEFAULT_LIMITS, sha256
from slidetransit.manifest import load_manifest
from slidetransit.models import BBox, TransitError
from slidetransit.pdf import inspect_pdf
from slidetransit.pptx import attribute, read_deck


def unit_manifest(real, tmp_path, reference, candidate):
    data = json.loads((real / "repeat.json").read_text())
    data["mode"] = "unknown"
    data["presentation"]["path"] = str(real / "baseline.pptx")
    for role, pdf in [("reference", reference), ("candidate", candidate)]:
        data[role] = {
            "path": str(pdf),
            "sha256": sha256(pdf),
            "renderer": {"name": "synthetic-unit-fixture", "version": "explicit unknown"},
            "provenanceAssurance": "unknown",
            "environment": {},
            "exportOptions": {},
        }
    data["limitations"] = ["Synthetic unit PDF; not an Office or LibreOffice export."]
    path = tmp_path / "unit.json"
    path.write_text(json.dumps(data))
    return load_manifest(path)


def test_identical_image_only_pdf_cannot_pass_required_text_channel(real, tmp_path):
    pdf = tmp_path / "image-only-unit.pdf"
    c = canvas.Canvas(str(pdf), pagesize=(720, 405))
    for _ in range(2):
        c.rect(30, 30, 120, 90, fill=1)
        c.showPage()
    c.save()
    report = run_comparison(unit_manifest(real, tmp_path, pdf, pdf), tmp_path / "report")
    assert report["findings"] == []
    assert report["analysisStatus"] == "incomplete"
    assert report["summary"]["exitCode"] == 3
    assert all(p["reference"]["text"] == "unavailable" for p in report["coverage"])


def test_detected_reorder_never_forces_index_pairing(real, tmp_path):
    reader = PdfReader(real / "baseline.pdf")
    writer = PdfWriter()
    for page in reversed(reader.pages):
        writer.add_page(page)
    reordered = tmp_path / "reordered-unit.pdf"
    writer.write(reordered)
    report = run_comparison(
        unit_manifest(real, tmp_path, real / "baseline.pdf", reordered), tmp_path / "report"
    )
    assert report["analysisStatus"] == "incomplete"
    assert len(report["findings"]) == 1
    assert report["findings"][0]["ruleId"] == "page-correspondence-problem"
    assert report["findings"][0]["evidence"]["observed"]["orderConflicts"]


def test_encrypted_pdf_is_rejected(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=100)
    writer.encrypt("secret")
    pdf = tmp_path / "encrypted.pdf"
    writer.write(pdf)
    (tmp_path / "assets").mkdir()
    with pytest.raises(TransitError, match="parser/render|encrypted"):
        inspect_pdf(pdf, "bad", tmp_path, 100, DEFAULT_LIMITS)


def test_total_character_limit(tmp_path):
    pdf = tmp_path / "text.pdf"
    c = canvas.Canvas(str(pdf))
    c.drawString(40, 80, "A modest character budget canary")
    c.save()
    (tmp_path / "assets").mkdir()
    with pytest.raises(TransitError, match="total character"):
        inspect_pdf(pdf, "large", tmp_path, 72, replace(DEFAULT_LIMITS, characters_per_document=10))


def test_grouped_duplicate_anchor_prevents_false_attribution(real, tmp_path):
    # Add a duplicate anchor inside an unsupported group to the own source.
    from lxml import etree

    source = real / "baseline.pptx"
    mutated = tmp_path / "grouped.pptx"
    pns = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
    with zipfile.ZipFile(source) as z, zipfile.ZipFile(mutated, "w") as target:
        for item in z.infolist():
            data = z.read(item)
            if item.filename == "ppt/slides/slide1.xml":
                root = etree.fromstring(data)
                tree = root.find(pns + "cSld/" + pns + "spTree")
                title = tree.findall(pns + "sp")[1]
                group = etree.SubElement(tree, pns + "grpSp")
                clone = etree.fromstring(etree.tostring(title))
                group.append(clone)
                data = etree.tostring(root)
            target.writestr(item, data)
    deck = read_deck(mutated, DEFAULT_LIMITS)
    result = attribute(deck, 1, "Delivery without surprises", BBox(42, 92, 550, 126), (720, 405))
    assert result["status"] == "unattributed"
