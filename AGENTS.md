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
  --config configs/v0.4.0.json \
  --scenario scenario_0 \
  --net net/scenario_0/loop.net.xml \
  --model IDM \
  --seeds 1 \
  --output-root raw \
  --resume

# 阶段二：解析 raw run
python3 -m scripts.parsing.batch --input-root raw --resume

# 阶段三：统一写出 run-level CSV
python3 -m scripts.results.writer \
  --input-root raw \
  --output-dir out \
  --manifest raw/manifest.json

# 多 assignment-seed 聚合
python3 -m scripts.results.aggregate \
  --input out/run_level_results.csv \
  --output out/aggregated_results.csv \
  --schema-version 1

# 单次仿真
python3 -m scripts.simulation.single_run --vehN 30 --pCAV 0.5 --model IDM --net net/scenario_1/loop.net.xml

# v0.4 聚合结果可视化
python3 -m scripts.results.visualization \
  --aggregated out/aggregated_results.csv \
  --v4
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

**v0.4.1 阶段 2 完成**（2026-07-29）

### 阶段 2 交付
- HV/CAV 子群拆分（detector/edgeData/SSM/vehroute/lanechange/stderr + FCD headway）
- `parsing/metrics.py` 统一指标计算与 subgroup 长表生成
- schema=2 writer/aggregate 路由（`--schema-version` 必填）
- SSM 敏感性 CLI（none/greedy/sorted_greedy dedup）
- 自由流参考测量
- 45 个 stage2 测试（总 149）

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
- S8 冻结输入（canonical_json_bytes, atomic_write_bytes, --acceptance）
- PreparedRun.fcd_path

### 测试基线
- 149 tests passed（85 legacy + 19 v0.4.1 + 45 stage2）
- Ruff / mypy / compileall / format 全通过
- dry-run: v0.4.0 10,080 / pilot 162 / smoke 1
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
