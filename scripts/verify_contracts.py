"""Run fresh positive/negative CLI probes in an installed consumer without dev dependencies."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from create_contract_fixtures import create_fixtures
from PIL import Image


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(cli, root, presentation):
    if root.exists():
        raise ValueError("contract output already exists")
    root.mkdir(parents=True)
    hashes = create_fixtures(root / "fixtures", presentation)
    cases = []

    def run(name, arguments, expected):
        started = time.monotonic()
        result = subprocess.run(
            [str(cli), *map(str, arguments), "--json", "--no-open"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=180,
            env=dict(os.environ, CI="1"),
        )
        (root / (name + ".stdout.txt")).write_text(result.stdout)
        (root / (name + ".stderr.txt")).write_text(result.stderr)
        value = json.loads(result.stdout)  # Reject extra JSON documents/progress on stdout.
        assert result.returncode == expected, (
            name,
            result.returncode,
            result.stdout,
            result.stderr,
        )
        assert value.get("exitCode", expected) == expected
        assert "Traceback" not in result.stderr
        if expected == 2:
            assert value["result"] == "error" and not value["message"].startswith(
                "Operation failed:"
            )
        cases.append(
            {
                "name": name,
                "exitCode": result.returncode,
                "seconds": round(time.monotonic() - started, 3),
                "summary": value,
            }
        )
        return value

    reports = {}
    for folder in sorted((root / "fixtures").iterdir()):
        if not folder.is_dir():
            continue
        name = folder.name
        # Fractional grid outcomes depend on measured native dimensions, not idealized ceil math.
        expected = 0 if name == "repeat" else 1
        if name.startswith("fractional"):
            command = [
                str(cli),
                "compare",
                "--manifest",
                str(folder / "comparison.json"),
                "--out",
                str(root / name),
                "--json",
                "--no-open",
            ]
            started = time.monotonic()
            result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=180)
            value = json.loads(result.stdout)
            assert result.returncode in [0, 1, 3], (name, result.stdout)
            assert value["exitCode"] == result.returncode
            (root / (name + ".stdout.txt")).write_text(result.stdout)
            (root / (name + ".stderr.txt")).write_text(result.stderr)
            cases.append(
                {
                    "name": name,
                    "exitCode": result.returncode,
                    "seconds": round(time.monotonic() - started, 3),
                    "summary": value,
                }
            )
        else:
            run(
                name,
                ["compare", "--manifest", folder / "comparison.json", "--out", root / name],
                expected,
            )
        report = json.loads((root / name / "report.json").read_text())
        reports[name] = report
        if name.startswith("fractional"):
            page = report["pages"][0]
            same = page["reference"]["rasterSize"] == page["candidate"]["rasterSize"]
            assert report["coverage"][0]["rasterComparison"] == (
                "complete" if same else "unavailable-different-raster-grid"
            )
            assert report["analysisStatus"] == ("complete" if same else "incomplete")
            assert bool(page.get("mask")) == same
            assert all(
                report["coverage"][0][r][c] == "complete"
                for r in ["reference", "candidate"]
                for c in ["text", "geometry", "raster"]
            )
        if name == "partial":
            assert len(report["findings"]) == 1
            assert report["coverage"][1]["candidate"]["text"] == "unavailable"
        if name == "shift":
            assert any(f["ruleId"] == "displacement" for f in report["findings"])
        if name == "deletion":
            assert any(f["ruleId"] == "extracted-text-change" for f in report["findings"])

    def decisions(report):
        return {
            "schemaVersion": "1.0",
            **{k: report[k] for k in ["comparisonId", "inputs", "rules", "renderer"]},
            "decisions": [
                {
                    "type": "accept-difference",
                    "findingId": f["id"],
                    "regionHash": f["regionHash"],
                    "reason": "Own synthetic evidence inspected",
                    "author": "Consumer contract probe",
                    "timestamp": "2026-10-14T00:00:00Z",
                }
                for f in report["findings"]
            ],
        }

    for name, expected in [("repeat", 0), ("shift", 0), ("partial", 3)]:
        document = decisions(reports[name])
        path = root / (name + "-decisions.json")
        path.write_text(json.dumps(document))
        run(
            name + "-review",
            [
                "apply-review",
                "--report",
                root / name / "report.json",
                "--decisions",
                path,
                "--out",
                root / (name + "-review"),
            ],
            expected,
        )
        for image in (root / name / "assets").glob("*.png"):
            assert digest(image) == digest(root / (name + "-review") / "assets" / image.name)
    stale = decisions(reports["partial"])
    stale["comparisonId"] = "f" * 64
    (root / "stale.json").write_text(json.dumps(stale))
    value = run(
        "stale",
        [
            "apply-review",
            "--report",
            root / "partial/report.json",
            "--decisions",
            root / "stale.json",
            "--out",
            root / "stale",
        ],
        1,
    )
    assert value["staleDecisions"] == 1 and value["accepted"] == 0
    assert value["analysisStatus"] == "incomplete"

    mutations = [
        "missing-coverage",
        "duplicate-coverage",
        "range-coverage",
        "duplicate-page",
        "unknown-channel",
        "unknown-state",
        "dangling-finding",
        "dangling-asset",
        "summary",
        "analysis-status",
        "acceptance",
        "applied-reference",
        "symlink-parent",
        "symlink-final",
        "escape",
        "non-png",
        "oversized",
        "corrupt-png",
        "wrong-grid",
        "config-binding",
        "input-binding",
        "renderer-binding",
    ]
    for name in mutations:
        bundle = root / ("invalid-" + name)
        shutil.copytree(root / "partial", bundle)
        report = copy.deepcopy(reports["partial"])
        if name == "missing-coverage":
            report["coverage"].pop()
            report["analysisStatus"] = "complete"
        elif name == "duplicate-coverage":
            report["coverage"].append(copy.deepcopy(report["coverage"][0]))
        elif name == "range-coverage":
            report["coverage"][-1]["page"] = 999
        elif name == "duplicate-page":
            report["pages"][-1]["page"] = 1
        elif name == "unknown-channel":
            report["coverage"][0]["candidate"]["invented"] = "complete"
        elif name == "unknown-state":
            report["coverage"][0]["candidate"]["text"] = "invented"
        elif name == "dangling-finding":
            report["findings"][0]["page"] = 999
        elif name == "dangling-asset":
            report["pages"][0]["candidate"]["image"] = "assets/missing.png"
        elif name == "summary":
            report["summary"]["findings"] = 0
        elif name == "analysis-status":
            report["analysisStatus"] = "complete"
        elif name == "acceptance":
            report["findings"][0]["reviewState"] = "accepted"
        elif name == "applied-reference":
            report = json.loads((root / "partial-review/report.json").read_text())
            report["decisions"][0]["decision"]["findingId"] = "f" * 24
        elif name == "symlink-parent":
            external = root / "own-external-parent"
            (bundle / "assets").rename(external)
            (bundle / "assets").symlink_to(external, target_is_directory=True)
        elif name == "symlink-final":
            image = bundle / report["pages"][0]["candidate"]["image"]
            external = root / "own-external-final.png"
            image.rename(external)
            image.symlink_to(external)
        elif name == "escape":
            report["pages"][0]["candidate"]["image"] = "assets/../own-external-final.png"
        elif name == "non-png":
            Image.new("RGB", (10, 10)).save(
                bundle / report["pages"][0]["candidate"]["image"], format="JPEG"
            )
        elif name == "oversized":
            with (bundle / report["pages"][0]["candidate"]["image"]).open("r+b") as stream:
                stream.truncate(100 * 1024 * 1024 + 1)
        elif name == "corrupt-png":
            image = bundle / report["pages"][0]["candidate"]["image"]
            image.write_bytes(image.read_bytes()[:40])
        elif name == "wrong-grid":
            for role in ["reference", "candidate"]:
                report["pages"][0][role]["rasterSize"] = [1, 1]
        elif name == "config-binding":
            report["config"]["fail_on"] = "info"
        elif name == "input-binding":
            report["inputs"]["candidate"] = "f" * 64
        elif name == "renderer-binding":
            report["renderer"]["pdfium"] = "invented"
        (bundle / "report.json").write_text(json.dumps(report))
        output = root / ("rejected-" + name)
        run(
            "reject-" + name,
            [
                "apply-review",
                "--report",
                bundle / "report.json",
                "--decisions",
                root / "partial-decisions.json",
                "--out",
                output,
            ],
            2,
        )
        assert not output.exists()
        assert not list(root.glob(".slidetransit-*"))

    sentinel = root / "existing-output"
    sentinel.mkdir()
    (sentinel / "sentinel").write_bytes(b"other invocation")
    run(
        "existing-output",
        [
            "apply-review",
            "--report",
            root / "partial/report.json",
            "--decisions",
            root / "partial-decisions.json",
            "--out",
            sentinel,
        ],
        2,
    )
    assert (sentinel / "sentinel").read_bytes() == b"other invocation"

    other = root / (".slidetransit-" + "f" * 32 + "-other")
    other.mkdir()
    (other / "sentinel").write_bytes(b"other invocation")
    started = time.monotonic()
    process = subprocess.Popen(
        [
            str(cli),
            "compare",
            "--manifest",
            str(root / "fixtures/repeat/comparison.json"),
            "--out",
            str(root / "interrupted"),
            "--json",
            "--no-open",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not [
            p for p in root.glob(".slidetransit-*") if p != other and (p / "assets").is_dir()
        ]:
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(0.005)
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 130 and json.loads(stdout)["exitCode"] == 130
        assert "Traceback" not in stderr and not (root / "interrupted").exists()
        assert list(root.glob(".slidetransit-*")) == [other]
        assert (other / "sentinel").read_bytes() == b"other invocation"
        (root / "interrupt.stdout.txt").write_text(stdout)
        (root / "interrupt.stderr.txt").write_text(stderr)
        cases.append(
            {"name": "interrupt", "exitCode": 130, "seconds": round(time.monotonic() - started, 3)}
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
    assert hashes == {name: digest(root / "fixtures" / name) for name in hashes}
    result = {
        "result": "contracts-verified",
        "synthetic": True,
        "inputHashes": hashes,
        "cases": cases,
        "singleJSONStdout": True,
        "negativeOutputsAbsent": True,
        "copiedAssetsHashEqual": True,
        "inputsUnchanged": True,
        "otherOutputPreserved": True,
    }
    (root / "contract-results.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--presentation", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.cli.resolve(), args.out.resolve(), args.presentation.resolve())
    print(json.dumps({"result": result["result"], "cases": len(result["cases"])}))


if __name__ == "__main__":
    main()
