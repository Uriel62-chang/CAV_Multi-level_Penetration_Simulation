"""SUMO lanechange-output 解析：换道计数与间隙安全判定。"""

import xml.etree.ElementTree as ET


def parse_lanechange(xml_path: str, warmup_period: float = 600.0):
    """解析 SUMO lanechange-output XML。

    Args:
        xml_path: lanechange XML 文件路径。
        warmup_period: 预热期 (s)，time < warmup_period 的换道不计入。

    Returns:
        dict: {
            "lane_change_count": int,
            "unsafe_lc_gap_count": int,
            "unsafe_lc_gap_ratio": float or NaN,
            "parse_success": bool,
        }
    """

    result = {
        "lane_change_count": 0,
        "unsafe_lc_gap_count": 0,
        "unsafe_lc_gap_ratio": float("nan"),
        "parse_success": False,
    }

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError, OSError):
        return result

    total = 0
    unsafe = 0

    for change in root.findall("change"):
        try:
            time_val = float(change.get("time", "0"))
        except (ValueError, TypeError):
            continue

        if time_val < warmup_period:
            continue

        total += 1

        # 间隙安全判定
        leader_gap = _parse_float_attr(change, "leaderGap")
        leader_secure = _parse_float_attr(change, "leaderSecureGap")
        follower_gap = _parse_float_attr(change, "followerGap")
        follower_secure = _parse_float_attr(change, "followerSecureGap")

        leader_unsafe = (
            leader_gap is not None and leader_secure is not None and leader_gap < leader_secure
        )
        follower_unsafe = (
            follower_gap is not None
            and follower_secure is not None
            and follower_gap < follower_secure
        )

        if leader_unsafe or follower_unsafe:
            unsafe += 1

    result["lane_change_count"] = total
    result["unsafe_lc_gap_count"] = unsafe
    result["unsafe_lc_gap_ratio"] = unsafe / total if total > 0 else float("nan")
    result["parse_success"] = True
    return result


def parse_lanechange_subgroup(
    xml_path: str,
    type_map: dict[str, str],
    warmup_period: float = 600.0,
) -> dict:
    counts: dict[str, dict[str, int]] = {
        "all": {"total": 0, "unsafe": 0},
        "HV": {"total": 0, "unsafe": 0},
        "CAV": {"total": 0, "unsafe": 0},
    }

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError, OSError):
        return {
            label: {
                "lane_change_count": 0,
                "unsafe_lc_gap_count": 0,
                "unsafe_lc_gap_ratio": float("nan"),
                "parse_success": False,
            }
            for label in ("all", "HV", "CAV")
        }

    for change in root.findall("change"):
        change_id = change.get("id", "")
        if change_id not in type_map:
            raise ValueError(f"change id '{change_id}' not found in type_map")
        veh_type = type_map[change_id]
        if veh_type not in ("HV", "CAV"):
            raise ValueError(f"unexpected vehicle type '{veh_type}' for '{change_id}'")

        try:
            time_val = float(change.get("time", "0"))
        except (ValueError, TypeError):
            continue

        if time_val < warmup_period:
            continue

        counts["all"]["total"] += 1
        counts[veh_type]["total"] += 1

        leader_gap = _parse_float_attr(change, "leaderGap")
        leader_secure = _parse_float_attr(change, "leaderSecureGap")
        follower_gap = _parse_float_attr(change, "followerGap")
        follower_secure = _parse_float_attr(change, "followerSecureGap")

        leader_unsafe = (
            leader_gap is not None and leader_secure is not None and leader_gap < leader_secure
        )
        follower_unsafe = (
            follower_gap is not None
            and follower_secure is not None
            and follower_gap < follower_secure
        )

        if leader_unsafe or follower_unsafe:
            counts["all"]["unsafe"] += 1
            counts[veh_type]["unsafe"] += 1

    def _build(label: str) -> dict:
        t = counts[label]["total"]
        u = counts[label]["unsafe"]
        return {
            "lane_change_count": t,
            "unsafe_lc_gap_count": u,
            "unsafe_lc_gap_ratio": u / t if t > 0 else float("nan"),
            "parse_success": True,
        }

    return {"all": _build("all"), "HV": _build("HV"), "CAV": _build("CAV")}


def _parse_float_attr(elem, attr_name):
    """安全解析 XML 属性为 float，None 或 'None' 都返回 None。"""
    val = elem.get(attr_name)
    if val is None or val == "None":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
