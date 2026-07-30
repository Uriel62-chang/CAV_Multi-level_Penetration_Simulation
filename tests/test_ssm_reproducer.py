import json
from pathlib import Path

import pytest

from scripts.analysis.ssm_reproducer import load_case, summarize_ssm_evidence


def test_frozen_s2_and_s3_cases_only_differ_by_scenario():
    s2 = load_case("configs/v0.4.1/ssm_reproducer_s2.json")
    s3 = load_case("configs/v0.4.1/ssm_reproducer_s3.json")

    assert s2["expected_ttc"] == "zero"
    assert s3["expected_ttc"] == "positive"
    assert {
        key: value
        for key, value in s2.items()
        if key not in {"case_id", "scenario", "network_file", "expected_ttc"}
    } == {
        key: value
        for key, value in s3.items()
        if key not in {"case_id", "scenario", "network_file", "expected_ttc"}
    }


def test_load_case_rejects_noncanonical_full_cav_seed(tmp_path):
    case = json.loads(Path("configs/v0.4.1/ssm_reproducer_s2.json").read_text(encoding="utf-8"))
    case["assignment_seed"] = 1
    path = tmp_path / "case.json"
    path.write_text(json.dumps(case), encoding="utf-8")

    with pytest.raises(ValueError, match="assignment_seed=0"):
        load_case(path)


def test_summarize_ssm_evidence_marks_failed_positive_control(tmp_path):
    xml = tmp_path / "ssm.xml"
    xml.write_text("<ssmLog/>", encoding="utf-8")

    evidence = summarize_ssm_evidence(xml, warmup=600, expected_ttc="positive")

    assert evidence["ttc_event_count"] == 0
    assert evidence["control_status"] == "positive-control failed"
