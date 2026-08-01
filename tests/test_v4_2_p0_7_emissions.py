"""v0.4.2 P0-7 回归测试：排放 non-internal 双累计。"""

import xml.etree.ElementTree as ET

from scripts.parsing.edge_emissions import parse_edge_emissions
from scripts.parsing.metrics import (
    SubgroupPrimitives,
    compute_core_summary,
    compute_subgroup_records,
)
from scripts.run_spec import PIPELINE_V4_2, RunSpec


def _write_emissions(path, edges):
    """edges: list of (edge_id, co2_mg, nox_mg)。"""
    root = ET.Element("edgeData")
    interval = ET.SubElement(root, "interval", {"begin": "600", "end": "900"})
    for eid, co2, nox in edges:
        ET.SubElement(
            interval,
            "edge",
            {"id": eid, "CO2_abs": str(co2), "NOx_abs": str(nox), "PMx_abs": "0", "fuel_abs": "0"},
        )
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def test_dual_accumulation_separates_internal(tmp_path):
    path = tmp_path / "emissions.xml"
    # 普通 edge 1000 mg CO2；internal edge（:开头）500 mg
    _write_emissions(path, [("e0", 1000.0, 10.0), (":e0_0", 500.0, 5.0)])
    r = parse_edge_emissions(str(path), warmup_period=600)
    assert r["total_CO2_kg"] == 1500.0 / 1e6
    assert r["non_internal_CO2_kg"] == 1000.0 / 1e6
    assert r["total_NOx_g"] == 15.0 / 1e3
    assert r["non_internal_NOx_g"] == 10.0 / 1e3


def test_no_internal_edges_identical(tmp_path):
    path = tmp_path / "emissions.xml"
    _write_emissions(path, [("e0", 100.0, 1.0), ("e1", 200.0, 2.0)])
    r = parse_edge_emissions(str(path), warmup_period=600)
    assert r["total_CO2_kg"] == r["non_internal_CO2_kg"] == 300.0 / 1e6


def test_warmup_filter_applies(tmp_path):
    path = tmp_path / "emissions.xml"
    root = ET.Element("edgeData")
    # warmup 前 interval 应被排除
    iv1 = ET.SubElement(root, "interval", {"begin": "0", "end": "300"})
    ET.SubElement(
        iv1, "edge", {"id": "e0", "CO2_abs": "999", "NOx_abs": "9", "PMx_abs": "0", "fuel_abs": "0"}
    )
    iv2 = ET.SubElement(root, "interval", {"begin": "600", "end": "900"})
    ET.SubElement(
        iv2, "edge", {"id": "e0", "CO2_abs": "100", "NOx_abs": "1", "PMx_abs": "0", "fuel_abs": "0"}
    )
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    r = parse_edge_emissions(str(path), warmup_period=600)
    assert r["total_CO2_kg"] == 100.0 / 1e6  # 仅 warmup 后


# ── P0-4：subgroup 排放口径与 core 一致（non-internal 主口径 + 全路网次要） ──


def _spec() -> RunSpec:
    return RunSpec(
        scenario="scenario_2",
        model="IDM",
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


def _emission_primitives():
    def _ee(total_co2, ni_co2):
        return {
            "total_CO2_kg": total_co2,
            "non_internal_CO2_kg": ni_co2,
            "total_NOx_g": 0.0,
            "non_internal_NOx_g": 0.0,
            "total_PMx_g": 0.0,
            "non_internal_PMx_g": 0.0,
            "total_fuel_kg": 0.0,
            "non_internal_fuel_kg": 0.0,
        }

    return SubgroupPrimitives(
        detector={"all": {}},
        ssm={"all": {}},
        lanechange={"all": {}},
        edge_perf={
            "all": {"total_vehicle_km": 120.0, "non_internal_edge_vehicle_km": 100.0},
            "HV": {"total_vehicle_km": 60.0, "non_internal_edge_vehicle_km": 50.0},
            "CAV": {"total_vehicle_km": 60.0, "non_internal_edge_vehicle_km": 50.0},
        },
        edge_emis={
            "all": _ee(1.5e-3, 1.0e-3),
            "HV": _ee(0.75e-3, 0.6e-3),
            "CAV": _ee(0.75e-3, 0.4e-3),
        },
        vehroute={"all": {}, "HV": {}, "CAV": {}},
        emerg_brake={"all": {}},
        fcd=None,
    )


def _subgroup_metric(records, group_value, metric_name):
    for r in records:
        if (
            r["metric_family"] == "emissions"
            and r["group_value"] == group_value
            and r["metric_name"] == metric_name
        ):
            return r["metric_value"]
    raise AssertionError(f"missing subgroup metric {group_value}/{metric_name}")


def test_subgroup_emission_main_ratio_uses_non_internal_scope():
    """P0-4：subgroup CO2_g_per_veh_km 必须用 non-internal 排放 / non-internal veh-km（与 core 主口径一致）。"""
    prim = _emission_primitives()
    refs = {"HV": 60.0, "IDM": 58.0}
    records = compute_subgroup_records(prim, _spec(), refs)
    # HV: 0.6e-3 kg / 50 km → 0.6e-3*1000/50 = 0.012 g/veh-km
    assert _subgroup_metric(records, "HV", "CO2_g_per_veh_km") == 0.6e-3 * 1000.0 / 50.0
    assert _subgroup_metric(records, "CAV", "CO2_g_per_veh_km") == 0.4e-3 * 1000.0 / 50.0


def test_subgroup_emission_whole_network_ratio_secondary():
    """P0-4：全路网次要强度 = all-edge 排放 / all-edge veh-km。"""
    prim = _emission_primitives()
    records = compute_subgroup_records(prim, _spec(), {"HV": 60.0, "IDM": 58.0})
    assert (
        _subgroup_metric(records, "HV", "whole_network_CO2_g_per_veh_km") == 0.75e-3 * 1000.0 / 60.0
    )
    assert (
        _subgroup_metric(records, "CAV", "whole_network_CO2_g_per_veh_km")
        == 0.75e-3 * 1000.0 / 60.0
    )


def test_subgroup_emission_absolute_non_internal_present():
    """P0-4：non-internal 绝对量进入 subgroup 长表。"""
    prim = _emission_primitives()
    records = compute_subgroup_records(prim, _spec(), {"HV": 60.0, "IDM": 58.0})
    assert _subgroup_metric(records, "HV", "non_internal_CO2_kg") == 0.6e-3
    assert _subgroup_metric(records, "CAV", "non_internal_CO2_kg") == 0.4e-3


def test_core_and_subgroup_emission_ratio_consistent():
    """P0-4：同一 run 内 core 与 subgroup 的同名主强度指标口径一致。"""
    prim = _emission_primitives()
    refs = {"HV": 60.0, "IDM": 58.0}
    core = compute_core_summary(prim, _spec(), refs)
    # core 主口径 = all 级 non-internal/non-internal；HV/CAV 子群按各自 ni 分子分母
    assert core["CO2_g_per_veh_km"] == 1.0e-3 * 1000.0 / 100.0
    assert core["whole_network_CO2_g_per_veh_km"] == 1.5e-3 * 1000.0 / 120.0
    assert "non_internal_CO2_kg" in core
    assert core["non_internal_CO2_kg"] == 1.0e-3
