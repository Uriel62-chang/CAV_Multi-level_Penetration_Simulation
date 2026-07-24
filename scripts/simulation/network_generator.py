import argparse
import json
import math
import os


def generate_polygon_loop(scenario_dir: str, num_sides: int, radius: float,
                           num_lanes: int, speed: float) -> dict:
    """生成多边形闭环路网源文件（nodes.nod.xml, edges.edg.xml, net.json）

    Args:
        scenario_dir: 输出目录，如 "net/scenario_1"
        num_sides: 多边形边数（16 或 32）
        radius: 外接圆半径 (m)
        num_lanes: 车道数
        speed: 限速 (m/s)

    Returns:
        dict: 路网元数据
    """
    os.makedirs(scenario_dir, exist_ok=True)

    # 边长（弦长）
    edge_length = 2.0 * radius * math.sin(math.pi / num_sides)

    # ---------- 生成节点文件 ----------
    node_lines = ['<nodes>']
    for i in range(num_sides):
        angle = 2.0 * math.pi * i / num_sides
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        node_lines.append(
            f'    <node id="n{i}" x="{x:.2f}" y="{y:.2f}" type="priority"/>'
        )
    node_lines.append('</nodes>')

    node_path = os.path.join(scenario_dir, "nodes.nod.xml")
    with open(node_path, "w", encoding="utf-8") as f:
        f.write("\n".join(node_lines))

    # ---------- 生成边文件 ----------
    edge_lines = ['<edges>']
    for i in range(num_sides):
        next_node = (i + 1) % num_sides
        edge_lines.append(
            f'    <edge id="e{i}" from="n{i}" to="n{next_node}" '
            f'numLanes="{num_lanes}" speed="{speed}"/>'
        )
    edge_lines.append('</edges>')

    edge_path = os.path.join(scenario_dir, "edges.edg.xml")
    with open(edge_path, "w", encoding="utf-8") as f:
        f.write("\n".join(edge_lines))

    # ---------- 生成元数据文件 ----------
    total_length = num_sides * edge_length
    meta = {
        "scenario": os.path.basename(scenario_dir),
        "num_sides": num_sides,
        "num_lanes": num_lanes,
        "radius_m": round(radius, 2),
        "edge_length_m": round(edge_length, 4),
        "total_length_m": round(total_length, 4),
        "total_length_km": round(total_length / 1000.0, 6),
        "edge_ids": [f"e{i}" for i in range(num_sides)],
        "speed_mps": speed,
    }

    meta_path = os.path.join(scenario_dir, "net.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"路网源文件已生成: {scenario_dir}/ (nodes.nod.xml, edges.edg.xml, net.json)")
    print(f"  边数={num_sides}  车道数={num_lanes}  边长={edge_length:.2f}m  "
          f"环路总长={total_length:.2f}m  ({total_length/1000:.3f}km)")
    return meta


def main():
    parser = argparse.ArgumentParser(description="生成多边形闭环路网源文件")
    parser.add_argument("--scenario", default="scenario_1",
                        help="场景目录名 (默认: scenario_1)")
    parser.add_argument("--sides", type=int, default=32,
                        help="多边形边数 (默认: 32)")
    parser.add_argument("--radius", type=float, default=1000.0,
                        help="外接圆半径/m (默认: 1000)")
    parser.add_argument("--lanes", type=int, default=1,
                        help="车道数 (默认: 1)")
    parser.add_argument("--speed", type=float, default=33.33,
                        help="限速 m/s (默认: 33.33 ≈ 120km/h)")
    parser.add_argument("--outdir", default="net",
                        help="输出父目录 (默认: net)")
    args = parser.parse_args()

    scenario_dir = os.path.join(args.outdir, args.scenario)
    generate_polygon_loop(scenario_dir, args.sides, args.radius,
                           args.lanes, args.speed)


if __name__ == "__main__":
    main()
