"""SUMO SSM 输出解析：TTC / DRAC 冲突提取 + 时间区间镜像去重。"""

import xml.etree.ElementTree as ET
from collections import defaultdict

# 镜像判定：方向相反且 min(较短时长) 覆盖比 ≥ 阈值
_MIRROR_OVERLAP_RATIO = 0.8


def _overlap_ratio(a_begin: float, a_end: float, b_begin: float, b_end: float) -> float:
    """重叠时长 / min(|A|, |B|)。"""
    duration_a = a_end - a_begin
    duration_b = b_end - b_begin
    if duration_a <= 0 or duration_b <= 0:
        return 0.0
    overlap = max(0.0, min(a_end, b_end) - max(a_begin, b_begin))
    return overlap / min(duration_a, duration_b)


def parse_ssm(
    xml_path: str,
    warmup_period: float = 600.0,
    ttc_threshold: float = 3.0,
    drac_threshold: float = 3.0,
):
    """解析 SUMO SSM 输出 XML。

    1. 收集所有有效记录
    2. 按车辆对分组，组内一对一匹配时间重叠的 ego↔foe 镜像
    3. TTC / DRAC 分别统计

    Returns dict with event counts, min/max values, vehicle counts,
    audit trail counters, and parse_success flag.
    """

    result = {
        "ttc_conflict_event_count": 0,
        "min_ttc_s": float("nan"),
        "ttc_involved_vehicle_count": 0,
        "drac_conflict_event_count": 0,
        "max_drac_mps2": float("nan"),
        "ssm_raw_record_count": 0,
        "ssm_invalid_record_count": 0,
        "ssm_warmup_filtered_count": 0,
        "ssm_valid_record_count": 0,
        "ssm_mirrored_record_count": 0,
        "parse_success": False,
    }

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError, OSError):
        return result

    # ── 第一步：收集记录 ──
    records = []
    invalid = 0

    records.extend(root.findall("conflict"))

    raw_count = len(records)

    parsed = []
    warmup_filtered = 0
    for conflict in records:
        try:
            begin = float(conflict.get("begin", "0"))
            end = float(conflict.get("end", "0"))
        except (ValueError, TypeError):
            invalid += 1
            continue

        if end <= warmup_period:
            warmup_filtered += 1
            continue

        ego = conflict.get("ego", "")
        foe = conflict.get("foe", "")

        # TTC
        ttc_val = None
        min_ttc_elem = conflict.find("minTTC")
        if min_ttc_elem is not None:
            try:
                ttc_val = float(min_ttc_elem.get("value", ""))
                ttc_time = float(min_ttc_elem.get("time", str(begin)))
                if ttc_time < warmup_period:
                    ttc_val = None
            except (ValueError, TypeError):
                ttc_val = None

        # DRAC
        drac_val = None
        max_drac_elem = conflict.find("maxDRAC")
        if max_drac_elem is not None:
            try:
                drac_val = float(max_drac_elem.get("value", ""))
                drac_time = float(max_drac_elem.get("time", str(begin)))
                if drac_time < warmup_period:
                    drac_val = None
            except (ValueError, TypeError):
                drac_val = None

        parsed.append(
            {
                "ego": ego,
                "foe": foe,
                "begin": begin,
                "end": end,
                "min_ttc": ttc_val,
                "max_drac": drac_val,
            }
        )

    valid_count = len(parsed)

    # ── 第二步：按车辆对分组，组内一对一匹配镜像 ──
    groups = defaultdict(list)
    for idx, rec in enumerate(parsed):
        pair = tuple(sorted((rec["ego"], rec["foe"])))
        groups[pair].append((idx, rec))

    keep = [True] * len(parsed)
    mirrored = 0

    for pair, entries in groups.items():
        # 分为 A→B 和 B→A 两个方向
        forward = [(i, r) for i, r in entries if r["ego"] == pair[0] and r["foe"] == pair[1]]
        reverse = [(i, r) for i, r in entries if r["ego"] == pair[1] and r["foe"] == pair[0]]

        if not forward or not reverse:
            continue

        # 从较短的列表出发，每个元素只匹配一次
        matched_reverse = set()
        for i_fwd, r_fwd in forward:
            if not keep[i_fwd]:
                continue
            best_idx = -1
            best_overlap = 0.0
            for i_rev, r_rev in reverse:
                if not keep[i_rev] or i_rev in matched_reverse:
                    continue
                ov = _overlap_ratio(
                    r_fwd["begin"],
                    r_fwd["end"],
                    r_rev["begin"],
                    r_rev["end"],
                )
                if ov >= _MIRROR_OVERLAP_RATIO and ov > best_overlap:
                    best_overlap = ov
                    best_idx = i_rev

            if best_idx >= 0:
                keep[best_idx] = False
                matched_reverse.add(best_idx)
                mirrored += 1
                # 合并极值到保留记录
                r_rev = parsed[best_idx]
                if r_rev["min_ttc"] is not None and (
                    r_fwd["min_ttc"] is None or r_rev["min_ttc"] < r_fwd["min_ttc"]
                ):
                    r_fwd["min_ttc"] = r_rev["min_ttc"]
                if r_rev["max_drac"] is not None and (
                    r_fwd["max_drac"] is None or r_rev["max_drac"] > r_fwd["max_drac"]
                ):
                    r_fwd["max_drac"] = r_rev["max_drac"]

    # ── 第三步：统计保留记录 ──
    ttc_events = 0
    drac_events = 0
    ttc_involved = set()
    min_ttc = float("inf")
    max_drac = float("-inf")

    for idx, rec in enumerate(parsed):
        if not keep[idx]:
            continue

        has_ttc = rec["min_ttc"] is not None and rec["min_ttc"] < ttc_threshold
        has_drac = rec["max_drac"] is not None and rec["max_drac"] > drac_threshold

        if has_ttc:
            ttc_events += 1
            min_ttc = min(min_ttc, rec["min_ttc"])
            if rec["ego"]:
                ttc_involved.add(rec["ego"])
            if rec["foe"]:
                ttc_involved.add(rec["foe"])

        if has_drac:
            drac_events += 1
            max_drac = max(max_drac, rec["max_drac"])

    result["ssm_raw_record_count"] = raw_count
    result["ssm_invalid_record_count"] = invalid
    result["ssm_warmup_filtered_count"] = warmup_filtered
    result["ssm_valid_record_count"] = valid_count
    result["ssm_mirrored_record_count"] = mirrored
    result["ttc_conflict_event_count"] = ttc_events
    result["min_ttc_s"] = min_ttc if min_ttc != float("inf") else float("nan")
    result["ttc_involved_vehicle_count"] = len(ttc_involved)
    result["drac_conflict_event_count"] = drac_events
    result["max_drac_mps2"] = max_drac if max_drac != float("-inf") else float("nan")
    result["parse_success"] = True
    return result
