"""Install final wheel and a wheel built from final sdist outside the checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run(args, cwd, env, expected=0):
    result = subprocess.run(
        list(map(str, args)), cwd=cwd, env=env, capture_output=True, text=True, timeout=240
    )
    if result.returncode != expected:
        raise RuntimeError(
            f"consumer command failed ({result.returncode}, expected {expected}): {args[1:3]}\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def consumer(wheel, root, env):
    started = time.monotonic()
    root.mkdir()
    venv = root / "venv"
    run([sys.executable, "-m", "venv", venv], root, env)
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    cli = venv / ("Scripts/slidetransit.exe" if os.name == "nt" else "bin/slidetransit")
    run(
        [
            python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--index-url",
            "https://pypi.org/simple",
            wheel,
        ],
        root,
        env,
    )
    module = run(
        [python, "-c", "import slidetransit;print(slidetransit.__file__)"], root, env
    ).strip()
    if not Path(module).resolve().is_relative_to(venv.resolve()):
        raise RuntimeError("consumer imported checkout instead of installed package")
    installed = json.loads(run([python, "-m", "pip", "list", "--format=json"], root, env))
    forbidden = {
        "pytest",
        "ruff",
        "mypy",
        "reportlab",
        "python-pptx",
        "pypdf",
        "playwright",
        "build",
    }
    if forbidden & {p["name"].lower() for p in installed}:
        raise RuntimeError("consumer contains development dependencies")
    run([cli, "--help"], root, env)
    version = run([cli, "--version"], root, env).strip()
    doctor = json.loads(run([cli, "doctor", "--json"], root, env))
    run([cli, "init", "--dir", "sample", "--no-open"], root, env)
    comparison = json.loads(
        run(
            [
                cli,
                "compare",
                "--manifest",
                "sample/comparison.json",
                "--out",
                "report",
                "--no-open",
                "--json",
            ],
            root,
            env,
            1,
        )
    )
    run(
        [
            cli,
            "compare",
            "--manifest",
            "sample/repeat.json",
            "--out",
            "repeat",
            "--no-open",
            "--json",
        ],
        root,
        env,
    )
    demo = json.loads(run([cli, "demo", "--out", "demo-output", "--no-open", "--json"], root, env))
    report = json.loads((root / "report/report.json").read_text())
    binding = {k: report[k] for k in ["comparisonId", "inputs", "rules", "renderer"]}
    decisions = {
        "schemaVersion": "1.0",
        **binding,
        "decisions": [
            {
                "type": "accept-difference",
                "findingId": f["id"],
                "regionHash": f["regionHash"],
                "reason": "Own intentional mutation reviewed in the packaged real-export example.",
                "timestamp": "2026-10-12T12:00:00Z",
            }
            for f in report["findings"]
        ],
    }
    (root / "review.json").write_text(json.dumps(decisions))
    reviewed = json.loads(
        run(
            [
                cli,
                "apply-review",
                "--report",
                "report/report.json",
                "--decisions",
                "review.json",
                "--out",
                "reviewed",
                "--no-open",
                "--json",
            ],
            root,
            env,
        )
    )
    run(
        [
            python,
            "-c",
            "from importlib.resources import files; r=files('slidetransit'); assert r.joinpath('assets/viewer.js').is_file(); assert r.joinpath('examples/baseline.pdf').is_file(); assert r.joinpath('schemas/report.schema.json').is_file(); assert r.joinpath('licenses/Noto-CJK-LICENSE.txt').is_file()",
        ],
        root,
        env,
    )
    html = (root / "report/report.html").read_text()
    assert "data:image/png;base64," in html and "fetch(" not in html
    assert demo["cases"]["clipped"]["exitCode"] == 1 and comparison["analysisStatus"] == "complete"
    for script in ["create_contract_fixtures.py", "verify_contracts.py"]:
        shutil.copyfile(Path(__file__).parent / script, root / script)
    run(
        [
            python,
            root / "verify_contracts.py",
            "--cli",
            cli,
            "--out",
            root / "contracts",
            "--presentation",
            root / "sample/baseline.pptx",
        ],
        root,
        env,
    )
    contracts = json.loads((root / "contracts/contract-results.json").read_text())
    return {
        "wheel": wheel.name,
        "version": version,
        "doctor": doctor,
        "comparison": comparison,
        "reviewed": reviewed,
        "demo": demo,
        "seconds": round(time.monotonic() - started, 2),
        "installedOutsideCheckout": True,
        "noDevDependencies": True,
        "installedPackages": installed,
        "contracts": contracts,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument(
        "--consumer-root",
        type=Path,
        help="Retain both owned consumers at a new path for inspection/UI QA",
    )
    args = parser.parse_args()
    dist = args.dist.resolve()
    wheels = list(dist.glob("*.whl"))
    sdists = list(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        parser.error("dist must contain exactly one final wheel and one final sdist")
    env = dict(os.environ, CI="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    for key in ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"]:
        env.pop(key, None)
    from contextlib import nullcontext

    if args.consumer_root:
        args.consumer_root.mkdir(parents=True)
    context = (
        nullcontext(str(args.consumer_root.resolve()))
        if args.consumer_root
        else tempfile.TemporaryDirectory(prefix="slidetransit-consumer-")
    )
    with context as temporary:
        root = Path(temporary)
        wheel_result = consumer(wheels[0], root / "wheel", env)
        run([sys.executable, "-m", "venv", root / "builder"], root, env)
        builder_python = (
            root / "builder" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        run(
            [
                builder_python,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--index-url",
                "https://pypi.org/simple",
                sdists[0],
                "--wheel-dir",
                root / "rebuilt",
            ],
            root,
            env,
        )
        rebuilt = list((root / "rebuilt").glob("*.whl"))
        if len(rebuilt) != 1:
            raise RuntimeError("sdist did not build a wheel")
        sdist_result = consumer(rebuilt[0], root / "sdist", env)
    result = {
        "result": "final-consumers-verified",
        "artifacts": [
            {
                "name": p.name,
                "size": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in wheels + sdists
        ],
        "consumers": [wheel_result, sdist_result],
    }
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
