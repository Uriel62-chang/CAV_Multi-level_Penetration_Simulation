"""v0.4.2 分析层统一编排入口（数据零重跑：只消费 aggregated_results.csv）。

依次运行 7 模块 + 双 Phase Diagram，产物：
- CSV → out/analysis/（descriptive/effect_size/interaction/threshold/pareto/sensitivity）
- 图 → graph/v0.4.2/chart_phase_diagrams.png

用法：
  python3 -m scripts.analysis.run \
    --input out/aggregated_results.csv \
    --output-dir out/analysis \
    --chart-dir graph/v0.4.2
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.analysis import (
    benefit_phase_diagram,
    descriptive_analysis,
    effect_size,
    interaction_analysis,
    pareto_analysis,
    sensitivity_analysis,
    threshold_detection,
)
from scripts.analysis.common import ensure_dir, load_aggregated

MODULE_ORDER = (
    "descriptive_analysis",
    "effect_size",
    "interaction_analysis",
    "threshold_detection",
    "benefit_phase_diagram",
    "pareto_analysis",
    "sensitivity_analysis",
)


def run_all(
    df,
    output_dir: str | Path,
    chart_dir: str | Path,
    interpolate: bool = False,
    modules: tuple[str, ...] = MODULE_ORDER,
) -> dict[str, dict[str, Path]]:
    """运行指定分析模块（默认全部），返回 {模块: {产物名: 路径}}。"""
    out = ensure_dir(output_dir)
    ensure_dir(chart_dir)
    results: dict[str, dict[str, Path]] = {}
    for name in modules:
        if name == "descriptive_analysis":
            results[name] = descriptive_analysis.analyze(df, out)
        elif name == "effect_size":
            results[name] = effect_size.analyze(df, out)
        elif name == "interaction_analysis":
            results[name] = interaction_analysis.analyze(df, out)
        elif name == "threshold_detection":
            results[name] = threshold_detection.analyze(df, out, interpolate=interpolate)
        elif name == "benefit_phase_diagram":
            results[name] = benefit_phase_diagram.analyze(df, chart_dir)
        elif name == "pareto_analysis":
            results[name] = pareto_analysis.analyze(df, out)
        elif name == "sensitivity_analysis":
            results[name] = sensitivity_analysis.analyze(df, out)
        else:
            raise ValueError(f"未知分析模块: {name}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="v0.4.2 分析层（7 模块 + 双 Phase Diagram）")
    parser.add_argument("--input", default="out/aggregated_results.csv", help="aggregated CSV")
    parser.add_argument(
        "--output-dir", default="out/analysis", help="CSV 产物目录（默认 out/analysis）"
    )
    parser.add_argument(
        "--chart-dir", default="graph/v0.4.2", help="图产物目录（默认 graph/v0.4.2）"
    )
    parser.add_argument(
        "--interpolate",
        action="store_true",
        help="阈值检测额外输出插值细值（标注'估计/探索性插值'，非档位口径）",
    )
    parser.add_argument(
        "--modules",
        nargs="+",
        default=list(MODULE_ORDER),
        help=f"仅运行指定模块（默认全部: {' '.join(MODULE_ORDER)}）",
    )
    args = parser.parse_args()

    df = load_aggregated(args.input)
    results = run_all(
        df,
        args.output_dir,
        args.chart_dir,
        interpolate=args.interpolate,
        modules=tuple(args.modules),
    )
    total = sum(len(v) for v in results.values())
    print(
        f"\n[DONE] analysis layer: {len(results)} modules, {total} artifacts → "
        f"{Path(args.output_dir).resolve()} + {Path(args.chart_dir).resolve()}"
    )


if __name__ == "__main__":
    main()
