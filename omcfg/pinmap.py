"""按封装脚位组织引脚：芯片硬约束、可选功能、脚位行数据。

芯片事实来自 chip/om6239.json；配置用法与 validate 保持一致。
SCLK/SDIO/UART 在 SDK 里是软件 GPIO 位翻转，不受 alt 约束，只作界面提示。
"""

from __future__ import annotations

from typing import Any

from . import model


def _mux(chip: dict[str, Any]) -> dict[str, Any]:
    value = chip.get("mux") or {}
    return value if isinstance(value, dict) else {}


def internal_flash(chip: dict[str, Any] | None = None) -> dict[str, str]:
    chip = chip or model.load_chip()
    value = chip.get("internal_flash") or {}
    return {str(role): str(pin) for role, pin in value.items()} if isinstance(value, dict) else {}


def reserved_pins(chip: dict[str, Any] | None = None) -> set[str]:
    chip = chip or model.load_chip()
    value = chip.get("reserved_pins")
    if isinstance(value, list) and value:
        return {str(item) for item in value}
    return set(chip.get("internal_not_on_package", []))


def free_gpio(chip: dict[str, Any] | None = None) -> set[str]:
    """任意功能都能接的普通 GPIO：非 special、非保留、非 USB 专用脚。"""
    chip = chip or model.load_chip()
    usb = set(_mux(chip).get("USB", {}).get("fixed", {}).values())
    return (
        {
            str(item.get("name"))
            for item in chip.get("package_pins", [])
            if not item.get("special") and str(item.get("name", "")).startswith("P")
        }
        - reserved_pins(chip)
        - usb
    )


def _encoder_pin_set(chip: dict[str, Any]) -> set[str]:
    pins: set[str] = set()
    for item in _mux(chip).get("ENCODER", {}).get("sdk_macros", []):
        pins.update(str(pin) for pin in item.get("pins", []))
    return pins


def _ledc_pin_set(chip: dict[str, Any]) -> set[str]:
    pins: set[str] = set()
    for option in _mux(chip).get("LEDC_SEL", {}).get("options", []):
        if option.get("sdk_supported") is False:
            continue
        pins.update(str(pin) for pin in option.get("pins", []))
    return pins


def constraint_pins(chip: dict[str, Any] | None, role: str) -> set[str] | None:
    """角色的硬件/板型允许脚位；None 表示任意普通 GPIO。

    只含真正有硬件约束的功能，不把 SCLK/SDIO 的 alt 当约束。
    """
    chip = chip or model.load_chip()
    flash = internal_flash(chip)
    if role in flash:
        return {flash[role]}
    usb = _mux(chip).get("USB", {}).get("fixed", {})
    if role in usb:
        return {str(usb[role])}
    if role == "LVD_PIN":
        common = _mux(chip).get("LVD", {}).get("common_pins", [])
        return {str(pin) for pin in common} or None
    if role in ("WHEEL_A_PIN", "WHEEL_B_PIN"):
        return _encoder_pin_set(chip) or None
    if role == "LEDC_PIN":
        return _ledc_pin_set(chip) or None
    return None


def allowed_pins(chip: dict[str, Any] | None, role: str) -> set[str]:
    chip = chip or model.load_chip()
    constrained = constraint_pins(chip, role)
    return set(constrained) if constrained else free_gpio(chip)


def role_pin_problem(chip: dict[str, Any] | None, role: str, pin: str) -> str | None:
    """该脚是否具备该功能；合法返回 None，否则给出可操作提示。"""
    chip = chip or model.load_chip()
    pin = str(pin).strip()
    flash = internal_flash(chip)
    if role in flash:
        expected = flash[role]
        if pin != expected:
            return f"{role} 固定为 {expected}（片内 Flash），不能改到 {pin}"
        return None
    if pin in reserved_pins(chip):
        owners = [r for r, value in flash.items() if value == pin]
        if owners:
            return f"{pin} 是片内 Flash 保留脚，只允许 {owners[0]}"
        return f"{pin} 不在封装上（保留脚），不能分配功能"
    usb = _mux(chip).get("USB", {}).get("fixed", {})
    if role in usb and pin != str(usb[role]):
        return f"{role} 的 USB 固定脚必须是 {usb[role]}"
    if role not in usb and pin in {str(value) for value in usb.values()}:
        return f"{pin} 固定为 USB 差分脚，不能接 {role}"
    if role == "LVD_PIN":
        common = [str(item) for item in _mux(chip).get("LVD", {}).get("common_pins", [])]
        if common and pin not in common:
            return f"{pin} 不具备 LVD 功能（只能 {'/'.join(common)}）"
    if role == "LEDC_PIN":
        options = sorted(_ledc_pin_set(chip))
        if options and pin not in options:
            return f"{pin} 不具备 LEDC 功能（LEDC_SEL 只能 {'/'.join(options)}）"
    if role in ("WHEEL_A_PIN", "WHEEL_B_PIN"):
        options = sorted(_encoder_pin_set(chip))
        if options and pin not in options:
            return f"{pin} 不具备 ENCODER 功能，滚轮只能接四对之一：P00/P01、P05/P06、P20/P21、P24/P25"
    return None


def _assigned_by_pin(config: dict[str, Any]) -> dict[str, list[str]]:
    by_pin: dict[str, list[str]] = {}
    for role, item in model.pin_entries(config).items():
        by_pin.setdefault(item["pin"], []).append(role)
    return by_pin


def assignable_roles(chip: dict[str, Any] | None, config: dict[str, Any], pin: str) -> list[str]:
    """当前配置下可以放到该脚的角色：排除已被其它角色占用的脚。"""
    chip = chip or model.load_chip()
    by_pin = _assigned_by_pin(config)
    occupied = set(by_pin.get(pin, []))
    out: list[str] = []
    for role in model.ROLE_ORDER:
        allowed = allowed_pins(chip, role)
        if pin not in allowed:
            continue
        if occupied and role not in occupied:
            continue
        out.append(role)
    return out


def rows(config: dict[str, Any], chip: dict[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    """按封装脚位 1–32 生成界面行；片内/保留脚单列一组。"""
    chip = chip or model.load_chip()
    by_pin = _assigned_by_pin(config)
    fixed = chip.get("fixed_package") or {}
    package: list[dict[str, Any]] = []
    for item in sorted(chip.get("package_pins", []), key=lambda value: int(value.get("pkg", 0))):
        name = str(item.get("name", ""))
        special = bool(item.get("special"))
        assigned = [role for role in model.ROLE_ORDER if role in by_pin.get(name, [])]
        desc = ""
        if special:
            desc = str((fixed.get(name) or {}).get("desc", ""))
        candidates = [] if special else assignable_roles(chip, config, name)
        package.append(
            {
                "pkg": int(item.get("pkg", 0)),
                "name": name,
                "side": str(item.get("side", "")),
                "special": special,
                "reserved": False,
                "desc": desc,
                "assigned": assigned,
                "candidates": candidates,
                "locked": special or len(assigned) > 1,
            }
        )

    flash = internal_flash(chip)
    internal: list[dict[str, Any]] = []
    for pin in sorted(reserved_pins(chip), key=lambda value: (value[1:], value)):
        assigned = [role for role in model.ROLE_ORDER if role in by_pin.get(pin, [])]
        desc = "片内/非封装脚"
        owners = [role for role, value in flash.items() if value == pin]
        if owners:
            desc = f"片内 Flash 固定：{owners[0]}"
        internal.append(
            {
                "pkg": 0,
                "name": pin,
                "side": "internal",
                "special": False,
                "reserved": True,
                "desc": desc,
                "assigned": assigned,
                "candidates": [],
                "locked": True,
            }
        )

    assigned_all = {role for roles in by_pin.values() for role in roles}
    unassigned = [role for role in model.ROLE_ORDER if role not in assigned_all]
    return {"package": package, "internal": internal, "unassigned": unassigned}


def editable(config: dict[str, Any], chip: dict[str, Any] | None = None) -> dict[str, Any]:
    """GUI 需要的扁平信息：行 + 待分配 + 必需角色（只读原因由 validate 提供）。"""
    data = rows(config, chip)
    data["roles"] = list(model.ROLE_ORDER)
    return data
