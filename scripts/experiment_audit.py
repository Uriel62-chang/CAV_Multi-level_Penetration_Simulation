"""只读实验网格审计：渗透率离散化与车辆类型排列信息量。"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.experiment_config import ExperimentConfig, load_experiment_config


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
    """量化正式网格中的 pCAV 离散化和端点 assignment-seed 冗余。"""
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
