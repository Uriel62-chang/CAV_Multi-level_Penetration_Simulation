"""v0.4.1 stage2 type-map 校验测试"""

import json

import pytest

from scripts.parsing.runner import load_and_validate_type_map
from scripts.run_spec import PIPELINE_V4_2, RunSpec, build_run_id


def _make_spec(cav_count=5, vehicle_count=10):
    return RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=cav_count / vehicle_count,
        vehicle_count=vehicle_count,
        seed=1,
        run_id=build_run_id(
            "scenario_0",
            "IDM",
            vehicle_count=vehicle_count,
            cav_count=cav_count,
            assignment_seed=1,
            sumo_seed=101,
        ),
        pipeline_version=PIPELINE_V4_2,
        schema_version="2",
        sumo_seed=101,
        cav_count=cav_count,
        requested_pcav=None,
    )


def _write_type_map(tmp_path, data):
    p = tmp_path / "vehicle_type_map.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


def test_valid_type_map(tmp_path):
    spec = _make_spec(cav_count=5, vehicle_count=10)
    tm = {f"veh{i}": ("CAV" if i < 5 else "HV") for i in range(10)}
    result = load_and_validate_type_map(_write_type_map(tmp_path, tm), spec)
    assert result == tm


def test_missing_file(tmp_path):
    spec = _make_spec()
    with pytest.raises(FileNotFoundError, match="missing"):
        load_and_validate_type_map(tmp_path, spec)


def test_not_dict(tmp_path):
    spec = _make_spec()
    _write_type_map(tmp_path, [1, 2, 3])
    with pytest.raises(ValueError, match="top-level must be dict"):
        load_and_validate_type_map(tmp_path, spec)


def test_invalid_json(tmp_path):
    spec = _make_spec()
    (tmp_path / "vehicle_type_map.json").write_text("{not json}", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_and_validate_type_map(tmp_path, spec)


def test_wrong_count(tmp_path):
    spec = _make_spec(vehicle_count=10)
    tm = {f"veh{i}": "HV" for i in range(5)}
    with pytest.raises(ValueError, match="entries"):
        load_and_validate_type_map(_write_type_map(tmp_path, tm), spec)


def test_missing_keys(tmp_path):
    spec = _make_spec(cav_count=3, vehicle_count=10)
    tm = {f"veh{i}": ("CAV" if i < 3 else "HV") for i in range(10) if i != 5}
    tm["veh_extra"] = "HV"
    with pytest.raises(ValueError, match="missing keys"):
        load_and_validate_type_map(_write_type_map(tmp_path, tm), spec)


def test_extra_keys(tmp_path):
    spec = _make_spec(cav_count=5, vehicle_count=10)
    tm = {f"veh{i}": ("CAV" if i < 5 else "HV") for i in range(10)}
    tm["veh10"] = "HV"
    with pytest.raises(ValueError, match="entries"):
        load_and_validate_type_map(_write_type_map(tmp_path, tm), spec)


def test_invalid_type(tmp_path):
    spec = _make_spec(cav_count=5, vehicle_count=10)
    tm = {f"veh{i}": ("CAV" if i < 5 else "HV") for i in range(10)}
    tm["veh7"] = "INVALID"
    with pytest.raises(ValueError, match="unknown type"):
        load_and_validate_type_map(_write_type_map(tmp_path, tm), spec)


def test_cav_count_mismatch(tmp_path):
    spec = _make_spec(cav_count=5, vehicle_count=10)
    tm = {f"veh{i}": ("CAV" if i < 3 else "HV") for i in range(10)}
    with pytest.raises(ValueError, match="CAV count"):
        load_and_validate_type_map(_write_type_map(tmp_path, tm), spec)


def test_all_cav(tmp_path):
    spec = _make_spec(cav_count=10, vehicle_count=10)
    tm = {f"veh{i}": "CAV" for i in range(10)}
    result = load_and_validate_type_map(_write_type_map(tmp_path, tm), spec)
    assert result == tm


def test_all_hv(tmp_path):
    spec = _make_spec(cav_count=0, vehicle_count=10)
    tm = {f"veh{i}": "HV" for i in range(10)}
    result = load_and_validate_type_map(_write_type_map(tmp_path, tm), spec)
    assert result == tm
