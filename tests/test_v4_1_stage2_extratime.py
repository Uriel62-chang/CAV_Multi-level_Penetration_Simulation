"""v0.4.1 stage2 ssm_extratime_s + fragment merge tests"""

import pytest

from scripts.run_spec import PIPELINE_V4_1, RunSpec, build_run_id


def test_ssm_extratime_s_rejects_negative():
    with pytest.raises(ValueError, match="ssm_extratime_s"):
        RunSpec(
            scenario="scenario_0",
            model="IDM",
            pcav=0.5,
            vehicle_count=10,
            seed=1,
            run_id=build_run_id(
                "scenario_0", "IDM", vehicle_count=10, cav_count=5, assignment_seed=1, sumo_seed=101
            ),
            pipeline_version=PIPELINE_V4_1,
            schema_version="2",
            sumo_seed=101,
            cav_count=5,
            requested_pcav=None,
            ssm_extratime_s=-1.0,
        )


def test_ssm_extratime_s_rejects_zero():
    with pytest.raises(ValueError, match="ssm_extratime_s"):
        RunSpec(
            scenario="scenario_0",
            model="IDM",
            pcav=0.5,
            vehicle_count=10,
            seed=1,
            run_id=build_run_id(
                "scenario_0", "IDM", vehicle_count=10, cav_count=5, assignment_seed=1, sumo_seed=101
            ),
            pipeline_version=PIPELINE_V4_1,
            schema_version="2",
            sumo_seed=101,
            cav_count=5,
            requested_pcav=None,
            ssm_extratime_s=0.0,
        )


def test_ssm_extratime_s_default():
    spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id=build_run_id(
            "scenario_0", "IDM", vehicle_count=10, cav_count=5, assignment_seed=1, sumo_seed=101
        ),
        pipeline_version=PIPELINE_V4_1,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
    )
    assert spec.ssm_extratime_s == 5.0


def test_ssm_extratime_s_custom():
    spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id=build_run_id(
            "scenario_0", "IDM", vehicle_count=10, cav_count=5, assignment_seed=1, sumo_seed=101
        ),
        pipeline_version=PIPELINE_V4_1,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
        ssm_extratime_s=1.0,
    )
    assert spec.ssm_extratime_s == 1.0


def test_ssm_extratime_s_roundtrip():
    spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id=build_run_id(
            "scenario_0", "IDM", vehicle_count=10, cav_count=5, assignment_seed=1, sumo_seed=101
        ),
        pipeline_version=PIPELINE_V4_1,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
        ssm_extratime_s=2.5,
    )
    d = spec.to_dict()
    assert d["ssm_extratime_s"] == 2.5
    spec2 = RunSpec.from_dict(d)
    assert spec2.ssm_extratime_s == 2.5


def test_fragment_merge_counter_present():
    from scripts.parsing.ssm import parse_ssm

    r = parse_ssm(
        "raw/v0.4.1-pilot-1/s0_IDM_v120_c120_as00_ss101/ssm.xml",
        warmup_period=600,
        ttc_threshold=3.0,
        drac_threshold=3.0,
    )
    assert "ssm_fragment_merged_count" in r
    assert r["ssm_fragment_merged_count"] >= 0


def test_fragment_merge_baseline_noop_on_high_density():
    from scripts.parsing.ssm import parse_ssm

    r = parse_ssm(
        "raw/v0.4.1-pilot-1/s0_IDM_v120_c120_as00_ss101/ssm.xml",
        warmup_period=600,
        ttc_threshold=3.0,
        drac_threshold=3.0,
    )
    assert r["ssm_fragment_merged_count"] == 0
