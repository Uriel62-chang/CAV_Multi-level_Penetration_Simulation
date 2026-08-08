# 项目约定 (Project Conventions)

## 脚本架构

`scripts/` 为 Python 包（含 `__init__.py`），按领域分为三个子包，Python
脚本之间通过 import 直接调用函数，**不使用 subprocess** 互相调用。调用 SUMO、
netconvert 等外部系统程序不属于这一限制。

- `simulation/single_run.py` — 单次仿真编排，直接调用 `flow_generator.generate_flow()` 和解析器
- `simulation/batch_run.py` — 批量仿真控制器，直接调用 `single_run.prepare_run()`
- `simulation/flow_generator.py` — 混合车流生成，场景专属车辆偏移函数（`_place_vehicles_s0/s1`）
- `simulation/network_generator.py` — 多边形闭环路网源文件生成及外部 netconvert 编译入口
- `parsing/runner.py` — 阶段二：单 run 解析 + 状态机
- `parsing/batch.py` — 阶段二：批量解析调度
- `parsing/` (7 files) — SUMO 输出解析器（detector / ssm / lanechange / edge_performance / edge_emissions / vehroute / stderr）
- `results/writer.py` — 阶段三：统一结果写入
- `results/aggregate.py` — 多种子聚合
- `results/visualization.py` — 数据可视化
- `config.py` `run_spec.py` `schema.py` `experiment_audit.py` — 共享模块（保留在 scripts/ 根部）

### 场景化设计

路网按场景分目录（`net/scenario_X/`），各目录含 `net.json` 元数据。`single_run.py` 通过 `--net` 参数读取元数据，自动适配 edges、检测器、偏移逻辑。新增场景仅需实现专属 `_place_vehicles_sN()` 函数。

## CLI 接口

```bash
# clean clone 先从跟踪的 node/edge 源文件编译四个 SUMO 路网
python3 -m scripts.simulation.network_generator --build-all

# smoke 配置校验（不启动 SUMO）
python3 -m scripts.simulation.batch_run --config configs/smoke.json --dry-run

# 批量仿真阶段一：每个 run 写入独立 raw 目录；--net 必须与 --scenario 同用
python3 -m scripts.simulation.batch_run \
  --config configs/v0.4.2/main.json \
  --scenario scenario_0 \
  --net net/scenario_0/loop.net.xml \
  --model IDM \
  --assignment-seeds 1 \
  --output-root raw \
  --resume

# 阶段二：解析 raw run
python3 -m scripts.parsing.batch --input-root raw --resume

# 阶段三：统一写出 run-level CSV
python3 -m scripts.results.writer \
  --input-root raw \
  --output-dir out \
  --manifest raw/manifest.json

# 多 assignment-seed 聚合（schema=2 强制；--manifest 必需）
python3 -m scripts.results.aggregate \
  --input out/run_level_results.csv \
  --output out/aggregated_results.csv \
  --schema-version 2 \
  --manifest raw/manifest.json

# 单次仿真
python3 -m scripts.simulation.single_run --vehN 30 --pCAV 0.5 --model IDM --net net/scenario_1/loop.net.xml

# v0.4.2 聚合结果可视化
python3 -m scripts.results.visualization \
  --aggregated out/aggregated_results.csv \
  --v4-2
```

## 环境

- 依赖 SUMO (`sumo`, `sumo-gui`, `netconvert`)
- Python 依赖：`pandas`, `matplotlib`
- 使用项目根目录的 `.venv` 虚拟环境运行所有 Python 命令（`ruff`、`mypy`、`pytest`、`compileall` 等）
  ```bash
  .venv/bin/python3 -m pytest -q
  .venv/bin/python3 -m ruff check .
  .venv/bin/python3 -m mypy scripts/run_spec.py scripts/experiment_config.py scripts/provenance.py
  .venv/bin/python3 -m compileall -q scripts tests
  .venv/bin/python3 -m ruff format --check .
  ```

## 当前版本

**v0.4.2 发布目标**（跳号发布；GitHub 最新公开版本仍为 v0.4.0.post3）

> 版本状态（2026-08 更新）：v0.4.1 为本地内部里程碑，**未对外发布**（pilot 未过旧资源
> 门禁），tag 已删，成果并入 v0.4.2 发布说明；已决定**跳号发布**。v0.4.2 主线
> 「设计 → 实现 → 数据 → 结论」四环节已闭环并获正式 Reviewer 背书：
> **U55 重设计（2026-08，内存约束修订）落地 + 正式重跑完成**——7,524 runs 主网格
> （基本图方案：密度轴至 55 veh/km/道；s0/s1 单车道 10–110、s2/s3 双车道 20–220；
> departSpeed="0" + warmup=600（9 档标定 ≤120 s 稳定）；SSM 全开、合并设计）。
> **2026-08 正式重跑：7,524/7,524 全 SUCCESS**（3 workers / 21.86 h / 0 失败；
> 解析 0 INVALID + 插入完整性守卫通过；writer 0 排除；聚合 924 组；可视化 5 主图
> ——FD 峰位/HV→CACC 移动/s0 转角基线/s3 瓶颈语义全部符合设计）。产物：
> out/（run-level 7,524×80、subgroup 782,496 行、aggregated 924 组）、
> graph/v0.4.2/（6 图：5 main-grid + 分析层双 Phase Diagram）、raw/（76 GB，
> 外部备份待处置）。
> **2026-08 发布承接完成（管线审查第五轮）**：aggregated CSV 已 ship 至
> `results/v0.4.2/main/`（924 组 × 329 列，跟踪文件）；报告 `docs/report.cn.md`
> （中文）+ `docs/report.en.md`（英文）；README 重写为 U55 正式口径。
> 旧 A 方案 8,208 为上一版设计（已取代）。
> 公开基线为 v0.4.0.post3；**2026-08 数据清空**：v0.4.0 与 v0.4.2 历史数据
> （raw_v0.4.2/ 34 GB、raw/、results/v0.4.2/、graph/v0.4.2/、docs/report.md）已删
> （用户拍板，外部备份保留）；仓库为纯工具链 + 未来重跑定义（main 全开 SSM）。
> 以下为**外部备份保留**的旧结果清单（仓库内已清空，重跑后按
> writer/aggregate/handover/inventory 链路重建）：aggregated_results.csv、
> result_handover.json、raw_status_inventory.jsonl、result_analysis.md、
> graph/v0.4.2/ 图（main 3 + Safety 1）。
> 时间线说明（管线审查第四轮，消除歧义）：上两行"graph/v0.4.2/ 已删"指 2026-08
> 清空**历史旧网格**产物；U55 正式重跑后 5 图已重新生成并随 commit 233ddff
> **重新入库**（跟踪文件，见上"产物"行）——"清空 → 重跑重建 → 重新入库"为同一
> 时间线的先后节点，二者不冲突。

### v0.4.2 正式网格（新，2026-08 U55 基本图方案）
- main factorial：**7,524 runs（SSM 全开——安全维度并入主网格，合并设计）**：
  s0/s1 单车道 10–110、s2/s3 双车道 20–220（统一密度轴 5–55 veh/km/道，
  上限 55 由 s2 SSM 内存边界（v220=22.67 GiB 实测）约束），cav_count 0.1 步长 11
  档、每 treatment 171 runs、每场景 1,881；s3 为 v0.3.1 几何（32 边形、e15/e16 单车道 125m 瓶颈，net.json 元数据
  驱动，报告单独成图标注瓶颈语义）；departSpeed="0" + warmup=600（标定闭环）。
- 旧网格历史（2026-08 已清空、外部备份保留）：main 3,888（SSM 关闭）关键数值
  s2 CACC 全 CAV 峰值 7,128 veh/h、s3 高密度全 CAV 瓶颈反转；独立 safety 84 runs
  s1/s2 零检出；SSM-on 峰值 RSS 按场景 s0 6.52 / s1 1.81 / s2 8.91 / s3 1.50 GiB
  （与 B 线历史观测一致，不作硬预算——仅历史内存参考）
- subgroup HV/CAV 分拆、排放双口径（non-internal 主 + 全路网次要）、双 seed 统计单位

### 阶段 2 交付
- HV/CAV 子群拆分（detector/edgeData/SSM/vehroute/lanechange/stderr + FCD headway）
- `parsing/metrics.py` 统一指标计算与 subgroup 长表生成
- schema=2 writer/aggregate 路由（`--schema-version` 必填）
- SSM 敏感性 CLI（none/greedy/sorted_greedy dedup）
- 自由流参考测量
- 66 个 stage2 测试（总 170）

### 阶段 0 交付
- cav_count 双 seed 网格（新 run_id 格式 `s2_IDM_v120_c060_as01_ss101`）
- RunSpec 哈希向后兼容（legacy to_dict 不含新字段）
- inactive dimension 规范化（cav=0 → model="IDM" sentinel, seed=0 sentinel）
- resume 输入完整性校验（routes.rou.xml, vehicle_type_map.json, SHA-256）
- v0.4.1 非 dry-run 门禁已解除

### 阶段 1 交付
- SUMO 命令注入 `--seed`、`--device.ssm.measures/thresholds/range`、FCD 输出
- additional 文件 `withInternal="true"`
- writer `non_internal_edge_vehicle_km` 列名语义修正
- 进程退出轮询检测（不依赖 `process.wait()` 唤醒）
- SIGINT → CANCELLED 状态机
- CLI `--assignment-seeds` / `--sumo-seeds` 命名

### 推迟到 1.post1
- S8 剩余项：PreparedRun.fcd_path（canonical_json_bytes、atomic_write_bytes、--acceptance 已在阶段 2 实现）

### 测试基线
- 492 tests passed（当前基线：451 基线 + 38 分析层 + 1 R13 零方差回归 + 2 R16
  回归；历史追溯：pipeline.md 第一轮记 445 → 第一轮修订 P2-1/P2-2 回归 2 条
  → 447 → round 9 free_flow/FCD 回归 2 条 → 449 → ACC 兼容 +2 → 451 → 分析层
  38 → 489 → R13 零方差回归 → 490 → R16 CLI/死分支回归 2 条 → 492）
- Ruff / mypy / compileall / format 全通过
- dry-run: main 7,524（U55）/ smoke（configs/smoke.json；v0.4.0 10,080 网格
  数据红线不重跑、本地数据已删（2026-08 用户拍板，外部备份保留）、配置已移除；
  旧独立 safety 84 runs 已随 2026-08 合并设计删除（安全维度并入主网格）；
  v0.4.1 正式实验配置已归档 docs/internal/archive/configs-v0.4.1/）
- aggregate 现已要求 --schema-version 参数
- 使用项目根目录的 `.venv` 虚拟环境运行所有 Python 命令（`ruff`、`mypy`、`pytest`、`compileall` 等）
  ```bash
  .venv/bin/python3 -m pytest -q
  .venv/bin/python3 -m ruff check .
  .venv/bin/python3 -m mypy scripts/run_spec.py scripts/experiment_config.py scripts/provenance.py
  .venv/bin/python3 -m compileall -q scripts tests
  .venv/bin/python3 -m ruff format --check .
  ```

## 辅助文档

以下文件是被 Git 忽略的本地维护记录，用于项目作者日后回顾 v0.4.0–post2
期间已经识别或处理的实验与工程问题。它们不是运行、验证、复现实验或使用公开
仓库所需的依赖；公开克隆中不存在这些文件属于预期行为。文件在本地存在时，可
在维护项目或追溯历史决策时按需读取：

- `docs/internal/roadmap.md` — 开发路线图（已完成/待办阶段）
- `docs/internal/experiment-issues.md` — 已完成实验的设计问题与解释边界
- `docs/internal/engineering-issues.md` — 工程问题与处理记录
- `docs/internal/README.md` — 本地维护文档与历史归档索引
