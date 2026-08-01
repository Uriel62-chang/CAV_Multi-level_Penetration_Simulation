"""版本化实验配置的加载、规范化、校验与哈希。"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts.config import (
    CAV_ACTION_STEP_LENGTH,
    CAV_MODELS,
    SSM_DRAC_THRESHOLD_MPS2,
    SSM_TTC_THRESHOLD_S,
)

PIPELINE_V4_1 = "v0.4.1"
PIPELINE_V4_0_POST1 = "v0.4.0.post1"
PIPELINE_V4_2 = "v0.4.2"
SEED_SCOPE = "vehicle_type_assignment"
GRID_MODE_REQUESTED_PCAV = "requested_pcav"
GRID_MODE_CAV_COUNT = "cav_count"
GRID_MODES = (GRID_MODE_REQUESTED_PCAV, GRID_MODE_CAV_COUNT)

_COMMON_REQUIRED = {
    "config_version",
    "pipeline_version",
    "schema_version",
    "scenarios",
    "models",
    "seed_scope",
    "simulation_end",
    "warmup",
    "step_length",
    "detector_frequency",
    "edge_data_frequency",
    "loops",
    "network_files",
}

_PCAV_MODE_EXTRA = {"pcav_levels", "vehicle_counts", "seeds"}
_CAV_COUNT_MODE_EXTRA = {"treatments", "sumo_seeds"}

_ALL_KNOWN_FIELDS = (
    _COMMON_REQUIRED
    | _PCAV_MODE_EXTRA
    | _CAV_COUNT_MODE_EXTRA
    | {
        "grid_mode",
        "assignment_seeds",
        "ssm_capture_ttc_threshold_s",
        "ssm_capture_drac_threshold_mps2",
        "ssm_measures",
        "ssm_range",
        "ssm_range_m",
        "ssm_trajectories",
        "ssm_extratime_s",
        "fcd_profile",
        "fcd_max_leader_distance_m",
        "with_internal",
    }
)


def canonical_json(data: Any) -> str:
    """返回跨平台稳定的紧凑 JSON。"""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ExperimentConfig:
    config_version: str
    pipeline_version: str
    schema_version: str
    scenarios: tuple[str, ...]
    models: tuple[str, ...]
    seed_scope: str
    simulation_end: float
    warmup: float
    step_length: float
    detector_frequency: int
    edge_data_frequency: int
    loops: int
    network_files: dict[str, str]

    # ── 网格模式 ──
    grid_mode: str = GRID_MODE_REQUESTED_PCAV

    # requested_pcav 模式字段
    pcav_levels: tuple[float, ...] = ()
    vehicle_counts: tuple[int, ...] = ()
    seeds: tuple[int, ...] = ()

    # cav_count 模式字段
    treatments: tuple[dict[str, Any], ...] = ()
    sumo_seeds: tuple[int, ...] = ()

    # ── SSM capture 配置 ──
    ssm_capture_ttc_threshold_s: float = SSM_TTC_THRESHOLD_S
    ssm_capture_drac_threshold_mps2: float = SSM_DRAC_THRESHOLD_MPS2
    ssm_measures: str = "TTC DRAC"
    ssm_range: str = "50.0"
    ssm_trajectories: bool = False
    ssm_extratime_s: float = 5.0

    # 阶段 1 新增：ssm_range 数值形式
    ssm_range_m: float = 50.0

    # 阶段 1 新增：FCD output profile
    fcd_profile: str | None = None
    fcd_max_leader_distance_m: float | None = None

    # ── edgeData internal edge ──
    with_internal: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentConfig:
        _check_common_missing(data)
        _warn_or_reject_unknown(data)

        grid_mode = str(data.get("grid_mode", GRID_MODE_REQUESTED_PCAV))
        if grid_mode not in GRID_MODES:
            raise ValueError(f"grid_mode must be one of {GRID_MODES}, got {grid_mode!r}")

        if grid_mode == GRID_MODE_REQUESTED_PCAV:
            _check_required(data, _PCAV_MODE_EXTRA)
            pcav = tuple(float(Decimal(str(x))) for x in data["pcav_levels"])
            vct = tuple(int(x) for x in data["vehicle_counts"])
            seeds = tuple(int(x) for x in data["seeds"])
            treatments: tuple[dict[str, Any], ...] = ()
            sumo_seeds: tuple[int, ...] = ()
        else:
            _check_required(data, _CAV_COUNT_MODE_EXTRA)
            treatments = tuple(dict(t) for t in data["treatments"])
            sumo_seeds = tuple(int(x) for x in data["sumo_seeds"])
            pcav = ()
            vct = ()
            seeds = tuple(int(x) for x in data.get("assignment_seeds", data.get("seeds", ())))

        config = cls(
            config_version=str(data["config_version"]),
            pipeline_version=str(data["pipeline_version"]),
            schema_version=str(data["schema_version"]),
            scenarios=tuple(str(x) for x in data["scenarios"]),
            models=tuple(str(x) for x in data["models"]),
            seed_scope=str(data["seed_scope"]),
            simulation_end=float(data["simulation_end"]),
            warmup=float(data["warmup"]),
            step_length=float(data["step_length"]),
            detector_frequency=int(data["detector_frequency"]),
            edge_data_frequency=int(data["edge_data_frequency"]),
            loops=int(data["loops"]),
            network_files={str(k): str(v) for k, v in data["network_files"].items()},
            grid_mode=grid_mode,
            pcav_levels=pcav,
            vehicle_counts=vct,
            seeds=seeds,
            treatments=treatments,
            sumo_seeds=sumo_seeds,
            ssm_capture_ttc_threshold_s=float(
                data.get("ssm_capture_ttc_threshold_s", SSM_TTC_THRESHOLD_S)
            ),
            ssm_capture_drac_threshold_mps2=float(
                data.get("ssm_capture_drac_threshold_mps2", SSM_DRAC_THRESHOLD_MPS2)
            ),
            ssm_measures=str(data.get("ssm_measures", "TTC DRAC")),
            ssm_range=str(data.get("ssm_range", "50.0")),
            ssm_range_m=float(data.get("ssm_range_m", 50.0)),
            ssm_trajectories=bool(data.get("ssm_trajectories", False)),
            ssm_extratime_s=float(data.get("ssm_extratime_s", 5.0)),
            fcd_profile=_optional_str(data, "fcd_profile"),
            fcd_max_leader_distance_m=_optional_float(data, "fcd_max_leader_distance_m"),
            with_internal=bool(data.get("with_internal", False)),
        )
        config.validate()
        return config

    def to_dict(self) -> dict[str, Any]:
        # This is the historical resolved-manifest representation.  It includes
        # the capture defaults available in v0.4.0.post1, but not later fields.
        if self.pipeline_version != PIPELINE_V4_1:
            return {
                "config_version": self.config_version,
                "pipeline_version": self.pipeline_version,
                "schema_version": self.schema_version,
                "scenarios": list(self.scenarios),
                "models": list(self.models),
                "pcav_levels": list(self.pcav_levels),
                "vehicle_counts": list(self.vehicle_counts),
                "seeds": list(self.seeds),
                "seed_scope": self.seed_scope,
                "simulation_end": self.simulation_end,
                "warmup": self.warmup,
                "step_length": self.step_length,
                "detector_frequency": self.detector_frequency,
                "edge_data_frequency": self.edge_data_frequency,
                "loops": self.loops,
                "network_files": dict(self.network_files),
                "grid_mode": self.grid_mode,
                "ssm_capture_ttc_threshold_s": self.ssm_capture_ttc_threshold_s,
                "ssm_capture_drac_threshold_mps2": self.ssm_capture_drac_threshold_mps2,
                "ssm_measures": self.ssm_measures,
                "ssm_range": self.ssm_range,
                "ssm_trajectories": self.ssm_trajectories,
                "with_internal": self.with_internal,
            }

        result: dict[str, Any] = {
            "config_version": self.config_version,
            "pipeline_version": self.pipeline_version,
            "schema_version": self.schema_version,
            "scenarios": list(self.scenarios),
            "models": list(self.models),
            "seed_scope": self.seed_scope,
            "simulation_end": self.simulation_end,
            "warmup": self.warmup,
            "step_length": self.step_length,
            "detector_frequency": self.detector_frequency,
            "edge_data_frequency": self.edge_data_frequency,
            "loops": self.loops,
            "network_files": dict(self.network_files),
            "grid_mode": self.grid_mode,
            "ssm_capture_ttc_threshold_s": self.ssm_capture_ttc_threshold_s,
            "ssm_capture_drac_threshold_mps2": self.ssm_capture_drac_threshold_mps2,
            "ssm_measures": self.ssm_measures,
            "ssm_trajectories": self.ssm_trajectories,
            "ssm_extratime_s": self.ssm_extratime_s,
            "with_internal": self.with_internal,
        }
        result["ssm_range_m"] = self.ssm_range_m
        if self.grid_mode == GRID_MODE_REQUESTED_PCAV:
            result["pcav_levels"] = list(self.pcav_levels)
            result["vehicle_counts"] = list(self.vehicle_counts)
            result["seeds"] = list(self.seeds)
        else:
            result["treatments"] = list(self.treatments)
            result["assignment_seeds"] = list(self.seeds)
            result["sumo_seeds"] = list(self.sumo_seeds)
        if self.fcd_profile is not None:
            result["fcd_profile"] = self.fcd_profile
        if self.fcd_max_leader_distance_m is not None:
            result["fcd_max_leader_distance_m"] = self.fcd_max_leader_distance_m
        return result

    def sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict()).encode("utf-8")).hexdigest()

    def validate(self) -> None:
        # pipeline/schema 版本配对
        if self.pipeline_version == PIPELINE_V4_1:
            if self.schema_version != "2":
                raise ValueError(
                    f"v0.4.1 pipeline requires schema_version=2, got {self.schema_version}"
                )
            if self.ssm_measures != "TTC DRAC":
                raise ValueError(
                    f"stage 1 only supports ssm_measures='TTC DRAC', got {self.ssm_measures!r}"
                )
        if self.pipeline_version == PIPELINE_V4_2 and self.schema_version != "2":
            raise ValueError(
                f"v0.4.2 pipeline requires schema_version=2, got {self.schema_version}"
            )
        _require_nonempty_unique("scenarios", self.scenarios)
        _require_nonempty_unique("models", self.models)
        if self.warmup < 0 or self.warmup >= self.simulation_end:
            raise ValueError("warmup must satisfy 0 <= warmup < simulation_end")
        for name in ("step_length", "detector_frequency", "edge_data_frequency", "loops"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        # NaN/Infinity 拒绝
        for name in (
            "simulation_end",
            "warmup",
            "step_length",
            "ssm_capture_ttc_threshold_s",
            "ssm_capture_drac_threshold_mps2",
            "ssm_extratime_s",
        ):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite, got {getattr(self, name)}")
        if self.fcd_max_leader_distance_m is not None and not math.isfinite(
            self.fcd_max_leader_distance_m
        ):
            raise ValueError(
                f"fcd_max_leader_distance_m must be finite, got {self.fcd_max_leader_distance_m}"
            )
        # pipeline 白名单
        allowed_pipelines = {"v0.4.0.post1", "v0.4.1", "v0.4.2"}
        if self.pipeline_version not in allowed_pipelines:
            raise ValueError(
                f"unsupported pipeline_version: {self.pipeline_version!r}, "
                f"allowed: {sorted(allowed_pipelines)}"
            )
        unsupported = sorted(set(self.models) - set(CAV_MODELS))
        if unsupported:
            raise ValueError(f"unsupported models: {', '.join(unsupported)}")
        if set(self.network_files) != set(self.scenarios):
            raise ValueError("network_files keys must exactly match scenarios")
        if self.seed_scope != SEED_SCOPE:
            raise ValueError(f"seed_scope must be {SEED_SCOPE!r}, got {self.seed_scope!r}")
        if self.ssm_capture_ttc_threshold_s <= 0:
            raise ValueError(
                f"ssm_capture_ttc_threshold_s must be positive, got {self.ssm_capture_ttc_threshold_s}"
            )
        if self.ssm_capture_drac_threshold_mps2 <= 0:
            raise ValueError(
                f"ssm_capture_drac_threshold_mps2 must be positive, got {self.ssm_capture_drac_threshold_mps2}"
            )
        if self.fcd_profile is not None and self.fcd_profile not in ("1s", "0.1s"):
            raise ValueError(f"fcd_profile must be '1s' or '0.1s', got {self.fcd_profile!r}")
        if (
            self.fcd_profile is not None
            and self.fcd_max_leader_distance_m is not None
            and self.fcd_max_leader_distance_m <= 0
        ):
            raise ValueError("fcd_max_leader_distance_m must be positive")
        ratio = Decimal(str(CAV_ACTION_STEP_LENGTH)) / Decimal(str(self.step_length))
        if ratio != ratio.to_integral_value():
            raise ValueError(
                f"step_length must evenly divide CAV actionStepLength ({CAV_ACTION_STEP_LENGTH})"
            )
        validate_analysis_windows(self.warmup, self.detector_frequency, self.edge_data_frequency)
        if self.grid_mode == GRID_MODE_REQUESTED_PCAV:
            self._validate_requested_pcav_mode()
        else:
            self._validate_cav_count_mode()
        if self.fcd_profile is not None and self.fcd_max_leader_distance_m is None:
            raise ValueError("fcd_max_leader_distance_m is required when fcd_profile is set")
        if self.pipeline_version == PIPELINE_V4_1 and (
            self.ssm_range_m <= 0 or not math.isfinite(self.ssm_range_m)
        ):
            raise ValueError(f"ssm_range_m must be positive and finite, got {self.ssm_range_m}")
        if self.ssm_extratime_s <= 0 or not math.isfinite(self.ssm_extratime_s):
            raise ValueError(
                f"ssm_extratime_s must be positive and finite, got {self.ssm_extratime_s}"
            )

    def _validate_requested_pcav_mode(self) -> None:
        _require_nonempty_unique("pcav_levels", self.pcav_levels)
        _require_nonempty_unique("vehicle_counts", self.vehicle_counts)
        _require_nonempty_unique("seeds", self.seeds)
        if any(value < 0 or value > 1 for value in self.pcav_levels):
            raise ValueError("pcav_levels values must satisfy 0 <= pCAV <= 1")
        if any(value <= 0 for value in self.vehicle_counts):
            raise ValueError("vehicle_counts values must be positive")

    def _validate_cav_count_mode(self) -> None:
        if not self.treatments:
            raise ValueError("treatments must not be empty in cav_count mode")
        _require_nonempty_unique("sumo_seeds", self.sumo_seeds)
        if self.seeds and len(self.seeds) != len(set(self.seeds)):
            raise ValueError("duplicate assignment_seeds at config level")
        seen_vn = set()
        for t in self.treatments:
            vn = int(t.get("vehicle_count", 0))
            if vn <= 0:
                raise ValueError(f"treatment vehicle_count must be positive, got {vn}")
            if vn in seen_vn:
                raise ValueError(f"duplicate vehicle_count in treatments: {vn}")
            seen_vn.add(vn)
            cavs = t.get("cav_counts", [])
            if not cavs:
                raise ValueError(f"cav_counts must not be empty for vehicle_count={vn}")
            seen_c = set()
            for c in cavs:
                c = int(c)
                if c < 0 or c > vn:
                    raise ValueError(f"cav_count {c} out of range [0, {vn}] for vehicle_count={vn}")
                if c in seen_c:
                    raise ValueError(f"duplicate cav_count {c} for vehicle_count={vn}")
                seen_c.add(c)
            # 校验 treatment 级 assignment_seeds 无重复
            aseeds = t.get("assignment_seeds", [])
            if aseeds and len(aseeds) != len(set(aseeds)):
                raise ValueError(f"duplicate assignment_seeds in treatment vehN={vn}")


def _check_common_missing(data: dict[str, Any]) -> None:
    missing = sorted(_COMMON_REQUIRED - data.keys())
    if missing:
        raise ValueError(f"experiment config missing fields: {', '.join(missing)}")


def _check_required(data: dict[str, Any], required: set[str]) -> None:
    missing = sorted(required - data.keys())
    if missing:
        raise ValueError(
            f"experiment config missing fields for {data.get('grid_mode', 'legacy')!r} mode: {', '.join(missing)}"
        )


def _warn_or_reject_unknown(data: dict[str, Any]) -> None:
    unknown = sorted(data.keys() - _ALL_KNOWN_FIELDS)
    if unknown:
        raise ValueError(f"experiment config unknown fields: {', '.join(unknown)}")


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    return str(value) if value is not None else None


def _optional_float(data: dict[str, Any], key: str) -> float | None:
    value = data.get(key)
    return float(value) if value is not None else None


def _require_nonempty_unique(name: str, values: tuple[Any, ...]) -> None:
    if not values:
        raise ValueError(f"{name} must not be empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicates")


def _validate_window_alignment(warmup: float, frequency: int, frequency_name: str) -> None:
    ratio = Decimal(str(warmup)) / Decimal(str(frequency))
    if ratio != ratio.to_integral_value():
        raise ValueError(f"warmup must be an exact multiple of {frequency_name}")


def validate_analysis_windows(
    warmup: float,
    detector_frequency: int,
    edge_data_frequency: int,
) -> None:
    """确保所有按完整 interval 过滤的指标从同一 warmup 边界开始。"""
    _validate_window_alignment(warmup, detector_frequency, "detector_frequency")
    _validate_window_alignment(warmup, edge_data_frequency, "edge_data_frequency")


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    config_path = Path(path)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"experiment config not found: {config_path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"experiment config unreadable: {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("experiment config root must be an object")
    return ExperimentConfig.from_dict(data)
