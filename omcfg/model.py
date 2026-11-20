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

# 逐脚极性：极性是每只灯/每个按键各自的电气属性，不是全板一个值。
# 命名沿用 user_config.h 里的真实宏（带 R/G/B），工程师按原理图逐只指定，
# 工具不按数量、不按统计、不按选料替他统一分配。
# 只列有独立极性语义的脚：模式灯 R/G/B/低电灯各有 led_*_on/off 宏，按键各有
# 有效电平。业务灯 LED_R/G/B 由业务代码直接操作（工具不生成其 on/off），旧版
# 24G/BT0/BT1 是 R/G/B 的别名（跟随主灯），都不放进可分配列表，避免界面承诺
# 一个改了不生效的选项。
# (宏名, 界面显示名, 是否 LED)
POLARITY_ROLES: list[tuple[str, str, bool]] = [
    ("LED_MODE_R_PIN", "模式灯 R", True),
    ("LED_MODE_G_PIN", "模式灯 G", True),
    ("LED_MODE_B_PIN", "模式灯 B", True),
    ("LED_LOW_PIN", "低电指示灯", True),
    ("KEY_R0_PIN", "按键 R0", False),
    ("KEY_R1_PIN", "按键 R1", False),
    ("KEY_R2_PIN", "按键 R2", False),
    ("KEY_B_PIN", "按键 B", False),
    ("KEY_P_PIN", "按键 P", False),
    ("KEY_DPI_PIN", "DPI 键", False),
    ("KEY_PAIR_PIN", "对码键", False),
    ("KEY_C0_PIN", "矩阵列 C0", False),
    ("KEY_DPI_SUB_PIN", "DPI 减键", False),
    ("KEY_DPI_ADD_PIN", "DPI 加键", False),
]
# 旧版模式灯别名：复用 R/G/B 物理脚，极性跟随主灯（生成时用，不给用户单独选）。
POLARITY_ALIAS_OF = {
    "LED_MODE_24G_PIN": "LED_MODE_R_PIN",
    "LED_MODE_BT1_PIN": "LED_MODE_G_PIN",
    "LED_MODE_BT0_PIN": "LED_MODE_B_PIN",
}
POLARITY_LED_NAMES = {name: display for name, display, is_led in POLARITY_ROLES if is_led}
POLARITY_KEY_NAMES = {name: display for name, display, is_led in POLARITY_ROLES if not is_led}
DIR_CLOCK_ENUM = {0, 3, 6, 9}
# 2.4G 指示灯复用哪只物理模式灯（R/G/B）：由硬件决定，默认 R 保 KC536 字节一致，
# S205 真机是 G（P05 绿灯）。别名脚极性跟随被指定的主灯。
MODE_24G_LED_ENUM = {"R", "G", "B"}
# 指示灯策略：KC536 骨架有两套点灯机制（底层 logo_cfg/ind_config 用 PWM 直接点灯，
# 与 mode_led_hint 的 GPIO 状态机打架）。hint_only 在编译期排除底层点灯调用，
# 只留 mode_led_hint 独占模式灯（S205 需求）；full 保留原版全部调用（KC536 默认，字节一致）。
LED_INDICATOR_ENUM = {"full", "hint_only"}
# 滚轮编码器硬件 pinmux；P24/P25 走 SOFT_GPIO 由用户按原理图自由配脚。
WHEEL_ENUM = {
    "ENCODER_PINMUX_SEL_IO_00_01",
    "ENCODER_PINMUX_SEL_IO_20_21",
    "SOFT_GPIO",
}


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
            if lines[index].lstrip().startswith(f"{role}:") and not lines[index].lstrip().startswith("#")
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
            if lines[index].lstrip().startswith(f"{role}:") and not lines[index].lstrip().startswith("#")
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


def _set_scalar(lines: list[str], start: int, stop: int, key: str, value: str) -> list[str] | None:
    """在 [start, stop) 行区间内改写/追加标量键，保留行尾注释；无改动返回 None。"""
    target = next(
        (
            index
            for index in range(start + 1, stop)
            if lines[index].lstrip().startswith(f"{key}:") and not lines[index].lstrip().startswith("#")
        ),
        None,
    )
    if target is None:
        # 子项缩进取区间内首个非空行，缺省用 2 空格。
        indent = next(
            (len(lines[i]) - len(lines[i].lstrip()) for i in range(start + 1, stop) if lines[i].strip()),
            2,
        )
        lines.insert(stop, f"{' ' * indent}{key}: {value}")
        return lines
    line = lines[target]
    prefix, rest = line.split(":", 1)
    tail = ""
    if "#" in rest:
        tail = " " + rest.split("#", 1)[1]
        tail = " #" + tail.lstrip()
    lines[target] = f"{prefix}: {value}{tail}"
    return lines


def set_board_value_text(text: str, key: str, value: str) -> str:
    """改写 board 段的标量值（wheel / sensor.dir_clock 等），保留行尾注释。

    支持点号形式的嵌套键 sensor.dir_clock（对应 board.sensor.dir_clock）：
    在 board 段的 sensor 子块内改写/追加 dir_clock；sensor 子块不存在时新建。
    """
    lines = text.split("\n")
    start, stop, child = _block_lines(lines, "board")
    if "." in key:
        parent, leaf = key.split(".", 1)
        sensor_start = next(
            (
                index
                for index in range(start + 1, stop)
                if lines[index].lstrip().startswith(f"{parent}:") and not lines[index].lstrip().startswith("#")
            ),
            None,
        )
        if sensor_start is None:
            # 在 board 段末尾新建 sensor 子块。
            lines[stop:stop] = [f"{' ' * child}{parent}:", f"{' ' * (child + 2)}{leaf}: {value}"]
            return "\n".join(lines)
        parent_indent = len(lines[sensor_start]) - len(lines[sensor_start].lstrip())
        sensor_stop = stop
        for index in range(sensor_start + 1, stop):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip()) <= parent_indent:
                sensor_stop = index
                break
        result = _set_scalar(lines, sensor_start, sensor_stop, leaf, value)
        return "\n".join(result or lines)
    result = _set_scalar(lines, start, stop, key, value)
    return "\n".join(result or lines)


def _drop_block_list_items(
    lines: list[str], key: str, start: int, stop: int
) -> tuple[list[str], int]:
    """删除 block list 形式的 `key:` 后面那些缩进更深的 '- ' 项，返回 (新行, 新 stop)。

    YAML 里 ble_names 有两种写法：行内 `[a, b]` 或块列表：
        ble_names:
          - Draft Bt1
          - Draft Bt2
    _set_scalar 把 `ble_names:` 改成行内列表时若不删掉旧的 '- ' 项，残留项会
    破坏缩进结构，load_config_text 解析失败。标量字段（customer）无后续列表项，
    本函数对其无副作用。
    """
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
        return lines, stop
    after = lines[target].split(":", 1)[1].strip()
    if after and not after.startswith("#"):
        return lines, stop  # 已有行内值，不是块列表
    base_indent = len(lines[target]) - len(lines[target].lstrip())
    drop: set[int] = set()
    for index in range(target + 1, stop):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.lstrip()
        # YAML 允许块列表的 '- ' 与父键同缩进（omcfg 的 dump_config 就是 2/2）。
        if indent >= base_indent and stripped.startswith("- "):
            drop.add(index)
        elif indent <= base_indent:
            break  # 同级的新键（如 id:）或更深的非列表内容，停止
        else:
            break
    if not drop:
        return lines, stop
    return [line for i, line in enumerate(lines) if i not in drop], stop - len(drop)


def set_project_field_text(text: str, key: str, value: str) -> str:
    """改写 project 段的标量/列表字段（customer / ble_names），保留行尾注释。
    ble_names 传入已格式化的 YAML 列表字面量，如 '["S205-BLE"]'。
    原值是块列表时先清掉旧 '- ' 项，避免残留破坏 YAML 结构。"""
    lines = text.split("\n")
    try:
        start, stop, _child = _block_lines(lines, "project")
    except ValueError:
        return text
    lines, stop = _drop_block_list_items(lines, key, start, stop)
    result = _set_scalar(lines, start, stop, key, value)
    return "\n".join(result or lines)


def set_polarity_value_text(text: str, role: str, value: str) -> str:
    """在文本配置里设置逐脚极性（保留注释/排版）。

    polarity 段不存在时新建在 board 段之后；值为空则删除该角色的极性行，
    让该脚回退到兼容默认。值必须是 POLARITY_ENUM，否则原样返回。
    """
    if value and value not in POLARITY_ENUM:
        return text
    lines = text.split("\n")
    try:
        start, stop, child = _block_lines(lines, "polarity")
    except ValueError:
        if not value:
            return text
        # 在 board 段之后插入新的 polarity 段（保持顶层段顺序紧凑）。
        try:
            _bstart, bstop, _bchild = _block_lines(lines, "board")
        except ValueError:
            bstop = len(lines)
        lines[bstop:bstop] = ["polarity:", f"  {role}: {value}"]
        return "\n".join(lines)
    target = _role_line(lines, role, start, stop)
    if value:
        if target is None:
            lines.insert(stop, f"{' ' * child}{role}: {value}")
        else:
            prefix = lines[target].split(":", 1)[0]
            lines[target] = f"{prefix}: {value}"
    elif target is not None:
        del lines[target]
        # 删空后整段移除，避免留下解析为 None 的空 polarity 段。
        start, stop, _child = _block_lines(lines, "polarity")
        if not any(line.strip() and not line.lstrip().startswith("#") for line in lines[start + 1 : stop]):
            del lines[start:stop]
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


def mode_24g_led(config: dict[str, Any]) -> str:
    """2.4G 指示灯复用的物理模式灯：R/G/B，缺省 R（KC536 基线字节不变）。"""
    value = str(board(config).get("mode_24g_led") or "R").upper()
    return value if value in MODE_24G_LED_ENUM else "R"


def led_indicator(config: dict[str, Any]) -> str:
    """指示灯策略：full=原版两套点灯机制；hint_only=只留 mode_led_hint。
    缺省 full 保证 KC536 基线字节不变。"""
    value = str(board(config).get("led_indicator") or "full").lower()
    return value if value in LED_INDICATOR_ENUM else "full"


def mode_24g_main_role(config: dict[str, Any]) -> str:
    return f"LED_MODE_{mode_24g_led(config)}_PIN"


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


def set_project_id_version_text(text: str, version: int) -> str:
    """改写 project.id.version 标量（保留行尾注释）；project.id 段不存在则原样返回。

    version 必须是正整数——它是固件版本真相源，生成时由 version 模块 +1 后写回。
    """
    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        return text
    lines = text.split("\n")
    try:
        start, stop, _child = _block_lines(lines, "project")
    except ValueError:
        return text
    id_start = next(
        (
            index
            for index in range(start + 1, stop)
            if lines[index].lstrip().startswith("id:") and not lines[index].lstrip().startswith("#")
        ),
        None,
    )
    if id_start is None:
        return text
    id_indent = len(lines[id_start]) - len(lines[id_start].lstrip())
    id_stop = stop
    for index in range(id_start + 1, stop):
        line = lines[index]
        if not line.strip():
            continue
        if len(line) - len(line.lstrip()) <= id_indent:
            id_stop = index
            break
    result = _set_scalar(lines, id_start, id_stop, "version", str(version))
    return "\n".join(result or lines)


def features(config: dict[str, Any], pins: dict[str, dict[str, str]] | None = None) -> dict[str, bool]:
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
        "BOARD_LED_ACTIVE_HIGH": role_polarity(config, "LED_MODE_R_PIN") == "active_high",
        "BOARD_LED_ACTIVE_LOW": role_polarity(config, "LED_MODE_R_PIN") == "active_low",
        "BOARD_WHEEL_SOFT_GPIO": b.get("wheel") == "SOFT_GPIO",
        # 物料参数投影：拨杆段数 / 蓝牙通道 / mode 键 / RGB 数量极性。
        "BOARD_SWITCH_SEGMENTS_2": switch_segments(config) == 2,
        "BOARD_SWITCH_SEGMENTS_3": switch_segments(config) == 3,
        "BOARD_BLE_CHANNELS_1": ble_channels(config) == 1,
        "BOARD_BLE_CHANNELS_2": ble_channels(config) == 2,
        "BOARD_HAS_MODE_KEY": mode_key_present(config),
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


def switch_segments(config: dict[str, Any]) -> int:
    """模式拨杆段数：2=开/关，3=2.4G/BAT/蓝牙。缺省 3。"""
    try:
        return int(board(config).get("switch_segments", 3))
    except (TypeError, ValueError):
        return 3


def ble_channels(config: dict[str, Any]) -> int:
    """蓝牙通道数，缺省 2。"""
    try:
        return int(board(config).get("ble_channels", 2))
    except (TypeError, ValueError):
        return 2


def mode_key_present(config: dict[str, Any]) -> bool:
    """是否有 mode 键（程序 pair 键）：选料显式关闭时以 project.materials 为准。"""
    store = project(config).get("materials") or {}
    params = store.get("params") if isinstance(store, dict) else None
    if isinstance(params, dict) and "mode_key" in params:
        return bool(params["mode_key"])
    # 未选料的老工程：以 pin 是否配置为准。
    return "KEY_PAIR_PIN" in pin_entries(config)


def polarity_map(config: dict[str, Any]) -> dict[str, str]:
    """逐脚极性表，键是 user_config.h 的真实宏名。非法值直接忽略。"""
    value = config.get("polarity") or {}
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items() if str(v) in POLARITY_ENUM}


def role_polarity(config: dict[str, Any], role: str) -> str:
    """某只灯/按键的极性；没有显式设置时按角色类型回退到兼容默认。

    LED 逐脚默认沿用旧 board.led_polarity（老工程字节不变），按键逐脚默认
    active_low（上拉、按下为低，与 KC536 基线一致）。一旦工程师在界面为某只脚
    选过极性，就以 config.polarity 为准，不受全局值/数量/选料影响。
    """
    explicit = polarity_map(config).get(role)
    if explicit in POLARITY_ENUM:
        return explicit
    # 旧版别名脚没有独立极性：跟随其主模式灯。
    # 24G 复用哪只灯由 board.mode_24g_led 决定（KC536=R，S205=G），不能写死 R。
    main = mode_24g_main_role(config) if role == "LED_MODE_24G_PIN" else POLARITY_ALIAS_OF.get(role)
    if main:
        main_explicit = polarity_map(config).get(main)
        if main_explicit in POLARITY_ENUM:
            return main_explicit
        legacy = board(config).get("led_polarity")
        return legacy if legacy in POLARITY_ENUM else "active_low"
    if role in POLARITY_LED_NAMES:
        legacy = board(config).get("led_polarity")
        if legacy in POLARITY_ENUM:
            return legacy
    return "active_low"


def active_polarity_roles(
    config: dict[str, Any], pins: dict[str, dict[str, str]] | None = None
) -> list[tuple[str, str, bool]]:
    """当前工程里实际存在（已配脚）的可配极性角色，按 POLARITY_ROLES 顺序。

    没配脚的角色不列出——极性面板“根据数量”生成：板上有几只脚就列几行。
    """
    pins = pins if pins is not None else pin_entries(config)
    return [(name, display, is_led) for name, display, is_led in POLARITY_ROLES if name in pins]


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
