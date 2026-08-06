import json
from pathlib import Path

from scripts.run_spec import SimulationResult
from scripts.simulation.single_run import run_simulation


def _run_with_fakes(monkeypatch, tmp_path, vehicle_count, cav_ratio):
    """构造 run_simulation 的 fake 依赖链，返回捕获的 simulation spec 与 manifest。"""
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

    network_dir = tmp_path / "net" / "scenario_0"
    network_dir.mkdir(parents=True)
    network_path = network_dir / "loop.net.xml"
    network_path.write_text("<net/>", encoding="utf-8")
    source_metadata = Path("net/scenario_0/net.json")
    (network_dir / "net.json").write_text(source_metadata.read_text(encoding="utf-8"))

    output_csv = tmp_path / "single.csv"
    run_simulation(
        vehicle_count=vehicle_count,
        cav_ratio=cav_ratio,
        seed=1,
        loops=2,
        sim_end_time=10,
        warmup_period=1,
        detector_frequency=2,
        output_csv=str(output_csv),
        network_file=str(network_path),
    )
    return calls


def test_single_run_reuses_batch_parser_and_writer(monkeypatch, tmp_path):
    calls = _run_with_fakes(monkeypatch, tmp_path, vehicle_count=10, cav_ratio=0.5)

    manifest_path = tmp_path / "single_raw" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["total"] == 1
    assert manifest["results"][0]["status"] == "SUCCESS"
    assert calls["simulation"]["spec"].seed_scope == "vehicle_type_assignment"
    assert calls["writer"]["results_filename"] == "single.csv"
    assert calls["simulation"]["spec"].cav_count == 5


def test_single_run_cav_count_rounds_half_up_not_banker(monkeypatch, tmp_path):
    """审查 P2-2：cav_count 四舍五入（int(x+0.5)）而非 round() 银行家舍入。

    --pCAV 0.35 --vehN 30 → 10.5：round() 取偶得 10（realized 0.333），
    四舍五入得 11（realized 0.367）——后者更接近请求值 0.35。
    """
    calls = _run_with_fakes(monkeypatch, tmp_path, vehicle_count=30, cav_ratio=0.35)

    spec = calls["simulation"]["spec"]
    assert spec.cav_count == 11
    assert spec.run_id.endswith("_c011_as01_ss000")
