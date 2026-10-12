import json
from importlib.resources import as_file, files

from slidetransit.limits import sha256
from slidetransit.manifest import load_manifest, validate


def test_portable_package_resources_and_assurances():
    root = files("slidetransit")
    for name in [
        "assets/viewer.js",
        "assets/viewer.css",
        "assets/NotoSans-Regular.ttf",
        "assets/LiberationSerif-Regular.ttf",
        "schemas/manifest.schema.json",
        "schemas/report.schema.json",
        "schemas/decisions.schema.json",
        "licenses/Noto-CJK-LICENSE.txt",
        "licenses/pypdfium2-5.3.0/LICENSES/BSD-3-Clause.txt",
    ]:
        assert root.joinpath(name).is_file()
    with as_file(root.joinpath("examples")) as sample:
        for name in ["comparison.json", "repeat.json", "fixed.json"]:
            manifest = load_manifest(sample / name)
            validate(manifest.data, "manifest")
        entries = json.loads((sample / "provenance.json").read_text())
        assert set(entries) == {"baseline", "repeat", "clipping", "fixed"}
        for entry in entries.values():
            assert sha256(sample / entry["path"]) == entry["sha256"]
            assert sha256(sample / entry["source"]["path"]) == entry["source"]["sha256"]
