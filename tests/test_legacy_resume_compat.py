"""Frozen v0.4.0 resume compatibility probes.

These fixtures deliberately model persisted historical inputs rather than a
RunSpec serialization round trip.  A legacy run is reusable only if every
identity and frozen-input check still closes.
"""

import json

from scripts.experiment_config import load_experiment_config
from scripts.provenance import sha256_file
from scripts.run_spec import PIPELINE_V4_0_POST1, RunSpec, is_simulation_complete

LEGACY_CONFIG_SHA256 = "178dfcef1bf352ab27eb1b91ec59b001418416387cf703a7e62a0aa6ff883b87"


def _legacy_spec_data() -> dict:
    return {
        "run_id": "s0_IDM_p050_v010_seed1",
        "scenario": "scenario_0",
        "model": "IDM",
        "pcav": 0.5,
        "vehicle_count": 10,
        "seed": 1,
        "simulation_end": 3600.0,
        "warmup": 600.0,
        "step_length": 0.1,
        "detector_frequency": 120,
        "edge_data_frequency": 300,
        "loops": 300,
        "network_file": "net/scenario_0/loop.net.xml",
        "seed_scope": "vehicle_type_assignment",
        "pipeline_version": "v0.4.0.post1",
        "schema_version": "1",
        "config_sha256": LEGACY_CONFIG_SHA256,
        "network_sha256": "a" * 64,
        "experiment_id": "v0.4.0",
        "requested_pcav": 0.5,
        "cav_count": 5,
        "hv_count": 5,
        "realized_pcav": 0.5,
    }


def _write_frozen_legacy_run(run_dir):
    run_dir.mkdir()
    spec_data = _legacy_spec_data()
    (run_dir / "run_spec.json").write_text(json.dumps(spec_data), encoding="utf-8")
    spec = RunSpec.from_dict(spec_data)
    for name in (
        "routes.rou.xml",
        "ssm.xml",
        "lanechange.xml",
        "performance.xml",
        "emissions.xml",
        "vehroute.xml",
    ):
        (run_dir / name).write_text("frozen", encoding="utf-8")
    (run_dir / "simulation_status.json").write_text(
        json.dumps(
            {
                "run_id": spec.run_id,
                "status": "SUCCESS",
                "return_code": 0,
                "pipeline_version": PIPELINE_V4_0_POST1,
                "run_spec_sha256": spec.sha256(),
                "schema_version": spec.schema_version,
                "config_sha256": spec.config_sha256,
                "network_sha256": spec.network_sha256,
                "experiment_id": spec.experiment_id,
                "route_file_sha256": sha256_file(run_dir / "routes.rou.xml"),
            }
        ),
        encoding="utf-8",
    )
    return spec


def test_v040_config_hash_is_frozen():
    config = load_experiment_config("configs/v0.4.0.json")

    assert config.sha256() == LEGACY_CONFIG_SHA256
    assert "ssm_capture_ttc_threshold_s" not in config.to_dict()
    assert "with_internal" not in config.to_dict()


def test_frozen_legacy_run_is_skipped_and_rejects_tampering(tmp_path):
    run_dir = tmp_path / "s0_IDM_p050_v010_seed1"
    spec = _write_frozen_legacy_run(run_dir)

    assert is_simulation_complete(spec, run_dir, PIPELINE_V4_0_POST1)

    status_path = run_dir / "simulation_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["config_sha256"] = "b" * 64
    status_path.write_text(json.dumps(status), encoding="utf-8")
    assert not is_simulation_complete(spec, run_dir, PIPELINE_V4_0_POST1)

    status["config_sha256"] = spec.config_sha256
    status["run_spec_sha256"] = "c" * 64
    status_path.write_text(json.dumps(status), encoding="utf-8")
    assert not is_simulation_complete(spec, run_dir, PIPELINE_V4_0_POST1)

    status["run_spec_sha256"] = spec.sha256()
    status_path.write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "routes.rou.xml").write_text("modified", encoding="utf-8")
    assert not is_simulation_complete(spec, run_dir, PIPELINE_V4_0_POST1)
