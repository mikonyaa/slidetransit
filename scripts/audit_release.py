"""Audit staged/history/package contents without printing secret values."""

import argparse
import io
import json
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path

PATTERNS = {
    "private filesystem path": re.compile(rb"/" + rb"(?:Users|home)/[A-Za-z0-9_.-]+/"),
    "GitHub token": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9_]{24,}|github_pat_[A-Za-z0-9_]{30,})"),
    "OpenAI token": re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{30,}"),
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(rb"AKIA[A-Z0-9]{16}"),
}


def scan(label, data, errors):
    for name, pattern in PATTERNS.items():
        if pattern.search(data):
            errors.append({"file": label, "marker": name})
    if label.endswith(".pptx"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for item in archive.infolist():
                if item.filename.endswith((".xml", ".rels")):
                    scan(label + ":" + item.filename, archive.read(item), errors)
    if label.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        extracted = (
            json.dumps(dict(reader.metadata or {}))
            + "\n"
            + "\n".join(page.extract_text() or "" for page in reader.pages)
        )
        scan(label + ":metadata+text", extracted.encode(), errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    errors = []
    tracked = subprocess.check_output(["git", "ls-files", "--cached", "-z"]).decode().split("\0")
    count = 0
    for name in filter(None, tracked):
        if name.startswith(("work/", ".venv/", "dist/", "site/")):
            errors.append({"file": name, "marker": "foreign/intermediate content staged"})
        path = Path(name)
        if path.is_symlink():
            errors.append({"file": name, "marker": "symlink staged"})
        scan(name, subprocess.check_output(["git", "show", ":" + name]), errors)
        count += 1
    history = subprocess.run(["git", "rev-list", "--all"], capture_output=True, text=True)
    commits = history.stdout.split() if history.returncode == 0 else []
    for commit in commits:
        names = (
            subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "-z", commit])
            .decode()
            .split("\0")
        )
        for name in filter(None, names):
            scan(
                "history:" + commit[:8] + ":" + name,
                subprocess.check_output(["git", "show", commit + ":" + name]),
                errors,
            )
    artifacts = []
    for package in sorted(args.dist.iterdir()):
        if package.suffix in [".whl", ".zip"]:
            with zipfile.ZipFile(package) as archive:
                for item in archive.infolist():
                    if not item.is_dir():
                        scan(package.name + ":" + item.filename, archive.read(item), errors)
        elif package.name.endswith(".tar.gz"):
            with tarfile.open(package) as archive:
                for item in archive.getmembers():
                    if item.issym() or item.islnk():
                        errors.append({"file": item.name, "marker": "archive link"})
                    if item.isfile():
                        data = archive.extractfile(item)
                        scan(package.name + ":" + item.name, data.read(), errors)
        else:
            continue
        artifacts.append(package.name)
    result = {
        "result": "audit-passed" if not errors else "audit-failed",
        "stagedFiles": count,
        "historyCommits": len(commits),
        "packages": artifacts,
        "errors": errors,
        "boundary": "Pattern and allowlist review; not proof that all possible secrets are absent.",
    }
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
