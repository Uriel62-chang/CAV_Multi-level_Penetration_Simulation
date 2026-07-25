"""版本化实验配置的加载、规范化、校验与哈希。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts.config import CAV_ACTION_STEP_LENGTH, CAV_MODELS

SEED_SCOPE = "vehicle_type_assignment"


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
    pcav_levels: tuple[float, ...]
    vehicle_counts: tuple[int, ...]
    seeds: tuple[int, ...]
    seed_scope: str
    simulation_end: float
    warmup: float
    step_length: float
    detector_frequency: int
    edge_data_frequency: int
    loops: int
    network_files: dict[str, str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentConfig:
        required = {
            "config_version",
            "pipeline_version",
            "schema_version",
            "scenarios",
            "models",
            "pcav_levels",
            "vehicle_counts",
            "seeds",
            "seed_scope",
            "simulation_end",
            "warmup",
            "step_length",
            "detector_frequency",
            "edge_data_frequency",
            "loops",
            "network_files",
        }
        missing = sorted(required - data.keys())
        unknown = sorted(data.keys() - required)
        if missing:
            raise ValueError(f"experiment config missing fields: {', '.join(missing)}")
        if unknown:
            raise ValueError(f"experiment config unknown fields: {', '.join(unknown)}")
        config = cls(
            config_version=str(data["config_version"]),
            pipeline_version=str(data["pipeline_version"]),
            schema_version=str(data["schema_version"]),
            scenarios=tuple(str(x) for x in data["scenarios"]),
            models=tuple(str(x) for x in data["models"]),
            pcav_levels=tuple(float(Decimal(str(x))) for x in data["pcav_levels"]),
            vehicle_counts=tuple(int(x) for x in data["vehicle_counts"]),
            seeds=tuple(int(x) for x in data["seeds"]),
            seed_scope=str(data["seed_scope"]),
            simulation_end=float(data["simulation_end"]),
            warmup=float(data["warmup"]),
            step_length=float(data["step_length"]),
            detector_frequency=int(data["detector_frequency"]),
            edge_data_frequency=int(data["edge_data_frequency"]),
            loops=int(data["loops"]),
            network_files={str(key): str(value) for key, value in data["network_files"].items()},
        )
        config.validate()
        return config

    def to_dict(self) -> dict[str, Any]:
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
        }

    def sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict()).encode("utf-8")).hexdigest()

    def validate(self) -> None:
        _require_nonempty_unique("scenarios", self.scenarios)
        _require_nonempty_unique("models", self.models)
        _require_nonempty_unique("pcav_levels", self.pcav_levels)
        _require_nonempty_unique("vehicle_counts", self.vehicle_counts)
        _require_nonempty_unique("seeds", self.seeds)
        if any(value < 0 or value > 1 for value in self.pcav_levels):
            raise ValueError("pcav_levels values must satisfy 0 <= pCAV <= 1")
        if any(value <= 0 for value in self.vehicle_counts):
            raise ValueError("vehicle_counts values must be positive")
        if self.warmup < 0 or self.warmup >= self.simulation_end:
            raise ValueError("warmup must satisfy 0 <= warmup < simulation_end")
        for name in ("step_length", "detector_frequency", "edge_data_frequency", "loops"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.seed_scope != SEED_SCOPE:
            raise ValueError(f"seed_scope must be {SEED_SCOPE!r}")
        unsupported = sorted(set(self.models) - set(CAV_MODELS))
        if unsupported:
            raise ValueError(f"unsupported models: {', '.join(unsupported)}")
        if set(self.network_files) != set(self.scenarios):
            raise ValueError("network_files keys must exactly match scenarios")
        ratio = Decimal(str(CAV_ACTION_STEP_LENGTH)) / Decimal(str(self.step_length))
        if ratio != ratio.to_integral_value():
            raise ValueError(
                f"step_length must evenly divide CAV actionStepLength ({CAV_ACTION_STEP_LENGTH})"
            )


def _require_nonempty_unique(name: str, values: tuple[Any, ...]) -> None:
    if not values:
        raise ValueError(f"{name} must not be empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicates")


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    config_path = Path(path)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"experiment config not found: {config_path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"experiment config unreadable: {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise TypeError("experiment config root must be an object")
    return ExperimentConfig.from_dict(data)
