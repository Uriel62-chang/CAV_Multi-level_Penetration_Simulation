"""SUMO stderr 解析：emergency braking 事件提取。"""

import re


def parse_emergency_braking(
    stderr_text: str, warmup_period: float = 600.0, simulation_end: float | None = None
):
    """解析 SUMO stderr 中的 emergency braking 警告。

    Args:
        stderr_text: SUMO 仿真 stderr 文本。
        warmup_period: 预热期 (s)，time < warmup_period 的事件不计入。
        simulation_end: 观测窗上界（审阅 P1-1）；time >= simulation_end 的事件不计入。

    Returns:
        dict: {
            "emergency_braking_count": int,
            "emergency_braking_affected_vehicle_count": int,
            "parse_success": bool,
            "invalid_record_count": int,
        }
        若 stderr_text 为 None（日志缺失），返回 NaN 标记且 parse_success=False。
    """

    if stderr_text is None:
        return {
            "emergency_braking_count": float("nan"),
            "emergency_braking_affected_vehicle_count": float("nan"),
            "parse_success": False,
            "invalid_record_count": 0,
        }

    # 匹配格式：
    # Warning: Vehicle 'veh113' performs emergency braking on lane 'e14_0'
    #          with decel=9.00, wished=4.50, severity=1.00, time=405.80.
    # P2-3（本轮审查）：事件声明与 time 提取分离——旧正则强制 time= 后跟数字，
    # 损坏行（time 缺失/非数值）整行不匹配被静默跳过（与真实零检出不可区分）。
    # 现先匹配事件声明，再在同一行内提取 time；行内无合法 time → invalid。
    event_pattern = re.compile(r"Vehicle '(\S+?)' performs emergency braking")
    time_pattern = re.compile(r"time=([0-9]+(?:\.[0-9]+)?)")

    events = []
    affected = set()
    invalid = 0

    for match in event_pattern.finditer(stderr_text):
        vehicle_id = match.group(1)
        tail = stderr_text[match.end() : match.end() + 200]
        newline = tail.find("\n")
        if newline != -1:
            tail = tail[:newline]
        tm = time_pattern.search(tail)
        if tm is None:
            # P2-3（本轮审查）：匹配到紧急制动但同行无合法 time → 损坏记录
            # fail-closed（parse_success=False），与 subgroup 版 raise 语义对齐
            # （解析器用标志而非 raise）——"日志损坏"与"真实零检出"可区分。
            invalid += 1
            continue
        event_time = float(tm.group(1))

        if event_time < warmup_period:
            continue
        if simulation_end is not None and event_time >= simulation_end:
            continue

        events.append(event_time)
        affected.add(vehicle_id)

    return {
        "emergency_braking_count": len(events),
        "emergency_braking_affected_vehicle_count": len(affected),
        # 审阅 P2-2：显式解析质量标志（声明"日志已处理"；供未来严格校验扩展，
        # 与其他解析器接口对齐——"确实无制动"与"日志未解析"可区分）
        # P2-3（本轮审查）：time 损坏行存在 → parse_success=False
        "parse_success": invalid == 0,
        "invalid_record_count": invalid,
    }


def parse_emergency_braking_subgroup(
    stderr_text: str,
    type_map: dict[str, str],
    warmup_period: float = 600.0,
    simulation_end: float | None = None,
) -> dict:
    if stderr_text is None:
        return {
            label: {
                "emergency_braking_count": float("nan"),
                "emergency_braking_affected_vehicle_count": float("nan"),
                "parse_success": False,
                "invalid_record_count": 0,
            }
            for label in ("all", "HV", "CAV")
        }

    pattern = re.compile(r"Vehicle '(\S+?)' performs emergency braking")
    time_pattern = re.compile(r"time=([0-9]+(?:\.[0-9]+)?)")

    grouped_events: dict[str, list[float]] = {"all": [], "HV": [], "CAV": []}
    grouped_affected: dict[str, set[str]] = {"all": set(), "HV": set(), "CAV": set()}
    invalid = 0

    for match in pattern.finditer(stderr_text):
        vehicle_id = match.group(1)
        tail = stderr_text[match.end() : match.end() + 200]
        newline = tail.find("\n")
        if newline != -1:
            tail = tail[:newline]
        tm = time_pattern.search(tail)
        if tm is None:
            # P2-3（本轮审查）：与顶层版一致——同行无合法 time → invalid
            invalid += 1
            continue
        event_time = float(tm.group(1))

        if event_time < warmup_period:
            continue
        if simulation_end is not None and event_time >= simulation_end:
            continue

        grouped_events["all"].append(event_time)
        grouped_affected["all"].add(vehicle_id)

        if vehicle_id not in type_map:
            raise ValueError(f"vehicle_id '{vehicle_id}' not found in type_map")
        veh_type = type_map[vehicle_id]
        if veh_type not in ("HV", "CAV"):
            raise ValueError(f"unexpected vehicle type '{veh_type}' for '{vehicle_id}'")

        grouped_events[veh_type].append(event_time)
        grouped_affected[veh_type].add(vehicle_id)

    return {
        label: {
            "emergency_braking_count": len(grouped_events[label]),
            "emergency_braking_affected_vehicle_count": len(grouped_affected[label]),
            "parse_success": invalid == 0,
            "invalid_record_count": invalid,
        }
        for label in ("all", "HV", "CAV")
    }
