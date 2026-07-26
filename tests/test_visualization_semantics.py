import pandas as pd

from scripts.results.visualization import _ttc_metric_column


def test_safety_chart_prefers_explicit_spatial_scope_column():
    explicit = "whole_network_ttc_events_per_1000_non_internal_edge_veh_km_mean"
    frame = pd.DataFrame(columns=["ttc_per_k_mean", explicit])

    assert _ttc_metric_column(frame) == explicit
