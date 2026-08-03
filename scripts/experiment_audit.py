"""只读实验网格审计：渗透率离散化与车辆类型排列信息量。"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.experiment_config import (
    GRID_MODE_CAV_COUNT,
    ExperimentConfig,
    _coerce_int,
    load_experiment_config,
)


@dataclass(frozen=True)
class VehicleCountAudit:
    vehicle_count: int
    requested_level_count: int
    realized_composition_count: int
    mismatched_level_count: int
    duplicate_treatment_level_count: int
    max_absolute_pcav_error: float


@dataclass(frozen=True)
class ExperimentAudit:
    planned_run_count: int
    requested_realized_mismatch_runs: int
    duplicate_penetration_treatment_runs: int
    endpoint_run_count: int
    endpoint_unique_assignment_treatments: int
    endpoint_assignment_redundant_runs: int
    by_vehicle_count: tuple[VehicleCountAudit, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def audit_experiment_config(config: ExperimentConfig) -> ExperimentAudit:
    """量化正式网格中的 pCAV 离散化和端点 assignment-seed 冗余。

    requested_pcav 模式：按 pcav_levels × vehicle_counts 的离散化误差审计。
    cav_count 模式：treatments 直接指定精确 cav_counts（无 requested/realized
    离散化误差，mismatch 恒 0）；planned run 数与端点冗余按
    batch_run._build_cav_count_specs 的展开口径计算（P2 本轮审查修复：
    旧实现仅支持 requested_pcav，cav_count 模式输出全零误导）。
    """
    if config.grid_mode == GRID_MODE_CAV_COUNT:
        return _audit_cav_count_grid(config)

    scenario_model_seed_multiplier = len(config.scenarios) * len(config.models) * len(config.seeds)
    by_vehicle_count = []
    mismatch_cells = 0
    duplicate_cells = 0

    for vehicle_count in config.vehicle_counts:
        realized_counts = []
        mismatched_levels = 0
        max_error = 0.0
        for requested_pcav in config.pcav_levels:
            cav_count = round(vehicle_count * requested_pcav)
            realized_pcav = cav_count / vehicle_count
            realized_counts.append(cav_count)
            error = abs(realized_pcav - requested_pcav)
            if error > 1e-12:
                mismatched_levels += 1
            max_error = max(max_error, error)

        realized_compositions = len(set(realized_counts))
        duplicate_levels = len(realized_counts) - realized_compositions
        mismatch_cells += mismatched_levels
        duplicate_cells += duplicate_levels
        by_vehicle_count.append(
            VehicleCountAudit(
                vehicle_count=vehicle_count,
                requested_level_count=len(config.pcav_levels),
                realized_composition_count=realized_compositions,
                mismatched_level_count=mismatched_levels,
                duplicate_treatment_level_count=duplicate_levels,
                max_absolute_pcav_error=max_error,
            )
        )

    planned_run_count = (
        len(config.scenarios)
        * len(config.models)
        * len(config.pcav_levels)
        * len(config.vehicle_counts)
        * len(config.seeds)
    )
    endpoint_count = sum(level in {0.0, 1.0} for level in config.pcav_levels)
    endpoint_unique = (
        len(config.scenarios) * len(config.models) * len(config.vehicle_counts) * endpoint_count
    )
    endpoint_runs = endpoint_unique * len(config.seeds)

    return ExperimentAudit(
        planned_run_count=planned_run_count,
        requested_realized_mismatch_runs=mismatch_cells * scenario_model_seed_multiplier,
        duplicate_penetration_treatment_runs=duplicate_cells * scenario_model_seed_multiplier,
        endpoint_run_count=endpoint_runs,
        endpoint_unique_assignment_treatments=endpoint_unique,
        endpoint_assignment_redundant_runs=endpoint_runs - endpoint_unique,
        by_vehicle_count=tuple(by_vehicle_count),
    )


def _default_assignment_seeds(cav_count: int, vehicle_count: int) -> list[int]:
    """cav_count 模式下无显式 assignment_seeds 时的默认值（与 batch_run 口径一致）。"""
    if cav_count == 0 or cav_count == vehicle_count:
        return [1]  # 不可区分，仅需一个
    return [1, 2, 3]


def _audit_cav_count_grid(config: ExperimentConfig) -> ExperimentAudit:
    """cav_count 模式审计：treatments 为唯一事实源。"""
    by_vehicle_count = []
    duplicate_cells = 0
    duplicate_runs = 0
    endpoint_model_cells = 0  # 端点 (cav=0 | cav=vn) 单元格 × 生效模型数
    planned_run_count = 0

    for t in config.treatments:
        vn = _coerce_int(t.get("vehicle_count", 0), "vehicle_count")
        cav_counts = [_coerce_int(c, "cav_counts") for c in t["cav_counts"]]
        unique_count = len(set(cav_counts))
        dup = len(cav_counts) - unique_count
        duplicate_cells += dup
        by_vehicle_count.append(
            VehicleCountAudit(
                vehicle_count=vn,
                requested_level_count=len(cav_counts),
                realized_composition_count=unique_count,
                mismatched_level_count=0,  # cav_count 精确指定，无离散化误差
                duplicate_treatment_level_count=dup,
                max_absolute_pcav_error=0.0,
            )
        )

        seen: set[int] = set()
        for cav_count in cav_counts:
            # 与 batch_run._build_cav_count_specs 展开口径一致：
            # cav=0 时模型维度失活（1 个）；端点 assignment_seed 截断为 1
            n_models = 1 if cav_count == 0 else len(config.models)
            aseeds_raw = t.get("assignment_seeds", [])
            aseeds = (
                [_coerce_int(a, "assignment_seeds") for a in aseeds_raw]
                if aseeds_raw
                else _default_assignment_seeds(cav_count, vn)
            )
            if cav_count == 0 or cav_count == vn:
                aseeds = aseeds[:1]
            planned_run_count += n_models * len(aseeds) * len(config.sumo_seeds)
            if cav_count in seen:
                duplicate_runs += n_models * len(aseeds) * len(config.sumo_seeds)
            seen.add(cav_count)
            if cav_count == 0 or cav_count == vn:
                endpoint_model_cells += n_models

    endpoint_unique = len(config.scenarios) * endpoint_model_cells
    endpoint_runs = endpoint_unique * len(config.sumo_seeds)

    return ExperimentAudit(
        planned_run_count=planned_run_count,
        requested_realized_mismatch_runs=0,
        duplicate_penetration_treatment_runs=duplicate_runs * len(config.scenarios),
        endpoint_run_count=endpoint_runs,
        endpoint_unique_assignment_treatments=endpoint_unique,
        endpoint_assignment_redundant_runs=endpoint_runs - endpoint_unique,
        by_vehicle_count=tuple(by_vehicle_count),
    )


def _format_text(audit: ExperimentAudit) -> str:
    lines = [
        f"planned runs: {audit.planned_run_count:,}",
        (f"requested != realized pCAV: {audit.requested_realized_mismatch_runs:,} runs"),
        (f"duplicate penetration treatments: {audit.duplicate_penetration_treatment_runs:,} runs"),
        (
            "endpoint assignment-seed redundancy: "
            f"{audit.endpoint_assignment_redundant_runs:,} / "
            f"{audit.endpoint_run_count:,} runs"
        ),
        "",
        "vehN  requested  realized  mismatch  duplicate  max_error",
    ]
    for item in audit.by_vehicle_count:
        lines.append(
            f"{item.vehicle_count:>4}  "
            f"{item.requested_level_count:>9}  "
            f"{item.realized_composition_count:>8}  "
            f"{item.mismatched_level_count:>8}  "
            f"{item.duplicate_treatment_level_count:>9}  "
            f"{item.max_absolute_pcav_error:>9.6f}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit requested/realized pCAV and assignment-seed redundancy"
    )
    parser.add_argument("--config", default="configs/v0.4.0.json")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args()

    audit = audit_experiment_config(load_experiment_config(Path(args.config)))
    if args.json:
        print(json.dumps(audit.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(_format_text(audit))


if __name__ == "__main__":
    main()
