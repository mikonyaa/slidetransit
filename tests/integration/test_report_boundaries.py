"""Own inputs exercise imported bundles, independently of the saved exports."""

import copy
import json
import shutil

import pytest
from reportlab.pdfgen import canvas

from slidetransit.compare import run_comparison
from slidetransit.limits import sha256
from slidetransit.manifest import load_manifest
from slidetransit.models import TransitError, update_summary
from slidetransit.review import apply_review, binding


@pytest.fixture
def own_bundle(real, tmp_path):
    """Two pages: a measured text change, then an unchanged raster-only page."""
    for role, text in [("reference", "Reference 123"), ("candidate", "Candidate 456")]:
        pdf = tmp_path / (role + ".pdf")
        drawing = canvas.Canvas(str(pdf), pagesize=(240, 160), invariant=1)
        drawing.drawString(20, 100, text)
        drawing.showPage()
        drawing.rect(30, 30, 80, 40, fill=1)
        drawing.showPage()
        drawing.save()
    data = json.loads((real / "repeat.json").read_text())
    data["mode"] = "unknown"
    data["presentation"] = {"path": str(real / "baseline.pptx")}
    data["limitations"] = ["Own synthetic PDFs; no fresh Office compatibility evidence."]
    for role in ["reference", "candidate"]:
        pdf = tmp_path / (role + ".pdf")
        data[role] = {
            "path": str(pdf),
            "sha256": sha256(pdf),
            "renderer": {"name": "reportlab synthetic", "version": "4.4.4"},
            "provenanceAssurance": "unknown",
            "environment": {},
            "exportOptions": {},
        }
    manifest_path = tmp_path / "comparison.json"
    manifest_path.write_text(json.dumps(data))
    bundle = tmp_path / "bundle"
    report = run_comparison(load_manifest(manifest_path), bundle)
    decisions = {
        "schemaVersion": "1.0",
        **binding(report),
        "decisions": [
            {
                "type": "accept-difference",
                "findingId": f["id"],
                "regionHash": f["regionHash"],
                "reason": "Own synthetic change inspected",
                "author": "Boundary regression",
                "timestamp": "2026-10-14T00:00:00Z",
            }
            for f in report["findings"]
        ],
    }
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(json.dumps(decisions))
    return bundle, report, decisions_path


def test_unchanged_report_acceptance_retains_incomplete_and_copies_pngs(own_bundle, tmp_path):
    bundle, original, decisions = own_bundle
    result = apply_review(bundle / "report.json", decisions, tmp_path / "reviewed")
    assert original["analysisStatus"] == result["analysisStatus"] == "incomplete"
    assert result["summary"]["exitCode"] == 3
    assert result["summary"]["accepted"] == len(original["findings"]) > 0
    for png in (bundle / "assets").glob("*.png"):
        assert sha256(png) == sha256(tmp_path / "reviewed/assets" / png.name)


def test_missing_coverage_cannot_become_clear_after_acceptance(own_bundle, tmp_path):
    bundle, report, decisions = own_bundle
    changed = copy.deepcopy(report)
    changed["coverage"].pop()
    changed["analysisStatus"] = "complete"
    update_summary(changed)
    (bundle / "report.json").write_text(json.dumps(changed))
    with pytest.raises(TransitError, match="coverage"):
        apply_review(bundle / "report.json", decisions, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()
    assert list(tmp_path.glob(".slidetransit-*")) == []


@pytest.mark.parametrize("link", ["parent", "final"])
def test_symlinks_are_rejected_at_every_asset_component(own_bundle, tmp_path, link):
    bundle, _, decisions = own_bundle
    external = tmp_path / "own-external"
    if link == "parent":
        (bundle / "assets").rename(external)
        (bundle / "assets").symlink_to(external, target_is_directory=True)
    else:
        external.mkdir()
        image = next((bundle / "assets").glob("*.png"))
        shutil.move(image, external / image.name)
        image.symlink_to(external / image.name)
    before = {p.name: sha256(p) for p in external.glob("*.png")}
    with pytest.raises(TransitError, match="asset|image"):
        apply_review(bundle / "report.json", decisions, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()
    assert list(tmp_path.glob(".slidetransit-*")) == []
    assert before == {p.name: sha256(p) for p in external.glob("*.png")}
