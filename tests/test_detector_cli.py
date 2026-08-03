import sys

from scripts.parsing.detector import main, parse_detector


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
