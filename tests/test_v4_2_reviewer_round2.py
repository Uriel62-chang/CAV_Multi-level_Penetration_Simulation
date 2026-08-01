"""正式 Reviewer 复检（第二轮）回归测试：P0-1 / P1-1 / P1-2 / P1-3 / P1-4。"""

import pandas as pd
import pytest

from scripts.results.aggregate import aggregate
from scripts.results.visualization import _paired_ttc_metric_column
from scripts.run_spec import PIPELINE_V4_1, PIPELINE_V4_2, RunSpec
from scripts.schema import (
    EMISSIONS_COLUMNS_V4_2,
    RUN_LEVEL_COLUMNS_V4_1,
    RUN_LEVEL_COLUMNS_V4_2,
    SUMMARY_REQUIRED_KEYS_V4_1,
    SUMMARY_REQUIRED_KEYS_V4_2,
    validate_summary_contract,
)

# ── P1-1：schema 分流，v0.4.2 扩展不污染 v0.4.1 schema=2 ──


def test_v4_1_columns_exclude_v4_2_emission_fields():
    for col in EMISSIONS_COLUMNS_V4_2:
        assert col not in RUN_LEVEL_COLUMNS_V4_1
        assert col not in SUMMARY_REQUIRED_KEYS_V4_1


def test_v4_2_columns_include_v4_2_emission_fields():
    for col in EMISSIONS_COLUMNS_V4_2:
        assert col in RUN_LEVEL_COLUMNS_V4_2
        assert col in SUMMARY_REQUIRED_KEYS_V4_2


def test_v4_1_summary_without_v4_2_fields_passes_contract():
    """v0.4.1 schema=2 summary（不含 v0.4.2 排放字段）必须通过契约校验（P1-1）。"""
    integer_keys = {
        "vehN",
        "seed",
        "cav_count",
        "hv_count",
        "assignment_seed",
        "sumo_seed",
        "detector_speed_window_count",
        "ssm_raw_record_count",
        "ssm_invalid_record_count",
        "ssm_warmup_filtered_count",
        "ssm_valid_record_count",
        "ssm_mirrored_record_count",
        "ssm_fragment_merged_count",
        "ttc_conflict_event_count",
        "ttc_affected_vehicle_count",
        "drac_conflict_event_count",
        "emergency_braking_count",
        "emergency_braking_affected_vehicle_count",
        "lane_change_count",
        "unsafe_lc_gap_count",
        "completed_lap_count",
        "detector_frequency_s",
        "edge_data_frequency_s",
    }
    bool_keys = {
        "ssm_parse_success",
        "lc_parse_success",
        "ep_parse_success",
        "ee_parse_success",
        "vr_parse_success",
        "fcd_parse_success",
        "ssm_not_collected",
        "with_internal",
    }
    summary = {}
    for key in SUMMARY_REQUIRED_KEYS_V4_1:
        if key in ("run_id", "scenario", "model", "det_xml"):
            summary[key] = "x"
        elif key in bool_keys:
            summary[key] = True
        elif key in integer_keys:
            summary[key] = 1
        else:
            summary[key] = 1.0
    assert validate_summary_contract(summary, "2", pipeline_version=PIPELINE_V4_1) == []
    # v0.4.2 契约则要求 V4_2 扩展字段
    errors = validate_summary_contract(summary, "2", pipeline_version=PIPELINE_V4_2)
    assert any("non_internal_CO2_kg" in e for e in errors)


# ── P1-2：排放双口径进入 run-level 聚合 ──


def _make_v4_2_agg_input(tmp_path):
    rows = []
    for a in (1, 2):
        rows.append(
            {
                "scenario": "scenario_0",
                "model": "IDM",
                "requested_pcav": None,
                "realized_pcav": 0.5,
                "cav_count": 5,
                "hv_count": 5,
                "vehN": 10,
                "assignment_seed": a,
                "sumo_seed": 101,
                "mean_flow_veh_h": 100.0,
                "data_quality": "ok",
                "non_internal_CO2_kg": 0.001 * a,
                "whole_network_CO2_g_per_veh_km": 1.5 * a,
            }
        )
    df = pd.DataFrame(rows)
    in_csv = tmp_path / "in.csv"
    out_csv = tmp_path / "out.csv"
    df.to_csv(in_csv, index=False)
    return aggregate(in_csv, out_csv, "2")


def test_aggregate_includes_v4_2_emission_columns(tmp_path):
    out = _make_v4_2_agg_input(tmp_path)
    row = out.iloc[0]
    assert "ni_co2_mean" in row and "ni_co2_count" in row
    assert "wn_co2_per_k_mean" in row
    assert row["ni_co2_mean"] == pytest.approx(0.0015)  # mean of 0.001, 0.002
    assert row["wn_co2_per_k_mean"] == pytest.approx(2.25)  # mean of 1.5, 3.0


# ── P1-3：Safety 入口对 legacy 错配列 fail-closed ──


def test_safety_metric_column_rejects_legacy_mismatched():
    df = pd.DataFrame({"whole_network_ttc_events_per_1000_non_internal_edge_veh_km_mean": [1.0]})
    with pytest.raises(ValueError, match="space-matched"):
        _paired_ttc_metric_column(df)


def test_safety_metric_column_accepts_paired():
    df = pd.DataFrame({"ttc_per_k_mean": [1.0]})
    assert _paired_ttc_metric_column(df) == "ttc_per_k_mean"


# ── P1-4：RunSpec 直构/from_dict 路径同样拒绝无效 v0.4.2 身份 ──


def _spec_v4_2(**overrides) -> RunSpec:
    base = dict(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="s0_IDM_v010_c005_as01_ss101",
        pipeline_version=PIPELINE_V4_2,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
    )
    base.update(overrides)
    return RunSpec(**base)


def test_runspec_rejects_main_with_ssm_enabled():
    with pytest.raises(ValueError, match="ssm_enabled=false"):
        _spec_v4_2(experiment_role="main_factorial", ssm_enabled=True)


def test_runspec_rejects_safety_without_ssm():
    with pytest.raises(ValueError, match="ssm_enabled=true"):
        _spec_v4_2(experiment_role="safety", ssm_enabled=False)


def test_runspec_rejects_analysis_outside_capture():
    with pytest.raises(ValueError, match="exceeds"):
        _spec_v4_2(analysis_ttc_threshold_s=5.0)  # capture ceiling 3.0
    with pytest.raises(ValueError, match="below"):
        _spec_v4_2(analysis_drac_threshold_mps2=2.0)  # capture floor 3.0


def test_runspec_accepts_valid_v4_2():
    _spec_v4_2(experiment_role="main_factorial", ssm_enabled=False)
    _spec_v4_2(experiment_role="safety", ssm_enabled=True)
