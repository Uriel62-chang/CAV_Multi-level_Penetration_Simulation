"""新审阅（2 P0 + 5 P1 + 2 P2）回归：P1-3 CLI 语义 / P1-4 输入完整性 / P1-5 aggregate 期望集合 / P2-1 from_dict 单次构造。"""

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.results.aggregate import aggregate

# ── P1-3：CLI 过滤语义 ──


def _parser():
    import argparse

    return argparse.ArgumentParser()


def _config_dict(**overrides):
    base = {
        "config_version": "v0.4.2-p1-3-test",
        "pipeline_version": "v0.4.2",
        "schema_version": "2",
        "scenarios": ["scenario_0"],
        "models": ["IDM"],
        "grid_mode": "cav_count",
        "seed_scope": "vehicle_type_assignment",
        "simulation_end": 3600,
        "warmup": 600,
        "step_length": 0.1,
        "detector_frequency": 120,
        "edge_data_frequency": 300,
        "loops": 300,
        "network_files": {"scenario_0": "net/scenario_0/loop.net.xml"},
        "treatments": [
            {"vehicle_count": 10, "cav_counts": [0, 5, 10], "assignment_seeds": [1, 2, 3]},
            {"vehicle_count": 30, "cav_counts": [0, 15, 30], "assignment_seeds": [1, 2, 3]},
        ],
        "sumo_seeds": [101],
        "experiment_role": "main_factorial",
        "ssm_enabled": False,
    }
    base.update(overrides)
    return base


def test_vehN_list_filters_existing_treatments_only(monkeypatch, capsys):
    """--vehN-list 只过滤配置已有 treatment，不得发明新 treatment。"""
    import sys

    from scripts.experiment_config import ExperimentConfig

    cfg = ExperimentConfig.from_dict(_config_dict())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "batch_run",
            "--config",
            "configs/v0.4.2/main.json",
            "--vehN-list",
            "10",
            "--dry-run",
            "--config-override",
        ],
    )
    # 直接测试 resolve 逻辑：从 main 读取 CLI 处理函数
    from scripts.simulation import batch_run as br

    class _Args:
        vehN_list = "10"
        assignment_seeds = None
        seeds = None
        sumo_seeds = None
        scenario = None
        model = None
        net = None

    resolved = br._resolve_cli_overrides(cfg, _Args(), _parser())
    treatments = resolved["treatments"]
    assert [int(t["vehicle_count"]) for t in treatments] == [10]
    assert all(t["cav_counts"] == [0, 5, 10] for t in treatments)


def test_vehN_list_unknown_rejected(monkeypatch):
    """未知 vehN 必须报错（不得静默生成 {0, 0.5, 1}）。"""

    from scripts.experiment_config import ExperimentConfig
    from scripts.simulation import batch_run as br

    cfg = ExperimentConfig.from_dict(_config_dict())

    class _Args:
        vehN_list = "30,40"
        assignment_seeds = None
        seeds = None
        sumo_seeds = None
        scenario = None
        model = None
        net = None

    with pytest.raises(SystemExit):
        br._resolve_cli_overrides(cfg, _Args(), _parser())


def test_assignment_seeds_unconditionally_replace(monkeypatch):
    """--assignment-seeds 必须无条件替换 interior seeds（不得因 treatment 已有键而跳过）。"""
    from scripts.experiment_config import ExperimentConfig
    from scripts.simulation import batch_run as br

    cfg = ExperimentConfig.from_dict(_config_dict())

    class _Args:
        vehN_list = None
        assignment_seeds = "9"
        seeds = None
        sumo_seeds = None
        scenario = None
        model = None
        net = None

    resolved = br._resolve_cli_overrides(cfg, _Args(), _parser())
    for t in resolved["treatments"]:
        assert t["assignment_seeds"] == [9]
    # 端点 sentinel 0 由 _build_cav_count_specs 保证
    specs = br.build_run_specs(
        scenarios=["scenario_0"],
        models=["IDM"],
        treatments=resolved["treatments"],
        sumo_seeds=resolved["sumo_seeds"],
        pipeline_version="v0.4.2",
        schema_version="2",
        config_sha256="x",
        network_sha256={"scenario_0": "y"},
        experiment_id="e",
        network_files={"scenario_0": "net/scenario_0/loop.net.xml"},
    )
    interior = [s for s in specs if s.cav_count not in (0, s.vehicle_count)]
    endpoints = [s for s in specs if s.cav_count in (0, s.vehicle_count)]
    assert interior and all(s.seed == 9 for s in interior)
    assert endpoints and all(s.seed == 0 for s in endpoints)


# ── P1-4：输入完整性（stderr 哈希 + sidecar 迁移）──


def _write_status_with_raw_hashes(run_dir: Path, raw_hashes: dict) -> None:
    (run_dir / "simulation_status.json").write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "pipeline_version": "v0.4.2",
                "status": "SUCCESS",
                "return_code": 0,
                "run_spec_sha256": "x",
                "schema_version": "2",
                "config_sha256": "",
                "network_sha256": "",
                "experiment_id": "",
                "raw_output_sha256": raw_hashes,
            }
        ),
        encoding="utf-8",
    )


class _SpecStub:
    pipeline_version = "v0.4.2"
    fcd_profile = None
    ssm_enabled = False
    network_file = "net/scenario_0/loop.net.xml"
    run_id = "run-1"


def test_input_integrity_new_run_status_covers_stderr(tmp_path):
    """新 run：status 的 raw_output_sha256 含 stderr.log → 直接校验通过。"""
    from scripts.parsing.input_integrity import verify
    from scripts.provenance import sha256_file

    rd = tmp_path / "run-1"
    rd.mkdir()
    (rd / "stderr.log").write_text("log", encoding="utf-8")
    _write_status_with_raw_hashes(rd, {"stderr.log": sha256_file(rd / "stderr.log")})
    ok, errors = verify(rd, _SpecStub())
    assert ok, errors


def test_input_integrity_old_run_requires_sidecar(tmp_path):
    """旧 run：status 未哈希 stderr.log → 无 sidecar 时 fail-closed。"""
    from scripts.parsing.input_integrity import verify

    rd = tmp_path / "run-1"
    rd.mkdir()
    (rd / "stderr.log").write_text("log", encoding="utf-8")
    _write_status_with_raw_hashes(rd, {"performance.xml": "a" * 64})
    ok, errors = verify(rd, _SpecStub())
    assert not ok
    assert any("input_integrity.sidecar.json" in e for e in errors)


def test_input_integrity_sidecar_migration_passes(tmp_path):
    """迁移路径：显式 sidecar（purpose 正确 + stderr SHA 匹配）放行。"""
    from scripts.parsing.input_integrity import PURPOSE, verify, write_sidecar

    rd = tmp_path / "run-1"
    rd.mkdir()
    (rd / "stderr.log").write_text("log", encoding="utf-8")
    perf = rd / "performance.xml"
    perf.write_text("perf", encoding="utf-8")
    from scripts.provenance import sha256_file

    _write_status_with_raw_hashes(rd, {"performance.xml": sha256_file(perf)})
    sidecar_path = write_sidecar(rd, _SpecStub())
    assert sidecar_path.exists()
    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert payload["purpose"] == PURPOSE
    assert "stderr.log" in payload["files"]
    ok, errors = verify(rd, _SpecStub())
    assert ok, errors
    # sidecar 篡改（stderr 哈希错误）→ 拒绝
    payload["files"]["stderr.log"] = "f" * 64
    payload["anchor_sha256"] = json.dumps(payload["files"], sort_keys=True)[:64]
    sidecar_path.write_text(json.dumps(payload), encoding="utf-8")
    ok, errors = verify(rd, _SpecStub())
    assert not ok
    assert any("anchor_sha256" in e for e in errors)


# ── P1-5：aggregate 期望集合校验 ──


def _run_level_df(schema_cols, rows):
    data = []
    for r in rows:
        row = {c: "" for c in schema_cols}
        row.update(r)
        data.append(row)
    return pd.DataFrame(data)


def test_aggregate_missing_seed_pair_fails_closed(tmp_path):
    """删除 3×3 网格中的一个组合 → 必须 fail-closed（不得输出 n=8）。"""
    from scripts.schema import RUN_LEVEL_COLUMNS_V4_2

    cols = RUN_LEVEL_COLUMNS_V4_2
    rows = []
    combos = [(a, s) for a in (1, 2, 3) for s in (101, 102, 103)]
    combos.pop(2)  # 缺失 (3, 101)
    for i, (a, s) in enumerate(combos):
        rows.append(
            {
                "run_id": f"r{i}",
                "scenario": "scenario_0",
                "model": "IDM",
                "requested_pcav": 0.5,
                "realized_pcav": 0.5,
                "cav_count": 5,
                "hv_count": 5,
                "vehN": 10,
                "assignment_seed": a,
                "sumo_seed": s,
                "data_quality": "ok",
                "mean_flow_veh_h": 100.0,
                "total_vehicle_km": 10.0,
            }
        )
    df = _run_level_df(cols, rows)
    in_csv = tmp_path / "in.csv"
    out_csv = tmp_path / "out.csv"
    df.to_csv(in_csv, index=False)
    manifest = {
        "treatments": [{"vehicle_count": 10, "cav_counts": [5], "assignment_seeds": [1, 2, 3]}],
        "sumo_seeds": [101, 102, 103],
        "results": [{"run_id": f"r{i}"} for i in range(len(rows))],
    }
    with pytest.raises(ValueError, match="missing="):
        aggregate(in_csv, out_csv, "2", manifest=manifest)


def test_aggregate_manifest_run_id_set_mismatch(tmp_path):
    """CSV run_id 与 manifest 期望集合不等 → fail-closed。"""
    from scripts.schema import RUN_LEVEL_COLUMNS_V4_2

    cols = RUN_LEVEL_COLUMNS_V4_2
    rows = [
        {
            "run_id": f"r{i}",
            "scenario": "scenario_0",
            "model": "IDM",
            "requested_pcav": 0.5,
            "realized_pcav": 0.5,
            "cav_count": 5,
            "hv_count": 5,
            "vehN": 10,
            "assignment_seed": a,
            "sumo_seed": s,
            "data_quality": "ok",
            "mean_flow_veh_h": 100.0,
            "total_vehicle_km": 10.0,
        }
        for i, (a, s) in enumerate((a, s) for a in (1, 2, 3) for s in (101, 102, 103))
    ]
    df = _run_level_df(cols, rows)
    in_csv = tmp_path / "in.csv"
    out_csv = tmp_path / "out.csv"
    df.to_csv(in_csv, index=False)
    manifest = {
        "treatments": [{"vehicle_count": 10, "cav_counts": [5], "assignment_seeds": [1, 2, 3]}],
        "sumo_seeds": [101, 102, 103],
        "results": [{"run_id": f"r{i}"} for i in range(9) if i != 5],  # 缺一个
    }
    with pytest.raises(ValueError, match="run_id set mismatch"):
        aggregate(in_csv, out_csv, "2", manifest=manifest)


def test_aggregate_full_combo_passes(tmp_path):
    """完整 9 组合 + manifest 全等 → 通过。"""
    from scripts.schema import RUN_LEVEL_COLUMNS_V4_2

    cols = RUN_LEVEL_COLUMNS_V4_2
    rows = []
    for i, (a, s) in enumerate((a, s) for a in (1, 2, 3) for s in (101, 102, 103)):
        rows.append(
            {
                "run_id": f"r{i}",
                "scenario": "scenario_0",
                "model": "IDM",
                "requested_pcav": 0.5,
                "realized_pcav": 0.5,
                "cav_count": 5,
                "hv_count": 5,
                "vehN": 10,
                "assignment_seed": a,
                "sumo_seed": s,
                "data_quality": "ok",
                "mean_flow_veh_h": 100.0,
                "total_vehicle_km": 10.0,
            }
        )
    df = _run_level_df(cols, rows)
    in_csv = tmp_path / "in.csv"
    out_csv = tmp_path / "out.csv"
    df.to_csv(in_csv, index=False)
    manifest = {
        "treatments": [{"vehicle_count": 10, "cav_counts": [5], "assignment_seeds": [1, 2, 3]}],
        "sumo_seeds": [101, 102, 103],
        "results": [{"run_id": f"r{i}"} for i in range(9)],
    }
    out = aggregate(in_csv, out_csv, "2", manifest=manifest)
    assert len(out) == 1


# ── P2-1：from_dict 单次构造（envelope 校验生效）──


def _v4_2_spec_dict(**overrides):
    from scripts.run_spec import PIPELINE_V4_2, RunSpec

    spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="x",
        pipeline_version=PIPELINE_V4_2,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
        experiment_role="main_factorial",
        ssm_enabled=False,
    )
    d = spec.to_dict()
    d.update(overrides)
    return d


def test_from_dict_rejects_safety_with_ssm_disabled():
    from scripts.run_spec import RunSpec

    with pytest.raises(ValueError, match="safety experiment must set ssm_enabled=true"):
        RunSpec.from_dict(_v4_2_spec_dict(experiment_role="safety", ssm_enabled=False))


def test_from_dict_rejects_main_with_ssm_enabled():
    from scripts.run_spec import RunSpec

    with pytest.raises(ValueError, match="main_factorial experiment must set ssm_enabled=false"):
        RunSpec.from_dict(_v4_2_spec_dict(experiment_role="main_factorial", ssm_enabled=True))


def test_from_dict_rejects_analysis_ttc_above_capture():
    from scripts.run_spec import RunSpec

    with pytest.raises(ValueError, match="analysis_ttc_threshold_s"):
        RunSpec.from_dict(_v4_2_spec_dict(analysis_ttc_threshold_s=4.0))


def test_from_dict_rejects_analysis_drac_below_capture():
    from scripts.run_spec import RunSpec

    with pytest.raises(ValueError, match="analysis_drac_threshold_mps2"):
        RunSpec.from_dict(_v4_2_spec_dict(analysis_drac_threshold_mps2=2.0))


def test_from_dict_valid_round_trip():
    from scripts.run_spec import RunSpec

    spec = RunSpec.from_dict(_v4_2_spec_dict())
    assert spec.experiment_role == "main_factorial"
    assert spec.ssm_enabled is False
    assert spec.analysis_ttc_threshold_s == 3.0
