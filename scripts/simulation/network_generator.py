import argparse
import json
import math
import os
import subprocess
from pathlib import Path


def generate_polygon_loop(
    scenario_dir: str, num_sides: int, radius: float, num_lanes: int, speed: float
) -> dict:
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
    node_lines = ["<nodes>"]
    for i in range(num_sides):
        angle = 2.0 * math.pi * i / num_sides
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        node_lines.append(f'    <node id="n{i}" x="{x:.2f}" y="{y:.2f}" type="priority"/>')
    node_lines.append("</nodes>")

    node_path = os.path.join(scenario_dir, "nodes.nod.xml")
    with open(node_path, "w", encoding="utf-8") as f:
        f.write("\n".join(node_lines))

    # ---------- 生成边文件 ----------
    edge_lines = ["<edges>"]
    for i in range(num_sides):
        next_node = (i + 1) % num_sides
        edge_lines.append(
            f'    <edge id="e{i}" from="n{i}" to="n{next_node}" '
            f'numLanes="{num_lanes}" speed="{speed}"/>'
        )
    edge_lines.append("</edges>")

    edge_path = os.path.join(scenario_dir, "edges.edg.xml")
    with open(edge_path, "w", encoding="utf-8") as f:
        f.write("\n".join(edge_lines))

    # ---------- 生成元数据文件 ----------
    total_length = num_sides * edge_length
    edge_ids = [f"e{i}" for i in range(num_sides)]
    legal_lanes = list(range(num_lanes))
    meta = {
        "schema_version": "1",
        "scenario": os.path.basename(scenario_dir),
        "num_sides": num_sides,
        "num_lanes": num_lanes,
        "radius_m": round(radius, 2),
        "edge_length_m": round(edge_length, 4),
        "total_length_m": round(total_length, 4),
        "total_length_km": round(total_length / 1000.0, 6),
        "edge_ids": edge_ids,
        "route_edge_ids": edge_ids,
        "detector_edge_id": edge_ids[0],
        "detector_position_m": round(edge_length / 2.0, 4),
        "bottleneck_edge_ids": [],
        "edge_lane_counts": {"default": num_lanes, "overrides": {}},
        "legal_initial_lanes": {"default": legal_lanes, "overrides": {}},
        "speed_mps": speed,
    }

    meta_path = os.path.join(scenario_dir, "net.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"路网源文件已生成: {scenario_dir}/ (nodes.nod.xml, edges.edg.xml, net.json)")
    print(
        f"  边数={num_sides}  车道数={num_lanes}  边长={edge_length:.2f}m  "
        f"环路总长={total_length:.2f}m  ({total_length / 1000:.3f}km)"
    )
    return meta


def build_network(scenario_dir: str | Path, netconvert_command: str = "netconvert") -> Path:
    """从已跟踪的 node/edge 源文件编译 SUMO `loop.net.xml`。"""
    directory = Path(scenario_dir)
    node_path = directory / "nodes.nod.xml"
    edge_path = directory / "edges.edg.xml"
    output_path = directory / "loop.net.xml"
    for path in (node_path, edge_path):
        if not path.is_file():
            raise FileNotFoundError(f"network source not found: {path}")
    subprocess.run(
        [
            netconvert_command,
            "--node-files",
            str(node_path),
            "--edge-files",
            str(edge_path),
            "--output-file",
            str(output_path),
        ],
        check=True,
    )
    # 审阅 P2-1：源文件变更检测——net.json 若锚定 network_sources_sha256 则强校验；
    # 未锚定则警告（消除"源文件修改后元数据静默过期"）。不自动重建 net.json
    # （其包含 bottleneck/detector 等场景专属元数据，需人工核对）。
    import hashlib
    import json as _json

    digest = hashlib.sha256()
    for path in (node_path, edge_path):
        digest.update(path.read_bytes())
    sources_sha256 = digest.hexdigest()
    net_json_path = directory / "net.json"
    if net_json_path.exists():
        meta = _json.loads(net_json_path.read_text(encoding="utf-8"))
        anchored = meta.get("network_sources_sha256")
        if anchored is None:
            print(
                f"[WARN] {net_json_path} 未锚定 network_sources_sha256；"
                f"源文件若已修改请核对元数据（当前源 SHA {sources_sha256[:12]}...）"
            )
        elif anchored != sources_sha256:
            raise RuntimeError(
                f"{net_json_path} 锚定的源 SHA {anchored[:12]}... 与当前源 "
                f"{sources_sha256[:12]}... 不一致——路网元数据可能过期，请核对/更新 net.json"
            )
    print(f"SUMO 路网已编译: {output_path}")
    return output_path


def build_all_networks(
    parent_dir: str | Path, netconvert_command: str = "netconvert"
) -> list[Path]:
    """编译 parent_dir 下所有包含已跟踪源文件的 scenario 目录。"""
    parent = Path(parent_dir)
    scenario_dirs = sorted(
        path
        for path in parent.glob("scenario_*")
        if (path / "nodes.nod.xml").is_file() and (path / "edges.edg.xml").is_file()
    )
    if not scenario_dirs:
        raise FileNotFoundError(f"no scenario sources found under: {parent}")
    return [build_network(path, netconvert_command) for path in scenario_dirs]


def main():
    parser = argparse.ArgumentParser(description="生成多边形闭环路网源文件")
    parser.add_argument("--scenario", default="scenario_1", help="场景目录名 (默认: scenario_1)")
    parser.add_argument("--sides", type=int, default=32, help="多边形边数 (默认: 32)")
    parser.add_argument("--radius", type=float, default=1000.0, help="外接圆半径/m (默认: 1000)")
    parser.add_argument("--lanes", type=int, default=1, help="车道数 (默认: 1)")
    parser.add_argument(
        "--speed", type=float, default=33.33, help="限速 m/s (默认: 33.33 ≈ 120km/h)"
    )
    parser.add_argument("--outdir", default="net", help="输出父目录 (默认: net)")
    parser.add_argument(
        "--build-all",
        action="store_true",
        help="从 outdir 下已跟踪的四场景源文件编译 loop.net.xml",
    )
    parser.add_argument("--netconvert", default="netconvert", help="netconvert 可执行文件")
    args = parser.parse_args()

    if args.build_all:
        build_all_networks(args.outdir, args.netconvert)
        return

    scenario_dir = os.path.join(args.outdir, args.scenario)
    generate_polygon_loop(scenario_dir, args.sides, args.radius, args.lanes, args.speed)
    build_network(scenario_dir, args.netconvert)


if __name__ == "__main__":
    main()
