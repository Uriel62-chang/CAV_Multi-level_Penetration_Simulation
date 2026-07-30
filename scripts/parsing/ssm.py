"""SUMO SSM 输出解析：TTC / DRAC 冲突提取 + 时间区间镜像去重。"""

import xml.etree.ElementTree as ET
from collections import defaultdict

# 镜像判定：方向相反且 min(较短时长) 覆盖比 ≥ 阈值
_MIRROR_OVERLAP_RATIO = 0.8

# extratime=1.0 后置同向碎片合并间隔 (s)，默认 0 禁用
_FRAGMENT_MERGE_GAP_S = 0.0


def _overlap_ratio(a_begin: float, a_end: float, b_begin: float, b_end: float) -> float:
    """重叠时长 / min(|A|, |B|)。"""
    duration_a = a_end - a_begin
    duration_b = b_end - b_begin
    if duration_a <= 0 or duration_b <= 0:
        return 0.0
    overlap = max(0.0, min(a_end, b_end) - max(a_begin, b_begin))
    return overlap / min(duration_a, duration_b)


def _merge_fragments(records, gap_s=5.0):
    """按有向 (ego, foe) 合并 ≤5s 间隙的同向碎片。

    Returns (merged_records, fragments_absorbed).
    每个 group 内按 begin 排序，相邻记录 end→begin ≤ _FRAGMENT_MERGE_GAP_S 时合并，
    保留更危急的 TTC/DRAC 极值及其 provenance（time, type_code, source_ego, source_foe）。
    """
    groups = defaultdict(list)
    for rec in records:
        groups[(rec["ego"], rec["foe"])].append(rec)

    merged = []
    absorbed = 0
    for recs in groups.values():
        recs.sort(key=lambda r: r["begin"])
        current = None
        for rec in recs:
            if current is None:
                current = dict(rec)
                continue
            gap = rec["begin"] - current["end"]
            if gap <= gap_s:
                current["end"] = max(current["end"], rec["end"])
                if rec.get("min_ttc") is not None and (
                    current.get("min_ttc") is None or rec["min_ttc"] < current["min_ttc"]
                ):
                    current["min_ttc"] = rec["min_ttc"]
                    current["min_ttc_time"] = rec.get("min_ttc_time", 0)
                    current["min_ttc_type_code"] = rec.get("min_ttc_type_code")
                    current["min_ttc_source_ego"] = rec["ego"]
                    current["min_ttc_source_foe"] = rec["foe"]
                if rec.get("max_drac") is not None and (
                    current.get("max_drac") is None or rec["max_drac"] > current["max_drac"]
                ):
                    current["max_drac"] = rec["max_drac"]
                    current["max_drac_time"] = rec.get("max_drac_time", 0)
                    current["max_drac_type_code"] = rec.get("max_drac_type_code")
                    current["max_drac_source_ego"] = rec["ego"]
                    current["max_drac_source_foe"] = rec["foe"]
                absorbed += 1
            else:
                merged.append(current)
                current = dict(rec)
        if current is not None:
            merged.append(current)
    return merged, absorbed


def parse_ssm(
    xml_path: str,
    warmup_period: float = 600.0,
    ttc_threshold: float = 3.0,
    drac_threshold: float = 3.0,
    fragment_merge_gap_s: float = 0.0,
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
        "ssm_fragment_merged_count": 0,
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

    if fragment_merge_gap_s > 0:
        parsed, fragment_merged = _merge_fragments(parsed, gap_s=fragment_merge_gap_s)
    else:
        fragment_merged = 0

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
    result["ssm_fragment_merged_count"] = fragment_merged
    result["ttc_conflict_event_count"] = ttc_events
    result["min_ttc_s"] = min_ttc if min_ttc != float("inf") else float("nan")
    result["ttc_involved_vehicle_count"] = len(ttc_involved)
    result["drac_conflict_event_count"] = drac_events
    result["max_drac_mps2"] = max_drac if max_drac != float("-inf") else float("nan")
    result["parse_success"] = True
    return result


def _make_default_all_result() -> dict:
    return {
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
        "ssm_fragment_merged_count": 0,
        "parse_success": False,
    }


def parse_ssm_subgroup(
    xml_path: str,
    type_map: dict[str, str],
    warmup_period: float = 600.0,
    ttc_threshold: float = 3.0,
    drac_threshold: float = 3.0,
    fragment_merge_gap_s: float = 0.0,
) -> dict:
    all_result = _make_default_all_result()

    pair_keys = ("pair_HV_HV", "pair_HV_CAV", "pair_CAV_CAV")
    role_keys = (
        "role_f_HV_l_HV",
        "role_f_HV_l_CAV",
        "role_f_CAV_l_HV",
        "role_f_CAV_l_CAV",
    )
    zero_event = {"ttc_event_count": 0, "drac_event_count": 0}
    result: dict = {"all": all_result, "unclassified": dict(zero_event)}
    for pk in pair_keys:
        result[pk] = dict(zero_event)
    for rk in role_keys:
        result[rk] = dict(zero_event)

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError, OSError):
        return result

    records = []
    invalid = 0

    records.extend(root.findall("conflict"))

    raw_count = len(records)

    parsed: list[dict] = []
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

        ttc_val = None
        ttc_type_code = None
        ttc_time = 0.0
        min_ttc_elem = conflict.find("minTTC")
        if min_ttc_elem is not None:
            try:
                ttc_val = float(min_ttc_elem.get("value", ""))
                ttc_time = float(min_ttc_elem.get("time", str(begin)))
                ttc_type_code = int(min_ttc_elem.get("type", "0"))
                if ttc_time < warmup_period:
                    ttc_val = None
                    ttc_type_code = None
            except (ValueError, TypeError):
                ttc_val = None
                ttc_type_code = None

        drac_val = None
        drac_type_code = None
        drac_time = 0.0
        max_drac_elem = conflict.find("maxDRAC")
        if max_drac_elem is not None:
            try:
                drac_val = float(max_drac_elem.get("value", ""))
                drac_time = float(max_drac_elem.get("time", str(begin)))
                drac_type_code = int(max_drac_elem.get("type", "0"))
                if drac_time < warmup_period:
                    drac_val = None
                    drac_type_code = None
            except (ValueError, TypeError):
                drac_val = None
                drac_type_code = None

        parsed.append(
            {
                "ego": ego,
                "foe": foe,
                "begin": begin,
                "end": end,
                "min_ttc": ttc_val,
                "min_ttc_type_code": ttc_type_code,
                "min_ttc_time": ttc_time,
                "max_drac": drac_val,
                "max_drac_type_code": drac_type_code,
                "max_drac_time": drac_time,
                "min_ttc_source_ego": ego,
                "min_ttc_source_foe": foe,
                "max_drac_source_ego": ego,
                "max_drac_source_foe": foe,
            }
        )

    valid_count = len(parsed)

    if fragment_merge_gap_s > 0:
        parsed, fragment_merged = _merge_fragments(parsed, gap_s=fragment_merge_gap_s)
    else:
        fragment_merged = 0

    groups = defaultdict(list)
    for idx, rec in enumerate(parsed):
        pair = tuple(sorted((rec["ego"], rec["foe"])))
        groups[pair].append((idx, rec))

    keep = [True] * len(parsed)
    mirrored = 0

    for pair, entries in groups.items():
        forward = [(i, r) for i, r in entries if r["ego"] == pair[0] and r["foe"] == pair[1]]
        reverse = [(i, r) for i, r in entries if r["ego"] == pair[1] and r["foe"] == pair[0]]

        if not forward or not reverse:
            continue

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
                r_rev = parsed[best_idx]
                if r_rev["min_ttc"] is not None and (
                    r_fwd["min_ttc"] is None or r_rev["min_ttc"] < r_fwd["min_ttc"]
                ):
                    r_fwd["min_ttc"] = r_rev["min_ttc"]
                    r_fwd["min_ttc_type_code"] = r_rev["min_ttc_type_code"]
                    r_fwd["min_ttc_time"] = r_rev.get("min_ttc_time", 0)
                    r_fwd["min_ttc_source_ego"] = r_rev["ego"]
                    r_fwd["min_ttc_source_foe"] = r_rev["foe"]
                if r_rev["max_drac"] is not None and (
                    r_fwd["max_drac"] is None or r_rev["max_drac"] > r_fwd["max_drac"]
                ):
                    r_fwd["max_drac"] = r_rev["max_drac"]
                    r_fwd["max_drac_type_code"] = r_rev["max_drac_type_code"]
                    r_fwd["max_drac_time"] = r_rev.get("max_drac_time", 0)
                    r_fwd["max_drac_source_ego"] = r_rev["ego"]
                    r_fwd["max_drac_source_foe"] = r_rev["foe"]

    ttc_events = 0
    drac_events = 0
    ttc_involved: set[str] = set()
    min_ttc = float("inf")
    max_drac = float("-inf")

    type_order = {"HV": 0, "CAV": 1}

    def _classify_role(rec_type_code, rec_ego_type, rec_foe_type):
        if rec_type_code not in (2, 3):
            return None
        if rec_type_code == 2:
            return f"role_f_{rec_ego_type}_l_{rec_foe_type}"
        if rec_type_code == 3:
            return f"role_f_{rec_foe_type}_l_{rec_ego_type}"
        return None

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

        if not has_ttc and not has_drac:
            continue

        pair_ego = rec.get("min_ttc_source_ego") or rec["ego"]
        pair_foe = rec.get("min_ttc_source_foe") or rec["foe"]
        ego_type = type_map.get(pair_ego, "UNKNOWN")
        foe_type = type_map.get(pair_foe, "UNKNOWN")

        pair_key = tuple(sorted([ego_type, foe_type], key=lambda t: type_order.get(t, 2)))
        pair_type = f"pair_{pair_key[0]}_{pair_key[1]}"

        if has_ttc and pair_type in result:
            result[pair_type]["ttc_event_count"] += 1
        if has_drac and pair_type in result:
            result[pair_type]["drac_event_count"] += 1

        if has_ttc:
            ttc_src_ego = rec.get("min_ttc_source_ego") or rec["ego"]
            ttc_src_foe = rec.get("min_ttc_source_foe") or rec["foe"]
            ttc_src_etype = type_map.get(ttc_src_ego, "UNKNOWN")
            ttc_src_ftype = type_map.get(ttc_src_foe, "UNKNOWN")
            ttc_role = _classify_role(rec.get("min_ttc_type_code"), ttc_src_etype, ttc_src_ftype)
            if ttc_role and ttc_role in result:
                result[ttc_role]["ttc_event_count"] += 1
            else:
                result["unclassified"]["ttc_event_count"] += 1

        if has_drac:
            drac_src_ego = rec.get("max_drac_source_ego") or rec["ego"]
            drac_src_foe = rec.get("max_drac_source_foe") or rec["foe"]
            drac_src_etype = type_map.get(drac_src_ego, "UNKNOWN")
            drac_src_ftype = type_map.get(drac_src_foe, "UNKNOWN")
            drac_role = _classify_role(
                rec.get("max_drac_type_code"), drac_src_etype, drac_src_ftype
            )
            if drac_role and drac_role in result:
                result[drac_role]["drac_event_count"] += 1
            else:
                result["unclassified"]["drac_event_count"] += 1

    all_result["ssm_raw_record_count"] = raw_count
    all_result["ssm_invalid_record_count"] = invalid
    all_result["ssm_warmup_filtered_count"] = warmup_filtered
    all_result["ssm_valid_record_count"] = valid_count
    all_result["ssm_mirrored_record_count"] = mirrored
    all_result["ssm_fragment_merged_count"] = fragment_merged
    all_result["ttc_conflict_event_count"] = ttc_events
    all_result["min_ttc_s"] = min_ttc if min_ttc != float("inf") else float("nan")
    all_result["ttc_involved_vehicle_count"] = len(ttc_involved)
    all_result["drac_conflict_event_count"] = drac_events
    all_result["max_drac_mps2"] = max_drac if max_drac != float("-inf") else float("nan")
    all_result["parse_success"] = True
    return result
