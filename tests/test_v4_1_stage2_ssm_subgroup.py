"""v0.4.1 stage2 SSM parse_ssm_subgroup pair/role classification tests"""

import math
import os

from scripts.parsing.ssm import parse_ssm, parse_ssm_subgroup

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

TYPE_MAP = {
    "veh24": "HV",
    "veh26": "CAV",
    "veh10": "HV",
    "veh6": "HV",
    "veh16": "CAV",
    "veh50": "CAV",
    "veh51": "HV",
}


def test_ssm_subgroup_all_matches_parse_ssm():
    path = os.path.join(FIXTURES, "ssm_minimal.xml")
    base = parse_ssm(path, warmup_period=0.0, ttc_threshold=3.0, drac_threshold=3.0)
    subgroup = parse_ssm_subgroup(
        path, TYPE_MAP, warmup_period=0.0, ttc_threshold=3.0, drac_threshold=3.0
    )

    for key in base:
        v1, v2 = base[key], subgroup["all"][key]
        if isinstance(v1, float) and math.isnan(v1) and math.isnan(v2):
            continue
        assert v1 == v2, f"Key {key}: base={v1} subgroup.all={v2}"


def test_ssm_pair_closure():
    path = os.path.join(FIXTURES, "ssm_minimal.xml")
    result = parse_ssm_subgroup(
        path, TYPE_MAP, warmup_period=0.0, ttc_threshold=3.0, drac_threshold=3.0
    )

    all_ttc = result["all"]["ttc_conflict_event_count"]
    pair_ttc = (
        result["pair_HV_HV"]["ttc_event_count"]
        + result["pair_HV_CAV"]["ttc_event_count"]
        + result["pair_CAV_CAV"]["ttc_event_count"]
    )
    assert pair_ttc == all_ttc, f"pair TTC={pair_ttc} != all TTC={all_ttc}"

    all_drac = result["all"]["drac_conflict_event_count"]
    pair_drac = (
        result["pair_HV_HV"]["drac_event_count"]
        + result["pair_HV_CAV"]["drac_event_count"]
        + result["pair_CAV_CAV"]["drac_event_count"]
    )
    assert pair_drac == all_drac, f"pair DRAC={pair_drac} != all DRAC={all_drac}"


def test_ssm_role_closure():
    path = os.path.join(FIXTURES, "ssm_minimal.xml")
    result = parse_ssm_subgroup(
        path, TYPE_MAP, warmup_period=0.0, ttc_threshold=3.0, drac_threshold=3.0
    )

    all_ttc = result["all"]["ttc_conflict_event_count"]
    role_ttc = (
        result["role_f_HV_l_HV"]["ttc_event_count"]
        + result["role_f_HV_l_CAV"]["ttc_event_count"]
        + result["role_f_CAV_l_HV"]["ttc_event_count"]
        + result["role_f_CAV_l_CAV"]["ttc_event_count"]
        + result["unclassified"]["ttc_event_count"]
    )
    assert role_ttc == all_ttc, f"role TTC={role_ttc} != all TTC={all_ttc}"

    all_drac = result["all"]["drac_conflict_event_count"]
    role_drac = (
        result["role_f_HV_l_HV"]["drac_event_count"]
        + result["role_f_HV_l_CAV"]["drac_event_count"]
        + result["role_f_CAV_l_HV"]["drac_event_count"]
        + result["role_f_CAV_l_CAV"]["drac_event_count"]
        + result["unclassified"]["drac_event_count"]
    )
    assert role_drac == all_drac, f"role DRAC={role_drac} != all DRAC={all_drac}"


def test_ssm_subgroup_keys():
    path = os.path.join(FIXTURES, "ssm_minimal.xml")
    result = parse_ssm_subgroup(
        path, TYPE_MAP, warmup_period=0.0, ttc_threshold=3.0, drac_threshold=3.0
    )

    expected_keys = {
        "all",
        "pair_HV_HV",
        "pair_HV_CAV",
        "pair_CAV_CAV",
        "role_f_HV_l_HV",
        "role_f_HV_l_CAV",
        "role_f_CAV_l_HV",
        "role_f_CAV_l_CAV",
        "unclassified",
    }
    assert set(result.keys()) == expected_keys

    for pair_key in ("pair_HV_HV", "pair_HV_CAV", "pair_CAV_CAV"):
        for sub_key in ("ttc_event_count", "drac_event_count"):
            assert sub_key in result[pair_key], f"{pair_key} missing {sub_key}"

    for role_key in ("role_f_HV_l_HV", "role_f_HV_l_CAV", "role_f_CAV_l_HV", "role_f_CAV_l_CAV"):
        for sub_key in ("ttc_event_count", "drac_event_count"):
            assert sub_key in result[role_key], f"{role_key} missing {sub_key}"

    for sub_key in ("ttc_event_count", "drac_event_count"):
        assert sub_key in result["unclassified"], f"unclassified missing {sub_key}"


def test_ssm_pair_counts_non_negative():
    path = os.path.join(FIXTURES, "ssm_minimal.xml")
    result = parse_ssm_subgroup(
        path, TYPE_MAP, warmup_period=0.0, ttc_threshold=3.0, drac_threshold=3.0
    )

    for pair_key in ("pair_HV_HV", "pair_HV_CAV", "pair_CAV_CAV"):
        assert result[pair_key]["ttc_event_count"] >= 0
        assert result[pair_key]["drac_event_count"] >= 0

    for role_key in ("role_f_HV_l_HV", "role_f_HV_l_CAV", "role_f_CAV_l_HV", "role_f_CAV_l_CAV"):
        assert result[role_key]["ttc_event_count"] >= 0
        assert result[role_key]["drac_event_count"] >= 0

    assert result["unclassified"]["ttc_event_count"] >= 0
    assert result["unclassified"]["drac_event_count"] >= 0
