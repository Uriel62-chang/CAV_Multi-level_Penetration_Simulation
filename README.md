# CAV Multi-level Penetration Simulation

基于 SUMO 的 CAV 多级渗透率混合交通流仿真与通行能力分析。

*SUMO-based mixed traffic flow simulation and capacity analysis under multi-level CAV penetration rates.*

> 当前版本 **v0.3.1** · [开发路线图](vibecoding/DEVELOPMENT.md)

### v0.3.1 修复

- **scenario_0 junction margin**：`_place_vehicles_s0()` 补全边界回绕逻辑（与 s1/s2/s3 对齐），避免特定车辆数下 departPos 落在边端点。
- **多车道 det_xml**：`det_xml` 列改为分号拼接所有车道检测器路径，不再只记录第一条车道。

### v0.3.0 主要变更

- **检测器频率 60s → 120s**：修复与环路单圈耗时（≈60s）的采样共振。v0.2.0 使用的 60s 频率与车辆周期通过检测器的时间形成 1:1 共振，导致流量数据大幅非物理波动。120s 下每窗口覆约 2 圈流量，消除共振。所有场景结果不可与旧版 60s 数据直接混用。
- **场景化路网**：新增 scenario_1（32边形单车道平滑闭环）、scenario_2（32边形双车道 + LC2013 换道）、scenario_3（32边形双车道 + 125m 单车道瓶颈），原方形闭环迁移为 scenario_0（baseline）。
- **多边形路网生成器**：`scripts/network_generator.py`，支持任意边数/车道数/半径。
- **多车道检测器聚合**：`parse_detector_multi()` 按时间窗口跨车道加权聚合。
- **场景注册表**：`flow_generator.py` 中 `_PLACEMENT_REGISTRY`，新增场景仅需追加 1 个偏移函数。

## 目录结构

```text
.
├── add/                    # SUMO 附加文件（检测器配置）
├── cfg/                    # SUMO 仿真配置文件
├── graph/                  # 仿真结果图表（运行后生成）
├── net/                    # 路网源文件（按场景分目录）
│   ├── scenario_0/         # 方形闭环（baseline）
│   ├── scenario_1/         # 32边形单车道平滑闭环
│   ├── scenario_2/         # 32边形双车道闭环
│   └── scenario_3/         # 32边形双车道 + 125m单车道瓶颈
├── out/                    # 仿真输出数据（运行后生成）
├── routes/                 # 生成的车辆路径文件（运行后生成）
├── scripts/                # 核心 Python 脚本
│   ├── batch_run.py        # 批量仿真控制器
│   ├── detector_parser.py  # 检测器 XML 解析
│   ├── flow_generator.py   # 混合交通流生成
│   ├── network_generator.py# 多边形路网生成器
│   └── single_run.py       # 单次仿真编排
├── vibecoding/             # 开发辅助文档
│   └── DEVELOPMENT.md      # 开发路线图
├── AGENTS.md               # 项目约定
├── visualization.py        # 数据可视化
├── README.md
└── LICENSE
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
# 生成路网源文件
netconvert -n net/scenario_0/nodes.nod.xml -e net/scenario_0/edges.edg.xml -o net/scenario_0/loop.net.xml
netconvert -n net/scenario_1/nodes.nod.xml -e net/scenario_1/edges.edg.xml -o net/scenario_1/loop.net.xml
netconvert -n net/scenario_2/nodes.nod.xml -e net/scenario_2/edges.edg.xml -o net/scenario_2/loop.net.xml
netconvert -n net/scenario_3/nodes.nod.xml -e net/scenario_3/edges.edg.xml -o net/scenario_3/loop.net.xml
```

### 2. 单次验证

```bash
# GUI 预览路网
sumo-gui -n net/scenario_3/loop.net.xml

# 单次仿真（含车流生成 + SUMO 仿真 + 检测器解析）
python3 scripts/single_run.py --vehN 60 --pCAV 0.5 --model IDM --net net/scenario_3/loop.net.xml --outcsv out/test.csv
```

### 3. 批量仿真

```bash
# scenario_0 方形闭环（单车道，vehN 10~120）
python3 scripts/batch_run.py --pstep 0.05 --model IDM --net net/scenario_0/loop.net.xml --outcsv out/results_s0_IDM.csv

# scenario_1 32边形单车道平滑闭环
python3 scripts/batch_run.py --pstep 0.05 --model IDM --net net/scenario_1/loop.net.xml --outcsv out/results_s1_IDM.csv

# scenario_2 32边形双车道闭环（vehN 20~240）
python3 scripts/batch_run.py --pstep 0.05 --vehN-list "20,40,60,80,100,120,140,160,180,200,220,240" --model CACC --net net/scenario_2/loop.net.xml --outcsv out/results_s2_CACC.csv

# scenario_3 32边形双车道 + 125m 单车道瓶颈
python3 scripts/batch_run.py --pstep 0.05 --vehN-list "20,40,60,80,100,120,140,160,180,200,220,240" --model IDM --net net/scenario_3/loop.net.xml --outcsv out/results_s3_IDM.csv
```

### 4. 可视化

```bash
python3 visualization.py --csv out/results_s0_IDM.csv --outDir graph/s0_IDM
python3 visualization.py --csv out/results_s1_IDM.csv --net net/scenario_1/loop.net.xml --outDir graph/s1_IDM
python3 visualization.py --csv out/results_s2_IDM.csv --net net/scenario_2/loop.net.xml --outDir graph/s2_IDM
python3 visualization.py --csv out/results_s3_IDM.csv --net net/scenario_3/loop.net.xml --outDir graph/s3_IDM
```

生成的图表（密度-流量基本图 + 渗透率-通行能力曲线）保存在 `graph/` 下。

## 声明

该项目由个人独立完成，仅用于研究、学习。
