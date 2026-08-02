"""旧 raw 输入完整性 sidecar 与解析前置校验（P1-4 新审阅）。

新 run：simulation_status.json 的 ``raw_output_sha256`` 覆盖全部解析输入（含
stderr.log，见 batch_run._collect_v4_2_raw_hashes），runner 直接校验 fail-closed。

旧 run（3,972 个正式 v0.4.2 run）：simulation_status.json 的 raw_output_sha256
**不含** stderr.log（生成时代码未记录）。不允许事后回填 status 伪装成仿真时
证据；重解析前由本模块生成独立的 ``input_integrity.sidecar.json``
（purpose="pre-reparse input integrity freeze"），记录全部解析输入 SHA 与
自锚 anchor_sha256。runner 仅在显式存在该 sidecar 时放行迁移路径，否则
fail-closed。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.provenance import canonical_json_bytes, sha256_file

SIDECAR_NAME = "input_integrity.sidecar.json"
PURPOSE = "pre-reparse input integrity freeze"


def _parser_input_names(run_dir: Path, spec) -> list[str]:
    """runner 解析时读取的全部输入文件名（相对 run_dir）。"""
    names = [
        "performance.xml",
        "performance_HV.xml",
        "performance_CAV.xml",
        "emissions.xml",
        "emissions_HV.xml",
        "emissions_CAV.xml",
        "vehroute.xml",
        "lanechange.xml",
        "stderr.log",
        "routes.rou.xml",
        "additional.add.xml",
        "vehicle_type_map.json",
    ]
    if getattr(spec, "ssm_enabled", False):
        names.append("ssm.xml")
    if spec.fcd_profile is not None:
        names.append("fcd.xml.gz")
    net_meta_path = Path(spec.network_file).with_name("net.json")
    num_lanes = 1
    try:
        with open(net_meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        nl = meta.get("num_lanes")
        if type(nl) is int and nl >= 1:
            num_lanes = nl
    except (OSError, ValueError):
        pass
    for lane_idx in range(num_lanes):
        names.extend(
            [
                f"detector_lane{lane_idx}.xml",
                f"detector_lane{lane_idx}_HV.xml",
                f"detector_lane{lane_idx}_CAV.xml",
            ]
        )
    return names


def build_sidecar(run_dir: Path, spec) -> dict:
    """构造 sidecar 内容（不写盘）。files 记录全部解析输入 + simulation_status.json。"""
    files: dict[str, str] = {}
    for name in _parser_input_names(run_dir, spec):
        p = run_dir / name
        if p.exists():
            files[name] = sha256_file(p)
    sim_status_path = run_dir / "simulation_status.json"
    if sim_status_path.exists():
        files["simulation_status.json"] = sha256_file(sim_status_path)
    payload = {
        "purpose": PURPOSE,
        "run_id": str(getattr(spec, "run_id", run_dir.name)),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    payload["anchor_sha256"] = hashlib.sha256(canonical_json_bytes(files)).hexdigest()
    return payload


def write_sidecar(run_dir: Path, spec) -> Path:
    sidecar_path = run_dir / SIDECAR_NAME
    payload = build_sidecar(run_dir, spec)
    sidecar_path.write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return sidecar_path


def verify(run_dir: Path, spec) -> tuple[bool, list[str]]:
    """解析前置校验：status 已哈希文件逐一比对；stderr.log 未被 status 覆盖时
    要求显式 sidecar（迁移路径）。返回 (ok, errors)。"""
    errors: list[str] = []
    status_path = run_dir / "simulation_status.json"
    if not status_path.exists():
        return True, []
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, ["simulation_status.json unreadable for input integrity check"]
    raw_hashes = status.get("raw_output_sha256")
    if not isinstance(raw_hashes, dict):
        # P1（第二轮）：v0.4.2 run 必须有 raw 哈希契约（或 sidecar 迁移路径），
        # 不得 fail-open 静默通过；非 v0.4.2 旧格式保持旧行为。
        if getattr(spec, "pipeline_version", "") == "v0.4.2":
            errors.append("v0.4.2 run missing raw_output_sha256 in simulation_status")
            return False, errors
        return True, []

    # 1) status 已覆盖的解析输入
    for name, expected in raw_hashes.items():
        p = run_dir / name
        if not p.exists():
            errors.append(f"raw input missing: {name}")
            continue
        if sha256_file(p) != expected:
            errors.append(f"raw input hash mismatch: {name}")

    # 2) stderr.log：status 未覆盖 → 要求迁移 sidecar（不回填 status）。
    #    P1（第二轮）：sidecar 记录的全部解析输入逐一核验（不只 stderr.log），
    #    修改 vehicle_type_map.json 等任何 sidecar 输入都必须被检出。
    if "stderr.log" not in raw_hashes:
        sidecar_path = run_dir / SIDECAR_NAME
        if not sidecar_path.exists():
            errors.append(
                "raw input stderr.log not hashed in simulation_status; migration "
                f"requires {SIDECAR_NAME} (purpose={PURPOSE!r})"
            )
        else:
            try:
                sc = json.loads(sidecar_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                errors.append("input integrity sidecar unreadable")
                sc = {}
            if sc.get("purpose") != PURPOSE:
                errors.append(f"input integrity sidecar purpose mismatch: {sc.get('purpose')!r}")
            files = sc.get("files")
            if not isinstance(files, dict):
                errors.append("input integrity sidecar missing files")
            else:
                anchor = sc.get("anchor_sha256")
                if anchor != hashlib.sha256(canonical_json_bytes(files)).hexdigest():
                    errors.append("input integrity sidecar anchor_sha256 mismatch")
                if "stderr.log" not in files:
                    errors.append("input integrity sidecar missing stderr.log")
                for name, expected in files.items():
                    p = run_dir / name
                    if not p.exists():
                        errors.append(f"sidecar input missing: {name}")
                    elif sha256_file(p) != expected:
                        errors.append(f"sidecar input hash mismatch: {name}")
    return not errors, errors
