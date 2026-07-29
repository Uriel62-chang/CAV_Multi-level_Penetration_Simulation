"""v0.4.1 stage2 edge perf/emis/detector subgroup additivity tests"""

from pathlib import Path

from scripts.parsing.detector import parse_detector_subgroup
from scripts.parsing.edge_emissions import parse_edge_emissions
from scripts.parsing.edge_performance import parse_edge_performance

_BASE = Path("/tmp/v4_1_probes_multi3/probe_multi_s0")


def _assert_additive(all_val, hv_val, cav_val, rel_tol=5e-5, abs_tol=1e-9):
    summed = hv_val + cav_val
    if all_val == 0.0 and summed == 0.0:
        return
    rel_err = abs(summed - all_val) / max(abs(all_val), 1e-6)
    assert rel_err <= rel_tol, (
        f"HV+CAV={summed}, all={all_val}, rel_err={rel_err}"
    )


def test_edge_perf_veh_km_additivity():
    all_r = parse_edge_performance(str(_BASE / "performance_all.xml"), warmup_period=60)
    hv_r = parse_edge_performance(str(_BASE / "performance_HV.xml"), warmup_period=60)
    cav_r = parse_edge_performance(str(_BASE / "performance_CAV.xml"), warmup_period=60)

    assert all_r["parse_success"] is True
    assert hv_r["parse_success"] is True
    assert cav_r["parse_success"] is True

    _assert_additive(all_r["total_vehicle_km"], hv_r["total_vehicle_km"], cav_r["total_vehicle_km"])
    _assert_additive(all_r["non_internal_edge_vehicle_km"],
                     hv_r["non_internal_edge_vehicle_km"],
                     cav_r["non_internal_edge_vehicle_km"])
    _assert_additive(all_r["total_time_loss_s"], hv_r["total_time_loss_s"], cav_r["total_time_loss_s"],
                     rel_tol=1e-3, abs_tol=1e-3)


def test_edge_emis_additivity():
    all_r = parse_edge_emissions(str(_BASE / "emissions_all.xml"), warmup_period=60)
    hv_r = parse_edge_emissions(str(_BASE / "emissions_HV.xml"), warmup_period=60)
    cav_r = parse_edge_emissions(str(_BASE / "emissions_CAV.xml"), warmup_period=60)

    for metric in ["total_CO2_kg", "total_NOx_g", "total_PMx_g", "total_fuel_kg"]:
        _assert_additive(all_r[metric], hv_r[metric], cav_r[metric])


def test_detector_subgroup():
    det_all = [str(_BASE / "detector_lane0_all.xml")]
    det_hv = [str(_BASE / "detector_lane0_HV.xml")]
    det_cav = [str(_BASE / "detector_lane0_CAV.xml")]

    result = parse_detector_subgroup(det_all, det_hv, det_cav, warmup_period=60)

    assert result["all"]["parse_success"] is True
    assert result["HV"]["parse_success"] is True
    assert result["CAV"]["parse_success"] is True

    assert result["all"]["mean_flow_veh_h"] >= 0
    assert result["HV"]["mean_flow_veh_h"] >= 0
    assert result["CAV"]["mean_flow_veh_h"] >= 0
    assert result["all"]["window_count"] > 0


def test_subgroup_keys():
    result = parse_detector_subgroup(
        [str(_BASE / "detector_lane0_all.xml")],
        [str(_BASE / "detector_lane0_HV.xml")],
        [str(_BASE / "detector_lane0_CAV.xml")],
    )
    for label in ("all", "HV", "CAV"):
        for key in ("mean_flow_veh_h", "max_flow_veh_h", "mean_speed_m_s",
                    "speed_variance", "window_count", "parse_success"):
            assert key in result[label], f"{label} missing {key}"
