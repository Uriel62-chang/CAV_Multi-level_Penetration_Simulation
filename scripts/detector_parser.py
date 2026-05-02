import argparse
import xml.etree.ElementTree as ET


def parse_detector(xml_path: str, warmup_period: float = 600.0):
    # 解析xml文件并拿到根节点
    root = ET.parse(xml_path).getroot()
    flow_values, speed_values = [], []

    # 获取解析器每60s的数据，筛除处于预热期的数据
    for interval in root.findall("interval"):
        begin = float(interval.get("begin", "0"))
        if begin < warmup_period:
            continue
        flow = float(interval.get("flow", "0"))   # 流量（veh/h）
        speed = float(interval.get("speed", "0"))  # 速度（m/s）
        flow_values.append(flow)
        speed_values.append(speed)

    if len(flow_values) == 0:
        return 0.0, 0.0, 0.0

    # 计算并返回有效期断面车流的：平均流量、峰值流量、平均速度

    mean_flow = sum(flow_values) / len(flow_values)
    max_flow = max(flow_values)
    mean_speed = sum(speed_values) / len(speed_values)
    return mean_flow, max_flow, mean_speed


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
