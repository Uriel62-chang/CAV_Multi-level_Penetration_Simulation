import json

from scripts.simulation.network_generator import build_network, generate_polygon_loop


def test_generated_network_metadata_uses_current_schema(tmp_path):
    scenario_dir = tmp_path / "scenario_test"
    metadata = generate_polygon_loop(
        str(scenario_dir),
        num_sides=8,
        radius=100,
        num_lanes=2,
        speed=20,
    )
    persisted = json.loads((scenario_dir / "net.json").read_text(encoding="utf-8"))

    assert persisted == metadata
    assert metadata["schema_version"] == "1"
    assert metadata["route_edge_ids"] == metadata["edge_ids"]
    assert metadata["detector_edge_id"] == "e0"
    assert metadata["bottleneck_edge_ids"] == []
    assert metadata["edge_lane_counts"] == {"default": 2, "overrides": {}}
    assert metadata["legal_initial_lanes"] == {
        "default": [0, 1],
        "overrides": {},
    }


def test_build_network_invokes_netconvert_with_tracked_sources(tmp_path, monkeypatch):
    scenario_dir = tmp_path / "scenario_test"
    scenario_dir.mkdir()
    (scenario_dir / "nodes.nod.xml").write_text("<nodes/>", encoding="utf-8")
    (scenario_dir / "edges.edg.xml").write_text("<edges/>", encoding="utf-8")
    observed = {}

    def fake_run(command, check):
        observed["command"] = command
        observed["check"] = check

    monkeypatch.setattr("scripts.simulation.network_generator.subprocess.run", fake_run)
    output = build_network(scenario_dir, "test-netconvert")

    assert output == scenario_dir / "loop.net.xml"
    assert observed == {
        "command": [
            "test-netconvert",
            "--node-files",
            str(scenario_dir / "nodes.nod.xml"),
            "--edge-files",
            str(scenario_dir / "edges.edg.xml"),
            "--output-file",
            str(output),
        ],
        "check": True,
    }
