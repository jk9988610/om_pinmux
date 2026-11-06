"""项目配置模型：读取 .omcfg、补默认值、计算派生量。

唯一真相源是 SDK 里的 project.omcfg；chip/om6239.json 只提供芯片事实，
boards/*.json 是历史档案，运行时不读取。
"""

from __future__ import annotations

import json
import re
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
    "SENSOR_MOSI_PIN",
    "SENSOR_MISO_PIN",
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
    (
        "Sensor",
        [
            "SENSOR_MOTION_PIN",
            "SENSOR_SCLK_PIN",
            "SENSOR_SDIO_PIN",
            "SENSOR_NCS_PIN",
            "SENSOR_MOSI_PIN",
            "SENSOR_MISO_PIN",
        ],
    ),
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
    "SENSOR_MOSI_PIN": ("output_pp", "pu_30k", "high"),
    "SENSOR_MISO_PIN": ("input_pullup", "pu_30k", "high"),
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


def load_config_text(text: str) -> dict[str, Any]:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("配置文件顶层必须是映射")
    return data


def load_config(path: Path | str) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        return load_config_text(handle.read())


PIN_INLINE_RE = re.compile(r"pin\s*:\s*[^,}\s#]+")
PIN_SCALAR_RE = re.compile(r"(?P<lead>\s*)(?P<value>[^#\s]+)(?P<tail>\s*(?:#.*)?)")


def set_pin_text(text: str, role: str, pin: str) -> str:
    """只在 YAML 文本里替换某个引脚的 pin 值，保留注释与排版。

    支持三种既有写法：`ROLE: Pxx`、`ROLE: { pin: Pxx, ... }`、
    `ROLE:` 换行缩进的 `pin: Pxx`。找不到角色时抛 ValueError。
    """
    pin = str(pin).strip()
    if not pin:
        raise ValueError("引脚值不能为空")
    lines = text.split("\n")
    target = next(
        (
            index
            for index, line in enumerate(lines)
            if line.lstrip().startswith(f"{role}:") and not line.lstrip().startswith("#")
        ),
        None,
    )
    if target is None:
        raise ValueError(f"配置里没有引脚 {role}；先 init 或手工添加后再改")
    line = lines[target]
    indent = len(line) - len(line.lstrip())
    prefix, rest = line.split(":", 1)
    if "{" in rest:
        replaced, count = PIN_INLINE_RE.subn(f"pin: {pin}", rest, count=1)
        if count != 1:
            raise ValueError(f"{role} 的内联写法里没有 pin: 字段")
        lines[target] = f"{prefix}:{replaced}"
        return "\n".join(lines)
    if rest.split("#", 1)[0].strip():
        match = PIN_SCALAR_RE.match(rest)
        if not match:
            raise ValueError(f"{role} 的写法无法识别：{line.strip()}")
        lines[target] = f"{prefix}:{match.group('lead')}{pin}{match.group('tail')}"
        return "\n".join(lines)
    for index in range(target + 1, len(lines)):
        nested = lines[index]
        if not nested.strip():
            continue
        nested_indent = len(nested) - len(nested.lstrip())
        if nested_indent <= indent:
            break
        match = re.match(r"(?P<lead>\s*pin\s*:\s*)(?P<value>[^#\s]+)(?P<tail>\s*(?:#.*)?)$", nested)
        if match:
            lines[index] = f"{match.group('lead')}{pin}{match.group('tail')}"
            return "\n".join(lines)
    raise ValueError(f"{role} 是嵌套写法但没有 pin: 字段")


def _block_lines(lines: list[str], key: str) -> tuple[int, int, int]:
    """返回顶层段的 (起始行, 结束行(不含), 子项缩进)；找不到抛 ValueError。"""
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if line.lstrip().startswith(f"{key}:") and not line.lstrip().startswith("#")
        ),
        None,
    )
    if start is None:
        raise ValueError(f"配置里没有 {key}: 段")
    indent = len(lines[start]) - len(lines[start].lstrip())
    stop = len(lines)
    for index in range(start + 1, len(lines)):
        text = lines[index]
        if not text.strip():
            continue
        if len(text) - len(text.lstrip()) <= indent:
            stop = index
            break
    child = indent + 2
    for index in range(start + 1, stop):
        text = lines[index]
        if text.strip() and not text.lstrip().startswith("#"):
            child = len(text) - len(text.lstrip())
            break
    return start, stop, child


def _role_line(lines: list[str], role: str, start: int, stop: int) -> int | None:
    return next(
        (
            index
            for index in range(start + 1, stop)
            if lines[index].lstrip().startswith(f"{role}:")
            and not lines[index].lstrip().startswith("#")
        ),
        None,
    )


def remove_pin_text(text: str, role: str) -> str:
    """解除某个角色的分配；角色不存在时原样返回。"""
    lines = text.split("\n")
    try:
        start, stop, _child = _block_lines(lines, "pins")
    except ValueError:
        return text
    target = next(
        (
            index
            for index in range(start + 1, stop)
            if lines[index].lstrip().startswith(f"{role}:")
            and not lines[index].lstrip().startswith("#")
        ),
        None,
    )
    if target is None:
        return text
    indent = len(lines[target]) - len(lines[target].lstrip())
    inline = lines[target].split(":", 1)[1].split("#", 1)[0].strip()
    if inline:
        del lines[target]
        return "\n".join(lines)
    end = target + 1
    while end < len(lines):
        nested = lines[end]
        if not nested.strip():
            end += 1
            continue
        if len(nested) - len(nested.lstrip()) <= indent:
            break
        end += 1
    del lines[target:end]
    return "\n".join(lines)


def add_pin_text(text: str, role: str, pin: str) -> str:
    """新增角色分配；已存在则改值，保证幂等。"""
    pin = str(pin).strip()
    if not pin:
        raise ValueError("引脚值不能为空")
    lines = text.split("\n")
    start, stop, child = _block_lines(lines, "pins")
    if _role_line(lines, role, start, stop) is not None:
        return set_pin_text(text, role, pin)
    entry = f"{' ' * child}{role}: {pin}"
    head = lines[start]
    if "{" in head.split(":", 1)[1]:
        lines[start] = head.split(":", 1)[0] + ":\n" + entry
        return "\n".join(lines)
    last = None
    for index in range(start + 1, stop):
        if lines[index].strip() and not lines[index].lstrip().startswith("#"):
            last = index
    insert = (last + 1) if last is not None else (start + 1)
    lines.insert(insert, entry)
    return "\n".join(lines)


def set_board_value_text(text: str, key: str, value: str) -> str:
    """改写 board 段的标量值（目前只用于 wheel），保留行尾注释。"""
    lines = text.split("\n")
    start, stop, child = _block_lines(lines, "board")
    target = next(
        (
            index
            for index in range(start + 1, stop)
            if lines[index].lstrip().startswith(f"{key}:")
            and not lines[index].lstrip().startswith("#")
        ),
        None,
    )
    if target is None:
        lines.insert(stop, f"{' ' * child}{key}: {value}")
        return "\n".join(lines)
    line = lines[target]
    prefix, rest = line.split(":", 1)
    tail = ""
    if "#" in rest:
        tail = " " + rest.split("#", 1)[1]
        tail = " #" + tail.lstrip()
    lines[target] = f"{prefix}: {value}{tail}"
    return "\n".join(lines)


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


def sensor_v2_en(config: dict[str, Any]) -> bool:
    return sensor(config).get("v2_en") is True


def sensor_bus(config: dict[str, Any]) -> str:
    return str(sensor(config).get("bus") or "")


def dpi_levels(config: dict[str, Any]) -> list[int]:
    """配置声明的 DPI 档位；未配置返回空列表。"""
    value = sensor(config).get("dpi_levels")
    if not isinstance(value, list):
        return []
    return [int(item) for item in value if isinstance(item, int) and not isinstance(item, bool)]


def dpi_default(config: dict[str, Any]) -> int | None:
    value = sensor(config).get("dpi_default")
    if isinstance(value, bool):
        return None
    return int(value) if isinstance(value, int) else None


def ble_names(config: dict[str, Any]) -> list[str]:
    """BLE 广播名：仅 project.ble_names 显式配置时改写，缺省不改源工程。"""
    value = project(config).get("ble_names")
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


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
