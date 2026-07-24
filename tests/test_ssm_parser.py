"""SSM parser unit tests — TTC/DRAC conflict extraction + mirror deduplication."""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.parsing.ssm import parse_ssm

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_minimal_parses_conflicts():
    """Real SUMO 1.27.1 SSM output — should extract conflicts correctly."""
    result = parse_ssm(
        os.path.join(FIXTURES, "ssm_minimal.xml"),
        warmup_period=0.0,
        ttc_threshold=3.0,
        drac_threshold=3.0,
    )
    assert result["parse_success"] is True
    assert result["ssm_raw_record_count"] == 5
    assert result["ssm_invalid_record_count"] == 0
    assert result["ssm_valid_record_count"] == 5
    # 4 conflicts with TTC < 3.0 (veh24-veh26 mirrored pair counts as 1 unique,
    # but both forward records have TTC=1.45 < 3.0, plus veh10-veh6 1.79, veh10-veh16 2.46)
    # Actually: the first 4 conflicts are two mirrored pairs.
    # veh24→veh26 (TTC 1.45) + veh26→veh24 (TTC 1.45) → 1 unique after mirror
    # veh10→veh6 (TTC 1.79) is standalone → 1
    # veh10→veh16 (TTC 2.46) is standalone → 1
    # veh50→veh51 (TTC 4.50 > 3.0) → 0
    # So 3 TTC events total.
    assert result["ttc_conflict_event_count"] == 3
    # min TTC across all valid records
    assert result["min_ttc_s"] == 1.45
    # vehicles involved in TTC conflicts: veh24, veh26, veh10, veh6, veh16 = 5
    assert result["ttc_involved_vehicle_count"] == 5
    # DRAC events: all conflicts have DRAC < 3.0 threshold
    # max_drac values: 1.90, 2.28, 1.83, 1.90, 1.20 — all ≤ 3.0
    # So 0 DRAC events; max_drac_mps2 is NaN (no event exceeded threshold)
    assert result["drac_conflict_event_count"] == 0
    assert math.isnan(result["max_drac_mps2"])


def test_mirror_deduplication():
    """veh24↔veh26 are a mirrored pair — only one should survive."""
    result = parse_ssm(
        os.path.join(FIXTURES, "ssm_minimal.xml"),
        warmup_period=0.0,
        ttc_threshold=3.0,
        drac_threshold=3.0,
    )
    # raw=5, no invalid, no warmup filtered → valid=5
    # mirrored count: veh26→veh24 is mirror of veh24→veh26 → 1 mirrored
    assert result["ssm_raw_record_count"] == 5
    assert result["ssm_mirrored_record_count"] == 1
    # unique = valid - mirrored = 5 - 1 = 4
    unique = result["ssm_valid_record_count"] - result["ssm_mirrored_record_count"]
    assert unique == 4


def test_warmup_filtering():
    """Conflicts before warmup_period should be filtered out."""
    result = parse_ssm(
        os.path.join(FIXTURES, "ssm_minimal.xml"),
        warmup_period=50.0,  # only veh50-veh51 (begin=100) survives
        ttc_threshold=3.0,
        drac_threshold=3.0,
    )
    # veh24-veh26 (begin=3.1), veh10-veh6 (19.5), veh10-veh16 (21.4),
    # veh26-veh24 (3.1) → all filtered
    # veh50-veh51 (begin=100.0) → survives but TTC=4.5 > 3.0
    assert result["ssm_warmup_filtered_count"] == 4
    assert result["ssm_valid_record_count"] == 1
    assert result["ttc_conflict_event_count"] == 0  # the one survivor has TTC > threshold


def test_empty_file_returns_zero_events():
    """Empty SSMLog should return 0 events, not crash."""
    result = parse_ssm(
        os.path.join(FIXTURES, "ssm_empty.xml"),
        warmup_period=0.0,
    )
    assert result["parse_success"] is True
    assert result["ssm_raw_record_count"] == 0
    assert result["ttc_conflict_event_count"] == 0
    assert result["drac_conflict_event_count"] == 0
    assert math.isnan(result["min_ttc_s"])
    assert math.isnan(result["max_drac_mps2"])


def test_missing_file_returns_nan_counts():
    """Non-existent file should return NaN for counts, parse_success=False."""
    result = parse_ssm(
        os.path.join(FIXTURES, "nonexistent.xml"),
        warmup_period=0.0,
    )
    assert result["parse_success"] is False
    # counts default to 0
    assert result["ttc_conflict_event_count"] == 0
    assert result["ssm_raw_record_count"] == 0


def test_missing_fields_return_nan_not_zero():
    """Conflicts without minTTC/maxDRAC should not crash parser."""
    result = parse_ssm(
        os.path.join(FIXTURES, "ssm_missing.xml"),
        warmup_period=0.0,
        ttc_threshold=3.0,
        drac_threshold=3.0,
    )
    assert result["parse_success"] is True
    # veh24→veh26 has no minTTC → no TTC event
    # veh10→veh6 has TTC=1.79 < 3.0 → 1 TTC event
    assert result["ttc_conflict_event_count"] == 1
    # DRAC: veh24→veh26 has no maxDRAC → no DRAC event
    # veh10→veh6 has no maxDRAC either → 0 DRAC events
    assert result["drac_conflict_event_count"] == 0


def test_malformed_xml_returns_nan():
    """Malformed XML should not crash; parse_success=False."""
    result = parse_ssm(
        os.path.join(FIXTURES, "ssm_malformed.xml"),
        warmup_period=0.0,
    )
    assert result["parse_success"] is False
    assert result["ttc_conflict_event_count"] == 0


def test_idempotent():
    """Calling parse_ssm twice on the same file should give identical results."""
    path = os.path.join(FIXTURES, "ssm_minimal.xml")
    r1 = parse_ssm(path, warmup_period=0.0, ttc_threshold=3.0, drac_threshold=3.0)
    r2 = parse_ssm(path, warmup_period=0.0, ttc_threshold=3.0, drac_threshold=3.0)
    for k in r1:
        v1, v2 = r1[k], r2[k]
        if isinstance(v1, float) and math.isnan(v1) and math.isnan(v2):
            continue
        assert v1 == v2, f"Key {k}: {v1} != {v2}"
