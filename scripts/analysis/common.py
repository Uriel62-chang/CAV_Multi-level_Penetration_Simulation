"""v0.4.2 分析层公共基础设施（数据零重跑：只消费 aggregated_results.csv）。

四口径定稿（analysis-layer-v042-design.md §四）在此落地：
1. **Baseline 双概念**：通用 Δ 指标族（Δ>0 = CACC 收益）之上定义
   - Δq_model = q_CACC,p − q_IDM,p（同渗透率控制模型差异，主 Phase Diagram）
   - Δq_abs   = q_CACC,p − q_HV,0（纯 HV 基线绝对收益，第二张图）
   - 两语义独立命名、并列解读不强行选 baseline。
2. **p=0 sentinel**：p=0 仅纯 HV/IDM 有物理意义，不构造 "CACC@p=0"；
   model×pCAV 比较限定 p>0；p=0 仅作公共 HV reference。
3. **n=9 不升级强推断**：interior cell 仅 9 观测——以效应量 + 区间估计 +
   稳健性/一致性为主；区间为**跨 seed 等权描述性区间**（正态近似，非正式
   显著性检验）；正式推断需增加 seed 数并显式升级统计口径。
4. **p* 档位粒度**：p 为 0.1 步长 → 报告 `p* ∈ (0.5, 0.6]` 而非 `p*=0.537`；
   插值细值仅标"估计/探索性插值"。

符号约定（统一收益方向，Δ>0 = CACC 更优）：
- flow（越高越好）：    Δ = v_CACC − v_baseline
- delay / 事件率 / 排放（越低越好）：Δ = v_baseline − v_CACC
（设计文档四口径 1 的 Δsafety = safety_CACC − safety_baseline 以"安全性能"语义
书写；实现中 safety 使用事件率列 ttc_per_k_mean / drac_per_k_mean，收益方向为
事件率下降——与 Δq 同向，"Δ>0 收益"约定保持一致。）
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# ═══════════════════════════════════════════════════════════════════
# 常量与口径
# ═══════════════════════════════════════════════════════════════════

# 分析层只处理正式网格的 model 维度（IDM / CACC）；ACC 非正式比较对象，不入分析层。
ANALYSIS_MODELS = ("IDM", "CACC")
# 基线语义（口径定稿 1）在 compute_delta_frame 中内联：baseline_model = 同 p 的
# IDM 行；baseline_abs = p=0 的 IDM（纯 HV）行——不设独立常量，避免死代码。

# 渗透率档位步长（口径文档常量：cav_count 0.1 步长 11 档；档位值由数据 pCAV 列
# 驱动，p* 档位区间表达见 p_star_interval）
P_STEP = 0.1

# 描述性区间 z 值（正态近似；非正式推断——口径定稿 3）
INTERVAL_Z = 1.96
# 双 seed 统计单位（口径定稿 3）：interior n=9 = 3 assignment × 3 sumo；端点
# p=0 时 assignment_seed 失活 → n=3。实际 n 以 aggregated CSV 的
# REPLICATION_COLUMN 列值为准（load_aggregated 对非 {3,9} 值发警告）。

# ═══════════════════════════════════════════════════════════════════
# 指标族规格
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class MetricSpec:
    """分析指标族：聚合列 + 收益方向（higher = 越高越好）。"""

    column: str  # aggregated CSV 列名（_mean 后缀）
    direction: str  # "higher" | "lower"
    label: str  # 人类可读标签（Phase Diagram 轴/图例）

    @property
    def higher_is_better(self) -> bool:
        return self.direction == "higher"


# 有序：flow 为主指标（Phase Diagram 用），delay/safety/emission 为次指标。
METRIC_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec("flow", "higher", "Flow (veh/h)"),
    MetricSpec("delay", "lower", "Mean lap delay (s)"),
    MetricSpec("delay_p95", "lower", "p95 lap delay (s)"),
    MetricSpec("ttc_per_k", "lower", "TTC events per 1000 veh-km"),
    MetricSpec("drac_per_k", "lower", "DRAC events per 1000 veh-km"),
    MetricSpec("co2_per_k", "lower", "CO2 per veh-km (g)"),
    MetricSpec("fuel_per_k", "lower", "Fuel per veh-km (g)"),
)

# 聚合 CSV 中缺失可选列时自动跳过的次指标（如 delay_p95 / drac_per_k / fuel_per_k）；
# 主指标（flow / delay / ttc_per_k / co2_per_k）缺失时 fail-closed。
CORE_METRICS = ("flow", "delay", "ttc_per_k", "co2_per_k")

# 每车道流量口径：aggregate 派生列 flow_per_lane = flow_mean / 车道数；分析层
# Δq 主展示用 per-lane（与 FD/visualization 口径一致），由 flow 统计列派生。
LANE_MAP = {
    "scenario_0": 1,
    "scenario_1": 1,
    "scenario_2": 2,
    "scenario_3": 2,
}

# 分析层输入契约列（除指标列外）
IDENTITY_COLUMNS = (
    "scenario",
    "model",
    "vehN",
    "pCAV",
    "realized_pcav",
    "density_veh_per_km_lane",
)
# 区间估计所需统计列
STAT_COLUMNS = ("_mean", "_std", "_min", "_max", "_count")
REPLICATION_COLUMN = "independent_random_replication_count"


class AnalysisInputError(ValueError):
    """分析层输入契约违规（fail-closed，不得静默降级）。"""


# ═══════════════════════════════════════════════════════════════════
# 数据加载与校验
# ═══════════════════════════════════════════════════════════════════


def load_aggregated(path: str | Path) -> pd.DataFrame:
    """加载 aggregated_results.csv 并做输入契约校验（fail-closed）。

    - 校验 experiment_role == main_factorial（含分析层在内的 v0.4.2 主网格契约）；
    - 校验必需标识列与主指标列存在；
    - 校验 model 维度 ⊆ {IDM, CACC} 且 CACC 无 p=0 行（p=0 sentinel 契约）。
    """
    df = pd.read_csv(path)
    if "experiment_role" in df.columns:
        roles = sorted(str(r) for r in df["experiment_role"].dropna().unique())
        if roles and roles != ["main_factorial"]:
            raise AnalysisInputError(
                f"分析层需要 experiment_role=main_factorial 的聚合 CSV，实际含 {roles}"
            )
    missing = [c for c in IDENTITY_COLUMNS if c not in df.columns]
    if missing:
        raise AnalysisInputError(f"聚合 CSV 缺少标识列: {missing}")
    missing_core = [
        f"{s.column}_mean"
        for s in METRIC_SPECS
        if s.column in CORE_METRICS and f"{s.column}_mean" not in df.columns
    ]
    if missing_core:
        raise AnalysisInputError(f"聚合 CSV 缺少主指标列: {missing_core}")
    missing_stat = [
        f"{s.column}{suffix}"
        for s in METRIC_SPECS
        if f"{s.column}_mean" in df.columns
        for suffix in STAT_COLUMNS
        if f"{s.column}{suffix}" not in df.columns and f"{s.column}{suffix}" != f"{s.column}_count"
    ]
    # aggregate 对 flow 的 count 列特例重命名为 n_valid（契约；其余指标为 {short}_count）
    if "flow_count" not in df.columns and "n_valid" not in df.columns:
        missing_stat.append("flow_count/n_valid")
    if missing_stat:
        raise AnalysisInputError(f"聚合 CSV 缺少统计列: {missing_stat[:8]}...")
    if REPLICATION_COLUMN not in df.columns:
        raise AnalysisInputError(f"聚合 CSV 缺少 {REPLICATION_COLUMN} 列")

    present_models = sorted(set(df["model"].dropna().unique()))
    unknown = [m for m in present_models if m not in ANALYSIS_MODELS]
    if unknown:
        raise AnalysisInputError(f"分析层仅处理 IDM/CACC（正式网格），CSV 含非正式模型: {unknown}")
    # 口径定稿 3 的 n=9/端点 n=3 是 U55 网格事实，而非硬性契约；非 {3,9} 时
    # 警告（未来 seed 数变化仍可分析，SE 传播按实际 n 计算）。
    reps = sorted(set(df[REPLICATION_COLUMN].dropna().unique()))
    if reps and not set(reps) <= {3, 9}:
        print(
            f"[WARN] {REPLICATION_COLUMN} 取值 {reps} 非 U55 网格的 {{3, 9}}——"
            "n=9 描述性口径假设需在报告中重新声明"
        )
    # p=0 sentinel：pCAV==0 的行必须 model==IDM（CACC@p=0 无物理意义）
    zero_p = df[df["pCAV"] == 0.0]
    bad_zero = set(zero_p["model"].dropna().unique()) - {"IDM"}
    if bad_zero:
        raise AnalysisInputError(f"p=0 sentinel 契约被破坏：非 IDM 模型含 p=0 行: {bad_zero}")
    return df


def available_specs(df: pd.DataFrame) -> tuple[MetricSpec, ...]:
    """按数据中存在性过滤指标族（可选次指标缺失时自动跳过）。"""
    return tuple(s for s in METRIC_SPECS if f"{s.column}_mean" in df.columns)


# ═══════════════════════════════════════════════════════════════════
# Δ 指标族（baseline 双概念）
# ═══════════════════════════════════════════════════════════════════


def _benefit_delta(v_cacc: pd.Series, v_base: pd.Series, higher: bool) -> pd.Series:
    """统一收益方向 Δ：Δ>0 = CACC 更优。"""
    return (v_cacc - v_base) if higher else (v_base - v_cacc)


def compute_delta_frame(df: pd.DataFrame) -> pd.DataFrame:
    """构造 Δ 长表：每 (scenario, density, pCAV>0) 行相对两个 baseline 的 Δ 指标族。

    列：scenario / density_veh_per_km_lane / pCAV + 每指标 × {model, abs} 的
    {delta, delta_lo, delta_hi, min, max, n_cacc, n_base, consistent}。

    - baseline_model：同 (scenario, density, pCAV) 的 IDM 行（p>0 才构造）；
    - baseline_abs：同 (scenario, density) 的纯 HV 行（pCAV=0, model=IDM）；
    - 区间：SE_Δ = sqrt(std_CACC²/n_CACC + std_base²/n_base)，Δ ± z·SE
      （跨 seed 等权描述性区间，正态近似——口径定稿 3）；
    - consistent：跨 seed 全范围一致（min>0 全收益 / max<0 全反转 / 跨 0 临界）。
    """
    df = df.copy()
    p_col = "pCAV"
    dens_col = "density_veh_per_km_lane"

    cacc = df[(df["model"] == "CACC") & (df[p_col] > 0.0)].copy()
    idm = df[df["model"] == "IDM"].copy()
    hv = idm[idm[p_col] == 0.0].copy()

    rows = []
    for (sc, dens), grp in cacc.groupby(["scenario", dens_col], sort=False):
        # 同密度 p 对齐：CACC p 行 vs IDM 同 p 行（baseline_model）
        idm_same = idm[(idm["scenario"] == sc) & (idm[dens_col] == dens)]
        hv_same = hv[(hv["scenario"] == sc) & (hv[dens_col] == dens)]
        if hv_same.empty:
            # 纯 HV baseline 缺失：该 (scenario, density) 无 p=0 行——契约违规
            raise AnalysisInputError(f"(scenario={sc}, density={dens}) 缺 p=0 纯 HV reference 行")
        hv_row = hv_same.iloc[0]
        for _, c_row in grp.iterrows():
            p = float(c_row[p_col])
            idm_row = idm_same[idm_same[p_col] == p]
            if idm_row.empty:
                # 同 p 的 IDM 行缺失（网格不对称）——fail-closed，不静默跳过
                raise AnalysisInputError(
                    f"(scenario={sc}, density={dens}, pCAV={p}) 缺同渗透率 IDM 行"
                )
            idm_row = idm_row.iloc[0]
            rec = {
                "scenario": sc,
                "density_veh_per_km_lane": dens,
                "pCAV": p,
                "n_cacc": int(c_row[REPLICATION_COLUMN]),
                "n_idm": int(idm_row[REPLICATION_COLUMN]),
                "n_hv": int(hv_row[REPLICATION_COLUMN]),
            }
            for spec in available_specs(df):
                col = spec.column
                higher = spec.higher_is_better
                # baseline_model（同 p IDM）
                _push_delta(rec, f"{col}_model", c_row, idm_row, col, higher)
                # baseline_abs（纯 HV）
                _push_delta(rec, f"{col}_abs", c_row, hv_row, col, higher)
            rows.append(rec)
    out = pd.DataFrame(rows)
    # 每车道流量 Δ（Phase Diagram / 阈值主口径）：flow 统计列 / 车道数——
    # 与 FD 口径一致；Δq=0 交叉点与 total 尺度等价（车道数固定）。
    if "flow_model_delta" in out.columns:
        out["flow_per_lane_model_delta"] = out.apply(
            lambda r: r["flow_model_delta"] / LANE_MAP.get(r["scenario"], 1), axis=1
        )
    if "flow_abs_delta" in out.columns:
        out["flow_per_lane_abs_delta"] = out.apply(
            lambda r: r["flow_abs_delta"] / LANE_MAP.get(r["scenario"], 1), axis=1
        )
    return out


def _push_delta(
    rec: dict,
    out_prefix: str,
    c_row: pd.Series,
    b_row: pd.Series,
    col: str,
    higher: bool,
) -> None:
    """向 rec 写入 {prefix}_delta / _delta_lo / _delta_hi / _min / _max / _consistent。"""
    v_c = float(c_row[f"{col}_mean"])
    v_b = float(b_row[f"{col}_mean"])
    delta = v_c - v_b if higher else v_b - v_c

    n_c = int(c_row[REPLICATION_COLUMN])
    n_b = int(b_row[REPLICATION_COLUMN])
    se = np.sqrt(
        float(c_row[f"{col}_std"]) ** 2 / max(n_c, 1)
        + float(b_row[f"{col}_std"]) ** 2 / max(n_b, 1)
    )
    lo = delta - INTERVAL_Z * se
    hi = delta + INTERVAL_Z * se

    # 跨 seed 全范围（min/max 保守组合）
    if higher:
        rng_min = float(c_row[f"{col}_min"]) - float(b_row[f"{col}_max"])
        rng_max = float(c_row[f"{col}_max"]) - float(b_row[f"{col}_min"])
    else:
        rng_min = float(b_row[f"{col}_min"]) - float(c_row[f"{col}_max"])
        rng_max = float(b_row[f"{col}_max"]) - float(c_row[f"{col}_min"])
    if rng_min > 0:
        consistent = "gain"  # 所有 seed 组合下 CACC 均更优
    elif rng_max < 0:
        consistent = "reversal"  # 所有 seed 组合下 CACC 均更差
    else:
        consistent = "mixed"  # 跨 0：临界/不一致

    rec[f"{out_prefix}_delta"] = delta
    rec[f"{out_prefix}_delta_lo"] = lo
    rec[f"{out_prefix}_delta_hi"] = hi
    rec[f"{out_prefix}_min"] = rng_min
    rec[f"{out_prefix}_max"] = rng_max
    rec[f"{out_prefix}_consistent"] = consistent


# ═══════════════════════════════════════════════════════════════════
# 档位区间表达（口径定稿 4）
# ═══════════════════════════════════════════════════════════════════


def p_star_interval(p_lo: float, p_hi: float) -> str:
    """p* 档位区间表达：报告 `p* ∈ (0.5, 0.6]` 而非插值细值（一位小数）。"""
    return f"({p_lo:.1f}, {p_hi:.1f}]"


def format_p_star(p_lo: float | None, p_hi: float | None) -> str:
    """边界外无交叉时的语义表达。

    - 全部档位 Δ>0：`p* ≤ 0.1`（最低测试渗透率已正收益）；
    - 全部档位 Δ<0：`p* > 1.0`（测试范围内未达正收益）。
    """
    if p_lo is None or p_hi is None:
        return ""
    return p_star_interval(p_lo, p_hi)


# ═══════════════════════════════════════════════════════════════════
# 通用输出
# ═══════════════════════════════════════════════════════════════════


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_csv(df: pd.DataFrame, path: str | Path, label: str) -> Path:
    out = Path(path)
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"[WRITE] {label}: {len(df)} rows → {out}")
    return out
