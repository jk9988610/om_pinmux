"""空白起步：从选项逐步构建 project.omcfg 的纯数据操作。

与 generate/validate/transaction 分层一致：本模块只产出/修改配置对象，
不写文件、不生成代码。所有写盘仍走既有的 new/init/gen/transaction 链路。

设计：
- empty_config()   造一份“工程身份已定、pins 为空、board 为默认值”的草稿配置；
- assign()/unassign()  逐角色增删脚位，复用 pinmap 的芯片约束 + options.json 的成对/互斥；
- missing_roles()  列出当前 board 选项下还缺哪些必需角色（复用 validate.required_roles）；
- is_complete()    是否可交给 gen（无缺脚、无冲突）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import model, pinmap, validate

DATA_DIR = Path(__file__).resolve().parent / "data"
OPTIONS_PATH = DATA_DIR / "options.json"


def load_options() -> dict[str, dict[str, Any]]:
    """角色宏 -> 选项元数据（显示名/合法脚/推荐脚/成对/互斥）。"""
    if not OPTIONS_PATH.is_file():
        return {}
    data = json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
    return dict(data.get("options", {}))


def default_board() -> dict[str, Any]:
    """空白起步的默认板型：single 模式 + RGB + 3 线传感器 + 20/21 滚轮。

    这些是“可选项的默认值”，用户可在向导第一步改；与 KC536 基线一致，
    保证按推荐脚填完后能直接编译。
    """
    return {
        "mode_pins": "single",
        "logo": "rgb",
        "led_polarity": "active_low",
        "sensor": {"bus": "sdio_3wire", "dir_clock": 6},
        "wheel": "ENCODER_PINMUX_SEL_IO_20_21",
    }


def empty_config(name: str, customer: str = "BYC", version: int = 1) -> dict[str, Any]:
    """造一份引脚为空的草稿配置；项目身份来自参数，脚位留给选项逐步填。"""
    return {
        "schema": model.SCHEMA,
        "chip": model.CHIP_MODEL,
        "project": {
            "name": name,
            "customer": customer,
            "ble_names": [f"{name} Bt1", f"{name} Bt2"],
            "id": {"low": "0x0001", "high": "0x071", "version": version},
        },
        "board": default_board(),
        "pins": {},
        "codegen": {
            "output": "periph",
            "keil_project": "projects/mouse_demo/keil5/SE71M.uvprojx",
        },
    }


def _pin_of(config: dict[str, Any], role: str) -> str | None:
    value = config.get("pins", {}).get(role)
    if isinstance(value, dict):
        return str(value.get("pin")) if value.get("pin") else None
    return str(value) if value else None


def _by_pin(config: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for role in config.get("pins", {}):
        pin = _pin_of(config, role)
        if pin:
            out.setdefault(pin, []).append(role)
    return out


def assign_problem(config: dict[str, Any], role: str, pin: str) -> str | None:
    """把 role 放到 pin 是否合法；合法返回 None。复用芯片约束 + 选项关系。"""
    chip = model.load_chip()
    problem = pinmap.role_pin_problem(chip, role, pin)
    if problem:
        return problem
    # 同脚已被别的角色占用（LED 别名对除外）
    aliases = {
        frozenset(("LED_MODE_R_PIN", "LED_R_PIN")),
        frozenset(("LED_MODE_G_PIN", "LED_G_PIN")),
        frozenset(("LED_MODE_B_PIN", "LED_B_PIN")),
    }
    for other in _by_pin(config).get(pin, []):
        if other == role:
            continue
        if frozenset((other, role)) in aliases:
            continue
        return f"{pin} 已被 {other} 占用"
    # 成对角色：允许先放一个，build 完备性阶段会检查成对
    return None


def assign(config: dict[str, Any], role: str, pin: str) -> dict[str, Any]:
    """逐项构建一个引脚映射。会先看该角色在芯片上是否合法。"""
    problem = assign_problem(config, role, pin)
    if problem:
        raise ValueError(f"无法把 {role} 配到 {pin}: {problem}")
    config.setdefault("pins", {})[role] = pin
    return config


def unassign(config: dict[str, Any], role: str) -> dict[str, Any]:
    """解除某角色；必需角色允许解除（草稿态），完备性阶段再提示补齐。"""
    config.setdefault("pins", {}).pop(role, None)
    return config


def set_board_option(config: dict[str, Any], key: str, value: Any) -> dict[str, Any]:
    """设置板型选项（mode_pins / logo / sensor.bus / wheel 等）。"""
    board = config.setdefault("board", {})
    if key in ("sensor.bus", "sensor.dir_clock", "sensor"):
        sensor = board.setdefault("sensor", {})
        if key == "sensor":
            sensor.update(value or {})
        else:
            sensor[key.split(".", 1)[1]] = value
    else:
        board[key] = value
    return config


def build_required_roles() -> list[str]:
    """key_io 等软件侧硬依赖的角色：不配会编译失败（与板型无关的额外必需集）。"""
    return [mac for mac, opt in load_options().items() if opt.get("build_required")]


def missing_roles(config: dict[str, Any]) -> list[str]:
    """当前 board 选项下缺哪些必需角色。

    = validate 按板型推导的必需角色 ∪ options.json 标了 build_required 的软件硬依赖
    （如 KC536 的 key_io.h 无条件展开 KEY_B/P/DPI/PAIR）。
    """
    pins = model.pin_entries(config)
    required = list(validate.required_roles(config, pins))
    for role in build_required_roles():
        if role not in required:
            required.append(role)
    return [role for role in required if role not in pins]


def conflicts(config: dict[str, Any]) -> list[str]:
    """已分配脚里的冲突（不含缺脚，缺脚由 missing_roles 负责）。"""
    problems: list[str] = []
    chip = model.load_chip()
    for role in config.get("pins", {}):
        pin = _pin_of(config, role)
        if pin is None:
            continue
        problem = pinmap.role_pin_problem(chip, role, pin)
        if problem:
            problems.append(f"pins.{role}: {problem}")
    aliases = {
        frozenset(("LED_MODE_R_PIN", "LED_R_PIN")),
        frozenset(("LED_MODE_G_PIN", "LED_G_PIN")),
        frozenset(("LED_MODE_B_PIN", "LED_B_PIN")),
    }
    for pin, roles in _by_pin(config).items():
        if len(roles) > 1 and frozenset(roles) not in aliases:
            problems.append(f"{pin} 被重复分配: {', '.join(roles)}")
    return problems


def is_complete(config: dict[str, Any]) -> bool:
    """是否可交给 gen：必需脚齐、已分配脚无冲突。"""
    return not missing_roles(config) and not conflicts(config)


def summary(config: dict[str, Any]) -> dict[str, Any]:
    """给 GUI/CLI 展示的构建进度。"""
    opts = load_options()
    assigned = config.get("pins", {})
    return {
        "total_roles": len(opts),
        "assigned": len(assigned),
        "missing": missing_roles(config),
        "conflicts": conflicts(config),
        "complete": is_complete(config),
    }
