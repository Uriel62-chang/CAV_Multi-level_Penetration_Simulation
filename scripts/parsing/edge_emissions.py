"""SUMO edgeData emissions 解析：排放总量与强度。"""

import xml.etree.ElementTree as ET


def parse_edge_emissions(xml_path: str, warmup_period: float = 0.0):
    """解析 SUMO edgeData type='emissions' XML。

    Args:
        xml_path: edgeData XML 文件路径。
        warmup_period: 仅累计 begin >= 此时刻的完整 interval。

    Returns:
        dict: {
            "total_CO2_kg": float or NaN,
            "total_NOx_g": float or NaN,
            "total_PMx_g": float or NaN,
            "total_fuel_kg": float or NaN,
            "parse_success": bool,
        }
    """

    result = {
        "total_CO2_kg": float("nan"),
        "total_NOx_g": float("nan"),
        "total_PMx_g": float("nan"),
        "total_fuel_kg": float("nan"),
        "parse_success": False,
    }

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError, OSError):
        return result

    total_co2_mg = 0.0
    total_nox_mg = 0.0
    total_pmx_mg = 0.0
    total_fuel_mg = 0.0
    # P0-7：non-internal-edge 双累计（internal edge id 以 ":" 开头，与 performance 一致）
    ni_co2_mg = 0.0
    ni_nox_mg = 0.0
    ni_pmx_mg = 0.0
    ni_fuel_mg = 0.0

    for interval in root.findall("interval"):
        try:
            interval_begin = float(interval.get("begin", "0"))
        except (ValueError, TypeError):
            continue
        if interval_begin < warmup_period:
            continue
        for edge in interval.findall("edge"):
            try:
                co2_mg = float(edge.get("CO2_abs", "0"))
                nox_mg = float(edge.get("NOx_abs", "0"))
                pmx_mg = float(edge.get("PMx_abs", "0"))
                fuel_mg = float(edge.get("fuel_abs", "0"))
            except (ValueError, TypeError):
                continue
            total_co2_mg += co2_mg
            total_nox_mg += nox_mg
            total_pmx_mg += pmx_mg
            total_fuel_mg += fuel_mg
            if not edge.get("id", "").startswith(":"):
                ni_co2_mg += co2_mg
                ni_nox_mg += nox_mg
                ni_pmx_mg += pmx_mg
                ni_fuel_mg += fuel_mg

    # 转换为 kg / g / kg
    result["non_internal_CO2_kg"] = ni_co2_mg / 1e6
    result["non_internal_NOx_g"] = ni_nox_mg / 1e3
    result["non_internal_PMx_g"] = ni_pmx_mg / 1e3
    result["non_internal_fuel_kg"] = ni_fuel_mg / 1e6
    result["total_CO2_kg"] = total_co2_mg / 1e6
    result["total_NOx_g"] = total_nox_mg / 1e3
    result["total_PMx_g"] = total_pmx_mg / 1e3
    result["total_fuel_kg"] = total_fuel_mg / 1e6
    result["parse_success"] = True
    return result
