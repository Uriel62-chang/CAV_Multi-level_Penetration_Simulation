"""v0.4.0 批量并行仿真 — asyncio + Queue + N worker

架构：
  Python 父进程
  ├── async worker 1 → SUMO 子进程 → 独立 run 目录
  ├── async worker 2 → SUMO 子进程 → 独立 run 目录
  ├── ...
  └── async worker N → SUMO 子进程 → 独立 run 目录

第一阶段只运行 SUMO 并产出原始 XML + simulation_status.json，不做解析。
"""
import argparse
import asyncio
import os
import shutil
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.run_spec import (
    RunSpec, SimulationResult, build_run_id,
    atomic_write_json, is_simulation_complete,
)
from scripts.simulation.single_run import prepare_run, build_sumo_command, DEFAULT_NETWORK_FILE
from scripts.config import (
    DEFAULT_DETECTOR_FREQ, DEFAULT_SIM_END, DEFAULT_WARMUP,
    DEFAULT_STEP_LENGTH, CAV_MODELS,
)

# ═══════════════════════════════════════════════════════════════════
# 默认实验参数
# ═══════════════════════════════════════════════════════════════════

SCENARIOS = ["scenario_0", "scenario_1", "scenario_2", "scenario_3"]
CAV_MODEL_LIST = ["IDM", "CACC"]
DEFAULT_VEHICLE_LEVELS = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120]
DEFAULT_SEEDS = [1, 2, 3, 4, 5]

SCENARIO_WEIGHT = {"scenario_3": 4, "scenario_2": 3, "scenario_1": 2, "scenario_0": 1}


# ═══════════════════════════════════════════════════════════════════
# 任务生成 & 校验
# ═══════════════════════════════════════════════════════════════════

def generate_pcav_levels(step: float = 0.05) -> list:
    n = int(round(1.0 / step))
    return [round(i * step, 10) for i in range(n + 1)]


def build_run_specs(scenarios: list, models: list, pcav_levels: list,
                    vehicle_levels: list, seeds: list,
                    pipeline_version: str = "v0.4.0-dev") -> list[RunSpec]:
    """生成全部 RunSpec，run_id 确定性派生"""
    specs = []
    for scenario in scenarios:
        for model in models:
            for pcav in pcav_levels:
                for vn in vehicle_levels:
                    for seed in seeds:
                        run_id = build_run_id(scenario, model, pcav, vn, seed)
                        specs.append(RunSpec(
                            scenario=scenario, model=model, pcav=pcav,
                            vehicle_count=vn, seed=seed, run_id=run_id,
                            simulation_end=DEFAULT_SIM_END,
                            warmup=DEFAULT_WARMUP,
                            step_length=DEFAULT_STEP_LENGTH,
                            pipeline_version=pipeline_version,
                        ))
    return specs


def validate_specs(specs: list[RunSpec], scenarios: list, models: list,
                   pcav_levels: list, vehicle_levels: list, seeds: list) -> None:
    """全局校验：数量、唯一性、参数合法性"""
    # 数量
    expected = len(scenarios) * len(models) * len(pcav_levels) * len(vehicle_levels) * len(seeds)
    if len(specs) != expected:
        raise RuntimeError(f"Unexpected run count: {len(specs)}, expected {expected}")

    # run_id 唯一性
    seen = {}
    for s in specs:
        seen[s.run_id] = seen.get(s.run_id, 0) + 1
    dupes = {k: v for k, v in seen.items() if v > 1}
    if dupes:
        raise RuntimeError(f"Duplicate run_id: {dupes}")

    # 参数合法性
    for s in specs:
        if s.scenario not in scenarios:
            raise RuntimeError(f"Invalid scenario: {s.scenario}")
        if s.model not in models:
            raise RuntimeError(f"Invalid model: {s.model}")
        if not (0 <= s.pcav <= 1):
            raise RuntimeError(f"Invalid pCAV: {s.pcav}")
        if s.vehicle_count not in vehicle_levels:
            raise RuntimeError(f"Invalid vehN: {s.vehicle_count}")
        if s.seed not in seeds:
            raise RuntimeError(f"Invalid seed: {s.seed}")


def validate_path_safety(output_root: Path, specs: list[RunSpec]) -> None:
    """校验所有 run_dir 均位于 output_root 下方，防止路径逃逸"""
    output_resolved = output_root.resolve()
    for spec in specs:
        run_dir = (output_root / spec.run_id).resolve()
        if output_resolved not in run_dir.parents:
            raise RuntimeError(f"Path escape: {run_dir} not under {output_resolved}")


def validate_environment(output_root: Path, sumo_command: str,
                         network_files: dict) -> None:
    """启动前环境校验：SUMO、路网、磁盘"""
    if shutil.which(sumo_command) is None:
        raise RuntimeError(f"SUMO binary not found: {sumo_command}")

    for scenario, net_file in network_files.items():
        if not os.path.isfile(net_file):
            raise RuntimeError(f"Network file not found: {net_file}")

    output_root.mkdir(parents=True, exist_ok=True)
    if not os.access(output_root, os.W_OK):
        raise RuntimeError(f"Output root not writable: {output_root}")

    usage = shutil.disk_usage(output_root)
    min_bytes = 10 * 1024 ** 3
    if usage.free < min_bytes:
        raise RuntimeError(
            f"Insufficient disk space: {usage.free / 1024**3:.1f} GB free, "
            f"need at least {min_bytes / 1024**3:.0f} GB")


def sort_specs(specs: list[RunSpec]) -> list[RunSpec]:
    """重任务优先：s3 > s2 > s1 > s0，vehN 降序"""
    return sorted(specs, key=lambda s: (
        SCENARIO_WEIGHT.get(s.scenario, 0),
        s.vehicle_count,
        s.pcav,
    ), reverse=True)


# ═══════════════════════════════════════════════════════════════════
# 异步 SUMO 执行
# ═══════════════════════════════════════════════════════════════════

_active_processes: dict[str, asyncio.subprocess.Process] = {}
_shutting_down = False


async def run_sumo_process(
    spec: RunSpec,
    output_root: Path,
    network_file: str,
    sumo_command: str,
    pipeline_version: str,
    timeout_s: float | None,
    resume: bool,
) -> SimulationResult:
    """执行单次 SUMO 仿真，返回 SimulationResult"""
    global _active_processes, _shutting_down

    run_dir = output_root / spec.run_id
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()

    # 断点续跑
    if resume and is_simulation_complete(spec, run_dir, pipeline_version):
        return SimulationResult(
            run_id=spec.run_id, status="SKIPPED", return_code=None,
            run_dir=str(run_dir), started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            wall_time_s=0.0, error_message=None,
        )

    try:
        # 中断检查：收到信号后不再启动新 SUMO
        if _shutting_down:
            return SimulationResult(
                run_id=spec.run_id, status="CANCELLED", return_code=None,
                run_dir=str(run_dir), started_at=started_at,
                finished_at=datetime.now(timezone.utc).isoformat(),
                wall_time_s=0.0, error_message="Interrupted before start",
            )

        # 准备 run 目录
        prepared = prepare_run(spec, run_dir, network_file)
        cmd = build_sumo_command(prepared, network_file, sumo_command,
                                 spec.simulation_end, spec.step_length)

        # 启动 SUMO 子进程
        with prepared.stdout_path.open("wb") as stdout_f, \
             prepared.stderr_path.open("wb") as stderr_f:
            # 不设 cwd，继承项目根目录；所有路径相对项目根即可跨机器
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=stdout_f,
                stderr=stderr_f,
            )
            _active_processes[spec.run_id] = process

            try:
                if timeout_s:
                    return_code = await asyncio.wait_for(
                        process.wait(), timeout=timeout_s)
                else:
                    return_code = await process.wait()
            except asyncio.TimeoutError:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=10)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()

                wall_time = time.monotonic() - t0
                finished_at = datetime.now(timezone.utc).isoformat()
                status_data = {
                    "run_id": spec.run_id, "stage": "SIMULATION",
                    "status": "TIMEOUT", "return_code": None,
                    "pipeline_version": pipeline_version,
                    "started_at": started_at, "finished_at": finished_at,
                    "wall_time_s": wall_time,
                    "error_message": f"Timeout after {timeout_s}s",
                }
                atomic_write_json(prepared.status_path, status_data)
                return SimulationResult(
                    run_id=spec.run_id, status="TIMEOUT", return_code=None,
                    run_dir=str(run_dir), started_at=started_at,
                    finished_at=finished_at, wall_time_s=wall_time,
                    error_message=f"Timeout after {timeout_s}s",
                )

        _active_processes.pop(spec.run_id, None)
        wall_time = time.monotonic() - t0
        finished_at = datetime.now(timezone.utc).isoformat()
        success = return_code == 0

        if success:
            status = "SUCCESS"
            error_msg = None
        elif _shutting_down:
            status = "CANCELLED"
            error_msg = "Interrupted by user"
        else:
            status = "FAILED"
            error_msg = f"SUMO exited with code {return_code}"

        status_data = {
            "run_id": spec.run_id, "stage": "SIMULATION",
            "status": status,
            "return_code": return_code,
            "pipeline_version": pipeline_version,
            "started_at": started_at, "finished_at": finished_at,
            "wall_time_s": wall_time,
            "error_message": error_msg,
        }
        atomic_write_json(prepared.status_path, status_data)

        return SimulationResult(
            run_id=spec.run_id,
            status=status,
            return_code=return_code,
            run_dir=str(run_dir),
            started_at=started_at, finished_at=finished_at,
            wall_time_s=wall_time,
            error_message=error_msg,
        )

    except Exception as e:
        _active_processes.pop(spec.run_id, None)
        wall_time = time.monotonic() - t0
        finished_at = datetime.now(timezone.utc).isoformat()
        return SimulationResult(
            run_id=spec.run_id, status="FAILED", return_code=None,
            run_dir=str(run_dir), started_at=started_at,
            finished_at=finished_at, wall_time_s=wall_time,
            error_message=str(e),
        )


async def sumo_worker(
    worker_id: int,
    queue: asyncio.Queue,
    output_root: Path,
    network_files: dict,
    sumo_command: str,
    pipeline_version: str,
    timeout_s: float | None,
    resume: bool,
    results: list,
    progress: dict,
    total: int,
) -> None:
    """Worker 协程：循环从队列取 RunSpec → 执行 SUMO → 直到收到 None"""
    global _shutting_down
    while True:
        spec = await queue.get()
        if spec is None or _shutting_down:
            queue.task_done()
            break

        net_file = network_files.get(spec.scenario)
        if net_file is None:
            net_file = f"net/{spec.scenario}/loop.net.xml"

        result = await run_sumo_process(
            spec=spec, output_root=output_root, network_file=net_file,
            sumo_command=sumo_command, pipeline_version=pipeline_version,
            timeout_s=timeout_s, resume=resume,
        )
        results.append(result)

        progress["done"] += 1
        done = progress["done"]
        icon = {"SUCCESS": "✓", "FAILED": "✗", "SKIPPED": "○",
                "TIMEOUT": "⏱", "CANCELLED": "⊘"}.get(result.status, "?")
        elapsed = time.monotonic() - progress["start_time"]
        rate = done / elapsed * 3600 if elapsed > 0 else 0

        print(f"[{done:>5}/{total}] {icon} {result.run_id:40s} "
              f"({result.wall_time_s:5.0f}s) | {rate:5.0f} runs/h | {result.status}")

        queue.task_done()


# ═══════════════════════════════════════════════════════════════════
# 信号处理
# ═══════════════════════════════════════════════════════════════════

def handle_signal():
    global _shutting_down
    if _shutting_down:
        return  # 已经处理过，避免重复 terminate
    _shutting_down = True
    print("\n[SIGNAL] Terminating SUMO processes...")
    for run_id, process in list(_active_processes.items()):
        try:
            process.terminate()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════
# 主调度器
# ═══════════════════════════════════════════════════════════════════

async def run_batch(
    specs: list[RunSpec],
    output_root: Path,
    network_files: dict,
    sumo_command: str,
    sumo_processes: int,
    pipeline_version: str,
    timeout_s: float | None,
    resume: bool,
) -> list[SimulationResult]:
    """asyncio Queue + N worker 调度器"""
    global _shutting_down

    # 信号处理器注册在当前运行 loop 上（asyncio.run() 内部创建的 loop）
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            pass

    total = len(specs)
    results: list[SimulationResult] = []
    progress = {"done": 0, "start_time": time.monotonic()}

    queue: asyncio.Queue = asyncio.Queue()

    # 重任务优先入队
    for spec in sort_specs(specs):
        await queue.put(spec)

    # 启动 worker
    workers = [
        asyncio.create_task(sumo_worker(
            worker_id=i, queue=queue, output_root=output_root,
            network_files=network_files, sumo_command=sumo_command,
            pipeline_version=pipeline_version, timeout_s=timeout_s,
            resume=resume, results=results, progress=progress, total=total,
        ))
        for i in range(sumo_processes)
    ]

    # 哨兵值
    for _ in workers:
        await queue.put(None)

    # gather 等待所有 worker 退出（shutdown 时 worker 检测 _shutting_down 后自行退出；
    # 不用 queue.join()——shutdown 后队列仍有未处理条目会导致永久阻塞）
    await asyncio.gather(*workers)

    return results


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="v0.4.0 批量并行仿真")
    parser.add_argument("--sumo-processes", type=int, default=4,
                        help="同时运行的 SUMO 进程数 (默认: 4)")
    parser.add_argument("--output-root", default="raw",
                        help="独立 run 目录根路径 (默认: raw/)")
    parser.add_argument("--pipeline-version", default="v0.4.0-dev",
                        help="管线版本标识，用于断点续跑匹配")
    parser.add_argument("--timeout", type=float, default=None,
                        help="单次 SUMO 最大允许时间 (s)，默认无限制")
    parser.add_argument("--resume", action="store_true",
                        help="跳过已完成且版本匹配的 run")
    parser.add_argument("--dry-run", action="store_true",
                        help="只生成和校验任务，不启动 SUMO")
    parser.add_argument("--sumo", default="sumo",
                        help="SUMO 可执行文件 (默认: sumo)")
    parser.add_argument("--pstep", type=float, default=0.05,
                        help="pCAV 步长 (默认: 0.05 → 21 级)")
    parser.add_argument("--vehN-list", default="",
                        help="自定义车辆数列表，逗号分隔 (默认: 10~120, 步长 10)")
    parser.add_argument("--seeds", default="1,2,3,4,5",
                        help="随机种子列表 (默认: 1,2,3,4,5)")
    args = parser.parse_args()

    # ── 解析参数 ──
    veh_levels = DEFAULT_VEHICLE_LEVELS
    if args.vehN_list.strip():
        veh_levels = [int(x.strip()) for x in args.vehN_list.split(",") if x.strip()]

    seeds = DEFAULT_SEEDS
    if args.seeds.strip():
        seeds = [int(x.strip()) for x in args.seeds.split(",") if x.strip()]

    pcav_levels = generate_pcav_levels(args.pstep)
    scenarios = SCENARIOS
    models = CAV_MODEL_LIST

    # ── 网络文件映射（相对路径，依赖项目根为 CWD，天然跨机器） ──
    network_files = {
        f"scenario_{i}": f"net/scenario_{i}/loop.net.xml"
        for i in range(4)
    }

    # ── 生成 & 校验任务 ──
    specs = build_run_specs(scenarios, models, pcav_levels, veh_levels, seeds,
                            args.pipeline_version)
    print(f"[VALIDATE] {len(specs)} tasks generated")

    try:
        validate_specs(specs, scenarios, models, pcav_levels, veh_levels, seeds)
        print("[VALIDATE] run_id uniqueness: OK")
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    output_root = Path(args.output_root)
    try:
        validate_path_safety(output_root, specs)
        print("[VALIDATE] path safety: OK")
        validate_environment(output_root, args.sumo, network_files)
        print(f"[VALIDATE] SUMO={args.sumo}, output={output_root.resolve()}: OK")
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    # ── dry-run ──
    if args.dry_run:
        ordered = sort_specs(specs)
        print(f"\n[DRY RUN] {len(ordered)} tasks (heavy-first order):")
        for s in ordered[:20]:
            print(f"  {s.run_id:45s} {s.scenario} {s.model} "
                  f"p={s.pcav:.2f} v={s.vehicle_count:>3d} seed={s.seed}")
        if len(ordered) > 20:
            print(f"  ... and {len(ordered) - 20} more")
        print(f"\n[DRY RUN] Validation passed. Use --sumo-processes N to execute.")
        return

    # ── 执行 ──
    print(f"\n[START] {len(specs)} tasks × {args.sumo_processes} workers, "
          f"resume={'ON' if args.resume else 'OFF'}, "
          f"timeout={'{:.0f}s'.format(args.timeout) if args.timeout else 'none'}\n")

    try:
        results = asyncio.run(run_batch(
            specs=specs, output_root=output_root, network_files=network_files,
            sumo_command=args.sumo, sumo_processes=args.sumo_processes,
            pipeline_version=args.pipeline_version, timeout_s=args.timeout,
            resume=args.resume,
        ))
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Cleaning up...")
        return

    # ── 汇总 ──
    status_counts = {}
    for r in results:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
    total_wall = sum(r.wall_time_s for r in results if r.wall_time_s > 0)

    print(f"\n{'='*60}")
    print(f"[DONE] {len(results)} runs completed")
    for st, cnt in sorted(status_counts.items()):
        print(f"  {st}: {cnt}")
    print(f"  total SUMO wall time: {total_wall:.0f}s ({total_wall/3600:.1f}h)")

    # 写 manifest
    manifest_path = output_root / "manifest.json"
    manifest = {
        "pipeline_version": args.pipeline_version,
        "total": len(results),
        "status_counts": status_counts,
        "total_wall_time_s": total_wall,
        "results": [
            {"run_id": r.run_id, "status": r.status,
             "return_code": r.return_code, "wall_time_s": r.wall_time_s,
             "error_message": r.error_message}
            for r in results
        ],
    }
    atomic_write_json(manifest_path, manifest)
    print(f"  manifest → {manifest_path}")


if __name__ == "__main__":
    main()
