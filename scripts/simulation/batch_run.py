"""v0.4.0.post1 批量并行仿真 — asyncio + Queue + N worker

架构：
  Python 父进程
  ├── async worker 1 → SUMO 子进程 → 独立 run 目录
  ├── async worker 2 → SUMO 子进程 → 独立 run 目录
  ├── ...
  └── async worker N → SUMO 子进程 → 独立 run 目录

第一阶段只运行 SUMO 并产出原始 XML + simulation_status.json，不做解析。
"""

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import signal
import sys
import time
import traceback
from contextlib import suppress
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from scripts.config import (
    CAV_MODELS,
    DEFAULT_DETECTOR_FREQ,
    DEFAULT_SIM_END,
    DEFAULT_STEP_LENGTH,
    DEFAULT_WARMUP,
)
from scripts.experiment_config import load_experiment_config, validate_analysis_windows
from scripts.provenance import collect_provenance, freeze_input_pair, sha256_file
from scripts.run_spec import (
    PIPELINE_V4_1,
    PIPELINE_V4_2,
    RunSpec,
    SimulationResult,
    atomic_write_json,
    build_run_id,
    is_simulation_complete,
)
from scripts.simulation.single_run import (
    build_sumo_command,
    build_sumo_command_v4_1,
    build_sumo_command_v4_2,
    prepare_run,
)

# ═══════════════════════════════════════════════════════════════════
# 默认实验参数
# ═══════════════════════════════════════════════════════════════════

SCENARIOS = ["scenario_0", "scenario_1", "scenario_2", "scenario_3"]
SCENARIO_WEIGHT = {"scenario_3": 4, "scenario_2": 3, "scenario_1": 2, "scenario_0": 1}


# ═══════════════════════════════════════════════════════════════════
# 任务生成 & 校验
# ═══════════════════════════════════════════════════════════════════


def generate_pcav_levels(step: float = 0.05) -> list:
    decimal_step = Decimal(str(step))
    if decimal_step <= 0 or Decimal(1) % decimal_step:
        raise ValueError("pCAV step must be positive and evenly divide 1")
    count = int(Decimal(1) / decimal_step)
    return [float(decimal_step * index) for index in range(count + 1)]


def build_run_specs(
    scenarios: list,
    models: list,
    pipeline_version: str = "v0.4.0.post1",
    *,
    # requested_pcav 模式参数（旧）
    pcav_levels: list | None = None,
    vehicle_levels: list | None = None,
    seeds: list | None = None,
    # cav_count 模式参数（新）
    treatments: list | None = None,
    sumo_seeds: list | None = None,
    # 公共参数
    simulation_end: float = DEFAULT_SIM_END,
    warmup: float = DEFAULT_WARMUP,
    step_length: float = DEFAULT_STEP_LENGTH,
    detector_frequency: int = DEFAULT_DETECTOR_FREQ,
    edge_data_frequency: int = 300,
    loops: int = 300,
    network_files: dict[str, str] | None = None,
    seed_scope: str = "vehicle_type_assignment",
    schema_version: str = "1",
    config_sha256: str = "",
    network_sha256: dict[str, str] | None = None,
    experiment_id: str = "",
    # v0.4.1 capture/FCD
    ssm_capture_ttc_threshold_s: float = 3.0,
    ssm_capture_drac_threshold_mps2: float = 3.0,
    ssm_range_m: float = 50.0,
    ssm_trajectories: bool = False,
    ssm_extratime_s: float = 5.0,
    fcd_profile: str | None = None,
    fcd_max_leader_distance_m: float | None = None,
    with_internal: bool = False,
    experiment_role: str = "main_factorial",
    ssm_enabled: bool = False,
    analysis_ttc_threshold_s: float = 3.0,
    analysis_drac_threshold_mps2: float = 3.0,
    ssm_dedup_method: str = "greedy_one_to_one_80pct",
    ssm_mirror_overlap_ratio: float = 0.8,
    ssm_fragment_merge_gap_s: float = 0.0,
) -> list[RunSpec]:
    """生成全部 RunSpec，根据参数自动选择 requested_pcav 或 cav_count 网格模式。"""
    if sumo_seeds is not None and treatments is not None:
        return _build_cav_count_specs(
            scenarios=scenarios,
            models=models,
            treatments=treatments,
            sumo_seeds=sumo_seeds,
            simulation_end=simulation_end,
            warmup=warmup,
            step_length=step_length,
            detector_frequency=detector_frequency,
            edge_data_frequency=edge_data_frequency,
            loops=loops,
            network_files=network_files or {},
            seed_scope=seed_scope,
            pipeline_version=pipeline_version,
            schema_version=schema_version,
            config_sha256=config_sha256,
            network_sha256=network_sha256 or {},
            experiment_id=experiment_id,
            ssm_capture_ttc_threshold_s=ssm_capture_ttc_threshold_s,
            ssm_capture_drac_threshold_mps2=ssm_capture_drac_threshold_mps2,
            ssm_range_m=ssm_range_m,
            ssm_trajectories=ssm_trajectories,
            ssm_extratime_s=ssm_extratime_s,
            fcd_profile=fcd_profile,
            fcd_max_leader_distance_m=fcd_max_leader_distance_m,
            with_internal=with_internal,
            experiment_role=experiment_role,
            ssm_enabled=ssm_enabled,
            analysis_ttc_threshold_s=analysis_ttc_threshold_s,
            analysis_drac_threshold_mps2=analysis_drac_threshold_mps2,
            ssm_dedup_method=ssm_dedup_method,
            ssm_mirror_overlap_ratio=ssm_mirror_overlap_ratio,
            ssm_fragment_merge_gap_s=ssm_fragment_merge_gap_s,
        )
    if pcav_levels is None or vehicle_levels is None or seeds is None:
        raise ValueError(
            "either (pcav_levels, vehicle_levels, seeds) or (treatments, sumo_seeds) required"
        )
    return _build_requested_pcav_specs(
        scenarios=scenarios,
        models=models,
        pcav_levels=pcav_levels,
        vehicle_levels=vehicle_levels,
        seeds=seeds,
        simulation_end=simulation_end,
        warmup=warmup,
        step_length=step_length,
        detector_frequency=detector_frequency,
        edge_data_frequency=edge_data_frequency,
        loops=loops,
        network_files=network_files or {},
        seed_scope=seed_scope,
        pipeline_version=pipeline_version,
        schema_version=schema_version,
        config_sha256=config_sha256,
        network_sha256=network_sha256 or {},
        experiment_id=experiment_id,
        ssm_capture_ttc_threshold_s=ssm_capture_ttc_threshold_s,
        ssm_capture_drac_threshold_mps2=ssm_capture_drac_threshold_mps2,
        ssm_range_m=ssm_range_m,
        ssm_trajectories=ssm_trajectories,
        ssm_extratime_s=ssm_extratime_s,
        fcd_profile=fcd_profile,
        fcd_max_leader_distance_m=fcd_max_leader_distance_m,
        with_internal=with_internal,
    )


def _build_spec_common(
    scenario: str,
    model: str,
    run_id: str,
    pcav: float,
    vehicle_count: int,
    assignment_seed: int,
    sumo_seed: int,
    simulation_end: float,
    warmup: float,
    step_length: float,
    detector_frequency: int,
    edge_data_frequency: int,
    loops: int,
    network_file: str,
    seed_scope: str,
    pipeline_version: str,
    schema_version: str,
    config_sha256: str,
    network_sha256: str,
    experiment_id: str,
    *,
    cav_count: int | None = None,
    requested_pcav: float | None = None,
    ssm_capture_ttc_threshold_s: float = 3.0,
    ssm_capture_drac_threshold_mps2: float = 3.0,
    ssm_range_m: float = 50.0,
    ssm_trajectories: bool = False,
    ssm_extratime_s: float = 5.0,
    fcd_profile: str | None = None,
    fcd_max_leader_distance_m: float | None = None,
    with_internal: bool = False,
    experiment_role: str = "main_factorial",
    ssm_enabled: bool = False,
    analysis_ttc_threshold_s: float = 3.0,
    analysis_drac_threshold_mps2: float = 3.0,
    ssm_dedup_method: str = "greedy_one_to_one_80pct",
    ssm_mirror_overlap_ratio: float = 0.8,
    ssm_fragment_merge_gap_s: float = 0.0,
) -> RunSpec:
    """创建 RunSpec 的公共工厂。"""
    return RunSpec(
        scenario=scenario,
        model=model,
        pcav=pcav,
        vehicle_count=vehicle_count,
        seed=assignment_seed,
        run_id=run_id,
        simulation_end=simulation_end,
        warmup=warmup,
        step_length=step_length,
        detector_frequency=detector_frequency,
        edge_data_frequency=edge_data_frequency,
        loops=loops,
        network_file=network_file,
        seed_scope=seed_scope,
        pipeline_version=pipeline_version,
        schema_version=schema_version,
        config_sha256=config_sha256,
        network_sha256=network_sha256,
        experiment_id=experiment_id,
        sumo_seed=sumo_seed,
        cav_count=cav_count,
        requested_pcav=requested_pcav,
        ssm_capture_ttc_threshold_s=ssm_capture_ttc_threshold_s,
        ssm_capture_drac_threshold_mps2=ssm_capture_drac_threshold_mps2,
        ssm_range_m=ssm_range_m,
        ssm_trajectories=ssm_trajectories,
        ssm_extratime_s=ssm_extratime_s,
        fcd_profile=fcd_profile,
        fcd_max_leader_distance_m=fcd_max_leader_distance_m,
        with_internal=with_internal,
        experiment_role=experiment_role,
        ssm_enabled=ssm_enabled,
        analysis_ttc_threshold_s=analysis_ttc_threshold_s,
        analysis_drac_threshold_mps2=analysis_drac_threshold_mps2,
        ssm_dedup_method=ssm_dedup_method,
        ssm_mirror_overlap_ratio=ssm_mirror_overlap_ratio,
        ssm_fragment_merge_gap_s=ssm_fragment_merge_gap_s,
    )


def _build_requested_pcav_specs(
    scenarios: list,
    models: list,
    pcav_levels: list,
    vehicle_levels: list,
    seeds: list,
    simulation_end: float,
    warmup: float,
    step_length: float,
    detector_frequency: int,
    edge_data_frequency: int,
    loops: int,
    network_files: dict[str, str],
    seed_scope: str,
    pipeline_version: str,
    schema_version: str,
    config_sha256: str,
    network_sha256: dict[str, str],
    experiment_id: str,
    ssm_capture_ttc_threshold_s: float,
    ssm_capture_drac_threshold_mps2: float,
    ssm_range_m: float,
    ssm_trajectories: bool,
    ssm_extratime_s: float,
    fcd_profile: str | None,
    fcd_max_leader_distance_m: float | None,
    with_internal: bool,
) -> list[RunSpec]:
    """以旧 requested_pcav 模式展开网格。"""
    specs = []
    for scenario in scenarios:
        for model in models:
            for pcav in pcav_levels:
                for vn in vehicle_levels:
                    for seed in seeds:
                        run_id = build_run_id(scenario, model, pcav, vn, seed)
                        specs.append(
                            _build_spec_common(
                                scenario=scenario,
                                model=model,
                                run_id=run_id,
                                pcav=pcav,
                                vehicle_count=vn,
                                assignment_seed=seed,
                                sumo_seed=0,
                                simulation_end=simulation_end,
                                warmup=warmup,
                                step_length=step_length,
                                detector_frequency=detector_frequency,
                                edge_data_frequency=edge_data_frequency,
                                loops=loops,
                                network_file=network_files.get(
                                    scenario, f"net/{scenario}/loop.net.xml"
                                ),
                                seed_scope=seed_scope,
                                pipeline_version=pipeline_version,
                                schema_version=schema_version,
                                config_sha256=config_sha256,
                                network_sha256=network_sha256.get(scenario, ""),
                                experiment_id=experiment_id,
                                ssm_capture_ttc_threshold_s=ssm_capture_ttc_threshold_s,
                                ssm_capture_drac_threshold_mps2=ssm_capture_drac_threshold_mps2,
                                ssm_range_m=ssm_range_m,
                                ssm_trajectories=ssm_trajectories,
                                ssm_extratime_s=ssm_extratime_s,
                                fcd_profile=fcd_profile,
                                fcd_max_leader_distance_m=fcd_max_leader_distance_m,
                                with_internal=with_internal,
                            )
                        )
    return specs


def _build_cav_count_specs(
    scenarios: list,
    models: list,
    treatments: list,
    sumo_seeds: list,
    simulation_end: float,
    warmup: float,
    step_length: float,
    detector_frequency: int,
    edge_data_frequency: int,
    loops: int,
    network_files: dict[str, str],
    seed_scope: str,
    pipeline_version: str,
    schema_version: str,
    config_sha256: str,
    network_sha256: dict[str, str],
    experiment_id: str,
    ssm_capture_ttc_threshold_s: float,
    ssm_capture_drac_threshold_mps2: float,
    ssm_range_m: float,
    ssm_trajectories: bool,
    ssm_extratime_s: float,
    fcd_profile: str | None,
    fcd_max_leader_distance_m: float | None,
    with_internal: bool,
    experiment_role: str = "main_factorial",
    ssm_enabled: bool = False,
    analysis_ttc_threshold_s: float = 3.0,
    analysis_drac_threshold_mps2: float = 3.0,
    ssm_dedup_method: str = "greedy_one_to_one_80pct",
    ssm_mirror_overlap_ratio: float = 0.8,
    ssm_fragment_merge_gap_s: float = 0.0,
) -> list[RunSpec]:
    """以新 cav_count 模式展开网格，含 inactive-dimension 处理。"""
    specs: list[RunSpec] = []

    cartesian_total = 0

    for scenario in scenarios:
        for treatment in treatments:
            vn = int(treatment["vehicle_count"])
            cav_counts = [int(c) for c in treatment["cav_counts"]]
            for cav_count in cav_counts:
                for s_seed in sumo_seeds:
                    # model 维度：cav_count=0 时无 CAV，model 固定为 None
                    effective_models = [None] if cav_count == 0 else models

                    for model in effective_models:
                        # assignment_seed 维度处理
                        aseeds_raw = treatment.get("assignment_seeds", [])
                        if not aseeds_raw:
                            aseeds = _default_assignment_seeds(cav_count, vn)
                        else:
                            aseeds = [int(a) for a in aseeds_raw]
                        # inactive 维度：无 CAV 或全 CAV 时 assignment_seed 不可区分
                        if cav_count == 0 or cav_count == vn:
                            aseeds = aseeds[:1]

                        for aseed in aseeds:
                            cartesian_total += 1

                            # inactive-dimension：无 CAV 或全 CAV 时 assignment_seed 不可区分
                            effective_aseed = aseed
                            if cav_count == 0 or cav_count == vn:
                                effective_aseed = None

                            # run_id 用 HVONLY，RunSpec.model 用固定占位值（cav=0 时不使用 CAV 模型）
                            run_id_token = "HVONLY" if cav_count == 0 else (model or "UNKN")
                            spec_model = "IDM" if cav_count == 0 else model

                            run_id = build_run_id(
                                scenario,
                                run_id_token,
                                vehicle_count=vn,
                                cav_count=cav_count,
                                assignment_seed=effective_aseed,
                                sumo_seed=s_seed,
                            )

                            spec = _build_spec_common(
                                scenario=scenario,
                                model=spec_model,
                                run_id=run_id,
                                pcav=cav_count / vn,
                                vehicle_count=vn,
                                assignment_seed=effective_aseed
                                if effective_aseed is not None
                                else 0,
                                sumo_seed=s_seed,
                                cav_count=cav_count,
                                requested_pcav=None,
                                simulation_end=simulation_end,
                                warmup=warmup,
                                step_length=step_length,
                                detector_frequency=detector_frequency,
                                edge_data_frequency=edge_data_frequency,
                                loops=loops,
                                network_file=network_files.get(
                                    scenario, f"net/{scenario}/loop.net.xml"
                                ),
                                seed_scope=seed_scope,
                                pipeline_version=pipeline_version,
                                schema_version=schema_version,
                                config_sha256=config_sha256,
                                network_sha256=network_sha256.get(scenario, ""),
                                experiment_id=experiment_id,
                                ssm_capture_ttc_threshold_s=ssm_capture_ttc_threshold_s,
                                ssm_capture_drac_threshold_mps2=ssm_capture_drac_threshold_mps2,
                                experiment_role=experiment_role,
                                ssm_enabled=ssm_enabled,
                                analysis_ttc_threshold_s=analysis_ttc_threshold_s,
                                analysis_drac_threshold_mps2=analysis_drac_threshold_mps2,
                                ssm_dedup_method=ssm_dedup_method,
                                ssm_mirror_overlap_ratio=ssm_mirror_overlap_ratio,
                                ssm_fragment_merge_gap_s=ssm_fragment_merge_gap_s,
                                ssm_range_m=ssm_range_m,
                                ssm_trajectories=ssm_trajectories,
                                ssm_extratime_s=ssm_extratime_s,
                                fcd_profile=fcd_profile,
                                fcd_max_leader_distance_m=fcd_max_leader_distance_m,
                                with_internal=with_internal,
                            )
                            specs.append(spec)

    # 重复 run_id 检测：拒绝，不静默删除
    seen: dict[str, int] = {}
    for spec in specs:
        seen[spec.run_id] = seen.get(spec.run_id, 0) + 1
    dupes = {rid: cnt for rid, cnt in seen.items() if cnt > 1}
    if dupes:
        raise RuntimeError(
            f"Duplicate run_id in cav_count grid: {dupes}. "
            "Check treatment assignment_seeds for unintended overlaps."
        )

    planned_count = len(specs)
    print(f"[GRID] Cartesian: {cartesian_total}, planned: {planned_count}")

    return specs


def _default_assignment_seeds(cav_count: int, vehicle_count: int) -> list[int]:
    """cav_count 模式下无显式 assignment_seeds 时的默认值。"""
    if cav_count == 0 or cav_count == vehicle_count:
        return [1]  # 不可区分，仅需一个
    return [1, 2, 3]


def validate_specs(
    specs: list[RunSpec],
    scenarios: list,
    models: list,
    *,
    pcav_levels: list | None = None,
    vehicle_levels: list | None = None,
    seeds: list | None = None,
    treatments: list | None = None,
    sumo_seeds: list | None = None,
) -> None:
    """全局校验：数量、唯一性、参数合法性。根据提供参数自动选择模式。"""
    # run_id 唯一性
    seen: dict[str, int] = {}
    for s in specs:
        seen[s.run_id] = seen.get(s.run_id, 0) + 1
    dupes = {k: v for k, v in seen.items() if v > 1}
    if dupes:
        raise RuntimeError(f"Duplicate run_id: {dupes}")

    if sumo_seeds is not None and treatments is not None:
        _validate_cav_count_specs(specs, scenarios, models, treatments, sumo_seeds)
    elif pcav_levels is not None and vehicle_levels is not None and seeds is not None:
        # 数量校验（requested_pcav 模式）
        expected = (
            len(scenarios) * len(models) * len(pcav_levels) * len(vehicle_levels) * len(seeds)
        )
        if len(specs) != expected:
            raise RuntimeError(f"Unexpected run count: {len(specs)}, expected {expected}")
        _validate_requested_pcav_specs(specs, scenarios, models, pcav_levels, vehicle_levels, seeds)
    else:
        raise RuntimeError("validation requires either requested_pcav or cav_count parameters")


def _validate_requested_pcav_specs(
    specs: list[RunSpec],
    scenarios: list,
    models: list,
    pcav_levels: list,
    vehicle_levels: list,
    seeds: list,
) -> None:
    """requested_pcav 模式完整校验（含 model/pCAV/vehN/seed）。"""
    _validate_common(specs, scenarios)
    for s in specs:
        if s.model not in models:
            raise RuntimeError(f"Invalid model: {s.model}")
        if not (0 <= s.pcav <= 1):
            raise RuntimeError(f"Invalid pCAV: {s.pcav}")
        if s.vehicle_count not in vehicle_levels:
            raise RuntimeError(f"Invalid vehN: {s.vehicle_count}")
        if s.seed not in seeds:
            raise RuntimeError(f"Invalid seed: {s.seed}")


def _validate_common(specs: list[RunSpec], scenarios: list) -> None:
    """公共参数校验（scenario + 时序 + 频率）。"""
    for s in specs:
        if s.scenario not in scenarios:
            raise RuntimeError(f"Invalid scenario: {s.scenario}")
        if s.warmup < 0 or s.warmup >= s.simulation_end:
            raise RuntimeError(
                f"Invalid timing for {s.run_id}: warmup must be less than simulation_end"
            )
        if min(s.step_length, s.detector_frequency, s.edge_data_frequency, s.loops) <= 0:
            raise RuntimeError(f"Non-positive runtime parameter in {s.run_id}")
        try:
            validate_analysis_windows(
                s.warmup,
                s.detector_frequency,
                s.edge_data_frequency,
            )
        except ValueError as exc:
            raise RuntimeError(f"Invalid timing for {s.run_id}: {exc}") from exc


def _validate_cav_count_specs(
    specs: list[RunSpec],
    scenarios: list,
    models: list,
    treatments: list,
    sumo_seeds: list,
) -> None:
    """cav_count 模式校验：expected count、model/seed 规范化、treatment membership、run_id 重推导。"""
    if not specs:
        raise RuntimeError("cav_count grid produced zero specs")
    _validate_common(specs, scenarios)

    # 计算预期总数并构建期望组合集
    expected_count = 0
    # {(scenario, vehN, cav_count): (allowed_models, allowed_seeds)}
    expected_combos: dict[tuple[str, int, int], tuple[set[str], set[int]]] = {}
    for _scenario in scenarios:
        for t in treatments:
            vn = int(t["vehicle_count"])
            cav_counts = [int(c) for c in t["cav_counts"]]
            for cc in cav_counts:
                n_models = 1 if cc == 0 else len(models)
                aseeds = t.get("assignment_seeds", _default_assignment_seeds(cc, vn))
                n_aseeds = 1 if (cc == 0 or cc == vn) else len(aseeds)
                expected_count += n_models * n_aseeds * len(sumo_seeds)
                for scenario in scenarios:
                    key = (scenario, vn, cc)
                    allowed_models = set(models)
                    allowed_seeds = set(int(a) for a in aseeds)
                    if key not in expected_combos:
                        expected_combos[key] = (allowed_models, allowed_seeds)
                    else:
                        expected_combos[key][1].update(allowed_seeds)
    if len(specs) != expected_count:
        raise RuntimeError(f"Expected {expected_count} specs for cav_count grid, got {len(specs)}")

    # 构建 treatment 查找表
    treatment_set: dict[str, dict[int, set[int]]] = {}
    for scenario in scenarios:
        treatment_set[scenario] = {}
    for t in treatments:
        vn = int(t["vehicle_count"])
        cavs = set(int(c) for c in t["cav_counts"])
        for scenario in scenarios:
            treatment_set[scenario][vn] = cavs

    for s in specs:
        if s.sumo_seed not in sumo_seeds:
            raise RuntimeError(f"Invalid sumo_seed: {s.sumo_seed}")
        if s.seed_scope != "vehicle_type_assignment":
            raise RuntimeError(f"Invalid seed_scope: {s.seed_scope}")
        if s.pipeline_version not in (PIPELINE_V4_1, PIPELINE_V4_2):
            raise RuntimeError(
                f"Expected pipeline_version={PIPELINE_V4_1} or {PIPELINE_V4_2}, got {s.pipeline_version}"
            )

        s_vn = s.vehicle_count
        s_cc = s.cav_count or 0

        # model 校验：cav=0 使用固定占位 "IDM"，其他使用配置模型
        if s_cc == 0:
            if s.model != "IDM":
                raise RuntimeError(f"cav_count=0 requires model=IDM, got {s.model}")
        elif s.model not in models:
            raise RuntimeError(f"Invalid model: {s.model}")

        # assignment seed 校验
        if 0 < s_cc < s_vn:
            combo = expected_combos.get((s.scenario, s_vn, s_cc))
            if combo and s.seed not in combo[1]:
                raise RuntimeError(
                    f"seed {s.seed} not allowed for (scenario={s.scenario}, "
                    f"vehN={s_vn}, cav={s_cc}); allowed: {combo[1]}"
                )
        elif s_cc == 0 or s_cc == s_vn:
            # 端点：assignment_seed 不可区分，必须为 sentinel 值 0
            if s.seed != 0:
                raise RuntimeError(f"endpoint (cav={s_cc}) seed must be 0 (inactive), got {s.seed}")

        # treatment membership
        scenario_table = treatment_set.get(s.scenario, {})
        if s_vn not in scenario_table:
            raise RuntimeError(f"vehicle_count={s_vn} not in treatments for {s.scenario}")
        if s_cc not in scenario_table[s_vn]:
            raise RuntimeError(
                f"cav_count={s_cc} not in treatments for vehN={s_vn} in {s.scenario}"
            )

        # run_id 重推导
        effective_model = s.model if s_cc > 0 else "HVONLY"
        expected_rid = build_run_id(
            s.scenario,
            effective_model,
            vehicle_count=s_vn,
            cav_count=s_cc,
            assignment_seed=s.seed if 0 < s_cc < s_vn else None,
            sumo_seed=s.sumo_seed,
        )
        if s.run_id != expected_rid:
            raise RuntimeError(f"run_id mismatch: stored={s.run_id}, rederived={expected_rid}")


def prepare_post1_frozen_inputs(
    output_root: Path,
    pipeline_version: str,
    resolved_config: dict,
    acceptance_path: str | Path | None,
    resume: bool,
) -> dict[str, str] | None:
    """Freeze post1 inputs and reject unsafe manifest reuse before a batch starts."""
    if pipeline_version != PIPELINE_V4_1:
        return None
    if acceptance_path is None:
        raise ValueError("--acceptance is required for v0.4.1.post1 execution")

    manifest_path = output_root / "manifest.json"
    if manifest_path.exists() and not resume:
        raise ValueError(
            "output manifest already exists; use --resume after verifying frozen inputs"
        )

    hashes = freeze_input_pair(output_root / "frozen_inputs", resolved_config, acceptance_path)
    if not resume:
        return hashes
    if not manifest_path.exists():
        raise ValueError("--resume requires an existing manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"resume manifest unreadable: {manifest_path}") from exc
    if manifest.get("frozen_inputs") != hashes:
        raise ValueError("resume manifest frozen_inputs mismatch")
    return hashes


def validate_path_safety(output_root: Path, specs: list[RunSpec]) -> None:
    """校验所有 run_dir 均位于 output_root 下方，防止路径逃逸"""
    output_resolved = output_root.resolve()
    for spec in specs:
        run_dir = (output_root / spec.run_id).resolve()
        if output_resolved not in run_dir.parents:
            raise RuntimeError(f"Path escape: {run_dir} not under {output_resolved}")


def validate_environment(
    output_root: Path, sumo_command: str, network_files: dict, specs: list | None = None
) -> None:
    """启动前环境校验：SUMO、路网、磁盘"""
    if shutil.which(sumo_command) is None:
        raise RuntimeError(f"SUMO binary not found: {sumo_command}")

    for net_file in network_files.values():
        if not os.path.isfile(net_file):
            raise RuntimeError(f"Network file not found: {net_file}")

    output_root.mkdir(parents=True, exist_ok=True)
    if not os.access(output_root, os.W_OK):
        raise RuntimeError(f"Output root not writable: {output_root}")

    if specs:
        usage = shutil.disk_usage(output_root)
        # P1-8：磁盘检查按 run 数估算参考用量（~20 MB/run），仅提示不硬门禁；
        # 实际容量以运行时的 resume/OOM 恢复兜底。
        per_run = 20 * 1024**2  # 20 MB per-run reference
        est_gb = (per_run * len(specs)) / 1024**3
        if usage.free < per_run * len(specs):
            print(
                f"[WARN] Estimated disk usage ~{est_gb:.1f} GB for {len(specs)} runs, "
                f"{usage.free / 1024**3:.1f} GB free; runs exceeding capacity will be "
                f"recovered via resume (not a hard gate)."
            )


def sort_specs(specs: list[RunSpec]) -> list[RunSpec]:
    """重任务优先：s3 > s2 > s1 > s0，vehN 降序"""
    return sorted(
        specs,
        key=lambda s: (
            SCENARIO_WEIGHT.get(s.scenario, 0),
            s.vehicle_count,
            s.pcav,
        ),
        reverse=True,
    )


# ═══════════════════════════════════════════════════════════════════
# 异步 SUMO 执行
# ═══════════════════════════════════════════════════════════════════

_active_processes: dict[str, asyncio.subprocess.Process] = {}
_shutting_down = False


def _stderr_tail(path: Path, limit: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-limit:]
    except OSError:
        return ""


def _collect_v4_2_raw_hashes(run_dir: Path, spec: RunSpec) -> dict[str, str]:
    """v0.4.2 raw SUMO 输出文件的 SHA 清单（resume 闭包，P0-1）。

    覆盖 performance/emissions/lanechange/vehroute/ssm（safety）/fcd（启用）/
    detector（按 net.json num_lanes）；仅记录实际存在的文件。
    """
    names = [
        "performance.xml",
        "emissions.xml",
        "lanechange.xml",
        "vehroute.xml",
        "performance_HV.xml",
        "performance_CAV.xml",
        "emissions_HV.xml",
        "emissions_CAV.xml",
    ]
    if getattr(spec, "ssm_enabled", False):
        names.append("ssm.xml")
    if spec.fcd_profile is not None:
        names.append("fcd.xml.gz")
    net_meta_path = Path(spec.network_file).with_name("net.json")
    num_lanes = 1
    try:
        with open(net_meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        nl = meta.get("num_lanes")
        if type(nl) is int and nl >= 1:
            num_lanes = nl
    except (OSError, ValueError):
        pass
    for lane_idx in range(num_lanes):
        names.extend(
            [
                f"detector_lane{lane_idx}.xml",
                f"detector_lane{lane_idx}_HV.xml",
                f"detector_lane{lane_idx}_CAV.xml",
            ]
        )
    hashes: dict[str, str] = {}
    for name in names:
        p = run_dir / name
        if p.exists():
            hashes[name] = sha256_file(str(p))
    return hashes


def _missing_required_outputs(run_dir: Path, spec: RunSpec) -> list[str]:
    # P0-4：v0.4.2 主 factorial（ssm_enabled=False）不要求 ssm.xml（意图性缺失）
    names = ["lanechange.xml", "performance.xml", "emissions.xml", "vehroute.xml"]
    if not (getattr(spec, "pipeline_version", "") == "v0.4.2" and not spec.ssm_enabled):
        names.append("ssm.xml")
    if spec.fcd_profile is not None:
        names.append("fcd.xml.gz")
    if getattr(spec, "schema_version", "1") == "2":
        names.extend(
            [
                "performance_HV.xml",
                "performance_CAV.xml",
                "emissions_HV.xml",
                "emissions_CAV.xml",
            ]
        )
        import json as _json

        net_meta_path = Path(spec.network_file).with_name("net.json")
        if not net_meta_path.exists():
            raise FileNotFoundError(f"net.json missing: {net_meta_path}")
        net_meta = _json.loads(net_meta_path.read_text(encoding="utf-8"))
        if not isinstance(net_meta, dict):
            raise ValueError(f"net.json root must be object, got {type(net_meta).__name__}")
        raw = net_meta.get("num_lanes")
        if type(raw) is not int or raw < 1:
            raise ValueError(f"net.json num_lanes must be int >= 1, got {raw!r}")
        num_lanes = raw
        for lane_idx in range(num_lanes):
            names.append(f"detector_lane{lane_idx}.xml")
            names.append(f"detector_lane{lane_idx}_HV.xml")
            names.append(f"detector_lane{lane_idx}_CAV.xml")
    return [
        name
        for name in names
        if not (run_dir / name).is_file() or (run_dir / name).stat().st_size == 0
    ]


async def run_sumo_process(
    spec: RunSpec,
    output_root: Path,
    network_file: str,
    sumo_command: str,
    pipeline_version: str,
    timeout_s: float | None,
    resume: bool,
    frozen_inputs_root: Path | None = None,
) -> SimulationResult:
    """执行单次 SUMO 仿真，返回 SimulationResult"""
    global _active_processes, _shutting_down

    run_dir = output_root / spec.run_id
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()

    # 断点续跑
    if resume and is_simulation_complete(spec, run_dir, pipeline_version):
        return SimulationResult(
            run_id=spec.run_id,
            status="SKIPPED",
            return_code=None,
            run_dir=str(run_dir),
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            wall_time_s=0.0,
            error_message=None,
        )

    try:
        # 中断检查：收到信号后不再启动新 SUMO
        if _shutting_down:
            run_dir.mkdir(parents=True, exist_ok=True)
            finished_at = datetime.now(timezone.utc).isoformat()
            atomic_write_json(
                run_dir / "simulation_status.json",
                {
                    "run_id": spec.run_id,
                    "stage": "SIMULATION",
                    "status": "CANCELLED",
                    "return_code": None,
                    "pipeline_version": pipeline_version,
                    "run_spec_sha256": spec.sha256(),
                    "schema_version": spec.schema_version,
                    "config_sha256": spec.config_sha256,
                    "network_sha256": spec.network_sha256,
                    "experiment_id": spec.experiment_id,
                    "sumo_seed": spec.sumo_seed,
                    "assignment_seed": spec.seed,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "wall_time_s": 0.0,
                    "error_message": "Interrupted before start",
                    "sumo_peak_rss_kb": 0,
                },
            )
            return SimulationResult(
                run_id=spec.run_id,
                status="CANCELLED",
                return_code=None,
                run_dir=str(run_dir),
                started_at=started_at,
                finished_at=finished_at,
                wall_time_s=0.0,
                error_message="Interrupted before start",
            )

        # 准备 run 目录
        prepared = prepare_run(
            spec,
            run_dir,
            network_file,
            frozen_routes_dir=frozen_inputs_root / spec.run_id if frozen_inputs_root else None,
        )
        run_spec_sha256 = spec.sha256()
        if spec.pipeline_version == "v0.4.1":
            cmd = build_sumo_command_v4_1(prepared, network_file, spec, sumo_command)
        elif spec.pipeline_version == "v0.4.2":
            cmd = build_sumo_command_v4_2(prepared, network_file, spec, sumo_command)
        else:
            cmd = build_sumo_command(
                prepared, network_file, sumo_command, spec.simulation_end, spec.step_length
            )

        # 启动 SUMO 子进程
        _max_rss_kb = 0
        with (
            prepared.stdout_path.open("wb") as stdout_f,
            prepared.stderr_path.open("wb") as stderr_f,
        ):
            # 不设 cwd，继承项目根目录；所有路径相对项目根即可跨机器
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=stdout_f,
                stderr=stderr_f,
            )
            _active_processes[spec.run_id] = process

            try:
                deadline = timeout_s if timeout_s else 7200.0
                poll_interval = min(0.5, deadline / 10.0)
                started = time.monotonic()
                _pid = process.pid
                _status_path = f"/proc/{_pid}/status" if _pid else None
                while True:
                    rc = getattr(process, "returncode", None)
                    if rc is not None:
                        return_code = rc
                        break
                    if _status_path:
                        try:
                            with open(_status_path) as _sf:
                                for _line in _sf:
                                    if _line.startswith("VmHWM:"):
                                        _val = int(_line.split()[1])
                                        if _val > _max_rss_kb:
                                            _max_rss_kb = _val
                                        break
                        except (OSError, ValueError, IndexError):
                            pass
                    if _shutting_down:
                        raise asyncio.CancelledError()
                    if time.monotonic() - started >= deadline:
                        raise asyncio.TimeoutError()
                    await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                return_code = getattr(process, "returncode", None)
                if return_code is None:
                    with suppress(ProcessLookupError):
                        process.terminate()
                    try:
                        return_code = await asyncio.wait_for(process.wait(), timeout=10)
                    except (asyncio.TimeoutError, ProcessLookupError):
                        return_code = None
                wall_time = time.monotonic() - t0
                finished_at = datetime.now(timezone.utc).isoformat()
                _active_processes.pop(spec.run_id, None)
                status_data = {
                    "run_id": spec.run_id,
                    "stage": "SIMULATION",
                    "status": "CANCELLED",
                    "return_code": return_code,
                    "pipeline_version": pipeline_version,
                    "run_spec_sha256": run_spec_sha256,
                    "schema_version": spec.schema_version,
                    "config_sha256": spec.config_sha256,
                    "network_sha256": spec.network_sha256,
                    "experiment_id": spec.experiment_id,
                    "sumo_seed": spec.sumo_seed,
                    "assignment_seed": spec.seed,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "wall_time_s": wall_time,
                    "error_message": "Cancelled by user",
                    "sumo_command": cmd,
                    "stderr_tail": _stderr_tail(prepared.stderr_path),
                    "sumo_peak_rss_kb": _max_rss_kb,
                }
                atomic_write_json(prepared.status_path, status_data)
                return SimulationResult(
                    run_id=spec.run_id,
                    status="CANCELLED",
                    return_code=return_code,
                    run_dir=str(run_dir),
                    started_at=started_at,
                    finished_at=finished_at,
                    wall_time_s=wall_time,
                    error_message="Cancelled by user",
                )
            except asyncio.TimeoutError:
                if getattr(process, "returncode", None) is not None:
                    # 进程已自行退出 → 使用实际返回码，继续正常判定
                    return_code = process.returncode
                else:
                    # 进程未退出 → 强制终止，记为 TIMEOUT
                    with suppress(ProcessLookupError):
                        process.terminate()
                    try:
                        return_code = await asyncio.wait_for(process.wait(), timeout=10)
                    except asyncio.TimeoutError:
                        with suppress(ProcessLookupError):
                            process.kill()
                        return_code = await process.wait()
                    except ProcessLookupError:
                        pass

                    wall_time = time.monotonic() - t0
                    finished_at = datetime.now(timezone.utc).isoformat()
                    _active_processes.pop(spec.run_id, None)
                    status_data = {
                        "run_id": spec.run_id,
                        "stage": "SIMULATION",
                        "status": "TIMEOUT",
                        "return_code": None,
                        "pipeline_version": pipeline_version,
                        "run_spec_sha256": run_spec_sha256,
                        "schema_version": spec.schema_version,
                        "config_sha256": spec.config_sha256,
                        "network_sha256": spec.network_sha256,
                        "experiment_id": spec.experiment_id,
                        "sumo_seed": spec.sumo_seed,
                        "assignment_seed": spec.seed,
                        "started_at": started_at,
                        "finished_at": finished_at,
                        "wall_time_s": wall_time,
                        "error_message": f"Timeout after {deadline}s",
                        "sumo_command": cmd,
                        "stderr_tail": _stderr_tail(prepared.stderr_path),
                        "sumo_peak_rss_kb": _max_rss_kb,
                    }
                    atomic_write_json(prepared.status_path, status_data)
                    return SimulationResult(
                        run_id=spec.run_id,
                        status="TIMEOUT",
                        return_code=None,
                        run_dir=str(run_dir),
                        started_at=started_at,
                        finished_at=finished_at,
                        wall_time_s=wall_time,
                        error_message=f"Timeout after {deadline}s",
                    )
                # returncode 可用 → 继续正常判定

        _active_processes.pop(spec.run_id, None)
        wall_time = time.monotonic() - t0
        finished_at = datetime.now(timezone.utc).isoformat()
        missing_outputs = _missing_required_outputs(run_dir, spec)
        success = return_code == 0 and not missing_outputs

        if success:
            status = "SUCCESS"
            error_msg = None
        elif _shutting_down:
            status = "CANCELLED"
            error_msg = "Interrupted by user"
        else:
            status = "FAILED"
            error_msg = (
                f"missing or empty outputs: {', '.join(missing_outputs)}"
                if return_code == 0
                else f"SUMO exited with code {return_code}"
            )

        status_data = {
            "run_id": spec.run_id,
            "stage": "SIMULATION",
            "status": status,
            "return_code": return_code,
            "pipeline_version": pipeline_version,
            "run_spec_sha256": run_spec_sha256,
            "schema_version": spec.schema_version,
            "config_sha256": spec.config_sha256,
            "network_sha256": spec.network_sha256,
            "experiment_id": spec.experiment_id,
            "sumo_seed": spec.sumo_seed,
            "assignment_seed": spec.seed,
            "started_at": started_at,
            "finished_at": finished_at,
            "wall_time_s": wall_time,
            "error_message": error_msg,
            "sumo_command": cmd,
            "stderr_tail": _stderr_tail(prepared.stderr_path),
            "sumo_peak_rss_kb": _max_rss_kb,
        }
        # v0.4.1/v0.4.2: 记录冻结输入哈希供 resume 校验（P0-4 覆盖 v0.4.2）
        if status == "SUCCESS" and spec.pipeline_version in ("v0.4.1", "v0.4.2"):
            status_data["route_file_sha256"] = sha256_file(str(prepared.route_path))
            type_map_path = prepared.vehicle_type_map_path or (run_dir / "vehicle_type_map.json")
            if type_map_path.exists():
                status_data["vehicle_type_map_sha256"] = sha256_file(str(type_map_path))
            # P0-10：v0.4.2 额外记录 additional 与 network XML SHA（resume 闭包）
            if spec.pipeline_version == "v0.4.2":
                status_data["additional_file_sha256"] = sha256_file(str(prepared.additional_path))
                if spec.network_sha256:
                    status_data["network_xml_sha256"] = spec.network_sha256
                # P0-1：net.json 与 raw SUMO 输出进 SHA 闭包（Reviewer 复检 P0-1）
                net_meta_path = Path(spec.network_file).with_name("net.json")
                if net_meta_path.exists():
                    status_data["net_json_sha256"] = sha256_file(str(net_meta_path))
                status_data["raw_output_sha256"] = _collect_v4_2_raw_hashes(run_dir, spec)
        atomic_write_json(prepared.status_path, status_data)

        return SimulationResult(
            run_id=spec.run_id,
            status=status,
            return_code=return_code,
            run_dir=str(run_dir),
            started_at=started_at,
            finished_at=finished_at,
            wall_time_s=wall_time,
            error_message=error_msg,
        )

    except BaseException as e:
        _active_processes.pop(spec.run_id, None)
        wall_time = time.monotonic() - t0
        finished_at = datetime.now(timezone.utc).isoformat()
        run_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            run_dir / "simulation_status.json",
            {
                "run_id": spec.run_id,
                "stage": "SIMULATION",
                "status": "FAILED",
                "return_code": None,
                "pipeline_version": pipeline_version,
                "run_spec_sha256": spec.sha256(),
                "schema_version": spec.schema_version,
                "config_sha256": spec.config_sha256,
                "network_sha256": spec.network_sha256,
                "experiment_id": spec.experiment_id,
                "sumo_seed": spec.sumo_seed,
                "assignment_seed": spec.seed,
                "started_at": started_at,
                "finished_at": finished_at,
                "wall_time_s": wall_time,
                "error_message": str(e) or type(e).__name__,
                "exception_type": type(e).__name__,
                "traceback": "".join(traceback.format_exception(type(e), e, e.__traceback__))[
                    -4000:
                ],
                "stderr_tail": _stderr_tail(run_dir / "stderr.log"),
                "sumo_peak_rss_kb": _max_rss_kb if "_max_rss_kb" in dir() else 0,
            },
        )
        return SimulationResult(
            run_id=spec.run_id,
            status="FAILED",
            return_code=None,
            run_dir=str(run_dir),
            started_at=started_at,
            finished_at=finished_at,
            wall_time_s=wall_time,
            error_message=str(e) or type(e).__name__,
        )


async def sumo_worker(
    worker_id: int,
    queue: asyncio.Queue,
    output_root: Path,
    network_files: dict,
    sumo_command: str,
    pipeline_version: str,
    timeout_s: float | None,
    resume: bool,
    results: list,
    progress: dict,
    total: int,
    frozen_inputs_root: Path | None = None,
) -> None:
    """Worker 协程：循环从队列取 RunSpec → 执行 SUMO → 直到收到 None"""
    global _shutting_down
    while True:
        spec = await queue.get()
        if spec is None or _shutting_down:
            queue.task_done()
            break

        net_file = network_files.get(spec.scenario)
        if net_file is None:
            net_file = f"net/{spec.scenario}/loop.net.xml"

        result = await run_sumo_process(
            spec=spec,
            output_root=output_root,
            network_file=net_file,
            sumo_command=sumo_command,
            pipeline_version=pipeline_version,
            timeout_s=timeout_s,
            resume=resume,
            frozen_inputs_root=frozen_inputs_root,
        )
        results.append(result)

        progress["done"] += 1
        done = progress["done"]
        icon = {
            "SUCCESS": "✓",
            "FAILED": "✗",
            "SKIPPED": "○",
            "TIMEOUT": "⏱",
            "CANCELLED": "⊘",
        }.get(result.status, "?")
        elapsed = time.monotonic() - progress["start_time"]
        rate = done / elapsed * 3600 if elapsed > 0 else 0

        print(
            f"[{done:>5}/{total}] {icon} {result.run_id:40s} "
            f"({result.wall_time_s:5.0f}s) | {rate:5.0f} runs/h | {result.status}"
        )

        queue.task_done()


# ═══════════════════════════════════════════════════════════════════
# 信号处理
# ═══════════════════════════════════════════════════════════════════


def handle_signal():
    global _shutting_down
    if _shutting_down:
        return  # 已经处理过，避免重复 terminate
    _shutting_down = True
    print("\n[SIGNAL] Terminating SUMO processes...")
    for process in list(_active_processes.values()):
        with suppress(Exception):
            process.terminate()


# ═══════════════════════════════════════════════════════════════════
# 主调度器
# ═══════════════════════════════════════════════════════════════════


async def run_batch(
    specs: list[RunSpec],
    output_root: Path,
    network_files: dict,
    sumo_command: str,
    sumo_processes: int,
    pipeline_version: str,
    timeout_s: float | None,
    resume: bool,
    frozen_inputs_root: Path | None = None,
) -> list[SimulationResult]:
    """asyncio Queue + N worker 调度器"""
    global _shutting_down

    # 信号处理器注册在当前运行 loop 上（asyncio.run() 内部创建的 loop）
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, handle_signal)

    total = len(specs)
    results: list[SimulationResult] = []
    progress = {"done": 0, "start_time": time.monotonic()}

    queue: asyncio.Queue = asyncio.Queue()

    # 重任务优先入队
    for spec in sort_specs(specs):
        await queue.put(spec)

    # 启动 worker
    workers = [
        asyncio.create_task(
            sumo_worker(
                worker_id=i,
                queue=queue,
                output_root=output_root,
                network_files=network_files,
                sumo_command=sumo_command,
                pipeline_version=pipeline_version,
                timeout_s=timeout_s,
                resume=resume,
                results=results,
                progress=progress,
                total=total,
                frozen_inputs_root=frozen_inputs_root,
            )
        )
        for i in range(sumo_processes)
    ]

    # 哨兵值
    for _ in workers:
        await queue.put(None)

    # gather 等待所有 worker 退出（shutdown 时 worker 检测 _shutting_down 后自行退出；
    # 不用 queue.join()——shutdown 后队列仍有未处理条目会导致永久阻塞）
    await asyncio.gather(*workers)

    return results


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="批量并行仿真")
    parser.add_argument(
        "--config",
        default="configs/v0.4.0.json",
        help="版本化实验配置 JSON (默认: configs/v0.4.0.json)",
    )
    parser.add_argument(
        "--sumo-processes", type=int, default=4, help="同时运行的 SUMO 进程数 (默认: 4)"
    )
    parser.add_argument("--output-root", default="raw", help="独立 run 目录根路径 (默认: raw/)")
    parser.add_argument(
        "--frozen-inputs", default=None, help="冻结输入源目录 (复制 routes+type_map)"
    )
    parser.add_argument(
        "--acceptance",
        default=None,
        help="v0.4.1.post1 pilot acceptance JSON（非 dry-run 必填）",
    )
    parser.add_argument(
        "--timeout", type=float, default=None, help="单次 SUMO 最大允许时间 (s)，默认 7200"
    )
    parser.add_argument("--resume", action="store_true", help="跳过已完成且版本匹配的 run")
    parser.add_argument("--dry-run", action="store_true", help="只生成和校验任务，不启动 SUMO")
    parser.add_argument("--sumo", default="sumo", help="SUMO 可执行文件 (默认: sumo)")
    parser.add_argument("--pstep", type=float, default=None, help="显式覆盖配置中的 pCAV 网格步长")
    parser.add_argument("--vehN-list", default=None, help="显式覆盖配置中的车辆数列表，逗号分隔")
    parser.add_argument(
        "--assignment-seeds",
        default=None,
        help="显式覆盖车辆类型排列种子列表（推荐）",
    )
    parser.add_argument(
        "--seeds",
        default=None,
        help="[deprecated] 同 --assignment-seeds",
    )
    parser.add_argument(
        "--model", choices=CAV_MODELS, default=None, help="显式覆盖配置，仅运行一个 CAV 模型"
    )
    parser.add_argument("--net", default=None, help="显式覆盖单场景路网；需与 --scenario 一起使用")
    parser.add_argument("--scenario", default=None, help="显式覆盖配置，仅运行一个场景")
    parser.add_argument(
        "--sumo-seeds",
        default=None,
        help="显式覆盖 sumo 随机种子列表（cav_count 模式），逗号分隔",
    )
    args = parser.parse_args()

    # ── 加载配置并应用显式 CLI 覆盖 ──
    try:
        config = load_experiment_config(args.config)
    except ValueError as exc:
        parser.error(str(exc))

    if args.seeds is not None and args.assignment_seeds is not None:
        parser.error("cannot use both --seeds and --assignment-seeds")
    if args.seeds is not None:
        print("[WARNING] --seeds is deprecated, use --assignment-seeds")

    scenarios = [args.scenario] if args.scenario else list(config.scenarios)
    # 校验 --scenario 是否在配置的场景列表中
    if args.scenario and args.scenario not in config.scenarios:
        parser.error(
            f"scenario {args.scenario!r} not in config scenarios: {list(config.scenarios)}"
        )
    models = [args.model] if args.model else list(config.models)
    network_files = dict(config.network_files)
    if args.net:
        if not args.scenario:
            parser.error("--net requires --scenario")
        network_files[args.scenario] = args.net

    # 按 grid_mode 构造 resolved_config
    common_overrides = {
        "scenarios": tuple(scenarios),
        "models": tuple(models),
        "network_files": {s: network_files[s] for s in scenarios},
    }

    if config.grid_mode == "cav_count":
        # cav_count 模式：CLI 覆盖 treatments/sumo_seeds 可选
        treatments = list(config.treatments)
        if args.vehN_list is not None:
            try:
                veh_levels = [int(x.strip()) for x in args.vehN_list.split(",") if x.strip()]
            except ValueError:
                parser.error(f"invalid --vehN-list value: {args.vehN_list}")
            treatments = [
                {"vehicle_count": vn, "cav_counts": [0, vn // 2, vn]} for vn in veh_levels
            ]
        sumo_seeds = list(config.sumo_seeds)
        if args.sumo_seeds is not None:
            try:
                sumo_seeds = [int(x.strip()) for x in args.sumo_seeds.split(",") if x.strip()]
            except ValueError:
                parser.error(f"invalid --sumo-seeds value: {args.sumo_seeds}")
        # 注入全局 assignment_seeds 到 treatments（CLI 覆盖优先）
        aseeds = list(config.seeds)
        seeds_arg = args.assignment_seeds or args.seeds
        if seeds_arg is not None:
            try:
                aseeds = [int(x.strip()) for x in seeds_arg.split(",") if x.strip()]
            except ValueError:
                parser.error(f"invalid assignment seeds value: {seeds_arg}")
        for t in treatments:
            if "assignment_seeds" not in t and aseeds:
                t["assignment_seeds"] = aseeds

        resolved_config = replace(
            config, treatments=tuple(treatments), sumo_seeds=tuple(sumo_seeds), **common_overrides
        )
        spec_kwargs = {
            "treatments": list(resolved_config.treatments),
            "sumo_seeds": list(resolved_config.sumo_seeds),
            "pcav_levels": None,
            "vehicle_levels": None,
            "seeds": None,
        }
    else:
        # requested_pcav 模式（兼容旧行为）
        veh_levels = list(config.vehicle_counts)
        if args.vehN_list is not None:
            try:
                veh_levels = [int(x.strip()) for x in args.vehN_list.split(",") if x.strip()]
            except ValueError:
                parser.error(f"invalid --vehN-list value: {args.vehN_list}")
        seeds = list(config.seeds)
        seeds_arg = args.assignment_seeds or args.seeds
        if seeds_arg is not None:
            try:
                seeds = [int(x.strip()) for x in seeds_arg.split(",") if x.strip()]
            except ValueError:
                parser.error(f"invalid assignment seeds value: {seeds_arg}")
        try:
            pcav_levels = (
                generate_pcav_levels(args.pstep)
                if args.pstep is not None
                else list(config.pcav_levels)
            )
        except ValueError as exc:
            parser.error(str(exc))

        resolved_config = replace(
            config,
            pcav_levels=tuple(pcav_levels),
            vehicle_counts=tuple(veh_levels),
            seeds=tuple(seeds),
            **common_overrides,
        )
        spec_kwargs = {
            "pcav_levels": list(resolved_config.pcav_levels),
            "vehicle_levels": list(resolved_config.vehicle_counts),
            "seeds": list(resolved_config.seeds),
            "treatments": None,
            "sumo_seeds": None,
        }

    try:
        resolved_config.validate()
    except ValueError as exc:
        parser.error(str(exc))
    network_files = dict(resolved_config.network_files)
    for scenario, network_file in network_files.items():
        if not Path(network_file).is_file():
            parser.error(f"network file not found for {scenario}: {network_file}")
    config_sha256 = resolved_config.sha256()
    network_sha256 = {
        scenario: sha256_file(network_file) for scenario, network_file in network_files.items()
    }
    batch_started_at = datetime.now(timezone.utc).isoformat()
    input_signature = "".join(network_sha256[scenario] for scenario in sorted(network_sha256))
    input_sha256 = hashlib.sha256(input_signature.encode("ascii")).hexdigest()
    experiment_id = f"{resolved_config.config_version}-{config_sha256[:12]}-{input_sha256[:12]}"

    # ── 生成 & 校验任务 ──
    try:
        specs = build_run_specs(
            scenarios,
            models,
            resolved_config.pipeline_version,
            simulation_end=resolved_config.simulation_end,
            warmup=resolved_config.warmup,
            step_length=resolved_config.step_length,
            detector_frequency=resolved_config.detector_frequency,
            edge_data_frequency=resolved_config.edge_data_frequency,
            loops=resolved_config.loops,
            network_files=network_files,
            seed_scope=resolved_config.seed_scope,
            schema_version=resolved_config.schema_version,
            config_sha256=config_sha256,
            network_sha256=network_sha256,
            experiment_id=experiment_id,
            **spec_kwargs,
            ssm_capture_ttc_threshold_s=resolved_config.ssm_capture_ttc_threshold_s,
            ssm_capture_drac_threshold_mps2=resolved_config.ssm_capture_drac_threshold_mps2,
            ssm_range_m=resolved_config.ssm_range_m,
            ssm_trajectories=resolved_config.ssm_trajectories,
            ssm_extratime_s=resolved_config.ssm_extratime_s,
            fcd_profile=resolved_config.fcd_profile,
            fcd_max_leader_distance_m=resolved_config.fcd_max_leader_distance_m,
            with_internal=resolved_config.with_internal,
            experiment_role=resolved_config.experiment_role,
            ssm_enabled=resolved_config.ssm_enabled,
            analysis_ttc_threshold_s=resolved_config.analysis_ttc_threshold_s,
            analysis_drac_threshold_mps2=resolved_config.analysis_drac_threshold_mps2,
            ssm_dedup_method=resolved_config.ssm_dedup_method,
            ssm_mirror_overlap_ratio=resolved_config.ssm_mirror_overlap_ratio,
            ssm_fragment_merge_gap_s=resolved_config.ssm_fragment_merge_gap_s,
        )
    except (ValueError, RuntimeError) as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    print(f"[VALIDATE] {len(specs)} tasks generated")

    # v0.4.1 pipeline: gate removed for stages 1-4; S8 (frozen inputs) deferred

    try:
        validate_specs(specs, scenarios, models, **spec_kwargs)
        print("[VALIDATE] run_id uniqueness: OK")
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    for spec in specs:
        if spec.schema_version == "2" and spec.fcd_profile is not None:
            from scripts.parsing.runner import validate_fcd_leader_distance

            network_file = network_files.get(spec.scenario, spec.network_file)
            validate_fcd_leader_distance(spec, network_file)

    output_root = Path(args.output_root)
    try:
        validate_path_safety(output_root, specs)
        print("[VALIDATE] path safety: OK")
        validate_environment(output_root, args.sumo, network_files, specs)
        print(f"[VALIDATE] SUMO={args.sumo}, output={output_root.resolve()}: OK")
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    frozen_input_hashes = None
    if not args.dry_run:
        try:
            frozen_input_hashes = prepare_post1_frozen_inputs(
                output_root,
                resolved_config.pipeline_version,
                resolved_config.to_dict(),
                args.acceptance,
                args.resume,
            )
        except (OSError, ValueError) as exc:
            parser.error(str(exc))

    # ── dry-run ──
    if args.dry_run:
        ordered = sort_specs(specs)
        print(f"\n[DRY RUN] {len(ordered)} tasks (heavy-first order):")
        for s in ordered[:20]:
            print(
                f"  {s.run_id:45s} {s.scenario} {s.model} "
                f"p={s.pcav:.2f} v={s.vehicle_count:>3d} seed={s.seed}"
            )
        if len(ordered) > 20:
            print(f"  ... and {len(ordered) - 20} more")
        print("\n[DRY RUN] Validation passed. Use --sumo-processes N to execute.")
        return

    provenance = collect_provenance(network_files, args.sumo, sys.argv)
    manifest_path = output_root / "manifest.json"
    manifest = {
        "experiment_id": experiment_id,
        "pipeline_version": resolved_config.pipeline_version,
        "schema_version": resolved_config.schema_version,
        "seed_scope": resolved_config.seed_scope,
        "resolved_config": resolved_config.to_dict(),
        "config_sha256": config_sha256,
        "sumo_seed_mode": "explicit"
        if resolved_config.pipeline_version in ("v0.4.1", "v0.4.2")
        else "SUMO default; no --seed passed",
        "started_at": batch_started_at,
        "finished_at": None,
        "provenance": provenance,
        "total": len(specs),
        "status_counts": {"PLANNED": len(specs)},
        "results": [
            {
                "run_id": spec.run_id,
                "assignment_seed": spec.seed,
                "sumo_seed": spec.sumo_seed,
                "status": "PLANNED",
                "run_spec_sha256": spec.sha256(),
                "network_sha256": spec.network_sha256,
            }
            for spec in specs
        ],
    }
    if frozen_input_hashes is not None:
        manifest["frozen_inputs"] = frozen_input_hashes
    atomic_write_json(manifest_path, manifest)

    # ── 执行 ──
    print(
        f"\n[START] {len(specs)} tasks × {args.sumo_processes} workers, "
        f"resume={'ON' if args.resume else 'OFF'}, "
        f"timeout={f'{args.timeout:.0f}s' if args.timeout else '7200s'}\n"
    )

    try:
        results = asyncio.run(
            run_batch(
                specs=specs,
                output_root=output_root,
                network_files=network_files,
                sumo_command=args.sumo,
                sumo_processes=args.sumo_processes,
                pipeline_version=resolved_config.pipeline_version,
                timeout_s=args.timeout,
                resume=args.resume,
                frozen_inputs_root=Path(args.frozen_inputs) if args.frozen_inputs else None,
            )
        )
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Cleaning up...")
        results = []

    # ── 汇总 ──
    status_counts = {}
    for r in results:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
    total_wall = sum(r.wall_time_s for r in results if r.wall_time_s > 0)

    print(f"\n{'=' * 60}")
    print(f"[DONE] {len(results)} runs completed")
    for st, cnt in sorted(status_counts.items()):
        print(f"  {st}: {cnt}")
    print(f"  total SUMO wall time: {total_wall:.0f}s ({total_wall / 3600:.1f}h)")

    # 更新 manifest；保留未启动任务，确保总数始终等于计划网格。
    returned = {result.run_id: result for result in results}
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    manifest["total"] = len(specs)
    manifest["status_counts"] = status_counts
    manifest["status_counts"]["NOT_STARTED"] = len(specs) - len(results)
    manifest["total_wall_time_s"] = total_wall
    manifest["results"] = [
        {
            "run_id": spec.run_id,
            "assignment_seed": spec.seed,
            "sumo_seed": spec.sumo_seed,
            "status": returned[spec.run_id].status if spec.run_id in returned else "NOT_STARTED",
            "return_code": returned[spec.run_id].return_code if spec.run_id in returned else None,
            "wall_time_s": returned[spec.run_id].wall_time_s if spec.run_id in returned else 0.0,
            "error_message": returned[spec.run_id].error_message
            if spec.run_id in returned
            else None,
            "run_spec_sha256": spec.sha256(),
            "network_sha256": spec.network_sha256,
        }
        for spec in specs
    ]
    atomic_write_json(manifest_path, manifest)
    print(f"  manifest → {manifest_path}")


if __name__ == "__main__":
    main()
