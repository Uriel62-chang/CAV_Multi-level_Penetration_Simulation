import pytest

from scripts.experiment_audit import audit_experiment_config
from scripts.experiment_config import load_experiment_config


def test_v040_grid_audit_freezes_known_experiment_limitations():
    audit = audit_experiment_config(load_experiment_config("configs/v0.4.0.json"))

    assert audit.planned_run_count == 10080
    assert audit.requested_realized_mismatch_runs == 2400
    assert audit.duplicate_penetration_treatment_runs == 400
    assert audit.endpoint_run_count == 960
    assert audit.endpoint_unique_assignment_treatments == 192
    assert audit.endpoint_assignment_redundant_runs == 768

    veh10 = next(item for item in audit.by_vehicle_count if item.vehicle_count == 10)
    assert veh10.requested_level_count == 21
    assert veh10.realized_composition_count == 11
    assert veh10.mismatched_level_count == 10
    assert veh10.duplicate_treatment_level_count == 10
    assert veh10.max_absolute_pcav_error == pytest.approx(0.05)
