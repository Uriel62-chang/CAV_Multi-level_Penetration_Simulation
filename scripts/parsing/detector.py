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
    window_interval_count = 0

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
        # 审阅 P1-3：仅在分析窗口 [warmup, simulation_end) 内的 interval 计数
        window_interval_count += 1
        flow_values.append(flow)
        if flow > 0:
            speed_values.append(speed)

    # 审阅 P1-1/P1-3：分析窗口内无观测 interval（空/截断/仅窗外 interval）→ 抛错
    # （fail-closed，不得把"无窗内观测数据"的损坏 run 混入容量统计）
    if window_interval_count == 0:
        raise ValueError(
            f"detector: no interval in window [{warmup_period}, {simulation_end}) in {xml_path}"
        )

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
    # 审阅 P1-4/P1-5：每个车道文件分别维护窗内 interval 集合——任一车道无窗内观测
    # 即 fail-closed；各车道 begin（及对应 end）集合必须完全一致，缺失/多余窗口
    # 同样 fail-closed（不得把缺失窗口按零贡献处理导致流量低估）
    window_sets_per_file: list[tuple[str, set[tuple[float, float]]]] = []
    for path in xml_paths:
        window_set: set[tuple[float, float]] = set()
        seen_begins: set[float] = set()
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
            window_key = (begin, float(interval.get("end", "0")))
            # 审阅 P1-6/P1-7：同一车道重复 (begin, end) 或重复 begin（不同 end）
            # interval → fail-closed（不得静默累加导致流量高估）
            if window_key in window_set or begin in seen_begins:
                raise ValueError(
                    f"detector: duplicate interval for begin={begin} in lane file {path}"
                )
            window_set.add(window_key)
            seen_begins.add(begin)
            if begin not in lane_data:
                lane_data[begin] = {"flow": 0.0, "weighted_speed": 0.0}
            lane_data[begin]["flow"] += flow
            lane_data[begin]["weighted_speed"] += flow * speed
        window_sets_per_file.append((str(path), window_set))

    # 审阅 P1-1/P1-3/P1-4：任一车道在窗口内无观测 interval → fail-closed
    empty_files = [name for name, wset in window_sets_per_file if not wset]
    if empty_files:
        raise ValueError(
            f"detector: no interval in window [{warmup_period}, {simulation_end}) in "
            f"lane file(s): {empty_files}"
        )

    # 审阅 P1-5：各车道窗内 (begin, end) 集合必须完全一致
    first_set = window_sets_per_file[0][1]
    mismatched = [name for name, wset in window_sets_per_file[1:] if wset != first_set]
    if mismatched:
        raise ValueError(
            f"detector: lane interval sets inconsistent across files: {mismatched} "
            f"(first={sorted(first_set)}, differs from expected consistent set)"
        )

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
                # 审阅 P1-1：空/截断 XML 由 parse_detector 抛 ValueError（此处捕获 →
                # parse_success=False）；有观测窗口（含全零流量）为合法
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
