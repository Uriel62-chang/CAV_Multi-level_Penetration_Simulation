"""v0.4.2 P0-7 回归测试：排放 non-internal 双累计。"""

import xml.etree.ElementTree as ET

from scripts.parsing.edge_emissions import parse_edge_emissions


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
