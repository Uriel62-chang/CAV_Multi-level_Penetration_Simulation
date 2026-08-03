"""v0.4.0.post3：从冻结 raw XML 重算统一观测窗指标，不重跑 SUMO。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.parsing.edge_emissions import parse_edge_emissions
from scripts.parsing.edge_performance import parse_edge_performance
from scripts.parsing.runner import _validate_invariants
from scripts.parsing.ssm import parse_ssm
from scripts.results.aggregate import aggregate
from scripts.schema import RUN_LEVEL_COLUMNS


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else float("nan")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_raw_inventory(paths: set[Path], raw_root: Path, output_path: Path) -> dict:
    """记录实际读取的 raw 文件，形成不依赖本机绝对路径的稳定摘要。"""
    digest = hashlib.sha256()
    with output_path.open("w", encoding="utf-8", newline="\n") as stream:
        for path in sorted(paths, key=lambda item: item.relative_to(raw_root).as_posix()):
            record = {
                "path": path.relative_to(raw_root).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
            line = json.dumps(record, sort_keys=True, separators=(",", ":"))
            stream.write(line + "\n")
            digest.update((line + "\n").encode())
    return {
        "file_count": len(paths),
        "inventory_file": output_path.name,
        "inventory_sha256": digest.hexdigest(),
    }


def reanalyze(raw_root: Path, source_csv: Path, output_dir: Path) -> tuple[Path, Path]:
    """重算 SSM 极值时间过滤及 warmup 后 edgeData 指标。"""
    frame = pd.read_csv(source_csv)
    corrected_rows = []
    raw_inputs: set[Path] = set()

    for row in frame.to_dict(orient="records"):
        run_id = str(row["run_id"])
        run_dir = raw_root / run_id
        warmup = float(row["warmup_period_s"])

        ssm_path = run_dir / "ssm_compact.xml"
        if not ssm_path.exists():
            ssm_path = run_dir / "ssm.xml"
        performance_path = run_dir / "performance.xml"
        emissions_path = run_dir / "emissions.xml"
        raw_inputs.update((ssm_path, performance_path, emissions_path))
        # 审阅 P1-2：SSM 观测窗 [warmup, simulation_end)——不传 simulation_end 会把
        # 3600s 后的极值计入，与项目声明窗口不一致
        ssm = parse_ssm(
            str(ssm_path),
            warmup_period=warmup,
            simulation_end=float(row["simulation_end_s"]),
        )
        # 审阅 P1-1：edgeData 与 SSM 同窗口 [warmup, simulation_end)（与 v0.4.2 runner 一致）
        performance = parse_edge_performance(
            str(performance_path),
            warmup_period=warmup,
            simulation_end=float(row["simulation_end_s"]),
        )
        emissions = parse_edge_emissions(
            str(emissions_path),
            warmup_period=warmup,
            simulation_end=float(row["simulation_end_s"]),
        )

        if not all(result["parse_success"] for result in (ssm, performance, emissions)):
            raise RuntimeError(f"{run_id}: corrected parser failed")

        row.update(
            {
                "requested_pcav": float(row["pCAV"]),
                "realized_pcav": round(int(row["vehN"]) * float(row["pCAV"])) / int(row["vehN"]),
                "cav_count": round(int(row["vehN"]) * float(row["pCAV"])),
                "hv_count": int(row["vehN"]) - round(int(row["vehN"]) * float(row["pCAV"])),
                "ssm_raw_record_count": ssm["ssm_raw_record_count"],
                "ssm_invalid_record_count": ssm["ssm_invalid_record_count"],
                "ssm_warmup_filtered_count": ssm["ssm_warmup_filtered_count"],
                "ssm_valid_record_count": ssm["ssm_valid_record_count"],
                "ssm_mirrored_record_count": ssm["ssm_mirrored_record_count"],
                "ttc_conflict_event_count": ssm["ttc_conflict_event_count"],
                "min_ttc_s": ssm["min_ttc_s"],
                "ttc_affected_vehicle_count": ssm["ttc_involved_vehicle_count"],
                "drac_conflict_event_count": ssm["drac_conflict_event_count"],
                "max_drac_mps2": ssm["max_drac_mps2"],
                "total_CO2_kg": emissions["total_CO2_kg"],
                "total_NOx_g": emissions["total_NOx_g"],
                "total_PMx_g": emissions["total_PMx_g"],
                "total_fuel_kg": emissions["total_fuel_kg"],
                "total_vehicle_km": performance["total_vehicle_km"],
                "non_internal_edge_vehicle_km": performance["total_vehicle_km"],
                "total_time_loss_s": performance["total_time_loss_s"],
            }
        )

        veh_km = float(row["total_vehicle_km"])
        row["ttc_events_per_1000_veh_km"] = _safe_div(
            float(row["ttc_conflict_event_count"]) * 1000.0, veh_km
        )
        row["whole_network_ttc_events_per_1000_non_internal_edge_veh_km"] = row[
            "ttc_events_per_1000_veh_km"
        ]
        row["emergency_brakes_per_1000_veh_km"] = _safe_div(
            float(row["emergency_braking_count"]) * 1000.0, veh_km
        )
        row["lane_changes_per_1000_veh_km"] = _safe_div(
            float(row["lane_change_count"]) * 1000.0, veh_km
        )
        row["CO2_g_per_veh_km"] = _safe_div(float(row["total_CO2_kg"]) * 1000.0, veh_km)
        row["NOx_mg_per_veh_km"] = _safe_div(float(row["total_NOx_g"]) * 1000.0, veh_km)
        row["PMx_mg_per_veh_km"] = _safe_div(float(row["total_PMx_g"]) * 1000.0, veh_km)
        row["fuel_g_per_veh_km"] = _safe_div(float(row["total_fuel_kg"]) * 1000.0, veh_km)
        row["time_loss_s_per_veh_km"] = _safe_div(float(row["total_time_loss_s"]), veh_km)
        invariant_errors = _validate_invariants(row)
        row["data_quality"] = "invariant_failed" if invariant_errors else "ok"
        row["data_quality_detail"] = "; ".join(invariant_errors)
        corrected_rows.append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    run_level_path = output_dir / "run_level_results.csv"
    aggregated_path = output_dir / "aggregated_results.csv"
    corrected = pd.DataFrame(corrected_rows, columns=RUN_LEVEL_COLUMNS)
    corrected.to_csv(run_level_path, index=False)
    invalid_count = int((corrected["data_quality"] != "ok").sum())
    if invalid_count:
        raise RuntimeError(f"post3 reanalysis produced {invalid_count} invariant-invalid rows")
    aggregate(run_level_path, aggregated_path)
    raw_inventory = _write_raw_inventory(
        raw_inputs, raw_root, output_dir / "raw_input_inventory.jsonl"
    )
    windows = sorted(
        {
            f"[{float(row['warmup_period_s']):g}, {float(row['simulation_end_s']):g})"
            for row in corrected_rows
        }
    )

    metadata = {
        "analysis_version": "v0.4.0.post3",
        "output_schema": "v0.4.0.post3.1",
        "source_release": "v0.4.0.post2",
        "source_run_level_sha256": _sha256(source_csv),
        "run_count": len(corrected),
        "quality_ok_count": len(corrected) - invalid_count,
        "quality_invalid_count": invalid_count,
        "raw_inputs": raw_inventory,
        "observation_window": windows[0] if len(windows) == 1 else windows,
        "edge_scope": "non-internal edges (withInternal=false)",
        "ssm_time_rule": "minTTC@time and maxDRAC@time",
        "penetration_columns": {
            "pCAV": "legacy alias of requested_pcav",
            "requested_pcav": "requested treatment",
            "realized_pcav": "round(vehN * requested_pcav) / vehN",
        },
        "seed_scope": "vehicle_type_assignment",
        "ratio_aggregation": "equal-run-weight arithmetic statistics; not pooled exposure",
        "independent_random_replication_count": 0,
        "run_level_sha256": _sha256(run_level_path),
        "aggregated_sha256": _sha256(aggregated_path),
    }
    (output_dir / "reanalysis_manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return run_level_path, aggregated_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--source-run-level", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    reanalyze(args.raw_root, args.source_run_level, args.output_dir)


if __name__ == "__main__":
    main()
