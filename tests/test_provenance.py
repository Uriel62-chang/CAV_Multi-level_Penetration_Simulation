import hashlib

from scripts.provenance import collect_provenance, sha256_file


def test_sha256_file(tmp_path):
    path = tmp_path / "input.bin"
    path.write_bytes(b"reproducible")
    assert sha256_file(path) == hashlib.sha256(b"reproducible").hexdigest()


def test_collect_provenance_hashes_network_and_metadata():
    data = collect_provenance(
        {"scenario_0": "net/scenario_0/loop.net.xml"}, "sumo", ["batch", "--dry-run"]
    )
    item = data["inputs"]["scenario_0"]
    assert len(item["network_sha256"]) == 64
    assert len(item["metadata_sha256"]) == 64
    assert data["sumo_version"].startswith("Eclipse SUMO")
