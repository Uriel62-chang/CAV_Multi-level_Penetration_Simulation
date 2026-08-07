"""分析层回归测试：effect_size（效应量）+ interaction_analysis（交互分解）。"""

import numpy as np
import pandas as pd
import pytest
from analysis_fixtures import make_agg_csv, make_agg_df

from scripts.analysis import effect_size, interaction_analysis
from scripts.analysis.common import compute_delta_frame, load_aggregated

# ── effect_size ──


def test_cohens_d_basic():
    # d = Δ / s_pooled；s_pooled = sqrt(((n1-1)s1²+(n2-1)s2²)/(n1+n2-2))
    d = effect_size.cohens_d(delta=10.0, s_cacc=10.0, s_base=10.0, n_cacc=9, n_base=9)
    assert d == pytest.approx(10.0 / 10.0)
    # Δ=0 → d=0
    assert effect_size.cohens_d(0.0, 5.0, 5.0, 9, 9) == 0.0
    # R13-P2-①：双组零方差（复现完全确定性）→ d 数学未定义 → NaN（非 0/negligible）
    assert np.isnan(effect_size.cohens_d(5.0, 0.0, 0.0, 9, 9))
    # 单组零方差仍可计算（s_pooled > 0）
    assert np.isfinite(effect_size.cohens_d(5.0, 0.0, 10.0, 9, 9))


def test_compute_effect_sizes_deterministic_flag(tmp_path):
    """R13-P2-① 回归：确定性档（双组零方差）d=NaN + d_deterministic=True +
    d_label 空；非确定性档正常。fixture 中 flow_std 恒 100 → 全为非确定性，
    人为置零一档验证标注。"""
    df = load_aggregated(make_agg_csv(tmp_path))
    # 人为构造确定性档：density=10 p=0.5 的 CACC 与 IDM 行 flow_std 置 0
    mask = (df["density_veh_per_km_lane"] == 10.0) & (df["pCAV"] == 0.5)
    df.loc[mask, "flow_std"] = 0.0
    es = effect_size.compute_effect_sizes(df)
    row = es[(es["density_veh_per_km_lane"] == 10.0) & (es["pCAV"] == 0.5)].iloc[0]
    assert np.isnan(row["flow_model_d"])
    assert bool(row["flow_model_d_deterministic"])
    assert row["flow_model_d_label"] == ""
    # 其他档不受影响（非确定性）
    other = es[(es["density_veh_per_km_lane"] == 20.0) & (es["pCAV"] == 1.0)].iloc[0]
    assert not bool(other["flow_model_d_deterministic"])
    assert other["flow_model_d_label"] != ""


def test_interpret_d_thresholds():
    assert effect_size.interpret_d(0.0) == "negligible"
    assert effect_size.interpret_d(0.19) == "negligible"
    assert effect_size.interpret_d(0.2) == "small"
    assert effect_size.interpret_d(0.5) == "medium"
    assert effect_size.interpret_d(1.5) == "large"


def test_compute_effect_sizes(tmp_path):
    df = load_aggregated(make_agg_csv(tmp_path))
    es = effect_size.compute_effect_sizes(df)
    assert len(es) == 4  # 2 density × 2 pCAV>0
    # (density=10, p=0.5)：Δq=+50，d>0
    row = es[(es["density_veh_per_km_lane"] == 10.0) & (es["pCAV"] == 0.5)].iloc[0]
    assert row["flow_model_delta"] == pytest.approx(50.0)
    assert row["flow_model_d"] > 0
    # (density=20, p=1.0)：Δq=-50，d<0（反转）
    row = es[(es["density_veh_per_km_lane"] == 20.0) & (es["pCAV"] == 1.0)].iloc[0]
    assert row["flow_model_d"] < 0
    # 双 baseline 均输出
    assert "flow_abs_delta" in es.columns
    assert "flow_abs_d" in es.columns


def test_effect_size_missing_row_raises():
    """同渗透率 IDM 行缺失 → compute_delta_frame fail-closed（不静默跳过）。"""
    from scripts.analysis.common import AnalysisInputError

    df = make_agg_df()
    df = df[~((df["model"] == "IDM") & (df["pCAV"] == 1.0))]  # 删 IDM p=1.0，CACC p=1.0 保留
    with pytest.raises(AnalysisInputError, match="缺同渗透率 IDM 行"):
        effect_size.compute_effect_sizes(df)


# ── interaction_analysis ──


def test_interaction_decomposition_terms(tmp_path):
    df = load_aggregated(make_agg_csv(tmp_path))
    d = compute_delta_frame(df)
    dec = interaction_analysis.compute_interaction_decomposition(d)
    terms = set(dec["term"])
    assert {
        "model×scenario",
        "model×density",
        "pCAV×density",
        "pCAV×density_slope",
        "model×scenario×density",
    } <= terms
    # model×scenario：单场景 → 均值 = Δ 均值
    ms = dec[dec["term"] == "model×scenario"]
    assert len(ms) == 1
    assert ms.iloc[0]["value"] == pytest.approx(d["flow_per_lane_model_delta"].mean())
    # model×density：每 p 一行（2 个 p）
    md = dec[dec["term"] == "model×density"]
    assert len(md) == 2
    # 三阶：每 p 一行
    three = dec[dec["term"] == "model×scenario×density"]
    assert len(three) == 2


def test_interaction_slope_sign(tmp_path):
    """density=20 反转 → model×density 斜率应为负（优势随密度下降）。"""
    df = load_aggregated(make_agg_csv(tmp_path))
    d = compute_delta_frame(df)
    dec = interaction_analysis.compute_interaction_decomposition(d)
    md = dec[dec["term"] == "model×density"]
    assert (md["value"] < 0).all()


def test_interaction_missing_delta_col():
    d = pd.DataFrame({"pCAV": [0.5]})
    with pytest.raises(ValueError, match="flow_per_lane_model_delta"):
        interaction_analysis.compute_interaction_decomposition(d)
