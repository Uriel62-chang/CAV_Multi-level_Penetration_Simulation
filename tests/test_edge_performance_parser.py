"""Edge performance parser unit tests — veh-km and timeLoss extraction."""

import math
import os

from scripts.parsing.edge_performance import parse_edge_performance

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_minimal_veh_km_calculation():
    """Real SUMO 1.27.1 edgeData performance output — correct veh-km and timeLoss."""
    result = parse_edge_performance(
        os.path.join(FIXTURES, "edge_performance_minimal.xml"),
    )
    assert result["parse_success"] is True

    # Interval 1: speed=10.20, sampledSeconds=19100.29 → dist = 194822.958 m = 194.823 km
    # Interval 2: speed=10.95, sampledSeconds=11454.87 → dist = 125430.8265 m = 125.431 km
    # Total = 320.254 km (approximately)
    expected_km = (10.20 * 19100.29 + 10.95 * 11454.87) / 1000.0
    assert math.isclose(result["total_vehicle_km"], expected_km, rel_tol=1e-6)

    # timeLoss: 13074.01 + 7583.95 = 20657.96
    assert math.isclose(result["total_time_loss_s"], 13074.01 + 7583.95, rel_tol=1e-6)

    assert result["total_vehicle_km"] > 0
    assert result["total_time_loss_s"] > 0


def test_warmup_filters_complete_intervals():
    result = parse_edge_performance(
        os.path.join(FIXTURES, "edge_performance_minimal.xml"),
        warmup_period=420.0,
    )
    expected_km = 10.95 * 11454.87 / 1000.0
    assert math.isclose(result["total_vehicle_km"], expected_km, rel_tol=1e-6)
    assert math.isclose(result["total_time_loss_s"], 7583.95, rel_tol=1e-6)


def test_empty_file_returns_zero():
    """Empty meandata: valid XML but no data → returns 0.0, not NaN."""
    result = parse_edge_performance(
        os.path.join(FIXTURES, "edge_performance_empty.xml"),
    )
    assert result["parse_success"] is True
    assert result["total_vehicle_km"] == 0.0
    assert result["total_time_loss_s"] == 0.0


def test_missing_file_returns_nan():
    """Non-existent file should return NaN, parse_success=False."""
    result = parse_edge_performance(
        os.path.join(FIXTURES, "nonexistent.xml"),
    )
    assert result["parse_success"] is False
    assert math.isnan(result["total_vehicle_km"])


def test_missing_fields():
    """Edge without speed or sampledSeconds: 记录不完整 → fail-closed（P1-1）。

    缺失必需属性（speed/sampledSeconds）的 edge 计为 invalid 记录并跳过；
    parse_success=False。其余有效记录仍累计。
    """
    result = parse_edge_performance(
        os.path.join(FIXTURES, "edge_performance_missing.xml"),
    )
    assert result["parse_success"] is False
    assert result["invalid_record_count"] >= 1
    # 仅 interval 2 有完整数据：speed=10.95, sampledSeconds=11454.87
    expected_km = (10.95 * 11454.87) / 1000.0
    assert math.isclose(result["total_vehicle_km"], expected_km, rel_tol=1e-6)
    # interval 1 的 edge 缺 speed → 整条跳过（含其 timeLoss 13074.01）；
    # interval 2 的 timeLoss=7583.95 仍计入
    assert math.isclose(result["total_time_loss_s"], 7583.95, rel_tol=1e-6)


def test_malformed_xml_returns_nan():
    """Malformed XML should not crash; parse_success=False."""
    result = parse_edge_performance(
        os.path.join(FIXTURES, "edge_performance_malformed.xml"),
    )
    assert result["parse_success"] is False
    assert math.isnan(result["total_vehicle_km"])


def test_idempotent():
    """Calling parse_edge_performance twice should give identical results."""
    path = os.path.join(FIXTURES, "edge_performance_minimal.xml")
    r1 = parse_edge_performance(path)
    r2 = parse_edge_performance(path)
    for k in r1:
        v1, v2 = r1[k], r2[k]
        if isinstance(v1, float) and math.isnan(v1) and math.isnan(v2):
            continue
        assert v1 == v2, f"Key {k}: {v1} != {v2}"
