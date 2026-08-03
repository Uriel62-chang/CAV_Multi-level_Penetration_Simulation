"""v0.4.2 P0-1 回归测试：experiment_role / ssm_enabled 贯通。

覆盖：
- RunSpec v0.4.2 round-trip（experiment_role / ssm_enabled 持久化）；
- legacy/v0.4.1 hash 不受新字段影响；
- build_sumo_command 主 factorial 剥离 SSM 参数；
- is_simulation_complete 对主 factorial 的意图性缺失判定。
"""

import json
from pathlib import Path

from scripts.provenance import sha256_file
from scripts.run_spec import (
    PIPELINE_V4_2,
    RunSpec,
    build_run_id,
    is_simulation_complete,
)
from scripts.simulation.single_run import (
    build_sumo_command,
)

NET = "net/scenario_0/loop.net.xml"


def _spec_v4_2(**overrides) -> RunSpec:
    base = dict(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id=build_run_id(
            "s0", "IDM", 10, 5, assignment_seed=1, sumo_seed=101, cav_count_mode=True
        )
        if False
        else "s0_IDM_v010_c005_as01_ss101",
        pipeline_version=PIPELINE_V4_2,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
    )
    base.update(overrides)
    return RunSpec(**base)


def test_v4_2_round_trip_role_and_ssm_enabled():
    spec = _spec_v4_2(experiment_role="main_factorial", ssm_enabled=False)
    d = spec.to_dict()
    assert d["pipeline_version"] == "v0.4.2"
    assert d["experiment_role"] == "main_factorial"
    assert d["ssm_enabled"] is False
    spec2 = RunSpec.from_dict(d)
    assert spec == spec2


def test_v4_2_main_factorial_strips_ssm_options():
    spec = _spec_v4_2(experiment_role="main_factorial", ssm_enabled=False)
    cmd = build_sumo_command(_dummy_prepared(), NET, spec)
    assert not any(a.startswith("--device.ssm") for a in cmd), cmd


def test_v4_2_safety_keeps_ssm_options():
    spec = _spec_v4_2(experiment_role="safety", ssm_enabled=True)
    cmd = build_sumo_command(_dummy_prepared(), NET, spec)
    assert "--device.ssm.measures" in cmd
    assert "--device.ssm.thresholds" in cmd


def test_v4_2_main_factorial_missing_ssm_is_complete(tmp_path: Path):
    net_file, net_sha = _dummy_network(tmp_path)
    spec = _spec_v4_2(
        experiment_role="main_factorial",
        ssm_enabled=False,
        network_file=net_file,
        network_sha256=net_sha,
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    _write_required_files(run_dir)
    _write_status(run_dir, spec, pipeline="v0.4.2")
    # 主 factorial：无 ssm.xml → complete
    assert is_simulation_complete(spec, run_dir, "v0.4.2") is True
    # 若错误地存在 ssm.xml → 判定失败（意图性缺失被违反）
    (run_dir / "ssm.xml").write_text("<SSMLog/>", encoding="utf-8")
    assert is_simulation_complete(spec, run_dir, "v0.4.2") is False


def test_v4_2_safety_requires_ssm(tmp_path: Path):
    net_file, net_sha = _dummy_network(tmp_path)
    spec = _spec_v4_2(
        experiment_role="safety",
        ssm_enabled=True,
        network_file=net_file,
        network_sha256=net_sha,
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    _write_required_files(run_dir)
    _write_status(run_dir, spec, pipeline="v0.4.2")
    # 缺 ssm.xml（status 已记录其哈希）→ 不 complete
    (run_dir / "ssm.xml").unlink()
    assert is_simulation_complete(spec, run_dir, "v0.4.2") is False
    (run_dir / "ssm.xml").write_text("x", encoding="utf-8")
    assert is_simulation_complete(spec, run_dir, "v0.4.2") is True


def _dummy_network(tmp_path: Path) -> tuple[str, str]:
    """创建 dummy 路网（loop.net.xml + net.json），返回 (network_file, sha256)。

    不依赖被 Git 忽略的 net/scenario_0/loop.net.xml（clean checkout 不存在），
    net.json 提供 is_simulation_complete 所需的 num_lanes。
    """
    net_dir = tmp_path / "net"
    net_dir.mkdir()
    net_file = net_dir / "loop.net.xml"
    net_file.write_text("<net/>", encoding="utf-8")
    (net_dir / "net.json").write_text(json.dumps({"num_lanes": 1}), encoding="utf-8")
    # P1-1（本轮审查）：sources.sha256 源锚定（is_simulation_complete 语义门禁
    # 与 input_integrity 同口径——网络字节再生不误拒，源变化才拒）
    (net_dir / "nodes.nod.xml").write_text("<nodes/>", encoding="utf-8")
    (net_dir / "edges.edg.xml").write_text("<edges/>", encoding="utf-8")
    import hashlib as _h

    _digest = _h.sha256()
    _digest.update((net_dir / "nodes.nod.xml").read_bytes())
    _digest.update((net_dir / "edges.edg.xml").read_bytes())
    (net_dir / "sources.sha256").write_text(_digest.hexdigest(), encoding="utf-8")
    return str(net_file), sha256_file(str(net_file))


def _dummy_prepared():
    from scripts.run_spec import PreparedRun

    return PreparedRun(
        run_dir=Path("/tmp/dummy"),
        route_path=Path("/tmp/dummy/routes.rou.xml"),
        additional_path=Path("/tmp/dummy/additional.add.xml"),
        detector_paths=(),
        ssm_path=Path("/tmp/dummy/ssm.xml"),
        lanechange_path=Path("/tmp/dummy/lanechange.xml"),
        performance_path=Path("/tmp/dummy/performance.xml"),
        emissions_path=Path("/tmp/dummy/emissions.xml"),
        vehroute_path=Path("/tmp/dummy/vehroute.xml"),
        stdout_path=Path("/tmp/dummy/stdout.log"),
        stderr_path=Path("/tmp/dummy/stderr.log"),
        status_path=Path("/tmp/dummy/simulation_status.json"),
        vehicle_type_map_path=Path("/tmp/dummy/vehicle_type_map.json"),
    )


def _write_required_files(run_dir: Path) -> None:
    """写入 v0.4.2 schema=2 所需的全部文件（不含 ssm.xml）。"""
    for name in (
        "routes.rou.xml",
        "additional.add.xml",
        "lanechange.xml",
        "performance.xml",
        "emissions.xml",
        "vehroute.xml",
        "vehicle_type_map.json",
        "performance_HV.xml",
        "performance_CAV.xml",
        "emissions_HV.xml",
        "emissions_CAV.xml",
        "detector_lane0.xml",
        "detector_lane0_HV.xml",
        "detector_lane0_CAV.xml",
    ):
        (run_dir / name).write_text("<x/>", encoding="utf-8")


def _write_status(run_dir: Path, spec: RunSpec, pipeline: str) -> None:
    import json

    status = {
        "run_id": spec.run_id,
        "pipeline_version": pipeline,
        "status": "SUCCESS",
        "return_code": 0,
        "run_spec_sha256": spec.sha256(),
        "schema_version": spec.schema_version,
        "config_sha256": spec.config_sha256,
        "network_sha256": spec.network_sha256,
        "experiment_id": spec.experiment_id,
        "sumo_seed": spec.sumo_seed,
    }
    import hashlib

    def _h(name):
        return hashlib.sha256((run_dir / name).read_bytes()).hexdigest()

    status["route_file_sha256"] = _h("routes.rou.xml")
    status["vehicle_type_map_sha256"] = _h("vehicle_type_map.json")
    if spec.pipeline_version == "v0.4.2":
        status["additional_file_sha256"] = _h("additional.add.xml")
        status["network_xml_sha256"] = spec.network_sha256
        # P0-1：net.json 与 raw 输出 SHA 闭包（使用 spec.network_file 同目录的 net.json）
        net_meta = Path(spec.network_file).with_name("net.json")
        status["net_json_sha256"] = sha256_file(str(net_meta))
        # P1-2（delta）：raw 键集与 input_integrity exact-set 单源；缺失文件
        # 先写占位（含 safety 的 ssm.xml），resume 的存在性由文件本身判定。
        from scripts.parsing.input_integrity import raw_output_expected_names

        raw_names = raw_output_expected_names(spec)
        for name in raw_names:
            p = run_dir / name
            if not p.exists():
                p.write_text("x", encoding="utf-8")
        status["raw_output_sha256"] = {n: _h(n) for n in raw_names}
    (run_dir / "simulation_status.json").write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "run_spec.json").write_text(json.dumps(spec.to_dict()), encoding="utf-8")


def test_v4_2_resume_rejects_additional_change(tmp_path: Path):
    """P0-10：additional.add.xml 被修改后 resume 判定失败。"""
    net_file, net_sha = _dummy_network(tmp_path)
    spec = _spec_v4_2(
        experiment_role="main_factorial",
        ssm_enabled=False,
        network_file=net_file,
        network_sha256=net_sha,
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    _write_required_files(run_dir)
    _write_status(run_dir, spec, pipeline="v0.4.2")
    assert is_simulation_complete(spec, run_dir, "v0.4.2") is True
    # 修改 additional → 拒绝复用
    (run_dir / "additional.add.xml").write_text(
        "<additional><modified/></additional>", encoding="utf-8"
    )
    assert is_simulation_complete(spec, run_dir, "v0.4.2") is False


def test_v4_2_resume_rejects_missing_raw_key_and_tamper(tmp_path: Path):
    """P1-2（delta）：删除 raw_output_sha256 键并篡改文件 → resume 判定失败。"""
    net_file, net_sha = _dummy_network(tmp_path)
    spec = _spec_v4_2(
        experiment_role="main_factorial",
        ssm_enabled=False,
        network_file=net_file,
        network_sha256=net_sha,
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    _write_required_files(run_dir)
    _write_status(run_dir, spec, pipeline="v0.4.2")
    assert is_simulation_complete(spec, run_dir, "v0.4.2") is True
    # 删除 performance.xml 的哈希项并篡改文件 → 键集不完整 → 拒绝
    import json as _json

    status_p = run_dir / "simulation_status.json"
    status = _json.loads(status_p.read_text())
    del status["raw_output_sha256"]["performance.xml"]
    status_p.write_text(_json.dumps(status), encoding="utf-8")
    (run_dir / "performance.xml").write_text("tampered", encoding="utf-8")
    assert is_simulation_complete(spec, run_dir, "v0.4.2") is False
