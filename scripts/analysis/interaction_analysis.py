"""分析层模块 3/7：交互效应分解（p×density、model×scenario、model×density、三阶）。

以 Δq_model（flow 的 model baseline 差）为核心，对曲面做**分层描述分解**
（n=9 等权均值/斜率，非正式推断——口径定稿 3）：

- model × scenario：每场景的 Δq_model 等权均值（跨 density×p）——CACC 优势
  是否依赖道路场景；
- model × density：每 (scenario, pCAV) 下 Δq_model 对 density 的线性斜率——
  CACC 在何种密度下开始失效（斜率<0 = 优势随密度下降）；
- pCAV × density：每 (scenario, density) 下跨 p 的平均收益与 p 方向斜率——
  渗透率收益是否随密度变化；
- model × scenario × density（三阶）：Δq_model 对 density 的响应斜率在不同
  场景间的差异——场景是否改变 CACC 对密度的响应规律。

产出：`interaction_decomposition.csv`（长表：term / 分组键 / 描述量 /
解释标签）。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.analysis.common import (
    compute_delta_frame,
    ensure_dir,
    load_aggregated,
    write_csv,
)

DEFAULT_OUTPUT = "out/analysis/interaction"

# 三阶分解主指标：flow 的 model baseline 差（同 p 下 CACC − IDM）
MAIN_DELTA_COL = "flow_per_lane_model_delta"


def _lin_slope(x: pd.Series, y: pd.Series) -> float:
    """一阶线性拟合斜率；不足 2 个点返回 NaN（不推断）。"""
    if len(x) < 2:
        return float("nan")
    return float(np.polyfit(x.to_numpy(dtype=float), y.to_numpy(dtype=float), 1)[0])


def compute_interaction_decomposition(delta_df: pd.DataFrame) -> pd.DataFrame:
    """四类交互项的描述性分解长表。"""
    if MAIN_DELTA_COL not in delta_df.columns:
        raise ValueError(f"Δ 长表缺少 {MAIN_DELTA_COL}——flow_per_lane 必须存在")
    d = delta_df.dropna(subset=[MAIN_DELTA_COL])
    rows: list[dict] = []

    # ── model × scenario：每场景 Δq_model 均值 ──
    for (sc,), g in d.groupby(["scenario"]):
        rows.append(
            {
                "term": "model×scenario",
                "scenario": sc,
                "density_veh_per_km_lane": np.nan,
                "pCAV": np.nan,
                "value": g[MAIN_DELTA_COL].mean(),
                "n": len(g),
                "note": "CACC 优势的场景均值（跨 density×p 等权）",
            }
        )

    # ── model × density：每 (scenario, pCAV) 的 Δ 对 density 斜率 ──
    for (sc, p), g in d.groupby(["scenario", "pCAV"]):
        slope = _lin_slope(g["density_veh_per_km_lane"], g[MAIN_DELTA_COL])
        rows.append(
            {
                "term": "model×density",
                "scenario": sc,
                "density_veh_per_km_lane": np.nan,
                "pCAV": p,
                "value": slope,
                "n": len(g),
                "note": (
                    "Δq_model 对 density 的斜率（veh/h/lane per veh/km/lane）；"
                    "负值 = CACC 优势随密度下降"
                ),
            }
        )

    # ── pCAV × density：每 (scenario, density) 跨 p 均值 + p 方向斜率 ──
    for (sc, dens), g in d.groupby(["scenario", "density_veh_per_km_lane"]):
        p_slope = _lin_slope(g["pCAV"], g[MAIN_DELTA_COL])
        rows.append(
            {
                "term": "pCAV×density",
                "scenario": sc,
                "density_veh_per_km_lane": dens,
                "pCAV": np.nan,
                "value": g[MAIN_DELTA_COL].mean(),
                "n": len(g),
                "note": "Δq_model 跨 p 等权均值（渗透率收益的密度剖面）",
            }
        )
        rows.append(
            {
                "term": "pCAV×density_slope",
                "scenario": sc,
                "density_veh_per_km_lane": dens,
                "pCAV": np.nan,
                "value": p_slope,
                "n": len(g),
                "note": "Δq_model 对 pCAV 的斜率（veh/h/lane per 1.0 渗透率）；正值 = 渗透率收益",
            }
        )

    # ── model × scenario × density（三阶）：density 斜率跨场景差异 ──
    slopes: dict[tuple[str, float], float] = {}
    for (sc, p), g in d.groupby(["scenario", "pCAV"]):
        slopes[(sc, p)] = _lin_slope(g["density_veh_per_km_lane"], g[MAIN_DELTA_COL])
    sc_avail = sorted({sc for sc, _ in slopes})
    for p in sorted({p for _, p in slopes}):
        per_sc = {sc: slopes[(sc, p)] for sc in sc_avail if (sc, p) in slopes}
        vals = list(per_sc.values())
        rows.append(
            {
                "term": "model×scenario×density",
                "scenario": np.nan,
                "density_veh_per_km_lane": np.nan,
                "pCAV": p,
                "value": (max(vals) - min(vals)) if vals else np.nan,
                "n": len(vals),
                "note": (
                    "同一 pCAV 下 Δq_model 对 density 斜率在场景间的最大差"
                    f"（各场景斜率: { {k: round(v, 3) for k, v in per_sc.items()} }）"
                ),
            }
        )

    out = pd.DataFrame(rows)
    return out.sort_values(["term", "scenario", "density_veh_per_km_lane", "pCAV"]).reset_index(
        drop=True
    )


def analyze(df: pd.DataFrame, output_dir: str | Path) -> dict[str, Path]:
    out = ensure_dir(output_dir)
    deltas = compute_delta_frame(df)
    decomp = compute_interaction_decomposition(deltas)
    paths = {
        "interaction_decomposition": write_csv(
            decomp, out / "interaction_decomposition.csv", "interaction decomposition"
        ),
    }
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="v0.4.2 分析层：交互效应分解")
    parser.add_argument("--input", default="out/aggregated_results.csv", help="aggregated CSV")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT, help="CSV 输出目录")
    args = parser.parse_args()
    analyze(load_aggregated(args.input), args.output_dir)


if __name__ == "__main__":
    main()
