"""v0.4.1 stage2 smoke: full sim→parse→write→aggregate pipeline

集成测试（``@pytest.mark.sumo``）：需要真实 SUMO 二进制与已构建的 SUMO 路网
（``net/scenario_0/loop.net.xml``，gitignored 生成物）。普通单测门禁默认排除
（``pytest -q -m "not sumo"``），由已安装 SUMO 并构建路网的 sumo-smoke CI job
显式执行（``pytest -q -m sumo``）。

测试不会临时修改被 Git 跟踪的 ``net/scenario_0/net.json``：将路网复制到临时
目录并 patch 副本的 ``free_flow_reference_path``，再以 ``--net/--scenario``
指向副本。
"""

import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.sumo


def test_smoke_v4_1_full_pipeline():
    root = Path(tempfile.mkdtemp(prefix="smoke_v4_1_"))
    net_copy_dir = None
    ff_dir = None
    try:
        # ── 复制 scenario_0 路网到临时目录，patch 副本 net.json（不动 tracked 原件）──
        net_src = Path("net/scenario_0")
        net_copy_dir = Path(tempfile.mkdtemp(prefix="net_copy_"))
        shutil.copy2(net_src / "loop.net.xml", net_copy_dir / "loop.net.xml")
        net_meta_patched = copy.deepcopy(
            json.loads((net_src / "net.json").read_text(encoding="utf-8"))
        )

        # Create free-flow artifact in temp path, referenced from the copied net.json
        ff_dir = Path(tempfile.mkdtemp(prefix="ff_art_"))
        from scripts.provenance import sha256_file

        net_sha = sha256_file(str(net_copy_dir / "loop.net.xml"))
        ff_artifact = {
            "reference_id": "ff-smoke",
            "free_flow_version": "v0.4.1-pilot-ff-1",
            "sumo_version": subprocess.run(
                ["sumo", "--version"], capture_output=True, text=True
            ).stdout.strip(),
            "results": {
                "scenario_0": {
                    "net_sha256": net_sha,
                    "references": {
                        "HV": {"lap_time_s": 98.8, "source_run_id": "ff_smoke"},
                        "CAV_IDM": {"lap_time_s": 98.8, "source_run_id": "ff_smoke"},
                        "CAV_CACC": {"lap_time_s": 98.8, "source_run_id": "ff_smoke"},
                    },
                }
            },
        }
        from scripts.run_spec import atomic_write_json

        atomic_write_json(ff_dir / "free_flow_references.json", ff_artifact)
        acceptance_path = ff_dir / "pilot_acceptance.json"
        atomic_write_json(acceptance_path, {"purpose": "post1 smoke only"})

        net_meta_patched["free_flow_reference_path"] = str(ff_dir / "free_flow_references.json")
        (net_copy_dir / "net.json").write_text(json.dumps(net_meta_patched), encoding="utf-8")

        # Stage 1: simulation（--net/--scenario 指向临时副本路网）
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.simulation.batch_run",
                "--config",
                "configs/v0.4.1/smoke_v4_1.json",
                "--output-root",
                str(root),
                "--sumo-processes",
                "1",
                "--acceptance",
                str(acceptance_path),
                "--net",
                str(net_copy_dir / "loop.net.xml"),
                "--scenario",
                "scenario_0",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=".",
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
            ss = json.loads((rd / "simulation_status.json").read_text())
            assert "sumo_peak_rss_kb" in ss
            assert ss["sumo_peak_rss_kb"] > 0

        # Stage 2: parsing
        result = subprocess.run(
            [sys.executable, "-m", "scripts.parsing.batch", "--input-root", str(root), "--resume"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=".",
        )
        assert result.returncode == 0, f"parse failed: {result.stderr[-500:]}"

        # Verify parse_status.json and subgroup_summary.jsonl
        manifest = json.loads((root / "manifest.json").read_text())
        assert set(manifest["frozen_inputs"]) == {"resolved_config_sha256", "acceptance_sha256"}
        for entry in manifest.get("results", []):
            rd = root / entry["run_id"]
            ps = json.loads((rd / "parse_status.json").read_text())
            assert ps["status"] == "SUCCESS", f"parse status: {ps['status']}"
            assert (rd / "subgroup_summary.jsonl").exists()
            assert "parse_peak_rss_kb" in ps
            assert ps["parse_peak_rss_kb"] > 0

        # Stage 3: writer
        out_dir = root / "results"
        out_dir.mkdir(exist_ok=True)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.results.writer",
                "--input-root",
                str(root),
                "--output-dir",
                str(out_dir),
                "--manifest",
                str(root / "manifest.json"),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=".",
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

        # Verify subgroup CSV contains headway metrics
        subgroup = out_dir / "run_level_subgroup_results.csv"
        if subgroup.exists():
            subgroup_text = subgroup.read_text()
            assert "headway" in subgroup_text, "subgroup CSV missing headway metric_family"

        # Stage 4: aggregate
        agg_dir = root / "aggregated"
        agg_dir.mkdir(exist_ok=True)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.results.aggregate",
                "--input",
                str(out_dir / "run_level_results.csv"),
                "--output",
                str(agg_dir / "aggregated_results.csv"),
                "--schema-version",
                "2",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=".",
        )
        assert result.returncode == 0, f"aggregate failed: {result.stderr[-500:]}"
        assert (agg_dir / "aggregated_results.csv").exists()

    finally:
        # 各临时目录均先初始化，setup 提前失败时 cleanup 不会引用未定义变量
        if root is not None:
            shutil.rmtree(root, ignore_errors=True)
        if net_copy_dir is not None:
            shutil.rmtree(net_copy_dir, ignore_errors=True)
        if ff_dir is not None:
            shutil.rmtree(ff_dir, ignore_errors=True)
