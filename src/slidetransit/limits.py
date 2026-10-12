"""Bounded read-only inputs and transactional outputs. These bounds are not a sandbox."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unicodedata
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from slidetransit.models import JSON, TransitError


@dataclass(frozen=True)
class Limits:
    file_bytes: int = 100 * 1024 * 1024
    zip_entries: int = 5000
    xml_bytes: int = 32 * 1024 * 1024
    expanded_bytes: int = 128 * 1024 * 1024
    pages: int = 200
    page_pixels: int = 8_000_000
    characters_per_page: int = 100_000
    characters_per_document: int = 250_000
    findings: int = 5000
    output_bytes: int = 128 * 1024 * 1024
    html_bytes: int = 64 * 1024 * 1024
    report_json_bytes: int = 32 * 1024 * 1024
    worker_seconds: int = 180

    def json(self) -> JSON:
        return asdict(self)


DEFAULT_LIMITS = Limits()


def check_file(path: Path, limit: int = DEFAULT_LIMITS.file_bytes) -> None:
    if not path.is_file() or path.is_symlink():
        raise TransitError("input must be a regular file: " + path.name)
    if not 0 < path.stat().st_size <= limit:
        raise TransitError("input is empty or exceeds size limit: " + path.name)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, max_bytes: int = 4 * 1024 * 1024) -> JSON:
    check_file(path, max_bytes)
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)),
        )
    except (ValueError, UnicodeError) as exc:
        raise TransitError("invalid UTF-8 JSON: " + path.name) from exc
    if not isinstance(value, dict):
        raise TransitError("JSON root must be an object")
    return value


def read_pptx(path: Path, limits: Limits = DEFAULT_LIMITS) -> dict[str, bytes]:
    check_file(path, limits.file_bytes)
    parts: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > limits.zip_entries:
                raise TransitError("PPTX exceeds ZIP entry limit")
            expanded = xml_total = 0
            for info in entries:
                name = unicodedata.normalize("NFC", info.filename)
                parts_path = PurePosixPath(name)
                if (
                    "\\" in name
                    or name.startswith("/")
                    or ":" in name
                    or any(p in ["..", ".", ""] for p in name.split("/"))
                    or parts_path.is_absolute()
                ):
                    raise TransitError("unsafe PPTX ZIP path")
                if name in parts or info.flag_bits & 1:
                    raise TransitError("duplicate ZIP name or encrypted PPTX")
                expanded += info.file_size
                if expanded > limits.expanded_bytes or (
                    info.file_size > 1024 * 1024
                    and info.file_size > max(info.compress_size, 1) * 200
                ):
                    raise TransitError("PPTX exceeds expanded size / compression ratio limit")
                if name.lower().endswith((".xml", ".rels")):
                    xml_total += info.file_size
                    if xml_total > limits.xml_bytes:
                        raise TransitError("PPTX exceeds total XML limit")
                    data = archive.read(info)
                    ElementTree.fromstring(
                        data, forbid_dtd=True, forbid_entities=True, forbid_external=True
                    )
                    parts[name] = data
                else:
                    # No arbitrary extraction or macro/embedded-object execution.
                    parts[name] = b""
    except (zipfile.BadZipFile, ElementTree.ParseError, DefusedXmlException) as exc:
        raise TransitError("damaged or forbidden PPTX ZIP/XML") from exc
    if "ppt/presentation.xml" not in parts or "[Content_Types].xml" not in parts:
        raise TransitError("not a supported PPTX container")
    if any("vbaProject" in name for name in parts):
        raise TransitError("macro-enabled presentations are unsupported")
    return parts


def guard_output(out: Path, inputs: list[Path]) -> None:
    out = out.resolve()
    if out.exists():
        raise TransitError("output already exists; choose a new directory")
    for path in inputs:
        resolved = path.resolve()
        if out == resolved or out in resolved.parents:
            raise TransitError("output would contain or overwrite an input")


@contextmanager
def atomic_output(out: Path, inputs: list[Path], limits: Limits = DEFAULT_LIMITS) -> Iterator[Path]:
    guard_output(out, inputs)
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    run_id = os.environ.get("SLIDETRANSIT_RUN_ID", "")
    prefix = ".slidetransit-" + (
        run_id + "-" if len(run_id) == 32 and all(c in "0123456789abcdef" for c in run_id) else ""
    )
    temporary = Path(tempfile.mkdtemp(prefix=prefix, dir=out.parent))
    try:
        yield temporary
        total = sum(p.stat().st_size for p in temporary.rglob("*") if p.is_file())
        if total > limits.output_bytes:
            raise TransitError("report exceeds total output limit")
        if out.exists():
            raise TransitError("output appeared during analysis; refusing overwrite")
        os.rename(temporary, out)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
