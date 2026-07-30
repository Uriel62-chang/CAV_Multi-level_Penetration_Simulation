"""Run one frozen SUMO SSM diagnostic case and preserve raw evidence separately."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.parsing.ssm import parse_ssm
from scripts.provenance import (
    atomic_write_bytes,
    canonical_json_bytes,
    collect_provenance,
    sha256_file,
)
from scripts.run_spec import PIPELINE_V4_1, RunSpec, build_run_id, write_run_spec
from scripts.simulation.single_run import build_sumo_command_v4_1, prepare_run

_REQUIRED_CASE_KEYS = {
    "case_id",
    "expected_ttc",
    "scenario",
    "network_file",
    "model",
    "vehicle_count",
    "cav_count",
    "assignment_seed",
    "sumo_seed",
    "simulation_end",
    "warmup",
    "step_length",
    "detector_frequency",
    "edge_data_frequency",
    "loops",
    "ssm_capture_ttc_threshold_s",
    "ssm_capture_drac_threshold_mps2",
    "ssm_range_m",
    "ssm_trajectories",
    "ssm_extratime_s",
    "fcd_profile",
    "fcd_max_leader_distance_m",
    "with_internal",
}


def create_attempt_directory(output_root: str | Path, case_id: str) -> Path:
    """Create one exclusive, monotonically numbered diagnostic attempt."""
    case_root = Path(output_root) / case_id
    case_root.mkdir(parents=True, exist_ok=True)
    for number in range(1, 1_000_000):
        attempt = case_root / f"attempt-{number:03d}"
        try:
            attempt.mkdir()
        except FileExistsError:
            continue
        return attempt
    raise RuntimeError(f"no available attempt directory for {case_id}")


def collect_attempt_files(root: Path, expected: list[Path]) -> dict:
    """Return hashes for produced files and an explicit expected-but-missing list."""
    files = {}
    missing = []
    for path in expected:
        if path.is_file():
            files[str(path.relative_to(root))] = {
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        else:
            missing.append(str(path.relative_to(root)))
    return {"files": files, "missing": missing}


def write_attempt_terminal_status(
    attempt: Path, status: dict, original_error: BaseException | None = None
) -> None:
    """Persist terminal status without masking the triggering failure."""
    try:
        atomic_write_bytes(attempt / "attempt_status.json", canonical_json_bytes(status))
    except OSError as write_error:
        if original_error is not None:
            raise original_error from write_error
        raise


class PositiveControlError(RuntimeError):
    """The frozen case ran, but did not demonstrate its declared control."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expected_evidence_paths(root: Path, prepared) -> list[Path]:
    """List the immutable inputs and raw outputs that make an attempt auditable."""
    return [
        root / "raw" / "frozen_case.json",
        prepared.run_dir / "run_spec.json",
        prepared.route_path,
        prepared.ssm_path,
        prepared.run_dir / "fcd.xml.gz",
        prepared.stderr_path,
        prepared.stdout_path,
        root / "raw" / "rss_samples.jsonl",
    ]


def load_case(path: str | Path) -> dict:
    """Load a frozen diagnostic case without selecting replacement treatments."""
    case_path = Path(path)
    try:
        case = json.loads(case_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"diagnostic case unreadable: {case_path}") from exc
    if not isinstance(case, dict):
        raise ValueError("diagnostic case root must be an object")
    missing = sorted(_REQUIRED_CASE_KEYS - case.keys())
    if missing:
        raise ValueError(f"diagnostic case missing keys: {', '.join(missing)}")
    if case["expected_ttc"] not in {"zero", "positive"}:
        raise ValueError("expected_ttc must be 'zero' or 'positive'")
    if case["cav_count"] == case["vehicle_count"] and case["assignment_seed"] != 0:
        raise ValueError("full-CAV diagnostic case requires assignment_seed=0")
    if case["cav_count"] == 0 and case["assignment_seed"] != 0:
        raise ValueError("HV-only diagnostic case requires assignment_seed=0")
    return case


def _rss_kb(pid: int | None) -> int | None:
    if not pid:
        return None
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def summarize_ssm_evidence(ssm_path: str | Path, warmup: float, expected_ttc: str) -> dict:
    """Summarize the raw SSM output and never substitute a failed positive control."""
    path = Path(ssm_path)
    parsed = parse_ssm(str(path), warmup, 3.0, 3.0)
    ttc_events = parsed["ttc_conflict_event_count"]
    control_status = (
        "pass"
        if (expected_ttc == "zero" and ttc_events == 0)
        or (expected_ttc == "positive" and ttc_events > 0)
        else "positive-control failed"
        if expected_ttc == "positive"
        else "zero-event control failed"
    )
    return {
        "ssm_sha256": sha256_file(path) if path.exists() else None,
        "ssm_size_bytes": path.stat().st_size if path.exists() else 0,
        "ssm_raw_record_count": parsed["ssm_raw_record_count"],
        "ttc_event_count": ttc_events,
        "drac_event_count": parsed["drac_conflict_event_count"],
        "control_status": control_status,
    }


def run_case(
    case_path: str | Path,
    output_root: str | Path,
    sumo_command: str = "sumo",
    sample_period_s: float = 1.0,
    timeout_s: float = 7200.0,
) -> dict:
    """Execute exactly one frozen case; raw inputs/outputs and derived report are separate."""
    if sample_period_s <= 0 or timeout_s <= 0:
        raise ValueError("sample_period_s and timeout_s must be positive")
    case = load_case(case_path)
    root = create_attempt_directory(output_root, str(case["case_id"]))
    raw_dir = root / "raw"
    case_sha = hashlib.sha256(canonical_json_bytes(case)).hexdigest()
    started_at = _utc_now()
    started = time.monotonic()
    network_file = str(case["network_file"])
    process = None
    expected: list[Path] = [raw_dir / "frozen_case.json", raw_dir / "rss_samples.jsonl"]
    terminal_status = "FAILED"
    failure_stage = "setup"
    evidence: dict | None = None
    provenance: dict | None = None
    active_error: BaseException | None = None
    sumo_return_code: int | None = None
    rss_peak_kb = 0
    rss_sample_count = 0

    try:
        raw_dir.mkdir(parents=True)
        atomic_write_bytes(raw_dir / "frozen_case.json", canonical_json_bytes(case))
        network_sha = sha256_file(network_file)
        spec = RunSpec(
            scenario=str(case["scenario"]),
            model=str(case["model"]),
            pcav=float(case["cav_count"]) / float(case["vehicle_count"]),
            vehicle_count=int(case["vehicle_count"]),
            seed=int(case["assignment_seed"]),
            run_id=build_run_id(
                str(case["scenario"]),
                str(case["model"]),
                vehicle_count=int(case["vehicle_count"]),
                cav_count=int(case["cav_count"]),
                assignment_seed=int(case["assignment_seed"]),
                sumo_seed=int(case["sumo_seed"]),
            ),
            simulation_end=float(case["simulation_end"]),
            warmup=float(case["warmup"]),
            step_length=float(case["step_length"]),
            detector_frequency=int(case["detector_frequency"]),
            edge_data_frequency=int(case["edge_data_frequency"]),
            loops=int(case["loops"]),
            network_file=network_file,
            pipeline_version=PIPELINE_V4_1,
            schema_version="2",
            config_sha256=case_sha,
            network_sha256=network_sha,
            experiment_id=f"ssm-reproducer-{case_sha[:12]}-{network_sha[:12]}",
            sumo_seed=int(case["sumo_seed"]),
            cav_count=int(case["cav_count"]),
            requested_pcav=None,
            ssm_capture_ttc_threshold_s=float(case["ssm_capture_ttc_threshold_s"]),
            ssm_capture_drac_threshold_mps2=float(case["ssm_capture_drac_threshold_mps2"]),
            ssm_range_m=float(case["ssm_range_m"]),
            ssm_trajectories=bool(case["ssm_trajectories"]),
            ssm_extratime_s=float(case["ssm_extratime_s"]),
            fcd_profile=case["fcd_profile"],
            fcd_max_leader_distance_m=float(case["fcd_max_leader_distance_m"]),
            with_internal=bool(case["with_internal"]),
        )
        run_dir = raw_dir / "run"
        run_dir.mkdir()
        write_run_spec(spec, run_dir)
        prepared = prepare_run(spec, run_dir, network_file)
        expected = _expected_evidence_paths(root, prepared)
        command = build_sumo_command_v4_1(prepared, network_file, spec, sumo_command)
        provenance = collect_provenance({case["scenario"]: network_file}, sumo_command, command)
        atomic_write_bytes(
            root / "attempt_status.json",
            canonical_json_bytes(
                {
                    "status": "RUNNING",
                    "attempt_id": root.name,
                    "case_sha256": case_sha,
                    "git_commit": provenance.get("git_commit"),
                    "git_dirty": provenance.get("git_dirty"),
                    "started_at": started_at,
                    "provenance": provenance,
                }
            ),
        )

        failure_stage = "sumo"
        rss_path = raw_dir / "rss_samples.jsonl"
        with (
            prepared.stdout_path.open("wb") as stdout,
            prepared.stderr_path.open("wb") as stderr,
            rss_path.open("wb") as rss_stream,
        ):
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
            while process.poll() is None:
                sample = {"elapsed_s": time.monotonic() - started, "rss_kb": _rss_kb(process.pid)}
                rss_stream.write(canonical_json_bytes(sample) + b"\n")
                rss_stream.flush()
                rss_sample_count += 1
                rss_peak_kb = max(rss_peak_kb, sample["rss_kb"] or 0)
                if time.monotonic() - started >= timeout_s:
                    process.terminate()
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=30)
                    raise TimeoutError(f"SUMO exceeded diagnostic timeout of {timeout_s}s")
                time.sleep(sample_period_s)
        sumo_return_code = process.returncode
        if sumo_return_code != 0:
            raise subprocess.CalledProcessError(sumo_return_code, command)

        evidence_files = collect_attempt_files(root, expected)
        if evidence_files["missing"]:
            failure_stage = "evidence"
            raise FileNotFoundError(
                "expected diagnostic evidence missing: " + ", ".join(evidence_files["missing"])
            )
        failure_stage = "ssm_parse"
        evidence = summarize_ssm_evidence(prepared.ssm_path, spec.warmup, str(case["expected_ttc"]))
        if evidence["control_status"] != "pass":
            failure_stage = "positive_control"
            raise PositiveControlError(evidence["control_status"])

        report = {
            "case_id": case["case_id"],
            "case_sha256": case_sha,
            "network_sha256": network_sha,
            "command": command,
            "sample_period_s": sample_period_s,
            "wall_time_s": time.monotonic() - started,
            "return_code": sumo_return_code,
            "rss_peak_kb": rss_peak_kb,
            "rss_sample_count": rss_sample_count,
            "ssm": evidence,
            "provenance": provenance,
        }
        failure_stage = "report"
        report_dir = root / "report"
        report_dir.mkdir()
        atomic_write_bytes(report_dir / "diagnostic_report.json", canonical_json_bytes(report))
        terminal_status = "SUCCESS"
        failure_stage = None
        return report
    except KeyboardInterrupt as exc:
        terminal_status = "INTERRUPTED"
        active_error = exc
        raise
    except TimeoutError as exc:
        terminal_status = "TIMEOUT"
        active_error = exc
        raise
    except BaseException as exc:
        terminal_status = "REPORT_FAILED" if failure_stage == "report" else "FAILED"
        active_error = exc
        raise
    finally:
        if process is not None:
            sumo_return_code = process.returncode
        inventory = collect_attempt_files(root, expected)
        terminal = {
            "status": terminal_status,
            "attempt_id": root.name,
            "case_sha256": case_sha,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "wall_time_s": time.monotonic() - started,
            "failure_stage": failure_stage,
            "exception_type": type(active_error).__name__ if active_error else None,
            "exception_message": str(active_error) if active_error else None,
            "sumo_return_code": sumo_return_code,
            "rss_peak_kb": rss_peak_kb,
            "rss_sample_count": rss_sample_count,
            "evidence": inventory["files"],
            "expected_but_missing": inventory["missing"],
            "ssm": evidence,
            "provenance": provenance,
        }
        try:
            write_attempt_terminal_status(root, terminal, active_error)
        except OSError as status_error:
            if active_error is not None:
                raise active_error from status_error
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one frozen SUMO SSM diagnostic case")
    parser.add_argument("--case", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--sumo", default="sumo")
    parser.add_argument("--sample-period-s", type=float, default=1.0)
    parser.add_argument("--timeout-s", type=float, default=7200.0)
    args = parser.parse_args()
    report = run_case(args.case, args.output_root, args.sumo, args.sample_period_s, args.timeout_s)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
