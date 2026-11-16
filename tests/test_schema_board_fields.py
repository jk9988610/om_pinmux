"""board 段 schema 字段：uart_pin / ledc_rgb_number / sensor.dpi_levels / sensor.v2_en。"""

import json
from pathlib import Path

import yaml

from omcfg import validate

SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "omcfg-v1.schema.json"
CONFIGS = Path(__file__).resolve().parents[1] / "configs"


def _load_schema():
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _load_config(name):
    return yaml.safe_load((CONFIGS / f"{name}.omcfg").read_text(encoding="utf-8"))


def test_schema_has_uart_pin_field():
    s = _load_schema()
    assert "uart_pin" in s["properties"]["board"]["properties"]
    assert set(s["properties"]["board"]["properties"]["uart_pin"]["enum"]) == {
        "KEY_R0_PIN",
        "KEY_R1_PIN",
        "KEY_R2_PIN",
        "KEY_PAIR_PIN",
    }


def test_schema_has_ledc_rgb_number_field():
    s = _load_schema()
    p = s["properties"]["board"]["properties"]["ledc_rgb_number"]
    assert p["type"] == "integer"
    assert p["minimum"] == 1 and p["maximum"] == 64


def test_schema_sensor_has_dpi_fields():
    s = _load_schema()
    sensor_props = s["properties"]["board"]["properties"]["sensor"]["properties"]
    assert "dpi_levels" in sensor_props
    assert "dpi_default" in sensor_props
    assert "v2_en" in sensor_props


def test_uart_pin_enum_validated():
    """uart_pin 只能是 4 个按键脚之一。"""
    config = _load_config("CH04")
    config["board"]["uart_pin"] = "P99"
    report = validate.validate_config(config)
    assert not report.ok
    assert any("uart_pin" in e.path for e in report.errors)


def test_ledc_rgb_number_range_validated():
    """ledc_rgb_number 必须 1..64。"""
    config = _load_config("CH04")
    config["board"]["ledc_rgb_number"] = 100
    report = validate.validate_config(config)
    assert not report.ok
    assert any("ledc_rgb_number" in e.path for e in report.errors)


def test_ledc_rgb_number_zero_rejected():
    config = _load_config("CH04")
    config["board"]["ledc_rgb_number"] = 0
    report = validate.validate_config(config)
    assert not report.ok


def test_ledc_rgb_number_non_int_rejected():
    config = _load_config("CH04")
    config["board"]["ledc_rgb_number"] = "abc"
    report = validate.validate_config(config)
    assert not report.ok
