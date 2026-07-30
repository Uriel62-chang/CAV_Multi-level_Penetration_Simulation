"""Regression probes for parser/writer summary and closure gates."""

import json
import math

from scripts.schema import SUMMARY_REQUIRED_KEYS, validate_summary_contract


def _legacy_summary():
    summary = {key: 0.0 for key in SUMMARY_REQUIRED_KEYS}
    summary.update(
        {
            "run_id": "run-1",
            "scenario": "scenario_0",
            "model": "IDM",
            "det_xml": "detector.xml",
            "pCAV": 0.5,
            "vehN": 10,
            "seed": 1,
            "step_length_s": 0.1,
            "warmup_period_s": 600.0,
            "simulation_end_s": 3600.0,
            "detector_frequency_s": 120,
            "total_vehicle_km": 1.0,
            "ssm_parse_success": True,
            "lc_parse_success": True,
            "ep_parse_success": True,
            "ee_parse_success": True,
            "vr_parse_success": True,
        }
    )
    for key in (
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
    ):
        summary[key] = 0
    return summary


def test_summary_contract_rejects_missing_core_field_and_accepts_no_event_nan():
    summary = _legacy_summary()
    summary["min_ttc_s"] = math.nan
    summary["max_drac_mps2"] = math.nan
    assert validate_summary_contract(summary, "1") == []

    del summary["total_vehicle_km"]
    assert validate_summary_contract(summary, "1") == [
        "summary missing required key: total_vehicle_km"
    ]


def test_summary_contract_rejects_invalid_identity_count_and_exposure():
    summary = _legacy_summary()
    summary["run_id"] = ""
    summary["ttc_conflict_event_count"] = 1.5
    summary["total_vehicle_km"] = math.nan
    summary["total_CO2_kg"] = math.nan
    summary["non_internal_edge_vehicle_km"] = -1.0

    errors = validate_summary_contract(summary, "1")
    assert "summary run_id must be a non-empty string" in errors
    assert "summary ttc_conflict_event_count must be a non-negative int" in errors
    assert "summary total_vehicle_km must be finite" in errors
    assert "summary total_CO2_kg must be finite" in errors
    assert "summary non_internal_edge_vehicle_km must be non-negative" in errors


def test_writer_summary_read_rejects_missing_core_field(tmp_path):
    from scripts.results.writer import _read_summary

    summary = _legacy_summary()
    del summary["total_vehicle_km"]
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    _, error = _read_summary(tmp_path, "run-1", "1")
    assert error == "summary missing required key: total_vehicle_km"


def test_runner_never_marks_contract_invalid_summary_success(tmp_path, monkeypatch):
    from scripts.parsing.runner import parse_one_run
    from scripts.run_spec import RunSpec, write_run_spec

    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    spec = RunSpec(
        scenario="scenario_0", model="IDM", pcav=0.5, vehicle_count=10, seed=1, run_id="run-1"
    )
    spec_sha = write_run_spec(spec, run_dir)
    for name in (
        "performance.xml",
        "emissions.xml",
        "vehroute.xml",
        "lanechange.xml",
        "stderr.log",
        "ssm.xml",
    ):
        (run_dir / name).write_text("fixture", encoding="utf-8")
    (run_dir / "simulation_status.json").write_text(
        json.dumps(
            {
                "run_id": spec.run_id,
                "status": "SUCCESS",
                "return_code": 0,
                "pipeline_version": spec.pipeline_version,
                "run_spec_sha256": spec_sha,
                "schema_version": spec.schema_version,
                "config_sha256": spec.config_sha256,
                "network_sha256": spec.network_sha256,
                "experiment_id": spec.experiment_id,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.parsing.runner.parse_run_outputs", lambda *_: {"run_id": "run-1"})

    result = parse_one_run(run_dir, spec.pipeline_version)
    assert result["status"] == "INVALID_DATA"
    assert "summary missing required key" in result["error_message"]


def test_subgroup_gate_checks_unique_expected_keys_not_only_row_count():
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
            "metric_value": 0.0,
        }
        for family, dimension, value, metric in expected
    ]
    assert _valid_subgroup_rows(rows, "run-1", spec)
    rows[-1] = dict(rows[0])
    assert not _valid_subgroup_rows(rows, "run-1", spec)


def test_subgroup_gate_rejects_missing_identity_and_metric_value():
    from scripts.results.writer import _valid_subgroup_rows

    assert not _valid_subgroup_rows([{"run_id": "run-1", "metric_family": "capacity"}], "run-1", {})


def test_writer_manifest_duplicate_never_closes_complete_gate(tmp_path):
    from scripts.results.writer import build_run_level_results

    manifest = {
        "pipeline_version": "v0.4.0.post1",
        "schema_version": "1",
        "config_sha256": "a" * 64,
        "total": 2,
        "results": [
            {"run_id": "run-1", "run_spec_sha256": "b" * 64},
            {"run_id": "run-1", "run_spec_sha256": "b" * 64},
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = build_run_level_results(tmp_path, tmp_path / "out", "v0.4.0.post1", manifest_path)
    assert report["duplicate_run_ids"] == 1
    assert report["complete"] is False


def test_writer_manifest_requires_explicit_nonzero_total_and_results(tmp_path):
    from scripts.results.writer import build_run_level_results

    manifest = {
        "pipeline_version": "v0.4.0.post1",
        "schema_version": "1",
        "config_sha256": "a" * 64,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    report = build_run_level_results(tmp_path, tmp_path / "out", "v0.4.0.post1", path)

    assert report["manifest_structure_valid"] is False
    assert report["complete"] is False
