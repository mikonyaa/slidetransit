import json
import zipfile
from dataclasses import replace

import pytest

from slidetransit.limits import DEFAULT_LIMITS, atomic_output, check_file, load_json, read_pptx
from slidetransit.manifest import load_manifest
from slidetransit.models import BBox, Config, TransitError, normalize


@pytest.mark.parametrize(
    "name", ["../x.xml", "/x.xml", "C:/x.xml", "a\\b.xml", "a/./b.xml", "a//b.xml"]
)
def test_pptx_paths_are_never_extracted(tmp_path, name):
    path = tmp_path / "hostile.pptx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, "<x/>")
    with pytest.raises(TransitError, match="unsafe"):
        read_pptx(path)
    assert not (tmp_path.parent / "x.xml").exists()


def test_duplicate_normalized_zip_names(tmp_path):
    path = tmp_path / "duplicates.pptx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("é.xml", "<x/>")
        archive.writestr("e\u0301.xml", "<x/>")
    with pytest.raises(TransitError, match="duplicate"):
        read_pptx(path)


@pytest.mark.parametrize(
    "content",
    [
        "<broken>",
        '<!DOCTYPE x [<!ENTITY ex SYSTEM "file:///etc/passwd">]><x>&ex;</x>',
        '<!DOCTYPE x [<!ENTITY a "value">]><x>&a;</x>',
    ],
)
def test_xml_no_dtd_entities_or_malformed_input(tmp_path, content):
    path = tmp_path / "xml.pptx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", content)
    with pytest.raises(TransitError, match="ZIP/XML"):
        read_pptx(path)


def test_zip_bomb_entries_xml_and_expanded_limits(tmp_path):
    path = tmp_path / "bomb.pptx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/presentation.xml", "<x>" + " " * 2_000_000 + "</x>")
    with pytest.raises(TransitError, match="compression ratio"):
        read_pptx(path)
    path = tmp_path / "entries.pptx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("a.xml", "<x/>")
        archive.writestr("b.xml", "<x/>")
    with pytest.raises(TransitError, match="entry"):
        read_pptx(path, replace(DEFAULT_LIMITS, zip_entries=1))
    with pytest.raises(TransitError, match="XML limit"):
        read_pptx(path, replace(DEFAULT_LIMITS, xml_bytes=1))
    with pytest.raises(TransitError, match="expanded"):
        read_pptx(path, replace(DEFAULT_LIMITS, expanded_bytes=1))


def test_file_and_output_limits_are_errors(tmp_path):
    path = tmp_path / "big.pdf"
    path.write_bytes(b"%PDF-" + b"x" * 50)
    with pytest.raises(TransitError, match="size limit"):
        check_file(path, 10)
    out = tmp_path / "report"
    with pytest.raises(TransitError, match="output limit"):
        with atomic_output(out, [], replace(DEFAULT_LIMITS, output_bytes=1)) as stage:
            (stage / "large.txt").write_text("xx")
    assert not out.exists()


def test_existing_output_is_never_overwritten(tmp_path):
    out = tmp_path / "existing"
    out.mkdir()
    (out / "other.txt").write_text("belongs to someone else")
    with pytest.raises(TransitError, match="already exists"):
        with atomic_output(out, []):
            pass
    assert (out / "other.txt").read_text() == "belongs to someone else"


def test_atomic_failure_rolls_back(tmp_path):
    out = tmp_path / "fresh"
    with pytest.raises(RuntimeError):
        with atomic_output(out, []) as stage:
            (stage / "report.json").write_text("partial")
            raise RuntimeError("canary")
    assert not out.exists()
    assert list(tmp_path.glob(".slidetransit-*")) == []


def test_numeric_and_unicode_normalization():
    assert normalize("  東京\n12.5%,\tＡ  ") == "東京 12.5%, Ａ"
    with pytest.raises(TransitError):
        BBox(float("nan"), 0, 1, 1)
    with pytest.raises(TransitError):
        Config(displacement_pt=float("inf"))
    with pytest.raises(TransitError):
        Config(dpi=1000)


def test_json_nan_is_rejected(tmp_path):
    path = tmp_path / "nan.json"
    path.write_text('{"threshold":NaN}')
    with pytest.raises(TransitError, match="invalid"):
        load_json(path)


def test_hash_mismatch_and_variant_declaration(real, tmp_path):
    data = json.loads((real / "clipping.json").read_text())
    for role in ["presentation", "reference", "candidate"]:
        data[role]["path"] = str(real / data[role]["path"])
    for role in ["reference", "candidate"]:
        data[role]["source"]["path"] = str(real / data[role]["source"]["path"])
    data["mode"] = "declared-same-source"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(TransitError, match="conflicts"):
        load_manifest(path)
    data["mode"] = "documented-test-variant"
    del data["candidate"]["source"]
    path.write_text(json.dumps(data))
    with pytest.raises(TransitError, match="source hashes"):
        load_manifest(path)
