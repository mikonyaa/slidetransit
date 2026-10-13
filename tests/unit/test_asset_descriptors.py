import os
from dataclasses import replace

import pytest
from PIL import Image

from slidetransit.limits import DEFAULT_LIMITS, atomic_output
from slidetransit.models import TransitError
from slidetransit.report_assets import bundle_assets


def test_open_asset_directory_is_anchored_across_parent_replacement(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    (bundle / "assets").mkdir(parents=True)
    Image.new("RGB", (10, 10), "red").save(bundle / "assets/image.png")
    expected = (bundle / "assets/image.png").read_bytes()
    external = tmp_path / "own-external"
    external.mkdir()
    Image.new("RGB", (10, 10), "blue").save(external / "image.png")
    opened = os.open

    def replace_parent(name, *args, **kwargs):
        if name == "image.png":
            (bundle / "assets").rename(bundle / "anchored-assets")
            (bundle / "assets").symlink_to(external, target_is_directory=True)
        return opened(name, *args, **kwargs)

    with bundle_assets(bundle, DEFAULT_LIMITS) as assets:
        monkeypatch.setattr(os, "open", replace_parent)
        assert assets.read("assets/image.png") == expected


def test_fifo_asset_is_rejected_without_blocking(tmp_path):
    (tmp_path / "assets").mkdir()
    os.mkfifo(tmp_path / "assets/fifo.png")
    with bundle_assets(tmp_path, DEFAULT_LIMITS) as assets:
        with pytest.raises(TransitError, match="regular PNG"):
            assets.read("assets/fifo.png")


def test_png_pixel_budget_is_checked_before_decode(tmp_path):
    (tmp_path / "assets").mkdir()
    Image.new("RGB", (11, 10)).save(tmp_path / "assets/image.png")
    with bundle_assets(tmp_path, replace(DEFAULT_LIMITS, page_pixels=100)) as assets:
        with pytest.raises(TransitError, match="bounded PNG"):
            assets.read("assets/image.png")


def test_rollback_does_not_delete_replacement_directory(tmp_path):
    moved = tmp_path / "owned-moved"
    replacement = None
    with pytest.raises(TransitError, match="ownership changed"):
        with atomic_output(tmp_path / "out", []) as stage:
            stage.rename(moved)
            stage.mkdir()
            (stage / "sentinel").write_text("belongs to another writer")
            replacement = stage
    assert replacement is not None
    assert (replacement / "sentinel").read_text() == "belongs to another writer"
    assert moved.is_dir() and not (tmp_path / "out").exists()
