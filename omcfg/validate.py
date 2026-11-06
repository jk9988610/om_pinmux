"""配置校验：规则只读 chip/om6239.json 与 .omcfg，不读旧 boards/。"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import model


@dataclass
class Issue:
    level: str
    path: str
    message: str
    hint: str = ""

    def render(self) -> str:
        text = f"[{self.level.upper()}] {self.path}: {self.message}"
        if self.hint:
            text += f"\n        提示: {self.hint}"
        return text


@dataclass
class Report:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    derived: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add_error(self, path: str, message: str, hint: str = "") -> None:
        self.errors.append(Issue("error", path, message, hint))

    def add_warning(self, path: str, message: str, hint: str = "") -> None:
        self.warnings.append(Issue("warning", path, message, hint))


def _chip_pins(chip: dict) -> set[str]:
    names = {
        item["name"]
        for item in chip.get("package_pins", [])
        if not item.get("special") and str(item.get("name", "")).startswith("P")
    }
    return names | set(chip.get("internal_not_on_package", []))


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            return None
    return None


def _required_roles(config: dict, pins: dict) -> list[str]:
    required = [
        "KEY_R0_PIN",
        "KEY_R1_PIN",
        "KEY_R2_PIN",
        "WHEEL_A_PIN",
        "WHEEL_B_PIN",
        "SENSOR_MOTION_PIN",
        "SENSOR_SCLK_PIN",
        "LED_MODE_R_PIN",
        "LED_MODE_G_PIN",
        "LED_MODE_B_PIN",
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
    b = model.board(config)
    if b.get("mode_pins") == "dual":
        required += ["MODE_24G_PIN", "MODE_BLE_PIN"]
    elif b.get("mode_pins") == "single":
        required += ["MODE_BLE_24G_PIN"]
    if b.get("logo") == "rgb":
        required += ["LED_R_PIN", "LED_G_PIN", "LED_B_PIN"]
    elif b.get("logo") == "ledc":
        required += ["LEDC_CTRL_PIN", "LEDC_PIN"]
    if model.sensor(config).get("bus") == "spi_4wire":
        required += ["SENSOR_NCS_PIN", "SENSOR_MOSI_PIN", "SENSOR_MISO_PIN"]
    else:
        required += ["SENSOR_SDIO_PIN"]
    return required


def validate_config(config: dict, chip: dict | None = None) -> Report:
    report = Report()
    chip = chip or model.load_chip()

    if not isinstance(config, dict):
        report.add_error("$", "配置文件顶层必须是映射")
        return report

    if config.get("schema") != model.SCHEMA:
        report.add_error("schema", f"必须为 {model.SCHEMA!r}")
    if config.get("chip") != model.CHIP_MODEL:
        report.add_error("chip", f"必须为 {model.CHIP_MODEL!r}")

    for key in sorted(model.FORBIDDEN_TOP_KEYS & set(config)):
        report.add_error(
            key, "派生字段不允许写进配置，应由 pins/board 计算", "删除该字段，生成器会自动派生"
        )
    b = model.board(config)
    for key in b:
        if str(key).startswith("BOARD_") or str(key).startswith("has"):
            report.add_error(f"board.{key}", "派生字段不允许写进配置，应由 pins 计算")
    for key in ("projName", "projIdL", "projIdH", "verId", "consumerName"):
        if key in model.project(config):
            report.add_error(f"project.{key}", "旧字段名已废弃，请用 project.name/customer/id")

    proj = model.project(config)
    if not str(proj.get("name") or "").strip():
        report.add_error(
            "project.name", "不能为空", "补 project.name（如 KC536），可对照 configs/*.omcfg"
        )
    if not str(proj.get("customer") or "").strip():
        report.add_error(
            "project.customer", "不能为空", "补 project.customer（如 BYC），可对照 configs/*.omcfg"
        )
    if "ble_names" in proj:
        names = proj.get("ble_names")
        if not isinstance(names, list) or not 1 <= len(names) <= 2:
            report.add_error(
                "project.ble_names",
                "必须是 1~2 个字符串的列表",
                "例如 ble_names: [\"BT5.1Mouse\"]；BT0/BT1 两个广播名各占一项",
            )
        else:
            for index, name in enumerate(names):
                text = str(name)
                if not text.strip():
                    report.add_error(f"project.ble_names[{index}]", "不能为空")
                elif len(text) > 28:
                    report.add_error(
                        f"project.ble_names[{index}]",
                        "超过 MOUSE_NAME_MAX_LEN-1（28 字符），会被截断",
                    )
                elif '"' in text or "\\" in text or "\n" in text:
                    report.add_error(
                        f"project.ble_names[{index}]",
                        "不能包含双引号、反斜杠或换行（会破坏 C 字符串）",
                    )
    pid = model.project_id(config)
    for key, maximum in (("low", 0xFFFF), ("high", 0xFFFF), ("version", 0x7F)):
        number = _as_int(pid.get(key))
        if number is None:
            report.add_error(f"project.id.{key}", "必须是整数或 0x 前缀字符串")
        elif not 1 <= number <= maximum:
            report.add_error(f"project.id.{key}", f"超出范围 1..{maximum}")
    if not str(pid.get("high")) or not str(pid.get("low")):
        report.add_error("project.id", "high/low 不能为空")

    mode = b.get("mode_pins")
    if mode not in model.MODE_ENUM:
        report.add_error("board.mode_pins", f"只允许 {sorted(model.MODE_ENUM)}")
    if b.get("logo") not in model.LOGO_ENUM:
        report.add_error("board.logo", f"只允许 {sorted(model.LOGO_ENUM)}")
    if b.get("ledc_rgb_number") is not None:
        number = _as_int(b.get("ledc_rgb_number"))
        if number is None or not 1 <= number <= 64:
            report.add_error("board.ledc_rgb_number", "必须是 1..64 的整数")
    if b.get("led_polarity") not in model.POLARITY_ENUM:
        report.add_error("board.led_polarity", f"只允许 {sorted(model.POLARITY_ENUM)}")
    wheel = str(b.get("wheel") or "")
    if not wheel:
        report.add_error("board.wheel", "必须指定编码器宏或 SOFT_GPIO")
    sens = model.sensor(config)
    if sens.get("bus") not in model.BUS_ENUM:
        report.add_error("board.sensor.bus", f"只允许 {sorted(model.BUS_ENUM)}")
    if sens.get("dir_clock") not in model.DIR_CLOCK_ENUM:
        report.add_error("board.sensor.dir_clock", "只允许 0/3/6/9")
    if "v2_en" in sens and not isinstance(sens.get("v2_en"), bool):
        report.add_error("board.sensor.v2_en", "必须是布尔值")

    pins = model.pin_entries(config)
    if not pins:
        report.add_error("pins", "至少需要一个引脚")
    allowed_pins = _chip_pins(chip)
    known_roles = set(model.ROLE_ORDER)
    for role, item in pins.items():
        if role not in known_roles:
            report.add_error(f"pins.{role}", "未知的功能宏名")
        if item["pin"] not in allowed_pins:
            report.add_error(f"pins.{role}.pin", f"{item['pin']} 不在 OM6239 可用 GPIO 列表")
        for name, value, valid in (
            ("mode", item["mode"], model.GPIO_MODES),
            ("pull", item["pull"], model.GPIO_PULLS),
            ("init", item["init"], model.GPIO_INITS),
        ):
            if value and value not in valid:
                report.add_error(f"pins.{role}.gpio.{name}", f"只允许 {sorted(valid)}")

    uart = b.get("uart_pin")
    if uart is not None:
        if uart not in ("KEY_R0_PIN", "KEY_R1_PIN", "KEY_R2_PIN", "KEY_PAIR_PIN"):
            report.add_error("board.uart_pin", "只允许复用 KEY_R0/R1/R2/PAIR")
        elif uart not in pins:
            report.add_error("board.uart_pin", "该引脚未在 pins 中分配")

    by_pin: dict[str, list[str]] = {}
    for role, item in pins.items():
        by_pin.setdefault(item["pin"], []).append(role)
    led_aliases = {
        frozenset(("LED_MODE_R_PIN", "LED_R_PIN")),
        frozenset(("LED_MODE_G_PIN", "LED_G_PIN")),
        frozenset(("LED_MODE_B_PIN", "LED_B_PIN")),
    }
    for pin, roles in by_pin.items():
        if len(roles) > 1 and frozenset(roles) not in led_aliases:
            report.add_error(
                "pins", f"{pin} 被重复分配: {', '.join(roles)}", "一个封装脚只能有一个功能"
            )

    for role in _required_roles(config, pins):
        if role not in pins:
            report.add_error(f"pins.{role}", "当前板型需要该引脚")

    usb = chip.get("mux", {}).get("USB", {}).get("fixed", {})
    for role, expected in usb.items():
        if role in pins and pins[role]["pin"] != expected:
            report.add_error(f"pins.{role}", f"USB 固定脚必须是 {expected}")

    lvd_pins = set(chip.get("mux", {}).get("LVD", {}).get("common_pins", []))
    if "LVD_PIN" in pins and lvd_pins and pins["LVD_PIN"]["pin"] not in lvd_pins:
        report.add_error("pins.LVD_PIN", f"LVD 只能接 {sorted(lvd_pins)}")

    encoder_macros = chip.get("mux", {}).get("ENCODER", {}).get("sdk_macros", [])
    if wheel and wheel != "SOFT_GPIO":
        matched = next(
            (
                m
                for m in encoder_macros
                if set(m.get("pins", []))
                == {pins.get("WHEEL_A_PIN", {}).get("pin"), pins.get("WHEEL_B_PIN", {}).get("pin")}
            ),
            None,
        )
        if matched is None:
            report.add_error("board.wheel", "WHEEL_A/B 与任何 ENCODER 引脚对都不匹配")
        elif matched["macro"] != wheel:
            report.add_error("board.wheel", f"应为 {matched['macro']}（由 WHEEL_A/B 推导）")

    if b.get("logo") == "ledc":
        ledc_pins: set[str] = set()
        for option in chip.get("mux", {}).get("LEDC_SEL", {}).get("options", []):
            ledc_pins.update(option.get("pins", []))
        ctrl = pins.get("LEDC_CTRL_PIN", {}).get("pin")
        if ctrl and ledc_pins and ctrl not in ledc_pins:
            report.add_error("pins.LEDC_CTRL_PIN", f"LEDC_SEL 只能选 {sorted(ledc_pins)}")

    if "KEY_PAIR_PIN" not in pins:
        report.add_warning(
            "pins.KEY_PAIR_PIN",
            "当前 key_io.h 无条件引用 KEY_PAIR_PIN；编译前需 P2 的 key_io 契约或手工包 #ifdef",
        )

    report.derived = {
        "features": model.features(config, pins),
        "PIN_WAKE_UP_MASK": model.wake_keys(config, pins),
        "LVD_CHECK_INDEX": model.lvd_index(config, pins),
        "WHEEL_IO_SELECT": model.wheel_select(config),
        "mode_pins": model.mode_pins(config, pins),
    }
    return report


def render_report(report: Report) -> str:
    lines = [issue.render() for issue in report.errors + report.warnings]
    if not lines:
        lines = ["OK: 配置校验通过"]
    return "\n".join(lines)


def summary(config: dict, report: Report) -> str:
    pins = model.pin_entries(config)
    features = report.derived.get("features", {})
    active = [name for name, value in features.items() if value]
    return (
        f"配置: {model.project(config).get('name', '')}  "
        f"引脚: {len(pins)}  "
        f"features: {len(active)}  "
        f"errors: {len(report.errors)}  warnings: {len(report.warnings)}"
    )
