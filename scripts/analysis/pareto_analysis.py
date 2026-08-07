"""分析层模块 6/7：四维 Pareto Front（无人工权重）。

维度：max flow、min delay、min ttc_per_k（conflict）、min co2_per_k。
候选集 = 每场景每密度下全部 (model, pCAV) 组合（IDM p=0..1.0 + CACC p=0.1..1.0）。

**Pareto 比较限定同 (scenario, density) 组内**（语义决策，2026-08）：
density 是外部交通需求参数而非设计变量——设计变量是 (model, pCAV) 渗透率
配置；跨 density 支配会把 front 退化为"密度越低越好"的无意义结论。

支配定义（A 支配 B）：A 在所有参与维度不劣于 B，且至少一维严格更优。
- 维度缺失（全 NaN）→ 从 Pareto 维度剔除并在 note 标注（不静默按 0 处理）；
- 部分 NaN 行 → 剔除（保守，避免错误支配）。

产出：`pareto_front.csv`（每场景 front 点 + 摘要列）、`pareto_summary.csv`
（每场景 front 大小 / pCAV 范围——预期结论：不同场景存在不同的 Pareto
optimal region，无单一全局最优渗透率）。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.analysis.common import (
    AnalysisInputError,
    ensure_dir,
    load_aggregated,
    write_csv,
)

DEFAULT_OUTPUT = "out/analysis/pareto"

PARETO_DIMS: tuple[tuple[str, str], ...] = (
    ("flow", "max"),
    ("delay", "min"),
    ("ttc_per_k", "min"),
    ("co2_per_k", "min"),
)


def _pareto_dims(df: pd.DataFrame) -> list[str]:
    """数据中实际可用的 Pareto 维度（全 NaN 维度剔除 + 警告标注）。"""
    dims = []
    for col, _ in PARETO_DIMS:
        if f"{col}_mean" not in df.columns:
            raise AnalysisInputError(f"Pareto 维度列缺失: {col}_mean")
        if df[f"{col}_mean"].notna().any():
            dims.append(col)
        else:
            print(f"[WARN] Pareto 维度 {col} 全 NaN，已剔除（不计入支配比较）")
    if not dims:
        raise AnalysisInputError("Pareto 无可用维度")
    return dims


def _dominates(a: np.ndarray, b: np.ndarray, dims: list[str], directions: list[str]) -> bool:
    """a 支配 b？所有维度不劣 + 至少一维严格。"""
    better_any = False
    for i, (_, direction) in enumerate(zip(dims, directions, strict=True)):
        va, vb = a[i], b[i]
        if np.isnan(va) or np.isnan(vb):
            return False  # 任一 NaN 不判定支配（保守）
        if direction == "max":
            if va < vb:
                return False
            if va > vb:
                better_any = True
        else:
            if va > vb:
                return False
            if va < vb:
                better_any = True
    return better_any


def compute_pareto_front(df: pd.DataFrame) -> pd.DataFrame:
    """全场景 Pareto front 计算。

    返回长表：每场景的候选点 + is_front 标记 + 被支配点数量；front 点附带
    维度值列。

    **Pareto 比较限定同 (scenario, density) 组内**（语义决策，2026-08）：
    density 是外部交通需求参数而非设计变量——跨 density 支配（低密度所有配置
    均更优）会把 front 退化为"密度越低越好"的无意义结论；设计变量是
    (model, pCAV) 渗透率配置。模块 docstring 与报告需同步声明此口径。
    """
    dims = _pareto_dims(df)
    dim_directions = dict(PARETO_DIMS)
    directions = [dim_directions[d] for d in dims]
    records = []
    for sc, g in df.groupby("scenario", sort=False):
        for dens, gd in g.groupby("density_veh_per_km_lane", sort=False):
            gd = gd.dropna(subset=[f"{d}_mean" for d in dims]).copy()
            vals = gd[[f"{d}_mean" for d in dims]].to_numpy(dtype=float)
            is_front = np.ones(len(gd), dtype=bool)
            dominated_count = np.zeros(len(gd), dtype=int)
            for i in range(len(gd)):
                for j in range(len(gd)):
                    if i == j:
                        continue
                    if _dominates(vals[j], vals[i], dims, directions):
                        is_front[i] = False
                        dominated_count[i] += 1
            for i in range(len(gd)):
                row = gd.iloc[i]
                records.append(
                    {
                        "scenario": sc,
                        "density_veh_per_km_lane": dens,
                        "model": row["model"],
                        "pCAV": row["pCAV"],
                        "vehN": row["vehN"],
                        **{f"{d}_mean": row[f"{d}_mean"] for d in dims},
                        "is_front": bool(is_front[i]),
                        "dominated_by_count": int(dominated_count[i]),
                        "pareto_dims": "+".join(dims),
                    }
                )
    return pd.DataFrame(records)


def compute_pareto_summary(front_df: pd.DataFrame) -> pd.DataFrame:
    """每场景 front 摘要：front 点数、front 覆盖的 model/pCAV 范围。"""
    rows = []
    for sc, g in front_df.groupby("scenario", sort=False):
        f = g[g["is_front"]]
        rows.append(
            {
                "scenario": sc,
                "front_size": len(f),
                "front_models": "+".join(sorted(set(f["model"]))),
                "front_pcav_min": f["pCAV"].min() if len(f) else np.nan,
                "front_pcav_max": f["pCAV"].max() if len(f) else np.nan,
                "front_pcav_range": (
                    f"p∈[{f['pCAV'].min():.1f},{f['pCAV'].max():.1f}]" if len(f) else "empty"
                ),
                "total_candidates": len(g),
                "note": (
                    "Pareto 比较限定同 (scenario, density) 组内——density 是外部"
                    "需求参数非设计变量；front 点按密度分组判定"
                ),
            }
        )
    return pd.DataFrame(rows)


def analyze(df: pd.DataFrame, output_dir: str | Path) -> dict[str, Path]:
    out = ensure_dir(output_dir)
    front = compute_pareto_front(df)
    summary = compute_pareto_summary(front)
    paths = {
        "pareto_front": write_csv(front, out / "pareto_front.csv", "pareto front"),
        "pareto_summary": write_csv(summary, out / "pareto_summary.csv", "pareto summary"),
    }
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="v0.4.2 分析层：四维 Pareto Front")
    parser.add_argument("--input", default="out/aggregated_results.csv", help="aggregated CSV")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT, help="CSV 输出目录")
    args = parser.parse_args()
    analyze(load_aggregated(args.input), args.output_dir)


if __name__ == "__main__":
    main()
