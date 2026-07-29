"""阶段 2 指标计算：从 parser primitives 派生 core summary 和 subgroup 记录。"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SubgroupPrimitives:
    detector: dict
    ssm: dict
    lanechange: dict
    edge_perf: dict
    edge_emis: dict
    vehroute: dict
    emerg_brake: dict
    fcd: dict | None = None


def _safe_div(numerator, denominator):
    if denominator is None or (isinstance(denominator, float) and math.isnan(denominator)):
        return float("nan")
    if denominator == 0:
        return float("nan")
    if isinstance(numerator, float) and math.isnan(numerator):
        return float("nan")
    return numerator / denominator


def _per_1000_veh_km(value, total_veh_km):
    if isinstance(total_veh_km, float) and math.isnan(total_veh_km):
        return float("nan")
    if total_veh_km is None or total_veh_km <= 0:
        return float("nan")
    if isinstance(value, float) and math.isnan(value):
        return float("nan")
    return value / total_veh_km * 1000.0


def compute_core_summary(primitives, spec, free_flow_refs):
    """Compute the all-level flat core summary dict, compatible with current parse_run_outputs."""
    import math as _math

    warmup_period = spec.warmup
    sim_end_time = spec.simulation_end
    net_scenario = spec.scenario

    # Extract all-level values from primitives
    det = primitives.detector.get("all", {})
    ssm_all = primitives.ssm.get("all", {})
    lc = primitives.lanechange.get("all", {})
    ep = primitives.edge_perf.get("all", {})
    ee = primitives.edge_emis.get("all", {})
    vr = primitives.vehroute.get("all", {})
    eb = primitives.emerg_brake.get("all", {})

    total_veh_km = ep.get("total_vehicle_km", float("nan"))
    ttc_per_1000 = _per_1000_veh_km(ssm_all.get("ttc_conflict_event_count", 0), total_veh_km)
    eb_per_1000 = _per_1000_veh_km(eb.get("emergency_braking_count", 0), total_veh_km)
    lc_per_1000 = _per_1000_veh_km(lc.get("lane_change_count", 0), total_veh_km)
    co2_per = _safe_div(ee.get("total_CO2_kg", 0) * 1000.0, total_veh_km)
    nox_per = _safe_div(ee.get("total_NOx_g", 0) * 1000.0, total_veh_km)
    pmx_per = _safe_div(ee.get("total_PMx_g", 0) * 1000.0, total_veh_km)
    fuel_per = _safe_div(ee.get("total_fuel_kg", 0) * 1000.0, total_veh_km)
    tl_per = _safe_div(ep.get("total_time_loss_s", 0), total_veh_km)

    hv_ref = free_flow_refs.get("HV", float("nan"))
    ml = vr.get("mean_lap_time_s", float("nan"))
    p95 = vr.get("p95_lap_time_s", float("nan"))
    mean_delay = ml - hv_ref if not _math.isnan(ml) and not _math.isnan(hv_ref) else float("nan")
    p95_delay = p95 - hv_ref if not _math.isnan(p95) and not _math.isnan(hv_ref) else float("nan")

    # Build flat dict compatible with current parse_run_outputs
    return {
        "run_id": spec.run_id,
        "scenario": net_scenario,
        "model": spec.model,
        "vehN": spec.vehicle_count,
        "pCAV": spec.pcav,
        "seed": spec.seed,
        "requested_pcav": spec.requested_pcav,
        "realized_pcav": spec.realized_pcav,
        "cav_count": spec.cav_count,
        "hv_count": spec.hv_count,
        "assignment_seed": spec.seed,
        "sumo_seed": spec.sumo_seed,
        "step_length_s": spec.step_length,
        "warmup_period_s": warmup_period,
        "simulation_end_s": sim_end_time,
        "detector_frequency_s": spec.detector_frequency,
        "edge_data_frequency_s": spec.edge_data_frequency,
        "ssm_capture_ttc_threshold_s": spec.ssm_capture_ttc_threshold_s,
        "ssm_capture_drac_threshold_mps2": spec.ssm_capture_drac_threshold_mps2,
        "with_internal": spec.with_internal,
        "mean_flow_veh_h": det.get("mean_flow_veh_h", float("nan")),
        "max_flow_veh_h": det.get("max_flow_veh_h", float("nan")),
        "mean_speed_m_s": det.get("mean_speed_m_s", float("nan")),
        "detector_mean_speed_temporal_variance": det.get("speed_variance", float("nan")),
        "detector_speed_window_count": det.get("window_count", 0),
        "det_xml": "",
        "ssm_raw_record_count": ssm_all.get("ssm_raw_record_count", 0),
        "ssm_invalid_record_count": ssm_all.get("ssm_invalid_record_count", 0),
        "ssm_warmup_filtered_count": ssm_all.get("ssm_warmup_filtered_count", 0),
        "ssm_valid_record_count": ssm_all.get("ssm_valid_record_count", 0),
        "ssm_mirrored_record_count": ssm_all.get("ssm_mirrored_record_count", 0),
        "ttc_conflict_event_count": ssm_all.get("ttc_conflict_event_count", 0),
        "min_ttc_s": ssm_all.get("min_ttc_s", float("nan")),
        "ttc_affected_vehicle_count": ssm_all.get("ttc_involved_vehicle_count", 0),
        "drac_conflict_event_count": ssm_all.get("drac_conflict_event_count", 0),
        "max_drac_mps2": ssm_all.get("max_drac_mps2", float("nan")),
        "emergency_braking_count": eb.get("emergency_braking_count", 0),
        "emergency_braking_affected_vehicle_count": eb.get(
            "emergency_braking_affected_vehicle_count", 0
        ),
        "lane_change_count": lc.get("lane_change_count", 0),
        "unsafe_lc_gap_count": lc.get("unsafe_lc_gap_count", 0),
        "unsafe_lc_gap_ratio": lc.get("unsafe_lc_gap_ratio", float("nan")),
        "total_CO2_kg": ee.get("total_CO2_kg", float("nan")),
        "total_NOx_g": ee.get("total_NOx_g", float("nan")),
        "total_PMx_g": ee.get("total_PMx_g", float("nan")),
        "total_fuel_kg": ee.get("total_fuel_kg", float("nan")),
        "total_vehicle_km": total_veh_km,
        "non_internal_edge_vehicle_km": ep.get("non_internal_edge_vehicle_km", float("nan")),
        "total_time_loss_s": ep.get("total_time_loss_s", float("nan")),
        "completed_lap_count": vr.get("completed_lap_count", 0),
        "mean_lap_time_s": vr.get("mean_lap_time_s", float("nan")),
        "median_lap_time_s": vr.get("median_lap_time_s", float("nan")),
        "p95_lap_time_s": vr.get("p95_lap_time_s", float("nan")),
        "lap_time_std_s": vr.get("lap_time_std_s", float("nan")),
        "ttc_events_per_1000_veh_km": ttc_per_1000,
        "whole_network_ttc_events_per_1000_non_internal_edge_veh_km": _per_1000_veh_km(
            ssm_all.get("ttc_conflict_event_count", 0),
            ep.get("non_internal_edge_vehicle_km", float("nan")),
        ),
        "emergency_brakes_per_1000_veh_km": eb_per_1000,
        "lane_changes_per_1000_veh_km": lc_per_1000,
        "CO2_g_per_veh_km": co2_per,
        "NOx_mg_per_veh_km": nox_per,
        "PMx_mg_per_veh_km": pmx_per,
        "fuel_g_per_veh_km": fuel_per,
        "time_loss_s_per_veh_km": tl_per,
        "mean_lap_delay_s": mean_delay,
        "p95_lap_delay_s": p95_delay,
        "ssm_parse_success": ssm_all.get("parse_success", False),
        "lc_parse_success": lc.get("parse_success", False),
        "ep_parse_success": ep.get("parse_success", False),
        "ee_parse_success": ee.get("parse_success", False),
        "vr_parse_success": vr.get("parse_success", False),
        "fcd_parse_success": primitives.fcd.get("all", {}).get("parse_success", True)
        if primitives.fcd
        else True,
    }


def compute_subgroup_records(primitives, spec, free_flow_refs):
    """Generate subgroup long-format records list."""
    import math as _math

    records = []
    rid = spec.run_id
    ident = {
        "run_id": rid,
        "scenario": spec.scenario,
        "model": spec.model,
        "requested_pcav": spec.requested_pcav,
        "realized_pcav": spec.realized_pcav,
        "cav_count": spec.cav_count,
        "hv_count": spec.hv_count,
        "vehN": spec.vehicle_count,
        "assignment_seed": spec.seed,
        "sumo_seed": spec.sumo_seed,
    }

    def _add(group_dim, group_val, family, metric_name, metric_value):
        records.append(
            {
                **ident,
                "metric_family": family,
                "group_dimension": group_dim,
                "group_value": group_val,
                "metric_name": metric_name,
                "metric_value": metric_value,
            }
        )

    # Capacity: vehicle_type → HV, CAV
    for vt in ("HV", "CAV"):
        det = primitives.detector.get(vt, {})
        for key in (
            "mean_flow_veh_h",
            "max_flow_veh_h",
            "mean_speed_m_s",
            "speed_variance",
            "window_count",
        ):
            _add("vehicle_type", vt, "capacity", key, det.get(key, float("nan")))

    # Safety SSM: pair types
    for pair in ("HV_HV", "HV_CAV", "CAV_CAV"):
        key = f"pair_{pair}"
        data = primitives.ssm.get(key, {})
        _add(
            "pair_type",
            pair.replace("_", "-"),
            "safety_ssm",
            "ttc_event_count",
            data.get("ttc_event_count", 0),
        )
        _add(
            "pair_type",
            pair.replace("_", "-"),
            "safety_ssm",
            "drac_event_count",
            data.get("drac_event_count", 0),
        )

    # Safety SSM: role types
    for role in ("f_HV_l_HV", "f_HV_l_CAV", "f_CAV_l_HV", "f_CAV_l_CAV"):
        key = f"role_{role}"
        data = primitives.ssm.get(key, {})
        _add("role_type", role, "safety_ssm", "ttc_event_count", data.get("ttc_event_count", 0))
        _add("role_type", role, "safety_ssm", "drac_event_count", data.get("drac_event_count", 0))

    # Safety EB
    for vt in ("HV", "CAV"):
        eb = primitives.emerg_brake.get(vt, {})
        _add(
            "vehicle_type",
            vt,
            "safety_eb",
            "emergency_braking_count",
            eb.get("emergency_braking_count", 0),
        )
        _add(
            "vehicle_type",
            vt,
            "safety_eb",
            "affected_vehicle_count",
            eb.get("emergency_braking_affected_vehicle_count", 0),
        )

    # Lanechange
    for vt in ("HV", "CAV"):
        lc = primitives.lanechange.get(vt, {})
        _add("vehicle_type", vt, "lanechange", "lane_change_count", lc.get("lane_change_count", 0))
        _add(
            "vehicle_type",
            vt,
            "lanechange",
            "unsafe_lc_gap_count",
            lc.get("unsafe_lc_gap_count", 0),
        )
        _add(
            "vehicle_type",
            vt,
            "lanechange",
            "unsafe_lc_gap_ratio",
            lc.get("unsafe_lc_gap_ratio", float("nan")),
        )

    # Emissions
    for vt in ("HV", "CAV"):
        ee = primitives.edge_emis.get(vt, {})
        ep = primitives.edge_perf.get(vt, {})
        veh_km = ep.get("total_vehicle_km", float("nan"))
        for key in ("total_CO2_kg", "total_NOx_g", "total_PMx_g", "total_fuel_kg"):
            _add("vehicle_type", vt, "emissions", key, ee.get(key, float("nan")))
        _add(
            "vehicle_type",
            vt,
            "emissions",
            "CO2_g_per_veh_km",
            _safe_div(ee.get("total_CO2_kg", 0) * 1000.0, veh_km),
        )
        _add(
            "vehicle_type",
            vt,
            "emissions",
            "NOx_mg_per_veh_km",
            _safe_div(ee.get("total_NOx_g", 0) * 1000.0, veh_km),
        )
        _add(
            "vehicle_type",
            vt,
            "emissions",
            "PMx_mg_per_veh_km",
            _safe_div(ee.get("total_PMx_g", 0) * 1000.0, veh_km),
        )
        _add(
            "vehicle_type",
            vt,
            "emissions",
            "fuel_g_per_veh_km",
            _safe_div(ee.get("total_fuel_kg", 0) * 1000.0, veh_km),
        )

    # Efficiency + Delay
    hv_ref = free_flow_refs.get("HV", float("nan"))
    model_ref = free_flow_refs.get(spec.model, float("nan"))
    for vt in ("HV", "CAV"):
        ep = primitives.edge_perf.get(vt, {})
        vr = primitives.vehroute.get(vt, {})
        for key in ("total_vehicle_km", "non_internal_edge_vehicle_km", "total_time_loss_s"):
            _add("vehicle_type", vt, "efficiency", key, ep.get(key, float("nan")))
        _add(
            "vehicle_type",
            vt,
            "efficiency",
            "time_loss_s_per_veh_km",
            _safe_div(ep.get("total_time_loss_s", 0), ep.get("total_vehicle_km", float("nan"))),
        )
        for key in (
            "completed_lap_count",
            "mean_lap_time_s",
            "median_lap_time_s",
            "p95_lap_time_s",
            "lap_time_std_s",
        ):
            _add("vehicle_type", vt, "efficiency", key, vr.get(key, float("nan")))

        ml_sub = vr.get("mean_lap_time_s", float("nan"))
        ref = hv_ref if vt == "HV" else model_ref
        delay = ml_sub - ref if not _math.isnan(ml_sub) and not _math.isnan(ref) else float("nan")
        _add("vehicle_type", vt, "delay", "mean_lap_delay_s", delay)

        p95_sub = vr.get("p95_lap_time_s", float("nan"))
        delay_p95 = (
            p95_sub - ref if not _math.isnan(p95_sub) and not _math.isnan(ref) else float("nan")
        )
        _add("vehicle_type", vt, "delay", "p95_lap_delay_s", delay_p95)

    # FCD headway
    if primitives.fcd is not None:
        for vt in ("HV", "CAV"):
            fcd_vt = primitives.fcd.get(vt, {})
            for key in (
                "mean_thw_s",
                "median_thw_s",
                "p05_thw_s",
                "thw_lt_1s_ratio",
                "valid_thw_sample_count",
                "low_speed_excluded_count",
                "no_leader_count",
                "self_leader_count",
            ):
                _add("vehicle_type", vt, "headway", key, fcd_vt.get(key, float("nan")))

    return records


def validate_subgroup_invariants(primitives):
    """Validate additivity invariants. Returns list of error strings."""
    errors = []

    # Check HV/CAV parser success (not just all); empty subgroups
    # naturally have 0 data but parse_success=True after vehroute fix.
    for group_name, prim_key, parser_name in [
        ("HV", "edge_perf", "edge_performance"),
        ("CAV", "edge_perf", "edge_performance"),
        ("HV", "edge_emis", "edge_emissions"),
        ("CAV", "edge_emis", "edge_emissions"),
        ("HV", "lanechange", "lanechange"),
        ("CAV", "lanechange", "lanechange"),
        ("HV", "vehroute", "vehroute"),
        ("CAV", "vehroute", "vehroute"),
    ]:
        sub = primitives.__dict__.get(prim_key, {}).get(group_name, {})
        if sub.get("parse_success") is not True:
            errors.append(f"subgroup {group_name} {parser_name} parse_success is not True")
            continue
        for metric_key in ("total_vehicle_km", "total_CO2_kg", "completed_lap_count"):
            if metric_key in sub:
                val = sub[metric_key]
                import math as _m

                if isinstance(val, float) and _m.isnan(val):
                    errors.append(
                        f"subgroup {group_name} {parser_name} {metric_key} is NaN "
                        "(valid data expected, not parser failure)"
                    )

    # Check detector subgroup
    for group_name in ("HV", "CAV"):
        det_sub = primitives.detector.get(group_name, {})
        if det_sub.get("parse_success") is not True:
            errors.append(f"detector subgroup {group_name} parse_success is not True")

    def _check_additive(all_dict, hv_dict, cav_dict, key, rel_tol, abs_tol):
        av = all_dict.get(key, 0)
        hv_val = hv_dict.get(key, 0)
        cv_val = cav_dict.get(key, 0)
        import math as _m

        if av is None or hv_val is None or cv_val is None:
            return
        if isinstance(av, float) and _m.isnan(av):
            return
        if isinstance(hv_val, float) and _m.isnan(hv_val):
            return
        if isinstance(cv_val, float) and _m.isnan(cv_val):
            return
        av = float(av)
        hv_val = float(hv_val)
        cv_val = float(cv_val)
        sv = hv_val + cv_val
        if av == 0 and sv == 0:
            return
        if abs(sv - av) <= abs_tol:
            return
        rel_err = abs(sv - av) / max(abs(av), 1e-6)
        if rel_err > rel_tol:
            errors.append(f"{key}: HV+CAV={sv}, all={av}, rel_err={rel_err:.2e}")

    ep_all = primitives.edge_perf.get("all", {})
    ep_hv = primitives.edge_perf.get("HV", {})
    ep_cav = primitives.edge_perf.get("CAV", {})
    for key in ("total_vehicle_km", "non_internal_edge_vehicle_km"):
        _check_additive(ep_all, ep_hv, ep_cav, key, 5e-5, 1e-6)
    _check_additive(ep_all, ep_hv, ep_cav, "total_time_loss_s", 1e-6, 1e-3)

    ee_all = primitives.edge_emis.get("all", {})
    ee_hv = primitives.edge_emis.get("HV", {})
    ee_cav = primitives.edge_emis.get("CAV", {})
    for key in ("total_CO2_kg", "total_NOx_g", "total_PMx_g", "total_fuel_kg"):
        _check_additive(ee_all, ee_hv, ee_cav, key, 1e-5, 1e-9)

    # Exact counts
    for src_name, src_key in [
        ("lanechange", "lane_change_count"),
        ("emerg_brake", "emergency_braking_count"),
        ("vehroute", "completed_lap_count"),
    ]:
        a = primitives.__dict__[src_name].get("all", {}).get(src_key, 0) or 0
        h = primitives.__dict__[src_name].get("HV", {}).get(src_key, 0) or 0
        c = primitives.__dict__[src_name].get("CAV", {}).get(src_key, 0) or 0
        if h + c != a:
            errors.append(f"{src_name}.{src_key}: HV({h})+CAV({c}) != all({a})")

    # SSM pair closure
    ssm_all_ttc = primitives.ssm.get("all", {}).get("ttc_conflict_event_count", 0)
    ssm_all_drac = primitives.ssm.get("all", {}).get("drac_conflict_event_count", 0)
    pair_ttc = 0
    pair_drac = 0
    for pair in ("HV_HV", "HV_CAV", "CAV_CAV"):
        pair_ttc += primitives.ssm.get(f"pair_{pair}", {}).get("ttc_event_count", 0) or 0
        pair_drac += primitives.ssm.get(f"pair_{pair}", {}).get("drac_event_count", 0) or 0
    if pair_ttc != ssm_all_ttc:
        errors.append(f"SSM pair TTC sum {pair_ttc} != all {ssm_all_ttc}")
    if pair_drac != ssm_all_drac:
        errors.append(f"SSM pair DRAC sum {pair_drac} != all {ssm_all_drac}")

    # SSM role closure
    role_ttc = 0
    role_drac = 0
    for role in ("f_HV_l_HV", "f_HV_l_CAV", "f_CAV_l_HV", "f_CAV_l_CAV"):
        role_ttc += primitives.ssm.get(f"role_{role}", {}).get("ttc_event_count", 0) or 0
        role_drac += primitives.ssm.get(f"role_{role}", {}).get("drac_event_count", 0) or 0
    uncl_ttc = primitives.ssm.get("unclassified", {}).get("ttc_event_count", 0) or 0
    uncl_drac = primitives.ssm.get("unclassified", {}).get("drac_event_count", 0) or 0
    if role_ttc + uncl_ttc != ssm_all_ttc:
        errors.append(f"SSM role+uncl TTC {role_ttc + uncl_ttc} != all {ssm_all_ttc}")
    if role_drac + uncl_drac != ssm_all_drac:
        errors.append(f"SSM role+uncl DRAC {role_drac + uncl_drac} != all {ssm_all_drac}")

    return errors
