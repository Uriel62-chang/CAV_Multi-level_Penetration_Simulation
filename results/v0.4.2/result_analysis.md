# v0.4.2 正式网格结果分析（结构化摘要）

> 数据：`results/v0.4.2/{main,safety}/aggregated_results.csv`（schema=2，双 seed 统计单位）
> 状态：main 3,888 runs / 528 组、safety 84 runs / 84 组，全部 data_quality=ok，writer complete=true
> 图：`graph/v0.4.2/`（main 3 张 + safety 按 scenario × vehN 分面）
> 口径说明：流量/排放主强度用 non-internal 配对；全路网次要强度用 `wn_*` 列；Safety 每格仅 1 个 seed pair，结果为描述性。

## 1. 主 factorial：各场景网格内最大观测流量

| 场景 | 模型 | vehN | realized p | 流量 (veh/h) | 与 v0.4.0 对照 |
|---|---|---|---|---:|---|
| s0 | CACC | 90 | 1.0 | 1,856.4 | = v0.4.0 1,856 ✓ |
| s1 | CACC | 70 | 1.0 | 4,178.4 | v0.4.0 4,344.96 @ v90 p0.95（分辨率压缩差异，见 §4）|
| s2 | CACC | 120 | 1.0 | **7,128.0** | = v0.4.0 7,128 ✓ |
| s3 | IDM | 80 | 1.0 | 3,902.4 | = v0.4.0 3,902 ✓ |

s2 高渗透率（v120）：CACC cav=96/120 → 6,166 / 7,128；IDM → 5,647 / 6,276。CACC 的测试网格内最大观测流量优势在 s2 全 CAV 端点复现（+13.6%）。

## 2. s3 高密度全 CAV 运行点（v120）：瓶颈反转

| 模型 | 流量 (veh/h) | delay (s) | non-internal CO₂ (g/veh-km) | 全路网 CO₂ (g/veh-km) |
|---|---:|---:|---:|---:|
| IDM | 3,204 | 74.2 | 260.8 | 244.1 |
| CACC | 1,536 | 215.8 | 426.6 | 400.0 |

IDM 流量约为 CACC 2.1 倍、delay 约 1/3、排放强度更低——v0.4.0 定性结论复现。排放仅作 v0.4.2 内部 IDM/CACC 比较（口径与 v0.4.0 不同，不做跨版本变化率）。

## 3. Safety：TTC 事件率随渗透率（按 vehN 分层，每格 1 seed，描述性）

- **s0**：p=1.0 端点事件率数值上明显上升（v30: IDM/CACC ~1,952；v60: 5,855/3,905；v120: 3,939/1,951），与 s0 急弯周期制动一致；vehN 与渗透率效应叠加，须分面阅读。单 seed 描述性结果，不作置信/显著性推断。
- **s3**：v120 事件率随 p 单调上升（IDM 843→1,445、CACC 897→3,006）；v30/v60 的 p=1.0 端点反而为 0（该格无 TTC 事件，单 seed 描述性结果）。
- **s1 与 s2 均未检出 TTC 事件**（s1 max ttc_per_k_mean=0.0、s2 非零组=0）；仅表示当前 TTC<3.0 s 阈值、SUMO 1.27.1、Safety 网格、单 seed 和现有 SSM 配置下未检测到，不升级为「无安全冲突」。

## 4. 跨版本（v0.4.2 vs v0.4.0）比较边界

- **精确复现**：s0/s2/s3 网格峰值与 s3 高密度全 CAV 运行点（flow/delay）与 v0.4.0 数值一致。
- **非全网格一致**：Reviewer 对 528 个共享键独立比较——flow 完全相同 96/528、1% 内 315/528、最大绝对差 337.55 veh/h；delay 中位相对差约 6.0%；CO₂ 无相同项。
- **差异来源（可预期，非错误）**：① 渗透率分辨率 21 档→6 档（s1 峰值从 v90 p0.95 移到 v70 p1.0）；② seed 设计（assignment 3 + SUMO 3 独立维度 vs v0.4.0 仅 assignment 5）；③ 暴露量口径 withInternal=true + non-internal 主强度。
- **排放**：只做 v0.4.2 内部 IDM/CACC 比较；v0.4.0 的 352/228 与 v0.4.2 的 426.6/260.8 口径不同，不计算变化率。
- **s1 安全事件跨版本不可直接比较**：v0.4.0 的 s1 TTC 场景累计 9,109.2（各处理组合 assignment-seed 均值之和，8 个非零组）vs v0.4.2 Safety 网格 s1 21 组全零——v0.4.2 Safety 每格仅 1 个 seed pair、vehN∈{30,60,120} 子采样，与 v0.4.0 完整网格 × 5 assignment seed 采样设计不同；零检出不构成「s1 无冲突」的跨版本结论。

## 5. Subgroup（HV/CAV 分拆）

数据：`results/v0.4.2/main/run_level_subgroup_results.csv`（长表）+ `aggregate_subgroup` 按 (scenario, model, vehN, cav_count, family, group, metric) 聚合（mean 跨 9 个 seed 组合）。示例运行点 vehN=120、cav=96（HV 24 辆 / CAV 96 辆——HV 子群流量与 veh_km 低首先与 24:96 车辆组成有关；单凭总量不能断言不存在单位车辆性能差异；`co2_ni` 为每类车辆强度）：

| 场景 模型 v120 cav=96 | 子群 | flow (veh/h) | veh_km | non-internal CO₂ (g/veh-km) |
|---|---|---|---:|---:|
| s2 IDM | HV | 1,080 | 2,107 | 169.7 |
| s2 IDM | CAV | 4,567 | 8,903 | 171.3 |
| s2 CACC | HV | 1,222 | 2,383 | 177.5 |
| s2 CACC | CAV | 4,944 | 9,638 | 176.8 |
| s3 IDM | HV | 451 | 879 | 319.4 |
| s3 IDM | CAV | 1,836 | 3,579 | 308.3 |
| s3 CACC | HV | 321 | 626 | 383.0 |
| s3 CACC | CAV | 1,286 | 2,506 | 407.0 |

要点（描述性）：在 s2、vehN=120、cav=96 这一运行点，各模型内部 HV/CAV 的 non-internal CO₂ 强度接近（IDM 169.7/171.3、CACC 177.5/176.8）；在 s3 同运行点，CACC 的 CAV 子群强度（407.0）高于 HV（383.0），IDM 反之（CAV 308.3 < HV 319.4）。这些是单运行点描述性观察，不能凭一个 treatment 点分解模型差异的成因。端点 run（cav=0/vehN）空子群强度为规则化 NaN（见 writer NaN 规则），未列入。子群拆分是 v0.4.2 新增维度，本表为描述性摘要，不替代逐指标全表。

## 6. 边界声明

- Safety 每格 1 个 seed pair：结果为描述性，不做显著性/置信推断。
- **s1 与 s2 零事件**：全路网 TTC 事件率（ttc_per_k）分母为 withInternal=true 全路网 veh-km，空间配对；仅表示当前 TTC<3.0 s 阈值、SUMO 1.27.1、网格与 SSM 配置下未检测到，不升级为「无安全冲突」。

## 7. 2026-08 重解析修订（P0-1/P0-2 数据正确性）

- **p95 delay 修正**：修复前 v0.4.2 的 p95 delay 统一使用 HV 自由流参考
  （all-level p95 − HV_ref）。修复后逐 lap 按车辆类型减对应参考再 pooled 求
  分位数（CAV 用 CAV_model ref）。影响 120/528 聚合键（差异 >1s，最大 20.2s），
  全 CAV/高 CAV CACC 组修正最大；全 CAV CACC 代表性样例 s0 v90 c90：
  delay_p95 4.6 → 24.8 s。mean delay、流量、排放与 safety TTC 结论不变
  （528 键 flow_mean / delay_mean / CO₂ 强度完全相等）。
- **SSM 未采集语义**：main factorial（3,888 runs）不配置 SSM device
  （意图性缺失），修复前 TTC 计数/事件率以 0 呈现，现改为 NaN 且
  ssm_not_collected=True（run-level CSV 新增 experiment_role / ssm_enabled /
  ssm_not_collected 状态列）；聚合层面 ttc_mean=NaN、count=0。safety
  （84 runs）不受影响（合法零检出仍为 0）。
- **图**：graph/v0.4.2/ 4 张图字节级不变（图使用 mean delay 与独立 safety
  TTC，不受上述两项修正影响）。
- **输入完整性**：3,972 个旧 run 的 stderr.log 哈希通过重解析前生成的
  input_integrity.sidecar.json（purpose=pre-reparse freeze）补全，
  未回填 simulation_status.json（不回填仿真时证据）。
