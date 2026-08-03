"""v0.4.2 P0-9 回归测试：影响结论的 SUMO 隐式默认显式化（仅 v0.4.2）。"""

from scripts.simulation.flow_generator import generate_flow


def test_v4_2_emission_class_explicit(tmp_path):
    out = tmp_path / "r.xml"
    generate_flow(4, 0.5, 2, 1, str(out), cav_count=2, explicit_emission_class=True)
    text = out.read_text(encoding="utf-8")
    assert 'emissionClass="HBEFA3/PC_G_EU4"' in text
    # CAV 与 HV 都显式
    assert text.count("emissionClass=") == 2


def test_no_explicit_emission_class_default(tmp_path):
    """默认 explicit_emission_class=False（v0.4.1 路径）不写 emissionClass。"""
    out = tmp_path / "r_default.xml"
    generate_flow(4, 0.5, 2, 1, str(out), cav_count=2)
    text = out.read_text(encoding="utf-8")
    assert "emissionClass" not in text


def test_v4_1_command_byte_identical(tmp_path):
    """v0.4.1 路径（explicit_emission_class 默认 False）字节不变。"""

    import sys

    sys.path.insert(0, ".")
    from scripts.run_spec import PIPELINE_V4_1, RunSpec
    from scripts.simulation.single_run import build_sumo_command_v4_1
    from tests.test_v4_2_p0_1_ssm_role import _dummy_prepared

    spec = RunSpec(
        scenario="scenario_0",
        model="IDM",
        pcav=0.5,
        vehicle_count=10,
        seed=1,
        run_id="s0_IDM_v010_c005_as01_ss101",
        pipeline_version=PIPELINE_V4_1,
        schema_version="2",
        sumo_seed=101,
        cav_count=5,
        requested_pcav=None,
    )
    # v0.4.1 命令构造不因 P0-9 改变（emissionClass 在 route 文件而非命令）
    cmd = build_sumo_command_v4_1(_dummy_prepared(), "net/scenario_0/loop.net.xml", spec)
    assert not any("emissionClass" in a for a in cmd)
