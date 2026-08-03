"""SUMO edgeData performance 解析：车辆行驶距离与 timeLoss。"""

import math
import xml.etree.ElementTree as ET


def parse_edge_performance(
    xml_path: str, warmup_period: float = 0.0, simulation_end: float | None = None
):
    """解析 SUMO edgeData type='performance' XML。

    Args:
        xml_path: edgeData XML 文件路径。
        warmup_period: 仅累计 begin >= 此时刻的完整 interval。
        simulation_end: 观测窗上界（审阅 P1-1）；begin >= simulation_end 的 interval 不计入。

    Returns:
        dict: {
            "total_vehicle_km": float or NaN,
            "non_internal_edge_vehicle_km": float or NaN,
            "total_time_loss_s": float or NaN,
            "invalid_record_count": int,
            "parse_success": bool,
        }

    fail-closed（审阅 P1-1 / delta review）：原子验证 interval.begin 与每条
    edge 的 id/sampledSeconds/speed/timeLoss 后统一累计；任何坏记录使
    ``parse_success`` 为 False 并计入 ``invalid_record_count``：

    - begin / id / sampledSeconds 缺失、非法、非有限或负 → invalid；
    - 出现但非有限或负的 speed/timeLoss → invalid；
    - 无车 edge（sampledSeconds==0.0）缺省 speed/timeLoss 为合法零贡献
      （SUMO 省略无意义属性，实测形态如 s3_IDM_v100_c080_as01_ss103
      performance_HV.xml 的 e15/e16）；有车（>0）却缺失 → invalid。
    """

    result = {
        "total_vehicle_km": float("nan"),
        "non_internal_edge_vehicle_km": float("nan"),
        "total_time_loss_s": float("nan"),
        "invalid_record_count": 0,
        "parse_success": False,
    }

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError, OSError):
        return result

    total_distance_m = 0.0
    non_internal_distance_m = 0.0
    total_time_loss = 0.0
    invalid_record_count = 0

    def _parse_interval_begin(interval):
        """返回 (begin, None) 或 (None, edge_count)；begin 缺失/非法/非有限/负 → 整段 invalid。"""
        begin_raw = interval.get("begin")
        if begin_raw is None:
            return None, len(interval.findall("edge"))
        try:
            begin = float(begin_raw)
        except (ValueError, TypeError):
            return None, len(interval.findall("edge"))
        if not math.isfinite(begin) or begin < 0:
            return None, len(interval.findall("edge"))
        return begin, None

    def _nonneg_attr(edge, name, default):
        """属性出现则校验（有限且非负），缺失返回 default；非法返回 None。"""
        raw = edge.get(name)
        if raw is None:
            return default
        try:
            value = float(raw)
        except (ValueError, TypeError):
            return None
        if not math.isfinite(value) or value < 0:
            return None
        return value

    for interval in root.findall("interval"):
        begin, invalid_edges = _parse_interval_begin(interval)
        if invalid_edges is not None:
            invalid_record_count += invalid_edges
            continue
        if begin < warmup_period:
            continue
        if simulation_end is not None and begin >= simulation_end:
            continue
        for edge in interval.findall("edge"):
            edge_id = edge.get("id")
            if edge_id is None:
                invalid_record_count += 1
                continue
            sampled_raw = edge.get("sampledSeconds")
            if sampled_raw is None:
                invalid_record_count += 1
                continue
            try:
                sampled_seconds = float(sampled_raw)
            except (ValueError, TypeError):
                invalid_record_count += 1
                continue
            if not math.isfinite(sampled_seconds) or sampled_seconds < 0:
                invalid_record_count += 1
                continue
            # 无车 edge（ss==0）：speed/timeLoss 缺省合法零贡献；有车（ss>0）必须给出
            default = 0.0 if sampled_seconds == 0.0 else None
            speed = _nonneg_attr(edge, "speed", default)
            time_loss = _nonneg_attr(edge, "timeLoss", default)
            if speed is None or time_loss is None:
                invalid_record_count += 1
                continue

            # 原子：全部验证通过后统一累计
            edge_dist = speed * sampled_seconds
            total_distance_m += edge_dist
            if edge_id.startswith(":"):
                pass  # internal edge, excluded from non_internal
            else:
                non_internal_distance_m += edge_dist
            total_time_loss += time_loss

    total_vehicle_km = total_distance_m / 1000.0
    non_internal_km = non_internal_distance_m / 1000.0

    result["total_vehicle_km"] = total_vehicle_km
    result["non_internal_edge_vehicle_km"] = non_internal_km
    result["total_time_loss_s"] = total_time_loss
    result["invalid_record_count"] = invalid_record_count
    result["parse_success"] = invalid_record_count == 0
    return result
