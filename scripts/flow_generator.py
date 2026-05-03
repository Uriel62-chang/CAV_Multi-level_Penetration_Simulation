import argparse
import os
import random

EDGES = ["e0", "e1", "e2", "e3"]
EDGE_LENGTH = 500.0
RING_LENGTH = EDGE_LENGTH * 4

# CAV 跟驰模型可选值
CAV_MODELS = {"IDM", "ACC", "CACC"}

# CAV 各跟驰模型的 tau（期望车头时距）
CAV_TAU_MAP = {
    "IDM": "0.6",
    "ACC": "1.1",
    "CACC": "0.6",
}


def _build_route(start_edge_index: int, loops: int) -> str:
    # 拼接完整环路
    one_lap = EDGES[start_edge_index:] + EDGES[:start_edge_index]
    return " ".join(one_lap * loops)


def _build_cav_vtype(model: str) -> str:
    """根据跟驰模型生成 CAV vType XML 行"""
    if model not in CAV_TAU_MAP:
        raise ValueError(f"不支持的 CAV 跟驰模型: {model}，可选: {sorted(CAV_MODELS)}")
    tau = CAV_TAU_MAP[model]
    return (
        f'  <vType id="CAV" accel="3.0" decel="4.5" length="5" minGap="0.5" maxSpeed="33.33" '
        f'speedDev="0.0" carFollowModel="{model}" tau="{tau}" actionStepLength="0.1"/>'
    )


def generate_flow(vehicle_count: int, cav_ratio: float, loops: int, seed: int,
                  output_path: str, model: str = "IDM"):
    # or "."：针对输出目录为当前目录的情况，即：out_path = "xxx.rou.xml"，以防os.makedirs()检测到空目录报错
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    random.seed(seed)

    # CAV数量
    cav_count = int(round(vehicle_count * cav_ratio))
    # CAV、HV组成的列表（元素数量为vehicle_count）
    vehicle_types = ["CAV"] * cav_count + ["HV"] * (vehicle_count - cav_count)
    # 打乱列表顺序，模拟随机车流
    random.shuffle(vehicle_types)

    # 定义车流属性
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<routes>')

    # HV：Krauss（人类驾驶参数）
    lines.append(
        '  <vType id="HV" accel="2.0" decel="4.5" length="5" minGap="2.5" maxSpeed="33.33" '
        'speedDev="0.1" carFollowModel="Krauss" tau="1.5" sigma="0.5" actionStepLength="1.0"/>'
    )
    # CAV：按 model 参数动态选用跟驰模型（IDM / ACC / CACC）
    lines.append(_build_cav_vtype(model))

    # 定义每辆车的空间属性及其自身路线
    spacing = RING_LENGTH / vehicle_count
    for i in range(vehicle_count):
        offset = i * spacing
        edge_index = int(offset // EDGE_LENGTH) % 4  # 起始边
        position = offset % EDGE_LENGTH  # 起始位置
        vehicle_type = vehicle_types[i]  # 车辆类型（HV或CAV）

        edges_str = _build_route(edge_index, loops)
        lines.append(f'  <route id="r{i}" edges="{edges_str}"/>')
        lines.append(
            f'  <vehicle id="veh{i}" type="{vehicle_type}" route="r{i}" depart="0" '
            f'departPos="{position:.2f}" departSpeed="max"/>'
        )  # 车辆自身的车号、路径号、类型

    lines.append('</routes>')

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"车辆参数已写入：{output_path}")


def main():
    # 引入并设置命令行位置参数
    parser = argparse.ArgumentParser()
    parser.add_argument("--vehN", type=int, default=40)
    parser.add_argument("--pCAV", type=float, default=0.5)
    parser.add_argument("--loops", type=int, default=300)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=str, default="routes/loop.rou.xml")
    parser.add_argument("--model", type=str, default="IDM", choices=sorted(CAV_MODELS),
                        help="CAV跟驰模型: IDM / ACC / CACC")
    args = parser.parse_args()

    generate_flow(args.vehN, args.pCAV, args.loops, args.seed, args.out, args.model)


if __name__ == "__main__":
    main()