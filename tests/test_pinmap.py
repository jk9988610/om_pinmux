from pathlib import Path

from omcfg import model, pinmap

CONFIGS = Path(__file__).resolve().parent.parent / "configs"


def _load(name: str = "CH04") -> dict:
    return model.load_config(CONFIGS / f"{name}.omcfg")


def test_rows_cover_package_and_internal_pins():
    data = pinmap.rows(_load())
    assert [row["pkg"] for row in data["package"]] == list(range(1, 33))
    assert {row["name"] for row in data["internal"]} == {
        "P14", "P15", "P16", "P17", "P35", "P37"
    }
    vdd = next(row for row in data["package"] if row["name"] == "VDD")
    assert vdd["special"] is True
    assert vdd["candidates"] == []
    assert vdd["locked"] is True


def test_internal_flash_pin_is_fixed_and_readonly():
    data = pinmap.rows(_load())
    miso = next(row for row in data["internal"] if row["name"] == "P14")
    assert miso["assigned"] == ["FLASH_MISO_PIN"]
    assert miso["candidates"] == []
    assert miso["locked"] is True
    assert pinmap.role_pin_problem(None, "FLASH_MISO_PIN", "P15")
    assert pinmap.role_pin_problem(None, "KEY_R0_PIN", "P14")


def test_usb_pins_only_offer_usb_functions():
    data = pinmap.rows(_load())
    dn = next(row for row in data["package"] if row["name"] == "P02")
    assert dn["candidates"] == ["USB_DN_PIN"]
    assert pinmap.role_pin_problem(None, "KEY_R0_PIN", "P02")


def test_ledc_and_encoder_constraints():
    pins = pinmap.constraint_pins(None, "LEDC_CTRL_PIN")
    assert pins == {"P01", "P05", "P21", "P33"}
    assert pinmap.role_pin_problem(None, "LEDC_CTRL_PIN", "P34")
    assert pinmap.role_pin_problem(None, "WHEEL_A_PIN", "P10")


def test_moving_key_to_free_pin_keeps_candidates():
    config = _load()
    free = next(row for row in pinmap.rows(config)["package"] if row["name"] == "P10")
    assert "KEY_R0_PIN" in free["candidates"]
    assert "KEY_C0_PIN" in free["candidates"]
    config["pins"]["KEY_R0_PIN"] = "P10"
    after = pinmap.rows(config)
    p10 = next(row for row in after["package"] if row["name"] == "P10")
    assert p10["assigned"] == ["KEY_R0_PIN"]
    assert "KEY_R0_PIN" in p10["candidates"]
    p32 = next(row for row in after["package"] if row["name"] == "P32")
    assert p32["assigned"] == []
