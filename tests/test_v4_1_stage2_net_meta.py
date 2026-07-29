"""v0.4.1 stage2 net.json num_lanes validation tests"""

import json

import pytest

from scripts.provenance import sha256_file
from scripts.run_spec import PIPELINE_V4_1, RunSpec, is_simulation_complete
from scripts.simulation.batch_run import _missing_required_outputs


def _make_spec(cav_count=5, vehicle_count=10, net_file="net/scenario_0/loop.net.xml"):
    return RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=cav_count / vehicle_count,
        vehicle_count=vehicle_count,
        seed=1,
        run_id="test-net-meta",
        pipeline_version=PIPELINE_V4_1,
        schema_version="2",
        sumo_seed=101,
        cav_count=cav_count,
        requested_pcav=None,
        network_file=net_file,
    )


def _setup_run_dir(tmp_path, spec, net_json_content):
    rd = tmp_path / "run"
    rd.mkdir()
    fake_net = tmp_path / "scenario_0" / "loop.net.xml"
    fake_net.parent.mkdir(parents=True, exist_ok=True)
    fake_net.write_text("<root/>")

    meta_file = fake_net.parent / "net.json"
    if isinstance(net_json_content, str):
        meta_file.write_text(net_json_content, encoding="utf-8")
    else:
        meta_file.write_text(json.dumps(net_json_content), encoding="utf-8")

    spec = RunSpec(
        scenario=spec.scenario,
        model=spec.model,
        pcav=spec.pcav,
        vehicle_count=spec.vehicle_count,
        seed=spec.seed,
        run_id=spec.run_id,
        pipeline_version=spec.pipeline_version,
        schema_version=spec.schema_version,
        sumo_seed=spec.sumo_seed,
        cav_count=spec.cav_count,
        requested_pcav=spec.requested_pcav,
        network_file=str(fake_net),
    )
    for f in [
        "routes.rou.xml",
        "ssm.xml",
        "lanechange.xml",
        "performance.xml",
        "emissions.xml",
        "vehroute.xml",
    ]:
        (rd / f).write_text("<root/>")
    (rd / "vehicle_type_map.json").write_text(
        json.dumps(
            {f"veh{i}": ("CAV" if i < spec.cav_count else "HV") for i in range(spec.vehicle_count)}
        )
    )
    status = {
        "run_id": spec.run_id,
        "pipeline_version": PIPELINE_V4_1,
        "status": "SUCCESS",
        "return_code": 0,
        "run_spec_sha256": spec.sha256(),
        "schema_version": spec.schema_version,
        "config_sha256": "",
        "network_sha256": "",
        "experiment_id": "",
        "sumo_seed": spec.sumo_seed,
        "route_file_sha256": sha256_file(str(rd / "routes.rou.xml")),
        "vehicle_type_map_sha256": sha256_file(str(rd / "vehicle_type_map.json")),
    }
    (rd / "simulation_status.json").write_text(json.dumps(status))
    (rd / "run_spec.json").write_text(json.dumps(spec.to_dict()))
    return rd, spec


_SUBGROUP_FILES = (
    "performance_HV.xml",
    "performance_CAV.xml",
    "emissions_HV.xml",
    "emissions_CAV.xml",
)
_DETECTOR_FILES = (
    "detector_lane0.xml",
    "detector_lane0_HV.xml",
    "detector_lane0_CAV.xml",
)


def _write_all_files(rd):
    for fname in _SUBGROUP_FILES + _DETECTOR_FILES:
        (rd / fname).write_text("<root/>")


def _write_subgroup_only(rd):
    for fname in _SUBGROUP_FILES:
        (rd / fname).write_text("<root/>")


class TestNetMetaResume:
    def test_net_json_list_root(self, tmp_path):
        spec = _make_spec()
        rd, spec = _setup_run_dir(tmp_path, spec, "[]")
        _write_all_files(rd)
        assert is_simulation_complete(spec, rd, PIPELINE_V4_1) is False

    def test_net_json_nan_num_lanes(self, tmp_path):
        spec = _make_spec()
        rd, spec = _setup_run_dir(tmp_path, spec, {"num_lanes": float("nan")})
        _write_all_files(rd)
        assert is_simulation_complete(spec, rd, PIPELINE_V4_1) is False

    def test_net_json_float_num_lanes(self, tmp_path):
        spec = _make_spec()
        rd, spec = _setup_run_dir(tmp_path, spec, {"num_lanes": 1.5})
        _write_all_files(rd)
        assert is_simulation_complete(spec, rd, PIPELINE_V4_1) is False

    def test_net_json_valid_num_lanes(self, tmp_path):
        spec = _make_spec()
        rd, spec = _setup_run_dir(tmp_path, spec, {"num_lanes": 1, "edge_ids": ["e0"]})
        _write_all_files(rd)
        assert is_simulation_complete(spec, rd, PIPELINE_V4_1) is True


class TestNetMetaMissingOutputs:
    def test_list_root_raises(self, tmp_path):
        spec = _make_spec()
        rd, spec = _setup_run_dir(tmp_path, spec, "[]")
        with pytest.raises(ValueError, match="object"):
            _missing_required_outputs(rd, spec)

    def test_nan_num_lanes_raises(self, tmp_path):
        spec = _make_spec()
        rd, spec = _setup_run_dir(tmp_path, spec, {"num_lanes": float("nan")})
        with pytest.raises(ValueError, match="num_lanes"):
            _missing_required_outputs(rd, spec)

    def test_float_num_lanes_raises(self, tmp_path):
        spec = _make_spec()
        rd, spec = _setup_run_dir(tmp_path, spec, {"num_lanes": 1.5})
        with pytest.raises(ValueError, match="num_lanes"):
            _missing_required_outputs(rd, spec)
