"""P0-1（新审阅）回归：SSM 未采集语义（main 网格不得伪装为零事件）。

覆盖：
- runner 对 v0.4.2 main_factorial（ssm_enabled=False）run：SSM 原始/处理计数、
  事件数、极值、受影响车辆数与事件率全部 NaN，ssm_not_collected=True，
  experiment_role / ssm_enabled 写入 summary；
- safety（ssm_enabled=True）run：合法零检出仍为数值 0；
- validate_summary_contract 对未采集 summary 通过（SSM 键 NaN 合法）；
- aggregate 对全 NaN SSM 组：count=0、mean/std/min/max/median 保留 NaN；
- writer subgroup gate 对未采集 SSM 计数 NaN 通过。
"""

import json
import math
from pathlib import Path

from scripts.results.aggregate import aggregate
from scripts.schema import validate_summary_contract


def _spec_v4_2(tmp_path, run_id="s0_IDM_v010_c005_as01_ss101", **overrides):
    from scripts.run_spec import PIPELINE_V4_2, RunSpec

    net_dir = tmp_path / "net"
    net_dir.mkdir(parents=True, exist_ok=True)
    (net_dir / "loop.net.xml").write_text("<net/>", encoding="utf-8")
    # load_network_meta 要求完整元数据字段（tracked net.json 字段齐全）
    real_meta = json.loads((Path("net/scenario_0/net.json")).read_text(encoding="utf-8"))
    (net_dir / "net.json").write_text(json.dumps(real_meta), encoding="utf-8")

    base = dict(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id=run_id,
        pipeline_version=PIPELINE_V4_2,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
        network_file=str(tmp_path / "net" / "loop.net.xml"),
    )
    base.update(overrides)
    return RunSpec(**base)


def _write_run_dir(tmp_path, spec, ssm_file: bool) -> Path:
    from scripts.run_spec import write_run_spec

    rd = tmp_path / "run"
    rd.mkdir(parents=True)
    write_run_spec(spec, rd)
    type_map = {
        f"veh{i}": ("CAV" if i < spec.cav_count else "HV") for i in range(spec.vehicle_count)
    }
    (rd / "vehicle_type_map.json").write_text(json.dumps(type_map))
    for f in (
        "routes.rou.xml",
        "performance.xml",
        "performance_HV.xml",
        "performance_CAV.xml",
        "emissions.xml",
        "emissions_HV.xml",
        "emissions_CAV.xml",
        "vehroute.xml",
        "lanechange.xml",
        "stderr.log",
        "detector_lane0.xml",
        "detector_lane0_HV.xml",
        "detector_lane0_CAV.xml",
    ):
        (rd / f).write_text("<root/>", encoding="utf-8")
    if ssm_file:
        (rd / "ssm.xml").write_text("<SSMLog/>", encoding="utf-8")
    status = {
        "run_id": spec.run_id,
        "pipeline_version": spec.pipeline_version,
        "status": "SUCCESS",
        "return_code": 0,
        "run_spec_sha256": spec.sha256(),
        "schema_version": spec.schema_version,
        "config_sha256": "",
        "network_sha256": "",
        "experiment_id": "",
        "sumo_seed": 101,
        "route_file_sha256": "",
        "vehicle_type_map_sha256": "",
    }
    (rd / "simulation_status.json").write_text(json.dumps(status))
    return rd


def _parse(tmp_path, spec, monkeypatch, ssm_file=False):
    from scripts.parsing.runner import _parse_one_run_v4_1

    rd = _write_run_dir(tmp_path, spec, ssm_file=ssm_file)
    monkeypatch.setattr(
        "scripts.parsing.runner._load_free_flow_references",
        lambda spec: {"HV": 100.0, "IDM": 100.0},
    )
    core, subgroup, errors = _parse_one_run_v4_1(rd, spec, spec.network_file)
    return core, subgroup, errors


def test_main_factorial_ssm_not_collected_is_nan(tmp_path, monkeypatch):
    """main 网格（ssm_enabled=False）：SSM 全 NaN + 状态列透传，非零计数。"""
    spec = _spec_v4_2(tmp_path)
    core, subgroup, errors = _parse(tmp_path, spec, monkeypatch)

    assert core["experiment_role"] == "main_factorial"
    assert core["ssm_enabled"] is False
    assert core["ssm_not_collected"] is True
    for key in (
        "ssm_raw_record_count",
        "ssm_invalid_record_count",
        "ssm_warmup_filtered_count",
        "ssm_valid_record_count",
        "ssm_mirrored_record_count",
        "ssm_fragment_merged_count",
        "ttc_conflict_event_count",
        "min_ttc_s",
        "ttc_affected_vehicle_count",
        "drac_conflict_event_count",
        "max_drac_mps2",
        "ttc_events_per_1000_veh_km",
    ):
        assert isinstance(core[key], float) and math.isnan(core[key]), f"{key} 应为 NaN"
    # subgroup SSM 同样未采集
    ssm_sub = [r for r in subgroup if r["metric_family"] == "safety_ssm"]
    assert ssm_sub
    for r in ssm_sub:
        assert math.isnan(r["metric_value"])
    assert not any("SSM" in e for e in errors)


def test_safety_legal_zero_stays_zero(tmp_path, monkeypatch):
    """safety（ssm_enabled=True）：空 SSMLog 合法零检出仍为数值 0。"""
    spec = _spec_v4_2(
        tmp_path,
        run_id="s0_IDM_v010_c005_as01_ss101_safety",
        experiment_role="safety",
        ssm_enabled=True,
        analysis_ttc_threshold_s=3.0,
        analysis_drac_threshold_mps2=3.0,
        ssm_dedup_method="greedy_one_to_one_80pct",
        ssm_mirror_overlap_ratio=0.8,
        ssm_fragment_merge_gap_s=0.0,
    )
    core, subgroup, errors = _parse(tmp_path, spec, monkeypatch, ssm_file=True)

    assert core["experiment_role"] == "safety"
    assert core["ssm_enabled"] is True
    assert core["ssm_not_collected"] is False
    assert core["ssm_raw_record_count"] == 0
    assert core["ttc_conflict_event_count"] == 0
    assert math.isnan(core["min_ttc_s"])  # 零事件极值 NaN（既有语义）


def test_not_collected_summary_passes_contract():
    """未采集 summary（SSM 键 NaN）必须通过 schema=2 contract。"""
    from scripts.parsing.metrics import compute_core_summary
    from scripts.run_spec import PIPELINE_V4_2, RunSpec

    spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="x",
        pipeline_version=PIPELINE_V4_2,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
        experiment_role="main_factorial",
        ssm_enabled=False,
    )
    nan = float("nan")
    ssm_not_collected = {
        "all": {
            "ssm_raw_record_count": nan,
            "ssm_invalid_record_count": nan,
            "ssm_warmup_filtered_count": nan,
            "ssm_valid_record_count": nan,
            "ssm_mirrored_record_count": nan,
            "ssm_fragment_merged_count": nan,
            "ttc_conflict_event_count": nan,
            "min_ttc_s": nan,
            "ttc_involved_vehicle_count": nan,
            "drac_conflict_event_count": nan,
            "max_drac_mps2": nan,
            "parse_success": True,
            "ssm_not_collected": True,
        },
        "pair_HV_HV": {"ttc_event_count": nan, "drac_event_count": nan},
        "pair_HV_CAV": {"ttc_event_count": nan, "drac_event_count": nan},
        "pair_CAV_CAV": {"ttc_event_count": nan, "drac_event_count": nan},
        "role_f_HV_l_HV": {"ttc_event_count": nan, "drac_event_count": nan},
        "role_f_HV_l_CAV": {"ttc_event_count": nan, "drac_event_count": nan},
        "role_f_CAV_l_HV": {"ttc_event_count": nan, "drac_event_count": nan},
        "role_f_CAV_l_CAV": {"ttc_event_count": nan, "drac_event_count": nan},
        "unclassified": {"ttc_event_count": nan, "drac_event_count": nan},
    }
    from scripts.parsing.metrics import SubgroupPrimitives

    def _ee_zero():
        return {
            "total_CO2_kg": 0.0,
            "total_NOx_g": 0.0,
            "total_PMx_g": 0.0,
            "total_fuel_kg": 0.0,
            "non_internal_CO2_kg": 0.0,
            "non_internal_NOx_g": 0.0,
            "non_internal_PMx_g": 0.0,
            "non_internal_fuel_kg": 0.0,
            "parse_success": True,
        }

    prim = SubgroupPrimitives(
        detector={
            "all": {
                "mean_flow_veh_h": 100.0,
                "max_flow_veh_h": 100.0,
                "mean_speed_m_s": 30.0,
                "speed_variance": 0.0,
                "window_count": 5,
                "parse_success": True,
            }
        },
        ssm=ssm_not_collected,
        lanechange={
            "all": {
                "lane_change_count": 0,
                "unsafe_lc_gap_count": 0,
                "unsafe_lc_gap_ratio": 0.0,
                "parse_success": True,
            }
        },
        edge_perf={
            "all": {
                "total_vehicle_km": 100.0,
                "non_internal_edge_vehicle_km": 90.0,
                "total_time_loss_s": 0.0,
                "parse_success": True,
            }
        },
        edge_emis={"all": _ee_zero()},
        vehroute={
            "all": {"completed_lap_count": 0, "parse_success": True},
            "HV": {},
            "CAV": {},
        },
        emerg_brake={
            "all": {
                "emergency_braking_count": 0,
                "emergency_braking_affected_vehicle_count": 0,
                "parse_success": True,
            }
        },
        fcd=None,
    )
    core = compute_core_summary(prim, spec, {"HV": 100.0, "IDM": 100.0})
    assert validate_summary_contract(core, "2", pipeline_version="v0.4.2") == []


def test_aggregate_all_nan_group_count_zero_std_nan(tmp_path):
    """aggregate：全 NaN 组 count=0、std/min/max/median/mean 保留 NaN（不得填 0）。"""
    from scripts.schema import RUN_LEVEL_COLUMNS_V4_2

    rows = []
    for i, (asd, ss) in enumerate([(1, 101), (2, 101), (3, 101)]):
        row = {col: "" for col in RUN_LEVEL_COLUMNS_V4_2}
        row.update(
            {
                "run_id": f"r{i}",
                "scenario": "scenario_0",
                "model": "IDM",
                "requested_pcav": 0.5,
                "realized_pcav": 0.5,
                "cav_count": 5,
                "hv_count": 5,
                "vehN": 10,
                "assignment_seed": asd,
                "sumo_seed": ss,
                "experiment_role": "main_factorial",
                "ssm_enabled": "False",
                "ssm_not_collected": "True",
                "data_quality": "ok",
                "mean_flow_veh_h": 100.0,
                "total_vehicle_km": 10.0,
                "ssm_raw_record_count": "",
                "ttc_conflict_event_count": "",
                "ttc_events_per_1000_veh_km": "",
                "max_drac_mps2": "",
            }
        )
        rows.append(row)
    import pandas as pd

    df = pd.DataFrame(rows)
    in_csv = tmp_path / "run_level.csv"
    out_csv = tmp_path / "aggregated.csv"
    df.to_csv(in_csv, index=False)
    out = aggregate(in_csv, out_csv, schema_ver="2")

    group = out[out["cav_count"] == 5].iloc[0]
    assert group["ssm_raw_count"] == 0
    assert math.isnan(float(group["ttc_mean"]))
    assert math.isnan(float(group["ttc_std"]))
    assert math.isnan(float(group["ttc_min"]))
    assert math.isnan(float(group["ttc_max"]))
    assert math.isnan(float(group["ttc_median"]))


def test_writer_subgroup_gate_accepts_not_collected_nan():
    """writer subgroup gate：未采集（v0.4.2 main_factorial）SSM 计数 NaN 合法。"""
    from scripts.results.writer import _expected_subgroup_keys, _valid_subgroup_rows

    spec = {
        "scenario": "scenario_0",
        "model": "IDM",
        "requested_pcav": None,
        "cav_count": 5,
        "vehicle_count": 10,
        "seed": 1,
        "sumo_seed": 101,
        "fcd_profile": None,
        "pipeline_version": "v0.4.2",
        "ssm_enabled": False,
    }
    nan = float("nan")
    rows = []
    for family, dimension, value, metric in _expected_subgroup_keys(False):
        m = metric
        if family == "safety_ssm" and m in {"ttc_event_count", "drac_event_count"}:
            val = nan
        elif m in {
            "window_count",
            "ttc_event_count",
            "drac_event_count",
            "emergency_braking_count",
            "affected_vehicle_count",
            "lane_change_count",
            "unsafe_lc_gap_count",
            "completed_lap_count",
        }:
            val = 0
        else:
            val = 0.0
        rows.append(
            {
                "run_id": "run-1",
                "scenario": "scenario_0",
                "model": "IDM",
                "requested_pcav": None,
                "realized_pcav": 0.5,
                "cav_count": 5,
                "hv_count": 5,
                "vehN": 10,
                "assignment_seed": 1,
                "sumo_seed": 101,
                "metric_family": family,
                "group_dimension": dimension,
                "group_value": value,
                "metric_name": m,
                "metric_value": val,
            }
        )
    assert _valid_subgroup_rows(rows, "run-1", spec)
