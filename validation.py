"""Validation services for OM6239 chip and board descriptions.

The validator intentionally uses only the standard library so it is available to the
GUI and command-line tools without an extra runtime dependency.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

TOOL_DIR = Path(__file__).resolve().parent
BOARDS_DIR = TOOL_DIR / "boards"
CHIP_PATH = TOOL_DIR / "chip" / "om6239.json"
PIN_RE = re.compile(r"^P\d{2}$")


def _issue(path: str, message: str, suggestion: str = "") -> dict[str, str]:
    result = {"path": path, "message": message}
    if suggestion:
        result["suggestion"] = suggestion
    return result


def load_json(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path}")
    return data


def load_chip(path: str | Path = CHIP_PATH) -> dict[str, Any]:
    return load_json(path)


def validate_chip(chip: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if chip.get("chip") != "OM6239":
        errors.append(_issue("chip", "仅支持 OM6239 芯片描述"))
    package = chip.get("package_pins")
    if not isinstance(package, list) or not package:
        errors.append(_issue("package_pins", "必须包含封装脚定义"))
    return errors


def _allowed_pins(chip: dict[str, Any]) -> set[str]:
    return {
        str(item.get("name"))
        for item in chip.get("package_pins", [])
        if isinstance(item, dict) and PIN_RE.match(str(item.get("name", "")))
    }


def _encoder_pairs(chip: dict[str, Any]) -> set[frozenset[str]]:
    return {
        frozenset(item.get("pins", []))
        for item in chip.get("mux", {}).get("ENCODER", {}).get("sdk_macros", [])
        if isinstance(item, dict)
    }


def _ledc_sel_pins(chip: dict[str, Any]) -> set[str]:
    return {
        pin
        for item in chip.get("mux", {}).get("LEDC_SEL", {}).get("options", [])
        if isinstance(item, dict)
        for pin in item.get("pins", [])
    }


def validate_board(board: dict[str, Any], chip: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate schema-shaped fields and OM6239 board-level safety rules."""
    chip = chip or load_chip()
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if board.get("schema") != "om6239-board-desc/v2":
        errors.append(_issue("schema", "必须为 om6239-board-desc/v2"))
    if board.get("chip") != "OM6239":
        errors.append(_issue("chip", "板描述仅允许 OM6239"))

    meta = board.get("meta")
    features = board.get("features")
    pins = board.get("pins")
    derived = board.get("derived")
    if not isinstance(meta, dict):
        errors.append(_issue("meta", "必须是对象"))
        meta = {}
    if not isinstance(features, dict):
        errors.append(_issue("features", "必须是对象"))
        features = {}
    if not isinstance(pins, dict) or not pins:
        errors.append(_issue("pins", "必须是非空对象"))
        pins = {}
    if not isinstance(derived, dict):
        errors.append(_issue("derived", "必须是对象"))
        derived = {}

    for name in ("projName", "modePins", "logoType", "ledPolarity"):
        if not meta.get(name):
            errors.append(_issue(f"meta.{name}", "必填字段缺失"))
    if meta.get("modePins") not in ("single", "dual"):
        errors.append(_issue("meta.modePins", "仅允许 single 或 dual"))
    if meta.get("logoType") not in ("ledc", "rgb"):
        errors.append(_issue("meta.logoType", "仅允许 ledc 或 rgb"))
    if meta.get("ledPolarity") not in ("active_high", "active_low"):
        errors.append(_issue("meta.ledPolarity", "仅允许 active_high 或 active_low"))

    allowed = _allowed_pins(chip)
    internal = set(chip.get("internal_not_on_package", []))
    locations: dict[str, list[str]] = {}
    for macro, pin in pins.items():
        if not isinstance(pin, str) or not PIN_RE.match(pin):
            errors.append(_issue(f"pins.{macro}", "脚位必须为 Pxx 格式"))
            continue
        if macro.startswith("FLASH_"):
            # SDK flash placeholders are intentionally not normal package GPIOs.
            continue
        if pin in internal or pin not in allowed:
            errors.append(_issue(f"pins.{macro}", f"{pin} 不是可用 QFN32 GPIO", "选择 chip/om6239.json 中的封装 GPIO"))
        locations.setdefault(pin, []).append(macro)

    # LED_MODE_* and LED_* can intentionally describe the same RGB channel.
    for pin, macros in locations.items():
        exclusive = [m for m in macros if not m.startswith("LED_")]
        if len(exclusive) > 1:
            errors.append(_issue(f"pins[{pin}]", f"独占功能脚重复分配: {', '.join(exclusive)}", "为每个独占功能分配不同 GPIO"))

    logo_ledc = meta.get("logoType") == "ledc"
    if bool(features.get("BOARD_LOGO_LEDC")) != logo_ledc:
        errors.append(_issue("features.BOARD_LOGO_LEDC", "必须与 meta.logoType 一致"))
    if bool(features.get("BOARD_LOGO_RGB")) == logo_ledc:
        errors.append(_issue("features.BOARD_LOGO_RGB", "必须与 meta.logoType 一致"))

    dual = meta.get("modePins") == "dual"
    expected_mode = ("MODE_24G_PIN", "MODE_BLE_PIN") if dual else ("MODE_BLE_24G_PIN",)
    missing_mode = [name for name in expected_mode if name not in pins]
    if missing_mode:
        errors.append(_issue("pins", f"{meta.get('modePins')} 模式缺少: {', '.join(missing_mode)}"))
    forbidden_mode = "MODE_BLE_24G_PIN" if dual else None
    if forbidden_mode and forbidden_mode in pins:
        errors.append(_issue(f"pins.{forbidden_mode}", "双模式板不可同时定义单模式脚"))
    if bool(features.get("BOARD_MODE_DUAL_PIN")) != dual or bool(features.get("BOARD_MODE_SINGLE_PIN")) == dual:
        errors.append(_issue("features", "BOARD_MODE_DUAL_PIN / BOARD_MODE_SINGLE_PIN 必须与 meta.modePins 一致"))

    fixed_usb = chip.get("mux", {}).get("USB", {}).get("fixed", {})
    for macro, expected in fixed_usb.items():
        if macro in pins and pins[macro] != expected:
            errors.append(_issue(f"pins.{macro}", f"USB 脚固定为 {expected}，当前为 {pins[macro]}"))

    wheel = {pins.get("WHEEL_A_PIN"), pins.get("WHEEL_B_PIN")}
    if None not in wheel:
        if frozenset(wheel) not in _encoder_pairs(chip):
            errors.append(_issue("pins.WHEEL_A_PIN", "滚轮脚不是芯片支持的 ENCODER 对"))
        if derived.get("WHEEL_IO_SELECT") != meta.get("wheelMux"):
            errors.append(_issue("derived.WHEEL_IO_SELECT", "必须与 meta.wheelMux 一致"))

    if logo_ledc:
        ledc_candidates = {pins.get("LEDC_PIN"), pins.get("LEDC_CTRL_PIN")} & _ledc_sel_pins(chip)
        if not ledc_candidates:
            warnings.append(_issue("pins.LEDC_CTRL_PIN", "未从板描述推断到 LEDC SEL 脚；请在 ledc.c 确认"))
        elif wheel & ledc_candidates:
            errors.append(_issue("pins.LEDC_CTRL_PIN", "LEDC SEL 不可与滚轮脚重叠"))
    elif "LEDC_PIN" in pins or "LEDC_CTRL_PIN" in pins:
        warnings.append(_issue("pins", "RGB 板定义了 LEDC 脚，请确认不是遗留配置"))

    lvd = pins.get("LVD_PIN")
    if lvd and derived.get("LVD_CHECK_INDEX") != f"POF_LVD_PIN_{lvd}":
        errors.append(_issue("derived.LVD_CHECK_INDEX", f"必须为 POF_LVD_PIN_{lvd}"))

    return {"ok": not errors, "errors": errors, "warnings": warnings, "summary": {"error": len(errors), "warn": len(warnings)}}


def validate_board_file(path: str | Path, chip_path: str | Path = CHIP_PATH) -> dict[str, Any]:
    try:
        result = validate_board(load_json(path), load_chip(chip_path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [_issue(str(path), str(exc))], "warnings": [], "summary": {"error": 1, "warn": 0}}
    result["path"] = str(Path(path).resolve())
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 OM6239 板描述")
    parser.add_argument("board", nargs="?", help="boards/<name>.json 或完整 JSON 路径")
    parser.add_argument("--all", action="store_true", help="校验 boards/ 下全部 JSON")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)
    paths = sorted(BOARDS_DIR.glob("*.json")) if args.all else [Path(args.board or "")]
    if not args.all and not args.board:
        parser.error("请提供 board 或 --all")
    results = []
    for path in paths:
        if not path.is_file():
            path = BOARDS_DIR / f"{path.name}.json"
        results.append(validate_board_file(path))
    ok = all(item["ok"] for item in results)
    if args.json:
        print(json.dumps({"ok": ok, "results": results}, ensure_ascii=False, indent=2))
    else:
        for item in results:
            print(f"{'PASS' if item['ok'] else 'FAIL'} {item.get('path', '')}")
            for issue in item["errors"] + item["warnings"]:
                print(f"  {issue['path']}: {issue['message']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
