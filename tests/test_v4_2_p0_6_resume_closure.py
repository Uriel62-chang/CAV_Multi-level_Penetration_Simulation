"""v0.4.2 P0-6 回归测试：resume 闭包（additional + network XML 实际重新哈希）。"""

import json

from scripts.provenance import sha256_file
from scripts.run_spec import PIPELINE_V4_2, RunSpec, is_simulation_complete


def _make_v4_2_run(tmp_path):
    """创建最小 v0.4.2 main-factorial（ssm_enabled=False）完整 run 目录。"""
    rd = tmp_path / "run"
    rd.mkdir()
    net_dir = tmp_path / "net"
    net_dir.mkdir()
    net_file = net_dir / "loop.net.xml"
    net_file.write_text("<net/>")
    (net_dir / "net.json").write_text(json.dumps({"num_lanes": 1}))
    spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="resume-v42-test",
        pipeline_version=PIPELINE_V4_2,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
        network_file=str(net_file),
        network_sha256=sha256_file(str(net_file)),
        ssm_enabled=False,
        fcd_profile=None,
    )
    for f in [
        "routes.rou.xml",
        "lanechange.xml",
        "performance.xml",
        "emissions.xml",
        "vehroute.xml",
        "performance_HV.xml",
        "performance_CAV.xml",
        "emissions_HV.xml",
        "emissions_CAV.xml",
        "additional.add.xml",
        "detector_lane0.xml",
        "detector_lane0_HV.xml",
        "detector_lane0_CAV.xml",
        "vehicle_type_map.json",
    ]:
        (rd / f).write_text("<root/>")
    status = {
        "run_id": spec.run_id,
        "pipeline_version": PIPELINE_V4_2,
        "status": "SUCCESS",
        "return_code": 0,
        "run_spec_sha256": spec.sha256(),
        "schema_version": spec.schema_version,
        "config_sha256": spec.config_sha256,
        "network_sha256": spec.network_sha256,
        "experiment_id": spec.experiment_id,
        "sumo_seed": spec.sumo_seed,
        "route_file_sha256": sha256_file(str(rd / "routes.rou.xml")),
        "vehicle_type_map_sha256": sha256_file(str(rd / "vehicle_type_map.json")),
        "additional_file_sha256": sha256_file(str(rd / "additional.add.xml")),
        "network_xml_sha256": spec.network_sha256,
        "net_json_sha256": sha256_file(str(net_dir / "net.json")),
        "raw_output_sha256": {
            name: sha256_file(str(rd / name))
            for name in (
                "performance.xml",
                "emissions.xml",
                "lanechange.xml",
                "vehroute.xml",
                "performance_HV.xml",
                "performance_CAV.xml",
                "emissions_HV.xml",
                "emissions_CAV.xml",
                "detector_lane0.xml",
                "detector_lane0_HV.xml",
                "detector_lane0_CAV.xml",
            )
        },
    }
    (rd / "simulation_status.json").write_text(json.dumps(status))
    (rd / "run_spec.json").write_text(json.dumps(spec.to_dict()))
    return rd, spec, net_file


def test_v4_2_complete_run_passes(tmp_path):
    rd, spec, _ = _make_v4_2_run(tmp_path)
    assert is_simulation_complete(spec, rd, PIPELINE_V4_2)


def test_v4_2_rejects_tampered_network(tmp_path):
    """P0-6：网络文件被修改后 resume 必须拒绝（重新哈希，而非仅与同源 SHA 比较）。"""
    rd, spec, net_file = _make_v4_2_run(tmp_path)
    assert is_simulation_complete(spec, rd, PIPELINE_V4_2)
    net_file.write_text("<tampered-network/>")
    assert not is_simulation_complete(spec, rd, PIPELINE_V4_2)


def test_v4_2_rejects_missing_network_sha(tmp_path):
    """P0-6：v0.4.2 status 缺 network_xml_sha256 → fail-closed。"""
    rd, spec, _ = _make_v4_2_run(tmp_path)
    st = json.loads((rd / "simulation_status.json").read_text())
    del st["network_xml_sha256"]
    (rd / "simulation_status.json").write_text(json.dumps(st))
    assert not is_simulation_complete(spec, rd, PIPELINE_V4_2)


def test_v4_2_rejects_tampered_additional(tmp_path):
    """P0-10 既有行为保持：additional 文件被修改后 resume 拒绝。"""
    rd, spec, _ = _make_v4_2_run(tmp_path)
    assert is_simulation_complete(spec, rd, PIPELINE_V4_2)
    (rd / "additional.add.xml").write_text("<tampered/>")
    assert not is_simulation_complete(spec, rd, PIPELINE_V4_2)


def test_v4_2_rejects_tampered_raw_output(tmp_path):
    """P0-1：raw SUMO 输出（performance.xml）被修改后 resume 必须拒绝。"""
    rd, spec, _ = _make_v4_2_run(tmp_path)
    assert is_simulation_complete(spec, rd, PIPELINE_V4_2)
    (rd / "performance.xml").write_text("<tampered-raw/>")
    assert not is_simulation_complete(spec, rd, PIPELINE_V4_2)


def test_v4_2_rejects_tampered_net_json(tmp_path):
    """P0-1：net.json 内容被修改（num_lanes 仍合法）后 resume 必须拒绝。"""
    rd, spec, _ = _make_v4_2_run(tmp_path)
    assert is_simulation_complete(spec, rd, PIPELINE_V4_2)
    net_dir = tmp_path / "net"
    # 修改 num_lanes 之外的字段，num_lanes 仍为合法正整数
    (net_dir / "net.json").write_text(json.dumps({"num_lanes": 1, "note": "tampered"}))
    assert not is_simulation_complete(spec, rd, PIPELINE_V4_2)
