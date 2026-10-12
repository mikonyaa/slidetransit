import json

import numpy as np
import pytest
from PIL import Image

from slidetransit.compare import run_comparison
from slidetransit.limits import sha256
from slidetransit.manifest import load_manifest, validate
from slidetransit.models import BBox


def test_repeat_stable_read_only(real, tmp_path):
    manifest = load_manifest(real / "repeat.json")
    before = [sha256(p) for p in manifest.inputs]
    first = run_comparison(manifest, tmp_path / "one")
    second = run_comparison(manifest, tmp_path / "two")
    assert first == second
    assert first["analysisStatus"] == "complete"
    assert first["findings"] == []
    assert first["summary"]["exitCode"] == 0
    assert before == [sha256(p) for p in manifest.inputs]
    assert manifest.hashes["reference"] != manifest.hashes["candidate"]  # metadata bytes can differ
    validate(first, "report")


@pytest.mark.parametrize(
    ("case", "rule"),
    [
        ("clipping", "possible-clipping"),
        ("deleted-text", "extracted-text-change"),
        ("deleted-image", "raster-region-change"),
        ("wrap", "line-wrap-change"),
        ("font", "raster-region-change"),
        ("symbol", "extracted-text-change"),
        ("cjk", "extracted-text-change"),
        ("displacement", "displacement"),
        ("duplicate", "displacement"),
        ("pages", "page-correspondence-problem"),
        ("aspect", "page-geometry-change"),
    ],
)
def test_real_mutation_evidence(case, rule, compare_case):
    report = compare_case(case)
    assert any(f["ruleId"] == rule for f in report["findings"])
    assert report["summary"]["exitCode"] == 1
    exports = report["provenance"]["exports"]
    assert exports["reference"]["sourceSha256"] != exports["candidate"]["sourceSha256"]
    assert report["provenance"]["mode"] == "documented-test-variant"
    if case in ["pages", "aspect"]:
        assert report["analysisStatus"] == "incomplete"


def test_real_clipping_text_is_present_in_layer(real, tmp_path):
    report = run_comparison(load_manifest(real / "clipping.json"), tmp_path / "clip")
    clip = next(f for f in report["findings"] if f["ruleId"] == "possible-clipping")
    assert "Delivery without surprises" in json.dumps(clip["evidence"])
    assert clip["candidateBBox"][3] > 405
    candidate = report["pages"][0]["candidate"]
    assert any("Delivery without surprises" in b["text"] for b in candidate["textBlocks"])
    assert clip["cropReferences"]["candidate"]
    crop = Image.open(tmp_path / "clip" / clip["cropReferences"]["candidate"]).convert("RGB")
    assert int((np.asarray(crop).min(axis=2) < 170).sum()) > 30


def test_duplicate_attribution_is_never_confirmed(compare_case):
    report = compare_case("duplicate")
    matches = [f for f in report["findings"] if f["ruleId"] == "displacement" and f["page"] == 2]
    assert matches
    assert all(f["attribution"]["status"] == "unattributed" for f in matches)
    assert report["analysisStatus"] == "complete"


def test_source_objects_are_scoped_to_slide_part(compare_case):
    report = compare_case("displacement")
    displacement = next(f for f in report["findings"] if f["ruleId"] == "displacement")
    assert displacement["attribution"]["status"] == "likely"
    assert displacement["attribution"]["slidePart"] == "ppt/slides/slide1.xml"
    assert "confirmed" not in displacement["attribution"].get("label", "").lower()


def test_unresolved_pages_are_not_compared_by_index(compare_case):
    report = compare_case("pages")
    assert [f["ruleId"] for f in report["findings"]] == ["page-correspondence-problem"]
    assert all(p["correspondence"] == "unresolved" for p in report["pages"])


def test_cjk_punctuation_and_meaningful_small_digit(compare_case):
    report = compare_case("symbol")
    finding = next(f for f in report["findings"] if f["ruleId"] == "extracted-text-change")
    assert "12.5%" in finding["evidence"]["observed"]["referenceText"]
    assert "12.6%" in finding["evidence"]["observed"]["candidateText"]
    assert finding["severity"] == "high"
    assert BBox(*finding["referenceBBox"]).x1 > 42
    assert any("東京" in b["normalized"] for b in report["pages"][0]["reference"]["textBlocks"])


def test_noise_never_creates_serious_text_finding(compare_case):
    report = compare_case("noise")
    assert not any(f["ruleId"] == "extracted-text-change" for f in report["findings"])
    assert report["summary"]["exitCode"] == 0


def test_real_fixtures_have_captured_commands_and_verified_hashes(real):
    entries = json.loads((real / "provenance.json").read_text())
    assert len(entries) >= 10
    for entry in entries.values():
        assert sha256(real / entry["path"]) == entry["sha256"]
        assert sha256(real / entry["source"]["path"]) == entry["source"]["sha256"]
        assert entry["renderer"]["name"] == "LibreOfficeDev"
        assert entry["provenanceAssurance"] == "captured-by-fixture-script"
        assert "--convert-to" in entry["command"]
        assert entry["environment"]["architecture"] == "arm64"
