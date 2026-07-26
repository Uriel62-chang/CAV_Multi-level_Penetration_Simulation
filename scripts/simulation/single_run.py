import argparse
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path

from scripts.config import (
    CAV_MODELS,
    DEFAULT_DETECTOR_FREQ,
    DEFAULT_EDGEDATA_FREQ,
    DEFAULT_SIM_END,
    DEFAULT_STEP_LENGTH,
    DEFAULT_WARMUP,
    FREE_FLOW_LAP_TIME_S,
    SSM_DRAC_THRESHOLD_MPS2,
    SSM_TTC_THRESHOLD_S,
)
from scripts.experiment_config import canonical_json, validate_analysis_windows
from scripts.parsing import parse_detector, parse_detector_multi
from scripts.parsing.edge_emissions import parse_edge_emissions
from scripts.parsing.edge_performance import parse_edge_performance
from scripts.parsing.lanechange import parse_lanechange
from scripts.parsing.ssm import parse_ssm
from scripts.parsing.stderr import parse_emergency_braking
from scripts.parsing.vehroute import parse_lap_times
from scripts.provenance import collect_provenance, sha256_file
from scripts.run_spec import (
    PreparedRun,
    RunSpec,
    atomic_write_json,
    build_run_id,
    write_run_spec,
)
from scripts.simulation.flow_generator import generate_flow

ROUTES_DIR = "routes"
DEFAULT_NETWORK_FILE = "net/scenario_0/loop.net.xml"

# 默认路网元数据（向后兼容：无 net.json 时使用）
_LEGACY_NET_META = {
    "edge_ids": ["e0", "e1", "e2", "e3"],
    "edge_length_m": 500.0,
    "num_lanes": 1,
    "num_sides": 4,
}


# ═══════════════════════════════════════════════════════════════════
# 路网元数据
# ═══════════════════════════════════════════════════════════════════


def load_network_meta(network_file: str) -> dict:
    """从路网文件所在目录读取 net.json 元数据"""
    net_dir = os.path.dirname(network_file)
    meta_path = os.path.join(net_dir, "net.json")
    if not os.path.isfile(meta_path):
        raise ValueError(f"路网元数据缺失: {meta_path}")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    required = {
        "schema_version",
        "scenario",
        "num_lanes",
        "edge_length_m",
        "edge_ids",
        "route_edge_ids",
        "detector_edge_id",
        "detector_position_m",
        "bottleneck_edge_ids",
        "edge_lane_counts",
        "legal_initial_lanes",
    }
    missing = sorted(required - meta.keys())
    if missing:
        raise ValueError(f"路网元数据缺少字段: {', '.join(missing)}")
    if meta["schema_version"] != "1":
        raise ValueError(f"不支持的 net.json schema: {meta['schema_version']}")
    if meta["route_edge_ids"] != meta["edge_ids"]:
        raise ValueError("当前闭环路网要求 route_edge_ids 与 edge_ids 顺序一致")
    if meta["detector_edge_id"] not in meta["edge_ids"]:
        raise ValueError("detector_edge_id 不在 route_edge_ids 中")
    return meta


# ═══════════════════════════════════════════════════════════════════
# run 准备（供 batch_run 复用）
# ═══════════════════════════════════════════════════════════════════


def prepare_run(
    spec: RunSpec,
    run_dir: Path,
    network_file: str,
    detector_frequency: int = DEFAULT_DETECTOR_FREQ,
    loops: int = 300,
) -> PreparedRun:
    """准备一次 SUMO 仿真的所有输入文件

    在 run_dir 下生成：
      routes.rou.xml          车流定义
      additional.add.xml      检测器 + edgeData 附加配置
    返回 PreparedRun 含所有输出路径。
    """
    validate_analysis_windows(
        spec.warmup,
        spec.detector_frequency,
        spec.edge_data_frequency,
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    write_run_spec(spec, run_dir)

    net_meta = load_network_meta(network_file)
    edge_ids = net_meta.get("edge_ids", _LEGACY_NET_META["edge_ids"])
    edge_length = net_meta.get("edge_length_m", _LEGACY_NET_META["edge_length_m"])
    edge_count = len(edge_ids)
    net_scenario = net_meta.get("scenario", "scenario_0")
    if net_scenario != spec.scenario:
        raise ValueError(f"RunSpec 场景 {spec.scenario} 与路网元数据 {net_scenario} 不一致")
    num_lanes = net_meta.get("num_lanes", 1)
    first_edge = net_meta["detector_edge_id"]
    detector_pos = float(net_meta["detector_position_m"])

    # ── 路径定义 ──
    route_path = run_dir / "routes.rou.xml"
    additional_path = run_dir / "additional.add.xml"
    detector_paths = tuple(
        run_dir / f"detector_lane{lane_index}.xml" for lane_index in range(num_lanes)
    )
    ssm_path = run_dir / "ssm.xml"
    lanechange_path = run_dir / "lanechange.xml"
    performance_path = run_dir / "performance.xml"
    emissions_path = run_dir / "emissions.xml"
    vehroute_path = run_dir / "vehroute.xml"
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    status_path = run_dir / "simulation_status.json"

    # ── 生成车流 ──
    generate_flow(
        spec.vehicle_count,
        spec.pcav,
        spec.loops,
        spec.seed,
        str(route_path),
        spec.model,
        edge_count=edge_count,
        edge_length=edge_length,
        scenario=net_scenario,
        num_lanes=num_lanes,
        edge_ids=edge_ids,
        bottleneck_edge_ids=net_meta.get("bottleneck_edge_ids"),
    )

    # ── 生成附加文件（检测器 + edgeData 合并） ──
    _write_additional_xml(
        additional_path,
        detector_paths,
        spec.detector_frequency,
        first_edge,
        detector_pos,
        num_lanes,
        performance_path,
        emissions_path,
        spec.simulation_end,
        spec.edge_data_frequency,
    )

    return PreparedRun(
        run_dir=run_dir,
        route_path=route_path,
        additional_path=additional_path,
        detector_paths=detector_paths,
        ssm_path=ssm_path,
        lanechange_path=lanechange_path,
        performance_path=performance_path,
        emissions_path=emissions_path,
        vehroute_path=vehroute_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        status_path=status_path,
    )


def _write_additional_xml(
    additional_path: Path,
    detector_paths: tuple,
    detector_frequency: int,
    first_edge: str,
    detector_pos: float,
    num_lanes: int,
    performance_path: Path,
    emissions_path: Path,
    sim_end_time: float,
    edge_data_freq: int,
) -> None:
    """写入合并的附加 XML（检测器 + edgeData）"""
    with additional_path.open("w", encoding="utf-8") as f:
        f.write("<additional>\n")
        # E1 检测器
        for lane_idx in range(num_lanes):
            det_file = detector_paths[lane_idx].name  # 相对路径
            f.write(
                f'    <e1Detector id="det_l{lane_idx}" lane="{first_edge}_{lane_idx}" '
                f'pos="{detector_pos:.1f}" freq="{detector_frequency}" '
                f'file="{det_file}"/>\n'
            )
        # edgeData
        f.write(
            f'    <edgeData id="ed_perf" type="performance" file="{performance_path.name}" '
            f'freq="{edge_data_freq}" begin="0" end="{int(sim_end_time)}" '
            f'excludeEmpty="true"/>\n'
        )
        f.write(
            f'    <edgeData id="ed_emis" type="emissions" file="{emissions_path.name}" '
            f'freq="{edge_data_freq}" begin="0" end="{int(sim_end_time)}" '
            f'excludeEmpty="true"/>\n'
        )
        f.write("</additional>\n")


def build_sumo_command(
    prepared: PreparedRun,
    network_file: str,
    sumo_command: str = "sumo",
    sim_end_time: float = DEFAULT_SIM_END,
    step_length: float = DEFAULT_STEP_LENGTH,
) -> list:
    """构造 SUMO 命令行参数列表（相对路径，依赖项目根为 CWD）"""
    return [
        sumo_command,
        "-n",
        network_file,
        "-r",
        str(prepared.route_path),
        "-a",
        str(prepared.additional_path),
        "-b",
        "0",
        "-e",
        str(int(sim_end_time)),
        "--step-length",
        str(step_length),
        "--no-step-log",
        "true",
        "--device.ssm.probability",
        "1.0",
        "--device.ssm.file",
        str(prepared.ssm_path),
        "--device.ssm.trajectories",
        "false",
        "--lanechange-output",
        str(prepared.lanechange_path),
        "--vehroute-output",
        str(prepared.vehroute_path),
        "--vehroute-output.exit-times",
        "true",
        "--vehroute-output.write-unfinished",
        "true",
    ]


# ═══════════════════════════════════════════════════════════════════
# 单次仿真（CLI 入口 + 完整解析管线）
# ═══════════════════════════════════════════════════════════════════


def _safe_div(numerator, denominator):
    """安全除法"""
    if denominator is None or (isinstance(denominator, float) and math.isnan(denominator)):
        return float("nan")
    if denominator == 0:
        return float("nan")
    if isinstance(numerator, float) and math.isnan(numerator):
        return float("nan")
    return numerator / denominator


def _per_1000_veh_km(value, total_veh_km):
    """归一化到 per-1000-veh-km"""
    if isinstance(total_veh_km, float) and math.isnan(total_veh_km):
        return float("nan")
    if total_veh_km is None or total_veh_km <= 0:
        return float("nan")
    if isinstance(value, float) and math.isnan(value):
        return float("nan")
    return value / total_veh_km * 1000.0


def parse_run_outputs(
    run_dir: Path, spec: RunSpec, network_file: str = DEFAULT_NETWORK_FILE
) -> dict:
    """解析单个 run 目录的全部原始输出，返回完整 summary dict。

    供 parser_batch 和 run_simulation 共用，确保解析逻辑单一数据源。
    SSM 优先读 ssm_compact.xml，fallback 到 ssm.xml。
    """
    import math as _math

    net_meta = load_network_meta(network_file)
    net_scenario = net_meta.get("scenario", "scenario_0")
    num_lanes = net_meta.get("num_lanes", 1)
    edges_per_lap = net_meta.get("num_sides", 4)
    warmup_period = spec.warmup
    sim_end_time = spec.simulation_end

    # SSM 文件兼容：compact 优先
    ssm_file = run_dir / "ssm_compact.xml"
    if not ssm_file.exists():
        ssm_file = run_dir / "ssm.xml"

    # 读取 stderr
    stderr_path = run_dir / "stderr.log"
    stderr_text = ""
    if stderr_path.exists():
        stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")

    # ── 解析 emergency braking (stderr) ──
    eb_result = parse_emergency_braking(stderr_text, warmup_period)

    # ── 解析检测器 ──
    detector_paths = [
        str(run_dir / f"detector_lane{lane_index}.xml") for lane_index in range(max(num_lanes, 1))
    ]
    if num_lanes > 1:
        mean_flow, max_flow, mean_speed, speed_variance, window_count = parse_detector_multi(
            detector_paths, warmup_period
        )
    else:
        mean_flow, max_flow, mean_speed, speed_variance, window_count = parse_detector(
            detector_paths[0], warmup_period
        )

    # ── 解析 SSM ──
    ssm_result = parse_ssm(
        str(ssm_file),
        warmup_period,
        ttc_threshold=SSM_TTC_THRESHOLD_S,
        drac_threshold=SSM_DRAC_THRESHOLD_MPS2,
    )

    # ── 解析换道 ──
    lc_path = run_dir / "lanechange.xml"
    lc_result = (
        parse_lanechange(str(lc_path), warmup_period)
        if lc_path.exists()
        else {
            "lane_change_count": 0,
            "unsafe_lc_gap_count": 0,
            "unsafe_lc_gap_ratio": float("nan"),
            "parse_success": False,
        }
    )

    # ── 解析 edge performance / emissions ──
    ep_result = parse_edge_performance(str(run_dir / "performance.xml"), warmup_period)
    ee_result = parse_edge_emissions(str(run_dir / "emissions.xml"), warmup_period)

    # ── 解析 vehroute ──
    vr_result = parse_lap_times(
        str(run_dir / "vehroute.xml"), edges_per_lap, warmup_period, sim_end_time
    )

    # ── 归一化 ──
    total_veh_km = ep_result["total_vehicle_km"]
    ttc_per_1000 = _per_1000_veh_km(ssm_result["ttc_conflict_event_count"], total_veh_km)
    eb_per_1000 = _per_1000_veh_km(eb_result["emergency_braking_count"], total_veh_km)
    lc_per_1000 = _per_1000_veh_km(lc_result["lane_change_count"], total_veh_km)
    co2_per = _safe_div(ee_result["total_CO2_kg"] * 1000.0, total_veh_km)
    nox_per = _safe_div(ee_result["total_NOx_g"] * 1000.0, total_veh_km)
    pmx_per = _safe_div(ee_result["total_PMx_g"] * 1000.0, total_veh_km)
    fuel_per = _safe_div(ee_result["total_fuel_kg"] * 1000.0, total_veh_km)
    tl_per = _safe_div(ep_result["total_time_loss_s"], total_veh_km)

    # ── 延误 ──
    free_flow = FREE_FLOW_LAP_TIME_S.get(net_scenario, float("nan"))
    ml = vr_result["mean_lap_time_s"]
    p95 = vr_result["p95_lap_time_s"]
    mean_delay = (
        ml - free_flow if not _math.isnan(ml) and not _math.isnan(free_flow) else float("nan")
    )
    p95_delay = (
        p95 - free_flow if not _math.isnan(p95) and not _math.isnan(free_flow) else float("nan")
    )

    # ── 组装 summary ──
    return {
        "run_id": spec.run_id,
        "scenario": net_scenario,
        "model": spec.model,
        "vehN": spec.vehicle_count,
        "pCAV": spec.pcav,
        "seed": spec.seed,
        "step_length_s": spec.step_length,
        "warmup_period_s": warmup_period,
        "simulation_end_s": sim_end_time,
        "detector_frequency_s": spec.detector_frequency,
        "mean_flow_veh_h": mean_flow,
        "max_flow_veh_h": max_flow,
        "mean_speed_m_s": mean_speed,
        "detector_mean_speed_temporal_variance": speed_variance,
        "detector_speed_window_count": window_count,
        "det_xml": ";".join(detector_paths),
        "ssm_raw_record_count": ssm_result["ssm_raw_record_count"],
        "ssm_invalid_record_count": ssm_result["ssm_invalid_record_count"],
        "ssm_warmup_filtered_count": ssm_result["ssm_warmup_filtered_count"],
        "ssm_valid_record_count": ssm_result["ssm_valid_record_count"],
        "ssm_mirrored_record_count": ssm_result["ssm_mirrored_record_count"],
        "ttc_conflict_event_count": ssm_result["ttc_conflict_event_count"],
        "min_ttc_s": ssm_result["min_ttc_s"],
        "ttc_affected_vehicle_count": ssm_result["ttc_involved_vehicle_count"],
        "drac_conflict_event_count": ssm_result["drac_conflict_event_count"],
        "max_drac_mps2": ssm_result["max_drac_mps2"],
        "emergency_braking_count": eb_result["emergency_braking_count"],
        "emergency_braking_affected_vehicle_count": eb_result[
            "emergency_braking_affected_vehicle_count"
        ],
        "lane_change_count": lc_result["lane_change_count"],
        "unsafe_lc_gap_count": lc_result["unsafe_lc_gap_count"],
        "unsafe_lc_gap_ratio": lc_result["unsafe_lc_gap_ratio"],
        "total_CO2_kg": ee_result["total_CO2_kg"],
        "total_NOx_g": ee_result["total_NOx_g"],
        "total_PMx_g": ee_result["total_PMx_g"],
        "total_fuel_kg": ee_result["total_fuel_kg"],
        "total_vehicle_km": total_veh_km,
        "total_time_loss_s": ep_result["total_time_loss_s"],
        "completed_lap_count": vr_result["completed_lap_count"],
        "mean_lap_time_s": vr_result["mean_lap_time_s"],
        "median_lap_time_s": vr_result["median_lap_time_s"],
        "p95_lap_time_s": vr_result["p95_lap_time_s"],
        "lap_time_std_s": vr_result["lap_time_std_s"],
        "ttc_events_per_1000_veh_km": ttc_per_1000,
        "emergency_brakes_per_1000_veh_km": eb_per_1000,
        "lane_changes_per_1000_veh_km": lc_per_1000,
        "CO2_g_per_veh_km": co2_per,
        "NOx_mg_per_veh_km": nox_per,
        "PMx_mg_per_veh_km": pmx_per,
        "fuel_g_per_veh_km": fuel_per,
        "time_loss_s_per_veh_km": tl_per,
        "mean_lap_delay_s": mean_delay,
        "p95_lap_delay_s": p95_delay,
        # 审计台账
        "ssm_parse_success": ssm_result["parse_success"],
        "lc_parse_success": lc_result["parse_success"],
        "ep_parse_success": ep_result["parse_success"],
        "ee_parse_success": ee_result["parse_success"],
        "vr_parse_success": vr_result["parse_success"],
    }


def run_simulation(
    vehicle_count: int,
    cav_ratio: float,
    seed: int,
    loops: int = 300,
    sim_end_time: int = DEFAULT_SIM_END,
    warmup_period: int = DEFAULT_WARMUP,
    detector_frequency: int = DEFAULT_DETECTOR_FREQ,
    sumo_command: str = "sumo",
    output_csv: str = "out/results_raw.csv",
    model: str = "IDM",
    network_file: str = DEFAULT_NETWORK_FILE,
):
    """使用与批处理相同的仿真、解析和 writer 链路执行一个 run。"""
    from scripts.parsing.runner import parse_one_run
    from scripts.results.writer import build_run_level_results
    from scripts.simulation.batch_run import run_sumo_process

    net_meta = load_network_meta(network_file)
    net_scenario = net_meta["scenario"]
    run_id = build_run_id(net_scenario, model, cav_ratio, vehicle_count, seed)
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_root = output_path.with_suffix("").with_name(output_path.stem + "_raw")
    run_dir = raw_root / run_id
    raw_root.mkdir(parents=True, exist_ok=True)

    resolved_config = {
        "entrypoint": "single_run",
        "scenario": net_scenario,
        "model": model,
        "pcav": cav_ratio,
        "vehicle_count": vehicle_count,
        "seed": seed,
        "seed_scope": "vehicle_type_assignment",
        "simulation_end": float(sim_end_time),
        "warmup": float(warmup_period),
        "step_length": DEFAULT_STEP_LENGTH,
        "detector_frequency": detector_frequency,
        "edge_data_frequency": DEFAULT_EDGEDATA_FREQ,
        "loops": loops,
        "network_file": network_file,
        "pipeline_version": "v0.4.0.post1",
        "schema_version": "1",
    }
    config_sha256 = hashlib.sha256(canonical_json(resolved_config).encode("utf-8")).hexdigest()
    network_sha256 = sha256_file(network_file)
    experiment_id = f"single-{config_sha256[:12]}-{network_sha256[:12]}"

    spec = RunSpec(
        scenario=net_scenario,
        model=model,
        pcav=cav_ratio,
        vehicle_count=vehicle_count,
        seed=seed,
        run_id=run_id,
        simulation_end=float(sim_end_time),
        warmup=float(warmup_period),
        step_length=DEFAULT_STEP_LENGTH,
        detector_frequency=detector_frequency,
        edge_data_frequency=DEFAULT_EDGEDATA_FREQ,
        loops=loops,
        network_file=network_file,
        config_sha256=config_sha256,
        network_sha256=network_sha256,
        experiment_id=experiment_id,
    )

    print("\n[RUN CONFIG]")
    print(f"  scenario    = {net_scenario}")
    print(f"  model       = {model}")
    print(f"  vehN        = {vehicle_count}")
    print(f"  pCAV        = {cav_ratio}")
    print(f"  seed        = {seed}")
    print(f"  freq        = {detector_frequency}")
    print(f"  warmup      = {warmup_period}\n")

    manifest_path = raw_root / "manifest.json"
    manifest = {
        "experiment_id": experiment_id,
        "pipeline_version": spec.pipeline_version,
        "schema_version": spec.schema_version,
        "seed_scope": spec.seed_scope,
        "resolved_config": resolved_config,
        "config_sha256": config_sha256,
        "sumo_seed_mode": "SUMO default; no --seed passed",
        "provenance": collect_provenance(
            {net_scenario: network_file}, sumo_command, ["single_run", run_id]
        ),
        "total": 1,
        "status_counts": {"PLANNED": 1},
        "results": [
            {
                "run_id": run_id,
                "status": "PLANNED",
                "run_spec_sha256": spec.sha256(),
                "network_sha256": network_sha256,
            }
        ],
    }
    atomic_write_json(manifest_path, manifest)

    simulation_result = asyncio.run(
        run_sumo_process(
            spec=spec,
            output_root=raw_root,
            network_file=network_file,
            sumo_command=sumo_command,
            pipeline_version=spec.pipeline_version,
            timeout_s=None,
            resume=False,
        )
    )
    manifest["status_counts"] = {simulation_result.status: 1}
    manifest["results"][0].update(
        {
            "status": simulation_result.status,
            "return_code": simulation_result.return_code,
            "wall_time_s": simulation_result.wall_time_s,
            "error_message": simulation_result.error_message,
        }
    )
    atomic_write_json(manifest_path, manifest)

    parse_status = parse_one_run(run_dir, spec.pipeline_version)
    build_run_level_results(
        input_root=raw_root,
        output_dir=output_path.parent,
        pipeline_version=spec.pipeline_version,
        manifest_path=manifest_path,
        results_filename=output_path.name,
    )
    return {
        "simulation_status": simulation_result.status,
        "parse_status": parse_status["status"],
        "run_dir": str(run_dir),
        "output_csv": str(output_path),
    }


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vehN", type=int, required=True)
    parser.add_argument("--pCAV", type=float, required=True)
    parser.add_argument(
        "--seed",
        type=int,
        default=1,
        help="车辆类型排列种子（仅控制 Python 侧 CAV/HV 空间排列，不传给 SUMO）",
    )
    parser.add_argument("--loops", type=int, default=300)
    parser.add_argument("--end", type=int, default=DEFAULT_SIM_END)
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    parser.add_argument("--freq", type=int, default=DEFAULT_DETECTOR_FREQ)
    parser.add_argument("--sumo", default="sumo")
    parser.add_argument("--outcsv", default="out/results_raw.csv")
    parser.add_argument(
        "--model",
        type=str,
        default="IDM",
        choices=list(CAV_MODELS),
        help="CAV跟驰模型: IDM / ACC / CACC",
    )
    parser.add_argument(
        "--net", default=DEFAULT_NETWORK_FILE, help=f"路网文件路径 (默认: {DEFAULT_NETWORK_FILE})"
    )
    args = parser.parse_args()

    run_simulation(
        vehicle_count=args.vehN,
        cav_ratio=args.pCAV,
        seed=args.seed,
        loops=args.loops,
        sim_end_time=args.end,
        warmup_period=args.warmup,
        detector_frequency=args.freq,
        sumo_command=args.sumo,
        output_csv=args.outcsv,
        model=args.model,
        network_file=args.net,
    )


if __name__ == "__main__":
    main()
