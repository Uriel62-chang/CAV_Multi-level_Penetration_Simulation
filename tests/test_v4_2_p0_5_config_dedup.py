"""v0.4.2 P0-5 回归测试：配置/算法单源闭合。

覆盖：
- _parse_bool：字符串 "false" 必须解析为 False（bool("false")==True 缺陷）
- v0.4.2 experiment_role × ssm_enabled 一致性校验
- capture/analysis 阈值包络校验
- sorted_greedy_80pct 在主 parser 真实实现（非退化为未排序 greedy）
"""

import json
import xml.etree.ElementTree as ET

import pytest

from scripts.experiment_config import ExperimentConfig, _parse_bool
from scripts.parsing.ssm import parse_ssm
from scripts.run_spec import PIPELINE_V4_2, RunSpec

# ── 配置校验 ──


def _cfg(**overrides) -> ExperimentConfig:
    with open("configs/v0.4.2/main.json") as f:
        data = json.load(f)
    data.update(overrides)
    return ExperimentConfig.from_dict(data)


def test_parse_bool_string_false_is_false():
    cfg = _cfg(ssm_enabled="false")
    assert cfg.ssm_enabled is False
    cfg.validate()  # main_factorial + ssm_enabled=false 合法


def test_parse_bool_string_true_is_true():
    cfg = _cfg(experiment_role="safety", ssm_enabled="true")
    assert cfg.ssm_enabled is True
    cfg.validate()  # safety + ssm_enabled=true 合法


def test_parse_bool_rejects_invalid_string():
    with pytest.raises(ValueError):
        _parse_bool({"x": "maybe"}, "x", False)


def test_main_factorial_rejects_ssm_enabled():
    with pytest.raises(ValueError, match="ssm_enabled=false"):
        _cfg(ssm_enabled=True).validate()


def test_safety_rejects_ssm_disabled():
    with pytest.raises(ValueError, match="ssm_enabled=true"):
        _cfg(experiment_role="safety", ssm_enabled=False).validate()


def test_threshold_envelope_ttc():
    with pytest.raises(ValueError, match="exceeds"):
        _cfg(analysis_ttc_threshold_s=5.0).validate()  # capture ceiling 3.0


def test_threshold_envelope_drac():
    with pytest.raises(ValueError, match="below"):
        _cfg(analysis_drac_threshold_mps2=2.0).validate()  # capture floor 3.0


def test_valid_configs_still_pass():
    _cfg().validate()  # main.json
    _cfg(experiment_role="safety", ssm_enabled=True).validate()


# ── sorted_greedy_80pct 真实实现 ──


def _write_ssm(path, conflicts):
    root = ET.Element("conflicts")
    for c in conflicts:
        el = ET.SubElement(
            root,
            "conflict",
            {"ego": c["ego"], "foe": c["foe"], "begin": str(c["begin"]), "end": str(c["end"])},
        )
        ET.SubElement(el, "minTTC", {"value": str(c["ttc"]), "time": str(c["time"])})
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def test_sorted_greedy_not_degenerate(tmp_path):
    """P0-5：sorted_greedy 与 greedy 必须产生不同结果（排序改变匹配选择）。

    保留记录吸收不同 reverse：greedy 吸收 R1(ttc=1.0) → F 保持 0.6 且 R2(0.5) 残留；
    sorted 吸收 R2(ttc=0.5) → F 降至 0.5 且 R1(1.0) 残留。threshold=0.8 时事件数不同。
    """
    path = tmp_path / "ssm.xml"
    _write_ssm(
        path,
        [
            {"ego": "A", "foe": "B", "begin": 0, "end": 100, "ttc": 0.6, "time": 10},
            {"ego": "B", "foe": "A", "begin": 0, "end": 100, "ttc": 1.0, "time": 10},
            {"ego": "B", "foe": "A", "begin": 0, "end": 60, "ttc": 0.5, "time": 5},
        ],
    )
    g = parse_ssm(
        str(path),
        warmup_period=0,
        ttc_threshold=0.8,
        dedup_method="greedy_one_to_one_80pct",
    )
    s = parse_ssm(
        str(path),
        warmup_period=0,
        ttc_threshold=0.8,
        dedup_method="sorted_greedy_80pct",
    )
    assert g["ttc_conflict_event_count"] == 2  # F(0.6) + 残留 R2(0.5)
    assert s["ttc_conflict_event_count"] == 1  # F(0.5) + 残留 R1(1.0)
    assert g["ssm_mirrored_record_count"] == s["ssm_mirrored_record_count"] == 1


def test_sorted_greedy_matches_sensitivity_impl(tmp_path):
    """P0-5：主 parser 的 sorted_greedy 与 ssm_sensitivity._dedup_sorted_greedy 一致。"""
    from scripts.analysis.ssm_sensitivity import _dedup_sorted_greedy

    path = tmp_path / "ssm.xml"
    _write_ssm(
        path,
        [
            {"ego": "A", "foe": "B", "begin": 0, "end": 100, "ttc": 1.5, "time": 10},
            {"ego": "B", "foe": "A", "begin": 0, "end": 100, "ttc": 1.0, "time": 10},
            {"ego": "B", "foe": "A", "begin": 0, "end": 60, "ttc": 0.5, "time": 5},
        ],
    )
    s = parse_ssm(
        str(path),
        warmup_period=0,
        ttc_threshold=1.0,
        dedup_method="sorted_greedy_80pct",
    )
    sens = _dedup_sorted_greedy(str(path), 0, 1.0, 3.0)
    assert sens[0] == s["ttc_conflict_event_count"]  # ttc events
    assert sens[1] == s["drac_conflict_event_count"]  # drac events


def test_greedy_matches_baseline_behavior(tmp_path):
    """greedy_one_to_one_80pct 主路径行为不因 P0-5 改动而改变（回归）。"""
    path = tmp_path / "ssm.xml"
    _write_ssm(
        path,
        [
            {"ego": "A", "foe": "B", "begin": 0, "end": 100, "ttc": 1.5, "time": 10},
            {"ego": "B", "foe": "A", "begin": 0, "end": 100, "ttc": 1.0, "time": 10},
        ],
    )
    g = parse_ssm(str(path), warmup_period=0, ttc_threshold=1.0)
    assert g["ttc_conflict_event_count"] == 0  # F 吸收 1.0 后不 < 1.0
    assert g["ssm_mirrored_record_count"] == 1


def _spec() -> RunSpec:
    return RunSpec(
        scenario="scenario_2",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="s2_IDM_v010_c005_as01_ss101",
        pipeline_version=PIPELINE_V4_2,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
    )
