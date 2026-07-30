# 开发文档

> 新参与者应先阅读：
> 1. README.md
> 2. 本文档（关键决策 + 交接摘要）
> 3. AGENTS.md（项目约定、CLI 入口）
> 4. `docs/development/v0.4.1-stage2-design.md`（当前阶段批准基线）
> 5. `git log --oneline -10`
>
> 补充材料（Git 忽略，本地可用时参考）：
> `docs/internal/releases/v0.4.1.md`（完整开发计划）、
> `docs/internal/releases/v0.4.1-stage1-design.md`（阶段 1 设计文档）
>
> 阶段 2 批准基线已受 Git 跟踪；实现或审查不得用聊天记录覆盖其函数契约、校验矩阵和验收探针。

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

### D-005：S8 冻结输入推迟到 1.post1

- **状态**：Deferred（部分完成：环路距离校验已在阶段 2 实现）
- **决策提交**：`59c1b17`
- **适用范围**：frozen_inputs、canonical_json_bytes、atomic_write_bytes、--acceptance CLI、PreparedRun.fcd_path
- **重新评估触发条件**：阶段 1.post1 开始
- **背景**：冻结输入是实现 provenance 可追溯性的独立功能，不影响 raw 生成核心路径。
- **决定**：推迟到阶段 1.post1。阶段 1 解除门禁条件改为 S1–S7, S9, S10。
- **当前代价**：暂无 frozen_inputs 目录、非 resume 覆盖保护和 fcd_path 字段。

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
- **决定**：legacy `to_dict()` 只输出 v0.4.0 字段集；精确匹配已发布 v0.4.0 配置的实例返回冻结哈希，其他配置仍按规范 JSON 计算。
- **原因**：使原始 `run_spec.json` / `simulation_status.json` 可在不重写历史产物的前提下被 resume 验证，同时保证任一配置修改不会被误认作冻结配置。
- **当前代价**：该单一已发布配置需保留显式识别器和回归探针。

---

## 当前交接摘要

### 已完成

- **阶段 0+1 已实现**：cav_count 双 seed 网格 + inactive-dimension 规范化；SUMO 命令注入 seed/SSM capture/FCD 输出；withInternal=true additional；writer `non_internal_edge_vehicle_km` 列名修正；进程退出轮询 + SIGINT→CANCELLED；CLI `--assignment-seeds`/`--sumo-seeds` 命名。
- **阶段 2 完成**（2026-07-30，v0.4.1 发布）：HV/CAV 子群拆分；FCD physical THW；SSM pair/role provenance（D-006）；schema=2 runner/writer/aggregate；subgroup JSONL + SHA；自由流 artifact（D-008）；SSM sensitivity CLI；free-flow 测量；FCD numpy 内存方案（D-007）；net.json num_lanes fail-closed（D-009）；fragment merge（opt-in）；`--frozen-inputs`；per-run RSS；sim→parse→write→aggregate smoke。
- **已验证**：170 tests passed；Ruff/mypy/format/compileall 通过；pilot 162 与 legacy 10,080 dry-run 通过；micro-pilot Level 1 通过（10/10）；Level 2 bounded factorial pilot 完成（162 runs, failed original resource gate）；mitigation calibration 完成（48 runs with extratime=1.0+merge, failed simultaneous fidelity+RSS gates）。
- **已提交**：阶段 2 从设计基线 `460f0e6` 到 v0.4.1 发布。

### 当前状态

- **当前分支**：`main`
- **本文档最后更新**：参见 `git log -1 --oneline -- DEVELOPMENT.md`
- **验证环境**：SUMO 1.27.1, Python 3.10, .venv/; 验证日期 2026-07-30
- **可运行入口**：
  ```bash
  .venv/bin/python3 -m scripts.simulation.batch_run --config configs/v0.4.1/smoke_v4_1.json --output-root /tmp/smoke --sumo-processes 1
  .venv/bin/python3 -m scripts.parsing.batch --input-root /tmp/smoke
  .venv/bin/python3 -m scripts.results.writer --input-root /tmp/smoke --output-dir /tmp/smoke-out --manifest /tmp/smoke/manifest.json
  .venv/bin/python3 -m scripts.results.aggregate --input /tmp/smoke-out/run_level_results.csv --output /tmp/smoke-out/aggregated_results.csv --schema-version 2
  .venv/bin/python3 -m scripts.simulation.batch_run --config configs/v0.4.1/pilot.json --dry-run
  .venv/bin/python3 -m scripts.simulation.batch_run --config configs/v0.4.0.json --dry-run
  ```

### 待处理

- **v0.4.2**：分拆设计——主 factorial 关闭 SSM 运行效率/排放/FCD 完整网格；独立 safety experiment 专门定义 TTC/DRAC estimand。
- **SUMO upstream**：s2 无事件但 RSS ~9 GiB 的 encounter-tracking 行为，制作最小复现提交。
- **known gaps**：SSM sensitivity 三种 dedup 未覆盖 crossing/merging 探针。
- **暂缓**：S8 冻结输入、PreparedRun.fcd_path → 1.post1。

### 重要约束

- **不得未经版本化决策修改**：`configs/v0.4.0.json`、`configs/smoke.json`（旧哈希基线）；legacy RunSpec.to_dict() 字段集；legacy SUMO 命令字节序列。修改时必须同步更新哈希基线和兼容测试。
- **需要保持兼容**：`build_run_id()` 旧调用方式（`cav_count=None` 走 legacy 格式）；flow_generator 输出；10,080 旧 run ID 列表。
- **schema=2 完整性约束**：detector 必须覆盖 net.json 指定的全部 lane，且每个 lane 同时存在 all/HV/CAV；net.json 异常不得回退单车道。subgroup JSONL 必须存在、非空且 SHA 与 parse_status 一致。
- **自由流约束**：不得恢复硬编码 98.8 fallback；artifact 的 SUMO 完整版本、scenario net SHA、HV/当前 model 有限正圈时必须全部匹配。
- **修改前验证**：`ExperimentConfig.sha256() == 178dfcef...`；旧 pipeline dry-run 10,080；RunSpec legacy hash 不变；涉及 schema=2 时额外运行 pilot 162 dry-run 和定向完整性探针。

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
