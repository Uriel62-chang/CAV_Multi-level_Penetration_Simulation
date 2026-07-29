"""v0.4.1 stage2 FCD parser tests"""

import json
import tempfile
from pathlib import Path

from scripts.parsing.fcd import parse_fcd

_BASE = Path("/tmp/v4_1_probes/s0_IDM_v010_c005_as01_ss101")
_TYPE_MAP = json.loads((_BASE / "vehicle_type_map.json").read_text())


def test_fcd_valid_parse():
    result = parse_fcd(str(_BASE / "fcd.xml.gz"), _TYPE_MAP, warmup_period=60)
    assert result["all"]["parse_success"] is True
    assert result["HV"]["parse_success"] is True
    assert result["CAV"]["parse_success"] is True
    assert result["all"]["valid_thw_sample_count"] > 0


def test_fcd_thw_reasonable():
    result = parse_fcd(str(_BASE / "fcd.xml.gz"), _TYPE_MAP, warmup_period=60)
    thw = result["all"]["mean_thw_s"]
    assert 0 < thw < 100


def test_fcd_additivity():
    result = parse_fcd(str(_BASE / "fcd.xml.gz"), _TYPE_MAP, warmup_period=60)
    assert (
        result["all"]["valid_thw_sample_count"]
        == result["HV"]["valid_thw_sample_count"] + result["CAV"]["valid_thw_sample_count"]
    )


def test_fcd_exclusion_additivity():
    result = parse_fcd(str(_BASE / "fcd.xml.gz"), _TYPE_MAP, warmup_period=60)
    for key in ("low_speed_excluded_count", "no_leader_count", "self_leader_count"):
        assert result["all"][key] == result["HV"][key] + result["CAV"][key], (
            f"{key}: all={result['all'][key]}, HV+CAV={result['HV'][key] + result['CAV'][key]}"
        )


def test_fcd_empty_gzip():
    with tempfile.NamedTemporaryFile(suffix=".xml.gz", delete=False) as f:
        f.write(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00")
        empty_gz = f.name
    result = parse_fcd(empty_gz, _TYPE_MAP)
    assert result["all"]["parse_success"] is False


def test_fcd_id_not_in_map(tmp_path):
    result = parse_fcd(str(_BASE / "fcd.xml.gz"), {}, warmup_period=60)
    assert result["all"]["parse_success"] is False


def test_fcd_type_mismatch(tmp_path):
    bad_map = {k: ("HV" if v == "CAV" else "CAV") for k, v in _TYPE_MAP.items()}
    result = parse_fcd(str(_BASE / "fcd.xml.gz"), bad_map, warmup_period=60)
    assert result["all"]["parse_success"] is False


def test_fcd_self_leader():
    result = parse_fcd(str(_BASE / "fcd.xml.gz"), _TYPE_MAP, warmup_period=60)
    assert result["all"]["self_leader_count"] >= 0


def test_fcd_keys():
    result = parse_fcd(str(_BASE / "fcd.xml.gz"), _TYPE_MAP, warmup_period=60)
    expected = (
        "mean_thw_s",
        "median_thw_s",
        "p05_thw_s",
        "thw_lt_1s_ratio",
        "valid_thw_sample_count",
        "low_speed_excluded_count",
        "no_leader_count",
        "self_leader_count",
        "parse_success",
    )
    for label in ("all", "HV", "CAV"):
        for key in expected:
            assert key in result[label], f"{label} missing {key}"
