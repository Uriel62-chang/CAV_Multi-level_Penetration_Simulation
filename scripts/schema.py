"""v0.4.0 统一数据 Schema — 阶段二/三共用，避免字段清单漂移。

RUN_LEVEL_COLUMNS: 正式 CSV 列定义（阶段三 writer 使用）
SUMMARY_SCHEMA:     summary.json 必需字段（阶段二 parser 校验使用）
"""

from __future__ import annotations

# ── 正式 run-level CSV 列定义（阶段三 writer 按此顺序输出） ──

IDENTIFIER_COLUMNS = [
    "run_id",
    "scenario",
    "model",
    "pCAV",
    "requested_pcav",
    "realized_pcav",
    "cav_count",
    "hv_count",
    "vehN",
    "seed",
]

CONFIG_COLUMNS = [
    "step_length_s",
    "warmup_period_s",
    "simulation_end_s",
    "detector_frequency_s",
]

CAPACITY_COLUMNS = [
    "mean_flow_veh_h",
    "max_flow_veh_h",
    "mean_speed_m_s",
    "detector_mean_speed_temporal_variance",
    "detector_speed_window_count",
    "det_xml",
]

SAFETY_SSM_COLUMNS = [
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
]

SAFETY_EB_COLUMNS = [
    "emergency_braking_count",
    "emergency_braking_affected_vehicle_count",
]

LANECHANGE_COLUMNS = [
    "lane_change_count",
    "unsafe_lc_gap_count",
    "unsafe_lc_gap_ratio",
]

EMISSIONS_COLUMNS = [
    "total_CO2_kg",
    "total_NOx_g",
    "total_PMx_g",
    "total_fuel_kg",
]

EFFICIENCY_COLUMNS = [
    "total_vehicle_km",
    "non_internal_edge_vehicle_km",
    "total_time_loss_s",
    "completed_lap_count",
    "mean_lap_time_s",
    "median_lap_time_s",
    "p95_lap_time_s",
    "lap_time_std_s",
]

NORMALIZED_COLUMNS = [
    "ttc_events_per_1000_veh_km",
    "whole_network_ttc_events_per_1000_non_internal_edge_veh_km",
    "emergency_brakes_per_1000_veh_km",
    "lane_changes_per_1000_veh_km",
    "CO2_g_per_veh_km",
    "NOx_mg_per_veh_km",
    "PMx_mg_per_veh_km",
    "fuel_g_per_veh_km",
    "time_loss_s_per_veh_km",
]

DELAY_COLUMNS = [
    "mean_lap_delay_s",
    "p95_lap_delay_s",
]

QUALITY_COLUMNS = [
    "data_quality",
    "data_quality_detail",
]

RUN_LEVEL_COLUMNS = (
    IDENTIFIER_COLUMNS
    + CONFIG_COLUMNS
    + CAPACITY_COLUMNS
    + SAFETY_SSM_COLUMNS
    + SAFETY_EB_COLUMNS
    + LANECHANGE_COLUMNS
    + EMISSIONS_COLUMNS
    + EFFICIENCY_COLUMNS
    + NORMALIZED_COLUMNS
    + DELAY_COLUMNS
    + QUALITY_COLUMNS
)

# ── summary.json 审计字段（仅供阶段二内部，不进入 CSV） ──

AUDIT_COLUMNS = [
    "ssm_parse_success",
    "lc_parse_success",
    "ep_parse_success",
    "ee_parse_success",
    "vr_parse_success",
]

# ── summary.json 完整必需字段 = CSV 列（去掉 quality 列）+ 审计字段 ──

SUMMARY_REQUIRED_KEYS = (
    [
        column
        for column in IDENTIFIER_COLUMNS
        if column
        not in {
            "requested_pcav",
            "realized_pcav",
            "cav_count",
            "hv_count",
        }
    ]
    + CONFIG_COLUMNS
    + CAPACITY_COLUMNS
    + SAFETY_SSM_COLUMNS
    + SAFETY_EB_COLUMNS
    + LANECHANGE_COLUMNS
    + EMISSIONS_COLUMNS
    + [column for column in EFFICIENCY_COLUMNS if column != "non_internal_edge_vehicle_km"]
    + [
        column
        for column in NORMALIZED_COLUMNS
        if column != "whole_network_ttc_events_per_1000_non_internal_edge_veh_km"
    ]
    + DELAY_COLUMNS
    + AUDIT_COLUMNS
)
