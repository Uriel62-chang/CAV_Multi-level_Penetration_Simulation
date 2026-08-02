"""旧 raw 输入完整性 sidecar 与解析前置校验（P1-4 新审阅；P1 round-3 收紧）。

新 run：simulation_status.json 的 ``raw_output_sha256`` 覆盖全部解析输入（含
stderr.log，names 见 ``raw_output_expected_names``），runner 直接校验 fail-closed。

旧 run（3,972 个正式 v0.4.2 run）：simulation_status.json 的 raw_output_sha256
**不含** stderr.log（生成时代码未记录）。不允许事后回填 status 伪装成仿真时
证据；重解析前由本模块生成独立的 ``input_integrity.sidecar.json``
（purpose="pre-reparse input integrity freeze"），记录全部解析输入 SHA 与
自锚 anchor_sha256。runner 仅在显式存在该 sidecar 时放行迁移路径，否则
fail-closed。

round-3（P1-1）：校验 exact expected set——raw_output_sha256 / sidecar files
的键集合必须与按 spec 推导的预期输入集合**完全相等**（缺失/多余均 fail），
并核验 status 顶层 route/type-map/additional/network/net.json 哈希。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.provenance import canonical_json_bytes, sha256_file

SIDECAR_NAME = "input_integrity.sidecar.json"
PURPOSE = "pre-reparse input integrity freeze"


def _read_net_meta(spec) -> dict:
    import json as _json

    net_meta_path = Path(spec.network_file).with_name("net.json")
    try:
        with open(net_meta_path, encoding="utf-8") as f:
            meta = _json.load(f)
        return meta if isinstance(meta, dict) else {}
    except (OSError, ValueError):
        return {}


def _num_lanes(spec) -> int:
    raw = _read_net_meta(spec).get("num_lanes")
    return int(raw) if type(raw) is int and raw >= 1 else 1


def raw_output_expected_names(spec) -> list[str]:
    """simulation_status.raw_output_sha256 的预期键集（与 batch_run 共享单源）。

    覆盖 SUMO 输出（performance/emissions/lanechange/vehroute 全量 + HV/CAV 子群、
    stderr.log、ssm（safety）、fcd（启用）、detector（按 net.json num_lanes））。
    routes.rou.xml / additional.add.xml / vehicle_type_map.json / network / net.json
    不在其中——它们在 status 顶层以 route_file_sha256 等单独记录。
    """
    names = [
        "performance.xml",
        "emissions.xml",
        "lanechange.xml",
        "vehroute.xml",
        "performance_HV.xml",
        "performance_CAV.xml",
        "emissions_HV.xml",
        "emissions_CAV.xml",
        "stderr.log",
    ]
    if getattr(spec, "ssm_enabled", False):
        names.append("ssm.xml")
    if spec.fcd_profile is not None:
        names.append("fcd.xml.gz")
    for lane_idx in range(_num_lanes(spec)):
        names.extend(
            [
                f"detector_lane{lane_idx}.xml",
                f"detector_lane{lane_idx}_HV.xml",
                f"detector_lane{lane_idx}_CAV.xml",
            ]
        )
    return names


def _parser_input_names(spec) -> list[str]:
    """sidecar 记录的解析输入：raw 输出 + 顶层输入（routes/additional/type-map）。"""
    names = raw_output_expected_names(spec) + [
        "routes.rou.xml",
        "additional.add.xml",
        "vehicle_type_map.json",
    ]
    return names


# status 顶层哈希键 → 相对/绝对文件解析
_TOP_LEVEL_HASH_FIELDS = [
    ("route_file_sha256", "routes.rou.xml"),
    ("vehicle_type_map_sha256", "vehicle_type_map.json"),
    ("additional_file_sha256", "additional.add.xml"),
]


def build_sidecar(run_dir: Path, spec) -> dict:
    """构造 sidecar 内容（不写盘）。files 记录全部解析输入 + simulation_status.json。"""
    files: dict[str, str] = {}
    for name in _parser_input_names(spec):
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
    """解析前置校验（fail-closed）。

    - v0.4.2 必须存在 raw_output_sha256（或缺 stderr 时的迁移 sidecar）；
    - raw_output_sha256 键集与预期集合完全相等（缺失/多余均 fail）；
    - status 顶层 route/type-map/additional/network/net.json 哈希核验；
    - sidecar（迁移路径）files 键集与预期集合完全相等 + 逐文件哈希比对。
    """
    errors: list[str] = []
    status_path = run_dir / "simulation_status.json"
    if not status_path.exists():
        return True, []
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, ["simulation_status.json unreadable for input integrity check"]

    if getattr(spec, "pipeline_version", "") != "v0.4.2":
        return True, []  # 非 v0.4.2 旧格式：无 raw 哈希契约

    raw_hashes = status.get("raw_output_sha256")
    if not isinstance(raw_hashes, dict):
        errors.append("v0.4.2 run missing raw_output_sha256 in simulation_status")
        return False, errors

    expected_raw = set(raw_output_expected_names(spec))
    actual_raw = set(raw_hashes.keys())
    # round-3（P1-1）：exact expected set——旧 run 的 stderr 由 sidecar 补，允许缺失；
    # 其余键必须完全相等（缺失/多余均 fail）。
    if "stderr.log" in actual_raw:
        expected = expected_raw
        stderr_via_sidecar = False
    else:
        expected = expected_raw - {"stderr.log"}
        stderr_via_sidecar = True
    missing = expected - actual_raw
    extra = actual_raw - expected
    if missing or extra:
        errors.append(
            "raw_output_sha256 key set mismatch: "
            f"missing={sorted(missing)} extra={sorted(extra)}"
        )

    # 1) status 已覆盖的解析输入逐文件哈希
    for name, expected_sha in raw_hashes.items():
        p = run_dir / name
        if not p.exists():
            errors.append(f"raw input missing: {name}")
        elif sha256_file(p) != expected_sha:
            errors.append(f"raw input hash mismatch: {name}")

    # 2) status 顶层输入哈希核验（route/type-map/additional/network/net.json）
    for field, rel_name in _TOP_LEVEL_HASH_FIELDS:
        expected_sha = status.get(field)
        p = run_dir / rel_name
        if not expected_sha:
            errors.append(f"v0.4.2 run missing top-level hash {field} in simulation_status")
        elif not p.exists():
            errors.append(f"top-level input missing: {rel_name}")
        elif sha256_file(p) != expected_sha:
            errors.append(f"top-level input hash mismatch: {rel_name}")
    network_file = Path(spec.network_file)
    net_meta_path = network_file.with_name("net.json")
    for field, p in (
        ("network_xml_sha256", network_file),
        ("net_json_sha256", net_meta_path),
    ):
        expected_sha = status.get(field)
        if not expected_sha:
            errors.append(f"v0.4.2 run missing top-level hash {field} in simulation_status")
        elif not p.exists():
            errors.append(f"top-level input missing: {p}")
        elif field == "network_xml_sha256":
            # 本地 net 为生成物，字节含 netconvert 时间戳/输出路径漂移（已披露的已知
            # 状态，P1-2 以 net_semantic_sha256 为主门禁，runner 加载 artifact 时校验）；
            # 此处仅核验记录存在与 SHA-256 格式，不做字节比对。
            if len(expected_sha) != 64 or any(c not in "0123456789abcdef" for c in expected_sha):
                errors.append(f"top-level hash invalid format: {field}")
        elif sha256_file(p) != expected_sha:
            errors.append(f"top-level input hash mismatch: {p}")

    # 3) stderr.log：status 未覆盖 → 要求迁移 sidecar（不回填 status）。
    if stderr_via_sidecar:
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
                # round-3（P1-1）：sidecar 键集必须与预期集合完全相等
                expected_sidecar = set(_parser_input_names(spec)) | {"simulation_status.json"}
                actual_sidecar = set(files.keys())
                missing_sc = expected_sidecar - actual_sidecar
                extra_sc = actual_sidecar - expected_sidecar
                if missing_sc or extra_sc:
                    errors.append(
                        "input integrity sidecar key set mismatch: "
                        f"missing={sorted(missing_sc)} extra={sorted(extra_sc)}"
                    )
                for name, expected_sha in files.items():
                    p = run_dir / name
                    if not p.exists():
                        errors.append(f"sidecar input missing: {name}")
                    elif sha256_file(p) != expected_sha:
                        errors.append(f"sidecar input hash mismatch: {name}")
    return not errors, errors
