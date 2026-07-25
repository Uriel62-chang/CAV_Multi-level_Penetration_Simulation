"""Edge emissions parser unit tests — CO2/NOx/PMx/fuel extraction and unit conversion."""

import math
import os

from scripts.parsing.edge_emissions import parse_edge_emissions

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_minimal_emissions_units():
    """Real SUMO 1.27.1 edgeData emissions output — verify unit conversions."""
    result = parse_edge_emissions(
        os.path.join(FIXTURES, "edge_emissions_minimal.xml"),
    )
    assert result["parse_success"] is True

    # Interval 1: CO2_abs=52065938.32 mg, NOx_abs=20112.49 mg, PMx_abs=5366.66 mg,
    #              fuel_abs=16878966.62 mg
    # Interval 2: CO2_abs=31126175.71 mg, NOx_abs=12004.36 mg, PMx_abs=3399.24 mg,
    #              fuel_abs=10090615.01 mg
    total_co2_mg = 52065938.32 + 31126175.71
    total_nox_mg = 20112.49 + 12004.36
    total_pmx_mg = 5366.66 + 3399.24
    total_fuel_mg = 16878966.62 + 10090615.01

    # CO2: mg → kg (/ 1e6)
    expected_co2_kg = total_co2_mg / 1e6
    assert math.isclose(result["total_CO2_kg"], expected_co2_kg, rel_tol=1e-6)

    # NOx: mg → g (/ 1e3)
    expected_nox_g = total_nox_mg / 1e3
    assert math.isclose(result["total_NOx_g"], expected_nox_g, rel_tol=1e-6)

    # PMx: mg → g (/ 1e3)
    expected_pmx_g = total_pmx_mg / 1e3
    assert math.isclose(result["total_PMx_g"], expected_pmx_g, rel_tol=1e-6)

    # fuel: mg → kg (/ 1e6)
    expected_fuel_kg = total_fuel_mg / 1e6
    assert math.isclose(result["total_fuel_kg"], expected_fuel_kg, rel_tol=1e-6)

    # Sanity: values should be positive
    assert result["total_CO2_kg"] > 0
    assert result["total_NOx_g"] > 0
    assert result["total_PMx_g"] > 0
    assert result["total_fuel_kg"] > 0


def test_empty_file_returns_zero():
    """Empty meandata: valid XML but no data → returns 0.0, not NaN."""
    result = parse_edge_emissions(
        os.path.join(FIXTURES, "edge_emissions_empty.xml"),
    )
    assert result["parse_success"] is True
    assert result["total_CO2_kg"] == 0.0
    assert result["total_NOx_g"] == 0.0
    assert result["total_PMx_g"] == 0.0
    assert result["total_fuel_kg"] == 0.0


def test_missing_file_returns_nan():
    """Non-existent file should return NaN, parse_success=False."""
    result = parse_edge_emissions(
        os.path.join(FIXTURES, "nonexistent.xml"),
    )
    assert result["parse_success"] is False
    assert math.isnan(result["total_CO2_kg"])


def test_missing_fields_default_to_zero_contribution():
    """Edge without emission attributes: skip, parse whatever else is there."""
    result = parse_edge_emissions(
        os.path.join(FIXTURES, "edge_emissions_missing.xml"),
    )
    assert result["parse_success"] is True
    # All emission attributes missing → totals should be 0.0, but parse_success=True
    # (file was valid, just no emission data)
    assert result["total_CO2_kg"] == 0.0
    assert result["total_NOx_g"] == 0.0
    assert result["total_PMx_g"] == 0.0
    assert result["total_fuel_kg"] == 0.0


def test_malformed_xml_returns_nan():
    """Malformed XML should not crash; parse_success=False."""
    result = parse_edge_emissions(
        os.path.join(FIXTURES, "edge_emissions_malformed.xml"),
    )
    assert result["parse_success"] is False
    assert math.isnan(result["total_CO2_kg"])


def test_idempotent():
    """Calling parse_edge_emissions twice should give identical results."""
    path = os.path.join(FIXTURES, "edge_emissions_minimal.xml")
    r1 = parse_edge_emissions(path)
    r2 = parse_edge_emissions(path)
    for k in r1:
        v1, v2 = r1[k], r2[k]
        if isinstance(v1, float) and math.isnan(v1) and math.isnan(v2):
            continue
        assert v1 == v2, f"Key {k}: {v1} != {v2}"
