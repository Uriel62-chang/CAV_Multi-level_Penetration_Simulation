"""v0.4.1 stage2 smoke: full sim→parse→write→aggregate pipeline"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def test_smoke_v4_1_full_pipeline():
    root = Path(tempfile.mkdtemp(prefix="smoke_v4_1_"))
    try:
        # Stage 1: simulation
        result = subprocess.run(
            [sys.executable, "-m", "scripts.simulation.batch_run",
             "--config", "configs/v0.4.1/smoke_v4_1.json",
             "--output-root", str(root), "--sumo-processes", "1"],
            capture_output=True, text=True, timeout=120, cwd=".",
        )
        assert result.returncode == 0, f"sim failed: {result.stderr[-500:]}"
        assert "SUCCESS" in result.stdout

        # Verify subgroup files exist
        run_dirs = sorted(d for d in root.iterdir() if d.is_dir() and d.name != "frozen_inputs")
        assert len(run_dirs) >= 1
        for rd in run_dirs:
            assert (rd / "performance_HV.xml").exists()
            assert (rd / "performance_CAV.xml").exists()
            assert (rd / "emissions_HV.xml").exists()
            assert (rd / "emissions_CAV.xml").exists()

        # Stage 2: parsing
        result = subprocess.run(
            [sys.executable, "-m", "scripts.parsing.batch",
             "--input-root", str(root), "--resume"],
            capture_output=True, text=True, timeout=60, cwd=".",
        )
        assert result.returncode == 0, f"parse failed: {result.stderr[-500:]}"

        # Verify parse_status.json and subgroup_summary.jsonl
        manifest = json.loads((root / "manifest.json").read_text())
        for entry in manifest.get("results", []):
            rd = root / entry["run_id"]
            ps = json.loads((rd / "parse_status.json").read_text())
            assert ps["status"] == "SUCCESS", f"parse status: {ps['status']}"
            assert (rd / "subgroup_summary.jsonl").exists()

        # Stage 3: writer
        out_dir = root / "results"
        out_dir.mkdir(exist_ok=True)
        result = subprocess.run(
            [sys.executable, "-m", "scripts.results.writer",
             "--input-root", str(root), "--output-dir", str(out_dir),
             "--manifest", str(root / "manifest.json")],
            capture_output=True, text=True, timeout=60, cwd=".",
        )
        assert result.returncode == 0, f"writer failed: {result.stderr[-500:]}"
        assert (out_dir / "run_level_results.csv").exists()
        assert (out_dir / "run_level_subgroup_results.csv").exists()
        report = json.loads((out_dir / "writer_report.json").read_text())
        assert report["csv_rows"] > 0
        assert report.get("subgroup_csv_rows", 0) > 0
        assert report["complete"] is True

        # Verify failed_runs.csv if any
        failed = out_dir / "failed_runs.csv"
        if failed.exists():
            with failed.open() as f:
                failed_lines = f.read().strip().split("\n")
                assert len(failed_lines) <= 1  # header only, no failed

    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)
