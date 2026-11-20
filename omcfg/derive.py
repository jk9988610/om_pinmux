"""从未初始化 SDK 的 user_config.h/.c 推导一份配置初稿。

只读工程现状，不写文件；用于 configs/ 里没有对应模板的新板首次接入。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import model
from .targets import sdk

PIN_RE = re.compile(r"^[ \t]*#define[ \t]+(?P<role>[A-Z][A-Z0-9_]*)[ \t]+\((?P<pin>P\d{2})\)[ \t]*$", re.M)
DEFINE_RE = re.compile(r"^[ \t]*#define[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)[ \t]+(?P<value>[^\s/]+)", re.M)
STRING_RE = re.compile(r'^[ \t]*#define[ \t]+(?P<name>iPROJECT_NAME|iCONSUMER_NAME)[ \t]+"(?P<value>[^"]*)"', re.M)
LED_ON_RE = re.compile(r"led_r_on\(\)[ \t]*(?:\([ \t]*)?(?P<fn>gpio_set|gpio_clear)\(")
# 逐只灯的 on 宏：函数名 -> (主极性角色, 宏目标脚)。别名脚跟随主模式灯。
LED_ON_SPECS = {
    "led_r_on": ("LED_MODE_R_PIN", "LED_MODE_R_PIN"),
    "led_g_on": ("LED_MODE_G_PIN", "LED_MODE_G_PIN"),
    "led_b_on": ("LED_MODE_B_PIN", "LED_MODE_B_PIN"),
    "led_low_on": ("LED_LOW_PIN", "LED_LOW_PIN"),
    "led_24g_on": ("LED_MODE_R_PIN", "LED_MODE_24G_PIN"),
    "led_bt1_on": ("LED_MODE_G_PIN", "LED_MODE_BT1_PIN"),
    "led_bt0_on": ("LED_MODE_B_PIN", "LED_MODE_BT0_PIN"),
}


def _derive_led_polarities(header: str, baseline: str) -> dict[str, str]:
    """逐只灯解析极性，只记录与基线不同的脚（相同则沿用全局兼容值）。"""
    out: dict[str, str] = {}
    for func, (source_role, macro) in LED_ON_SPECS.items():
        pat = re.compile(
            rf"#define\s+{func}\(\)[ \t]*(?:\([ \t]*)?(?P<fn>gpio_set|gpio_clear)\([ \t]*{macro}[ \t]*\)"
        )
        match = pat.search(header)
        if not match:
            continue
        polarity = "active_high" if match.group("fn") == "gpio_set" else "active_low"
        if polarity != baseline:
            out[source_role] = polarity
    return out
DIR_CLOCK_RE = re.compile(r"SENSOR_DIR_DEFINE[ \t]+SENSOR_DIR_CLOCK_(?P<value>0|3|6|9)")
DPI_INI_RE = re.compile(r"sensor_dpi_ini\s*\[\s*\]\s*=\s*\{([^}]*)\}", re.S)
DPI_ENTRY_RE = re.compile(r"(\d+)L/200L-1")
DPI_DEFAULT_RE = re.compile(r"#define\s+DEFAULT_DPI_GRADE\s+(\d+)")
GPIO_ROW_RE = re.compile(
    r"\{[ \t]*(?P<role>[A-Za-z_][A-Za-z0-9_]*)[ \t]*,[ \t]*"
    r"USER_GPIO_MODE_(?P<mode>[A-Z_]+)[ \t]*,[ \t]*"
    r"(?P<pull>PU_[A-Z0-9_]+|PD_[A-Z0-9_]+)[ \t]*,[ \t]*"
    r"PIN_(?P<level>HIGH|LOW)_LEV[ \t]*\}",
    re.M,
)

MODE_MAP = {
    "INPUT_FLOATING": "input_floating",
    "INPUT_PULLUP": "input_pullup",
    "INPUT_PULLDOWN": "input_pulldown",
    "OUTPUT_PP": "output_pp",
}
PULL_MAP = {"PU_NONE": "pu_none", "PU_30K": "pu_30k", "PU_150K": "pu_150k", "PD_150K": "pd_150k"}
BOARD_HEADER = "# 由 omcfg 依据工程现状推导的配置初稿；请复核后再生成\n"


def _defines(text: str) -> dict[str, str]:
    return {match.group("name"): match.group("value") for match in DEFINE_RE.finditer(text)}


def _pins_from_header(text: str) -> dict[str, str]:
    pins: dict[str, str] = {}
    for match in PIN_RE.finditer(text):
        role = match.group("role")
        if role in model.ROLE_ORDER:
            pins[role] = match.group("pin")
    return pins


def _gpio_from_source(text: str) -> dict[str, dict[str, str]]:
    start = text.find("gpio_config_table")
    if start == -1:
        return {}
    end = text.find("};", start)
    rows = text[start : end if end != -1 else len(text)]
    gpio: dict[str, dict[str, str]] = {}
    for match in GPIO_ROW_RE.finditer(rows):
        mode = MODE_MAP.get(match.group("mode"))
        pull = PULL_MAP.get(match.group("pull"))
        if not mode or not pull:
            continue
        gpio[match.group("role")] = {
            "mode": mode,
            "pull": pull,
            "init": match.group("level").lower(),
        }
    return gpio


def _wheel(header: str, pins: dict[str, str]) -> str:
    if re.search(r"^[ \t]*#define[ \t]+WHEEL_SOFT_GPIO", header, re.M):
        return "SOFT_GPIO"
    macro = _defines(header).get("WHEEL_IO_SELECT")
    if macro:
        return macro
    pair = {pins.get("WHEEL_A_PIN"), pins.get("WHEEL_B_PIN")}
    for item in model.load_chip()["mux"]["ENCODER"]["sdk_macros"]:
        if set(item["pins"]) == pair:
            return str(item["macro"])
    raise sdk.TargetError("user_config.h 缺少 WHEEL_IO_SELECT，且 WHEEL_A/B 不对应任何编码器对")


def _require(numbers: dict[str, str], name: str, path: Path) -> str:
    value = numbers.get(name, "")
    if not value:
        raise sdk.TargetError(f"{path} 中找不到 {name}，无法推导 project.id")
    return value


def derive_config(root: Path | str) -> dict:
    """按工程现状拼出一份可通过校验的配置；工程不完整时抛 TargetError。"""
    root_path = Path(root)
    header_path = root_path / sdk.USER_CONFIG_H
    source_path = root_path / sdk.USER_CONFIG_C
    if not header_path.is_file() or not source_path.is_file():
        raise sdk.TargetError(f"{root_path} 缺少 user_config.h/.c，无法推导配置")
    header = sdk.read_source(header_path).text
    source = sdk.read_source(source_path).text

    pins = _pins_from_header(header)
    if not pins:
        raise sdk.TargetError(f"{header_path} 中找不到功能引脚宏，无法推导 pins")
    gpio = _gpio_from_source(source)

    strings = {match.group("name"): match.group("value") for match in STRING_RE.finditer(header)}
    name = strings.get("iPROJECT_NAME", "").strip()
    customer = strings.get("iCONSUMER_NAME", "").strip()
    if not name or not customer:
        raise sdk.TargetError(f"{header_path} 缺少 iPROJECT_NAME / iCONSUMER_NAME，无法推导项目名")

    numbers = _defines(header)
    project_id = {
        "low": _require(numbers, "iPROJECT_ID_L", header_path),
        "high": _require(numbers, "iPROJECT_ID_H", header_path),
        "version": _require(numbers, "iREAL_VERSION_ID", header_path),
    }

    if {"MODE_24G_PIN", "MODE_BLE_PIN"} & set(pins):
        mode = "dual"
    elif "MODE_BLE_24G_PIN" in pins:
        mode = "single"
    else:
        raise sdk.TargetError(f"{header_path} 缺少模式检测脚宏，无法推导 board.mode_pins")

    if "LED_R_PIN" in pins:
        logo = "rgb"
    elif "LEDC_PIN" in pins:
        logo = "ledc"
    else:
        logo = "none"

    match = LED_ON_RE.search(header)
    polarity = "active_high" if match and match.group("fn") == "gpio_set" else "active_low"
    dir_match = DIR_CLOCK_RE.search(header)
    dir_clock = int(dir_match.group("value")) if dir_match else 6

    sensor_board: dict[str, object] = {
        "bus": "sdio_3wire" if "SENSOR_SDIO_PIN" in pins else "spi_4wire",
        "dir_clock": dir_clock,
    }
    sensor_c = root_path / sdk.PERIPH / "sensor.c"
    sensor_h = root_path / sdk.PERIPH / "sensor.h"
    if sensor_c.is_file():
        match = DPI_INI_RE.search(sdk.read_source(sensor_c).text)
        levels = [int(value) for value in DPI_ENTRY_RE.findall(match.group(1))] if match else []
        if levels:
            sensor_board["dpi_levels"] = levels
            if sensor_h.is_file():
                default = DPI_DEFAULT_RE.search(sdk.read_source(sensor_h).text)
                if default:
                    sensor_board["dpi_default"] = int(default.group(1))

    board: dict[str, object] = {
        "mode_pins": mode,
        "logo": logo,
        "led_polarity": polarity,
        "sensor": sensor_board,
        "wheel": _wheel(header, pins),
    }
    uart = numbers.get("UART_PIN", "").strip("()")
    if uart in ("KEY_R0_PIN", "KEY_R1_PIN", "KEY_R2_PIN", "KEY_PAIR_PIN"):
        board["uart_pin"] = uart
    if logo == "ledc" and numbers.get("LEDC_RGB_NUMBER", "").isdigit():
        board["ledc_rgb_number"] = int(numbers["LEDC_RGB_NUMBER"])

    entries: dict[str, object] = {}
    for role in model.ROLE_ORDER:
        pin = pins.get(role)
        if not pin:
            continue
        item = gpio.get(role)
        entries[role] = {"pin": pin, "gpio": item} if item else pin

    config: dict = {
        "schema": model.SCHEMA,
        "chip": model.CHIP_MODEL,
        "project": {"name": name, "customer": customer, "id": project_id},
        "board": board,
        "pins": entries,
        "codegen": {
            "output": "periph",
            "keil_project": sdk.KEIL_PROJECT.as_posix(),
        },
    }
    per_pin = _derive_led_polarities(header, polarity)
    if per_pin:
        config["polarity"] = per_pin
    return config


def render(config: dict) -> str:
    """带说明的 YAML 文本；写进 SDK 前先给人一眼判断来源。"""
    return BOARD_HEADER + model.dump_config(config)
