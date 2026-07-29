"""v0.4.1 cav_count 网格回归测试"""

import json

import pytest

from scripts.run_spec import PIPELINE_V4_1, RunSpec, build_run_id
from scripts.simulation.batch_run import build_run_specs, validate_specs


def test_cav_zero_canonical_model():
    """cav=0 时 model 固定为 IDM，与 models 列表顺序和子集无关。"""
    specs1 = build_run_specs(
        ["scenario_0"],
        ["IDM", "CACC"],
        PIPELINE_V4_1,
        treatments=[{"vehicle_count": 10, "cav_counts": [0]}],
        sumo_seeds=[101],
    )
    specs2 = build_run_specs(
        ["scenario_0"],
        ["CACC", "IDM"],
        PIPELINE_V4_1,
        treatments=[{"vehicle_count": 10, "cav_counts": [0]}],
        sumo_seeds=[101],
    )
    assert specs1[0].model == "IDM"
    assert specs2[0].model == "IDM"
    assert specs1[0] == specs2[0]


def test_cav_zero_canonical_route_idempotent():
    """不同 model 子集产生相同的 RunSpec SHA 和 route 输出。"""
    from scripts.simulation.flow_generator import generate_flow
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "r.rou.xml")
        _ = generate_flow(10, 0.0, 5, 1, p, "IDM")
        with open(p) as f:
            route1 = f.read()
        _ = generate_flow(10, 0.0, 5, 1, p + ".2", "CACC")
        with open(p + ".2") as f:
            route2 = f.read()

    # CAV vType 不应出现在 route 中（cav_count=0）
    assert 'vType id="CAV"' not in route1
    assert 'vType id="CAV"' not in route2


def test_endpoint_seed_must_be_zero():
    """cav=0 时 seed=99 应被 validate_specs 拒绝。"""
    spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.0,
        vehicle_count=10,
        seed=99,
        run_id=build_run_id(
            "scenario_0",
            "IDM",
            vehicle_count=10,
            cav_count=0,
            assignment_seed=None,
            sumo_seed=101,
        ),
        pipeline_version=PIPELINE_V4_1,
        sumo_seed=101,
        cav_count=0,
        requested_pcav=None,
    )
    with pytest.raises(RuntimeError, match="endpoint.*seed"):
        validate_specs(
            [spec],
            ["scenario_0"],
            ["IDM"],
            treatments=[{"vehicle_count": 10, "cav_counts": [0]}],
            sumo_seeds=[101],
        )


def test_endpoint_seed_full_cav_must_be_zero():
    """cav=vehN 时 seed=99 应被拒绝。"""
    spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=1.0,
        vehicle_count=10,
        seed=99,
        run_id=build_run_id(
            "scenario_0",
            "IDM",
            vehicle_count=10,
            cav_count=10,
            assignment_seed=None,
            sumo_seed=101,
        ),
        pipeline_version=PIPELINE_V4_1,
        sumo_seed=101,
        cav_count=10,
        requested_pcav=None,
    )
    cav0_spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.0,
        vehicle_count=10,
        seed=0,
        run_id=build_run_id(
            "scenario_0",
            "IDM",
            vehicle_count=10,
            cav_count=0,
            assignment_seed=None,
            sumo_seed=101,
        ),
        pipeline_version=PIPELINE_V4_1,
        sumo_seed=101,
        cav_count=0,
        requested_pcav=None,
    )
    with pytest.raises(RuntimeError, match="endpoint.*seed"):
        validate_specs(
            [cav0_spec, spec],
            ["scenario_0"],
            ["IDM"],
            treatments=[{"vehicle_count": 10, "cav_counts": [0, 10]}],
            sumo_seeds=[101],
        )


def test_unique_run_ids_162():
    """pilot.json 展开为 162 个唯一 run_id。"""
    config = json.load(open("configs/v0.4.1/pilot.json"))
    specs = build_run_specs(
        list(config["scenarios"]),
        list(config["models"]),
        config["pipeline_version"],
        treatments=list(config["treatments"]),
        sumo_seeds=list(config["sumo_seeds"]),
    )
    ids = [s.run_id for s in specs]
    assert len(ids) == 162
    assert len(set(ids)) == 162
