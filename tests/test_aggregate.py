from pathlib import Path

import pandas as pd

from scripts.results.aggregate import aggregate


def test_aggregate_emits_unique_metric_count_columns(tmp_path: Path):
    input_path = tmp_path / "run_level.csv"
    output_path = tmp_path / "aggregated.csv"
    pd.DataFrame(
        [
            {
                "scenario": "scenario_0",
                "model": "IDM",
                "pCAV": 0.5,
                "requested_pcav": 0.5,
                "vehN": 20,
                "seed": 1,
                "data_quality": "ok",
                "mean_flow_veh_h": 100.0,
                "max_flow_veh_h": 120.0,
                "ttc_events_per_1000_veh_km": 10.0,
            },
            {
                "scenario": "scenario_0",
                "model": "IDM",
                "pCAV": 0.5,
                "requested_pcav": 0.5,
                "vehN": 20,
                "seed": 2,
                "data_quality": "ok",
                "mean_flow_veh_h": 110.0,
                "max_flow_veh_h": 130.0,
                "ttc_events_per_1000_veh_km": 30.0,
            },
        ]
    ).to_csv(input_path, index=False)

    result = aggregate(input_path, output_path, "1")

    assert result.columns.is_unique
    assert result.loc[0, "n_valid"] == 2
    assert result.loc[0, "flow_valid_run_count"] == 2
    assert result.loc[0, "assignment_seed_run_count"] == 2
    assert result.loc[0, "independent_random_replication_count"] == 0
    assert result.loc[0, "requested_pcav"] == 0.5
    assert result.loc[0, "realized_pcav"] == 0.5
    assert result.loc[0, "max_flow_count"] == 2
    assert result.loc[0, "ttc_per_k_mean"] == 20.0
    assert "n_valid.1" not in pd.read_csv(output_path).columns
