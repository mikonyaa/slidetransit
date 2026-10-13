"""Bounded PNG reads anchored to directory descriptors, without following links."""

from __future__ import annotations

import io
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from PIL import Image

from slidetransit.limits import Limits
from slidetransit.models import JSON, TransitError


def asset_name(name: str) -> str:
    parts = name.split("/")
    if (
        len(parts) != 2
        or parts[0] != "assets"
        or parts[1] in ["", ".", ".."]
        or not parts[1].endswith(".png")
        or any(c in name for c in ["\\", "\x00", ":"])
    ):
        raise TransitError("unsafe report asset reference")
    return parts[1]


def asset_names(report: JSON) -> set[str]:
    names: set[str] = set()
    for page in report["pages"]:
        for role in ["reference", "candidate"]:
            if page[role] is not None:
                names.add(page[role]["image"])
        if page.get("mask"):
            names.add(page["mask"])
    for item in report["findings"]:
        names.update(item["cropReferences"].values())
    for name in names:
        asset_name(name)
    return names


def _directory(path: Path) -> int:
    """Walk the supplied bundle path as well; resolving it would conceal links."""
    absolute = path.absolute()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            following = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


class AssetLoader:
    def __init__(self, descriptor: int, limits: Limits) -> None:
        self.descriptor = descriptor
        self.limits = limits
        self.total = 0
        self.sizes: dict[str, tuple[int, int]] = {}

    def read(self, name: str) -> bytes:
        basename = asset_name(name)
        directory = descriptor = None
        try:
            directory = os.open(
                "assets",
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=self.descriptor,
            )
            descriptor = os.open(
                basename,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory,
            )
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= self.limits.file_bytes:
                raise TransitError("report asset must be a bounded regular PNG")
            if self.total + before.st_size > self.limits.output_bytes // 2:
                raise TransitError("reviewed asset set exceeds output budget")
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = None  # The stream owns this descriptor now.
                data = stream.read(before.st_size + 1)
                after = os.fstat(stream.fileno())
            if len(data) != before.st_size or (before.st_size, before.st_mtime_ns) != (
                after.st_size,
                after.st_mtime_ns,
            ):
                raise TransitError("report asset changed during reading")
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "PNG" or image.width * image.height > self.limits.page_pixels:
                    raise TransitError("report asset must be a bounded PNG image")
                self.sizes[name] = image.size
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()  # Verify compressed pixels as well as PNG chunk checksums.
            self.total += len(data)
            return data
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
            if isinstance(exc, TransitError):
                raise
            raise TransitError("missing, unsafe or invalid report asset: " + name) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if directory is not None:
                os.close(directory)


@contextmanager
def bundle_assets(root: Path, limits: Limits) -> Iterator[AssetLoader]:
    try:
        descriptor = _directory(root)
    except OSError as exc:
        raise TransitError("unsafe report asset directory (links are forbidden)") from exc
    try:
        yield AssetLoader(descriptor, limits)
    finally:
        os.close(descriptor)
