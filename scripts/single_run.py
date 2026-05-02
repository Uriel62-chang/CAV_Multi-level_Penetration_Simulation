import argparse
import os
import sys
import subprocess
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.flow_generator import generate_flow
from scripts.detector_parser import parse_detector

DETECTOR_CONFIG_DIR = "add"
OUTPUT_DIR = "out"
ROUTES_DIR = "routes"
NETWORK_FILE = "net/loop.net.xml"


def _generate_detector_config(detector_xml_abs: str, frequency: int = 60) -> str:
    os.makedirs(DETECTOR_CONFIG_DIR, exist_ok=True)
    config_path = os.path.join(DETECTOR_CONFIG_DIR, "det_tmp.add.xml")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(
            f'<additional>\n'
            f'    <e1Detector id="det0" lane="e0_0" pos="250" freq="{frequency}" file="{detector_xml_abs}"/>\n'
            f'</additional>\n'
        )
    return config_path


def run_simulation(vehicle_count: int, cav_ratio: float, seed: int,
                   loops: int = 300, sim_end_time: int = 3600,
                   warmup_period: int = 600, detector_frequency: int = 60,
                   sumo_command: str = "sumo", output_csv: str = "out/results_raw.csv"):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(ROUTES_DIR, exist_ok=True)

    run_id = f"vehN{vehicle_count}_p{int(round(cav_ratio * 100)):03d}_seed{seed}"  # 本次仿真的id
    route_file = os.path.join(ROUTES_DIR, f"{run_id}.rou.xml")  # 本次仿真生成的车流
    detector_output = os.path.join(OUTPUT_DIR, f"{run_id}_e1.xml")  # 本次仿真生成的检测器
    detector_output_abs = os.path.abspath(detector_output)  # 检测器的绝对路径

    # 调用flow_generator生成本次仿真的混合车流
    generate_flow(vehicle_count, cav_ratio, loops, seed, route_file)

    # 生成本次仿真的检测器（可自设频率）
    detector_config = _generate_detector_config(detector_output_abs, detector_frequency)

    # SUMO仿真
    subprocess.check_call([
        sumo_command,
        "-n", NETWORK_FILE,  # 路网文件
        "-r", route_file,  # 本次仿真生成的车流
        "-a", detector_config,  # 本次仿真生成的检测器
        "-b", "0",  # 本次仿真的起始时间
        "-e", str(sim_end_time),  # 本次仿真的终止时间
        "--no-step-log", "true"
    ])

    # 仿真结束，调用detector_parser解析检测器采集到的数据
    mean_flow, max_flow, mean_speed = parse_detector(detector_output, warmup_period)

    # 保存仿真生数据
    columns = ["run_id", "vehN", "pCAV", "seed", "mean_flow(veh/h)", "max_flow(veh/h)", "mean_speed(m/s)", "det_xml"]
    row_data = [run_id, vehicle_count, cav_ratio, seed, mean_flow, max_flow, mean_speed, detector_output]
    result_df = pd.DataFrame(data=[row_data], columns=columns)

    write_header = not (os.path.isfile(output_csv) and os.path.getsize(output_csv) > 0)
    result_df.to_csv(output_csv, mode="a", header=write_header, index=False, encoding="utf-8")

    # 输出日志
    print(f"[OK] {run_id} mean_flow={mean_flow} veh/h, det={detector_output}")


def main():
    # 设置命令行位置参数
    parser = argparse.ArgumentParser()
    parser.add_argument("--vehN", type=int, required=True)  # 车辆数
    parser.add_argument("--pCAV", type=float, required=True)  # CAV渗透率
    parser.add_argument("--seed", type=int, default=1)  # 随机种子
    parser.add_argument("--loops", type=int, default=300)  # 每辆车的路线循环次数
    parser.add_argument("--end", type=int, default=3600)  # 仿真结束时间
    parser.add_argument("--warmup", type=int, default=600)  # 预热期
    parser.add_argument("--freq", type=int, default=60)  # 检测器统计频率
    parser.add_argument("--sumo", default="sumo")  # sumo命令，也可以是sumo-gui
    parser.add_argument("--outcsv", default="out/results_raw.csv")  # 生数据输出路径（csv文件）
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
    )


if __name__ == "__main__":
    main()
