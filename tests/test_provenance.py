import hashlib
import json

from scripts.provenance import (
    atomic_write_bytes,
    canonical_json_bytes,
    collect_provenance,
    sha256_file,
)


def test_canonical_json_bytes_are_stable_utf8():
    assert canonical_json_bytes({"z": "中文", "a": [2, 1]}) == (
        b'{"a":[2,1],"z":"\xe4\xb8\xad\xe6\x96\x87"}'
    )


def test_atomic_write_bytes_replaces_existing_content(tmp_path):
    path = tmp_path / "frozen.json"
    path.write_bytes(b"old")

    atomic_write_bytes(path, b"new")

    assert path.read_bytes() == b"new"
    assert not path.with_suffix(".json.tmp").exists()


def test_sha256_file(tmp_path):
    path = tmp_path / "input.bin"
    path.write_bytes(b"reproducible")
    assert sha256_file(path) == hashlib.sha256(b"reproducible").hexdigest()


def test_collect_provenance_hashes_network_and_metadata(tmp_path, monkeypatch):
    network_path = tmp_path / "loop.net.xml"
    metadata_path = tmp_path / "net.json"
    network_path.write_text("<net/>", encoding="utf-8")
    metadata_path.write_text(json.dumps({"schema_version": "1"}), encoding="utf-8")
    monkeypatch.setattr(
        "scripts.provenance._command_output",
        lambda command: "Eclipse SUMO test" if command[0] == "sumo" else "test",
    )

    data = collect_provenance({"scenario_0": str(network_path)}, "sumo", ["batch", "--dry-run"])
    item = data["inputs"]["scenario_0"]
    assert len(item["network_sha256"]) == 64
    assert len(item["metadata_sha256"]) == 64
    assert data["sumo_version"].startswith("Eclipse SUMO")
