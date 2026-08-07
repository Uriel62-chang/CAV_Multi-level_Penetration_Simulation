"""分析层模块 5/7：双 Phase Diagram（核心产出）。

- **Model Effect Surface**（Δq_model = q_CACC,p − q_IDM,p）：同一 pCAV 下 CACC
  相比 IDM 是否更优——pCAV × density 平面，颜色 Δq_model，标注 Δq=0 分界线；
- **Absolute Benefit Surface**（Δq_abs = q_CACC,p − q_HV,0）：相对纯 HV 基线
  的绝对 CAV 收益。

两图语义不同、独立命名、并列解读不强行选 baseline（口径定稿 1）；s3 高密度
三态判读在两面板对照中直接可读。Δ 为正（暖色）= 收益，负（冷色）= 反转。

图注声明：Δq=0 分界线为 contour 在档位间线性插值（可视化示意）；档位级阈值
以 threshold_detection 的 p_star.csv / k_star.csv 为准（口径定稿 4）。

产出：`chart_phase_diagrams.png`（4 场景 × 2 曲面）。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.analysis.common import (
    compute_delta_frame,
    ensure_dir,
    load_aggregated,
)

DEFAULT_CHART_DIR = "graph/v0.4.2"

SCENARIO_LABELS = {
    "scenario_0": "s0 (square ring)",
    "scenario_1": "s1 (32-gon single-lane)",
    "scenario_2": "s2 (dual-lane)",
    "scenario_3": "s3 (bottleneck)",
}
MODEL_DELTA_COL = "flow_per_lane_model_delta"
ABS_DELTA_COL = "flow_per_lane_abs_delta"


def surface_matrix(
    delta_df: pd.DataFrame, scenario: str, delta_col: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(scenario, delta_col) → (density_levels, p_levels, Δ 矩阵)。

    网格：density 升序 × pCAV 升序（p>0，CACC 曲面无 p=0 sentinel）；
    缺失 cell 置 NaN（pcolormesh 显示空白，不插值——档位粒度）。
    """
    g = delta_df[(delta_df["scenario"] == scenario) & (delta_df["pCAV"] > 0.0)]
    piv = g.pivot_table(
        index="density_veh_per_km_lane", columns="pCAV", values=delta_col, aggfunc="mean"
    )
    if piv.empty:
        raise ValueError(f"scenario={scenario} 无 {delta_col} 数据")
    # 行/列排序并补齐缺失档位（网格不对称时以 NaN 填充）
    density_levels = sorted(piv.index)
    p_levels = sorted(piv.columns)
    mat = piv.reindex(index=density_levels, columns=p_levels).to_numpy(dtype=float)
    return (
        np.asarray(density_levels, dtype=float),
        np.asarray(p_levels, dtype=float),
        mat,
    )


def _draw_surface(ax, density_levels, p_levels, mat, title: str, vmax: float) -> None:
    """绘制单曲面；vmax 为**全局**色标对称半宽（跨场景×跨曲面统一，保证
    Model Effect 与 Absolute Benefit 两曲面颜色-数值映射一致可比）。"""
    cmap = plt.get_cmap("RdBu_r")  # 暖=正收益，冷=负收益
    pcm = ax.pcolormesh(
        density_levels, p_levels, mat.T, cmap=cmap, vmin=-vmax, vmax=vmax, shading="auto"
    )
    # Δq=0 分界线（contour 档位间线性插值——可视化示意）
    if np.isfinite(mat).sum() >= 4 and mat.shape[0] >= 2 and mat.shape[1] >= 2:
        ax.contour(
            density_levels,
            p_levels,
            mat.T,
            levels=[0.0],
            colors="black",
            linestyles="--",
            linewidths=1.2,
        )
    ax.set_title(title, fontsize=11)
    ax.set_xlabel("Density (veh/km/lane)", fontsize=9)
    ax.set_ylabel("CAV penetration p", fontsize=9)
    ax.grid(True, alpha=0.2)
    return pcm


def chart_phase_diagrams(delta_df: pd.DataFrame, out_dir: str | Path) -> Path:
    """双 Phase Diagram 一张图：场景行 × 2 曲面列（Model Effect | Absolute Benefit）。

    场景按数据中存在性数据驱动（SCENARIO_LABELS 顺序过滤），单场景 fixture
    也可出图；行数 = 数据中的场景数。**色标为全局对称半宽**（跨场景×跨曲面
    统一 vmax）——两曲面在同一 Δ 尺度下可比，图注与 colorbar 一致。
    """
    out = ensure_dir(out_dir)
    scenarios = [sc for sc in SCENARIO_LABELS if sc in set(delta_df["scenario"])]
    if not scenarios:
        raise ValueError("Δ 长表无场景数据")
    # 先收集全部 surface + 计算全局 vmax（一次调用，避免重复 pivot）
    surfaces: dict[tuple[str, str], tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    vmax = 0.0
    for sc in scenarios:
        for col in (MODEL_DELTA_COL, ABS_DELTA_COL):
            dens, ps, mat = surface_matrix(delta_df, sc, col)
            surfaces[(sc, col)] = (dens, ps, mat)
            if np.isfinite(mat).any():
                vmax = max(vmax, float(np.nanmax(np.abs(mat))))
    vmax = max(vmax, 1e-9)
    fig, axes = plt.subplots(
        len(scenarios), 2, figsize=(14, 4.5 * len(scenarios)), constrained_layout=True
    )
    if len(scenarios) == 1:
        axes = axes.reshape(1, 2)
    for row, sc in enumerate(scenarios):
        label = SCENARIO_LABELS[sc]
        for col, (delta_col, title) in enumerate(
            (
                (MODEL_DELTA_COL, f"{label}\nModel Effect Δq_model"),
                (ABS_DELTA_COL, f"{label}\nAbsolute Benefit Δq_abs"),
            )
        ):
            ax = axes[row, col]
            dens, ps, mat = surfaces[(sc, delta_col)]
            _draw_surface(ax, dens, ps, mat, title, vmax=vmax)
    sm = plt.cm.ScalarMappable(cmap=plt.get_cmap("RdBu_r"), norm=plt.Normalize(-vmax, vmax))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes, orientation="vertical", fraction=0.02, pad=0.02)
    cbar.set_label("Δq (veh/h/lane): warm = CACC benefit, cold = reversal", fontsize=10)
    fig.suptitle(
        "CAV Benefit Phase Diagrams (v0.4.2 main grid)\n"
        "Model Effect: q_CACC,p − q_IDM,p  |  Absolute Benefit: q_CACC,p − q_HV,0",
        fontsize=14,
    )
    path = out / "chart_phase_diagrams.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {path}")
    return path


def analyze(df: pd.DataFrame, chart_dir: str | Path) -> dict[str, Path]:
    deltas = compute_delta_frame(df)
    paths = {"chart_phase_diagrams": chart_phase_diagrams(deltas, chart_dir)}
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="v0.4.2 分析层：双 Phase Diagram")
    parser.add_argument("--input", default="out/aggregated_results.csv", help="aggregated CSV")
    parser.add_argument("--chart-dir", default=DEFAULT_CHART_DIR, help="图输出目录")
    args = parser.parse_args()
    analyze(load_aggregated(args.input), args.chart_dir)


if __name__ == "__main__":
    main()
