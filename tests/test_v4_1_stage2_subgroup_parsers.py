"""v0.4.1 stage2 vehroute/lanechange/stderr subgroup tests"""

import json
import math
import os
from pathlib import Path

from scripts.parsing.lanechange import parse_lanechange, parse_lanechange_subgroup
from scripts.parsing.stderr import parse_emergency_braking, parse_emergency_braking_subgroup
from scripts.parsing.vehroute import parse_lap_times, parse_lap_times_subgroup

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "stage2_subgroup")
_BASE = Path(_FIXTURES)
_TYPE_MAP = json.loads((_BASE / "vehicle_type_map.json").read_text())


def test_lap_times_subgroup_keys():
    result = parse_lap_times_subgroup(
        str(_BASE / "vehroute.xml"), _TYPE_MAP, edges_per_lap=4, warmup_period=60, sim_end_time=360
    )
    for label in ("all", "HV", "CAV"):
        for key in (
            "completed_lap_count",
            "mean_lap_time_s",
            "median_lap_time_s",
            "p95_lap_time_s",
            "lap_time_std_s",
            "parse_success",
        ):
            assert key in result[label], f"{label} missing {key}"


def test_lap_times_lap_count_additivity():
    result = parse_lap_times_subgroup(
        str(_BASE / "vehroute.xml"), _TYPE_MAP, edges_per_lap=4, warmup_period=60, sim_end_time=360
    )
    assert (
        result["HV"]["completed_lap_count"] + result["CAV"]["completed_lap_count"]
        == result["all"]["completed_lap_count"]
    )


def test_lc_subgroup_keys():
    result = parse_lanechange_subgroup(str(_BASE / "lanechange.xml"), _TYPE_MAP, warmup_period=60)
    for label in ("all", "HV", "CAV"):
        for key in (
            "lane_change_count",
            "unsafe_lc_gap_count",
            "unsafe_lc_gap_ratio",
            "parse_success",
        ):
            assert key in result[label]


def test_lc_count_additivity():
    result = parse_lanechange_subgroup(str(_BASE / "lanechange.xml"), _TYPE_MAP, warmup_period=60)
    assert (
        result["HV"]["lane_change_count"] + result["CAV"]["lane_change_count"]
        == result["all"]["lane_change_count"]
    )


def test_eb_count_additivity():
    stderr_text = (_BASE / "stderr.log").read_text(encoding="utf-8", errors="replace")
    result = parse_emergency_braking_subgroup(stderr_text, _TYPE_MAP, warmup_period=60)
    assert (
        result["HV"]["emergency_braking_count"] + result["CAV"]["emergency_braking_count"]
        == result["all"]["emergency_braking_count"]
    )


def test_all_matches_original():
    r1 = parse_lap_times(
        str(_BASE / "vehroute.xml"), edges_per_lap=4, warmup_period=60, sim_end_time=360
    )
    r2 = parse_lap_times_subgroup(
        str(_BASE / "vehroute.xml"), _TYPE_MAP, edges_per_lap=4, warmup_period=60, sim_end_time=360
    )
    assert r1["completed_lap_count"] == r2["all"]["completed_lap_count"]
    assert r1["mean_lap_time_s"] == r2["all"]["mean_lap_time_s"]


def test_lc_all_matches_original():
    r1 = parse_lanechange(str(_BASE / "lanechange.xml"), warmup_period=60)
    r2 = parse_lanechange_subgroup(str(_BASE / "lanechange.xml"), _TYPE_MAP, warmup_period=60)
    assert r1["lane_change_count"] == r2["all"]["lane_change_count"]
    assert r1["unsafe_lc_gap_count"] == r2["all"]["unsafe_lc_gap_count"]
    assert (
        math.isnan(r1["unsafe_lc_gap_ratio"])
        and math.isnan(r2["all"]["unsafe_lc_gap_ratio"])
        or r1["unsafe_lc_gap_ratio"] == r2["all"]["unsafe_lc_gap_ratio"]
    )


def test_eb_all_matches_original():
    stderr_text = (_BASE / "stderr.log").read_text(encoding="utf-8", errors="replace")
    r1 = parse_emergency_braking(stderr_text, warmup_period=60)
    r2 = parse_emergency_braking_subgroup(stderr_text, _TYPE_MAP, warmup_period=60)
    assert r1["emergency_braking_count"] == r2["all"]["emergency_braking_count"]
    assert (
        r1["emergency_braking_affected_vehicle_count"]
        == r2["all"]["emergency_braking_affected_vehicle_count"]
    )
