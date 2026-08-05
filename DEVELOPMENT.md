# 开发文档

> 新 Developer、Improver 或 Reviewer 应先阅读：
> 1. README.md
> 2. DEVELOPMENT.md
> 3. 当前阶段任务、用户授权与运行门禁
> 4. 相关关键决策（尤其 D-012–D-015）
> 5. 本文“当前交接摘要”
> 6. 最近相关 Git 提交（至少 `git log --oneline -15`）
> 7. AGENTS.md（项目约定、CLI 入口）及
>    `docs/development/v0.4.1-stage2-design.md`（批准基线）
>
> 补充材料（Git 忽略，本地可用时参考）：
> `docs/internal/releases/v0.4.1.md`（完整开发计划）、
> `docs/internal/releases/v0.4.1-stage1-design.md`（阶段 1 设计文档）
>
> 阶段 2 批准基线已受 Git 跟踪；实现或审查不得用聊天记录覆盖其函数契约、校验矩阵和验收探针。

> **Reviewer 保留声明**：本文档由 Developer 维护，Reviewer 可将其用作项目状态与证据路径索引。尚未经独立 Reviewer 会话核验的 archive、inventory、A/B 对照及 upstream issue 包内容，不因纳入本文档而自动获得 Reviewer 背书；正式审查结论以独立 Reviewer 报告为准。

---

## 关键决策

### D-001：cav_count=0 时 RunSpec.model 使用 sentinel "IDM" 而非 JSON null

- **状态**：Active
- **决策提交**：`acb5bc6`
- **适用范围**：RunSpec.model 字段定义，batch_run 网格展开，validate_specs
- **重新评估触发条件**：RunSpec 类型系统重构为 model: Optional[str] 时
- **背景**：v0.4.1 设计文档要求无 CAV 时 model=null。RunSpec 的 model 字段类型为 `str`，改为 `Optional[str]` 会波及所有消费方（flow_generator、parser、writer、aggregate、visualization）。
- **决定**：cav_count=0 时 model 固定为 "IDM"（与配置模型集合及顺序无关），seed 固定为 0。run_id 使用 "HVONLY" token 和 "as00" 表示非活动维度。非活动语义由 `cav_count ∈ {0, vehN}` 唯一确定。
- **原因**：避免 Optional[str] 贯穿式重构；flow_generator 在 cav=0 时跳过 CAV vType 写入，model 值不影响 route 输出。
- **已考虑的替代方案**：Optional[str] + Optional[int]（改动量过大）；空字符串（flow_generator 不接受）。
- **当前代价**：后续聚合需根据 cav_count 而非 model/seed 判断非活动维度。

### D-002：route/type-map 哈希归属 simulation_status 而非 RunSpec SHA

- **状态**：Active
- **决策提交**：`acb5bc6`
- **适用范围**：RunSpec.to_dict()、is_simulation_complete()、simulation_status.json 字段
- **重新评估触发条件**：RunSpec 改为两阶段构造（先创建后回填）时
- **背景**：设计文档最初要求 route_file_sha256 和 vehicle_type_map_sha256 进入 RunSpec 稳定 SHA。但这两个哈希在 RunSpec 创建时尚不存在（flow_generator 运行后才能计算）。
- **决定**：route/type-map 哈希记录在 simulation_status.json，由 is_simulation_complete() 校验。RunSpec 稳定 SHA 仅覆盖仿真参数和双 seed。simulation_status.json 是 resume 完整性校验的状态与哈希锚点。
- **原因**：避免两阶段构造破坏 frozen dataclass 不可变性；status 已是 resume 的核心数据源。
- **当前代价**：RunSpec SHA 不覆盖输入文件完整性（需配合 status 和文件内容双重校验）。

### D-003：schema_version="2" 的解析路由在阶段 2 实现

- **状态**：Implemented（阶段 1 的推迟决定已履行）
- **决策提交**：`1f61e36`；实现提交：`ef0d9ad`、`c73007e`、`9c33477`
- **适用范围**：RunSpec.schema_version、parser/writer/aggregate 输出路由
- **重新评估触发条件**：新增 schema_version="3" 或修改 schema=2 公共列时
- **背景**：v0.4.1 新增列需 parser/writer 切换。阶段 1 只产生 raw，不调用解析链路，因此当时只使用 schema_version="2" 作为身份标记。
- **决定**：阶段 2 已实现完整 schema=2 parser、writer 和 aggregate 路由；aggregate 的 `schema_ver`/`--schema-version` 必须显式传入，不从 CSV 列推断。
- **原因**：显式 schema 消除含兼容列的 legacy CSV 被误判为 schema=2 的风险。
- **当前代价**：所有 aggregate 调用方必须明确选择 schema 1 或 2。

### D-004：进程退出检测使用轮询 process.returncode

- **状态**：Active
- **决策提交**：`e341668`
- **适用范围**：batch_run.py worker 主循环
- **重新评估触发条件**：asyncio 上游修复 `process.wait()` 唤醒问题后
- **背景**：`process.wait()` 在某些内核/SUMO 版本组合下不自主唤醒，即使子进程已退出。
- **决定**：用 while 轮询 `getattr(process, "returncode", None)`（默认间隔 0.5s，硬截止 7200s）。
- **原因**：`process.returncode` 是 asyncio 在子进程退出时设置的属性，在当前支持环境中可被可靠轮询观察到，比 `wait()` 更可靠。
- **已考虑的替代方案**：只对显式 timeout 轮询，默认仍 `wait()`（不解决默认无限等待）。
- **当前代价**：最多约 0.5 秒的退出检测延迟；mock Process 类需添加 `returncode` 属性。

### D-005：S8 冻结输入推迟到 1.post1（Partially implemented，仅剩 fcd_path）

- **状态**：Partially implemented（阶段 2 已实现主体；唯一剩余项 `PreparedRun.fcd_path` 推迟到 1.post1；2026-07-31 依 Reviewer 复检 P1-6 更新本体）
- **决策提交**：`59c1b17`
- **适用范围**：frozen_inputs、canonical_json_bytes、atomic_write_bytes、--acceptance CLI、PreparedRun.fcd_path
- **重新评估触发条件**：阶段 1.post1 开始（仅剩余项 fcd_path）
- **背景**：冻结输入是实现 provenance 可追溯性的独立功能，不影响 raw 生成核心路径。
- **决定**：阶段 2 已实现 `frozen_inputs` 目录（frozen acceptance 输入对，`prepare_post1_frozen_inputs` 入口 scripts/simulation/batch_run.py:625）、`canonical_json_bytes`（scripts/provenance.py:17）、`atomic_write_bytes`（scripts/provenance.py:24）、`--acceptance` CLI（scripts/simulation/batch_run.py:1240）与非 resume 覆盖保护；唯一剩余项 `PreparedRun.fcd_path` 推迟到 1.post1。
- **当前代价**：仅缺 `PreparedRun.fcd_path` 字段；无其他未交付组件。

### D-006：SSM role 按 measure 独立保留极值来源

- **状态**：Active
- **决策提交**：`460f0e6`；实现提交：`a76ffd2`、`d0c54a2`
- **适用范围**：SSM 镜像去重、HV/CAV pair 分类、follow/leader role 分类
- **重新评估触发条件**：支持 code 2/3 以外的 encounter type，或 SUMO 修改 SSM XML 语义时
- **背景**：镜像 conflict 合并后，TTC 与 DRAC 的更危急极值可能分别来自相反的 ego/foe 方向。
- **决定**：只在 `<minTTC>` / `<maxDRAC>` 的 type code ∈ {2,3} 时恢复角色；TTC 与 DRAC 分别保存 `{value,time,type_code,source_ego,source_foe}`，分类时使用对应 measure 的 provenance。
- **原因**：用去重后保留记录的 ego/foe 会在反向记录贡献极值时颠倒 follower/leader。
- **当前代价**：无法可靠恢复的 encounter 进入 unclassified，不推测角色。

### D-007：FCD 分位数使用 numpy float64 原地排序

- **状态**：Active
- **决策提交**：`460f0e6`；实现提交：`7274412`
- **适用范围**：`scripts/parsing/fcd.py` 的 THW 数组和分位数计算
- **重新评估触发条件**：FCD 规模超过当前 200 MB RSS 预算，或移除 numpy 依赖时
- **背景**：FCD gzip 需流式解析，但精确 higher quantile 仍需保存并排序有效 THW 样本。
- **决定**：先以 `array('d')` 流式收集，逐组转为 `numpy.ndarray(dtype=float64)`，执行 `sort()` 原地排序并及时释放。
- **原因**：在当前规模下保持精确分位数，同时满足阶段 2 内存预算。
- **当前代价**：FCD parser 直接依赖 numpy；内存仍随有效样本数线性增长。

### D-008：v0.4.1 不接受 ACC 自由流参考

- **状态**：Active
- **决策提交**：`460f0e6`；实现提交：`8b13dbe`、`34534a5`、`f0dd97f`
- **适用范围**：v0.4.1 pilot、free-flow artifact 生成与加载
- **重新评估触发条件**：正式实验把 ACC 纳入模型集合并生成对应单车参考时
- **背景**：v0.4.1 pilot 只包含 IDM/CACC，现有自由流测量没有 ACC 基准。
- **决定**：ACC 在自由流 reference selection 中 hard reject；artifact 必须匹配 SUMO 完整版本字符串和每场景 net SHA，且 HV/当前 CAV model 圈时均为有限正数。
- **原因**：用 IDM/CACC 或硬编码值代替 ACC 会产生无 provenance 的 delay。
- **当前代价**：ACC 配置在补充参考 artifact 前不能进入 schema=2 正式解析。

### D-009：schema=2 detector 预期输出由 net.json.num_lanes 决定并 fail-closed

- **状态**：Active
- **决策提交**：`faac364`；实现提交：`80ac97b`；测试提交：`9ae9ae8`、`53d8e11`
- **适用范围**：`_missing_required_outputs()`、`is_simulation_complete()`、schema=2 simulation/resume
- **重新评估触发条件**：PreparedRun 固化 expected-output 清单，或网络元数据 schema 变更时
- **背景**：从实际存在的 detector 文件反推预期集合无法发现"全部缺失"或双车道缺 lane1。
- **决定**：从 RunSpec.network_file 同目录的受验证 `net.json` 读取正整数 `num_lanes`，无条件要求 `0..num_lanes-1` 每个 lane 的 all/HV/CAV 三件套；元数据缺失、损坏、结构错误或 num_lanes 非正整数时 fail-closed（`_missing_required_outputs` 抛 ValueError，`is_simulation_complete` 返回 False）。
- **原因**：required-output 和 resume 必须 fail-closed，不能用缺失输出来推断实验结构。
- **当前代价**：两个调用点有少量重复读取逻辑。

### D-010：冻结 v0.4.0 ExperimentConfig 哈希兼容外部 manifest

- **状态**：Active
- **适用范围**：`ExperimentConfig.sha256()`、legacy resume
- **背景**：已发布 v0.4.0 raw manifest 和 run status 使用 `178dfcef…` 作为配置身份；v0.4.1 添加的配置默认字段曾改变 legacy 规范化表示。
- **决定**：legacy `to_dict()` 使用历史 resolved-manifest 字段集（含当时的 grid/SSM capture 字段，不含之后的 FCD、extra-time、range-m 字段）；哈希始终由该表示的规范 JSON 自然计算。
- **原因**：使配置内容与 manifest SHA 同源，原始 `run_spec.json` / `simulation_status.json` 可在不重写历史产物的前提下被 resume 验证，且 CLI 覆盖配置同样产生可审计的新哈希。
- **当前代价**：该历史字段集需保留冻结与 CLI override 的回归探针。

### D-011：summary 契约在 runner 与 writer 双层 fail-closed

- **状态**：Active
- **适用范围**：schema=1/2 summary、阶段二状态机、阶段三输出门禁
- **背景**：仅依赖 parser audit flag 会让缺失 core 字段经 writer 默认 NaN 后被误标为 `data_quality=ok`。
- **决定**：以 `schema.py` 的字段级契约在 runner 写状态前和 writer 读入时各校验一次；无事件极值可为 NaN，其余身份、计数、暴露量按字段规则验证。manifest 与 subgroup 也按唯一键集合闭合。
- **原因**：将损坏/不完整产物隔离在生成和汇总两个边界，避免报告“完整”但缺少计划输出。
- **当前代价**：新增 schema 字段时必须同步更新契约与 subgroup 预期键测试。


---

## 当前交接摘要

### 已完成

- **阶段 0+1 已实现**：cav_count 双 seed 网格 + inactive-dimension 规范化；SUMO 命令注入 seed/SSM capture/FCD 输出；withInternal=true additional；writer `non_internal_edge_vehicle_km` 列名修正；进程退出轮询 + SIGINT→CANCELLED；CLI `--assignment-seeds`/`--sumo-seeds` 命名。
- **阶段 2 完成**（2026-07-30，**v0.4.1 内部里程碑，未对外发布**）：HV/CAV 子群拆分；FCD physical THW；SSM pair/role provenance（D-006）；schema=2 runner/writer/aggregate；subgroup JSONL + SHA；自由流 artifact（D-008）；SSM sensitivity CLI；free-flow 测量；FCD numpy 内存方案（D-007）；net.json num_lanes fail-closed（D-009）；fragment merge（opt-in）；`--frozen-inputs`；per-run RSS；sim→parse→write→aggregate smoke。
- **分拆设计骨架已审查（2026-07-31）**：v0.4.2 分拆设计经 6 项 P1 + 3 项 P2 两轮修订后，机械短检通过（`5ace1b5`，无 P0/P1/P2），骨架获正式 Reviewer 背书；网格设计附录（`a28b84e`）已起草，后续按冗余门禁清理（见下）。
- **冗余门禁清理（2026-07-31）**：废止 12 GiB 两阶段校准体系、resource addendum、反复 Reviewer 审批与逐提交审查流水账；SSM 内存管理降级为普通资源规则（OOM 降并发 resume，v0.4.0 已验证）。B 线诊断证据（D-012~D-015）已移入历史归档，不再推进；SSM 全量采集成本（9,292,312 KiB/run，零事件 case）仅作为提示性信息写入 REPORT/README，不作硬预算。
- **A 线实现完成（2026-08-01）**：v0.4.0 代码逻辑与实验设计对齐全部落地。实现提交链 =
  前置提交 `73814bf`（P0-6 报告入口）+ `6147853`~`b72c381`（**8 个实现提交**）；
  `1aa9632` 为范围外的交接文档提交（P2-1 修正：原"9 个提交"计数不准确）：
  - **P0-1**（`370d3a2`/`44e8932`）：v0.4.2 pipeline 身份（PIPELINE_V4_2 + experiment_role/ssm_enabled），config→RunSpec→command→required-outputs→parser 贯通；主 factorial 可表达 SSM-off 意图性缺失；runner 分派 v0.4.2 到 stage2 parser
  - **P0-2**（`a06e4dd`/`6147853`）：cav_count 权威处理变量（flow 生成不再 round 二义）；配置序列化含网格字段（不同网格 SHA 不碰撞）；绘图横轴 realized_pcav 优先
  - **P0-3**（`c57e5ff`）：聚合分别记录 assignment/sumo 水平数、组合数、有效 n，拒缺失/重复组合
  - **P0-4**（`05cd260`/`44e8932`）：SSM 观测窗上界 [warmup,3600)，主 parser/subgroup/sensitivity 统一；main_factorial 成功判定不要求 ssm.xml
  - **P0-5**（`1916d53`/`44e8932`）：SSM analysis 配置单源（阈值/dedup/overlap/fragment 参数化并写入 summary）；ssm_not_collected 透传（区分未采集/零事件）；dedup_method 声明与实际执行一致
  - **P0-6**（`73814bf`/`44e8932`）：main/safety 报告分离（`--v4-2` 不生成 trade-off；`--safety` 生成事件率随渗透率图）
  - **P0-7**（`3c8f0ce`）：排放双累计（non-internal 主口径 + 全路网次要）
  - **P0-8**（`47fa29d`）：自由流 4 场景参考 + 逐类型 delay（HV→HV ref、CAV→CAV_model ref，lap 加权）
  - **P0-9**（`723bb2c`）：emissionClass 显式化（仅 v0.4.2，legacy 字节不变）
  - **P0-10**（`658a055`）：resume 闭包扩展（additional/network XML SHA）
  - **P0-11**（`ff30425`）：84-run Safety 正式配置（`configs/v0.4.2/safety.json`，p∈{0,0.2,0.6,1.0}）+ 独立报告入口
  - **P1 组**（`b72c381`）：aggregate 输出 seed_scope；图表标签改"CAV Penetration"；删除 reasonix.toml 工具缓存
- **已验证（2026-08-01）**：266 tests passed；Ruff/mypy/format/compileall 通过；legacy 10,080 / pilot 162 / safety 84 三 dry-run 通过；legacy SUMO 命令字节与路由 SHA 基线未变（P0-9 参数隔离验证）。
- **正式 Reviewer 背书（2026-08，三轮复检后无 P0/P1/P2）**：A 线实现批次 `a8aa09a` 获背书；复检驱动修复——delay 键（`metrics.py` 读 `spec.model`）、Safety 配对列 fail-closed、subgroup 排放双口径、schema=2 按 pipeline 分流（V4_2 集合）、RunSpec role×SSM/阈值包络约束、resume 闭包扩展（net.json + raw 输出 SHA）。
- **v0.4.2 正式网格完成（2026-08）**：main 3,888 runs + safety 84 runs 全部 SUCCESS（main 累计 per-run SUMO wall time 9.8 h，resume 续跑）——**旧网格历史（2026-08 已清空、外部备份保留）；当前设计为 U90 7,524 runs（近阻塞密度轴、SSM 全开、合并设计），待正式重跑**。热修复（正式数据驱动）：①可加性容差放宽（实测浮点噪声 vehicle_km 2.0e-4/time_loss 1.1e-3/PMx 3.2e-4，旧容差误报 770 个 INVALID_DATA → `a21e05e`）；②writer subgroup NaN 规则补 whole-network 强度（端点 run 空子群 432 个被排除 → `6637519`）；③Safety 图按 scenario × vehN 分面（`439ace6`）；④热修复回归测试（`1a6da3c`）。
- **结果分析与 release notes 已背书（2026-08）**：`results/v0.4.2/`（run-level/aggregated/subgroup CSV + result_handover.json + result_analysis.md）与 CHANGELOG v0.4.2 条目获 Reviewer 短复检通过（`ef1e536`）；309 tests 基线。v0.4.2 发布前审阅修复后基线为 365 tests（P0/P1/P2 修复 + 重算 + 门禁补齐）。
- **已提交**：`7ea2e08`、`f675717`（D-012）；`7145a2d`（D-013 设计）；`6a5d772`、`ad95058`（A/B 实现和命令等价回归）。
- **主线回归交接（2026-07-31，`47e72c5`）**：v0.4.1 确认为未发布内部里程碑（GitHub 最新 v0.4.0.post3，tag 已删）；跳号发布决定；B 线（SSM 内存诊断）宣告结束，降级为 REPORT/README 提示信息；v0.4.2 为唯一开发主线（设计→实现→数据→结论四环节对齐）；主线纪律约束生效。

### 当前状态

- **当前分支**：`main`
- **本文档最后更新**：参见 `git log -1 --oneline -- DEVELOPMENT.md`
- **最近代码稳定提交**：`e99cd89`（release-review P1/P2 修复）；历史锚点 `439ace6`（Safety 图）、`ef1e536`/`53ca434`（docs-only）、A 线实现链 `6147853`~`b72c381`、正式网格热修复 `a21e05e`/`6637519`/`1a6da3c`
- **版本发布状态**：GitHub 最新公开版本 v0.4.0.post3；v0.4.1 为本地内部里程碑（未 push、tag 已删）；**v0.4.2 为发布目标（跳号发布，release notes 已就绪）**；本地 annotated tag 已创建（当前指向旧 c1695ce，待 Reviewer 背书后重打至背书 SHA；未 push，方案 A：push main → 观察期 → push tag + release）；**2026-08 历史数据已清空**（raw_v0.4.2/ 34 GB、raw/、results/v0.4.2/、graph/v0.4.2/、docs/report.md 全删，用户拍板、外部备份保留）——仓库为纯工具链 + 未来重跑定义（main 全开 SSM，合并设计）
- **验证环境**：SUMO 1.27.1, Python 3.10, .venv/; 验证日期 2026-07-31
- **可运行入口**：
  ```bash
  .venv/bin/python3 -m scripts.simulation.batch_run --config configs/smoke.json --output-root /tmp/smoke --sumo-processes 1
  .venv/bin/python3 -m scripts.parsing.batch --input-root /tmp/smoke
  .venv/bin/python3 -m scripts.results.writer --input-root /tmp/smoke --output-dir /tmp/smoke-out --manifest /tmp/smoke/manifest.json
  .venv/bin/python3 -m scripts.results.aggregate --input /tmp/smoke-out/run_level_results.csv --output /tmp/smoke-out/aggregated_results.csv --schema-version 2 --manifest /tmp/smoke/manifest.json
  .venv/bin/python3 -m scripts.simulation.batch_run --config docs/internal/archive/configs-v0.4.1/pilot.json --dry-run
  .venv/bin/python3 -m scripts.simulation.batch_run --config configs/v0.4.2/main.json --dry-run
  ```

### 待处理

- **v0.4.2（发布目标，跳号发布）**：四环节已闭环并获背书（见「已完成」）；发布正文（README/CHANGELOG/DEVELOPMENT）已切换为 v0.4.2 状态。剩余动作：
  1. **打 tag / 发布**：`git tag v0.4.2`（指向新背书 SHA）+ push + 执行 `docs/engineering/release-checklist.md`（需用户指示）；
  2. **数据归档**：~~`raw_v0.4.2/`（34 GB）与 `results/v0.4.2/` 外部归档~~ →
     2026-08 历史数据已清空（raw/results/graph/report.md 全删，外部备份保留）；
     未来重跑后按既有链路重建并归档；
  3. **发布后同步**：AGENTS.md/DEVELOPMENT.md/roadmap 版本状态切换为已发布——tag 所指提交本身即最终发布状态，不得依赖 tag 后新 commit（如需再校，在 tag 前完成）。
- **SUMO upstream（可选开源贡献，范围外 backlog，不在 v0.4.2 发布动作内）**：`raw/diagnostics/sumo_upstream_issue_ssm_s2_ab/ISSUE_DRAFT.md` 状态——
  - **Developer 预检认为**：issue 主内容（device-on/off 关联、零事件输出、可复现 RSS 差异）符合 D-014 表述边界，但 observation 2 含内部存储机制推断（引用旧 tag 源码），超出「只报告关联」范围；
  - **正式 Reviewer 尚未核验 issue 包**（此前背书范围是 A 线实现与正式网格，不含本包）；
  - **当前任务不授权**修订、复核或提交；
  - 仅在用户另行授权后恢复流程（先由正式 Reviewer 核验 `ISSUE_DRAFT.md`、archive 与 inventory，再决定对外提交；B 线门禁维持：不修改原证据或提交外部 issue）。
- **B 线收尾文案（已完成，随 v0.4.2 CHANGELOG 落地）**：SSM 全量采集内存成本（9,292,312 KiB/run，零事件 case）已作为提示性信息写入 CHANGELOG（v0.4.1 已知限制 + v0.4.2 SSM 内存成本提示），注明受硬件影响、不作硬预算、不再改进；正式 safety 网格实测峰值 s2 8.91 GiB 与历史观测一致。
- **发布治理（v0.4.2 发布前）**：本地 `v0.4.1` tag 已删（2026-07-31）；release notes 显式说明跳号原因（pilot 未过门禁；D-012–D-015 技术证据已闭合、治理状态未闭合）并列明 v0.4.1 全部工程成果归属；AGENTS.md/DEVELOPMENT.md 版本状态已同步（本次提交）。
- **known gaps**：SSM sensitivity 三种 dedup 未覆盖 crossing/merging 探针。
- **非阻塞工程遗留（随 v0.4.2 顺带处理，不单独立项）**：① `scripts/config.py:50-51` `SSM_TTC_THRESHOLD_S=3.0`/`SSM_DRAC_THRESHOLD_MPS2=3.0` 与 RunSpec 传入的 5.0/3.0 构成阈值双源，v0.4.2 重定 estimand 时应统一为单一来源；② `scripts/config.py:59-64` `FREE_FLOW_LAP_TIME_S` 残留表（含 98.8）已被 D-008 自由流 artifact 取代，应废弃（不得恢复硬编码 fallback）；③ `scripts/parsing/ssm.py:7,10` `_MIRROR_OVERLAP_RATIO=0.8`/`_FRAGMENT_MERGE_GAP_S=0.0` 不可配置，v0.4.2 若改 dedup/merge 规则需参数化。风险可控（post1 领域分组先例 + 基线护栏：10,080 run ID / legacy hash / dry-run / 85+ tests）。
- **暂缓**：S8 剩余项 `PreparedRun.fcd_path` → 1.post1（`canonical_json_bytes`、`atomic_write_bytes`、`--acceptance` 已在阶段 2 实现，见 P1-6 复核）。

### 重要约束

- **不得未经版本化决策修改**：`configs/smoke.json`、`configs/v0.4.2/{main,safety}.json`
  （哈希基线）；legacy RunSpec.to_dict() 字段集；legacy SUMO 命令字节序列。修改时
  必须同步更新哈希基线和兼容测试。（v0.4.0 本地数据已移除；`configs/v0.4.0.json`
  不存在于 head，历史基线由 `v0.4.0.post3` tag 承载。）
- **需要保持兼容**：`build_run_id()` 旧调用方式（`cav_count=None` 走 legacy 格式）；flow_generator 输出；10,080 旧 run ID 列表。
- **schema=2 完整性约束**：detector 必须覆盖 net.json 指定的全部 lane，且每个 lane 同时存在 all/HV/CAV；net.json 异常不得回退单车道。subgroup JSONL 必须存在、非空且 SHA 与 parse_status 一致。
- **自由流约束**：不得恢复硬编码 98.8 fallback；artifact 的 SUMO 完整版本、scenario net SHA、HV/当前 model 有限正圈时必须全部匹配。
- **A 线实现约束（2026-08-01）**：P0-9 的 `explicit_emission_class` 参数默认 False（legacy v0.4.0/v0.4.1 路由字节不变），仅 v0.4.2 传 True；P0-10 的 v0.4.2 resume 要求 status 含 `additional_file_sha256` 与 `network_xml_sha256`（缺少即判定 incomplete）；SSM analysis 配置（阈值/dedup/overlap/fragment）仅 v0.4.2 从 RunSpec 读取，v0.4.1 保持旧 merge_gap 推导。
- **修改前验证**：`ExperimentConfig.sha256() == 178dfcef...`；旧 pipeline dry-run 10,080；RunSpec legacy hash 不变；涉及 schema=2 时额外运行 pilot 162 dry-run 和定向完整性探针。
- **Reviewer 边界**：正式 Reviewer 由用户指定；内部静态预检不构成正式 Reviewer 复核，Reviewer 不直接修改代码。
- **主线纪律（2026-07-31 起）**：SSM 内存诊断为 B 线，不再推进（门禁维持：不再运行任何诊断，不得修改原证据或提交外部 issue，除非新版本化设计获批）；开发投入集中在 v0.4.2「设计 → 实现 → 数据 → 结论」对齐；提交任何文档/代码前先检查是否服务于 A 线或发布治理，避免再次偏离主线。

---

## Agent 交接原则

Agent 之间不直接依赖上一会话的自然语言记忆。重要信息必须沉淀到：

1. **项目代码** — 设计意图通过函数签名、类型注解、docstring 表达
2. **自动化测试** — 行为契约通过 test case 和验收探针固定
3. **DEVELOPMENT.md** — 关键决策、交接摘要、约束
4. **Git 提交记录** — 每个 commit 标注范围和通过条件

如果某项约束只存在于聊天记录中，则视为尚未完成交接。

---

## Git 安全机制

Git 不只是版本记录工具，也是 Agent 修改时的安全边界。

### 修改前检查
```bash
git status && git branch --show-current && git log -1 --oneline
```
确认分支正确、工作区干净、无未处理的改动、当前稳定提交已知。

### 检查点提交
以下操作前建立可回滚提交：大范围重构、批量改多文件、升级核心依赖、修改数据格式或公共接口、自动修复大量问题。提交示例：`git commit -m "checkpoint: before parser refactor"`

### 分支隔离
以下修改使用独立分支：实验性功能、高风险重构、多种方案对比、大规模自动修改。小型明确修改可直接在开发分支完成。

### 小步提交
每完成一个稳定独立的修改就提交，一个提交只表达一个主要意图。不混合：新功能 + 无关格式化 + 重命名 + 依赖升级 + 文档重写 + 临时文件。

### 提交前检查
`git status && git diff --stat && git diff --staged`：确认修改符合目标、无不相关改动、无密钥/隐私信息、测试通过、文档同步。

### 差异审查
Agent 的修改说明只作为索引，Git diff 才是实际依据。核对：声称的修改是否真的发生、是否改了任务外文件、是否删除原有行为、是否硬编码让测试通过。

### 回滚原则
以下情况优先回滚而非继续修复：修改范围失控、核心功能破坏、测试失败持续增加、实现偏离阶段目标。

### 稳定提交标记
阶段验收完成、干净环境验证通过、正式发布前应打 tag：`git tag v0.1.0`

---

## Agent 角色边界

### Developer
**负责**：理解阶段目标、制定实现计划、编写代码、增加测试、完成功能自检、更新阶段状态。

**不得**：未经说明扩大需求范围；擅自改变关键架构；删除不理解用途的兼容逻辑；为通过测试而降低验收标准。

### Improver
**负责**：根据明确问题改进结构和可维护性；处理已确认的技术债务；补充错误处理和测试；保持原有功能与接口稳定。

**不得**：仅因风格偏好进行大范围重构；在没有收益说明时替换稳定方案；忽略关键决策中的约束。

### Reviewer
**负责发现**：与需求不符的问题、正确性缺陷、异常和边界、安全和稳定性风险、可维护性问题、测试和文档缺失。

**可以质疑已有设计，但必须**：指出具体风险、说明触发条件和影响、区分缺陷/改进建议/个人偏好、检查相关关键决策后再建议修改。
**不直接修改代码**，除非用户明确要求修复或切换为 Developer/Improver 角色。

---

## 历史决策归档（B 线，不再推进）

> 以下决策为 v0.4.1 SSM 内存诊断（B 线）的历史记录，保留供追溯。B 线已宣告结束：
> 不再运行任何诊断、不修改原证据、不对外提交 issue（除非用户另行授权 + 正式 Reviewer 核验）。
> SSM 全量采集内存成本（9,292,312 KiB/run，零事件 case）仅作为提示性信息，不作硬预算。

### D-012：SSM 诊断证据使用不可复用 attempt，而非 case 根目录

- **状态**：Implemented（历史）；s3/s2 运行结果曾为 Developer 预检，正式 Reviewer 复核已由 2026-07-31 核验覆盖
- **适用范围**：`scripts/analysis/ssm_reproducer.py`、`configs/ssm_reproducer_s[2|3].json`
- **决定**：每次诊断写入 `case_id/attempt-###/{raw,report}`；启动前原子写 RUNNING，finally 写终态、错误与存在文件 SHA/缺失清单；仅完整成功且控制条件满足时生成派生 report。
- **原因**：使失败、超时、解析和报告异常均可审计，防止覆盖或倒灌追认。

### D-013：SSM-on/off 最小复现先冻结设计，后实现与运行

- **状态**：Implemented（历史）
- **适用范围**：`docs/development/v0.4.1-post1-ssm-ab-design.md`
- **决定**：以已冻结的 s2 CACC/v120/c120/as00/ss102 treatment 为两臂公共输入；A 保持 SSM，B 仅移除 SSM device。SSM-off 的 `ssm.xml` 是意图性缺失，状态机必须显式记录，不得伪装成零事件或证据缺失。
- **原因**：先隔离 SSM device 才能形成可解释的 upstream 最小复现。

### D-014：SSM A/B 结论只表述为 device-on/off 关联

- **状态**：Active（表述边界仍适用）
- **适用范围**：SUMO upstream issue、README/report 后续解释、v0.4.2 safety 设计
- **决定**：可表述“在该冻结工况与 SUMO 1.27.1 中，启用 SSM device 与约 8.86 GiB 额外 sampled peak RSS 相关”（9,292,312 KiB = 8.86 GiB）；不得称为内存泄漏或断言具体 SUMO 内部数据结构。
- **原因**：A/B 隔离了 device 配置因素，但单个 treatment 不能识别更细的内部机制或普适性。

### D-015：SSM 诊断证据使用显式 arm 目录与非自包含 inventory

- **状态**：Implemented（历史）
- **适用范围**：`raw/diagnostics/ssm_reproducer_ab_s2_arms/`、SUMO upstream issue 包
- **决定**：A/B archive 固定为 `ssm_off/attempt-001` 与 `ssm_on/attempt-001`；`EVIDENCE_INVENTORY.sha256` 明确排除自身及其他 inventory 文件。
- **原因**：两臂 case_id 相同，平铺复制会覆盖/混淆 evidence；inventory 自包含条目无意义。
