"""v0.4.1 RunSpec 回归测试"""

from scripts.run_spec import PIPELINE_V4_2, RunSpec, build_run_id


def test_v4_1_round_trip_cav_count_mode():
    spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="s0_IDM_v010_c005_as01_ss101",
        pipeline_version=PIPELINE_V4_2,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
    )
    d = spec.to_dict()
    assert d["sumo_seed"] == 101
    assert d["cav_count"] == 5
    assert d["requested_pcav"] is None
    spec2 = RunSpec.from_dict(d)
    assert spec == spec2


def test_v4_1_pcav_consistency_rejected():
    import pytest

    with pytest.raises(ValueError, match="pcav.*inconsistent"):
        RunSpec(
            scenario="s0",
            model="M",
            pcav=0.51,
            vehicle_count=10,
            seed=1,
            run_id="r",
            pipeline_version=PIPELINE_V4_2,
            sumo_seed=101,
            cav_count=5,
        )


def test_v4_1_hash_stable():
    spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="s0_IDM_p050_v010_seed1",
        pipeline_version=PIPELINE_V4_2,
        sumo_seed=101,
        cav_count=5,
    )
    h1 = spec.sha256()
    h2 = spec.sha256()
    assert h1 == h2


def test_v4_1_run_id_new_format():
    rid = build_run_id(
        "scenario_2",
        "IDM",
        vehicle_count=120,
        cav_count=60,
        assignment_seed=1,
        sumo_seed=101,
    )
    assert rid == "s2_IDM_v120_c060_as01_ss101"


def test_v4_1_run_id_hvonly():
    rid = build_run_id(
        "scenario_2",
        None,
        vehicle_count=120,
        cav_count=0,
        assignment_seed=None,
        sumo_seed=101,
    )
    assert "HVONLY" in rid
    assert "as00" in rid
