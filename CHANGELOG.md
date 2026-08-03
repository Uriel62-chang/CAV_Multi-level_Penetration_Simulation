# Changelog

## v0.4.2 (2026-08，跳号发布)

> **跳号发布说明**：v0.4.1 是本地内部里程碑，**未对外发布**（Level 2 pilot 未过旧资源
> 门禁；D-012–D-015 技术证据已闭合、治理状态未闭合，本地 tag 已删）。其全部工程成果
> 并入本版发布说明。本版为 v0.4.0.post3 之后的下一公开版本。

### 正式实验（新）

- **主 factorial 网格**：4 场景 × 12 vehN × 每 (scenario, vehN) 81 runs
  （cav=0: 3 + 内部 4 档×2 模型×3 assignment×3 SUMO: 72 + cav=vehN: 6）= 3,888 runs，
  SSM 关闭。关键数值：s2 CACC 全 CAV 网格内最大观测流量 7,128 veh/h；s3 高密度全
  CAV 运行点 IDM 3,204 vs CACC 1,536 veh/h（瓶颈反转复现 v0.4.0 定性结论）。
- **独立 safety experiment**：84 runs（p∈{0,0.2,0.6,1.0} × vehN∈{30,60,120}），TTC/DRAC
  事件率与暴露量空间配对（withInternal=true）；s1 与 s2 在当前阈值/配置下未检出事件
  （边界声明，不升级为「无安全冲突」）。
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

- **507 tests**；Ruff / mypy / compileall / format 全通过
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

- 当时基线 **170 tests**（85 legacy + 19 v0.4.1 + 66 stage2）；现行为 498（v0.4.2 发布前修复后基线）
- Stage 2 设计基线冻结于 `docs/development/v0.4.1-stage2-design.md`
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
