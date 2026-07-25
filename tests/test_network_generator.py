import json

from scripts.simulation.network_generator import generate_polygon_loop


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
