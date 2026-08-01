"""v0.4.1 stage2 ssm_extratime_s + fragment merge tests"""

import os

import pytest

from scripts.parsing.ssm import _merge_fragments, parse_ssm
from scripts.run_spec import PIPELINE_V4_1, RunSpec, build_run_id

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


def test_runner_merge_gap_when_extratime_reduced(tmp_path):
    import json

    from scripts.parsing.runner import _parse_one_run_v4_1
    from scripts.run_spec import PIPELINE_V4_1, RunSpec, write_run_spec

    rd = tmp_path / "run"
    rd.mkdir()
    spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="merge-gap-test",
        pipeline_version=PIPELINE_V4_1,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
        with_internal=True,
        ssm_capture_ttc_threshold_s=5.0,
        ssm_extratime_s=1.0,
        detector_frequency=60,
        edge_data_frequency=60,
        simulation_end=360,
        warmup=60,
        step_length=0.1,
        loops=4,
        network_file="net/scenario_0/loop.net.xml",
    )
    write_run_spec(spec, rd)

    type_map = {f"veh{i}": ("CAV" if i < 5 else "HV") for i in range(10)}
    (rd / "vehicle_type_map.json").write_text(json.dumps(type_map))
    for f in (
        "routes.rou.xml",
        "performance.xml",
        "performance_HV.xml",
        "performance_CAV.xml",
        "emissions.xml",
        "emissions_HV.xml",
        "emissions_CAV.xml",
        "vehroute.xml",
        "lanechange.xml",
        "stderr.log",
        "ssm.xml",
        "detector_lane0.xml",
        "detector_lane0_HV.xml",
        "detector_lane0_CAV.xml",
    ):
        (rd / f).write_text("<root/>")
    status = {
        "run_id": spec.run_id,
        "pipeline_version": PIPELINE_V4_1,
        "status": "SUCCESS",
        "return_code": 0,
        "run_spec_sha256": spec.sha256(),
        "schema_version": "2",
        "config_sha256": "",
        "network_sha256": "",
        "experiment_id": "",
        "sumo_seed": 101,
        "route_file_sha256": "",
        "vehicle_type_map_sha256": "",
    }
    (rd / "simulation_status.json").write_text(json.dumps(status))

    import scripts.parsing.ssm as ssm_mod

    _original = ssm_mod.parse_ssm_subgroup
    captured_gap = []

    def tracking(
        fpath,
        type_map,
        warmup_period=600,
        ttc_threshold=3.0,
        drac_threshold=3.0,
        fragment_merge_gap_s=0.0,
        simulation_end=None,
        mirror_overlap_ratio=0.8,
        dedup_method="greedy_one_to_one_80pct",
    ):
        captured_gap.append(fragment_merge_gap_s)
        return _original(
            fpath,
            type_map,
            warmup_period,
            ttc_threshold,
            drac_threshold,
            fragment_merge_gap_s=fragment_merge_gap_s,
        )

    ssm_mod.parse_ssm_subgroup = tracking
    try:
        core, subgroup, errors = _parse_one_run_v4_1(rd, spec, spec.network_file)
    finally:
        ssm_mod.parse_ssm_subgroup = _original

    assert 5.0 in captured_gap, f"expected merge_gap=5.0 when extratime=1.0, got {captured_gap}"


def test_runner_merge_gap_default_disabled(tmp_path):
    import json

    from scripts.parsing.runner import _parse_one_run_v4_1
    from scripts.run_spec import PIPELINE_V4_1, RunSpec, write_run_spec

    rd = tmp_path / "run"
    rd.mkdir()
    spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="merge-gap-default",
        pipeline_version=PIPELINE_V4_1,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
        with_internal=True,
        ssm_capture_ttc_threshold_s=5.0,
        detector_frequency=60,
        edge_data_frequency=60,
        simulation_end=360,
        warmup=60,
        step_length=0.1,
        loops=4,
        network_file="net/scenario_0/loop.net.xml",
    )
    write_run_spec(spec, rd)

    type_map = {f"veh{i}": ("CAV" if i < 5 else "HV") for i in range(10)}
    (rd / "vehicle_type_map.json").write_text(json.dumps(type_map))
    for f in (
        "routes.rou.xml",
        "performance.xml",
        "performance_HV.xml",
        "performance_CAV.xml",
        "emissions.xml",
        "emissions_HV.xml",
        "emissions_CAV.xml",
        "vehroute.xml",
        "lanechange.xml",
        "stderr.log",
        "ssm.xml",
        "detector_lane0.xml",
        "detector_lane0_HV.xml",
        "detector_lane0_CAV.xml",
    ):
        (rd / f).write_text("<root/>")
    status = {
        "run_id": spec.run_id,
        "pipeline_version": PIPELINE_V4_1,
        "status": "SUCCESS",
        "return_code": 0,
        "run_spec_sha256": spec.sha256(),
        "schema_version": "2",
        "config_sha256": "",
        "network_sha256": "",
        "experiment_id": "",
        "sumo_seed": 101,
        "route_file_sha256": "",
        "vehicle_type_map_sha256": "",
    }
    (rd / "simulation_status.json").write_text(json.dumps(status))

    import scripts.parsing.ssm as ssm_mod

    _original = ssm_mod.parse_ssm_subgroup
    captured_gap = []

    def tracking(
        fpath,
        type_map,
        warmup_period=600,
        ttc_threshold=3.0,
        drac_threshold=3.0,
        fragment_merge_gap_s=0.0,
        simulation_end=None,
        mirror_overlap_ratio=0.8,
        dedup_method="greedy_one_to_one_80pct",
    ):
        captured_gap.append(fragment_merge_gap_s)
        return _original(
            fpath,
            type_map,
            warmup_period,
            ttc_threshold,
            drac_threshold,
            fragment_merge_gap_s=fragment_merge_gap_s,
        )

    ssm_mod.parse_ssm_subgroup = tracking
    try:
        core, subgroup, errors = _parse_one_run_v4_1(rd, spec, spec.network_file)
    finally:
        ssm_mod.parse_ssm_subgroup = _original

    assert captured_gap == [0.0], (
        f"expected merge_gap=0.0 when extratime default, got {captured_gap}"
    )
