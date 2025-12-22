import argparse, subprocess

# 将字符列表转换为数值列表
def parse_list(s: str, cast=float):
    return [cast(x.strip()) for x in s.split(",") if x.strip()]


def gen_p_list(step: float):
    n = int(round(1.0 / step))
    return [round(i * step, 10) for i in range(n + 1)]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pCAV-list", default="") # CAV渗透率
    ap.add_argument("--pstep", type=float, default=0.05)  # CAV渗透率步长（默认5%）
    ap.add_argument("--vehN-list", default="10,20,30,40,50,60,70,80,90,100,110,120") # 车辆数列表
    ap.add_argument("--seeds", default="1") # 随机种子列表
    ap.add_argument("--end", type=int, default=3600) # 每次仿真的结束时间
    ap.add_argument("--warmup", type=int, default=600) # 预热期
    ap.add_argument("--freq", type=int, default=60) # 检测器统计
    ap.add_argument("--outcsv", default="out/results_raw_p05.csv") # 生数据输出路径
    args = ap.parse_args()

    # 若没有提供渗透率列表，则依据步长生成
    if args.pCAV_list.strip():
        p_list = parse_list(args.pCAV_list, float)
    else:
        p_list = gen_p_list(args.pstep)

    v_list = parse_list(args.vehN_list, int) # 车辆数列表
    seeds  = parse_list(args.seeds, int) # 随机种子列表

    # 批量仿真
    for p in p_list:
        for v in v_list:
            for sd in seeds:
                subprocess.check_call([
                    "python3","scripts/run.py",
                    "--vehN", str(v),
                    "--pCAV", str(p),
                    "--seed", str(sd),
                    "--end", str(args.end),
                    "--warmup", str(args.warmup),
                    "--freq", str(args.freq),
                    "--outcsv", args.outcsv
                ])

if __name__ == "__main__":
    main()
