import argparse
import os
import pandas as pd
import matplotlib.pyplot as plt

RING_LENGTH_KM = 2.0  # 环路长度 (km)，用于计算密度
CAPACITY_SUMMARY_PATH = "graph/Capacity_summary.png"


def load_and_aggregate(csv_path: str):
    # 1. 检查文件是否存在
    if not os.path.exists(csv_path):
        print(f"错误: 找不到文件 {csv_path}")
        if os.path.isdir("out"):
            csv_files = [f for f in os.listdir("out") if f.endswith(".csv")]
            if csv_files:
                print(f"out/ 目录中现有 csv 文件: {', '.join(csv_files)}")
                print(f"提示: 使用 --csv 指定对应文件，如 --csv out/{csv_files[0]}")
            else:
                print("out/ 目录为空，请先运行 batch.py 生成数据。")
        else:
            print("请确保你已经运行了 batch.py 并生成了数据。")
        return None, None

    # 2. 读取数据
    print(f"正在读取数据: {csv_path} ...")
    data = pd.read_csv(csv_path)
    # 计算密度 k = N / L (veh/km)
    data["density"] = data["vehN"] / RING_LENGTH_KM

    # 分组聚类（以"渗透率"、"车辆数"、"密度"为依据——对多个随机种子的车流取平均流量）
    aggregated = data.groupby(["pCAV", "vehN", "density"])["mean_flow(veh/h)"].mean().reset_index()
    # 排序、去重后收集所有情况的渗透率
    cav_ratios = sorted(aggregated["pCAV"].unique())
    return aggregated, cav_ratios


def compute_capacities(aggregated: pd.DataFrame, cav_ratios: list):
    # 存储通行能力的列表
    capacities = []
    # 遍历所有渗透率
    for ratio in cav_ratios:
        # 筛出渗透率对应的DataFrame
        subset = aggregated[aggregated["pCAV"] == ratio]
        # 记录当前渗透率的通行能力
        peak_row = subset["mean_flow(veh/h)"].idxmax()
        peak_flow = subset.loc[peak_row, "mean_flow(veh/h)"]
        peak_density = subset.loc[peak_row, "density"]
        capacities.append({
            "cav_ratio": ratio,
            "peak_flow": peak_flow,
            "peak_density": peak_density,
        })
    return capacities


def plot_density_flow(ratio: float, density: pd.Series, flow: pd.Series,
                      peak_density: float, peak_flow: float, output_dir: str):
    # 框定画布大小
    plt.figure(figsize=(10, 5))

    # 绘制密度-流量曲线
    plt.plot(density, flow, marker="o", color="blue", label="Flow", linewidth=2, linestyle="-")
    # 在图中标注出峰值流量（即该渗透率下的通行能力）
    plt.plot(peak_density, peak_flow, marker="*", markersize=12, color="red", label="Capacity")

    plt.title(f"Density-Flow Curve (CAV penetration rate: {int(ratio * 100)}%)", fontsize=20)
    plt.xlabel("Density (veh/km)", fontsize=15)
    plt.ylabel("Flow (veh/h)", fontsize=15)
    plt.xlim(0, 70)
    plt.ylim(0, 3000)

    # 显示折点的y值
    for x, y in zip(density, flow):
        plt.text(x, y, str(y), ha="center", va="bottom")

    plt.legend(loc="upper left")
    plt.grid(axis="y")

    save_path = os.path.join(output_dir, f"fd_p{int(ratio * 100):03d}.png")
    plt.savefig(save_path)
    print(f"[OK] {int(ratio * 100)}%渗透率的[密度-流量]曲线已成功保存至{save_path}")
    plt.close()


def plot_capacity_summary(capacities: list):
    # 绘制CAV渗透率-通行能力曲线
    # 框定画布大小
    plt.figure(figsize=(10, 5))

    # 选取x轴、y轴元素
    cav_percentages = [c["cav_ratio"] * 100 for c in capacities]  # x轴：渗透率
    capacity_values = [c["peak_flow"] for c in capacities]  # y轴：对应的通行能力

    # 绘制折线图
    plt.plot(cav_percentages, capacity_values, marker="o", markersize=8,
             label="Capacity", color="blue", linewidth=2, linestyle="-")

    # 找出全局最大值
    max_capacity = max(capacity_values)
    max_index = capacity_values.index(max_capacity)
    max_percentage = cav_percentages[max_index]
    # 在图中标出最大通行能力
    plt.plot(max_percentage, max_capacity, marker="*", markersize=12,
             color="red", linestyle="None", label="Max Capacity")

    plt.title("CAV Penetration Rate - Capacity Curve", fontsize=20)
    plt.xlabel("CAV Penetration Rate (%)", fontsize=15)
    plt.ylabel("Capacity (veh/h)", fontsize=15)
    plt.ylim(500, 3500)

    # 仅在图中显示最大通行能力的y值
    for x, y in zip(cav_percentages, capacity_values):
        if y == max_capacity:
            plt.text(x, y, f"({x}, {y})", ha="center", va="bottom")

    plt.legend(loc="upper left")
    plt.grid(axis="y")

    os.makedirs("graph", exist_ok=True)
    plt.savefig(CAPACITY_SUMMARY_PATH)
    print(f"[OK] [CAV渗透率-通行能力]曲线已成功保存至{CAPACITY_SUMMARY_PATH}")
    plt.close()


def main():
    # 引入并设置命令行位置参数
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=str, default="out/results_raw_p05.csv")
    parser.add_argument("--outDir", type=str, default="graph/fd_plots")
    args = parser.parse_args()

    aggregated, cav_ratios = load_and_aggregate(args.csv)
    if aggregated is None:
        return

    os.makedirs(args.outDir, exist_ok=True)

    capacities = compute_capacities(aggregated, cav_ratios)

    for capacity in capacities:
        subset = aggregated[aggregated["pCAV"] == capacity["cav_ratio"]]
        plot_density_flow(
            capacity["cav_ratio"],
            subset["density"],
            subset["mean_flow(veh/h)"],
            capacity["peak_density"],
            capacity["peak_flow"],
            args.outDir,
        )

    plot_capacity_summary(capacities)


if __name__ == "__main__":
    main()
