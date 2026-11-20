#!/usr/bin/env python3
"""CH04 自动填表 + 生成 + Keil 编译验收（端到端）。

从 CH04 真实工程的 user_config.h **解析**硬件需求（脚位 / 极性 / 项目号 /
模式 / 滚轮 / LEDC 灯带 / 矩阵键 / 客户名 / BLE 名 / 版本号），走工具完整
新建流程：
    新建空白 → 选料 → 板型 → 配脚 → 逐脚极性 → 生成 → Keil 真编译
断言 Keil 0 Error / 0 Warning。脚位来自原理图（user_config.h），
**不用工具的推荐配置、不用扫描统计**——工程一改，脚本解析结果自动跟上。

与 S205 的差异（脚本自动处理，不硬编码脚位）：
- LOGO 走 LEDC 灯带，不是 RGB：led.c 的 pwm_off/pwm_write 由 BOARD_LOGO_RGB
  守护，灯带模式编译为空，不要求 LED_R/G/B。
- 矩阵键 KEY_C0：不要求 KEY_B/P/DPI（生成时 key_io.c 改写为矩阵扫描）。
- LEDC 两脚语义对调：原工程 LEDC_PIN=P34(控制)/LEDC_CTRL_PIN=P05(DIN)，
  工具约定 LEDC_PIN=P05(DIN)/LEDC_CTRL_PIN=P34(控制)，脚本交换后再填。
- 版本号来自 iREAL_VERSION_ID；客户名来自 iCONSUMER_NAME；BLE 名来自 mouse_hw.c。

用法：
    python scripts/ch04_autofill.py
    python scripts/ch04_autofill.py --project "E:\\...\\user_config.h" --out D:\\ch04_e2e
    python scripts/ch04_autofill.py --no-keil        # 只生成、不编译

依赖：Python 3.10+；Keil 可选（OMCFG_UV4 覆盖 UV4 路径）。不依赖 GUI/node。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from omcfg import derive  # noqa: E402
from omcfg.api import Api  # noqa: E402
from omcfg.autofill import unique_project_dir  # noqa: E402

DEFAULT_PROJECT = (
    Path("E:/M_2026/M_2026_T/457_CH04/SE71M_0457_CH04_V4_20260829")
    / "projects/mouse_demo/periph/user_config.h"
)

# LED 别名宏：#define LED_R_PIN LED_MODE_R_PIN —— 同物理脚，展开成同一个脚位。
LED_ALIASES = {
    "LED_R_PIN": "LED_MODE_R_PIN",
    "LED_G_PIN": "LED_MODE_G_PIN",
    "LED_B_PIN": "LED_MODE_B_PIN",
}
# 极性宏 → 主角色，gpio_set=高有效，gpio_clear=低有效。
POLARITY_SPECS = {
    "led_r_on": "LED_MODE_R_PIN",
    "led_g_on": "LED_MODE_G_PIN",
    "led_b_on": "LED_MODE_B_PIN",
    "led_low_on": "LED_LOW_PIN",
}
# 光电型号映射：只认目录里确实存在的选项；CH04 原工程 user_config.h 未写明
# 光电型号（只给 SCLK/SDIO 两线），留空交由选料步骤不指定，绝不硬造型号。
SENSOR_WIRE_OPTIONS = {
    "S205": "S205", "S201B": "S205", "KA8": "KA8",
    "MX8650A": "MX8650A", "S203": "S203",
}


def line(msg: str = "") -> None:
    print(msg, flush=True)


def step(label: str, result: dict) -> None:
    if not result or not result.get("ok"):
        line(f"  ✕ {label}: {result}")
        raise RuntimeError(f"{label} 失败: {(result or {}).get('error', '未知')}")
    detail = f"（变更 {result['changed']}）" if result.get("changed") else ""
    line(f"  ✓ {label}{detail}")


def parse_requirements(header_path: Path) -> dict:
    """从 CH04 user_config.h 解析硬件需求；只看事实，不套用任何默认值/统计。"""
    if not header_path.is_file():
        raise FileNotFoundError(f"找不到 CH04 user_config.h: {header_path}")
    text = header_path.read_text(encoding="utf-8", errors="replace")

    pins = derive._pins_from_header(text)
    if not pins:
        raise ValueError(f"{header_path} 解析不到任何 (Pnn) 脚位宏")

    # 展开 LED 别名（CH04 原工程可能没有，有则展开）。
    defs = derive._defines(text)
    for alias, target in LED_ALIASES.items():
        if target in pins:
            pins[alias] = pins[target]

    # LEDC 两脚语义对调：原工程 LEDC_PIN=P34(控制)、LEDC_CTRL_PIN=P05(DIN)，
    # 工具约定 LEDC_PIN=P05(DIN)、LEDC_CTRL_PIN=P34(控制)。
    ledc_note = ""
    if "LEDC_PIN" in pins and "LEDC_CTRL_PIN" in pins:
        if "PMU_LEDC_SEL_IO_05" in text or pins.get("LEDC_CTRL_PIN") == "P05":
            pins["LEDC_PIN"], pins["LEDC_CTRL_PIN"] = pins["LEDC_CTRL_PIN"], pins["LEDC_PIN"]
            ledc_note = f"（DIN/控制已对调 → DIN {pins['LEDC_PIN']} / 控制 {pins['LEDC_CTRL_PIN']}）"

    # 逐只灯极性。
    polarity: dict[str, str] = {}
    for func, role in POLARITY_SPECS.items():
        pat = re.compile(
            rf"#define\s+{func}\(\)[ \t]*(?:\([ \t]*)?(?P<fn>gpio_set|gpio_clear)\([ \t]*{role}[ \t]*\)"
        )
        m = pat.search(text)
        if m and role in pins:
            polarity[role] = "active_high" if m.group("fn") == "gpio_set" else "active_low"

    numbers = defs
    id_raw = numbers.get("iPROJECT_ID_L", "")
    if not id_raw:
        raise ValueError("user_config.h 缺 iPROJECT_ID_L，无法填项目号")
    id_low = int(id_raw, 0)
    name = numbers.get("iPROJECT_NAME", "CH04").strip('"') or "CH04"
    customer = numbers.get("iCONSUMER_NAME", "").strip('"') or "BYC"

    # 版本号来自 iREAL_VERSION_ID（工具在 apply 时还会 +1，这里传原值）。
    version_raw = numbers.get("iREAL_VERSION_ID", "1").strip()
    try:
        version = int(version_raw, 0)
    except ValueError:
        version = 1
    version = max(1, min(version, 0x7F - 1))  # apply 会 +1，留出余量

    # BLE 广播名来自 mouse_hw.c 的 mouse_name。
    project_root = header_path.parents[3]
    ble_name = ""
    mhw = project_root / "projects/mouse_demo/main/mouse_hw.c"
    if mhw.is_file():
        mname = re.search(
            r'mouse_name\s*\[[^\]]*\]\s*=\s*"([^"]+)"',
            mhw.read_text(encoding="utf-8", errors="replace"),
        )
        if mname:
            ble_name = mname.group(1).strip()

    # 传感器安装方向。
    dir_clock = 6
    m = re.search(r"SENSOR_DIR_CLOCK_(\d+)", defs.get("SENSOR_DIR_DEFINE", ""))
    if m and int(m.group(1)) in (0, 3, 6, 9):
        dir_clock = int(m.group(1))

    # 2.4G 指示灯复用哪只物理模式灯（CH04=R 红灯，S205=G 绿灯）。
    mode_24g_led = "R"
    m24 = re.search(r"LED_MODE_([RGB])_PIN", defs.get("LED_MODE_24G_PIN", ""))
    if m24:
        mode_24g_led = m24.group(1)

    has_pair = "KEY_PAIR_PIN" in pins
    has_key_c0 = "KEY_C0_PIN" in pins
    mode_dual = "MODE_24G_PIN" in pins and "MODE_BLE_PIN" in pins
    has_ledc = "LEDC_PIN" in pins

    # 滚轮：CH04 走硬件 pinmux（ENCODER_PINMUX_SEL_IO_00_01），直接采用原宏值。
    wheel_macro = defs.get("WHEEL_IO_SELECT", "")
    wheel = wheel_macro if wheel_macro in (
        "ENCODER_PINMUX_SEL_IO_00_01", "ENCODER_PINMUX_SEL_IO_20_21"
    ) else "SOFT_GPIO"

    # 选料：全部来自 user_config.h 事实。
    has_charger = "BAT_CHG_PIN" in pins
    sensor_model = name if name in SENSOR_WIRE_OPTIONS else ""
    selections: dict[str, str] = {}
    if sensor_model:
        selections["sensor"] = sensor_model
    if has_ledc:
        selections["led_strip"] = "WS2812"
    if has_charger:
        selections["charger"] = "4056H"
    selections["mode_key"] = "present" if has_pair else "absent"

    # LEDC 灯珠数：来自 LEDC_RGB_NUMBER；RGB 模式数三只模式灯。
    params: dict[str, object] = {}
    rgb_number = re.search(r"\d+", defs.get("LEDC_RGB_NUMBER", "") or "")
    if has_ledc and rgb_number:
        params["rgb_count"] = int(rgb_number.group())
    elif sum(1 for r in ("LED_MODE_R_PIN", "LED_MODE_G_PIN", "LED_MODE_B_PIN") if r in pins):
        params["rgb_count"] = sum(
            1 for r in ("LED_MODE_R_PIN", "LED_MODE_G_PIN", "LED_MODE_B_PIN") if r in pins
        )
    if mode_dual:
        params["switch_segments"] = 3  # 双脚 = 三段拨杆（2.4G/BAT/BT）

    return {
        "name": name,
        "id_low": id_low,
        "version": version,
        "customer": customer,
        "ble_name": ble_name,
        "pins": pins,
        "polarity": polarity,
        "mode_dual": mode_dual,
        "has_key_c0": has_key_c0,
        "wheel": wheel,
        "dir_clock": dir_clock,
        "mode_24g_led": mode_24g_led,
        "led_indicator": "full",  # CH04 原工程无 no-24g-rgb 标记，保留原版灯效
        "selections": selections,
        "params": params,
        "ledc_note": ledc_note,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="CH04 自动填表 + 生成 + Keil 编译验收")
    ap.add_argument("--project", default=str(DEFAULT_PROJECT), help="CH04 工程 user_config.h 路径")
    ap.add_argument("--out", default="", help="输出根目录（默认系统临时目录）")
    ap.add_argument("--name", default="CH04", help="新工程目录名")
    ap.add_argument("--no-keil", action="store_true", help="只生成、不编译")
    args = ap.parse_args()

    header = Path(args.project).expanduser().resolve()
    line(f"需求来源: {header}")
    try:
        req = parse_requirements(header)
    except Exception as exc:
        line(f"✕ 解析需求失败: {exc}")
        return 2
    line(
        f"解析完成: {req['name']} (0x{req['id_low']:04X}) v{req['version']} · {len(req['pins'])} 脚 · "
        f"{len(req['polarity'])} 只灯极性 · "
        f"{'双脚' if req['mode_dual'] else '单脚'} · {'矩阵键 KEY_C0' if req['has_key_c0'] else '独立键'} · "
        f"滚轮 {req['wheel']} · 传感器方向 CLOCK_{req['dir_clock']} · 2.4G灯 {req['mode_24g_led']}"
    )
    line(f"  身份: 客户名 {req['customer']} · BLE {req['ble_name'] or '(自动生成)'}")
    line(f"  选料: {req['selections']}  参数: {req['params']}{req['ledc_note']}\n")

    base = Path(args.out).resolve() if args.out else Path(tempfile.gettempdir()) / "ch04_autofill"
    sdk = unique_project_dir(base, args.name)
    if sdk.name != args.name:
        line(f"同名目录已存在，改写到 {sdk.name}（不覆盖原产物）")
    api = Api()

    try:
        line("开始自动填表:")
        step(
            "① 新建空白工程",
            api.blank_new(
                args.name, str(sdk), customer=req["customer"], id_low=req["id_low"],
                version=req["version"], ble_name=req["ble_name"] or None,
            ),
        )
        step("② 选料", api.material_apply(str(sdk), req["selections"], req["params"]))
        step(
            "③ 板型",
            api.blank_set_board(
                str(sdk),
                {
                    "mode_pins": "dual" if req["mode_dual"] else "single",
                    "logo": "ledc" if "LEDC_PIN" in req["pins"] else ("rgb" if "LED_MODE_R_PIN" in req["pins"] else "none"),
                    "wheel": req["wheel"],
                    "ledc_rgb_number": req["params"].get("rgb_count", 6),
                    "led_polarity": req["polarity"].get("LED_MODE_R_PIN", "active_high"),
                    "switch_segments": req["params"].get("switch_segments", 2),
                    "ble_channels": 2,
                    "sensor.dir_clock": req["dir_clock"],
                    "mode_24g_led": req["mode_24g_led"],
                    "led_indicator": req["led_indicator"],
                },
            ),
        )
        step("④ 配脚", api.blank_save(str(sdk), req["pins"]))
        if req["polarity"]:
            step("⑤ 逐脚极性", api.blank_set_polarity(str(sdk), req["polarity"]))
        else:
            line("  - ⑤ 极性: user_config.h 无可解析极性宏，跳过")
        st = api.blank_status(str(sdk))
        if not st.get("complete") or st.get("missing") or st.get("conflicts"):
            line(f"  ✕ 工程未就绪: 缺={st.get('missing')} 冲突={st.get('conflicts')}")
            return 1
        line("  ✓ 校验通过: 无缺脚、无冲突、可生成\n")
        step("⑥ 生成 Keil 工程", api.blank_apply(str(sdk)))
    except RuntimeError as exc:
        line(f"\n✕ 自动填表中断: {exc}")
        return 1

    proj = sdk / "projects/mouse_demo/keil5/SE71M.uvprojx"
    if not proj.is_file():
        line(f"✕ Keil 工程未生成: {proj}")
        return 1
    line(f"✓ Keil 工程: {proj}")

    if args.no_keil:
        line("\n（--no-keil：跳过编译）")
        return 0

    uv4 = Path(os.environ.get("OMCFG_UV4", r"C:\Keil_v5\UV4\UV4.exe"))
    if not uv4.is_file():
        line(f"\n⚠ 未找到 Keil UV4（{uv4}），跳过编译；可用 OMCFG_UV4 指定路径")
        return 0
    log = base / (sdk.name + "_build.log")
    line("\nKeil 全量重编...")
    subprocess.run(
        [str(uv4), "-r", str(proj), "-o", str(log)],
        capture_output=True, text=True, timeout=300, check=False,
    )
    content = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    for ln in content.splitlines():
        if "error" in ln.lower() or "Error(s)" in ln or "Warning(s)" in ln:
            line("  " + ln.strip()[:160])
    if "0 Error(s), 0 Warning(s)" in content:
        line(f"\n✓ PASS：Keil 0 Error / 0 Warning\n日志: {log}\n工程: {sdk}")
        return 0
    line(f"\n✕ FAIL：Keil 编译未通过。日志: {log}\n工程: {sdk}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
