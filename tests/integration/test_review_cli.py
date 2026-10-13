import copy
import json
import os
import shutil
import subprocess

import pytest

from slidetransit.compare import run_comparison
from slidetransit.manifest import load_manifest
from slidetransit.models import TransitError, fingerprint
from slidetransit.review import apply_decisions, apply_review, binding


def document(report):
    return {
        "schemaVersion": "1.0",
        **binding(report),
        "decisions": [
            {
                "type": "accept-difference",
                "findingId": f["id"],
                "regionHash": f["regionHash"],
                "reason": "Own documented test variant reviewed against the original.",
                "timestamp": "2026-10-12T12:00:00Z",
            }
            for f in report["findings"]
        ],
    }


def test_apply_review_and_stale_inputs_rules_renderer_region(real, tmp_path):
    original = run_comparison(load_manifest(real / "symbol.json"), tmp_path / "original")
    decisions = document(original)
    reviewed = apply_decisions(original, decisions)
    assert reviewed["summary"]["exitCode"] == 0
    assert len(reviewed["findings"]) == len(original["findings"])
    for change in ["inputs", "rules", "renderer", "region"]:
        changed = copy.deepcopy(original)
        current_decisions = copy.deepcopy(decisions)
        if change == "region":
            current_decisions["decisions"][0]["regionHash"] = "f" * 64
        elif change == "inputs":
            changed[change]["candidate"] = "f" * 64
        elif change == "rules":
            changed[change]["hash"] = "f" * 64
        else:
            changed[change]["pdfium"] = "changed"
        stale = apply_decisions(changed, current_decisions)
        assert stale["summary"]["staleDecisions"] >= 1
        assert stale["summary"]["exitCode"] == 1
    decision_path = tmp_path / "decisions.json"
    decision_path.write_text(json.dumps(decisions))
    result = apply_review(tmp_path / "original/report.json", decision_path, tmp_path / "reviewed")
    assert result["summary"]["exitCode"] == 0
    assert (tmp_path / "reviewed/report.html").stat().st_size > 10000


def test_real_pdf_change_invalidates_previous_decision(real, tmp_path):
    a = run_comparison(load_manifest(real / "symbol.json"), tmp_path / "a")
    b = run_comparison(load_manifest(real / "cjk.json"), tmp_path / "b")
    reviewed = apply_decisions(b, document(a))
    assert reviewed["summary"]["accepted"] == 0
    assert reviewed["summary"]["staleDecisions"] == len(a["findings"])


def test_limited_regions_cannot_hide_structure(real, tmp_path):
    report = run_comparison(load_manifest(real / "symbol.json"), tmp_path / "symbol")
    f = next(f for f in report["findings"] if f["ruleId"] == "extracted-text-change")
    region = f["referenceBBox"]
    region = [region[0] - 2, region[1] - 2, region[2] + 2, region[3] + 2]
    d = {
        "type": "ignore-region",
        "page": 1,
        "region": region,
        "regionHash": fingerprint({"page": 1, "region": [f"{v:.4f}" for v in region]}),
        "reason": "Reviewed metric variant",
        "timestamp": "2026-10-12T12:00:00Z",
    }
    decisions = {"schemaVersion": "1.0", **binding(report), "decisions": [d]}
    accepted = apply_decisions(report, decisions)
    assert accepted["summary"]["regionAccepted"] > 0
    changed = copy.deepcopy(decisions)
    changed["decisions"][0]["region"] = [0, 0, 720, 405]
    changed["decisions"][0]["regionHash"] = fingerprint(
        {"page": 1, "region": [f"{v:.4f}" for v in [0, 0, 720, 405]]}
    )
    with pytest.raises(TransitError, match="25%"):
        apply_decisions(report, changed)
    missing = run_comparison(load_manifest(real / "pages.json"), tmp_path / "pages")
    decisions.update(binding(missing))
    result = apply_decisions(missing, decisions)
    assert result["findings"][0]["reviewState"] == "open"
    assert result["decisions"][0]["state"] == "stale"


def test_whitespace_reason_is_forbidden(compare_case):
    report = compare_case("symbol")
    d = document(report)
    d["decisions"][0]["reason"] = "  \n"
    with pytest.raises(TransitError, match="nonblank"):
        apply_decisions(report, d)


def run_cli(*args):
    return subprocess.run(
        ["slidetransit", *map(str, args)],
        capture_output=True,
        text=True,
        env=dict(os.environ, CI="1"),
        timeout=180,
    )


def test_cli_real_flow_unicode_space_paths(real, tmp_path):
    inputs = tmp_path / "Тест source with spaces"
    result = run_cli("init", "--dir", inputs, "--json", "--no-open")
    assert result.returncode == 0
    result = run_cli(
        "compare",
        "--manifest",
        inputs / "comparison.json",
        "--out",
        tmp_path / "report space",
        "--json",
        "--no-open",
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["analysisStatus"] == "complete"
    result = run_cli(
        "compare",
        "--manifest",
        inputs / "repeat.json",
        "--out",
        tmp_path / "repeat",
        "--json",
        "--no-open",
    )
    assert result.returncode == 0
    result = run_cli(
        "compare",
        "--manifest",
        inputs / "repeat.json",
        "--out",
        tmp_path / "repeat",
        "--json",
        "--no-open",
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stdout + result.stderr


def test_doctor_and_demo(tmp_path):
    assert run_cli("--version").stdout.strip() == "slidetransit 0.1.0"
    assert run_cli("--help").returncode == 0
    doctor = run_cli("doctor", "--json")
    assert doctor.returncode == 0
    assert json.loads(doctor.stdout)["pdfiumFlags"] == []
    result = run_cli("demo", "--out", tmp_path / "demo", "--json", "--no-open")
    assert result.returncode == 0
    assert json.loads(result.stdout)["cases"]["clipped"]["exitCode"] == 1


def test_corrupted_pdf_cli_is_error_not_pass(real, tmp_path):
    inputs = tmp_path / "inputs"
    shutil.copytree(real, inputs)
    data = json.loads((inputs / "repeat.json").read_text())
    data["candidate"].pop("sha256")
    (inputs / "repeat.pdf").write_bytes(b"%PDF-1.7\nBROKEN")
    (inputs / "bad.json").write_text(json.dumps(data))
    result = run_cli(
        "compare",
        "--manifest",
        inputs / "bad.json",
        "--out",
        tmp_path / "bad-output",
        "--json",
        "--no-open",
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stdout + result.stderr
    assert not (tmp_path / "bad-output").exists()
