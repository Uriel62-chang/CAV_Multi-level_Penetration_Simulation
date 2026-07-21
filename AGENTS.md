# 项目约定 (Project Conventions)

## 脚本架构

`scripts/` 为 Python 包（含 `__init__.py`），脚本间通过 import 直接调用函数，**不使用 subprocess** 互相调用。

- `batch_run.py` — 批量仿真控制器，直接调用 `single_run.run_simulation()`
- `single_run.py` — 单次仿真编排，直接调用 `flow_generator.generate_flow()` 和 `detector_parser.parse_detector()`
- `flow_generator.py` — 混合车流生成，场景专属车辆偏移函数（`_place_vehicles_s0/s1`）
- `detector_parser.py` — SUMO 检测器 XML 解析
- `network_generator.py` — 多边形闭环路网生成器
- `visualization.py` — 数据可视化（位于项目根目录）

### 场景化设计

路网按场景分目录（`net/scenario_X/`），各目录含 `net.json` 元数据。`single_run.py` 通过 `--net` 参数读取元数据，自动适配 edges、检测器、偏移逻辑。新增场景仅需实现专属 `_place_vehicles_sN()` 函数。

## CLI 接口

```bash
# 批量仿真（--net 指定路网；--model 可选 IDM / ACC / CACC）
python3 scripts/batch_run.py --pstep 0.20 --seeds 1 --model IDM --net net/scenario_0/loop.net.xml --outcsv out/results.csv

# 单次仿真
python3 scripts/single_run.py --vehN 30 --pCAV 0.5 --model IDM --net net/scenario_1/loop.net.xml

# 可视化（scenario_1 需通过 --net 自动读取环路总长）
python3 visualization.py --csv out/results.csv
python3 visualization.py --csv out/results.csv --net net/scenario_1/loop.net.xml
```

## 环境

- 依赖 SUMO (`sumo`, `sumo-gui`, `netconvert`)
- Python 依赖：`pandas`, `matplotlib`

## vibecoding 辅助文档

启动时自动读取 `vibecoding/` 目录下的所有文档（含当前及后续迭代的开发规划）：
- `vibecoding/DEVELOPMENT.md` — 开发路线图（已完成/待办阶段）
