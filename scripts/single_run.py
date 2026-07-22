import argparse
import json
import os
import sys
import subprocess
import pandas as pd

# 将当前文件的所在目录的上级目录（项目根目录）加入到系统搜索路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.flow_generator import generate_flow
from scripts.detector_parser import parse_detector, parse_detector_multi
from scripts.config import (
    DEFAULT_DETECTOR_FREQ, DEFAULT_STEP_LENGTH, DEFAULT_SIM_END, DEFAULT_WARMUP,
    CAV_MODELS,
)

DETECTOR_CONFIG_DIR = "add"
ROUTES_DIR = "routes"
DEFAULT_NETWORK_FILE = "net/scenario_0/loop.net.xml"

# 默认路网元数据（向后兼容：无 net.json 时使用）
_LEGACY_NET_META = {
    "edge_ids": ["e0", "e1", "e2", "e3"],
    "edge_length_m": 500.0,
    "num_lanes": 1,
}


def load_network_meta(network_file: str) -> dict:
    """从路网文件所在目录读取 net.json 元数据

    若 net.json 不存在，则回退到旧版方形环路默认值。
    """
    net_dir = os.path.dirname(network_file)
    meta_path = os.path.join(net_dir, "net.json")
    if os.path.isfile(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return _LEGACY_NET_META


def _generate_detector_config(detector_xml_paths: list,
                               frequency: int = DEFAULT_DETECTOR_FREQ,
                               first_edge: str = "e0", detector_pos: float = 250.0) -> str:
    """生成 SUMO e1 检测器附加文件（add/det_tmp.add.xml）

    单车道（num_lanes=1）生成 1 个 e1Detector；
    多车道时按 lane_idx 循环生成，每条车道一个独立检测器输出文件。
    """
    os.makedirs(DETECTOR_CONFIG_DIR, exist_ok=True)
    config_path = os.path.join(DETECTOR_CONFIG_DIR, "det_tmp.add.xml")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write('<additional>\n')
        for lane_idx, xml_path in enumerate(detector_xml_paths):
            f.write(
                f'    <e1Detector id="det_l{lane_idx}" lane="{first_edge}_{lane_idx}" '
                f'pos="{detector_pos:.1f}" freq="{frequency}" file="{xml_path}"/>\n'
            )
        f.write('</additional>\n')
    return config_path


def run_simulation(vehicle_count: int, cav_ratio: float, seed: int,
                   loops: int = 300, sim_end_time: int = DEFAULT_SIM_END,
                   warmup_period: int = DEFAULT_WARMUP,
                   detector_frequency: int = DEFAULT_DETECTOR_FREQ,
                   sumo_command: str = "sumo", output_csv: str = "out/results_raw.csv",
                   model: str = "IDM", network_file: str = DEFAULT_NETWORK_FILE):
    """编排一次完整仿真：生成车流 → SUMO 仿真 → 解析检测器 → 写入 CSV

    返回 None；结果追加写入 output_csv，检测器 XML 留存于 {stem}_e1/ 子目录。
    """
    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    os.makedirs(ROUTES_DIR, exist_ok=True)

    # 检测器输出目录：--outcsv out/results_s2_IDM.csv → out/results_s2_IDM_e1/
    det_dir = os.path.splitext(output_csv)[0] + "_e1"
    os.makedirs(det_dir, exist_ok=True)

    # 读取路网元数据
    net_meta = load_network_meta(network_file)
    edge_ids = net_meta.get("edge_ids", _LEGACY_NET_META["edge_ids"])
    edge_length = net_meta.get("edge_length_m", _LEGACY_NET_META["edge_length_m"])
    edge_count = len(edge_ids)
    net_scenario = net_meta.get("scenario", "scenario_0")
    num_lanes = net_meta.get("num_lanes", 1)
    first_edge = edge_ids[0]
    # 检测器置于第一条边的中点
    detector_pos = edge_length / 2.0

    print(f"\n[RUN CONFIG]")
    print(f"  scenario    = {net_scenario}")
    print(f"  model       = {model}")
    print(f"  vehN        = {vehicle_count}")
    print(f"  pCAV        = {cav_ratio}")
    print(f"  seed        = {seed}")
    print(f"  freq        = {detector_frequency}")
    print(f"  warmup      = {warmup_period}\n")

    run_id = f"{net_scenario}_{model}_vehN{vehicle_count}_p{int(round(cav_ratio * 100)):03d}_seed{seed}"
    route_file = os.path.join(ROUTES_DIR, f"{run_id}.rou.xml")  # 本次仿真生成的车流
    detector_outputs = [os.path.join(det_dir, f"{run_id}_e1_l{l}.xml")
                        for l in range(num_lanes)]
    detector_outputs_abs = [os.path.abspath(p) for p in detector_outputs]

    # 调用flow_generator生成本次仿真的混合车流
    generate_flow(vehicle_count, cav_ratio, loops, seed, route_file, model,
                  edge_count=edge_count, edge_length=edge_length,
                  scenario=net_scenario, num_lanes=num_lanes)

    # 生成本次仿真的检测器（可自设频率）
    detector_config = _generate_detector_config(
        detector_outputs_abs, detector_frequency,
        first_edge=first_edge, detector_pos=detector_pos)

    # SUMO仿真
    try:
        subprocess.check_call([
            sumo_command,
            "-n", network_file,
            "-r", route_file,
            "-a", detector_config,
            "-b", "0",
            "-e", str(sim_end_time),
            "--step-length", str(DEFAULT_STEP_LENGTH),
            "--no-step-log", "true"
        ])
    except FileNotFoundError:
        print(f"[ERR] SUMO 未找到: {sumo_command}")
        return
    except subprocess.CalledProcessError as e:
        print(f"[ERR] SUMO 异常退出: {e}")
        return

    # 仿真结束，调用detector_parser解析检测器采集到的数据
    if num_lanes > 1:
        mean_flow, max_flow, mean_speed = parse_detector_multi(
            detector_outputs, warmup_period)
    else:
        mean_flow, max_flow, mean_speed = parse_detector(
            detector_outputs[0], warmup_period)

    # 保存仿真生数据
    columns = ["run_id", "vehN", "pCAV", "seed", "model", "detector_freq",
               "mean_flow(veh/h)", "max_flow(veh/h)", "mean_speed(m/s)", "det_xml"]
    det_xml_all = ";".join(detector_outputs)
    row_data = [run_id, vehicle_count, cav_ratio, seed, model, detector_frequency,
                mean_flow, max_flow, mean_speed, det_xml_all]
    result_df = pd.DataFrame(data=[row_data], columns=columns)

    # 导出csv文件（若文件存在且不为空，则不增加表头）
    write_header = not (os.path.isfile(output_csv) and os.path.getsize(output_csv) > 0)
    result_df.to_csv(output_csv, mode="a", header=write_header, index=False, encoding="utf-8")

    # 输出日志
    print(f"[OK] {run_id} mean_flow={mean_flow} veh/h, det={detector_outputs[0]}")


def main():
    # 设置命令行位置参数
    parser = argparse.ArgumentParser()
    parser.add_argument("--vehN", type=int, required=True)  # 车辆数
    parser.add_argument("--pCAV", type=float, required=True)  # CAV渗透率
    parser.add_argument("--seed", type=int, default=1)  # 随机种子
    parser.add_argument("--loops", type=int, default=300)  # 每辆车的路线循环次数
    parser.add_argument("--end", type=int, default=DEFAULT_SIM_END)  # 仿真结束时间
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)  # 预热期
    parser.add_argument("--freq", type=int, default=DEFAULT_DETECTOR_FREQ)  # 检测器统计频率
    parser.add_argument("--sumo", default="sumo")  # sumo命令，也可以是sumo-gui
    parser.add_argument("--outcsv", default="out/results_raw.csv")  # 生数据输出路径（csv文件）
    parser.add_argument("--model", type=str, default="IDM", choices=list(CAV_MODELS),
                        help="CAV跟驰模型: IDM / ACC / CACC")
    parser.add_argument("--net", default=DEFAULT_NETWORK_FILE,
                        help=f"路网文件路径 (默认: {DEFAULT_NETWORK_FILE})")
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
