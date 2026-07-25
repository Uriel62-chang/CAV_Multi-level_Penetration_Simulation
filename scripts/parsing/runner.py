"""阶段二：单 run 解析器 — 状态机 + 不变量校验。

parse_one_run(run_dir, pipeline_version)
  1. 读取 simulation_status.json 重建 RunSpec
  2. 写 parse_status.json (RUNNING)
  3. 调用 single_run.parse_run_outputs()
  4. 校验不变量
  5. 原子写 summary.json + parse_status.json
"""

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.provenance import sha256_file
from scripts.run_spec import atomic_write_json, load_run_spec
from scripts.simulation.single_run import parse_run_outputs

# ── 必须存在的原始文件 ──
_REQUIRED_FILES = [
    "performance.xml",
    "emissions.xml",
    "vehroute.xml",
    "lanechange.xml",
    "stderr.log",
]


def _find_ssm_file(run_dir: Path) -> Path | None:
    """SSM 兼容：compact 优先，fallback 原件"""
    for name in ("ssm_compact.xml", "ssm.xml"):
        p = run_dir / name
        if p.exists():
            return p
    return None


def _find_detector_files(run_dir: Path, num_lanes: int) -> list[str]:
    """返回存在的检测器文件路径列表"""
    paths = []
    for lane_index in range(num_lanes):
        p = run_dir / f"detector_lane{lane_index}.xml"
        if p.exists():
            paths.append(str(p))
    return paths


def _check_preconditions(run_dir: Path, pipeline_version: str) -> dict | None:
    """返回 None 表示可解析，否则返回错误状态的 parse_status dict"""
    status_path = run_dir / "simulation_status.json"

    if not status_path.exists():
        return {
            "status": "SIMULATION_NOT_SUCCESS",
            "error_message": "simulation_status.json not found",
        }

    try:
        sim_status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "SIMULATION_NOT_SUCCESS",
            "error_message": "simulation_status.json unreadable",
        }

    if sim_status.get("status") != "SUCCESS":
        return {
            "status": "SIMULATION_NOT_SUCCESS",
            "error_message": f"simulation status={sim_status.get('status')}",
        }

    if sim_status.get("return_code") != 0:
        return {
            "status": "SIMULATION_NOT_SUCCESS",
            "error_message": f"simulation return_code={sim_status.get('return_code')}",
        }

    if sim_status.get("pipeline_version") != pipeline_version:
        return {"status": "SIMULATION_NOT_SUCCESS", "error_message": "pipeline_version mismatch"}

    try:
        spec = load_run_spec(run_dir, expected_sha256=sim_status.get("run_spec_sha256"))
    except ValueError as exc:
        return {"status": "SIMULATION_NOT_SUCCESS", "error_message": str(exc)}
    if spec.pipeline_version != pipeline_version:
        return {
            "status": "SIMULATION_NOT_SUCCESS",
            "error_message": "run_spec pipeline_version mismatch",
        }
    for field in ("schema_version", "config_sha256", "network_sha256", "experiment_id"):
        if sim_status.get(field) != getattr(spec, field):
            return {"status": "SIMULATION_NOT_SUCCESS", "error_message": f"{field} mismatch"}

    # 必要文件检查
    for fname in _REQUIRED_FILES:
        if not (run_dir / fname).exists():
            return {"status": "SIMULATION_NOT_SUCCESS", "error_message": f"missing file: {fname}"}

    if _find_ssm_file(run_dir) is None:
        return {
            "status": "SIMULATION_NOT_SUCCESS",
            "error_message": "missing ssm.xml / ssm_compact.xml",
        }

    return None


def _validate_invariants(summary: dict) -> list[str]:
    """校验关键不变量，返回错误信息列表"""
    errors = []
    s = summary

    # SSM 台账
    raw = s.get("ssm_raw_record_count", 0)
    inv = s.get("ssm_invalid_record_count", 0)
    warm = s.get("ssm_warmup_filtered_count", 0)
    valid = s.get("ssm_valid_record_count", 0)
    mirrored = s.get("ssm_mirrored_record_count", 0)
    ttc = s.get("ttc_conflict_event_count", 0)
    drac = s.get("drac_conflict_event_count", 0)
    ttc_veh = s.get("ttc_affected_vehicle_count", 0)
    eb_veh = s.get("emergency_braking_affected_vehicle_count", 0)
    lc = s.get("lane_change_count", 0)
    unsafe_lc = s.get("unsafe_lc_gap_count", 0)
    veh_km = s.get("total_vehicle_km", float("nan"))
    laps = s.get("completed_lap_count", 0)

    if raw != inv + warm + valid:
        errors.append(f"SSM ledger: raw({raw}) != inv({inv}) + warm({warm}) + valid({valid})")
    if valid - mirrored >= 0 and valid - mirrored != valid - mirrored:
        pass  # NaN guard
    elif valid < mirrored:
        errors.append(f"SSM: valid({valid}) < mirrored({mirrored})")
    if ttc > valid:
        errors.append(f"TTC events({ttc}) > valid({valid})")
    if drac > valid:
        errors.append(f"DRAC events({drac}) > valid({valid})")
    if (
        isinstance(ttc_veh, (int, float))
        and not math.isnan(ttc_veh)
        and ttc_veh > s.get("vehN", 9999)
    ):
        errors.append(f"TTC affected({ttc_veh}) > vehN({s.get('vehN')})")
    if isinstance(eb_veh, (int, float)) and not math.isnan(eb_veh) and eb_veh > s.get("vehN", 9999):
        errors.append(f"EB affected({eb_veh}) > vehN({s.get('vehN')})")
    if isinstance(unsafe_lc, (int, float)) and not math.isnan(unsafe_lc) and unsafe_lc > lc:
        errors.append(f"unsafe LC({unsafe_lc}) > total LC({lc})")
    if isinstance(veh_km, (int, float)) and not math.isnan(veh_km) and veh_km <= 0:
        errors.append(f"total_vehicle_km({veh_km}) <= 0")
    if isinstance(laps, (int, float)) and not math.isnan(laps) and laps < 0:
        errors.append(f"completed_lap_count({laps}) < 0")

    return errors


def parse_one_run(run_dir: Path, pipeline_version: str, network_file: str = "") -> dict:
    """解析单个 run 目录，返回 parse_status dict。

    状态机：RUNNING → SUCCESS | FAILED | INVALID_DATA | SIMULATION_NOT_SUCCESS
    """
    run_dir = Path(run_dir)
    run_id = run_dir.name
    status_path = run_dir / "parse_status.json"
    summary_path = run_dir / "summary.json"
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()

    # ── 预检 ──
    skip_reason = _check_preconditions(run_dir, pipeline_version)
    if skip_reason:
        parse_status = {
            "run_id": run_id,
            "status": skip_reason["status"],
            "pipeline_version": pipeline_version,
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "wall_time_s": 0.0,
            "error_message": skip_reason["error_message"],
        }
        atomic_write_json(status_path, parse_status)
        return parse_status

    # ── 写 RUNNING ──
    atomic_write_json(
        status_path,
        {
            "run_id": run_id,
            "status": "RUNNING",
            "pipeline_version": pipeline_version,
            "started_at": started_at,
        },
    )

    try:
        # ── 只从 run_spec.json 重建 RunSpec；目录名仅作标识 ──
        sim_status = json.loads((run_dir / "simulation_status.json").read_text(encoding="utf-8"))
        spec = load_run_spec(run_dir, expected_sha256=sim_status["run_spec_sha256"])

        # ── 解析 ──
        net_file = network_file or spec.network_file
        summary = parse_run_outputs(run_dir, spec, net_file)

        # ── 不变量校验 ──
        errors = _validate_invariants(summary)

        wall_time = time.monotonic() - t0
        finished_at = datetime.now(timezone.utc).isoformat()

        if errors:
            summary["_invariant_errors"] = errors
            atomic_write_json(summary_path, summary)
            parse_status = {
                "run_id": run_id,
                "status": "INVALID_DATA",
                "pipeline_version": pipeline_version,
                "run_spec_sha256": spec.sha256(),
                "schema_version": spec.schema_version,
                "config_sha256": spec.config_sha256,
                "network_sha256": spec.network_sha256,
                "experiment_id": spec.experiment_id,
                "started_at": started_at,
                "finished_at": finished_at,
                "wall_time_s": wall_time,
                "error_message": "; ".join(errors),
                "summary_sha256": sha256_file(summary_path),
            }
        else:
            summary.pop("_invariant_errors", None)
            atomic_write_json(summary_path, summary)
            parse_status = {
                "run_id": run_id,
                "status": "SUCCESS",
                "pipeline_version": pipeline_version,
                "run_spec_sha256": spec.sha256(),
                "schema_version": spec.schema_version,
                "config_sha256": spec.config_sha256,
                "network_sha256": spec.network_sha256,
                "experiment_id": spec.experiment_id,
                "started_at": started_at,
                "finished_at": finished_at,
                "wall_time_s": wall_time,
                "error_message": None,
                "summary_sha256": sha256_file(summary_path),
            }

        atomic_write_json(status_path, parse_status)
        return parse_status

    except Exception as e:
        wall_time = time.monotonic() - t0
        parse_status = {
            "run_id": run_id,
            "status": "FAILED",
            "pipeline_version": pipeline_version,
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "wall_time_s": wall_time,
            "error_message": str(e),
        }
        atomic_write_json(status_path, parse_status)
        return parse_status
