"""统一数据 Schema — 阶段二/三共用，避免字段清单漂移。

RUN_LEVEL_COLUMNS: 正式 CSV 列定义（阶段三 writer 使用）
SUMMARY_REQUIRED_KEYS: summary.json 必需字段（阶段二 parser 校验使用）

从 v0.4.1 起 schema_version=2，新增双 seed 标识列与 subgroup 长表。
旧 schema_version=1 列定义保留以支持只读加载。
"""

from __future__ import annotations

import math

# ═══════════════════════════════════════════════════════════════
# v0.4.1 schema_version=2 列定义
# ═══════════════════════════════════════════════════════════════

IDENTIFIER_COLUMNS_V4_1 = [
    "run_id",
    "scenario",
    "model",
    "requested_pcav",
    "realized_pcav",
    "cav_count",
    "hv_count",
    "vehN",
    "assignment_seed",
    "sumo_seed",
]

CONFIG_COLUMNS_V4_1 = [
    "step_length_s",
    "warmup_period_s",
    "simulation_end_s",
    "detector_frequency_s",
    "edge_data_frequency_s",
    "ssm_capture_ttc_threshold_s",
    "ssm_capture_drac_threshold_mps2",
    "with_internal",
]

# ═══════════════════════════════════════════════════════════════
# v0.4.0 schema_version=1 列定义（只读兼容，不修改）
# ═══════════════════════════════════════════════════════════════

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
    "ssm_fragment_merged_count",
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

# ═══════════════════════════════════════════════════════════════
# v0.4.1 schema_version=2 审计字段
# ═══════════════════════════════════════════════════════════════

AUDIT_COLUMNS_V4_1 = AUDIT_COLUMNS + ["fcd_parse_success"]

# v0.4.1 schema_version=2 核心 run-level CSV 列 (64 列)
RUN_LEVEL_COLUMNS_V4_1 = (
    list(IDENTIFIER_COLUMNS_V4_1)
    + list(CONFIG_COLUMNS_V4_1)
    + list(CAPACITY_COLUMNS)
    + list(SAFETY_SSM_COLUMNS)
    + list(SAFETY_EB_COLUMNS)
    + list(LANECHANGE_COLUMNS)
    + list(EMISSIONS_COLUMNS)
    + list(EFFICIENCY_COLUMNS)
    + list(NORMALIZED_COLUMNS)
    + list(DELAY_COLUMNS)
    + list(QUALITY_COLUMNS)
)

# v0.4.1 schema_version=2 summary.json 必需字段
SUMMARY_REQUIRED_KEYS_V4_1 = (
    list(IDENTIFIER_COLUMNS_V4_1)
    + list(CONFIG_COLUMNS_V4_1)
    + list(CAPACITY_COLUMNS)
    + list(SAFETY_SSM_COLUMNS)
    + list(SAFETY_EB_COLUMNS)
    + list(LANECHANGE_COLUMNS)
    + list(EMISSIONS_COLUMNS)
    + list(EFFICIENCY_COLUMNS)
    + list(NORMALIZED_COLUMNS)
    + list(DELAY_COLUMNS)
    + list(AUDIT_COLUMNS_V4_1)
)

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

# ── v0.4.1 subgroup 长表列定义 ──

SUBGROUP_LONG_COLUMNS_V4_1 = [
    "run_id",
    "scenario",
    "model",
    "requested_pcav",
    "realized_pcav",
    "cav_count",
    "hv_count",
    "vehN",
    "assignment_seed",
    "sumo_seed",
    "metric_family",
    "group_dimension",
    "group_value",
    "metric_name",
    "metric_value",
]

# metric -> (companion field, maximum companion value for which NaN is valid)
SUMMARY_NAN_RULES = {
    "min_ttc_s": ("ttc_conflict_event_count", 0),
    "max_drac_mps2": ("drac_conflict_event_count", 0),
    "mean_speed_m_s": ("detector_speed_window_count", 0),
    "detector_mean_speed_temporal_variance": ("detector_speed_window_count", 1),
    "unsafe_lc_gap_ratio": ("lane_change_count", 0),
    "mean_lap_time_s": ("completed_lap_count", 0),
    "median_lap_time_s": ("completed_lap_count", 0),
    "p95_lap_time_s": ("completed_lap_count", 0),
    "lap_time_std_s": ("completed_lap_count", 0),
    "mean_lap_delay_s": ("completed_lap_count", 0),
    "p95_lap_delay_s": ("completed_lap_count", 0),
    "ttc_events_per_1000_veh_km": ("total_vehicle_km", 0),
    "emergency_brakes_per_1000_veh_km": ("total_vehicle_km", 0),
    "lane_changes_per_1000_veh_km": ("total_vehicle_km", 0),
    "CO2_g_per_veh_km": ("total_vehicle_km", 0),
    "NOx_mg_per_veh_km": ("total_vehicle_km", 0),
    "PMx_mg_per_veh_km": ("total_vehicle_km", 0),
    "fuel_g_per_veh_km": ("total_vehicle_km", 0),
    "time_loss_s_per_veh_km": ("total_vehicle_km", 0),
    "whole_network_ttc_events_per_1000_non_internal_edge_veh_km": (
        "non_internal_edge_vehicle_km",
        0,
    ),
}


def validate_summary_contract(summary: dict, schema_version: str) -> list[str]:
    """Return field-level schema errors; valid no-event extrema may be NaN."""
    required = SUMMARY_REQUIRED_KEYS_V4_1 if schema_version == "2" else SUMMARY_REQUIRED_KEYS
    errors = [f"summary missing required key: {key}" for key in required if key not in summary]
    if errors:
        return errors

    string_keys = {"run_id", "scenario", "model", "det_xml"}
    bool_keys = set(AUDIT_COLUMNS_V4_1 if schema_version == "2" else AUDIT_COLUMNS) | {
        "with_internal"
    }
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
    finite_nonnegative = {
        "pCAV",
        "requested_pcav",
        "realized_pcav",
        "step_length_s",
        "warmup_period_s",
        "simulation_end_s",
        "ssm_capture_ttc_threshold_s",
        "ssm_capture_drac_threshold_mps2",
        "total_vehicle_km",
        "non_internal_edge_vehicle_km",
        "mean_flow_veh_h",
        "max_flow_veh_h",
        "total_CO2_kg",
        "total_NOx_g",
        "total_PMx_g",
        "total_fuel_kg",
        "total_time_loss_s",
    }
    strictly_positive = {
        "step_length_s",
        "simulation_end_s",
        "ssm_capture_ttc_threshold_s",
        "ssm_capture_drac_threshold_mps2",
        "total_vehicle_km",
        "non_internal_edge_vehicle_km",
    }
    nullable = {"requested_pcav"}
    keys_to_validate = list(required)
    for optional_key in (
        "non_internal_edge_vehicle_km",
        "whole_network_ttc_events_per_1000_non_internal_edge_veh_km",
    ):
        if optional_key in summary and optional_key not in keys_to_validate:
            keys_to_validate.append(optional_key)
    for key in keys_to_validate:
        value = summary[key]
        if key in nullable and value is None:
            continue
        if key in string_keys:
            if not isinstance(value, str) or (key != "det_xml" and not value):
                errors.append(f"summary {key} must be a non-empty string")
        elif key in bool_keys:
            if type(value) is not bool:
                errors.append(f"summary {key} must be bool")
        elif key in integer_keys:
            if type(value) is not int or value < 0:
                errors.append(f"summary {key} must be a non-negative int")
        elif not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"summary {key} must be numeric")
        elif math.isinf(float(value)):
            errors.append(f"summary {key} must not be infinite")
        elif math.isnan(float(value)) and key not in SUMMARY_NAN_RULES:
            errors.append(f"summary {key} must be finite")
        elif key in finite_nonnegative and float(value) < 0:
            errors.append(f"summary {key} must be non-negative")
        elif key in strictly_positive and float(value) <= 0:
            errors.append(f"summary {key} must be positive")
        elif key in {"pCAV", "requested_pcav", "realized_pcav"} and not 0 <= float(value) <= 1:
            errors.append(f"summary {key} must be within [0, 1]")
    if errors:
        return errors
    for metric, (companion, max_value) in SUMMARY_NAN_RULES.items():
        if metric not in summary:
            continue
        if companion not in summary:
            errors.append(f"summary {metric} requires companion key: {companion}")
        elif math.isnan(summary[metric]) and summary[companion] > max_value:
            errors.append(f"summary {metric} may be NaN only when {companion}<={max_value}")
    return errors
