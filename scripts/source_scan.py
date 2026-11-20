"""Scan BYKC firmware source for pin macros, polarity and material-relevant params.

Primary source: ``projects/mouse_demo/periph/user_config.h``
Secondary:      ``projects/mouse_demo/config/RTE_om6239.h`` (RTE_* switches)
Cross-check:    ``projects/mouse_demo/periph/sensor_type_check.h`` (sensor enums)

Extracts:
  - macros:        MACRO -> pin (Pnn) or alias string
  - active/enabled flags (whether a #define is commented out)
  - led polarity:  "active_low" when led_<x>_on() uses gpio_clear, else "active_high"
  - ledc:          enabled flag + RGB count
  - sensor:        model type constants present; wire count (2 vs 4) inferred
  - mode keys:     MODE_24G/MODE_BLE/MODE_WIRED, pair/mode key presence
  - encoder:       WHEEL_A/B or H_ENCODER_A/B pins
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["scan_build", "find_builds", "choose_latest"]

_DEFINE = re.compile(r"^\s*(//\s*)?#define\s+([A-Za-z_][\w()]*)\s*(.*?)\s*$")
_PIN = re.compile(r"\(?\bP(\d{2})\b\)?")
_NUMBER = re.compile(r"\b(\d+)\b")

# Sensor type constant -> model name (from sensor_type_check.h comments)
_SENSOR_MODELS = {
    "iSENSOR_TYPE_S201B": "S201B",
    "iSENSOR_TYPE_KA8": "KA8",
    "iSENSOR_TYPE_KA5857": "KA5857",
    "iSENSOR_TYPE_3205_TJ3T": "PAN3205_TJ3T",
    "iSENSOR_TYPE_3205_TJNT": "PAN3205_TJNT",
    "iSENSOR_TYPE_YS8008": "YS8008",
    "iSENSOR_TYPE_MX8650A": "MX8650A",
    "iSENSOR_TYPE_S203": "S203",
    "iSENSOR_TYPE_KA8G2": "KA8G2",
    "iSENSOR_TYPE_S205": "S205",
    "iSENSOR_TYPE_OM18": "OM18",
    "iSENSOR_TYPE_SG8912": "SG8912",
}

# Two-wire sensors expose only SDIO (no SPI clock); four-wire expose SCLK+NCS.
_FOUR_WIRE_MACROS = ("SENSOR_SCLK_PIN", "SENSOR_NCS_PIN")


def find_builds(root: str | Path) -> list[Path]:
    """Return dirs that contain a mouse_demo/periph/user_config.h."""
    root = Path(root)
    return sorted({p.parent.parent.parent.parent for p in root.rglob("user_config.h")})


def _ver_date(path: Path) -> tuple:
    """Sort key from directory names like SE71M_0512_S205_V1_20261017.

    Duplicate "- 副本"/"copy" dirs are deprioritized so the canonical build wins.
    """
    text = str(path)
    ver = re.search(r"[_-]V(\d+)", text, re.I)
    date = re.search(r"[_-](20\d{6})", text)
    is_copy = bool(re.search(r"副本|copy|backup|\(2\)", text, re.I))
    return (
        int(date.group(1)) if date else 0,
        int(ver.group(1)) if ver else 0,
        not is_copy,  # canonical -> True (wins); copy -> False (loses)
        text,
    )


def choose_latest(builds: list[Path]) -> Path | None:
    """Pick the most recent build dir by V/date encoded in the path."""
    if not builds:
        return None
    return max(builds, key=_ver_date)


def parse_defines(path: Path) -> dict:
    """Parse #define lines into {macro: (value, active)}; keep comments flag."""
    out: dict[str, tuple[str, bool]] = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        m = _DEFINE.match(line)
        if not m:
            continue
        commented, macro, value = m.groups()
        value = value.split("/*")[0].strip()
        # a #define inside a //{ ... //} block indented with spaces is still active;
        # only a leading // immediately before #define means disabled.
        active = not bool(commented)
        out[macro] = (value, active)
    return out


def _pin_of(value: str) -> str | None:
    m = _PIN.search(value)
    return f"P{m.group(1)}" if m else None


def _resolve(macros: dict, macro: str, seen=None) -> str | None:
    """Resolve a macro value to a pin, following aliases like LED_R_PIN -> LED_MODE_R_PIN."""
    seen = seen or set()
    if macro not in macros or macro in seen:
        return None
    seen.add(macro)
    value, active = macros[macro]
    if not active:
        return None
    pin = _pin_of(value)
    if pin:
        return pin
    # alias: value is another macro name
    alias = value.strip().lstrip("(").rstrip(")")
    if re.match(r"^[A-Za-z_]\w*$", alias):
        return _resolve(macros, alias, seen)
    return None


def _polarity(macros: dict, color: str) -> str | None:
    """active_low if led_<color>_on() calls gpio_clear, active_high if gpio_set."""
    value, active = macros.get(f"led_{color}_on()", ("", False))
    if not active or not value:
        return None
    m = re.search(r"gpio_(set|clear)\s*\(", value, re.I)
    if not m:
        return None
    return "active_low" if m.group(1).lower() == "clear" else "active_high"


def scan_build(build_dir: str | Path) -> dict:
    """Scan one build directory; returns a normalized project record fragment."""
    build_dir = Path(build_dir)
    uc = build_dir / "projects/mouse_demo/periph/user_config.h"
    rte = build_dir / "projects/mouse_demo/config/RTE_om6239.h"
    stc = build_dir / "projects/mouse_demo/periph/sensor_type_check.h"

    result: dict = {
        "build_dir": str(build_dir).replace("\\", "/"),
        "macros": {},
        "pins": {},
        "polarity": {},
        "ledc": {"enabled": False, "rgb_count": None},
        "sensor": {"models": [], "wire": None},
        "mode": {"modes": [], "pair_key": None},
        "encoder": {},
        "sources": {},
    }
    if not uc.is_file():
        return result
    result["sources"]["user_config"] = str(uc).replace("\\", "/")

    macros = parse_defines(uc)
    result["macros"] = {k: v[0] for k, v in macros.items()}

    # pin map: only active macros that resolve to a physical pin
    pin_macro_groups = [
        "KEY_R0_PIN", "KEY_R1_PIN", "KEY_R2_PIN", "KEY_B_PIN", "KEY_P_PIN",
        "KEY_DPI_PIN", "KEY_PAIR_PIN", "KEY_L_PIN", "KEY_M_PIN", "KEY_R_PIN",
        "WHEEL_A_PIN", "WHEEL_B_PIN", "H_ENCODER_A_PIN", "H_ENCODER_B_PIN",
        "SENSOR_NCS_PIN", "SENSOR_SCLK_PIN", "SENSOR_SDIO_PIN",
        "SENSOR_MOSI_PIN", "SENSOR_MISO_PIN", "SENSOR_MOTION_PIN",
        "MODE_24G_PIN", "MODE_BLE_PIN", "MODE_WIRED_PIN", "MODE_BLE_24G_PIN",
        "LED_MODE_R_PIN", "LED_MODE_G_PIN", "LED_MODE_B_PIN",
        "LED_MODE_24G_PIN", "LED_MODE_BT0_PIN", "LED_MODE_BT1_PIN",
        "LED_R_PIN", "LED_G_PIN", "LED_B_PIN", "LED_LOW_PIN", "LED_CHG_PIN",
        "LEDC_PIN", "LEDC_CTRL_PIN", "USB_5V", "BAT_CHG_PIN",
        "LVD_PIN", "POWER_ON_PIN", "USB_5V_CHECK_PIN",
    ]
    for mac in pin_macro_groups:
        pin = _resolve(macros, mac)
        if pin:
            result["pins"][mac] = pin

    # RGB polarity (from led_r/g/b_on)
    for color in ("r", "g", "b"):
        pol = _polarity(macros, color)
        if pol:
            result["polarity"][f"led_{color}"] = pol

    # LEDC enable + RGB count
    if rte.is_file():
        rte_macros = parse_defines(rte)
        result["sources"]["rte"] = str(rte).replace("\\", "/")
        enable, active = rte_macros.get("RTE_LEDC", ("0", False))
        result["ledc"]["enabled"] = active and enable.strip() != "0"
    # some projects define RTE_LEDC inside user_config
    if "RTE_LEDC" in macros:
        v, a = macros["RTE_LEDC"]
        result["ledc"]["enabled"] = a and v.strip() != "0"
    if "LEDC_RGB_NUMBER" in macros:
        v, a = macros["LEDC_RGB_NUMBER"]
        if a:
            m = _NUMBER.search(v)
            if m:
                result["ledc"]["rgb_count"] = int(m.group(1))

    # Sensor model / wire count
    sensor_text = ""
    if stc.is_file():
        sensor_text = stc.read_text(encoding="utf-8", errors="replace")
        result["sources"]["sensor_type"] = str(stc).replace("\\", "/")
    for const, model in _SENSOR_MODELS.items():
        if re.search(rf"^\s*#define\s+{re.escape(const)}\b", sensor_text, re.M):
            result["sensor"]["models"].append(model)
    four_wire = all(mac in result["pins"] for mac in _FOUR_WIRE_MACROS)
    result["sensor"]["wire"] = 4 if four_wire else (2 if "SENSOR_SDIO_PIN" in result["pins"] else None)

    # Mode / pair key
    for mac in ("MODE_24G_PIN", "MODE_BLE_PIN", "MODE_WIRED_PIN", "MODE_BLE_24G_PIN"):
        if mac in result["pins"]:
            result["mode"]["modes"].append(mac)
    # pair key is "present" only if active define exists (commented-out = absent)
    if "KEY_PAIR_PIN" in macros and macros["KEY_PAIR_PIN"][1]:
        result["mode"]["pair_key"] = _resolve(macros, "KEY_PAIR_PIN")

    # Encoder A/B (wheel or optical)
    for mac in ("WHEEL_A_PIN", "WHEEL_B_PIN", "H_ENCODER_A_PIN", "H_ENCODER_B_PIN"):
        if mac in result["pins"]:
            result["encoder"][mac] = result["pins"][mac]

    return result


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("usage: python source_scan.py <build_dir>")
        raise SystemExit(1)
    print(json.dumps(scan_build(sys.argv[1]), ensure_ascii=False, indent=2))
