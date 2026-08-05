"""结果可视化（纯净分支：仅 v0.4.2 schema=2 聚合 CSV；v0.3 旧模式已退役）。

v0.4.2 聚合模式（--v4-2，唯一入口）：
  python3 -m scripts.results.visualization --aggregated out/aggregated_results.csv --v4-2
"""

import argparse
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
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
    """v0.3.0 模式（已退役，fail-closed）。

    收敛审核 P1（Phase 3 加固）：纯净分支仅保留 v0.4.2 schema=2 聚合——v0.3.0
    数据已清空、schema=1 契约已移除，旧模式对 schema=2 CSV 会抛裸 KeyError；
    改为显式报错提示唯一入口 --v4-2。
    """
    raise SystemExit(
        "v0.3.0 模式已退役（纯净分支仅支持 v0.4.2 schema=2 聚合 CSV）："
        "请使用 --v4-2 模式：python3 -m scripts.results.visualization "
        "--aggregated out/aggregated_results.csv --v4-2"
    )


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
    """v0.4.2 路径：只接受空间配对列（纯净分支已移除 legacy post3 错配列回退）。

    v0.4.0~post3 的 whole_network_ttc_events_per_1000_non_internal_edge_veh_km
    （全路网事件 / non-internal-edge veh-km）为 A 线已修正的错误口径，head 数据
    一律用配对列；历史 post3 CSV 展示需 checkout v0.4.0.post3 tag。
    """
    if _PAIRED_TTC_METRIC in df.columns:
        return _PAIRED_TTC_METRIC
    raise ValueError(f"no TTC per-veh-km column in aggregated CSV; expected {_PAIRED_TTC_METRIC}")


def _assert_experiment_role(df: pd.DataFrame, expected: str) -> None:
    """审阅 P2-2：可视化入口校验 experiment_role——误把 main/safety CSV 传给错误
    模式时 fail-closed（而非生成空图/语义错误图）。CSV 无角色列时跳过（legacy 兼容）。"""
    if "experiment_role" not in df.columns:
        return
    roles = sorted(str(r) for r in df["experiment_role"].dropna().unique())
    if roles and roles != [expected]:
        raise ValueError(f"当前模式需要 experiment_role={expected!r} 的 CSV，实际含 {roles}")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _penetration_column(df: pd.DataFrame) -> str:
    """v0.4.2 绘图横轴：realized_pcav 优先（count 网格下恒等于设计渗透率且非空）；
    pCAV 为最旧兼容。纯净分支无 requested_pcav 契约列（legacy requested-grid 已删）。"""
    for col in ("realized_pcav", "pCAV"):
        if col in df.columns:
            return col
    raise ValueError("no penetration column (realized_pcav/pCAV) in dataframe")


def _flow_metric_column(df: pd.DataFrame) -> str:
    """收敛审核 P0（FD 口径）：流量指标取每车道口径（flow_per_lane，双车道已
    归一化）；旧聚合 CSV 无该列时回退 flow_mean（车道总和）。"""
    if "flow_per_lane" in df.columns:
        return "flow_per_lane"
    return "flow_mean"


def chart_observed_peak_flow_v4(df: pd.DataFrame, out_dir: Path) -> None:
    """x=pCAV, y=每个 pCAV 下最高 flow（每车道口径），四场景分面"""
    penetration_column = _penetration_column(df)
    flow_col = _flow_metric_column(df)
    observed_peaks = (
        df.groupby(["scenario", "model", penetration_column])[flow_col].max().reset_index()
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
                d[flow_col],
                marker=s["marker"],
                linestyle=s["linestyle"],
                linewidth=s["linewidth"],
                color=MODEL_COLORS[model],
                markersize=5,
                label=model,
                alpha=0.85,
            )
        ax.set_title(label, fontsize=12)
        ax.set_ylabel("Maximum Observed Flow in Tested Grid (veh/h/lane)", fontsize=10)
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


def chart_co2_flow_v4(df: pd.DataFrame, out_dir: Path) -> None:
    """x=flow_per_lane, y=co2_per_k_mean，四场景分面，x 轴统一"""
    flow_col = _flow_metric_column(df)
    x_min = df[flow_col].min() * 0.95
    x_max = df[flow_col].max() * 1.05
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
                d[flow_col],
                d["co2_per_k_mean"],
                s=15,
                alpha=0.5,
                edgecolors="none",
                color=MODEL_COLORS[model],
                marker=s["marker"],
                label=model,
            )
        ax.set_title(label, fontsize=12)
        ax.set_xlabel("Flow (veh/h/lane)", fontsize=10)
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


# 审查 P2-3：网格 cav_count 实为 0.1 步长 11 档，此处取 6 个代表档显示（0.2 步长）
# 避免 22 条线不可读；p=0.0 时仅 IDM 有线（cav=0 为全 HV 运行、model=IDM sentinel）。
_PENETRATION_LEVELS = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
_PENETRATION_CMAP = "viridis"


def _fd_panel(ax, d: pd.DataFrame, flow_col: str, with_legend: bool = True) -> None:
    """FD 单场景面板：每条线 = (model, 渗透率档)——渗透率用颜色渐变（viridis
    0→1.0 浅→深）、模型用线型区分；设计声明"FD 峰位随 cav_count 连续移动
    （HV kc≈17.4 → CACC kc≈39.2）"由分线直接可读。"""
    cmap = plt.get_cmap(_PENETRATION_CMAP)
    for model in ["IDM", "CACC"]:
        for p_idx, p in enumerate(_PENETRATION_LEVELS):
            dm = d[(d["model"] == model) & (d["cav_count"] / d["vehN"] - p).abs() < 1e-9]
            dm = dm.sort_values("density_veh_per_km_lane")
            if len(dm) == 0:
                continue
            style = MODEL_STYLES[model]
            ax.plot(
                dm["density_veh_per_km_lane"],
                dm[flow_col],
                marker=style["marker"],
                linestyle=style["linestyle"],
                linewidth=style["linewidth"],
                color=cmap(p_idx / (len(_PENETRATION_LEVELS) - 1)),
                markersize=4,
                alpha=0.85,
                label=f"{model} p={p:.1f}" if with_legend else None,
            )
    ax.axhline(2400, color="gray", linestyle=":", linewidth=1, alpha=0.7)
    ax.axvline(17.4, color="gray", linestyle=":", linewidth=1, alpha=0.7)
    ax.set_xlabel("Density (veh/km/lane)", fontsize=10)
    ax.set_ylabel("Flow per Lane (veh/h/lane)", fontsize=10)
    ax.grid(True, alpha=0.3)
    if with_legend:
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(fontsize=7, ncol=2)


def chart_fundamental_diagram_v4(df: pd.DataFrame, out_dir: Path) -> None:
    """基本图（审查 P1-1）：x=密度(veh/km/道)、y=每车道流量(veh/h/lane)。

    口径封闭：密度列 density_veh_per_km_lane（aggregate 按 vehN/车道数/2km 生成）、
    流量列 flow_per_lane（每车道）。主图 s0/s1/s2 三面板（s3 瓶颈排队–吞吐语义
    与主线基本图不可比，单独成图并标注瓶颈）；每条线 = (model, 渗透率档)，
    峰位随 cav_count 移动可读。标注理论参考线（HV q_max≈2400 veh/h/道、
    kc≈17.4 veh/km/道）。
    """
    if "density_veh_per_km_lane" not in df.columns:
        raise ValueError("聚合 CSV 缺 density_veh_per_km_lane 列——请用当前 aggregate 重生成")
    flow_col = _flow_metric_column(df)
    main_scenarios = ["scenario_0", "scenario_1", "scenario_2"]
    fig, axes = plt.subplots(
        1, 3, figsize=(18, 6), sharex=False, sharey=False, constrained_layout=True
    )
    for ax, sc in zip(axes, main_scenarios, strict=True):
        ax.set_title(f"{SCENARIO_LABELS[sc]}", fontsize=12)
        _fd_panel(ax, df[df["scenario"] == sc], flow_col)
    fig.suptitle("Fundamental Diagram (per-lane flow vs density, by CAV penetration)", fontsize=14)
    path = out_dir / "chart_fundamental_diagram.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {path}")

    # s3 单独成图（设计 §三.5：瓶颈排队–吞吐关系，标注瓶颈语义）
    fig3, ax3 = plt.subplots(figsize=(9, 6), constrained_layout=True)
    ax3.set_title(f"{SCENARIO_LABELS['scenario_3']} (bottleneck queue-throughput)", fontsize=12)
    _fd_panel(ax3, df[df["scenario"] == "scenario_3"], flow_col)
    ax3.text(
        0.5,
        -0.18,
        "s3：e15/e16 单车道 125 m 瓶颈，FD 为瓶颈排队–吞吐关系（非主线基本图），"
        "与 s0/s1/s2 不可直接比较",
        transform=ax3.transAxes,
        ha="center",
        fontsize=9,
        color="gray",
    )
    path3 = out_dir / "chart_fundamental_diagram_s3.png"
    fig3.savefig(path3, dpi=150, bbox_inches="tight")
    plt.close(fig3)
    print(f"[OK] {path3}")


def chart_delay_v4(
    df: pd.DataFrame,
    out_dir: Path,
    vehN: int | None = None,
    target_density: float = 30.0,
) -> None:
    """x=渗透率, y=相对固定参考圈时的有符号差。

    审阅 P2-5：默认按**场景密度对齐**取档——target_density（veh/km/道，默认
    30）→ s0/s1 单车道 vehN=density×2、s2/s3 双车道 vehN=density×4；避免
    "vehN 相同但跨场景密度不同"（s0/s1 v60=30 veh/km/道 vs s2/s3 v60=15）。
    --delay-vehN 显式传值时以 vehN 为准。
    """
    lane_map = {"scenario_0": 1, "scenario_1": 1, "scenario_2": 2, "scenario_3": 2}
    penetration_column = _penetration_column(df)
    fig, axes = plt.subplots(
        2, 2, figsize=(16, 11), sharex=True, sharey=False, constrained_layout=True
    )
    axes = axes.flatten()
    for ax, (sc, label) in zip(axes, SCENARIO_LABELS.items(), strict=True):
        eff_vehN = vehN if vehN is not None else int(target_density * lane_map[sc] * 2)
        d = df[(df["scenario"] == sc) & (df["vehN"] == eff_vehN)]
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
        ax.set_title(f"{label} (vehN={eff_vehN}, {target_density:.0f} veh/km/lane)", fontsize=12)
        ax.set_ylabel("Mean Lap-Time Difference From Reference (s)", fontsize=10)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%d%%"))
        ax.tick_params(labelbottom=True)  # 所有面板显示 x 轴刻度
    axes[2].set_xlabel("CAV Penetration Rate", fontsize=11)
    axes[3].set_xlabel("CAV Penetration Rate", fontsize=11)
    fig.suptitle(
        f"Lap-Time Difference From Fixed Reference vs CAV Penetration (vehN={vehN})",
        fontsize=14,
    )
    path = out_dir / "chart_delay.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {path}")


def run_v4_2(args) -> None:
    """v0.4.2 main-factorial 报告入口（P0-6）。

    合并设计（2026-08）：安全维度已并入主网格（SSM 采集随主网格），不再有独立
    safety 报告板块。"""
    if not os.path.exists(args.aggregated):
        print(f"错误: 找不到文件 {args.aggregated}")
        return
    df = pd.read_csv(args.aggregated)
    _assert_experiment_role(df, "main_factorial")  # 审阅 P2-2：角色门禁
    out_dir = Path(args.outDir)
    _ensure_dir(out_dir)
    chart_observed_peak_flow_v4(df, out_dir)
    chart_co2_flow_v4(df, out_dir)
    chart_fundamental_diagram_v4(df, out_dir)
    # 审阅 P2-5：默认按场景密度对齐取档（target_density=30 veh/km/道）；
    # --delay-vehN 显式传值时以 vehN 为准；getattr 兜底仅防程序化调用缺属性。
    chart_delay_v4(df, out_dir, getattr(args, "delay_vehN", None))
    print(f"\n[DONE] 5 charts (main factorial, no safety-flow trade-off) → {out_dir.resolve()}")


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
    # 聚合 CSV 展示参数（--v4-2 为 v0.4.2 报告模式）
    parser.add_argument(
        "--aggregated",
        default="out/aggregated_results.csv",
        help="多种子聚合 CSV（默认 out/aggregated_results.csv；v0.4.2 旧结果路径已随数据清空退役）",
    )
    parser.add_argument(
        "--v4-2",
        action="store_true",
        help="启用 v0.4.2 main-factorial 报告模式（合并设计：安全维度已并入主网格）",
    )
    parser.add_argument(
        "--delay-vehN",
        type=int,
        default=None,
        help="delay 图固定 vehN 档（默认按场景密度对齐取档：30 veh/km/道 → "
        "s0/s1 vehN=60、s2/s3 vehN=120，跨场景密度一致）",
    )
    # 通用
    parser.add_argument(
        "--outDir",
        default=None,
        help="输出目录（默认：--v4-2 → graph/v0.4.2）",
    )
    args = parser.parse_args()

    if args.outDir is None:
        if args.v4_2:
            args.outDir = "graph/v0.4.2"
        else:
            args.outDir = "graph/v0.3"  # v0.3 旧模式默认输出目录

    if args.v4_2:
        run_v4_2(args)
    else:
        run_v03(args)


if __name__ == "__main__":
    main()
