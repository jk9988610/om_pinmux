"""模块连带规则：把"改一处要连带改哪些文件"变成可执行审计。

规则清单是普通 Python 常量，不引入第二套 schema。strict=True 时错误计入
退出码（check --sdk）；GUI/gen 用 strict=False，只提示、不阻塞。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import model, validate
from .targets import sdk


@dataclass(frozen=True)
class Rule:
    id: str
    summary: str
    files: str
    level: str = "error"


RULES = (
    Rule("pins.macro", "角色宏值必须等于配置脚位", "user_config.h pins 块"),
    Rule("pins.gpio_table", "每个已分配角色必须出现在 GPIO 表", "user_config.c gpio_table"),
    Rule("pins.wake", "唤醒掩码与 EN/DIS 的角色集合必须一致", "user_config.h"),
    Rule("key_io.refs", "key_io 必须引用配置中的按键角色", "key_io.h / key_io.c"),
    Rule("led.polarity", "灯极性与 led_*_on() 的 gpio 操作一致", "user_config.h"),
    Rule("led.driver", "LEDC_SEL 驱动选择与灯脚提示", "ledc.c", "warning"),
    Rule("led.sleep", "sleep 断电列表必须覆盖灯脚", "user_config.c sleep 块"),
    Rule("dpi.table", "DPI 档位表与配置一致", "sensor.c", "warning"),
    Rule("dpi.persist", "DPI 持久化表存在且回退到出厂表", "flash_process.c", "warning"),
    Rule("dpi.default", "默认 DPI 档位与配置一致", "sensor.h", "warning"),
)

MARKERS = {
    "gpio_table": ("/* OMCFG BEGIN gpio_table */", "/* OMCFG END gpio_table */"),
    "sleep": ("/* OMCFG BEGIN sleep */", "/* OMCFG END sleep */"),
}

PIN_DEFINE_RE = re.compile(r"#define\s+([A-Z0-9_]+)\s*\(\s*(P\d{2})\s*\)")
TABLE_ROW_RE = re.compile(r"^\s*\{\s*([A-Z0-9_]+)\s*,", re.M)
WAKE_MASK_RE = re.compile(r"#define\s+PIN_WAKE_UP_MASK\s+(.*)")
WAKE_CALL_RE = re.compile(r"drv_pmu_wakeup_pin_set\s*\(\s*([A-Z0-9_]+)\s*,")
ROLE_REF_RE = re.compile(r"\b(KEY_[A-Z0-9_]+)\b")
KEY_MODE_USE_RE = re.compile(r"\bKEY_MODE_\w+\b")
# 从 key_io.h 的 "#define KEY_MODE_R7 (OM_GPIO0->DATA & (1<<KEY_DPI_PIN))" 解析映射
KEY_MODE_DEF_RE = re.compile(
    r"#define\s+(KEY_MODE_\w+)\s+[^\n]*?\(\s*1\s*<<\s*(KEY_[A-Z0-9_]+)\s*\)"
)

# 回退映射：key_io.h 不可解析时沿用（历史 CH04 口径）。
FALLBACK_KEY_MODE_TO_PIN = {
    "KEY_MODE_PAIR": "KEY_PAIR_PIN",
    "KEY_MODE_R0": "KEY_R0_PIN",
    "KEY_MODE_R1": "KEY_R1_PIN",
    "KEY_MODE_R2": "KEY_R2_PIN",
    "KEY_MODE_R3": "KEY_B_PIN",
    "KEY_MODE_R4": "KEY_P_PIN",
    "KEY_MODE_R5": "KEY_DPI_SUB_PIN",
    "KEY_MODE_R7": "KEY_DPI_ADD_PIN",
}


def _key_mode_map(key_io_h: str) -> dict[str, str]:
    """从 key_io.h 的宏定义推导 KEY_MODE_* → KEY_*_PIN。

    解析到任何一条就以解析结果为准（映射是工程事实，不能掺入别板的硬编码）；
    一条都解析不到时才回退到历史表，兼容没有 key_io.h 的最小测试桩。
    """
    mapping = {m.group(1): m.group(2) for m in KEY_MODE_DEF_RE.finditer(key_io_h)}
    return mapping if mapping else dict(FALLBACK_KEY_MODE_TO_PIN)


def active_key_mode_roles(root: Path | str, config: dict | None = None) -> set[str] | None:
    """工程源码里真正参与编译的 KEY_MODE_* 所对应的角色集合。

    key_io.h 里定义但未在 key_io.c 使用的宏不会展开，不能算“硬依赖”；
    这是 CH04 旧工程能被当前工具正确打开的关键。读不到源码时返回 None，
    调用方应保守沿用 options.json 的全局 build_required。
    """
    try:
        key_c = _read(root, "projects/mouse_demo/periph/key_io.c")
        key_h = _read(root, "projects/mouse_demo/periph/key_io.h")
    except (OSError, UnicodeError):
        return None
    if config and "KEY_PAIR_PIN" not in model.pin_entries(config):
        key_c = _strip_ifdef_block(key_c, "KEY_PAIR_PIN")
    mapping = _key_mode_map(key_h)
    return {
        mapping[mode]
        for mode in KEY_MODE_USE_RE.findall(key_c)
        if mode in mapping
    }
LED_ON_RE = re.compile(r"#define\s+led_r_on\(\)\s+\((gpio_set|gpio_clear)\(LED_MODE_R_PIN\)\)")
LEDC_SEL_RE = re.compile(r"drv_pmu_ledc_sel\s*\(\s*PMU_LEDC_SEL_IO_(\d{2})\s*\)")
DPI_INI_RE = re.compile(r"sensor_dpi_ini\s*\[\s*\]\s*=\s*\{([^}]*)\}", re.S)
DPI_DEFAULT_RE = re.compile(r"#define\s+DEFAULT_DPI_GRADE\s+(\d+)")
DPI_ENTRY_RE = re.compile(r"(\d+)L/200L-1")


def render_rules() -> str:
    lines = [f"{rule.id:<16}{rule.level:<8}{rule.files:<28}{rule.summary}" for rule in RULES]
    return "\n".join(lines)


def _read(root: Path, relative: Path | str) -> str:
    path = root / relative
    return sdk.read_source(path).text if path.is_file() else ""


def _block(text: str, name: str) -> str:
    begin, end = MARKERS[name]
    start = text.find(begin)
    stop = text.find(end)
    if start == -1 or stop == -1 or stop < start:
        return ""
    return text[start + len(begin) : stop]


def _macro_body(text: str, name: str) -> str:
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if re.match(rf"#define\s+{re.escape(name)}(?=\s)", line):
            body = [line]
            while body[-1].rstrip().endswith("\\") and index + len(body) < len(lines):
                body.append(lines[index + len(body)])
            return "\n".join(body)
    return ""


def _expected_table_roles(pins: dict[str, dict[str, str]]) -> list[str]:
    """模板按 GROUP_ORDER 每脚只输出首个角色；USB_DN/DP 不进表。"""
    roles: list[str] = []
    seen: set[str] = set()
    for _name, group in model.GROUP_ORDER:
        for role in group:
            if role not in pins or role in model.NO_GPIO_TABLE:
                continue
            pin = pins[role]["pin"]
            if pin in seen:
                continue
            seen.add(pin)
            roles.append(role)
    return roles


def _strip_ifdef_block(text: str, macro: str) -> str:
    """去掉 #ifdef <macro> ... #endif 块的内容（保留 #ifndef 块）。支持单层。

    用于 key_io.refs 规则：被 #ifdef KEY_PAIR_PIN 包裹的引用视为条件引用，
    当 pins 未配置 KEY_PAIR_PIN 时不应报"未定义"warning。
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    depth_ifdef = 0
    depth_ifndef = 0
    for line in lines:
        stripped = line.strip()
        m_ifdef = re.match(r"#ifdef\s+(\w+)\b", stripped)
        m_ifndef = re.match(r"#ifndef\s+(\w+)\b", stripped)
        if m_ifdef and m_ifdef.group(1) == macro:
            depth_ifdef += 1
            continue
        if m_ifndef and m_ifndef.group(1) == macro:
            depth_ifndef += 1
            out.append(line)
            continue
        if stripped == "#endif":
            if depth_ifndef > 0:
                depth_ifndef -= 1
                out.append(line)
                continue
            if depth_ifdef > 0:
                depth_ifdef -= 1
                continue
        if depth_ifdef == 0:
            out.append(line)
    return "".join(out)


def audit(config: dict, root: Path | str, strict: bool = False) -> validate.Report:
    root = Path(root)
    report = validate.Report()
    pins = model.resolved_pins(config)
    header = _read(root, sdk.USER_CONFIG_H)
    source_c = _read(root, sdk.USER_CONFIG_C)

    def add(rule_id: str, path: str, message: str, hint: str = "") -> None:
        rule = next((item for item in RULES if item.id == rule_id), None)
        level = "error" if rule is None else rule.level
        target = f"{rule_id}: {path}"
        if level == "warning" or not strict:
            report.add_warning(target, message, hint)
        else:
            report.add_error(target, message, hint)

    def warn(rule_id: str, path: str, message: str, hint: str = "") -> None:
        report.add_warning(f"{rule_id}: {path}", message, hint)

    def missing(rule_id: str, relative: Path, required: bool = False) -> bool:
        if (root / relative).is_file():
            return False
        message = f"审计跳过：缺少 {relative.as_posix()}"
        if required and strict:
            report.add_error(rule_id, message, "确认 SDK 副本完整；该文件是生成/编译前提")
        else:
            report.add_warning(rule_id, message)
        return True

    if missing("pins.macro", sdk.USER_CONFIG_H, True):
        return report

    macros = dict(PIN_DEFINE_RE.findall(header))
    for role, item in pins.items():
        if role not in macros:
            add(
                "pins.macro",
                f"pins.{role}",
                f"user_config.h 缺少 #define {role}",
                "重新执行 gen --apply",
            )
        elif macros[role] != item["pin"]:
            add(
                "pins.macro",
                f"pins.{role}",
                f"配置为 {item['pin']}，user_config.h 为 {macros[role]}",
                "说明修改绕过生成；执行 python -m omcfg gen --sdk <SDK> --apply",
            )

    if source_c:
        table = _block(source_c, "gpio_table")
        present = set(TABLE_ROW_RE.findall(table)) if table else set()
        if not table:
            add("pins.gpio_table", "gpio_table", "user_config.c 缺少 OMCFG gpio_table 块")
        else:
            for role in _expected_table_roles(pins):
                if role not in present:
                    add(
                        "pins.gpio_table",
                        f"pins.{role}",
                        f"GPIO 表漏掉 {role}（{pins[role]['pin']}）",
                        "gpio_config_table 与引脚宏必须成组更新；执行 gen --apply",
                    )

    expected_wake = set(model.wake_keys(config, pins)) | {"SENSOR_MOTION_PIN"}
    mask_match = WAKE_MASK_RE.search(header)
    if not mask_match:
        add("pins.wake", "PIN_WAKE_UP_MASK", "user_config.h 缺少 PIN_WAKE_UP_MASK")
    else:
        mask_roles = set(re.findall(r"\(1<<([A-Z0-9_]+)\)", mask_match.group(1)))
        if mask_roles != expected_wake:
            add(
                "pins.wake",
                "PIN_WAKE_UP_MASK",
                f"唤醒角色 {sorted(mask_roles)} 与配置 {sorted(expected_wake)} 不一致",
                "改脚位后必须同步唤醒掩码；执行 gen --apply",
            )
    for name in ("KEY_PIN_WAKE_UP_EN()", "KEY_PIN_WAKE_UP_DIS()"):
        body = _macro_body(header, name)
        if not body:
            add("pins.wake", name, f"user_config.h 缺少 {name}")
            continue
        roles = set(WAKE_CALL_RE.findall(body))
        if roles != expected_wake:
            add(
                "pins.wake",
                name,
                f"角色 {sorted(roles)} 与配置 {sorted(expected_wake)} 不一致",
                "唤醒注册/注销必须与 PIN_WAKE_UP_MASK 同一组角色",
            )

    key_io_h = _read(root, sdk.PERIPH / "key_io.h")
    key_io_c = _read(root, sdk.PERIPH / "key_io.c")
    if key_io_h or key_io_c:
        KEY_MODE_TO_PIN = _key_mode_map(key_io_h)
        key_io_c_effective = key_io_c
        if "KEY_PAIR_PIN" not in pins:
            key_io_c_effective = _strip_ifdef_block(key_io_c, "KEY_PAIR_PIN")
        used_modes = set(KEY_MODE_USE_RE.findall(key_io_c_effective))
        refs = {KEY_MODE_TO_PIN[m] for m in used_modes if m in KEY_MODE_TO_PIN}
        refs |= {role for role in ROLE_REF_RE.findall(key_io_c_effective) if role in model.ROLE_ORDER}
        configured = {role for role in pins if role.startswith("KEY_")}
        for role in sorted(configured - refs):
            add(
                "key_io.refs",
                f"pins.{role}",
                f"key_io 未引用 {role}，按键分组可能漏改",
                "确认 key_io.h/.c 的扫描与状态位是否覆盖该键",
            )
        for role in sorted(refs - configured):
            warn(
                "key_io.refs",
                f"pins.{role}",
                f"key_io 引用了未配置的 {role}（宏未定义时展开会编译失败）",
                "若该分支不使用可忽略；否则补配置或给 key_io 加 #ifdef",
            )
        if "KEY_C0_PIN" in refs and "KEY_C0_PIN" not in pins:
            add(
                "key_io.refs",
                "pins.KEY_C0_PIN",
                "key_io.c 无条件使用 KEY_C0_PIN，但配置已解除",
                "恢复 KEY_C0_PIN，或给矩阵列扫描加 #ifdef",
            )
        if "KEY_PAIR_PIN" not in pins and "#ifdef KEY_PAIR_PIN" not in key_io_h:
            add(
                "key_io.refs",
                "pins.KEY_PAIR_PIN",
                "配置无 KEY_PAIR_PIN，但 key_io.h 未用 #ifdef KEY_PAIR_PIN 保护，编译可能失败",
                "给 key_io.h/.c 的 PAIR 相关代码加 #ifdef KEY_PAIR_PIN",
            )

    polarity = model.board(config).get("led_polarity")
    on_match = LED_ON_RE.search(header)
    if on_match:
        expected_on = "gpio_set" if polarity == "active_high" else "gpio_clear"
        if on_match.group(1) != expected_on:
            add(
                "led.polarity",
                "board.led_polarity",
                f"配置 {polarity}，但 led_r_on() 使用 {on_match.group(1)}",
                "灯极性与驱动宏必须成组更新；执行 gen --apply",
            )
    else:
        add("led.polarity", "led_r_on()", "user_config.h 缺少 led_r_on() 宏")

    ledc_text = _read(root, sdk.PERIPH / "ledc.c")
    data_pin = pins.get("LEDC_PIN", {}).get("pin", "")
    sel = LEDC_SEL_RE.search(ledc_text) if ledc_text else None
    if sel and data_pin and sel.group(1) != data_pin[1:]:
        add(
            "led.driver",
            "pins.LEDC_PIN",
            f"ledc.c 写死 PMU_LEDC_SEL_IO_{sel.group(1)}，与 LEDC_PIN({data_pin}) 不对应",
            "LEDC 数据脚需手工改 ledc.c 并确认 PINMUX 解锁；本阶段只提示",
        )

    sleep_block = _block(source_c, "sleep") if source_c else ""
    if model.board(config).get("logo") == "ledc" and "LEDC_PIN" in pins:
        if "gpio_dir_in(LEDC_PIN)" not in sleep_block:
            add(
                "led.sleep",
                "sleep",
                "sleep 断电列表未把 LEDC_PIN 设为输入",
                "LOGO=LEDC 时休眠前需关闭 LEDC 数据脚；执行 gen --apply",
            )
        if "LED_LOW_PIN" in pins and "led_low_off()" not in sleep_block:
            add(
                "led.sleep",
                "sleep",
                "sleep 断电列表未关闭 LED_LOW_PIN",
                "补 led_low_off()，否则休眠漏电；执行 gen --apply",
            )

    levels = model.dpi_levels(config)
    sensor_c = _read(root, sdk.PERIPH / "sensor.c")
    if levels and sensor_c:
        ini = DPI_INI_RE.search(sensor_c)
        if not ini:
            add("dpi.table", "sensor_dpi_ini", "sensor.c 找不到 sensor_dpi_ini[]", "")
        else:
            decoded = [int(value) for value in DPI_ENTRY_RE.findall(ini.group(1))]
            if decoded[: len(levels)] != levels:
                add(
                    "dpi.table",
                    "board.sensor.dpi_levels",
                    f"配置 {levels}，sensor_dpi_ini 为 {decoded[: len(levels)]}",
                    "DPI 档位表与配置需同改；当前不生成 sensor.c，请手工同步",
                )

    flash_c = _read(root, Path("projects/mouse_demo/flash/flash_process.c"))
    if levels and flash_c:
        ok = (
            "dpi_value_tbl" in flash_c
            and "memcpy(dpi_value_tbl, sensor_dpi_ini, 8)" in flash_c
            and "memcpy(dat_temp+8, dpi_value_tbl, 8)" in flash_c
        )
        if not ok:
            add(
                "dpi.persist",
                "flash_process.c",
                "DPI 持久化链不完整（读取/出厂回退/写回三者缺一）",
                "确认 dpi_value_tbl 能持久化并回退到 sensor_dpi_ini",
            )

    sensor_h = _read(root, sdk.PERIPH / "sensor.h")
    default = model.dpi_default(config)
    if default is not None and sensor_h:
        match = DPI_DEFAULT_RE.search(sensor_h)
        if not match:
            add("dpi.default", "sensor.h", "找不到 DEFAULT_DPI_GRADE", "")
        elif int(match.group(1)) != default:
            add(
                "dpi.default",
                "board.sensor.dpi_default",
                f"配置档位 {default}，sensor.h 为 {match.group(1)}",
                "默认档位与配置需同改；当前不生成 sensor.h，请手工同步",
            )
    return report
