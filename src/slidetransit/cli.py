"""A small local CLI. Native parsing runs in a bounded, owned subprocess."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid
import webbrowser
from importlib.resources import as_file, files
from pathlib import Path

from slidetransit import __version__
from slidetransit.limits import DEFAULT_LIMITS, atomic_output
from slidetransit.models import JSON, TransitError


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="slidetransit",
        description="Compare real presentation exports and locate delivery regressions.",
    )
    root.add_argument("--version", action="version", version="slidetransit " + __version__)
    sub = root.add_subparsers(dest="command", required=True)
    for name in ["doctor", "init", "compare", "apply-review", "demo"]:
        p = sub.add_parser(
            name,
            help={
                "doctor": "Check local analysis capabilities (Office not required)",
                "init": "Copy a portable genuinely exported example",
                "compare": "Compare one manifest's PPTX and PDF pair",
                "apply-review": "Apply current decisions and retain stale ones",
                "demo": "Run repeat, clipped and fixed real-export cases",
            }[name],
        )
        p.add_argument("--json", action="store_true", help="Print a machine-readable summary")
        p.add_argument("--no-open", action="store_true", help="Never launch a browser")
        if name == "init":
            p.add_argument("--dir", type=Path, required=True)
        if name in ["compare", "apply-review", "demo"]:
            p.add_argument(
                "--out",
                type=Path,
                required=True,
                help="New output directory; existing directories are never replaced",
            )
        if name == "compare":
            p.add_argument("--manifest", type=Path, required=True)
            p.add_argument("--dpi", type=int)
            p.add_argument("--pixel-delta", type=int)
            p.add_argument("--displacement-pt", type=float)
            p.add_argument("--fail-on", choices=["info", "low", "medium", "high"])
        if name == "apply-review":
            p.add_argument("--report", type=Path, required=True)
            p.add_argument("--decisions", type=Path, required=True)
    return root


def emit(value: JSON, machine: bool) -> None:
    if machine:
        print(json.dumps(value, ensure_ascii=False, allow_nan=False))
    else:
        print("SlideTransit: " + str(value.get("message", value.get("result", "complete"))))
        if "analysisStatus" in value:
            print(
                f"Analysis {value['analysisStatus']}; {value['findings']} findings; {value['unhandledAtThreshold']} unhandled at threshold; exit {value['exitCode']}."
            )


def doctor() -> JSON:
    import pypdfium2 as pdfium

    from slidetransit.pdf import versions

    pdf = pdfium.PdfDocument.new()
    try:
        page = pdf.new_page(120, 80)
        bitmap = page.render(may_draw_forms=False)
        try:
            if bitmap.width != 120 or bitmap.height != 80:
                raise TransitError("PDFium capability canary failed")
        finally:
            bitmap.close()
            page.close()
    finally:
        pdf.close()
    flags = list(pdfium.PDFIUM_INFO.flags)
    if any("v8" in flag.lower() or "xfa" in flag.lower() for flag in flags):
        raise TransitError("this release requires PDFium without V8/XFA")
    return {
        "result": "ready",
        "message": "PDF rendering and text geometry ready; Office is not required.",
        "python": platform.python_version(),
        "platform": platform.system(),
        "architecture": platform.machine(),
        "versions": versions(),
        "pdfiumFlags": flags,
        "limits": DEFAULT_LIMITS.json(),
        "supportedExtraction": "horizontal Unicode text with character geometry; other orientations are explicit partial coverage",
    }


def init_example(out: Path) -> None:
    with atomic_output(out, []) as working:
        with as_file(files("slidetransit").joinpath("examples")) as example:
            shutil.copytree(example, working, dirs_exist_ok=True)


def summarize(report: JSON) -> JSON:
    return {
        **report["summary"],
        "analysisStatus": report["analysisStatus"],
        "comparisonId": report["comparisonId"],
    }


def demo(out: Path) -> JSON:
    from slidetransit.compare import run_comparison
    from slidetransit.manifest import load_manifest

    cases: JSON = {}
    with atomic_output(out, []) as working:
        init_example(working / "inputs")
        for name, config in [
            ("repeat", "repeat.json"),
            ("clipped", "comparison.json"),
            ("fixed", "fixed.json"),
        ]:
            report = run_comparison(load_manifest(working / "inputs" / config), working / name)
            cases[name] = summarize(report)
        if (
            cases["repeat"]["exitCode"] != 0
            or cases["fixed"]["exitCode"] != 0
            or cases["clipped"]["exitCode"] != 1
        ):
            raise TransitError("real-export demo canary failed")
        clipped = json.loads((working / "clipped/report.json").read_text())
        if not any(f["ruleId"] == "possible-clipping" for f in clipped["findings"]):
            raise TransitError("demo did not localize possible clipping")
        result = {
            "result": "demo-verified",
            "message": "Real-export demo verified: repeat=0, clipped=1 (expected difference), fixed=0.",
            "cases": cases,
            "mode": "documented-test-variant",
            "limitation": "Source mutation sensitivity test; not a regression between exporters of the same source.",
        }
        (working / "demo-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def execute(args: argparse.Namespace) -> tuple[JSON, int]:
    from slidetransit.compare import run_comparison
    from slidetransit.manifest import load_manifest
    from slidetransit.review import apply_review

    if args.command == "doctor":
        return doctor(), 0
    if args.command == "init":
        init_example(args.dir)
        return {"result": "example-created", "message": "Portable real-export example created."}, 0
    if args.command == "compare":
        overrides = {
            key: getattr(args, key)
            for key in ["dpi", "pixel_delta", "displacement_pt", "fail_on"]
            if getattr(args, key) is not None
        }
        report = run_comparison(load_manifest(args.manifest, overrides), args.out)
        return summarize(report), int(report["summary"]["exitCode"])
    if args.command == "apply-review":
        report = apply_review(args.report, args.decisions, args.out)
        return summarize(report), int(report["summary"]["exitCode"])
    result = demo(args.out)
    return result, 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    worker = "--_worker" in arguments
    if worker:
        arguments.remove("--_worker")
    args = parser().parse_args(arguments)
    try:
        if not worker:
            # Limit native-parser lifetime; never use shell strings or shared workers.
            with tempfile.TemporaryDirectory(prefix="slidetransit-worker-") as temporary:
                run_id = uuid.uuid4().hex
                env = dict(
                    os.environ, SLIDETRANSIT_WORKER_TEMP=temporary, SLIDETRANSIT_RUN_ID=run_id
                )
                try:
                    process = subprocess.run(
                        [sys.executable, "-m", "slidetransit.cli", "--_worker", *arguments],
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=DEFAULT_LIMITS.worker_seconds,
                    )
                finally:
                    target = getattr(args, "out", getattr(args, "dir", None))
                    if target is not None:
                        # A native crash cannot run the child's Python finally block.
                        # Clean only directories named with this invocation's nonce.
                        for owned in target.resolve().parent.glob(".slidetransit-" + run_id + "-*"):
                            if owned.is_dir() and not owned.is_symlink():
                                shutil.rmtree(owned)
            if process.returncode not in [0, 1, 2, 3, 130]:
                raise TransitError(
                    "analysis worker stopped unexpectedly; no successful analysis is asserted"
                )
            print(process.stdout, end="")
            if process.stderr:
                print(process.stderr, file=sys.stderr, end="")
            code = process.returncode
            if (
                code in [0, 1, 3]
                and args.command in ["compare", "apply-review", "demo"]
                and not args.no_open
                and not os.environ.get("CI")
                and sys.stdout.isatty()
            ):
                target = args.out / (
                    "clipped/report.html" if args.command == "demo" else "report.html"
                )
                webbrowser.open(target.resolve().as_uri())
            return code
        value, code = execute(args)
        emit(value, args.json)
        return code
    except KeyboardInterrupt:
        return 130
    except subprocess.TimeoutExpired:
        emit(
            {
                "result": "error",
                "message": "Analysis worker exceeded 180-second limit; reduce scope or DPI.",
                "exitCode": 2,
            },
            args.json,
        )
        return 2
    except Exception as exc:
        message = (
            str(exc) if isinstance(exc, TransitError) else "Operation failed: " + type(exc).__name__
        )
        emit({"result": "error", "message": message, "exitCode": 2}, args.json)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
