import pytest

from slidetransit.models import TransitError
from slidetransit.review import apply_decisions, binding


def test_acceptance_cannot_convert_inconsistent_stored_coverage_to_pass(compare_case):
    report = compare_case("symbol")
    report["coverage"][0]["candidate"]["text"] = "unavailable"
    decisions = {
        "schemaVersion": "1.0",
        **binding(report),
        "decisions": [
            {
                "type": "accept-difference",
                "findingId": f["id"],
                "regionHash": f["regionHash"],
                "reason": "Synthetic acceptance exercise",
                "timestamp": "2026-10-12T12:00:00Z",
            }
            for f in report["findings"]
        ],
    }
    with pytest.raises(TransitError, match="analysisStatus.*coverage"):
        apply_decisions(report, decisions)
