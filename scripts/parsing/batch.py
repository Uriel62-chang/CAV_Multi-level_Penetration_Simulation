"""阶段二：串行批量解析调度器。

    python3 -m scripts.parsing.batch --input-root /path/to/raw
    python3 -m scripts.parsing.batch --input-root /path/to/raw --resume --limit 50
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.parsing.runner import parse_one_run, _check_preconditions
from scripts.run_spec import RunSpec, atomic_write_json

STATUS_ICONS = {
    "SUCCESS": "✓", "FAILED": "✗", "SKIPPED": "○",
    "INVALID_DATA": "⚠", "SIMULATION_NOT_SUCCESS": "⊘",
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
    if not (run_dir / "summary.json").exists():
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="v0.4.0 串行批量解析")
    parser.add_argument("--input-root", required=True,
                        help="raw run 目录根路径")
    parser.add_argument("--resume", action="store_true",
                        help="跳过已成功解析的 run")
    parser.add_argument("--pipeline-version", default="v0.4.0-rc1",
                        help="管线版本标识")
    parser.add_argument("--limit", type=int, default=0,
                        help="限制解析数量（测试用）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只扫描不解析")
    parser.add_argument("--progress-interval", type=int, default=50,
                        help="每 N 个 run 输出一次进度 (默认: 50)")
    args = parser.parse_args()

    input_root = Path(args.input_root)
    if not input_root.is_dir():
        print(f"[ERROR] {input_root} not found")
        sys.exit(1)

    # ── 收集 run 目录 ──
    run_dirs = sorted(d for d in input_root.iterdir()
                      if d.is_dir() and (d / "simulation_status.json").exists())
    total_found = len(run_dirs)

    if args.limit > 0:
        run_dirs = run_dirs[:args.limit]

    print(f"[SCAN] {total_found} run directories found"
          + (f", processing {len(run_dirs)}" if args.limit else ""))

    if args.dry_run:
        skipped = success = fail = sim_fail = 0
        for d in run_dirs:
            if args.resume and is_parse_complete(d, args.pipeline_version):
                skipped += 1
            else:
                pre = _check_preconditions(d, args.pipeline_version)
                if pre:
                    sim_fail += 1
                else:
                    success += 1
        print(f"[DRY RUN] parseable={success}  already-parsed={skipped}  "
              f"sim-not-ok={sim_fail}  total={len(run_dirs)}")
        return

    # ── 串行解析 ──
    counts = {"SUCCESS": 0, "FAILED": 0, "SKIPPED": 0,
              "INVALID_DATA": 0, "SIMULATION_NOT_SUCCESS": 0}
    timings = []
    t0 = time.monotonic()

    for i, run_dir in enumerate(run_dirs):
        # resume 检查
        if args.resume and is_parse_complete(run_dir, args.pipeline_version):
            counts["SKIPPED"] += 1
            continue

        result = parse_one_run(run_dir, args.pipeline_version)
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
            print(f"[{done:>5}/{len(run_dirs)}] {icon} {run_dir.name:45s}"
                  f" ({result.get('wall_time_s', 0):4.0f}s)"
                  f" | {rate:5.1f} runs/s"
                  f" | ok={counts['SUCCESS']} fail={counts['FAILED']}"
                  f" inv={counts['INVALID_DATA']} skip={counts['SKIPPED']}")

    # ── 汇总 ──
    elapsed_total = time.monotonic() - t0
    print(f"\n{'='*60}")
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
        "pipeline_version": args.pipeline_version,
        "total": sum(counts.values()),
        "status_counts": counts,
        "elapsed_s": elapsed_total,
        "avg_time_s": avg if timings else 0,
    }
    atomic_write_json(manifest_path, manifest)
    print(f"  manifest → {manifest_path}")


if __name__ == "__main__":
    main()
