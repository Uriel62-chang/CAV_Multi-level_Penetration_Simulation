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


def _net_meta_with_anchor(sources_sha256):
    return json.dumps({"scenario": "scenario_0", "network_sources_sha256": sources_sha256})


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
    (d / "net.json").write_text(_net_meta_with_anchor(digest.hexdigest()), encoding="utf-8")
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
    (d / "net.json").write_text(
        _net_meta_with_anchor("0" * 64),
        encoding="utf-8",  # 锚定值与实际源不符
    )
    monkeypatch.setattr(ng.subprocess, "run", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="不一致"):
        ng.build_network(str(d), netconvert_command="netconvert")


def test_build_network_unanchored_fails(tmp_path, monkeypatch):
    """审阅 P1-1：未锚定 network_sources_sha256 → 强制失败（不得警告后继续编译）。"""
    import scripts.simulation.network_generator as ng

    d = tmp_path / "scenario_0"
    d.mkdir()
    (d / "nodes.nod.xml").write_text("<nodes/>", encoding="utf-8")
    (d / "edges.edg.xml").write_text("<edges/>", encoding="utf-8")
    (d / "net.json").write_text('{"scenario": "scenario_0"}', encoding="utf-8")
    monkeypatch.setattr(ng.subprocess, "run", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="未锚定"):
        ng.build_network(str(d), netconvert_command="netconvert")


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
    from tests.test_v4_2_review_round4 import _make_stub, _write_full_status, _full_raw_hashes, _SpecStub  # noqa: E501
    from scripts.parsing.input_integrity import verify

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
