import copy
from pathlib import Path

from omcfg import model, validate

CONFIGS = Path(__file__).resolve().parent.parent / "configs"


def _load(name: str) -> dict:
    return model.load_config(CONFIGS / f"{name}.omcfg")


def test_all_templates_pass():
    for name in ("KC536", "CH04"):
        report = validate.validate_config(_load(name))
        assert report.ok, [issue.render() for issue in report.errors]


def test_duplicate_pin_is_error():
    config = _load("KC536")
    config["pins"]["LED_R_PIN"] = "P34"
    report = validate.validate_config(config)
    assert not report.ok
    assert any("重复分配" in issue.message for issue in report.errors)


def test_led_alias_pair_is_allowed():
    config = _load("CH04")
    config["pins"]["LED_R_PIN"] = config["pins"]["LED_MODE_R_PIN"]
    report = validate.validate_config(config)
    assert report.ok


def test_unknown_role_is_error():
    config = _load("KC536")
    config["pins"]["NOT_A_ROLE"] = "P22"
    report = validate.validate_config(config)
    assert any("未知" in issue.message for issue in report.errors)


def test_derived_fields_are_rejected():
    config = _load("KC536")
    config["features"] = {"BOARD_LOGO_RGB": True}
    config["board"]["BOARD_HAS_KEY_C0"] = True
    report = validate.validate_config(config)
    assert not report.ok


def test_wheel_mismatch_is_error():
    config = _load("KC536")
    config["board"]["wheel"] = "ENCODER_PINMUX_SEL_IO_24_25"
    report = validate.validate_config(config)
    assert any("应为" in issue.message for issue in report.errors)


def test_ledc_control_must_be_selector_pin():
    config = _load("CH04")
    config["pins"]["LEDC_PIN"] = "P07"
    report = validate.validate_config(config)
    assert any("LEDC_SEL" in issue.message for issue in report.errors)
    # 对照：LEDC_CTRL_PIN 是 MOS 控制脚，任意普通 GPIO 合法，不应报 LEDC_SEL
    config2 = _load("CH04")
    config2["pins"]["LEDC_CTRL_PIN"] = "P07"
    report2 = validate.validate_config(config2)
    assert not any("LEDC_SEL" in issue.message for issue in report2.errors)


def test_ledc_ctrl_pin_is_optional():
    """LEDC_CTRL_PIN 可选：logo=ledc 时只强制 LEDC_PIN。"""
    config = _load("CH04")
    del config["pins"]["LEDC_CTRL_PIN"]
    report = validate.validate_config(config)
    assert report.ok, [issue.render() for issue in report.errors]


def test_usb_fixed_pins():
    config = _load("KC536")
    config["pins"]["USB_DN_PIN"] = "P04"
    report = validate.validate_config(config)
    assert any("USB 固定脚" in issue.message for issue in report.errors)


def test_missing_required_mode_pin_is_error():
    config = _load("CH04")
    del config["pins"]["MODE_BLE_PIN"]
    report = validate.validate_config(config)
    assert any("MODE_BLE_PIN" in issue.message for issue in report.errors)


def test_illegal_encoder_pair_is_error():
    config = _load("CH04")
    config["pins"]["WHEEL_B_PIN"] = "P06"
    report = validate.validate_config(config)
    assert any("ENCODER 四对" in issue.message for issue in report.errors)


def test_reserved_pin_is_error():
    config = _load("CH04")
    config["pins"]["KEY_R0_PIN"] = "P14"
    report = validate.validate_config(config)
    assert any("片内 Flash 保留脚" in issue.message for issue in report.errors)


def test_non_usb_role_cannot_use_usb_pin():
    config = _load("CH04")
    config["pins"]["KEY_R0_PIN"] = "P02"
    report = validate.validate_config(config)
    assert any("USB 差分脚" in issue.message for issue in report.errors)


def test_dpi_metadata_consistency():
    config = _load("CH04")
    config["board"]["sensor"]["dpi_levels"] = [1200, 1300]
    report = validate.validate_config(config)
    assert any("200 的整数倍" in issue.message for issue in report.errors)
    config["board"]["sensor"]["dpi_levels"] = [1200, 1600]
    config["board"]["sensor"]["dpi_default"] = 5
    report = validate.validate_config(config)
    assert any("档位下标" in issue.message for issue in report.errors)


def test_ble_names_validation():
    config = _load("KC536")
    for bad in ([], ["x" * 29], ['bad"name']):
        config["project"]["ble_names"] = bad
        report = validate.validate_config(config)
        assert not report.ok, bad
        assert any("ble_names" in issue.path for issue in report.errors)


def test_report_is_detached_from_input():
    config = _load("KC536")
    snapshot = copy.deepcopy(config)
    validate.validate_config(config)
    assert config == snapshot
