from scripts.results.writer import (
    _build_row,
    _completion_flags,
    _format_report_summary,
    _quality_counts,
)


def _summary(**overrides):
    """纯净分支：_build_row 走 schema=2 v4_1 语义——summary 需自带身份/审计字段。"""
    summary = {
        "run_id": "writer-test",
        "scenario": "scenario_0",
        "model": "IDM",
        "realized_pcav": 0.5,
        "cav_count": 5,
        "hv_count": 5,
        "vehN": 10,
        "total_vehicle_km": 2.0,
        "non_internal_edge_vehicle_km": 2.0,
        "ttc_events_per_1000_veh_km": 500.0,
        "whole_network_ttc_events_per_1000_non_internal_edge_veh_km": 500.0,
        "ssm_parse_success": True,
        "lc_parse_success": True,
        "ep_parse_success": True,
        "ee_parse_success": True,
        "vr_parse_success": True,
        "fcd_parse_success": True,
    }
    summary.update(overrides)
    return summary


def test_writer_marks_all_successful_parsers_as_ok():
    row = _build_row(_summary(), "SUCCESS")
    assert row["data_quality"] == "ok"
    assert row["data_quality_detail"] == ""
    # 纯净分支：requested_pcav 已从契约列集移除（RunSpec 内部字段保留）
    assert "requested_pcav" not in row
    assert row["realized_pcav"] == 0.5
    assert row["cav_count"] == 5
    assert row["hv_count"] == 5
    assert row["non_internal_edge_vehicle_km"] == 2.0


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


def test_writer_complete_requires_valid_rows():
    assert _completion_flags(0, 0) == {
        "structurally_complete": True,
        "all_rows_valid": True,
        "complete": True,
    }
    assert _completion_flags(0, 1) == {
        "structurally_complete": True,
        "all_rows_valid": False,
        "complete": False,
    }
    warning = _build_row(_summary(vr_parse_success=False), "SUCCESS")
    counts = _quality_counts([warning])
    assert counts == {
        "quality_ok": 0,
        "quality_invariant_failed": 0,
        "quality_parser_warning": 1,
        "quality_non_ok": 1,
    }
    assert _completion_flags(0, counts["quality_non_ok"])["complete"] is False


def test_writer_cli_summary_uses_current_quality_schema():
    summary = _format_report_summary(
        {
            "csv_rows": 1,
            "quality_ok": 1,
            "quality_invariant_failed": 0,
            "quality_parser_warning": 0,
            "quality_non_ok": 0,
            "excluded_runs": 0,
            "complete": True,
        }
    )
    assert summary == (
        "[DONE] csv_rows=1  ok=1  non_ok=0  invariant_failed=0  "
        "parser_warning=0  excluded=0  complete=True"
    )
