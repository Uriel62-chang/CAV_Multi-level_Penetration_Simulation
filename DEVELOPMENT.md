# 开发文档

> 新 Developer、Improver 或 Reviewer 开始工作前应先阅读：
> 1. README.md
> 2. 本文档
> 3. `docs/internal/releases/v0.4.1.md`（当前阶段任务）
> 4. 关键决策记录
> 5. 交接摘要
> 6. 最近相关 Git 提交（`git log --oneline -10`）

---

## 关键决策

### D-001：cav_count=0 时 RunSpec.model 使用 sentinel "IDM" 而非 JSON null

- **背景**：v0.4.1 设计文档要求无 CAV 时 model=null、assignment_seed=null。RunSpec 的 model 字段类型为 `str`，改为 `Optional[str]` 会波及所有消费方（flow_generator、parser、writer、aggregate、visualization），改动量相当于贯穿式重构。
- **决定**：cav_count=0 时 model 固定为 "IDM"（字母序首个合法 CAV 模型），seed 固定为 0。run_id 使用 "HVONLY" token 和 "as00" 表示非活动维度。非活动语义由 `cav_count ∈ {0, vehN}` 唯一确定。
- **原因**：RunSpec 类型系统改动波及过大；sentinel 方案在不改变类型的前提下达到语义等价。
- **已考虑的替代方案**：Optional[str] + Optional[int]（改动量过大）；空字符串（flow_generator 不接受）。
- **当前代价**：与设计文档的 null 要求存在字面差异；后续聚合需根据 cav_count 而非 model/seed 判断非活动维度。
- **不应随意破坏的约束**：model 字段类型不可改为 Optional。

### D-002：route/type-map 哈希归属 simulation_status 而非 RunSpec SHA

- **背景**：设计文档最初要求 route_file_sha256 和 vehicle_type_map_sha256 进入 RunSpec 稳定 SHA。但这两个哈希在 RunSpec 创建时尚不存在（需 flow_generator 运行后才能计算）。
- **决定**：route/type-map 哈希记录在 simulation_status.json 中，由 is_simulation_complete() 校验；RunSpec 的稳定 SHA 仅覆盖仿真参数和双 seed。
- **原因**：两阶段构造（先创建 spec → 再回填哈希）引入不必要的复杂度；status 文件是 resume 的唯一数据源，哈希放在那里形成闭环。
- **已考虑的替代方案**：在 prepare_run() 中修改 RunSpec 并重写（破坏 frozen dataclass 不可变性）。
- **当前代价**：RunSpec SHA 不覆盖输入文件完整性（需配合 status 文件校验）。

### D-003：schema_version 路由推迟到阶段 2

- **背景**：v0.4.1 新增了 FCD、THW、子群等列，需 parser/writer 切换到新 schema。但阶段 1 只产生 raw，不调用解析链路。
- **决定**：阶段 1 的 RunSpec 使用 schema_version="2" 作为身份标记，但 parser/writer 仍使用旧的 schema=1 路由。实际列切换在阶段 2 完成。
- **原因**：schema 路由是 parser/writer 层的改动，与阶段 1 的 SUMO 命令构建无关；分离关注点避免一次改动涉及过多模块。
- **当前代价**：schema_version="2" 的 raw 暂时无法被 writer 解析（阶段 1 不调用 writer，无实际影响）。

### D-004：进程退出检测使用轮询而非 asyncio.wait_for

- **背景**：asyncio 的 `process.wait()` 在某些 Linux 内核/SUMO 版本组合下不会自主唤醒，即使子进程已退出且 `process.returncode` 已设置。
- **决定**：用 `while` 轮询 `process.returncode`（默认间隔 0.5s，硬截止 7200s），替代直接 `await process.wait()`。
- **原因**：`process.returncode` 是 asyncio 在子进程退出时立即设置的属性，轮询它比等待 `wait()` 唤醒更可靠。
- **已考虑的替代方案**：只对显式 timeout 使用轮询，默认仍用 `wait()`（不解决默认无限等待）。
- **当前代价**：增加 0.5s 轮询间隔的 CPU 开销（可忽略）；mock 测试中的 Process 类需添加 `returncode` 属性。

### D-005：S8 冻结输入、PreparedRun.fcd_path、环路距离校验推迟到 1.post1

- **背景**：阶段 1 的主要目标是让 SUMO 命令实际产生与配置声明一致的 raw。冻结输入（canonical_json_bytes、atomic_write_bytes、四状态冲突、三方 SHA、--acceptance CLI）是实现 provenance 可追溯性的独立功能，不影响 raw 生成的核心路径。
- **决定**：S8 及相关子项推迟到阶段 1.post1。阶段 1 的解除门禁条件改为 S1–S7, S9, S10。
- **原因**：冻结输入功能自包含，推迟不影响阶段 2 对阶段 1 产出 raw 的解析和验证（raw 本身已正确生成）。
- **已考虑的替代方案**：在阶段 1 内完成所有 S1–S9（导致阶段 1 无法收敛）。
- **当前代价**：暂无 frozen_inputs/ 目录和非 resume 覆盖保护。

---

## 当前交接摘要

### 已完成

- **已实现**：cav_count 双 seed 网格 + inactive-dimension 规范化；SUMO 命令注入 seed/SSM capture/FCD 输出；withInternal=true additional 文件；writer `non_internal_edge_vehicle_km` 列名语义修正；进程退出轮询检测 + SIGINT→CANCELLED 状态机；CLI `--assignment-seeds`/`--sumo-seeds` 命名。
- **已验证**：104 tests passed；pilot dry-run 162 唯一 run；legacy 10,080 dry-run 无回归；smoke SUMO run SUCCESS + resume SKIPPED；FCD gzip 有效。
- **已提交**：阶段 0（`acb5bc6`）→ 阶段 1（`05ab6bb`~`a999e77`），共 14 commits。

### 当前状态

- **当前分支**：`main`
- **最近稳定提交**：`a999e77` docs: update AGENTS.md with v0.4.1 stage 1 completion status
- **可正常运行的入口**：
  - `python3 -m scripts.simulation.batch_run --config configs/v0.4.1/smoke.json --output-root /tmp/smoke --sumo-processes 1`
  - `python3 -m scripts.simulation.batch_run --config configs/v0.4.1/pilot.json --dry-run`
  - `python3 -m scripts.simulation.batch_run --config configs/v0.4.0.json --dry-run`

### 待处理

- **下一阶段任务**：阶段 2 — HV/CAV 子群指标拆分、FCD THW 解析、SSM 敏感性分析、自由流参考、micro-pilot（见 `docs/internal/releases/v0.4.1.md` 第 2.1–2.2 节）。
- **已知问题**：无已知阻塞缺陷。
- **暂缓问题**：
  - S8 冻结输入 → 1.post1
  - PreparedRun.fcd_path → 1.post1
  - fcd_max_leader_distance_m ≥ 环路总长校验 → 1.post1
  - test_simulation_state_machine 缺少「进程启动后 SIGINT」测试

### 重要约束

- **不得修改**：`configs/v0.4.0.json`、`configs/smoke.json`（旧 config 哈希基线）；old RunSpec `to_dict()` 输出字段集；legacy SUMO 命令字节序列。
- **需要保持兼容**：`build_run_id()` 旧调用方式（`cav_count=None` 走 legacy 格式）；flow_generator 输出；10,080 旧 run ID 列表。
- **修改前必须确认**：`ExperimentConfig.sha256()` 是否变化（基线 `178dfcef...`）；旧 pipeline dry-run 仍为 10,080；RunSpec legacy hash 不变（`090ca5c3...`）。

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

**不直接修改代码**，避免审查和实现职责混合。
