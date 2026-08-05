import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from scripts.config import (
    CAV_MODELS,
    DEFAULT_DETECTOR_FREQ,
    DEFAULT_EDGEDATA_FREQ,
    DEFAULT_SIM_END,
    DEFAULT_STEP_LENGTH,
    DEFAULT_WARMUP,
)
from scripts.experiment_config import canonical_json, validate_analysis_windows
from scripts.provenance import collect_provenance, sha256_file
from scripts.run_spec import (
    PIPELINE_V4_2,
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
    *,
    frozen_routes_dir: Path | None = None,
) -> PreparedRun:
    """"""
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
    detector_paths_HV = tuple(
        run_dir / f"detector_lane{lane_index}_HV.xml" for lane_index in range(num_lanes)
    )
    detector_paths_CAV = tuple(
        run_dir / f"detector_lane{lane_index}_CAV.xml" for lane_index in range(num_lanes)
    )
    performance_HV_path = run_dir / "performance_HV.xml"
    performance_CAV_path = run_dir / "performance_CAV.xml"
    emissions_HV_path = run_dir / "emissions_HV.xml"
    emissions_CAV_path = run_dir / "emissions_CAV.xml"

    # ── 生成车流 ──
    if frozen_routes_dir is not None:
        import shutil as _shutil

        type_map_path = run_dir / "vehicle_type_map.json"
        for src_name in ("routes.rou.xml", "vehicle_type_map.json"):
            src = frozen_routes_dir / src_name
            dst = run_dir / src_name
            if not src.exists():
                raise FileNotFoundError(f"frozen {src_name} not found: {src}")
            _shutil.copy2(src, dst)
            if sha256_file(str(src)) != sha256_file(str(dst)):
                raise ValueError(f"frozen {src_name} SHA mismatch after copy")
        vehicle_type_map = json.loads(type_map_path.read_text(encoding="utf-8"))
    else:
        # P0-2：cav_count 为权威来源，直接传入，避免 round 二义性
        effective_cav_count = spec.cav_count
        vehicle_type_map = generate_flow(
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
            cav_count=effective_cav_count,
            # P0-9：v0.4.2 显式固定 emissionClass（纯净分支恒显式）
        )
        type_map_path = run_dir / "vehicle_type_map.json"
        atomic_write_json(type_map_path, vehicle_type_map)

    # ── 生成附加文件（检测器 + edgeData 合并） ──
    if spec.schema_version == "2":
        _write_additional_v4_1_subgroup(
            additional_path,
            detector_paths,
            detector_paths_HV,
            detector_paths_CAV,
            spec.detector_frequency,
            first_edge,
            detector_pos,
            num_lanes,
            performance_path,
            performance_HV_path,
            performance_CAV_path,
            emissions_path,
            emissions_HV_path,
            emissions_CAV_path,
            spec.simulation_end,
            spec.edge_data_frequency,
            with_internal=spec.with_internal,
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
            vehicle_type_map_path=type_map_path,
            performance_HV_path=performance_HV_path,
            performance_CAV_path=performance_CAV_path,
            emissions_HV_path=emissions_HV_path,
            emissions_CAV_path=emissions_CAV_path,
            detector_paths_HV=detector_paths_HV,
            detector_paths_CAV=detector_paths_CAV,
        )
    else:
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
            with_internal=spec.with_internal,
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
            vehicle_type_map_path=type_map_path,
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
    *,
    with_internal: bool = False,
) -> None:
    """写入合并的附加 XML（检测器 + edgeData）"""
    internal_attr = ' withInternal="true"' if with_internal else ""
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
            f'excludeEmpty="true"{internal_attr}/>\n'
        )
        f.write(
            f'    <edgeData id="ed_emis" type="emissions" file="{emissions_path.name}" '
            f'freq="{edge_data_freq}" begin="0" end="{int(sim_end_time)}" '
            f'excludeEmpty="true"{internal_attr}/>\n'
        )
        f.write("</additional>\n")


def _write_additional_v4_1_subgroup(
    additional_path: Path,
    detector_paths: tuple[Path, ...],
    detector_paths_HV: tuple[Path, ...],
    detector_paths_CAV: tuple[Path, ...],
    detector_frequency: int,
    first_edge: str,
    detector_pos: float,
    num_lanes: int,
    performance_path: Path,
    performance_HV_path: Path,
    performance_CAV_path: Path,
    emissions_path: Path,
    emissions_HV_path: Path,
    emissions_CAV_path: Path,
    sim_end_time: float,
    edge_data_freq: int,
    *,
    with_internal: bool = True,
) -> None:
    """写入 schema=2 多测量子群附加 XML（all / HV / CAV）"""
    internal_attr = ' withInternal="true"' if with_internal else ""
    with additional_path.open("w", encoding="utf-8") as f:
        f.write("<additional>\n")
        # E1 检测器: all
        for lane_idx in range(num_lanes):
            f.write(
                f'    <e1Detector id="det_l{lane_idx}" lane="{first_edge}_{lane_idx}" '
                f'pos="{detector_pos:.1f}" freq="{detector_frequency}" '
                f'file="{detector_paths[lane_idx].name}"/>\n'
            )
        # E1 检测器: HV
        for lane_idx in range(num_lanes):
            f.write(
                f'    <e1Detector id="det_l{lane_idx}_HV" lane="{first_edge}_{lane_idx}" '
                f'pos="{detector_pos:.1f}" freq="{detector_frequency}" '
                f'file="{detector_paths_HV[lane_idx].name}" vTypes="HV"/>\n'
            )
        # E1 检测器: CAV
        for lane_idx in range(num_lanes):
            f.write(
                f'    <e1Detector id="det_l{lane_idx}_CAV" lane="{first_edge}_{lane_idx}" '
                f'pos="{detector_pos:.1f}" freq="{detector_frequency}" '
                f'file="{detector_paths_CAV[lane_idx].name}" vTypes="CAV"/>\n'
            )
        # edgeData performance: all
        f.write(
            f'    <edgeData id="ed_perf" type="performance" file="{performance_path.name}" '
            f'freq="{edge_data_freq}" begin="0" end="{int(sim_end_time)}" '
            f'excludeEmpty="true"{internal_attr}/>\n'
        )
        # edgeData performance: HV
        f.write(
            f'    <edgeData id="ed_perf_HV" type="performance" '
            f'file="{performance_HV_path.name}" '
            f'freq="{edge_data_freq}" begin="0" end="{int(sim_end_time)}" '
            f'excludeEmpty="true"{internal_attr} vTypes="HV"/>\n'
        )
        # edgeData performance: CAV
        f.write(
            f'    <edgeData id="ed_perf_CAV" type="performance" '
            f'file="{performance_CAV_path.name}" '
            f'freq="{edge_data_freq}" begin="0" end="{int(sim_end_time)}" '
            f'excludeEmpty="true"{internal_attr} vTypes="CAV"/>\n'
        )
        # edgeData emissions: all
        f.write(
            f'    <edgeData id="ed_emis" type="emissions" file="{emissions_path.name}" '
            f'freq="{edge_data_freq}" begin="0" end="{int(sim_end_time)}" '
            f'excludeEmpty="true"{internal_attr}/>\n'
        )
        # edgeData emissions: HV
        f.write(
            f'    <edgeData id="ed_emis_HV" type="emissions" '
            f'file="{emissions_HV_path.name}" '
            f'freq="{edge_data_freq}" begin="0" end="{int(sim_end_time)}" '
            f'excludeEmpty="true"{internal_attr} vTypes="HV"/>\n'
        )
        # edgeData emissions: CAV
        f.write(
            f'    <edgeData id="ed_emis_CAV" type="emissions" '
            f'file="{emissions_CAV_path.name}" '
            f'freq="{edge_data_freq}" begin="0" end="{int(sim_end_time)}" '
            f'excludeEmpty="true"{internal_attr} vTypes="CAV"/>\n'
        )
        f.write("</additional>\n")


def build_sumo_command(
    prepared: PreparedRun,
    network_file: str,
    spec,
    sumo_command: str = "sumo",
) -> list:
    """SUMO 命令行（纯净分支 v0.4.2 唯一；v0.4.0 基与 v0.4.1 变体已合并）。

    - 主 factorial（ssm_enabled=False）：不注入任何 --device.ssm.*，ssm.xml 意图性缺失；
    - safety（ssm_enabled=True）：注入 SSM capture（measures/thresholds/range/trajectories/extratime）。
    """
    cmd = [
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
        str(int(spec.simulation_end)),
        "--step-length",
        str(spec.step_length),
        "--no-step-log",
        "true",
        "--device.ssm.probability",
        "1.0",
        "--device.ssm.file",
        str(prepared.ssm_path),
        "--lanechange-output",
        str(prepared.lanechange_path),
        "--vehroute-output",
        str(prepared.vehroute_path),
        "--vehroute-output.exit-times",
        "true",
        "--vehroute-output.write-unfinished",
        "true",
    ]
    cmd.extend(
        [
            "--seed",
            str(spec.sumo_seed),
            "--device.ssm.measures",
            "TTC DRAC",
            "--device.ssm.thresholds",
            f"{spec.ssm_capture_ttc_threshold_s} {spec.ssm_capture_drac_threshold_mps2}",
            "--device.ssm.range",
            str(spec.ssm_range_m),
            "--device.ssm.trajectories",
            "true" if spec.ssm_trajectories else "false",
            # 无条件显式传 extratime（含默认 5.0），不依赖 SUMO 隐式默认
            "--device.ssm.extratime",
            str(spec.ssm_extratime_s),
        ]
    )
    # FCD 选项
    if spec.fcd_profile is not None:
        period = 1 if spec.fcd_profile == "1s" else 0.1
        fcd_path = prepared.run_dir / "fcd.xml.gz"
        cmd.extend(
            [
                "--fcd-output",
                str(fcd_path),
                "--fcd-output.attributes",
                "id,type,speed,lane,pos,leaderID,leaderGap",
                "--fcd-output.max-leader-distance",
                str(spec.fcd_max_leader_distance_m or 0),
                "--device.fcd.begin",
                str(int(spec.warmup)),
                "--device.fcd.period",
                str(period),
            ]
        )
    if not spec.ssm_enabled:
        cmd = _without_ssm_device_options(cmd)
    return cmd


def _without_ssm_device_options(cmd: list) -> list:
    """移除全部 --device.ssm.* 选项及其值，返回新列表（P0-1 主 factorial SSM-off）。"""
    out: list = []
    i = 0
    while i < len(cmd):
        arg = cmd[i]
        if arg.startswith("--device.ssm.") or arg == "--device.ssm":
            # 跳过该选项；若下一项不是选项，则一并跳过（选项值）
            i += 1
            if i < len(cmd) and not cmd[i].startswith("-"):
                i += 1
            continue
        out.append(arg)
        i += 1
    return out


# ═══════════════════════════════════════════════════════════════════
# 单次仿真（CLI 入口 + 完整解析管线）
# ═══════════════════════════════════════════════════════════════════


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
    # 收敛审核 P1（Phase 3 加固）：测量设置不再静默使用 RunSpec 出厂默认
    # （with_internal=False / ssm_enabled=False / fcd=None——与 A 方案主网格
    # configs/v0.4.2/main.json 不一致：不同 veh-km 分母、无 SSM/FCD 采集）。
    # 默认值现与主网格对齐（with_internal=true、SSM 全开、fcd="1s"、
    # TTC=3.0/range=50/dedup greedy），可按需传参覆盖。
    with_internal: bool = True,
    ssm_enabled: bool = True,
    fcd_profile: str | None = "1s",
    sumo_seed: int = 0,
    ssm_capture_ttc_threshold_s: float = 3.0,
    ssm_capture_drac_threshold_mps2: float = 3.0,
    ssm_range_m: float = 50.0,
    ssm_extratime_s: float = 5.0,
    ssm_trajectories: bool = False,
    analysis_ttc_threshold_s: float = 3.0,
    analysis_drac_threshold_mps2: float = 3.0,
    ssm_dedup_method: str = "greedy_one_to_one_80pct",
    ssm_mirror_overlap_ratio: float = 0.8,
    ssm_fragment_merge_gap_s: float = 0.0,
    fcd_max_leader_distance_m: float = 4000.0,
):
    """使用与批处理相同的仿真、解析和 writer 链路执行一个 run。"""
    from scripts.parsing.runner import parse_one_run
    from scripts.results.writer import build_run_level_results
    from scripts.simulation.batch_run import run_sumo_process

    net_meta = load_network_meta(network_file)
    net_scenario = net_meta["scenario"]
    # 纯净分支：build_run_id 仅 cav_count 格式（cav_count 从请求渗透率取整推导）
    cav_count = round(vehicle_count * cav_ratio)
    run_id = build_run_id(
        net_scenario,
        model,
        cav_ratio,
        vehicle_count,
        seed,
        cav_count=cav_count,
        assignment_seed=seed,
        # 审查 P2-2：run_id 用实际 sumo_seed（原硬编码 0——程序化传非 0 seed 时
        # 不同 seed 的单跑写同一 raw 目录、CSV 静默覆盖）。
        sumo_seed=sumo_seed,
    )
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
        "pipeline_version": "v0.4.2",
        "schema_version": "2",
        # 收敛审核 P2：单跑 resolved_config 补齐测量设置字段（与 RunSpec 构造
        # 同源）——config_sha256 语义完整（单跑自身一致；与 batch 因 entrypoint
        # 与 treatments 差异本就不等价，独立工具不影响主网格）。
        "with_internal": with_internal,
        "ssm_enabled": ssm_enabled,
        "fcd_profile": fcd_profile,
        "ssm_capture_ttc_threshold_s": ssm_capture_ttc_threshold_s,
        "ssm_capture_drac_threshold_mps2": ssm_capture_drac_threshold_mps2,
        "ssm_range_m": ssm_range_m,
        "ssm_extratime_s": ssm_extratime_s,
        "ssm_trajectories": ssm_trajectories,
        "analysis_ttc_threshold_s": analysis_ttc_threshold_s,
        "analysis_drac_threshold_mps2": analysis_drac_threshold_mps2,
        "ssm_dedup_method": ssm_dedup_method,
        "ssm_mirror_overlap_ratio": ssm_mirror_overlap_ratio,
        "ssm_fragment_merge_gap_s": ssm_fragment_merge_gap_s,
        "fcd_max_leader_distance_m": fcd_max_leader_distance_m,
        "sumo_seed": sumo_seed,
    }
    config_sha256 = hashlib.sha256(canonical_json(resolved_config).encode("utf-8")).hexdigest()
    network_sha256 = sha256_file(network_file)
    experiment_id = f"single-{config_sha256[:12]}-{network_sha256[:12]}"

    # 纯净分支：single_run 单跑（v0.4.2，与 batch 同架构）——cav_count 取整（run_id
    # 生成处已算）、pcav 用 realized、requested_pcav 保持 None（D3：内部字段，与
    # batch cav_count 路径一致；请求比例不可表示时（round(vn×r)/vn≠r）若存请求值会
    # 导致 from_dict 自读不一致 raise）。
    realized_pcav = cav_count / vehicle_count

    spec = RunSpec(
        scenario=net_scenario,
        model=model,
        pcav=realized_pcav,
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
        pipeline_version=PIPELINE_V4_2,
        schema_version="2",
        cav_count=cav_count,
        requested_pcav=None,
        sumo_seed=sumo_seed,
        with_internal=with_internal,
        ssm_enabled=ssm_enabled,
        fcd_profile=fcd_profile,
        ssm_capture_ttc_threshold_s=ssm_capture_ttc_threshold_s,
        ssm_capture_drac_threshold_mps2=ssm_capture_drac_threshold_mps2,
        ssm_range_m=ssm_range_m,
        ssm_extratime_s=ssm_extratime_s,
        ssm_trajectories=ssm_trajectories,
        analysis_ttc_threshold_s=analysis_ttc_threshold_s,
        analysis_drac_threshold_mps2=analysis_drac_threshold_mps2,
        ssm_dedup_method=ssm_dedup_method,
        ssm_mirror_overlap_ratio=ssm_mirror_overlap_ratio,
        ssm_fragment_merge_gap_s=ssm_fragment_merge_gap_s,
        fcd_max_leader_distance_m=fcd_max_leader_distance_m,
    )

    # 收敛审核 P2：single_run 与 batch 共用 FCD 采集距离校验（batch 在
    # validate_environment 中调用，single_run 不经过该流程——此处显式补齐）。
    if spec.fcd_profile is not None:
        from scripts.parsing.runner import validate_fcd_leader_distance

        validate_fcd_leader_distance(spec, network_file)

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
        # 收敛审核 P1（Phase 3 加固）：build_sumo_command 恒注入
        # --seed <spec.sumo_seed>（single_run sentinel 默认 0）——旧文案
        # "SUMO default; no --seed passed" 与实际行为不符。
        "sumo_seed_mode": f"explicit --seed {sumo_seed} (single_run sentinel; SUMO randomness fixed)",
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
    # 审查 P2-1：warmup/freq/edge_data_frequency 组合预校验（prepare_run 的
    # validate_analysis_windows 要求 warmup 同时整除 detector 与 edge_data 频率；
    # 此处 argparse 层给出明确提示，而非仿真启动后抛错）。
    if args.warmup % args.freq != 0 or args.warmup % DEFAULT_EDGEDATA_FREQ != 0:
        parser.error(
            f"warmup={args.warmup} 必须是 detector_frequency={args.freq} 与 "
            f"edge_data_frequency={DEFAULT_EDGEDATA_FREQ} 的整数倍"
        )

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
    # 审查 P2-6：single_run 产物 manifest 不含 treatments，不支持 aggregate——
    # CLI 层提示，避免用户误喂 aggregate 后报晦涩错误。
    print(
        "\n提示：single_run 产物为独立工具格式（manifest 无 treatments），"
        "不支持 aggregate 聚合；请使用 batch_run 正式网格产物。"
    )


if __name__ == "__main__":
    main()
