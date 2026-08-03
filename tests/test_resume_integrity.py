import json

from scripts.parsing.batch import is_parse_complete
from scripts.provenance import sha256_file
from scripts.run_spec import RunSpec, atomic_write_json, write_run_spec


def _spec() -> RunSpec:
    return RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="resume-test",
        config_sha256="c" * 64,
        network_sha256="n" * 64,
        experiment_id="experiment-test",
    )


def _make_complete_run(run_dir):
    spec = _spec()
    run_dir.mkdir()
    digest = write_run_spec(spec, run_dir)
    common = {
        "run_id": spec.run_id,
        "pipeline_version": spec.pipeline_version,
        "schema_version": spec.schema_version,
        "config_sha256": spec.config_sha256,
        "network_sha256": spec.network_sha256,
        "experiment_id": spec.experiment_id,
        "run_spec_sha256": digest,
    }
    atomic_write_json(
        run_dir / "simulation_status.json",
        {**common, "status": "SUCCESS", "return_code": 0},
    )
    atomic_write_json(run_dir / "summary.json", {"run_id": spec.run_id})
    # 纯净分支：schema=2 解析 resume 要求 subgroup 产物（subgroup_summary.jsonl）
    subgroup_path = run_dir / "subgroup_summary.jsonl"
    subgroup_path.write_text('{"run_id": "resume-test"}\n', encoding="utf-8")
    atomic_write_json(
        run_dir / "parse_status.json",
        {
            **common,
            "status": "SUCCESS",
            "summary_sha256": sha256_file(run_dir / "summary.json"),
            "subgroup_summary_sha256": sha256_file(subgroup_path),
        },
    )
    return spec


def test_parse_resume_accepts_unchanged_complete_run(tmp_path):
    spec = _make_complete_run(tmp_path / "run")
    assert is_parse_complete(tmp_path / "run", spec.pipeline_version)


def test_parse_resume_rejects_modified_summary(tmp_path):
    spec = _make_complete_run(tmp_path / "run")
    (tmp_path / "run" / "summary.json").write_text(
        json.dumps({"run_id": spec.run_id, "tampered": True}), encoding="utf-8"
    )
    assert not is_parse_complete(tmp_path / "run", spec.pipeline_version)


def test_parse_resume_rejects_config_hash_mismatch(tmp_path):
    spec = _make_complete_run(tmp_path / "run")
    status_path = tmp_path / "run" / "parse_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["config_sha256"] = "wrong"
    atomic_write_json(status_path, status)
    assert not is_parse_complete(tmp_path / "run", spec.pipeline_version)
