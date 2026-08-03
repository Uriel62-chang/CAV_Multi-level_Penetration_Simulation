import argparse
import xml.etree.ElementTree as ET


def _compute_speed_variance(speed_values: list) -> float:
    """计算速度序列的总体方差（ddof=0）。

    Args:
        speed_values: 各时间窗口的跨车道聚合后平均速度。

    Returns:
        总体方差。若有效窗口数 < 2 返回 NaN；空序列返回 NaN。
    """
    n = len(speed_values)
    if n < 2:
        return float("nan")
    mean = sum(speed_values) / n
    variance = sum((v - mean) ** 2 for v in speed_values) / n
    return variance


def parse_detector(
    xml_path: str, warmup_period: float = 600.0, simulation_end: float | None = None
):
    """解析单个 e1 检测器 XML，返回 (mean_flow, max_flow, mean_speed, speed_variance, window_count)

    审阅 P1-2：interval 属性（begin/flow/speed）非数值或非有限 → 抛 ValueError
    （fail-closed，与 SSM/EdgeData 语义一致），不再把 nan 流量当作有效数据。
    审阅 P1-1（本轮）：观测窗 [warmup, simulation_end)——begin >= simulation_end 的
    interval 不计入；负 begin 拒绝（损坏记录）。
    """
    import math

    root = ET.parse(xml_path).getroot()
    flow_values, speed_values = [], []

    for interval in root.findall("interval"):
        try:
            begin = float(interval.get("begin", "0"))
            flow = float(interval.get("flow", "0"))
            speed = float(interval.get("speed", "0"))
        except (ValueError, TypeError):
            raise ValueError(f"detector: non-numeric interval attribute in {xml_path}") from None
        if not (math.isfinite(begin) and math.isfinite(flow) and math.isfinite(speed)):
            raise ValueError(
                f"detector: non-finite interval attribute in {xml_path} "
                f"(begin={begin!r}, flow={flow!r}, speed={speed!r})"
            )
        # 审阅 P2-2：数值域校验——负流量/负均速拒绝；仅允许 SUMO 空窗口
        # "flow=0 且 speed=-1" 的占位形态
        if flow < 0:
            raise ValueError(f"detector: negative flow in {xml_path} (flow={flow!r})")
        if speed < 0 and not (flow == 0 and speed == -1):
            raise ValueError(f"detector: invalid negative speed in {xml_path} (speed={speed!r})")
        if begin < 0:
            raise ValueError(f"detector: negative begin in {xml_path} (begin={begin!r})")
        if begin < warmup_period:
            continue
        if simulation_end is not None and begin >= simulation_end:
            continue
        flow_values.append(flow)
        if flow > 0:
            speed_values.append(speed)

    if len(flow_values) == 0:
        return 0.0, 0.0, 0.0, float("nan"), 0

    mean_flow = sum(flow_values) / len(flow_values)
    max_flow = max(flow_values)
    mean_speed = sum(speed_values) / len(speed_values) if speed_values else 0.0
    speed_variance = _compute_speed_variance(speed_values)
    return mean_flow, max_flow, mean_speed, speed_variance, len(speed_values)


def parse_detector_multi(
    xml_paths: list, warmup_period: float = 600.0, simulation_end: float | None = None
):
    """解析多个车道 e1 检测器 XML，按时间窗口聚合流量与速度

    同 interval 的 flow 跨车道求和、speed 取加权平均（以 flow 为权重）。
    返回 (mean_flow, max_flow, mean_speed, speed_variance, window_count)。
    审阅 P1-1：观测窗 [warmup, simulation_end)。
    """
    if len(xml_paths) == 1:
        # 审阅 P2（复核）：单文件分支同样传递 simulation_end（公共 API 契约完整）
        return parse_detector(xml_paths[0], warmup_period, simulation_end=simulation_end)

    # 读取所有车道的检测器数据，按 begin 时间分组
    import math

    lane_data = {}
    for path in xml_paths:
        root = ET.parse(path).getroot()
        for interval in root.findall("interval"):
            # 审阅 P1-2（multi）：非数值/非有限 → 抛 ValueError（fail-closed，与单车道一致）
            try:
                begin = float(interval.get("begin", "0"))
                flow = float(interval.get("flow", "0"))
                speed = float(interval.get("speed", "0"))
            except (ValueError, TypeError):
                raise ValueError(f"detector: non-numeric interval attribute in {path}") from None
            if not (math.isfinite(begin) and math.isfinite(flow) and math.isfinite(speed)):
                raise ValueError(
                    f"detector: non-finite interval attribute in {path} "
                    f"(begin={begin!r}, flow={flow!r}, speed={speed!r})"
                )
            if flow < 0:
                raise ValueError(f"detector: negative flow in {path} (flow={flow!r})")
            if speed < 0 and not (flow == 0 and speed == -1):
                raise ValueError(f"detector: invalid negative speed in {path} (speed={speed!r})")
            if begin < 0:
                raise ValueError(f"detector: negative begin in {path} (begin={begin!r})")
            if begin < warmup_period:
                continue
            if simulation_end is not None and begin >= simulation_end:
                continue
            if begin not in lane_data:
                lane_data[begin] = {"flow": 0.0, "weighted_speed": 0.0}
            lane_data[begin]["flow"] += flow
            lane_data[begin]["weighted_speed"] += flow * speed

    if not lane_data:
        return 0.0, 0.0, 0.0, float("nan"), 0

    flow_values, speed_values = [], []
    for begin in sorted(lane_data):
        total_flow = lane_data[begin]["flow"]
        flow_values.append(total_flow)
        if total_flow > 0:
            speed_values.append(lane_data[begin]["weighted_speed"] / total_flow)

    mean_flow = sum(flow_values) / len(flow_values)
    max_flow = max(flow_values)
    mean_speed = sum(speed_values) / len(speed_values) if speed_values else 0.0
    speed_variance = _compute_speed_variance(speed_values)
    return mean_flow, max_flow, mean_speed, speed_variance, len(speed_values)


def parse_detector_subgroup(
    xml_paths_all,
    xml_paths_HV,
    xml_paths_CAV,
    warmup_period=600.0,
    simulation_end: float | None = None,
):
    result = {}
    for label, paths in [
        ("all", xml_paths_all),
        ("HV", xml_paths_HV),
        ("CAV", xml_paths_CAV),
    ]:
        try:
            if len(paths) > 1:
                mf, xf, ms, sv, wc = parse_detector_multi(
                    list(paths), warmup_period, simulation_end=simulation_end
                )
            else:
                mf, xf, ms, sv, wc = parse_detector(
                    list(paths)[0], warmup_period, simulation_end=simulation_end
                )
            result[label] = {
                "mean_flow_veh_h": mf,
                "max_flow_veh_h": xf,
                "mean_speed_m_s": ms,
                "speed_variance": sv,
                "window_count": wc,
                "parse_success": True,
            }
        except (ValueError, ET.ParseError, OSError):
            # 审阅 P1-2：语义损坏 → parse_success=False（fail-closed，writer 标 parser_warning）
            result[label] = {
                "mean_flow_veh_h": float("nan"),
                "max_flow_veh_h": float("nan"),
                "mean_speed_m_s": float("nan"),
                "speed_variance": float("nan"),
                "window_count": 0,
                "parse_success": False,
            }
    return result


def main():
    # 设置命令行位置参数
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml", required=True)
    parser.add_argument("--warmup", type=float, default=600.0)  # 预热期
    args = parser.parse_args()

    mean_flow, max_flow, mean_speed, speed_variance, window_count = parse_detector(
        args.xml, args.warmup
    )
    print(f"{mean_flow:.3f},{max_flow:.3f},{mean_speed:.3f},{speed_variance:.6f},{window_count}")


if __name__ == "__main__":
    main()
