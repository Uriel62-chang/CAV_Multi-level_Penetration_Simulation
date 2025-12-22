import argparse, random

EDGES = ["e0", "e1", "e2", "e3"]
EDGE_LEN = 500.0
RING_LEN = EDGE_LEN * 4

# 拼接完整环路
def route_from_edge(start_idx: int, loops: int) -> str:
    one_lap = EDGES[start_idx:] + EDGES[:start_idx]
    return " ".join(one_lap * loops)

# 主函数
def main():
    # 引入并设置命令行位置参数
    ap = argparse.ArgumentParser()
    ap.add_argument("--vehN", type=int, default=40)
    ap.add_argument("--pCAV", type=float, default=0.5)
    ap.add_argument("--loops", type=int, default=300) # 循环次数
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=str, default="routes/loop.rou.xml")
    args = ap.parse_args()

    random.seed(args.seed) # 随机种子
    N = args.vehN # 车辆总数（HV+CAV）
    p = args.pCAV # CAV渗透率

    cavN = int(round(N * p)) # CAV数量
    types = ["CAV"] * cavN + ["HV"] * (N - cavN) # CAV、HV组成的列表（元素数量为N）
    random.shuffle(types) # 打乱列表顺序，模拟随机车流

    # 定义车流属性
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<routes>')

    '''
    参数说明：
    tau：反应时间
    sigma：驾驶不稳定性
    minGap：最小车头间距
    '''
    # HV：Krauss（更大时距tau、更大随机性sigma）
    lines.append('  <vType id="HV" accel="2.0" decel="4.5" length="5" minGap="2.5" maxSpeed="33.33" '
                 'carFollowModel="Krauss" tau="1.2" sigma="0.5"/>')
    # CAV：Krauss（更小tau、更小sigma、更小minGap）作为“更稳、更短时距”的等效ACC/CAV
    lines.append('  <vType id="CAV" accel="2.5" decel="4.5" length="5" minGap="1.0" maxSpeed="33.33" '
                 'carFollowModel="Krauss" tau="0.6" sigma="0.1"/>')

    # 定义每辆车的空间属性及其自身路线
    spacing = RING_LEN / N # 间距
    for i in range(N):
        s = i * spacing
        edge_idx = int(s // EDGE_LEN) % 4 # 起始边
        pos = s % EDGE_LEN # 起始位置
        vtype = types[i] # 车辆类型（HV或CAV）
        rid = f"r{i}" # 车辆自身的路径号
        vid = f"veh{i}" # 车辆自身的车号

        edges_str = route_from_edge(edge_idx, args.loops) # 构建车辆环路
        lines.append(f'  <route id="{rid}" edges="{edges_str}"/>')
        lines.append(f'  <vehicle id="{vid}" type="{vtype}" route="{rid}" depart="0" departPos="{pos:.2f}" departSpeed="max"/>')

    lines.append('</routes>')

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"车辆参数已写入：{args.out}")

if __name__ == "__main__":
    main()
