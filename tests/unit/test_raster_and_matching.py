import numpy as np
from PIL import Image

from slidetransit.compare import raster_regions
from slidetransit.matching import match_blocks
from slidetransit.models import BBox, Config, TextBlock, update_summary


def test_raster_noise_hint_keeps_small_meaningful_region():
    before = Image.new("RGB", (100, 60), "white")
    after = before.copy()
    after.putpixel((10, 10), (230, 230, 230))
    after.putpixel((80, 45), (0, 0, 0))
    regions, mask = raster_regions(before, after, Config())
    assert len(regions) == 2
    assert sorted(r["maxDelta"] for r in regions) == [25, 255]
    assert np.asarray(mask).sum() == 2 * 255


def test_text_duplicates_never_force_a_pair():
    one = TextBlock("same", BBox(0, 0, 20, 10), ["same"], 10, [])
    two = TextBlock("same", BBox(5, 0, 25, 10), ["same"], 10, [])
    pairs, left, right = match_blocks([one, two], [one, two])
    assert pairs == []
    assert len(left) == len(right) == 2


def test_exit_precedence_and_absent_coverage():
    r = {
        "config": {"fail_on": "medium"},
        "analysisStatus": "incomplete",
        "findings": [],
        "decisions": [],
    }
    assert update_summary(r) == 3
    r["findings"] = [{"reviewState": "open", "severity": "high"}]
    assert update_summary(r) == 1
    r["analysisStatus"] = "error"
    assert update_summary(r) == 2
