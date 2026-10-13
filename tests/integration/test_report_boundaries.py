"""Own inputs exercise imported bundles, independently of the saved exports."""

import copy
import json
import shutil

import pytest
from reportlab.pdfgen import canvas

from slidetransit.compare import run_comparison
from slidetransit.limits import DEFAULT_LIMITS, sha256
from slidetransit.manifest import load_manifest
from slidetransit.models import TransitError, update_summary
from slidetransit.report import write_report
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


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate-coverage",
        "out-of-range-coverage",
        "duplicate-page",
        "unknown-channel",
        "unknown-state",
        "dangling-finding",
        "duplicate-finding",
        "dangling-asset",
        "escape-asset",
        "fabricated-summary",
        "false-complete",
        "unsupported-acceptance",
        "wrong-raster-size",
    ],
)
def test_malformed_import_is_rejected_without_committed_output(own_bundle, tmp_path, mutation):
    bundle, original, decisions = own_bundle
    report = copy.deepcopy(original)
    if mutation == "duplicate-coverage":
        report["coverage"].append(copy.deepcopy(report["coverage"][0]))
    elif mutation == "out-of-range-coverage":
        report["coverage"][-1]["page"] = 999
    elif mutation == "duplicate-page":
        report["pages"][-1]["page"] = 1
    elif mutation == "unknown-channel":
        report["coverage"][0]["candidate"]["invented"] = "complete"
    elif mutation == "unknown-state":
        report["coverage"][0]["candidate"]["text"] = "magically-complete"
    elif mutation == "dangling-finding":
        report["findings"][0]["page"] = 999
    elif mutation == "duplicate-finding":
        report["findings"].append(copy.deepcopy(report["findings"][0]))
    elif mutation == "dangling-asset":
        report["pages"][0]["candidate"]["image"] = "assets/missing.png"
    elif mutation == "escape-asset":
        report["pages"][0]["candidate"]["image"] = "assets/../own-external.png"
    elif mutation == "fabricated-summary":
        report["summary"]["unhandledAtThreshold"] = 0
    elif mutation == "false-complete":
        report["analysisStatus"] = "complete"
    elif mutation == "unsupported-acceptance":
        report["findings"][0]["reviewState"] = "accepted"
        update_summary(report)
    elif mutation == "wrong-raster-size":
        for role in ["reference", "candidate"]:
            report["pages"][0][role]["rasterSize"] = [1, 1]
    (bundle / "report.json").write_text(json.dumps(report))
    with pytest.raises(TransitError):
        apply_review(bundle / "report.json", decisions, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()
    assert list(tmp_path.glob(".slidetransit-*")) == []


def test_render_uses_same_semantic_and_asset_boundaries(own_bundle):
    bundle, original, _ = own_bundle
    before = (bundle / "report.html").read_bytes()
    changed = copy.deepcopy(original)
    changed["coverage"].pop()
    with pytest.raises(TransitError, match="coverage"):
        write_report(changed, bundle, DEFAULT_LIMITS)
    assert (bundle / "report.html").read_bytes() == before


@pytest.mark.parametrize("kind", ["non-png", "corrupt-png", "missing", "oversized", "over-budget"])
def test_invalid_assets_are_rejected_with_rollback(own_bundle, tmp_path, monkeypatch, kind):
    from dataclasses import replace

    from slidetransit import review

    bundle, _, decisions = own_bundle
    image = next((bundle / "assets").glob("*.png"))
    if kind == "non-png":
        from PIL import Image

        Image.new("RGB", (10, 10)).save(image, format="JPEG")
    elif kind == "corrupt-png":
        image.write_bytes(image.read_bytes()[:40])
    elif kind == "missing":
        image.unlink()
    elif kind == "oversized":
        monkeypatch.setattr(review, "DEFAULT_LIMITS", replace(DEFAULT_LIMITS, file_bytes=1))
    else:
        monkeypatch.setattr(review, "DEFAULT_LIMITS", replace(DEFAULT_LIMITS, output_bytes=2))
    with pytest.raises(TransitError, match="asset|image|PNG|budget"):
        apply_review(bundle / "report.json", decisions, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()
    assert list(tmp_path.glob(".slidetransit-*")) == []


def test_existing_output_sentinel_survives_review(own_bundle, tmp_path):
    bundle, _, decisions = own_bundle
    out = tmp_path / "existing"
    out.mkdir()
    (out / "sentinel").write_bytes(b"other session")
    with pytest.raises(TransitError, match="already exists"):
        apply_review(bundle / "report.json", decisions, out)
    assert (out / "sentinel").read_bytes() == b"other session"


def test_applied_decision_dangling_reference_is_invalid_but_stale_is_retained(own_bundle, tmp_path):
    from slidetransit.report_validation import validate_report_semantics
    from slidetransit.review import apply_decisions

    _, report, decisions = own_bundle
    reviewed = apply_decisions(report, json.loads(decisions.read_text()))
    changed = copy.deepcopy(reviewed)
    changed["decisions"][0]["decision"]["findingId"] = "f" * 24
    with pytest.raises(TransitError, match="dangling"):
        validate_report_semantics(changed)
    document = json.loads(decisions.read_text())
    document["comparisonId"] = "f" * 64
    stale = apply_decisions(report, document)
    assert stale["summary"]["staleDecisions"] == len(report["findings"])
    assert stale["summary"]["accepted"] == 0 and stale["summary"]["exitCode"] == 1


def test_historical_report_without_optional_raster_size_remains_reviewable(own_bundle, tmp_path):
    bundle, report, decisions = own_bundle
    for page in report["pages"]:
        for role in ["reference", "candidate"]:
            page[role].pop("rasterSize")
    (bundle / "report.json").write_text(json.dumps(report))
    assert (
        apply_review(bundle / "report.json", decisions, tmp_path / "reviewed")["summary"][
            "exitCode"
        ]
        == 3
    )
