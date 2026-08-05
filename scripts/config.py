"""仿真参数默认值，统一管理。所有可调参数以此文件为单一数据源。"""

# ── 仿真时间 ──
DEFAULT_SIM_END = 1800  # 仿真结束时间 (s)；U55 网格观测窗 [600,1800)（单跑默认与网格一致）
DEFAULT_WARMUP = 600  # 预热期 (s)
DEFAULT_STEP_LENGTH = 0.1  # SUMO 仿真步长 (s)，须与 CAV actionStepLength 一致

# ── 检测器 ──
DEFAULT_DETECTOR_FREQ = 120  # e1 检测器统计频率 (s)；2×单圈耗时避免共振（对 32 边形场景圈时 ~61 s 成立；s0 方形转角圈时 ~112 s 例外，s0 的转角限速基线单独声明）

# ── 跟驰模型 ──
CAV_MODELS = ("IDM", "ACC", "CACC")

CAV_TAU = {  # CAV 期望车头时距 (s)
    "IDM": 0.6,
    "ACC": 1.1,
    "CACC": 0.6,
}

# ── 车辆物理参数 ──
CAV_ACCEL = 3.0
CAV_DECEL = 4.5
CAV_LENGTH = 5.0
CAV_MIN_GAP = 0.5
CAV_MAX_SPEED = 33.33
CAV_SPEED_DEV = 0.0
CAV_ACTION_STEP_LENGTH = 0.1

HV_ACCEL = 2.0
HV_DECEL = 4.5
HV_LENGTH = 5.0
HV_MIN_GAP = 2.5
HV_MAX_SPEED = 33.33
HV_SPEED_DEV = 0.1
HV_TAU = 1.5
HV_SIGMA = 0.5
HV_ACTION_STEP_LENGTH = 1.0

# ── LC2013 换道模型 ──
LC2013_STRATEGIC = 1.0
LC2013_SPEED_GAIN = 1.0
LC2013_KEEP_RIGHT = 0.8
LC2013_COOPERATIVE = 0.8
LC2013_SIGMA = 0.5

# ── 路网 ──
JUNCTION_MARGIN_M = 3.0  # 32边形路口占用 + {:.2f} 四舍五入余量 (m)

# ── 安全评价 ──
SSM_TTC_THRESHOLD_S = 3.0  # TTC 冲突阈值 (s)
SSM_DRAC_THRESHOLD_MPS2 = 3.0  # DRAC 冲突阈值 (m/s²)

# ── 环保评价 ──
# emissionClass 使用 SUMO 默认值 "HBEFA3/PC_G_EU4"（vType 未显式设置时），
# HV 与 CAV 使用同一排放等级，仅比较跟驰控制逻辑造成的排放差异。

# ── edgeData 配置 ──
DEFAULT_EDGEDATA_FREQ = 300  # edgeData 聚合周期 (s)；仅影响文件大小，不改变总量
