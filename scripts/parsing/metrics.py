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
    # P0-7：主强度用 non-internal 排放 / non-internal veh-km（与 v0.4.0 可比）；
    # 全路网强度保留为次要字段
    ni_veh_km = ep.get("non_internal_edge_vehicle_km", float("nan"))
    ni_co2 = ee.get("non_internal_CO2_kg", float("nan"))
    ni_nox = ee.get("non_internal_NOx_g", float("nan"))
    ni_pmx = ee.get("non_internal_PMx_g", float("nan"))
    ni_fuel = ee.get("non_internal_fuel_kg", float("nan"))
    co2_per = _safe_div(ni_co2 * 1000.0, ni_veh_km)
    nox_per = _safe_div(ni_nox * 1000.0, ni_veh_km)
    pmx_per = _safe_div(ni_pmx * 1000.0, ni_veh_km)
    fuel_per = _safe_div(ni_fuel * 1000.0, ni_veh_km)
    # 全路网强度（次要）
    wn_co2_per = _safe_div(ee.get("total_CO2_kg", 0) * 1000.0, total_veh_km)
    wn_nox_per = _safe_div(ee.get("total_NOx_g", 0) * 1000.0, total_veh_km)
    wn_pmx_per = _safe_div(ee.get("total_PMx_g", 0) * 1000.0, total_veh_km)
    wn_fuel_per = _safe_div(ee.get("total_fuel_kg", 0) * 1000.0, total_veh_km)
    tl_per = _safe_div(ep.get("total_time_loss_s", 0), total_veh_km)

    # P0-8 修订（新审阅 P0-2）：逐 lap 转换后 pooled 求 delay 统计。
    # 对每个有效 lap：delay_i = lap_time_i - reference[vehicle_type_i]；
    # mean/p95 全部基于 pooled delay 样本直接计算，不得用 subgroup 分位数
    # 加权近似（分位数不满足加权线性关系，加权 subgroup p95 ≠ pooled p95）。
    # 键契约（与 runner._load_free_flow_references 一致）：{"HV", spec.model}
    hv_ref = free_flow_refs.get("HV", float("nan"))
    cav_ref = (
        free_flow_refs.get(spec.model, float("nan"))
        if spec.model in ("IDM", "CACC")
        else float("nan")
    )

    from scripts.parsing.vehroute import _quantile_higher

    vr_hv = primitives.vehroute.get("HV", {})
    vr_cav = primitives.vehroute.get("CAV", {})
    delay_samples: list[float] = []
    # P0-1（本轮审查）：循环迭代变量不得复用外层 `vr`（:55 提取的 all-level 子群）。
    # 旧实现 for vr, ref in ... 在循环结束时把 vr 重绑定为 CAV 子群，导致
    # completed_lap_count / mean|median|p95_lap_time_s / lap_time_std_s / vr_parse_success
    # 六个 all-level 列实际报告 CAV 子群值（cav=0 组整体缺失）。独立命名 vr_item。
    for vr_item, ref in ((vr_hv, hv_ref), (vr_cav, cav_ref)):
        laps = vr_item.get("lap_times_s") or []
        if not laps or _math.isnan(ref):
            continue
        delay_samples.extend(t - ref for t in laps)

    if delay_samples:
        n_delay = len(delay_samples)
        mean_delay = sum(delay_samples) / n_delay
        p95_delay = _quantile_higher(sorted(delay_samples), 0.95)
    else:
        mean_delay = float("nan")
        p95_delay = float("nan")

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
        # P0-5：v0.4.2 记录 analysis 配置（单源可审计）
        **(
            {
                "analysis_ttc_threshold_s": spec.analysis_ttc_threshold_s,
                "analysis_drac_threshold_mps2": spec.analysis_drac_threshold_mps2,
                "ssm_dedup_method": spec.ssm_dedup_method,
                "ssm_mirror_overlap_ratio": spec.ssm_mirror_overlap_ratio,
                "ssm_fragment_merge_gap_s": spec.ssm_fragment_merge_gap_s,
            }
            if getattr(spec, "pipeline_version", "") == "v0.4.2"
            else {}
        ),
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
        "ssm_fragment_merged_count": ssm_all.get("ssm_fragment_merged_count", 0),
        # P0-1（新审阅）：采集状态写入 run-level CSV，区分未采集/解析失败/合法零检出
        "experiment_role": getattr(spec, "experiment_role", "main_factorial"),
        "ssm_enabled": bool(getattr(spec, "ssm_enabled", False)),
        "ssm_not_collected": ssm_all.get("ssm_not_collected", False),
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
        # P2-1（本轮审查）：legacy 空间错配列（全路网 TTC 分子 / non-internal
        # veh-km 分母）仅 legacy 输出——v0.4.2 用空间配对列（whole_network_ttc /
        # whole_network veh-km）已由 P1-4 实现，错误口径列残留正式工件易被按名
        # 误选（aggregate 曾输出其 _mean 0-5942）。
        **(
            {
                "whole_network_ttc_events_per_1000_non_internal_edge_veh_km": _per_1000_veh_km(
                    ssm_all.get("ttc_conflict_event_count", 0),
                    ep.get("non_internal_edge_vehicle_km", float("nan")),
                )
            }
            if getattr(spec, "pipeline_version", "") != "v0.4.2"
            else {}
        ),
        "emergency_brakes_per_1000_veh_km": eb_per_1000,
        "lane_changes_per_1000_veh_km": lc_per_1000,
        "CO2_g_per_veh_km": co2_per,
        "NOx_mg_per_veh_km": nox_per,
        "PMx_mg_per_veh_km": pmx_per,
        "fuel_g_per_veh_km": fuel_per,
        "whole_network_CO2_g_per_veh_km": wn_co2_per,
        "whole_network_NOx_mg_per_veh_km": wn_nox_per,
        "whole_network_PMx_mg_per_veh_km": wn_pmx_per,
        "whole_network_fuel_g_per_veh_km": wn_fuel_per,
        "non_internal_CO2_kg": ni_co2,
        "non_internal_NOx_g": ni_nox,
        "non_internal_PMx_g": ni_pmx,
        "non_internal_fuel_kg": ni_fuel,
        "time_loss_s_per_veh_km": tl_per,
        "mean_lap_delay_s": mean_delay,
        "p95_lap_delay_s": p95_delay,
        "ssm_parse_success": ssm_all.get("parse_success", False),
        "lc_parse_success": lc.get("parse_success", False),
        "ep_parse_success": ep.get("parse_success", False),
        "ee_parse_success": ee.get("parse_success", False),
        "vr_parse_success": vr.get("parse_success", False),
        # 审阅 P2（复核）：emergency braking 解析质量贯穿结果链路
        "eb_parse_success": eb.get("parse_success", False),
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

    # Emissions（与 core P0-7 口径一致：主强度 non-internal/non-internal，
    # 全路网强度次要；同名列含义必须与 core 相同）
    for vt in ("HV", "CAV"):
        ee = primitives.edge_emis.get(vt, {})
        ep = primitives.edge_perf.get(vt, {})
        veh_km = ep.get("total_vehicle_km", float("nan"))
        ni_veh_km = ep.get("non_internal_edge_vehicle_km", float("nan"))
        for key in (
            "total_CO2_kg",
            "total_NOx_g",
            "total_PMx_g",
            "total_fuel_kg",
            "non_internal_CO2_kg",
            "non_internal_NOx_g",
            "non_internal_PMx_g",
            "non_internal_fuel_kg",
        ):
            _add("vehicle_type", vt, "emissions", key, ee.get(key, float("nan")))
        # 主口径：non-internal 排放 / non-internal veh-km
        _add(
            "vehicle_type",
            vt,
            "emissions",
            "CO2_g_per_veh_km",
            _safe_div(ee.get("non_internal_CO2_kg", 0) * 1000.0, ni_veh_km),
        )
        _add(
            "vehicle_type",
            vt,
            "emissions",
            "NOx_mg_per_veh_km",
            _safe_div(ee.get("non_internal_NOx_g", 0) * 1000.0, ni_veh_km),
        )
        _add(
            "vehicle_type",
            vt,
            "emissions",
            "PMx_mg_per_veh_km",
            _safe_div(ee.get("non_internal_PMx_g", 0) * 1000.0, ni_veh_km),
        )
        _add(
            "vehicle_type",
            vt,
            "emissions",
            "fuel_g_per_veh_km",
            _safe_div(ee.get("non_internal_fuel_kg", 0) * 1000.0, ni_veh_km),
        )
        # 全路网次要强度：all-edge 排放 / all-edge veh-km
        _add(
            "vehicle_type",
            vt,
            "emissions",
            "whole_network_CO2_g_per_veh_km",
            _safe_div(ee.get("total_CO2_kg", 0) * 1000.0, veh_km),
        )
        _add(
            "vehicle_type",
            vt,
            "emissions",
            "whole_network_NOx_mg_per_veh_km",
            _safe_div(ee.get("total_NOx_g", 0) * 1000.0, veh_km),
        )
        _add(
            "vehicle_type",
            vt,
            "emissions",
            "whole_network_PMx_mg_per_veh_km",
            _safe_div(ee.get("total_PMx_g", 0) * 1000.0, veh_km),
        )
        _add(
            "vehicle_type",
            vt,
            "emissions",
            "whole_network_fuel_g_per_veh_km",
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
    # 可加性容差（v0.4.2 正式网格实测驱动，2026 复检后放宽）：
    # SUMO 多 measurement（all/HV/CAV 独立 vTypes 过滤）的浮点累加噪声在
    # 全网格下实测 max：vehicle_km 2.0e-4 / time_loss 1.1e-3 / PMx 3.2e-4
    # （PMx 小值受 SUMO 输出小数位精度影响，相对误差放大）。
    # 旧容差（2e-4/1e-4/1e-5）在正式数据上误报 770 个 INVALID_DATA
    # （首轮解析终态计数；中途观察值 454 非最终口径），全部重跑成功。
    for key in ("total_vehicle_km", "non_internal_edge_vehicle_km"):
        _check_additive(ep_all, ep_hv, ep_cav, key, 5e-4, 1e-3)
    _check_additive(ep_all, ep_hv, ep_cav, "total_time_loss_s", 2e-3, 1e-3)

    ee_all = primitives.edge_emis.get("all", {})
    ee_hv = primitives.edge_emis.get("HV", {})
    ee_cav = primitives.edge_emis.get("CAV", {})
    for key in ("total_CO2_kg", "total_NOx_g", "total_PMx_g", "total_fuel_kg"):
        _check_additive(ee_all, ee_hv, ee_cav, key, 5e-4, 1e-9)
    # 审阅 P1-2：non-internal 双口径加性校验（all/HV/CAV 各自文件内筛选，
    # HV+CAV == all 应同样成立；此前仅覆盖全路网 total_* 四项）
    for key in (
        "non_internal_CO2_kg",
        "non_internal_NOx_g",
        "non_internal_PMx_g",
        "non_internal_fuel_kg",
    ):
        _check_additive(ee_all, ee_hv, ee_cav, key, 5e-4, 1e-9)

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

    # SSM pair closure（未采集时跳过：NaN 无法参与等式校验）
    ssm_not_collected = primitives.ssm.get("all", {}).get("ssm_not_collected", False)
    if not ssm_not_collected:
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

    # P2-3（审查）：FCD 台账闭合——样本数与三类排除计数 all == HV+CAV。
    # parse_fcd 构造上保证（all_arr/hv_arr/cav_arr 独立累计、排除计数 all 与
    # vt 同步自增），此处显式断言设计 §6.2 台账不变量，防未来改动破坏。
    if primitives.fcd is not None:
        for key in (
            "valid_thw_sample_count",
            "low_speed_excluded_count",
            "no_leader_count",
            "self_leader_count",
        ):
            a = primitives.fcd.get("all", {}).get(key, 0) or 0
            h = primitives.fcd.get("HV", {}).get(key, 0) or 0
            c = primitives.fcd.get("CAV", {}).get(key, 0) or 0
            if h + c != a:
                errors.append(f"fcd.{key}: HV({h})+CAV({c}) != all({a})")

    return errors
