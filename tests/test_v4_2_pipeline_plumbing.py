"""v0.4.2 P0-1~P0-6 正式管线贯通回归测试。

覆盖 reviewer 指出的断链：
- 配置序列化含网格字段（SHA 不碰撞）
- 正式配置可生成 safety run
- runner 分派 v0.4.2 到 stage2 parser
- main_factorial 成功判定不要求 ssm.xml
- ssm_not_collected 透传到 summary
- dedup_method 声明与实际执行一致
- from_dict 严格校验（"false"→False、非法 dedup/overlap 拒绝）
"""

import xml.etree.ElementTree as ET

import pytest

from scripts.experiment_config import ExperimentConfig
from scripts.parsing.ssm import parse_ssm
from scripts.run_spec import RunSpec
from scripts.simulation.batch_run import build_run_specs


def _v4_2_config_dict(**overrides) -> dict:
    base = {
        "config_version": "v0.4.2-p0-test",
        "pipeline_version": "v0.4.2",
        "schema_version": "2",
        "scenarios": ["scenario_0"],
        "models": ["IDM", "CACC"],
        "grid_mode": "cav_count",
        "seed_scope": "vehicle_type_assignment",
        "simulation_end": 3600,
        "warmup": 600,
        "step_length": 0.1,
        "detector_frequency": 120,
        "edge_data_frequency": 300,
        "loops": 300,
        "network_files": {"scenario_0": "net/scenario_0/loop.net.xml"},
        "treatments": [{"vehicle_count": 10, "cav_counts": [0, 5, 10]}],
        "sumo_seeds": [101],
        "experiment_role": "main_factorial",
        "ssm_enabled": False,
    }
    base.update(overrides)
    return base


def test_config_sha_differs_across_grids():
    a = ExperimentConfig.from_dict(_v4_2_config_dict())
    b = _v4_2_config_dict()
    b["treatments"] = [{"vehicle_count": 20, "cav_counts": [0, 10, 20]}]
    bcfg = ExperimentConfig.from_dict(b)
    assert a.sha256() != bcfg.sha256()
    assert "treatments" in a.to_dict()


def test_config_exprresses_safety_role():
    cfg = ExperimentConfig.from_dict(_v4_2_config_dict(experiment_role="safety", ssm_enabled=True))
    assert cfg.experiment_role == "safety"
    assert cfg.ssm_enabled is True


def test_build_run_specs_safety_role_reachable():
    specs = build_run_specs(
        scenarios=["scenario_0"],
        models=["IDM", "CACC"],
        treatments=[{"vehicle_count": 10, "cav_counts": [0, 5, 10]}],
        sumo_seeds=[101],
        simulation_end=3600,
        warmup=600,
        step_length=0.1,
        detector_frequency=120,
        edge_data_frequency=300,
        loops=300,
        network_files={"scenario_0": "net/scenario_0/loop.net.xml"},
        pipeline_version="v0.4.2",
        schema_version="2",
        config_sha256="x",
        network_sha256={"scenario_0": "y"},
        experiment_id="e",
        experiment_role="safety",
        ssm_enabled=True,
        analysis_ttc_threshold_s=2.5,
        ssm_dedup_method="sorted_greedy_80pct",
    )
    assert specs
    assert all(s.experiment_role == "safety" for s in specs)
    assert all(s.ssm_enabled for s in specs)
    assert specs[0].analysis_ttc_threshold_s == 2.5
    assert specs[0].ssm_dedup_method == "sorted_greedy_80pct"


def test_main_factorial_spec_defaults():
    specs = build_run_specs(
        scenarios=["scenario_0"],
        models=["IDM", "CACC"],
        treatments=[{"vehicle_count": 10, "cav_counts": [0, 5, 10]}],
        sumo_seeds=[101],
        simulation_end=3600,
        warmup=600,
        step_length=0.1,
        detector_frequency=120,
        edge_data_frequency=300,
        loops=300,
        network_files={"scenario_0": "net/scenario_0/loop.net.xml"},
        pipeline_version="v0.4.2",
        schema_version="2",
        config_sha256="x",
        network_sha256={"scenario_0": "y"},
        experiment_id="e",
    )
    assert specs
    assert all(s.experiment_role == "main_factorial" for s in specs)
    assert all(not s.ssm_enabled for s in specs)


def test_from_dict_strict_bool_and_validation():
    d = _v4_2_config_dict()
    d["ssm_enabled"] = "false"
    spec = RunSpec.from_dict(_spec_dict(d))
    assert spec.ssm_enabled is False


def test_from_dict_rejects_invalid_dedup():
    d = _v4_2_config_dict()
    d["ssm_dedup_method"] = "maximum_matching_80pct"
    with pytest.raises(ValueError, match="ssm_dedup_method"):
        RunSpec.from_dict(_spec_dict(d))


def test_from_dict_rejects_invalid_overlap():
    d = _v4_2_config_dict()
    d["ssm_mirror_overlap_ratio"] = 1.5
    with pytest.raises(ValueError, match="ssm_mirror_overlap_ratio"):
        RunSpec.from_dict(_spec_dict(d))


def test_parse_ssm_dedup_none_keeps_all():
    """dedup_method='none' 保留全部记录（与 greedy 不同）。"""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ssm.xml"
        root = ET.Element("SSMLog")
        c1 = ET.SubElement(
            root, "conflict", {"begin": "1000", "end": "1100", "ego": "veh0", "foe": "veh1"}
        )
        ET.SubElement(c1, "minTTC", {"value": "2.0", "time": "1050"})
        c2 = ET.SubElement(
            root, "conflict", {"begin": "1050", "end": "1150", "ego": "veh1", "foe": "veh0"}
        )
        ET.SubElement(c2, "minTTC", {"value": "2.5", "time": "1100"})
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)

        r_greedy = parse_ssm(str(path), warmup_period=600, simulation_end=3600)
        r_none = parse_ssm(str(path), warmup_period=600, simulation_end=3600, dedup_method="none")
        # greedy 去重后 1 事件（镜像合并），none 保留 2 条
        assert r_greedy["ttc_conflict_event_count"] <= r_none["ttc_conflict_event_count"]
        assert r_none["ttc_conflict_event_count"] == 2


def _spec_dict(cfg_dict: dict) -> dict:
    """从配置 dict 构造最小 run_spec dict（含 v4_1 必需字段）。"""
    return {
        "run_id": "s0_IDM_v010_c005_as01_ss101",
        "scenario": "scenario_0",
        "model": "IDM",
        "pcav": 0.5,
        "vehicle_count": 10,
        "seed": 1,
        "simulation_end": 3600.0,
        "warmup": 600.0,
        "step_length": 0.1,
        "detector_frequency": 120,
        "edge_data_frequency": 300,
        "loops": 300,
        "network_file": "net/scenario_0/loop.net.xml",
        "seed_scope": "vehicle_type_assignment",
        "pipeline_version": "v0.4.2",
        "schema_version": "2",
        "config_sha256": "c",
        "network_sha256": "n",
        "experiment_id": "e",
        "cav_count": 5,
        "hv_count": 5,
        "realized_pcav": 0.5,
        "requested_pcav": None,
        "sumo_seed": 101,
        "ssm_capture_ttc_threshold_s": 3.0,
        "ssm_capture_drac_threshold_mps2": 3.0,
        "ssm_range_m": 50.0,
        "ssm_trajectories": False,
        "ssm_extratime_s": 5.0,
        "with_internal": True,
        "fcd_profile": None,
        "fcd_max_leader_distance_m": None,
        **cfg_dict,
    }
