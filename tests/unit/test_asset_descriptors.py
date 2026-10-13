import json
import os
from dataclasses import replace

import pytest
from PIL import Image

from slidetransit.limits import DEFAULT_LIMITS, atomic_output, cleanup_owned_outputs
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


def test_parent_crash_cleanup_requires_registered_inode(tmp_path, monkeypatch):
    worker_temp = tmp_path / "worker-temp"
    worker_temp.mkdir()
    run_id = "a" * 32
    monkeypatch.setenv("SLIDETRANSIT_RUN_ID", run_id)
    monkeypatch.setenv("SLIDETRANSIT_WORKER_TEMP", str(worker_temp))
    replacement = None
    with pytest.raises(TransitError, match="ownership changed"):
        with atomic_output(tmp_path / "out", []) as stage:
            assert (
                json.loads((worker_temp / "owned-outputs.jsonl").read_text())["inode"]
                == stage.lstat().st_ino
            )
            stage.rename(tmp_path / "owned-moved")
            stage.mkdir()
            (stage / "sentinel").write_text("another writer")
            replacement = stage
    cleanup_owned_outputs(worker_temp, tmp_path, run_id)
    assert (replacement / "sentinel").read_text() == "another writer"
    assert (tmp_path / "owned-moved").is_dir()
    unregistered = tmp_path / (".slidetransit-" + run_id + "-unregistered")
    unregistered.mkdir()
    cleanup_owned_outputs(worker_temp, tmp_path, run_id)
    assert unregistered.is_dir()


def test_parent_crash_cleanup_removes_registered_owned_stage(tmp_path):
    worker_temp = tmp_path / "worker-temp"
    worker_temp.mkdir()
    run_id = "a" * 32
    stage = tmp_path / (".slidetransit-" + run_id + "-owned")
    stage.mkdir()
    metadata = stage.lstat()
    (stage / "partial").write_text("uncommitted")
    (worker_temp / "owned-outputs.jsonl").write_text(
        json.dumps(
            {
                "runId": run_id,
                "path": str(stage),
                "device": metadata.st_dev,
                "inode": metadata.st_ino,
            }
        )
        + "\n"
    )
    cleanup_owned_outputs(worker_temp, tmp_path, run_id)
    assert not stage.exists()
