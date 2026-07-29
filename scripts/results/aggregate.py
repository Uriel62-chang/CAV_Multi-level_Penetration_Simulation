"""Step 14: 多种子聚合 —— run-level → aggregated statistics.

    输入：run_level_results.csv（post3 为 10,080 行 × 60 列，每行一个 assignment seed）
    输出：aggregated_results.csv（2,016 行，每行一个 scenario×model×pCAV×vehN，
          含 5 个车辆类型排列 seed 的等权算术 mean/std/median/min/max/count）

    python3 -m scripts.results.aggregate \
      --input /home/lyc/simdata/cav-v0.4.0/results/run_level_results.csv \
      --output /home/lyc/simdata/cav-v0.4.0/results/aggregated_results.csv
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from scripts.schema import (
    CAPACITY_COLUMNS,
    DELAY_COLUMNS,
    EFFICIENCY_COLUMNS,
    EMISSIONS_COLUMNS,
    LANECHANGE_COLUMNS,
    NORMALIZED_COLUMNS,
    SAFETY_EB_COLUMNS,
    SAFETY_SSM_COLUMNS,
)

# 每个 run 先计算自身的比率，以下聚合再对各车辆类型排列 run 等权求算术统计；
# 它不是把事件数和暴露量分别跨 seed 汇总后计算 pooled ratio。

# ── 需要进行跨种子统计的指标列（排除标识列和 data_quality） ──

METRIC_COLUMNS = (
    CAPACITY_COLUMNS
    + SAFETY_SSM_COLUMNS
    + SAFETY_EB_COLUMNS
    + LANECHANGE_COLUMNS
    + EMISSIONS_COLUMNS
    + EFFICIENCY_COLUMNS
    + NORMALIZED_COLUMNS
    + DELAY_COLUMNS
)

# 排除非数值列（det_xml 是路径字符串，detector 窗口数是离散量但可聚合）
_NON_AGGREGATABLE = {"det_xml"}
METRIC_COLUMNS = tuple(c for c in METRIC_COLUMNS if c not in _NON_AGGREGATABLE)

GROUP_KEYS_LEGACY = ["scenario", "model", "requested_pcav", "vehN"]
GROUP_KEYS_V4_1 = ["scenario", "model", "vehN", "cav_count"]


def aggregate(input_csv: Path, output_csv: Path, schema_ver: str) -> pd.DataFrame:
    if schema_ver not in ("1", "2"):
        raise ValueError(f"schema_ver must be '1' or '2', got {schema_ver!r}")

    group_keys = GROUP_KEYS_V4_1 if schema_ver == "2" else GROUP_KEYS_LEGACY

    df = pd.read_csv(input_csv)
    if schema_ver == "1" and "requested_pcav" not in df.columns:
        df["requested_pcav"] = df["pCAV"]

    # 排除 data_quality != ok 的行（仅对 ok 数据做聚合）
    df_ok = df[df["data_quality"] == "ok"].copy()

    # 聚合函数
    agg_funcs = {
        col: ["mean", "std", "median", "min", "max", "count"]
        for col in METRIC_COLUMNS
        if col in df_ok.columns
    }

    grouped = df_ok.groupby(list(group_keys), dropna=False).agg(agg_funcs)

    # 展平 MultiIndex 列名：mean_flow_veh_h → flow_mean, flow_std, ...
    short_names = {
        "mean_flow_veh_h": "flow",
        "max_flow_veh_h": "max_flow",
        "mean_speed_m_s": "speed",
        "detector_mean_speed_temporal_variance": "speed_var",
        "detector_speed_window_count": "det_win",
        "ssm_raw_record_count": "ssm_raw",
        "ssm_invalid_record_count": "ssm_inv",
        "ssm_warmup_filtered_count": "ssm_warm",
        "ssm_valid_record_count": "ssm_valid",
        "ssm_mirrored_record_count": "ssm_mirr",
        "ttc_conflict_event_count": "ttc",
        "min_ttc_s": "min_ttc",
        "ttc_affected_vehicle_count": "ttc_veh",
        "drac_conflict_event_count": "drac",
        "max_drac_mps2": "max_drac",
        "emergency_braking_count": "eb",
        "emergency_braking_affected_vehicle_count": "eb_veh",
        "lane_change_count": "lc",
        "unsafe_lc_gap_count": "unsafe_lc",
        "unsafe_lc_gap_ratio": "unsafe_lc_ratio",
        "total_CO2_kg": "co2",
        "total_NOx_g": "nox",
        "total_PMx_g": "pmx",
        "total_fuel_kg": "fuel",
        "total_vehicle_km": "veh_km",
        "total_time_loss_s": "time_loss",
        "completed_lap_count": "laps",
        "mean_lap_time_s": "lap",
        "median_lap_time_s": "lap_med",
        "p95_lap_time_s": "lap_p95",
        "lap_time_std_s": "lap_std",
        "ttc_events_per_1000_veh_km": "ttc_per_k",
        "emergency_brakes_per_1000_veh_km": "eb_per_k",
        "lane_changes_per_1000_veh_km": "lc_per_k",
        "CO2_g_per_veh_km": "co2_per_k",
        "NOx_mg_per_veh_km": "nox_per_k",
        "PMx_mg_per_veh_km": "pmx_per_k",
        "fuel_g_per_veh_km": "fuel_per_k",
        "time_loss_s_per_veh_km": "tl_per_k",
        "mean_lap_delay_s": "delay",
        "p95_lap_delay_s": "delay_p95",
    }

    new_columns = {}
    for col in METRIC_COLUMNS:
        if col not in df_ok.columns:
            continue
        short = short_names.get(col, col)
        for stat in ["mean", "std", "median", "min", "max"]:
            new_columns[(col, stat)] = f"{short}_{stat}"
        new_columns[(col, "count")] = f"{short}_count"
    new_columns[("mean_flow_veh_h", "count")] = "n_valid"

    grouped.columns = grouped.columns.map(lambda x: new_columns.get(x, f"{x[0]}_{x[1]}"))
    grouped = grouped.reset_index()
    if schema_ver == "2":
        grouped.insert(2, "pCAV", grouped["cav_count"] / grouped["vehN"])
        grouped.insert(4, "requested_pcav", float("nan"))
    else:
        grouped.insert(2, "pCAV", grouped["requested_pcav"])
        requested_pcav_col = grouped.pop("requested_pcav")
        grouped.insert(4, "requested_pcav", requested_pcav_col)
    grouped.insert(
        5,
        "realized_pcav",
        (grouped["vehN"] * grouped["pCAV"]).round() / grouped["vehN"],
    )
    grouped.insert(6, "flow_valid_run_count", grouped["n_valid"])
    grouped.insert(7, "assignment_seed_run_count", grouped["n_valid"])
    grouped.insert(8, "independent_random_replication_count", 0)

    if not grouped.columns.is_unique:
        duplicates = grouped.columns[grouped.columns.duplicated()].tolist()
        raise RuntimeError(f"duplicate aggregated column names: {duplicates}")

    # 标准差为 NaN（n_valid=1 时）填 0
    std_cols = [c for c in grouped.columns if c.endswith("_std")]
    for c in std_cols:
        grouped[c] = grouped[c].fillna(0.0)

    grouped.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"[WRITE] {len(grouped)} aggregated rows → {output_csv}")

    return grouped


def aggregate_subgroup(input_csv: Path, output_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(input_csv)
    group_keys = [
        "scenario",
        "model",
        "vehN",
        "cav_count",
        "metric_family",
        "group_dimension",
        "group_value",
        "metric_name",
    ]
    grouped = (
        df.groupby(group_keys, dropna=False)
        .agg(
            mean=("metric_value", "mean"),
            std=("metric_value", "std"),
            median=("metric_value", "median"),
            min=("metric_value", "min"),
            max=("metric_value", "max"),
            count=("metric_value", "count"),
        )
        .reset_index()
    )
    std_cols = [c for c in grouped.columns if c == "std"]
    for c in std_cols:
        grouped[c] = grouped[c].fillna(0.0)
    grouped.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"[WRITE] {len(grouped)} aggregated subgroup rows → {output_csv}")
    return grouped


def main():
    parser = argparse.ArgumentParser(description="v0.4.0 多种子聚合")
    parser.add_argument("--input", required=True, help="run_level_results.csv 路径")
    parser.add_argument("--output", required=True, help="输出 aggregated_results.csv 路径")
    parser.add_argument(
        "--schema-version", required=True, help="schema version for column routing (1 or 2)"
    )
    args = parser.parse_args()

    input_csv = Path(args.input)
    if not input_csv.exists():
        print(f"[ERROR] {input_csv} not found")
        sys.exit(1)

    df = aggregate(input_csv, Path(args.output), args.schema_version)

    # 汇总
    groups = len(df)
    metrics = sum(1 for c in df.columns if c not in GROUP_KEYS_LEGACY and c != "n_valid") // 5
    print(f"[DONE] {groups} groups × {metrics} metrics × 5 statistics (mean/std/median/min/max)")
    print(f"       input: {input_csv}")
    print(f"       output: {args.output}")


if __name__ == "__main__":
    main()
