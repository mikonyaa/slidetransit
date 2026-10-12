"""Package only the own real-export demo and its reproducible reports."""

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path

from slidetransit import __version__
from slidetransit.cli import demo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    repository = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="slidetransit-bundle-") as temporary:
        root = Path(temporary) / "example"
        demo(root)
        (root / "README.md").write_text(
            "# SlideTransit real-export example\n\nOpen `clipped/report.html` directly. These are our own documented source mutations, exported with the accurately identified LibreOfficeDev development build. `repeat` and `fixed` return 0; `clipped` returns 1. This is sensitivity evidence, not proof of a cross-exporter regression. No Office is needed to analyze the supplied PDFs.\n\nAfter installing the release wheel:\n\n```sh\nslidetransit compare --manifest inputs/comparison.json --out new-report --no-open\n# Expected exit code: 1\n```\n\nThe reports embed all imagery/fonts; their JSON references adjacent `assets/`. Keep each JSON and its asset directory together when applying decisions.\n"
        )
        shutil.copyfile(repository / "LICENSE", root / "LICENSE")
        shutil.copytree(repository / "src/slidetransit/licenses", root / "licenses")
        target = args.out / ("slidetransit-example-" + __version__ + ".zip")
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(root.rglob("*")):
                if file.is_file():
                    archive.write(file, file.relative_to(root))
    print(target.name)


if __name__ == "__main__":
    main()
