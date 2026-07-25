import json

import pytest

from scripts.parsing.legacy import (
    LEGACY_PIPELINE_VERSION,
    LEGACY_QUALITY,
    LEGACY_SCHEMA_VERSION,
    legacy_spec_from_run_id,
    parse_legacy_run,
)


def test_legacy_spec_requires_explicit_assumptions():
    spec = legacy_spec_from_run_id(
        "s3_CACC_p050_v120_seed5",
        simulation_end=1800,
        warmup=300,
        step_length=0.1,
        detector_frequency=60,
        edge_data_frequency=120,
        loops=150,
    )
    assert spec.scenario == "scenario_3"
    assert spec.model == "CACC"
    assert spec.pcav == 0.5
    assert spec.vehicle_count == 120
    assert spec.seed == 5
    assert spec.pipeline_version == LEGACY_PIPELINE_VERSION
    assert spec.schema_version == LEGACY_SCHEMA_VERSION
    assert spec.experiment_id == LEGACY_QUALITY


def test_legacy_spec_rejects_unknown_directory_name():
    with pytest.raises(ValueError, match="unsupported legacy run_id"):
        legacy_spec_from_run_id(
            "renamed-directory",
            simulation_end=3600,
            warmup=600,
            step_length=0.1,
            detector_frequency=120,
            edge_data_frequency=300,
            loops=300,
        )


def test_legacy_failure_writes_separate_marked_status(tmp_path):
    run_dir = tmp_path / "renamed-directory"
    run_dir.mkdir()
    result = parse_legacy_run(run_dir)
    persisted = json.loads((run_dir / "legacy_parse_status.json").read_text(encoding="utf-8"))

    assert result == persisted
    assert result["status"] == "LEGACY_FAILED"
    assert result["quality"] == LEGACY_QUALITY
    assert not (run_dir / "parse_status.json").exists()
