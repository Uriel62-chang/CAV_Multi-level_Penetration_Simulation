"""v0.4.0.post1 仿真任务数据结构

RunSpec / PreparedRun / SimulationResult + 工具函数。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

# ── run_id 生成 ──


def encode_pcav(pcav: float) -> int:
    """浮点 pCAV → 整数编码 (0.50 → 50)"""
    return round(pcav * 100)


def build_run_id(scenario: str, model: str, pcav: float, vehicle_count: int, seed: int) -> str:
    """确定性 run_id：s2_CACC_p050_v120_seed1"""
    pcav_code = encode_pcav(pcav)
    short_scenario = scenario.replace("scenario_", "s")
    return f"{short_scenario}_{model}_p{pcav_code:03d}_v{vehicle_count:03d}_seed{seed}"


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
    detector_frequency: int = 120
    edge_data_frequency: int = 300
    loops: int = 300
    network_file: str = "net/scenario_0/loop.net.xml"
    seed_scope: str = "vehicle_type_assignment"
    pipeline_version: str = "v0.4.0.post1"
    schema_version: str = "1"
    config_sha256: str = ""
    network_sha256: str = ""
    experiment_id: str = ""

    @property
    def cav_count(self) -> int:
        return round(self.vehicle_count * self.pcav)

    @property
    def hv_count(self) -> int:
        return self.vehicle_count - self.cav_count

    @property
    def realized_pcav(self) -> float:
        return self.cav_count / self.vehicle_count

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "scenario": self.scenario,
            "model": self.model,
            "pcav": self.pcav,
            "requested_pcav": self.pcav,
            "cav_count": self.cav_count,
            "hv_count": self.hv_count,
            "realized_pcav": self.realized_pcav,
            "vehicle_count": self.vehicle_count,
            "seed": self.seed,
            "simulation_end": self.simulation_end,
            "warmup": self.warmup,
            "step_length": self.step_length,
            "detector_frequency": self.detector_frequency,
            "edge_data_frequency": self.edge_data_frequency,
            "loops": self.loops,
            "network_file": self.network_file,
            "seed_scope": self.seed_scope,
            "pipeline_version": self.pipeline_version,
            "schema_version": self.schema_version,
            "config_sha256": self.config_sha256,
            "network_sha256": self.network_sha256,
            "experiment_id": self.experiment_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RunSpec:
        """从持久化数据严格重建规格，不从 run_id 推导任何参数。"""
        required = {
            "scenario",
            "model",
            "pcav",
            "vehicle_count",
            "seed",
            "run_id",
            "simulation_end",
            "warmup",
            "step_length",
            "detector_frequency",
            "edge_data_frequency",
            "loops",
            "network_file",
            "seed_scope",
            "pipeline_version",
            "schema_version",
            "config_sha256",
            "network_sha256",
            "experiment_id",
            "requested_pcav",
            "cav_count",
            "hv_count",
            "realized_pcav",
        }
        missing = sorted(required - data.keys())
        if missing:
            raise ValueError(f"run_spec.json missing fields: {', '.join(missing)}")
        init_fields = required - {
            "requested_pcav",
            "cav_count",
            "hv_count",
            "realized_pcav",
        }
        spec = cls(**{key: data[key] for key in init_fields})
        expected = {
            "requested_pcav": spec.pcav,
            "cav_count": spec.cav_count,
            "hv_count": spec.hv_count,
            "realized_pcav": spec.realized_pcav,
        }
        for key, value in expected.items():
            if data[key] != value:
                raise ValueError(f"run_spec.json inconsistent derived field: {key}")
        return spec

    def sha256(self) -> str:
        """规范化 JSON 的稳定 SHA-256。"""
        payload = json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


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
    return_code: int | None
    run_dir: str
    started_at: str
    finished_at: str
    wall_time_s: float
    error_message: str | None = None


# ── 工具函数 ──


def atomic_write_json(path: Path, data: dict) -> None:
    """原子写入 JSON：先写 .tmp，fsync 后 os.replace"""
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, path)


def write_run_spec(spec: RunSpec, run_dir: Path) -> str:
    """原子持久化完整 RunSpec，并返回内容哈希。"""
    atomic_write_json(run_dir / "run_spec.json", spec.to_dict())
    return spec.sha256()


def load_run_spec(run_dir: Path, expected_sha256: str | None = None) -> RunSpec:
    """读取并校验 run_spec.json。"""
    path = run_dir / "run_spec.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"run_spec.json not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"run_spec.json unreadable: {path}") from exc
    spec = RunSpec.from_dict(data)
    actual = spec.sha256()
    if expected_sha256 is not None and actual != expected_sha256:
        raise ValueError(
            f"run_spec.json SHA-256 mismatch: expected {expected_sha256}, got {actual}"
        )
    return spec


def is_simulation_complete(spec: RunSpec, run_dir: Path, pipeline_version: str) -> bool:
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
    if data.get("run_spec_sha256") != spec.sha256():
        return False
    for field in ("schema_version", "config_sha256", "network_sha256", "experiment_id"):
        if data.get(field) != getattr(spec, field):
            return False
    try:
        persisted_spec = load_run_spec(run_dir, expected_sha256=data["run_spec_sha256"])
    except (ValueError, KeyError):
        return False
    if persisted_spec != spec:
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
