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
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.run_spec import atomic_write_json
from scripts.schema import RUN_LEVEL_COLUMNS


def _read_summary(run_dir: Path, run_id: str,
                  pipeline_version: str) -> tuple[dict | None, str | None]:
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


def _build_row(summary: dict, parse_status: str) -> dict:
    """从 summary dict 构建 CSV 行，补 data_quality 标记"""
    row = {col: summary.get(col, float("nan")) for col in RUN_LEVEL_COLUMNS}

    # data_quality 判定
    errors = summary.get("_invariant_errors", [])
    if parse_status == "SUCCESS":
        row["data_quality"] = "ok"
        row["data_quality_detail"] = ""
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


def build_run_level_results(
    input_root: Path,
    output_dir: Path,
    pipeline_version: str,
    manifest_path: Path,
) -> dict:
    """主入口：读取 summary.json，输出三文件。"""

    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 读取 manifest ──
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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

        # 失败判定
        if sim_status != "SUCCESS":
            failed_rows.append({
                "run_id": run_id,
                "scenario": "", "model": "", "pCAV": "", "vehN": "", "seed": "",
                "failure_stage": "SIMULATION",
                "failure_reason": f"simulation status={sim_status}",
            })
            continue

        if parse_status not in ("SUCCESS", "INVALID_DATA"):
            failed_rows.append({
                "run_id": run_id,
                "scenario": "", "model": "", "pCAV": "", "vehN": "", "seed": "",
                "failure_stage": "PARSER" if parse_status != "MISSING" else "SUMMARY",
                "failure_reason": f"parse status={parse_status}",
            })
            continue

        # 读取 summary
        summary, error = _read_summary(run_dir, run_id, pipeline_version)
        if summary is None:
            failed_rows.append({
                "run_id": run_id,
                "scenario": "", "model": "", "pCAV": "", "vehN": "", "seed": "",
                "failure_stage": "SUMMARY",
                "failure_reason": error or "unknown",
            })
            continue

        # 构建 CSV 行
        row = _build_row(summary, parse_status)
        success_rows.append(row)

    # ── 排序 ──
    success_rows.sort(key=lambda r: (
        r.get("scenario", ""), r.get("model", ""),
        r.get("pCAV", 0), r.get("vehN", 0), r.get("seed", 0),
    ))

    # ── 写入 run_level_results.csv ──
    csv_path = output_dir / "run_level_results.csv"
    _atomic_write_csv(csv_path, success_rows, RUN_LEVEL_COLUMNS)
    print(f"[WRITE] {len(success_rows)} rows → {csv_path}")

    # ── 写入 failed_runs.csv ──
    failed_path = output_dir / "failed_runs.csv"
    failed_cols = ["run_id", "scenario", "model", "pCAV", "vehN", "seed",
                   "failure_stage", "failure_reason"]
    _atomic_write_csv(failed_path, failed_rows, failed_cols)
    print(f"[WRITE] {len(failed_rows)} failed → {failed_path}")

    # ── writer_report.json ──
    quality_counter = Counter(r["data_quality"] for r in success_rows)
    report = {
        "expected_runs": expected_total,
        "discovered_runs": discovered,
        "csv_rows": len(success_rows),
        "quality_ok": quality_counter.get("ok", 0),
        "quality_invalid": quality_counter.get("invariant_failed", 0),
        "excluded_runs": len(failed_rows),
        "duplicate_run_ids": duplicates,
        "missing_run_ids": expected_total - discovered,
        "complete": len(failed_rows) == 0,
        "pipeline_version": pipeline_version,
    }
    report_path = output_dir / "writer_report.json"
    atomic_write_json(report_path, report)
    print(f"[WRITE] report → {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="v0.4.0 统一结果写入")
    parser.add_argument("--input-root", required=True,
                        help="raw run 目录根路径")
    parser.add_argument("--output-dir", required=True,
                        help="输出目录")
    parser.add_argument("--manifest", required=True,
                        help="正式实验 manifest.json")
    parser.add_argument("--pipeline-version", default="v0.4.0-rc1",
                        help="管线版本标识")
    parser.add_argument("--dry-run", action="store_true",
                        help="只检查不写入")
    args = parser.parse_args()

    input_root = Path(args.input_root)
    manifest_path = Path(args.manifest)

    if not manifest_path.exists():
        print(f"[ERROR] manifest not found: {manifest_path}")
        sys.exit(1)

    if args.dry_run:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        total = manifest.get("total", 0)
        results = manifest.get("results", [])
        sim_ok = sum(1 for r in results if r.get("status") == "SUCCESS")
        print(f"[DRY RUN] {total} runs in manifest, {sim_ok} simulation SUCCESS")
        return

    report = build_run_level_results(
        input_root=input_root,
        output_dir=Path(args.output_dir),
        pipeline_version=args.pipeline_version,
        manifest_path=manifest_path,
    )

    print(f"\n{'='*60}")
    print(f"[DONE] csv_rows={report['csv_rows']}  "
          f"ok={report['quality_ok']}  invalid={report['quality_invalid']}  "
          f"excluded={report['excluded_runs']}  complete={report['complete']}")


if __name__ == "__main__":
    main()
