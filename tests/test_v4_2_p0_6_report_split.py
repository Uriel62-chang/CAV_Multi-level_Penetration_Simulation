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
    assert "chart_delay.png" in files
    assert len(files) == 3


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


def test_safety_config_expands_to_84(tmp_path):
    """P0-11：v0.4.2 safety 配置展开为 4×3×7=84 runs。"""
    from scripts.experiment_config import load_experiment_config
    from scripts.simulation.batch_run import build_run_specs

    cfg = load_experiment_config("configs/v0.4.2/safety.json")
    specs = build_run_specs(
        scenarios=list(cfg.scenarios),
        models=list(cfg.models),
        treatments=[dict(t) for t in cfg.treatments],
        sumo_seeds=list(cfg.sumo_seeds),
        simulation_end=cfg.simulation_end,
        warmup=cfg.warmup,
        step_length=cfg.step_length,
        detector_frequency=cfg.detector_frequency,
        edge_data_frequency=cfg.edge_data_frequency,
        loops=cfg.loops,
        network_files=dict(cfg.network_files),
        seed_scope=cfg.seed_scope,
        pipeline_version=cfg.pipeline_version,
        schema_version=cfg.schema_version,
        config_sha256=cfg.sha256(),
        network_sha256={},
        experiment_id=cfg.sha256(),
        ssm_capture_ttc_threshold_s=cfg.ssm_capture_ttc_threshold_s,
        ssm_capture_drac_threshold_mps2=cfg.ssm_capture_drac_threshold_mps2,
        ssm_range_m=cfg.ssm_range_m,
        ssm_trajectories=cfg.ssm_trajectories,
        ssm_extratime_s=cfg.ssm_extratime_s,
        fcd_profile=cfg.fcd_profile,
        fcd_max_leader_distance_m=cfg.fcd_max_leader_distance_m,
        with_internal=cfg.with_internal,
        experiment_role=cfg.experiment_role,
        ssm_enabled=cfg.ssm_enabled,
        analysis_ttc_threshold_s=cfg.analysis_ttc_threshold_s,
        analysis_drac_threshold_mps2=cfg.analysis_drac_threshold_mps2,
        ssm_dedup_method=cfg.ssm_dedup_method,
        ssm_mirror_overlap_ratio=cfg.ssm_mirror_overlap_ratio,
        ssm_fragment_merge_gap_s=cfg.ssm_fragment_merge_gap_s,
    )
    assert len(specs) == 84
    assert all(s.experiment_role == "safety" for s in specs)
    assert all(s.ssm_enabled for s in specs)
    # p 档位与 vehN 组合验证
    per_vehn = {vn: set() for vn in (30, 60, 120)}
    for s in specs:
        per_vehn[s.vehicle_count].add(s.cav_count / s.vehicle_count)
    for vn, levels in per_vehn.items():
        assert levels == {0.0, 0.2, 0.6, 1.0}, f"vehN={vn}: {levels}"


def test_safety_report_generates_events_chart(tmp_path, monkeypatch):
    """P0-11：safety 报告生成事件率随渗透率图，无 trade-off；用空间配对列。"""
    import argparse

    from scripts.results import visualization as viz

    df = pd.DataFrame(
        {
            "scenario": ["scenario_0", "scenario_0"],
            "model": ["IDM", "CACC"],
            "requested_pcav": [None, None],
            "realized_pcav": [0.2, 0.6],
            "pCAV": [0.2, 0.6],
            "vehN": [60, 60],
            "cav_count": [12, 36],
            "ttc_per_k_mean": [0.5, 1.2],
            "drac_per_k_mean": [0.1, 0.3],
        }
    )
    p = tmp_path / "agg.csv"
    df.to_csv(p, index=False)
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(viz.plt, "show", lambda: None)
    viz.run_safety_v4_2(argparse.Namespace(aggregated=str(p), outDir=str(out)))
    files = sorted(x.name for x in out.iterdir())
    assert "chart_safety_events_by_penetration.png" in files
    assert "chart_safety_drac_by_penetration.png" in files  # 审阅 P0-1：DRAC 图
    assert "chart_safety_flow.png" not in files
    # P1-3：曲线必须基于非空数据渲染（scenario_0 两模型行），PNG 非空
    png = out / "chart_safety_events_by_penetration.png"
    assert png.stat().st_size > 1000, f"safety chart unexpectedly small: {png.stat().st_size}"


def test_safety_plot_separates_vehn(tmp_path, monkeypatch):
    """P0（Reviewer 复检）：同一渗透率下不同 vehN 的点不得连成一条响应曲线。

    修复前每场景仅按 model 分线，同一 x 出现竖线并混合 vehN 点；
    修复后按 scenario × vehN 分面，每条线的 x 值必须唯一（无竖线）。
    """
    import numpy as np

    from scripts.results import visualization as viz

    calls = []

    class FakeAx:
        def plot(self, x, y, **kw):
            calls.append((list(x), list(y), kw.get("label")))
            self._plotted = True

        def get_legend_handles_labels(self):
            # 仅已绘制曲线的面返回 handle（对应实现的条件 legend）
            return (["h"] if getattr(self, "_plotted", False) else []), []

        def set_xlabel(self, *a, **k):
            pass

        def set_ylabel(self, *a, **k):
            pass

        def set_title(self, *a, **k):
            pass

        def legend(self, *a, **k):
            pass

    class FakeFig:
        def savefig(self, *a, **k):
            pass

        def close(self):
            pass

    def fake_subplots(nrows, ncols, **kw):
        return FakeFig(), np.array([[FakeAx() for _ in range(ncols)] for _ in range(nrows)])

    monkeypatch.setattr(viz.plt, "subplots", fake_subplots)
    monkeypatch.setattr(viz.plt, "close", lambda fig: None)

    # scenario_0：vehN=30 与 vehN=60 在相同渗透率 0.2 下不同 TTC 值
    df = pd.DataFrame(
        {
            "scenario": ["scenario_0"] * 4,
            "model": ["IDM", "CACC", "IDM", "CACC"],
            "requested_pcav": [None] * 4,
            "realized_pcav": [0.2, 0.2, 0.2, 0.2],
            "pCAV": [0.2] * 4,
            "vehN": [30, 30, 60, 60],
            "cav_count": [6, 6, 12, 12],
            "ttc_per_k_mean": [0.5, 0.8, 1.2, 1.5],
            "drac_per_k_mean": [0.1, 0.2, 0.3, 0.4],
        }
    )
    p = tmp_path / "agg.csv"
    df.to_csv(p, index=False)
    out = tmp_path / "out"
    out.mkdir()
    viz.run_safety_v4_2(argparse.Namespace(aggregated=str(p), outDir=str(out)))

    # scenario_0 有 2 个 vehN × 2 model = 4 条线 × 2 指标（TTC + DRAC 图，审阅 P0-1）
    assert len(calls) == 8, f"expected 8 plot calls (TTC+DRAC), got {len(calls)}"
    for x, y, label in calls:
        assert len(x) == len(set(x)), f"vertical line (duplicate x) for {label}: {x}"
        # 每条线只含单一 vehN 的数据（修复前 0.5 与 1.2 会在同一条线）
        assert len(y) == 1, f"mixed vehN points in one line for {label}: {y}"


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


def test_safety_cli_help_mentions_ttc_and_drac():
    """审阅 P0-1 残留 P2：--safety help 不得再声称"仅 TTC"。"""
    import inspect

    from scripts.results.visualization import main as viz_main

    src = inspect.getsource(viz_main)
    assert "TTC + DRAC" in src, "safety CLI help must mention both TTC and DRAC"
    assert "仅 TTC" not in src, "stale 'TTC-only' claim in CLI help"
