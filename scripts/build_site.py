"""Build an allowlisted static sample; never accept/upload visitor PDFs."""

import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from slidetransit.cli import demo


def build(destination: Path) -> None:
    if destination.exists():
        raise ValueError("site destination must be new")
    destination.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="slidetransit-site-") as temporary:
        root = Path(temporary) / "demo"
        demo(root)
        for source, filename in [
            ("clipped", "index.html"),
            ("fixed", "fixed.html"),
            ("repeat", "repeat.html"),
        ]:
            html = (root / source / "report.html").read_text()
            banner = '<nav aria-label="Static demo cases" style="padding:12px 32px;border-bottom:1px solid #d7ddd5;font-size:12px">Own documented source mutation · <a href="./index.html">Clipped export</a> · <a href="./fixed.html">After actual source fix</a> · <a href="./repeat.html">Unchanged control</a> · <a href="./sample.zip">Download real inputs</a>. Static sample; analysis runs in the Python CLI.</nav>'
            html = html.replace('<section class="intro">', banner + '<section class="intro">', 1)
            (destination / filename).write_text(html)
        with zipfile.ZipFile(destination / "sample.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted((root / "inputs").iterdir()):
                if path.is_file() and path.suffix in [".json", ".pdf", ".pptx", ".md", ".txt"]:
                    archive.write(path, path.name)
        (destination / ".nojekyll").write_text("")
        (destination / "demo-summary.json").write_text((root / "demo-summary.json").read_text())
        schemas = Path(__file__).resolve().parents[1] / "src/slidetransit/schemas"
        shutil.copytree(schemas, destination / "schemas")
    allowed = {
        "index.html",
        "fixed.html",
        "repeat.html",
        "sample.zip",
        ".nojekyll",
        "demo-summary.json",
        "schemas",
    }
    assert {p.name for p in destination.iterdir()} == allowed
    print(json.dumps({"result": "static-site-built", "files": sorted(allowed)}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("site"))
    args = parser.parse_args()
    build(args.out)


if __name__ == "__main__":
    main()
