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
