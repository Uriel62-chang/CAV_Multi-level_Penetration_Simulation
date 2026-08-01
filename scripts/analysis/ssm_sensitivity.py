"""阶段 2 SSM 敏感性分析：TTC 阈值扫描 + mirror dedup 方法比较。"""

import argparse
import csv
import json
import os
from pathlib import Path

from scripts.parsing.ssm import parse_ssm
from scripts.run_spec import load_run_spec

DEDUP_MAP = {
    "none": "none",
    "greedy_one_to_one_80pct": "greedy_one_to_one_80pct",
    "sorted_greedy_80pct": "sorted_greedy_80pct",
}


def _dedup_none(xml_path, warmup, ttc_th, drac_th, simulation_end=None):
    """No dedup: count all valid records directly."""
    import xml.etree.ElementTree as ET

    result = {
        "ttc_event_count": 0,
        "drac_event_count": 0,
        "min_ttc": float("inf"),
        "max_drac": float("-inf"),
        "affected": set(),
    }
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError, OSError):
        return (0, 0, float("nan"), float("nan"), 0)

    for conflict in root.findall("conflict"):
        try:
            begin = float(conflict.get("begin", "0"))
            end = float(conflict.get("end", "0"))
        except (ValueError, TypeError):
            continue
        if end <= warmup or (simulation_end is not None and begin >= simulation_end):
            continue

        ego = conflict.get("ego", "")
        foe = conflict.get("foe", "")

        for elem_name, attr, threshold, compare in [
            ("minTTC", "value", ttc_th, lambda v, t: v < t),
            ("maxDRAC", "value", drac_th, lambda v, t: v > t),
        ]:
            elem = conflict.find(elem_name)
            if elem is None:
                continue
            try:
                val = float(elem.get(attr, ""))
            except (ValueError, TypeError):
                continue
            try:
                etime = float(elem.get("time", "0"))
            except (ValueError, TypeError):
                continue
            if etime < warmup or (simulation_end is not None and etime >= simulation_end):
                continue
            if not compare(val, threshold):
                continue
            if elem_name == "minTTC":
                result["ttc_event_count"] += 1
                result["min_ttc"] = min(result["min_ttc"], val)
                if ego:
                    result["affected"].add(ego)
                if foe:
                    result["affected"].add(foe)
            else:
                result["drac_event_count"] += 1
                result["max_drac"] = max(result["max_drac"], val)

    min_ttc = result["min_ttc"] if result["min_ttc"] != float("inf") else float("nan")
    max_drac = result["max_drac"] if result["max_drac"] != float("-inf") else float("nan")
    return (
        result["ttc_event_count"],
        result["drac_event_count"],
        min_ttc,
        max_drac,
        len(result["affected"]),
    )


def _dedup_current(xml_path, warmup, ttc_th, drac_th, simulation_end=None):
    """Current greedy one-to-one dedup (same as parse_ssm)."""
    result = parse_ssm(xml_path, warmup, ttc_th, drac_th, simulation_end=simulation_end)
    return (
        result["ttc_conflict_event_count"],
        result["drac_conflict_event_count"],
        result["min_ttc_s"],
        result["max_drac_mps2"],
        result["ttc_involved_vehicle_count"],
    )


def _dedup_sorted_greedy(xml_path, warmup, ttc_th, drac_th, simulation_end=None):
    """Sorted greedy: sort records by (begin,end,ego,foe,minTTC,maxDRAC) before dedup."""
    import xml.etree.ElementTree as ET
    from collections import defaultdict

    records = []
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError, OSError):
        return (0, 0, float("nan"), float("nan"), 0)

    for conflict in root.findall("conflict"):
        try:
            begin = float(conflict.get("begin", "0"))
            end = float(conflict.get("end", "0"))
        except (ValueError, TypeError):
            continue
        if end <= warmup or (simulation_end is not None and begin >= simulation_end):
            continue
        ego = conflict.get("ego", "")
        foe = conflict.get("foe", "")

        min_ttc_val = None
        min_ttc_time = 0
        me = conflict.find("minTTC")
        if me is not None:
            try:
                min_ttc_val = float(me.get("value", ""))
                t = float(me.get("time", "0"))
                if warmup <= t and (simulation_end is None or t < simulation_end):
                    min_ttc_time = t
                else:
                    min_ttc_val = None
            except (ValueError, TypeError):
                pass

        max_drac_val = None
        max_drac_time = 0
        mde = conflict.find("maxDRAC")
        if mde is not None:
            try:
                max_drac_val = float(mde.get("value", ""))
                t = float(mde.get("time", "0"))
                if warmup <= t and (simulation_end is None or t < simulation_end):
                    max_drac_time = t
                else:
                    max_drac_val = None
            except (ValueError, TypeError):
                pass

        records.append(
            {
                "ego": ego,
                "foe": foe,
                "begin": begin,
                "end": end,
                "min_ttc": min_ttc_val,
                "max_drac": max_drac_val,
                "min_ttc_time": min_ttc_time,
                "max_drac_time": max_drac_time,
            }
        )

    def _sort_key(r):
        return (
            r["begin"],
            r["end"],
            r["ego"],
            r["foe"],
            r["min_ttc"] if r["min_ttc"] is not None else float("inf"),
            r.get("min_ttc_time", 0) if r.get("min_ttc_time") is not None else 0,
            r["max_drac"] if r["max_drac"] is not None else float("-inf"),
            r.get("max_drac_time", 0) if r.get("max_drac_time") is not None else 0,
        )

    records.sort(key=_sort_key)

    groups = defaultdict(list)
    for idx, rec in enumerate(records):
        pair = tuple(sorted((rec["ego"], rec["foe"])))
        groups[pair].append((idx, rec))

    def _overlap_ratio(a_begin, a_end, b_begin, b_end):
        duration_a = a_end - a_begin
        duration_b = b_end - b_begin
        if duration_a <= 0 or duration_b <= 0:
            return 0.0
        overlap = max(0.0, min(a_end, b_end) - max(a_begin, b_begin))
        return overlap / min(duration_a, duration_b)

    keep = [True] * len(records)
    for pair, entries in groups.items():
        forward = [(i, r) for i, r in entries if r["ego"] == pair[0] and r["foe"] == pair[1]]
        reverse = [(i, r) for i, r in entries if r["ego"] == pair[1] and r["foe"] == pair[0]]
        if not forward or not reverse:
            continue
        matched_reverse = set()
        for i_fwd, r_fwd in forward:
            if not keep[i_fwd]:
                continue
            for i_rev, r_rev in reverse:
                if not keep[i_rev] or i_rev in matched_reverse:
                    continue
                ov = _overlap_ratio(r_fwd["begin"], r_fwd["end"], r_rev["begin"], r_rev["end"])
                if ov >= 0.8:
                    keep[i_rev] = False
                    matched_reverse.add(i_rev)
                    if r_rev["min_ttc"] is not None and (
                        r_fwd["min_ttc"] is None or r_rev["min_ttc"] < r_fwd["min_ttc"]
                    ):
                        r_fwd["min_ttc"] = r_rev["min_ttc"]
                    if r_rev["max_drac"] is not None and (
                        r_fwd["max_drac"] is None or r_rev["max_drac"] > r_fwd["max_drac"]
                    ):
                        r_fwd["max_drac"] = r_rev["max_drac"]
                    break

    ttc_events = 0
    drac_events = 0
    ttc_involved = set()
    min_ttc = float("inf")
    max_drac = float("-inf")
    for idx, rec in enumerate(records):
        if not keep[idx]:
            continue
        if rec["min_ttc"] is not None and rec["min_ttc"] < ttc_th:
            ttc_events += 1
            min_ttc = min(min_ttc, rec["min_ttc"])
            if rec["ego"]:
                ttc_involved.add(rec["ego"])
            if rec["foe"]:
                ttc_involved.add(rec["foe"])
        if rec["max_drac"] is not None and rec["max_drac"] > drac_th:
            drac_events += 1
            max_drac = max(max_drac, rec["max_drac"])

    return (
        ttc_events,
        drac_events,
        min_ttc if min_ttc != float("inf") else float("nan"),
        max_drac if max_drac != float("-inf") else float("nan"),
        len(ttc_involved),
    )


_DEDUP_FUNCS = {
    "none": _dedup_none,
    "greedy_one_to_one_80pct": _dedup_current,
    "sorted_greedy_80pct": _dedup_sorted_greedy,
}


def run_sensitivity(input_root, output_dir, analysis_config_path):
    with open(analysis_config_path) as f:
        config = json.load(f)
    ssm_cfg = config.get("ssm", {})
    ttc_thresholds = ssm_cfg.get("analysis_ttc_thresholds_s", [])
    drac_thresholds = ssm_cfg.get("analysis_drac_thresholds_mps2", [])
    dedup_methods = ssm_cfg.get("dedup_methods", [])

    for method in dedup_methods:
        if method not in DEDUP_MAP and method != "maximum_matching_80pct":
            raise ValueError(f"Unknown dedup method: {method}")
        if method == "maximum_matching_80pct":
            raise ValueError(
                "maximum_matching_80pct is not yet implemented. "
                "Use sorted_greedy_80pct or greedy_one_to_one_80pct instead."
            )

    rows = []
    run_dirs = sorted(
        d for d in Path(input_root).iterdir() if d.is_dir() and (d / "ssm.xml").exists()
    )

    for run_dir in run_dirs:
        run_id = run_dir.name
        try:
            spec = load_run_spec(run_dir)
        except Exception:
            continue
        capture_ttc = spec.ssm_capture_ttc_threshold_s
        capture_drac = spec.ssm_capture_drac_threshold_mps2
        ssm_path = str(run_dir / "ssm_compact.xml")
        if not Path(ssm_path).exists():
            ssm_path = str(run_dir / "ssm.xml")

        # Validate capture envelope
        if ttc_thresholds and max(ttc_thresholds) > capture_ttc:
            raise ValueError(
                f"max analysis TTC {max(ttc_thresholds)}s > capture ceiling {capture_ttc}s"
            )
        if drac_thresholds and min(drac_thresholds) < capture_drac:
            raise ValueError(
                f"min analysis DRAC {min(drac_thresholds)} < capture floor {capture_drac}"
            )

        for method in dedup_methods:
            if method not in _DEDUP_FUNCS:
                continue
            func = _DEDUP_FUNCS[method]
            for th in ttc_thresholds:
                ttc_cnt, _, min_ttc, _, ttc_veh = func(
                    ssm_path, spec.warmup, th, 9999, simulation_end=spec.simulation_end
                )
                rows.append(
                    {
                        "run_id": run_id,
                        "measure": "TTC",
                        "threshold": th,
                        "dedup_method": method,
                        "event_count": ttc_cnt,
                        "extreme_value": min_ttc
                        if not (isinstance(min_ttc, float) and min_ttc != min_ttc)
                        else "",
                        "affected_vehicle_count": ttc_veh,
                    }
                )
            for th in drac_thresholds:
                _, drac_cnt, _, max_drac, _ = func(
                    ssm_path, spec.warmup, 9999, th, simulation_end=spec.simulation_end
                )
                rows.append(
                    {
                        "run_id": run_id,
                        "measure": "DRAC",
                        "threshold": th,
                        "dedup_method": method,
                        "event_count": drac_cnt,
                        "extreme_value": max_drac
                        if not (isinstance(max_drac, float) and max_drac != max_drac)
                        else "",
                        "affected_vehicle_count": "",
                    }
                )

    out = Path(output_dir) / "ssm_sensitivity_results.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".csv.tmp")
    cols = [
        "run_id",
        "measure",
        "threshold",
        "dedup_method",
        "event_count",
        "extreme_value",
        "affected_vehicle_count",
    ]
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, out)
    print(f"[WRITE] {len(rows)} rows → {out}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--analysis-config", default="configs/v0.4.1/analysis.json")
    args = parser.parse_args()
    run_sensitivity(args.input_root, args.output_dir, args.analysis_config)


if __name__ == "__main__":
    main()
