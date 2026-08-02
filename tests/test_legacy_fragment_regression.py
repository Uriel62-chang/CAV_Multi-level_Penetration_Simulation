"""Regression: ``ssm_fragment_merged_count`` must not leak into legacy schema=1 contracts.

a424cb8 把 ``ssm_fragment_merged_count`` 加进共享 ``SAFETY_SSM_COLUMNS``，导致 legacy
schema=1 producer（``single_run.py`` 不输出该键）在 runner/writer 双层契约处失败：
parse 变 INVALID_DATA、writer 报 ``summary missing required key``。

本文件使用**非自证 fixture**（冻结 a424cb8 之前的历史 producer/contract 形状，
不随被测试集合动态构造）锁定修复结果：

- legacy 冻结集合（SAFETY_SSM_COLUMNS / SUMMARY_REQUIRED_KEYS / RUN_LEVEL_COLUMNS）不含 fragment；
- V4_1 / V4_2 集合保留 fragment（正式 v0.4.2 CSV 不丢列）；
- 冻结的历史 legacy 形状可通过 schema=1 contract；
- legacy writer 对冻结的 legacy 形状 run 得到 complete=True；
- 两个 legacy 集合 digest 精确等于 a424cb8 之前的历史值。
"""

import hashlib
import json

from scripts.schema import (
    RUN_LEVEL_COLUMNS,
    RUN_LEVEL_COLUMNS_V4_1,
    RUN_LEVEL_COLUMNS_V4_2,
    SAFETY_SSM_COLUMNS,
    SAFETY_SSM_COLUMNS_V4_1,
    SUMMARY_REQUIRED_KEYS,
    SUMMARY_REQUIRED_KEYS_V4_1,
    SUMMARY_REQUIRED_KEYS_V4_2,
    validate_summary_contract,
)

# a424cb8 之前 legacy schema=1 summary.json 必需键（冻结的历史 producer/contract 形状，
# 无 fragment）。硬编码：若 consumer 契约错误扩张，此 fixture 不会跟着扩张。
LEGACY_SUMMARY_KEYS = [
    "run_id",
    "scenario",
    "model",
    "pCAV",
    "vehN",
    "seed",
    "step_length_s",
    "warmup_period_s",
    "simulation_end_s",
    "detector_frequency_s",
    "mean_flow_veh_h",
    "max_flow_veh_h",
    "mean_speed_m_s",
    "detector_mean_speed_temporal_variance",
    "detector_speed_window_count",
    "det_xml",
    "ssm_raw_record_count",
    "ssm_invalid_record_count",
    "ssm_warmup_filtered_count",
    "ssm_valid_record_count",
    "ssm_mirrored_record_count",
    "ttc_conflict_event_count",
    "min_ttc_s",
    "ttc_affected_vehicle_count",
    "drac_conflict_event_count",
    "max_drac_mps2",
    "emergency_braking_count",
    "emergency_braking_affected_vehicle_count",
    "lane_change_count",
    "unsafe_lc_gap_count",
    "unsafe_lc_gap_ratio",
    "total_CO2_kg",
    "total_NOx_g",
    "total_PMx_g",
    "total_fuel_kg",
    "total_vehicle_km",
    "total_time_loss_s",
    "completed_lap_count",
    "mean_lap_time_s",
    "median_lap_time_s",
    "p95_lap_time_s",
    "lap_time_std_s",
    "ttc_events_per_1000_veh_km",
    "emergency_brakes_per_1000_veh_km",
    "lane_changes_per_1000_veh_km",
    "CO2_g_per_veh_km",
    "NOx_mg_per_veh_km",
    "PMx_mg_per_veh_km",
    "fuel_g_per_veh_km",
    "time_loss_s_per_veh_km",
    "mean_lap_delay_s",
    "p95_lap_delay_s",
    "ssm_parse_success",
    "lc_parse_success",
    "ep_parse_success",
    "ee_parse_success",
    "vr_parse_success",
]

_STRING_KEYS = {"run_id", "scenario", "model", "det_xml"}
_BOOL_KEYS = {
    "ssm_parse_success",
    "lc_parse_success",
    "ep_parse_success",
    "ee_parse_success",
    "vr_parse_success",
}
_INT_KEYS = {
    "vehN",
    "seed",
    "detector_frequency_s",
    "detector_speed_window_count",
    "ssm_raw_record_count",
    "ssm_invalid_record_count",
    "ssm_warmup_filtered_count",
    "ssm_valid_record_count",
    "ssm_mirrored_record_count",
    "ttc_conflict_event_count",
    "ttc_affected_vehicle_count",
    "drac_conflict_event_count",
    "emergency_braking_count",
    "emergency_braking_affected_vehicle_count",
    "lane_change_count",
    "unsafe_lc_gap_count",
    "completed_lap_count",
}
_STRING_VALUES = {
    "run_id": "run-1",
    "scenario": "scenario_0",
    "model": "IDM",
    "det_xml": "detector.xml",
}
_POSITIVE_FLOAT_KEYS = {
    "step_length_s": 0.1,
    "warmup_period_s": 600.0,
    "simulation_end_s": 3600.0,
    "total_vehicle_km": 1.0,
}
_POSITIVE_INT_KEYS = {"vehN": 10}


def _legacy_producer_summary() -> dict:
    """构造冻结的历史 legacy producer/contract 形状（a424cb8 前），不含 fragment 键。

    注意：这是契约 surrogate（硬编码键清单与取值），并非直接调用 legacy producer；
    用于非自证地锚定 schema=1 契约形状，不随被测试集合动态扩张。
    """
    summary = {}
    for key in LEGACY_SUMMARY_KEYS:
        if key in _STRING_KEYS:
            summary[key] = _STRING_VALUES[key]
        elif key in _BOOL_KEYS:
            summary[key] = True
        elif key in _POSITIVE_FLOAT_KEYS:
            summary[key] = _POSITIVE_FLOAT_KEYS[key]
        elif key in _POSITIVE_INT_KEYS:
            summary[key] = _POSITIVE_INT_KEYS[key]
        elif key in _INT_KEYS:
            summary[key] = 0
        elif key == "pCAV":
            summary[key] = 0.5
        else:
            summary[key] = 0.0
    return summary


def _digest(value) -> str:
    payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def test_legacy_sets_exclude_fragment_key():
    assert "ssm_fragment_merged_count" not in SAFETY_SSM_COLUMNS
    assert "ssm_fragment_merged_count" not in SUMMARY_REQUIRED_KEYS
    assert "ssm_fragment_merged_count" not in RUN_LEVEL_COLUMNS


def test_v4_1_and_v4_2_sets_keep_fragment_key():
    assert "ssm_fragment_merged_count" in SAFETY_SSM_COLUMNS_V4_1
    assert "ssm_fragment_merged_count" in SUMMARY_REQUIRED_KEYS_V4_1
    assert "ssm_fragment_merged_count" in RUN_LEVEL_COLUMNS_V4_1
    assert "ssm_fragment_merged_count" in SUMMARY_REQUIRED_KEYS_V4_2
    assert "ssm_fragment_merged_count" in RUN_LEVEL_COLUMNS_V4_2


def test_frozen_legacy_shape_passes_schema1_contract():
    summary = _legacy_producer_summary()
    assert "ssm_fragment_merged_count" not in summary
    assert validate_summary_contract(summary, "1") == []


def test_legacy_sets_digests_match_frozen_history():
    assert _digest(SUMMARY_REQUIRED_KEYS) == (
        "3e0e6441587f26604222e99eb543e47df8b6ea66f4bb963a4b1fb797a5754848"
    )
    assert _digest(RUN_LEVEL_COLUMNS) == (
        "24544f47367b5a61378d64394da7701e302823877055e19fa7d89c53d4395532"
    )


def test_frozen_legacy_writer_complete(tmp_path):
    import hashlib

    from scripts.results.writer import build_run_level_results

    run_id = "run-1"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    summary = _legacy_producer_summary()
    summary_bytes = json.dumps(summary).encode("utf-8")
    (run_dir / "summary.json").write_bytes(summary_bytes)
    status_common = {
        "pipeline_version": "v0.4.0.post1",
        "schema_version": "1",
        "config_sha256": "a" * 64,
        "run_spec_sha256": "b" * 64,
    }
    (run_dir / "simulation_status.json").write_text(
        json.dumps({**status_common, "run_id": run_id, "status": "SUCCESS"}),
        encoding="utf-8",
    )
    (run_dir / "parse_status.json").write_text(
        json.dumps(
            {
                **status_common,
                "run_id": run_id,
                "status": "SUCCESS",
                "summary_sha256": hashlib.sha256(summary_bytes).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    manifest = {
        "pipeline_version": "v0.4.0.post1",
        "schema_version": "1",
        "config_sha256": "a" * 64,
        "total": 1,
        "results": [{"run_id": run_id, "run_spec_sha256": "b" * 64}],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = build_run_level_results(tmp_path, tmp_path / "out", "v0.4.0.post1", manifest_path)
    assert report["complete"] is True
    assert report["excluded_runs"] == 0
    assert report["csv_rows"] == 1
