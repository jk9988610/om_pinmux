from pathlib import Path

from omcfg import model

CONFIGS = Path(__file__).resolve().parent.parent / "configs"


def test_all_templates_load():
    for name in ("KC536", "CH04"):
        config = model.load_config(CONFIGS / f"{name}.omcfg")
        assert config["schema"] == model.SCHEMA


def test_kc536_derived_values():
    config = model.load_config(CONFIGS / "KC536.omcfg")
    pins = model.pin_entries(config)
    features = model.features(config, pins)
    assert features["BOARD_MODE_SINGLE_PIN"] is True
    assert features["BOARD_LOGO_RGB"] is True
    assert features["BOARD_HAS_EXTRA_KEYS"] is True
    assert model.wheel_select(config) == "ENCODER_PINMUX_SEL_IO_20_21"
    assert model.lvd_index(config, pins) == "POF_LVD_PIN_P23"
    assert model.wake_keys(config, pins) == [
        "KEY_R0_PIN",
        "KEY_R1_PIN",
        "KEY_R2_PIN",
        "KEY_PAIR_PIN",
    ]


def test_ch04_derived_values():
    config = model.load_config(CONFIGS / "CH04.omcfg")
    pins = model.pin_entries(config)
    features = model.features(config, pins)
    assert features["BOARD_LOGO_LEDC"] is True
    assert features["BOARD_HAS_LED_LOW"] is True
    assert features["BOARD_HAS_KEY_C0"] is True
    assert features["BOARD_MODE_DUAL_PIN"] is True
    assert model.lvd_index(config, pins) == "POF_LVD_PIN_P33"
    assert model.uart_pin(config) == "KEY_R2_PIN"


def test_dual_mode_without_pair_only_wakes_matrix_keys():
    config = model.load_config(CONFIGS / "CH04.omcfg")
    del config["pins"]["KEY_PAIR_PIN"]
    pins = model.pin_entries(config)
    assert "KEY_PAIR_PIN" not in pins
    assert model.mode_pins(config, pins) == ["MODE_24G_PIN", "MODE_BLE_PIN"]
    assert model.wake_keys(config, pins) == ["KEY_R0_PIN", "KEY_R1_PIN", "KEY_R2_PIN"]


def test_gpio_defaults_fill_missing_fields():
    config = {"pins": {"KEY_R0_PIN": {"pin": "P34"}}}
    pins = model.resolved_pins(config)
    assert pins["KEY_R0_PIN"] == {
        "pin": "P34",
        "mode": "input_pullup",
        "pull": "pu_30k",
        "init": "high",
    }


def test_set_pin_text_preserves_layout():
    text = (CONFIGS / "KC536.omcfg").read_text(encoding="utf-8")
    after = model.set_pin_text(text, "KEY_R0_PIN", "P36")
    assert after.replace("KEY_R0_PIN: P36", "KEY_R0_PIN: P34") == text
    config = model.load_config_text(after)
    assert model.pin_entries(config)["KEY_R0_PIN"]["pin"] == "P36"

    nested = model.set_pin_text(text, "MODE_BLE_24G_PIN", "P22")
    assert nested.replace("pin: P22", "pin: P26", 1) == text

    inline = model.set_pin_text(text, "LED_MODE_R_PIN", "P22")
    assert inline.replace("pin: P22", "pin: P32", 1) == text


def test_set_pin_text_rejects_unknown_role():
    text = (CONFIGS / "KC536.omcfg").read_text(encoding="utf-8")
    try:
        model.set_pin_text(text, "NOT_A_PIN", "P34")
    except ValueError as exc:
        assert "没有引脚" in str(exc)
    else:
        raise AssertionError("应当拒绝未知角色")
