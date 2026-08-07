"""分析层回归测试：common（数据加载契约 / Δ 长表 / 档位区间表达）。

fixture：迷你 aggregated CSV——scenario_0（单车道）× 2 密度 × pCAV{0,0.5,1.0}
× {IDM, CACC}，Δ 语义已知（density=10 正收益、density=20 负收益）。
"""

import pandas as pd
import pytest

from scripts.analysis import common


def _make_agg_df():
    """构造迷你聚合 DF（10 行：IDM 2×3 + CACC 2×2，p>0 仅 CACC）。"""
    rows = []
    for vehN, dens in ((20, 10.0), (40, 20.0)):
        for p in (0.0, 0.5, 1.0):
            for model in ("IDM", "CACC"):
                if p == 0.0 and model != "IDM":
                    continue  # p=0 sentinel
                flow = 1000.0
                if model == "CACC":
                    flow = {10.0: {0.5: 1050.0, 1.0: 1020.0}, 20.0: {0.5: 980.0, 1.0: 950.0}}[dens][
                        p
                    ]
                delay = 5.0 if model == "CACC" else 8.0
                rows.append(
                    {
                        "experiment_role": "main_factorial",
                        "scenario": "scenario_0",
                        "model": model,
                        "vehN": vehN,
                        "cav_count": int(p * vehN),
                        "pCAV": p,
                        "realized_pcav": p,
                        "density_veh_per_km_lane": dens,
                        "independent_random_replication_count": 9 if p > 0 else 3,
                        "flow_mean": flow,
                        "flow_std": 100.0,
                        "flow_min": flow - 5.0,
                        "flow_max": flow + 5.0,
                        "n_valid": 9 if p > 0 else 3,
                        "delay_mean": delay,
                        "delay_std": 1.0,
                        "delay_min": delay - 0.5,
                        "delay_max": delay + 0.5,
                        "delay_count": 9 if p > 0 else 3,
                        "delay_p95_mean": delay + 2.0,
                        "delay_p95_std": 1.0,
                        "delay_p95_min": delay + 1.5,
                        "delay_p95_max": delay + 2.5,
                        "delay_p95_count": 9 if p > 0 else 3,
                        "ttc_per_k_mean": 1.0,
                        "ttc_per_k_std": 0.2,
                        "ttc_per_k_min": 0.8,
                        "ttc_per_k_max": 1.2,
                        "ttc_per_k_count": 9 if p > 0 else 3,
                        "drac_per_k_mean": 0.5,
                        "drac_per_k_std": 0.1,
                        "drac_per_k_min": 0.4,
                        "drac_per_k_max": 0.6,
                        "drac_per_k_count": 9 if p > 0 else 3,
                        "co2_per_k_mean": 200.0,
                        "co2_per_k_std": 10.0,
                        "co2_per_k_min": 190.0,
                        "co2_per_k_max": 210.0,
                        "co2_per_k_count": 9 if p > 0 else 3,
                        "fuel_per_k_mean": 60.0,
                        "fuel_per_k_std": 3.0,
                        "fuel_per_k_min": 57.0,
                        "fuel_per_k_max": 63.0,
                        "fuel_per_k_count": 9 if p > 0 else 3,
                    }
                )
    return pd.DataFrame(rows)


def _make_agg_csv(tmp_path):
    p = tmp_path / "agg.csv"
    _make_agg_df().to_csv(p, index=False)
    return str(p)


def test_load_aggregated_accepts_fixture(tmp_path):
    df = common.load_aggregated(_make_agg_csv(tmp_path))
    assert len(df) == 10
    assert set(df["model"]) == {"IDM", "CACC"}


def test_load_aggregated_rejects_unknown_model(tmp_path):
    df = _make_agg_df()
    df.loc[df.index[0], "model"] = "ACC"
    p = tmp_path / "agg.csv"
    df.to_csv(p, index=False)
    with pytest.raises(common.AnalysisInputError, match="非正式模型"):
        common.load_aggregated(p)


def test_load_aggregated_rejects_cacc_at_p0(tmp_path):
    """p=0 sentinel：CACC@p=0 无物理意义——契约破坏必须 fail-closed。"""
    df = _make_agg_df()
    bad = df.iloc[[0]].copy()
    bad["model"] = "CACC"
    df = pd.concat([df, bad], ignore_index=True)
    p = tmp_path / "agg.csv"
    df.to_csv(p, index=False)
    with pytest.raises(common.AnalysisInputError, match="p=0 sentinel"):
        common.load_aggregated(p)


def test_load_aggregated_rejects_wrong_role(tmp_path):
    df = _make_agg_df()
    df["experiment_role"] = "safety"
    p = tmp_path / "agg.csv"
    df.to_csv(p, index=False)
    with pytest.raises(common.AnalysisInputError, match="main_factorial"):
        common.load_aggregated(p)


def test_load_aggregated_missing_core_metric(tmp_path):
    df = _make_agg_df().drop(columns=["ttc_per_k_mean"])
    p = tmp_path / "agg.csv"
    df.to_csv(p, index=False)
    with pytest.raises(common.AnalysisInputError, match="主指标列"):
        common.load_aggregated(p)


def test_compute_delta_frame_signs_and_baselines(tmp_path):
    """Δ 符号方向 + baseline 双概念（model 同 p IDM / abs 纯 HV p=0）。"""
    df = common.load_aggregated(_make_agg_csv(tmp_path))
    d = common.compute_delta_frame(df)
    assert len(d) == 4  # 2 density × 2 pCAV>0
    # (density=10, p=0.5)：CACC flow=1050 > IDM 1000 → Δq_model = +50
    row = d[(d["density_veh_per_km_lane"] == 10.0) & (d["pCAV"] == 0.5)].iloc[0]
    assert row["flow_model_delta"] == pytest.approx(50.0)
    assert row["flow_abs_delta"] == pytest.approx(50.0)  # IDM p=0.5 == HV p=0（flow 恒 1000）
    # (density=20, p=1.0)：CACC 950 < IDM 1000 → Δq_model = -50（反转）
    row = d[(d["density_veh_per_km_lane"] == 20.0) & (d["pCAV"] == 1.0)].iloc[0]
    assert row["flow_model_delta"] == pytest.approx(-50.0)
    # delay 方向相反：CACC delay=5 < IDM 8 → Δdelay = +3（收益）
    assert d["delay_model_delta"].min() == pytest.approx(3.0)
    # per-lane 派生：scenario_0 单车道 → 与 total 相等
    assert d["flow_per_lane_model_delta"].equals(d["flow_model_delta"])


def test_compute_delta_frame_consistency(tmp_path):
    """跨 seed 全范围一致性三态：density=10 全正 → gain；density=20 全负 → reversal。"""
    df = common.load_aggregated(_make_agg_csv(tmp_path))
    d = common.compute_delta_frame(df)
    g = d[d["density_veh_per_km_lane"] == 10.0]
    assert (g["flow_model_consistent"] == "gain").all()
    r = d[d["density_veh_per_km_lane"] == 20.0]
    assert (r["flow_model_consistent"] == "reversal").all()


def test_compute_delta_frame_missing_hv_reference(tmp_path):
    """缺 p=0 纯 HV reference 行 → fail-closed。"""
    df = _make_agg_df()
    df = df[df["pCAV"] != 0.0]
    p = tmp_path / "agg.csv"
    df.to_csv(p, index=False)
    with pytest.raises(common.AnalysisInputError, match="纯 HV reference"):
        common.compute_delta_frame(df)


def test_p_star_interval():
    assert common.p_star_interval(0.5, 0.6) == "(0.5, 0.6]"
    # 一位小数一致化（档位 0.1 步长）
    assert common.p_star_interval(0.5, 1.0) == "(0.5, 1.0]"
    # 边界外无交叉时的语义表达
    assert common.format_p_star(0.0, 0.1) == "(0.0, 0.1]"
    assert common.format_p_star(None, None) == ""
