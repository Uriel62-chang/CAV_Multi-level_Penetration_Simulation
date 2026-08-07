"""分析层测试共享 fixture（非 test_* 前缀，不被 pytest 收集）。

迷你 aggregated CSV 构造：scenario_0（单车道）× 2 密度 × pCAV{0,0.5,1.0} ×
{IDM, CACC}，Δ 语义已知（density=10 正收益、density=20 负收益/反转）。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def make_agg_df() -> pd.DataFrame:
    """构造迷你聚合 DF（10 行：IDM 2×3 + CACC 2×2，p>0 仅 CACC）。"""
    rows = []
    for vehN, dens in ((20, 10.0), (40, 20.0)):
        for p in (0.0, 0.5, 1.0):
            for model in ("IDM", "CACC"):
                if p == 0.0 and model != "IDM":
                    continue  # p=0 sentinel
                flow = 1000.0
                if model == "CACC":
                    flow = {10.0: {0.5: 1050.0, 1.0: 1020.0}, 20.0: {0.5: 980.0, 1.0: 950.0}}[dens][
                        p
                    ]
                delay = 5.0 if model == "CACC" else 8.0
                rows.append(
                    {
                        "experiment_role": "main_factorial",
                        "scenario": "scenario_0",
                        "model": model,
                        "vehN": vehN,
                        "cav_count": int(p * vehN),
                        "pCAV": p,
                        "realized_pcav": p,
                        "density_veh_per_km_lane": dens,
                        "independent_random_replication_count": 9 if p > 0 else 3,
                        "flow_mean": flow,
                        "flow_std": 100.0,
                        "flow_min": flow - 5.0,
                        "flow_max": flow + 5.0,
                        "n_valid": 9 if p > 0 else 3,
                        "delay_mean": delay,
                        "delay_std": 1.0,
                        "delay_min": delay - 0.5,
                        "delay_max": delay + 0.5,
                        "delay_count": 9 if p > 0 else 3,
                        "delay_p95_mean": delay + 2.0,
                        "delay_p95_std": 1.0,
                        "delay_p95_min": delay + 1.5,
                        "delay_p95_max": delay + 2.5,
                        "delay_p95_count": 9 if p > 0 else 3,
                        "ttc_per_k_mean": 1.0,
                        "ttc_per_k_std": 0.2,
                        "ttc_per_k_min": 0.8,
                        "ttc_per_k_max": 1.2,
                        "ttc_per_k_count": 9 if p > 0 else 3,
                        "drac_per_k_mean": 0.5,
                        "drac_per_k_std": 0.1,
                        "drac_per_k_min": 0.4,
                        "drac_per_k_max": 0.6,
                        "drac_per_k_count": 9 if p > 0 else 3,
                        "co2_per_k_mean": 200.0,
                        "co2_per_k_std": 10.0,
                        "co2_per_k_min": 190.0,
                        "co2_per_k_max": 210.0,
                        "co2_per_k_count": 9 if p > 0 else 3,
                        "fuel_per_k_mean": 60.0,
                        "fuel_per_k_std": 3.0,
                        "fuel_per_k_min": 57.0,
                        "fuel_per_k_max": 63.0,
                        "fuel_per_k_count": 9 if p > 0 else 3,
                    }
                )
    return pd.DataFrame(rows)


def make_agg_csv(tmp_path) -> str:
    p = Path(tmp_path) / "agg.csv"
    make_agg_df().to_csv(p, index=False)
    return str(p)
