"""SUMO FCD 输出解析：physical THW 计算（流式 gzip/plain XML）。"""

from __future__ import annotations

import gzip
import math
import xml.etree.ElementTree as ET
from array import array

import numpy as np


def parse_fcd(
    fcd_path: str,
    type_map: dict[str, str],
    warmup_period: float = 600.0,
    simulation_end: float | None = None,
    thw_min_speed_mps: float = 0.1,
) -> dict:

    def _init() -> dict:
        return {
            "mean_thw_s": float("nan"),
            "median_thw_s": float("nan"),
            "p05_thw_s": float("nan"),
            "thw_lt_1s_ratio": float("nan"),
            "valid_thw_sample_count": 0,
            "low_speed_excluded_count": 0,
            "no_leader_count": 0,
            "self_leader_count": 0,
            "parse_success": False,
        }

    result = {"all": _init(), "HV": _init(), "CAV": _init()}
    # 审阅 P1-1：非法/非有限 timestep 时间计数——fail-closed，不得静默丢弃 FCD 数据
    invalid = 0
    # 审阅 P1-2：窗内 timestep 计数——空/全窗外 FCD 不得判为成功（与"正常采集但
    # 无有效样本"可区分）
    windowed_timesteps = 0

    open_fn = gzip.open if fcd_path.endswith(".gz") else open

    try:
        all_arr = array("d")
        hv_arr = array("d")
        cav_arr = array("d")

        with open_fn(fcd_path, "rb") as f:
            for _event, elem in ET.iterparse(f, events=("end",)):
                if elem.tag != "timestep":
                    continue
                # 审阅 P2-4：缺失 time 属性 → invalid（不得默认 0 被 warmup 静默过滤）
                time_raw = elem.get("time")
                if time_raw is None:
                    invalid += 1
                    elem.clear()
                    continue
                try:
                    time = float(time_raw)
                except (ValueError, TypeError):
                    invalid += 1
                    elem.clear()
                    continue
                if not math.isfinite(time):
                    invalid += 1
                    elem.clear()
                    continue
                if time < warmup_period:
                    elem.clear()
                    continue
                if simulation_end is not None and time >= simulation_end:
                    elem.clear()
                    continue

                windowed_timesteps += 1

                for veh in elem.findall("vehicle"):
                    vid = veh.get("id", "")
                    if vid not in type_map:
                        elem.clear()
                        for key in ("all", "HV", "CAV"):
                            result[key]["parse_success"] = False
                        return result

                    vt = type_map[vid]
                    fcd_type = veh.get("type", "")
                    if fcd_type != vt:
                        elem.clear()
                        for key in ("all", "HV", "CAV"):
                            result[key]["parse_success"] = False
                        return result

                    try:
                        speed = float(veh.get("speed", ""))
                    except (ValueError, TypeError):
                        # P1-1（本轮审查）：speed 解析失败/非有限 → low_speed_excluded
                        # 台账（设计 §6.3 步骤 2），与 gap 分支（步骤 3 → no_leader）一致；
                        # 不再计 invalid（整 run fail-closed），仅剔除该样本。
                        result["all"]["low_speed_excluded_count"] += 1
                        result[vt]["low_speed_excluded_count"] += 1
                        continue
                    if not math.isfinite(speed):
                        result["all"]["low_speed_excluded_count"] += 1
                        result[vt]["low_speed_excluded_count"] += 1
                        continue

                    gap_str = veh.get("leaderGap", "")
                    if gap_str == "":
                        result["all"]["no_leader_count"] += 1
                        result[vt]["no_leader_count"] += 1
                        continue
                    try:
                        leader_gap = float(gap_str)
                    except (ValueError, TypeError):
                        result["all"]["no_leader_count"] += 1
                        result[vt]["no_leader_count"] += 1
                        continue
                    if leader_gap <= 0 or not math.isfinite(leader_gap):
                        result["all"]["no_leader_count"] += 1
                        result[vt]["no_leader_count"] += 1
                        continue

                    leader_id = veh.get("leaderID", "")
                    if leader_id == "":
                        result["all"]["no_leader_count"] += 1
                        result[vt]["no_leader_count"] += 1
                        continue
                    if leader_id == vid:
                        result["all"]["self_leader_count"] += 1
                        result[vt]["self_leader_count"] += 1
                        continue

                    if speed < thw_min_speed_mps:
                        result["all"]["low_speed_excluded_count"] += 1
                        result[vt]["low_speed_excluded_count"] += 1
                        continue

                    thw = leader_gap / speed
                    if not math.isfinite(thw):
                        result["all"]["no_leader_count"] += 1
                        result[vt]["no_leader_count"] += 1
                        continue

                    all_arr.append(thw)
                    if vt == "HV":
                        hv_arr.append(thw)
                    else:
                        cav_arr.append(thw)

                elem.clear()

        for label, arr in [("all", all_arr), ("HV", hv_arr), ("CAV", cav_arr)]:
            result[label]["parse_success"] = invalid == 0 and windowed_timesteps > 0
            if len(arr) == 0:
                continue
            a = np.array(arr, dtype=np.float64)
            a.sort()
            n = len(a)
            result[label]["valid_thw_sample_count"] = n
            result[label]["mean_thw_s"] = float(np.mean(a))
            result[label]["median_thw_s"] = float(np.median(a))
            p05_idx = math.ceil((n - 1) * 0.05)
            result[label]["p05_thw_s"] = float(a[p05_idx])
            result[label]["thw_lt_1s_ratio"] = float(np.sum(a < 1.0) / n)

    except (ET.ParseError, FileNotFoundError, OSError, EOFError):
        pass

    return result
