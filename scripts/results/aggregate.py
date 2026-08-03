"""Step 14: 多种子聚合 —— run-level → aggregated statistics.

    输入：run_level_results.csv（v0.4.2 为 3,888/84 行，每行一个 (assignment_seed, sumo_seed)
          组合）
    输出：aggregated_results.csv（v0.4.2 为 528/84 行，每行一个 scenario×model×vehN×cav_count，
          含双 seed 组合的等权算术 mean/std/median/min/max/count）

    python3 -m scripts.results.aggregate \
      --input results/v0.4.2/main/run_level_results.csv \
      --output results/v0.4.2/main/aggregated_results.csv \
      --schema-version 2 --manifest raw_v0.4.2/main/manifest.json
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from scripts.schema import (
    CAPACITY_COLUMNS,
    DELAY_COLUMNS,
    DRAC_RATE_COLUMNS_V4_2,
    EFFICIENCY_COLUMNS,
    EMISSIONS_COLUMNS,
    EMISSIONS_COLUMNS_V4_2,
    LANECHANGE_COLUMNS,
    NORMALIZED_COLUMNS,
    SAFETY_EB_COLUMNS,
    SAFETY_SSM_COLUMNS_V4_1,
)

# 每个 run 先计算自身的比率，以下聚合再对各车辆类型排列 run 等权求算术统计；
# 它不是把事件数和暴露量分别跨 seed 汇总后计算 pooled ratio。

# ── 需要进行跨种子统计的指标列（排除标识列和 data_quality） ──

METRIC_COLUMNS = (
    CAPACITY_COLUMNS
    + SAFETY_SSM_COLUMNS_V4_1
    + SAFETY_EB_COLUMNS
    + LANECHANGE_COLUMNS
    + EMISSIONS_COLUMNS
    + EMISSIONS_COLUMNS_V4_2  # P1-2：排放双口径进入 run-level 聚合（schema=1 CSV 无这些列，自动跳过）
    + EFFICIENCY_COLUMNS
    + NORMALIZED_COLUMNS
    + DELAY_COLUMNS
    + DRAC_RATE_COLUMNS_V4_2  # 审阅 P0-1：DRAC 空间配对事件率进入聚合（V4_1 CSV 无此列，自动跳过）
)

# 排除非数值列（det_xml 是路径字符串，detector 窗口数是离散量但可聚合）
_NON_AGGREGATABLE = {"det_xml"}
METRIC_COLUMNS = tuple(c for c in METRIC_COLUMNS if c not in _NON_AGGREGATABLE)

GROUP_KEYS_V4_1 = ["scenario", "model", "vehN", "cav_count"]


def _expected_seed_pairs(manifest: dict, vehN: int, cav_count: int) -> set[tuple[int, int]]:
    """从实验 manifest（resolved config）推导某 treatment 的期望 (assignment, sumo) 对。

    端点（cav=0 或 cav=vehN）assignment_seed 为失活 sentinel 0；interior 为
    treatment.assignment_seeds × sumo_seeds（无显式时回退 [1,2,3]）。
    """
    cfg = manifest.get("resolved_config") or manifest
    treatments = cfg.get("treatments") or []
    treatment = next((t for t in treatments if int(t.get("vehicle_count", -1)) == vehN), None)
    if treatment is None:
        raise ValueError(f"manifest missing treatment for vehN={vehN}")
    aseeds_raw = treatment.get("assignment_seeds") or cfg.get("seeds") or []
    aseeds = [int(a) for a in aseeds_raw]
    if not aseeds:
        aseeds = [1] if cav_count in (0, vehN) else [1, 2, 3]
    if cav_count == 0 or cav_count == vehN:
        aseeds = [0]  # 失活 sentinel（_build_cav_count_specs 端点截断）
    sumo_seeds = [int(s) for s in (cfg.get("sumo_seeds") or [])]
    return {(a, s) for a in aseeds for s in sumo_seeds}


def aggregate(
    input_csv: Path, output_csv: Path, schema_ver: str, manifest: dict | None = None
) -> pd.DataFrame:
    # 纯净分支：仅支持 schema=2（v0.4.1/v0.4.2）——schema=1（v0.4.0~post3）已移除
    if schema_ver != "2":
        raise ValueError(f"schema_ver must be '2', got {schema_ver!r}")
    # P1-2（审阅）：schema=2 在函数层强制 manifest（CLI 强制可被 import 调用绕过）。
    if manifest is None:
        raise ValueError(
            "schema=2 aggregation requires experiment manifest (--manifest); "
            "run_id / seed-pair completeness cannot be verified without it"
        )

    group_keys = GROUP_KEYS_V4_1

    df = pd.read_csv(input_csv)
    # 审阅 P2-2：聚合入口强制单一 experiment_role——main factorial 与
    # safety 不得混合聚合（分组键不含角色，混合会串组）
    if "experiment_role" in df.columns:
        roles = sorted(str(r) for r in df["experiment_role"].dropna().unique())
        if len(roles) > 1:
            raise ValueError(
                f"run-level CSV 含多个 experiment_role: {roles}——main/safety 必须分开聚合"
            )

    # 排除 data_quality != ok 的行（仅对 ok 数据做聚合）
    df_ok = df[df["data_quality"] == "ok"].copy()

    # P0-3：schema=2 双 seed 统计单位——分别记录 assignment/sumo 水平数、组合数与有效 n，
    # 并拒绝缺失/重复组合（端点 assignment 失活为 1 个水平，sumo seed 仍活动）。
    # P0-7：schema=2 时缺失 seed 列必须 fail-closed，不得静默退回旧统计。
    seed_stats = None
    if schema_ver == "2":
        if "assignment_seed" not in df_ok.columns or "sumo_seed" not in df_ok.columns:
            raise ValueError(
                "schema=2 aggregation requires both 'assignment_seed' and 'sumo_seed' "
                f"columns; missing: "
                f"{[c for c in ('assignment_seed', 'sumo_seed') if c not in df_ok.columns]}"
            )
        # P1-5（新审阅）：manifest 提供时，CSV run_id 集合必须与 manifest 期望完全相等。
        if manifest is not None:
            manifest_run_ids = {
                r["run_id"] for r in (manifest.get("results") or []) if isinstance(r, dict)
            }
            csv_run_ids = set(df["run_id"])
            missing_ids = manifest_run_ids - csv_run_ids
            extra_ids = csv_run_ids - manifest_run_ids
            if missing_ids or extra_ids:
                raise ValueError(
                    "run_id set mismatch vs manifest: "
                    f"missing={sorted(missing_ids)[:5]} extra={sorted(extra_ids)[:5]}"
                )
        # P1（本轮）：预期分组来自完整 CSV（含非 ok 行），逐组检查 df_ok 的 seed 对；
        # 整组无 data_quality=ok 数据必须 fail-closed，不得静默删除该组。
        seed_groups = df_ok.groupby(list(group_keys), dropna=False)
        ok_group_map = {(k,) if not isinstance(k, tuple) else k: g for k, g in seed_groups}
        rows = []
        for keys, _grp_all in df.groupby(list(group_keys), dropna=False):
            if not isinstance(keys, tuple):
                keys = (keys,)
            grp_ok = ok_group_map.get(keys)
            if grp_ok is None or grp_ok.empty:
                raise ValueError(
                    f"group {keys} has no data_quality=ok runs "
                    "(whole treatment non-ok; not silently dropped)"
                )
            a_levels = sorted(grp_ok["assignment_seed"].dropna().unique())
            s_levels = sorted(grp_ok["sumo_seed"].dropna().unique())
            combos = list(zip(grp_ok["assignment_seed"], grp_ok["sumo_seed"], strict=True))
            # 组合唯一性检查（同一 (assignment, sumo) 不得出现多次）
            seen = set()
            for a, s in combos:
                pair = (a, s)
                if pair in seen:
                    raise ValueError(
                        f"duplicate (assignment_seed={a}, sumo_seed={s}) in group {keys}"
                    )
                seen.add(pair)
            # P1-5（新审阅）：期望组合必须与冻结配置完全相等（缺失/多余均 fail-closed）。
            if manifest is not None:
                expected = _expected_seed_pairs(manifest, int(keys[2]), int(keys[3]))
                actual = set(seen)
                missing_pairs = expected - actual
                extra_pairs = actual - expected
                if missing_pairs or extra_pairs:
                    raise ValueError(
                        f"seed pair set mismatch for group {keys}: "
                        f"missing={sorted(missing_pairs)[:6]} extra={sorted(extra_pairs)[:6]}"
                    )
            rows.append(
                {
                    **dict(zip(group_keys, keys, strict=True)),
                    "_a_levels": len(a_levels),
                    "_s_levels": len(s_levels),
                    "_combos": len(combos),
                    "_effective_n": len(combos),
                }
            )
        seed_stats = pd.DataFrame(rows)

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
        "non_internal_CO2_kg": "ni_co2",
        "non_internal_NOx_g": "ni_nox",
        "non_internal_PMx_g": "ni_pmx",
        "non_internal_fuel_kg": "ni_fuel",
        "whole_network_CO2_g_per_veh_km": "wn_co2_per_k",
        "whole_network_NOx_mg_per_veh_km": "wn_nox_per_k",
        "whole_network_PMx_mg_per_veh_km": "wn_pmx_per_k",
        "whole_network_fuel_g_per_veh_km": "wn_fuel_per_k",
        "total_vehicle_km": "veh_km",
        "total_time_loss_s": "time_loss",
        "completed_lap_count": "laps",
        "mean_lap_time_s": "lap",
        "median_lap_time_s": "lap_med",
        "p95_lap_time_s": "lap_p95",
        "lap_time_std_s": "lap_std",
        "ttc_events_per_1000_veh_km": "ttc_per_k",
        "drac_events_per_1000_veh_km": "drac_per_k",  # 审阅 P0-1：DRAC 空间配对事件率
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
        # P0-2：count 网格下 realized_pcav 为权威渗透率；requested_pcav 保持 nullable
        grouped.insert(2, "pCAV", grouped["cav_count"] / grouped["vehN"])
        grouped.insert(4, "requested_pcav", float("nan"))
    else:
        grouped.insert(2, "pCAV", grouped["requested_pcav"])
        requested_pcav_col = grouped.pop("requested_pcav")
        grouped.insert(4, "requested_pcav", requested_pcav_col)
    # 审阅 P2-2（本轮）：聚合输出保留 experiment_role——单角色时写入首列；
    # 输出层自描述，且可视化角色门禁依赖此列（防止 main/safety 聚合产物混用）
    if schema_ver == "2" and "experiment_role" in df_ok.columns:
        roles = df_ok["experiment_role"].dropna().unique()
        if len(roles) == 1:
            grouped.insert(0, "experiment_role", str(roles[0]))

    grouped.insert(
        5,
        "realized_pcav",
        (grouped["vehN"] * grouped["pCAV"]).round() / grouped["vehN"],
    )
    # P1-1：输出 seed_scope（设计要求的统计单位说明）
    if schema_ver == "2":
        grouped.insert(6, "seed_scope", "vehicle_type_assignment")
    grouped.insert(7, "flow_valid_run_count", grouped["n_valid"])
    # P0-3：双 seed 统计单位——assignment 水平数、sumo 水平数、组合数、有效 n
    if seed_stats is not None:
        grouped = grouped.merge(
            seed_stats.drop(columns=["_effective_n"]),
            on=list(group_keys),
            how="left",
            validate="one_to_one",
        )
        grouped = grouped.rename(
            columns={
                "_a_levels": "assignment_seed_level_count",
                "_s_levels": "sumo_seed_level_count",
                "_combos": "seed_pair_combination_count",
            }
        )
        grouped.insert(9, "assignment_seed_run_count", grouped["seed_pair_combination_count"])
        grouped.insert(10, "sumo_seed_run_count", grouped["sumo_seed_level_count"])
        grouped.insert(11, "independent_random_replication_count", 0)
    else:
        grouped.insert(7, "assignment_seed_run_count", grouped["n_valid"])
        grouped.insert(8, "independent_random_replication_count", 0)

    if not grouped.columns.is_unique:
        duplicates = grouped.columns[grouped.columns.duplicated()].tolist()
        raise RuntimeError(f"duplicate aggregated column names: {duplicates}")

    # 标准差 NaN 规则（P0-1 新审阅修订）：仅 count==1（单样本无方差）时填 0；
    # count==0（全 NaN 组，如 SSM 未采集的 main 网格）保留 NaN，不得填 0，
    # 否则无法区分"未采集"与"单样本"。
    std_cols = [c for c in grouped.columns if c.endswith("_std")]
    for c in std_cols:
        count_col = c[: -len("_std")] + "_count"
        if count_col in grouped.columns:
            single = grouped[count_col] == 1
            grouped.loc[single, c] = grouped.loc[single, c].fillna(0.0)
        else:
            grouped[c] = grouped[c].fillna(0.0)

    grouped.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"[WRITE] {len(grouped)} aggregated rows → {output_csv}")

    return grouped


def aggregate_subgroup(
    input_csv: Path, output_csv: Path, manifest: dict | None = None
) -> pd.DataFrame:
    """subgroup 长表聚合（P1-2 审阅：manifest 强制 + run_id/seed-pair/预期组检查）。

    subgroup CSV 为 schema=2 产物，必须带实验 manifest 才能验证 run_id 集合、
    每 treatment 的 seed pair 与预期 metric 组完整（缺失/多余/重复 fail-closed）。
    """
    if manifest is None:
        raise ValueError(
            "aggregate_subgroup requires experiment manifest; "
            "run_id / seed-pair / expected-group completeness cannot be verified without it"
        )
    df = pd.read_csv(input_csv)
    # run_id 集合全等
    manifest_run_ids = {r["run_id"] for r in (manifest.get("results") or []) if isinstance(r, dict)}
    csv_run_ids = set(df["run_id"])
    missing_ids = manifest_run_ids - csv_run_ids
    extra_ids = csv_run_ids - manifest_run_ids
    if missing_ids or extra_ids:
        raise ValueError(
            "subgroup run_id set mismatch vs manifest: "
            f"missing={sorted(missing_ids)[:5]} extra={sorted(extra_ids)[:5]}"
        )
    # 每 treatment 的 seed pair 与冻结配置全等
    for keys, grp in df.groupby(["scenario", "model", "vehN", "cav_count"], dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        actual = set(zip(grp["assignment_seed"], grp["sumo_seed"], strict=True))
        expected = _expected_seed_pairs(manifest, int(keys[2]), int(keys[3]))
        if actual != expected:
            raise ValueError(
                f"subgroup seed pair set mismatch for group {keys}: "
                f"missing={sorted(expected - actual)[:6]} extra={sorted(actual - expected)[:6]}"
            )
    # 预期 metric 组（与 writer _expected_subgroup_keys 一致）；fcd_enabled 从
    # manifest resolved_config 推导（P1-2 审阅：不得从 CSV 是否还有 headway 行推断，
    # 否则 headway 行被删会误判 FCD 未启用）。
    from scripts.results.writer import _expected_subgroup_keys

    cfg = manifest.get("resolved_config") or manifest
    fcd_enabled = cfg.get("fcd_profile") is not None
    expected_keys = set(_expected_subgroup_keys(fcd_enabled))
    # 逐 run_id 验证完整且唯一的 metric-key 集（P1-2 审阅：其他 run 的完整
    # 指标不得掩盖某个 run 的缺行；重复行会被 set 消除，必须用 len 一并拒绝）。
    for run_id, grp in df.groupby("run_id", dropna=False):
        keys = set(
            zip(
                grp["metric_family"],
                grp["group_dimension"],
                grp["group_value"],
                grp["metric_name"],
                strict=True,
            )
        )
        if keys != expected_keys or len(grp) != len(expected_keys):
            missing_keys = expected_keys - keys
            extra_keys = keys - expected_keys
            duplicates = len(grp) - len(keys) if len(grp) > len(keys) else 0
            raise ValueError(
                f"subgroup metric-key set mismatch for run {run_id}: "
                f"missing={sorted(missing_keys)[:5]} extra={sorted(extra_keys)[:5]} "
                f"duplicate_rows={duplicates}"
            )
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
    # P1（第二轮）：subgroup 聚合与 aggregate() 同规则——仅 count==1 时 std 填 0，
    # count==0（全 NaN 组，如 main 未采集 SSM）保留 NaN，不得填 0。
    std_cols = [c for c in grouped.columns if c == "std"]
    for c in std_cols:
        single = grouped["count"] == 1
        grouped.loc[single, c] = grouped.loc[single, c].fillna(0.0)
    grouped.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"[WRITE] {len(grouped)} aggregated subgroup rows → {output_csv}")
    return grouped


def main():
    parser = argparse.ArgumentParser(description="多种子聚合（纯净分支 schema=2）")
    parser.add_argument("--input", required=True, help="run_level_results.csv 路径")
    parser.add_argument("--output", required=True, help="输出 aggregated_results.csv 路径")
    parser.add_argument(
        "--schema-version", required=True, help="schema version for column routing (1 or 2)"
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="实验 manifest.json 路径（schema=2 必需；用于期望 run_id/seed pair 集合校验）",
    )
    args = parser.parse_args()

    input_csv = Path(args.input)
    if not input_csv.exists():
        print(f"[ERROR] {input_csv} not found")
        sys.exit(1)

    manifest_data = None
    if args.schema_version == "2":
        if not args.manifest:
            print("[ERROR] --manifest is required for --schema-version 2 (P1-5 fail-closed)")
            sys.exit(1)
        manifest_path = Path(args.manifest)
        if not manifest_path.exists():
            print(f"[ERROR] manifest not found: {manifest_path}")
            sys.exit(1)
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[ERROR] manifest unreadable: {exc}")
            sys.exit(1)

    df = aggregate(input_csv, Path(args.output), args.schema_version, manifest=manifest_data)

    # 汇总
    groups = len(df)
    metrics = sum(1 for c in df.columns if c not in GROUP_KEYS_V4_1 and c != "n_valid") // 5
    print(f"[DONE] {groups} groups × {metrics} metrics × 5 statistics (mean/std/median/min/max)")
    print(f"       input: {input_csv}")
    print(f"       output: {args.output}")


if __name__ == "__main__":
    main()
