from scripts.results.writer import _build_row


def _summary(**overrides):
    summary = {
        "run_id": "writer-test",
        "ssm_parse_success": True,
        "lc_parse_success": True,
        "ep_parse_success": True,
        "ee_parse_success": True,
        "vr_parse_success": True,
    }
    summary.update(overrides)
    return summary


def test_writer_marks_all_successful_parsers_as_ok():
    row = _build_row(_summary(), "SUCCESS")
    assert row["data_quality"] == "ok"
    assert row["data_quality_detail"] == ""


def test_writer_does_not_hide_failed_parser_audit():
    row = _build_row(_summary(vr_parse_success=False), "SUCCESS")
    assert row["data_quality"] == "parser_warning"
    assert "audit flags" in row["data_quality_detail"]


def test_writer_preserves_invariant_failure():
    row = _build_row(
        _summary(_invariant_errors=["total_vehicle_km <= 0"]),
        "INVALID_DATA",
    )
    assert row["data_quality"] == "invariant_failed"
    assert "total_vehicle_km" in row["data_quality_detail"]
