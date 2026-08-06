"""v0.4.2 P0-8 回归测试：逐 lap delay 与自由流 artifact 覆盖。"""

import json

import pytest

from scripts.parsing.metrics import SubgroupPrimitives, compute_core_summary
from scripts.run_spec import PIPELINE_V4_2, RunSpec


def _spec(model="IDM") -> RunSpec:
    return RunSpec(
        scenario="scenario_2",
        model=model,
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="s2_IDM_v010_c005_as01_ss101",
        pipeline_version=PIPELINE_V4_2,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
    )


def _primitives(hv_mean=70.0, cav_mean=65.0, n_hv=10, n_cav=10, hv_laps=None, cav_laps=None):
    return SubgroupPrimitives(
        detector={"all": {}},
        ssm={"all": {}},
        lanechange={"all": {}},
        edge_perf={"all": {"non_internal_edge_vehicle_km": 100.0, "total_vehicle_km": 120.0}},
        edge_emis={"all": {}},
        vehroute={
            "all": {"mean_lap_time_s": (hv_mean * n_hv + cav_mean * n_cav) / (n_hv + n_cav)},
            "HV": {
                "mean_lap_time_s": hv_mean,
                "completed_lap_count": n_hv,
                "lap_times_s": hv_laps if hv_laps is not None else [hv_mean] * n_hv,
            },
            "CAV": {
                "mean_lap_time_s": cav_mean,
                "completed_lap_count": n_cav,
                "lap_times_s": cav_laps if cav_laps is not None else [cav_mean] * n_cav,
            },
        },
        emerg_brake={"all": {}},
        fcd=None,
    )


def test_delay_per_vehicle_type_weighted():
    """HV lap → HV ref；CAV lap → IDM ref；加权汇总（runner 真实返回键结构）。"""
    refs = {"HV": 60.0, "IDM": 58.0}
    prim = _primitives(hv_mean=70.0, cav_mean=65.0, n_hv=10, n_cav=10)
    s = compute_core_summary(prim, _spec("IDM"), refs)
    expected = ((70.0 - 60.0) * 10 + (65.0 - 58.0) * 10) / 20
    assert s["mean_lap_delay_s"] == pytest.approx(expected)


def test_delay_cav_uses_model_specific_ref():
    """CAV delay 用 CACC 参考（非 HV/IDM）。"""
    refs = {"HV": 60.0, "CACC": 57.0}
    prim = _primitives(hv_mean=70.0, cav_mean=65.0, n_hv=10, n_cav=10)
    s = compute_core_summary(prim, _spec("CACC"), refs)
    expected = ((70.0 - 60.0) * 10 + (65.0 - 57.0) * 10) / 20
    assert s["mean_lap_delay_s"] == pytest.approx(expected)


def test_delay_all_hv_no_cav():
    refs = {"HV": 60.0, "IDM": 58.0}
    prim = _primitives(hv_mean=70.0, cav_mean=0.0, n_hv=20, n_cav=0)
    s = compute_core_summary(prim, _spec("IDM"), refs)
    assert s["mean_lap_delay_s"] == pytest.approx(10.0)


def test_delay_runner_key_structure_mixed():
    """P0-2 回归：runner 返回键为 {"HV", spec.model}，CAV delay 不得被静默丢弃。

    Reviewer 复算场景：hv_mean=70/ref 60（+10）、cav_mean=65/ref 58（+7），
    等权混合 → 8.5 s；旧实现只取 HV 项得 5.0 s。
    """
    refs = {"HV": 60.0, "IDM": 58.0}  # runner._load_free_flow_references 返回结构
    prim = _primitives(hv_mean=70.0, cav_mean=65.0, n_hv=10, n_cav=10)
    s = compute_core_summary(prim, _spec("IDM"), refs)
    assert s["mean_lap_delay_s"] == pytest.approx(8.5)


def test_p95_delay_uses_pooled_lap_samples_not_weighted_subgroup_p95():
    """P0-2（新审阅修订 1）：p95 必须基于逐 lap 转换后的 pooled 样本重求分位数。

    混合分布设计：HV 20 圈 = 19×60 + 1×100；CAV 20 圈 = 19×55 + 1×70；
    ref 均为 50。pooled delay 样本 = [5×19, 10×19, 20, 50]，n=40：
    higher p95 = sorted[ceil(39*0.95)] = sorted[38] = 20。
    加权 subgroup p95 = (50 + 20) / 2 = 35 ≠ 20 —— 若用近似算法必然失败。
    """
    refs = {"HV": 50.0, "CACC": 50.0}
    prim = _primitives(
        hv_laps=[60.0] * 19 + [100.0],
        cav_laps=[55.0] * 19 + [70.0],
    )
    s = compute_core_summary(prim, _spec("CACC"), refs)
    assert s["p95_lap_delay_s"] == pytest.approx(20.0)
    weighted_subgroup_p95 = (50.0 + 20.0) / 2  # 被禁止的近似
    assert abs(s["p95_lap_delay_s"] - weighted_subgroup_p95) > 5.0


def test_p95_delay_all_cav_uses_cav_ref_not_hv_ref():
    """P0-2：全 CAV run 的 p95 delay 必须用 CAV_model ref。

    对应正式数据样例：s0_CACC_v090_c090_as00_ss101 lap p95=116.4，
    HV ref=111.8 / CACC ref=91.6 → 正确 24.8 s，而非旧的 4.6 s。
    """
    refs = {"HV": 111.8, "CACC": 91.6}
    prim = _primitives(
        n_hv=0,
        n_cav=90,
        cav_laps=[116.4] * 90,
    )
    s = compute_core_summary(prim, _spec("CACC"), refs)
    assert s["p95_lap_delay_s"] == pytest.approx(24.8)
    assert s["mean_lap_delay_s"] == pytest.approx(24.8)


def test_free_flow_artifact_covers_all_scenarios():
    with open("artifacts/free_flow/v0.4.1-pilot-ff-1/free_flow_references.json") as f:
        art = json.load(f)
    assert set(art["results"].keys()) == {
        "scenario_0",
        "scenario_1",
        "scenario_2",
        "scenario_3",
    }
    for _sc, info in art["results"].items():
        refs = info["references"]
        assert "HV" in refs
        assert "CAV_IDM" in refs
        assert "CAV_CACC" in refs


def test_run_free_flow_passes_cav_count_to_generate_flow(monkeypatch, tmp_path):
    """审查 P1-1（第九轮）：_run_free_flow 必须向 generate_flow 显式传 cav_count。

    纯净分支 flow_generator 对 cav_count=None 直接 raise（无 round fallback），
    缺失时 free_flow 参考测量工具完全不可用（无法再生 artifact）。
    """
    import types
    from pathlib import Path

    import scripts.analysis.free_flow as ff

    captured = {}

    def fake_generate_flow(vehicle_count, cav_ratio, loops, seed, route_path, model, **kwargs):
        captured.update(kwargs)
        Path(route_path).write_text("<routes/>", encoding="utf-8")

    monkeypatch.setattr(ff, "generate_flow", fake_generate_flow)
    monkeypatch.setattr(
        ff.subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stderr="", stdout=""),
    )
    monkeypatch.setattr(ff, "parse_lap_times", lambda *a, **k: {"median_lap_time_s": 111.8})
    monkeypatch.setattr(ff, "write_run_spec", lambda *a, **k: None)

    net_meta = {
        "edge_ids": [f"e{i}" for i in range(4)],
        "edge_length_m": 500.0,
        "num_lanes": 1,
    }
    for model, cav_count in [("IDM", 0), ("CACC", 1)]:
        spec = RunSpec(
            scenario="scenario_0",
            model=model,
            pcav=0.0 if cav_count == 0 else 1.0,
            vehicle_count=1,
            seed=1,
            run_id=f"ff_scenario_0_{model}",
            simulation_end=5000,
            warmup=120,
            step_length=0.1,
            detector_frequency=60,
            edge_data_frequency=60,
            loops=60,
            network_file="net/scenario_0/loop.net.xml",
            pipeline_version=PIPELINE_V4_2,
            schema_version="2",
            sumo_seed=1,
            cav_count=cav_count,
            requested_pcav=None,
            with_internal=False,
            experiment_role="main_factorial",
            ssm_enabled=False,
        )
        captured.clear()
        lap = ff._run_free_flow("ff_x", spec, "net/scenario_0/loop.net.xml", net_meta, {})
        assert captured["cav_count"] == cav_count, f"{model} arm 未传 cav_count={cav_count}"
        assert lap == 111.8


def test_evidence_profile_fcd_conditional():
    """审查 P2-2（第九轮）：_evidence_profile 按 fcd_enabled 条件插入 fcd.xml.gz。

    fcd_profile=None（FCD 关闭）时 fcd.xml.gz 必须进入有意缺失清单而非 expected，
    否则冻结 case 证据校验必然 FileNotFoundError。
    """
    from pathlib import Path

    from scripts.analysis.ssm_reproducer import _evidence_profile

    root = Path("/x")
    run_dir = Path("/x/raw/run")
    # FCD 开 + SSM 开
    exp, absent = _evidence_profile(root, run_dir, ssm_enabled=True, fcd_enabled=True)
    assert run_dir / "fcd.xml.gz" in exp
    assert run_dir / "fcd.xml.gz" not in absent
    assert run_dir / "ssm.xml" in exp
    # FCD 关 + SSM 开：fcd 进 absent，ssm 仍在 expected
    exp, absent = _evidence_profile(root, run_dir, ssm_enabled=True, fcd_enabled=False)
    assert run_dir / "fcd.xml.gz" not in exp
    assert run_dir / "fcd.xml.gz" in absent
    assert run_dir / "ssm.xml" in exp
    # FCD 关 + SSM 关：两者都在 absent
    exp, absent = _evidence_profile(root, run_dir, ssm_enabled=False, fcd_enabled=False)
    assert run_dir / "ssm.xml" in absent
    assert run_dir / "fcd.xml.gz" in absent
