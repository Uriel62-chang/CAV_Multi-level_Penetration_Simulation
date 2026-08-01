"""v0.4.2 P0-8 回归测试：逐 lap delay 与自由流 artifact 覆盖。"""

import json

import pytest

from scripts.parsing.metrics import SubgroupPrimitives, compute_core_summary
from scripts.run_spec import PIPELINE_V4_2, RunSpec


def _spec(model="IDM") -> RunSpec:
    return RunSpec(
        scenario="scenario_2",
        model=model,
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="s2_IDM_v010_c005_as01_ss101",
        pipeline_version=PIPELINE_V4_2,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
    )


def _primitives(hv_mean=70.0, cav_mean=65.0, n_hv=10, n_cav=10):
    return SubgroupPrimitives(
        detector={"all": {}},
        ssm={"all": {}},
        lanechange={"all": {}},
        edge_perf={"all": {"non_internal_edge_vehicle_km": 100.0, "total_vehicle_km": 120.0}},
        edge_emis={"all": {}},
        vehroute={
            "all": {"mean_lap_time_s": (hv_mean * n_hv + cav_mean * n_cav) / (n_hv + n_cav)},
            "HV": {"mean_lap_time_s": hv_mean, "completed_lap_count": n_hv},
            "CAV": {"mean_lap_time_s": cav_mean, "completed_lap_count": n_cav},
        },
        emerg_brake={"all": {}},
        fcd=None,
    )


def test_delay_per_vehicle_type_weighted():
    """HV lap → HV ref；CAV lap → CAV_IDM ref；加权汇总。"""
    refs = {"HV": 60.0, "CAV_IDM": 58.0}
    prim = _primitives(hv_mean=70.0, cav_mean=65.0, n_hv=10, n_cav=10)
    s = compute_core_summary(prim, _spec("IDM"), refs)
    expected = ((70.0 - 60.0) * 10 + (65.0 - 58.0) * 10) / 20
    assert s["mean_lap_delay_s"] == pytest.approx(expected)


def test_delay_cav_uses_model_specific_ref():
    """CAV delay 用 CAV_CACC 参考（非 HV/CAV_IDM）。"""
    refs = {"HV": 60.0, "CAV_CACC": 57.0}
    prim = _primitives(hv_mean=70.0, cav_mean=65.0, n_hv=10, n_cav=10)
    s = compute_core_summary(prim, _spec("CACC"), refs)
    expected = ((70.0 - 60.0) * 10 + (65.0 - 57.0) * 10) / 20
    assert s["mean_lap_delay_s"] == pytest.approx(expected)


def test_delay_all_hv_no_cav():
    refs = {"HV": 60.0, "CAV_IDM": 58.0}
    prim = _primitives(hv_mean=70.0, cav_mean=0.0, n_hv=20, n_cav=0)
    s = compute_core_summary(prim, _spec("IDM"), refs)
    assert s["mean_lap_delay_s"] == pytest.approx(10.0)


def test_free_flow_artifact_covers_all_scenarios():
    with open("artifacts/free_flow/v0.4.1-pilot-ff-1/free_flow_references.json") as f:
        art = json.load(f)
    assert set(art["results"].keys()) == {
        "scenario_0",
        "scenario_1",
        "scenario_2",
        "scenario_3",
    }
    for _sc, info in art["results"].items():
        refs = info["references"]
        assert "HV" in refs
        assert "CAV_IDM" in refs
        assert "CAV_CACC" in refs
