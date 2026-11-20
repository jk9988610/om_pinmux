"""自动填表统一引擎：从已有工程的 user_config.h 解析硬件事实，走完整新建流程。

供可视化工具（web）与命令行脚本共用。引擎只做两件事：
- parse(header)：只读解析，返回 req dict（不写盘），供 UI 预览；
- run(header, out, name, keil)：新建→选料→板型→配脚→极性→生成→Keil，返回结构化日志。

工程类型不再由脚本名决定，而是由硬件事实决定：
- 有 LEDC_PIN → CH04 风格（LEDC 对调、版本来自 iREAL_VERSION_ID、矩阵键 KEY_C0）；
- 否则 → S205 风格（RGB 灯、led_indicator 由 no-24g-rgb 标记推导）。
差异都走"有则处理、无则跳过"，不硬造型号/脚位。
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from . import derive


HEADER_REL = "projects/mouse_demo/periph/user_config.h"

LED_ALIASES = {
    "LED_R_PIN": "LED_MODE_R_PIN",
    "LED_G_PIN": "LED_MODE_G_PIN",
    "LED_B_PIN": "LED_MODE_B_PIN",
}
POLARITY_SPECS = {
    "led_r_on": "LED_MODE_R_PIN",
    "led_g_on": "LED_MODE_G_PIN",
    "led_b_on": "LED_MODE_B_PIN",
    "led_low_on": "LED_LOW_PIN",
}
SENSOR_WIRE_OPTIONS = {
    "S205": "S205", "S201B": "S205", "KA8": "KA8",
    "MX8650A": "MX8650A", "S203": "S203",
}
WHEEL_PINMUX = ("ENCODER_PINMUX_SEL_IO_00_01", "ENCODER_PINMUX_SEL_IO_20_21")

LogFn = Callable[[str], None]


def _noop(msg: str) -> None:
    pass


def unique_project_dir(base: Path | str, name: str) -> Path:
    """在输出根目录里分配一个不存在的工程目录，绝不覆盖已有产物。

    同名时追加序号：name → name(1) → name(2) …。既有目录原样保留，
    便于反复测试同一工程时对比每次生成结果。
    """
    root = Path(base).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    stem = (name or "MyMouse").strip() or "MyMouse"
    candidate = root / stem
    if not candidate.exists():
        return candidate
    index = 1
    while True:
        candidate = root / f"{stem}({index})"
        if not candidate.exists():
            return candidate
        index += 1


def _detect_led_effect(root: Path) -> tuple[str, str]:
    """从源工程 led.c 判断灯效真正走 LEDC 灯带还是三色灯。

    事实依据：灯带工程（CH04/HTS092/BM2017）把底层 logo_cfg/pwm_write 留空，
    灯效交给 LEDC 驱动；三色灯工程（S205/KC536/LJ-A08）在这两个函数里用
    PWM/GPIO 点灯。LJ-A08 虽定义了 LEDC 脚，但灯效仍走三色灯，不能一刀切。

    返回 (logo, reason)：logo 为 ledc / rgb / 空（无事实，回退到脚位判断）。
    """
    led = root / "projects/mouse_demo/periph/led.c"
    if not led.is_file():
        return "", "源工程无 led.c，回退脚位判断"
    text = led.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    body = ""
    for fn in ("logo_cfg", "pwm_write"):
        match = re.search(rf"\b{fn}\s*\([^)]*\)\s*\{{", text)
        if not match:
            continue
        depth, i = 1, match.end()
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body += text[match.end():i - 1]
    if re.search(r"OM_PWM|OM_GPIO|gpio_|PWMPRD|PWMCON|DATAOUT|memcpy", body):
        return "rgb", "源 led.c 的 logo_cfg/pwm_write 含三色灯点灯实现"
    if "logo_cfg" in text or "pwm_write" in text:
        return "ledc", "源 led.c 的 logo_cfg/pwm_write 为空，灯效走 LEDC 灯带"
    return "", "源 led.c 无灯效函数，回退脚位判断"


def parse(header_path: Path | str) -> dict[str, Any]:
    """只读解析 user_config.h（及同工程 mouse_hw.c / mode_24g），返回硬件需求。

    不套用任何默认值/统计，不写盘。所有脚位来自 user_config.h 的 (Pnn) 宏。
    """
    header = Path(header_path).expanduser().resolve()
    if not header.is_file():
        raise FileNotFoundError(f"找不到 user_config.h: {header}")
    text = header.read_text(encoding="utf-8", errors="replace")

    pins = derive._pins_from_header(text)
    if not pins:
        raise ValueError(f"{header} 解析不到任何 (Pnn) 脚位宏")
    defs = derive._defines(text)

    # LED 别名展开（同物理脚）。
    for alias, target in LED_ALIASES.items():
        if target in pins:
            pins[alias] = pins[target]

    # LEDC 两脚语义对调：原工程 LEDC_PIN=P34(控制)/LEDC_CTRL_PIN=P05(DIN)，
    # 工具约定 LEDC_PIN=P05(DIN)/LEDC_CTRL_PIN=P34(控制)。
    ledc_note = ""
    if "LEDC_PIN" in pins and "LEDC_CTRL_PIN" in pins:
        if "PMU_LEDC_SEL_IO_05" in text or pins.get("LEDC_CTRL_PIN") == "P05":
            pins["LEDC_PIN"], pins["LEDC_CTRL_PIN"] = pins["LEDC_CTRL_PIN"], pins["LEDC_PIN"]
            ledc_note = "DIN/控制已对调"

    # 逐只灯极性：gpio_set=高有效，gpio_clear=低有效。
    polarity: dict[str, str] = {}
    for func, role in POLARITY_SPECS.items():
        pat = re.compile(
            rf"#define\s+{func}\(\)[ \t]*(?:\([ \t]*)?(?P<fn>gpio_set|gpio_clear)\([ \t]*{role}[ \t]*\)"
        )
        m = pat.search(text)
        if m and role in pins:
            polarity[role] = "active_high" if m.group("fn") == "gpio_set" else "active_low"

    id_raw = defs.get("iPROJECT_ID_L", "")
    if not id_raw:
        raise ValueError("user_config.h 缺 iPROJECT_ID_L，无法填项目号")
    id_low = int(id_raw, 0)
    name = defs.get("iPROJECT_NAME", "").strip('"') or header.parents[3].name or "MyMouse"
    customer = defs.get("iCONSUMER_NAME", "").strip('"') or "BYC"

    # 版本号：CH04 风格给 iREAL_VERSION_ID，S205 缺省 1；apply 会 +1，留出余量。
    version = 1
    version_raw = defs.get("iREAL_VERSION_ID", "").strip()
    if version_raw:
        try:
            version = int(version_raw, 0)
        except ValueError:
            version = 1
    version = max(1, min(version, 0x7F - 1))

    # 工程身份：BLE 广播名来自 mouse_hw.c 的 mouse_name。
    root = header.parents[3]
    ble_name = ""
    mhw = root / "projects/mouse_demo/main/mouse_hw.c"
    if mhw.is_file():
        m = re.search(r'mouse_name\s*\[[^\]]*\]\s*=\s*"([^"]+)"', mhw.read_text(encoding="utf-8", errors="replace"))
        if m:
            ble_name = m.group(1).strip()

    # 指示灯策略：底层点灯已让路给 mode_led_hint 的工程用 hint_only。
    led_indicator = "full"
    hints = ""
    for rel in ("mode_24g/rf_data_process.c", "mode_24g/sleep.c"):
        p = root / rel
        if p.is_file():
            hints += p.read_text(encoding="utf-8", errors="replace")
    if "no-24g-rgb" in hints or "no-dongle-led" in hints:
        led_indicator = "hint_only"

    # 传感器安装方向。
    dir_clock = 6
    m = re.search(r"SENSOR_DIR_CLOCK_(\d+)", defs.get("SENSOR_DIR_DEFINE", ""))
    if m and int(m.group(1)) in (0, 3, 6, 9):
        dir_clock = int(m.group(1))

    # 2.4G 指示灯复用哪只物理模式灯（读别名目标，不套默认）。
    mode_24g_led = "R"
    m24 = re.search(r"LED_MODE_([RGB])_PIN", defs.get("LED_MODE_24G_PIN", ""))
    if m24:
        mode_24g_led = m24.group(1)

    has_pair = "KEY_PAIR_PIN" in pins
    has_key_c0 = "KEY_C0_PIN" in pins
    has_ledc = "LEDC_PIN" in pins
    mode_dual = "MODE_24G_PIN" in pins and "MODE_BLE_PIN" in pins

    # 灯效类型（LOGO 用灯带还是三色灯）：以源工程 led.c 实现为事实。
    # 有 LEDC 脚 ≠ 灯效用灯带：LJ-A08 有 LEDC 脚但 logo_cfg 走三色灯。
    # 反过来 CH04/HTS092/BM2017 虽同时有 RGB 脚，logo_cfg 为空，灯效走灯带。
    led_effect, led_effect_reason = _detect_led_effect(root)
    # 没有 LEDC 脚就不可能是灯带（DIN 脚不存在）：MC329 的 led.c 空但灯效走 rgb.c。
    if led_effect == "ledc" and not has_ledc:
        led_effect, led_effect_reason = "", "led.c 空但无 LEDC 脚，回退脚位判断"
    if not led_effect:
        led_effect = "ledc" if has_ledc else ("rgb" if "LED_MODE_R_PIN" in pins else "none")

    # 滚轮：优先采用硬件 pinmux 宏；24_25 与无宏统一用 SOFT_GPIO（脚位仍按原理图）。
    wheel_macro = defs.get("WHEEL_IO_SELECT", "")
    if wheel_macro in WHEEL_PINMUX:
        wheel = wheel_macro
    elif "24_25" in wheel_macro:
        wheel = "SOFT_GPIO"
    else:
        wheel = wheel_macro or "SOFT_GPIO"

    # 选料：来自硬件事实；型号只认目录里的选项，否则留空（不硬造）。
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

    params: dict[str, object] = {}
    rgb_number = re.search(r"\d+", defs.get("LEDC_RGB_NUMBER", "") or "")
    if has_ledc and rgb_number:
        params["rgb_count"] = int(rgb_number.group())
    elif sum(1 for r in ("LED_MODE_R_PIN", "LED_MODE_G_PIN", "LED_MODE_B_PIN") if r in pins):
        params["rgb_count"] = sum(
            1 for r in ("LED_MODE_R_PIN", "LED_MODE_G_PIN", "LED_MODE_B_PIN") if r in pins
        )
    if mode_dual:
        params["switch_segments"] = 3

    return {
        "header": str(header),
        "project_root": str(root),
        "name": name,
        "id_low": id_low,
        "version": version,
        "customer": customer,
        "ble_name": ble_name,
        "pins": pins,
        "polarity": polarity,
        "mode_dual": mode_dual,
        "has_key_c0": has_key_c0,
        "has_ledc": has_ledc,
        "wheel": wheel,
        "dir_clock": dir_clock,
        "mode_24g_led": mode_24g_led,
        "led_indicator": led_indicator,
        "logo": led_effect,
        "led_effect_reason": led_effect_reason,
        "selections": selections,
        "params": params,
        "ledc_note": ledc_note,
        "style": "CH04" if (has_ledc or has_key_c0) else "S205",
    }


def board_updates(req: dict[str, Any]) -> dict[str, Any]:
    """把解析结果映射成 blank_set_board 的选项（allowed 字段全集）。"""
    pins = req["pins"]
    # 灯效类型来自源工程 led.c 事实解析，不再用"有没有 LEDC 脚"一刀切。
    logo = req.get("logo") or ("ledc" if "LEDC_PIN" in pins else ("rgb" if "LED_MODE_R_PIN" in pins else "none"))
    return {
        "mode_pins": "dual" if req["mode_dual"] else "single",
        "logo": logo,
        "wheel": req["wheel"],
        "ledc_rgb_number": req["params"].get("rgb_count", 6),
        "led_polarity": req["polarity"].get("LED_MODE_R_PIN", "active_high"),
        "switch_segments": req["params"].get("switch_segments", 2),
        "ble_channels": 2,
        "sensor.dir_clock": req["dir_clock"],
        "mode_24g_led": req["mode_24g_led"],
        "led_indicator": req["led_indicator"],
    }


def run(
    header_path: Path | str,
    out_root: Path | str,
    name: str = "",
    keil: bool = True,
    log: LogFn | None = None,
) -> dict[str, Any]:
    """执行完整自动填表。log 回调逐行输出（GUI 实时显示用）。

    返回 {ok, project, log_lines, error, ...}。失败不抛异常，结构化返回。
    """
    emit = log or _noop
    lines: list[str] = []

    def line(msg: str = "") -> None:
        lines.append(msg)
        emit(msg)

    def step(label: str, result: dict | None) -> None:
        if not result or not result.get("ok"):
            detail = (result or {}).get("error", "未知")
            line(f"  ✕ {label}: {detail}")
            raise RuntimeError(f"{label} 失败: {detail}")
        detail = f"（变更 {result['changed']}）" if result.get("changed") else ""
        line(f"  ✓ {label}{detail}")

    from .api import Api  # 延迟导入，避免 web/CLI 启动时循环依赖

    try:
        header = Path(header_path).expanduser().resolve()
        line(f"需求来源: {header}")
        req = parse(header)
        line(
            f"解析完成: {req['name']} (0x{req['id_low']:04X}) v{req['version']} · {len(req['pins'])} 脚 · "
            f"{len(req['polarity'])} 只灯极性 · {'双脚' if req['mode_dual'] else '单脚'} · "
            f"{'矩阵键 KEY_C0' if req['has_key_c0'] else '独立键'} · 滚轮 {req['wheel']} · "
            f"方向 CLOCK_{req['dir_clock']} · 2.4G灯 {req['mode_24g_led']} · 风格 {req['style']}"
        )
        line(f"  灯效: {'LEDC 灯带' if req['logo'] == 'ledc' else ('三色灯' if req['logo'] == 'rgb' else '无')}"
             f"（{req['led_effect_reason']}）")
        line(f"  身份: 客户 {req['customer']} · BLE {req['ble_name'] or '(自动生成)'}")
        line(f"  选料: {req['selections']}  参数: {req['params']}"
             + (f"  {req['ledc_note']}" if req["ledc_note"] else "") + "\n")

        base = Path(out_root).expanduser().resolve()
        proj_name = (name or req["name"]).strip() or "MyMouse"
        sdk = unique_project_dir(base, proj_name)
        line(f"输出目录: {sdk.name}（同名不覆盖，自动追加序号）")
        api = Api()

        line("开始自动填表:")
        step("① 新建空白工程", api.blank_new(
            proj_name, str(sdk), customer=req["customer"], id_low=req["id_low"],
            version=req["version"], ble_name=req["ble_name"] or None,
        ))
        step("② 选料", api.material_apply(str(sdk), req["selections"], req["params"]))
        step("③ 板型", api.blank_set_board(str(sdk), board_updates(req)))
        step("④ 配脚", api.blank_save(str(sdk), req["pins"]))
        if req["polarity"]:
            step("⑤ 逐脚极性", api.blank_set_polarity(str(sdk), req["polarity"]))
        else:
            line("  - ⑤ 极性: user_config.h 无可解析极性宏，跳过")
        st = api.blank_status(str(sdk))
        if not st.get("complete") or st.get("missing") or st.get("conflicts"):
            line(f"  ✕ 工程未就绪: 缺={st.get('missing')} 冲突={st.get('conflicts')}")
            raise RuntimeError("工程未就绪，拒绝生成")
        line("  ✓ 校验通过: 无缺脚、无冲突、可生成\n")
        step("⑥ 生成 Keil 工程", api.blank_apply(str(sdk)))

        proj = sdk / "projects/mouse_demo/keil5/SE71M.uvprojx"
        if not proj.is_file():
            line(f"✕ Keil 工程未生成: {proj}")
            raise RuntimeError("Keil 工程未生成")
        line(f"✓ Keil 工程: {proj}")

        if not keil:
            line("\n（跳过 Keil 编译）")
            return {"ok": True, "project": str(sdk), "keil": False, "lines": lines,
                    "version": req["version"]}

        uv4 = Path(os.environ.get("OMCFG_UV4", r"C:\Keil_v5\UV4\UV4.exe"))
        if not uv4.is_file():
            line(f"\n⚠ 未找到 Keil UV4（{uv4}），跳过编译；可用 OMCFG_UV4 指定路径")
            return {"ok": True, "project": str(sdk), "keil": False, "lines": lines,
                    "version": req["version"], "warning": "Keil 未找到，跳过编译"}
        log_path = base / (sdk.name + "_build.log")
        line("\nKeil 全量重编...")
        subprocess.run(
            [str(uv4), "-r", str(proj), "-o", str(log_path)],
            capture_output=True, text=True, timeout=300, check=False,
        )
        content = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
        for ln in content.splitlines():
            if "error" in ln.lower() or "Error(s)" in ln or "Warning(s)" in ln:
                line("  " + ln.strip()[:160])
        if "0 Error(s), 0 Warning(s)" in content:
            line(f"\n✓ PASS：Keil 0 Error / 0 Warning")
            line(f"日志: {log_path}")
            line(f"工程: {sdk}")
            return {"ok": True, "project": str(sdk), "keil": True, "lines": lines,
                    "version": req["version"], "build_log": str(log_path)}
        line(f"\n✕ FAIL：Keil 编译未通过。日志: {log_path}")
        return {"ok": False, "project": str(sdk), "keil": False, "lines": lines,
                "version": req["version"], "error": "Keil 编译未通过", "build_log": str(log_path)}
    except Exception as exc:
        line(f"\n✕ 自动填表失败: {exc}")
        return {"ok": False, "lines": lines, "error": str(exc)}


def discover(root: Path | str) -> list[dict[str, Any]]:
    """扫描根目录下的可填表工程（含 user_config.h 的 projects/mouse_demo）。

    只读，返回精简列表供 UI 列出；解析失败的单条标记 error，不影响其他工程。
    """
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise NotADirectoryError(f"不是有效目录: {base}")
    found: list[dict[str, Any]] = []
    for header in sorted(base.rglob(HEADER_REL)):
        proj_root = header.parents[3]
        item: dict[str, Any] = {
            "header": str(header),
            "project_root": str(proj_root),
            "name": proj_root.name,
        }
        try:
            req = parse(header)
            item.update({
                "project_name": req["name"],
                "id_low": req["id_low"],
                "version": req["version"],
                "customer": req["customer"],
                "ble_name": req["ble_name"],
                "style": req["style"],
                "pin_count": len(req["pins"]),
                "error": "",
            })
        except Exception as exc:
            item["error"] = str(exc)
        found.append(item)
    return found


# ---- 后台任务管理：前端轮询状态实现实时日志（不依赖平台相关 JS 回调） ----
import threading

_JOB: dict[str, Any] = {"running": False, "lines": [], "result": None, "error": ""}
_LOCK = threading.Lock()


def start_job(
    header_path: Path | str,
    out_root: Path | str,
    name: str = "",
    keil: bool = True,
) -> dict[str, Any]:
    """启动后台填表任务，立即返回。用 job_status() 轮询日志与结果。"""
    with _LOCK:
        if _JOB["running"]:
            return {"ok": False, "error": "已有填表任务在执行中"}
        _JOB.update({"running": True, "lines": [], "result": None, "error": ""})

    def emit(msg: str) -> None:
        with _LOCK:
            _JOB["lines"].append(msg)

    def worker() -> None:
        try:
            result = run(header_path, out_root, name=name, keil=keil, log=emit)
            with _LOCK:
                _JOB["result"] = result
        except Exception as exc:  # run 内部已捕获，这里是兜底
            with _LOCK:
                _JOB["error"] = str(exc)
        finally:
            with _LOCK:
                _JOB["running"] = False

    threading.Thread(target=worker, daemon=True, name="omcfg-autofill").start()
    return {"ok": True, "message": "填表任务已启动"}


def job_status() -> dict[str, Any]:
    """返回当前任务状态：running / lines（日志快照）/ result / error。"""
    with _LOCK:
        return {
            "running": bool(_JOB["running"]),
            "lines": list(_JOB["lines"]),
            "result": _JOB["result"],
            "error": _JOB["error"],
        }
