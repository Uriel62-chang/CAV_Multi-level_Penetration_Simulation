"""Lightweight no-pytest regression runner; not the complete release test suite."""

import sys
import traceback
from pathlib import Path

# 允许使用未安装 editable package 的系统 Python 从仓库根目录直接执行。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import test functions
from test_edge_emissions_parser import (
    test_empty_file_returns_zero as ee_empty,
)
from test_edge_emissions_parser import (
    test_idempotent as ee_idempotent,
)
from test_edge_emissions_parser import (
    test_malformed_xml_returns_nan as ee_malformed,
)
from test_edge_emissions_parser import (
    test_minimal_emissions_units,
    test_missing_fields_default_to_zero_contribution,
)
from test_edge_emissions_parser import (
    test_missing_file_returns_nan as ee_missing,
)
from test_edge_emissions_parser import (
    test_warmup_filters_complete_intervals as ee_warmup,
)
from test_edge_performance_parser import (
    test_empty_file_returns_zero as ep_empty,
)
from test_edge_performance_parser import (
    test_idempotent as ep_idempotent,
)
from test_edge_performance_parser import (
    test_malformed_xml_returns_nan as ep_malformed,
)
from test_edge_performance_parser import (
    test_minimal_veh_km_calculation,
    test_missing_fields,
)
from test_edge_performance_parser import (
    test_missing_file_returns_nan as ep_missing,
)
from test_edge_performance_parser import (
    test_warmup_filters_complete_intervals as ep_warmup,
)
from test_ssm_parser import (
    test_empty_file_returns_zero_events,
    test_malformed_xml_returns_nan,
    test_minimal_parses_conflicts,
    test_mirror_deduplication,
    test_missing_fields_return_nan_not_zero,
    test_missing_file_returns_nan_counts,
    test_warmup_filtering,
    test_warmup_uses_metric_extreme_time,
)
from test_ssm_parser import (
    test_idempotent as ssm_idempotent,
)
from test_vehroute_parser import (
    test_empty_file_returns_zero_laps,
    test_insufficient_exit_times,
    test_minimal_lap_times,
    test_missing_exit_times_returns_zero_laps,
    test_missing_file_returns_nan,
    test_p95_uses_documented_higher_method,
    test_sim_end_filters_laps,
    test_warmup_filters_laps,
)
from test_vehroute_parser import (
    test_idempotent as vr_idempotent,
)
from test_vehroute_parser import (
    test_malformed_xml_returns_nan as vr_malformed,
)
from test_writer_quality import test_writer_complete_requires_valid_rows

all_tests = [
    # SSM
    ("test_ssm_parser", "test_minimal_parses_conflicts", test_minimal_parses_conflicts),
    ("test_ssm_parser", "test_mirror_deduplication", test_mirror_deduplication),
    ("test_ssm_parser", "test_warmup_filtering", test_warmup_filtering),
    (
        "test_ssm_parser",
        "test_warmup_uses_metric_extreme_time",
        test_warmup_uses_metric_extreme_time,
    ),
    ("test_ssm_parser", "test_empty_file_returns_zero_events", test_empty_file_returns_zero_events),
    (
        "test_ssm_parser",
        "test_missing_file_returns_nan_counts",
        test_missing_file_returns_nan_counts,
    ),
    (
        "test_ssm_parser",
        "test_missing_fields_return_nan_not_zero",
        test_missing_fields_return_nan_not_zero,
    ),
    ("test_ssm_parser", "test_malformed_xml_returns_nan", test_malformed_xml_returns_nan),
    ("test_ssm_parser", "test_idempotent", ssm_idempotent),
    # Vehroute
    ("test_vehroute_parser", "test_minimal_lap_times", test_minimal_lap_times),
    (
        "test_vehroute_parser",
        "test_p95_uses_documented_higher_method",
        test_p95_uses_documented_higher_method,
    ),
    ("test_vehroute_parser", "test_warmup_filters_laps", test_warmup_filters_laps),
    ("test_vehroute_parser", "test_sim_end_filters_laps", test_sim_end_filters_laps),
    (
        "test_vehroute_parser",
        "test_empty_file_returns_zero_laps",
        test_empty_file_returns_zero_laps,
    ),
    ("test_vehroute_parser", "test_missing_file_returns_nan", test_missing_file_returns_nan),
    (
        "test_vehroute_parser",
        "test_missing_exit_times_returns_zero_laps",
        test_missing_exit_times_returns_zero_laps,
    ),
    ("test_vehroute_parser", "test_insufficient_exit_times", test_insufficient_exit_times),
    ("test_vehroute_parser", "test_malformed_xml_returns_nan", vr_malformed),
    ("test_vehroute_parser", "test_idempotent", vr_idempotent),
    # Edge Performance
    (
        "test_edge_performance_parser",
        "test_minimal_veh_km_calculation",
        test_minimal_veh_km_calculation,
    ),
    ("test_edge_performance_parser", "test_empty_file_returns_zero", ep_empty),
    ("test_edge_performance_parser", "test_missing_file_returns_nan", ep_missing),
    ("test_edge_performance_parser", "test_missing_fields", test_missing_fields),
    ("test_edge_performance_parser", "test_malformed_xml_returns_nan", ep_malformed),
    ("test_edge_performance_parser", "test_idempotent", ep_idempotent),
    ("test_edge_performance_parser", "test_warmup_filters_complete_intervals", ep_warmup),
    # Edge Emissions
    ("test_edge_emissions_parser", "test_minimal_emissions_units", test_minimal_emissions_units),
    ("test_edge_emissions_parser", "test_empty_file_returns_zero", ee_empty),
    ("test_edge_emissions_parser", "test_missing_file_returns_nan", ee_missing),
    (
        "test_edge_emissions_parser",
        "test_missing_fields_default_to_zero_contribution",
        test_missing_fields_default_to_zero_contribution,
    ),
    ("test_edge_emissions_parser", "test_malformed_xml_returns_nan", ee_malformed),
    ("test_edge_emissions_parser", "test_idempotent", ee_idempotent),
    ("test_edge_emissions_parser", "test_warmup_filters_complete_intervals", ee_warmup),
    (
        "test_writer_quality",
        "test_writer_complete_requires_valid_rows",
        test_writer_complete_requires_valid_rows,
    ),
]

passed = 0
failed = 0

print("[LIGHTWEIGHT] Running 34 parser/writer regressions; full release gate is pytest -q.\n")

for module, name, func in all_tests:
    try:
        func()
        print(f"  PASS {module}::{name}")
        passed += 1
    except Exception:
        print(f"  FAIL {module}::{name}")
        traceback.print_exc()
        print()
        failed += 1

print(f"\n{'=' * 50}")
print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
if failed:
    sys.exit(1)
