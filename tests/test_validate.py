import copy
from pathlib import Path

from omcfg import model, validate

CONFIGS = Path(__file__).resolve().parent.parent / "configs"


def _load(name: str) -> dict:
    return model.load_config(CONFIGS / f"{name}.omcfg")


def test_all_templates_pass():
    for name in ("KC536", "BD319", "CH04"):
        report = validate.validate_config(_load(name))
        assert report.ok, [issue.render() for issue in report.errors]


def test_duplicate_pin_is_error():
    config = _load("KC536")
    config["pins"]["LED_R_PIN"] = "P34"
    report = validate.validate_config(config)
    assert not report.ok
    assert any("重复分配" in issue.message for issue in report.errors)


def test_led_alias_pair_is_allowed():
    config = _load("BD319")
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
    config["pins"]["LEDC_CTRL_PIN"] = "P07"
    report = validate.validate_config(config)
    assert any("LEDC_SEL" in issue.message for issue in report.errors)


def test_usb_fixed_pins():
    config = _load("KC536")
    config["pins"]["USB_DN_PIN"] = "P04"
    report = validate.validate_config(config)
    assert any("USB 固定脚" in issue.message for issue in report.errors)


def test_report_is_detached_from_input():
    config = _load("KC536")
    snapshot = copy.deepcopy(config)
    validate.validate_config(config)
    assert config == snapshot
