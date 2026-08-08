import json
import re
from pathlib import Path

import pytest

from scripts.run_spec import RunSpec, load_run_spec, write_run_spec
from scripts.simulation.flow_generator import generate_flow
from scripts.simulation.single_run import build_sumo_command, prepare_run


def _spec(**overrides) -> RunSpec:
    values = {
        "scenario": "scenario_0",
        "model": "IDM",
        "pcav": 0.5,
        "vehicle_count": 10,
        "seed": 7,
        "run_id": "stable-id",
        "simulation_end": 37.0,
        "warmup": 5.0,
        "step_length": 0.1,
        "detector_frequency": 5,
        "edge_data_frequency": 5,
        "loops": 2,
        "network_file": "net/scenario_0/loop.net.xml",
    }
    values.update(overrides)
    return RunSpec(**values)


def _vehicle_types(path: Path) -> list[str]:
    return re.findall(r'<vehicle .*? type="([^"]+)"', path.read_text())


def test_run_spec_round_trip_and_stable_hash(tmp_path):
    spec = _spec()
    digest = write_run_spec(spec, tmp_path)

    assert load_run_spec(tmp_path, digest) == spec
    assert digest == spec.sha256()


def test_run_spec_tampering_is_rejected(tmp_path):
    spec = _spec()
    digest = write_run_spec(spec, tmp_path)
    path = tmp_path / "run_spec.json"
    data = json.loads(path.read_text())
    data["warmup"] = 6.0
    path.write_text(json.dumps(data))

    try:
        load_run_spec(tmp_path, digest)
    except ValueError as exc:
        assert "SHA-256 mismatch" in str(exc)
    else:
        raise AssertionError("tampered run_spec.json was accepted")


def test_prepare_persists_non_default_frequencies(tmp_path):
    spec = _spec()
    prepared = prepare_run(spec, tmp_path, spec.network_file)
    additional = prepared.additional_path.read_text()

    # 纯净分支：schema=2 subgroup 附加（detector all/HV/CAV + edgeData all/HV/CAV）
    assert additional.count('freq="5"') == 9
    assert load_run_spec(tmp_path) == spec


def test_prepare_rejects_detector_window_misalignment(tmp_path):
    spec = _spec(detector_frequency=7)
    with pytest.raises(ValueError, match="detector_frequency"):
        prepare_run(spec, tmp_path, spec.network_file)


def test_seed_only_controls_vehicle_type_assignment(tmp_path):
    same_a = tmp_path / "same_a.xml"
    same_b = tmp_path / "same_b.xml"
    other = tmp_path / "other.xml"
    args = (10, 0.5, 2)

    generate_flow(*args, 7, str(same_a), cav_count=5)
    generate_flow(*args, 7, str(same_b), cav_count=5)
    generate_flow(*args, 8, str(other), cav_count=5)

    assert _vehicle_types(same_a) == _vehicle_types(same_b)
    assert _vehicle_types(same_a) != _vehicle_types(other)


def test_flow_generator_cli_passes_cav_count(monkeypatch):
    """R16-P2-1 回归：CLI 必须显式传入 cav_count（否则 generate_flow 抛
    ValueError）——未给 --cav-count 时按 half-up 推导（int(vehN*pCAV+0.5)，
    与 single_run 一致；round 银行家舍入会给 0.35*30→10，half-up 给 11）。"""
    from scripts.simulation import flow_generator

    captured = {}

    def _spy(*args, **kwargs):
        captured.update(kwargs)
        return {"veh0": "HV"}

    monkeypatch.setattr(flow_generator, "generate_flow", _spy)
    monkeypatch.setattr(
        "sys.argv",
        ["flow_generator", "--vehN", "30", "--pCAV", "0.35"],
    )
    flow_generator.main()
    assert captured["cav_count"] == 11  # half-up：int(30*0.35+0.5)=11


def test_run_spec_legacy_construction_no_requested_fallback():
    """R16-P2-2 回归：旧式 pcav-only 构造（不传 cav_count）→ cav_count 按
    round 推导（兼容），requested_pcav 保持 None——已删除永假回退分支；
    显式 count 网格构造行为不变（v0.4.1 语义）。"""
    legacy = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=7,
        run_id="legacy-id",
        simulation_end=37.0,
        warmup=5.0,
        step_length=0.1,
        detector_frequency=5,
        edge_data_frequency=5,
        loops=2,
        network_file="net/scenario_0/loop.net.xml",
    )
    assert legacy.cav_count == 5  # round 推导（兼容）
    assert legacy.requested_pcav is None  # 不回退（死分支已删）
    # 显式 count 模式：requested_pcav 显式传值仍保留
    explicit = _spec(cav_count=5, requested_pcav=0.5)
    assert explicit.requested_pcav == 0.5


def test_seed_is_not_passed_to_sumo(tmp_path):
    spec = _spec()
    prepared = prepare_run(spec, tmp_path, spec.network_file)
    command = build_sumo_command(prepared, spec.network_file, spec)

    # v0.4.2：--seed 显式传 spec.sumo_seed（独立随机流）；--random 不得出现
    idx = command.index("--seed")
    assert command[idx + 1] == str(spec.sumo_seed)
    assert "--random" not in command
