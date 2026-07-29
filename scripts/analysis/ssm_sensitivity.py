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


def _dedup_none(xml_path, warmup, ttc_th, drac_th):
    result = parse_ssm(xml_path, warmup, ttc_th, drac_th)
    return (result["ttc_conflict_event_count"], result["drac_conflict_event_count"],
            result["min_ttc_s"], result["max_drac_mps2"],
            result["ttc_involved_vehicle_count"])


def _dedup_current(xml_path, warmup, ttc_th, drac_th):
    result = parse_ssm(xml_path, warmup, ttc_th, drac_th)
    return (result["ttc_conflict_event_count"], result["drac_conflict_event_count"],
            result["min_ttc_s"], result["max_drac_mps2"],
            result["ttc_involved_vehicle_count"])


def _dedup_sorted_greedy(xml_path, warmup, ttc_th, drac_th):
    from scripts.parsing.ssm import parse_ssm_subgroup
    result = parse_ssm_subgroup(xml_path, {}, warmup, ttc_th, drac_th)
    all_r = result.get("all", {})
    return (all_r.get("ttc_conflict_event_count", 0),
            all_r.get("drac_conflict_event_count", 0),
            all_r.get("min_ttc_s", float("nan")),
            all_r.get("max_drac_mps2", float("nan")),
            all_r.get("ttc_involved_vehicle_count", 0))


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
    run_dirs = sorted(d for d in Path(input_root).iterdir()
                      if d.is_dir() and (d / "ssm.xml").exists())

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
                ttc_cnt, _, min_ttc, _, ttc_veh = func(ssm_path, spec.warmup, th, 9999)
                rows.append({
                    "run_id": run_id, "measure": "TTC", "threshold": th,
                    "dedup_method": method, "event_count": ttc_cnt,
                    "extreme_value": min_ttc if not (isinstance(min_ttc, float) and min_ttc != min_ttc) else "",
                    "affected_vehicle_count": ttc_veh,
                })
            for th in drac_thresholds:
                _, drac_cnt, _, max_drac, _ = func(ssm_path, spec.warmup, 9999, th)
                rows.append({
                    "run_id": run_id, "measure": "DRAC", "threshold": th,
                    "dedup_method": method, "event_count": drac_cnt,
                    "extreme_value": max_drac if not (isinstance(max_drac, float) and max_drac != max_drac) else "",
                    "affected_vehicle_count": "",
                })

    out = Path(output_dir) / "ssm_sensitivity_results.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".csv.tmp")
    cols = ["run_id", "measure", "threshold", "dedup_method",
            "event_count", "extreme_value", "affected_vehicle_count"]
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
