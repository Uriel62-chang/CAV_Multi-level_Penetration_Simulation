"""v0.4.2 P0-4 回归测试：SSM 观测窗上界（[warmup, simulation_end)）。"""

import xml.etree.ElementTree as ET

from scripts.analysis.ssm_sensitivity import _dedup_none
from scripts.parsing.ssm import parse_ssm, parse_ssm_subgroup


def _write_ssm(path, conflicts):
    root = ET.Element("SSMLog")
    for c in conflicts:
        conflict = ET.SubElement(
            root,
            "conflict",
            {
                "begin": str(c["begin"]),
                "end": str(c["end"]),
                "ego": c.get("ego", "veh0"),
                "foe": c.get("foe", "veh1"),
            },
        )
        if "ttc" in c:
            ET.SubElement(conflict, "minTTC", {"value": str(c["ttc"]), "time": str(c["ttc_time"])})
        if "drac" in c:
            ET.SubElement(
                conflict, "maxDRAC", {"value": str(c["drac"]), "time": str(c["drac_time"])}
            )
    tree = ET.ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def test_parse_ssm_upper_bound_excludes_late_ttc(tmp_path):
    """TTC 极值时间 ≥3600 的事件应被排除（extratime 越窗场景）。"""
    path = tmp_path / "ssm.xml"
    _write_ssm(
        path,
        [
            {"begin": 3500, "end": 3605, "ttc": 1.0, "ttc_time": 3602},  # 越上界
            {"begin": 3500, "end": 3595, "ttc": 2.0, "ttc_time": 3550},  # 窗内
        ],
    )
    # 无上界（v0.4.1 兼容）：两个都算
    r_legacy = parse_ssm(str(path), warmup_period=600)
    assert r_legacy["ttc_conflict_event_count"] == 2
    # 有上界：越窗的 TTC 被排除
    r_new = parse_ssm(str(path), warmup_period=600, simulation_end=3600)
    assert r_new["ttc_conflict_event_count"] == 1
    assert r_new["min_ttc_s"] == 2.0


def test_parse_ssm_upper_bound_excludes_late_drac(tmp_path):
    path = tmp_path / "ssm.xml"
    _write_ssm(
        path,
        [
            {"begin": 3500, "end": 3605, "drac": 8.0, "drac_time": 3602},
            {"begin": 3500, "end": 3595, "drac": 6.0, "drac_time": 3550},
        ],
    )
    r_new = parse_ssm(str(path), warmup_period=600, simulation_end=3600)
    assert r_new["drac_conflict_event_count"] == 1
    assert r_new["max_drac_mps2"] == 6.0


def test_parse_ssm_record_crossing_upper_bound(tmp_path):
    """conflict begin ≥ 3600（整体越窗）应被 record 级排除。"""
    path = tmp_path / "ssm.xml"
    _write_ssm(
        path,
        [
            {"begin": 3600, "end": 3605, "ttc": 1.0, "ttc_time": 3601},
            {"begin": 3000, "end": 3590, "ttc": 2.0, "ttc_time": 3500},
        ],
    )
    r_new = parse_ssm(str(path), warmup_period=600, simulation_end=3600)
    assert r_new["ttc_conflict_event_count"] == 1


def test_parse_ssm_subgroup_upper_bound(tmp_path):
    path = tmp_path / "ssm.xml"
    _write_ssm(
        path,
        [
            {"begin": 3500, "end": 3605, "ttc": 1.0, "ttc_time": 3602},
            {"begin": 3500, "end": 3595, "ttc": 2.0, "ttc_time": 3550},
        ],
    )
    type_map = {"veh0": "CAV", "veh1": "HV"}
    r_new = parse_ssm_subgroup(str(path), type_map, warmup_period=600, simulation_end=3600)
    assert r_new["all"]["ttc_conflict_event_count"] == 1
    # pair 闭合：窗内 1 个事件进 HV_CAV pair
    assert r_new["pair_HV_CAV"]["ttc_event_count"] == 1


def test_sensitivity_dedup_none_upper_bound(tmp_path):
    path = tmp_path / "ssm.xml"
    _write_ssm(
        path,
        [
            {"begin": 3500, "end": 3605, "ttc": 1.0, "ttc_time": 3602},
            {"begin": 3500, "end": 3595, "ttc": 2.0, "ttc_time": 3550},
        ],
    )
    cnt, _, _, _, _ = _dedup_none(str(path), 600, 3.0, 9999, simulation_end=3600)
    assert cnt == 1
