"""v0.4.0 数据可视化 —— 兼容 v0.3.0 基本图 + v0.4.0 四组 trade-off 图表。

v0.3.0 模式（默认）：
  python3 -m scripts.results.visualization --csv out/results_raw_p05.csv

v0.4.0 模式：
  python3 -m scripts.results.visualization --aggregated results/aggregated_results.csv --v4
"""

import argparse
import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

RING_LENGTH_KM = 2.0  # 环路长度 (km)，v0.3.0 兼容


# ═══════════════════════════════════════════════════════════════════
# v0.3.0 兼容：密度-流量基本图 + 网格内观测峰值汇总
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


def compute_observed_peaks(aggregated: pd.DataFrame, cav_ratios: list):
    observed_peaks = []
    for ratio in cav_ratios:
        subset = aggregated[aggregated["pCAV"] == ratio]
        peak_row = subset["mean_flow(veh/h)"].idxmax()
        observed_peaks.append(
            {
                "cav_ratio": ratio,
                "peak_flow": subset.loc[peak_row, "mean_flow(veh/h)"],
                "peak_density": subset.loc[peak_row, "density"],
            }
        )
    return observed_peaks


def plot_density_flow(
    ratio: float,
    density: pd.Series,
    flow: pd.Series,
    peak_density: float,
    peak_flow: float,
    output_dir: str,
):
    plt.figure(figsize=(10, 5))
    plt.plot(density, flow, marker="o", color="blue", label="Flow", linewidth=2, linestyle="-")
    plt.plot(
        peak_density,
        peak_flow,
        marker="*",
        markersize=12,
        color="red",
        label="Maximum Observed Flow",
    )
    plt.title(
        f"Density-Flow Curve (requested CAV penetration: {int(ratio * 100)}%)",
        fontsize=20,
    )
    plt.xlabel("Density (veh/km)", fontsize=15)
    plt.ylabel("Flow (veh/h)", fontsize=15)
    plt.xlim(0, density.max() * 1.1)
    plt.ylim(0, peak_flow * 1.1)
    for x, y in zip(density, flow, strict=True):
        plt.text(x, y, str(y), ha="center", va="bottom")
    plt.legend(loc="upper left")
    plt.grid(axis="y")
    save_path = os.path.join(output_dir, f"fd_p{int(ratio * 100):03d}.png")
    plt.savefig(save_path)
    print(f"[OK] {int(ratio * 100)}%渗透率的[密度-流量]曲线已成功保存至{save_path}")
    plt.close()


def plot_observed_peak_summary(observed_peaks: list, output_dir: str):
    plt.figure(figsize=(10, 5))
    cav_percentages = [item["cav_ratio"] * 100 for item in observed_peaks]
    observed_peak_values = [item["peak_flow"] for item in observed_peaks]
    plt.plot(
        cav_percentages,
        observed_peak_values,
        marker="o",
        markersize=8,
        label="Maximum Observed Flow",
        color="blue",
        linewidth=2,
        linestyle="-",
    )
    grid_maximum = max(observed_peak_values)
    max_index = observed_peak_values.index(grid_maximum)
    max_percentage = cav_percentages[max_index]
    plt.plot(
        max_percentage,
        grid_maximum,
        marker="*",
        markersize=12,
        color="red",
        linestyle="None",
        label="Grid Maximum",
    )
    plt.title("CAV Penetration vs Maximum Observed Flow", fontsize=20)
    plt.xlabel("CAV Penetration Rate (%)", fontsize=15)
    plt.ylabel("Maximum Observed Flow in Tested Grid (veh/h)", fontsize=15)
    plt.ylim(0, grid_maximum * 1.1)
    for x, y in zip(cav_percentages, observed_peak_values, strict=True):
        if y == grid_maximum:
            plt.text(x, y, f"({x}, {y})", ha="center", va="bottom")
    plt.legend(loc="upper left")
    plt.grid(axis="y")
    os.makedirs(output_dir, exist_ok=True)
    save_path = os.path.join(output_dir, "Observed_peak_flow_summary.png")
    plt.savefig(save_path)
    print(f"[OK] [CAV渗透率-网格内最大观测流量]曲线已成功保存至{save_path}")
    plt.close()


def run_v03(args) -> None:
    ring_length_km = RING_LENGTH_KM
    if args.ring_length is not None:
        ring_length_km = args.ring_length
    elif args.net is not None:
        net_dir = os.path.dirname(args.net)
        meta_path = os.path.join(net_dir, "net.json")
        if os.path.isfile(meta_path):
            with open(meta_path, encoding="utf-8") as f:
                ring_length_km = json.load(f).get("total_length_km", RING_LENGTH_KM)
            print(f"从 {meta_path} 读取环路总长: {ring_length_km} km")

    aggregated, cav_ratios = load_and_aggregate(args.csv, ring_length_km)
    if aggregated is None:
        return
    os.makedirs(args.outDir, exist_ok=True)
    observed_peaks = compute_observed_peaks(aggregated, cav_ratios)
    for observed_peak in observed_peaks:
        subset = aggregated[aggregated["pCAV"] == observed_peak["cav_ratio"]]
        plot_density_flow(
            observed_peak["cav_ratio"],
            subset["density"],
            subset["mean_flow(veh/h)"],
            observed_peak["peak_density"],
            observed_peak["peak_flow"],
            args.outDir,
        )
    plot_observed_peak_summary(observed_peaks, args.outDir)


# ═══════════════════════════════════════════════════════════════════
# v0.4.0：四组 trade-off 图表
# ═══════════════════════════════════════════════════════════════════

SCENARIO_LABELS = {
    "scenario_0": "s0 (square ring)",
    "scenario_1": "s1 (32-gon single-lane)",
    "scenario_2": "s2 (dual-lane)",
    "scenario_3": "s3 (bottleneck)",
}
# 模型配色：同面板内两模型需一眼可辨，使用高对比色
MODEL_COLORS = {"IDM": "#2166ac", "CACC": "#b2182b"}  # 蓝 vs 红
MODEL_STYLES = {
    "IDM": {"marker": "o", "linestyle": "-", "linewidth": 1.5},
    "CACC": {"marker": "s", "linestyle": "--", "linewidth": 1.5},
}

# v0.4.2 withInternal=true 下空间配对列：全路网 TTC 事件 / 全路网 veh-km
_PAIRED_TTC_METRIC = "ttc_per_k_mean"
# legacy post3 错配列：全路网事件 / non-internal-edge veh-km（仅兼容旧 CSV，不得优先）
_LEGACY_MISMATCHED_TTC_METRIC = "whole_network_ttc_events_per_1000_non_internal_edge_veh_km_mean"


def _ttc_metric_column(df: pd.DataFrame) -> str:
    """优先使用空间配对列（全路网事件/全路网 veh-km，P0-3/A 线要求）；
    旧 non-internal 口径列仅作 legacy CSV 兼容 fallback。"""
    for col in (_PAIRED_TTC_METRIC, _LEGACY_MISMATCHED_TTC_METRIC):
        if col in df.columns:
            return col
    raise ValueError(f"no TTC per-veh-km column in aggregated CSV; expected {_PAIRED_TTC_METRIC}")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _penetration_column(df: pd.DataFrame) -> str:
    """v0.4.2 绘图横轴：realized_pcav 优先（count 网格下恒等于设计渗透率且非空）；
    requested_pcav 仅 legacy requested-grid 使用；pCAV 为最旧兼容。"""
    for col in ("realized_pcav", "requested_pcav", "pCAV"):
        if col in df.columns:
            return col
    raise ValueError("no penetration column (realized_pcav/requested_pcav/pCAV) in dataframe")


def chart_observed_peak_flow_v4(df: pd.DataFrame, out_dir: Path) -> None:
    """x=pCAV, y=每个 pCAV 下最高 flow，四场景分面"""
    penetration_column = _penetration_column(df)
    observed_peaks = (
        df.groupby(["scenario", "model", penetration_column])["flow_mean"].max().reset_index()
    )
    fig, axes = plt.subplots(
        2, 2, figsize=(16, 11), sharex=True, sharey=False, constrained_layout=True
    )
    axes = axes.flatten()
    for ax, (sc, label) in zip(axes, SCENARIO_LABELS.items(), strict=True):
        sub = observed_peaks[observed_peaks["scenario"] == sc]
        for model in ["IDM", "CACC"]:
            d = sub[sub["model"] == model].sort_values(penetration_column)
            if len(d) == 0:
                continue
            s = MODEL_STYLES[model]
            ax.plot(
                d[penetration_column] * 100,
                d["flow_mean"],
                marker=s["marker"],
                linestyle=s["linestyle"],
                linewidth=s["linewidth"],
                color=MODEL_COLORS[model],
                markersize=5,
                label=model,
                alpha=0.85,
            )
        ax.set_title(label, fontsize=12)
        ax.set_ylabel("Maximum Observed Flow in Tested Grid (veh/h)", fontsize=10)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%d%%"))
        ax.tick_params(labelbottom=True)  # 所有面板显示 x 轴刻度
    axes[2].set_xlabel("CAV Penetration Rate", fontsize=11)
    axes[3].set_xlabel("CAV Penetration Rate", fontsize=11)
    fig.suptitle("CAV Penetration vs Maximum Observed Flow", fontsize=14)
    path = out_dir / "chart_capacity.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {path}")


def chart_safety_flow_v4(df: pd.DataFrame, out_dir: Path) -> None:
    """x=flow_mean, y=全路网 TTC / 普通-edge 暴露量，s0+s3 双面板"""
    ttc_metric = _ttc_metric_column(df)
    fig, axes = plt.subplots(1, 2, figsize=(16, 7), constrained_layout=True)
    for ax, sc in zip(axes, ["scenario_0", "scenario_3"], strict=True):
        sub = df[df["scenario"] == sc]
        for model in ["IDM", "CACC"]:
            d = sub[sub["model"] == model]
            if len(d) == 0:
                continue
            s = MODEL_STYLES[model]
            sizes = np.clip(d["vehN"] / 2, 10, 120)
            ax.scatter(
                d["flow_mean"],
                d[ttc_metric],
                s=sizes,
                alpha=0.6,
                edgecolors="white",
                linewidth=0.3,
                color=MODEL_COLORS[model],
                marker=s["marker"],
                label=model,
            )
        ax.set_title(SCENARIO_LABELS.get(sc, sc), fontsize=12)
        ax.set_xlabel("Flow (veh/h)", fontsize=10)
        ax.set_ylabel("TTC Events / 1000 Non-internal-edge veh-km", fontsize=10)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
    fig.suptitle("Safety–Flow Trade-off: TTC Events per Non-internal-edge Exposure", fontsize=14)
    path = out_dir / "chart_safety_flow.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {path}")


def chart_co2_flow_v4(df: pd.DataFrame, out_dir: Path) -> None:
    """x=flow_mean, y=co2_per_k_mean，四场景分面，x 轴统一"""
    x_min = df["flow_mean"].min() * 0.95
    x_max = df["flow_mean"].max() * 1.05
    fig, axes = plt.subplots(
        2, 2, figsize=(16, 11), sharex=False, sharey=False, constrained_layout=True
    )
    axes = axes.flatten()
    for ax, (sc, label) in zip(axes, SCENARIO_LABELS.items(), strict=True):
        sub = df[df["scenario"] == sc]
        for model in ["IDM", "CACC"]:
            d = sub[sub["model"] == model]
            if len(d) == 0:
                continue
            s = MODEL_STYLES[model]
            ax.scatter(
                d["flow_mean"],
                d["co2_per_k_mean"],
                s=15,
                alpha=0.5,
                edgecolors="none",
                color=MODEL_COLORS[model],
                marker=s["marker"],
                label=model,
            )
        ax.set_title(label, fontsize=12)
        ax.set_xlabel("Flow (veh/h)", fontsize=10)
        ax.set_ylabel("CO₂ on Non-internal Edges (g/veh-km)", fontsize=10)
        ax.set_xlim(x_min, x_max)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
    fig.suptitle("Non-internal-edge CO₂–Flow Trade-off", fontsize=14)
    path = out_dir / "chart_co2_flow.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {path}")


def chart_delay_v4(df: pd.DataFrame, out_dir: Path) -> None:
    """x=渗透率, y=相对固定参考圈时的有符号差，vehN=120。"""
    sub = df[df["vehN"] == 120]
    penetration_column = _penetration_column(df)
    fig, axes = plt.subplots(
        2, 2, figsize=(16, 11), sharex=True, sharey=False, constrained_layout=True
    )
    axes = axes.flatten()
    for ax, (sc, label) in zip(axes, SCENARIO_LABELS.items(), strict=True):
        d = sub[sub["scenario"] == sc]
        for model in ["IDM", "CACC"]:
            dm = d[d["model"] == model].sort_values(penetration_column)
            if len(dm) == 0:
                continue
            s = MODEL_STYLES[model]
            ax.plot(
                dm[penetration_column] * 100,
                dm["delay_mean"],
                marker=s["marker"],
                linestyle=s["linestyle"],
                linewidth=s["linewidth"],
                color=MODEL_COLORS[model],
                markersize=5,
                label=model,
                alpha=0.85,
            )
        ax.set_title(f"{label} (vehN=120)", fontsize=12)
        ax.set_ylabel("Mean Lap-Time Difference From Reference (s)", fontsize=10)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%d%%"))
        ax.tick_params(labelbottom=True)  # 所有面板显示 x 轴刻度
    axes[2].set_xlabel("CAV Penetration Rate", fontsize=11)
    axes[3].set_xlabel("CAV Penetration Rate", fontsize=11)
    fig.suptitle(
        "Lap-Time Difference From Fixed Reference vs CAV Penetration (vehN=120)",
        fontsize=14,
    )
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
    chart_observed_peak_flow_v4(df, out_dir)
    chart_safety_flow_v4(df, out_dir)
    chart_co2_flow_v4(df, out_dir)
    chart_delay_v4(df, out_dir)
    print(f"\n[DONE] 4 charts → {out_dir.resolve()}")


def run_v4_2(args) -> None:
    """v0.4.2 main-factorial 报告入口（P0-6）。

    不生成 Safety–Flow trade-off 曲线（分拆设计 §3.4 禁止把两实验拼成联合 trade-off）；
    Safety 事件率仅由独立 safety 报告使用空间配对列。"""
    if not os.path.exists(args.aggregated):
        print(f"错误: 找不到文件 {args.aggregated}")
        return
    df = pd.read_csv(args.aggregated)
    out_dir = Path(args.outDir)
    _ensure_dir(out_dir)
    chart_observed_peak_flow_v4(df, out_dir)
    chart_co2_flow_v4(df, out_dir)
    chart_delay_v4(df, out_dir)
    print(f"\n[DONE] 3 charts (main factorial, no safety-flow trade-off) → {out_dir.resolve()}")


def run_safety_v4_2(args) -> None:
    """v0.4.2 safety 独立报告入口（P0-11）。

    生成 TTC 事件率随渗透率（realized_pcav）变化的图（仅 TTC、仅 scenario_0/scenario_3
    两个有事件集中度的场景），使用空间配对列；不生成与主 factorial 的联合 trade-off。
    注意：本实现不覆盖 DRAC 与四场景，文档/help 表述与此一致（P1-3）。
    """
    if not os.path.exists(args.aggregated):
        print(f"错误: 找不到文件 {args.aggregated}")
        return
    df = pd.read_csv(args.aggregated)
    out_dir = Path(args.outDir)
    _ensure_dir(out_dir)
    ttc_col = _ttc_metric_column(df)
    pen = _penetration_column(df)
    fig, axes = plt.subplots(1, 2, figsize=(16, 7), constrained_layout=True)
    for ax, sc in zip(axes, ["scenario_0", "scenario_3"], strict=True):
        sub = df[df["scenario"] == sc]
        for model in ["IDM", "CACC"]:
            d = sub[sub["model"] == model].sort_values(pen)
            ax.plot(d[pen], d[ttc_col], marker="o", label=model)
        ax.set_xlabel(f"{pen} (realized)")
        ax.set_ylabel("TTC events / 1000 veh-km (whole-network, space-matched)")
        ax.set_title(f"{sc} safety")
        ax.legend()
    fig.savefig(out_dir / "chart_safety_events_by_penetration.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n[DONE] safety report (TTC events by penetration) → {out_dir.resolve()}")


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="v0.4.0 数据可视化")
    # v0.3.0 参数
    parser.add_argument(
        "--csv", default="out/results_raw_p05.csv", help="v0.3.0 模式：批量仿真 CSV"
    )
    parser.add_argument("--ring-length", type=float, default=None)
    parser.add_argument("--net", default=None, help="路网文件路径，自动读取环路总长")
    # v0.4.0 参数
    parser.add_argument(
        "--aggregated", default="results/aggregated_results.csv", help="v0.4.0 模式：多种子聚合 CSV"
    )
    parser.add_argument("--v4", action="store_true", help="启用 v0.4.0 四组 trade-off 图表模式")
    parser.add_argument(
        "--v4-2",
        action="store_true",
        help="启用 v0.4.2 main-factorial 报告模式（不生成 safety-flow trade-off）",
    )
    parser.add_argument(
        "--safety",
        action="store_true",
        help="启用 v0.4.2 safety 独立报告模式（仅 TTC 事件率随渗透率、仅 scenario_0/scenario_3，"
        "使用空间配对列 ttc_per_k_mean）",
    )
    # 通用
    parser.add_argument(
        "--outDir",
        default=None,
        help="输出目录（默认：--v4 → graph/v0.4.0；--v4-2/--safety → graph/v0.4.2，P2-2 防版本混放）",
    )
    args = parser.parse_args()

    if args.outDir is None:
        if args.v4_2 or args.safety:
            args.outDir = "graph/v0.4.2"  # P2-2：v0.4.2 报告不与 v0.4.0 结果混放
        else:
            args.outDir = "graph/v0.4.0"

    if args.safety:
        run_safety_v4_2(args)
    elif args.v4_2:
        run_v4_2(args)
    elif args.v4:
        run_v4(args)
    else:
        run_v03(args)


if __name__ == "__main__":
    main()
