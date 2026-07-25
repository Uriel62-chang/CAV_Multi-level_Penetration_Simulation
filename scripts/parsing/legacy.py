"""显式处理缺少 RunSpec 的历史 v0.4.0 raw 数据。

该入口不属于当前可复现 schema，结果始终标记为 legacy_unverified。
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.provenance import sha256_file
from scripts.run_spec import RunSpec, atomic_write_json
from scripts.simulation.single_run import parse_run_outputs

LEGACY_PIPELINE_VERSION = "legacy-v0.4.0-unverified"
LEGACY_SCHEMA_VERSION = "legacy"
LEGACY_QUALITY = "legacy_unverified"

_RUN_ID_PATTERN = re.compile(
    r"^s(?P<scenario>\d+)_(?P<model>IDM|ACC|CACC)_"
    r"p(?P<pcav>\d{3})_v(?P<vehicles>\d{3})_seed(?P<seed>-?\d+)$"
)


def legacy_spec_from_run_id(
    run_id: str,
    *,
    simulation_end: float,
    warmup: float,
    step_length: float,
    detector_frequency: int,
    edge_data_frequency: int,
    loops: int,
    network_file: str | None = None,
) -> RunSpec:
    """从旧目录名和显式假设构建带有不可验证标记的 RunSpec。"""
    match = _RUN_ID_PATTERN.fullmatch(run_id)
    if match is None:
        raise ValueError(f"unsupported legacy run_id: {run_id}")
    scenario = f"scenario_{match.group('scenario')}"
    resolved_network = network_file or f"net/{scenario}/loop.net.xml"
    return RunSpec(
        scenario=scenario,
        model=match.group("model"),
        pcav=int(match.group("pcav")) / 100,
        vehicle_count=int(match.group("vehicles")),
        seed=int(match.group("seed")),
        run_id=run_id,
        simulation_end=simulation_end,
        warmup=warmup,
        step_length=step_length,
        detector_frequency=detector_frequency,
        edge_data_frequency=edge_data_frequency,
        loops=loops,
        network_file=resolved_network,
        pipeline_version=LEGACY_PIPELINE_VERSION,
        schema_version=LEGACY_SCHEMA_VERSION,
        experiment_id=LEGACY_QUALITY,
    )


def parse_legacy_run(
    run_dir: Path,
    *,
    simulation_end: float = 3600,
    warmup: float = 600,
    step_length: float = 0.1,
    detector_frequency: int = 120,
    edge_data_frequency: int = 300,
    loops: int = 300,
    network_file: str | None = None,
) -> dict:
    """解析历史 raw 文件并写入带明显质量标记的独立结果。"""
    run_dir = Path(run_dir)
    started_at = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    status_path = run_dir / "legacy_parse_status.json"
    summary_path = run_dir / "legacy_summary.json"
    try:
        spec = legacy_spec_from_run_id(
            run_dir.name,
            simulation_end=simulation_end,
            warmup=warmup,
            step_length=step_length,
            detector_frequency=detector_frequency,
            edge_data_frequency=edge_data_frequency,
            loops=loops,
            network_file=network_file,
        )
        summary = parse_run_outputs(run_dir, spec, spec.network_file)
        summary["_legacy_quality"] = LEGACY_QUALITY
        summary["_legacy_assumptions"] = {
            "simulation_end": simulation_end,
            "warmup": warmup,
            "step_length": step_length,
            "detector_frequency": detector_frequency,
            "edge_data_frequency": edge_data_frequency,
            "loops": loops,
            "network_file": spec.network_file,
        }
        atomic_write_json(summary_path, summary)
        status = {
            "run_id": run_dir.name,
            "status": "LEGACY_SUCCESS",
            "quality": LEGACY_QUALITY,
            "pipeline_version": LEGACY_PIPELINE_VERSION,
            "schema_version": LEGACY_SCHEMA_VERSION,
            "summary_sha256": sha256_file(summary_path),
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "wall_time_s": time.monotonic() - start,
            "error_message": None,
        }
    except Exception as exc:
        status = {
            "run_id": run_dir.name,
            "status": "LEGACY_FAILED",
            "quality": LEGACY_QUALITY,
            "pipeline_version": LEGACY_PIPELINE_VERSION,
            "schema_version": LEGACY_SCHEMA_VERSION,
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "wall_time_s": time.monotonic() - start,
            "error_message": str(exc) or type(exc).__name__,
        }
    atomic_write_json(status_path, status)
    return status
