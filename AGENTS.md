# 项目约定 (Project Conventions)

## 脚本架构

`scripts/` 为 Python 包（含 `__init__.py`），按领域分为三个子包，脚本间通过 import 直接调用函数，**不使用 subprocess** 互相调用。

- `simulation/single_run.py` — 单次仿真编排，直接调用 `flow_generator.generate_flow()` 和解析器
- `simulation/batch_run.py` — 批量仿真控制器，直接调用 `single_run.prepare_run()`
- `simulation/flow_generator.py` — 混合车流生成，场景专属车辆偏移函数（`_place_vehicles_s0/s1`）
- `simulation/network_generator.py` — 多边形闭环路网生成器
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
# 批量仿真（--net 指定路网；--model 可选 IDM / ACC / CACC）
python3 -m scripts.simulation.batch_run --pstep 0.20 --seeds 1 --model IDM --net net/scenario_0/loop.net.xml --outcsv out/results.csv

# 单次仿真
python3 -m scripts.simulation.single_run --vehN 30 --pCAV 0.5 --model IDM --net net/scenario_1/loop.net.xml

# 可视化（scenario_1 需通过 --net 自动读取环路总长）
python3 -m scripts.results.visualization --csv out/results.csv
python3 -m scripts.results.visualization --csv out/results.csv --net net/scenario_1/loop.net.xml
```

## 环境

- 依赖 SUMO (`sumo`, `sumo-gui`, `netconvert`)
- Python 依赖：`pandas`, `matplotlib`

## 辅助文档

以下文件是被 Git 忽略的本地维护记录，用于项目作者日后回顾 v0.4.0–post2
期间已经识别或处理的实验与工程问题。它们不是运行、验证、复现实验或使用公开
仓库所需的依赖；公开克隆中不存在这些文件属于预期行为。文件在本地存在时，可
在维护项目或追溯历史决策时按需读取：

- `docs/internal/roadmap.md` — 开发路线图（已完成/待办阶段）
- `docs/internal/experiment-issues.md` — 已完成实验的设计问题与解释边界
- `docs/internal/engineering-issues.md` — 工程问题与处理记录
- `docs/internal/README.md` — 本地维护文档与历史归档索引
