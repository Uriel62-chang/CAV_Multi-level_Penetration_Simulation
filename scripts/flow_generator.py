import argparse
import os
import random

from scripts.config import (
    CAV_ACCEL, CAV_ACTION_STEP_LENGTH, CAV_DECEL, CAV_LENGTH,
    CAV_MAX_SPEED, CAV_MIN_GAP, CAV_MODELS, CAV_SPEED_DEV, CAV_TAU,
    HV_ACCEL, HV_ACTION_STEP_LENGTH, HV_DECEL, HV_LENGTH,
    HV_MAX_SPEED, HV_MIN_GAP, HV_SIGMA, HV_SPEED_DEV, HV_TAU,
    JUNCTION_MARGIN_M, LC2013_COOPERATIVE, LC2013_KEEP_RIGHT,
    LC2013_SIGMA, LC2013_SPEED_GAIN, LC2013_STRATEGIC,
)


def _lc2013_attrs() -> str:
    """返回 LC2013 换道模型参数字符串（多车道路网注入 vType）"""
    return (f'lcStrategic="{LC2013_STRATEGIC}" lcSpeedGain="{LC2013_SPEED_GAIN}" '
            f'lcKeepRight="{LC2013_KEEP_RIGHT}" lcCooperative="{LC2013_COOPERATIVE}" '
            f'lcSigma="{LC2013_SIGMA}"')


def _build_route(edges: list, start_edge_index: int, loops: int) -> str:
    """拼接完整闭环路线：从 start_edge_index 出发，绕行 loops 圈

    edges = ["e0","e1","e2","e3"], start_edge_index=2, loops=2
    → "e2 e3 e0 e1 e2 e3 e0 e1"
    """
    one_lap = edges[start_edge_index:] + edges[:start_edge_index]
    return " ".join(one_lap * loops)


def _build_cav_vtype(model: str, lc2013: str = "") -> str:
    """根据跟驰模型生成 CAV vType XML 行"""
    if model not in CAV_TAU:
        raise ValueError(f"不支持的 CAV 跟驰模型: {model}，可选: {CAV_MODELS}")
    tau = CAV_TAU[model]
    return (
        f'  <vType id="CAV" accel="{CAV_ACCEL}" decel="{CAV_DECEL}" '
        f'length="{CAV_LENGTH:.0f}" minGap="{CAV_MIN_GAP}" maxSpeed="{CAV_MAX_SPEED}" '
        f'speedDev="{CAV_SPEED_DEV}" carFollowModel="{model}" tau="{tau}" '
        f'actionStepLength="{CAV_ACTION_STEP_LENGTH}"{lc2013}/>'
    )


def _place_vehicles_s0(vehicle_count: int, edge_length: float,
                        edge_count: int) -> list:
    """scenario_0 车辆偏移（方形闭环，v0.2.0 原始逻辑）

    车辆沿环路等距均匀分布，用截断除法避免浮点取模误差。
    靠近边末端的车辆回绕至下一边起点。
    返回 [(edge_index, position), ...]。
    """
    ring_length = edge_length * edge_count
    spacing = ring_length / vehicle_count
    result = []
    for i in range(vehicle_count):
        offset = i * spacing
        edge_index = int(offset // edge_length)
        position = offset - edge_index * edge_length
        if position > edge_length - JUNCTION_MARGIN_M:
            edge_index += 1
            position = 0.0
        edge_index %= edge_count
        result.append((edge_index, position))
    return result


def _place_vehicles_s1(vehicle_count: int, edge_length: float,
                        edge_count: int) -> list:
    """scenario_1 车辆偏移（多边形闭环，单车道）

    车辆沿环路等距均匀分布，用截断除法避免浮点取模误差。
    靠近边末端的车辆回绕至下一边起点（余量由 config.JUNCTION_MARGIN_M 控制）。
    """
    ring_length = edge_length * edge_count
    spacing = ring_length / vehicle_count
    result = []
    for i in range(vehicle_count):
        offset = i * spacing
        edge_index = int(offset // edge_length)
        position = offset - edge_index * edge_length
        if position > edge_length - JUNCTION_MARGIN_M:
            edge_index += 1
            position = 0.0
        edge_index %= edge_count
        result.append((edge_index, position))
    return result


def _place_vehicles_s2(vehicle_count: int, edge_length: float,
                        edge_count: int, num_lanes: int) -> list:
    """scenario_2 车辆偏移（多边形闭环，多车道 + 换道）

    几何逻辑同 scenario_1；每辆车按索引奇偶交替分配车道。
    返回 [(edge_index, position, lane), ...]。
    """
    ring_length = edge_length * edge_count
    spacing = ring_length / vehicle_count
    result = []
    for i in range(vehicle_count):
        offset = i * spacing
        edge_index = int(offset // edge_length)
        position = offset - edge_index * edge_length
        if position > edge_length - JUNCTION_MARGIN_M:
            edge_index += 1
            position = 0.0
        edge_index %= edge_count
        lane = i % num_lanes
        result.append((edge_index, position, lane))
    return result


def _place_vehicles_s3(vehicle_count: int, edge_length: float,
                        edge_count: int, num_lanes: int) -> list:
    """scenario_3 车辆偏移（瓶颈边单车道约束）

    几何逻辑复用 _place_vehicles_s2；但 e15/e16 为单车道，
    落在这些边上的车辆强制分配 lane=0，避免 SUMO departLane 越界。
    返回 [(edge_index, position, lane), ...]。
    """
    result = _place_vehicles_s2(vehicle_count, edge_length, edge_count, num_lanes)
    BOTTLENECK_EDGES = {15, 16}
    modified = []
    for edge_index, position, lane in result:
        if lane > 0 and edge_index in BOTTLENECK_EDGES:
            lane = 0
        modified.append((edge_index, position, lane))
    return modified


# 场景 → 车辆偏移函数注册表
_PLACEMENT_REGISTRY = {
    "scenario_0": _place_vehicles_s0,
    "scenario_1": _place_vehicles_s1,
    "scenario_2": _place_vehicles_s2,
    "scenario_3": _place_vehicles_s3,
}

# 多车道场景列表（触发 LC2013 + departLane）
_MULTI_LANE_SCENARIOS = {"scenario_2", "scenario_3"}


def generate_flow(vehicle_count: int, cav_ratio: float, loops: int, seed: int,
                  output_path: str, model: str = "IDM",
                  edge_count: int = 4, edge_length: float = 500.0,
                  scenario: str = "scenario_0", num_lanes: int = 1):
    """生成混合车流 SUMO route 文件 (.rou.xml)

    步骤：等距分布车辆 → 随机打乱 CAV/HV 顺序 → 写入 vType + vehicle + route。
    多车道场景（scenario_2）自动注入 LC2013 换道参数和 departLane 属性。
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    random.seed(seed)

    edges = [f"e{i}" for i in range(edge_count)]

    # 场景分发
    place_func = _PLACEMENT_REGISTRY.get(scenario, _place_vehicles_s0)
    multi_lane = scenario in _MULTI_LANE_SCENARIOS
    if multi_lane:
        vehicle_placements = place_func(vehicle_count, edge_length, edge_count, num_lanes)
    else:
        vehicle_placements = place_func(vehicle_count, edge_length, edge_count)

    lc2013 = f" {_lc2013_attrs()}" if multi_lane else ""

    # CAV数量
    cav_count = int(round(vehicle_count * cav_ratio))
    vehicle_types = ["CAV"] * cav_count + ["HV"] * (vehicle_count - cav_count)
    random.shuffle(vehicle_types)

    # 定义车流属性
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<routes>')

    # HV：Krauss（人类驾驶参数）
    lines.append(
        f'  <vType id="HV" accel="{HV_ACCEL}" decel="{HV_DECEL}" '
        f'length="{HV_LENGTH:.0f}" minGap="{HV_MIN_GAP}" maxSpeed="{HV_MAX_SPEED}" '
        f'speedDev="{HV_SPEED_DEV}" carFollowModel="Krauss" tau="{HV_TAU}" '
        f'sigma="{HV_SIGMA}" actionStepLength="{HV_ACTION_STEP_LENGTH}"{lc2013}/>'
    )
    # CAV
    lines.append(_build_cav_vtype(model, lc2013))

    # 写入每辆车
    for i in range(vehicle_count):
        placement = vehicle_placements[i]
        edge_index = placement[0]
        position = placement[1]
        lane = placement[2] if multi_lane else None
        vehicle_type = vehicle_types[i]

        edges_str = _build_route(edges, edge_index, loops)
        lines.append(f'  <route id="r{i}" edges="{edges_str}"/>')
        depart_attrs = (f'departPos="{position:.2f}" departSpeed="max"'
                        f' departLane="{lane}"' if lane is not None else
                        f'departPos="{position:.2f}" departSpeed="max"')
        lines.append(
            f'  <vehicle id="veh{i}" type="{vehicle_type}" route="r{i}" depart="0" '
            f'{depart_attrs}/>'
        )

    lines.append('</routes>')

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"车辆参数已写入：{output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vehN", type=int, default=40)
    parser.add_argument("--pCAV", type=float, default=0.5)
    parser.add_argument("--loops", type=int, default=300)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=str, default="routes/loop.rou.xml")
    parser.add_argument("--model", type=str, default="IDM", choices=list(CAV_MODELS),
                        help="CAV跟驰模型: IDM / ACC / CACC")
    parser.add_argument("--edge-count", type=int, default=4,
                        help="环路边数 (默认: 4)")
    parser.add_argument("--edge-length", type=float, default=500.0,
                        help="每条边长/m (默认: 500)")
    parser.add_argument("--scenario", default="scenario_0",
                        help="场景标识 (默认: scenario_0)")
    parser.add_argument("--num-lanes", type=int, default=1,
                        help="车道数 (默认: 1)")
    args = parser.parse_args()

    generate_flow(args.vehN, args.pCAV, args.loops, args.seed, args.out,
                  args.model, args.edge_count, args.edge_length,
                  args.scenario, args.num_lanes)


if __name__ == "__main__":
    main()