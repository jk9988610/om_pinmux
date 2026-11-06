"""P3：Sensor 总线形态与 2V 使能。"""

import copy
from pathlib import Path

from omcfg import model, validate
from omcfg.generate import templates

CONFIGS = Path(__file__).resolve().parent.parent / "configs"


def _spi_config() -> dict:
    config = copy.deepcopy(model.load_config(CONFIGS / "BD319.omcfg"))
    config["board"]["sensor"] = {"bus": "spi_4wire", "dir_clock": 6, "v2_en": True}
    del config["pins"]["SENSOR_SDIO_PIN"]
    config["pins"]["SENSOR_MOSI_PIN"] = "P13"
    config["pins"]["SENSOR_MISO_PIN"] = "P34"
    return config


def test_spi_4wire_generates_mosi_miso_and_2v():
    config = _spi_config()
    assert validate.validate_config(config).ok
    pins = model.resolved_pins(config)
    text = templates.render_pins(config, pins)
    assert "#define SENSOR_MOSI_PIN" in text
    assert "#define SENSOR_MISO_PIN" in text
    assert "#define SENSOR_NCS_PIN" in text
    assert "SENSOR_SDIO_PIN" not in text
    assert "#define SENSOR_2V_IN_EN" in text
    table = templates.render_gpio_table(config, pins)
    assert table.count("SENSOR_MOSI_PIN,") == 1
    assert table.count("SENSOR_MISO_PIN,") == 1


def test_sdio_3wire_keeps_sdio_and_has_no_2v():
    config = model.load_config(CONFIGS / "KC536.omcfg")
    pins = model.resolved_pins(config)
    text = templates.render_pins(config, pins)
    assert "#define SENSOR_SDIO_PIN" in text
    assert "SENSOR_MOSI_PIN" not in text
    assert "SENSOR_2V_IN_EN" not in text


def test_spi_4wire_requires_mosi_miso():
    config = _spi_config()
    del config["pins"]["SENSOR_MISO_PIN"]
    report = validate.validate_config(config)
    assert any(issue.path == "pins.SENSOR_MISO_PIN" for issue in report.errors)


def test_sdio_3wire_requires_sdio():
    config = copy.deepcopy(model.load_config(CONFIGS / "KC536.omcfg"))
    del config["pins"]["SENSOR_SDIO_PIN"]
    report = validate.validate_config(config)
    assert any(issue.path == "pins.SENSOR_SDIO_PIN" for issue in report.errors)


def test_v2_en_must_be_bool():
    config = copy.deepcopy(model.load_config(CONFIGS / "CH04.omcfg"))
    config["board"]["sensor"]["v2_en"] = 1
    report = validate.validate_config(config)
    assert any(issue.path == "board.sensor.v2_en" for issue in report.errors)
