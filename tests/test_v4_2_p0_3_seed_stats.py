"""v0.4.2 P0-3 回归测试：双 seed 统计单位。"""

import pandas as pd
import pytest

from scripts.results.aggregate import aggregate


def _make_df(n_assign: int, n_sumo: int) -> pd.DataFrame:
    """构造 (scenario, model, vehN, cav_count) 固定格，n_assign × n_sumo 组合。"""
    rows = []
    for a in range(n_assign):
        for s in range(n_sumo):
            rows.append(
                {
                    "scenario": "s0",
                    "model": "IDM",
                    "requested_pcav": None,
                    "realized_pcav": 0.5,
                    "cav_count": 5,
                    "hv_count": 5,
                    "vehN": 10,
                    "assignment_seed": a,
                    "sumo_seed": 101 + s,
                    "run_id": f"r{a}_{s}",
                    "mean_flow_veh_h": 100.0 + a + s,
                    "data_quality": "ok",
                }
            )
    return pd.DataFrame(rows)


def _aggregate(df: pd.DataFrame, tmp_path):
    in_csv = tmp_path / "in.csv"
    out_csv = tmp_path / "out.csv"
    df.to_csv(in_csv, index=False)
    manifest = {
        "treatments": [
            {
                "vehicle_count": int(df["vehN"].iloc[0]),
                "cav_counts": [int(df["cav_count"].iloc[0])],
                "assignment_seeds": sorted(int(x) for x in df["assignment_seed"].unique()),
            }
        ],
        "sumo_seeds": sorted(int(x) for x in df["sumo_seed"].unique()),
        "results": [{"run_id": r} for r in sorted(df["run_id"])],
    }
    return aggregate(in_csv, out_csv, "2", manifest=manifest)


def test_interior_seed_pair_stats(tmp_path):
    """3×3 内部格：3 assignment levels、3 sumo levels、9 combos、有效 n=9。"""
    out = _aggregate(_make_df(3, 3), tmp_path)
    row = out.iloc[0]
    assert row["assignment_seed_level_count"] == 3
    assert row["sumo_seed_level_count"] == 3
    assert row["seed_pair_combination_count"] == 9
    assert row["assignment_seed_run_count"] == 9
    assert row["sumo_seed_run_count"] == 3
    # 收敛审核 P2：双 seed 统计单位下独立随机复现数 = 有效 (assignment, sumo) 组合数
    assert row["independent_random_replication_count"] == 9
    assert row["n_valid"] == 9


def test_flow_per_lane_column(tmp_path):
    """收敛审核 P0（FD 口径）：flow_per_lane = flow_mean / 场景车道数——
    单车道（s0/s1）为 1 倍、双车道（scenario_2/scenario_3）为 1/2。"""
    out_single = _aggregate(_make_df(3, 3), tmp_path)  # scenario="s0"（单车道）
    row = out_single.iloc[0]
    assert abs(row["flow_per_lane"] - row["flow_mean"]) < 1e-9
    df_dual = _make_df(3, 3).assign(scenario="scenario_2")  # 双车道
    out_dual = _aggregate(df_dual, tmp_path)
    row2 = out_dual.iloc[0]
    assert abs(row2["flow_per_lane"] - row2["flow_mean"] / 2) < 1e-9
    assert row2["flow_per_lane"] < row2["flow_mean"]


def test_flow_per_lane_absent_on_old_csv_visualization_fallback():
    """收敛审核 P0：旧聚合 CSV 无 flow_per_lane 时可视化回退 flow_mean（不抛错）。"""
    from scripts.results.visualization import _flow_metric_column

    df_old = pd.DataFrame({"flow_mean": [1.0]})
    df_new = pd.DataFrame({"flow_mean": [1.0], "flow_per_lane": [0.5]})
    assert _flow_metric_column(df_old) == "flow_mean"
    assert _flow_metric_column(df_new) == "flow_per_lane"


def test_endpoint_seed_stats(tmp_path):
    """端点（cav=0 或 cav=vehN）：assignment 失活为 1 水平，sumo seed 仍活动。"""
    out = _aggregate(_make_df(1, 3), tmp_path)
    row = out.iloc[0]
    assert row["assignment_seed_level_count"] == 1
    assert row["sumo_seed_level_count"] == 3
    assert row["seed_pair_combination_count"] == 3
    assert row["assignment_seed_run_count"] == 3  # 3 个 sumo 组合，不是 3 个 assignment run
    assert row["sumo_seed_run_count"] == 3


def test_schema2_missing_seed_column_fails_closed(tmp_path):
    """P0-7：schema=2 缺 assignment_seed/sumo_seed 列必须拒绝，不得静默退回旧统计。"""
    df = _make_df(2, 2).drop(columns=["sumo_seed"])
    in_csv = tmp_path / "in.csv"
    out_csv = tmp_path / "out.csv"
    df.to_csv(in_csv, index=False)
    manifest = {
        "treatments": [{"vehicle_count": 10, "cav_counts": [5], "assignment_seeds": [0, 1]}],
        "sumo_seeds": [101, 102],
        "results": [{"run_id": r} for r in sorted(df["run_id"])],
    }
    with pytest.raises(ValueError, match="sumo_seed"):
        aggregate(in_csv, out_csv, "2", manifest=manifest)


def test_duplicate_seed_pair_rejected(tmp_path):
    """同一 (assignment, sumo) 组合重复出现 → 拒绝。"""
    df = _make_df(2, 2)
    df.loc[3, "sumo_seed"] = 101  # 与 row0 重复 (0, 101)
    with pytest.raises(ValueError, match="duplicate"):
        _aggregate(df, tmp_path)
