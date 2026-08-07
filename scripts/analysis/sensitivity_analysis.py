"""分析层模块 7/7：单/双维敏感性（复用 ssm_sensitivity 的扫描-对比模式，
作用于聚合数据层——数据零重跑）。

- **单维（指标口径/渗透率列选择）**：同一 Δ 概念在替代口径下的稳健性——
  - 渗透率列：pCAV vs realized_pcav（当前网格恒等，验证契约）；
  - 流量口径：flow_per_lane（每车道）vs flow_mean（车道总和）；
  - 延迟口径：delay_mean vs delay_p95_mean（若存在）；
  - 安全口径：ttc_per_k_mean vs drac_per_k_mean（若存在）。
  对每对替代口径计算 Δ 指标族（model baseline），报告每 (scenario, density)
  的 p* 档位区间差异（阈值稳健性：口径切换不改变 p* 档位 → 稳健）。
- **双维（阈值邻域稳定性）**：p* 档位沿 density 邻域的跳变次数（Δq=0 边界
  对密度轴的稳定性）+ Δq_model 曲面梯度幅度（|∂Δ/∂k|、|∂Δ/∂p| 最大区域）。

产出：`sensitivity_summary.csv`（单维对比）+ `threshold_stability.csv`（双维）。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.analysis.common import (
    AnalysisInputError,
    compute_delta_frame,
    ensure_dir,
    load_aggregated,
    write_csv,
)
from scripts.analysis.threshold_detection import _crossing

DEFAULT_OUTPUT = "out/analysis/sensitivity"
MODEL_DELTA_COL = "flow_per_lane_model_delta"

# 替代口径对：(Δ 长表列, 替代 Δ 长表列, 标签)——替代列缺失时该对比行跳过
ALT_DELTA_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("flow_model_delta", "flow_per_lane_model_delta", "flow total vs per-lane (scale)"),
    ("delay_model_delta", "delay_p95_model_delta", "delay mean vs p95"),
    ("ttc_per_k_model_delta", "drac_per_k_model_delta", "TTC vs DRAC event rate"),
)


def _delta_for_column(delta_df: pd.DataFrame, column: str) -> pd.Series:
    """按 Δ 长表列名取 Δ 序列（列不在时抛错）。"""
    if column not in delta_df.columns:
        raise AnalysisInputError(f"Δ 长表缺少 {column}")
    return delta_df[column]


def compute_column_sensitivity(delta_df: pd.DataFrame) -> pd.DataFrame:
    """单维：替代口径下 p* 档位区间对比（每 scenario×density）。"""
    available = [
        (col, alt, label)
        for col, alt, label in ALT_DELTA_PAIRS
        if col in delta_df.columns and alt in delta_df.columns
    ]
    if not available:
        return pd.DataFrame()
    rows = []
    for (sc, dens), g in delta_df.groupby(["scenario", "density_veh_per_km_lane"], sort=False):
        g = g.sort_values("pCAV")
        p_levels = list(g["pCAV"])
        for col, alt, label in available:
            base_vals = [float(v) if not pd.isna(v) else np.nan for v in _delta_for_column(g, col)]
            alt_vals = [float(v) if not pd.isna(v) else np.nan for v in _delta_for_column(g, alt)]
            base_cross = _crossing(p_levels, base_vals, neg_to_pos=True)
            alt_cross = _crossing(p_levels, alt_vals, neg_to_pos=True)
            same = (
                base_cross == alt_cross
                if base_cross is not None and alt_cross is not None
                else (base_cross is None and alt_cross is None)
            )
            rows.append(
                {
                    "scenario": sc,
                    "density_veh_per_km_lane": dens,
                    "pair": label,
                    "base_column": col,
                    "alt_column": alt,
                    "p_star_base": (
                        f"{base_cross[0]:.1f}–{base_cross[1]:.1f}" if base_cross else "none"
                    ),
                    "p_star_alt": (
                        f"{alt_cross[0]:.1f}–{alt_cross[1]:.1f}" if alt_cross else "none"
                    ),
                    "p_star_unchanged": same,
                    "max_abs_delta_diff": (
                        float(np.nanmax(np.abs(np.asarray(base_vals) - np.asarray(alt_vals))))
                        if any(not np.isnan(v) for v in base_vals + alt_vals)
                        else np.nan
                    ),
                }
            )
    return pd.DataFrame(rows)


def compute_threshold_stability(delta_df: pd.DataFrame) -> pd.DataFrame:
    """双维：p* 档位沿 density 邻域的跳变 + Δq 曲面梯度幅度。"""
    if MODEL_DELTA_COL not in delta_df.columns:
        raise AnalysisInputError(f"Δ 长表缺少 {MODEL_DELTA_COL}")
    rows = []
    for sc, g in delta_df.groupby("scenario", sort=False):
        g = g.sort_values(["density_veh_per_km_lane", "pCAV"])
        # p* 沿 density：每个 density 档一个 p* 交叉（无则 None）
        p_star_by_k: dict[float, tuple[float, float] | None] = {}
        for dens, gk in g.groupby("density_veh_per_km_lane", sort=False):
            gk = gk.sort_values("pCAV")
            vals = [float(v) if not pd.isna(v) else np.nan for v in gk[MODEL_DELTA_COL]]
            p_star_by_k[float(dens)] = _crossing(list(gk["pCAV"]), vals, neg_to_pos=True)
        k_sorted = sorted(p_star_by_k)
        jumps = 0
        for i in range(len(k_sorted) - 1):
            a, b = p_star_by_k[k_sorted[i]], p_star_by_k[k_sorted[i + 1]]
            if (a is None) != (b is None) or (a is not None and b is not None and a != b):
                jumps += 1
        # 曲面梯度幅度（中央差分，边缘 NaN）
        piv = g.pivot_table(
            index="density_veh_per_km_lane", columns="pCAV", values=MODEL_DELTA_COL
        ).sort_index()
        grad_k, grad_p = np.nan, np.nan
        if piv.shape[0] >= 2 and piv.shape[1] >= 2:
            grad_k = float(np.nanmax(np.abs(np.gradient(piv.to_numpy(dtype=float), axis=0))))
            grad_p = float(np.nanmax(np.abs(np.gradient(piv.to_numpy(dtype=float), axis=1))))
        rows.append(
            {
                "scenario": sc,
                "p_star_jumps_across_density": jumps,
                "n_density_levels": len(k_sorted),
                "max_grad_density": grad_k,
                "max_grad_pcav": grad_p,
                "note": (
                    "jumps = 相邻密度档 p* 档位变化次数（0 = 阈值沿密度轴稳定）；"
                    "grad = Δq_model 曲面最大梯度幅度"
                ),
            }
        )
    return pd.DataFrame(rows)


def analyze(df: pd.DataFrame, output_dir: str | Path) -> dict[str, Path]:
    out = ensure_dir(output_dir)
    deltas = compute_delta_frame(df)
    paths = {
        "sensitivity_summary": write_csv(
            compute_column_sensitivity(deltas),
            out / "sensitivity_summary.csv",
            "column sensitivity",
        ),
        "threshold_stability": write_csv(
            compute_threshold_stability(deltas),
            out / "threshold_stability.csv",
            "threshold stability",
        ),
    }
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="v0.4.2 分析层：单/双维敏感性")
    parser.add_argument("--input", default="out/aggregated_results.csv", help="aggregated CSV")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT, help="CSV 输出目录")
    args = parser.parse_args()
    analyze(load_aggregated(args.input), args.output_dir)


if __name__ == "__main__":
    main()
