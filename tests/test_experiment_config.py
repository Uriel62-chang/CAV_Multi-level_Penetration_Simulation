import json
from dataclasses import replace

import pytest

from scripts.experiment_config import ExperimentConfig, load_experiment_config
from scripts.simulation.batch_run import build_run_specs, validate_specs


def test_default_config_is_stable_and_generates_7524_runs():
    """v0.4.2 main 配置（cav_count 模式，U55 统一密度轴 + 观测窗 1800）round-trip 稳定 + 7,524 runs。"""
    config = load_experiment_config("configs/v0.4.2/main.json")
    assert config.sha256() == ExperimentConfig.from_dict(config.to_dict()).sha256()

    specs = build_run_specs(
        list(config.scenarios),
        list(config.models),
        config.pipeline_version,
        treatments=list(config.treatments),
        sumo_seeds=list(config.sumo_seeds),
        simulation_end=config.simulation_end,
        warmup=config.warmup,
        step_length=config.step_length,
        detector_frequency=config.detector_frequency,
        edge_data_frequency=config.edge_data_frequency,
        loops=config.loops,
        network_files=config.network_files,
        seed_scope=config.seed_scope,
    )
    validate_specs(
        specs,
        list(config.scenarios),
        list(config.models),
        treatments=list(config.treatments),
        sumo_seeds=list(config.sumo_seeds),
    )
    assert len(specs) == 7_524
    assert len({spec.run_id for spec in specs}) == 7_524


def test_smoke_config_passes_current_window_validation():
    config = load_experiment_config("configs/smoke.json")
    assert config.warmup == config.detector_frequency == config.edge_data_frequency == 60


def test_invalid_config_is_rejected_before_run_creation(tmp_path):
    data = load_experiment_config("configs/v0.4.2/main.json").to_dict()
    data["warmup"] = data["simulation_end"]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="warmup"):
        load_experiment_config(path)


def test_duplicate_seed_is_rejected(tmp_path):
    data = load_experiment_config("configs/v0.4.2/main.json").to_dict()
    data["sumo_seeds"] = [101, 101]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicates"):
        load_experiment_config(path)


def test_warmup_must_align_with_edge_data_intervals(tmp_path):
    data = load_experiment_config("configs/v0.4.2/main.json").to_dict()
    data["warmup"] = 240
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="edge_data_frequency"):
        load_experiment_config(path)


def test_warmup_must_align_with_detector_intervals(tmp_path):
    data = load_experiment_config("configs/v0.4.2/main.json").to_dict()
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
        treatments=list(config.treatments),
        sumo_seeds=list(config.sumo_seeds),
        simulation_end=config.simulation_end,
        warmup=config.warmup,
        step_length=config.step_length,
        detector_frequency=config.detector_frequency,
        edge_data_frequency=config.edge_data_frequency,
        loops=config.loops,
        network_files=config.network_files,
        seed_scope=config.seed_scope,
    )
    specs[0] = replace(specs[0], detector_frequency=7)
    with pytest.raises(RuntimeError, match="detector_frequency"):
        validate_specs(
            specs,
            list(config.scenarios),
            list(config.models),
            treatments=list(config.treatments),
            sumo_seeds=list(config.sumo_seeds),
        )
