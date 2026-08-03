"""外部审阅 delta（v0.4.2 发布前）回归测试：P1-1 / P1-2 / P1-3。

- P1-1：EdgeData 解析器坏记录静默丢弃 → fail-closed（parse_success=False）
         + ``invalid_record_count`` 计数
- P1-2：排放契约未跟随 non-internal 主 estimand（NaN companion / 非负门禁 /
         加性校验范围）
- P1-3：配置类型静默强制转换（int() 截断、bool() 强转）——拒绝小数与数字型
         bool，保留 "true"/"false" 字符串兼容
"""

import json
import math
import os
from pathlib import Path

import pytest

from scripts.experiment_config import ExperimentConfig, _coerce_int, load_experiment_config
from scripts.parsing.edge_emissions import parse_edge_emissions
from scripts.parsing.edge_performance import parse_edge_performance
from scripts.parsing.metrics import SubgroupPrimitives, validate_subgroup_invariants
from scripts.results.writer import SUBGROUP_NAN_RULES
from scripts.schema import SUMMARY_REQUIRED_KEYS_V4_2, validate_summary_contract

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

PIPELINE = "v0.4.2"


# ── P1-1：EdgeData 解析器 fail-closed ──


_PERF_MIXED = (
    '<meandata><interval begin="0.00" end="60.00" id="int1">'
    '<edge id="e1" speed="10.0" sampledSeconds="100.0" timeLoss="5.0"/>'
    '<edge id="e2" speed="BAD" sampledSeconds="50.0" timeLoss="1.0"/>'
    "</interval></meandata>"
)


def test_edge_perf_bad_speed_fails_closed(tmp_path):
    p = tmp_path / "perf.xml"
    p.write_text(_PERF_MIXED, encoding="utf-8")
    r = parse_edge_performance(str(p))
    assert r["parse_success"] is False
    assert r["invalid_record_count"] == 1
    # 正常 edge 仍累计（e1: 10.0 m/s × 100 s = 1000 m = 1 km；timeLoss 5 s）
    assert math.isclose(r["total_vehicle_km"], 1.0)
    assert math.isclose(r["total_time_loss_s"], 5.0)


def test_edge_perf_nonfinite_speed_fails_closed(tmp_path):
    p = tmp_path / "perf.xml"
    p.write_text(
        '<meandata><interval begin="0" end="60" id="i">'
        '<edge id="e1" speed="nan" sampledSeconds="100.0" timeLoss="1.0"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    r = parse_edge_performance(str(p))
    assert r["parse_success"] is False
    assert r["invalid_record_count"] == 1


def test_edge_perf_missing_time_loss_fails_closed(tmp_path):
    p = tmp_path / "perf.xml"
    p.write_text(
        '<meandata><interval begin="0" end="60" id="i">'
        '<edge id="e1" speed="10.0" sampledSeconds="100.0"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    r = parse_edge_performance(str(p))
    assert r["parse_success"] is False
    assert r["invalid_record_count"] == 1


def test_edge_perf_missing_sampled_seconds_fails_closed(tmp_path):
    p = tmp_path / "perf.xml"
    p.write_text(
        '<meandata><interval begin="0" end="60" id="i">'
        '<edge id="e1" speed="10.0" timeLoss="1.0"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    r = parse_edge_performance(str(p))
    assert r["parse_success"] is False
    assert r["invalid_record_count"] == 1


def test_edge_perf_valid_fixture_still_succeeds():
    r = parse_edge_performance(os.path.join(FIXTURES, "edge_performance_minimal.xml"))
    assert r["parse_success"] is True
    assert r["invalid_record_count"] == 0
    assert r["total_vehicle_km"] > 0


_EMIS_MIXED = (
    '<meandata><interval begin="0.00" end="60.00" id="int1">'
    '<edge id="e1" sampledSeconds="100.0" CO2_abs="1000" NOx_abs="2.0" PMx_abs="0.1" fuel_abs="500.0"/>'
    '<edge id="e2" sampledSeconds="100.0" CO2_abs="BAD" NOx_abs="2.0" PMx_abs="0.1" fuel_abs="500.0"/>'
    "</interval></meandata>"
)


def test_edge_emis_bad_value_fails_closed(tmp_path):
    p = tmp_path / "emis.xml"
    p.write_text(_EMIS_MIXED, encoding="utf-8")
    r = parse_edge_emissions(str(p))
    assert r["parse_success"] is False
    assert r["invalid_record_count"] == 1
    # 正常 edge 仍累计：CO2 1000 mg = 0.001 kg
    assert math.isclose(r["total_CO2_kg"], 1000.0 / 1e6)


def test_edge_emis_missing_attr_fails_closed(tmp_path):
    """有车（sampledSeconds>0）却缺 *_abs → invalid。"""
    p = tmp_path / "emis.xml"
    p.write_text(
        '<meandata><interval begin="0" end="60" id="i">'
        '<edge id="e1" sampledSeconds="100.0" CO2_abs="1000" NOx_abs="2.0" PMx_abs="0.1"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    r = parse_edge_emissions(str(p))
    assert r["parse_success"] is False
    assert r["invalid_record_count"] == 1


def test_edge_emis_valid_fixture_still_succeeds():
    r = parse_edge_emissions(os.path.join(FIXTURES, "edge_emissions_minimal.xml"))
    assert r["parse_success"] is True
    assert r["invalid_record_count"] == 0
    assert r["total_CO2_kg"] > 0


# ── P1-2：排放契约跟随 non-internal 主 estimand ──


def _valid_v4_2_summary():
    integer_keys = {
        "vehN",
        "seed",
        "cav_count",
        "hv_count",
        "assignment_seed",
        "sumo_seed",
        "detector_speed_window_count",
        "ssm_raw_record_count",
        "ssm_invalid_record_count",
        "ssm_warmup_filtered_count",
        "ssm_valid_record_count",
        "ssm_mirrored_record_count",
        "ssm_fragment_merged_count",
        "ttc_conflict_event_count",
        "ttc_affected_vehicle_count",
        "drac_conflict_event_count",
        "emergency_braking_count",
        "emergency_braking_affected_vehicle_count",
        "lane_change_count",
        "unsafe_lc_gap_count",
        "completed_lap_count",
        "detector_frequency_s",
        "edge_data_frequency_s",
    }
    bool_keys = {
        "ssm_parse_success",
        "lc_parse_success",
        "ep_parse_success",
        "ee_parse_success",
        "vr_parse_success",
        "fcd_parse_success",
        "with_internal",
    }
    string_keys = {"run_id", "scenario", "model", "det_xml", "experiment_role", "ssm_dedup_method"}
    summary = {}
    for key in SUMMARY_REQUIRED_KEYS_V4_2:
        if key in string_keys:
            summary[key] = "x"
        elif key in bool_keys:
            summary[key] = True
        elif key in integer_keys:
            summary[key] = 1
        else:
            summary[key] = 1.0
    # SSM 已采集语义（safety）：ssm 键为数值 0/1 合法，不触发未采集 NaN 强制
    summary["ssm_not_collected"] = False
    summary["ssm_enabled"] = True
    return summary


def test_summary_contract_rejects_negative_non_internal_fields():
    for key in (
        "non_internal_CO2_kg",
        "non_internal_NOx_g",
        "non_internal_PMx_g",
        "non_internal_fuel_kg",
    ):
        summary = _valid_v4_2_summary()
        summary[key] = -1.0
        errors = validate_summary_contract(summary, "2", pipeline_version=PIPELINE)
        assert any(key in e and "non-negative" in e for e in errors), (key, errors)


def test_summary_contract_rejects_negative_whole_network_fields():
    for key in (
        "whole_network_CO2_g_per_veh_km",
        "whole_network_NOx_mg_per_veh_km",
        "whole_network_PMx_mg_per_veh_km",
        "whole_network_fuel_g_per_veh_km",
        "whole_network_ttc_events_per_1000_non_internal_edge_veh_km",
    ):
        summary = _valid_v4_2_summary()
        summary[key] = -1.0
        errors = validate_summary_contract(summary, "2", pipeline_version=PIPELINE)
        assert any(key in e and "non-negative" in e for e in errors), (key, errors)


def test_summary_nan_rule_uses_non_internal_companion():
    """SUMMARY_NAN_RULES_V4_2 的排放强度 companion 跟随 non-internal 主 estimand；
    legacy 冻结表保持 total_vehicle_km（不污染 schema=1）。"""
    from scripts.schema import SUMMARY_NAN_RULES, SUMMARY_NAN_RULES_V4_2

    for key in ("CO2_g_per_veh_km", "NOx_mg_per_veh_km", "PMx_mg_per_veh_km", "fuel_g_per_veh_km"):
        assert SUMMARY_NAN_RULES_V4_2[key][0] == "non_internal_edge_vehicle_km"
        assert SUMMARY_NAN_RULES[key][0] == "total_vehicle_km"


def test_summary_nan_rule_rejects_nan_with_exposure():
    """有 non-internal 暴露量（companion>0）时强度 NaN 非法。"""
    summary = _valid_v4_2_summary()
    summary["CO2_g_per_veh_km"] = math.nan
    errors = validate_summary_contract(summary, "2", pipeline_version=PIPELINE)
    assert any("CO2_g_per_veh_km" in e for e in errors)


def test_subgroup_nan_rule_follows_non_internal_companion():
    for key in ("CO2_g_per_veh_km", "NOx_mg_per_veh_km", "PMx_mg_per_veh_km", "fuel_g_per_veh_km"):
        assert SUBGROUP_NAN_RULES[key] == ("efficiency", "non_internal_edge_vehicle_km", 0)


def _emis_primitive(ni, total):
    return {
        "parse_success": True,
        "total_CO2_kg": total,
        "non_internal_CO2_kg": ni,
        "total_NOx_g": total * 0.1,
        "non_internal_NOx_g": ni * 0.1,
        "total_PMx_g": total * 0.01,
        "non_internal_PMx_g": ni * 0.01,
        "total_fuel_kg": total * 0.5,
        "non_internal_fuel_kg": ni * 0.5,
    }


def _closure_primitives(ni_all, ni_hv, ni_cav):
    return SubgroupPrimitives(
        detector={"HV": {"parse_success": True}, "CAV": {"parse_success": True}},
        ssm={"all": {"ssm_not_collected": True}},
        lanechange={
            "all": {"lane_change_count": 0},
            "HV": {"parse_success": True, "lane_change_count": 0},
            "CAV": {"parse_success": True, "lane_change_count": 0},
        },
        edge_perf={
            "all": {
                "parse_success": True,
                "total_vehicle_km": 10.0,
                "non_internal_edge_vehicle_km": 10.0,
                "total_time_loss_s": 5.0,
            },
            "HV": {
                "parse_success": True,
                "total_vehicle_km": 5.0,
                "non_internal_edge_vehicle_km": 5.0,
                "total_time_loss_s": 2.0,
            },
            "CAV": {
                "parse_success": True,
                "total_vehicle_km": 5.0,
                "non_internal_edge_vehicle_km": 5.0,
                "total_time_loss_s": 3.0,
            },
        },
        edge_emis={
            "all": _emis_primitive(ni_all, 10.0),
            "HV": _emis_primitive(ni_hv, 5.0),
            "CAV": _emis_primitive(ni_cav, 5.0),
        },
        vehroute={
            "all": {"completed_lap_count": 2},
            "HV": {"parse_success": True, "completed_lap_count": 1},
            "CAV": {"parse_success": True, "completed_lap_count": 1},
        },
        emerg_brake={
            "all": {"emergency_braking_count": 0},
            "HV": {"emergency_braking_count": 0},
            "CAV": {"emergency_braking_count": 0},
        },
    )


def test_non_internal_additive_closure_passes():
    primitives = _closure_primitives(ni_all=10.0, ni_hv=5.0, ni_cav=5.0)
    assert validate_subgroup_invariants(primitives) == []


def test_non_internal_additive_closure_detects_mismatch():
    primitives = _closure_primitives(ni_all=10.0, ni_hv=4.0, ni_cav=5.0)
    errors = validate_subgroup_invariants(primitives)
    assert any("non_internal_CO2_kg" in e for e in errors), errors


# ── P1-3：配置类型严格化 ──


def test_coerce_int_accepts_int_integral_float_and_str():
    assert _coerce_int(5, "k") == 5
    assert _coerce_int(5.0, "k") == 5
    assert _coerce_int("10", "k") == 10
    assert _coerce_int("10.0", "k") == 10


@pytest.mark.parametrize(
    "bad", [10.9, True, False, "10.5", "abc", None, math.nan, math.inf, "Infinity", "inf", "nan"]
)
def test_coerce_int_rejects_non_integer(bad):
    with pytest.raises(ValueError, match="must be an integer"):
        _coerce_int(bad, "k")


def test_config_rejects_float_vehicle_count(tmp_path):
    data = json.loads(Path(r"configs/v0.4.0.json").read_text(encoding="utf-8"))
    data["vehicle_counts"] = [10.9]
    path = tmp_path / "c.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="vehicle_counts"):
        load_experiment_config(path)


def test_config_rejects_float_seed(tmp_path):
    data = json.loads(Path(r"configs/v0.4.0.json").read_text(encoding="utf-8"))
    data["seeds"] = [1.9, 2]
    path = tmp_path / "c.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="seeds"):
        load_experiment_config(path)


def test_config_rejects_numeric_bool(tmp_path):
    data = json.loads(Path(r"configs/v0.4.2/main.json").read_text(encoding="utf-8"))
    data["with_internal"] = 2
    path = tmp_path / "c.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="with_internal"):
        load_experiment_config(path)


def test_config_accepts_string_bool():
    data = json.loads(Path(r"configs/v0.4.2/main.json").read_text(encoding="utf-8"))
    data["with_internal"] = "true"
    assert ExperimentConfig.from_dict(data).with_internal is True
    data["with_internal"] = "false"
    assert ExperimentConfig.from_dict(data).with_internal is False


def test_config_rejects_float_treatment_vehicle_count(tmp_path):
    data = json.loads(Path(r"configs/v0.4.2/main.json").read_text(encoding="utf-8"))
    data["treatments"] = [
        {"vehicle_count": 10.9, "cav_counts": [0, 10], "assignment_seeds": [1, 2, 3]}
    ]
    path = tmp_path / "c.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="vehicle_count"):
        load_experiment_config(path)


def test_config_rejects_float_cav_count(tmp_path):
    data = json.loads(Path(r"configs/v0.4.2/main.json").read_text(encoding="utf-8"))
    data["treatments"] = [
        {"vehicle_count": 10, "cav_counts": [2.9, 10], "assignment_seeds": [1, 2, 3]}
    ]
    path = tmp_path / "c.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="cav_counts"):
        load_experiment_config(path)


# ── Delta review 补齐：P1-1 原子解析（begin/id/负值）──


def test_edge_perf_begin_nan_fails_closed(tmp_path):
    p = tmp_path / "perf.xml"
    p.write_text(
        '<meandata><interval begin="nan" end="60" id="i">'
        '<edge id="e1" speed="10.0" sampledSeconds="100.0" timeLoss="1.0"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    r = parse_edge_performance(str(p))
    assert r["parse_success"] is False
    assert r["invalid_record_count"] == 1  # begin 非有限 → 该 interval 全部 edge 计 invalid
    assert r["total_vehicle_km"] == 0.0  # 原子：整段不产生贡献


def test_edge_perf_missing_begin_fails_closed(tmp_path):
    p = tmp_path / "perf.xml"
    p.write_text(
        '<meandata><interval end="60" id="i">'
        '<edge id="e1" speed="10.0" sampledSeconds="100.0" timeLoss="1.0"/>'
        '<edge id="e2" speed="5.0" sampledSeconds="50.0" timeLoss="2.0"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    r = parse_edge_performance(str(p))
    assert r["parse_success"] is False
    assert r["invalid_record_count"] == 2


def test_edge_perf_missing_id_fails_closed(tmp_path):
    p = tmp_path / "perf.xml"
    p.write_text(
        '<meandata><interval begin="0" end="60" id="i">'
        '<edge speed="10.0" sampledSeconds="100.0" timeLoss="1.0"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    r = parse_edge_performance(str(p))
    assert r["parse_success"] is False
    assert r["invalid_record_count"] == 1


def test_edge_perf_negative_values_fail_closed(tmp_path):
    for attr, bad in (("speed", "-1.0"), ("sampledSeconds", "-5.0"), ("timeLoss", "-3.0")):
        p = tmp_path / "perf.xml"
        attrs = {"speed": "10.0", "sampledSeconds": "100.0", "timeLoss": "1.0", "id": "e1"}
        attrs[attr] = bad
        xml_attrs = " ".join(f'{k}="{v}"' for k, v in attrs.items())
        p.write_text(
            f'<meandata><interval begin="0" end="60" id="i"><edge {xml_attrs}/></interval></meandata>',
            encoding="utf-8",
        )
        r = parse_edge_performance(str(p))
        assert r["parse_success"] is False, attr
        assert r["invalid_record_count"] == 1, attr


def test_edge_perf_no_partial_contribution_for_bad_record(tmp_path):
    """坏记录（timeLoss 为负）不得贡献任何 distance/timeLoss（原子验证后累计）。"""
    p = tmp_path / "perf.xml"
    p.write_text(
        '<meandata><interval begin="0" end="60" id="i">'
        '<edge id="e1" speed="10.0" sampledSeconds="100.0" timeLoss="5.0"/>'
        '<edge id="e2" speed="10.0" sampledSeconds="100.0" timeLoss="-1.0"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    r = parse_edge_performance(str(p))
    assert r["parse_success"] is False
    assert r["invalid_record_count"] == 1
    assert math.isclose(r["total_vehicle_km"], 1.0)  # 仅 e1
    assert math.isclose(r["total_time_loss_s"], 5.0)  # 仅 e1


def test_edge_emis_begin_nan_fails_closed(tmp_path):
    p = tmp_path / "emis.xml"
    p.write_text(
        '<meandata><interval begin="nan" end="60" id="i">'
        '<edge id="e1" CO2_abs="1000" NOx_abs="2.0" PMx_abs="0.1" fuel_abs="500.0"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    r = parse_edge_emissions(str(p))
    assert r["parse_success"] is False
    assert r["invalid_record_count"] == 1
    assert r["total_CO2_kg"] == 0.0


def test_edge_emis_missing_id_fails_closed(tmp_path):
    p = tmp_path / "emis.xml"
    p.write_text(
        '<meandata><interval begin="0" end="60" id="i">'
        '<edge CO2_abs="1000" NOx_abs="2.0" PMx_abs="0.1" fuel_abs="500.0"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    r = parse_edge_emissions(str(p))
    assert r["parse_success"] is False
    assert r["invalid_record_count"] == 1


@pytest.mark.parametrize("neg_key", ["CO2_abs", "NOx_abs", "PMx_abs", "fuel_abs"])
def test_edge_emis_negative_abs_fails_closed(tmp_path, neg_key):
    """任一 *_abs 为负 → invalid（含 sampledSeconds 确保真正命中负值分支）。"""
    attrs = {
        "id": "e1",
        "sampledSeconds": "100.0",
        "CO2_abs": "1000",
        "NOx_abs": "2.0",
        "PMx_abs": "0.1",
        "fuel_abs": "500.0",
    }
    attrs[neg_key] = "-1.0"
    xml_attrs = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    p = tmp_path / "emis.xml"
    p.write_text(
        f'<meandata><interval begin="0" end="60" id="i"><edge {xml_attrs}/></interval></meandata>',
        encoding="utf-8",
    )
    r = parse_edge_emissions(str(p))
    assert r["parse_success"] is False, neg_key
    assert r["invalid_record_count"] == 1, neg_key
    # 原子：负值 edge 零贡献（全部累计量为零）
    assert r["total_CO2_kg"] == 0.0, neg_key
    assert r["total_NOx_g"] == 0.0, neg_key
    assert r["total_PMx_g"] == 0.0, neg_key
    assert r["total_fuel_kg"] == 0.0, neg_key
    assert r["non_internal_CO2_kg"] == 0.0, neg_key


# ── Delta review 补齐：P1-2 主强度与 subgroup 非负门禁 ──


def test_summary_contract_rejects_negative_main_emission_intensities():
    for key in ("CO2_g_per_veh_km", "NOx_mg_per_veh_km", "PMx_mg_per_veh_km", "fuel_g_per_veh_km"):
        summary = _valid_v4_2_summary()
        summary[key] = -1.0
        errors = validate_summary_contract(summary, "2", pipeline_version=PIPELINE)
        assert any(key in e and "non-negative" in e for e in errors), (key, errors)


def test_subgroup_nonnegative_metrics_cover_v4_2_fields():
    from scripts.results.writer import _expected_subgroup_keys, _valid_subgroup_rows

    expected = _expected_subgroup_keys(False)
    spec = {
        "scenario": "scenario_0",
        "model": "IDM",
        "requested_pcav": None,
        "cav_count": 5,
        "vehicle_count": 10,
        "seed": 1,
        "sumo_seed": 101,
    }
    rows = [
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
            "metric_name": metric,
            "metric_value": (
                0
                if metric
                in {
                    "window_count",
                    "ttc_event_count",
                    "drac_event_count",
                    "emergency_braking_count",
                    "affected_vehicle_count",
                    "lane_change_count",
                    "unsafe_lc_gap_count",
                    "completed_lap_count",
                    "valid_thw_sample_count",
                    "low_speed_excluded_count",
                    "no_leader_count",
                    "self_leader_count",
                }
                else 0.0
            ),
        }
        for family, dimension, value, metric in expected
    ]
    assert _valid_subgroup_rows(rows, "run-1", spec)
    negative_fields = (
        "non_internal_CO2_kg",
        "non_internal_NOx_g",
        "non_internal_PMx_g",
        "non_internal_fuel_kg",
        "whole_network_CO2_g_per_veh_km",
        "whole_network_NOx_mg_per_veh_km",
        "whole_network_PMx_mg_per_veh_km",
        "whole_network_fuel_g_per_veh_km",
        "CO2_g_per_veh_km",
        "NOx_mg_per_veh_km",
        "PMx_mg_per_veh_km",
        "fuel_g_per_veh_km",
    )
    for target in negative_fields:
        mutated = [dict(row) for row in rows]
        for row in mutated:
            if row["metric_name"] == target:
                row["metric_value"] = -1.0
                break
        else:
            raise AssertionError(f"{target} not in expected subgroup keys")
        assert not _valid_subgroup_rows(mutated, "run-1", spec), target


# ── Delta review 补齐：P1-3 treatment 级 assignment_seeds 严格校验 ──


def test_config_rejects_float_treatment_assignment_seed(tmp_path):
    data = json.loads(Path("configs/v0.4.2/main.json").read_text(encoding="utf-8"))
    data["treatments"] = [
        {"vehicle_count": 10, "cav_counts": [0, 10], "assignment_seeds": [1.9, 2, 3]}
    ]
    path = tmp_path / "c.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="assignment_seeds"):
        load_experiment_config(path)


def test_edge_perf_empty_edge_omitted_attrs_is_valid(tmp_path):
    """无车 edge（sampledSeconds=0.00）缺省 speed/timeLoss 为合法零贡献（SUMO 形态）。"""
    p = tmp_path / "perf.xml"
    p.write_text(
        '<meandata><interval begin="0" end="60" id="i">'
        '<edge id="e15" sampledSeconds="0.00"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    r = parse_edge_performance(str(p))
    assert r["parse_success"] is True
    assert r["invalid_record_count"] == 0
    assert r["total_vehicle_km"] == 0.0
    assert r["total_time_loss_s"] == 0.0


def test_edge_perf_omitted_speed_with_exposure_fails_closed(tmp_path):
    """有车（ss>0）却缺 speed → invalid。"""
    p = tmp_path / "perf.xml"
    p.write_text(
        '<meandata><interval begin="0" end="60" id="i">'
        '<edge id="e1" sampledSeconds="100.0" timeLoss="1.0"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    r = parse_edge_performance(str(p))
    assert r["parse_success"] is False
    assert r["invalid_record_count"] == 1


def test_edge_emis_empty_edge_omitted_attrs_is_valid(tmp_path):
    """无车 edge（sampledSeconds=0.00）缺省 *_abs 为合法零贡献（SUMO 形态）。"""
    p = tmp_path / "emis.xml"
    p.write_text(
        '<meandata><interval begin="0" end="60" id="i">'
        '<edge id="e15" sampledSeconds="0.00"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    r = parse_edge_emissions(str(p))
    assert r["parse_success"] is True
    assert r["invalid_record_count"] == 0
    assert r["total_CO2_kg"] == 0.0


# ── 审查 P0-1：DRAC 空间配对事件率（全路网 DRAC 事件 / 全路网 veh-km）──


def test_v4_2_run_level_columns_include_drac_rate():
    from scripts.schema import (
        DRAC_RATE_COLUMNS_V4_2,
        RUN_LEVEL_COLUMNS_V4_1,
        RUN_LEVEL_COLUMNS_V4_2,
    )

    assert "drac_events_per_1000_veh_km" in RUN_LEVEL_COLUMNS_V4_2
    assert "drac_events_per_1000_veh_km" in DRAC_RATE_COLUMNS_V4_2
    assert "drac_events_per_1000_veh_km" not in RUN_LEVEL_COLUMNS_V4_1  # v0.4.1 冻结


def test_writer_recomputes_drac_rate_v4_2():
    from scripts.results.writer import _build_row_v4_1

    summary = {
        "run_id": "r",
        "scenario": "scenario_0",
        "model": "IDM",
        "det_xml": "x",
        "vehN": 10,
        "drac_conflict_event_count": 100,
        "total_vehicle_km": 10.0,
    }
    row = _build_row_v4_1(summary, "SUCCESS", pipeline_version="v0.4.2")
    assert row["drac_events_per_1000_veh_km"] == pytest.approx(100.0 / 10.0 * 1000.0)


def test_writer_drac_rate_nan_when_not_collected():
    """main factorial ssm_not_collected：DRAC 计数为 NaN → 率 NaN（未采集语义）。"""
    from scripts.results.writer import _build_row_v4_1

    summary = {
        "run_id": "r",
        "scenario": "scenario_0",
        "model": "IDM",
        "det_xml": "x",
        "vehN": 10,
        "drac_conflict_event_count": math.nan,
        "total_vehicle_km": 10.0,
    }
    row = _build_row_v4_1(summary, "SUCCESS", pipeline_version="v0.4.2")
    assert math.isnan(row["drac_events_per_1000_veh_km"])


def test_aggregate_metrics_include_drac_rate():
    from scripts.results.aggregate import METRIC_COLUMNS

    assert "drac_events_per_1000_veh_km" in METRIC_COLUMNS


def test_paired_drac_metric_column():
    import pandas as pd

    from scripts.results.visualization import _paired_drac_metric_column

    assert _paired_drac_metric_column(pd.DataFrame({"drac_per_k_mean": [1.0]})) == "drac_per_k_mean"
    with pytest.raises(ValueError, match="drac_per_k_mean"):
        _paired_drac_metric_column(pd.DataFrame({"ttc_per_k_mean": [1.0]}))


# ── 审查 P1-2：SSM 解析器语义损坏记录 fail-closed ──

from scripts.parsing.ssm import parse_ssm, parse_ssm_subgroup  # noqa: E402


def test_ssm_nan_value_fails_closed(tmp_path):
    """value=\"nan\"（语义损坏）→ invalid，不再静默记为无 TTC 事件。"""
    p = tmp_path / "ssm.xml"
    p.write_text(
        '<SSMLog><conflict begin="100" end="200" ego="v1" foe="v2">'
        '<minTTC time="150" type="3" value="nan"/></conflict></SSMLog>',
        encoding="utf-8",
    )
    r = parse_ssm(str(p), warmup_period=0)
    assert r["parse_success"] is False
    assert r["ssm_invalid_record_count"] == 1
    assert r["ttc_conflict_event_count"] == 0


def test_ssm_begin_nan_fails_closed(tmp_path):
    p = tmp_path / "ssm.xml"
    p.write_text(
        '<SSMLog><conflict begin="nan" end="200" ego="v1" foe="v2">'
        '<minTTC time="150" type="3" value="1.0"/></conflict></SSMLog>',
        encoding="utf-8",
    )
    r = parse_ssm(str(p), warmup_period=0)
    assert r["parse_success"] is False
    assert r["ssm_invalid_record_count"] == 1


def test_ssm_missing_ego_fails_closed(tmp_path):
    p = tmp_path / "ssm.xml"
    p.write_text(
        '<SSMLog><conflict begin="100" end="200" foe="v2">'
        '<minTTC time="150" type="3" value="1.0"/></conflict></SSMLog>',
        encoding="utf-8",
    )
    r = parse_ssm(str(p), warmup_period=0)
    assert r["parse_success"] is False
    assert r["ssm_invalid_record_count"] == 1


def test_ssm_reversed_interval_fails_closed(tmp_path):
    """区间检查：end < begin 为语义损坏。"""
    p = tmp_path / "ssm.xml"
    p.write_text(
        '<SSMLog><conflict begin="200" end="100" ego="v1" foe="v2">'
        '<minTTC time="150" type="3" value="1.0"/></conflict></SSMLog>',
        encoding="utf-8",
    )
    r = parse_ssm(str(p), warmup_period=0)
    assert r["parse_success"] is False
    assert r["ssm_invalid_record_count"] == 1


def test_ssm_subgroup_missing_type_fails_closed(tmp_path):
    """subgroup 路径：minTTC 元素存在但 type 缺失（SUMO 恒输出数字 type）→ invalid。"""
    p = tmp_path / "ssm.xml"
    p.write_text(
        '<SSMLog><conflict begin="100" end="200" ego="v1" foe="v2">'
        '<minTTC time="150" value="1.0"/></conflict></SSMLog>',
        encoding="utf-8",
    )
    r = parse_ssm_subgroup(str(p), {}, warmup_period=0)
    assert r["all"]["parse_success"] is False
    assert r["all"]["ssm_invalid_record_count"] == 1


def test_ssm_valid_fixture_still_succeeds():
    r = parse_ssm(os.path.join(FIXTURES, "ssm_minimal.xml"), warmup_period=600)
    assert r["parse_success"] is True
    assert r["ssm_invalid_record_count"] == 0


# ── 审查 P2-3：writer --dry-run 核验磁盘终态（resume 场景 manifest 含 SKIPPED）──


def test_writer_dry_run_reports_disk_status(tmp_path):
    import subprocess
    import sys as _sys

    raw = tmp_path / "raw"
    (raw / "r1").mkdir(parents=True)
    (raw / "r2").mkdir()
    (raw / "r1" / "simulation_status.json").write_text(
        json.dumps({"run_id": "r1", "status": "SUCCESS"}), encoding="utf-8"
    )
    (raw / "r2" / "simulation_status.json").write_text(
        json.dumps({"run_id": "r2", "status": "SUCCESS"}), encoding="utf-8"
    )
    manifest = {
        "pipeline_version": "v0.4.2",
        "total": 2,
        "results": [
            {"run_id": "r1", "status": "SUCCESS"},
            {"run_id": "r2", "status": "SKIPPED"},  # resume 场景：manifest 记录 SKIPPED
        ],
    }
    mp = tmp_path / "manifest.json"
    mp.write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "out"
    proc = subprocess.run(
        [
            _sys.executable,
            "-m",
            "scripts.results.writer",
            "--input-root",
            str(raw),
            "--output-dir",
            str(out),
            "--manifest",
            str(mp),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    assert proc.returncode == 0, proc.stderr
    # 修复前只报 manifest 内 SUCCESS（1）；修复后追加磁盘终态（2/2）
    assert "1 manifest-SUCCESS" in proc.stdout
    assert "2/2 disk simulation_status=SUCCESS" in proc.stdout


# ── 审查 P1-1/P2-1：SSM 敏感性分析 fail-closed ──


def test_sensitivity_load_failure_fails_closed(tmp_path):
    """审阅 P1-1：load_run_spec 失败不得静默跳过（防止生成缺 run 的分析结果）。"""
    from scripts.analysis.ssm_sensitivity import run_sensitivity

    rd = tmp_path / "input" / "run1"
    rd.mkdir(parents=True)
    (rd / "ssm.xml").write_text("<SSMLog/>", encoding="utf-8")
    (rd / "run_spec.json").write_text("{broken json", encoding="utf-8")
    cfg = tmp_path / "analysis.json"
    cfg.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="failed to load"):
        run_sensitivity(tmp_path / "input", tmp_path / "out", str(cfg))


def test_dedup_none_bad_record_fails_closed(tmp_path):
    """审阅 P2-1：敏感性 none 路径坏记录（value=\"nan\"）不再静默跳过。"""
    from scripts.analysis.ssm_sensitivity import _dedup_none

    p = tmp_path / "ssm.xml"
    p.write_text(
        '<SSMLog><conflict begin="100" end="200" ego="v1" foe="v2">'
        '<minTTC time="150" type="3" value="nan"/></conflict></SSMLog>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="damaged"):
        _dedup_none(str(p), warmup=0, ttc_th=3.0, drac_th=3.0)


def test_dedup_sorted_greedy_bad_record_fails_closed(tmp_path):
    """审阅 P2-1：敏感性 sorted_greedy 路径坏 begin 不再静默跳过。"""
    from scripts.analysis.ssm_sensitivity import _dedup_sorted_greedy

    p = tmp_path / "ssm.xml"
    p.write_text(
        '<SSMLog><conflict begin="nan" end="200" ego="v1" foe="v2">'
        '<minTTC time="150" type="3" value="1.0"/></conflict></SSMLog>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="damaged"):
        _dedup_sorted_greedy(str(p), warmup=0, ttc_th=3.0, drac_th=3.0)


# ── 审查 P2-2：RunSpec 反序列化严格布尔 ──


def test_run_spec_strict_bool_from_dict():
    from scripts.run_spec import PIPELINE_V4_2, RunSpec

    base = RunSpec(
        **{
            "scenario": "scenario_0",
            "model": "IDM",
            "pcav": 0.5,
            "vehicle_count": 10,
            "seed": 7,
            "run_id": "stable-id",
            "simulation_end": 37.0,
            "warmup": 5.0,
            "step_length": 0.1,
            "detector_frequency": 5,
            "edge_data_frequency": 5,
            "loops": 2,
            "network_file": "net/scenario_0/loop.net.xml",
            "pipeline_version": PIPELINE_V4_2,
        }
    ).to_dict()
    data = dict(base)
    assert data["pipeline_version"] == PIPELINE_V4_2
    # 字符串白名单：false → False，true → True（不再 bool("false")=True）
    data["ssm_trajectories"] = "false"
    assert RunSpec.from_dict(data).ssm_trajectories is False
    data["with_internal"] = "true"
    assert RunSpec.from_dict(data).with_internal is True
    data["ssm_enabled"] = "false"
    spec = RunSpec.from_dict(data)
    assert spec.ssm_enabled is False
    # 数字型布尔 → 拒绝（与配置层严格布尔一致）
    data["with_internal"] = 1
    with pytest.raises(ValueError, match="with_internal"):
        RunSpec.from_dict(data)


# ── 审查 P1-2：legacy post3 重分析传 simulation_end ──


def test_reanalyze_passes_simulation_end_to_parse_ssm():
    """审阅 P1-2：reanalyze_post3 的 parse_ssm 调用必须携带 simulation_end
    （SSM 观测窗 [warmup, simulation_end)，防止 3600s 后极值混入）。"""
    import inspect

    from scripts.results import reanalyze_post3

    src = inspect.getsource(reanalyze_post3.reanalyze)
    assert 'simulation_end=float(row["simulation_end_s"])' in src


# ── 审查 P1/P2 复审残留：敏感性完整性 + _dedup_none canonical 对齐 ──


def test_sensitivity_missing_ssm_file_fails_closed(tmp_path):
    """复审 P1：缺 ssm.xml 的 run 不得在目录收集阶段被静默过滤。"""
    from scripts.analysis.ssm_sensitivity import run_sensitivity

    rd = tmp_path / "input" / "run1"
    rd.mkdir(parents=True)
    # run 目录存在但无 ssm.xml（也无 ssm_compact.xml）
    (rd / "run_spec.json").write_text("{}", encoding="utf-8")
    cfg = tmp_path / "analysis.json"
    cfg.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="missing ssm"):
        run_sensitivity(tmp_path / "input", tmp_path / "out", str(cfg))


def test_dedup_none_xml_parse_failure_raises(tmp_path):
    """复审 P2：XML 解析失败抛错，不再返回全零结果。"""
    from scripts.analysis.ssm_sensitivity import _dedup_none

    p = tmp_path / "ssm.xml"
    p.write_text("<SSMLog><conflict", encoding="utf-8")  # 截断 XML
    with pytest.raises(ValueError, match="failed to parse"):
        _dedup_none(str(p), warmup=0, ttc_th=3.0, drac_th=3.0)


def test_dedup_none_missing_ego_fails_closed(tmp_path):
    """复审 P2：ego/foe 必填（与 canonical 一致）。"""
    from scripts.analysis.ssm_sensitivity import _dedup_none

    p = tmp_path / "ssm.xml"
    p.write_text(
        '<SSMLog><conflict begin="100" end="200" foe="v2">'
        '<minTTC time="150" type="3" value="1.0"/></conflict></SSMLog>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="damaged"):
        _dedup_none(str(p), warmup=0, ttc_th=3.0, drac_th=3.0)


def test_dedup_sorted_greedy_xml_parse_failure_raises(tmp_path):
    """复审 P2：sorted_greedy XML 解析失败抛错，不再返回全零结果。"""
    from scripts.analysis.ssm_sensitivity import _dedup_sorted_greedy

    p = tmp_path / "ssm.xml"
    p.write_text("<SSMLog><conflict", encoding="utf-8")  # 截断 XML
    with pytest.raises(ValueError, match="failed to parse"):
        _dedup_sorted_greedy(str(p), warmup=0, ttc_th=3.0, drac_th=3.0)


def test_dedup_sorted_greedy_missing_ego_fails_closed(tmp_path):
    """复审 P2：sorted_greedy ego/foe 必填（与 canonical 一致）。"""
    from scripts.analysis.ssm_sensitivity import _dedup_sorted_greedy

    p = tmp_path / "ssm.xml"
    p.write_text(
        '<SSMLog><conflict begin="100" end="200" foe="v2">'
        '<minTTC time="150" type="3" value="1.0"/></conflict></SSMLog>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="damaged"):
        _dedup_sorted_greedy(str(p), warmup=0, ttc_th=3.0, drac_th=3.0)


# ── 审查 P1-1：TTC/DRAC pair 归类分别使用各自 provenance ──


def test_ssm_pair_type_uses_drac_provenance():
    """DRAC pair 计数必须使用 max_drac_source（不得套用 min_ttc_source）。"""
    import inspect

    from scripts.parsing.ssm import parse_ssm_subgroup

    src = inspect.getsource(parse_ssm_subgroup)
    # has_drac 分支从 max_drac_source_* 构造 pair_type
    assert 'rec.get("max_drac_source_ego") or rec["ego"]' in src
    # pair 计算不再统一用 min_ttc_source 喂给两个计数
    assert "drac_pair_type = _pair_type(" in src


def test_ssm_pair_drac_only_event_counts_by_own_provenance(tmp_path):
    """DRAC-only conflict（无 minTTC）的 pair 计数正确（回归保护）。"""
    from scripts.parsing.ssm import parse_ssm_subgroup

    p = tmp_path / "ssm.xml"
    p.write_text(
        '<SSMLog><conflict begin="100" end="200" ego="veh1" foe="veh2">'
        '<maxDRAC time="150" type="3" value="6.0"/></conflict></SSMLog>',
        encoding="utf-8",
    )
    type_map = {"veh1": "CAV", "veh2": "CAV"}
    r = parse_ssm_subgroup(str(p), type_map, warmup_period=0)
    assert r["all"]["drac_conflict_event_count"] == 1
    assert r["pair_CAV_CAV"]["drac_event_count"] == 1
    assert r["all"]["ttc_conflict_event_count"] == 0


# ── 审查 P1-2：frozen_inputs/ 等非 run 目录不得误报 ──


def test_sensitivity_ignores_non_run_dirs(tmp_path):
    """frozen_inputs/（无 run_spec.json 的归档目录）不得计入失败集合。"""
    from scripts.analysis.ssm_sensitivity import run_sensitivity

    root = tmp_path / "input"
    (root / "frozen_inputs").mkdir(parents=True)
    (root / "frozen_inputs" / "net.xml").write_text("<net/>", encoding="utf-8")
    cfg = tmp_path / "analysis.json"
    cfg.write_text("{}", encoding="utf-8")
    # 无 run_spec.json 的目录 → 全部跳过 → 空结果 CSV 正常生成，不抛错
    run_sensitivity(str(root), str(tmp_path / "out"), str(cfg))


# ── 审查 P1-3：_dedup_current 检查 parse_success ──


def test_dedup_current_checks_parse_success(tmp_path):
    from scripts.analysis.ssm_sensitivity import _dedup_current

    p = tmp_path / "ssm.xml"
    p.write_text(
        '<SSMLog><conflict begin="100" end="200" ego="v1" foe="v2">'
        '<minTTC time="150" type="3" value="nan"/></conflict></SSMLog>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="parse_success"):
        _dedup_current(str(p), warmup=0, ttc_th=3.0, drac_th=3.0)


def test_ssm_pair_mirror_merge_split_provenance(tmp_path):
    """审阅 P2（复核修正）：pair_type 无方向，方向影响真正落在 DRAC role 计数上——
    镜像去重后 DRAC 极值来自反向记录 B（type=2 → follower=ego=CAV），DRAC role 必须按
    max_drac_source 归入 role_f_CAV_l_HV，而 TTC role 按 min_ttc_source 归入
    role_f_HV_l_CAV（两个方向分别保留）。"""
    from scripts.parsing.ssm import parse_ssm_subgroup

    p = tmp_path / "ssm.xml"
    p.write_text(
        "<SSMLog>"
        # A（正向 veh1→veh2，type=2 → follower=ego=HV, leader=foe=CAV）
        '<conflict begin="100" end="200" ego="veh1" foe="veh2">'
        '<minTTC time="150" type="2" value="1.0"/>'
        '<maxDRAC time="150" type="2" value="4.0"/>'
        "</conflict>"
        # B（反向 veh2→veh1，type=2 → follower=ego=CAV, leader=foe=HV）
        '<conflict begin="110" end="210" ego="veh2" foe="veh1">'
        '<minTTC time="160" type="2" value="2.0"/>'
        '<maxDRAC time="160" type="2" value="8.0"/>'
        "</conflict>"
        "</SSMLog>",
        encoding="utf-8",
    )
    type_map = {"veh1": "HV", "veh2": "CAV"}
    r = parse_ssm_subgroup(str(p), type_map, warmup_period=0)
    # 镜像合并：1 条保留记录（A），min_ttc 来自 A（1.0）、max_drac 来自 B（8.0）
    assert r["all"]["ssm_mirrored_record_count"] == 1
    assert r["all"]["min_ttc_s"] == 1.0
    assert r["all"]["max_drac_mps2"] == 8.0
    # pair 无方向：TTC/DRAC 均归入 pair_HV_CAV
    assert r["pair_HV_CAV"]["ttc_event_count"] == 1
    assert r["pair_HV_CAV"]["drac_event_count"] == 1
    # role 有方向：TTC 按 min_ttc_source（follower=HV），DRAC 按 max_drac_source
    # （follower=CAV）——各自落在正确方向，互不串位
    assert r["role_f_HV_l_CAV"]["ttc_event_count"] == 1
    assert r["role_f_HV_l_CAV"]["drac_event_count"] == 0
    assert r["role_f_CAV_l_HV"]["drac_event_count"] == 1
    assert r["role_f_CAV_l_HV"]["ttc_event_count"] == 0


# ── 审查 P1-2：detector/vehroute/lanechange fail-closed ──


def test_detector_nan_flow_fails_closed(tmp_path):
    """detector：nan 流量不得当作有效数据（fail-closed 抛 ValueError）。"""
    from scripts.parsing.detector import parse_detector

    p = tmp_path / "det.xml"
    p.write_text(
        '<detector xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<interval begin="0.00" end="60.00" id="det0" flow="nan" speed="10.0"/>'
        "</detector>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-finite"):
        parse_detector(str(p), warmup_period=0)


def test_detector_subgroup_bad_data_marks_parse_failure(tmp_path):
    """detector subgroup：语义损坏 → parse_success=False（writer 将标 parser_warning）。"""
    from scripts.parsing.detector import parse_detector_subgroup

    p = tmp_path / "det.xml"
    p.write_text(
        '<detector><interval begin="0.00" end="60.00" id="det0" flow="BAD" speed="10.0"/>'
        "</detector>",
        encoding="utf-8",
    )
    r = parse_detector_subgroup([str(p)], [str(p)], [str(p)], warmup_period=0)
    assert r["all"]["parse_success"] is False


def test_vehroute_bad_exit_time_fails_closed(tmp_path):
    """vehroute：exitTimes 含非数值/非有限 → parse_success=False（不得静默跳过伪造圈次）。"""
    from scripts.parsing.vehroute import parse_lap_times

    p = tmp_path / "vehroute.xml"
    p.write_text(
        '<routes><vehicle id="v0" depart="0.00">'
        '<route edges="e0 e1 e2 e3" exitTimes="10.0 20.0 nan 40.0 50.0 60.0 70.0 80.0"/>'
        "</vehicle></routes>",
        encoding="utf-8",
    )
    r = parse_lap_times(str(p), 4, warmup_period=0, sim_end_time=3600.0)
    assert r["parse_success"] is False


def test_lanechange_nan_time_fails_closed(tmp_path):
    """lanechange：time=\"nan\" 不得计入换道（fail-closed）。"""
    from scripts.parsing.lanechange import parse_lanechange

    p = tmp_path / "lc.xml"
    p.write_text(
        '<laneChanges><change id="v0" time="nan" type="LC" lane="0" '
        'leaderGap="10.0" leaderSecureGap="5.0" followerGap="10.0" followerSecureGap="5.0"/>'
        "</laneChanges>",
        encoding="utf-8",
    )
    r = parse_lanechange(str(p), warmup_period=0)
    assert r["parse_success"] is False
    assert r["lane_change_count"] == 0


# ── 审查 P1-2（复核）：subgroup 解析路径 fail-closed ──


def test_vehroute_subgroup_bad_exit_time_fails_closed(tmp_path):
    from scripts.parsing.vehroute import parse_lap_times_subgroup

    p = tmp_path / "vehroute.xml"
    p.write_text(
        '<routes><vehicle id="v0" depart="0.00">'
        '<route edges="e0 e1 e2 e3" exitTimes="10.0 20.0 nan 40.0 50.0 60.0 70.0 80.0"/>'
        "</vehicle></routes>",
        encoding="utf-8",
    )
    r = parse_lap_times_subgroup(str(p), {"v0": "CAV"}, 4, warmup_period=0, sim_end_time=3600.0)
    assert r["all"]["parse_success"] is False


def test_lanechange_subgroup_nan_time_fails_closed(tmp_path):
    from scripts.parsing.lanechange import parse_lanechange_subgroup

    p = tmp_path / "lc.xml"
    p.write_text(
        '<laneChanges><change id="v0" time="nan" type="LC" lane="0" '
        'leaderGap="10.0" leaderSecureGap="5.0" followerGap="10.0" followerSecureGap="5.0"/>'
        "</laneChanges>",
        encoding="utf-8",
    )
    r = parse_lanechange_subgroup(str(p), {"v0": "CAV"}, warmup_period=0)
    assert r["all"]["parse_success"] is False
    assert r["all"]["lane_change_count"] == 0


def test_detector_multi_nan_flow_fails_closed(tmp_path):
    """两个文件触发 parse_detector_multi 的多车道分支（单文件会委托 parse_detector）。"""
    from scripts.parsing.detector import parse_detector_multi

    p = tmp_path / "det.xml"
    p.write_text(
        '<detector><interval begin="0.00" end="60.00" id="det0" flow="nan" speed="10.0"/>'
        "</detector>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-finite"):
        parse_detector_multi([str(p), str(p)], warmup_period=0)


def test_vehroute_subgroup_empty_result_branch_fails_closed(tmp_path):
    """exitTimes 全坏值 → 空值 _stats 分支也必须 parse_success=False（审阅 P2 残留）。"""
    from scripts.parsing.vehroute import parse_lap_times_subgroup

    p = tmp_path / "vehroute.xml"
    p.write_text(
        '<routes><vehicle id="v0" depart="0.00">'
        '<route edges="e0 e1 e2 e3" exitTimes="nan"/>'
        "</vehicle></routes>",
        encoding="utf-8",
    )
    r = parse_lap_times_subgroup(str(p), {"v0": "CAV"}, 4, warmup_period=0, sim_end_time=3600.0)
    assert r["all"]["parse_success"] is False


# ── 审查 P1-1：vehroute 非单调时间 → invalid ──


def test_vehroute_non_monotonic_times_fails_closed(tmp_path):
    """非单调 exitTimes（lap_end < lap_start）→ invalid，不得生成负圈时。"""
    from scripts.parsing.vehroute import parse_lap_times

    p = tmp_path / "vehroute.xml"
    p.write_text(
        '<routes><vehicle id="v0" depart="0.00">'
        '<route edges="e0 e1 e2 e3" exitTimes="10 20 30 50 10 20 30 40"/>'
        "</vehicle></routes>",
        encoding="utf-8",
    )
    r = parse_lap_times(str(p), 4, warmup_period=0, sim_end_time=3600.0)
    assert r["parse_success"] is False
    assert r["completed_lap_count"] == 0  # 负圈时不得计入


def test_vehroute_subgroup_non_monotonic_times_fails_closed(tmp_path):
    from scripts.parsing.vehroute import parse_lap_times_subgroup

    p = tmp_path / "vehroute.xml"
    p.write_text(
        '<routes><vehicle id="v0" depart="0.00">'
        '<route edges="e0 e1 e2 e3" exitTimes="10 20 30 50 10 20 30 40"/>'
        "</vehicle></routes>",
        encoding="utf-8",
    )
    r = parse_lap_times_subgroup(str(p), {"v0": "CAV"}, 4, warmup_period=0, sim_end_time=3600.0)
    assert r["all"]["parse_success"] is False


# ── 审查 P2-2：可视化模式互斥 ──


def test_visualization_modes_are_mutually_exclusive(tmp_path, monkeypatch):
    import sys

    import scripts.results.visualization as viz

    monkeypatch.setattr(
        sys, "argv", ["viz", "--safety", "--v4-2", "--aggregated", str(tmp_path / "none.csv")]
    )
    with pytest.raises(SystemExit):
        viz.main()
    # --v4 与 --v4-2 同样互斥
    monkeypatch.setattr(
        sys, "argv", ["viz", "--v4", "--v4-2", "--aggregated", str(tmp_path / "none.csv")]
    )
    with pytest.raises(SystemExit):
        viz.main()


# ── 审查 P2-3：assignment seed 非负 ──


def test_config_rejects_negative_assignment_seed(tmp_path):
    data = json.loads(Path("configs/v0.4.2/main.json").read_text(encoding="utf-8"))
    data["treatments"] = [
        {"vehicle_count": 10, "cav_counts": [0, 10], "assignment_seeds": [-1, 2, 3]}
    ]
    path = tmp_path / "c.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="non-negative"):
        load_experiment_config(path)


# ── 审查 P2-1（复核）：build_network 源 SHA 锚定三态测试 ──


# ── 审查 P1-1：FCD 非法时间戳 fail-closed ──


def test_fcd_invalid_timestep_time_fails_closed(tmp_path):
    """非法/非有限 timestep time → invalid，parse_success=False（不得静默丢弃 FCD 数据）。"""
    import gzip

    from scripts.parsing.fcd import parse_fcd

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<fcd-export>"
        '<timestep time="nan">'
        '<vehicle id="v1" x="0.0" y="0.0" angle="0.0" speed="5.0" lane="e0_0" '
        'pos="5.0" type="passenger"/>'
        "</timestep>"
        "</fcd-export>"
    )
    p = tmp_path / "fcd.xml.gz"
    with gzip.open(p, "wb") as f:
        f.write(xml.encode("utf-8"))
    tm = {"v1": "CAV"}
    r = parse_fcd(str(p), tm, warmup_period=0)
    assert r["all"]["parse_success"] is False


# ── 审查 P2-1：lanechange gap 非法字符串 fail-closed ──


def test_lanechange_bad_gap_fails_closed(tmp_path):
    from scripts.parsing.lanechange import parse_lanechange

    p = tmp_path / "lc.xml"
    p.write_text(
        '<laneChanges><change id="v0" time="100.0" type="LC" lane="0" '
        'leaderGap="BAD" leaderSecureGap="5.0" followerGap="10.0" followerSecureGap="5.0"/>'
        "</laneChanges>",
        encoding="utf-8",
    )
    r = parse_lanechange(str(p), warmup_period=0)
    assert r["parse_success"] is False


def test_lanechange_subgroup_bad_gap_fails_closed(tmp_path):
    from scripts.parsing.lanechange import parse_lanechange_subgroup

    p = tmp_path / "lc.xml"
    p.write_text(
        '<laneChanges><change id="v0" time="100.0" type="LC" lane="0" '
        'leaderGap="nan" leaderSecureGap="5.0" followerGap="10.0" followerSecureGap="5.0"/>'
        "</laneChanges>",
        encoding="utf-8",
    )
    r = parse_lanechange_subgroup(str(p), {"v0": "CAV"}, warmup_period=0)
    assert r["all"]["parse_success"] is False


# ── 审查 P2-2：aggregate 混合角色拒绝 ──


def test_aggregate_rejects_mixed_experiment_role(tmp_path):
    import pandas as pd

    from scripts.results.aggregate import aggregate

    df = pd.DataFrame(
        {
            "scenario": ["scenario_0", "scenario_0"],
            "model": ["IDM", "IDM"],
            "vehN": [10, 10],
            "cav_count": [5, 5],
            "assignment_seed": [1, 2],
            "sumo_seed": [101, 102],
            "experiment_role": ["main_factorial", "safety"],
            "mean_flow_veh_h": [100.0, 120.0],
        }
    )
    p = tmp_path / "mixed.csv"
    df.to_csv(p, index=False)
    with pytest.raises(ValueError, match="experiment_role"):
        aggregate(p, tmp_path / "out.csv", "2", manifest={})


def test_fcd_missing_time_attr_fails_closed(tmp_path):
    """审阅 P2-4：<timestep> 缺失 time 属性 → invalid（不得默认 0 被 warmup 过滤）。"""
    import gzip

    from scripts.parsing.fcd import parse_fcd

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<fcd-export>"
        "<timestep>"
        '<vehicle id="v1" x="0.0" y="0.0" angle="0.0" speed="5.0" lane="e0_0" '
        'pos="5.0" type="passenger"/>'
        "</timestep>"
        "</fcd-export>"
    )
    p = tmp_path / "fcd.xml.gz"
    with gzip.open(p, "wb") as f:
        f.write(xml.encode("utf-8"))
    tm = {"v1": "CAV"}
    r = parse_fcd(str(p), tm, warmup_period=0)
    assert r["all"]["parse_success"] is False


# ── 审查 P1-1（本轮）：vehroute 未完成路段断点语义 ──


def test_vehroute_breakpoint_not_stitched(tmp_path):
    """-1（未到达）出现在圈间 → 断点终止连续段，不得跨越拼接虚假圈次。"""
    from scripts.parsing.vehroute import parse_lap_times

    # 12 个位置，-1 在第 5 位（第 2 圈第 1 edge 未到达）
    p = tmp_path / "vehroute.xml"
    p.write_text(
        '<routes><vehicle id="v0" depart="0.00">'
        '<route edges="e0 e1 e2 e3 e0 e1 e2 e3 e0 e1 e2 e3" '
        'exitTimes="10 20 30 40 -1 60 70 80 90 100 110 120"/>'
        "</vehicle></routes>",
        encoding="utf-8",
    )
    r = parse_lap_times(str(p), 4, warmup_period=0, sim_end_time=3600.0)
    # 旧实现（删 -1 后压缩切片）：lap_ends=[40,80,120] → 圈时 [40,40]（80-40 跨未到达 edge）
    # 新实现（断点重置）：lap_ends=[40,90] → 仅 1 个完整圈时 90-40=50
    assert r["completed_lap_count"] == 1
    assert r["mean_lap_time_s"] == 50.0
    assert r["parse_success"] is True


def test_vehroute_other_negative_value_invalid(tmp_path):
    """除 -1 外的负值 → invalid（只接受约定的 -1 表示未到达）。"""
    from scripts.parsing.vehroute import parse_lap_times

    p = tmp_path / "vehroute.xml"
    p.write_text(
        '<routes><vehicle id="v0" depart="0.00">'
        '<route edges="e0 e1 e2 e3" exitTimes="10 20 30 -5"/>'
        "</vehicle></routes>",
        encoding="utf-8",
    )
    r = parse_lap_times(str(p), 4, warmup_period=0, sim_end_time=3600.0)
    assert r["parse_success"] is False


# ── 审查 P2-1（本轮）：ssm_measures/ssm_range 一致性校验 ──


def test_config_rejects_non_default_ssm_measures(tmp_path):
    data = json.loads(Path("configs/v0.4.2/main.json").read_text(encoding="utf-8"))
    data["ssm_measures"] = "DRAC"  # SUMO 命令硬编码 "TTC DRAC"，此值不生效
    path = tmp_path / "c.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="不生效"):
        load_experiment_config(path)


def test_config_rejects_non_default_ssm_range(tmp_path):
    data = json.loads(Path("configs/v0.4.2/main.json").read_text(encoding="utf-8"))
    data["ssm_range"] = "99.0"  # 废弃字段（single_run 用 ssm_range_m）
    path = tmp_path / "c.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="废弃"):
        load_experiment_config(path)


def test_input_integrity_network_source_change_detected(tmp_path):
    """审阅 P1-1：源文件变化但 net.json 锚定未更新 → verify False。"""
    from scripts.parsing.input_integrity import verify
    from tests.test_v4_2_review_round4 import (
        _full_raw_hashes,
        _make_stub,
        _write_full_status,
    )

    stub = _make_stub(tmp_path)
    rd = tmp_path / "run-1"
    rd.mkdir()
    _write_full_status(rd, _full_raw_hashes(rd, stub), stub)
    # 修改源文件（锚定失效）
    src = tmp_path / "net" / "nodes.nod.xml"
    src.write_text("<nodes changed/>", encoding="utf-8")
    ok, errors = verify(rd, stub)
    assert ok is False
    assert any("network source changed" in e for e in errors)


def _write_sources_anchor(d, sources_sha256):
    (d / "sources.sha256").write_text(sources_sha256 + "\n", encoding="utf-8")


def test_build_network_anchored_match_passes(tmp_path, monkeypatch):
    """锚定且匹配 → 编译通过，无警告。"""
    import scripts.simulation.network_generator as ng

    d = tmp_path / "scenario_0"
    d.mkdir()
    (d / "nodes.nod.xml").write_text("<nodes/>", encoding="utf-8")
    (d / "edges.edg.xml").write_text("<edges/>", encoding="utf-8")
    import hashlib

    digest = hashlib.sha256()
    for name in ("nodes.nod.xml", "edges.edg.xml"):
        digest.update((d / name).read_bytes())
    _write_sources_anchor(d, digest.hexdigest())
    monkeypatch.setattr(ng.subprocess, "run", lambda *a, **k: None)
    out = ng.build_network(str(d), netconvert_command="netconvert")
    assert out == d / "loop.net.xml"


def test_build_network_anchored_mismatch_raises(tmp_path, monkeypatch):
    """锚定但不匹配（源文件已改）→ RuntimeError。"""
    import scripts.simulation.network_generator as ng

    d = tmp_path / "scenario_0"
    d.mkdir()
    (d / "nodes.nod.xml").write_text("<nodes/>", encoding="utf-8")
    (d / "edges.edg.xml").write_text("<edges/>", encoding="utf-8")
    _write_sources_anchor(d, "0" * 64)  # 锚定值与实际源不符
    monkeypatch.setattr(ng.subprocess, "run", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="不一致"):
        ng.build_network(str(d), netconvert_command="netconvert")


def test_build_network_unanchored_fails(tmp_path, monkeypatch):
    """审阅 P1-1：sources.sha256 缺失 → 强制失败（不得警告后继续编译）。"""
    import scripts.simulation.network_generator as ng

    d = tmp_path / "scenario_0"
    d.mkdir()
    (d / "nodes.nod.xml").write_text("<nodes/>", encoding="utf-8")
    (d / "edges.edg.xml").write_text("<edges/>", encoding="utf-8")
    monkeypatch.setattr(ng.subprocess, "run", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="缺失"):
        ng.build_network(str(d), netconvert_command="netconvert")


# ── 审查 P1-1（本轮）：解析器 [warmup, simulation_end) 时间窗 ──


def test_edge_perf_simulation_end_filters_late_intervals(tmp_path):
    from scripts.parsing.edge_performance import parse_edge_performance

    p = tmp_path / "perf.xml"
    p.write_text(
        '<meandata><interval begin="3000" end="3600" id="i1">'
        '<edge id="e1" speed="10.0" sampledSeconds="100.0" timeLoss="5.0"/>'
        "</interval>"
        '<interval begin="3600" end="3700" id="i2">'
        '<edge id="e1" speed="10.0" sampledSeconds="100.0" timeLoss="5.0"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    r = parse_edge_performance(str(p), warmup_period=600, simulation_end=3600)
    assert r["total_vehicle_km"] == 1.0  # 仅 i1（i2 begin>=3600 被排除）
    r2 = parse_edge_performance(str(p), warmup_period=600)  # 无上界：两条都计入
    assert r2["total_vehicle_km"] == 2.0


def test_edge_emis_simulation_end_filters_late_intervals(tmp_path):
    from scripts.parsing.edge_emissions import parse_edge_emissions

    p = tmp_path / "emis.xml"
    p.write_text(
        '<meandata><interval begin="3000" end="3600" id="i1">'
        '<edge id="e1" sampledSeconds="100.0" CO2_abs="1000" NOx_abs="2.0" PMx_abs="0.1" fuel_abs="500.0"/>'
        "</interval>"
        '<interval begin="3600" end="3700" id="i2">'
        '<edge id="e1" sampledSeconds="100.0" CO2_abs="2000" NOx_abs="2.0" PMx_abs="0.1" fuel_abs="500.0"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    r = parse_edge_emissions(str(p), warmup_period=600, simulation_end=3600)
    assert r["total_CO2_kg"] == 1000.0 / 1e6  # 仅 i1


def test_fcd_simulation_end_filters_late_timesteps(tmp_path):
    import gzip

    from scripts.parsing.fcd import parse_fcd

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<fcd-export>"
        '<timestep time="3500">'
        '<vehicle id="v1" x="0.0" y="0.0" angle="0.0" speed="5.0" lane="e0_0" '
        'pos="5.0" type="passenger"/>'
        "</timestep>"
        '<timestep time="3600">'
        '<vehicle id="v1" x="0.0" y="0.0" angle="0.0" speed="5.0" lane="e0_0" '
        'pos="5.0" type="passenger"/>'
        "</timestep>"
        "</fcd-export>"
    )
    p = tmp_path / "fcd.xml.gz"
    with gzip.open(p, "wb") as f:
        f.write(xml.encode("utf-8"))
    tm = {"v1": "CAV"}
    r = parse_fcd(str(p), tm, warmup_period=0, simulation_end=3600)
    assert r["all"]["valid_thw_sample_count"] == 0  # 3600 处 timestep 被排除


def test_fcd_bad_speed_fails_closed(tmp_path):
    """审阅 P2-1：非数值 speed 是语义损坏 → invalid（不得伪装成低速排除）。"""
    import gzip

    from scripts.parsing.fcd import parse_fcd

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<fcd-export>"
        '<timestep time="100">'
        '<vehicle id="v1" x="0.0" y="0.0" angle="0.0" speed="BAD" lane="e0_0" '
        'pos="5.0" type="passenger"/>'
        "</timestep>"
        "</fcd-export>"
    )
    p = tmp_path / "fcd.xml.gz"
    with gzip.open(p, "wb") as f:
        f.write(xml.encode("utf-8"))
    tm = {"v1": "CAV"}
    r = parse_fcd(str(p), tm, warmup_period=0)
    assert r["all"]["parse_success"] is False
    assert r["all"]["low_speed_excluded_count"] == 0  # 非低速排除


def test_detector_negative_flow_fails_closed(tmp_path):
    """审阅 P2-2：负流量 → ValueError（数值域门禁）。"""
    from scripts.parsing.detector import parse_detector

    p = tmp_path / "det.xml"
    p.write_text(
        '<detector><interval begin="0.00" end="60.00" id="det0" flow="-5.0" speed="10.0"/>'
        "</detector>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="negative flow"):
        parse_detector(str(p), warmup_period=0)


# ── 审查 P2（本轮）：聚合输出保留角色列 + 生成函数写 sources.sha256 ──


def test_aggregate_output_preserves_experiment_role(tmp_path):
    """聚合输出保留 experiment_role 列（可视化角色门禁依赖此列）。"""
    import pandas as pd

    from scripts.results.aggregate import aggregate

    df = pd.DataFrame(
        {
            "run_id": ["r1", "r2", "r3", "r4"],
            "scenario": ["scenario_0"] * 4,
            "model": ["IDM"] * 4,
            "vehN": [10] * 4,
            "cav_count": [5] * 4,
            "assignment_seed": [1, 1, 2, 2],
            "sumo_seed": [101, 102, 101, 102],
            "experiment_role": ["safety"] * 4,
            "data_quality": ["ok"] * 4,
            "mean_flow_veh_h": [100.0, 110.0, 120.0, 130.0],
        }
    )
    p = tmp_path / "r.csv"
    df.to_csv(p, index=False)
    manifest = {
        "results": [
            {"run_id": f"r{i}", "assignment_seed": a, "sumo_seed": s}
            for i, (a, s) in enumerate(((1, 101), (1, 102), (2, 101), (2, 102)), start=1)
        ],
        "resolved_config": {
            "treatments": [{"vehicle_count": 10, "assignment_seeds": [1, 2]}],
            "sumo_seeds": [101, 102],
        },
    }
    out = aggregate(p, tmp_path / "agg.csv", "2", manifest=manifest)
    assert "experiment_role" in out.columns
    assert (out["experiment_role"] == "safety").all()


def test_generate_polygon_loop_writes_sources_anchor(tmp_path):
    """生成场景同时写入 sources.sha256（build_network 强制门禁要求）。"""
    from scripts.simulation.network_generator import generate_polygon_loop

    out_dir = tmp_path / "scenario_new"
    generate_polygon_loop(str(out_dir), num_sides=16, radius=500.0, num_lanes=2, speed=20.0)
    assert (out_dir / "sources.sha256").exists()
    content = (out_dir / "sources.sha256").read_text(encoding="utf-8").strip()
    assert len(content) == 64


# ── 审查 P1-1（本轮）：post3 重分析 edgeData 传 simulation_end ──


def test_reanalyze_edge_parsers_pass_simulation_end():
    """post3 重分析 edge performance/emissions 调用必须携带 simulation_end。"""
    import inspect

    from scripts.results import reanalyze_post3

    src = inspect.getsource(reanalyze_post3.reanalyze)
    assert 'simulation_end=float(row["simulation_end_s"])' in src
    assert src.count('simulation_end=float(row["simulation_end_s"])') >= 3  # ssm + perf + emis


# ── 审查 P1-2（本轮）：sensitivity 缺失 time 默认 begin（与主解析一致）──


def test_sensitivity_missing_time_defaults_to_begin(tmp_path):
    """none 路径：极值元素缺失 time → 默认 begin（与 parse_ssm 一致，不再过滤）。"""
    from scripts.analysis.ssm_sensitivity import _dedup_none

    p = tmp_path / "ssm.xml"
    p.write_text(
        '<SSMLog><conflict begin="100" end="200" ego="v1" foe="v2">'
        '<minTTC value="1.0"/>'  # 无 time 属性
        "</conflict></SSMLog>",
        encoding="utf-8",
    )
    ttc_cnt, drac_cnt, min_ttc, max_drac, affected = _dedup_none(
        str(p), warmup=0, ttc_th=3.0, drac_th=3.0
    )
    assert ttc_cnt == 1  # 缺失 time 按 begin=100（warmup 内）保留
    assert min_ttc == 1.0


def test_reanalyze_edge_excludes_late_intervals(tmp_path, monkeypatch):
    """审阅 P1-1（复核补充）：reanalyze 的 edge performance 排除 begin >= simulation_end
    区间（实际 parser 行为，非仅源码锚定）。"""
    import pandas as pd

    import scripts.results.reanalyze_post3 as rp
    from scripts.schema import RUN_LEVEL_COLUMNS

    raw = tmp_path / "raw"
    rd = raw / "r1"
    rd.mkdir(parents=True)
    # performance：interval 3000-3600（窗内）+ 3600-3700（窗外，必须被排除）
    (rd / "performance.xml").write_text(
        '<meandata><interval begin="3000" end="3600" id="i1">'
        '<edge id="e1" speed="10.0" sampledSeconds="100.0" timeLoss="5.0"/>'
        "</interval>"
        '<interval begin="3600" end="3700" id="i2">'
        '<edge id="e1" speed="10.0" sampledSeconds="100.0" timeLoss="5.0"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    (rd / "emissions.xml").write_text(
        '<meandata><interval begin="3000" end="3600" id="i1">'
        '<edge id="e1" sampledSeconds="100.0" CO2_abs="1000" NOx_abs="2.0" PMx_abs="0.1" fuel_abs="500.0"/>'
        "</interval></meandata>",
        encoding="utf-8",
    )
    (rd / "ssm.xml").write_text("<SSMLog/>", encoding="utf-8")
    row = {
        "run_id": "r1",
        "scenario": "scenario_0",
        "model": "IDM",
        "warmup_period_s": 600.0,
        "simulation_end_s": 3600.0,
        "pCAV": 0.5,
        "vehN": 10,
        "seed": 1,
    }
    for col in RUN_LEVEL_COLUMNS:
        row.setdefault(col, 0.0)
    src_csv = tmp_path / "legacy.csv"
    pd.DataFrame([row]).to_csv(src_csv, index=False)
    monkeypatch.setattr(rp, "aggregate", lambda *a, **k: None)  # 跳过聚合
    monkeypatch.setattr(rp, "_write_raw_inventory", lambda *a, **k: {"paths": 0})
    monkeypatch.setattr(rp, "_sha256", lambda *a, **k: "0" * 64)  # 跳过产物哈希读取
    out_dir = tmp_path / "out"
    rp.reanalyze(raw, src_csv, out_dir)
    corrected = pd.read_csv(out_dir / "run_level_results.csv")
    assert corrected.iloc[0]["total_vehicle_km"] == 1.0  # 仅窗内 interval（3600 区间排除）
    assert corrected.iloc[0]["total_time_loss_s"] == 5.0


# ── 审查 P1-1（本轮）：detector/lanechange/stderr/vehroute 时间窗统一 ──


def test_detector_simulation_end_filters_late_intervals(tmp_path):
    from scripts.parsing.detector import parse_detector

    p = tmp_path / "det.xml"
    p.write_text(
        '<detector><interval begin="3000" end="3600" id="i1" flow="100.0" speed="10.0"/>'
        '<interval begin="3600" end="3700" id="i2" flow="100.0" speed="10.0"/>'
        "</detector>",
        encoding="utf-8",
    )
    r = parse_detector(str(p), warmup_period=600, simulation_end=3600)
    assert r[4] == 1  # window_count 仅 1（i2 begin>=3600 排除）


def test_detector_negative_begin_fails_closed(tmp_path):
    from scripts.parsing.detector import parse_detector

    p = tmp_path / "det.xml"
    p.write_text(
        '<detector><interval begin="-5.0" end="60" id="i1" flow="100.0" speed="10.0"/></detector>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="negative begin"):
        parse_detector(str(p), warmup_period=0)


def test_lanechange_simulation_end_and_negative_time(tmp_path):
    from scripts.parsing.lanechange import parse_lanechange

    # time == simulation_end → 排除
    p = tmp_path / "lc.xml"
    p.write_text(
        '<laneChanges><change id="v0" time="3600" type="LC" lane="0" '
        'leaderGap="10.0" leaderSecureGap="5.0" followerGap="10.0" followerSecureGap="5.0"/>'
        "</laneChanges>",
        encoding="utf-8",
    )
    r = parse_lanechange(str(p), warmup_period=0, simulation_end=3600)
    assert r["lane_change_count"] == 0  # 恰在 end 的换道排除
    # 负 time → invalid
    p2 = tmp_path / "lc2.xml"
    p2.write_text(
        '<laneChanges><change id="v0" time="-5.0" type="LC" lane="0" '
        'leaderGap="10.0" leaderSecureGap="5.0" followerGap="10.0" followerSecureGap="5.0"/>'
        "</laneChanges>",
        encoding="utf-8",
    )
    r2 = parse_lanechange(str(p2), warmup_period=0)
    assert r2["parse_success"] is False


def test_emergency_braking_simulation_end_and_flag(tmp_path):
    from scripts.parsing.stderr import parse_emergency_braking

    text = (
        "Warning: Vehicle 'veh1' performs emergency braking on lane 'e0_0' "
        "with decel=9.00, wished=4.50, severity=1.00, time=3599.00.\n"
        "Warning: Vehicle 'veh2' performs emergency braking on lane 'e0_0' "
        "with decel=9.00, wished=4.50, severity=1.00, time=3600.00.\n"
    )
    r = parse_emergency_braking(text, warmup_period=0, simulation_end=3600)
    assert r["emergency_braking_count"] == 1  # 仅 3599（3600 排除）
    assert r["parse_success"] is True
    assert r["invalid_record_count"] == 0
    # stderr 缺失 → parse_success=False
    r_none = parse_emergency_braking(None, warmup_period=0)
    assert r_none["parse_success"] is False
    assert r_none["emergency_braking_count"] != r_none["emergency_braking_count"]  # NaN


def test_vehroute_lap_end_at_simulation_end_excluded(tmp_path):
    """lap_end == simulation_end 的圈排除（[warmup, end) 半开）。"""
    from scripts.parsing.vehroute import parse_lap_times

    p = tmp_path / "vehroute.xml"
    p.write_text(
        '<routes><vehicle id="v0" depart="0.00">'
        '<route edges="e0 e1 e2 e3 e0 e1 e2 e3" exitTimes="100 200 300 400 3600 3600 3600 3600"/>'
        "</vehicle></routes>",
        encoding="utf-8",
    )
    r = parse_lap_times(str(p), 4, warmup_period=0, sim_end_time=3600)
    assert r["completed_lap_count"] == 0  # 第 2 圈终点恰为 3600 → 排除


# ── 审查 P2（复核）：detector 单文件分支 + EB 质量标志贯穿 ──


def test_detector_multi_single_file_passes_simulation_end(tmp_path):
    """单文件分支同样应用 simulation_end：仅窗外 interval → fail-closed（P1-3 语义）。"""
    from scripts.parsing.detector import parse_detector_multi

    p = tmp_path / "det.xml"
    p.write_text(
        '<detector><interval begin="3600" end="3700" id="i1" flow="100.0" speed="10.0"/>'
        "</detector>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no interval in window"):
        parse_detector_multi([str(p)], warmup_period=0, simulation_end=3600)


def test_writer_eb_parse_success_gate():
    """writer v0.4.2：eb_parse_success=False → data_quality 非 ok。"""
    from scripts.results.writer import _build_row_v4_1

    summary = {
        "run_id": "r",
        "scenario": "scenario_0",
        "model": "IDM",
        "det_xml": "x",
        "vehN": 10,
        "ssm_parse_success": True,
        "lc_parse_success": True,
        "ep_parse_success": True,
        "ee_parse_success": True,
        "vr_parse_success": True,
        "fcd_parse_success": True,
        "eb_parse_success": False,  # stderr 缺失
    }
    row = _build_row_v4_1(summary, "SUCCESS", pipeline_version="v0.4.2")
    assert row["data_quality"] != "ok"


def test_summary_contract_eb_parse_success_bool_check():
    """schema v0.4.2：eb_parse_success 存在但非 bool → 契约错误。"""
    from scripts.schema import validate_summary_contract

    summary = _valid_v4_2_summary()
    summary["eb_parse_success"] = "yes"  # 非 bool
    errors = validate_summary_contract(summary, "2", pipeline_version=PIPELINE)
    assert any("eb_parse_success" in e for e in errors)


# ── 审查 P1-1/P1-2/P2-1（本轮）：空 detector/FCD + SSM 负值域 ──


def test_detector_empty_xml_marks_parse_failure(tmp_path):
    """空/无观测窗口 detector XML → parse_success=False（不得制造零流量结果）。"""
    from scripts.parsing.detector import parse_detector_subgroup

    p = tmp_path / "det.xml"
    p.write_text("<detector/>", encoding="utf-8")
    r = parse_detector_subgroup([str(p)], [str(p)], [str(p)], warmup_period=0)
    assert r["all"]["parse_success"] is False


def test_detector_zero_flow_with_windows_still_ok(tmp_path):
    """有观测窗口但 flow=0（合法空车窗口）→ parse_success=True。"""
    from scripts.parsing.detector import parse_detector_subgroup

    p = tmp_path / "det.xml"
    p.write_text(
        '<detector><interval begin="0.00" end="60.00" id="det0" flow="0.0" speed="-1.0"/>'
        "</detector>",
        encoding="utf-8",
    )
    r = parse_detector_subgroup([str(p)], [str(p)], [str(p)], warmup_period=0)
    assert r["all"]["parse_success"] is True


def test_fcd_empty_file_fails_closed(tmp_path):
    """合法但不含窗内 timestep 的 FCD → parse_success=False（与"无有效样本"区分）。"""
    import gzip

    from scripts.parsing.fcd import parse_fcd

    xml = '<?xml version="1.0" encoding="UTF-8"?><fcd-export></fcd-export>'
    p = tmp_path / "fcd.xml.gz"
    with gzip.open(p, "wb") as f:
        f.write(xml.encode("utf-8"))
    r = parse_fcd(str(p), {"v1": "CAV"}, warmup_period=0)
    assert r["all"]["parse_success"] is False


def test_ssm_negative_ttc_fails_closed(tmp_path):
    """负 TTC → invalid（物理域校验）。"""
    from scripts.parsing.ssm import parse_ssm

    p = tmp_path / "ssm.xml"
    p.write_text(
        '<SSMLog><conflict begin="100" end="200" ego="v1" foe="v2">'
        '<minTTC time="150" type="3" value="-1.0"/></conflict></SSMLog>',
        encoding="utf-8",
    )
    r = parse_ssm(str(p), warmup_period=0)
    assert r["parse_success"] is False
    assert r["ssm_invalid_record_count"] == 1


def test_ssm_negative_drac_fails_closed(tmp_path):
    """负 DRAC → invalid（物理域校验）。"""
    from scripts.parsing.ssm import parse_ssm_subgroup

    p = tmp_path / "ssm.xml"
    p.write_text(
        '<SSMLog><conflict begin="100" end="200" ego="v1" foe="v2">'
        '<maxDRAC time="150" type="3" value="-2.0"/></conflict></SSMLog>',
        encoding="utf-8",
    )
    r = parse_ssm_subgroup(str(p), {"v1": "CAV", "v2": "HV"}, warmup_period=0)
    assert r["all"]["parse_success"] is False


def test_detector_only_outside_window_intervals_fails_closed(tmp_path):
    """审阅 P1-3：仅窗外 interval（begin < warmup）→ parse_success=False。"""
    from scripts.parsing.detector import parse_detector_subgroup

    p = tmp_path / "det.xml"
    p.write_text(
        '<detector><interval begin="0" end="60" flow="0" speed="-1"/></detector>',
        encoding="utf-8",
    )
    r = parse_detector_subgroup([str(p)], [str(p)], [str(p)], warmup_period=600)
    assert r["all"]["parse_success"] is False


def test_detector_multi_partial_lane_missing_window_fails_closed(tmp_path):
    """审阅 P1-4：多车道中仅部分车道缺少窗内 interval → fail-closed。"""
    from scripts.parsing.detector import parse_detector_multi

    lane0 = tmp_path / "det0.xml"
    lane0.write_text(
        '<detector><interval begin="0" end="60" flow="0" speed="-1"/></detector>',  # 仅窗外
        encoding="utf-8",
    )
    lane1 = tmp_path / "det1.xml"
    lane1.write_text(
        '<detector><interval begin="600" end="660" flow="120.0" speed="10.0"/>'
        "</detector>",  # 窗内正常
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="lane file"):
        parse_detector_multi([str(lane0), str(lane1)], warmup_period=600, simulation_end=3600)


def test_detector_multi_lane_interval_sets_must_match(tmp_path):
    """审阅 P1-5：各车道窗内 (begin, end) 集合不一致 → fail-closed。"""
    from scripts.parsing.detector import parse_detector_multi

    lane0 = tmp_path / "det0.xml"
    lane0.write_text(
        "<detector>"
        '<interval begin="600" end="660" flow="100.0" speed="10.0"/>'
        '<interval begin="660" end="720" flow="200.0" speed="10.0"/>'
        "</detector>",
        encoding="utf-8",
    )
    lane1 = tmp_path / "det1.xml"
    lane1.write_text(
        '<detector><interval begin="600" end="660" flow="100.0" speed="10.0"/>'
        "</detector>",  # 缺 660 窗口
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="inconsistent"):
        parse_detector_multi([str(lane0), str(lane1)], warmup_period=600, simulation_end=3600)


def test_detector_multi_duplicate_window_in_lane_fails_closed(tmp_path):
    """审阅 P1-6：同一车道重复 (begin, end) interval → fail-closed（不得静默累加）。"""
    from scripts.parsing.detector import parse_detector_multi

    lane0 = tmp_path / "det0.xml"
    lane0.write_text(
        "<detector>"
        '<interval begin="600" end="660" flow="100.0" speed="10.0"/>'
        '<interval begin="600" end="660" flow="100.0" speed="10.0"/>'  # 重复窗口
        "</detector>",
        encoding="utf-8",
    )
    lane1 = tmp_path / "det1.xml"
    lane1.write_text(
        '<detector><interval begin="600" end="660" flow="100.0" speed="10.0"/></detector>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate interval"):
        parse_detector_multi([str(lane0), str(lane1)], warmup_period=600, simulation_end=3600)


def test_detector_multi_same_begin_diff_end_fails_closed(tmp_path):
    """审阅 P1-7：同一车道相同 begin、不同 end → fail-closed（不得累加流量）。"""
    from scripts.parsing.detector import parse_detector_multi

    lane0 = tmp_path / "det0.xml"
    lane0.write_text(
        "<detector>"
        '<interval begin="600" end="660" flow="100.0" speed="10.0"/>'
        '<interval begin="600" end="720" flow="100.0" speed="10.0"/>'  # 同 begin 不同 end
        "</detector>",
        encoding="utf-8",
    )
    lane1 = tmp_path / "det1.xml"
    lane1.write_text(
        "<detector>"
        '<interval begin="600" end="660" flow="100.0" speed="10.0"/>'
        '<interval begin="600" end="720" flow="100.0" speed="10.0"/>'
        "</detector>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate interval for begin"):
        parse_detector_multi([str(lane0), str(lane1)], warmup_period=600, simulation_end=3600)


def test_detector_single_lane_duplicate_begin_fails_closed(tmp_path):
    """审阅 P1-8：单车道 parse_detector 同样拒绝重复 begin（与多车道规则一致）。"""
    from scripts.parsing.detector import parse_detector_multi

    p = tmp_path / "det.xml"
    p.write_text(
        "<detector>"
        '<interval begin="600" end="660" flow="100.0" speed="10.0"/>'
        '<interval begin="600" end="720" flow="200.0" speed="10.0"/>'  # 同 begin 不同 end
        "</detector>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate interval for begin"):
        parse_detector_multi([str(p)], warmup_period=600, simulation_end=3600)


def test_detector_invalid_end_fails_closed(tmp_path):
    """审阅 P2-2：end 缺失/非有限/end<begin → fail-closed（单车道与多车道统一）。"""
    from scripts.parsing.detector import parse_detector, parse_detector_multi

    # 单车道：缺失 end
    p1 = tmp_path / "det1.xml"
    p1.write_text(
        '<detector><interval begin="600" flow="100.0" speed="10.0"/></detector>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid end"):
        parse_detector(str(p1), warmup_period=600, simulation_end=3600)
    # 多车道：end < begin
    p2 = tmp_path / "det2.xml"
    p2.write_text(
        '<detector><interval begin="600" end="500" flow="100.0" speed="10.0"/></detector>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid end"):
        parse_detector_multi([str(p2)], warmup_period=600, simulation_end=3600)


# ── 本轮审查 P0-1：all-level 圈时统计变量遮蔽（delay 循环重绑定 vr）──


def _lap_primitives(cav_empty=False):
    """vehroute all/HV/CAV 圈时统计刻意不同，用于检测 all 列被 CAV 子群遮蔽。"""
    all_stats = {
        "completed_lap_count": 40,
        "mean_lap_time_s": 120.0,
        "median_lap_time_s": 119.0,
        "p95_lap_time_s": 135.0,
        "lap_time_std_s": 6.0,
        "parse_success": True,
        "lap_times_s": [118.0, 120.0, 122.0],
    }
    hv = {"completed_lap_count": 30, "mean_lap_time_s": 118.0, "lap_times_s": [110.0, 115.0]}
    if cav_empty:
        cav = {
            "completed_lap_count": 0,
            "mean_lap_time_s": float("nan"),
            "median_lap_time_s": float("nan"),
            "p95_lap_time_s": float("nan"),
            "lap_time_std_s": float("nan"),
            "parse_success": True,
            "lap_times_s": [],
        }
    else:
        cav = {
            "completed_lap_count": 10,
            "mean_lap_time_s": 130.0,
            "median_lap_time_s": 129.0,
            "p95_lap_time_s": 140.0,
            "lap_time_std_s": 8.0,
            "parse_success": True,
            "lap_times_s": [105.0],
        }
    return SubgroupPrimitives(
        detector={"all": {}},
        ssm={"all": {}},
        lanechange={"all": {}},
        edge_perf={
            "all": {"total_vehicle_km": 100.0, "non_internal_edge_vehicle_km": 100.0},
            "HV": {"total_vehicle_km": 60.0},
            "CAV": {"total_vehicle_km": 40.0},
        },
        edge_emis={
            "all": {
                "total_CO2_kg": 0.0,
                "total_NOx_g": 0.0,
                "total_PMx_g": 0.0,
                "total_fuel_kg": 0.0,
                "non_internal_CO2_kg": 0.0,
                "non_internal_NOx_g": 0.0,
                "non_internal_PMx_g": 0.0,
                "non_internal_fuel_kg": 0.0,
            }
        },
        vehroute={"all": all_stats, "HV": hv, "CAV": cav},
        emerg_brake={"all": {}},
        fcd=None,
    )


def _lap_spec():
    from scripts.run_spec import PIPELINE_V4_2, RunSpec

    return RunSpec(
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


def test_core_summary_lap_stats_use_all_level_vehroute():
    """P0-1：cav=0 等价场景（CAV 子群空）下五个圈时统计 + vr_parse_success
    必须来自 vehroute["all"]，不得被 delay 循环重绑定为 CAV 子群而整体缺失。"""
    from scripts.parsing.metrics import compute_core_summary

    prim = _lap_primitives(cav_empty=True)
    core = compute_core_summary(prim, _lap_spec(), {"HV": 100.0, "IDM": 100.0})
    assert core["completed_lap_count"] == 40
    assert core["mean_lap_time_s"] == 120.0
    assert core["median_lap_time_s"] == 119.0
    assert core["p95_lap_time_s"] == 135.0
    assert core["lap_time_std_s"] == 6.0
    assert core["vr_parse_success"] is True


def test_core_summary_lap_stats_not_cav_subgroup():
    """P0-1：混合组下 all-level 列必须等于 vehroute["all"] 且不等于 CAV 子群值。"""
    from scripts.parsing.metrics import compute_core_summary

    prim = _lap_primitives(cav_empty=False)
    core = compute_core_summary(prim, _lap_spec(), {"HV": 100.0, "IDM": 100.0})
    assert core["completed_lap_count"] == 40  # != CAV 10
    assert core["mean_lap_time_s"] == 120.0  # != CAV 130
    assert core["median_lap_time_s"] == 119.0  # != CAV 129
    assert core["p95_lap_time_s"] == 135.0  # != CAV 140
    assert core["lap_time_std_s"] == 6.0  # != CAV 8


def test_core_summary_delay_pooled_unchanged():
    """P0-1 防御：mean/p95_lap_delay_s 仍为逐 lap pooled 计算（遮蔽发生在 delay 之后）。"""
    from scripts.parsing.metrics import compute_core_summary

    prim = _lap_primitives(cav_empty=False)
    core = compute_core_summary(prim, _lap_spec(), {"HV": 100.0, "IDM": 100.0})
    # HV laps [110,115]-100 → [10,15]；CAV laps [105]-100 → [5]；pooled [5,10,15]
    assert core["mean_lap_delay_s"] == 10.0
    assert core["p95_lap_delay_s"] == 15.0


# ── 本轮审查 P1-1：FCD speed 解析失败/非有限 → low_speed_excluded 台账 ──


def test_fcd_bad_speed_goes_to_low_speed_excluded(tmp_path):
    """P1-1：speed 解析失败/非有限 → low_speed_excluded（设计 §6.3 步骤 2），
    进台账而非 invalid——不得整 run parse_success=False。"""
    from scripts.parsing.fcd import parse_fcd

    p = tmp_path / "fcd.xml"
    p.write_text(
        "<fcd-export>"
        '<timestep time="700">'
        '<vehicle id="v0" type="HV" speed="x" lane="0" pos="0" leaderID="v1" leaderGap="5.0"/>'
        '<vehicle id="v1" type="HV" speed="10.0" lane="0" pos="5" leaderID="v0" leaderGap="5.0"/>'
        "</timestep>"
        '<timestep time="701">'
        '<vehicle id="v2" type="CAV" speed="nan" lane="0" pos="0" leaderID="v3" leaderGap="5.0"/>'
        '<vehicle id="v3" type="CAV" speed="10.0" lane="0" pos="5" leaderID="v2" leaderGap="5.0"/>'
        "</timestep>"
        "</fcd-export>",
        encoding="utf-8",
    )
    type_map = {"v0": "HV", "v1": "HV", "v2": "CAV", "v3": "CAV"}
    r = parse_fcd(str(p), type_map, warmup_period=600, simulation_end=3600)
    assert r["all"]["parse_success"] is True
    assert r["all"]["low_speed_excluded_count"] == 2
    assert r["HV"]["low_speed_excluded_count"] == 1
    assert r["CAV"]["low_speed_excluded_count"] == 1
    assert r["all"]["valid_thw_sample_count"] == 2


# ── 本轮审查 P1-2：writer all 圈数>0 回归保护 ──


def test_writer_flags_missing_all_lap_stats_v4_2():
    """P1-2：v0.4.2 + vehroute 解析成功但 all completed_lap_count<=0 →
    invariant_failed（旧 P0-1 遮蔽恰好 0+NaN 静默通过 SUMMARY_NAN_RULES 的回归保护）。"""
    from scripts.results.writer import _build_row_v4_1

    base = {
        "ssm_parse_success": True,
        "lc_parse_success": True,
        "ep_parse_success": True,
        "ee_parse_success": True,
        "vr_parse_success": True,
        "fcd_parse_success": True,
        "eb_parse_success": True,
    }
    missing = dict(base, completed_lap_count=0, mean_lap_time_s=float("nan"))
    row = _build_row_v4_1(missing, "SUCCESS", "v0.4.2")
    assert row["data_quality"] == "invariant_failed"

    healthy = dict(base, completed_lap_count=40, mean_lap_time_s=120.0)
    row_ok = _build_row_v4_1(healthy, "SUCCESS", "v0.4.2")
    assert row_ok["data_quality"] == "ok"


# ── 本轮审查 P2：SUMO 命令 extratime 显式化 ──


def test_v4_1_command_always_explicit_extratime():
    """P2：--device.ssm.extratime 无条件显式传参（含默认 5.0），不依赖 SUMO 隐式默认。"""
    from scripts.run_spec import PIPELINE_V4_1, RunSpec
    from scripts.simulation.single_run import build_sumo_command_v4_1
    from tests.test_v4_2_p0_1_ssm_role import _dummy_prepared

    spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="s0_IDM_v010_c005_as01_ss101",
        pipeline_version=PIPELINE_V4_1,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
    )
    cmd = build_sumo_command_v4_1(_dummy_prepared(), "net/scenario_0/loop.net.xml", spec)
    idx = cmd.index("--device.ssm.extratime")
    assert cmd[idx + 1] == str(spec.ssm_extratime_s)


# ── 本轮审查 P2：legacy 自由流参考优先 artifact HV ──


def test_load_free_flow_hv_ref_artifact_priority(tmp_path, monkeypatch):
    """P2：legacy 自由流参考优先 artifact 的 HV 值（与阶段二 runner 口径一致），
    artifact 缺失/损坏时回退历史常量 FREE_FLOW_LAP_TIME_S。"""
    from scripts.config import FREE_FLOW_LAP_TIME_S
    from scripts.simulation import single_run
    from scripts.simulation.single_run import _load_free_flow_hv_ref

    artifact = tmp_path / "ff.json"
    artifact.write_text(
        json.dumps(
            {
                "results": {
                    "scenario_0": {
                        "references": {"HV": {"lap_time_s": 111.8}, "CAV_IDM": {"lap_time_s": 98.8}}
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    assert (
        _load_free_flow_hv_ref({"free_flow_reference_path": str(artifact)}, "scenario_0") == 111.8
    )
    # net_meta 无 free_flow_reference_path → 回退默认 artifact 路径（仓库真实
    # artifact HV≈111.8，不再使用陈旧常量 98.8——即修复目标）
    assert _load_free_flow_hv_ref({}, "scenario_0") == pytest.approx(111.8)
    # artifact 完全缺失 → 回退历史常量
    monkeypatch.setattr(single_run, "_DEFAULT_FREE_FLOW_ARTIFACT", str(tmp_path / "missing.json"))
    assert _load_free_flow_hv_ref({}, "scenario_0") == FREE_FLOW_LAP_TIME_S["scenario_0"]
    # 显式路径损坏 → 回退历史常量
    broken = tmp_path / "broken.json"
    broken.write_text("not json", encoding="utf-8")
    assert (
        _load_free_flow_hv_ref({"free_flow_reference_path": str(broken)}, "scenario_0")
        == FREE_FLOW_LAP_TIME_S["scenario_0"]
    )


# ── 本轮审查 P2：experiment_audit 支持 cav_count 模式 ──


def test_audit_cav_count_mode_nonzero():
    """P2：cav_count 模式审计输出有意义的 planned_run_count / by_vehicle_count
    （旧实现仅支持 requested_pcav，cav_count 模式输出全零误导）。"""
    from scripts.experiment_audit import audit_experiment_config

    cfg = ExperimentConfig.from_dict(
        {
            "config_version": "1",
            "pipeline_version": "v0.4.2",
            "schema_version": "2",
            "scenarios": ["scenario_0"],
            "models": ["IDM", "CACC"],
            "seed_scope": "vehicle_type_assignment",
            "simulation_end": 3600,
            "warmup": 600,
            "step_length": 0.1,
            "detector_frequency": 60,
            "edge_data_frequency": 300,
            "loops": 3,
            "network_files": {"scenario_0": "net/scenario_0/loop.net.xml"},
            "grid_mode": "cav_count",
            "treatments": [
                {"vehicle_count": 120, "cav_counts": [0, 60, 120]},
                {"vehicle_count": 80, "cav_counts": [40, 80]},
            ],
            "sumo_seeds": [101],
        }
    )
    audit = audit_experiment_config(cfg)
    # 展开：cav=0 → 1 模型 × 1 seed；cav=60 → 2 模型 × 3 默认 seed；
    # cav=120 → 2 模型 × 1 seed；cav=40 → 2×3；cav=80 → 2×1（scenario=1、sumo_seed=1）
    assert audit.planned_run_count == (1 + 6 + 2) + (6 + 2)
    assert audit.requested_realized_mismatch_runs == 0
    assert audit.by_vehicle_count[0].realized_composition_count == 3
    assert audit.by_vehicle_count[0].mismatched_level_count == 0
    assert audit.by_vehicle_count[0].duplicate_treatment_level_count == 0
    assert audit.endpoint_unique_assignment_treatments == 5  # cav=0(1 模型)+120(2)+80(2)
    assert audit.endpoint_assignment_redundant_runs == 0


# ── 本轮审查 P2：ssm all 版镜像合并契约（极值保留基线）──


def test_ssm_all_mirror_merge_keeps_extremes(tmp_path):
    """P2：parse_ssm（all 版）镜像合并保留更危急极值（min_ttc 来自正向、max_drac
    来自反向）；时间字段回填为内部契约，与 parse_ssm_subgroup 逐行对齐（代码审查确认）。"""
    from scripts.parsing.ssm import parse_ssm

    p = tmp_path / "ssm.xml"
    p.write_text(
        "<SSMLog>"
        '<conflict begin="100" end="200" ego="veh1" foe="veh2">'
        '<minTTC time="150" value="1.0"/>'
        '<maxDRAC time="150" value="4.0"/>'
        "</conflict>"
        '<conflict begin="110" end="210" ego="veh2" foe="veh1">'
        '<minTTC time="160" value="2.0"/>'
        '<maxDRAC time="160" value="8.0"/>'
        "</conflict>"
        "</SSMLog>",
        encoding="utf-8",
    )
    r = parse_ssm(str(p), warmup_period=0, ttc_threshold=3.0, drac_threshold=3.0)
    assert r["ssm_mirrored_record_count"] == 1
    assert r["min_ttc_s"] == 1.0
    assert r["max_drac_mps2"] == 8.0
    assert r["parse_success"] is True


def test_audit_cav_count_main_grid_planned_3888():
    """P2（reviewer 复核）：cav_count 模式 planned_run_count 必须乘场景数——
    main.json 实配（4 场景）输出 3,888（旧实现 972，缺场景乘数）。"""
    from scripts.experiment_audit import audit_experiment_config

    cfg = load_experiment_config("configs/v0.4.2/main.json")
    assert cfg.grid_mode == "cav_count"
    audit = audit_experiment_config(cfg)
    assert audit.planned_run_count == 3888
    # 与同函数端点口径一致（端点已乘场景数，planned 不得少乘）
    assert audit.endpoint_run_count == 432


# ── 本轮审查 P2-1：writer all 圈数>0 门禁贯通 subgroup 排除 ──


def test_all_lap_stats_missing_shared_judgement():
    """P2-1：all 圈数>0 判定函数——vehroute 解析成功但 completed_lap_count<=0
    → True（run-level 与 subgroup 排除共用同一判定，保证两输出一致）。"""
    from scripts.results.writer import _all_lap_stats_missing

    assert _all_lap_stats_missing({"vr_parse_success": True, "completed_lap_count": 0}, "v0.4.2")
    assert _all_lap_stats_missing(
        {"vr_parse_success": True, "completed_lap_count": 0, "mean_lap_time_s": float("nan")},
        "v0.4.2",
    )
    assert not _all_lap_stats_missing(
        {"vr_parse_success": True, "completed_lap_count": 40}, "v0.4.2"
    )
    # 非 v0.4.2 不触发；vr_parse_success 非 True 不触发
    assert not _all_lap_stats_missing(
        {"vr_parse_success": True, "completed_lap_count": 0}, "v0.4.1"
    )
    assert not _all_lap_stats_missing(
        {"vr_parse_success": False, "completed_lap_count": 0}, "v0.4.2"
    )


def test_writer_subgroup_excluded_when_lap_stats_missing(tmp_path, monkeypatch):
    """P2-1（集成）：P1-2 门禁触发的 run（all 圈数=0），其 subgroup 行同样被
    排除出 subgroup CSV——旧实现仅 run-level 置 invariant_failed，subgroup 仍进入。"""
    import hashlib

    from scripts.results.writer import build_run_level_results

    def _write_run(run_id, lap_count):
        run_dir = tmp_path / run_id
        run_dir.mkdir()
        summary = _valid_v4_2_summary()
        summary["run_id"] = run_id
        summary["completed_lap_count"] = lap_count
        summary["vr_parse_success"] = True
        if lap_count == 0:
            summary["mean_lap_time_s"] = float("nan")
        summary_bytes = json.dumps(summary).encode("utf-8")
        (run_dir / "summary.json").write_bytes(summary_bytes)
        sub_bytes = json.dumps({"run_id": run_id}).encode("utf-8")
        (run_dir / "subgroup_summary.jsonl").write_bytes(sub_bytes)
        (run_dir / "run_spec.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
        status_common = {
            "pipeline_version": "v0.4.2",
            "schema_version": "2",
            "config_sha256": "a" * 64,
            "run_spec_sha256": "b" * 64,
        }
        (run_dir / "simulation_status.json").write_text(
            json.dumps({**status_common, "run_id": run_id, "status": "SUCCESS"}),
            encoding="utf-8",
        )
        (run_dir / "parse_status.json").write_text(
            json.dumps(
                {
                    **status_common,
                    "run_id": run_id,
                    "status": "SUCCESS",
                    "summary_sha256": hashlib.sha256(summary_bytes).hexdigest(),
                    "subgroup_summary_sha256": hashlib.sha256(sub_bytes).hexdigest(),
                }
            ),
            encoding="utf-8",
        )

    _write_run("buggy-run", 0)
    _write_run("healthy-run", 40)
    manifest = {
        "pipeline_version": "v0.4.2",
        "schema_version": "2",
        "config_sha256": "a" * 64,
        "total": 2,
        "results": [
            {"run_id": "buggy-run", "run_spec_sha256": "b" * 64},
            {"run_id": "healthy-run", "run_spec_sha256": "b" * 64},
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr("scripts.results.writer._valid_subgroup_rows", lambda *a, **k: True)
    report = build_run_level_results(tmp_path, tmp_path / "out", "v0.4.2", manifest_path)
    # 仅 buggy-run 的 subgroup 被排除（旧实现 subgroup_excluded=0）
    assert report["subgroup_excluded_runs"] == 1
    assert report["subgroup_csv_rows"] == 1
    # run-level：buggy 置 invariant_failed、healthy ok
    import csv

    with (tmp_path / "out" / "run_level_results.csv").open(newline="", encoding="utf-8") as f:
        q = {row["run_id"]: row["data_quality"] for row in csv.DictReader(f)}
    assert q["buggy-run"] == "invariant_failed"
    assert q["healthy-run"] == "ok"


# ── 本轮审查 P2-2：v0.4.2 run_spec 专属键缺失 fail-closed ──


def test_run_spec_v4_2_missing_role_keys_fails_closed():
    """P2-2：v0.4.2 run_spec.json 缺 experiment_role/ssm_enabled/analysis_* →
    ValueError（不得静默默认 main_factorial 处理损坏的 run_spec）。"""
    from scripts.run_spec import PIPELINE_V4_2, RunSpec

    spec = RunSpec(
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
        experiment_role="safety",
        ssm_enabled=True,
    )
    d = spec.to_dict()
    for missing_key in ("experiment_role", "ssm_enabled", "analysis_ttc_threshold_s"):
        broken = dict(d)
        del broken[missing_key]
        with pytest.raises(ValueError, match="missing fields"):
            RunSpec.from_dict(broken)
    # 完整 dict 仍可反序列化
    assert RunSpec.from_dict(d) == spec


# ── 本轮审查 P2-3：FCD 台账闭合显式断言 ──


def _fcd_closure_primitives(broken=False):
    fcd = {
        "all": {
            "valid_thw_sample_count": 10,
            "low_speed_excluded_count": 2,
            "no_leader_count": 3,
            "self_leader_count": 1,
            "parse_success": True,
        },
        "HV": {
            "valid_thw_sample_count": 6,
            "low_speed_excluded_count": 1,
            "no_leader_count": 2,
            "self_leader_count": 1,
            "parse_success": True,
        },
        "CAV": {
            "valid_thw_sample_count": 4,
            "low_speed_excluded_count": 1,
            "no_leader_count": 1,
            "self_leader_count": 0,
            "parse_success": True,
        },
    }
    if broken:
        fcd["all"]["no_leader_count"] = 99
    return SubgroupPrimitives(
        detector={"all": {}, "HV": {"parse_success": True}, "CAV": {"parse_success": True}},
        ssm={"all": {}},
        lanechange={
            "all": {},
            "HV": {"parse_success": True},
            "CAV": {"parse_success": True},
        },
        edge_perf={
            "all": {},
            "HV": {"parse_success": True},
            "CAV": {"parse_success": True},
        },
        edge_emis={
            "all": {},
            "HV": {"parse_success": True},
            "CAV": {"parse_success": True},
        },
        vehroute={
            "all": {"parse_success": True},
            "HV": {"parse_success": True},
            "CAV": {"parse_success": True},
        },
        emerg_brake={"all": {}},
        fcd=fcd,
    )


def test_subgroup_invariants_fcd_closure():
    """P2-3：FCD 台账闭合（all == HV+CAV，样本数 + 排除计数）显式断言——
    破坏闭合时 validate_subgroup_invariants 必须报错。"""
    from scripts.parsing.metrics import validate_subgroup_invariants

    assert validate_subgroup_invariants(_fcd_closure_primitives()) == []
    errors = validate_subgroup_invariants(_fcd_closure_primitives(broken=True))
    assert any("fcd.no_leader_count" in e for e in errors)
