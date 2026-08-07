"""分析层模块 4/7：阈值检测——Δq=0 交叉点 + p*(k,s) / k*(p,s) 档位区间。

语义（analysis-layer-v042-design.md §五）：
- p*(k,s)：密度 k、场景 s 下 CACC 正收益所需**最低**渗透率（Δq_model 沿 p
  首个 负→正 交叉；首档已正 → `p* ≤ 0.1`，全负 → `p* > 1.0`）；
- k*(p,s)：给定渗透率下 CACC 优势**消失**的临界密度（Δq_model 沿 density
  首个 正→负 交叉——反转区域）。

口径定稿 4：p 为 0.1 步长 → 一律报告档位区间（如 `p* ∈ (0.5, 0.6]`）；
插值细值仅经 --interpolate 显式开启且标注"估计/探索性插值"。

产出：`p_star.csv`（每 scenario×density 的收益起点/反转起点档位区间）、
`k_star.csv`（每 scenario×pCAV 的优势消失/恢复密度区间）。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.analysis.common import (
    compute_delta_frame,
    ensure_dir,
    format_p_star,
    load_aggregated,
    p_star_interval,
    write_csv,
)

DEFAULT_OUTPUT = "out/analysis/threshold"
MAIN_DELTA_COL = "flow_per_lane_model_delta"


def _crossing(
    levels: list[float], values: list[float], neg_to_pos: bool
) -> tuple[float, float] | None:
    """沿 levels 找首个方向交叉（档位区间）。

    neg_to_pos=True：Δ≤0 → Δ>0（收益出现）；False：Δ>0 → Δ≤0（反转）。
    返回 (lo, hi] 档位区间；无交叉返回 None。
    """
    for i in range(len(levels) - 1):
        v0, v1 = values[i], values[i + 1]
        if neg_to_pos and v0 <= 0.0 < v1:
            return (levels[i], levels[i + 1])
        if not neg_to_pos and v0 > 0.0 >= v1:
            return (levels[i], levels[i + 1])
    return None


def _interpolate_crossing(lo: float, hi: float, v_lo: float, v_hi: float) -> float:
    """线性插值细值（仅 --interpolate；标注估计/探索性）。"""
    if v_hi == v_lo:
        return lo
    return lo + (hi - lo) * (0.0 - v_lo) / (v_hi - v_lo)


def detect_p_star(delta_df: pd.DataFrame, interpolate: bool = False) -> pd.DataFrame:
    """每 (scenario, density) 的 p* 档位区间（主指标 flow model baseline）。"""
    if MAIN_DELTA_COL not in delta_df.columns:
        raise ValueError(f"Δ 长表缺少 {MAIN_DELTA_COL}")
    rows = []
    for (sc, dens), g in delta_df.groupby(["scenario", "density_veh_per_km_lane"], sort=False):
        g = g.sort_values("pCAV")
        p_levels = list(g["pCAV"])
        vals = [float(v) if not pd.isna(v) else np.nan for v in g[MAIN_DELTA_COL]]
        gain = _crossing(p_levels, vals, neg_to_pos=True)
        rev = _crossing(p_levels, vals, neg_to_pos=False)
        # status：既有负→正又正→负 → mixed；仅 gain/reversal → 对应；无交叉时
        # 首档已正 = 全档位正收益（gain），否则全负（no_crossing）
        if gain and rev:
            status = "mixed"
        elif gain:
            status = "gain"
        elif rev:
            status = "reversal"
        else:
            status = "gain" if vals and vals[0] > 0.0 else "no_crossing"
        rec = {
            "scenario": sc,
            "density_veh_per_km_lane": dens,
            "p_star": format_p_star(gain[0], gain[1])
            if gain
            else ("p* ≤ 0.1" if vals and vals[0] > 0.0 else "p* > 1.0 (no gain in tested p)"),
            "p_reversal_start": p_star_interval(rev[0], rev[1]) if rev else "none",
            "status": status,
            "n_p_levels": len(p_levels),
        }
        if interpolate:
            if gain:
                i = p_levels.index(gain[0])
                rec["p_star_interpolated"] = _interpolate_crossing(
                    gain[0], gain[1], vals[i], vals[i + 1]
                )
                rec["p_star_interpolated_note"] = "估计/探索性插值（非档位口径）"
            else:
                rec["p_star_interpolated"] = np.nan
                rec["p_star_interpolated_note"] = ""
        rows.append(rec)
    return pd.DataFrame(rows)


def detect_k_star(delta_df: pd.DataFrame) -> pd.DataFrame:
    """每 (scenario, pCAV) 的 k* 档位区间（优势消失/恢复密度）。"""
    if MAIN_DELTA_COL not in delta_df.columns:
        raise ValueError(f"Δ 长表缺少 {MAIN_DELTA_COL}")
    rows = []
    for (sc, p), g in delta_df.groupby(["scenario", "pCAV"], sort=False):
        g = g.sort_values("density_veh_per_km_lane")
        k_levels = list(g["density_veh_per_km_lane"])
        vals = [float(v) if not pd.isna(v) else np.nan for v in g[MAIN_DELTA_COL]]
        rev = _crossing(k_levels, vals, neg_to_pos=False)  # 优势消失（正→负）
        rec = {
            "scenario": sc,
            "pCAV": p,
            "k_star": p_star_interval(rev[0], rev[1]) if rev else "none",
            "k_star_status": (
                "reversal_in_range"
                if rev
                else ("gain_throughout" if vals and vals[-1] > 0.0 else "no_gain_in_tested_k")
            ),
            "n_k_levels": len(k_levels),
        }
        rows.append(rec)
    return pd.DataFrame(rows)


def analyze(df: pd.DataFrame, output_dir: str | Path, interpolate: bool = False) -> dict[str, Path]:
    out = ensure_dir(output_dir)
    deltas = compute_delta_frame(df)
    paths = {
        "p_star": write_csv(
            detect_p_star(deltas, interpolate), out / "p_star.csv", "p* thresholds"
        ),
        "k_star": write_csv(detect_k_star(deltas), out / "k_star.csv", "k* thresholds"),
    }
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="v0.4.2 分析层：Δq=0 阈值检测")
    parser.add_argument("--input", default="out/aggregated_results.csv", help="aggregated CSV")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT, help="CSV 输出目录")
    parser.add_argument(
        "--interpolate",
        action="store_true",
        help="额外输出线性插值细值（标注'估计/探索性插值'，非档位口径）",
    )
    args = parser.parse_args()
    analyze(load_aggregated(args.input), args.output_dir, interpolate=args.interpolate)


if __name__ == "__main__":
    main()
