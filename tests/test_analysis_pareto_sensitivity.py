"""分析层回归测试：pareto_analysis（四维 front）+ sensitivity_analysis。"""

import numpy as np
import pandas as pd
import pytest
from analysis_fixtures import make_agg_csv

from scripts.analysis import pareto_analysis as pa
from scripts.analysis import sensitivity_analysis as sa
from scripts.analysis.common import compute_delta_frame, load_aggregated

# ── pareto_analysis ──


def test_dominates_basic():
    dims = ["flow", "delay"]
    directions = ["max", "min"]
    a = np.array([100.0, 5.0])  # 更高 flow、更低 delay
    b = np.array([90.0, 8.0])
    assert pa._dominates(a, b, dims, directions)
    assert not pa._dominates(b, a, dims, directions)
    # 平局（所有维度相等）不支配
    assert not pa._dominates(a, a, dims, directions)
    # 一维更优一维更差 → 不支配
    c = np.array([110.0, 9.0])
    assert not pa._dominates(a, c, dims, directions)
    assert not pa._dominates(c, a, dims, directions)
    # NaN 保守：不判定支配
    assert not pa._dominates(a, np.array([np.nan, 8.0]), dims, directions)


def test_pareto_front_fixture(tmp_path):
    """fixture：IDM 恒 flow=1000/delay=8；CACC delay 恒 5（更低=更优）但 flow 随
    (density, p) 变化——flow 更高且 delay 更低的 CACC 点应支配同密度 IDM 点。"""
    df = load_aggregated(make_agg_csv(tmp_path))
    front = pa.compute_pareto_front(df)
    assert len(front) == 10
    # 每个 density 内：CACC (p=0.5, flow=1050, delay=5) 支配 IDM 同密度所有行
    f10 = front[(front["density_veh_per_km_lane"] == 10.0)]
    cacc05 = f10[(f10["model"] == "CACC") & (f10["pCAV"] == 0.5)].iloc[0]
    assert cacc05["is_front"]
    idm10 = f10[(f10["model"] == "IDM") & (f10["pCAV"] == 0.0)].iloc[0]
    assert not idm10["is_front"]
    # density=20：CACC flow 更低（980/950）但 delay 更低 → 与 IDM 互不支配
    f20 = front[front["density_veh_per_km_lane"] == 20.0]
    idm20 = f20[(f20["model"] == "IDM") & (f20["pCAV"] == 0.0)].iloc[0]
    assert idm20["is_front"]  # 低流量高 delay 不被 CACC 支配（delay 维度 CACC 更优但 flow 更差）
    cacc20 = f20[(f20["model"] == "CACC") & (f20["pCAV"] == 0.5)].iloc[0]
    assert cacc20["is_front"]


def test_pareto_all_nan_dimension_warns(tmp_path, capsys):
    df = load_aggregated(make_agg_csv(tmp_path))
    df["ttc_per_k_mean"] = np.nan
    front = pa.compute_pareto_front(df)
    assert "ttc_per_k" not in front["pareto_dims"].iloc[0].split("+")  # 全 NaN 维度被剔除
    assert "flow" in front["pareto_dims"].iloc[0].split("+")
    out = capsys.readouterr().out
    assert "全 NaN" in out


def test_pareto_no_dims_raises(tmp_path):
    df = load_aggregated(make_agg_csv(tmp_path))
    for c in ("flow", "delay", "ttc_per_k", "co2_per_k"):
        df[f"{c}_mean"] = np.nan
    with pytest.raises(pa.AnalysisInputError, match="无可用维度"):
        pa.compute_pareto_front(df)


def test_pareto_summary(tmp_path):
    df = load_aggregated(make_agg_csv(tmp_path))
    front = pa.compute_pareto_front(df)
    summary = pa.compute_pareto_summary(front)
    assert len(summary) == 1  # 单场景
    assert summary.iloc[0]["total_candidates"] == 10
    assert summary.iloc[0]["front_size"] == front["is_front"].sum()


# ── sensitivity_analysis ──


def test_column_sensitivity_flow_scale(tmp_path):
    """flow total vs per-lane：单车道下 Δ 恒等 → p* 一致（稳健性检验核心）。"""
    df = load_aggregated(make_agg_csv(tmp_path))
    d = compute_delta_frame(df)
    sens = sa.compute_column_sensitivity(d)
    flow_rows = sens[sens["pair"].str.startswith("flow")]
    assert len(flow_rows) == 2
    assert (flow_rows["p_star_unchanged"]).all()
    assert flow_rows["max_abs_delta_diff"].abs().max() == 0.0  # 单车道下 total==per-lane


def test_column_sensitivity_delay_alt(tmp_path):
    df = load_aggregated(make_agg_csv(tmp_path))
    d = compute_delta_frame(df)
    sens = sa.compute_column_sensitivity(d)
    delay_rows = sens[sens["pair"].str.startswith("delay")]
    # delay 恒收益（CACC 5 < IDM 8）→ 两口径均无交叉 → unchanged
    assert (delay_rows["p_star_unchanged"]).all()
    assert delay_rows["p_star_base"].iloc[0] == "none"


def test_threshold_stability(tmp_path):
    df = load_aggregated(make_agg_csv(tmp_path))
    d = compute_delta_frame(df)
    stab = sa.compute_threshold_stability(d)
    assert len(stab) == 1
    row = stab.iloc[0]
    assert row["n_density_levels"] == 2
    assert row["p_star_jumps_across_density"] == 0  # 两 density 均无负→正交叉
    # R15-P2-1 物理单位回归：fixture Δ 矩阵 [[50,20],[-20,-50]]（density 步长
    # 10、p 步长 0.5）→ |∂Δ/∂k| = |(-20-50)/10| = 7.0、|∂Δ/∂p| = |(20-50)/0.5| = 60。
    # 若 np.gradient 回退到索引间距（步长 1），此断言即失败（70/60 → 值不同）。
    assert row["max_grad_density"] == pytest.approx(7.0)
    assert row["max_grad_pcav"] == pytest.approx(60.0)


def test_sensitivity_missing_delta_col():
    """无任何 Δ 列 → 全部替代对跳过，返回空 DataFrame（不崩溃）。"""
    d = pd.DataFrame(
        {
            "scenario": ["scenario_0", "scenario_0"],
            "density_veh_per_km_lane": [10.0, 10.0],
            "pCAV": [0.5, 1.0],
        }
    )
    out = sa.compute_column_sensitivity(d)
    assert len(out) == 0
