"""v0.4.0 数据可视化 —— 兼容 v0.3.0 基本图 + v0.4.0 四组 trade-off 图表。

    v0.3.0 模式（默认）：
      python3 -m scripts.results.visualization --csv out/results_raw_p05.csv

    v0.4.0 模式：
      python3 -m scripts.results.visualization --aggregated results/aggregated_results.csv --v4
"""
import argparse
import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

RING_LENGTH_KM = 2.0  # 环路长度 (km)，v0.3.0 兼容


# ═══════════════════════════════════════════════════════════════════
# v0.3.0 兼容：密度-流量基本图 + 通行能力汇总
# ═══════════════════════════════════════════════════════════════════

def load_and_aggregate(csv_path: str, ring_length_km: float = RING_LENGTH_KM):
    if not os.path.exists(csv_path):
        print(f"错误: 找不到文件 {csv_path}")
        return None, None
    print(f"正在读取数据: {csv_path} ...")
    data = pd.read_csv(csv_path)
    data["density"] = data["vehN"] / ring_length_km
    aggregated = data.groupby(["pCAV", "vehN", "density"])["mean_flow(veh/h)"].mean().reset_index()
    cav_ratios = sorted(aggregated["pCAV"].unique())
    return aggregated, cav_ratios


def compute_capacities(aggregated: pd.DataFrame, cav_ratios: list):
    capacities = []
    for ratio in cav_ratios:
        subset = aggregated[aggregated["pCAV"] == ratio]
        peak_row = subset["mean_flow(veh/h)"].idxmax()
        capacities.append({
            "cav_ratio": ratio,
            "peak_flow": subset.loc[peak_row, "mean_flow(veh/h)"],
            "peak_density": subset.loc[peak_row, "density"],
        })
    return capacities


def plot_density_flow(ratio: float, density: pd.Series, flow: pd.Series,
                      peak_density: float, peak_flow: float, output_dir: str):
    plt.figure(figsize=(10, 5))
    plt.plot(density, flow, marker="o", color="blue", label="Flow", linewidth=2, linestyle="-")
    plt.plot(peak_density, peak_flow, marker="*", markersize=12, color="red", label="Capacity")
    plt.title(f"Density-Flow Curve (CAV penetration rate: {int(ratio * 100)}%)", fontsize=20)
    plt.xlabel("Density (veh/km)", fontsize=15)
    plt.ylabel("Flow (veh/h)", fontsize=15)
    plt.xlim(0, density.max() * 1.1)
    plt.ylim(0, peak_flow * 1.1)
    for x, y in zip(density, flow):
        plt.text(x, y, str(y), ha="center", va="bottom")
    plt.legend(loc="upper left")
    plt.grid(axis="y")
    save_path = os.path.join(output_dir, f"fd_p{int(ratio * 100):03d}.png")
    plt.savefig(save_path)
    print(f"[OK] {int(ratio * 100)}%渗透率的[密度-流量]曲线已成功保存至{save_path}")
    plt.close()


def plot_capacity_summary(capacities: list, output_dir: str):
    plt.figure(figsize=(10, 5))
    cav_percentages = [c["cav_ratio"] * 100 for c in capacities]
    capacity_values = [c["peak_flow"] for c in capacities]
    plt.plot(cav_percentages, capacity_values, marker="o", markersize=8,
             label="Capacity", color="blue", linewidth=2, linestyle="-")
    max_capacity = max(capacity_values)
    max_index = capacity_values.index(max_capacity)
    max_percentage = cav_percentages[max_index]
    plt.plot(max_percentage, max_capacity, marker="*", markersize=12,
             color="red", linestyle="None", label="Max Capacity")
    plt.title("CAV Penetration Rate - Capacity Curve", fontsize=20)
    plt.xlabel("CAV Penetration Rate (%)", fontsize=15)
    plt.ylabel("Capacity (veh/h)", fontsize=15)
    plt.ylim(0, max_capacity * 1.1)
    for x, y in zip(cav_percentages, capacity_values):
        if y == max_capacity:
            plt.text(x, y, f"({x}, {y})", ha="center", va="bottom")
    plt.legend(loc="upper left")
    plt.grid(axis="y")
    os.makedirs(output_dir, exist_ok=True)
    save_path = os.path.join(output_dir, "Capacity_summary.png")
    plt.savefig(save_path)
    print(f"[OK] [CAV渗透率-通行能力]曲线已成功保存至{save_path}")
    plt.close()


def run_v03(args) -> None:
    ring_length_km = RING_LENGTH_KM
    if args.ring_length is not None:
        ring_length_km = args.ring_length
    elif args.net is not None:
        net_dir = os.path.dirname(args.net)
        meta_path = os.path.join(net_dir, "net.json")
        if os.path.isfile(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                ring_length_km = json.load(f).get("total_length_km", RING_LENGTH_KM)
            print(f"从 {meta_path} 读取环路总长: {ring_length_km} km")

    aggregated, cav_ratios = load_and_aggregate(args.csv, ring_length_km)
    if aggregated is None:
        return
    os.makedirs(args.outDir, exist_ok=True)
    capacities = compute_capacities(aggregated, cav_ratios)
    for capacity in capacities:
        subset = aggregated[aggregated["pCAV"] == capacity["cav_ratio"]]
        plot_density_flow(capacity["cav_ratio"], subset["density"],
                          subset["mean_flow(veh/h)"], capacity["peak_density"],
                          capacity["peak_flow"], args.outDir)
    plot_capacity_summary(capacities, args.outDir)


# ═══════════════════════════════════════════════════════════════════
# v0.4.0：四组 trade-off 图表
# ═══════════════════════════════════════════════════════════════════

SCENARIO_LABELS = {
    "scenario_0": "s0 (square ring)", "scenario_1": "s1 (32-gon single-lane)",
    "scenario_2": "s2 (dual-lane)", "scenario_3": "s3 (bottleneck)",
}
# 模型配色：同面板内两模型需一眼可辨，使用高对比色
MODEL_COLORS = {"IDM": "#2166ac", "CACC": "#b2182b"}  # 蓝 vs 红
MODEL_STYLES = {
    "IDM":  {"marker": "o", "linestyle": "-",  "linewidth": 1.5},
    "CACC": {"marker": "s", "linestyle": "--", "linewidth": 1.5},
}


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def chart_capacity_v4(df: pd.DataFrame, out_dir: Path) -> None:
    """x=pCAV, y=每个 pCAV 下最高 flow，四场景分面"""
    capacity = df.groupby(["scenario", "model", "pCAV"])["flow_mean"].max().reset_index()
    fig, axes = plt.subplots(2, 2, figsize=(16, 11), sharex=True, sharey=False,
                             constrained_layout=True)
    axes = axes.flatten()
    for ax, (sc, label) in zip(axes, SCENARIO_LABELS.items()):
        sub = capacity[capacity["scenario"] == sc]
        for model in ["IDM", "CACC"]:
            d = sub[sub["model"] == model].sort_values("pCAV")
            if len(d) == 0:
                continue
            s = MODEL_STYLES[model]
            ax.plot(d["pCAV"] * 100, d["flow_mean"], marker=s["marker"],
                    linestyle=s["linestyle"], linewidth=s["linewidth"],
                    color=MODEL_COLORS[model], markersize=5, label=model, alpha=0.85)
        ax.set_title(label, fontsize=12)
        ax.set_ylabel("Capacity (veh/h)", fontsize=10)
        ax.legend(fontsize=9); ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%d%%'))
        ax.tick_params(labelbottom=True)  # 所有面板显示 x 轴刻度
    axes[2].set_xlabel("CAV Penetration Rate", fontsize=11)
    axes[3].set_xlabel("CAV Penetration Rate", fontsize=11)
    fig.suptitle("CAV Penetration Rate vs Capacity (per scenario)", fontsize=14)
    path = out_dir / "chart_capacity.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {path}")


def chart_safety_flow_v4(df: pd.DataFrame, out_dir: Path) -> None:
    """x=flow_mean, y=ttc_per_k_mean, s0+s3 双面板"""
    fig, axes = plt.subplots(1, 2, figsize=(16, 7), constrained_layout=True)
    for ax, sc in zip(axes, ["scenario_0", "scenario_3"]):
        sub = df[df["scenario"] == sc]
        for model in ["IDM", "CACC"]:
            d = sub[sub["model"] == model]
            if len(d) == 0:
                continue
            s = MODEL_STYLES[model]
            sizes = np.clip(d["vehN"] / 2, 10, 120)
            ax.scatter(d["flow_mean"], d["ttc_per_k_mean"], s=sizes, alpha=0.6,
                       edgecolors="white", linewidth=0.3,
                       color=MODEL_COLORS[model], marker=s["marker"], label=model)
        ax.set_title(SCENARIO_LABELS.get(sc, sc), fontsize=12)
        ax.set_xlabel("Flow (veh/h)", fontsize=10)
        ax.set_ylabel("TTC Events / 1000 veh-km", fontsize=10)
        ax.legend(fontsize=9); ax.grid(True, alpha=0.3)
    fig.suptitle("Safety–Flow Trade-off: TTC/1000 veh-km vs Flow", fontsize=14)
    path = out_dir / "chart_safety_flow.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {path}")


def chart_co2_flow_v4(df: pd.DataFrame, out_dir: Path) -> None:
    """x=flow_mean, y=co2_per_k_mean，四场景分面，x 轴统一"""
    x_min = df["flow_mean"].min() * 0.95
    x_max = df["flow_mean"].max() * 1.05
    fig, axes = plt.subplots(2, 2, figsize=(16, 11), sharex=False, sharey=False,
                             constrained_layout=True)
    axes = axes.flatten()
    for ax, (sc, label) in zip(axes, SCENARIO_LABELS.items()):
        sub = df[df["scenario"] == sc]
        for model in ["IDM", "CACC"]:
            d = sub[sub["model"] == model]
            if len(d) == 0:
                continue
            s = MODEL_STYLES[model]
            ax.scatter(d["flow_mean"], d["co2_per_k_mean"], s=15, alpha=0.5,
                       edgecolors="none", color=MODEL_COLORS[model],
                       marker=s["marker"], label=model)
        ax.set_title(label, fontsize=12)
        ax.set_xlabel("Flow (veh/h)", fontsize=10)
        ax.set_ylabel("CO₂ (g/veh-km)", fontsize=10)
        ax.set_xlim(x_min, x_max)
        ax.legend(fontsize=9); ax.grid(True, alpha=0.3)
    fig.suptitle("CO₂–Flow Trade-off", fontsize=14)
    path = out_dir / "chart_co2_flow.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {path}")


def chart_delay_v4(df: pd.DataFrame, out_dir: Path) -> None:
    """x=pCAV, y=delay_mean, vehN=120 only，四场景分面"""
    sub = df[df["vehN"] == 120]
    fig, axes = plt.subplots(2, 2, figsize=(16, 11), sharex=True, sharey=False,
                             constrained_layout=True)
    axes = axes.flatten()
    for ax, (sc, label) in zip(axes, SCENARIO_LABELS.items()):
        d = sub[sub["scenario"] == sc]
        for model in ["IDM", "CACC"]:
            dm = d[d["model"] == model].sort_values("pCAV")
            if len(dm) == 0:
                continue
            s = MODEL_STYLES[model]
            ax.plot(dm["pCAV"] * 100, dm["delay_mean"], marker=s["marker"],
                    linestyle=s["linestyle"], linewidth=s["linewidth"],
                    color=MODEL_COLORS[model], markersize=5, label=model, alpha=0.85)
        ax.set_title(f"{label} (vehN=120)", fontsize=12)
        ax.set_ylabel("Mean Lap Delay (s)", fontsize=10)
        ax.legend(fontsize=9); ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%d%%'))
        ax.tick_params(labelbottom=True)  # 所有面板显示 x 轴刻度
    axes[2].set_xlabel("CAV Penetration Rate", fontsize=11)
    axes[3].set_xlabel("CAV Penetration Rate", fontsize=11)
    fig.suptitle("Single-Lap Delay vs CAV Penetration Rate (vehN=120)", fontsize=14)
    path = out_dir / "chart_delay.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {path}")


def run_v4(args) -> None:
    if not os.path.exists(args.aggregated):
        print(f"错误: 找不到文件 {args.aggregated}")
        return
    df = pd.read_csv(args.aggregated)
    out_dir = Path(args.outDir)
    _ensure_dir(out_dir)
    chart_capacity_v4(df, out_dir)
    chart_safety_flow_v4(df, out_dir)
    chart_co2_flow_v4(df, out_dir)
    chart_delay_v4(df, out_dir)
    print(f"\n[DONE] 4 charts → {out_dir.resolve()}")


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="v0.4.0 数据可视化")
    # v0.3.0 参数
    parser.add_argument("--csv", default="out/results_raw_p05.csv",
                        help="v0.3.0 模式：批量仿真 CSV")
    parser.add_argument("--ring-length", type=float, default=None)
    parser.add_argument("--net", default=None,
                        help="路网文件路径，自动读取环路总长")
    # v0.4.0 参数
    parser.add_argument("--aggregated", default="results/aggregated_results.csv",
                        help="v0.4.0 模式：多种子聚合 CSV")
    parser.add_argument("--v4", action="store_true",
                        help="启用 v0.4.0 四组 trade-off 图表模式")
    # 通用
    parser.add_argument("--outDir", default="graph/v0.4.0",
                        help="输出目录")
    args = parser.parse_args()

    if args.v4:
        run_v4(args)
    else:
        run_v03(args)


if __name__ == "__main__":
    main()
