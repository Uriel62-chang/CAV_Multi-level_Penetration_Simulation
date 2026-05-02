# CAV Multi-level Penetration Simulation

这是一个基于 SUMO 的多级 CAV 渗透率混合交通流仿真项目。

## 目录结构

```text
.
├── add/                    # SUMO附加文件（检测器配置）
├── cfg/                    # SUMO仿真配置文件
├── graph/                  # 仿真结果图表（基本图、通行能力等）
├── net/                    # 路网文件 (.net.xml, .nod.xml, .edg.xml)
├── out/                    # 仿真输出数据（原始XML及汇总CSV）
├── routes/                 # 生成的车辆路径文件 (.rou.xml)
├── scripts/                # 核心Python脚本
│   ├── batch_run.py        # 批处理控制脚本
│   ├── detector_parser.py  # 检测器数据解析工具
│   ├── flow_generator.py   # 混合交通流生成器
│   └── single_run.py       # 单次仿真运行器
├── visualization.py        # 数据可视化与绘图脚本
└── README.md               # 项目说明文档
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
生成车流并使用 GUI 查看（建议拉大 Delay 以观察车流），运行前先清理旧数据：

```bash
rm -r graph/* out/* routes/*
python3 scripts/flow_generator.py --vehN 40 --pCAV 0.5 --loops 300 --seed 1 --out routes/loop.rou.xml
sumo-gui -c cfg/loop.sumocfg
```

#### 批量仿真
执行批量仿真（5% 间隔渗透率，扫描不同车辆密度）：

```bash
python3 scripts/batch_run.py --pstep 0.05 --seeds 1 --outcsv out/results_raw_p05.csv
```

### 5. 数据分析与可视化

处理仿真结果并生成图表：

```bash
python3 visualization.py
```

生成的图表将保存在 `graph/` 目录下。

## 声明

该仿真实验由个人独立完成，仅用于研究、学习。
