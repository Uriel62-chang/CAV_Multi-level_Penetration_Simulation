import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.analysis import ssm_reproducer
from scripts.analysis.ssm_reproducer import (
    build_diagnostic_command,
    load_case,
    normalize_non_ssm_command,
    summarize_ssm_evidence,
)


def test_attempt_directory_is_monotonic_and_non_reusable(tmp_path):
    from scripts.analysis.ssm_reproducer import create_attempt_directory

    first = create_attempt_directory(tmp_path, "diag")
    second = create_attempt_directory(tmp_path, "diag")

    assert first.name == "attempt-001"
    assert second.name == "attempt-002"
    assert not (first / "attempt_status.json").exists()


def test_frozen_s2_and_s3_cases_only_differ_by_scenario():
    s2 = load_case("configs/v0.4.1/ssm_reproducer_s2.json")
    s3 = load_case("configs/v0.4.1/ssm_reproducer_s3.json")

    assert s2["expected_ttc"] == "zero"
    assert s3["expected_ttc"] == "positive"
    assert {
        key: value
        for key, value in s2.items()
        if key not in {"case_id", "scenario", "network_file", "expected_ttc"}
    } == {
        key: value
        for key, value in s3.items()
        if key not in {"case_id", "scenario", "network_file", "expected_ttc"}
    }


def test_load_case_rejects_noncanonical_full_cav_seed(tmp_path):
    case = json.loads(Path("configs/v0.4.1/ssm_reproducer_s2.json").read_text(encoding="utf-8"))
    case["assignment_seed"] = 1
    path = tmp_path / "case.json"
    path.write_text(json.dumps(case), encoding="utf-8")

    with pytest.raises(ValueError, match="assignment_seed=0"):
        load_case(path)


def test_summarize_ssm_evidence_marks_failed_positive_control(tmp_path):
    xml = tmp_path / "ssm.xml"
    xml.write_text("<ssmLog/>", encoding="utf-8")

    evidence = summarize_ssm_evidence(xml, warmup=600, expected_ttc="positive")

    assert evidence["ttc_event_count"] == 0
    assert evidence["control_status"] == "positive-control failed"


def test_ssm_off_command_removes_every_ssm_device_option(monkeypatch):
    monkeypatch.setattr(
        ssm_reproducer,
        "build_sumo_command",
        lambda *_: [
            "sumo",
            "--device.ssm.probability",
            "1.0",
            "--device.ssm.file",
            "/tmp/a/ssm.xml",
            "--device.ssm.measures",
            "TTC DRAC",
            "--device.ssm.thresholds",
            "5.0 3.0",
            "--device.ssm.range",
            "50.0",
            "--device.ssm.trajectories",
            "false",
            "--device.ssm.extratime",
            "5.0",
            "--fcd-output",
            "/tmp/a/fcd.xml.gz",
        ],
    )

    command = build_diagnostic_command(None, "net.xml", None, "sumo", ssm_enabled=False)

    assert not any(argument.startswith("--device.ssm") for argument in command)
    assert command == ["sumo", "--fcd-output", "/tmp/a/fcd.xml.gz"]


def test_normalized_non_ssm_commands_only_allow_ssm_and_attempt_path_differences(monkeypatch):
    def base_command(prepared, network_file, _spec, sumo_command):
        return [
            sumo_command,
            "-n",
            network_file,
            "-r",
            str(prepared.run_dir / "routes.rou.xml"),
            "--device.ssm.file",
            str(prepared.run_dir / "ssm.xml"),
            "--device.ssm.range",
            "50.0",
            "--fcd-output",
            str(prepared.run_dir / "fcd.xml.gz"),
        ]

    monkeypatch.setattr(ssm_reproducer, "build_sumo_command", base_command)
    prepared_on = SimpleNamespace(run_dir=Path("/tmp/attempt-a/raw/run"))
    prepared_off = SimpleNamespace(run_dir=Path("/tmp/attempt-b/raw/run"))
    on = build_diagnostic_command(prepared_on, "net.xml", None, "sumo", ssm_enabled=True)
    off = build_diagnostic_command(prepared_off, "net.xml", None, "sumo", ssm_enabled=False)

    normalized_on = normalize_non_ssm_command(on, prepared_on.run_dir)
    normalized_off = normalize_non_ssm_command(off, prepared_off.run_dir)
    assert normalized_on == normalized_off
    assert normalized_on != normalize_non_ssm_command(
        [*off, "--fcd-output.max-leader-distance", "999"], prepared_off.run_dir
    )


def _case(tmp_path):
    network = tmp_path / "loop.net.xml"
    network.write_text("<net/>", encoding="utf-8")
    (tmp_path / "net.json").write_text("{}", encoding="utf-8")
    return {
        "case_id": "diag",
        "expected_ttc": "positive",
        "scenario": "scenario_3",
        "network_file": str(network),
        "model": "CACC",
        "vehicle_count": 2,
        "cav_count": 2,
        "assignment_seed": 0,
        "sumo_seed": 102,
        "simulation_end": 10,
        "warmup": 1,
        "step_length": 0.1,
        "detector_frequency": 1,
        "edge_data_frequency": 1,
        "loops": 1,
        "ssm_capture_ttc_threshold_s": 5.0,
        "ssm_capture_drac_threshold_mps2": 3.0,
        "ssm_range_m": 50.0,
        "ssm_trajectories": False,
        "ssm_extratime_s": 5.0,
        "fcd_profile": "1s",
        "fcd_max_leader_distance_m": 4000,
        "with_internal": True,
    }


def _patch_run(monkeypatch, tmp_path, *, returncode=0, ssm_text="<ssmLog/>", emit_ssm=True):
    case = _case(tmp_path)
    monkeypatch.setattr(ssm_reproducer, "load_case", lambda _: case)
    monkeypatch.setattr(
        ssm_reproducer, "collect_provenance", lambda *_: {"git_commit": "abc", "git_dirty": False}
    )

    def prepare(spec, run_dir, _network):
        paths = SimpleNamespace(
            run_dir=run_dir,
            route_path=run_dir / "routes.rou.xml",
            ssm_path=run_dir / "ssm.xml",
            stdout_path=run_dir / "stdout.log",
            stderr_path=run_dir / "stderr.log",
        )
        paths.route_path.write_text("<routes/>", encoding="utf-8")
        return paths

    monkeypatch.setattr(ssm_reproducer, "prepare_run", prepare)
    monkeypatch.setattr(ssm_reproducer, "build_sumo_command", lambda *_: ["fake-sumo"])
    if ssm_text == "not xml":
        monkeypatch.setattr(
            ssm_reproducer,
            "summarize_ssm_evidence",
            lambda *_, **__: (_ for _ in ()).throw(ValueError("invalid SSM XML")),
        )
    else:
        monkeypatch.setattr(
            ssm_reproducer,
            "summarize_ssm_evidence",
            lambda *_, **__: {"ttc_event_count": 1, "control_status": "pass"},
        )

    class Process:
        pid = None

        def __init__(self, *_args, **_kwargs):
            # The output locations are encoded in the open file handles passed by run_case.
            stdout_path = Path(_kwargs["stdout"].name)
            run_dir = stdout_path.parent
            if emit_ssm:
                (run_dir / "ssm.xml").write_text(ssm_text, encoding="utf-8")
            (run_dir / "fcd.xml.gz").write_bytes(b"fcd")
            self.returncode = returncode

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            return self.returncode

    monkeypatch.setattr(ssm_reproducer.subprocess, "Popen", Process)
    return case


def _terminal_status(output_root):
    return json.loads((output_root / "diag" / "attempt-001" / "attempt_status.json").read_text())


def test_nonzero_sumo_closes_failed_attempt_without_report(monkeypatch, tmp_path):
    _patch_run(monkeypatch, tmp_path, returncode=7)
    output_root = tmp_path / "out"

    with pytest.raises(subprocess.CalledProcessError):
        ssm_reproducer.run_case("unused", output_root)

    status = _terminal_status(output_root)
    assert status["status"] == "FAILED"
    assert status["failure_stage"] == "sumo"
    assert status["sumo_return_code"] == 7
    assert status["expected_but_missing"] == []
    assert not (output_root / "diag" / "attempt-001" / "report").exists()


def test_ssm_parse_failure_closes_failed_attempt(monkeypatch, tmp_path):
    _patch_run(monkeypatch, tmp_path, ssm_text="not xml")
    output_root = tmp_path / "out"

    with pytest.raises(ValueError, match="invalid SSM XML"):
        ssm_reproducer.run_case("unused", output_root)

    status = _terminal_status(output_root)
    assert status["status"] == "FAILED"
    assert status["failure_stage"] == "ssm_parse"
    assert status["exception_type"]


def test_report_write_failure_closes_report_failed_attempt(monkeypatch, tmp_path):
    _patch_run(monkeypatch, tmp_path)
    output_root = tmp_path / "out"
    original_write = ssm_reproducer.atomic_write_bytes

    def fail_report(path, data):
        if Path(path).name == "diagnostic_report.json":
            raise OSError("disk full")
        original_write(path, data)

    monkeypatch.setattr(ssm_reproducer, "atomic_write_bytes", fail_report)

    with pytest.raises(OSError, match="disk full"):
        ssm_reproducer.run_case("unused", output_root)

    status = _terminal_status(output_root)
    assert status["status"] == "REPORT_FAILED"
    assert status["failure_stage"] == "report"


def test_timeout_closes_attempt_and_keeps_incremental_rss(monkeypatch, tmp_path):
    _patch_run(monkeypatch, tmp_path)
    output_root = tmp_path / "out"

    class SlowProcess:
        pid = None
        returncode = None

        def __init__(self, *_args, **_kwargs):
            self.returncode = None

        def poll(self):
            return None

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            return self.returncode

    monkeypatch.setattr(ssm_reproducer.subprocess, "Popen", SlowProcess)

    with pytest.raises(TimeoutError):
        ssm_reproducer.run_case("unused", output_root, sample_period_s=0.001, timeout_s=0.001)

    attempt = output_root / "diag" / "attempt-001"
    status = _terminal_status(output_root)
    assert status["status"] == "TIMEOUT"
    assert status["failure_stage"] == "sumo"
    assert (attempt / "raw" / "rss_samples.jsonl").read_bytes()


def test_terminal_status_write_preserves_original_and_status_errors(monkeypatch, tmp_path):
    original_error = ValueError("SSM parse failed")

    def fail_status(*_args):
        raise OSError("status volume unavailable")

    monkeypatch.setattr(ssm_reproducer, "atomic_write_bytes", fail_status)

    with pytest.raises(ValueError, match="SSM parse failed") as caught:
        ssm_reproducer.write_attempt_terminal_status(tmp_path, {}, original_error)

    assert isinstance(caught.value.__cause__, OSError)


def test_prepare_failure_inventories_written_run_spec(monkeypatch, tmp_path):
    _patch_run(monkeypatch, tmp_path)
    output_root = tmp_path / "out"

    def fail_prepare(_spec, _run_dir, _network):
        raise RuntimeError("prepare failed")

    monkeypatch.setattr(ssm_reproducer, "prepare_run", fail_prepare)

    with pytest.raises(RuntimeError, match="prepare failed"):
        ssm_reproducer.run_case("unused", output_root)

    status = _terminal_status(output_root)
    assert status["failure_stage"] == "setup"
    assert "raw/run/run_spec.json" in status["evidence"]
    assert "raw/run/routes.rou.xml" in status["expected_but_missing"]


def test_interrupt_terminates_running_sumo_before_terminal_status(monkeypatch, tmp_path):
    _patch_run(monkeypatch, tmp_path)
    output_root = tmp_path / "out"
    instances = []

    class InterruptingProcess:
        pid = None
        returncode = None

        def __init__(self, *_args, **_kwargs):
            self.returncode = None
            self.terminated = False
            instances.append(self)

        def poll(self):
            raise KeyboardInterrupt

        def terminate(self):
            self.terminated = True
            self.returncode = -15

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            return self.returncode

    monkeypatch.setattr(ssm_reproducer.subprocess, "Popen", InterruptingProcess)

    with pytest.raises(KeyboardInterrupt):
        ssm_reproducer.run_case("unused", output_root)

    assert instances[0].terminated
    assert _terminal_status(output_root)["status"] == "INTERRUPTED"


def test_ssm_off_marks_ssm_as_intentionally_absent_not_missing(monkeypatch, tmp_path):
    _patch_run(monkeypatch, tmp_path, emit_ssm=False)
    output_root = tmp_path / "out"

    report = ssm_reproducer.run_case("unused", output_root, ssm_enabled=False)

    status = _terminal_status(output_root)
    assert status["status"] == "SUCCESS"
    assert status["arm_id"] == "ssm_off"
    assert status["ab_descriptor_sha256"]
    assert "raw/ab_descriptor.json" in status["evidence"]
    assert status["intentionally_absent"] == ["raw/run/ssm.xml"]
    assert "raw/run/ssm.xml" not in status["expected_but_missing"]
    assert report["ssm"] == {"ssm_enabled": False, "status": "ssm_not_collected"}
