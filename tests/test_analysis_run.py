"""分析层回归测试：run.py 统一编排 + CLI。"""

import inspect

import pytest
from analysis_fixtures import make_agg_csv

from scripts.analysis import run as analysis_run
from scripts.analysis.common import load_aggregated

ALL_MODULES = (
    "descriptive_analysis",
    "effect_size",
    "interaction_analysis",
    "threshold_detection",
    "benefit_phase_diagram",
    "pareto_analysis",
    "sensitivity_analysis",
)


def test_run_all_artifacts(tmp_path):
    df = load_aggregated(make_agg_csv(tmp_path))
    out = tmp_path / "out"
    charts = tmp_path / "charts"
    results = analysis_run.run_all(df, out, charts)
    assert set(results) == set(ALL_MODULES)
    # 每模块 ≥1 产物且存在
    for module, artifacts in results.items():
        assert artifacts, f"{module} 无产物"
        for path in artifacts.values():
            assert path.exists(), f"{module} 产物缺失: {path}"
    # 关键产物
    assert (out / "p_star.csv").exists()
    assert (out / "effect_size.csv").exists()
    assert (charts / "chart_phase_diagrams.png").exists()


def test_run_all_subset(tmp_path):
    df = load_aggregated(make_agg_csv(tmp_path))
    out = tmp_path / "out"
    results = analysis_run.run_all(df, out, tmp_path / "charts", modules=("effect_size",))
    assert set(results) == {"effect_size"}


def test_run_all_unknown_module(tmp_path):
    df = load_aggregated(make_agg_csv(tmp_path))
    with pytest.raises(ValueError, match="未知分析模块"):
        analysis_run.run_all(df, tmp_path / "out", tmp_path / "charts", modules=("nope",))


def test_cli_has_expected_flags():
    src = inspect.getsource(analysis_run.main)
    assert "--input" in src
    assert "--output-dir" in src
    assert "--chart-dir" in src
    assert "--modules" in src
    assert "--interpolate" in src


def test_pyproject_entry_registered():
    """cav-analyze entry 注册（Python 3.10 无 tomllib，直接读文本断言）。"""
    with open("pyproject.toml", encoding="utf-8") as f:
        src = f.read()
    assert 'cav-analyze = "scripts.analysis.run:main"' in src
