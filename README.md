# CAV Multi-level Penetration Simulation

基于 SUMO 的 CAV 多级渗透率混合交通流仿真与通行能力分析。

*SUMO-based mixed traffic flow simulation and capacity analysis under multi-level CAV penetration rates.*

> 当前版本 **v0.1.0** · [开发路线图](vibecoding/DEVELOPMENT.md)

## 目录结构

```text
.
├── add/                    # SUMO 附加文件（检测器配置）
├── cfg/                    # SUMO 仿真配置文件
├── graph/                  # 仿真结果图表（运行后生成）
├── net/                    # 路网源文件（节点、边）
├── out/                    # 仿真输出数据（运行后生成）
├── routes/                 # 生成的车辆路径文件（运行后生成）
├── scripts/                # 核心 Python 脚本
│   ├── batch_run.py        # 批量仿真控制器
│   ├── detector_parser.py  # 检测器 XML 解析
│   ├── flow_generator.py   # 混合交通流生成
│   └── single_run.py       # 单次仿真编排
├── vibecoding/             # 开发辅助文档
│   └── DEVELOPMENT.md      # 开发路线图
├── AGENTS.md               # 项目约定（opencode 自动加载）
├── visualization.py        # 数据可视化
└── README.md
```

## 环境依赖

- [SUMO](https://sumo.dlr.de/) ≥ 1.25 (`sumo`, `netconvert`)
- Python ≥ 3.10
- pandas、matplotlib

```bash
pip install pandas matplotlib
```

## 快速上手

### 1. 编译路网

```bash
netconvert -n net/nodes.nod.xml -e net/edges.edg.xml -o net/loop.net.xml
```

### 2. 单次验证

生成车流并用 GUI 预览（建议拉大 Delay 以观察车流）：

```bash
python scripts/flow_generator.py --vehN 40 --pCAV 0.5 --loops 300 --seed 1 --out routes/loop.rou.xml
sumo-gui -c cfg/loop.sumocfg
```

### 3. 批量仿真

```bash
python scripts/batch_run.py --pstep 0.05 --seeds 1 --outcsv out/results_raw.csv
```

### 4. 可视化

```bash
python visualization.py --csv out/results_raw.csv
```

生成的图表保存在 `graph/` 下。

## 声明

该项目由个人独立完成，仅用于研究、学习。
