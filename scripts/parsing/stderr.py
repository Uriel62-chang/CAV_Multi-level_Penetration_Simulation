"""SUMO stderr 解析：emergency braking 事件提取。"""

import re


def parse_emergency_braking(stderr_text: str, warmup_period: float = 600.0):
    """解析 SUMO stderr 中的 emergency braking 警告。

    Args:
        stderr_text: SUMO 仿真 stderr 文本。
        warmup_period: 预热期 (s)，time < warmup_period 的事件不计入。

    Returns:
        dict: {
            "emergency_braking_count": int,
            "emergency_braking_affected_vehicle_count": int,
        }
        若 stderr_text 为 None 或无法解析，返回 NaN 标记。
    """
    import math

    if stderr_text is None:
        return {
            "emergency_braking_count": float("nan"),
            "emergency_braking_affected_vehicle_count": float("nan"),
        }

    # 匹配格式：
    # Warning: Vehicle 'veh113' performs emergency braking on lane 'e14_0'
    #          with decel=9.00, wished=4.50, severity=1.00, time=405.80.
    pattern = re.compile(
        r"Vehicle '(\S+?)' performs emergency braking.*?time=([0-9]+(?:\.[0-9]+)?)"
    )

    events = []
    affected = set()

    for match in pattern.finditer(stderr_text):
        vehicle_id = match.group(1)
        try:
            event_time = float(match.group(2))
        except ValueError:
            continue

        if event_time < warmup_period:
            continue

        events.append(event_time)
        affected.add(vehicle_id)

    return {
        "emergency_braking_count": len(events),
        "emergency_braking_affected_vehicle_count": len(affected),
    }
