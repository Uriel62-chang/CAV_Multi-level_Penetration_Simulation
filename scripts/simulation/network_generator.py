import argparse
import json
import math
import os
import subprocess
from pathlib import Path


def generate_polygon_loop(
    scenario_dir: str,
    num_sides: int,
    radius: float,
    num_lanes: int,
    speed: float,
    edge_lane_overrides: dict | None = None,
    bottleneck_edge_ids: list | None = None,
    force: bool = False,
) -> dict:
    """生成多边形闭环路网源文件（nodes.nod.xml, edges.edg.xml, net.json）

    复现已提交场景：s3 = 32 边形、radius=318.82、num_lanes=2、speed=33.33、
    bottleneck e15/e16（单车道）——CLI：
      --scenario scenario_3 --sides 32 --radius 318.82 --lanes 2 --speed 33.33
      --bottleneck-edges e15,e16 --force
    （s0/s1/s2 无瓶颈，不带 --bottleneck-edges 即可。）

    Args:
        scenario_dir: 输出目录，如 "net/scenario_1"
        num_sides: 多边形边数（16 或 32）
        radius: 外接圆半径 (m)
        num_lanes: 车道数
        speed: 限速 (m/s)
        edge_lane_overrides: per-edge 车道覆盖（如 {"e15": 1, "e16": 1}，
            用于 s3 瓶颈），覆盖边 id 必须合法
        bottleneck_edge_ids: 瓶颈边列表（写入 net.json 元数据；
            未在 edge_lane_overrides 中显式给出的瓶颈边默认单车道）
        force: 目标目录已被 sources.sha256 锚定（被跟踪/受保护源文件）时，
            必须显式 force=True 才允许覆盖重新生成

    Returns:
        dict: 路网元数据
    """
    from pathlib import Path

    directory = Path(scenario_dir)
    if (directory / "sources.sha256").exists() and not force:
        raise RuntimeError(
            f"{scenario_dir} 已被 sources.sha256 锚定（被跟踪/受保护的路网源文件）；"
            f"裸调用覆盖会破坏路网源一致性链——如确需重新生成请显式 --force"
        )
    os.makedirs(scenario_dir, exist_ok=True)

    # per-edge 车道覆盖：显式覆盖优先，瓶颈边缺省单车道
    effective_overrides = dict(edge_lane_overrides or {})
    for bid in bottleneck_edge_ids or []:
        effective_overrides.setdefault(bid, 1)
    valid_ids = {f"e{i}" for i in range(num_sides)}
    unknown = sorted(set(effective_overrides) - valid_ids)
    if unknown:
        raise ValueError(
            f"edge_lane_overrides 含非法边 id: {unknown}（合法范围 e0..e{num_sides - 1}）"
        )

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
        lanes = effective_overrides.get(f"e{i}", num_lanes)
        edge_lines.append(
            f'    <edge id="e{i}" from="n{i}" to="n{next_node}" '
            f'numLanes="{lanes}" speed="{speed}"/>'
        )
    edge_lines.append("</edges>")

    edge_path = os.path.join(scenario_dir, "edges.edg.xml")
    with open(edge_path, "w", encoding="utf-8") as f:
        f.write("\n".join(edge_lines))

    # ---------- 生成元数据文件 ----------
    total_length = num_sides * edge_length
    edge_ids = [f"e{i}" for i in range(num_sides)]
    legal_lanes = list(range(num_lanes))
    lane_overrides = {k: v for k, v in sorted(effective_overrides.items()) if v != num_lanes}
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
        "bottleneck_edge_ids": list(bottleneck_edge_ids or []),
        "edge_lane_counts": {"default": num_lanes, "overrides": lane_overrides},
        "legal_initial_lanes": {
            "default": legal_lanes,
            "overrides": {k: list(range(v)) for k, v in lane_overrides.items()},
        },
        "speed_mps": speed,
    }

    meta_path = os.path.join(scenario_dir, "net.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    # 审阅 P2-2（本轮）：生成场景同时写入 sources.sha256——build_network() 强制要求
    # 该锚定文件存在（否则"生成并编译"流程失败）
    import hashlib as _h

    digest = _h.sha256()
    for name in ("nodes.nod.xml", "edges.edg.xml"):
        with open(os.path.join(scenario_dir, name), "rb") as f:
            digest.update(f.read())
    with open(os.path.join(scenario_dir, "sources.sha256"), "w", encoding="utf-8") as f:
        f.write(digest.hexdigest() + "\n")

    print(
        f"路网源文件已生成: {scenario_dir}/ (nodes.nod.xml, edges.edg.xml, net.json, sources.sha256)"
    )
    print(
        f"  边数={num_sides}  车道数={num_lanes}  边长={edge_length:.2f}m  "
        f"环路总长={total_length:.2f}m  ({total_length / 1000:.3f}km)"
    )
    return meta


def build_network(scenario_dir: str | Path, netconvert_command: str = "netconvert") -> Path:
    """从已跟踪的 node/edge 源文件编译 SUMO `loop.net.xml`。

    审阅 P2-2：先校验 net.json 锚定的源 SHA（未锚定/不匹配直接失败），再执行
    netconvert——不产生"新 XML + 旧元数据"的中间状态。
    """
    import hashlib

    directory = Path(scenario_dir)
    node_path = directory / "nodes.nod.xml"
    edge_path = directory / "edges.edg.xml"
    output_path = directory / "loop.net.xml"
    for path in (node_path, edge_path):
        if not path.is_file():
            raise FileNotFoundError(f"network source not found: {path}")

    # 审阅 P1-1 / P2-2：源文件变更检测前置——net.json 不得承载锚定（其为已归档 raw
    # 证据，字节被 simulation_status 锚定，修改会破坏证据链）；锚定存于独立文件
    # sources.sha256（缺失或与当前源不匹配均抛 RuntimeError，强制门禁）。
    digest = hashlib.sha256()
    for path in (node_path, edge_path):
        digest.update(path.read_bytes())
    sources_sha256 = digest.hexdigest()
    anchor_path = directory / "sources.sha256"
    if not anchor_path.exists():
        raise RuntimeError(
            f"{anchor_path} 缺失——路网源一致性无法验证；"
            f"请将当前源 SHA {sources_sha256[:12]}... 写入 {anchor_path.name} 后重试"
        )
    anchored = anchor_path.read_text(encoding="utf-8").strip()
    if anchored != sources_sha256:
        raise RuntimeError(
            f"{anchor_path} 锚定的源 SHA {anchored[:12]}... 与当前源 "
            f"{sources_sha256[:12]}... 不一致——路网元数据可能过期，请核对/更新锚定"
        )

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
        help="从 outdir 下已跟踪的四场景源文件编译 loop.net.xml（只编译，不生成/不覆盖源文件）",
    )
    parser.add_argument(
        "--bottleneck-edges",
        default=None,
        help="瓶颈边列表（逗号分隔，如 e15,e16；缺省单车道并写入 net.json）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="允许覆盖已被 sources.sha256 锚定的路网源文件（裸调用默认拒绝）",
    )
    parser.add_argument("--netconvert", default="netconvert", help="netconvert 可执行文件")
    args = parser.parse_args()

    if args.build_all:
        build_all_networks(args.outdir, args.netconvert)
        return

    bottleneck_ids = (
        [e.strip() for e in args.bottleneck_edges.split(",") if e.strip()]
        if args.bottleneck_edges
        else None
    )
    scenario_dir = os.path.join(args.outdir, args.scenario)
    generate_polygon_loop(
        scenario_dir,
        args.sides,
        args.radius,
        args.lanes,
        args.speed,
        bottleneck_edge_ids=bottleneck_ids,
        force=args.force,
    )
    build_network(scenario_dir, args.netconvert)


if __name__ == "__main__":
    main()
