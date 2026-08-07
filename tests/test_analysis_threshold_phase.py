"""分析层回归测试：threshold_detection（p*/k* 档位区间）+ benefit_phase_diagram。"""

import numpy as np
import pandas as pd
import pytest
from analysis_fixtures import make_agg_csv

from scripts.analysis import benefit_phase_diagram as bpd
from scripts.analysis import threshold_detection as td
from scripts.analysis.common import compute_delta_frame, load_aggregated

# ── threshold_detection ──


def test_crossing_directions():
    # 负→正（收益出现）
    assert td._crossing([0.1, 0.2, 0.3], [-1.0, 0.0, 1.0], neg_to_pos=True) == (0.2, 0.3)
    # 正→负（反转）
    assert td._crossing([0.1, 0.2, 0.3], [1.0, 0.0, -1.0], neg_to_pos=False) == (0.1, 0.2)
    # 无交叉
    assert td._crossing([0.1, 0.2], [1.0, 2.0], neg_to_pos=True) is None
    # Δ=0 归负侧：0→+1 是负→正
    assert td._crossing([0.1, 0.2], [0.0, 1.0], neg_to_pos=True) == (0.1, 0.2)


def test_detect_p_star_fixture(tmp_path):
    """fixture 语义：density=10 首档已正 → p*≤0.1；density=20 全负 → 无正收益。"""
    df = load_aggregated(make_agg_csv(tmp_path))
    d = compute_delta_frame(df)
    ps = td.detect_p_star(d)
    assert len(ps) == 2  # 2 density
    r10 = ps[ps["density_veh_per_km_lane"] == 10.0].iloc[0]
    assert r10["p_star"] == "p* ≤ 0.1"
    assert r10["status"] == "gain"
    r20 = ps[ps["density_veh_per_km_lane"] == 20.0].iloc[0]
    assert "no gain" in r20["p_star"]
    assert r20["status"] == "no_crossing"


def test_detect_p_star_interpolate(tmp_path):
    """--interpolate：插值细值输出并标注估计。"""
    df = load_aggregated(make_agg_csv(tmp_path))
    d = compute_delta_frame(df)
    # 人为构造负→正交叉：density=10 把 p=0.5 改为负收益
    d.loc[
        (d["density_veh_per_km_lane"] == 10.0) & (d["pCAV"] == 0.5), "flow_per_lane_model_delta"
    ] = -1.0
    ps = td.detect_p_star(d, interpolate=True)
    r = ps[ps["density_veh_per_km_lane"] == 10.0].iloc[0]
    assert r["p_star"] == "(0.5, 1.0]"
    assert np.isfinite(r["p_star_interpolated"])
    assert "估计" in r["p_star_interpolated_note"]


def test_detect_k_star_fixture(tmp_path):
    """k*：p=0.5 与 p=1.0 均在 density 10→20 之间反转 → k* ∈ (10, 20]。"""
    df = load_aggregated(make_agg_csv(tmp_path))
    d = compute_delta_frame(df)
    ks = td.detect_k_star(d)
    assert len(ks) == 2
    assert (ks["k_star"] == "(10.0, 20.0]").all()
    assert (ks["k_star_status"] == "reversal_in_range").all()


def test_analyze_threshold_writes(tmp_path):
    df = load_aggregated(make_agg_csv(tmp_path))
    out = tmp_path / "out"
    paths = td.analyze(df, out)
    assert paths["p_star"].exists()
    assert paths["k_star"].exists()
    assert len(pd.read_csv(paths["p_star"])) == 2


# ── benefit_phase_diagram ──


def test_surface_matrix(tmp_path):
    df = load_aggregated(make_agg_csv(tmp_path))
    d = compute_delta_frame(df)
    dens, ps, mat = bpd.surface_matrix(d, "scenario_0", bpd.MODEL_DELTA_COL)
    assert list(dens) == [10.0, 20.0]
    assert list(ps) == [0.5, 1.0]
    assert mat.shape == (2, 2)
    # (density=10, p=0.5) 正收益
    assert mat[0, 0] == pytest.approx(50.0)
    # (density=20, p=1.0) 反转
    assert mat[1, 1] == pytest.approx(-50.0)


def test_surface_matrix_unknown_scenario(tmp_path):
    df = load_aggregated(make_agg_csv(tmp_path))
    d = compute_delta_frame(df)
    with pytest.raises(ValueError, match="scenario_X"):
        bpd.surface_matrix(d, "scenario_X", bpd.MODEL_DELTA_COL)


def test_chart_phase_diagrams_generates(tmp_path):
    df = load_aggregated(make_agg_csv(tmp_path))
    d = compute_delta_frame(df)
    out = tmp_path / "charts"
    path = bpd.chart_phase_diagrams(d, out)
    assert path.exists()
    assert path.stat().st_size > 10_000  # 非空 PNG
