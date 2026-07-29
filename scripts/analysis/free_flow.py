"""阶段 2 自由流参考测量。"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from scripts.parsing.vehroute import parse_lap_times
from scripts.provenance import sha256_file
from scripts.run_spec import PIPELINE_V4_1, RunSpec, atomic_write_json, write_run_spec
from scripts.simulation.flow_generator import generate_flow
from scripts.simulation.single_run import load_network_meta


def measure_free_flow(config_path="configs/v0.4.1/free_flow.json",
                      output_dir="artifacts/free_flow/v0.4.1-pilot-ff-1"):
    with open(config_path) as f:
        cfg = json.load(f)

    results = {}
    for scenario in cfg["scenarios"]:
        network_file = f"net/{scenario}/loop.net.xml"
        net_meta = load_network_meta(network_file)
        refs = {}

        # HV-only run (model sentinel "IDM", cav=0)
        run_id = f"ff_{scenario}_HV"
        spec = RunSpec(
            scenario=scenario, model="IDM", pcav=0.0, vehicle_count=1, seed=1,
            run_id=run_id, simulation_end=cfg.get("simulation_end", 600),
            warmup=cfg.get("warmup", 120), step_length=0.1,
            detector_frequency=60, edge_data_frequency=60,
            loops=cfg.get("loops", 60),
            network_file=network_file,
            pipeline_version=PIPELINE_V4_1, schema_version="2",
            sumo_seed=1, cav_count=0, requested_pcav=None,
            with_internal=False,
        )
        hv_lap = _run_free_flow(run_id, spec, network_file, net_meta, cfg)

        # CAV+IDM and CAV+CACC
        for model in cfg.get("models", ["IDM", "CACC"]):
            run_id = f"ff_{scenario}_CAV_{model}"
            spec = RunSpec(
                scenario=scenario, model=model, pcav=1.0, vehicle_count=1, seed=1,
                run_id=run_id, simulation_end=cfg.get("simulation_end", 600),
                warmup=cfg.get("warmup", 120), step_length=0.1,
                detector_frequency=60, edge_data_frequency=60,
                loops=cfg.get("loops", 60),
                network_file=network_file,
                pipeline_version=PIPELINE_V4_1, schema_version="2",
                sumo_seed=1, cav_count=1, requested_pcav=None,
                with_internal=False,
            )
            lap = _run_free_flow(run_id, spec, network_file, net_meta, cfg)
            refs[f"CAV_{model}"] = {"lap_time_s": lap, "source_run_id": run_id}

        refs["HV"] = {"lap_time_s": hv_lap, "source_run_id": f"ff_{scenario}_HV"}
        results[scenario] = {
            "net_sha256": sha256_file(network_file),
            "references": refs,
        }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    artifact = {
        "reference_id": "ff-v0.4.1-pilot-ff-1",
        "free_flow_version": cfg.get("free_flow_version", ""),
        "sumo_version": "1.27.1",
        "results": results,
    }
    atomic_write_json(out / "free_flow_references.json", artifact)
    print(f"[WRITE] free_flow_references.json → {out}")
    return artifact


def _run_free_flow(run_id, spec, network_file, net_meta, cfg):
    run_dir = Path(tempfile.mkdtemp(prefix="ff_"))
    write_run_spec(spec, run_dir)
    edge_ids = net_meta.get("edge_ids", [f"e{i}" for i in range(4)])
    generate_flow(1, spec.pcav, spec.loops, spec.seed, str(run_dir / "routes.rou.xml"),
                  spec.model, edge_count=len(edge_ids),
                  edge_length=net_meta["edge_length_m"],
                  scenario=spec.scenario, num_lanes=net_meta.get("num_lanes", 1),
                  edge_ids=edge_ids)
    cmd = [
        "sumo", "-n", network_file, "-r", str(run_dir / "routes.rou.xml"),
        "-b", "0", "-e", str(int(spec.simulation_end)),
        "--step-length", str(spec.step_length),
        "--no-step-log", "true",
        "--vehroute-output", str(run_dir / "vehroute.xml"),
        "--vehroute-output.exit-times", "true",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"free-flow run failed: {result.stderr[-500:]}")

    vr = parse_lap_times(
        str(run_dir / "vehroute.xml"),
        edges_per_lap=net_meta.get("num_sides", len(edge_ids)),
        warmup_period=cfg.get("warmup", 120),
        sim_end_time=spec.simulation_end,
    )
    shutil.rmtree(run_dir, ignore_errors=True)
    return vr["median_lap_time_s"]


if __name__ == "__main__":
    measure_free_flow()
