# -*- coding: utf-8 -*-
"""Bring-up survey: questionnaire -> board-desc JSON for om_pinmux.

Non-business board bring-up only (pins/features/pairing strategy).
Does not touch RF protocol / HID report mapping / OEM business logic.
"""
from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SURVEY_DIR = ROOT / "survey"
BOARDS_DIR = ROOT / "boards"
QUESTIONS_PATH = SURVEY_DIR / "questions.json"

GPIO_RE = re.compile(r"^P\d{2}$")


def _load_questions() -> dict[str, Any]:
    return json.loads(QUESTIONS_PATH.read_text(encoding="utf-8-sig"))


def blank_answers() -> dict[str, Any]:
    q = _load_questions()
    answers: dict[str, Any] = {
        "schema": "om6239-bringup-survey/v1",
        "filled_at": None,
        "answers": {},
        "notes": "",
    }
    for section in q["sections"]:
        for item in section["items"]:
            answers["answers"][item["id"]] = item.get("default")
    return answers


def write_blank(path: Path | None = None) -> Path:
    SURVEY_DIR.mkdir(parents=True, exist_ok=True)
    out = path or (SURVEY_DIR / "answers_blank.json")
    data = blank_answers()
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8-sig")
    return out


def _pin(ans: dict[str, Any], key: str) -> str | None:
    v = ans.get(key)
    if v in (None, "", "NONE", "N/A"):
        return None
    return str(v).strip().upper()


def _bool(ans: dict[str, Any], key: str) -> bool:
    v = ans.get(key)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y", "是")
    return bool(v)


def survey_issues(answers: dict[str, Any]) -> list[dict[str, str]]:
    a = answers.get("answers") or answers
    issues: list[dict[str, str]] = []

    def err(code: str, msg: str) -> None:
        issues.append({"level": "error", "code": code, "msg": msg})

    def warn(code: str, msg: str) -> None:
        issues.append({"level": "warn", "code": code, "msg": msg})

    def info(code: str, msg: str) -> None:
        issues.append({"level": "info", "code": code, "msg": msg})

    mode = a.get("mode_topology")
    logo = a.get("logo_type")
    sensor = a.get("sensor_bus")
    led_pol = a.get("led_polarity")

    # Only collect pins that apply to the chosen topology (ignore stale defaults).
    active = {
        "key_l", "key_r", "key_m", "wheel_a", "wheel_b", "motion", "sclk",
        "led_r", "led_g", "led_b", "usb_5v", "bat_chg", "lvd",
    }
    if _bool(a, "has_extra_keys"):
        active.update({"key_4", "key_5"})
    if a.get("key_dpi"):
        active.add("key_dpi")
    if _bool(a, "has_pair"):
        active.add("key_pair")
    if _bool(a, "has_key_c0"):
        active.add("key_c0")
    if mode == "single":
        active.add("mode_single")
    elif mode == "dual":
        active.update({"mode_24g", "mode_ble"})
    elif mode == "wired":
        active.add("mode_wired")
    if sensor == "sdio_3wire":
        active.add("sdio")
    elif sensor == "spi_4wire":
        active.update({"ncs", "mosi", "miso"})
    if _bool(a, "has_led_low"):
        active.add("led_low")
    if logo == "ledc":
        active.update({"ledc", "ledc_ctrl"})

    pins: dict[str, str] = {}
    for k in active:
        v = a.get(k)
        if isinstance(v, str) and GPIO_RE.match(v.strip().upper()):
            pins[k] = v.strip().upper()

    # required basics
    for need in ("key_l", "key_r", "key_m", "wheel_a", "wheel_b", "motion", "sclk", "usb_5v", "lvd"):
        if not _pin(a, need):
            err("MISSING_PIN", f"必填脚未填: {need}")

    if mode == "single" and not _pin(a, "mode_single"):
        err("MODE_SINGLE", "单模式脚拓扑必须填 mode_single (MODE_BLE_24G_PIN)")
    if mode == "dual":
        if not _pin(a, "mode_24g") or not _pin(a, "mode_ble"):
            err("MODE_DUAL", "双模式脚必须填 mode_24g 与 mode_ble")
    if mode == "wired" and not _pin(a, "mode_wired"):
        err("MODE_WIRED", "有线检测拓扑必须填 mode_wired")

    if sensor == "sdio_3wire":
        if not _pin(a, "sdio"):
            err("SENSOR_SDIO", "3 线 SDIO 必须填 sdio；且勿再写 MOSI/MISO")
        if _pin(a, "mosi") or _pin(a, "miso"):
            warn("SENSOR_MIX", "3 线模式仍填了 MOSI/MISO，易与 drv_senscan 冲突（BD319 踩过）")
    if sensor == "spi_4wire":
        for need in ("ncs", "mosi", "miso"):
            if not _pin(a, need):
                err("SENSOR_4WIRE", f"4 线 SPI 必须填: {need}")
        if _pin(a, "sdio"):
            warn("SENSOR_MIX", "4 线模式仍填了 SDIO，请确认驱动不是 drv_senscan 3 线")

    if logo == "ledc":
        if not _pin(a, "ledc"):
            err("LEDC_PIN", "LOGO=LEDC 必须填 ledc 脚")
        info("LEDC_RTE", "写入后需 RTE_LEDC=1，并编译 ledc.c / ledc_mode.c / drv_ledc.c")
    if logo == "rgb":
        info("RGB_NO_LEDC", "RGB LOGO 板勿用 CH04 整包 port_apply（会误引 ledc*）")

    if _bool(a, "has_led_low") and not _pin(a, "led_low"):
        err("LED_LOW", "勾选有 LED_LOW 时必须填 led_low 脚")

    if _bool(a, "has_pair") and not _pin(a, "key_pair"):
        err("PAIR_PIN", "有独立配对键时必须填 key_pair")
    if not _bool(a, "has_pair"):
        info("PAIR_AUTO", "无 PAIR 键：靠首次 24G(first_24g_con)/BLE(ble_id==0xFF)/reset_connect 自动配对；长按 pair 路径为死代码")

    if _bool(a, "has_extra_keys"):
        for need in ("key_4", "key_5"):
            if not _pin(a, need):
                warn("EXTRA_KEYS", f"有侧键但未填 {need}")

    # collisions
    used: dict[str, list[str]] = {}
    for name, p in pins.items():
        used.setdefault(p, []).append(name)
    for p, names in used.items():
        if len(names) > 1:
            # DPI+PAIR same pin is a known intentional conflict pattern when pair commented
            if set(names) <= {"key_dpi", "key_pair"}:
                err("DPI_PAIR_SAME", f"{p} 同时给 DPI 与 PAIR：必须二选一（A02/BD319 选择注释 PAIR）")
            else:
                err("PIN_COLLISION", f"{p} 被多个功能占用: {', '.join(names)}")

    wa, wb = _pin(a, "wheel_a"), _pin(a, "wheel_b")
    ledc = _pin(a, "ledc")
    if logo == "ledc" and ledc and ledc in (wa, wb):
        err("LEDC_WHEEL", f"LEDC 脚 {ledc} 与滚轮重叠，灯效与滚轮会同时挂")

    uart_alias = a.get("uart_alias")
    if uart_alias and uart_alias not in ("NONE", "none", None, ""):
        alias_map = {
            "KEY_R0": "key_l",
            "KEY_R1": "key_r",
            "KEY_R2": "key_m",
        }
        warn(
            "UART_ALIAS",
            f"UART_PIN 复用 {uart_alias}：调用 uart_tx() 会改脚方向，对应按键会失效（BD319 中键踩过）",
        )

    if a.get("mode_ble_check") == a.get("mode_24g_check") and mode == "dual":
        warn("MODE_CHECK_SAME", "MODE_BLE_CHECK 与 MODE_24G_CHECK 相同（如 HTW17），模式判定易歧义，请核原理图有效电平")

    if led_pol not in ("active_high", "active_low"):
        err("LED_POL", "led_polarity 须为 active_high 或 active_low")

    wheel_mux = a.get("wheel_mux")
    if wa and wb and wheel_mux:
        expect = {
            "ENCODER_PINMUX_SEL_IO_00_01": ("P00", "P01"),
            "ENCODER_PINMUX_SEL_IO_05_06": ("P05", "P06"),
            "ENCODER_PINMUX_SEL_IO_20_21": ("P20", "P21"),
            "ENCODER_PINMUX_SEL_IO_24_25": ("P24", "P25"),
        }
        pair = expect.get(str(wheel_mux))
        if pair and {wa, wb} != set(pair):
            err("WHEEL_MUX", f"滚轮脚 {wa}/{wb} 与 {wheel_mux} 不匹配，硬件 mux 只有固定四对")

    if a.get("pairing_24g") == "first_24g_auto":
        info("FIRST_24G", "需 main.c 保留 first_24g_con!=0x77 → rf_mode_convert(CONNECT)；配对成功写回 0x77")
    if a.get("pairing_24g") == "none" and not _bool(a, "has_pair"):
        warn("NO_24G_PAIR_PATH", "无 PAIR 且关闭 24G 首次自动配对：无线首次绑定会很难（BD319 现状）")

    return issues


def answers_to_board(answers: dict[str, Any]) -> dict[str, Any]:
    a = answers.get("answers") or answers
    mode = a.get("mode_topology")
    logo = a.get("logo_type")
    sensor = a.get("sensor_bus")
    led_pol = a.get("led_polarity")

    def p(key: str) -> str | None:
        return _pin(a, key)

    pins: dict[str, str] = {
        "KEY_R0_PIN": p("key_l") or "",
        "KEY_R1_PIN": p("key_r") or "",
        "KEY_R2_PIN": p("key_m") or "",
        "WHEEL_A_PIN": p("wheel_a") or "",
        "WHEEL_B_PIN": p("wheel_b") or "",
        "SENSOR_MOTION_PIN": p("motion") or "",
        "SENSOR_SCLK_PIN": p("sclk") or "",
        "USB_5V": p("usb_5v") or "",
        "BAT_CHG_PIN": p("bat_chg") or "",
        "LVD_PIN": p("lvd") or "",
        "USB_DN_PIN": "P02",
        "USB_DP_PIN": "P03",
        "FLASH_CS_PIN": "P17",
        "FLASH_SCLK_PIN": "P15",
        "FLASH_MOSI_PIN": "P16",
        "FLASH_MISO_PIN": "P14",
    }
    # drop empties
    pins = {k: v for k, v in pins.items() if v}

    if p("key_4"):
        pins["KEY_B_PIN"] = p("key_4")  # type: ignore
    if p("key_5"):
        pins["KEY_P_PIN"] = p("key_5")  # type: ignore
    if p("key_dpi"):
        pins["KEY_DPI_PIN"] = p("key_dpi")  # type: ignore
    if _bool(a, "has_pair") and p("key_pair"):
        pins["KEY_PAIR_PIN"] = p("key_pair")  # type: ignore
    if _bool(a, "has_key_c0") and p("key_c0"):
        pins["KEY_C0_PIN"] = p("key_c0")  # type: ignore

    if mode == "single" and p("mode_single"):
        pins["MODE_BLE_24G_PIN"] = p("mode_single")  # type: ignore
    if mode == "dual":
        if p("mode_24g"):
            pins["MODE_24G_PIN"] = p("mode_24g")  # type: ignore
        if p("mode_ble"):
            pins["MODE_BLE_PIN"] = p("mode_ble")  # type: ignore
    if mode == "wired" and p("mode_wired"):
        pins["MODE_WIRED_PIN"] = p("mode_wired")  # type: ignore

    if sensor == "sdio_3wire" and p("sdio"):
        pins["SENSOR_SDIO_PIN"] = p("sdio")  # type: ignore
    if sensor == "spi_4wire":
        if p("ncs"):
            pins["SENSOR_NCS_PIN"] = p("ncs")  # type: ignore
        if p("mosi"):
            pins["SENSOR_MOSI_PIN"] = p("mosi")  # type: ignore
        if p("miso"):
            pins["SENSOR_MISO_PIN"] = p("miso")  # type: ignore

    if p("led_r"):
        pins["LED_MODE_R_PIN"] = p("led_r")  # type: ignore
        pins["LED_R_PIN"] = p("led_r")  # type: ignore
    if p("led_g"):
        pins["LED_MODE_G_PIN"] = p("led_g")  # type: ignore
        pins["LED_G_PIN"] = p("led_g")  # type: ignore
    if p("led_b"):
        pins["LED_MODE_B_PIN"] = p("led_b")  # type: ignore
        pins["LED_B_PIN"] = p("led_b")  # type: ignore
    if _bool(a, "has_led_low") and p("led_low"):
        pins["LED_LOW_PIN"] = p("led_low")  # type: ignore
    if logo == "ledc" and p("ledc"):
        pins["LEDC_PIN"] = p("ledc")  # type: ignore
        if p("ledc_ctrl"):
            pins["LEDC_CTRL_PIN"] = p("ledc_ctrl")  # type: ignore

    features = {
        "BOARD_HAS_KEY_C0": _bool(a, "has_key_c0"),
        "BOARD_HAS_EXTRA_KEYS": _bool(a, "has_extra_keys"),
        "BOARD_HAS_DPI_PAIR": _bool(a, "has_dpi_pair"),
        "BOARD_HAS_LED_LOW": _bool(a, "has_led_low"),
        "BOARD_HAS_SENSOR_NCS": sensor == "spi_4wire",
        "BOARD_MODE_DUAL_PIN": mode == "dual",
        "BOARD_MODE_SINGLE_PIN": mode == "single",
        "BOARD_MODE_WIRED_PIN": mode == "wired",
        "BOARD_LOGO_LEDC": logo == "ledc",
        "BOARD_LOGO_RGB": logo == "rgb",
        "BOARD_LED_ACTIVE_HIGH": led_pol == "active_high",
        "BOARD_LED_ACTIVE_LOW": led_pol == "active_low",
        "BOARD_SENSOR_SDIO_3WIRE": sensor == "sdio_3wire",
        "BOARD_SENSOR_SPI_4WIRE": sensor == "spi_4wire",
        "BOARD_HAS_KEY_PAIR": _bool(a, "has_pair"),
        "BOARD_PAIR_FIRST_24G_AUTO": a.get("pairing_24g") == "first_24g_auto",
        "BOARD_WHEEL_SOFT_GPIO": _bool(a, "wheel_soft_gpio"),
    }

    lvd = p("lvd") or "P33"
    board = {
        "schema": "om6239-board-desc/v2",
        "chip": "OM6239",
        "meta": {
            "projName": a.get("proj_name") or "NEWBOARD",
            "consumerName": a.get("consumer_name") or "App",
            "projIdL": a.get("proj_id_l") or "0x0000",
            "projIdH": a.get("proj_id_h") or "0x071",
            "verId": a.get("ver_id") or 1,
            "modePins": mode or "dual",
            "logoType": logo or "rgb",
            "hasKeyC0": _bool(a, "has_key_c0"),
            "hasExtraKeys": _bool(a, "has_extra_keys"),
            "hasDpiPair": _bool(a, "has_dpi_pair"),
            "hasKeyPair": _bool(a, "has_pair"),
            "hasLedLow": _bool(a, "has_led_low"),
            "hasSensorNcs": sensor == "spi_4wire",
            "ledPolarity": led_pol,
            "sensorBus": sensor,
            "sensorDir": a.get("sensor_dir") or "SENSOR_DIR_CLOCK_6",
            "wheelMux": a.get("wheel_mux") or "",
            "pairing24g": a.get("pairing_24g"),
            "pairingBle": a.get("pairing_ble"),
            "uartAlias": a.get("uart_alias"),
            "modeBleCheck": a.get("mode_ble_check"),
            "mode24gCheck": a.get("mode_24g_check"),
            "goldenHint": a.get("golden_hint"),
            "surveyGenerated": datetime.now().isoformat(timespec="seconds"),
        },
        "features": features,
        "pins": pins,
        "derived": {
            "LVD_CHECK_INDEX": f"POF_LVD_PIN_{lvd}",
            "WHEEL_IO_SELECT": a.get("wheel_mux") or "",
            "WHEEL_SOFT_GPIO": _bool(a, "wheel_soft_gpio"),
        },
        "notes": [],
        "source": "survey/answers",
    }

    notes: list[str] = []
    if not _bool(a, "has_pair"):
        notes.append("无 KEY_PAIR：key_io 应用 #ifdef KEY_PAIR_PIN；勿把 DPI 脚再定义成 PAIR")
    if mode == "dual":
        notes.append("双模式脚：sleep/扫描用 MODE_24G_PIN + MODE_BLE_PIN，不要再用 MODE_BLE_24G_PIN")
    if mode == "single":
        notes.append("单模式脚：sleep/扫描用 MODE_BLE_24G_PIN")
    if sensor == "sdio_3wire":
        notes.append("传感器 3 线：user_config 只留 SENSOR_SDIO_PIN；驱动走 drv_senscan")
    if sensor == "spi_4wire":
        notes.append("传感器 4 线：NCS/SCLK/MOSI/MISO；勿混用 SDIO 宏")
    if a.get("uart_alias") not in (None, "", "NONE"):
        notes.append(f"UART_PIN 复用 {a.get('uart_alias')}，调试期慎用 uart_tx")
    if answers.get("notes"):
        notes.append(str(answers["notes"]))
    board["notes"] = notes
    return board


def export_board(answers_path: Path, out_path: Path | None = None, force: bool = False) -> dict[str, Any]:
    answers = json.loads(answers_path.read_text(encoding="utf-8-sig"))
    issues = survey_issues(answers)
    errors = [i for i in issues if i["level"] == "error"]
    board = answers_to_board(answers)
    name = board["meta"]["projName"]
    dest = out_path or (BOARDS_DIR / f"{name}.json")
    result = {
        "ok": len(errors) == 0 or force,
        "board_path": str(dest),
        "issues": issues,
        "board": board,
    }
    if errors and not force:
        result["message"] = f"调查表有 {len(errors)} 个错误，未写入。可 --force 强制导出。"
        return result
    BOARDS_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(board, ensure_ascii=False, indent=2) + "\n", encoding="utf-8-sig")
    result["message"] = f"已导出板描述: {dest}"
    return result


def check_answers(answers_path: Path) -> dict[str, Any]:
    answers = json.loads(answers_path.read_text(encoding="utf-8-sig"))
    issues = survey_issues(answers)
    errors = sum(1 for i in issues if i["level"] == "error")
    warns = sum(1 for i in issues if i["level"] == "warn")
    return {
        "ok": errors == 0,
        "summary": {"error": errors, "warn": warns, "info": len(issues) - errors - warns},
        "issues": issues,
        "message": f"调查表校验: error={errors} warn={warns}",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="survey", description="OM6239 开板调查表")
    sub = parser.add_subparsers(dest="command", required=True)

    blank = sub.add_parser("blank", help="生成空白 answers JSON")
    blank.add_argument("--out", default="")

    chk = sub.add_parser("check", help="校验已填调查表")
    chk.add_argument("--answers", required=True)

    exp = sub.add_parser("export", help="调查表导出 boards/<Name>.json")
    exp.add_argument("--answers", required=True)
    exp.add_argument("--out", default="")
    exp.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "blank":
        path = write_blank(Path(args.out) if args.out else None)
        print(json.dumps({"ok": True, "path": str(path), "message": f"空白调查表: {path}"}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "check":
        result = check_answers(Path(args.answers))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    result = export_board(Path(args.answers), Path(args.out) if args.out else None, force=args.force)
    print(json.dumps({k: v for k, v in result.items() if k != "board"}, ensure_ascii=False, indent=2))
    if result.get("ok") and "board" in result:
        # also print path
        pass
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
