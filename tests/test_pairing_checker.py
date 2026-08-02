"""P1-3（审阅）回归：main/Safety 配对静态验收 checker。"""

import json

from scripts.results.pairing_checker import _normalize_sumo_command, check_pairing


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


def test_pairing_match(tmp_path):
    main = tmp_path / "main"
    safety = tmp_path / "safety"
    main.mkdir()
    safety.mkdir()
    key = ("scenario_0", "IDM", 30, 6, 1, 101)
    _write_run(main, key, "a" * 64)
    _write_run(safety, key, "a" * 64, cmd_extra=("DRAC",))
    report = check_pairing(main, safety)
    assert report["shared_keys"] == 1
    assert report["all_match"] is True


def test_pairing_mismatch_sha(tmp_path):
    main = tmp_path / "main"
    safety = tmp_path / "safety"
    main.mkdir()
    safety.mkdir()
    key = ("scenario_0", "IDM", 30, 6, 1, 101)
    _write_run(main, key, "a" * 64)
    _write_run(safety, key, "b" * 64)
    report = check_pairing(main, safety)
    assert report["all_match"] is False
    assert any(m["field"] == "route_file_sha256" for m in report["mismatches"])


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


def test_pairing_requires_same_seed_pair(tmp_path):
    """routes/type-map 随 seed 变化：不同 seed pair 不配对。"""
    main = tmp_path / "main"
    safety = tmp_path / "safety"
    main.mkdir()
    safety.mkdir()
    _write_run(main, ("scenario_0", "IDM", 30, 6, 1, 101), "a" * 64)
    _write_run(safety, ("scenario_0", "IDM", 30, 6, 1, 102), "a" * 64)
    report = check_pairing(main, safety)
    assert report["shared_keys"] == 0
    assert report["all_match"] is True
