"""分析层模块 1/7：描述统计增强（替代原 mixed_effects 的分层描述角色）。

产出：
- `descriptive_deltas.csv`：Δ 长表——每 (scenario, density, pCAV>0) 相对两个
  baseline（同 p IDM / 纯 HV）的 Δ 指标族 + 描述性区间 + 跨 seed 一致性；
- `descriptive_summary.csv`：分组描述统计（scenario × density × model × pCAV
  的 mean/std/min/max/n 长表）。

纯函数 + analyze() 编排；`python3 -m scripts.analysis.descriptive_analysis`
可独立运行（调试/单模块产出）。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from scripts.analysis.common import (
    AnalysisInputError,
    available_specs,
    compute_delta_frame,
    ensure_dir,
    load_aggregated,
    write_csv,
)

DEFAULT_OUTPUT = "out/analysis/descriptive"


def compute_descriptive_summary(df: pd.DataFrame) -> pd.DataFrame:
    """分组描述统计长表（分层描述：scenario × density × model × pCAV × metric）。"""
    rows = []
    for spec in available_specs(df):
        col = spec.column
        count_col = "n_valid" if col == "flow" else f"{col}_count"
        sub = df[["scenario", "density_veh_per_km_lane", "model", "pCAV", "realized_pcav"]].copy()
        sub["metric"] = spec.column
        sub["metric_label"] = spec.label
        sub["value_mean"] = df[col + "_mean"]
        sub["value_std"] = df[col + "_std"]
        sub["value_min"] = df[col + "_min"]
        sub["value_max"] = df[col + "_max"]
        sub["n"] = df[count_col]
        rows.append(sub)
    out = pd.concat(rows, ignore_index=True)
    out = out.sort_values(
        ["scenario", "density_veh_per_km_lane", "model", "pCAV", "metric"]
    ).reset_index(drop=True)
    return out


def analyze(df: pd.DataFrame, output_dir: str | Path) -> dict[str, Path]:
    """运行描述统计增强，写出 CSV；返回 {名称: 路径}。"""
    out = ensure_dir(output_dir)
    if set(df["model"]) != {"IDM", "CACC"}:
        raise AnalysisInputError(
            f"描述统计需要 IDM+CACC 双模型网格，实际模型集: {sorted(set(df['model']))}"
        )
    deltas = compute_delta_frame(df)
    paths = {
        "descriptive_deltas": write_csv(
            deltas, out / "descriptive_deltas.csv", "descriptive deltas"
        ),
        "descriptive_summary": write_csv(
            compute_descriptive_summary(df), out / "descriptive_summary.csv", "descriptive summary"
        ),
    }
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="v0.4.2 分析层：描述统计增强")
    parser.add_argument("--input", default="out/aggregated_results.csv", help="aggregated CSV")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT, help="CSV 输出目录")
    args = parser.parse_args()
    analyze(load_aggregated(args.input), args.output_dir)


if __name__ == "__main__":
    main()
