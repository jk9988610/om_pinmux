"""smoke 场景配置与验证函数（纯函数测试，不跑 end-to-end）。"""

from __future__ import annotations

from omcfg import smoke


def test_scenarios_cover_three_logo_modes():
    names = [s.name for s in smoke.SCENARIOS]
    assert names == ["TEST_CLI", "TEST_NOCTRL", "TEST_NONE"]
    ids = [s.id_low for s in smoke.SCENARIOS]
    assert len(set(ids)) == 3


def test_drop_ctrl_removes_only_ctrl_pin():
    src = "  LEDC_PIN: P34\n  LEDC_CTRL_PIN: P05\n  USB_5V: P25\n"
    out = smoke._drop_ctrl(src)
    assert "LEDC_CTRL_PIN" not in out
    assert "LEDC_PIN: P34" in out
    assert "USB_5V: P25" in out


def test_logo_none_clears_logo_section():
    src = (
        "  logo: ledc\n"
        "  ledc_rgb_number: 6\n"
        "  LEDC_PIN: P34\n"
        "  LEDC_CTRL_PIN: P05\n"
        "  USB_5V: P25\n"
    )
    out = smoke._logo_none(src)
    assert "logo: none" in out
    assert "ledc_rgb_number" not in out
    assert "LEDC_PIN" not in out
    assert "LEDC_CTRL_PIN" not in out
    assert "USB_5V: P25" in out


def test_check_markers_passes_for_matching_scenario(tmp_path):
    proj = tmp_path / "sdk"
    periph = proj / "projects/mouse_demo/periph"
    periph.mkdir(parents=True)
    (periph / "user_config.h").write_text("#define LEDC_PIN (P34)\n", encoding="utf-8")
    (periph / "ledc.h").write_text("#if defined(LEDC_PIN)\n#endif\n", encoding="utf-8")
    sc = smoke.Scenario(
        name="X", id_low="0x0001", modify=None,
        expect_have=["#define LEDC_PIN", "#if defined(LEDC_PIN)"],
        expect_not_have=["#define LED_R_PIN"],
    )
    assert smoke._check_markers(proj, sc) == []


def test_check_markers_reports_missing_and_unexpected(tmp_path):
    proj = tmp_path / "sdk"
    periph = proj / "projects/mouse_demo/periph"
    periph.mkdir(parents=True)
    (periph / "user_config.h").write_text("#define LED_R_PIN (P04)\n", encoding="utf-8")
    sc = smoke.Scenario(
        name="X", id_low="0x0001", modify=None,
        expect_have=["#define LEDC_PIN"],
        expect_not_have=["#define LED_R_PIN"],
    )
    problems = smoke._check_markers(proj, sc)
    assert any("缺少" in p for p in problems)
    assert any("不应有" in p for p in problems)
