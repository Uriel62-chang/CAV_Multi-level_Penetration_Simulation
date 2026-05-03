# 项目约定 (Project Conventions)

## 脚本架构

`scripts/` 为 Python 包（含 `__init__.py`），脚本间通过 import 直接调用函数，**不使用 subprocess** 互相调用。

- `batch_run.py` — 批量仿真控制器，直接调用 `single_run.run_simulation()`
- `single_run.py` — 单次仿真编排，直接调用 `flow_generator.generate_flow()` 和 `detector_parser.parse_detector()`
- `flow_generator.py` — 混合车流生成
- `detector_parser.py` — SUMO 检测器 XML 解析
- `visualization.py` — 数据可视化（位于项目根目录）

## 代码风格

- 模块名：`snake_case`（PEP 8）
- 变量/函数名：`snake_case`，含描述性全称，禁止单字母缩写
- 注释：中文

## CLI 接口

命令行参数保持不变，常用命令：
```bash
python3 scripts/batch_run.py --pstep 0.20 --seeds 1 --outcsv out/results_raw_p20.csv
python3 visualization.py --csv out/results_raw_p20.csv
```

## 环境

- 依赖 SUMO (`sumo`, `sumo-gui`, `netconvert`)
- Python 依赖：`pandas`, `matplotlib`

## vibecoding 辅助文档

启动时自动读取 `vibecoding/` 目录下的所有文档（含当前及后续迭代的开发规划）：
- `vibecoding/DEVELOPMENT.md` — 开发路线图（已完成/待办阶段）
