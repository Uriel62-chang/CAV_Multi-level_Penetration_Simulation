"""v0.4.1.post1 acceptance freeze and resume closure probes."""

import json

import pytest

from scripts.simulation.batch_run import prepare_post1_frozen_inputs


def test_post1_freeze_requires_acceptance_for_v4_1(tmp_path):
    with pytest.raises(ValueError, match="--acceptance is required"):
        prepare_post1_frozen_inputs(tmp_path, "v0.4.1", {"models": ["IDM"]}, None, False)


def test_post1_resume_requires_matching_manifest_and_frozen_pair(tmp_path):
    acceptance = tmp_path / "acceptance.json"
    acceptance.write_text('{"budget":1}', encoding="utf-8")
    config = {"models": ["IDM"]}

    hashes = prepare_post1_frozen_inputs(tmp_path, "v0.4.1", config, acceptance, False)
    (tmp_path / "manifest.json").write_text(json.dumps({"frozen_inputs": hashes}), encoding="utf-8")
    assert prepare_post1_frozen_inputs(tmp_path, "v0.4.1", config, acceptance, True) == hashes

    (tmp_path / "manifest.json").write_text(
        json.dumps({"frozen_inputs": {**hashes, "acceptance_sha256": "x" * 64}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="manifest frozen_inputs mismatch"):
        prepare_post1_frozen_inputs(tmp_path, "v0.4.1", config, acceptance, True)


def test_post1_nonresume_refuses_to_overwrite_existing_manifest(tmp_path):
    acceptance = tmp_path / "acceptance.json"
    acceptance.write_text('{"budget":1}', encoding="utf-8")
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="output manifest already exists"):
        prepare_post1_frozen_inputs(tmp_path, "v0.4.1", {"models": ["IDM"]}, acceptance, False)
