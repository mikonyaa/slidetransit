import json
from dataclasses import replace

import pytest

from slidetransit import cli
from slidetransit.limits import DEFAULT_LIMITS
from slidetransit.models import TransitError
from slidetransit.report import write_report


def test_owned_worker_timeout_is_controlled_error(tmp_path, monkeypatch, capsys, real):
    monkeypatch.setattr(cli, "DEFAULT_LIMITS", replace(DEFAULT_LIMITS, worker_seconds=0.001))
    code = cli.main(
        [
            "compare",
            "--manifest",
            str(real / "repeat.json"),
            "--out",
            str(tmp_path / "report"),
            "--json",
            "--no-open",
        ]
    )
    assert code == 2
    output = json.loads(capsys.readouterr().out)
    assert output["exitCode"] == 2 and "limit" in output["message"]
    assert not (tmp_path / "report").exists()


def test_report_json_bound_precedes_embedding(tmp_path):
    (tmp_path / "assets").mkdir()
    with pytest.raises(TransitError, match="JSON exceeds"):
        write_report(
            {"ownUnitText": "x" * 100}, tmp_path, replace(DEFAULT_LIMITS, report_json_bytes=10)
        )
    assert not (tmp_path / "report.html").exists()
