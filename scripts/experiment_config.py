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
    SSM_DRAC_THRESHOLD_MPS2,
    SSM_TTC_THRESHOLD_S,
)

PIPELINE_V4_2 = "v0.4.2"
SEED_SCOPE = "vehicle_type_assignment"
GRID_MODE_CAV_COUNT = "cav_count"
GRID_MODES = (GRID_MODE_CAV_COUNT,)

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

_CAV_COUNT_MODE_EXTRA = {"treatments", "sumo_seeds"}

_ALL_KNOWN_FIELDS = (
    _COMMON_REQUIRED
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
        "experiment_role",
        "ssm_enabled",
        "analysis_ttc_threshold_s",
        "analysis_drac_threshold_mps2",
        "ssm_dedup_method",
        "ssm_mirror_overlap_ratio",
        "ssm_fragment_merge_gap_s",
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

    # ── 网格模式（纯净分支：仅 cav_count） ──
    grid_mode: str = GRID_MODE_CAV_COUNT

    # 全局 assignment_seeds 源（cav_count 模式；treatment 未显式指定时使用）
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

    # v0.4.2 新增：experiment role 与 SSM analysis 配置（P0-3/P0-5）
    experiment_role: str = "main_factorial"  # main_factorial | safety
    ssm_enabled: bool = False
    analysis_ttc_threshold_s: float = 3.0
    analysis_drac_threshold_mps2: float = 3.0
    ssm_dedup_method: str = "greedy_one_to_one_80pct"
    ssm_mirror_overlap_ratio: float = 0.8
    ssm_fragment_merge_gap_s: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentConfig:
        _check_common_missing(data)
        _warn_or_reject_unknown(data)

        grid_mode = str(data.get("grid_mode", GRID_MODE_CAV_COUNT))
        if grid_mode not in GRID_MODES:
            raise ValueError(f"grid_mode must be one of {GRID_MODES}, got {grid_mode!r}")

        _check_required(data, _CAV_COUNT_MODE_EXTRA)
        treatments = tuple(dict(t) for t in data["treatments"])
        sumo_seeds = tuple(_coerce_int(x, "sumo_seeds") for x in data["sumo_seeds"])
        seeds = tuple(
            _coerce_int(x, "assignment_seeds")
            for x in data.get("assignment_seeds", data.get("seeds", ()))
        )
        # 审阅 P2-3：assignment seed 非负（与 sumo_seed 语义一致）
        if any(s < 0 for s in seeds):
            raise ValueError("assignment_seeds must be non-negative")

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
            detector_frequency=_coerce_int(data["detector_frequency"], "detector_frequency"),
            edge_data_frequency=_coerce_int(data["edge_data_frequency"], "edge_data_frequency"),
            loops=_coerce_int(data["loops"], "loops"),
            network_files={str(k): str(v) for k, v in data["network_files"].items()},
            grid_mode=grid_mode,
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
            ssm_trajectories=_parse_bool(data, "ssm_trajectories", False),
            ssm_extratime_s=float(data.get("ssm_extratime_s", 5.0)),
            fcd_profile=_optional_str(data, "fcd_profile"),
            fcd_max_leader_distance_m=_optional_float(data, "fcd_max_leader_distance_m"),
            with_internal=_parse_bool(data, "with_internal", False),
            experiment_role=str(data.get("experiment_role", "main_factorial")),
            ssm_enabled=_parse_bool(data, "ssm_enabled", False),
            analysis_ttc_threshold_s=float(data.get("analysis_ttc_threshold_s", 3.0)),
            analysis_drac_threshold_mps2=float(data.get("analysis_drac_threshold_mps2", 3.0)),
            ssm_dedup_method=str(data.get("ssm_dedup_method", "greedy_one_to_one_80pct")),
            ssm_mirror_overlap_ratio=float(data.get("ssm_mirror_overlap_ratio", 0.8)),
            ssm_fragment_merge_gap_s=float(data.get("ssm_fragment_merge_gap_s", 0.0)),
        )
        config.validate()
        return config

    def to_dict(self) -> dict[str, Any]:
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
        result["treatments"] = list(self.treatments)
        result["assignment_seeds"] = list(self.seeds)
        result["sumo_seeds"] = list(self.sumo_seeds)
        if self.fcd_profile is not None:
            result["fcd_profile"] = self.fcd_profile
        if self.fcd_max_leader_distance_m is not None:
            result["fcd_max_leader_distance_m"] = self.fcd_max_leader_distance_m
        # P0-3/P0-5：v0.4.2 额外输出 experiment role 与 analysis 配置（P0-2 修复 SHA 碰撞）
        if self.pipeline_version == PIPELINE_V4_2:
            result["experiment_role"] = self.experiment_role
            result["ssm_enabled"] = self.ssm_enabled
            result["analysis_ttc_threshold_s"] = self.analysis_ttc_threshold_s
            result["analysis_drac_threshold_mps2"] = self.analysis_drac_threshold_mps2
            result["ssm_dedup_method"] = self.ssm_dedup_method
            result["ssm_mirror_overlap_ratio"] = self.ssm_mirror_overlap_ratio
            result["ssm_fragment_merge_gap_s"] = self.ssm_fragment_merge_gap_s
        return result

    def sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict()).encode("utf-8")).hexdigest()

    def _allowed_models(self) -> set[str]:
        """pipeline 模型白名单（P1-1 审阅）。

        v0.4.1/v0.4.2 阶段二解析要求自由流基准（D-008），仅 IDM/CACC 有 artifact；
        ACC 需补充基准后才开放，避免「通过校验 → 跑完昂贵仿真 → 批量解析失败」。
        纯净分支：v0.4.0.post1 全模型分支已移除。
        """
        return {"IDM", "CACC"}

    def validate(self) -> None:
        # pipeline/schema 版本配对（纯净分支：仅 v0.4.2）
        if self.schema_version != "2":
            raise ValueError(
                f"v0.4.2 pipeline requires schema_version=2, got {self.schema_version}"
            )
        # P0-5：v0.4.2 双实验 role×ssm_enabled 一致性 + capture/analysis 阈值包络
        # 审阅 P2-1：ssm_measures/ssm_range 可配置但不生效——SUMO 命令硬编码
        # "TTC DRAC" 与 ssm_range_m（single_run.py）；非默认值直接拒绝，防配置与实现不一致
        if self.ssm_measures != "TTC DRAC":
            raise ValueError(
                f"ssm_measures={self.ssm_measures!r} 不生效——SUMO 命令硬编码 "
                "'TTC DRAC'；请移除该字段或保持默认值"
            )
        if self.ssm_range != "50.0":
            raise ValueError(
                f"ssm_range={self.ssm_range!r} 为废弃字段（不生效）；"
                "请使用 ssm_range_m（当前有效字段）"
            )
        if self.experiment_role not in ("main_factorial", "safety"):
            raise ValueError(
                f"experiment_role must be 'main_factorial' or 'safety', "
                f"got {self.experiment_role!r}"
            )
        if self.experiment_role == "main_factorial" and self.ssm_enabled:
            raise ValueError("main_factorial experiment must set ssm_enabled=false (SSM disabled)")
        if self.experiment_role == "safety" and not self.ssm_enabled:
            raise ValueError("safety experiment must set ssm_enabled=true")
        if self.analysis_ttc_threshold_s > self.ssm_capture_ttc_threshold_s:
            raise ValueError(
                f"analysis_ttc_threshold_s ({self.analysis_ttc_threshold_s}) exceeds "
                f"ssm_capture_ttc_threshold_s ({self.ssm_capture_ttc_threshold_s}); "
                "analysis cannot request events the raw capture did not record"
            )
        if self.analysis_drac_threshold_mps2 < self.ssm_capture_drac_threshold_mps2:
            raise ValueError(
                f"analysis_drac_threshold_mps2 ({self.analysis_drac_threshold_mps2}) "
                f"below ssm_capture_drac_threshold_mps2 "
                f"({self.ssm_capture_drac_threshold_mps2}); "
                "analysis cannot request events the raw capture did not record"
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
        allowed_pipelines = {"v0.4.1", "v0.4.2"}
        if self.pipeline_version not in allowed_pipelines:
            raise ValueError(
                f"unsupported pipeline_version: {self.pipeline_version!r}, "
                f"allowed: {sorted(allowed_pipelines)}"
            )
        unsupported = sorted(set(self.models) - self._allowed_models())
        if unsupported:
            raise ValueError(
                f"unsupported models for pipeline {self.pipeline_version}: {', '.join(unsupported)}"
            )
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
        self._validate_cav_count_mode()
        if self.fcd_profile is not None and self.fcd_max_leader_distance_m is None:
            raise ValueError("fcd_max_leader_distance_m is required when fcd_profile is set")
        # P2-1（审阅）：ssm_range_m 对全部 pipeline 校验（原仅 v0.4.1）；
        # 分析阈值/镜像重叠率统一有限性（NaN 曾绕过 → 静默关闭镜像去重）
        if self.ssm_range_m <= 0 or not math.isfinite(self.ssm_range_m):
            raise ValueError(f"ssm_range_m must be positive and finite, got {self.ssm_range_m}")
        if not math.isfinite(self.ssm_mirror_overlap_ratio) or not (
            0 < self.ssm_mirror_overlap_ratio <= 1
        ):
            raise ValueError(
                f"ssm_mirror_overlap_ratio must be finite in (0, 1], got {self.ssm_mirror_overlap_ratio}"
            )
        if not math.isfinite(self.analysis_ttc_threshold_s) or self.analysis_ttc_threshold_s <= 0:
            raise ValueError(
                f"analysis_ttc_threshold_s must be positive and finite, "
                f"got {self.analysis_ttc_threshold_s}"
            )
        if (
            not math.isfinite(self.analysis_drac_threshold_mps2)
            or self.analysis_drac_threshold_mps2 <= 0
        ):
            raise ValueError(
                f"analysis_drac_threshold_mps2 must be positive and finite, "
                f"got {self.analysis_drac_threshold_mps2}"
            )
        if self.ssm_extratime_s <= 0 or not math.isfinite(self.ssm_extratime_s):
            raise ValueError(
                f"ssm_extratime_s must be positive and finite, got {self.ssm_extratime_s}"
            )

    def _validate_cav_count_mode(self) -> None:
        if not self.treatments:
            raise ValueError("treatments must not be empty in cav_count mode")
        _require_nonempty_unique("sumo_seeds", self.sumo_seeds)
        if self.seeds and len(self.seeds) != len(set(self.seeds)):
            raise ValueError("duplicate assignment_seeds at config level")
        seen_vn = set()
        for t in self.treatments:
            vn = _coerce_int(t.get("vehicle_count", 0), "vehicle_count")
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
                c = _coerce_int(c, "cav_counts")
                if c < 0 or c > vn:
                    raise ValueError(f"cav_count {c} out of range [0, {vn}] for vehicle_count={vn}")
                if c in seen_c:
                    raise ValueError(f"duplicate cav_count {c} for vehicle_count={vn}")
                seen_c.add(c)
            # 校验 treatment 级 assignment_seeds：严格整数 + 非负 + 无重复
            # （审阅 P1-3 / P2-3：与 sumo_seed 非负语义一致）
            aseeds = t.get("assignment_seeds", [])
            aseeds = tuple(_coerce_int(a, "assignment_seeds") for a in aseeds)
            if any(a < 0 for a in aseeds):
                raise ValueError(f"assignment_seeds must be non-negative in treatment vehN={vn}")
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
            f"experiment config missing fields for {data.get('grid_mode', '?')!r} mode: {', '.join(missing)}"
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


def _coerce_int(value: Any, key: str) -> int:
    """严格整数强制（审阅 P1-3）：接受 int、整数值 float、整数字符串。

    拒绝小数、非有限值与数字型 bool——不再静默 ``int()`` 截断（10.9 → 10）。
    """
    if isinstance(value, bool):
        raise ValueError(f"{key}: must be an integer, got boolean {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or value != int(value):
            raise ValueError(f"{key}: must be an integer, got {value!r}")
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        try:
            dec = Decimal(stripped)
        except Exception:
            raise ValueError(f"{key}: must be an integer, got {value!r}") from None
        # 审阅 P2-2：Decimal("Infinity") 的 to_integral_value() == 自身，需显式有限性检查，
        # 否则 int(dec) 抛 OverflowError（入口只捕获 ValueError → traceback）。
        if not dec.is_finite() or dec != dec.to_integral_value():
            raise ValueError(f"{key}: must be an integer, got {value!r}")
        return int(dec)
    raise ValueError(f"{key}: must be an integer, got {value!r}")


def _parse_bool(data: dict[str, Any], key: str, default: bool) -> bool:
    """类型化布尔解析：接受 JSON bool 及字符串 "true"/"false"（P0-5）。

    修复 bool("false") == True 的字符串解析缺陷：配置中写 "false" 必须解析为 False。
    审阅 P1-3：数字型值（0/1/2 等）不再被 ``bool()`` 静默强转，直接拒绝。
    """
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
        raise ValueError(f"{key}: invalid boolean string {value!r}")
    raise ValueError(f"{key}: must be a boolean, got {value!r}")


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
