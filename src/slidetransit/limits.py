"""Bounded read-only inputs and transactional outputs. These bounds are not a sandbox."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
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


def cleanup_owned_outputs(worker_temp: Path, parent: Path, run_id: str) -> None:
    """Crash fallback: a nonce alone does not prove ownership of a replacement inode."""
    ledger = worker_temp / "owned-outputs.jsonl"
    descriptor = None
    try:
        descriptor = os.open(ledger, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 64 * 1024:
            return
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = None
            records = stream.read(64 * 1024 + 1).splitlines()
        if len(records) > 256:
            return
        for line in records:
            record = json.loads(line)
            if not isinstance(record, dict) or record.get("runId") != run_id:
                continue
            path = Path(record["path"])
            if path.parent != parent or not path.name.startswith(".slidetransit-" + run_id + "-"):
                continue
            try:
                current = path.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISDIR(current.st_mode) and (current.st_dev, current.st_ino) == (
                record["device"],
                record["inode"],
            ):
                shutil.rmtree(path)
    except (OSError, ValueError, KeyError, TypeError):
        # Unregistered/uncertain directories are preserved rather than guessed owned.
        return
    finally:
        if descriptor is not None:
            os.close(descriptor)


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
    identity = temporary.lstat()

    def owned() -> bool:
        try:
            current = temporary.lstat()
        except FileNotFoundError:
            return False
        return stat.S_ISDIR(current.st_mode) and (current.st_dev, current.st_ino) == (
            identity.st_dev,
            identity.st_ino,
        )

    try:
        worker_temp = os.environ.get("SLIDETRANSIT_WORKER_TEMP")
        if worker_temp and len(run_id) == 32 and all(c in "0123456789abcdef" for c in run_id):
            ledger = Path(worker_temp) / "owned-outputs.jsonl"
            entry = (
                json.dumps(
                    {
                        "runId": run_id,
                        "path": str(temporary),
                        "device": identity.st_dev,
                        "inode": identity.st_ino,
                    }
                )
                + "\n"
            )
            descriptor = os.open(
                ledger, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                if os.fstat(stream.fileno()).st_size + len(entry.encode("utf-8")) > 64 * 1024:
                    raise TransitError("owned output ledger exceeds limit")
                stream.write(entry)
        yield temporary
        if not owned():
            raise TransitError("temporary output ownership changed; refusing commit")
        total = sum(p.stat().st_size for p in temporary.rglob("*") if p.is_file())
        if total > limits.output_bytes:
            raise TransitError("report exceeds total output limit")
        if out.exists():
            raise TransitError("output appeared during analysis; refusing overwrite")
        os.rename(temporary, out)
    finally:
        if owned():
            shutil.rmtree(temporary)
