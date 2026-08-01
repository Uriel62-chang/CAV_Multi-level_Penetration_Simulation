"""仿真任务数据结构

RunSpec / PreparedRun / SimulationResult + 工具函数。
从 v0.4.1 起新增 sumo_seed 字段、cav_count 作为输入字段（可空自动推导）、
以及 cav_count 网格模式的 run_id 格式；同时保持旧 pipeline_version 的哈希兼容。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from scripts.provenance import sha256_file

# pipeline 版本常量
PIPELINE_V4_0_POST1 = "v0.4.0.post1"
PIPELINE_V4_1 = "v0.4.1"
PIPELINE_V4_2 = "v0.4.2"

# ── run_id 生成 ──


def encode_pcav(pcav: float) -> int:
    """浮点 pCAV → 整数编码 (0.50 → 50)"""
    return round(pcav * 100)


def build_run_id(
    scenario: str,
    model: str | None = None,
    pcav: float | None = None,
    vehicle_count: int | None = None,
    seed: int | None = None,
    *,
    cav_count: int | None = None,
    assignment_seed: int | None = None,
    sumo_seed: int | None = None,
) -> str:
    """确定性 run_id 生成。

    cav_count 为 None → 旧格式（v0.4.0 兼容）：
      ``s2_CACC_p050_v120_seed1``

    cav_count 不为 None → 新格式（v0.4.1）：
      ``s2_CACC_v120_c060_as01_ss101``
      cav_count=0 时 model 替换为 ``HVONLY``，inactive aseed 写为 ``00``。
    """
    short_scenario = scenario.replace("scenario_", "s")

    if cav_count is None:
        if model is None or pcav is None or vehicle_count is None or seed is None:
            raise ValueError("legacy build_run_id requires model, pcav, vehicle_count, seed")
        pcav_code = encode_pcav(pcav)
        return f"{short_scenario}_{model}_p{pcav_code:03d}_v{vehicle_count:03d}_seed{seed}"

    if vehicle_count is None or sumo_seed is None:
        raise ValueError("v0.4.1 build_run_id requires vehicle_count, cav_count, sumo_seed")
    effective_model = "HVONLY" if cav_count == 0 else (model or "UNKN")
    effective_aseed = 0 if assignment_seed is None else assignment_seed
    return (
        f"{short_scenario}_{effective_model}_v{vehicle_count:03d}_"
        f"c{cav_count:03d}_as{effective_aseed:02d}_ss{sumo_seed:03d}"
    )


# ── 数据结构 ──


def _optional_str(data: dict, key: str) -> str | None:
    value = data.get(key)
    return str(value) if value is not None else None


def _optional_float(data: dict, key: str) -> float | None:
    value = data.get(key)
    return float(value) if value is not None else None


# v0.4.0.post1 to_dict 字段集合（保持稳定以保证哈希兼容）
_LEGACY_TO_DICT_KEYS = {
    "run_id",
    "scenario",
    "model",
    "pcav",
    "vehicle_count",
    "seed",
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

# v0.4.1 补充字段
_V4_1_EXTRA_KEYS = {
    "sumo_seed",
    "ssm_capture_ttc_threshold_s",
    "ssm_capture_drac_threshold_mps2",
    "ssm_range_m",
    "ssm_trajectories",
    "ssm_extratime_s",
    "with_internal",
    "fcd_profile",
    "fcd_max_leader_distance_m",
}


@dataclass(frozen=True)
class RunSpec:
    """一次 SUMO 仿真的完整参数（不可变）

    cav_count 为 None 时自动从 pcav 推导（向后兼容旧构造方式）。
    显式设置 cav_count 时（cav_count 网格模式），pcav 为 derived 值。
    requested_pcav 仅在 requested_pcav 网格模式下有意义，cav_count 模式为 None。
    """

    scenario: str
    model: str
    pcav: float
    vehicle_count: int
    seed: int  # assignment_seed（历史命名，保持兼容）
    run_id: str
    simulation_end: float = 3600.0
    warmup: float = 600.0
    step_length: float = 0.1
    detector_frequency: int = 120
    edge_data_frequency: int = 300
    loops: int = 300
    network_file: str = "net/scenario_0/loop.net.xml"
    seed_scope: str = "vehicle_type_assignment"
    pipeline_version: str = PIPELINE_V4_0_POST1
    schema_version: str = "1"
    config_sha256: str = ""
    network_sha256: str = ""
    experiment_id: str = ""

    # v0.4.1 新增
    sumo_seed: int = 0

    # cav_count 作为输入字段；None 时从 pcav*vehicle_count 推导
    cav_count: int | None = None
    # requested_pcav：requested_pcav 模式等于 pcav，cav_count 模式为 None
    requested_pcav: float | None = None

    # 阶段 1 新增：SSM capture profile
    ssm_capture_ttc_threshold_s: float = 3.0
    ssm_capture_drac_threshold_mps2: float = 3.0
    ssm_range_m: float = 50.0
    ssm_trajectories: bool = False
    ssm_extratime_s: float = 5.0

    # v0.4.2 新增：SSM analysis 配置（P0-5，单源；仅 v0.4.2 使用）
    analysis_ttc_threshold_s: float = 3.0
    analysis_drac_threshold_mps2: float = 3.0
    ssm_dedup_method: str = (
        "greedy_one_to_one_80pct"  # none | greedy_one_to_one_80pct | sorted_greedy_80pct
    )
    ssm_mirror_overlap_ratio: float = 0.8
    ssm_fragment_merge_gap_s: float = 0.0

    # 阶段 1 新增：edgeData
    with_internal: bool = False

    # 阶段 1 新增：FCD output
    fcd_profile: str | None = None

    # v0.4.2 新增：experiment role 与 SSM 启用状态（P0-1）
    experiment_role: str = "main_factorial"  # main_factorial | safety
    ssm_enabled: bool = False  # 主 factorial 关闭 SSM，safety 开启；ssm.xml 意图性缺失时 False
    fcd_max_leader_distance_m: float | None = None

    def __post_init__(self) -> None:
        if self.cav_count is None:
            derived = round(self.vehicle_count * self.pcav)
            object.__setattr__(self, "cav_count", derived)
        else:
            if self.cav_count < 0 or self.cav_count > self.vehicle_count:
                raise ValueError(
                    f"cav_count={self.cav_count} out of range [0, {self.vehicle_count}]"
                )
        # v0.4.1 / v0.4.2 模式下校验 pcav 与 cav_count 一致性
        if self.pipeline_version in (PIPELINE_V4_1, PIPELINE_V4_2):
            expected = (self.cav_count or 0) / self.vehicle_count
            if abs(self.pcav - expected) > 1e-9:
                raise ValueError(
                    f"pcav={self.pcav} inconsistent with cav_count={self.cav_count} "
                    f"(vehicle_count={self.vehicle_count}, expected pcav={expected})"
                )
        if self.requested_pcav is None and self.pipeline_version == PIPELINE_V4_0_POST1:
            object.__setattr__(self, "requested_pcav", self.pcav)
        if self.pipeline_version in (PIPELINE_V4_1, PIPELINE_V4_2) and self.sumo_seed < 0:
            raise ValueError(f"sumo_seed must be non-negative, got {self.sumo_seed}")
        # 阶段 1 新增字段校验（v0.4.1 / v0.4.2）
        if self.pipeline_version in (PIPELINE_V4_1, PIPELINE_V4_2):
            if self.ssm_capture_ttc_threshold_s <= 0 or not self._finite(
                self.ssm_capture_ttc_threshold_s
            ):
                raise ValueError("ssm_capture_ttc_threshold_s must be positive and finite")
            if self.ssm_capture_drac_threshold_mps2 <= 0 or not self._finite(
                self.ssm_capture_drac_threshold_mps2
            ):
                raise ValueError("ssm_capture_drac_threshold_mps2 must be positive and finite")
            if self.ssm_range_m <= 0 or not self._finite(self.ssm_range_m):
                raise ValueError("ssm_range_m must be positive and finite")
            if self.ssm_extratime_s <= 0 or not self._finite(self.ssm_extratime_s):
                raise ValueError("ssm_extratime_s must be positive and finite")
            if self.fcd_profile is not None and self.fcd_profile not in ("1s", "0.1s"):
                raise ValueError(f"fcd_profile must be '1s' or '0.1s', got {self.fcd_profile!r}")
            if self.fcd_profile is not None:
                if self.fcd_max_leader_distance_m is None:
                    raise ValueError("fcd_max_leader_distance_m required when fcd_profile is set")
                if self.fcd_max_leader_distance_m <= 0 or not self._finite(
                    self.fcd_max_leader_distance_m
                ):
                    raise ValueError("fcd_max_leader_distance_m must be positive and finite")
        # v0.4.2 新增：experiment_role / analysis 配置校验
        if self.pipeline_version == PIPELINE_V4_2:
            if self.experiment_role not in ("main_factorial", "safety"):
                raise ValueError(
                    f"experiment_role must be 'main_factorial' or 'safety', "
                    f"got {self.experiment_role!r}"
                )
            if self.analysis_ttc_threshold_s <= 0 or not self._finite(
                self.analysis_ttc_threshold_s
            ):
                raise ValueError("analysis_ttc_threshold_s must be positive and finite")
            if self.analysis_drac_threshold_mps2 <= 0 or not self._finite(
                self.analysis_drac_threshold_mps2
            ):
                raise ValueError("analysis_drac_threshold_mps2 must be positive and finite")
            if self.ssm_dedup_method not in (
                "none",
                "greedy_one_to_one_80pct",
                "sorted_greedy_80pct",
            ):
                raise ValueError(f"invalid ssm_dedup_method: {self.ssm_dedup_method!r}")
            if self.ssm_mirror_overlap_ratio <= 0 or self.ssm_mirror_overlap_ratio > 1:
                raise ValueError("ssm_mirror_overlap_ratio must be in (0, 1]")
            if self.ssm_fragment_merge_gap_s < 0 or not self._finite(self.ssm_fragment_merge_gap_s):
                raise ValueError("ssm_fragment_merge_gap_s must be non-negative and finite")

    @staticmethod
    def _finite(val: float) -> bool:
        import math

        return math.isfinite(val)

    @property
    def hv_count(self) -> int:
        return self.vehicle_count - (self.cav_count or 0)

    @property
    def realized_pcav(self) -> float:
        c = self.cav_count or 0
        return c / self.vehicle_count

    def to_dict(self) -> dict:
        """按 pipeline_version 输出对应字段集，保持旧版哈希兼容。"""
        result = {
            "run_id": self.run_id,
            "scenario": self.scenario,
            "model": self.model,
            "pcav": self.pcav,
            "vehicle_count": self.vehicle_count,
            "seed": self.seed,
            "simulation_end": float(self.simulation_end),
            "warmup": float(self.warmup),
            "step_length": float(self.step_length),
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
            "cav_count": self.cav_count,
            "hv_count": self.hv_count,
            "realized_pcav": self.realized_pcav,
            "requested_pcav": self.requested_pcav,
        }
        if self.pipeline_version == PIPELINE_V4_1:
            result["sumo_seed"] = self.sumo_seed
            result["ssm_capture_ttc_threshold_s"] = self.ssm_capture_ttc_threshold_s
            result["ssm_capture_drac_threshold_mps2"] = self.ssm_capture_drac_threshold_mps2
            result["ssm_range_m"] = self.ssm_range_m
            result["ssm_trajectories"] = self.ssm_trajectories
            result["ssm_extratime_s"] = self.ssm_extratime_s
            result["with_internal"] = self.with_internal
            result["fcd_profile"] = self.fcd_profile
            result["fcd_max_leader_distance_m"] = self.fcd_max_leader_distance_m
        if self.pipeline_version == PIPELINE_V4_2:
            result["sumo_seed"] = self.sumo_seed
            result["ssm_capture_ttc_threshold_s"] = self.ssm_capture_ttc_threshold_s
            result["ssm_capture_drac_threshold_mps2"] = self.ssm_capture_drac_threshold_mps2
            result["ssm_range_m"] = self.ssm_range_m
            result["ssm_trajectories"] = self.ssm_trajectories
            result["ssm_extratime_s"] = self.ssm_extratime_s
            result["with_internal"] = self.with_internal
            result["fcd_profile"] = self.fcd_profile
            result["fcd_max_leader_distance_m"] = self.fcd_max_leader_distance_m
            result["experiment_role"] = self.experiment_role
            result["ssm_enabled"] = self.ssm_enabled
            result["analysis_ttc_threshold_s"] = self.analysis_ttc_threshold_s
            result["analysis_drac_threshold_mps2"] = self.analysis_drac_threshold_mps2
            result["ssm_dedup_method"] = self.ssm_dedup_method
            result["ssm_mirror_overlap_ratio"] = self.ssm_mirror_overlap_ratio
            result["ssm_fragment_merge_gap_s"] = self.ssm_fragment_merge_gap_s
        return result

    @classmethod
    def from_dict(cls, data: dict) -> RunSpec:
        """从持久化数据重建规格，根据 pipeline_version 选择字段集。"""
        pv = data.get("pipeline_version", PIPELINE_V4_0_POST1)
        if pv == PIPELINE_V4_1:
            return cls._from_dict_v4_1(data)
        if pv == PIPELINE_V4_2:
            return cls._from_dict_v4_2(data)
        if pv == PIPELINE_V4_0_POST1:
            return cls._from_dict_legacy(data)
        raise ValueError(f"unsupported pipeline_version: {pv}")

    @classmethod
    def _from_dict_v4_1(cls, data: dict) -> RunSpec:
        required = _LEGACY_TO_DICT_KEYS | _V4_1_EXTRA_KEYS
        missing = sorted(required - data.keys())
        if missing:
            raise ValueError(f"v0.4.1 run_spec.json missing fields: {', '.join(missing)}")

        vn = int(data["vehicle_count"])
        pcav = float(data["pcav"])
        cav_count = int(data["cav_count"])
        hv_count = int(data["hv_count"])
        realized_pcav = float(data["realized_pcav"])
        requested_pcav_raw = data.get("requested_pcav")
        requested_pcav = float(requested_pcav_raw) if requested_pcav_raw is not None else None

        # 不变量校验
        if cav_count < 0 or cav_count > vn:
            raise ValueError(f"stored cav_count={cav_count} out of range [0, {vn}]")
        if hv_count != vn - cav_count:
            raise ValueError(
                f"stored hv_count={hv_count} != vehicle_count - cav_count ({vn} - {cav_count})"
            )
        if abs(realized_pcav - cav_count / vn) > 1e-9:
            raise ValueError(
                f"stored realized_pcav={realized_pcav} != cav_count/vn={cav_count / vn}"
            )
        if requested_pcav is not None and abs(requested_pcav - pcav) > 1e-9:
            raise ValueError(f"stored requested_pcav={requested_pcav} != pcav={pcav}")

        return cls(
            scenario=str(data["scenario"]),
            model=str(data["model"]),
            pcav=pcav,
            vehicle_count=vn,
            seed=int(data["seed"]),
            run_id=str(data["run_id"]),
            simulation_end=float(data["simulation_end"]),
            warmup=float(data["warmup"]),
            step_length=float(data["step_length"]),
            detector_frequency=int(data["detector_frequency"]),
            edge_data_frequency=int(data["edge_data_frequency"]),
            loops=int(data["loops"]),
            network_file=str(data["network_file"]),
            seed_scope=str(data["seed_scope"]),
            pipeline_version=str(data["pipeline_version"]),
            schema_version=str(data["schema_version"]),
            config_sha256=str(data.get("config_sha256", "")),
            network_sha256=str(data.get("network_sha256", "")),
            experiment_id=str(data.get("experiment_id", "")),
            sumo_seed=int(data["sumo_seed"]),
            cav_count=cav_count,
            requested_pcav=requested_pcav,
            ssm_capture_ttc_threshold_s=float(data["ssm_capture_ttc_threshold_s"]),
            ssm_capture_drac_threshold_mps2=float(data["ssm_capture_drac_threshold_mps2"]),
            ssm_range_m=float(data["ssm_range_m"]),
            ssm_trajectories=bool(data["ssm_trajectories"]),
            ssm_extratime_s=float(data.get("ssm_extratime_s", 5.0)),
            with_internal=bool(data["with_internal"]),
            fcd_profile=_optional_str(data, "fcd_profile"),
            fcd_max_leader_distance_m=_optional_float(data, "fcd_max_leader_distance_m"),
        )

    @classmethod
    def _from_dict_v4_2(cls, data: dict) -> RunSpec:
        """v0.4.2 run_spec：v4_1 全部字段 + experiment_role/ssm_enabled。"""
        required = _LEGACY_TO_DICT_KEYS | _V4_1_EXTRA_KEYS
        missing = sorted(required - data.keys())
        if missing:
            raise ValueError(f"v0.4.2 run_spec.json missing fields: {', '.join(missing)}")

        spec = cls._from_dict_v4_1(data)
        object.__setattr__(
            spec, "experiment_role", str(data.get("experiment_role", "main_factorial"))
        )
        # P0-6：显式布尔解析（"false"/"0"/"" → False），避免 bool("false")=True
        raw_ssm_enabled = data.get("ssm_enabled", False)
        if isinstance(raw_ssm_enabled, str):
            ssm_enabled = raw_ssm_enabled.strip().lower() in ("1", "true", "yes")
        else:
            ssm_enabled = bool(raw_ssm_enabled)
        object.__setattr__(spec, "ssm_enabled", ssm_enabled)
        object.__setattr__(
            spec, "analysis_ttc_threshold_s", float(data.get("analysis_ttc_threshold_s", 3.0))
        )
        object.__setattr__(
            spec,
            "analysis_drac_threshold_mps2",
            float(data.get("analysis_drac_threshold_mps2", 3.0)),
        )
        object.__setattr__(
            spec,
            "ssm_dedup_method",
            str(data.get("ssm_dedup_method", "greedy_one_to_one_80pct")),
        )
        object.__setattr__(
            spec, "ssm_mirror_overlap_ratio", float(data.get("ssm_mirror_overlap_ratio", 0.8))
        )
        object.__setattr__(
            spec, "ssm_fragment_merge_gap_s", float(data.get("ssm_fragment_merge_gap_s", 0.0))
        )
        # P0-6：反序列化后显式校验（frozen 对象 setattr 绕过 __post_init__）
        if spec.experiment_role not in ("main_factorial", "safety"):
            raise ValueError(f"invalid experiment_role: {spec.experiment_role}")
        if spec.analysis_ttc_threshold_s <= 0 or not spec._finite(spec.analysis_ttc_threshold_s):
            raise ValueError("analysis_ttc_threshold_s must be positive and finite")
        if spec.analysis_drac_threshold_mps2 <= 0 or not spec._finite(
            spec.analysis_drac_threshold_mps2
        ):
            raise ValueError("analysis_drac_threshold_mps2 must be positive and finite")
        if spec.ssm_dedup_method not in (
            "none",
            "greedy_one_to_one_80pct",
            "sorted_greedy_80pct",
        ):
            raise ValueError(f"invalid ssm_dedup_method: {spec.ssm_dedup_method!r}")
        if not (0 < spec.ssm_mirror_overlap_ratio <= 1):
            raise ValueError("ssm_mirror_overlap_ratio must be in (0, 1]")
        if spec.ssm_fragment_merge_gap_s < 0 or not spec._finite(spec.ssm_fragment_merge_gap_s):
            raise ValueError("ssm_fragment_merge_gap_s must be non-negative and finite")
        return spec

    @classmethod
    def _from_dict_legacy(cls, data: dict) -> RunSpec:
        """只读兼容 v0.4.0.post1 run_spec.json。"""
        required = _LEGACY_TO_DICT_KEYS
        missing = sorted(required - data.keys())
        if missing:
            raise ValueError(f"legacy run_spec.json missing fields: {', '.join(missing)}")
        vn = int(data["vehicle_count"])
        pcav = float(data["pcav"])
        expected_cav = round(vn * pcav)
        if data["cav_count"] != expected_cav:
            raise ValueError("legacy run_spec.json inconsistent cav_count")
        if data["hv_count"] != vn - expected_cav:
            raise ValueError("legacy run_spec.json inconsistent hv_count")
        if float(data["realized_pcav"]) != expected_cav / vn:
            raise ValueError("legacy run_spec.json inconsistent realized_pcav")
        return cls(
            scenario=str(data["scenario"]),
            model=str(data["model"]),
            pcav=pcav,
            vehicle_count=vn,
            seed=int(data["seed"]),
            run_id=str(data["run_id"]),
            simulation_end=float(data["simulation_end"]),
            warmup=float(data["warmup"]),
            step_length=float(data["step_length"]),
            detector_frequency=int(data["detector_frequency"]),
            edge_data_frequency=int(data["edge_data_frequency"]),
            loops=int(data["loops"]),
            network_file=str(data["network_file"]),
            seed_scope=str(data["seed_scope"]),
            pipeline_version=PIPELINE_V4_0_POST1,
            schema_version=str(data["schema_version"]),
            config_sha256=str(data.get("config_sha256", "")),
            network_sha256=str(data.get("network_sha256", "")),
            experiment_id=str(data.get("experiment_id", "")),
            sumo_seed=0,
            cav_count=expected_cav,
            requested_pcav=pcav,
        )

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
    detector_paths: tuple  # tuple[Path, ...]
    ssm_path: Path
    lanechange_path: Path
    performance_path: Path
    emissions_path: Path
    vehroute_path: Path
    stdout_path: Path
    stderr_path: Path
    status_path: Path
    vehicle_type_map_path: Path | None = None

    # 阶段 2：schema=2 子群输出路径
    performance_HV_path: Path | None = None
    performance_CAV_path: Path | None = None
    emissions_HV_path: Path | None = None
    emissions_CAV_path: Path | None = None
    detector_paths_HV: tuple[Path, ...] = ()
    detector_paths_CAV: tuple[Path, ...] = ()


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
    if spec.pipeline_version == PIPELINE_V4_1 and data.get("sumo_seed") != spec.sumo_seed:
        return False

    try:
        persisted_spec = load_run_spec(run_dir, expected_sha256=data["run_spec_sha256"])
    except (ValueError, KeyError):
        return False
    if persisted_spec != spec:
        return False

    required_files = [
        run_dir / "routes.rou.xml",
        run_dir / "lanechange.xml",
        run_dir / "performance.xml",
        run_dir / "emissions.xml",
        run_dir / "vehroute.xml",
    ]
    # SSM 输出：v0.4.2 主 factorial 为意图性缺失（ssm_enabled=False），safety 要求存在
    if spec.pipeline_version == PIPELINE_V4_2 and not spec.ssm_enabled:
        if (run_dir / "ssm.xml").exists():
            return False
        if (run_dir / "ssm_compact.xml").exists():
            return False
    else:
        required_files.append(run_dir / "ssm.xml")
    if spec.pipeline_version in (PIPELINE_V4_1, PIPELINE_V4_2):
        required_files.append(run_dir / "vehicle_type_map.json")
        if spec.fcd_profile is not None:
            required_files.append(run_dir / "fcd.xml.gz")
        if getattr(spec, "schema_version", "1") == "2":
            required_files.extend(
                [
                    run_dir / "performance_HV.xml",
                    run_dir / "performance_CAV.xml",
                    run_dir / "emissions_HV.xml",
                    run_dir / "emissions_CAV.xml",
                ]
            )
            network_file = Path(spec.network_file)
            net_meta_path = network_file.with_name("net.json")
            import json as _json

            if not net_meta_path.exists():
                return False
            try:
                net_meta = _json.loads(net_meta_path.read_text(encoding="utf-8"))
                if not isinstance(net_meta, dict):
                    return False
                raw = net_meta.get("num_lanes")
                if type(raw) is not int or raw < 1:
                    return False
            except Exception:
                return False
            num_lanes = raw
            for lane_idx in range(num_lanes):
                lane_all = run_dir / f"detector_lane{lane_idx}.xml"
                if not lane_all.exists() or lane_all.stat().st_size == 0:
                    return False
                p_hv = lane_all.with_name(lane_all.name.replace(".xml", "_HV.xml"))
                p_cav = lane_all.with_name(lane_all.name.replace(".xml", "_CAV.xml"))
                if not p_hv.exists() or p_hv.stat().st_size == 0:
                    return False
                if not p_cav.exists() or p_cav.stat().st_size == 0:
                    return False
    for path in required_files:
        if not path.exists() or path.stat().st_size == 0:
            return False

    # 校验冻结输入哈希（若 status 中有记录）
    for file_key, file_name in (
        ("route_file_sha256", "routes.rou.xml"),
        ("vehicle_type_map_sha256", "vehicle_type_map.json"),
    ):
        stored_hash = data.get(file_key)
        if stored_hash:
            if sha256_file(run_dir / file_name) != stored_hash:
                return False
        elif spec.pipeline_version in (PIPELINE_V4_1, PIPELINE_V4_2):
            return False

    # P0-10：v0.4.2 校验 additional 与 network XML（resume 闭包）
    if spec.pipeline_version == PIPELINE_V4_2:
        additional_sha = data.get("additional_file_sha256")
        if additional_sha:
            if sha256_file(run_dir / "additional.add.xml") != additional_sha:
                return False
        else:
            return False
        network_sha = data.get("network_xml_sha256")
        if network_sha:
            # P0-6：重新哈希实际网络文件比对（不能只与 RunSpec 内同源 SHA 比较）
            if sha256_file(spec.network_file) != network_sha:
                return False
        else:
            return False

    return True
