"""阶段二：串行批量解析调度器。

python3 -m scripts.parsing.batch --input-root /path/to/raw
python3 -m scripts.parsing.batch --input-root /path/to/raw --resume --limit 50
"""

import argparse
import json
import sys
import time
from pathlib import Path

from scripts.parsing.runner import _check_preconditions, parse_one_run
from scripts.provenance import sha256_file
from scripts.run_spec import atomic_write_json, load_run_spec

STATUS_ICONS = {
    "SUCCESS": "✓",
    "FAILED": "✗",
    "SKIPPED": "○",
    "INVALID_DATA": "⚠",
    "SIMULATION_NOT_SUCCESS": "⊘",
    "RUNNING": "…",
}


def is_parse_complete(run_dir: Path, pipeline_version: str) -> bool:
    """检查 parse_status.json 是否已成功完成"""
    sp = run_dir / "parse_status.json"
    if not sp.exists():
        return False
    try:
        data = json.loads(sp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if data.get("status") != "SUCCESS":
        return False
    if data.get("pipeline_version") != pipeline_version:
        return False
    summary_path = run_dir / "summary.json"
    if not summary_path.is_file() or summary_path.stat().st_size == 0:
        return False
    try:
        sim_status = json.loads((run_dir / "simulation_status.json").read_text(encoding="utf-8"))
        spec = load_run_spec(run_dir, expected_sha256=sim_status["run_spec_sha256"])
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        return False
    for field in (
        "schema_version",
        "config_sha256",
        "network_sha256",
        "experiment_id",
        "run_spec_sha256",
    ):
        expected = spec.sha256() if field == "run_spec_sha256" else getattr(spec, field)
        if data.get(field) != expected or sim_status.get(field) != expected:
            return False
    if data.get("summary_sha256") != sha256_file(summary_path):
        return False
    if spec.schema_version == "2":
        subgroup_sha = data.get("subgroup_summary_sha256")
        if not subgroup_sha:
            return False
        subgroup_path = run_dir / "subgroup_summary.jsonl"
        if not subgroup_path.is_file() or subgroup_path.stat().st_size == 0:
            return False
        if sha256_file(subgroup_path) != subgroup_sha:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description="v0.4.0 串行批量解析")
    parser.add_argument("--input-root", required=True, help="raw run 目录根路径")
    parser.add_argument("--resume", action="store_true", help="跳过已成功解析的 run")
    parser.add_argument(
        "--pipeline-version", default=None, help="管线版本；默认从实验 manifest 读取"
    )
    parser.add_argument("--limit", type=int, default=0, help="限制解析数量（测试用）")
    parser.add_argument("--dry-run", action="store_true", help="只扫描不解析")
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="显式解析缺少 RunSpec 的历史 raw；输出始终标记为 legacy_unverified",
    )
    parser.add_argument("--legacy-end", type=float, default=3600)
    parser.add_argument("--legacy-warmup", type=float, default=600)
    parser.add_argument("--legacy-step-length", type=float, default=0.1)
    parser.add_argument("--legacy-detector-frequency", type=int, default=120)
    parser.add_argument("--legacy-edge-frequency", type=int, default=300)
    parser.add_argument("--legacy-loops", type=int, default=300)
    parser.add_argument(
        "--progress-interval", type=int, default=50, help="每 N 个 run 输出一次进度 (默认: 50)"
    )
    parser.add_argument(
        "--freeze-input-integrity",
        action="store_true",
        help="P1-4 迁移：为旧 v0.4.2 run 生成 input_integrity.sidecar.json "
        "（重解析前冻结全部解析输入 SHA，不回填 simulation_status；随后解析默认 fail-closed）",
    )
    args = parser.parse_args()

    input_root = Path(args.input_root)
    if not input_root.is_dir():
        print(f"[ERROR] {input_root} not found")
        sys.exit(1)
    if args.legacy:
        from scripts.parsing.legacy import parse_legacy_run

        run_dirs = sorted(path for path in input_root.iterdir() if path.is_dir())
        if args.limit > 0:
            run_dirs = run_dirs[: args.limit]
        print(
            f"[LEGACY] {len(run_dirs)} directories; results are legacy_unverified "
            "and cannot enter the current writer"
        )
        if args.dry_run:
            return
        counts: dict[str, int] = {}
        for run_dir in run_dirs:
            result = parse_legacy_run(
                run_dir,
                simulation_end=args.legacy_end,
                warmup=args.legacy_warmup,
                step_length=args.legacy_step_length,
                detector_frequency=args.legacy_detector_frequency,
                edge_data_frequency=args.legacy_edge_frequency,
                loops=args.legacy_loops,
            )
            status = result["status"]
            counts[status] = counts.get(status, 0) + 1
        print(f"[LEGACY DONE] {counts}")
        return

    experiment_manifest_path = input_root / "manifest.json"
    if not experiment_manifest_path.is_file():
        print(f"[ERROR] experiment manifest not found: {experiment_manifest_path}")
        sys.exit(1)
    try:
        experiment_manifest = json.loads(experiment_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[ERROR] experiment manifest unreadable: {exc}")
        sys.exit(1)
    manifest_version = experiment_manifest.get("pipeline_version")
    if not manifest_version:
        print("[ERROR] experiment manifest missing pipeline_version")
        sys.exit(1)
    if args.pipeline_version and args.pipeline_version != manifest_version:
        print("[ERROR] --pipeline-version does not match experiment manifest")
        sys.exit(1)
    pipeline_version = args.pipeline_version or manifest_version

    # ── 收集 run 目录 ──
    run_dirs = sorted(
        d for d in input_root.iterdir() if d.is_dir() and (d / "simulation_status.json").exists()
    )
    total_found = len(run_dirs)

    if args.limit > 0:
        run_dirs = run_dirs[: args.limit]

    # P1-4（新审阅）：迁移路径——为旧 v0.4.2 run 冻结输入完整性 sidecar。
    if args.freeze_input_integrity:
        from scripts.parsing.input_integrity import write_sidecar
        from scripts.run_spec import load_run_spec

        frozen = 0
        for d in run_dirs:
            try:
                spec = load_run_spec(d)
            except Exception as exc:
                print(f"[SKIP] {d.name}: cannot load run_spec ({exc})")
                continue
            if spec.pipeline_version != "v0.4.2":
                continue
            write_sidecar(d, spec)
            frozen += 1
        print(f"[FROZEN] {frozen} v0.4.2 input-integrity sidecars written (no status backfill)")
        return

    print(
        f"[SCAN] {total_found} run directories found"
        + (f", processing {len(run_dirs)}" if args.limit else "")
    )

    if args.dry_run:
        skipped = success = sim_fail = 0
        for d in run_dirs:
            if args.resume and is_parse_complete(d, pipeline_version):
                skipped += 1
            else:
                pre = _check_preconditions(d, pipeline_version)
                if pre:
                    sim_fail += 1
                else:
                    success += 1
        print(
            f"[DRY RUN] parseable={success}  already-parsed={skipped}  "
            f"sim-not-ok={sim_fail}  total={len(run_dirs)}"
        )
        return

    # ── 串行解析 ──
    counts = {
        "SUCCESS": 0,
        "FAILED": 0,
        "SKIPPED": 0,
        "INVALID_DATA": 0,
        "SIMULATION_NOT_SUCCESS": 0,
    }
    timings = []
    t0 = time.monotonic()

    for i, run_dir in enumerate(run_dirs):
        # resume 检查
        if args.resume and is_parse_complete(run_dir, pipeline_version):
            counts["SKIPPED"] += 1
            continue

        result = parse_one_run(run_dir, pipeline_version)
        status = result["status"]
        counts[status] = counts.get(status, 0) + 1
        if result.get("wall_time_s", 0) > 0:
            timings.append(result["wall_time_s"])

        # 进度输出
        if (i + 1) % args.progress_interval == 0 or (i + 1) == len(run_dirs):
            done = sum(counts.values())
            elapsed = time.monotonic() - t0
            rate = done / elapsed if elapsed > 0 else 0
            icon = STATUS_ICONS.get(status, "?")
            print(
                f"[{done:>5}/{len(run_dirs)}] {icon} {run_dir.name:45s}"
                f" ({result.get('wall_time_s', 0):4.0f}s)"
                f" | {rate:5.1f} runs/s"
                f" | ok={counts['SUCCESS']} fail={counts['FAILED']}"
                f" inv={counts['INVALID_DATA']} skip={counts['SKIPPED']}"
            )

    # ── 汇总 ──
    elapsed_total = time.monotonic() - t0
    print(f"\n{'=' * 60}")
    print(f"[DONE] {sum(counts.values())} runs in {elapsed_total:.0f}s")
    for st, cnt in sorted(counts.items()):
        if cnt:
            print(f"  {st}: {cnt}")

    if timings:
        timings.sort()
        n = len(timings)
        avg = sum(timings) / n
        p50 = timings[n // 2]
        p95 = timings[int(n * 0.95)] if n > 1 else timings[-1]
        pmax = timings[-1]
        print(f"  time: avg={avg:.2f}s  P50={p50:.2f}s  P95={p95:.2f}s  max={pmax:.2f}s")
        print(f"  throughput: {n / elapsed_total:.1f} runs/s")

    # 写 manifest
    manifest_path = input_root / "parse_manifest.json"
    manifest = {
        "pipeline_version": pipeline_version,
        "schema_version": experiment_manifest.get("schema_version"),
        "config_sha256": experiment_manifest.get("config_sha256"),
        "experiment_id": experiment_manifest.get("experiment_id"),
        "total": sum(counts.values()),
        "status_counts": counts,
        "elapsed_s": elapsed_total,
        "avg_time_s": avg if timings else 0,
    }
    atomic_write_json(manifest_path, manifest)
    print(f"  manifest → {manifest_path}")


if __name__ == "__main__":
    main()
