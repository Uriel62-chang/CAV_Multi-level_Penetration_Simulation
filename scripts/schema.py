"""统一数据 Schema — 阶段二/三共用，避免字段清单漂移。

从 v0.4.1 起 schema_version=2（双 seed 标识列 + subgroup 长表 + 审计字段）；
v0.4.2 在其上扩展采集状态列与排放双口径。
纯净分支：schema_version=1（v0.4.0~post3）契约已移除，仅支持 schema=2。
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
    "ttc_conflict_event_count",
    "min_ttc_s",
    "ttc_affected_vehicle_count",
    "drac_conflict_event_count",
    "max_drac_mps2",
]

# v0.4.1 fragment merge 扩展（a424cb8）：仅 schema=2 producer/parser 输出该键。
# 独立于 SAFETY_SSM_COLUMNS，避免改变 legacy schema=1 的冻结字段集（仿
# EMISSIONS_COLUMNS_V4_2 先例）。fragment 恢复历史相对位置（ssm_mirrored_record_count
# 与 ttc_conflict_event_count 之间，与正式 v0.4.2 CSV header 一致）。
SAFETY_SSM_COLUMNS_V4_1 = [
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

# P0-1（新审阅）：v0.4.2 run-level 采集状态列，区分未采集/解析失败/合法零检出。
# 仅 v0.4.2（V4_2）输出；v0.4.1/V4_1 冻结集不含。
STATUS_COLUMNS_V4_2 = [
    "experiment_role",
    "ssm_enabled",
    "ssm_not_collected",
]

# P2-1（审阅）：v0.4.2 分析/去重参数列（split-design 验收矩阵要求输出阈值与
# dedup 方法；summary 已写入，补入 run-level CSV 保持设计验收闭合）。
ANALYSIS_COLUMNS_V4_2 = [
    "analysis_ttc_threshold_s",
    "analysis_drac_threshold_mps2",
    "ssm_dedup_method",
    "ssm_mirror_overlap_ratio",
    "ssm_fragment_merge_gap_s",
]

# v0.4.2 排放双口径扩展（P0-7/P0-4）：non-internal 绝对量与全路网次要强度。
# 独立于 EMISSIONS_COLUMNS，避免改变 legacy schema=1 的冻结字段集。
EMISSIONS_COLUMNS_V4_2 = [
    "non_internal_CO2_kg",
    "non_internal_NOx_g",
    "non_internal_PMx_g",
    "non_internal_fuel_kg",
    "whole_network_CO2_g_per_veh_km",
    "whole_network_NOx_mg_per_veh_km",
    "whole_network_PMx_mg_per_veh_km",
    "whole_network_fuel_g_per_veh_km",
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

# ── summary.json 审计字段（仅供阶段二内部，不进入 CSV） ──
# 纯净分支（v0.4.0~post3 已移除）：仅保留 v0.4.1 起的 schema=2 审计字段。

# ═══════════════════════════════════════════════════════════════
# v0.4.1 schema_version=2 审计字段
# ═══════════════════════════════════════════════════════════════

AUDIT_COLUMNS_V4_1 = [
    "ssm_parse_success",
    "lc_parse_success",
    "ep_parse_success",
    "ee_parse_success",
    "vr_parse_success",
    "fcd_parse_success",
    "ssm_not_collected",
]

# v0.4.1 schema_version=2 核心 run-level CSV 列 (65 列)
RUN_LEVEL_COLUMNS_V4_1 = (
    list(IDENTIFIER_COLUMNS_V4_1)
    + list(CONFIG_COLUMNS_V4_1)
    + list(CAPACITY_COLUMNS)
    + list(SAFETY_SSM_COLUMNS_V4_1)
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
    + list(SAFETY_SSM_COLUMNS_V4_1)
    + list(SAFETY_EB_COLUMNS)
    + list(LANECHANGE_COLUMNS)
    + list(EMISSIONS_COLUMNS)
    + list(EFFICIENCY_COLUMNS)
    + list(NORMALIZED_COLUMNS)
    + list(DELAY_COLUMNS)
    + list(AUDIT_COLUMNS_V4_1)
)

# ═══════════════════════════════════════════════════════════════
# v0.4.2 schema_version=2 扩展（P0-4/P1-1；P0-1 采集状态列）
# v0.4.2 在 v0.4.1 schema=2 契约之上新增：采集状态列（experiment_role /
# ssm_enabled / ssm_not_collected，位于 IDENTIFIER 之后）与排放双口径字段。
# V4_1 集合保持冻结；validator/writer 按 pipeline_version 分流。
# ═══════════════════════════════════════════════════════════════

# 审阅 P0-1（Safety 设计）：DRAC 空间配对事件率（全路网 DRAC 事件 / 全路网 veh-km，
# 与 ttc_events_per_1000_veh_km 同口径）。writer 层从 summary 已存计数重算
# （drac_conflict_event_count + total_vehicle_km），不进 summary 契约
# （SUMMARY_REQUIRED_KEYS_V4_2 保持不变；main factorial ssm_not_collected 时为 NaN）。
DRAC_RATE_COLUMNS_V4_2 = [
    "drac_events_per_1000_veh_km",
]

RUN_LEVEL_COLUMNS_V4_2 = (
    list(IDENTIFIER_COLUMNS_V4_1)
    + list(STATUS_COLUMNS_V4_2)
    + list(ANALYSIS_COLUMNS_V4_2)
    + list(CONFIG_COLUMNS_V4_1)
    + list(CAPACITY_COLUMNS)
    + list(SAFETY_SSM_COLUMNS_V4_1)
    + list(SAFETY_EB_COLUMNS)
    + list(LANECHANGE_COLUMNS)
    + list(EMISSIONS_COLUMNS)
    + list(EFFICIENCY_COLUMNS)
    # P2-1（本轮审查）：排除 legacy 空间错配列 whole_network_ttc_events_per_
    # 1000_non_internal_edge_veh_km（全路网 TTC / non-internal veh-km，P1-4 已用
    # 空间配对列替代）——错误口径列残留正式工件易被按名误选。NORMALIZED_COLUMNS
    # 本身保留（schema=1 / v0.4.1 契约含该列）。
    + [
        c
        for c in NORMALIZED_COLUMNS
        if c != "whole_network_ttc_events_per_1000_non_internal_edge_veh_km"
    ]
    + list(DELAY_COLUMNS)
    + list(QUALITY_COLUMNS)
    + list(EMISSIONS_COLUMNS_V4_2)
    + list(DRAC_RATE_COLUMNS_V4_2)
)


def _dedup_keep_order(items):
    """去重并保持首次出现顺序（summary 必需键中 ssm_not_collected 同时属于
    STATUS_COLUMNS_V4_2 与 AUDIT_COLUMNS_V4_1，需合并为单键）。"""
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


SUMMARY_REQUIRED_KEYS_V4_2 = _dedup_keep_order(
    list(IDENTIFIER_COLUMNS_V4_1)
    + list(STATUS_COLUMNS_V4_2)
    + list(ANALYSIS_COLUMNS_V4_2)
    + list(CONFIG_COLUMNS_V4_1)
    + list(CAPACITY_COLUMNS)
    + list(SAFETY_SSM_COLUMNS_V4_1)
    + list(SAFETY_EB_COLUMNS)
    + list(LANECHANGE_COLUMNS)
    + list(EMISSIONS_COLUMNS)
    + list(EFFICIENCY_COLUMNS)
    # P2-1（本轮审查）：与 RUN_LEVEL_COLUMNS_V4_2 一致排除 legacy 空间错配列
    # whole_network_ttc_events_per_1000_non_internal_edge_veh_km（metrics 不再
    # 输出，不再必填）
    + [
        c
        for c in NORMALIZED_COLUMNS
        if c != "whole_network_ttc_events_per_1000_non_internal_edge_veh_km"
    ]
    + list(DELAY_COLUMNS)
    + list(AUDIT_COLUMNS_V4_1)
    + list(EMISSIONS_COLUMNS_V4_2)
)

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
# v0.4.1（schema=2）冻结 companion 表：排放强度跟随 total_vehicle_km（v0.4.1
# summary 不含 non_internal_edge_vehicle_km 键）。纯净分支已移除 schema=1 契约。
SUMMARY_NAN_RULES_V4_1 = {
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
    # legacy（schema=1 / v0.4.1 schema=2）冻结 companion：total_vehicle_km。
    # 不得改动：legacy summary 不含 non_internal_edge_vehicle_km 键。
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

# 审阅 P1-2（v0.4.2 专属）：主 estimand 为 non-internal（metrics.py P0-7），
# 排放强度 NaN companion 跟随 non-internal veh-km。
SUMMARY_NAN_RULES_V4_2 = dict(SUMMARY_NAN_RULES_V4_1)
SUMMARY_NAN_RULES_V4_2.update(
    {
        "CO2_g_per_veh_km": ("non_internal_edge_vehicle_km", 0),
        "NOx_mg_per_veh_km": ("non_internal_edge_vehicle_km", 0),
        "PMx_mg_per_veh_km": ("non_internal_edge_vehicle_km", 0),
        "fuel_g_per_veh_km": ("non_internal_edge_vehicle_km", 0),
    }
)


def validate_summary_contract(
    summary: dict, schema_version: str, pipeline_version: str | None = None
) -> list[str]:
    """Return field-level schema errors; valid no-event extrema may be NaN.

    纯净分支：仅支持 schema=2。按 pipeline_version 分流：v0.4.2 要求 V4_2
    （含排放双口径扩展），v0.4.1 保持 V4_1 冻结契约（P1-1）。
    """
    if schema_version != "2":
        raise ValueError(f"unsupported schema_version: {schema_version!r} (only '2' supported)")
    required = (
        SUMMARY_REQUIRED_KEYS_V4_2 if pipeline_version == "v0.4.2" else SUMMARY_REQUIRED_KEYS_V4_1
    )
    # 审阅 P2（复核）：v0.4.2 时 eb_parse_success 作为可选审计字段（若存在必须为 bool）
    eb_audit_keys: set[str] = set()
    if pipeline_version == "v0.4.2" and "eb_parse_success" in summary:
        eb_audit_keys = {"eb_parse_success"}
    # 审阅 P1-2：NaN companion 表按 pipeline 分流——v0.4.2 用 non-internal
    # 主 estimand 覆盖表，v0.4.1 保持 V4_1 冻结表。
    nan_rules = SUMMARY_NAN_RULES_V4_2 if pipeline_version == "v0.4.2" else SUMMARY_NAN_RULES_V4_1
    errors = [f"summary missing required key: {key}" for key in required if key not in summary]
    if errors:
        return errors

    string_keys = {"run_id", "scenario", "model", "det_xml", "experiment_role", "ssm_dedup_method"}
    bool_keys = (
        set(AUDIT_COLUMNS_V4_1)
        | eb_audit_keys
        | {"with_internal"}
        # P0-1（新审阅）：SSM 采集状态列为 bool
        | {"ssm_enabled", "ssm_not_collected"}
    )
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
        # 审阅 P1-2 / delta review：主强度与 v0.4.2 新增排放双口径字段纳入非负门禁
        # （NaN 由 SUMMARY_NAN_RULES_V4_2 放行，数值必须非负）
        "CO2_g_per_veh_km",
        "NOx_mg_per_veh_km",
        "PMx_mg_per_veh_km",
        "fuel_g_per_veh_km",
        "non_internal_CO2_kg",
        "non_internal_NOx_g",
        "non_internal_PMx_g",
        "non_internal_fuel_kg",
        "whole_network_CO2_g_per_veh_km",
        "whole_network_NOx_mg_per_veh_km",
        "whole_network_PMx_mg_per_veh_km",
        "whole_network_fuel_g_per_veh_km",
        "whole_network_ttc_events_per_1000_non_internal_edge_veh_km",
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
    # P0-1（新审阅）：SSM 未采集（ssm_not_collected=True）时，SSM 原始/处理计数、
    # 事件数、极值、受影响车辆数与事件率均为 NaN（"未采集"语义），跳过这些键的
    # 类型与有限性检查；safety 合法零检出仍为数值 0（不走此分支）。
    ssm_not_collected = summary.get("ssm_not_collected") is True
    keys_to_validate = list(required)
    for optional_key in (
        "non_internal_edge_vehicle_km",
        "whole_network_ttc_events_per_1000_non_internal_edge_veh_km",
    ):
        if optional_key in summary and optional_key not in keys_to_validate:
            keys_to_validate.append(optional_key)
    # 审阅 P2（复核）：eb_parse_success 为可选审计字段——存在时纳入校验
    if eb_audit_keys:
        keys_to_validate = [k for k in keys_to_validate if k not in eb_audit_keys]
        keys_to_validate.extend(sorted(eb_audit_keys))
    if ssm_not_collected:
        ssm_skip = set(SAFETY_SSM_COLUMNS_V4_1) | {
            "ttc_events_per_1000_veh_km",
            "whole_network_ttc_events_per_1000_non_internal_edge_veh_km",
        }
        keys_to_validate = [k for k in keys_to_validate if k not in ssm_skip]
        # P1（第二轮）：v0.4.2 未采集必须为 NaN（fail-closed 双向）——"伪零"（计数填 0）
        # 同样拒绝，不能只跳过类型检查。v0.4.1 的 ssm_not_collected 语义不同
        # （parse 标记，非意图性未采集），不适用 NaN 强制。
        if pipeline_version == "v0.4.2":
            for key in sorted(ssm_skip):
                if key in summary:
                    value = summary[key]
                    if not (isinstance(value, float) and math.isnan(value)):
                        errors.append(
                            f"summary {key} must be NaN when ssm_not_collected (got {value!r})"
                        )
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
        elif math.isnan(float(value)) and key not in nan_rules:
            errors.append(f"summary {key} must be finite")
        elif key in finite_nonnegative and float(value) < 0:
            errors.append(f"summary {key} must be non-negative")
        elif key in strictly_positive and float(value) <= 0:
            errors.append(f"summary {key} must be positive")
        elif key in {"pCAV", "requested_pcav", "realized_pcav"} and not 0 <= float(value) <= 1:
            errors.append(f"summary {key} must be within [0, 1]")
    if errors:
        return errors
    nan_skip = ssm_skip if ssm_not_collected else set()
    for metric, (companion, max_value) in nan_rules.items():
        if metric not in summary or metric in nan_skip:
            continue
        if companion not in summary:
            errors.append(f"summary {metric} requires companion key: {companion}")
        elif math.isnan(summary[metric]) and summary[companion] > max_value:
            errors.append(f"summary {metric} may be NaN only when {companion}<={max_value}")
    return errors
