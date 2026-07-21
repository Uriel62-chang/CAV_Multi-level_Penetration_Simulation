"""仿真参数默认值，统一管理。所有可调参数以此文件为单一数据源。"""

# ── 仿真时间 ──
DEFAULT_SIM_END = 3600        # 仿真结束时间 (s)
DEFAULT_WARMUP = 600          # 预热期 (s)
DEFAULT_STEP_LENGTH = 0.1     # SUMO 仿真步长 (s)，须与 CAV actionStepLength 一致

# ── 检测器 ──
DEFAULT_DETECTOR_FREQ = 120   # e1 检测器统计频率 (s)；2×单圈耗时避免共振

# ── 跟驰模型 ──
CAV_MODELS = ("IDM", "ACC", "CACC")

CAV_TAU = {                   # CAV 期望车头时距 (s)
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
JUNCTION_MARGIN_M = 3.0       # 32边形路口占用 + {:.2f} 四舍五入余量 (m)
