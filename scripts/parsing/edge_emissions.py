"""SUMO edgeData emissions 解析：排放总量与强度。"""

import math
import xml.etree.ElementTree as ET


def parse_edge_emissions(
    xml_path: str, warmup_period: float = 0.0, simulation_end: float | None = None
):
    """解析 SUMO edgeData type='emissions' XML。

    Args:
        xml_path: edgeData XML 文件路径。
        warmup_period: 仅累计 begin >= 此时刻的完整 interval。
        simulation_end: 观测窗上界（审阅 P1-1）；begin >= simulation_end 的 interval 不计入。

    Returns:
        dict: {
            "total_CO2_kg": float or NaN,
            "total_NOx_g": float or NaN,
            "total_PMx_g": float or NaN,
            "total_fuel_kg": float or NaN,
            "non_internal_CO2_kg": float or NaN,
            "non_internal_NOx_g": float or NaN,
            "non_internal_PMx_g": float or NaN,
            "non_internal_fuel_kg": float or NaN,
            "invalid_record_count": int,
            "parse_success": bool,
        }

    fail-closed（审阅 P1-1 / delta review）：原子验证 interval.begin 与每条
    edge 的 id/sampledSeconds/CO2_abs/NOx_abs/PMx_abs/fuel_abs 后统一累计；
    任何坏记录使 ``parse_success`` 为 False 并计入 ``invalid_record_count``：

    - begin / id / sampledSeconds 缺失、非法、非有限或负 → invalid；
    - 出现但非有限或负的 *_abs → invalid；
    - 无车 edge（sampledSeconds==0.0）缺省 *_abs 为合法零贡献（SUMO 省略）；
      有车（>0）却缺失 → invalid。
    """

    result = {
        "total_CO2_kg": float("nan"),
        "total_NOx_g": float("nan"),
        "total_PMx_g": float("nan"),
        "total_fuel_kg": float("nan"),
        "non_internal_CO2_kg": float("nan"),
        "non_internal_NOx_g": float("nan"),
        "non_internal_PMx_g": float("nan"),
        "non_internal_fuel_kg": float("nan"),
        "invalid_record_count": 0,
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
    invalid_record_count = 0

    _EMIS_KEYS = ("CO2_abs", "NOx_abs", "PMx_abs", "fuel_abs")

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
            # 无车 edge（ss==0）：*_abs 缺省合法零贡献；有车（ss>0）必须给出
            default = 0.0 if sampled_seconds == 0.0 else None
            values = {}
            for key in _EMIS_KEYS:
                value = _nonneg_attr(edge, key, default)
                if value is None:
                    invalid_record_count += 1
                    break
                values[key] = value
            else:
                # 原子：全部验证通过后统一累计
                total_co2_mg += values["CO2_abs"]
                total_nox_mg += values["NOx_abs"]
                total_pmx_mg += values["PMx_abs"]
                total_fuel_mg += values["fuel_abs"]
                if not edge_id.startswith(":"):
                    ni_co2_mg += values["CO2_abs"]
                    ni_nox_mg += values["NOx_abs"]
                    ni_pmx_mg += values["PMx_abs"]
                    ni_fuel_mg += values["fuel_abs"]

    # 转换为 kg / g / kg
    result["non_internal_CO2_kg"] = ni_co2_mg / 1e6
    result["non_internal_NOx_g"] = ni_nox_mg / 1e3
    result["non_internal_PMx_g"] = ni_pmx_mg / 1e3
    result["non_internal_fuel_kg"] = ni_fuel_mg / 1e6
    result["total_CO2_kg"] = total_co2_mg / 1e6
    result["total_NOx_g"] = total_nox_mg / 1e3
    result["total_PMx_g"] = total_pmx_mg / 1e3
    result["total_fuel_kg"] = total_fuel_mg / 1e6
    result["invalid_record_count"] = invalid_record_count
    result["parse_success"] = invalid_record_count == 0
    return result
