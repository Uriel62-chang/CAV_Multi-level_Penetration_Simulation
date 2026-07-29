import asyncio
import json

import scripts.simulation.batch_run as batch_run
from scripts.run_spec import RunSpec


def _spec() -> RunSpec:
    return RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=2,
        seed=1,
        run_id="state-test",
        simulation_end=10,
        warmup=0,
        loops=2,
        network_file="net/scenario_0/loop.net.xml",
        config_sha256="c" * 64,
        network_sha256="n" * 64,
        experiment_id="state-machine-test",
    )


def _run(tmp_path, **overrides):
    spec = _spec()
    values = {
        "spec": spec,
        "output_root": tmp_path,
        "network_file": spec.network_file,
        "sumo_command": "sumo",
        "pipeline_version": spec.pipeline_version,
        "timeout_s": None,
        "resume": False,
    }
    values.update(overrides)
    result = asyncio.run(batch_run.run_sumo_process(**values))
    status = json.loads(
        (tmp_path / spec.run_id / "simulation_status.json").read_text(encoding="utf-8")
    )
    return result, status


def test_prepare_failure_writes_failed_terminal_status(monkeypatch, tmp_path):
    def fail_prepare(*args, **kwargs):
        raise ValueError("bad preparation")

    monkeypatch.setattr(batch_run, "prepare_run", fail_prepare)
    result, status = _run(tmp_path)

    assert result.status == "FAILED"
    assert status["status"] == "FAILED"
    assert status["exception_type"] == "ValueError"
    assert "bad preparation" in status["traceback"]


def test_missing_sumo_writes_failed_terminal_status(monkeypatch, tmp_path):
    async def missing_binary(*args, **kwargs):
        raise FileNotFoundError("sumo missing")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", missing_binary)
    result, status = _run(tmp_path)

    assert result.status == "FAILED"
    assert status["exception_type"] == "FileNotFoundError"
    assert status["run_spec_sha256"] == _spec().sha256()


def test_nonzero_return_code_writes_failed_terminal_status(monkeypatch, tmp_path):
    class Process:
        returncode = 2
        pid = None

        async def wait(self):
            return 2

    async def create_process(*args, **kwargs):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    result, status = _run(tmp_path)

    assert result.status == "FAILED"
    assert status["status"] == "FAILED"
    assert status["return_code"] == 2
    assert status["sumo_command"]
    assert "sumo_peak_rss_kb" in status


def test_zero_return_with_missing_outputs_is_failed(monkeypatch, tmp_path):
    class Process:
        returncode = 0
        pid = None

        async def wait(self):
            return 0

    async def create_process(*args, **kwargs):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    result, status = _run(tmp_path)

    assert result.status == "FAILED"
    assert "missing or empty outputs" in status["error_message"]
    assert status["sumo_peak_rss_kb"] == 0


def test_timeout_writes_timeout_terminal_status(monkeypatch, tmp_path):
    class Process:
        terminated = False
        pid = None

        async def wait(self):
            if not self.terminated:
                await asyncio.sleep(60)
            return -15

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.terminated = True

    async def create_process(*args, **kwargs):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    result, status = _run(tmp_path, timeout_s=0.001)

    assert result.status == "TIMEOUT"
    assert status["status"] == "TIMEOUT"
    assert status["return_code"] is None
    assert status["sumo_command"]


def test_shutdown_before_start_writes_cancelled_terminal_status(tmp_path):
    batch_run._shutting_down = True
    try:
        result, status = _run(tmp_path)
    finally:
        batch_run._shutting_down = False

    assert result.status == "CANCELLED"
    assert status["status"] == "CANCELLED"
    assert status["error_message"] == "Interrupted before start"
    assert status["sumo_peak_rss_kb"] == 0
