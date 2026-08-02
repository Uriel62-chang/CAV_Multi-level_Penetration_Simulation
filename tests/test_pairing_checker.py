"""P1-3（审阅）回归：main/Safety 配对静态验收 checker（fail-closed）。"""

import json

import pytest

from scripts.results.pairing_checker import (
    _normalize_sumo_command,
    check_pairing,
)


def _write_run(root, key, sha_val, cmd_extra=()):
    rd = root / f"run_{key[0]}_{key[1]}_{key[2]}_{key[3]}_{key[4]}_{key[5]}"
    rd.mkdir()
    spec = {
        "scenario": key[0],
        "model": key[1],
        "vehicle_count": key[2],
        "cav_count": key[3],
        "seed": key[4],
        "sumo_seed": key[5],
    }
    (rd / "run_spec.json").write_text(json.dumps(spec), encoding="utf-8")
    status = {
        "network_xml_sha256": sha_val,
        "route_file_sha256": sha_val,
        "additional_file_sha256": sha_val,
        "vehicle_type_map_sha256": sha_val,
        "sumo_command": [
            "sumo",
            "-n",
            str(rd / "loop.net.xml"),
            "-r",
            str(rd / "routes.rou.xml"),
            "--seed",
            str(key[5]),
            "--device.ssm.measures",
            "TTC",
            *cmd_extra,
        ],
    }
    (rd / "simulation_status.json").write_text(json.dumps(status), encoding="utf-8")


def _safety_manifest(keys):
    scenarios = sorted({k[0] for k in keys})
    models = sorted({k[1] for k in keys})
    vns = sorted({k[2] for k in keys})
    treatments = [
        {
            "vehicle_count": vn,
            "cav_counts": sorted({k[3] for k in keys if k[2] == vn}),
            "assignment_seeds": [1],
        }
        for vn in vns
    ]
    return {
        "experiment_role": "safety",
        "scenarios": scenarios,
        "models": models,
        "treatments": treatments,
        "sumo_seeds": sorted({k[5] for k in keys}),
    }


def test_pairing_match(tmp_path):
    main = tmp_path / "main"
    safety = tmp_path / "safety"
    main.mkdir()
    safety.mkdir()
    key = ("scenario_0", "IDM", 30, 6, 1, 101)
    _write_run(main, key, "a" * 64)
    _write_run(safety, key, "a" * 64, cmd_extra=("DRAC",))
    report = check_pairing(main, safety, _safety_manifest([key]))
    assert report["expected_safety_keys"] == 1
    assert report["shared_keys"] == 1
    assert report["all_match"] is True, report


def test_pairing_mismatch_sha(tmp_path):
    main = tmp_path / "main"
    safety = tmp_path / "safety"
    main.mkdir()
    safety.mkdir()
    key = ("scenario_0", "IDM", 30, 6, 1, 101)
    _write_run(main, key, "a" * 64)
    _write_run(safety, key, "b" * 64)
    report = check_pairing(main, safety, _safety_manifest([key]))
    assert report["all_match"] is False
    assert any(m["field"] == "route_file_sha256" for m in report["mismatches"])


def test_pairing_zero_shared_fails(tmp_path):
    """Safety 键不在 main 中（零共享）→ fail-closed，不得返回成功。"""
    main = tmp_path / "main"
    safety = tmp_path / "safety"
    main.mkdir()
    safety.mkdir()
    _write_run(main, ("scenario_0", "IDM", 30, 6, 1, 102), "a" * 64)
    key_s = ("scenario_0", "IDM", 30, 6, 1, 101)
    _write_run(safety, key_s, "a" * 64)
    report = check_pairing(main, safety, _safety_manifest([key_s]))
    assert report["shared_keys"] == 0
    assert report["all_match"] is False
    assert any("not covered by main" in e for e in report["closure_errors"])


def test_pairing_empty_safety_fails(tmp_path):
    """Safety 目录为空（collected < expected）→ fail-closed。"""
    main = tmp_path / "main"
    safety = tmp_path / "safety"
    main.mkdir()
    safety.mkdir()
    key = ("scenario_0", "IDM", 30, 6, 1, 101)
    _write_run(main, key, "a" * 64)
    report = check_pairing(main, safety, _safety_manifest([key]))
    assert report["all_match"] is False
    assert any("missing from collected" in e for e in report["closure_errors"])


def test_pairing_missing_manifest_raises(tmp_path):
    main = tmp_path / "main"
    safety = tmp_path / "safety"
    main.mkdir()
    safety.mkdir()
    with pytest.raises(ValueError, match="safety experiment manifest"):
        check_pairing(main, safety)


def test_pairing_duplicate_key_fails(tmp_path):
    """同一键两个 run → 收集错误 → fail-closed。"""
    main = tmp_path / "main"
    safety = tmp_path / "safety"
    main.mkdir()
    safety.mkdir()
    key = ("scenario_0", "IDM", 30, 6, 1, 101)
    _write_run(main, key, "a" * 64)
    # 第二个同键 run（不同目录名）
    rd = main / "dup"
    rd.mkdir()
    spec = {
        "scenario": key[0],
        "model": key[1],
        "vehicle_count": key[2],
        "cav_count": key[3],
        "seed": key[4],
        "sumo_seed": key[5],
    }
    (rd / "run_spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (rd / "simulation_status.json").write_text(
        json.dumps(
            {
                "network_xml_sha256": "a" * 64,
                "route_file_sha256": "a" * 64,
                "additional_file_sha256": "a" * 64,
                "vehicle_type_map_sha256": "a" * 64,
                "sumo_command": ["sumo", "-n", "x"],
            }
        ),
        encoding="utf-8",
    )
    _write_run(safety, key, "a" * 64)
    report = check_pairing(main, safety, _safety_manifest([key]))
    assert report["all_match"] is False
    assert any("duplicate key" in e for e in report["closure_errors"])


def test_pairing_invalid_sha_fails(tmp_path):
    """非法 SHA → 收集错误 → fail-closed。"""
    main = tmp_path / "main"
    safety = tmp_path / "safety"
    main.mkdir()
    safety.mkdir()
    key = ("scenario_0", "IDM", 30, 6, 1, 101)
    _write_run(main, key, "a" * 64)
    rd = safety / "bad"
    rd.mkdir()
    spec = {
        "scenario": key[0],
        "model": key[1],
        "vehicle_count": key[2],
        "cav_count": key[3],
        "seed": key[4],
        "sumo_seed": key[5],
    }
    (rd / "run_spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (rd / "simulation_status.json").write_text(
        json.dumps(
            {
                "network_xml_sha256": "not-a-sha",
                "route_file_sha256": "a" * 64,
                "additional_file_sha256": "a" * 64,
                "vehicle_type_map_sha256": "a" * 64,
                "sumo_command": ["sumo", "-n", "x"],
            }
        ),
        encoding="utf-8",
    )
    report = check_pairing(main, safety, _safety_manifest([key]))
    assert report["all_match"] is False
    assert any("invalid or missing" in e for e in report["closure_errors"])


def test_normalize_strips_ssm_and_run_paths(tmp_path):
    cmd = [
        "sumo",
        "-n",
        "net/scenario_0/loop.net.xml",
        "-r",
        str(tmp_path / "run_x" / "routes.rou.xml"),
        "--device.ssm.measures",
        "TTC",
        "DRAC",
        "--device.ssm.thresholds",
        "3.0",
        "3.0",
        "--lanechange-output",
        str(tmp_path / "run_x" / "lc.xml"),
    ]
    normalized = _normalize_sumo_command(cmd, tmp_path)
    assert "--device.ssm" not in normalized
    assert "<run>" in normalized
    assert str(tmp_path) not in normalized


def test_pairing_empty_manifest_rejected(tmp_path):
    """空 {} manifest（无 experiment_role/字段）→ 拒绝，不得返回成功。"""
    main = tmp_path / "main"
    safety = tmp_path / "safety"
    main.mkdir()
    safety.mkdir()
    with pytest.raises(ValueError, match="experiment_role"):
        check_pairing(main, safety, {})
