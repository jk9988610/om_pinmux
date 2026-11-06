from pathlib import Path

from omcfg import model

CONFIGS = Path(__file__).resolve().parent.parent / "configs"


def test_all_templates_load():
    for name in ("KC536", "BD319", "CH04"):
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


def test_bd319_has_no_pair_and_dual_mode():
    config = model.load_config(CONFIGS / "BD319.omcfg")
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
