import json

from scripts.run_spec import SimulationResult
from scripts.simulation.single_run import run_simulation


def test_single_run_reuses_batch_parser_and_writer(monkeypatch, tmp_path):
    calls = {}

    async def fake_run_sumo_process(**kwargs):
        calls["simulation"] = kwargs
        spec = kwargs["spec"]
        return SimulationResult(
            run_id=spec.run_id,
            status="SUCCESS",
            return_code=0,
            run_dir=str(kwargs["output_root"] / spec.run_id),
            started_at="start",
            finished_at="finish",
            wall_time_s=0.1,
        )

    def fake_parse(run_dir, pipeline_version):
        calls["parse"] = (run_dir, pipeline_version)
        return {"status": "SUCCESS"}

    def fake_writer(**kwargs):
        calls["writer"] = kwargs
        return {"complete": True}

    monkeypatch.setattr("scripts.simulation.batch_run.run_sumo_process", fake_run_sumo_process)
    monkeypatch.setattr("scripts.parsing.runner.parse_one_run", fake_parse)
    monkeypatch.setattr("scripts.results.writer.build_run_level_results", fake_writer)
    monkeypatch.setattr(
        "scripts.simulation.single_run.collect_provenance",
        lambda *args: {"test": True},
    )

    output_csv = tmp_path / "single.csv"
    result = run_simulation(
        vehicle_count=10,
        cav_ratio=0.5,
        seed=1,
        loops=2,
        sim_end_time=10,
        warmup_period=1,
        detector_frequency=2,
        output_csv=str(output_csv),
    )

    manifest_path = tmp_path / "single_raw" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["total"] == 1
    assert manifest["results"][0]["status"] == "SUCCESS"
    assert calls["simulation"]["spec"].seed_scope == "vehicle_type_assignment"
    assert calls["writer"]["results_filename"] == "single.csv"
    assert result["simulation_status"] == "SUCCESS"
    assert result["parse_status"] == "SUCCESS"
