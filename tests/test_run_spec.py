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

    assert additional.count('freq="5"') == 3
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

    generate_flow(*args, 7, str(same_a))
    generate_flow(*args, 7, str(same_b))
    generate_flow(*args, 8, str(other))

    assert _vehicle_types(same_a) == _vehicle_types(same_b)
    assert _vehicle_types(same_a) != _vehicle_types(other)


def test_seed_is_not_passed_to_sumo(tmp_path):
    spec = _spec()
    prepared = prepare_run(spec, tmp_path, spec.network_file)
    command = build_sumo_command(
        prepared,
        spec.network_file,
        sim_end_time=spec.simulation_end,
        step_length=spec.step_length,
    )

    assert "--seed" not in command
    assert "--random" not in command
