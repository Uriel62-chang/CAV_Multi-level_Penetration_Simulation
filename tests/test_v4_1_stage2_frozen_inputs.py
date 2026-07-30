"""v0.4.1 stage2 --frozen-inputs tests"""

import json

import pytest

from scripts.provenance import sha256_file
from scripts.run_spec import PIPELINE_V4_1, RunSpec, build_run_id
from scripts.simulation.single_run import prepare_run


def _make_spec(cav_count=5, vehicle_count=10):
    return RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=cav_count / vehicle_count,
        vehicle_count=vehicle_count,
        seed=1,
        run_id=build_run_id(
            "scenario_0",
            "IDM",
            vehicle_count=vehicle_count,
            cav_count=cav_count,
            assignment_seed=1,
            sumo_seed=101,
        ),
        pipeline_version=PIPELINE_V4_1,
        schema_version="2",
        sumo_seed=101,
        cav_count=cav_count,
        requested_pcav=None,
        with_internal=True,
        ssm_capture_ttc_threshold_s=5.0,
        ssm_capture_drac_threshold_mps2=3.0,
        detector_frequency=60,
        edge_data_frequency=60,
        simulation_end=360,
        warmup=60,
        step_length=0.1,
        loops=4,
        network_file="net/scenario_0/loop.net.xml",
    )


def test_frozen_inputs_routes_preserved(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    route = src_dir / "routes.rou.xml"
    route.write_text("<routes>frozen</routes>")
    tmap = src_dir / "vehicle_type_map.json"
    tmap.write_text(json.dumps({"veh0": "HV", "veh1": "HV"}))

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    spec = _make_spec(vehicle_count=2, cav_count=0)
    prepare_run(spec, run_dir, "net/scenario_0/loop.net.xml", frozen_routes_dir=src_dir)

    assert (run_dir / "routes.rou.xml").read_text() == "<routes>frozen</routes>"


def test_frozen_inputs_missing_file_raises(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    spec = _make_spec(vehicle_count=2, cav_count=0)
    with pytest.raises(FileNotFoundError, match="frozen routes.rou.xml not found"):
        prepare_run(spec, run_dir, "net/scenario_0/loop.net.xml", frozen_routes_dir=src_dir)


def test_frozen_inputs_sha_mismatch_raises(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src_dir.joinpath("routes.rou.xml").write_text("<routes>src</routes>")
    src_dir.joinpath("vehicle_type_map.json").write_text(json.dumps({"veh0": "HV"}))

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    spec = _make_spec(vehicle_count=1, cav_count=0)

    import shutil as _shutil

    original_copy2 = _shutil.copy2

    def broken_copy2(src, dst, **kwargs):
        original_copy2(src, dst, **kwargs)
        if str(dst).endswith("routes.rou.xml"):
            with open(dst, "w") as f:
                f.write("<routes>tampered</routes>")

    monkeypatch.setattr(_shutil, "copy2", broken_copy2)
    with pytest.raises(ValueError, match="SHA mismatch"):
        prepare_run(spec, run_dir, "net/scenario_0/loop.net.xml", frozen_routes_dir=src_dir)


def test_frozen_inputs_sha_match(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src_dir.joinpath("routes.rou.xml").write_text("<routes>ok</routes>")
    src_dir.joinpath("vehicle_type_map.json").write_text(json.dumps({"veh0": "HV"}))

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    spec = _make_spec(vehicle_count=1, cav_count=0)
    prepare_run(spec, run_dir, "net/scenario_0/loop.net.xml", frozen_routes_dir=src_dir)

    assert sha256_file(str(src_dir / "routes.rou.xml")) == sha256_file(
        str(run_dir / "routes.rou.xml")
    )
    assert sha256_file(str(src_dir / "vehicle_type_map.json")) == sha256_file(
        str(run_dir / "vehicle_type_map.json")
    )
