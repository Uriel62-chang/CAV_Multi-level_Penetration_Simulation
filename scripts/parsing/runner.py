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
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.provenance import sha256_file
from scripts.run_spec import PIPELINE_V4_2, atomic_write_json, load_run_spec
from scripts.schema import validate_summary_contract
from scripts.simulation.single_run import load_network_meta


def load_and_validate_type_map(run_dir, spec):
    path = Path(run_dir) / "vehicle_type_map.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing")

    raw = path.read_text(encoding="utf-8")
    try:
        type_map = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"vehicle_type_map.json: invalid JSON: {e}") from e
    if not isinstance(type_map, dict):
        raise ValueError("vehicle_type_map.json: top-level must be dict")

    vehicle_count = spec.vehicle_count
    if len(type_map) != vehicle_count:
        raise ValueError(f"type_map: {len(type_map)} entries, expected {vehicle_count}")

    cav_count = sum(1 for v in type_map.values() if v == "CAV")
    hv_count = vehicle_count - cav_count
    spec_cav = spec.cav_count or 0
    if cav_count != spec_cav:
        raise ValueError(f"type_map: CAV count {cav_count} != spec.cav_count {spec_cav}")
    if hv_count != spec.hv_count:
        raise ValueError(f"type_map: HV count {hv_count} != spec.hv_count {spec.hv_count}")

    for vid, vt in type_map.items():
        if vt not in ("HV", "CAV"):
            raise ValueError(f"type_map: vehicle {vid} has unknown type '{vt}'")

    expected_ids = {f"veh{i}" for i in range(vehicle_count)}
    actual_ids = set(type_map.keys())
    missing = expected_ids - actual_ids
    if missing:
        raise ValueError(f"type_map: missing keys {sorted(missing)}")
    extra = actual_ids - expected_ids
    if extra:
        raise ValueError(f"type_map: unexpected keys {sorted(extra)}")

    return type_map


def validate_fcd_leader_distance(spec, network_file):
    if spec.fcd_profile is None:
        return
    net_meta = load_network_meta(network_file)
    total_length_m = float(net_meta["total_length_m"])
    dist = spec.fcd_max_leader_distance_m
    if dist is None or dist < total_length_m:
        raise ValueError(
            f"fcd_max_leader_distance_m ({dist}) < loop total_length_m ({total_length_m})"
        )


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

    if getattr(spec, "pipeline_version", "") == "v0.4.2" and not spec.ssm_enabled:
        # v0.4.2 主 factorial：ssm.xml 意图性缺失，不得存在
        if _find_ssm_file(run_dir) is not None:
            return {
                "status": "SIMULATION_NOT_SUCCESS",
                "error_message": "unexpected ssm.xml for SSM-disabled main factorial",
            }
    elif _find_ssm_file(run_dir) is None:
        return {
            "status": "SIMULATION_NOT_SUCCESS",
            "error_message": "missing ssm.xml / ssm_compact.xml",
        }

    return None


def _validate_invariants(summary: dict) -> list[str]:
    """校验关键不变量，返回错误信息列表"""
    errors = []
    s = summary

    # SSM 台账（P0-1 新审阅：未采集时全部 NaN，跳过台账/极值检查）
    # P1-2（本轮审查）：SSM 解析失败（损坏/不可读 XML → parse_success=False）
    # 时同样跳过——0=0+0+0 的"伪零通过"不得掩盖解析失败（run 由 writer 按
    # ssm_parse_success 标 parser_warning 兜底，与 ssm_sensitivity fail-closed 对齐）。
    if s.get("ssm_not_collected") is not True and s.get("ssm_parse_success") is True:
        raw = s.get("ssm_raw_record_count", 0)
        inv = s.get("ssm_invalid_record_count", 0)
        warm = s.get("ssm_warmup_filtered_count", 0)
        valid = s.get("ssm_valid_record_count", 0)
        mirrored = s.get("ssm_mirrored_record_count", 0)
        ttc = s.get("ttc_conflict_event_count", 0)
        drac = s.get("drac_conflict_event_count", 0)
        ttc_veh = s.get("ttc_affected_vehicle_count", 0)

        if raw != inv + warm + valid:
            errors.append(f"SSM ledger: raw({raw}) != inv({inv}) + warm({warm}) + valid({valid})")
        # 审阅 P2-3：删除恒 False 的 NaN guard 死分支（valid/mirrored 为 int，不可能 NaN）
        if valid < mirrored:
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
    eb_veh = s.get("emergency_braking_affected_vehicle_count", 0)
    lc = s.get("lane_change_count", 0)
    unsafe_lc = s.get("unsafe_lc_gap_count", 0)
    veh_km = s.get("total_vehicle_km", float("nan"))
    laps = s.get("completed_lap_count", 0)

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
    subgroup_sha = None

    _max_rss_kb = 0
    _rss_stop = threading.Event()
    _rss_sampler = None

    def _rss_sample():
        nonlocal _max_rss_kb
        while not _rss_stop.is_set():
            try:
                with open("/proc/self/status") as _sf:
                    for _line in _sf:
                        if _line.startswith("VmRSS:"):
                            _val = int(_line.split()[1])
                            if _val > _max_rss_kb:
                                _max_rss_kb = _val
                            break
            except (OSError, ValueError, IndexError):
                pass
            _rss_stop.wait(0.01)

    # Capture initial baseline before starting thread
    try:
        with open("/proc/self/status") as _sf:
            for _line in _sf:
                if _line.startswith("VmRSS:"):
                    _max_rss_kb = int(_line.split()[1])
                    break
    except (OSError, ValueError, IndexError):
        pass

    _rss_sampler = threading.Thread(target=_rss_sample, daemon=True)
    _rss_sampler.start()

    # ── 预检 ──
    skip_reason = _check_preconditions(run_dir, pipeline_version)
    if skip_reason:
        _rss_stop.set()
        parse_status = {
            "run_id": run_id,
            "status": skip_reason["status"],
            "pipeline_version": pipeline_version,
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "wall_time_s": 0.0,
            "error_message": skip_reason["error_message"],
            "parse_peak_rss_kb": _max_rss_kb,
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

        # P1-4（新审阅）：解析前置 raw 输入完整性校验（v0.4.2，fail-closed）。
        # 新 run 校验 simulation_status.raw_output_sha256（含 stderr.log）；
        # 旧 run（status 未哈希 stderr.log）必须显式提供迁移 sidecar。
        if spec.pipeline_version == PIPELINE_V4_2:
            from scripts.parsing.input_integrity import verify as _verify_input_integrity

            _integrity_ok, _integrity_errors = _verify_input_integrity(run_dir, spec)
            if not _integrity_ok:
                raise ValueError("input integrity: " + "; ".join(_integrity_errors))

        # ── 解析（纯净分支：仅 schema=2，v0.4.2 单管线；schema=1 legacy 已移除）──
        net_file = network_file or spec.network_file
        core, subgroup, errors = _parse_one_run(run_dir, spec, net_file)
        summary = core
        import json as _json

        subgroup_path = run_dir / "subgroup_summary.jsonl"
        tmp = subgroup_path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as _f:
            for rec in subgroup:
                _f.write(_json.dumps(rec, ensure_ascii=False) + "\n")
            _f.flush()
            import os as _os

            _os.fsync(_f.fileno())
        import os as _os

        _os.replace(tmp, subgroup_path)
        subgroup_sha = sha256_file(subgroup_path)

        wall_time = time.monotonic() - t0
        finished_at = datetime.now(timezone.utc).isoformat()
        _rss_stop.set()
        if _rss_sampler is not None:
            _rss_sampler.join(timeout=1.0)

        contract_errors = validate_summary_contract(
            summary, spec.schema_version, pipeline_version=spec.pipeline_version
        )
        errors = contract_errors + errors
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
                "subgroup_summary_sha256": subgroup_sha,
                "parse_peak_rss_kb": _max_rss_kb,
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
                "subgroup_summary_sha256": subgroup_sha,
                "parse_peak_rss_kb": _max_rss_kb,
            }

        atomic_write_json(status_path, parse_status)
        return parse_status

    except Exception as e:
        _rss_stop.set()
        wall_time = time.monotonic() - t0
        parse_status = {
            "run_id": run_id,
            "status": "FAILED",
            "pipeline_version": pipeline_version,
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "wall_time_s": wall_time,
            "error_message": str(e),
            "parse_peak_rss_kb": _max_rss_kb,
        }
        atomic_write_json(status_path, parse_status)
        return parse_status


def _load_free_flow_references(spec, run_dir=None):
    import json as _json
    from pathlib import Path as _Path

    from scripts.provenance import net_semantic_sha256 as _net_semantic_sha256
    from scripts.provenance import sha256_file as _sha256_file

    net_meta = load_network_meta(spec.network_file)
    artifact_rel = net_meta.get("free_flow_reference_path")
    if artifact_rel:
        artifact_path = _Path(artifact_rel)
    else:
        artifact_path = _Path("artifacts/free_flow/v0.4.1-pilot-ff-1/free_flow_references.json")
    if not artifact_path.exists():
        raise FileNotFoundError(f"free-flow artifact not found: {artifact_path}")

    data = _json.loads(artifact_path.read_text(encoding="utf-8"))
    scenario_data = data.get("results", {}).get(spec.scenario, {})
    if not scenario_data:
        raise ValueError(f"scenario {spec.scenario} not in free-flow artifact")

    # P2-2（新审阅）：artifact 身份（reference_id / free_flow_version）必须自洽
    ref_id = data.get("reference_id", "")
    ff_version = data.get("free_flow_version", "")
    if not ref_id or not ff_version:
        raise ValueError("free-flow artifact missing reference_id/free_flow_version")
    if ref_id != f"ff-{ff_version}":
        raise ValueError(
            f"free-flow artifact reference_id ({ref_id!r}) inconsistent with "
            f"free_flow_version ({ff_version!r})"
        )

    # P1-2（新审阅）：以语义 SHA 为主兼容门禁（忽略生成时间戳/输出路径）；
    # 旧 artifact 无 semantic 字段时回退完整字节比较（历史审计路径）。
    artifact_semantic = scenario_data.get("net_semantic_sha256")
    if artifact_semantic:
        current_semantic = _net_semantic_sha256(spec.network_file)
        if artifact_semantic != current_semantic:
            raise ValueError(
                f"free-flow artifact net_semantic_sha256 ({artifact_semantic[:12]}...) "
                f"!= network semantic ({current_semantic[:12]}...)"
            )
    else:
        artifact_net_sha = scenario_data.get("net_sha256", "")
        current_net_sha = _sha256_file(spec.network_file)
        if artifact_net_sha != current_net_sha:
            raise ValueError(
                f"free-flow artifact net_sha256 ({artifact_net_sha[:12]}...) "
                f"!= network ({current_net_sha[:12]}...)"
            )

    import subprocess as _sp

    # P1-3（本轮）：优先使用仿真时持久化的实际 SUMO 版本（--sumo 自定义可执行
    # 文件可能与 PATH 不同）；无记录（旧 run）回退 PATH 查询。
    sumo_out: str | None = None
    if run_dir is not None:
        try:
            recorded = _json.loads(
                (_Path(run_dir) / "simulation_status.json").read_text(encoding="utf-8")
            ).get("sumo_version")
            if recorded:
                sumo_out = recorded
        except (OSError, _json.JSONDecodeError, AttributeError):
            pass
    if sumo_out is None:
        sumo_out = _sp.run(["sumo", "--version"], capture_output=True, text=True).stdout.strip()
    artifact_sumo = data.get("sumo_version", "")
    if artifact_sumo != sumo_out:
        raise ValueError(
            f"free-flow artifact sumo_version ({artifact_sumo!r}) != current ({sumo_out!r})"
        )

    refs = scenario_data.get("references", {})
    if "HV" not in refs:
        raise ValueError("free-flow artifact missing HV reference")
    hv_lap = refs["HV"]["lap_time_s"]
    import math as _m

    if (
        not isinstance(hv_lap, (int, float))
        or isinstance(hv_lap, bool)
        or _m.isnan(hv_lap)
        or _m.isinf(hv_lap)
        or hv_lap <= 0
    ):
        raise ValueError(f"free-flow artifact HV lap_time_s invalid: {hv_lap}")
    result = {"HV": hv_lap}
    key = f"CAV_{spec.model}"

    if key not in refs:
        if spec.model == "ACC":
            raise ValueError("ACC free-flow reference not available; add to artifact first")
        raise ValueError(f"model {spec.model} not in free-flow artifact")
    model_lap = refs[key]["lap_time_s"]
    if (
        not isinstance(model_lap, (int, float))
        or isinstance(model_lap, bool)
        or _m.isnan(model_lap)
        or _m.isinf(model_lap)
        or model_lap <= 0
    ):
        raise ValueError(f"free-flow artifact {key} lap_time_s invalid: {model_lap}")
    result[spec.model] = model_lap

    return result


def _parse_one_run(run_dir, spec, network_file):
    from scripts.parsing.detector import parse_detector_subgroup
    from scripts.parsing.edge_emissions import parse_edge_emissions
    from scripts.parsing.edge_performance import parse_edge_performance
    from scripts.parsing.lanechange import parse_lanechange_subgroup
    from scripts.parsing.metrics import (
        SubgroupPrimitives,
        compute_core_summary,
        compute_subgroup_records,
        validate_subgroup_invariants,
    )
    from scripts.parsing.ssm import parse_ssm_subgroup
    from scripts.parsing.stderr import parse_emergency_braking_subgroup
    from scripts.parsing.vehroute import parse_lap_times_subgroup

    type_map = load_and_validate_type_map(run_dir, spec)

    net_meta_raw = load_network_meta(network_file or spec.network_file)
    num_lanes = max(net_meta_raw.get("num_lanes", 1), 1)

    free_flow_refs = _load_free_flow_references(spec, run_dir=run_dir)

    warmup = spec.warmup

    # Detector
    det_all = [str(run_dir / f"detector_lane{lane_idx}.xml") for lane_idx in range(num_lanes)]
    det_HV = [str(run_dir / f"detector_lane{lane_idx}_HV.xml") for lane_idx in range(num_lanes)]
    det_CAV = [str(run_dir / f"detector_lane{lane_idx}_CAV.xml") for lane_idx in range(num_lanes)]
    detector = parse_detector_subgroup(
        det_all, det_HV, det_CAV, warmup, simulation_end=spec.simulation_end
    )

    # Edge performance / emissions
    edge_perf = {}
    edge_emis = {}
    for suffix, label in [("", "all"), ("_HV", "HV"), ("_CAV", "CAV")]:
        perf_path = run_dir / f"performance{suffix}.xml"
        emis_path = run_dir / f"emissions{suffix}.xml"
        edge_perf[label] = parse_edge_performance(
            str(perf_path), warmup, simulation_end=spec.simulation_end
        )
        edge_emis[label] = parse_edge_emissions(
            str(emis_path), warmup, simulation_end=spec.simulation_end
        )

    # SSM：v0.4.2 主 factorial 为意图性缺失（ssm_enabled=False），不解析。
    # P0-1（新审阅）：未采集 ≠ 零事件 —— 全部 SSM 计数/极值置 NaN（"未采集"语义），
    # 不得伪装为零检出；safety 的合法零检出仍为数值 0（见 parse_ssm_subgroup）。
    if getattr(spec, "pipeline_version", "") == "v0.4.2" and not spec.ssm_enabled:
        _ssm_nan = float("nan")
        ssm = {
            "all": {
                "ssm_raw_record_count": _ssm_nan,
                "ssm_invalid_record_count": _ssm_nan,
                "ssm_warmup_filtered_count": _ssm_nan,
                "ssm_valid_record_count": _ssm_nan,
                "ssm_mirrored_record_count": _ssm_nan,
                "ssm_fragment_merged_count": _ssm_nan,
                "ttc_conflict_event_count": _ssm_nan,
                "min_ttc_s": _ssm_nan,
                "ttc_involved_vehicle_count": _ssm_nan,
                "drac_conflict_event_count": _ssm_nan,
                "max_drac_mps2": _ssm_nan,
                "parse_success": True,
                "ssm_not_collected": True,
            },
            "pair_HV_HV": {"ttc_event_count": _ssm_nan, "drac_event_count": _ssm_nan},
            "pair_HV_CAV": {"ttc_event_count": _ssm_nan, "drac_event_count": _ssm_nan},
            "pair_CAV_CAV": {"ttc_event_count": _ssm_nan, "drac_event_count": _ssm_nan},
            "role_f_HV_l_HV": {"ttc_event_count": _ssm_nan, "drac_event_count": _ssm_nan},
            "role_f_HV_l_CAV": {"ttc_event_count": _ssm_nan, "drac_event_count": _ssm_nan},
            "role_f_CAV_l_HV": {"ttc_event_count": _ssm_nan, "drac_event_count": _ssm_nan},
            "role_f_CAV_l_CAV": {"ttc_event_count": _ssm_nan, "drac_event_count": _ssm_nan},
            "unclassified": {"ttc_event_count": _ssm_nan, "drac_event_count": _ssm_nan},
        }
    else:
        ssm_file = run_dir / "ssm_compact.xml"
        if not ssm_file.exists():
            ssm_file = run_dir / "ssm.xml"
        # P0-5：v0.4.2 从 spec 读取 analysis 配置（单源；v0.4.1 旧 merge_gap 推导已移除）
        merge_gap = spec.ssm_fragment_merge_gap_s
        ttc_th = spec.analysis_ttc_threshold_s
        drac_th = spec.analysis_drac_threshold_mps2
        overlap = spec.ssm_mirror_overlap_ratio
        dedup = spec.ssm_dedup_method
        ssm = parse_ssm_subgroup(
            str(ssm_file),
            type_map,
            warmup,
            ttc_threshold=ttc_th,
            drac_threshold=drac_th,
            fragment_merge_gap_s=merge_gap,
            simulation_end=spec.simulation_end,
            mirror_overlap_ratio=overlap,
            dedup_method=dedup,
        )

    # Lanechange
    lc_path = run_dir / "lanechange.xml"
    lc = (
        parse_lanechange_subgroup(
            str(lc_path), type_map, warmup, simulation_end=spec.simulation_end
        )
        if lc_path.exists()
        else {
            "all": {
                "lane_change_count": 0,
                "unsafe_lc_gap_count": 0,
                "unsafe_lc_gap_ratio": float("nan"),
                "parse_success": False,
            },
            "HV": {
                "lane_change_count": 0,
                "unsafe_lc_gap_count": 0,
                "unsafe_lc_gap_ratio": float("nan"),
                "parse_success": False,
            },
            "CAV": {
                "lane_change_count": 0,
                "unsafe_lc_gap_count": 0,
                "unsafe_lc_gap_ratio": float("nan"),
                "parse_success": False,
            },
        }
    )

    # Vehroute
    edges_per_lap = net_meta_raw.get("num_sides", 4)
    vr = parse_lap_times_subgroup(
        str(run_dir / "vehroute.xml"), type_map, edges_per_lap, warmup, spec.simulation_end
    )

    # Emergency braking
    stderr_path = run_dir / "stderr.log"
    stderr_text = (
        stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
    )
    eb = parse_emergency_braking_subgroup(
        stderr_text, type_map, warmup, simulation_end=spec.simulation_end
    )

    # FCD
    if spec.fcd_profile is not None:
        from scripts.parsing.fcd import parse_fcd

        fcd_path = run_dir / "fcd.xml.gz"
        if fcd_path.exists():
            fcd = parse_fcd(str(fcd_path), type_map, warmup, simulation_end=spec.simulation_end)
        else:
            fcd = {
                "all": {"parse_success": False},
                "HV": {"parse_success": False},
                "CAV": {"parse_success": False},
            }
    else:
        fcd = None

    primitives = SubgroupPrimitives(
        detector=detector,
        ssm=ssm,
        lanechange=lc,
        edge_perf=edge_perf,
        edge_emis=edge_emis,
        vehroute=vr,
        emerg_brake=eb,
        fcd=fcd,
    )

    core = compute_core_summary(primitives, spec, free_flow_refs)
    subgroup = compute_subgroup_records(primitives, spec, free_flow_refs)

    errors = _validate_invariants(core) + validate_subgroup_invariants(primitives)

    return core, subgroup, errors
