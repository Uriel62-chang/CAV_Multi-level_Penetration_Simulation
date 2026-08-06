# v0.4.2 正式实验报告：CAV 多级渗透仿真（U55 基本图方案）

> **版本**：v0.4.2（跳号发布；v0.4.1 为本地内部里程碑，未对外发布，成果并入本版）
> **网格**：7,524 runs 主网格（main factorial，SSM 全开——合并设计）
> **仿真**：SUMO 1.27.1 · 3 workers / 21.86 h / 0 失败 · 观测窗 [600, 1800)
> **数据**：`results/v0.4.2/main/aggregated_results.csv`（924 组 × 329 列）；raw 76 GB 外部备份
> **英文版**：`docs/report.en.md`

---

## 摘要

本实验在四种递进受限的路网结构（s0 方形单车道 → s1 平滑单车道 → s2 双车道 → s3
合流瓶颈）上，以统一密度轴 5–55 veh/km/道、cav_count 0.1 步长 11 档、3×3 双 seed
的 7,524-run 主网格，系统比较 IDM 与 CACC 两种跟驰控制在**流量、安全、排放、效率**
四个维度上的表现。主要结论：

1. **通行能力基本图成立且峰位随渗透率移动**：HV 峰位 k≈20、CACC 全 CAV k≈40，
   方向与理论临界密度（HV 17.4 / CAV 39.2 veh/km/道）一致；IDM 全 CAV 高密度支在
   轴上限（55 = 37.5% kj）内未观测到下降支，k≈50 为网格观测最大而非通行能力峰位。
2. **s0 转角基线**：方形 90° 转角把自由流速度钉在 ~17.9 m/s，HV 流量在 ~940
   veh/h/道平顶（k≥20），全 CAV 峰值 1,794（IDM）/ 1,857（CACC）@ k40。
3. **s3 高密度合流瓶颈反转**：k=55 全 CAV 时 IDM 1,620 veh/h/道、CACC 756
   veh/h/道——CACC 在高密度强制合流下吞吐劣化，delay 与排放同时上升。
4. **无全局最优模型**：CACC 在平滑无约束环境下优势明显，在瓶颈强制合流下劣化；
   安全事件（TTC）集中于高密度档（s1/s2 仅 k≥35 检出），s3 为事故高发场景。

---

## 1. 背景与动机

车辆自动化与网联化（CAV）被预期提升通行能力与行车安全，但其**收益是否伴随安全、
排放或时间效率代价**是核心开放问题。早期版本（v0.4.0，10,080-run 网格）主要评估
通行能力维度；v0.4.2 将评价框架扩展为四维（流量/安全/排放/效率），并在 P0 插入
缺陷修复（`departSpeed="0"`）与 warmup 实测标定（600 s）基础上，以**基本图方案**
（U55：自由流→临界→拥堵区上探受限——密度轴上限 55 = 37.5% kj，未覆盖近阻塞
   段）重设计主网格。

v0.4.1 作为内部里程碑完成测量链路升级（HV/CAV 子群、FCD 物理车头时距、独立
assignment/sumo 双 seed、SSM 敏感性工具等），但未通过旧资源门禁而未发布；其工程
成果全部并入本版。

---

## 2. 实验设计

### 2.1 场景链

| 场景 | 几何 | 车道 | 环长 | 设计对照 |
|---|---|---|---|---|
| s0 | 方形 90° 转角 | 1 | 2.0 km | 转角限速基线（转角内部车道 3.9 m/s） |
| s1 | 32 边形平滑 | 1 | 2.0 km | s0→s1 几何平滑 |
| s2 | 32 边形平滑 | 2 | 2.0 km | s1→s2 车道数/横向自由度 |
| s3 | 32 边形 + e15/e16 单车道 125 m 瓶颈 | 2 | 2.0 km | s2→s3 强制合流瓶颈 |

### 2.2 网格（U55）

- **密度轴**：统一 5–55 veh/km/道（s0/s1 单车道 vehN 10–110 步 10；s2/s3 双车道
  vehN 20–220 步 20）；上限 55 由 s2 SSM 内存边界实测约束（v220=22.67 GiB 探针）。
- **渗透率**：cav_count 0.1 步长 11 档（全整数；端点 assignment 失活 sentinel）。
- **seed**：3 × 3 双 seed（assignment_seed × sumo_seed；端点 n=3、内部 n=9）。
- **仿真窗**：warmup=600 s（9 档标定 ≤120 s 稳定）、simulation_end=1800 s、
  观测窗 [600, 1800)。
- **插入**：`departSpeed="0"`（静止插入，warmup 吸收冷启动；修复 P0 高密度插入损失）。
- **SSM 全开**（合并设计）：TTC=3.0 s、DRAC=3.0 m/s²、range=50 m、greedy 镜像去重
  80%、withInternal=true。
- **总量**：4 场景 × 11 档 × 171 runs/档 = **7,524 runs**。

### 2.3 指标口径

- **流量/密度**：detector 实测流量为权威；FD 横轴用名义密度（vehN/车道数/2 km）——
  **名义密度 × 实测点流量**双口径（见 §8 局限 1）。
- **安全**：全路网 TTC 事件 / 全路网 veh-km（withInternal=true 空间配对）；
  DRAC、紧急制动、换道间隙为支持指标。
- **排放**：主强度 non-internal CO₂/veh-km（与 v0.4.0 定义级可比），全路网强度为
  次要口径（`whole_network_*` 列）。
- **效率**：相对固定参考圈时的有符号差（vehroute 圈时重建）；0-vs-NaN 契约
  （0=已解析且无事件；NaN=不适用）。

---

## 3. 管线质量与可复现性

| 项 | 值 |
|---|---|
| 仿真 | 7,524/7,524 SUCCESS；3 workers / 21.86 h（SUMO 累计 65.53 h，并行效率 3.00）；0 失败（错峰排序） |
| 解析 | 0 INVALID（插入完整性守卫：vehroute 实际车辆数 < vehN → INVALID_DATA，全网格通过） |
| writer | 0 排除 |
| 聚合 | 924 组（4 × 11 × 21；interior n=9 / endpoint n=3） |
| 测试 | 447 passed（门禁基线）；ruff / mypy / compileall / format 全通过 |
| 硬件 | 宿主机 32 GB；WSL2 memory=24GB / processors=16 / swap=8GB；SUMO 1.27.1 |
| 资源 | 最坏档（s2 v220 全 CAV）峰值 RSS 13.64 GiB；raw 76 GB（≈10.1 GB/千 runs） |
| 数据自洽 | 检测器流量 = 圈时反推流量（偏差 <0.5%）；aggregate 重算 0 diff；HV+CAV 可加性通过 |

正式输入字节锚定：`net/*/net.json` 与正式运行一致；`artifacts/free_flow/` 自由流
参考为解析输入依赖（版本化 SHA 门禁）。

---

## 4. 结果

### 4.1 流量与基本图（FD）

每车道网格峰值（veh/h/道）：

| 场景 | IDM 峰值 | @vehN/k | CACC 峰值 | @vehN/k |
|---|---|---|---|---|
| s0 | 1,794 | 80 / k40 | 1,857 | 80 / k40 |
| s1 | 3,918 | 100 / k50 | 4,689 | 80 / k40 |
| s2 | 3,916（双车道合计 7,833） | 200 / k50 | 4,694（合计 9,387） | 160 / k40 |
| s3 | 1,952（合计 3,903） | 80 / k20 | 1,292（合计 2,583） | 60 / k15 |

![FD 主图](../graph/v0.4.2/chart_fundamental_diagram.png)

- **峰位随渗透率移动**（s1/s2）：HV-only k≈20 → CACC p=1.0 k≈40，方向与理论
  kc（17.4 / 39.2）一致；CACC 峰流量更高且峰位更靠近理论 kc。**IDM 全 CAV
  高密度支在轴内单调上升至 k50 后平台（无下降支）——k≈50 为网格观测最大而非
  实测通行能力峰位（轴上限 55 = 37.5% kj，近阻塞段未覆盖）**。
- **s0 转角基线**：HV-only ~940 veh/h/道平顶（k≥20）——转角限速而非 τ 限制；
  全 CAV 峰值 1,794（IDM）/ 1,857（CACC）@ k40，均低于 τ 上限 2,400。

![FD s3 瓶颈](../graph/v0.4.2/chart_fundamental_diagram_s3.png)

- **s3 瓶颈语义**：基本图为瓶颈排队–吞吐关系（非主线基本图）。s3 为闭环无出入
  流，各横断面流量守恒——**瓶颈单车道吞吐 = 环总量**。HV 吞吐 **~1,000–1,150
  veh/h 量级**（实测 976–1,111；per-lane ~520）；**IDM 全 CAV ~3,200–3,900**
  （峰值 3,903 @k20，k30–55 3,168–3,285，per-lane ~1,950），**高于 τ 上限的
  2,400**；CACC 全 CAV **~1,500–2,600**（峰值 2,583 @k15，k30–55 仅
  ~1,450–1,520，per-lane ~1,290）——**2→1 合流冲突主导**瓶颈行为。

![容量](../graph/v0.4.2/chart_capacity.png)

### 4.2 安全

- TTC 检出 run 数：s0 1,875/1,881（≈100%）、s1 161/1,881（9%）、s2 333/1,881
  （18%）、s3 1,807/1,881（96%）；s1/s2 检出集中于 k≥35。
- 高密度下 CACC 事件率高于 IDM（s2 CACC 最高 ~2,475 vs IDM ~2 事件/1,000 veh-km）。
- 紧急制动集中于 s3（14,989 次，max 44/run）。
- 说明：事件率为空间配对（全路网事件 / 全路网 veh-km）；镜像去重为分析启发式
  （80% 重叠一对一），绝对计数不作精确物理冲突总量解读。

### 4.3 排放

- CO₂ 强度（non-internal）：s0 337–462、s1 144–330、s2 146–305、s3 176–661
  g/veh-km。
- s2/s3 高密度下 CACC 高于 IDM（高密度瓶颈反转场景的排放代价）。

![CO2 vs 流量](../graph/v0.4.2/chart_co2_flow.png)

### 4.4 效率

- k=30 运行点（密度对齐档）参考圈时差：s0 全 CAV ~22–25 s、s1/s2 ~0–8 s；
  s3 全 CAV IDM 72 s vs CACC 203 s。
- **s3 k≥40 效率数字受圈计数选择偏差影响**（覆盖率 k=40 93% / k=50 68% /
  k=55 75%），定量结论只给到 k≤35，k≥40 仅方向性佐证（见 §8 局限 6）。

![时损](../graph/v0.4.2/chart_delay.png)

---

## 5. 综合分析

- **基本图形态与峰位移动**：HV、CACC 及混合渗透率（p=0.5）呈完整右偏山峰状
  （实测 p=0.5 峰 k30 2,447 → k55 1,991）；**IDM 全 CAV 高密度支受轴上限
  （55 = 37.5% kj）截断、轴内无下降支**。渗透率升高推动峰位向理论 kc 移动、
  峰流量上升——CACC 在小间距（τ 更小）下扩展了自由流–临界区间。
- **s0 转角基线**：转角限速把通行能力钉在 τ 上限 2,400 之下——HV-only 平顶
  ~940 veh/h/道（k≥20）、全 CAV 峰值 1,794/1,857 @ k40，是 s0→s1 几何平滑
  对照轴的设计内自变量，非缺陷；s0 的排放/TTC/时损被转角反复
  加减速放大。
- **s3 瓶颈反转**：高密度强制合流下 CACC 吞吐劣化（1,620→756 veh/h/道），同时
  delay（72→442 s）与排放（339→633 g/veh-km）恶化——"高吞吐即高效"在瓶颈场景
  不成立。
- **无全局最优**：四维评估下无单一模型全局占优；CACC 优势场景依赖（平滑无约束
  环境）、劣势集中于高密度瓶颈。

---

## 6. 结论

1. 7,524-run U55 主网格全链路完成（0 失败、0 INVALID、0 排除、924 组），数据自洽
   （检测器流量=圈时反推流量、HV+CAV 可加性、聚合重算 0 diff）。
2. FD 峰位随 cav 渗透率移动（HV k=20 / CACC k=40；IDM 全 CAV 高密度支受轴上限
   截断，k≈50 为网格观测最大），基本图方案达成设计意图（覆盖自由流→临界→拥堵
   区上探受限段）。
3. s3 高密度合流瓶颈反转成立且由流量口径稳健支撑；效率佐证按密度档分层使用。
4. 项目当前无 P0/P1 级代码逻辑缺陷（管线审查七轮收敛：前四轮代码层收敛、第五至
   七轮发布文档/图产物层收敛；2 项 P2 与后续文档级 P1 均已修复或文档化闭环）。

---

## 7. 展望

- v0.5.0：真实轨迹驱动的跟驰模型标定与仿真验证；
- v0.6.0：TraCI 动态交通控制；
- v0.7.0：CACC 通信降级（丢包、时延）。

---

## 8. 局限与报告边界

1. **FD 名义密度 × 实测点流量**：闭环有限环长 + s0/s3 非均匀环上不满足 q=k·v
   （s0 k=20：q=946 vs k·v=1,980）；报告 FD 图为名义密度口径。
2. **闭环有限环长效应**：低密度自由流档可能出现自发拥堵（phantom jam），自由流
   分支实测流量系统性低估（U55 实测：s1 k=10 流量 955 较理论 1,170 低 18%、峰值
   1,809 @ k20 为理论 2,400 的 75%）——低估是闭环普遍现象，非 s0 专属。
3. **s0 转角限速（设计内特征）**：自由流速度钉在 ~17.9 m/s，通行能力受转角吞吐
   限制；s0 的排放/TTC/时损被转角加减速放大，按场景独立声明基线。
4. **冷启动等价性**：`departSpeed="0"` 全车同时注入 vs 现实渐进注入的稳态等价性
   未做对照验证（可选 1–2 档）。
5. **s3 瓶颈语义**：s3 基本图为瓶颈排队–吞吐关系，不与 s0/s1/s2 主线基本图直接
   比较。
6. **s3 圈计数选择偏差（k≥40）**：窗内完整圈覆盖率 k=40 93% / k=50 68% /
   k=55 75%（s2 对照 100%）——mean/p95_lap_delay_s 系统偏低；s3 效率定量只给到
   k≤35，"瓶颈反转"主结论依赖流量口径。
7. **THW 为条件样本**：无 leader 样本（U55 端点 3 seeds 实测 s0 v10 占比
   3.1%/9.1%/9.2%、均值 ~7%，恰为最大间距样本）被排除出 THW——mean_thw_s 系统低估。
8. **SUMO 积分方式**：HV actionStepLength=1.0 触发自动 step-method.ballistic，
   全局积分方式被静默改变；参考基准同条件测得。
9. **detector 速度口径**：mean_speed 为算术平均（非谐波平均）且只取非零流量窗口；
   `detector_speed_window_count` 实为"非零流量窗口数"。
10. **安全事件计数**：镜像去重为分析启发式；绝对事件计数不作精确物理冲突总量。
11. **跨版本数值不可互换**：与 v0.4.0.post3 定义级可比（non-internal CO₂
    estimand 一致），但网格/seed/仿真窗/withInternal 不同，不作数值互换或变化率
    推断。

---

## 9. 参考文献

1. Treiber, M., Hennecke, A., & Helbing, D. (2000). Congested traffic states in
   empirical observations and microscopic simulations. *Physical Review E*, 62(2), 1805.
2. Kesting, A., Treiber, M., & Helbing, D. (2010). Enhanced intelligent driver
   model to access the impact of driving strategies on traffic capacity.
   *Philosophical Transactions of the Royal Society A*, 368(1928), 4585–4605.
3. Milanés, V., Shladover, S. E., Spring, J., Nowakowski, C., Kawazoe, H., &
   Nakamura, M. (2014). Cooperative adaptive cruise control in real traffic
   situations. *IEEE Transactions on Intelligent Transportation Systems*, 15(1), 296–305.
4. Behrisch, M., Bieker, L., Erdmann, J., & Krajzewicz, D. (2011). SUMO –
   Simulation of Urban MObility: An overview. *SIMUL 2011*, 55–60.
5. Krajzewicz, D., Erdmann, J., Behrisch, M., & Bieker, L. (2012). Recent
   development and applications of SUMO – Simulation of Urban MObility.
   *International Journal on Advances in Systems and Measurements*, 5(3&4), 128–138.
6. Gettman, D., & Head, L. (2003). Surrogate safety measures from traffic
   simulation models. *Transportation Research Record*, 1840(1), 104–115.
7. van der Hoorn, N., & Hoogendoorn, S. P. (2010). Fundamental diagram
   estimation. In *Traffic and Granular Flow*.
8. Uriel62-chang (2026). CAV Multi-level Penetration Simulation. GitHub
   repository, v0.4.2. https://github.com/Uriel62-chang/CAV_Multi-level_Penetration_Simulation
