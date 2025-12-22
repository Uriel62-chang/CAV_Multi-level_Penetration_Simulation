# CAV Multi-level Penetration Simulation

这是一个基于 SUMO 的多级 CAV 渗透率混合交通流仿真项目。

## 目录结构

```text
.
├── add/                    # 附加文件（如检测器定义）
├── cfg/                    # SUMO仿真配置文件
├── graph/                  # 可视化图表目录（包含FD图等）
├── net/                    # SUMO路网文件
├── out/                    # 仿真输出文件（XML结果及CSV）
├── scripts/                # 核心脚本目录
│   ├── batch.py            # 批处理仿真脚本
│   ├── e1Parser.py         # 检测器数据解析
│   ├── FlowGenerate.py     # 混合车流生成
│   └── run.py              # 单次仿真执行脚本
└── DataVisualization.py    # 数据可视化脚本
```

## 快速上手 (Ubuntu 20.04)

以下命令默认在 Ubuntu 20.04 终端执行。工程目录为：`~/CAV_Multi-level_Penetration_Simulation`。

### 1. 环境准备

安装 SUMO 与 Python 环境：

```bash
sudo apt update
sudo apt install -y sumo sumo-tools sumo-doc python3 python3-pip
python3 -m pip install -U pandas matplotlib
```

### 2. 获取代码

拉取项目源码，并进入工程目录：

```bash
git clone https://github.com/Uriel62-chang/CAV_Multi-level_Penetration_Simulation.git
cd ~/CAV_Multi-level_Penetration_Simulation
```

### 3. 编译路网

根据节点和边文件生成路网：

```bash
netconvert -n net/nodes.nod.xml -e net/edges.edg.xml -o net/loop.net.xml
```

### 4. 运行仿真

#### 单次验证
生成车流并使用 GUI 查看（建议拉大 Delay 以观察车流）：

```bash
python3 scripts/FlowGenerate.py --vehN 40 --pCAV 0.5 --loops 300 --seed 1 --out routes/loop.rou.xml
sumo-gui -c cfg/loop.sumocfg
```

#### 批量仿真
执行批量仿真（5% 间隔渗透率，扫描不同车辆密度），运行前先清理旧数据：

```bash
rm -r graph/* out/* routes/*
python3 scripts/batch.py --pstep 0.05 --seeds 1 --outcsv out/results_raw_p05.csv
```

### 5. 数据分析与可视化

处理仿真结果并生成图表：

```bash
python3 DataVisualization.py
```

生成的图表将保存在 `graph/` 目录下。

