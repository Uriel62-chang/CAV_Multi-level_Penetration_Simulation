# Changelog

## v0.4.2 (2026-08，跳号发布)

> **跳号发布说明**：v0.4.1 是本地内部里程碑，**未对外发布**（Level 2 pilot 未过旧资源
> 门禁；D-012–D-015 技术证据已闭合、治理状态未闭合，本地 tag 已删）。其全部工程成果
> 并入本版发布说明。本版为 v0.4.0.post3 之后的下一公开版本。

### 发布状态（2026-08，正式发布完成）

- **结果 ship**：`results/v0.4.2/main/aggregated_results.csv`（924 组 × 329 列）
  纳入公开仓库；raw 76 GB / run-level / subgroup 留外部备份。
- **报告**：`docs/report.cn.md`（中文）+ `docs/report.en.md`（英文）正式实验报告；
  README 重写为 U55 正式口径（英文），挂 `graph/v0.4.2/` 5 图。
- **管线审查十轮收敛**：无 P0/P1 代码逻辑缺陷（前四轮代码层收敛、第五至十轮
  发布文档/图产物/数据出处层收敛；2 项 P2 与后续文档级 P1（s3 模型归属/吞吐
  口径/subgroup 重解析等）均已修复或文档化闭环）。
- **发布动作（用户手动）**：tag v0.4.2、push main + tag、GitHub release——按
  `docs/engineering/release-checklist.md` 执行。

### 分析层（2026-08，v0.4.2 统计分析组件，管线审查背书）

- **`scripts/analysis/` 7 模块**（全部结果只消费 shipped aggregated CSV，单一
  数据源、无额外仿真）：
  descriptive_analysis（描述统计增强，替代 mixed_effects 分层描述角色）/
  effect_size（Δ 指标族 + Cohen's d 变体 + 跨 seed 描述性区间）/ interaction_analysis
  （p×density、model×scenario、model×density、三阶分解）/ threshold_detection
  （Δq=0 交叉点 + p*(k,s)/k*(p,s) 档位区间）/ benefit_phase_diagram（双 Phase
  Diagram：Model Effect + Absolute Benefit 并列）/ pareto_analysis（四维 Pareto
  Front，无人工权重，同 (scenario,density) 组内比较）/ sensitivity_analysis
  （口径替代 + 阈值邻域稳定性）。
- **四口径定稿落地**：baseline 双概念（Δq_model / Δq_abs 不混用）；p=0 sentinel
  （模型比较限定 p>0）；n=9 效应量+区间+一致性（非正式推断）；p* 档位区间表达
  （`p* ∈ (0.5, 0.6]`，插值细值仅 --interpolate 且标注估计）。
- **核心产出**：双 Phase Diagram（`graph/v0.4.2/chart_phase_diagrams.png`，挂
  README Core Results）+ p*/k* 阈值表 + Pareto front + 敏感性；s3 高密度
  k∈{30,40,45,50} 检出 CACC 反转（`p* ≤ 0.1`、`p_reversal_start ∈ (0.1,0.2]`）、
  效应量中位数 −2.74（确定性档排除）——反转非随机种子偶发现象。
- **门禁**：新增 38 个分析层测试（总 489 passed）；ruff/mypy/compileall/format +
  dry-run 全绿；报告 §5.1（中英）新增综合分析章节。

### ACC 模型链路兼容（2026-08，拓展）

- ACC 作为**第三个普通模型同权处理**（IDM/ACC/CACC）：自由流参考补齐 `CAV_ACC`
  （4 场景单车，只追加零漂移）、配置白名单放开、metrics delay 参考白名单移除
  （与 subgroup 口径对齐）、可视化补 ACC 配色 + 数据驱动模型集。
- 主实验（7,524 网格 IDM/CACC）零影响：metrics 复算一致、shipped/图产物字节
  一致、artifact 旧键零漂移；451 passed（+2 回归测试）。
- 范围：仅链路兼容；未重跑网格、未纳入正式实验设计（ACC 非正式比较对象）。

### 2026-08 U55 重设计 + 正式重跑完成（基本图方案，全链路产出）

- **实验参数重设计**（P0 插入缺陷终审 + 交通流理论评估驱动，内存约束修订）：
  统一密度轴 5–55 veh/km/道（s0/s1 10–110、s2/s3 20–220，11 档/场景），
  主网格 **7,524 runs**（基本图方案：自由流→临界→拥堵区上探受限——轴上限
  55 = 37.5% kj，未覆盖近阻塞段）。
- **`departSpeed="max"` → `"0"`**（P0 修复）：饱和环路高密度档插入损失
  （实测 s1 v120 仅 62/120、s2 v240 132/240）消除，100% 插入；warmup=600
  保持（9 档标定全部 ≤120 s 稳定）。
- **正式重跑（2026-08）**：7,524/7,524 全 SUCCESS——3 workers / **21.86 h** /
  0 失败（错峰排序 + 观测窗 1800）；解析 0 INVALID（**插入完整性守卫通过**）；
  writer 0 排除；聚合 924 组；可视化 5 图（FD 主图 + s3 瓶颈单独图）。
  产物：out/（run-level/subgroup/aggregated）、graph/v0.4.2/、raw/（76 GB）。
- **插入完整性守卫（审查 P1-1）**：vehroute 实际车辆数 < vehN → INVALID_DATA，
  结构性封死历史 P0 缩减车队缺陷复发。
- **设计文档**：设计口径/密度轴/warmup 标定/内存边界/报告边界已并入正式报告
  （report §2/§3/§8）与 README；完整设计基线留本地维护
  （`docs/internal/experiment-design-v042.md`，gitignored）。报告 §3 保留 2 处
  "并入自 EXPERIMENT_DESIGN" 出处注记（有意 provenance，非失效引用）。
- A 方案 8,208 为上一版设计（已取代，见下条历史记录）。

### 正式实验（历史：A 方案 v0.3.1 密度对齐版，已取代）

- **2026-08 A 方案（v0.3.1 密度对齐版）实验设计**：主网格扩展为 7,524 runs——
  vehN 轴按场景密度对齐（s0/s1 单车道 10–120、s2/s3 双车道 20–240，×2 密度
  对齐，每道 5–60 veh/km/道）；每档 cav_count 0.1 步长 11 档（全整数，替代
  v0.3.1 已删除的 0.05 requested_pcav 缺陷设计）；每 treatment 171 runs、
  每场景 2,052、总计 7,524。s3 路网为 v0.3.1 几何（32 边形、主线双车道、
  e15/e16 单车道 125 m 瓶颈），由 net.json 元数据驱动；s2↔s3 在匹配主线密度
  下隔离瓶颈效应，s2 真实峰值从 v120 边界伪影（7,128）重定位到预期 v140–180。
  treatments 扩展支持 per-scenario vehN 轴（treatment.scenarios 键）。
  **2026-08 合并设计**：安全维度并入主网格（main 全开 SSM 采集）；旧独立
  safety experiment（84 runs）板块取消（safety.json / pairing_checker / safety
  报告与相关数据随合并删除）。
- **HV/CAV 子群拆分**：detector/edgeData/SSM/vehroute/lanechange/stderr + FCD THW，
  排放双口径（non-internal 主强度 + 全路网次要强度）。
- 双 seed 统计单位：`(assignment_seed, sumo_seed)` 组合等权汇总，报告每格有效 n 与
  `seed_scope`；端点 assignment 失活、SUMO seed 保持活动。

### A 线实现（v0.4.0 逻辑对齐，正式 Reviewer 背书）

- cav_count 权威处理变量；resume 输入/输出 SHA 闭包（routes/type-map/additional/
  network/net.json/raw 输出）；SSM 观测窗上界 [warmup, 3600)；SSM analysis 配置单源
  （阈值/dedup/overlap/fragment）；sorted_greedy_80pct 真实实现；main/safety 报告分离；
  Safety 图按 scenario × vehN 分面；emissionClass 显式化（仅 v0.4.2）；自由流逐类型
  delay 参考；aggregate 双 seed fail-closed；schema=2 按 pipeline 分流。
- 自由流 artifact 版本化（`artifacts/free_flow/`）。

### v0.4.1 工程成果归属（内部里程碑，未发布）

- schema=2 runner/writer/aggregate、HV/CAV 子群、FCD physical THW（numpy 内存方案）、
  SSM pair/role provenance（D-006）、SSM 敏感性 CLI、自由流 artifact 链（D-008）、
  withInternal=true additional、CLI `--assignment-seeds`/`--sumo-seeds` 命名。
- **SSM 内存成本提示**（B 线历史观测，仅提示、不作硬预算、不再改进）：在 SUMO 1.27.1
  特定冻结工况（TTC=5.0/range=50、s2 零事件 case）下，启用 SSM device 与约 8.86 GiB
  额外 sampled peak RSS 相关（D-014 表述边界，不断言内部机制或内存泄漏）。v0.4.2
  safety 网格（TTC=3.0/range=50）逐 run 采样实测峰值：**s2 8.91 GiB**（s2_CACC_v120_c120，
  零事件 case，与 B 线历史观测一致）、s0 6.52、s1 1.81、s3 1.50 GiB——按普通资源规则
  运行（OOM 降并发 resume），峰值随场景/参数变化，不作硬预算。

### 测试与门禁

- **490 tests（当前基线）：441（2026-08 合并设计 + A 方案后基线 440；收敛审核
  Phase 2 增补 subgroup 解析质量门禁回归测试 → 441）→ 445（管线审查基线）→
  447（管线审查 P2-1/P2-2 回归测试 2 条）→ 449（round 9 free_flow/FCD 回归
  2 条）→ 451（ACC 兼容 +2）→ 489（分析层 38）→ 490（R13 零方差回归）**；
  Ruff / mypy / compileall / format 全通过
- 纯净分支重构（draft/pure-v042）：移除 v0.4.0~post3 兼容支持——schema=1 契约
  （RUN_LEVEL_COLUMNS/SUMMARY_REQUIRED_KEYS/_build_row_legacy）、PIPELINE_V4_0_POST1
  （_from_dict_legacy/默认值/白名单）、reanalyze_post3.py、FREE_FLOW_LAP_TIME_S
  历史常量、legacy.py 与 --legacy CLI、v0.4.0 配置；single_run 单跑迁移 v0.4.1
  （schema=2）。v0.4.0 数据红线不变（不重跑 10,080 网格、历史数据/tag 保留）；
  历史 post3 复现需 checkout v0.4.0.post3 tag。测试净减（legacy 契约测试移除，
  schema=2 主路径零行为变化）。
- 纯净分支阶段 1-3（本版发布说明随收尾更新）：**G1** 删除 requested_pcav 网格
  模式（pcav_levels/vehicle_counts/--pstep/--seeds/GRID_MODE_REQUESTED_PCAV 等，
  grid_mode 仅剩 cav_count）；**G2** v0.4.1 并入 v0.4.2 单管线（PIPELINE_V4_1/
  _from_dict_v4_1/V4_1 契约分支、--acceptance/--frozen-inputs 参数链、freeze_
  input_pair 移除）；**Part 3** requested_pcav 契约列删除——schema 列集/metrics
  输出/writer/aggregate/visualization 不再输出该列（RunSpec 内部字段保留，
  存量 raw 可重解析，D3），batch_run requested_pcav 死代码分支移除。
- 纯净分支阶段 5（本版发布说明随收尾更新）：**ssm_reproducer/free_flow 迁移
  v0.4.2**——RunSpec 补 experiment_role/ssm_enabled/analysis_* 字段（ssm_reproducer
  arm 语义：ssm_on=safety、ssm_off=main_factorial，analysis 阈值回退 capture 阈值）；
  **configs/v0.4.1 归档**——工具配置 analysis.json/free_flow.json/
  ssm_reproducer_s2/s3.json 迁 configs/ 根，门禁配置 smoke_v4_1.json（阶段 2 已
  迁移 v0.4.2 pipeline）迁根为 configs/smoke.json，其余 v0.4.1 正式实验配置
  （pilot/micro_pilot/mitigation/smoke 网格）归档 docs/internal/archive/
  configs-v0.4.1/（gitignored，不进 Git）；引用与测试同步（test_v4_1_grid 删除
  pilot 专属 run_id 测试，基线 459→458）。
- 审查复核（第三轮返工）：P1-1 真实 resume 路径修复——is_simulation_complete 的
  run_spec_sha256/network_sha256/persisted_spec 三处 fresh 直接比较在网络再生
  （字节漂移）时误拒（此前仅放宽下游 network_xml_sha256 块，未触及更早比较）。
  修复：v0.4.2 分支跳过前两处 fresh 直接比较（存档自洽由 load_run_spec 校验、
  网络语义由 sources.sha256 锚定保证），persisted_spec 比较归一化 network_sha256
  字段（config 变化仍检出）。实证：真实 raw 数据 scenario_0 972 runs
  fresh-spec（网络字节漂移）972/972 可跳过、config 变化 972/972 重跑。
- 审查复核（第三轮）修复：P1-1 resume 闭包与解析闭包网络口径统一（字节比对 →
  sources.sha256 语义锚定，网络再生不再误拒全量重跑）、P1-2 SSM 损坏 XML 台账
  不"伪零通过"（parse_success=False 时跳过台账检查）、P2-1 v0.4.2 不再导出 legacy
  空间错配列 whole_network_ttc_events_per_1000_non_internal_edge_veh_km（列集/
  required/metrics 三处一致）、P2-2 SSM subgroup 未知车辆 fail-closed、P2-3 stderr
  time 损坏行 fail-closed（损坏与零检出可区分）、P2-4 visualization --v4 角色门禁、
  P2-5 writer schema_version 未知拒绝、P2-6 audit cav_count 端点 assignment 冗余
  语义修正（恒 0）
- 审查复核（第二轮）P2 三项：P2-1 writer all 圈数>0 门禁贯通 subgroup 排除
  （run-level 与 subgroup CSV 共用同一判定，不再不一致）、P2-2 v0.4.2 run_spec
  专属键（experiment_role/ssm_enabled/analysis_*）缺失 fail-closed（不再静默
  当 main_factorial）、P2-3 validate_subgroup_invariants 增加 FCD 台账闭合
  断言（all==HV+CAV，样本数 + 排除计数）
- 审查循环（多轮 P0/P1/P2）修复条目：P0-1 all-level 圈时统计变量遮蔽
  （metrics.py delay 循环重绑定 vr → 5 列错标/缺失，正式 CSV 3,888 行全受影响；
  修复后需全量重解析以产出正确 all-level 圈时统计）、P1-1 FCD speed 台账对齐设计
  §6.3（→ low_speed_excluded）、P1-2 writer all 圈数>0 回归保护断言、P2 五项
  （extratime 显式化 / legacy 自由流参考优先 artifact / experiment_audit cav_count
  模式 / ssm all 版镜像合并回填时间 / legacy parse_detector 传 simulation_end）
- 四 dry-run：legacy 10,080 / pilot 162 / safety 84 / main 3,888
- v0.4.0 config SHA `178dfcef…` 与 legacy SUMO 命令字节基线不变

### 不做的事情（显式排除）

- 不重跑 v0.4.0 10,080-run 网格，不修改其配置/哈希/命令字节
- **v0.4.0 本地数据与图表已移除（2026-08 用户拍板，外部备份保留）**：`graph/v0.4.0/`
  图、`results/` 根 v0.4.0 产物（aggregated_results.csv / reanalysis_manifest.json /
  raw_input_inventory.jsonl）删除；README v0.4.0 Historical Baseline 章节移除；
  visualization `--v4` 模式与依赖 v0.4.0 数据的测试/fixture 清理。历史复现需
  checkout `v0.4.0.post3` tag（该 tag 保留完整工具链）。未来轨迹数据标定新版本
  以相同实验参数重跑时，以本版（v0.4.2）数据为对比基线。
- 不推进 B 线（SSM 内存诊断）与 SUMO upstream 提交——未获用户授权前不列为发布动作
- 不引入 ACC 自由流参考（D-008 约束保持）

---

## v0.4.1 (2026-07-30) — 内部里程碑，未对外发布

> **版本状态**：v0.4.1 为本地内部里程碑，未作为公开版本发布（GitHub 最新公开版本为
> v0.4.0.post3）。本条目保留供追溯；工程成果并入 v0.4.2 发布说明（见上）。

`v0.4.1` 是工具链功能发布，不包含正式实验结论。它构建了子群测量、FCD THW、
SSM 敏感性分析、自由流参考等能力，并完成 micro-pilot Level 1 验证。
Level 2 bounded factorial pilot 因 SSM 内存超出旧资源门禁而标记为 calibration /
failed gate（该门禁已废止，见 v0.4.2 跳号说明）。

### 新功能

- **HV/CAV 子群拆分**：detector/edgeData/SSM/vehroute/lanechange/stderr 均支持
  按车辆类型（HV/CAV）分别统计；SSM 新增 pair（HV-HV/HV-CAV/CAV-CAV）和
  role（follower→leader）分类。
- **FCD physical THW**：流式 gzip 解析，numpy float64 分位数计算，按 follower
  类型分 HV/CAV。
- **`parsing/metrics.py`**：统一指标计算模块，从 parser primitives 派生 core
  summary 和 subgroup 长表（`run_level_subgroup_results.csv`）。
- **schema=2 writer/aggregate 路由**：`--schema-version` 必填；aggregate 按
  `cav_count` 分组。
- **SSM 敏感性分析 CLI**（`scripts/analysis/ssm_sensitivity.py`）：三种 dedup
  方法（none / greedy_one_to_one_80pct / sorted_greedy_80pct），TTC/DRAC 阈值扫描。
- **自由流参考测量**（`scripts/analysis/free_flow.py`）：单车 HV/IDM/CACC 稳态
  圈时 artifact 生成，加载时强校验 SUMO 版本 + net SHA + 有限正数值。
- **fragment merge**（opt-in）：`ssm_extratime_s` 全链路（ExperimentConfig
  → RunSpec → SUMO 命令），parser 级同向 5s gap 合并恢复 encounter 语义；
  `ssm_fragment_merged_count` 独立台账。
- **`--frozen-inputs`**：baseline routes + type_map 复用与 SHA-256 校验，支持
  跨配置对比实验。
- **per-run RSS 采集**：SUMO 子进程 VmHWM 轮询 + parser 进程 VmRSS 采样。

### 已知限制

- **SSM 内存**（B 线历史观测，仅提示）：在 SUMO 1.27.1 特定冻结工况下，启用 SSM
  device 与约 8.86 GiB 额外 sampled peak RSS 相关（D-014 表述边界，不断言内部机制
  或内存泄漏）；受硬件与 SSM 参数配置影响，不作硬预算、不再改进（v0.4.0 曾以 74 次
  OOM 重跑兜底）。
- **CAV-CAV TTC**：extratime=1.0 + fragment merge 在混合交通下有 composition-
  dependent 低估（~13%，仅 vehN=60 IDM 混合）。
- fragment merge 默认禁用（`gap_s=0.0`）；仅在 `ssm_extratime_s < 5.0` 时由
  runner 自动启用到 5.0s gap。

### 测试

- 当时基线 **170 tests**（85 legacy + 19 v0.4.1 + 66 stage2）；498 为 stage2 时代
  瘦身前峰值（历史，非当前）；v0.4.2 时代基线 441（合并设计）→ 490（发布前）
- Stage 2 设计基线冻结于 `docs/internal/archive/v0.4.1-stage2-design.md`
  （本地维护文档，不随仓库发布；原 `docs/development/` 路径已于 2026-08 瘦身移入）
- 门禁：Ruff / mypy / compileall / format 全通过

`v0.4.0.post3` 不重跑 SUMO；它从冻结的 10,080-run raw XML 修正 post2
遗漏的跨解析器观测窗错配，并重新生成受影响的 run-level、聚合数据、图表与
报告。实验输入和原始观测保持不变，派生指标以 post3 为准。

### 数据与解释修正

- 将 edgeData performance、emissions 与安全事件统一到 `[600, 3600)`
  分析窗口，消除安全事件分子与车辆公里分母的时间窗错配。
- SSM warmup 边界按 `minTTC@time` 与 `maxDRAC@time` 分别判断，不再仅按
  encounter begin 丢弃跨越边界的整条记录。
- s3 全 CAV、vehN=120 的 TTC 率修正为 IDM 1,574.0、CACC 3,273.5
  events/1000 veh-km；CACC/IDM 比值约为 2.08。
- 同一运行点的 CO₂ 强度修正为 IDM 228.3、CACC 352.0 g/veh-km。
- 明确圈时“延误”是相对场景参考圈时的有符号差，并记录 P95 使用离散
  `higher` 分位数。

### 工程修正

- 增加独立 post3 再分析命令与 SHA-256 manifest，不覆盖冻结 raw 或 post2
  结果。
- 对实际读取的 30,240 个 raw XML 建立逐文件 SHA-256 清单，并在 manifest
  中记录稳定清单摘要；重分析后重新执行不变量校验，不再继承 post2 质量标签。
- 保留历史 CSV 列以兼容既有分析，同时增加 requested/realized pCAV、
  CAV/HV 数量、普通-edge 暴露量和全路网 TTC/普通-edge 暴露量的显式字段；
  聚合表增加 flow/assignment run 计数及独立随机重复数（固定为 0）。
- 明确跨 seed 比率使用各 assignment run 等权算术平均，而非 pooled exposure
  ratio；标准差不用于置信区间或显著性推断。
- post3 发布输出 schema 标记为 `v0.4.0.post3.1`；冻结 raw 中记录的 pipeline
  schema 仍为 `1`，原有指标列和值保持兼容。
- 配置、批处理与单次运行入口均拒绝无法同时与 detector 和 edgeData 完整
  interval 边界对齐的 warmup 配置；正式与 smoke 配置原本已对齐，既有数据
  不受影响。新增跨解析器回归测试纳入完整 pytest 门禁。
- 聚合器与 v4 图表显式使用 `requested_pcav`；兼容横轴标为 requested CAV
  penetration，避免把低车辆数下的请求水平误读为不同实际构成。
- 路网生成器增加 `--build-all`，从 Git 跟踪的四场景 node/edge 源文件调用
  netconvert 生成被忽略的 `loop.net.xml`；SUMO 1.27.1 生成网络与历史网络
  除生成注释外语义一致。
- 修复 detector 独立 CLI 的五返回值解包；空流量窗口不再以速度 0 进入未来
  速度均值/方差。冻结实验 252,000 个正式 detector 窗口中没有空窗，既有结果
  不受影响。
- writer 将结构完整与数据全部有效分开；`complete=true` 现在同时要求无失败
  run 且所有写入行均为 `data_quality=ok`，`parser_warning` 与
  `invariant_failed` 都会否决完整性。
- 增加跨解析器 warmup、SSM 极值时刻、P95 与 writer 完整性测试。
- 安全图直接读取完整语义的“全路网 TTC / 普通-edge 暴露量”聚合列，旧
  `ttc_per_k_mean` 仅作兼容 fallback；公开限制中记录 80% SSM 镜像去重规则。
- 从 post3 聚合 CSV 重算报告的场景 TTC 汇总，修正残留 post2 数字，并明确
  该列是“各处理组合的 assignment-seed 均值之和”，不是全部 run 事件总数。
- 场景关系统一称为结构递进/场景化比较，不再宣称隔离单一因素；图表和当前
  摘要将 `delay` 兼容字段展示为“相对固定参考圈时差”，模型比较仅排除显式
  tau 取值差异，不排除模型专属隐式默认参数。
- 修复 `configs/smoke.json` 与 warmup/edgeData 周期对齐门禁的冲突；更新
  AGENTS.md 为当前三阶段批处理 CLI，并让轻量测试入口醒目标注其不替代完整
  pytest 门禁。
- 收紧后续版本边界：v0.4.1 定位为测量链路、实验设计修订和有界 pilot，
  不默认重跑既有 10,080-run 网格；仅在 pilot 门禁通过且确有研究必要时，
  以条件性的 v0.4.2 发布新正式实验，且不覆盖 v0.4.0/post3。
- 修复 writer CLI 摘要仍读取已删除 `quality_invalid` 键的问题；摘要改为
  当前 report schema 的 `quality_non_ok`、`quality_invariant_failed` 与
  `quality_parser_warning`，并增加回归测试。

### 剩余历史数据边界

- v0.4.0 raw edgeData 使用 `withInternal=false`。SSM 事件与车辆公里的空间
  范围因此不完全配对；post3 不虚构无法从 raw 恢复的 internal-edge 里程，
  而是限定归一化安全指标含义并停止使用它做严格跨场景安全率排序。
- 所谓“容量”统一收敛为测试车辆数网格内的最大观测流量；尤其 s2 的
  7,128 veh/h 位于 `vehN=120` 上界，不宣称已识别真实容量峰值。

## v0.4.0.post2

`v0.4.0.post2` 是不改变或重跑 v0.4.0 正式实验、不改变既定实验数值结果的
文档、口径审计与验证修订版。实验配置和工程流水线语义继续保持
`v0.4.0.post1` 兼容；既有文字结论不属于无条件保留对象，与数据不一致或
超出证据支持范围的解释在本版本中予以修正。

### 修正与披露

- 明确区分 requested/realized pCAV，披露 2,400 个实际渗透率偏差 run，以及
  `vehN=10` 下 400 个重复渗透率处理。
- 将五个 seed 统一定义为车辆类型排列种子，而不是独立 SUMO 随机重复。
- 量化端点 seed 的 768 个信息冗余 run，并记录 SUMO 1.27.1 隐式默认参数是
  历史实验语义的一部分。
- 修正 SSM trajectories 默认值、数据压缩比、测试数、CSV 列数和最终成功
  run 数等文档口径。
- 统一使用归一化 TTC 事件率解释 s3 安全结果，修正“四维共赢”和 tau 因果
  归因等超出数据支持范围的表述。
- 在报告中区分直接观测、场景比较和机制假设，收敛 TTC、排放、延误与单车道
  效率章节中缺少直接证据的因果措辞。
- 修复聚合结果的重复 `n_valid` 表头，改为唯一的 `n_valid` 和
  `max_flow_count`；不改变任何聚合指标数值。
- 明确 release、experiment config、pipeline 和 result schema 四类版本边界。
- 增加只读实验网格审计 CLI，将 10,080 个计划 run、2,400 个实际渗透率偏差、
  400 个重复渗透率处理和 768 个端点信息冗余 run 固定为回归基线。

### 文档结构

- 根目录仅保留项目入口、版本历史、许可证和 Agent 约定。
- 实验报告迁入 `docs/report.md`。
- 工程审计、迁移指南和发布检查清单迁入 `docs/engineering/`。
- 路线图、实验问题、工程问题和历史开发文档迁入不发布的
  `docs/internal/`。

## v0.4.0.post1

`v0.4.0.post1` 是基于 `v0.4.0` 实验设计的工程质量修订版。

### 改进

- 将脚本整理为 simulation、parsing 和 results 领域子包。
- 增加实验配置校验、运行清单、输入哈希与断点续跑完整性检查。
- 增加 parser、状态机、结果写入、路网元数据和工程兼容性测试。
- 引入 Ruff、pytest、mypy、锁定依赖与 GitHub Actions 质量门禁。
- 补充迁移指南、工程审计和发布检查清单。

### 实验兼容性

- 实验配置仍为 `configs/v0.4.0.json`，`config_version` 仍为 `v0.4.0`。
- 4 个场景、2 个模型、21 个渗透率、12 个车辆数和 5 个车辆类型排列种子不变，
  共 10,080 个计划 run ID。
- 跟驰模型参数、车辆布置、车辆类型排列种子语义、仿真时长、预热时间、检测频率和
  结果 schema 均未改变。
- 工程流水线版本更新为 `v0.4.0.post1`，用于区分新旧流水线生成的中间产物。
