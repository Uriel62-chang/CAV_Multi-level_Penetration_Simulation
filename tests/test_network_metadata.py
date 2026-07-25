import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts.simulation.single_run import load_network_meta

SCENARIOS = tuple(f"scenario_{index}" for index in range(4))


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_network_metadata_matches_compiled_network(scenario):
    network_path = Path("net") / scenario / "loop.net.xml"
    metadata = load_network_meta(str(network_path))
    root = ET.parse(network_path).getroot()

    compiled_edges = {
        edge.get("id"): len(edge.findall("lane"))
        for edge in root.findall("edge")
        if edge.get("function") is None
    }
    assert metadata["scenario"] == scenario
    assert metadata["route_edge_ids"] == metadata["edge_ids"]
    assert set(metadata["edge_ids"]) == set(compiled_edges)
    assert metadata["detector_edge_id"] in compiled_edges

    lane_counts = metadata["edge_lane_counts"]
    legal_lanes = metadata["legal_initial_lanes"]
    for edge_id in metadata["edge_ids"]:
        expected_lanes = lane_counts["overrides"].get(edge_id, lane_counts["default"])
        expected_legal = legal_lanes["overrides"].get(edge_id, legal_lanes["default"])
        assert compiled_edges[edge_id] == expected_lanes
        assert expected_legal == list(range(expected_lanes))

    for edge_id in metadata["bottleneck_edge_ids"]:
        assert lane_counts["overrides"][edge_id] == 1


def test_all_network_metadata_use_supported_schema():
    for scenario in SCENARIOS:
        path = Path("net") / scenario / "net.json"
        metadata = json.loads(path.read_text(encoding="utf-8"))
        assert metadata["schema_version"] == "1"
