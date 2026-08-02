"""v0.4.2 正式网格热修复回归测试（Reviewer 复检 P1 闭合项）。

覆盖：
- a21e05e 容差放宽：实测浮点噪声（~1e-4~1e-3）可通过；明显可加性断裂仍被拒绝
- 6637519 whole-network 强度 NaN 规则：空子群（veh-km=0）NaN 合法；
  非空子群 NaN 拒绝；真实端点 run 的 subgroup 数据通过校验
- 770/454 表述：以首轮解析终态 770 为准
"""

import json
from pathlib import Path

from scripts.parsing.metrics import SubgroupPrimitives, validate_subgroup_invariants
from scripts.results.writer import _valid_subgroup_rows

_FIXTURES = Path(__file__).parent / "fixtures"


# ── a21e05e：容差边界 ──


def _minimal_primitives(ep_all, ep_hv, ep_cav, ee_all, ee_hv, ee_cav):
    def _perf(total, ni, tloss):
        return {
            "parse_success": True,
            "total_vehicle_km": total,
            "non_internal_edge_vehicle_km": ni,
            "total_time_loss_s": tloss,
        }

    def _emis(co2):
        return {
            "parse_success": True,
            "total_CO2_kg": co2,
            "total_NOx_g": 0.0,
            "total_PMx_g": 0.0,
            "total_fuel_kg": 0.0,
        }

    def _lc():
        return {"parse_success": True, "lane_change_count": 0}

    def _vr():
        return {"parse_success": True, "completed_lap_count": 0}

    def _eb():
        return {"parse_success": True, "emergency_braking_count": 0}

    return SubgroupPrimitives(
        detector={
            "all": {"parse_success": True},
            "HV": {"parse_success": True},
            "CAV": {"parse_success": True},
        },
        ssm={"all": {"parse_success": True}},
        lanechange={"all": _lc(), "HV": _lc(), "CAV": _lc()},
        edge_perf={"all": _perf(*ep_all), "HV": _perf(*ep_hv), "CAV": _perf(*ep_cav)},
        edge_emis={"all": _emis(*ee_all), "HV": _emis(*ee_hv), "CAV": _emis(*ee_cav)},
        vehroute={"all": _vr(), "HV": _vr(), "CAV": _vr()},
        emerg_brake={"all": _eb(), "HV": _eb(), "CAV": _eb()},
        fcd=None,
    )


def test_additivity_tolerance_accepts_measured_noise():
    """a21e05e：实测量级浮点噪声（rel 1e-4~1e-3）必须通过。"""
    prim = _minimal_primitives(
        ep_all=(1000.0, 800.0, 500.0),
        ep_hv=(600.2, 480.1, 300.5),  # 总和与 all 偏差 rel ~4e-4（vehicle_km）
        ep_cav=(400.1, 320.0, 200.3),
        ee_all=(1.0,),
        ee_hv=(0.6,),
        ee_cav=(0.4,),
    )
    errors = validate_subgroup_invariants(prim)
    assert not any("HV+CAV=" in e for e in errors), errors


def test_additivity_tolerance_rejects_clear_break():
    """a21e05e：明显可加性断裂（~10% 偏差）仍必须被拒绝。"""
    prim = _minimal_primitives(
        ep_all=(1000.0, 800.0, 500.0),
        ep_hv=(600.0, 480.0, 300.0),
        ep_cav=(300.0, 240.0, 150.0),  # 总和 900 vs 1000 → 10% 断裂
        ee_all=(1.0,),
        ee_hv=(0.6,),
        ee_cav=(0.3,),  # 0.9 vs 1.0 → 10%
    )
    errors = validate_subgroup_invariants(prim)
    assert any("HV+CAV=" in e for e in errors), "明显断裂应被拒绝"


# ── 6637519：whole-network 强度 NaN 规则 ──


def _row(spec, family, group, metric, value):
    return {
        "run_id": spec["run_id"],
        "scenario": spec["scenario"],
        "model": spec["model"],
        "requested_pcav": None,
        "realized_pcav": spec["cav_count"] / spec["vehicle_count"],
        "cav_count": spec["cav_count"],
        "hv_count": spec["vehicle_count"] - spec["cav_count"],
        "vehN": spec["vehicle_count"],
        "assignment_seed": spec["seed"],
        "sumo_seed": spec["sumo_seed"],
        "metric_family": family,
        "group_dimension": "vehicle_type",
        "group_value": group,
        "metric_name": metric,
        "metric_value": value,
    }


def _spec_dict(**overrides):
    base = {
        "run_id": "s2_HVONLY_v070_c000_as00_ss103",
        "scenario": "scenario_2",
        "model": "IDM",
        "vehicle_count": 70,
        "cav_count": 0,
        "seed": 0,
        "sumo_seed": 103,
        "fcd_profile": "1s",
    }
    base.update(overrides)
    return base


def test_whole_network_nan_rejected_when_subgroup_nonempty():
    """6637519：非空子群（total_vehicle_km=100）中 whole-network NaN 必须拒绝。"""
    spec = _spec_dict(cav_count=35, seed=1)
    rows = [
        _row(spec, "efficiency", "CAV", "total_vehicle_km", 100.0),
        _row(spec, "emissions", "CAV", "whole_network_CO2_g_per_veh_km", float("nan")),
    ]
    assert _valid_subgroup_rows(rows, spec["run_id"], spec) is False


def test_endpoint_run_subgroup_passes_validation():
    """6637519 回归：真实端点 run（cav=0，空 CAV 子群）的 subgroup 数据必须通过校验。

    修复前 whole_network_* NaN 不在 SUBGROUP_NAN_RULES → 432 个端点 run 被排除。
    """
    rows = []
    with open(_FIXTURES / "endpoint_subgroup.jsonl") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    spec = json.loads((_FIXTURES / "endpoint_run_spec.json").read_text(encoding="utf-8"))
    assert len(rows) == 104
    assert _valid_subgroup_rows(rows, spec["run_id"], spec) is True


def test_whole_network_nan_rules_present():
    """6637519：四个 whole-network 强度指标已进入 SUBGROUP_NAN_RULES。"""
    from scripts.results import writer

    for metric in (
        "whole_network_CO2_g_per_veh_km",
        "whole_network_NOx_mg_per_veh_km",
        "whole_network_PMx_mg_per_veh_km",
        "whole_network_fuel_g_per_veh_km",
    ):
        assert metric in writer.SUBGROUP_NAN_RULES


def test_hotfix_commit_notes_use_final_770():
    """P2：容差误报最终口径 = 首轮解析终态 770（中途观察值 454 已标注非最终）。"""
    from scripts.parsing import metrics

    src = Path(metrics.__file__).read_text(encoding="utf-8")
    assert "770 个 INVALID_DATA" in src
