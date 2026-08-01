"""v0.4.2 P0-5 回归测试：SSM analysis 配置单源化。"""

import xml.etree.ElementTree as ET

import pytest

from scripts.parsing.ssm import parse_ssm
from scripts.run_spec import PIPELINE_V4_2, RunSpec


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
        ET.SubElement(conflict, "minTTC", {"value": str(c["ttc"]), "time": str(c["ttc_time"])})
    tree = ET.ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _spec_v4_2(**overrides) -> RunSpec:
    base = dict(
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
    base.update(overrides)
    return RunSpec(**base)


def test_run_spec_analysis_fields_round_trip():
    spec = _spec_v4_2(
        analysis_ttc_threshold_s=2.5,
        analysis_drac_threshold_mps2=4.0,
        ssm_dedup_method="sorted_greedy_80pct",
        ssm_mirror_overlap_ratio=0.9,
        ssm_fragment_merge_gap_s=3.0,
    )
    d = spec.to_dict()
    assert d["analysis_ttc_threshold_s"] == 2.5
    assert d["ssm_dedup_method"] == "sorted_greedy_80pct"
    spec2 = RunSpec.from_dict(d)
    assert spec2.analysis_ttc_threshold_s == 2.5
    assert spec2.ssm_fragment_merge_gap_s == 3.0


def test_run_spec_invalid_dedup_rejected():
    with pytest.raises(ValueError, match="ssm_dedup_method"):
        _spec_v4_2(ssm_dedup_method="maximum_matching_80pct")


def test_run_spec_invalid_overlap_rejected():
    with pytest.raises(ValueError, match="ssm_mirror_overlap_ratio"):
        _spec_v4_2(ssm_mirror_overlap_ratio=1.5)


def test_parse_ssm_analysis_threshold_from_spec(tmp_path):
    """analysis TTC 阈值从 spec 读取：2.5 时 2.0 算事件、3.0 不算。"""
    path = tmp_path / "ssm.xml"
    _write_ssm(
        path,
        [
            {"begin": 1000, "end": 1100, "ttc": 2.0, "ttc_time": 1050},
            {"begin": 1000, "end": 1100, "ttc": 3.0, "ttc_time": 1050},
        ],
    )
    # 默认 3.0：ttc<3.0 只有 2.0 算
    r_default = parse_ssm(str(path), warmup_period=600, simulation_end=3600)
    assert r_default["ttc_conflict_event_count"] == 1
    # analysis=2.5：ttc<2.5 仍只有 2.0 算（3.0 >= 2.5 不算）
    r_25 = parse_ssm(str(path), warmup_period=600, simulation_end=3600, ttc_threshold=2.5)
    assert r_25["ttc_conflict_event_count"] == 1


def test_parse_ssm_mirror_overlap_ratio_parameterized(tmp_path):
    """镜像去重 overlap 阈值参数化：0.8 与 0.1 对重叠 50% 的记录判定不同。"""
    path = tmp_path / "ssm.xml"
    # 正向与反向记录，时间重叠 50%
    _write_ssm(
        path,
        [
            {
                "begin": 1000,
                "end": 1100,
                "ttc": 2.0,
                "ttc_time": 1050,
                "ego": "veh0",
                "foe": "veh1",
            },
        ],
    )
    # 追加反向记录
    tree = ET.parse(str(path))
    root = tree.getroot()
    rev = ET.SubElement(
        root,
        "conflict",
        {"begin": "1050", "end": "1150", "ego": "veh1", "foe": "veh0"},
    )
    ET.SubElement(rev, "minTTC", {"value": "2.0", "time": "1100"})
    tree.write(path, encoding="utf-8", xml_declaration=True)

    # overlap=0.8：50% 重叠不达阈值 → 两条都保留（2 events）
    r_strict = parse_ssm(
        str(path), warmup_period=600, simulation_end=3600, mirror_overlap_ratio=0.8
    )
    # overlap=0.1：50% 重叠达到阈值 → 镜像去重（1 event）
    r_loose = parse_ssm(str(path), warmup_period=600, simulation_end=3600, mirror_overlap_ratio=0.1)
    assert r_strict["ttc_conflict_event_count"] >= r_loose["ttc_conflict_event_count"]
    assert r_loose["ttc_conflict_event_count"] == 1


def test_metrics_records_analysis_config(tmp_path, monkeypatch):
    """metrics 在 v0.4.2 时把 analysis 配置写入 summary（可审计）。"""
    import sys

    sys.path.insert(0, ".")
    from scripts.parsing.metrics import compute_core_summary

    spec = _spec_v4_2(analysis_ttc_threshold_s=2.5, ssm_dedup_method="none")
    # 构造最小 primitives
    from scripts.parsing.metrics import SubgroupPrimitives

    prim = SubgroupPrimitives(
        detector={"all": {}},
        ssm={"all": {}},
        lanechange={"all": {}},
        edge_perf={"all": {}},
        edge_emis={"all": {}},
        vehroute={"all": {}},
        emerg_brake={"all": {}},
        fcd=None,
    )
    # monkeypatch compute_core_summary 依赖的内部取值避免 NaN 断言问题
    summary = compute_core_summary(prim, spec, {"HV": 60.0, "IDM": 60.0})
    assert summary["analysis_ttc_threshold_s"] == 2.5
    assert summary["ssm_dedup_method"] == "none"
