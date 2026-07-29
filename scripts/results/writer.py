"""阶段三：统一结果写入器。

    读取 10,080 个 summary.json，生成 run_level_results.csv + failed_runs.csv + writer_report.json。

    python3 -m scripts.results.writer \
      --input-root /home/lyc/simdata/cav-v0.4.0/raw \
      --output-dir /home/lyc/simdata/cav-v0.4.0/results \
      --manifest /home/lyc/simdata/cav-v0.4.0/raw/manifest.json \
      --pipeline-version v0.4.0-rc1
"""

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

from scripts.provenance import sha256_file
from scripts.run_spec import atomic_write_json
from scripts.schema import RUN_LEVEL_COLUMNS, RUN_LEVEL_COLUMNS_V4_1, SUBGROUP_LONG_COLUMNS_V4_1


def _recompute_rate(numerator, denominator, fallback=None):
    """由原始分子/分母重算比率；二者不可用时回退到旧预计算值。"""
    try:
        n = float(numerator) if numerator is not None else float("nan")
        d = float(denominator) if denominator is not None else float("nan")
    except (ValueError, TypeError):
        n = float("nan")
        d = float("nan")
    if math.isnan(n) or math.isnan(d) or d <= 0:
        if fallback is not None:
            try:
                return float(fallback)
            except (ValueError, TypeError):
                pass
        return float("nan")
    return n / d * 1000


def _read_summary(
    run_dir: Path, run_id: str, pipeline_version: str
) -> tuple[dict | None, str | None]:
    """读取 summary.json，返回 (data, error_reason)。error_reason 为 None 表示成功。"""
    sp = run_dir / "summary.json"
    if not sp.exists():
        return None, "summary.json missing"

    try:
        data = json.loads(sp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return None, f"summary.json unreadable: {e}"

    if data.get("run_id") != run_id:
        return None, f"run_id mismatch: {data.get('run_id')} != {run_id}"

    return data, None


def _read_parse_status(run_dir: Path) -> str:
    """读取 parse_status.json，返回 status 字符串"""
    pp = run_dir / "parse_status.json"
    if not pp.exists():
        return "MISSING"
    try:
        data = json.loads(pp.read_text(encoding="utf-8"))
        return data.get("status", "UNKNOWN")
    except (OSError, json.JSONDecodeError):
        return "UNREADABLE"


def _read_sim_status(run_dir: Path) -> str:
    """读取 simulation_status.json，返回 status 字符串"""
    sp = run_dir / "simulation_status.json"
    if not sp.exists():
        return "MISSING"
    try:
        data = json.loads(sp.read_text(encoding="utf-8"))
        return data.get("status", "UNKNOWN")
    except (OSError, json.JSONDecodeError):
        return "UNREADABLE"


def _build_row(summary: dict, parse_status: str, schema_ver: str = "1") -> dict:
    if schema_ver == "2":
        return _build_row_v4_1(summary, parse_status)
    else:
        return _build_row_legacy(summary, parse_status)


def _build_row_legacy(summary: dict, parse_status: str) -> dict:
    row = {col: summary.get(col, float("nan")) for col in RUN_LEVEL_COLUMNS}
    vehicle_count = int(summary["vehN"])
    requested_pcav = float(summary["pCAV"])
    cav_count = round(vehicle_count * requested_pcav)
    row.update(
        {
            "requested_pcav": requested_pcav,
            "realized_pcav": cav_count / vehicle_count,
            "cav_count": cav_count,
            "hv_count": vehicle_count - cav_count,
            "non_internal_edge_vehicle_km": summary.get(
                "non_internal_edge_vehicle_km",
                summary.get("total_vehicle_km", float("nan")),
            ),
            "whole_network_ttc_events_per_1000_non_internal_edge_veh_km": _recompute_rate(
                summary.get("ttc_conflict_event_count"),
                summary.get("non_internal_edge_vehicle_km"),
                summary.get("ttc_events_per_1000_veh_km"),
            ),
        }
    )

    errors = summary.get("_invariant_errors", [])
    parser_flags = [
        summary.get(name)
        for name in (
            "ssm_parse_success",
            "lc_parse_success",
            "ep_parse_success",
            "ee_parse_success",
            "vr_parse_success",
        )
    ]
    if parse_status == "SUCCESS" and all(flag is True for flag in parser_flags):
        row["data_quality"] = "ok"
        row["data_quality_detail"] = ""
    elif parse_status == "SUCCESS":
        row["data_quality"] = "parser_warning"
        row["data_quality_detail"] = "one or more parser audit flags are not true"
    elif parse_status == "INVALID_DATA":
        row["data_quality"] = "invariant_failed"
        row["data_quality_detail"] = json.dumps(errors, ensure_ascii=False) if errors else ""
    else:
        row["data_quality"] = "parser_warning"
        row["data_quality_detail"] = f"parse_status={parse_status}"

    return row


def _build_row_v4_1(summary: dict, parse_status: str) -> dict:
    row = {col: summary.get(col, float("nan")) for col in RUN_LEVEL_COLUMNS_V4_1}

    errors = summary.get("_invariant_errors", [])
    parser_flags = [
        summary.get(name)
        for name in (
            "ssm_parse_success",
            "lc_parse_success",
            "ep_parse_success",
            "ee_parse_success",
            "vr_parse_success",
            "fcd_parse_success",
        )
    ]
    if parse_status == "SUCCESS" and all(flag is True for flag in parser_flags):
        row["data_quality"] = "ok"
        row["data_quality_detail"] = ""
    elif parse_status == "SUCCESS":
        row["data_quality"] = "parser_warning"
        row["data_quality_detail"] = "one or more parser audit flags are not true"
    elif parse_status == "INVALID_DATA":
        row["data_quality"] = "invariant_failed"
        row["data_quality_detail"] = json.dumps(errors, ensure_ascii=False) if errors else ""
    else:
        row["data_quality"] = "parser_warning"
        row["data_quality_detail"] = f"parse_status={parse_status}"

    return row


def _atomic_write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    """原子写入 CSV：先写 .tmp，os.replace"""
    tmp = path.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _completion_flags(failed_count: int, non_ok_count: int) -> dict[str, bool]:
    structurally_complete = failed_count == 0
    return {
        "structurally_complete": structurally_complete,
        "all_rows_valid": structurally_complete and non_ok_count == 0,
        "complete": structurally_complete and non_ok_count == 0,
    }


def _quality_counts(rows: list[dict]) -> dict[str, int]:
    """统计质量标签；任何非 ok 行都必须否决 all_rows_valid/complete。"""
    counter = Counter(row["data_quality"] for row in rows)
    return {
        "quality_ok": counter.get("ok", 0),
        "quality_invariant_failed": counter.get("invariant_failed", 0),
        "quality_parser_warning": counter.get("parser_warning", 0),
        "quality_non_ok": sum(count for label, count in counter.items() if label != "ok"),
    }


def _format_report_summary(report: dict) -> str:
    """Format the CLI handoff using the current writer-report schema."""
    return (
        f"[DONE] csv_rows={report['csv_rows']}  "
        f"ok={report['quality_ok']}  non_ok={report['quality_non_ok']}  "
        f"invariant_failed={report['quality_invariant_failed']}  "
        f"parser_warning={report['quality_parser_warning']}  "
        f"excluded={report['excluded_runs']}  complete={report['complete']}"
    )


def build_run_level_results(
    input_root: Path,
    output_dir: Path,
    pipeline_version: str,
    manifest_path: Path,
    results_filename: str = "run_level_results.csv",
) -> dict:
    """主入口：读取 summary.json，输出三文件。"""

    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 读取 manifest ──
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("pipeline_version") != pipeline_version:
        raise ValueError(
            "manifest pipeline_version mismatch: "
            f"{manifest.get('pipeline_version')} != {pipeline_version}"
        )
    if not manifest.get("schema_version"):
        raise ValueError("manifest schema_version missing")
    if not manifest.get("config_sha256"):
        raise ValueError("manifest config_sha256 missing")
    schema_ver = manifest.get("schema_version", "1")
    manifest_results = manifest.get("results", [])

    expected_total = manifest.get("total", len(manifest_results))
    discovered = len(manifest_results)

    # ── 遍历所有 run ──
    success_rows = []
    failed_rows = []
    run_ids_seen = set()
    duplicates = 0

    for entry in manifest_results:
        run_id = entry["run_id"]
        run_dir = input_root / run_id

        if run_id in run_ids_seen:
            duplicates += 1
            continue
        run_ids_seen.add(run_id)

        sim_status = _read_sim_status(run_dir)
        parse_status = _read_parse_status(run_dir)

        try:
            sim_data = json.loads((run_dir / "simulation_status.json").read_text(encoding="utf-8"))
            parse_data = json.loads((run_dir / "parse_status.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            sim_data = {}
            parse_data = {}
        expected_hash = entry.get("run_spec_sha256")
        metadata_error = None
        for name, data in (("simulation", sim_data), ("parse", parse_data)):
            if data.get("pipeline_version") != pipeline_version:
                metadata_error = f"{name} pipeline_version mismatch"
                break
            if data.get("schema_version") != manifest["schema_version"]:
                metadata_error = f"{name} schema_version mismatch"
                break
            if data.get("config_sha256") != manifest["config_sha256"]:
                metadata_error = f"{name} config_sha256 mismatch"
                break
            if data.get("run_spec_sha256") != expected_hash:
                metadata_error = f"{name} run_spec_sha256 mismatch"
                break
        summary_path = run_dir / "summary.json"
        if (
            metadata_error is None
            and summary_path.is_file()
            and parse_data.get("summary_sha256") != sha256_file(summary_path)
        ):
            metadata_error = "summary_sha256 mismatch"
        if metadata_error:
            failed_rows.append(
                {
                    "run_id": run_id,
                    "scenario": "",
                    "model": "",
                    "pCAV": "",
                    "vehN": "",
                    "seed": "",
                    "failure_stage": "METADATA",
                    "failure_reason": metadata_error,
                }
            )
            continue

        # 失败判定
        if sim_status != "SUCCESS":
            failed_rows.append(
                {
                    "run_id": run_id,
                    "scenario": "",
                    "model": "",
                    "pCAV": "",
                    "vehN": "",
                    "seed": "",
                    "failure_stage": "SIMULATION",
                    "failure_reason": f"simulation status={sim_status}",
                }
            )
            continue

        if parse_status not in ("SUCCESS", "INVALID_DATA"):
            failed_rows.append(
                {
                    "run_id": run_id,
                    "scenario": "",
                    "model": "",
                    "pCAV": "",
                    "vehN": "",
                    "seed": "",
                    "failure_stage": "PARSER" if parse_status != "MISSING" else "SUMMARY",
                    "failure_reason": f"parse status={parse_status}",
                }
            )
            continue

        # 读取 summary
        summary, error = _read_summary(run_dir, run_id, pipeline_version)
        if summary is None:
            failed_rows.append(
                {
                    "run_id": run_id,
                    "scenario": "",
                    "model": "",
                    "pCAV": "",
                    "vehN": "",
                    "seed": "",
                    "failure_stage": "SUMMARY",
                    "failure_reason": error or "unknown",
                }
            )
            continue

        # 构建 CSV 行
        row = _build_row(summary, parse_status, schema_ver)
        success_rows.append(row)

    # ── 排序 ──
    if schema_ver == "2":
        success_rows.sort(
            key=lambda r: (
                r.get("scenario", ""),
                r.get("model", ""),
                r.get("cav_count", 0),
                r.get("vehN", 0),
                r.get("assignment_seed", 0),
                r.get("sumo_seed", 0),
            )
        )
    else:
        success_rows.sort(
            key=lambda r: (
                r.get("scenario", ""),
                r.get("model", ""),
                r.get("pCAV", 0),
                r.get("vehN", 0),
                r.get("seed", 0),
            )
        )

    # ── 写入 run_level_results.csv ──
    csv_path = output_dir / results_filename
    columns = RUN_LEVEL_COLUMNS_V4_1 if schema_ver == "2" else RUN_LEVEL_COLUMNS
    _atomic_write_csv(csv_path, success_rows, columns)
    print(f"[WRITE] {len(success_rows)} rows → {csv_path}")

    # ── 写入 failed_runs.csv ──
    failed_path = output_dir / "failed_runs.csv"
    failed_cols = [
        "run_id",
        "scenario",
        "model",
        "pCAV",
        "vehN",
        "seed",
        "failure_stage",
        "failure_reason",
    ]
    _atomic_write_csv(failed_path, failed_rows, failed_cols)
    print(f"[WRITE] {len(failed_rows)} failed → {failed_path}")

    # ── subgroup CSV ──
    subgroup_csv_rows = 0
    subgroup_excluded = 0
    if schema_ver == "2":
        subgroup_rows = []
        for entry in manifest_results:
            run_id = entry["run_id"]
            run_dir = input_root / run_id
            parse_status = _read_parse_status(run_dir)
            if parse_status != "SUCCESS":
                subgroup_excluded += 1
                continue
            summary_path = run_dir / "summary.json"
            if summary_path.exists():
                try:
                    sd = json.loads(summary_path.read_text(encoding="utf-8"))
                except Exception:
                    subgroup_excluded += 1
                    continue
                if sd.get("_invariant_errors"):
                    subgroup_excluded += 1
                    continue

            subgroup_path = run_dir / "subgroup_summary.jsonl"
            if not subgroup_path.exists():
                subgroup_excluded += 1
                continue
            try:
                pp = json.loads((run_dir / "parse_status.json").read_text(encoding="utf-8"))
                expected_sha = pp.get("subgroup_summary_sha256")
            except Exception:
                subgroup_excluded += 1
                continue
            if expected_sha and sha256_file(subgroup_path) != expected_sha:
                subgroup_excluded += 1
                continue
            try:
                for line in subgroup_path.read_text(encoding="utf-8").strip().split("\n"):
                    if line.strip():
                        subgroup_rows.append(json.loads(line))
            except Exception:
                subgroup_excluded += 1

        subgroup_csv_path = output_dir / "run_level_subgroup_results.csv"
        if subgroup_rows:
            _atomic_write_csv(subgroup_csv_path, subgroup_rows, SUBGROUP_LONG_COLUMNS_V4_1)
        else:
            with subgroup_csv_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=SUBGROUP_LONG_COLUMNS_V4_1, extrasaction="ignore")
                w.writeheader()
        print(f"[WRITE] {len(subgroup_rows)} subgroup rows → {subgroup_csv_path}")

        subgroup_csv_rows = len(subgroup_rows)

    # ── writer_report.json ──
    quality_counts = _quality_counts(success_rows)
    report = {
        "expected_runs": expected_total,
        "discovered_runs": discovered,
        "csv_rows": len(success_rows),
        "subgroup_csv_rows": subgroup_csv_rows,
        "subgroup_excluded_runs": subgroup_excluded,
        **quality_counts,
        "excluded_runs": len(failed_rows),
        "duplicate_run_ids": duplicates,
        "missing_run_ids": expected_total - discovered,
        "pipeline_version": pipeline_version,
    }
    report.update(
        _completion_flags(
            failed_count=len(failed_rows),
            non_ok_count=quality_counts["quality_non_ok"],
        )
    )
    report_path = output_dir / "writer_report.json"
    atomic_write_json(report_path, report)
    print(f"[WRITE] report → {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="v0.4.0 统一结果写入")
    parser.add_argument("--input-root", required=True, help="raw run 目录根路径")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    parser.add_argument("--manifest", required=True, help="正式实验 manifest.json")
    parser.add_argument(
        "--pipeline-version",
        default=None,
        help="管线版本；默认从实验 manifest 读取",
    )
    parser.add_argument("--dry-run", action="store_true", help="只检查不写入")
    args = parser.parse_args()

    input_root = Path(args.input_root)
    manifest_path = Path(args.manifest)

    if not manifest_path.exists():
        print(f"[ERROR] manifest not found: {manifest_path}")
        sys.exit(1)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[ERROR] manifest unreadable: {exc}")
        sys.exit(1)
    manifest_version = manifest.get("pipeline_version")
    if not manifest_version:
        print("[ERROR] manifest missing pipeline_version")
        sys.exit(1)
    if args.pipeline_version and args.pipeline_version != manifest_version:
        print("[ERROR] --pipeline-version does not match manifest")
        sys.exit(1)
    pipeline_version = args.pipeline_version or manifest_version

    if args.dry_run:
        total = manifest.get("total", 0)
        results = manifest.get("results", [])
        sim_ok = sum(1 for r in results if r.get("status") == "SUCCESS")
        print(f"[DRY RUN] {total} runs in manifest, {sim_ok} simulation SUCCESS")
        return

    report = build_run_level_results(
        input_root=input_root,
        output_dir=Path(args.output_dir),
        pipeline_version=pipeline_version,
        manifest_path=manifest_path,
    )

    print(f"\n{'=' * 60}")
    print(_format_report_summary(report))
    if not report["complete"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
