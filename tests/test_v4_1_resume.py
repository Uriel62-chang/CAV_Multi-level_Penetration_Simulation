"""v0.4.1 resume 回归测试"""

import json

from scripts.provenance import sha256_file
from scripts.run_spec import PIPELINE_V4_1, RunSpec, is_simulation_complete


def _make_v4_1_run(tmp_path):
    """创建最小 v0.4.1 完整 run 目录。"""
    rd = tmp_path / "run"
    rd.mkdir()
    spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="resume-test",
        pipeline_version=PIPELINE_V4_1,
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
    )
    # 必需文件
    for f in [
        "routes.rou.xml",
        "ssm.xml",
        "lanechange.xml",
        "performance.xml",
        "emissions.xml",
        "vehroute.xml",
        "vehicle_type_map.json",
    ]:
        (rd / f).write_text("<root/>")
    route_hash = sha256_file(str(rd / "routes.rou.xml"))
    type_map_hash = sha256_file(str(rd / "vehicle_type_map.json"))
    status = {
        "run_id": spec.run_id,
        "pipeline_version": PIPELINE_V4_1,
        "status": "SUCCESS",
        "return_code": 0,
        "run_spec_sha256": spec.sha256(),
        "schema_version": spec.schema_version,
        "config_sha256": spec.config_sha256,
        "network_sha256": spec.network_sha256,
        "experiment_id": spec.experiment_id,
        "sumo_seed": spec.sumo_seed,
        "route_file_sha256": route_hash,
        "vehicle_type_map_sha256": type_map_hash,
    }
    (rd / "simulation_status.json").write_text(json.dumps(status))
    (rd / "run_spec.json").write_text(json.dumps(spec.to_dict()))
    return rd, spec


def test_resume_rejects_tampered_routes(tmp_path):
    rd, spec = _make_v4_1_run(tmp_path)
    assert is_simulation_complete(spec, rd, PIPELINE_V4_1)
    (rd / "routes.rou.xml").write_text("<tampered/>")
    assert not is_simulation_complete(spec, rd, PIPELINE_V4_1)


def test_resume_rejects_tampered_type_map(tmp_path):
    rd, spec = _make_v4_1_run(tmp_path)
    assert is_simulation_complete(spec, rd, PIPELINE_V4_1)
    (rd / "vehicle_type_map.json").write_text("{tampered}")
    assert not is_simulation_complete(spec, rd, PIPELINE_V4_1)


def test_resume_requires_routes_file(tmp_path):
    rd, spec = _make_v4_1_run(tmp_path)
    (rd / "routes.rou.xml").unlink()
    assert not is_simulation_complete(spec, rd, PIPELINE_V4_1)


def test_resume_requires_type_map_for_v4_1(tmp_path):
    rd, spec = _make_v4_1_run(tmp_path)
    (rd / "vehicle_type_map.json").unlink()
    assert not is_simulation_complete(spec, rd, PIPELINE_V4_1)


def test_resume_requires_route_hash_for_v4_1(tmp_path):
    rd, spec = _make_v4_1_run(tmp_path)
    st = json.loads((rd / "simulation_status.json").read_text())
    del st["route_file_sha256"]
    (rd / "simulation_status.json").write_text(json.dumps(st))
    assert not is_simulation_complete(spec, rd, PIPELINE_V4_1)
