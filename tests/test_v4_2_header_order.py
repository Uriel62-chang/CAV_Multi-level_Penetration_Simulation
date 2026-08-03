"""P1-1（新审阅）回归：v0.4.2 正式 header 顺序冻结。

- fragment 恢复历史相对位置（ssm_mirrored_record_count 与 ttc_conflict_event_count 之间，
  与正式 v0.4.2 CSV 原 header 一致，方案 B 尾部追加的回归已消除）；
- 采集状态列（experiment_role / ssm_enabled / ssm_not_collected）紧随 IDENTIFIER；
- 完整 V4_2 run-level header 与冻结 fixture 逐项相等（tests/baselines/v0.4.2-schema-header.json），
  防止再次出现"字段存在但顺序漂移"的契约缺口；
- legacy schema=1 / V4_1 冻结集不受状态列影响。
"""

import hashlib
import json
from pathlib import Path

from scripts.schema import (
    RUN_LEVEL_COLUMNS,
    RUN_LEVEL_COLUMNS_V4_1,
    RUN_LEVEL_COLUMNS_V4_2,
    SAFETY_SSM_COLUMNS,
    SAFETY_SSM_COLUMNS_V4_1,
    STATUS_COLUMNS_V4_2,
    SUMMARY_REQUIRED_KEYS,
)

FIXTURE = json.loads(Path("tests/baselines/v0.4.2-schema-header.json").read_text(encoding="utf-8"))


def test_fragment_restored_between_mirrored_and_ttc():
    cols = RUN_LEVEL_COLUMNS_V4_2
    assert (
        cols.index("ssm_mirrored_record_count")
        < cols.index("ssm_fragment_merged_count")
        < cols.index("ttc_conflict_event_count")
    )
    # 与正式 v0.4.2 CSV 原相对顺序一致（fragment 紧跟 mirrored 之后）
    assert cols[cols.index("ssm_mirrored_record_count") + 1] == "ssm_fragment_merged_count"
    # legacy 集合保持不含 fragment
    assert "ssm_fragment_merged_count" not in SAFETY_SSM_COLUMNS
    assert "ssm_fragment_merged_count" not in RUN_LEVEL_COLUMNS
    assert "ssm_fragment_merged_count" not in SUMMARY_REQUIRED_KEYS


def test_status_columns_follow_identifiers():
    cols = RUN_LEVEL_COLUMNS_V4_2
    assert cols[:13] == [
        "run_id",
        "scenario",
        "model",
        "requested_pcav",
        "realized_pcav",
        "cav_count",
        "hv_count",
        "vehN",
        "assignment_seed",
        "sumo_seed",
        "experiment_role",
        "ssm_enabled",
        "ssm_not_collected",
    ]
    assert list(STATUS_COLUMNS_V4_2) == ["experiment_role", "ssm_enabled", "ssm_not_collected"]


def test_v4_2_header_matches_frozen_fixture():
    assert FIXTURE["run_level_columns_v4_2"] == RUN_LEVEL_COLUMNS_V4_2
    digest = hashlib.sha256(
        json.dumps(RUN_LEVEL_COLUMNS_V4_2, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert digest == "f2069d136fcfaada28c5809501aaf2c309340284bd662cc55a4fed98daffc4a0"


def test_status_columns_do_not_leak_to_legacy_sets():
    for col in STATUS_COLUMNS_V4_2:
        assert col not in RUN_LEVEL_COLUMNS
        assert col not in RUN_LEVEL_COLUMNS_V4_1
        assert col not in SAFETY_SSM_COLUMNS_V4_1
