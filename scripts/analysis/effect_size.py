"""分析层模块 2/7：效应量（Δ 指标族 + 标准化效应 + 跨 seed 区间）。

产出：`effect_size.csv`——每 (scenario, density, pCAV>0, metric, baseline)
的 Δ 指标族（双 baseline：model / abs）+ Cohen's d 变体 + 描述性区间 +
跨 seed 一致性。

口径（analysis-layer-v042-design.md §四.3）：n=9 不升级强推断——效应量为
**描述性标准化差**（Cohen's d 变体，s_pooled 按样本量加权），区间为跨 seed
等权正态近似，一致性为跨 seed 全范围判定；非正式显著性检验。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.analysis.common import (
    available_specs,
    compute_delta_frame,
    ensure_dir,
    load_aggregated,
    write_csv,
)

DEFAULT_OUTPUT = "out/analysis/effect_size"


# Cohen 惯例（非正式：仅便于量级沟通，不做显著性判定）
_D_LEVELS = (
    (0.2, "negligible"),
    (0.5, "small"),
    (0.8, "medium"),
    (np.inf, "large"),
)


def cohens_d(delta: float, s_cacc: float, s_base: float, n_cacc: int, n_base: int) -> float:
    """Cohen's d 变体：d = Δ / s_pooled（符号与 Δ 一致，Δ>0 = CACC 更优）。"""
    n_c = max(n_cacc, 2)
    n_b = max(n_base, 2)
    s_pooled = np.sqrt(((n_c - 1) * s_cacc**2 + (n_b - 1) * s_base**2) / (n_c + n_b - 2))
    if s_pooled == 0.0:
        return 0.0
    return delta / s_pooled


def interpret_d(abs_d: float) -> str:
    for threshold, label in _D_LEVELS:
        if abs_d < threshold:
            return label
    return "large"  # pragma: no cover（防御）


def _row_std_index(df: pd.DataFrame) -> dict[tuple[str, float, float, str], pd.Series]:
    """预构建 (scenario, density, pCAV, model) → 行 的索引，供 O(1) 查找 std。"""
    idx = {}
    for _, row in df.iterrows():
        key = (
            str(row["scenario"]),
            float(row["density_veh_per_km_lane"]),
            float(row["pCAV"]),
            str(row["model"]),
        )
        idx[key] = row
    return idx


def _row_std(
    idx: dict[tuple[str, float, float, str], pd.Series],
    sc: str,
    dens: float,
    p: float,
    model: str,
    col: str,
) -> float:
    key = (sc, dens, p, model)
    if key not in idx:
        raise ValueError(
            f"effect_size: 找不到行 (scenario={sc}, density={dens}, pCAV={p}, model={model})"
        )
    return float(idx[key][f"{col}_std"])


def compute_effect_sizes(df: pd.DataFrame) -> pd.DataFrame:
    """在 Δ 长表上追加效应量列（每 baseline 的 d + 解释）。"""
    deltas = compute_delta_frame(df)
    idx = _row_std_index(df)
    rows = []
    for _, r in deltas.iterrows():
        sc = str(r["scenario"])
        dens = float(r["density_veh_per_km_lane"])
        p = float(r["pCAV"])
        rec = {
            "scenario": sc,
            "density_veh_per_km_lane": dens,
            "pCAV": p,
            "n_cacc": int(r["n_cacc"]),
        }
        for spec in available_specs(df):
            col = spec.column
            for baseline, base_model in (("model", "IDM"), ("abs", "IDM")):
                prefix = f"{col}_{baseline}"
                n_c = int(r["n_cacc"])
                n_b = int(r["n_idm"] if baseline == "model" else r["n_hv"])
                d = cohens_d(
                    float(r[f"{prefix}_delta"]),
                    _row_std(idx, sc, dens, p, "CACC", col),
                    _row_std(idx, sc, dens, 0.0 if baseline == "abs" else p, base_model, col),
                    n_c,
                    n_b,
                )
                rec[f"{prefix}_d"] = d
                rec[f"{prefix}_d_label"] = interpret_d(abs(d))
                rec[f"{prefix}_delta"] = r[f"{prefix}_delta"]
                rec[f"{prefix}_delta_lo"] = r[f"{prefix}_delta_lo"]
                rec[f"{prefix}_delta_hi"] = r[f"{prefix}_delta_hi"]
                rec[f"{prefix}_consistent"] = r[f"{prefix}_consistent"]
        rows.append(rec)
    return pd.DataFrame(rows)


def analyze(df: pd.DataFrame, output_dir: str | Path) -> dict[str, Path]:
    out = ensure_dir(output_dir)
    es = compute_effect_sizes(df)
    paths = {
        "effect_size": write_csv(es, out / "effect_size.csv", "effect size"),
    }
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="v0.4.2 分析层：效应量")
    parser.add_argument("--input", default="out/aggregated_results.csv", help="aggregated CSV")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT, help="CSV 输出目录")
    args = parser.parse_args()
    analyze(load_aggregated(args.input), args.output_dir)


if __name__ == "__main__":
    main()
