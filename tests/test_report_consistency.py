from pathlib import Path

import pandas as pd


def test_report_ttc_scenario_summaries_match_published_aggregate():
    frame = pd.read_csv("results/aggregated_results.csv")
    report = Path("docs/report.md").read_text(encoding="utf-8")
    expected = frame.groupby("scenario")["ttc_mean"].sum()

    for scenario, value in expected.items():
        short = scenario.replace("scenario_", "s")
        rendered = "0" if value == 0 else f"{value:,.1f}"
        assert f"| {short} | {rendered} |" in report
