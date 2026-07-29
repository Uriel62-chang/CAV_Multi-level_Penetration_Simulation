"""SUMO edgeData performance 解析：车辆行驶距离与 timeLoss。"""

import xml.etree.ElementTree as ET


def parse_edge_performance(xml_path: str, warmup_period: float = 0.0):
    """解析 SUMO edgeData type='performance' XML。

    Args:
        xml_path: edgeData XML 文件路径。
        warmup_period: 仅累计 begin >= 此时刻的完整 interval。

    Returns:
        dict: {
            "total_vehicle_km": float or NaN,
            "non_internal_edge_vehicle_km": float or NaN,
            "total_time_loss_s": float or NaN,
            "parse_success": bool,
        }
    """

    result = {
        "total_vehicle_km": float("nan"),
        "non_internal_edge_vehicle_km": float("nan"),
        "total_time_loss_s": float("nan"),
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

    for interval in root.findall("interval"):
        try:
            interval_begin = float(interval.get("begin", "0"))
        except (ValueError, TypeError):
            continue
        if interval_begin < warmup_period:
            continue
        for edge in interval.findall("edge"):
            try:
                speed = float(edge.get("speed", "0"))
                sampled_seconds = float(edge.get("sampledSeconds", "0"))
            except (ValueError, TypeError):
                continue

            # distance = meanSpeed × sampledSeconds (m)
            edge_dist = speed * sampled_seconds
            total_distance_m += edge_dist
            if edge.get("id", "").startswith(":"):
                pass  # internal edge, excluded from non_internal
            else:
                non_internal_distance_m += edge_dist

            try:
                time_loss = float(edge.get("timeLoss", "0"))
            except (ValueError, TypeError):
                time_loss = 0.0
            total_time_loss += time_loss

    total_vehicle_km = total_distance_m / 1000.0
    non_internal_km = non_internal_distance_m / 1000.0

    result["total_vehicle_km"] = total_vehicle_km
    result["non_internal_edge_vehicle_km"] = non_internal_km
    result["total_time_loss_s"] = total_time_loss
    result["parse_success"] = True
    return result
