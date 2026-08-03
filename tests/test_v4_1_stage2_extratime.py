"""v0.4.1 stage2 ssm_extratime_s + fragment merge tests"""

import os

import pytest

from scripts.parsing.ssm import _merge_fragments, parse_ssm
from scripts.run_spec import PIPELINE_V4_2, RunSpec, build_run_id

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


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
            pipeline_version=PIPELINE_V4_2,
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
            pipeline_version=PIPELINE_V4_2,
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
        pipeline_version=PIPELINE_V4_2,
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
        pipeline_version=PIPELINE_V4_2,
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
        pipeline_version=PIPELINE_V4_2,
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
    r = parse_ssm(
        os.path.join(_FIXTURES, "ssm_minimal.xml"),
        warmup_period=0,
        ttc_threshold=3.0,
        drac_threshold=3.0,
    )
    assert r["parse_success"] is True
    assert "ssm_fragment_merged_count" in r
    assert r["ssm_fragment_merged_count"] >= 0


def test_fragment_merge_adjacent_directional():
    recs = [
        {"ego": "a", "foe": "b", "begin": 0.0, "end": 10.0, "min_ttc": 2.0, "max_drac": None},
        {"ego": "a", "foe": "b", "begin": 12.0, "end": 20.0, "min_ttc": 1.5, "max_drac": None},
    ]
    merged, absorbed = _merge_fragments(recs)
    assert absorbed == 1
    assert len(merged) == 1
    assert merged[0]["begin"] == 0.0
    assert merged[0]["end"] == 20.0
    assert merged[0]["min_ttc"] == 1.5


def test_fragment_merge_gap_too_large():
    recs = [
        {"ego": "a", "foe": "b", "begin": 0.0, "end": 10.0, "min_ttc": 2.0, "max_drac": None},
        {"ego": "a", "foe": "b", "begin": 16.0, "end": 20.0, "min_ttc": 1.5, "max_drac": None},
    ]
    merged, absorbed = _merge_fragments(recs)
    assert absorbed == 0
    assert len(merged) == 2


def test_fragment_merge_different_direction():
    recs = [
        {"ego": "a", "foe": "b", "begin": 0.0, "end": 10.0, "min_ttc": 2.0, "max_drac": None},
        {"ego": "b", "foe": "a", "begin": 12.0, "end": 20.0, "min_ttc": 1.5, "max_drac": None},
    ]
    merged, absorbed = _merge_fragments(recs)
    assert absorbed == 0
    assert len(merged) == 2


def test_fragment_merge_chain_three():
    recs = [
        {"ego": "a", "foe": "b", "begin": 0.0, "end": 10.0, "min_ttc": 3.0, "max_drac": 5.0},
        {"ego": "a", "foe": "b", "begin": 12.0, "end": 20.0, "min_ttc": 2.0, "max_drac": 6.0},
        {"ego": "a", "foe": "b", "begin": 22.0, "end": 30.0, "min_ttc": 1.0, "max_drac": 4.0},
    ]
    merged, absorbed = _merge_fragments(recs)
    assert absorbed == 2
    assert len(merged) == 1
    assert merged[0]["begin"] == 0.0
    assert merged[0]["end"] == 30.0
    assert merged[0]["min_ttc"] == 1.0
    assert merged[0]["max_drac"] == 6.0


def test_fragment_merge_provenance():
    recs = [
        {
            "ego": "a",
            "foe": "b",
            "begin": 0.0,
            "end": 10.0,
            "min_ttc": 3.0,
            "min_ttc_time": 5.0,
            "min_ttc_type_code": 2,
            "min_ttc_source_ego": "a",
            "min_ttc_source_foe": "b",
            "max_drac": None,
        },
        {
            "ego": "a",
            "foe": "b",
            "begin": 12.0,
            "end": 20.0,
            "min_ttc": 1.0,
            "min_ttc_time": 15.0,
            "min_ttc_type_code": 3,
            "min_ttc_source_ego": "a",
            "min_ttc_source_foe": "b",
            "max_drac": None,
        },
    ]
    merged, absorbed = _merge_fragments(recs)
    assert merged[0]["min_ttc"] == 1.0
    assert merged[0]["min_ttc_time"] == 15.0
    assert merged[0]["min_ttc_type_code"] == 3
    assert merged[0]["min_ttc_source_ego"] == "a"
    assert merged[0]["min_ttc_source_foe"] == "b"


def test_fragment_merge_parser_default_disabled():
    r = parse_ssm(
        os.path.join(_FIXTURES, "ssm_minimal.xml"),
        warmup_period=0,
        ttc_threshold=3.0,
        drac_threshold=3.0,
    )
    assert r["parse_success"] is True
    assert r["ssm_fragment_merged_count"] == 0


def test_fragment_merge_parser_explicit_enabled():
    r = parse_ssm(
        os.path.join(_FIXTURES, "ssm_fragmentable.xml"),
        warmup_period=0,
        ttc_threshold=3.0,
        drac_threshold=3.0,
        fragment_merge_gap_s=5.0,
    )
    assert r["parse_success"] is True
    assert r["ssm_fragment_merged_count"] == 1
    assert r["ttc_conflict_event_count"] == 1


def test_fragment_merge_parser_default_disabled_on_fragmentable():
    r = parse_ssm(
        os.path.join(_FIXTURES, "ssm_fragmentable.xml"),
        warmup_period=0,
        ttc_threshold=3.0,
        drac_threshold=3.0,
    )
    assert r["parse_success"] is True
    assert r["ssm_fragment_merged_count"] == 0
    assert r["ttc_conflict_event_count"] == 2
