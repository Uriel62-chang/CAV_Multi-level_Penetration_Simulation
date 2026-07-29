import hashlib
import json
from pathlib import Path

import pytest

from scripts.experiment_config import load_experiment_config
from scripts.run_spec import RunSpec
from scripts.schema import RUN_LEVEL_COLUMNS, SUMMARY_REQUIRED_KEYS
from scripts.simulation.batch_run import build_run_specs
from scripts.simulation.single_run import build_sumo_command, prepare_run

BASELINE = json.loads(Path("tests/baselines/v0.4.0-engineering.json").read_text(encoding="utf-8"))


def _digest_json(value) -> str:
    payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize("scenario", tuple(f"scenario_{index}" for index in range(4)))
def test_representative_generated_inputs_match_baseline(scenario, tmp_path):
    network_file = f"net/{scenario}/loop.net.xml"
    spec = RunSpec(
        scenario=scenario,
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id=f"baseline-{scenario}",
        network_file=network_file,
    )
    prepared = prepare_run(spec, tmp_path, network_file)
    command = build_sumo_command(
        prepared,
        network_file,
        sim_end_time=spec.simulation_end,
        step_length=spec.step_length,
    )
    normalized_command = [
        Path(value).name if str(tmp_path) in value else value for value in command
    ]
    actual = {
        "routes_sha256": hashlib.sha256(prepared.route_path.read_bytes()).hexdigest(),
        "additional_sha256": hashlib.sha256(prepared.additional_path.read_bytes()).hexdigest(),
        "sumo_command_sha256": _digest_json(normalized_command),
    }
    assert actual == BASELINE["representative_runs"][scenario]
    assert "--seed" not in command
    assert "--random" not in command


def test_default_grid_matches_baseline():
    config = load_experiment_config("configs/v0.4.0.json")
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
    run_ids = sorted(spec.run_id for spec in specs)
    assert len(run_ids) == BASELINE["default_grid"]["run_count"]
    assert _digest_json(run_ids) == BASELINE["default_grid"]["run_ids_sha256"]


def test_result_schemas_match_baseline():
    schemas = BASELINE["schemas"]
    assert _digest_json(SUMMARY_REQUIRED_KEYS) == schemas["summary_required_keys_sha256"]
    assert _digest_json(RUN_LEVEL_COLUMNS) == schemas["run_level_columns_sha256"]
