import argparse
import xml.etree.ElementTree as ET

def main():
    # 设置命令行位置参数
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", required=True) 
    ap.add_argument("--warmup", type=float, default=600.0) # 预热期
    args = ap.parse_args()

    root = ET.parse(args.xml).getroot() # 解析xml文件并拿到根节点
    flows, speeds = [], []
    # 获取解析器每 60s 的数据，筛除处于预热器的数据
    for itv in root.findall("interval"):
        begin = float(itv.get("begin", "0"))
        if begin < args.warmup:
            continue
        flow = float(itv.get("flow", "0"))   # 流量（veh/h）
        spd  = float(itv.get("speed", "0"))  # 速度（m/s）
        flows.append(flow); speeds.append(spd) 

    if len(flows) == 0:
        print("0,0,0")
        return
    # 计算并打印有效期断面车流的：平均流量、峰值流量、平均速度
    print(f"{sum(flows)/len(flows):.3f},{max(flows):.3f},{sum(speeds)/len(speeds):.3f}")

if __name__ == "__main__":
    main()
