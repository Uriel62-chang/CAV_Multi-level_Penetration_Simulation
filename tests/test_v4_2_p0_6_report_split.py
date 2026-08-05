"""v0.4.2 P0-6 回归测试：main/safety 报告分离。"""

import argparse

import pandas as pd


def _make_agg(tmp_path):
    df = pd.DataFrame(
        {
            "scenario": ["scenario_0", "scenario_0"],
            "model": ["IDM", "CACC"],
            "requested_pcav": [None, None],
            "realized_pcav": [0.5, 0.5],
            "pCAV": [0.5, 0.5],
            "vehN": [60, 60],
            "cav_count": [30, 30],
            "flow_mean": [1000.0, 1100.0],
            "flow_per_lane": [1000.0, 1100.0],
            "density_veh_per_km_lane": [30.0, 30.0],
            "co2_per_k_mean": [200.0, 190.0],
            "delay_mean": [10.0, 8.0],
            "ttc_per_k_mean": [0.1, 0.2],
        }
    )
    p = tmp_path / "agg.csv"
    df.to_csv(p, index=False)
    return str(p)


def test_run_v4_2_no_safety_flow_chart(tmp_path, monkeypatch):
    from scripts.results import visualization as viz

    agg = _make_agg(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    args = argparse.Namespace(aggregated=agg, outDir=str(out))
    # 避免 plt 需要 display
    monkeypatch.setattr(viz.plt, "show", lambda: None)
    viz.run_v4_2(args)
    files = sorted(p.name for p in out.iterdir())
    assert "chart_safety_flow.png" not in files
    assert "chart_capacity.png" in files
    assert "chart_co2_flow.png" in files
    assert "chart_fundamental_diagram.png" in files
    assert "chart_fundamental_diagram_s3.png" in files
    assert "chart_delay.png" in files
    assert len(files) == 5


def test_penetration_column_prefers_realized(tmp_path):
    from scripts.results.visualization import _penetration_column

    df = pd.DataFrame({"realized_pcav": [0.5], "requested_pcav": [None]})
    assert _penetration_column(df) == "realized_pcav"


def test_cli_has_v4_2_flag():
    # 仅验证 CLI 参数存在（不实际运行）
    import inspect

    from scripts.results.visualization import main as viz_main

    src = inspect.getsource(viz_main)
    assert "--v4-2" in src
    assert "run_v4_2" in src


def test_ttc_metric_column_prefers_paired(tmp_path):
    """P0-3：配对列存在时优先 ttc_per_k_mean，不选旧 non-internal 错配列。"""
    from scripts.results.visualization import _ttc_metric_column

    df = pd.DataFrame(
        {
            "ttc_per_k_mean": [1.0],
            "whole_network_ttc_events_per_1000_non_internal_edge_veh_km_mean": [9.9],
        }
    )
    assert _ttc_metric_column(df) == "ttc_per_k_mean"


def test_ttc_metric_column_rejects_mismatched(tmp_path):
    """纯净分支：仅 legacy 错配列（post3 口径）时 fail-closed——head 一律用
    空间配对列，不回退错误口径（历史 post3 CSV 展示走 v0.4.0.post3 tag）。"""
    import pytest

    from scripts.results.visualization import _ttc_metric_column

    df = pd.DataFrame({"whole_network_ttc_events_per_1000_non_internal_edge_veh_km_mean": [9.9]})
    with pytest.raises(ValueError, match="ttc_per_k_mean"):
        _ttc_metric_column(df)


def test_ttc_metric_column_missing_raises(tmp_path):
    """P0-3：无任何 TTC 列时 fail-closed。"""
    import pytest

    from scripts.results.visualization import _ttc_metric_column

    df = pd.DataFrame({"flow_mean": [1.0]})
    with pytest.raises(ValueError):
        _ttc_metric_column(df)
