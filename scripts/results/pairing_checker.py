"""main/Safety 配对静态验收 checker（P1-3 审阅；round-delta P1 fail-closed 收紧）。

设计要求（docs/development/v0.4.2-split-design.md §配对）：逐共享键比较
main 与 Safety 实验的 network / routes / additional / vehicle-type-map SHA，
并比较剔除 SSM 参数后的 SUMO 命令。从 raw run 目录的 run_spec.json 与
simulation_status.json 读取，不触碰证据文件。

fail-closed（round-delta P1）：Safety 预期键集从实验 manifest（resolved_config）
推导并强制 collected == expected；Safety 键必须 ⊆ main 键；shared == safety ==
expected；缺文件、非法 SHA、空命令、重复键均判失败——空目录/零共享键不得
再返回成功。

用法（dry gate）：
    python3 -m scripts.results.pairing_checker \
      --main-root raw_v0.4.2/main --safety-root raw_v0.4.2/safety \
      --safety-manifest raw_v0.4.2/safety/manifest.json
返回 all_match=true 且无收集错误时退出码 0，否则 1。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 逐共享键比较的输入 SHA 字段（simulation_status.json 顶层）
_PAIRED_SHA_FIELDS = (
    "network_xml_sha256",
    "route_file_sha256",
    "additional_file_sha256",
    "vehicle_type_map_sha256",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _run_key(spec_dict: dict) -> tuple:
    """共享键：scenario × model × vehN × cav_count × assignment_seed × sumo_seed。

    routes/vehicle-type-map 内容随 assignment seed 变化，必须按同 seed pair
    配对（safety 固定 as01_ss101，与 main 同键同 seed 的 run 比较）。
    """
    return (
        str(spec_dict["scenario"]),
        str(spec_dict["model"]),
        int(spec_dict["vehicle_count"]),
        int(spec_dict["cav_count"]),
        int(spec_dict.get("seed", spec_dict.get("assignment_seed", -1))),
        int(spec_dict.get("sumo_seed", -1)),
    )


def _normalize_sumo_command(cmd: list, root: Path) -> list:
    """剔除 --device.ssm* 参数及其全部值 token；run 目录路径替换为 <run>。

    SSM 参数值个数不定（如 --device.ssm.measures TTC DRAC），值区持续到下一个
    '--' 开头的参数。输出路径（-r/-a/--*-output 等）含各自 run 目录，须归一。
    """
    out: list = []
    root_str = str(root)
    i = 0
    while i < len(cmd):
        token = cmd[i]
        if token.startswith("--device.ssm"):
            i += 1
            while i < len(cmd) and not cmd[i].startswith("--"):
                i += 1
            continue
        if token.startswith(root_str):
            out.append("<run>")
            i += 1
            continue
        out.append(token)
        i += 1
    return out


def _expected_safety_keys(manifest: dict) -> set:
    """从 Safety 实验 manifest（resolved_config）推导预期共享键集合。

    端点（cav=0/vehN）assignment_seed 为失活 sentinel 0（与 aggregate
    _expected_seed_pairs 同一展开逻辑）。
    """
    from scripts.results.aggregate import _expected_seed_pairs

    cfg = manifest.get("resolved_config") or manifest
    keys: set = set()
    for scenario in cfg.get("scenarios", []):
        for model in cfg.get("models", []):
            for treatment in cfg.get("treatments", []):
                vn = int(treatment["vehicle_count"])
                for cav in treatment.get("cav_counts", []):
                    # cav=0（HV-only）端点：_build_cav_count_specs 把 model 占位为
                    # "IDM"（run_id 用 HVONLY），与 Safety 实际 run 的 spec 一致。
                    eff_model = "IDM" if int(cav) == 0 else str(model)
                    for a, s in _expected_seed_pairs(manifest, vn, int(cav)):
                        keys.add((str(scenario), eff_model, vn, int(cav), a, s))
    return keys


def _collect_runs(root: Path) -> tuple[dict, list[str]]:
    """收集 run（严格模式）：缺文件/非法 SHA/空命令/重复键均记录错误，不静默跳过。"""
    runs: dict = {}
    errors: list[str] = []
    for rd in sorted(p for p in root.iterdir() if p.is_dir()):
        label = rd.name
        try:
            spec = json.loads((rd / "run_spec.json").read_text(encoding="utf-8"))
            status = json.loads((rd / "simulation_status.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            errors.append(f"{label}: unreadable run_spec/status ({exc})")
            continue
        key = _run_key(spec)
        if key in runs:
            errors.append(f"{label}: duplicate key {key}")
            continue
        entry: dict = {}
        for field in _PAIRED_SHA_FIELDS:
            value = status.get(field)
            if not isinstance(value, str) or not _SHA256_RE.match(value):
                errors.append(f"{label}: {field} invalid or missing ({value!r})")
            entry[field] = value
        cmd = status.get("sumo_command") or []
        if not isinstance(cmd, list) or not cmd:
            errors.append(f"{label}: sumo_command missing or empty")
        entry["normalized_sumo_command"] = _normalize_sumo_command(cmd, root)
        runs[key] = entry
    return runs, errors


def check_pairing(main_root: Path, safety_root: Path, safety_manifest: dict | None = None) -> dict:
    """比较 main/Safety 共享键 run 的输入 SHA 与非 SSM SUMO 命令（fail-closed）。"""
    if safety_manifest is None:
        raise ValueError("check_pairing requires safety experiment manifest")
    main_runs, main_errors = _collect_runs(main_root)
    safety_runs, safety_errors = _collect_runs(safety_root)
    expected_safety_keys = _expected_safety_keys(safety_manifest)

    safety_keys = set(safety_runs)
    main_keys = set(main_runs)
    shared = sorted(safety_keys & main_keys)
    missing_safety = expected_safety_keys - safety_keys
    extra_safety = safety_keys - expected_safety_keys
    uncovered = safety_keys - main_keys
    expected_count = len(expected_safety_keys)

    mismatches: list[dict] = []
    for key in shared:
        m = main_runs[key]
        s = safety_runs[key]
        for field in _PAIRED_SHA_FIELDS + ("normalized_sumo_command",):
            if m[field] != s[field]:
                mismatches.append(
                    {
                        "key": list(key),
                        "field": field,
                        "main": m[field],
                        "safety": s[field],
                    }
                )

    closure_errors: list[str] = []
    if main_errors:
        closure_errors.extend(f"main: {e}" for e in main_errors)
    if safety_errors:
        closure_errors.extend(f"safety: {e}" for e in safety_errors)
    if missing_safety:
        closure_errors.append(
            f"safety keys missing from collected runs: {sorted(missing_safety)[:6]}"
        )
    if extra_safety:
        closure_errors.append(
            f"safety keys not in manifest expectation: {sorted(extra_safety)[:6]}"
        )
    if uncovered:
        closure_errors.append(f"safety keys not covered by main: {sorted(uncovered)[:6]}")
    if len(shared) != expected_count:
        closure_errors.append(
            f"shared_keys ({len(shared)}) != expected safety keys ({expected_count})"
        )

    return {
        "main_runs": len(main_runs),
        "safety_runs": len(safety_runs),
        "expected_safety_keys": expected_count,
        "shared_keys": len(shared),
        "all_match": not mismatches and not closure_errors,
        "closure_errors": closure_errors,
        "mismatches": mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="main/Safety 配对静态验收（fail-closed）")
    parser.add_argument("--main-root", required=True)
    parser.add_argument("--safety-root", required=True)
    parser.add_argument("--safety-manifest", required=True, help="Safety 实验 manifest.json")
    args = parser.parse_args()
    try:
        manifest = json.loads(Path(args.safety_manifest).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[PAIRING] FAIL: cannot read safety manifest: {exc}", file=sys.stderr)
        return 1
    report = check_pairing(Path(args.main_root), Path(args.safety_root), safety_manifest=manifest)
    print(json.dumps(report, indent=1, ensure_ascii=False))
    if report["all_match"]:
        print("[PAIRING] PASS: Safety 键完整覆盖、四类输入与非 SSM 命令全部一致")
        return 0
    print("[PAIRING] FAIL: 存在不一致或闭合错误", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
