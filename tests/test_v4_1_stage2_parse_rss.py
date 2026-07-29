"""v0.4.1 stage2 parse peak RSS isolation test"""

import json
import time


def test_parse_rss_reset_across_runs(tmp_path):
    from scripts.parsing.runner import parse_one_run

    rd1 = tmp_path / "run1"
    rd1.mkdir()
    rd2 = tmp_path / "run2"
    rd2.mkdir()

    for rd in (rd1, rd2):
        spec = {
            "scenario": "scenario_0",
            "model": "IDM",
            "pcav": 0.5,
            "vehicle_count": 10,
            "seed": 1,
            "run_id": rd.name,
            "pipeline_version": "v0.4.0.post1",
            "schema_version": "1",
            "config_sha256": "",
            "network_sha256": "",
            "experiment_id": "",
        }
        (rd / "run_spec.json").write_text(json.dumps(spec))
        for f in [
            "performance.xml",
            "emissions.xml",
            "vehroute.xml",
            "lanechange.xml",
            "stderr.log",
            "ssm.xml",
        ]:
            (rd / f).write_text("<root/>" if not f.endswith("log") else "")
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

    ps1 = parse_one_run(rd1, "v0.4.0.post1")
    time.sleep(0.05)
    ps2 = parse_one_run(rd2, "v0.4.0.post1")

    assert "parse_peak_rss_kb" in ps1
    assert "parse_peak_rss_kb" in ps2
    assert ps1["parse_peak_rss_kb"] > 0
    assert ps2["parse_peak_rss_kb"] > 0
