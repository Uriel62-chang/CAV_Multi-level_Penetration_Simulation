"""v0.4.2 P0-2 回归测试：cav_count 权威 + realized_pcav 绘图横轴。"""

import pandas as pd
import pytest

from scripts.results.aggregate import aggregate
from scripts.results.visualization import _penetration_column
from scripts.simulation.flow_generator import generate_flow


def test_generate_flow_cav_count_is_authoritative(tmp_path):
    """传入 cav_count 时不再 round(cav_ratio)，count 为唯一权威。"""
    out = tmp_path / "routes.rou.xml"
    # cav_ratio=0.5 会 round 出 5，但显式 cav_count=3 必须生效
    type_map = generate_flow(
        vehicle_count=10,
        cav_ratio=0.5,
        loops=2,
        seed=1,
        output_path=str(out),
        cav_count=3,
    )
    cavs = [v for v in type_map.values() if v == "CAV"]
    assert len(cavs) == 3
    assert out.exists()


def test_generate_flow_cav_count_out_of_range(tmp_path):
    with pytest.raises(ValueError):
        generate_flow(
            vehicle_count=10,
            cav_ratio=0.5,
            loops=2,
            seed=1,
            output_path=str(tmp_path / "x.xml"),
            cav_count=11,
        )


def test_penetration_column_prefers_realized():
    df = pd.DataFrame({"realized_pcav": [0.5], "requested_pcav": [None]})
    assert _penetration_column(df) == "realized_pcav"


def test_penetration_column_requested_alone_raises():
    """纯净分支：requested_pcav 不再是渗透率列（legacy requested-grid 已删）→ fail-closed。"""
    import pytest

    with pytest.raises(ValueError):
        _penetration_column(pd.DataFrame({"requested_pcav": [0.5]}))


def test_penetration_column_oldest_fallback():
    df = pd.DataFrame({"pCAV": [0.5]})
    assert _penetration_column(df) == "pCAV"


def test_penetration_column_missing_raises():
    with pytest.raises(ValueError):
        _penetration_column(pd.DataFrame({"flow_mean": [1.0]}))


def test_aggregate_schema2_uses_realized_pcav(tmp_path):
    """schema=2 聚合：pCAV = cav_count/vehN，输出无 requested_pcav 契约列。"""
    df = pd.DataFrame(
        {
            "scenario": ["s0"] * 4,
            "model": ["IDM"] * 4,
            "realized_pcav": [0.5] * 4,
            "cav_count": [5] * 4,
            "hv_count": [5] * 4,
            "vehN": [10] * 4,
            "assignment_seed": [0, 1, 2, 3],
            "sumo_seed": [101] * 4,
            "run_id": [f"r{i}" for i in range(4)],
            "mean_flow_veh_h": [100.0, 110.0, 90.0, 120.0],
            "data_quality": ["ok"] * 4,
        }
    )
    in_csv = tmp_path / "in.csv"
    out_csv = tmp_path / "out.csv"
    df.to_csv(in_csv, index=False)
    manifest = {
        "treatments": [{"vehicle_count": 10, "cav_counts": [5], "assignment_seeds": [0, 1, 2, 3]}],
        "sumo_seeds": [101],
        "results": [{"run_id": f"r{i}"} for i in range(4)],
    }
    out = aggregate(in_csv, out_csv, "2", manifest=manifest)
    row = out[out["vehN"] == 10].iloc[0]
    assert row["pCAV"] == pytest.approx(0.5)
    assert "requested_pcav" not in out.columns
    assert row["realized_pcav"] == pytest.approx(0.5)
