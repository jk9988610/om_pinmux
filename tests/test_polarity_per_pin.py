"""逐脚极性：每只灯/按键各自分配，不统一、不按统计、不按数量。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from omcfg import model
from omcfg.api import Api
from omcfg.generate import templates

UV4 = Path(os.environ.get("OMCFG_UV4", r"C:\Keil_v5\UV4\UV4.exe"))


def _cfg(**extra):
    config = {
        "schema": model.SCHEMA,
        "chip": model.CHIP_MODEL,
        "project": {"name": "T", "customer": "BYC", "id": {"low": "0x1", "high": "0x1", "version": "1"}},
        "board": {"mode_pins": "single", "logo": "rgb", "led_polarity": "active_low"},
        "pins": {
            "LED_MODE_R_PIN": "P00",
            "LED_MODE_G_PIN": "P01",
            "LED_MODE_B_PIN": "P04",
            "LED_LOW_PIN": "P05",
            "LED_MODE_24G_PIN": "P06",
            "KEY_R0_PIN": "P34",
            "KEY_R1_PIN": "P07",
        },
    }
    config.update(extra)
    return config


def test_role_polarity_defaults_follow_role_type():
    cfg = _cfg()
    # 灯缺省沿用旧全局值；按键缺省上拉低有效。
    assert model.role_polarity(cfg, "LED_MODE_R_PIN") == "active_low"
    assert model.role_polarity(cfg, "KEY_R0_PIN") == "active_low"
    cfg["board"]["led_polarity"] = "active_high"
    assert model.role_polarity(cfg, "LED_MODE_R_PIN") == "active_high"
    assert model.role_polarity(cfg, "KEY_R0_PIN") == "active_low"


def test_role_polarity_explicit_beats_global():
    cfg = _cfg(polarity={"LED_MODE_G_PIN": "active_high", "KEY_R1_PIN": "active_high"})
    # 显式逐脚值覆盖全局，且不影响其它脚。
    assert model.role_polarity(cfg, "LED_MODE_G_PIN") == "active_high"
    assert model.role_polarity(cfg, "LED_MODE_R_PIN") == "active_low"
    assert model.role_polarity(cfg, "KEY_R1_PIN") == "active_high"
    assert model.role_polarity(cfg, "KEY_R0_PIN") == "active_low"


def test_polarity_roles_named_with_rgb():
    led_names = " ".join(model.POLARITY_LED_NAMES.values())
    for color in ("R", "G", "B"):
        assert f"模式灯 {color}" in led_names or f"业务灯 {color}" in led_names
    assert all(m.endswith("_PIN") for m in model.POLARITY_LED_NAMES)


def test_active_polarity_roles_follows_assigned_pins():
    cfg = _cfg()
    active = model.active_polarity_roles(cfg)
    names = [r[0] for r in active]
    assert "LED_MODE_R_PIN" in names and "KEY_R0_PIN" in names
    assert "LED_R_PIN" not in names  # 没配脚就不列，极性面板“按数量”生成
    # 移除一只脚后不再列出
    del cfg["pins"]["KEY_R0_PIN"]
    assert "KEY_R0_PIN" not in [r[0] for r in model.active_polarity_roles(cfg)]


def test_led_on_macro_uses_each_own_polarity():
    cfg = _cfg(polarity={"LED_MODE_G_PIN": "active_high"})
    pins = model.resolved_pins(cfg)
    header = templates.render_pins(cfg, pins)
    # R 低有效→gpio_clear 点亮；G 高有效→gpio_set 点亮；各用各的。
    assert "#define led_r_on()            (gpio_clear(LED_MODE_R_PIN))" in header
    assert "#define led_g_on()            (gpio_set(LED_MODE_G_PIN))" in header
    assert "#define led_b_on()            (gpio_clear(LED_MODE_B_PIN))" in header
    assert "#define led_bt0_on()            (gpio_clear(LED_MODE_BT0_PIN))" in header


def test_alias_leds_follow_main_mode_led():
    cfg = _cfg(polarity={"LED_MODE_R_PIN": "active_high"})
    pins = model.resolved_pins(cfg)
    header = templates.render_pins(cfg, pins)
    # 24G 复用 R 物理脚，极性跟随 R：也变高有效。
    assert "#define led_24g_on()            (gpio_set(LED_MODE_24G_PIN))" in header
    assert "#define led_r_on()            (gpio_set(LED_MODE_R_PIN))" in header


def test_mode_24g_led_alias_and_dynamic_polarity():
    """2.4G 灯复用 R/G/B 由 board.mode_24g_led 决定（KC536=R，S205=G）。"""
    # 默认 R，保 KC536 字节一致。
    cfg_r = _cfg()
    assert model.mode_24g_led(cfg_r) == "R"
    assert "#define LED_MODE_24G_PIN        LED_MODE_R_PIN" in templates.render_pins(
        cfg_r, model.resolved_pins(cfg_r)
    )
    # S205=G(P05 绿灯)：宏别名跟随 G，极性跟随 G 而非写死 R。
    cfg_g = _cfg()
    cfg_g["board"]["mode_24g_led"] = "G"
    header = templates.render_pins(cfg_g, model.resolved_pins(cfg_g))
    assert "#define LED_MODE_24G_PIN        LED_MODE_G_PIN" in header
    assert model.mode_24g_main_role(cfg_g) == "LED_MODE_G_PIN"
    assert model.role_polarity(cfg_g, "LED_MODE_24G_PIN") == model.role_polarity(cfg_g, "LED_MODE_G_PIN")
    # 显式给 G 高有效时，24G 别名也高有效（不跟 R）。
    cfg_g["polarity"] = {"LED_MODE_G_PIN": "active_high", "LED_MODE_R_PIN": "active_low"}
    assert model.role_polarity(cfg_g, "LED_MODE_24G_PIN") == "active_high"


def test_mode_led_all_macro_when_mixed_polarity():
    cfg = _cfg(polarity={"LED_MODE_G_PIN": "active_high"})
    pins = model.resolved_pins(cfg)
    header = templates.render_pins(cfg, pins)
    # 三脚极性不同时，批量宏按每脚分别置位/清零，不能再用单个 DATAOUTSET/CLR。
    all_on = [ln for ln in header.splitlines() if "mode_led_all_on()" in ln][0]
    assert "gpio_set(LED_MODE_G_PIN)" in all_on
    assert "gpio_clear(LED_MODE_R_PIN)" in all_on


def test_count_change_does_not_touch_polarity():
    cfg = _cfg(polarity={"LED_MODE_R_PIN": "active_high"},
               board={"mode_pins": "single", "logo": "rgb", "led_polarity": "active_low",
                      "ledc_rgb_number": 12})
    assert model.role_polarity(cfg, "LED_MODE_R_PIN") == "active_high"
    assert model.ledc_rgb_number(cfg) == 12
    # 改数量只改数量宏，不产生/修改逐脚极性（选料契约里也没有极性）。
    header = templates.render_pins(cfg, model.resolved_pins(cfg))
    assert "gpio_set(LED_MODE_R_PIN)" in header


def test_set_polarity_value_text_roundtrip():
    cfg_text = "# header\nboard:\n  mode_pins: single\npins:\n  LED_MODE_R_PIN: P00\n"
    out = model.set_polarity_value_text(cfg_text, "LED_MODE_R_PIN", "active_high")
    assert "polarity:" in out
    assert "LED_MODE_R_PIN: active_high" in out
    assert model.load_config_text(out)["polarity"]["LED_MODE_R_PIN"] == "active_high"
    # 清空恢复默认
    cleared = model.set_polarity_value_text(out, "LED_MODE_R_PIN", "")
    assert model.load_config_text(cleared).get("polarity", {}).get("LED_MODE_R_PIN") is None


def test_api_roundtrip(tmp_path):
    sdk = tmp_path / "sdk"
    api = Api()
    assert api.blank_new("T", str(sdk), id_low=0x1)["ok"]
    assert api.blank_save(str(sdk), {"LED_MODE_R_PIN": "P00", "KEY_R0_PIN": "P34"})["ok"]
    # 未配脚的角色不能设极性
    bad = api.blank_set_polarity(str(sdk), {"LED_MODE_G_PIN": "active_high"})
    assert not bad["ok"] and "还没配脚" in bad["error"]
    # 已配脚可逐脚设置
    ok = api.blank_set_polarity(str(sdk), {"LED_MODE_R_PIN": "active_high", "KEY_R0_PIN": "active_low"})
    assert ok["ok"]
    assert ok["effective"]["LED_MODE_R_PIN"] == "active_high"
    st = api.blank_status(str(sdk))
    assert st["polarity_map"]["LED_MODE_R_PIN"] == "active_high"
    assert {r["role"]: r["effective"] for r in st["polarity_roles"]}["LED_MODE_R_PIN"] == "active_high"
    # 再改另一只脚不影响第一只
    api.blank_set_polarity(str(sdk), {"KEY_R0_PIN": "active_high"})
    st2 = api.blank_status(str(sdk))
    assert st2["polarity_map"]["LED_MODE_R_PIN"] == "active_high"
    assert st2["polarity_map"]["KEY_R0_PIN"] == "active_high"


@pytest.mark.skipif(not UV4.is_file(), reason="未找到 Keil UV4，跳过编译验收")
def test_keil_build_with_mixed_per_pin_polarity(tmp_path):
    """混合极性（R 高 / G 低 / B 高 + 按键高有效）也能 Keil 0/0。"""
    api = Api()
    sdk = str((tmp_path / "MixedPol").resolve())
    assert api.blank_new("MixedPol", sdk, id_low=0x0601)["ok"]
    assert api.blank_fill_recommended(sdk)["ok"]
    # 逐脚分配：R/G/B 各不相同，别名跟随主灯，按键单独高有效。
    r = api.blank_set_polarity(sdk, {
        "LED_MODE_R_PIN": "active_high",
        "LED_MODE_G_PIN": "active_low",
        "LED_MODE_B_PIN": "active_high",
        "KEY_R0_PIN": "active_high",
    })
    assert r["ok"], r
    assert api.blank_apply(sdk)["ok"]

    header = (Path(sdk) / "projects/mouse_demo/periph/user_config.h").read_text(
        encoding="utf-8", errors="replace"
    )
    assert "#define led_r_on()            (gpio_set(LED_MODE_R_PIN))" in header
    assert "#define led_g_on()            (gpio_clear(LED_MODE_G_PIN))" in header
    assert "#define led_b_on()            (gpio_set(LED_MODE_B_PIN))" in header

    proj = Path(sdk) / "projects/mouse_demo/keil5/SE71M.uvprojx"
    assert proj.is_file()
    log = tmp_path / "mixed_pol_build.log"
    subprocess.run(
        [str(UV4), "-r", str(proj), "-o", str(log)],
        capture_output=True, text=True, timeout=300, check=False,
    )
    content = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    assert "0 Error(s), 0 Warning(s)" in content, content[-1500:]
