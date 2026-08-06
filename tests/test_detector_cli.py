import math
import sys

from scripts.parsing.detector import main, parse_detector, parse_detector_multi


def test_detector_cli_prints_all_five_metrics(tmp_path, monkeypatch, capsys):
    path = tmp_path / "detector.xml"
    path.write_text(
        '<detector><interval begin="600" end="660" flow="120" speed="10"/></detector>',
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["detector", "--xml", str(path)])

    main()

    assert capsys.readouterr().out.strip() == "120.000,120.000,10.000,nan,1"


def test_detector_empty_flow_window_does_not_become_zero_speed(tmp_path):
    path = tmp_path / "detector.xml"
    path.write_text(
        """<detector>
<interval begin="600" end="660" flow="0" speed="0"/>
<interval begin="720" end="780" flow="120" speed="10"/>
</detector>""",
        encoding="utf-8",
    )

    mean_flow, max_flow, mean_speed, variance, speed_windows = parse_detector(str(path))

    assert mean_flow == 60
    assert max_flow == 120
    assert mean_speed == 10
    assert str(variance) == "nan"
    assert speed_windows == 1


def test_detector_all_zero_flow_subgroup_speed_is_nan_not_zero(tmp_path):
    """审查 P2-1：空子群（全程零流量）mean_speed 报 NaN 而非 0.0。

    0=已解析且无事件、NaN=不适用；flow=0 有语义，speed=0.0 误导（暗示"车速为 0"
    而非"无数据"）。单文件与多文件分支同规则。
    """
    xml = """<detector>
<interval begin="600" end="660" flow="0" speed="0"/>
<interval begin="720" end="780" flow="0" speed="0"/>
</detector>"""

    # 单文件分支
    path = tmp_path / "detector_zero.xml"
    path.write_text(xml, encoding="utf-8")
    mean_flow, max_flow, mean_speed, variance, speed_windows = parse_detector(str(path))
    assert mean_flow == 0
    assert max_flow == 0
    assert math.isnan(mean_speed)
    assert math.isnan(variance)
    assert speed_windows == 0

    # 多文件分支（parse_detector_multi）：全部零流量同样 NaN
    path2 = tmp_path / "detector_zero2.xml"
    path2.write_text(xml, encoding="utf-8")
    mean_flow, max_flow, mean_speed, variance, speed_windows = parse_detector_multi(
        [str(path), str(path2)]
    )
    assert mean_flow == 0
    assert math.isnan(mean_speed)
    assert speed_windows == 0
