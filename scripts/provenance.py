"""实验来源信息与内容哈希工具。"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path


def canonical_json_bytes(data: object) -> bytes:
    """Return canonical UTF-8 JSON bytes suitable for content hashing."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def atomic_write_bytes(path: str | Path, data: bytes) -> None:
    """Atomically replace *path* after flushing the temporary file to disk."""
    output_path = Path(path)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with temp_path.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp_path, output_path)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _command_output(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0] if output else "unavailable"


def _git_dirty() -> bool | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def collect_provenance(
    network_files: dict[str, str],
    sumo_command: str,
    argv: Iterable[str],
) -> dict:
    """收集只读的代码、环境、可执行文件和输入文件来源信息。"""
    sumo_path = shutil.which(sumo_command)
    git_commit = _command_output(["git", "rev-parse", "HEAD"])
    inputs = {}
    for scenario, network_file in sorted(network_files.items()):
        net_path = Path(network_file)
        meta_path = net_path.with_name("net.json")
        inputs[scenario] = {
            "network_file": str(net_path),
            "network_sha256": sha256_file(net_path),
            "metadata_file": str(meta_path),
            "metadata_sha256": sha256_file(meta_path),
        }
    return {
        "git_commit": git_commit,
        "git_dirty": _git_dirty(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "python_packages": _installed_package_versions(),
        "operating_system": platform.platform(),
        "architecture": platform.machine(),
        "sumo_version": _command_output([sumo_command, "--version"]),
        "sumo_executable": sumo_path or "unavailable",
        "netconvert_version": _command_output(["netconvert", "--version"]),
        "timezone": datetime.now().astimezone().tzname(),
        "launch_command": list(argv),
        "working_directory": os.getcwd(),
        "inputs": inputs,
    }


def _installed_package_versions() -> dict[str, str]:
    """返回运行时关键 Python 依赖的版本快照。"""
    import importlib.metadata

    packages = ["pandas", "numpy", "matplotlib"]
    versions: dict[str, str] = {}
    for name in packages:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not installed"
    return versions
