"""logo 形态三分支：ledc / rgb / none 的 render_pins 行为。"""

from __future__ import annotations

from pathlib import Path

from omcfg import model
from omcfg.generate import templates

CONFIGS = Path(__file__).resolve().parent.parent / "configs"


def _config(name: str = "CH04.omcfg") -> dict:
    return model.load_config(CONFIGS / name)


def _drop(config: dict, *roles: str) -> None:
    for role in roles:
        config["pins"].pop(role, None)


def test_logo_ledc_emits_ledc_macros():
    config = _config()
    pins = model.resolved_pins(config)
    text = templates.render_pins(config, pins)
    assert "#define LEDC_PIN" in text
    assert "#define LEDC_CTRL_PIN" in text
    assert "#define LEDC_RGB_NUMBER" in text
    assert "#define LED_R_PIN" not in text


def test_logo_rgb_emits_no_ledc_macros():
    config = _config("KC536.omcfg")
    pins = model.resolved_pins(config)
    text = templates.render_pins(config, pins)
    assert "#define LEDC_PIN" not in text
    assert "#define LEDC_CTRL_PIN" not in text
    if "LED_R_PIN" in pins:
        assert "#define LED_R_PIN" in text
        assert "#define LED_G_PIN" in text
        assert "#define LED_B_PIN" in text


def test_logo_ledc_without_ctrl_pin_skips_ctrl_macro():
    """LEDC_CTRL_PIN 可选：有 LEDC_PIN 就生成 LEDC 宏，CTRL 缺失时跳过。"""
    config = _config()
    _drop(config, "LEDC_CTRL_PIN")
    pins = model.resolved_pins(config)
    text = templates.render_pins(config, pins)
    assert "#define LEDC_PIN" in text
    assert "#define LEDC_CTRL_PIN" not in text
    assert "#define LEDC_RGB_NUMBER" in text


def test_logo_none_emits_no_logo_macros():
    """logo=none 时 LOGO 段只剩注释，不生成 LEDC 与 RGB 宏。"""
    config = _config()
    config["board"]["logo"] = "none"
    config["board"].pop("ledc_rgb_number", None)
    _drop(config, "LEDC_PIN", "LEDC_CTRL_PIN",
          "LED_R_PIN", "LED_G_PIN", "LED_B_PIN")
    pins = model.resolved_pins(config)
    text = templates.render_pins(config, pins)
    assert "LOGO灯配置" in text
    for key in ("LEDC_PIN", "LEDC_CTRL_PIN", "LEDC_RGB_NUMBER",
                "LED_R_PIN", "LED_G_PIN", "LED_B_PIN"):
        assert f"#define {key}" not in text, f"logo=none 不应生成 {key}"
