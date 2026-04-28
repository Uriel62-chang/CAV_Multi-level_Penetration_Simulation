import argparse
import pandas as pd
import matplotlib.pyplot as plt
import os

# 环路长度 (km)，用于计算密度
RING_LEN_KM = 2.0

def main():
    # 引入并设置命令行位置参数
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=str, default="out/results_raw_p05.csv")
    ap.add_argument("--outDir", type=str, default="graph/fd_plots")
    args = ap.parse_args()

    INPUT_CSV = args.csv
    OUT_DIR = args.outDir

    # 1. 检查文件是否存在
    if not os.path.exists(INPUT_CSV):
        print(f"错误: 找不到文件 {INPUT_CSV}")
        print("请确保你已经运行了 batch.py 并生成了数据。")

    # 创建输出目录
    os.makedirs(OUT_DIR, exist_ok=True)

    # 2. 读取数据
    print(f"正在读取数据: {INPUT_CSV} ...")
    df = pd.read_csv(INPUT_CSV)

    # 计算密度 k = N / L (veh/km)
    df["density"] = df["vehN"] / RING_LEN_KM

    # 分组聚类（以“渗透率”、“车辆数”、“密度”为依据——对多个随机种子的车流取平均流量）
    df_agg = df.groupby(["pCAV", "vehN", "density"])["mean_flow(veh/h)"].mean().reset_index()

    # 排序、去重后收集所有情况的渗透率
    p_cav = sorted(df_agg["pCAV"].unique())

    # 存储通行能力的列表
    capacities = []

    # 遍历所有渗透率
    for p in p_cav:
        # 筛出渗透率对应的DataFrame（包含“渗透率”、“流量”、“密度”）
        current = df_agg[df_agg["pCAV"] == p]

        # 记录当前渗透率的通行能力
        maxRow = current["mean_flow(veh/h)"].idxmax()
        maxFlow = current.loc[maxRow, "mean_flow(veh/h)"]
        itsDensity = current.loc[maxRow, "density"]
        capacities.append({
            "pCAV": p,
            "maxFlow": maxFlow,
            "itsDensity": itsDensity
        })

        '''
        绘图
        '''
        # 框定画布大小
        plt.figure(figsize=(10, 5))

        # 绘制密度-流量曲线
        plt.plot(current["density"], current["mean_flow(veh/h)"], marker="o", color="blue", label="Flow", linewidth=2,
                 linestyle='-')
        # 在图中标注出峰值流量（即该渗透率下的通行能力）
        plt.plot(itsDensity, maxFlow, marker="*", markersize=12, color="red", label="capacity")

        plt.title(f"Density-Flow Curve(CAV penetration rate: {int(p * 100)}%)", color="black", fontsize=20)  # 添加标题

        # x轴设置
        plt.xlabel("Density(veh/km)", rotation=0, fontsize=15)  # 设置x轴标题
        plt.xticks(rotation=0, fontsize=10)  # 设置x轴刻度
        plt.xlim(0, 70)  # 设置x轴大小的上下限

        # y轴设置
        plt.ylabel("Flow(veh/h)", rotation=90, fontsize=15)  # 设置y轴标题
        plt.yticks(rotation=0, fontsize=10)  # 设置y轴刻度
        plt.ylim(0, 3000)  # 设置y轴大小的上下限

        # 显示折点的y值
        for x, y in zip(current["density"], current["mean_flow(veh/h)"]):
            plt.text(x, y, str(y), ha="center", va="bottom")

        plt.legend(loc="upper left")  # 添加图例

        plt.grid(axis='y')  # 添加网格线

        # plt.show() # 显示图表
        # 保存图表（路径：graph/fd_plots/fd_pxxx.png）
        save_path = OUT_DIR + "/" + f"fd_p{int(p * 100):03d}" + ".png"
        plt.savefig(save_path)
        print(f"[OK] {int(p * 100)}%渗透率的[密度-流量]曲线已成功保存至{save_path}")

        plt.close()

    '''
    绘制CAV渗透率-通行能力曲线
    '''
    # 框定画布大小
    plt.figure(figsize=(10, 5))

    # 选取x轴、y轴元素
    pCAV = [x["pCAV"] * 100 for x in capacities] # x轴：渗透率
    capacity = [x["maxFlow"] for x in capacities] # y轴：对应的通行能力

    # 绘制折线图
    plt.plot(pCAV, capacity, marker="o", markersize=8, label="capacity", color="blue", linewidth=2, linestyle='-')

    # 找出全局最大值
    maxCapacity = max(capacity)
    max_idx = capacity.index(maxCapacity)
    max_p = pCAV[max_idx]
    # 在途中标出最大通行能力
    plt.plot(max_p, maxCapacity, marker="*", markersize=12, color="red", linestyle='None', label="Max Capacity")

    plt.title("CAV penetration rate-Capacity Curve", color="black", fontsize=20) # 设置标题

    # x轴设置
    plt.xlabel("CAV penetration rate(%)", rotation=0, fontsize=15)  # 设置x轴标题
    plt.xticks(rotation=0, fontsize=10)  # 设置x轴刻度
    # plt.xlim(0, 110)  # 设置x轴大小的上下限

    # y轴设置
    plt.ylabel("Capacity(veh/h)", rotation=90, fontsize=15)  # 设置y轴标题
    plt.yticks(rotation=0, fontsize=10)  # 设置y轴刻度
    plt.ylim(500, 3500)  # 设置y轴大小的上下限

    # 仅在图中显示最大通行能力的y值
    for x, y in zip(pCAV, capacity):
        if y == maxCapacity:
            plt.text(x, y, f"({x}, {y})", ha="center", va="bottom")

    plt.legend(loc="upper left")  # 添加图例

    plt.grid(axis='y')  # 添加网格线

    # plt.show() # 显示图表
    # 保存图表（路径：graph/Capacity_summary.png）
    save_path = "graph/" + f"Capacity_summary" + ".png"
    plt.savefig(save_path)
    print(f"[OK] [CAV渗透率-通行能力]曲线已成功保存至{save_path}")

    plt.close()

if __name__ == "__main__":
    main()