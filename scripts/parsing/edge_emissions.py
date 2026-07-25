"""SUMO edgeData emissions 解析：排放总量与强度。"""

import xml.etree.ElementTree as ET


def parse_edge_emissions(xml_path: str):
    """解析 SUMO edgeData type='emissions' XML。

    Args:
        xml_path: edgeData XML 文件路径。

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

    for interval in root.findall("interval"):
        for edge in interval.findall("edge"):
            try:
                total_co2_mg += float(edge.get("CO2_abs", "0"))
                total_nox_mg += float(edge.get("NOx_abs", "0"))
                total_pmx_mg += float(edge.get("PMx_abs", "0"))
                total_fuel_mg += float(edge.get("fuel_abs", "0"))
            except (ValueError, TypeError):
                continue

    # 转换为 kg / g / kg
    result["total_CO2_kg"] = total_co2_mg / 1e6
    result["total_NOx_g"] = total_nox_mg / 1e3
    result["total_PMx_g"] = total_pmx_mg / 1e3
    result["total_fuel_kg"] = total_fuel_mg / 1e6
    result["parse_success"] = True
    return result
