"""项目配置模型：读取 .omcfg、补默认值、计算派生量。

唯一真相源是 SDK 里的 project.omcfg；chip/om6239.json 只提供芯片事实，
boards/*.json 是历史档案，运行时不读取。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CHIP_PATH = REPO_ROOT / "chip" / "om6239.json"
SCHEMA = "om6239-project/v1"
CHIP_MODEL = "OM6239"

# 角色顺序与画表分组：key 顺序沿用 SDK 现有 user_config 的排版。
ROLE_ORDER = [
    "KEY_R0_PIN",
    "KEY_R1_PIN",
    "KEY_R2_PIN",
    "KEY_B_PIN",
    "KEY_P_PIN",
    "KEY_DPI_PIN",
    "KEY_PAIR_PIN",
    "KEY_C0_PIN",
    "KEY_DPI_SUB_PIN",
    "KEY_DPI_ADD_PIN",
    "WHEEL_A_PIN",
    "WHEEL_B_PIN",
    "MODE_24G_PIN",
    "MODE_BLE_PIN",
    "MODE_BLE_24G_PIN",
    "SENSOR_MOTION_PIN",
    "SENSOR_SCLK_PIN",
    "SENSOR_SDIO_PIN",
    "SENSOR_NCS_PIN",
    "LED_MODE_R_PIN",
    "LED_MODE_G_PIN",
    "LED_MODE_B_PIN",
    "LED_LOW_PIN",
    "LEDC_CTRL_PIN",
    "LEDC_PIN",
    "LED_R_PIN",
    "LED_G_PIN",
    "LED_B_PIN",
    "USB_5V",
    "BAT_CHG_PIN",
    "LVD_PIN",
    "USB_DN_PIN",
    "USB_DP_PIN",
    "FLASH_CS_PIN",
    "FLASH_SCLK_PIN",
    "FLASH_MOSI_PIN",
    "FLASH_MISO_PIN",
]

GROUP_ORDER = [
    (
        "按键",
        [
            "KEY_R0_PIN",
            "KEY_R1_PIN",
            "KEY_R2_PIN",
            "KEY_B_PIN",
            "KEY_P_PIN",
            "KEY_DPI_PIN",
            "KEY_PAIR_PIN",
            "KEY_C0_PIN",
            "KEY_DPI_SUB_PIN",
            "KEY_DPI_ADD_PIN",
        ],
    ),
    ("滚轮", ["WHEEL_A_PIN", "WHEEL_B_PIN"]),
    ("Sensor", ["SENSOR_MOTION_PIN", "SENSOR_SCLK_PIN", "SENSOR_SDIO_PIN", "SENSOR_NCS_PIN"]),
    ("模式", ["MODE_24G_PIN", "MODE_BLE_PIN", "MODE_BLE_24G_PIN"]),
    (
        "灯光",
        [
            "LED_MODE_R_PIN",
            "LED_MODE_G_PIN",
            "LED_MODE_B_PIN",
            "LED_LOW_PIN",
            "LEDC_CTRL_PIN",
            "LEDC_PIN",
            "LED_R_PIN",
            "LED_G_PIN",
            "LED_B_PIN",
        ],
    ),
    ("电源", ["USB_5V", "BAT_CHG_PIN"]),
    ("LVD", ["LVD_PIN"]),
    ("FLASH", ["FLASH_CS_PIN", "FLASH_SCLK_PIN", "FLASH_MOSI_PIN", "FLASH_MISO_PIN"]),
]

# 缺省 GPIO：与旧 GUI ROLE_DEFS 一致；配置里可以逐脚覆盖。
DEFAULT_GPIO = {
    "KEY_R0_PIN": ("input_pullup", "pu_30k", "high"),
    "KEY_R1_PIN": ("input_pullup", "pu_30k", "high"),
    "KEY_R2_PIN": ("input_pullup", "pu_30k", "high"),
    "KEY_B_PIN": ("input_pullup", "pu_30k", "high"),
    "KEY_P_PIN": ("input_pullup", "pu_30k", "high"),
    "KEY_DPI_PIN": ("input_pullup", "pu_30k", "high"),
    "KEY_PAIR_PIN": ("input_pullup", "pu_30k", "high"),
    "KEY_C0_PIN": ("output_pp", "pu_30k", "high"),
    "KEY_DPI_SUB_PIN": ("input_pullup", "pu_30k", "high"),
    "KEY_DPI_ADD_PIN": ("input_pullup", "pu_30k", "high"),
    "WHEEL_A_PIN": ("input_pullup", "pu_30k", "high"),
    "WHEEL_B_PIN": ("input_pullup", "pu_30k", "high"),
    "MODE_24G_PIN": ("input_pulldown", "pd_150k", "high"),
    "MODE_BLE_PIN": ("input_pulldown", "pd_150k", "high"),
    "MODE_BLE_24G_PIN": ("input_pullup", "pu_30k", "high"),
    "SENSOR_MOTION_PIN": ("input_pullup", "pu_30k", "high"),
    "SENSOR_SCLK_PIN": ("output_pp", "pu_30k", "high"),
    "SENSOR_SDIO_PIN": ("input_pullup", "pu_30k", "high"),
    "SENSOR_NCS_PIN": ("output_pp", "pu_30k", "high"),
    "LED_MODE_R_PIN": ("output_pp", "pu_30k", "low"),
    "LED_MODE_G_PIN": ("output_pp", "pu_30k", "low"),
    "LED_MODE_B_PIN": ("output_pp", "pu_30k", "low"),
    "LED_LOW_PIN": ("output_pp", "pu_30k", "low"),
    "LEDC_CTRL_PIN": ("output_pp", "pu_30k", "high"),
    "LEDC_PIN": ("output_pp", "pu_30k", "high"),
    "LED_R_PIN": ("output_pp", "pu_30k", "high"),
    "LED_G_PIN": ("output_pp", "pu_30k", "high"),
    "LED_B_PIN": ("output_pp", "pu_30k", "high"),
    "USB_5V": ("input_pulldown", "pd_150k", "high"),
    "BAT_CHG_PIN": ("input_pullup", "pu_30k", "high"),
    "LVD_PIN": ("input_floating", "pu_none", "high"),
    "USB_DN_PIN": ("input_floating", "pu_none", "high"),
    "USB_DP_PIN": ("input_floating", "pu_none", "high"),
    "FLASH_CS_PIN": ("input_pullup", "pu_30k", "high"),
    "FLASH_SCLK_PIN": ("input_pullup", "pu_30k", "high"),
    "FLASH_MOSI_PIN": ("input_pullup", "pu_30k", "high"),
    "FLASH_MISO_PIN": ("input_pullup", "pu_30k", "high"),
}

# 不参加 gpio_config_table 的纯宏角色。
NO_GPIO_TABLE = {"USB_DN_PIN", "USB_DP_PIN"}

GPIO_MODES = {"input_floating", "input_pullup", "input_pulldown", "output_pp"}
GPIO_PULLS = {"pu_none", "pu_30k", "pu_150k", "pd_150k"}
GPIO_INITS = {"high", "low"}

FORBIDDEN_TOP_KEYS = {
    "features",
    "derived",
    "PIN_WAKE_UP_MASK",
    "LVD_CHECK_INDEX",
    "WHEEL_IO_SELECT",
    "WHEEL_SOFT_GPIO",
    "LVD_INDEX",
}

MODE_ENUM = {"single", "dual", "wired"}
LOGO_ENUM = {"rgb", "ledc", "none"}
POLARITY_ENUM = {"active_high", "active_low"}
BUS_ENUM = {"sdio_3wire", "spi_4wire"}
DIR_CLOCK_ENUM = {0, 3, 6, 9}


def load_chip(path: Path | str | None = None) -> dict[str, Any]:
    with Path(path or CHIP_PATH).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_config(path: Path | str) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("配置文件顶层必须是映射")
    return data


def dump_config(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def pin_entries(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    raw = config.get("pins") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for role, value in raw.items():
        if isinstance(value, str):
            value = {"pin": value}
        if not isinstance(value, dict):
            continue
        pin = str(value.get("pin", "")).strip()
        if not pin:
            continue
        gpio = value.get("gpio") or {}
        if not isinstance(gpio, dict):
            gpio = {}
        out[str(role)] = {
            "pin": pin,
            "mode": str(gpio.get("mode") or ""),
            "pull": str(gpio.get("pull") or ""),
            "init": str(gpio.get("init") or ""),
        }
    return out


def resolved_pins(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    """补全 GPIO 缺省值，返回按 ROLE_ORDER 排列的引脚表。"""
    entries = pin_entries(config)
    out: dict[str, dict[str, str]] = {}
    for role in ROLE_ORDER + [r for r in entries if r not in ROLE_ORDER]:
        if role not in entries:
            continue
        item = entries[role]
        dmode, dpull, dinit = DEFAULT_GPIO.get(role, ("input_floating", "pu_none", "high"))
        out[role] = {
            "pin": item["pin"],
            "mode": item["mode"] or dmode,
            "pull": item["pull"] or dpull,
            "init": item["init"] or dinit,
        }
    return out


def board(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("board") or {}
    return value if isinstance(value, dict) else {}


def project(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("project") or {}
    return value if isinstance(value, dict) else {}


def sensor(config: dict[str, Any]) -> dict[str, Any]:
    value = board(config).get("sensor") or {}
    return value if isinstance(value, dict) else {}


def project_id(config: dict[str, Any]) -> dict[str, str]:
    value = project(config).get("id") or {}
    if not isinstance(value, dict):
        value = {}
    return {
        "low": str(value.get("low", "")),
        "high": str(value.get("high", "")),
        "version": str(value.get("version", "")),
    }


def features(
    config: dict[str, Any], pins: dict[str, dict[str, str]] | None = None
) -> dict[str, bool]:
    pins = pins or pin_entries(config)
    b = board(config)
    return {
        "BOARD_HAS_KEY_C0": "KEY_C0_PIN" in pins,
        "BOARD_HAS_EXTRA_KEYS": any(r in pins for r in ("KEY_B_PIN", "KEY_P_PIN", "KEY_DPI_PIN")),
        "BOARD_HAS_DPI_PAIR": "KEY_DPI_SUB_PIN" in pins and "KEY_DPI_ADD_PIN" in pins,
        "BOARD_HAS_SENSOR_NCS": "SENSOR_NCS_PIN" in pins,
        "BOARD_HAS_LED_LOW": "LED_LOW_PIN" in pins,
        "BOARD_MODE_DUAL_PIN": b.get("mode_pins") == "dual",
        "BOARD_MODE_SINGLE_PIN": b.get("mode_pins") == "single",
        "BOARD_LOGO_LEDC": b.get("logo") == "ledc",
        "BOARD_LOGO_RGB": b.get("logo") == "rgb",
        "BOARD_LED_ACTIVE_HIGH": b.get("led_polarity") == "active_high",
        "BOARD_LED_ACTIVE_LOW": b.get("led_polarity") == "active_low",
        "BOARD_WHEEL_SOFT_GPIO": b.get("wheel") == "SOFT_GPIO",
    }


def wake_keys(config: dict[str, Any], pins: dict[str, dict[str, str]] | None = None) -> list[str]:
    pins = pins or pin_entries(config)
    return [r for r in ("KEY_R0_PIN", "KEY_R1_PIN", "KEY_R2_PIN", "KEY_PAIR_PIN") if r in pins]


def wheel_select(config: dict[str, Any]) -> str:
    wheel = str(board(config).get("wheel") or "")
    return "ENCODER_PINMUX_SEL_IO_00_01" if wheel == "SOFT_GPIO" else wheel


def lvd_index(config: dict[str, Any], pins: dict[str, dict[str, str]] | None = None) -> str:
    pins = pins or pin_entries(config)
    pin = pins.get("LVD_PIN", {}).get("pin")
    return f"POF_LVD_PIN_{pin}" if pin else ""


def uart_pin(config: dict[str, Any]) -> str:
    """调试 UART 复用的按键脚，缺省与 KC536 一致。"""
    return str(board(config).get("uart_pin") or "KEY_R0_PIN")


def ledc_rgb_number(config: dict[str, Any]) -> int:
    """LEDC LOGO 的像素数，缺省 6 保持既有工程行为。"""
    try:
        return int(board(config).get("ledc_rgb_number"))
    except (TypeError, ValueError):
        return 6


def mode_pins(config: dict[str, Any], pins: dict[str, dict[str, str]] | None = None) -> list[str]:
    pins = pins or pin_entries(config)
    mode = board(config).get("mode_pins")
    if mode == "dual":
        return [r for r in ("MODE_24G_PIN", "MODE_BLE_PIN") if r in pins]
    if mode == "single":
        return [r for r in ("MODE_BLE_24G_PIN",) if r in pins]
    return []


def gpio_c_constant(value: str) -> str:
    return {
        "input_floating": "USER_GPIO_MODE_INPUT_FLOATING",
        "input_pullup": "USER_GPIO_MODE_INPUT_PULLUP",
        "input_pulldown": "USER_GPIO_MODE_INPUT_PULLDOWN",
        "output_pp": "USER_GPIO_MODE_OUTPUT_PP",
    }.get(value, value.upper())


def pull_c_constant(value: str) -> str:
    return {
        "pu_none": "PU_NONE",
        "pu_30k": "PU_30K",
        "pu_150k": "PU_150K",
        "pd_150k": "PD_150K",
    }.get(value, value.upper())


def level_c_constant(value: str) -> str:
    return "PIN_HIGH_LEV" if value == "high" else "PIN_LOW_LEV"


def default_config_path(sdk_root: Path | str) -> Path:
    return Path(sdk_root) / "projects" / "mouse_demo" / "project.omcfg"
