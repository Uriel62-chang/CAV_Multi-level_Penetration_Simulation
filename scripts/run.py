import argparse, os, subprocess
import pandas as pd

def write_detector_add(det_xml_abs: str, freq: int = 60):
    os.makedirs("add", exist_ok=True)
    path = "add/det_tmp.add.xml"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f'''<additional>
    <e1Detector id="det0" lane="e0_0" pos="250" freq="{freq}" file="{det_xml_abs}"/>
</additional>
''')
    return path

def main():
    # 设置命令行位置参数
    ap = argparse.ArgumentParser()
    ap.add_argument("--vehN", type=int, required=True) # 车辆数
    ap.add_argument("--pCAV", type=float, required=True) # CAV渗透率
    ap.add_argument("--seed", type=int, default=1) # 随机种子
    ap.add_argument("--loops", type=int, default=300) # 每辆车的路线循环次数
    ap.add_argument("--end", type=int, default=3600) # 仿真结束时间
    ap.add_argument("--warmup", type=int, default=600) # 预热期
    ap.add_argument("--freq", type=int, default=60) # 检测器统计频率
    ap.add_argument("--sumo", default="sumo") # sumo命令，也可以是sumo-gui
    ap.add_argument("--outcsv", default="out/results_raw.csv") # 生数据输出路径（csv文件）
    args = ap.parse_args()

    os.makedirs("out", exist_ok=True)
    os.makedirs("routes", exist_ok=True)


    run_id = f"vehN{args.vehN}_p{int(round(args.pCAV*100)):03d}_seed{args.seed}" # 本次仿真的id
    rou = f"routes/{run_id}.rou.xml" # 本次仿真生成的车流
    det_xml = f"out/{run_id}_e1.xml" # 本次仿真生成的检测器
    det_xml_abs = os.path.abspath(det_xml) # 检测器的绝对路径（write_detector_add()需要）

    # 调用阶段1实现的脚本：scripts/FlowGenerate.py生成本次仿真的混合车流
    subprocess.check_call([
        "python3", "scripts/FlowGenerate.py",
        "--vehN", str(args.vehN),
        "--pCAV", str(args.pCAV),
        "--loops", str(args.loops),
        "--seed", str(args.seed),
        "--out", rou
    ])

    # 生成本次仿真的检测器（可自设频率）
    det_add = write_detector_add(det_xml_abs, args.freq)

    # sumo仿真
    subprocess.check_call([
        args.sumo,
        "-n", "net/loop.net.xml", # 阶段1生成的路网文件
        "-r", rou, # 本次仿真生成的车流
        "-a", det_add, # 本次仿真生成的检测器
        "-b", "0", # 本次仿真的起始时间
        "-e", str(args.end), # 本次仿真的终止时间
        "--no-step-log", "true" # 不打印每一步的日志
    ])

    '''
    仿真结束
    '''

    # 调用阶段2实现的脚本：scripts/e1Parser.py解析检测器采集到的数据，将其存储进列表out
    out = subprocess.check_output([
        "python3", "scripts/e1Parser.py",
        "--xml", det_xml, # 本次仿真生成的检测器
        "--warmup", str(args.warmup) # 预热期
    ], text=True).strip()
    mean_flow, max_flow, mean_speed = out.split(",") # 获取平均流量、峰值流量、平均速度

    # 保存仿真生数据
    col = ["run_id",     "vehN",    "pCAV",    "seed", "mean_flow(veh/h)", "max_flow(veh/h)", "mean_speed(m/s)", "det_xml"]
    row = [  run_id,  args.vehN, args.pCAV, args.seed,          mean_flow,          max_flow,        mean_speed,  det_xml ]
    df = pd.DataFrame(data=[row], columns=col)

    with open(args.outcsv, "a+", encoding="utf-8", newline="") as f:
        f.seek(0, 2)                 # 移到文件末尾
        need_header = (f.tell() == 0)
        df.to_csv(f, header=need_header, index=False)

    print(f"[OK] {run_id} mean_flow={mean_flow} veh/h, det={det_xml}")

if __name__ == "__main__":
    main()
