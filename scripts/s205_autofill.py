#!/usr/bin/env python3
"""S205 自动填表 + 生成 + Keil 编译验收（端到端）。

从 S205 真实工程的 user_config.h **解析**硬件需求（脚位 / 极性 / 项目号 /
模式 / 滚轮 / 有无 mode 键），走工具完整新建流程：
    新建空白 → 选料 → 板型 → 配脚 → 逐脚极性 → 生成 → Keil 真编译
断言 Keil 0 Error / 0 Warning。脚位来自原理图（user_config.h），
**不用工具的推荐配置、不用扫描统计**——工程一改，脚本解析结果自动跟上。

用法：
    python scripts/s205_autofill.py
    python scripts/s205_autofill.py --project "E:\\...\\user_config.h" --out D:\\s205_e2e
    python scripts/s205_autofill.py --no-keil        # 只生成、不编译

依赖：Python 3.10+；Keil 可选（OMCFG_UV4 覆盖 UV4 路径）。不依赖 GUI/node。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from omcfg import derive  # noqa: E402
from omcfg.api import Api  # noqa: E402

DEFAULT_PROJECT = (
    Path("E:/M_2026/512_S205/software/trunk/SE71M_0512_S205_V1_20261017")
    / "projects/mouse_demo/periph/user_config.h"
)

# 别名宏：#define LED_R_PIN LED_MODE_R_PIN —— 同物理脚，展开成同一个脚位。
LED_ALIASES = {
    "LED_R_PIN": "LED_MODE_R_PIN",
    "LED_G_PIN": "LED_MODE_G_PIN",
    "LED_B_PIN": "LED_MODE_B_PIN",
}
# 极性宏 → (主角色, 宏目标脚)，别名脚跟随主灯。
POLARITY_SPECS = {
    "led_r_on": "LED_MODE_R_PIN",
    "led_g_on": "LED_MODE_G_PIN",
    "led_b_on": "LED_MODE_B_PIN",
    "led_low_on": "LED_LOW_PIN",
}
# 由解析出的脚位事实推导选料（不读扫描统计）。
SENSOR_WIRE_OPTIONS = {
    "S205": "S205", "S201B": "S205", "KA8": "KA8", "MX8650A": "MX8650A",
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
    """从 user_config.h 解析硬件需求；只看事实，不套用任何默认值/统计。"""
    if not header_path.is_file():
        raise FileNotFoundError(f"找不到 S205 user_config.h: {header_path}")
    text = header_path.read_text(encoding="utf-8", errors="replace")

    pins = derive._pins_from_header(text)
    if not pins:
        raise ValueError(f"{header_path} 解析不到任何 (Pnn) 脚位宏")

    # 展开 LED 别名（LED_R_PIN = LED_MODE_R_PIN）。
    defs = derive._defines(text)
    for alias, target in LED_ALIASES.items():
        if target in pins:
            pins[alias] = pins[target]

    # 逐只灯极性：gpio_set=高有效，gpio_clear=低有效。
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
    name = numbers.get("iPROJECT_NAME", "S205").strip('"') or "S205"

    # 工程身份：客户名写进 iCONSUMER_NAME；BLE 广播名来自 mouse_hw.c 的 mouse_name。
    customer = numbers.get("iCONSUMER_NAME", "").strip('"') or "BYC"
    # user_config.h 在 <root>/projects/mouse_demo/periph/ 下，项目根是 parents[3]
    project_root = header_path.parents[3]
    ble_name = ""
    mhw = project_root / "projects/mouse_demo/main/mouse_hw.c"
    if mhw.is_file():
        mname = re.search(r'mouse_name\s*\[[^\]]*\]\s*=\s*"([^"]+)"', mhw.read_text(encoding="utf-8", errors="replace"))
        if mname:
            ble_name = mname.group(1).strip()

    # 指示灯策略：原工程若带 [no-24g-rgb] / [no-dongle-led] 标记，说明底层点灯调用
    # 已让路给 mode_led_hint（仅指示灯），生成时用 hint_only 编译期排除等价调用。
    led_indicator = "full"
    rf_c = project_root / "mode_24g/rf_data_process.c"
    slp_c = project_root / "mode_24g/sleep.c"
    hints = ""
    for p in (rf_c, slp_c):
        if p.is_file():
            hints += p.read_text(encoding="utf-8", errors="replace")
    if "no-24g-rgb" in hints or "no-dongle-led" in hints:
        led_indicator = "hint_only"

    # 传感器安装方向：由硬件安装角度决定，忠于 user_config.h，不用工具默认 6。
    dir_clock = 6
    dir_define = defs.get("SENSOR_DIR_DEFINE", "")
    m = re.search(r"SENSOR_DIR_CLOCK_(\d+)", dir_define)
    if m and int(m.group(1)) in (0, 3, 6, 9):
        dir_clock = int(m.group(1))

    # 2.4G 指示灯复用哪只物理模式灯：由硬件决定（S205=P05 绿灯 G，KC536=R 红灯）。
    # 读 #define LED_MODE_24G_PIN LED_MODE_G_PIN 的别名目标，不套默认值。
    mode_24g_led = "R"
    alias_24g = defs.get("LED_MODE_24G_PIN", "")
    m24 = re.search(r"LED_MODE_([RGB])_PIN", alias_24g)
    if m24:
        mode_24g_led = m24.group(1)

    has_pair = "KEY_PAIR_PIN" in pins
    mode_dual = "MODE_24G_PIN" in pins and "MODE_BLE_PIN" in pins
    # 滚轮：P24/P25 走硬件 pinmux；工具的 WHEEL_ENUM 不认 24_25，
    # 统一用 SOFT_GPIO 表达「脚位自由分配」，脚位仍按原理图填 P24/P25。
    wheel_macro = defs.get("WHEEL_IO_SELECT", "")
    wheel = "SOFT_GPIO" if "24_25" in wheel_macro else (wheel_macro or "SOFT_GPIO")

    # 选料：全部来自 user_config.h 事实。
    has_charger = "BAT_CHG_PIN" in pins
    has_ledc = "LEDC_PIN" in pins
    rgb_count = sum(1 for r in ("LED_MODE_R_PIN", "LED_MODE_G_PIN", "LED_MODE_B_PIN") if r in pins)
    # 光电型号：优先项目名，其次 DPI 表特征；命中目录选项才写，否则留空（不硬造型号）。
    model_name = name if name in SENSOR_WIRE_OPTIONS else ""
    selections = {
        "sensor": model_name,
        "led_strip": "WS2812" if has_ledc else "none",
        "charger": "4056H" if has_charger else "none",
        "mode_key": "present" if has_pair else "absent",
    }
    selections = {k: v for k, v in selections.items() if v}
    params: dict[str, object] = {}
    if rgb_count:
        params["rgb_count"] = rgb_count
    if "MODE_24G_PIN" in pins and "MODE_BLE_PIN" in pins:
        params["switch_segments"] = 3  # 双脚对应三段拨杆（2.4G/BAT/BT）

    return {
        "name": name,
        "id_low": id_low,
        "customer": customer,
        "ble_name": ble_name,
        "led_indicator": led_indicator,
        "pins": pins,
        "polarity": polarity,
        "mode_dual": mode_dual,
        "wheel": wheel,
        "dir_clock": dir_clock,
        "mode_24g_led": mode_24g_led,
        "selections": selections,
        "params": params,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="S205 自动填表 + 生成 + Keil 编译验收")
    ap.add_argument("--project", default=str(DEFAULT_PROJECT), help="S205 工程 user_config.h 路径")
    ap.add_argument("--out", default="", help="输出根目录（默认系统临时目录）")
    ap.add_argument("--name", default="S205", help="新工程目录名")
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
        f"解析完成: {req['name']} (0x{req['id_low']:04X}) · {len(req['pins'])} 脚 · "
        f"{len(req['polarity'])} 只灯极性 · "
        f"{'双脚' if req['mode_dual'] else '单脚'} · 滚轮 {req['wheel']} · "
        f"传感器方向 CLOCK_{req['dir_clock']} · 2.4G灯 {req['mode_24g_led']} · "
        f"指示灯 {req['led_indicator']}"
    )
    line(f"  身份: 客户名 {req['customer']} · BLE {req['ble_name'] or '(自动生成)'}")
    line(f"  选料: {req['selections']}  参数: {req['params']}\n")

    base = Path(args.out).resolve() if args.out else Path(tempfile.gettempdir()) / "s205_autofill"
    sdk = base / args.name
    if sdk.exists():
        shutil.rmtree(sdk)
    api = Api()

    try:
        line("开始自动填表:")
        step(
            "① 新建空白工程",
            api.blank_new(
                args.name, str(sdk), customer=req["customer"], id_low=req["id_low"], ble_name=req["ble_name"] or None
            ),
        )
        step("② 选料", api.material_apply(str(sdk), req["selections"], req["params"]))
        step(
            "③ 板型",
            api.blank_set_board(
                str(sdk),
                {
                    "mode_pins": "dual" if req["mode_dual"] else "single",
                    "logo": "rgb" if "LED_MODE_R_PIN" in req["pins"] else "none",
                    "wheel": req["wheel"],
                    "sensor.dir_clock": req["dir_clock"],
                    "mode_24g_led": req["mode_24g_led"],
                    "led_indicator": req["led_indicator"],
                    "switch_segments": req["params"].get("switch_segments", 2),
                    "ble_channels": 2,
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
    log = base / (args.name + "_build.log")
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
