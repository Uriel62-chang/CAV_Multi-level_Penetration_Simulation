"""SUMO vehroute output 解析：闭环单圈时间计算。"""

import xml.etree.ElementTree as ET


def _quantile_higher(sorted_values: list[float], quantile: float) -> float:
    """返回离散 higher 分位数：ceil((n - 1) * q) 对应的顺序统计量。"""
    import math

    return sorted_values[math.ceil((len(sorted_values) - 1) * quantile)]


def parse_lap_times(
    xml_path: str, edges_per_lap: int, warmup_period: float = 600.0, sim_end_time: float = 3600.0
):
    """解析 SUMO vehroute exitTimes XML，计算单圈时间。

    Args:
        xml_path: vehroute XML 文件路径。
        edges_per_lap: 每圈的 edge 数量。
        warmup_period: 预热期 (s)。
        sim_end_time: 仿真结束时间 (s)。

    Returns:
        dict: {
            "completed_lap_count": int,
            "mean_lap_time_s": float or NaN,
            "median_lap_time_s": float or NaN,
            "p95_lap_time_s": float or NaN,
            "lap_time_std_s": float or NaN,
            "parse_success": bool,
        }
    """

    result = {
        "completed_lap_count": 0,
        "mean_lap_time_s": float("nan"),
        "median_lap_time_s": float("nan"),
        "p95_lap_time_s": float("nan"),
        "lap_time_std_s": float("nan"),
        "parse_success": False,
    }

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError, OSError):
        return result

    all_lap_times = []

    for vehicle in root.findall("vehicle"):
        route = vehicle.find("route")
        if route is None:
            continue
        exit_times_str = route.get("exitTimes", "")
        if not exit_times_str:
            continue

        times = []
        for t in exit_times_str.split():
            try:
                val = float(t)
                if val < 0:
                    continue  # -1 = not reached
                times.append(val)
            except ValueError:
                continue

        if len(times) < edges_per_lap * 1:
            continue  # not even one complete lap

        # 提取每圈终点时间
        # 第1圈终点 = times[edges_per_lap - 1]
        # 第2圈终点 = times[2*edges_per_lap - 1]
        lap_ends = times[edges_per_lap - 1 :: edges_per_lap]

        # 计算圈时间
        for i in range(1, len(lap_ends)):
            lap_start = lap_ends[i - 1]
            lap_end = lap_ends[i]
            # 圈必须在预热期后开始、仿真结束前完成
            if lap_start < warmup_period:
                continue
            if lap_end > sim_end_time:
                continue
            all_lap_times.append(lap_end - lap_start)

    if not all_lap_times:
        return result

    all_lap_times.sort()
    n = len(all_lap_times)

    result["completed_lap_count"] = n
    result["mean_lap_time_s"] = sum(all_lap_times) / n
    result["lap_time_std_s"] = (
        sum((x - result["mean_lap_time_s"]) ** 2 for x in all_lap_times) / n
    ) ** 0.5
    result["median_lap_time_s"] = (
        all_lap_times[n // 2]
        if n % 2 == 1
        else (all_lap_times[n // 2 - 1] + all_lap_times[n // 2]) / 2
    )
    result["p95_lap_time_s"] = _quantile_higher(all_lap_times, 0.95)
    result["parse_success"] = True

    return result


def parse_lap_times_subgroup(
    xml_path: str,
    type_map: dict[str, str],
    edges_per_lap: int,
    warmup_period: float = 600.0,
    sim_end_time: float = 3600.0,
) -> dict:
    grouped: dict[str, list[float]] = {"all": [], "HV": [], "CAV": []}

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError, OSError):
        return {
            label: {
                "completed_lap_count": 0,
                "mean_lap_time_s": float("nan"),
                "median_lap_time_s": float("nan"),
                "p95_lap_time_s": float("nan"),
                "lap_time_std_s": float("nan"),
                "parse_success": False,
            }
            for label in ("all", "HV", "CAV")
        }

    for vehicle in root.findall("vehicle"):
        vehicle_id = vehicle.get("id", "")
        if vehicle_id not in type_map:
            raise ValueError(f"vehicle_id '{vehicle_id}' not found in type_map")
        veh_type = type_map[vehicle_id]
        if veh_type not in ("HV", "CAV"):
            raise ValueError(f"unexpected vehicle type '{veh_type}' for '{vehicle_id}'")

        route = vehicle.find("route")
        if route is None:
            continue
        exit_times_str = route.get("exitTimes", "")
        if not exit_times_str:
            continue

        times = []
        for t in exit_times_str.split():
            try:
                val = float(t)
                if val < 0:
                    continue
                times.append(val)
            except ValueError:
                continue

        if len(times) < edges_per_lap * 1:
            continue

        lap_ends = times[edges_per_lap - 1 :: edges_per_lap]

        for i in range(1, len(lap_ends)):
            lap_start = lap_ends[i - 1]
            lap_end = lap_ends[i]
            if lap_start < warmup_period:
                continue
            if lap_end > sim_end_time:
                continue
            lap_time = lap_end - lap_start
            grouped["all"].append(lap_time)
            grouped[veh_type].append(lap_time)

    def _stats(values: list[float]) -> dict:
        if not values:
            return {
                "completed_lap_count": 0,
                "mean_lap_time_s": float("nan"),
                "median_lap_time_s": float("nan"),
                "p95_lap_time_s": float("nan"),
                "lap_time_std_s": float("nan"),
                "parse_success": False,
            }
        values.sort()
        n = len(values)
        mean_val = sum(values) / n
        std_val = (sum((x - mean_val) ** 2 for x in values) / n) ** 0.5
        median_val = values[n // 2] if n % 2 == 1 else (values[n // 2 - 1] + values[n // 2]) / 2
        return {
            "completed_lap_count": n,
            "mean_lap_time_s": mean_val,
            "median_lap_time_s": median_val,
            "p95_lap_time_s": _quantile_higher(values, 0.95),
            "lap_time_std_s": std_val,
            "parse_success": True,
        }

    return {
        "all": _stats(grouped["all"]),
        "HV": _stats(grouped["HV"]),
        "CAV": _stats(grouped["CAV"]),
    }
