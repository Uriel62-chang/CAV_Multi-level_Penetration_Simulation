"""结果可视化（纯净分支：v0.4.1/v0.4.2 schema=2 聚合 CSV；v0.4.0 旧 CSV 经 --v4 兼容展示）。

v0.3.0 模式（默认）：
  python3 -m scripts.results.visualization --csv out/results_raw_p05.csv

v0.4.x 聚合模式：
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
# 审阅 P0-1（Safety 设计）：DRAC 空间配对事件率（全路网 DRAC 事件 / 全路网 veh-km）
_PAIRED_DRAC_METRIC = "drac_per_k_mean"


def _ttc_metric_column(df: pd.DataFrame) -> str:
    """--v4 路径：只接受空间配对列（纯净分支已移除 legacy post3 错配列回退）。

    v0.4.0~post3 的 whole_network_ttc_events_per_1000_non_internal_edge_veh_km
    （全路网事件 / non-internal-edge veh-km）为 A 线已修正的错误口径，head 数据
    一律用配对列；历史 post3 CSV 展示需 checkout v0.4.0.post3 tag。
    """
    if _PAIRED_TTC_METRIC in df.columns:
        return _PAIRED_TTC_METRIC
    raise ValueError(f"no TTC per-veh-km column in aggregated CSV; expected {_PAIRED_TTC_METRIC}")


def _paired_ttc_metric_column(df: pd.DataFrame) -> str:
    """v0.4.2 --safety 路径（P1-3）：只接受空间配对列，缺失 fail-closed。

    不回退到 legacy non-internal 错配列——那会重新生成 A 线已修正的错误口径。
    """
    if _PAIRED_TTC_METRIC in df.columns:
        return _PAIRED_TTC_METRIC
    raise ValueError(f"safety report requires space-matched column {_PAIRED_TTC_METRIC!r}")


def _assert_experiment_role(df: pd.DataFrame, expected: str) -> None:
    """审阅 P2-2：可视化入口校验 experiment_role——误把 main/safety CSV 传给错误
    模式时 fail-closed（而非生成空图/语义错误图）。CSV 无角色列时跳过（legacy 兼容）。"""
    if "experiment_role" not in df.columns:
        return
    roles = sorted(str(r) for r in df["experiment_role"].dropna().unique())
    if roles and roles != [expected]:
        raise ValueError(f"当前模式需要 experiment_role={expected!r} 的 CSV，实际含 {roles}")


def _paired_drac_metric_column(df: pd.DataFrame) -> str:
    """v0.4.2 --safety 路径（审阅 P0-1）：DRAC 空间配对事件率列，缺失 fail-closed。"""
    if _PAIRED_DRAC_METRIC in df.columns:
        return _PAIRED_DRAC_METRIC
    raise ValueError(f"safety report requires space-matched DRAC column {_PAIRED_DRAC_METRIC!r}")


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
        if ax.get_legend_handles_labels()[0]:
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
        if ax.get_legend_handles_labels()[0]:
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
        if ax.get_legend_handles_labels()[0]:
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
        if ax.get_legend_handles_labels()[0]:
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
    # P2-4（本轮审查）：旧入口同样加 experiment_role 门禁——误传 v0.4.2 safety
    # CSV 会渲染设计 §3.4 禁止的联合 trade-off 图（无角色列时跳过，legacy 兼容）。
    _assert_experiment_role(df, "main_factorial")
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
    _assert_experiment_role(df, "main_factorial")  # 审阅 P2-2：角色门禁
    out_dir = Path(args.outDir)
    _ensure_dir(out_dir)
    chart_observed_peak_flow_v4(df, out_dir)
    chart_co2_flow_v4(df, out_dir)
    chart_delay_v4(df, out_dir)
    print(f"\n[DONE] 3 charts (main factorial, no safety-flow trade-off) → {out_dir.resolve()}")


def run_safety_v4_2(args) -> None:
    """v0.4.2 safety 独立报告入口（P0-11）。

    生成 TTC 与 DRAC 事件率随渗透率（realized_pcav）变化的图（审阅 P0-1 补 DRAC；
    审阅 P1-1 四场景全分面，s1/s2 零检出边界一并展示），使用空间配对列
    （ttc_per_k_mean / drac_per_k_mean）；不生成与主 factorial 的联合 trade-off。
    P0（Reviewer 复检）：按 scenario × vehN 分面、model 分线——Safety 每渗透率有
    vehN={30,60,120} 三个点，不得在同一响应曲线中混合。
    """
    if not os.path.exists(args.aggregated):
        print(f"错误: 找不到文件 {args.aggregated}")
        return
    df = pd.read_csv(args.aggregated)
    _assert_experiment_role(df, "safety")  # 审阅 P2-2：角色门禁
    out_dir = Path(args.outDir)
    _ensure_dir(out_dir)
    ttc_col = _paired_ttc_metric_column(df)  # P1-3：fail-closed，不回退 legacy 错配列
    pen = _penetration_column(df)
    # 审阅 P1-1：四场景全分面（s1/s2 零事件检出也是正式结果，纳入图表边界展示）
    scenarios = ["scenario_0", "scenario_1", "scenario_2", "scenario_3"]
    vehn_levels = sorted(df["vehN"].dropna().unique().tolist())
    n_sc, n_vn = len(scenarios), len(vehn_levels)

    def _plot_safety_metric(metric_col: str, ylabel: str, out_name: str, metric_label: str):
        fig, axes = plt.subplots(
            n_sc, n_vn, figsize=(5.5 * max(n_vn, 1), 6.5 * n_sc), constrained_layout=True
        )

        def _get_ax(i: int, j: int):
            # matplotlib 对 1×1 / 1×N / N×1 布局的 axes 退化处理
            if isinstance(axes, np.ndarray):
                if axes.ndim == 2:
                    return axes[i, j]
                return axes[j] if n_sc == 1 else axes[i]
            return axes  # 单个 Axes

        for i, sc in enumerate(scenarios):
            sub = df[df["scenario"] == sc]
            for j, vn in enumerate(vehn_levels):
                ax = _get_ax(i, j)
                d = sub[sub["vehN"] == vn]
                ax.set_title(f"{sc} vehN={vn}" if not d.empty else f"{sc} vehN={vn} (no data)")
                ax.set_xlabel(f"{pen} (realized)")
                ax.set_ylabel(ylabel)
                if d.empty:
                    continue
                for model in ["IDM", "CACC"]:
                    m = d[d["model"] == model].sort_values(pen)
                    if not m.empty:
                        ax.plot(m[pen], m[metric_col], marker="o", label=model)
                if ax.get_legend_handles_labels()[0]:
                    ax.legend(fontsize=8)
        fig.savefig(out_dir / out_name, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"[safety] {metric_label} chart → {out_dir.resolve()}")

    _plot_safety_metric(
        ttc_col,
        "TTC events / 1000 veh-km (whole-network)",
        "chart_safety_events_by_penetration.png",
        "TTC",
    )
    # 审阅 P0-1（Safety 设计）：DRAC 空间配对事件率（全路网 DRAC 事件 / 全路网 veh-km）
    drac_col = _paired_drac_metric_column(df)
    _plot_safety_metric(
        drac_col,
        "DRAC events / 1000 veh-km (whole-network)",
        "chart_safety_drac_by_penetration.png",
        "DRAC",
    )
    print(
        f"\n[DONE] safety report (TTC + DRAC events by penetration, by vehN) → {out_dir.resolve()}"
    )


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="结果可视化（纯净分支）")
    # v0.3.0 参数
    parser.add_argument(
        "--csv", default="out/results_raw_p05.csv", help="v0.3.0 模式：批量仿真 CSV"
    )
    parser.add_argument("--ring-length", type=float, default=None)
    parser.add_argument("--net", default=None, help="路网文件路径，自动读取环路总长")
    # 聚合 CSV 展示参数（--v4 为历史模式名，保留目录约定 graph/v0.4.0）
    parser.add_argument(
        "--aggregated", default="results/aggregated_results.csv", help="多种子聚合 CSV"
    )
    parser.add_argument("--v4", action="store_true", help="启用四组 trade-off 图表模式")
    parser.add_argument(
        "--v4-2",
        action="store_true",
        help="启用 v0.4.2 main-factorial 报告模式（不生成 safety-flow trade-off）",
    )
    parser.add_argument(
        "--safety",
        action="store_true",
        help="启用 v0.4.2 safety 独立报告模式（TTC + DRAC 事件率随渗透率、"
        "四场景全分面，使用空间配对列 ttc_per_k_mean / drac_per_k_mean）",
    )
    # 通用
    parser.add_argument(
        "--outDir",
        default=None,
        help="输出目录（默认：--v4 → graph/v0.4.0；--v4-2 → graph/v0.4.2；"
        "--safety → graph/v0.4.2/safety，P2-2 防版本混放）",
    )
    args = parser.parse_args()

    # 审阅 P2-2：--safety / --v4-2 / --v4 互斥——不得静默按固定优先级执行
    modes = [
        name
        for name, flag in (("--safety", args.safety), ("--v4-2", args.v4_2), ("--v4", args.v4))
        if flag
    ]
    if len(modes) > 1:
        parser.error(f"互斥选项：{'、'.join(modes)} 只能同时指定一个（当前传入 {len(modes)} 个）")

    if args.outDir is None:
        if args.safety:
            args.outDir = "graph/v0.4.2/safety"  # 审阅 P2-2：safety 归档层级
        elif args.v4_2:
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
