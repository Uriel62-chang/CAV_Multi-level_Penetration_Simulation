"""v0.4.1 stage2 parse peak RSS isolation test"""

import json
import time


def test_parse_rss_isolation_large_then_small(tmp_path, monkeypatch):
    from scripts.parsing.runner import parse_one_run

    spec = {
        "scenario": "scenario_0",
        "model": "IDM",
        "pcav": 0.5,
        "vehicle_count": 10,
        "seed": 1,
        "run_id": "run1",
        "simulation_end": 3600,
        "warmup": 600,
        "pipeline_version": "v0.4.0.post1",
        "schema_version": "1",
        "config_sha256": "",
        "network_sha256": "",
        "experiment_id": "",
    }

    rd1 = tmp_path / "run1"
    rd1.mkdir()
    rd2 = tmp_path / "run2"
    rd2.mkdir()

    for rd in (rd1, rd2):
        (rd / "run_spec.json").write_text(json.dumps(spec))
        (rd / "performance.xml").write_text("<meandata/>")
        (rd / "emissions.xml").write_text("<meandata/>")
        (rd / "vehroute.xml").write_text("<routes/>")
        (rd / "lanechange.xml").write_text("<lanechanges/>")
        (rd / "stderr.log").write_text("")
        (rd / "ssm.xml").write_text("<SSMLog/>")
        status = {
            "run_id": rd.name,
            "pipeline_version": "v0.4.0.post1",
            "status": "SUCCESS",
            "return_code": 0,
            "run_spec_sha256": "",
            "schema_version": "1",
            "config_sha256": "",
            "network_sha256": "",
            "experiment_id": "",
        }
        (rd / "simulation_status.json").write_text(json.dumps(status))

    _block = ["x"] * (10 * 1024 * 1024)  # ~80 MB string allocation
    ps1 = parse_one_run(rd1, "v0.4.0.post1")
    del _block
    time.sleep(0.05)
    ps2 = parse_one_run(rd2, "v0.4.0.post1")

    assert ps1["parse_peak_rss_kb"] > 0
    assert ps2["parse_peak_rss_kb"] > 0
    assert ps1["parse_peak_rss_kb"] > ps2["parse_peak_rss_kb"], (
        f"large run RSS ({ps1['parse_peak_rss_kb']}) should exceed "
        f"small run RSS ({ps2['parse_peak_rss_kb']})"
    )
