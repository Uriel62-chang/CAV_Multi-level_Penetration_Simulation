"""v0.4.0 仿真任务数据结构

RunSpec / PreparedRun / SimulationResult + 工具函数。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── run_id 生成 ──

def encode_pcav(pcav: float) -> int:
    """浮点 pCAV → 整数编码 (0.50 → 50)"""
    return round(pcav * 100)


def build_run_id(scenario: str, model: str, pcav: float,
                 vehicle_count: int, seed: int) -> str:
    """确定性 run_id：s2_CACC_p050_v120_seed1"""
    pcav_code = encode_pcav(pcav)
    short_scenario = scenario.replace("scenario_", "s")
    return (f"{short_scenario}_{model}_"
            f"p{pcav_code:03d}_"
            f"v{vehicle_count:03d}_"
            f"seed{seed}")


# ── 数据结构 ──

@dataclass(frozen=True)
class RunSpec:
    """一次 SUMO 仿真的完整参数（不可变）"""
    scenario: str
    model: str
    pcav: float
    vehicle_count: int
    seed: int
    run_id: str
    simulation_end: float = 3600.0
    warmup: float = 600.0
    step_length: float = 0.1
    pipeline_version: str = "v0.4.0-dev"

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "scenario": self.scenario,
            "model": self.model,
            "pcav": self.pcav,
            "vehicle_count": self.vehicle_count,
            "seed": self.seed,
            "simulation_end": self.simulation_end,
            "warmup": self.warmup,
            "step_length": self.step_length,
            "pipeline_version": self.pipeline_version,
        }


@dataclass(frozen=True)
class PreparedRun:
    """准备完成的 run 目录中所有文件路径"""
    run_dir: Path
    route_path: Path
    additional_path: Path
    detector_paths: tuple  # tuple[Path, ...] — 每车道一个
    ssm_path: Path
    lanechange_path: Path
    performance_path: Path
    emissions_path: Path
    vehroute_path: Path
    stdout_path: Path
    stderr_path: Path
    status_path: Path


@dataclass
class SimulationResult:
    """单次 SUMO 仿真的执行结果"""
    run_id: str
    status: str  # SUCCESS | FAILED | SKIPPED | CANCELLED | TIMEOUT
    return_code: Optional[int]
    run_dir: str
    started_at: str
    finished_at: str
    wall_time_s: float
    error_message: Optional[str] = None


# ── 工具函数 ──

def atomic_write_json(path: Path, data: dict) -> None:
    """原子写入 JSON：先写 .tmp，fsync 后 os.replace"""
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, path)


def is_simulation_complete(spec: RunSpec, run_dir: Path,
                           pipeline_version: str) -> bool:
    """检查 run 是否已成功完成（断点续跑判定）"""
    status_path = run_dir / "simulation_status.json"
    if not status_path.exists():
        return False

    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    if data.get("run_id") != spec.run_id:
        return False
    if data.get("pipeline_version") != pipeline_version:
        return False
    if data.get("status") != "SUCCESS":
        return False
    if data.get("return_code") != 0:
        return False

    required_files = [
        run_dir / "ssm.xml",
        run_dir / "lanechange.xml",
        run_dir / "performance.xml",
        run_dir / "emissions.xml",
        run_dir / "vehroute.xml",
    ]
    for path in required_files:
        if not path.exists():
            return False
        if path.stat().st_size == 0:
            return False

    return True
