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


def parse_detector(xml_path: str, warmup_period: float = 600.0):
    """解析单个 e1 检测器 XML，返回 (mean_flow, max_flow, mean_speed, speed_variance, window_count)"""
    root = ET.parse(xml_path).getroot()
    flow_values, speed_values = [], []

    for interval in root.findall("interval"):
        begin = float(interval.get("begin", "0"))
        if begin < warmup_period:
            continue
        flow = float(interval.get("flow", "0"))
        speed = float(interval.get("speed", "0"))
        flow_values.append(flow)
        speed_values.append(speed)

    if len(flow_values) == 0:
        return 0.0, 0.0, 0.0, float("nan"), 0

    mean_flow = sum(flow_values) / len(flow_values)
    max_flow = max(flow_values)
    mean_speed = sum(speed_values) / len(speed_values)
    speed_variance = _compute_speed_variance(speed_values)
    return mean_flow, max_flow, mean_speed, speed_variance, len(speed_values)


def parse_detector_multi(xml_paths: list, warmup_period: float = 600.0):
    """解析多个车道 e1 检测器 XML，按时间窗口聚合流量与速度

    同 interval 的 flow 跨车道求和、speed 取加权平均（以 flow 为权重）。
    返回 (mean_flow, max_flow, mean_speed, speed_variance, window_count)。
    """
    if len(xml_paths) == 1:
        return parse_detector(xml_paths[0], warmup_period)

    # 读取所有车道的检测器数据，按 begin 时间分组
    lane_data = {}
    for path in xml_paths:
        root = ET.parse(path).getroot()
        for interval in root.findall("interval"):
            begin = float(interval.get("begin", "0"))
            if begin < warmup_period:
                continue
            flow = float(interval.get("flow", "0"))
            speed = float(interval.get("speed", "0"))
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
        else:
            speed_values.append(0.0)

    mean_flow = sum(flow_values) / len(flow_values)
    max_flow = max(flow_values)
    mean_speed = sum(speed_values) / len(speed_values)
    speed_variance = _compute_speed_variance(speed_values)
    return mean_flow, max_flow, mean_speed, speed_variance, len(speed_values)


def main():
    # 设置命令行位置参数
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml", required=True)
    parser.add_argument("--warmup", type=float, default=600.0)  # 预热期
    args = parser.parse_args()

    mean_flow, max_flow, mean_speed = parse_detector(args.xml, args.warmup)
    print(f"{mean_flow:.3f},{max_flow:.3f},{mean_speed:.3f}")


if __name__ == "__main__":
    main()
