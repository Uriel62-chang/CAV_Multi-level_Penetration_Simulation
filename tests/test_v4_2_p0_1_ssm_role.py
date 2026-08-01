"""v0.4.2 P0-1 回归测试：experiment_role / ssm_enabled 贯通。

覆盖：
- RunSpec v0.4.2 round-trip（experiment_role / ssm_enabled 持久化）；
- legacy/v0.4.1 hash 不受新字段影响；
- build_sumo_command_v4_2 主 factorial 剥离 SSM 参数；
- is_simulation_complete 对主 factorial 的意图性缺失判定。
"""

from pathlib import Path

from scripts.run_spec import (
    PIPELINE_V4_0_POST1,
    PIPELINE_V4_1,
    PIPELINE_V4_2,
    RunSpec,
    build_run_id,
    is_simulation_complete,
)
from scripts.simulation.single_run import (
    build_sumo_command_v4_2,
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


def test_v4_2_legacy_hash_unaffected():
    """legacy 字段集不含 v4_2 新字段，哈希兼容保持不变。"""
    spec_legacy = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="s0_IDM_p050_v010_seed1",
        pipeline_version=PIPELINE_V4_0_POST1,
    )
    d = spec_legacy.to_dict()
    assert "experiment_role" not in d
    assert "ssm_enabled" not in d


def test_v4_1_hash_unaffected_by_v4_2_fields():
    spec41 = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="s0_IDM_v010_c005_as01_ss101",
        pipeline_version=PIPELINE_V4_1,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
    )
    d41 = spec41.to_dict()
    assert "experiment_role" not in d41
    assert "ssm_enabled" not in d41


def test_v4_2_main_factorial_strips_ssm_options():
    spec = _spec_v4_2(experiment_role="main_factorial", ssm_enabled=False)
    cmd = build_sumo_command_v4_2(_dummy_prepared(), NET, spec)
    assert not any(a.startswith("--device.ssm") for a in cmd), cmd


def test_v4_2_safety_keeps_ssm_options():
    spec = _spec_v4_2(experiment_role="safety", ssm_enabled=True)
    cmd = build_sumo_command_v4_2(_dummy_prepared(), NET, spec)
    assert "--device.ssm.measures" in cmd
    assert "--device.ssm.thresholds" in cmd


def test_v4_2_main_factorial_missing_ssm_is_complete(tmp_path: Path):
    spec = _spec_v4_2(experiment_role="main_factorial", ssm_enabled=False)
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
    spec = _spec_v4_2(experiment_role="safety", ssm_enabled=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    _write_required_files(run_dir)
    _write_status(run_dir, spec, pipeline="v0.4.2")
    # 缺 ssm.xml → 不 complete
    assert is_simulation_complete(spec, run_dir, "v0.4.2") is False
    (run_dir / "ssm.xml").write_text("<SSMLog/>", encoding="utf-8")
    assert is_simulation_complete(spec, run_dir, "v0.4.2") is True


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
    (run_dir / "simulation_status.json").write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "run_spec.json").write_text(json.dumps(spec.to_dict()), encoding="utf-8")


def test_v4_2_resume_rejects_additional_change(tmp_path: Path):
    """P0-10：additional.add.xml 被修改后 resume 判定失败。"""
    spec = _spec_v4_2(experiment_role="main_factorial", ssm_enabled=False)
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
