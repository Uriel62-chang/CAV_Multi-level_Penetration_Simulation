import json
from dataclasses import replace

import pytest

from scripts.experiment_config import ExperimentConfig, load_experiment_config
from scripts.simulation.batch_run import build_run_specs, validate_specs


def test_default_config_is_stable_and_generates_10080_runs():
    config = load_experiment_config("configs/v0.4.0.json")
    assert config.sha256() == ExperimentConfig.from_dict(config.to_dict()).sha256()

    specs = build_run_specs(
        list(config.scenarios),
        list(config.models),
        config.pipeline_version,
        pcav_levels=list(config.pcav_levels),
        vehicle_levels=list(config.vehicle_counts),
        seeds=list(config.seeds),
        simulation_end=config.simulation_end,
        warmup=config.warmup,
        step_length=config.step_length,
        detector_frequency=config.detector_frequency,
        edge_data_frequency=config.edge_data_frequency,
        loops=config.loops,
        network_files=config.network_files,
        seed_scope=config.seed_scope,
        schema_version=config.schema_version,
    )
    validate_specs(
        specs,
        list(config.scenarios),
        list(config.models),
        pcav_levels=list(config.pcav_levels),
        vehicle_levels=list(config.vehicle_counts),
        seeds=list(config.seeds),
    )
    assert len(specs) == 10_080
    assert len({spec.run_id for spec in specs}) == 10_080


def test_smoke_config_passes_current_window_validation():
    config = load_experiment_config("configs/smoke.json")
    assert config.warmup == config.detector_frequency == config.edge_data_frequency == 20


def test_invalid_config_is_rejected_before_run_creation(tmp_path):
    data = load_experiment_config("configs/v0.4.0.json").to_dict()
    data["warmup"] = data["simulation_end"]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="warmup"):
        load_experiment_config(path)


def test_duplicate_seed_is_rejected(tmp_path):
    data = load_experiment_config("configs/v0.4.0.json").to_dict()
    data["seeds"] = [1, 1]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicates"):
        load_experiment_config(path)


def test_warmup_must_align_with_edge_data_intervals(tmp_path):
    data = load_experiment_config("configs/v0.4.0.json").to_dict()
    data["warmup"] = 240
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="edge_data_frequency"):
        load_experiment_config(path)


def test_warmup_must_align_with_detector_intervals(tmp_path):
    data = load_experiment_config("configs/v0.4.0.json").to_dict()
    data["detector_frequency"] = 110
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="detector_frequency"):
        load_experiment_config(path)


def test_batch_validation_rejects_detector_window_misalignment():
    config = load_experiment_config("configs/smoke.json")
    specs = build_run_specs(
        list(config.scenarios),
        list(config.models),
        config.pipeline_version,
        pcav_levels=list(config.pcav_levels),
        vehicle_levels=list(config.vehicle_counts),
        seeds=list(config.seeds),
        simulation_end=config.simulation_end,
        warmup=config.warmup,
        step_length=config.step_length,
        detector_frequency=config.detector_frequency,
        edge_data_frequency=config.edge_data_frequency,
        loops=config.loops,
        network_files=config.network_files,
        seed_scope=config.seed_scope,
        schema_version=config.schema_version,
    )
    specs[0] = replace(specs[0], detector_frequency=7)
    with pytest.raises(RuntimeError, match="detector_frequency"):
        validate_specs(
            specs,
            list(config.scenarios),
            list(config.models),
            pcav_levels=list(config.pcav_levels),
            vehicle_levels=list(config.vehicle_counts),
            seeds=list(config.seeds),
        )
