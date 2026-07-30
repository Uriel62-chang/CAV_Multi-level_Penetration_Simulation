"""Regression probes for parser/writer summary and closure gates."""

import json
import math

import pytest

from scripts.schema import SUMMARY_NAN_RULES, SUMMARY_REQUIRED_KEYS, validate_summary_contract


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


def test_summary_contract_rejects_infinity_zero_exposure_and_invalid_ranges():
    summary = _legacy_summary()
    summary.update(
        {
            "min_ttc_s": math.inf,
            "mean_speed_m_s": math.inf,
            "total_vehicle_km": 0.0,
            "pCAV": 1.5,
            "step_length_s": 0.0,
        }
    )

    errors = validate_summary_contract(summary, "1")
    assert "summary min_ttc_s must not be infinite" in errors
    assert "summary mean_speed_m_s must not be infinite" in errors
    assert "summary total_vehicle_km must be positive" in errors
    assert "summary pCAV must be within [0, 1]" in errors
    assert "summary step_length_s must be positive" in errors


def test_summary_nan_requires_an_empty_companion_measure():
    summary = _legacy_summary()
    summary.update(
        {
            "ttc_conflict_event_count": 1,
            "min_ttc_s": math.nan,
            "drac_conflict_event_count": 1,
            "max_drac_mps2": math.nan,
            "lane_change_count": 1,
            "unsafe_lc_gap_ratio": math.nan,
            "completed_lap_count": 1,
            "mean_lap_time_s": math.nan,
            "CO2_g_per_veh_km": math.nan,
        }
    )
    errors = validate_summary_contract(summary, "1")
    assert "summary min_ttc_s may be NaN only when ttc_conflict_event_count<=0" in errors
    assert "summary max_drac_mps2 may be NaN only when drac_conflict_event_count<=0" in errors
    assert "summary unsafe_lc_gap_ratio may be NaN only when lane_change_count<=0" in errors
    assert "summary mean_lap_time_s may be NaN only when completed_lap_count<=0" in errors
    assert "summary CO2_g_per_veh_km may be NaN only when total_vehicle_km<=0" in errors


def test_summary_rates_require_exposure_and_bad_types_return_errors():
    summary = _legacy_summary()
    summary.update(
        {
            "ttc_events_per_1000_veh_km": math.nan,
            "emergency_brakes_per_1000_veh_km": math.nan,
            "lane_changes_per_1000_veh_km": math.nan,
        }
    )
    errors = validate_summary_contract(summary, "1")
    assert "summary ttc_events_per_1000_veh_km may be NaN only when total_vehicle_km<=0" in errors
    assert (
        "summary emergency_brakes_per_1000_veh_km may be NaN only when total_vehicle_km<=0"
        in errors
    )
    assert "summary lane_changes_per_1000_veh_km may be NaN only when total_vehicle_km<=0" in errors

    summary["ttc_conflict_event_count"] = "bad"
    assert validate_summary_contract(summary, "1") == [
        "summary ttc_conflict_event_count must be a non-negative int"
    ]


def test_optional_whole_network_ttc_rate_requires_its_optional_exposure():
    summary = _legacy_summary()
    summary["whole_network_ttc_events_per_1000_non_internal_edge_veh_km"] = math.nan

    assert validate_summary_contract(summary, "1") == [
        "summary whole_network_ttc_events_per_1000_non_internal_edge_veh_km "
        "requires companion key: non_internal_edge_vehicle_km"
    ]


def test_summary_nan_rule_table_is_complete_and_respects_thresholds():
    assert set(SUMMARY_NAN_RULES) == {
        "min_ttc_s",
        "max_drac_mps2",
        "mean_speed_m_s",
        "detector_mean_speed_temporal_variance",
        "unsafe_lc_gap_ratio",
        "mean_lap_time_s",
        "median_lap_time_s",
        "p95_lap_time_s",
        "lap_time_std_s",
        "mean_lap_delay_s",
        "p95_lap_delay_s",
        "ttc_events_per_1000_veh_km",
        "emergency_brakes_per_1000_veh_km",
        "lane_changes_per_1000_veh_km",
        "CO2_g_per_veh_km",
        "NOx_mg_per_veh_km",
        "PMx_mg_per_veh_km",
        "fuel_g_per_veh_km",
        "time_loss_s_per_veh_km",
        "whole_network_ttc_events_per_1000_non_internal_edge_veh_km",
    }
    summary = _legacy_summary()
    summary.update(
        {
            "detector_speed_window_count": 2,
            "mean_speed_m_s": math.nan,
            "detector_mean_speed_temporal_variance": math.nan,
            "completed_lap_count": 1,
            "mean_lap_delay_s": math.nan,
            "non_internal_edge_vehicle_km": 1.0,
            "whole_network_ttc_events_per_1000_non_internal_edge_veh_km": math.nan,
        }
    )
    assert len(validate_summary_contract(summary, "1")) == 4
    assert (
        validate_summary_contract(
            {
                **_legacy_summary(),
                "detector_speed_window_count": 1,
                "detector_mean_speed_temporal_variance": math.nan,
            },
            "1",
        )
        == []
    )


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
                }
                else 0.0
            ),
        }
        for family, dimension, value, metric in expected
    ]
    assert _valid_subgroup_rows(rows, "run-1", spec)
    for row in rows:
        if row["metric_family"] == "capacity" and row["metric_name"] == "window_count":
            row["metric_value"] = 1
        if row["metric_family"] == "capacity" and row["metric_name"] == "speed_variance":
            row["metric_value"] = math.nan
    assert _valid_subgroup_rows(rows, "run-1", spec)
    rows[-1] = dict(rows[0])
    assert not _valid_subgroup_rows(rows, "run-1", spec)


def test_subgroup_gate_rejects_missing_identity_and_metric_value():
    from scripts.results.writer import _valid_subgroup_rows

    assert not _valid_subgroup_rows([{"run_id": "run-1", "metric_family": "capacity"}], "run-1", {})


def test_subgroup_gate_rejects_nan_for_nonnullable_metric():
    from scripts.results.writer import _expected_subgroup_keys, _valid_subgroup_rows

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
            "metric_value": math.nan,
        }
        for family, dimension, value, metric in _expected_subgroup_keys(False)
    ]
    assert not _valid_subgroup_rows(rows, "run-1", spec)


def test_subgroup_gate_rejects_negative_counts_exposure_and_emissions():
    from scripts.results.writer import _expected_subgroup_keys, _valid_subgroup_rows

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
            "metric_value": 0,
        }
        for family, dimension, value, metric in _expected_subgroup_keys(False)
    ]
    for row in rows:
        if row["metric_name"] in {"total_vehicle_km", "ttc_event_count", "total_CO2_kg"}:
            row["metric_value"] = -1
    assert not _valid_subgroup_rows(rows, "run-1", spec)


def test_subgroup_gate_resolves_cross_family_nan_prerequisites():
    from scripts.results.writer import _expected_subgroup_keys, _valid_subgroup_rows

    spec = {
        "scenario": "scenario_0",
        "model": "IDM",
        "requested_pcav": None,
        "cav_count": 5,
        "vehicle_count": 10,
        "seed": 1,
        "sumo_seed": 101,
    }
    rows = []
    integer_metrics = {
        "window_count",
        "ttc_event_count",
        "drac_event_count",
        "emergency_braking_count",
        "affected_vehicle_count",
        "lane_change_count",
        "unsafe_lc_gap_count",
        "completed_lap_count",
    }
    for family, dimension, value, metric in _expected_subgroup_keys(False):
        metric_value = 0 if metric in integer_metrics else 0.0
        if (family, metric) in {
            ("efficiency", "total_vehicle_km"),
            ("efficiency", "completed_lap_count"),
            ("capacity", "window_count"),
        }:
            metric_value = 1
        if (family, metric) in {
            ("emissions", "CO2_g_per_veh_km"),
            ("delay", "mean_lap_delay_s"),
            ("capacity", "mean_speed_m_s"),
        }:
            metric_value = math.nan
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
                "metric_name": metric,
                "metric_value": metric_value,
            }
        )
    assert not _valid_subgroup_rows(rows, "run-1", spec)


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


def test_writer_dry_run_rejects_manifest_missing_total_and_results(tmp_path, monkeypatch):
    import sys

    from scripts.results import writer

    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {"pipeline_version": "v0.4.0.post1", "schema_version": "1", "config_sha256": "a" * 64}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "writer",
            "--input-root",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--manifest",
            str(path),
            "--dry-run",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        writer.main()
    assert exc.value.code == 1


@pytest.mark.parametrize(
    "results", [[{"run_id": "run-1"}], [{"run_id": "run-1"}, {"run_id": "run-1"}]]
)
def test_writer_dry_run_requires_manifest_coverage_closure(tmp_path, monkeypatch, results):
    import sys

    from scripts.results import writer

    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "pipeline_version": "v0.4.0.post1",
                "schema_version": "1",
                "config_sha256": "a" * 64,
                "total": 2,
                "results": results,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "writer",
            "--input-root",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--manifest",
            str(path),
            "--dry-run",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        writer.main()
    assert exc.value.code == 1
