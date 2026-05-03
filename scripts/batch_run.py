import argparse
import os
import sys

# 将当前文件的所在目录的上级目录（项目根目录）加入到系统搜索路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.single_run import run_simulation


def parse_numeric_list(s: str, cast=float):
    # 将字符列表转换为数值列表
    return [cast(x.strip()) for x in s.split(",") if x.strip()]


def generate_cav_ratios(step: float):
    n = int(round(1.0 / step))
    return [round(i * step, 10) for i in range(n + 1)]


def main():
    # 设置命令行位置参数
    parser = argparse.ArgumentParser()
    parser.add_argument("--pCAV-list", default="")  # CAV渗透率
    parser.add_argument("--pstep", type=float, default=0.05)  # CAV渗透率步长（默认5%）
    parser.add_argument("--vehN-list", default="10,20,30,40,50,60,70,80,90,100,110,120")  # 车辆数列表
    parser.add_argument("--seeds", default="1")  # 随机种子列表
    parser.add_argument("--end", type=int, default=3600)  # 每次仿真的结束时间
    parser.add_argument("--warmup", type=int, default=600)  # 预热期
    parser.add_argument("--freq", type=int, default=60)  # 检测器统计
    parser.add_argument("--outcsv", default="out/results_raw_p05.csv")  # 生数据输出路径
    args = parser.parse_args()

    # 若没有提供渗透率列表，则依据步长生成
    if args.pCAV_list.strip():
        cav_ratios = parse_numeric_list(args.pCAV_list, float)
    else:
        cav_ratios = generate_cav_ratios(args.pstep)

    vehicle_counts = parse_numeric_list(args.vehN_list, int)  # 车辆数列表
    seeds = parse_numeric_list(args.seeds, int)  # 随机种子列表

    # 批量仿真
    for p in cav_ratios:
        for v in vehicle_counts:
            for sd in seeds:
                run_simulation(
                    vehicle_count=v,
                    cav_ratio=p,
                    seed=sd,
                    sim_end_time=args.end,
                    warmup_period=args.warmup,
                    detector_frequency=args.freq,
                    output_csv=args.outcsv,
                )


if __name__ == "__main__":
    main()
