"""main/Safety 配对静态验收 checker（P1-3 审阅）。

设计要求（docs/development/v0.4.2-split-design.md §配对）：逐共享键比较
main 与 Safety 实验的 network / routes / additional / vehicle-type-map SHA，
并比较剔除 SSM 参数后的 SUMO 命令。从 raw run 目录的 run_spec.json 与
simulation_status.json 读取，不触碰证据文件。

用法（dry gate）：
    python3 -m scripts.results.pairing_checker \
      --main-root raw_v0.4.2/main --safety-root raw_v0.4.2/safety
返回 all_match=true 时退出码 0，否则 1（可接入 release gate）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 逐共享键比较的输入 SHA 字段（simulation_status.json 顶层）
_PAIRED_SHA_FIELDS = (
    "network_xml_sha256",
    "route_file_sha256",
    "additional_file_sha256",
    "vehicle_type_map_sha256",
)


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


def _collect_runs(root: Path) -> dict:
    runs: dict = {}
    for rd in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            spec = json.loads((rd / "run_spec.json").read_text(encoding="utf-8"))
            status = json.loads((rd / "simulation_status.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, KeyError):
            continue
        runs[_run_key(spec)] = {field: status.get(field) for field in _PAIRED_SHA_FIELDS} | {
            "normalized_sumo_command": _normalize_sumo_command(
                status.get("sumo_command", []) or [], root
            )
        }
    return runs


def check_pairing(main_root: Path, safety_root: Path) -> dict:
    """比较 main/Safety 共享键 run 的输入 SHA 与非 SSM SUMO 命令。"""
    main_runs = _collect_runs(main_root)
    safety_runs = _collect_runs(safety_root)
    shared = sorted(set(main_runs) & set(safety_runs))
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
    return {
        "main_runs": len(main_runs),
        "safety_runs": len(safety_runs),
        "shared_keys": len(shared),
        "all_match": not mismatches,
        "mismatches": mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="main/Safety 配对静态验收")
    parser.add_argument("--main-root", required=True)
    parser.add_argument("--safety-root", required=True)
    args = parser.parse_args()
    report = check_pairing(Path(args.main_root), Path(args.safety_root))
    print(json.dumps(report, indent=1, ensure_ascii=False))
    if report["all_match"]:
        print("[PAIRING] PASS: 共享键输入与规范化命令全部一致")
        return 0
    print("[PAIRING] FAIL: 存在不一致", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
