from pathlib import Path

import pytest

from slidetransit.compare import run_comparison
from slidetransit.manifest import load_manifest

REAL = Path(__file__).parent / "fixtures/real"


@pytest.fixture
def real():
    return REAL


@pytest.fixture
def compare_case(tmp_path):
    def run(name, overrides=None):
        return run_comparison(load_manifest(REAL / (name + ".json"), overrides), tmp_path / name)

    return run
