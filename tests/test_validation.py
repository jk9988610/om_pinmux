import copy
import json
from pathlib import Path

import pytest

import validation


@pytest.fixture
def chip():
    return validation.load_chip()


@pytest.fixture
def bd319():
    return validation.load_json(Path("boards") / "BD319.json")


def test_all_tracked_boards_are_valid():
    paths = sorted(Path("boards").glob("*.json"))
    assert paths
    results = [validation.validate_board_file(path) for path in paths]
    assert all(result["ok"] for result in results), json.dumps(results, ensure_ascii=False, indent=2)


def test_rejects_fixed_usb_mismatch(bd319, chip):
    board = copy.deepcopy(bd319)
    board["pins"]["USB_DP_PIN"] = "P04"

    result = validation.validate_board(board, chip)

    assert not result["ok"]
    assert any(issue["path"] == "pins.USB_DP_PIN" for issue in result["errors"])


def test_rejects_ledc_wheel_collision(chip):
    board = validation.load_json(Path("boards") / "CH04.json")
    board["pins"]["LEDC_CTRL_PIN"] = "P01"

    result = validation.validate_board(board, chip)

    assert not result["ok"]
    assert any("LEDC SEL" in issue["message"] for issue in result["errors"])


def test_rejects_dual_mode_with_single_mode_pin(bd319, chip):
    board = copy.deepcopy(bd319)
    board["pins"]["MODE_BLE_24G_PIN"] = "P26"

    result = validation.validate_board(board, chip)

    assert not result["ok"]
    assert any(issue["path"] == "pins.MODE_BLE_24G_PIN" for issue in result["errors"])
