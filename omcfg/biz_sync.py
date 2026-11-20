# -*- coding: utf-8 -*-
"""
业务契约同步：扫描工程中对脚位宏的引用，并按板型安全改写。

只改「契约层」（宏是否存在、单/双模式、有无 PAIR、矩阵键、LEDC 文件），
不改配对协议细节。
"""

# === 状态标注（pinmux_7, 2026-11-16）===
# 状态：删除 workflow.py / policy.py 后，本模块暂无外部调用者（孤儿保留）。
# 依据：ROADMAP §0.2 序 3 规划「拆分保留 key_io/sleep 契约」，后续收敛为 contracts.py。
# 能力：sync_board_contracts 的 6 个 action（key_io.h / key_io.c / user_config.c / RTE / logo_ledc）有实测功能，不可删。
# 原调用点：workflow.py L1033-1037 apply_policies 的 kind=="biz_sync" 分支（已随 workflow 删除）。
# 接手方：pinmux_8 收敛为 contracts.py 并接入配置驱动路径。
# ========================================

from __future__ import annotations

import os
import re
import shutil

PIN_MACROS = [
    "KEY_R0_PIN",
    "KEY_R1_PIN",
    "KEY_R2_PIN",
    "KEY_PAIR_PIN",
    "KEY_C0_PIN",
    "KEY_B_PIN",
    "KEY_P_PIN",
    "KEY_DPI_PIN",
    "KEY_DPI_SUB_PIN",
    "KEY_DPI_ADD_PIN",
    "WHEEL_A_PIN",
    "WHEEL_B_PIN",
    "WHEEL_IO_SELECT",
    "WHEEL_SOFT_GPIO",
    "MODE_24G_PIN",
    "MODE_BLE_PIN",
    "MODE_BLE_24G_PIN",
    "MODE_BLE_CHECK",
    "MODE_24G_CHECK",
    "SENSOR_MOTION_PIN",
    "SENSOR_SCLK_PIN",
    "SENSOR_SDIO_PIN",
    "SENSOR_NCS_PIN",
    "LED_MODE_R_PIN",
    "LED_MODE_G_PIN",
    "LED_MODE_B_PIN",
    "LED_LOW_PIN",
    "LED_R_PIN",
    "LED_G_PIN",
    "LED_B_PIN",
    "LEDC_PIN",
    "LEDC_CTRL_PIN",
    "USB_5V",
    "BAT_CHG_PIN",
    "LVD_PIN",
    "LVD_CHECK_INDEX",
]

SCAN_EXTS = {".c", ".h"}
SKIP_DIR_NAMES = {
    "out",
    "Objects",
    "Listings",
    "DebugConfig",
    "lib_build",
    ".git",
    "node_modules",
    "__pycache__",
}


def _iter_source_files(root: str):
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES and not d.startswith("_pinmux_bak")]
        for name in filenames:
            if os.path.splitext(name)[1].lower() in SCAN_EXTS:
                yield os.path.join(dirpath, name)


def scan_project_refs(project_hint: str) -> dict:
    """扫描 periph + 同级 main 中的脚位宏引用。"""
    periph = os.path.abspath(project_hint)
    roots = [periph]
    main_dir = os.path.join(os.path.dirname(periph), "main")
    if os.path.isdir(main_dir):
        roots.append(main_dir)

    by_macro: dict[str, list[dict]] = {}
    issues: list[str] = []
    macro_re = re.compile(r"\b(" + "|".join(PIN_MACROS) + r")\b")
    total = 0

    for root in roots:
        for path in _iter_source_files(root):
            if path.endswith("board_features.h") or path.endswith(".pinmux.c"):
                continue
            try:
                lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
            except OSError:
                continue
            rel = os.path.relpath(path, periph).replace("\\", "/")
            for i, line in enumerate(lines, 1):
                for m in macro_re.finditer(line):
                    total += 1
                    mac = m.group(1)
                    by_macro.setdefault(mac, []).append(
                        {
                            "file": rel,
                            "line": i,
                            "text": line.strip()[:160],
                        }
                    )

    if "MODE_BLE_24G_PIN" in by_macro and "MODE_24G_PIN" in by_macro:
        issues.append("同时发现 MODE_BLE_24G_PIN 与 MODE_24G_PIN，可能混用单/双模式契约")
    if "KEY_PAIR_PIN" in by_macro:
        issues.append("引用 KEY_PAIR_PIN：无配对键板写入时应同步改造 key_io")
    if "KEY_DPI_SUB_PIN" in by_macro or "KEY_DPI_ADD_PIN" in by_macro:
        issues.append("引用 KEY_DPI_SUB/ADD：单 DPI 脚板应改为 KEY_DPI_PIN")
    if "LED_R_PIN" in by_macro and "LEDC_PIN" in by_macro:
        issues.append("同时发现 LED_R_PIN 与 LEDC_PIN：RGB 与 LEDC 路径可能混用")

    # 从 user_config 抽脚位，检查 LEDC_SEL 与滚轮互斥（KC536→CH04 实战坑）
    uc = os.path.join(periph, "user_config.h")
    pin_map = _parse_user_config_pins(uc) if os.path.isfile(uc) else {}
    coll = _ledc_wheel_collision_from_pins(pin_map, periph)
    if coll:
        issues.append(coll)

    return {
        "ok": True,
        "roots": roots,
        "ref_count": total,
        "macros": {k: v[:30] for k, v in sorted(by_macro.items())},
        "macro_files": {k: sorted({x["file"] for x in v}) for k, v in sorted(by_macro.items())},
        "issues": issues,
        "pins": pin_map,
    }


LEDC_SEL_PINS = {"P01", "P05", "P21", "P33"}
LEDC_SEL_HINT = {
    "P01": "PMU_LEDC_SEL_IO_01",
    "P05": "PMU_LEDC_SEL_IO_05",
    "P21": "PMU_LEDC_SEL_IO_21",
    "P33": "PMU_LEDC_SEL_IO_33",
}


def _parse_user_config_pins(path: str) -> dict[str, str]:
    """解析 #define XXX_PIN (Pxx)。"""
    out: dict[str, str] = {}
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return out
    for m in re.finditer(
        r"#define\s+(KEY_\w+_PIN|WHEEL_[AB]_PIN|LEDC(?:_CTRL)?_PIN|MODE_\w+_PIN)\s+\(?\s*(P\d{2})\s*\)?",
        text,
    ):
        out[m.group(1)] = m.group(2)
    return out


def _infer_ledc_mux_pin(pins: dict[str, str], periph: str) -> tuple[str | None, str]:
    """
    推断硬件 LEDC_SEL 占用脚：优先 ledc.c 里的 PMU_LEDC_SEL_IO_xx，
    否则用 LEDC_PIN / LEDC_CTRL_PIN 中落在 {P01,P05,P21,P33} 的脚。
    """
    ledc_c = os.path.join(periph, "ledc.c")
    if os.path.isfile(ledc_c):
        try:
            body = open(ledc_c, encoding="utf-8", errors="replace").read()
        except OSError:
            body = ""
        m = re.search(r"PMU_LEDC_SEL_IO_(\d+)", body)
        if m:
            code = m.group(1).zfill(2)
            pin_by_code = {"01": "P01", "05": "P05", "21": "P21", "33": "P33"}
            pin = pin_by_code.get(code)
            if pin:
                return pin, f"ledc.c → {LEDC_SEL_HINT.get(pin, code)}"

    for key in ("LEDC_PIN", "LEDC_CTRL_PIN"):
        p = pins.get(key)
        if p in LEDC_SEL_PINS:
            return p, f"{key}={p}（可作 SEL）"
    return None, "未推断到 LEDC_SEL 脚"


def _ledc_wheel_collision_from_pins(pins: dict[str, str], periph: str) -> str | None:
    wa, wb = pins.get("WHEEL_A_PIN"), pins.get("WHEEL_B_PIN")
    if not (wa and wb):
        return None
    mux, src = _infer_ledc_mux_pin(pins, periph)
    if not mux:
        if pins.get("LEDC_PIN") or pins.get("LEDC_CTRL_PIN"):
            return (
                "已配置 LEDC 脚但无法推断 SEL；请确认 ledc.c 调用 "
                "drv_pmu_ledc_sel(PMU_LEDC_SEL_IO_xx)，且 xx 不与滚轮脚重叠"
            )
        return None
    if mux in (wa, wb):
        return (
            f"LEDC_SEL 占用 {mux}（{src}）与滚轮 {wa}/{wb} 冲突："
            f"会抢走编码器脚（典型：IO_01 抢 P01）。请改 SEL 到空闲的 "
            f"P05/P21/P33 之一，并同步改 ledc.c"
        )
    return None


def _find_sdk_root(periph: str) -> str | None:
    p = os.path.abspath(periph)
    for _ in range(8):
        if os.path.isdir(os.path.join(p, "hal")) and (
            os.path.isdir(os.path.join(p, "projects")) or os.path.isdir(os.path.join(p, "mode_24g"))
        ):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return None


def _file_contains(path: str, pattern: str) -> bool:
    if not os.path.isfile(path):
        return False
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    return re.search(pattern, text) is not None


def scan_port_checklist(project_hint: str, feat: dict | None = None) -> dict:
    """
    换板体检（吸收 KC536→CH04 经验）：扫 C/D/E 阶段常见缺口。
    不改文件，只出清单。feat 可传 logo_ledc / has_key_c0 等。
    """
    feat = feat or {}
    periph = os.path.abspath(project_hint)
    demo = os.path.dirname(periph)
    sdk = _find_sdk_root(periph)
    logo_ledc = bool(feat.get("logo_ledc", True))
    has_key_c0 = bool(feat.get("has_key_c0", True))

    items: list[dict] = []

    def add(item_id: str, stage: str, level: str, title: str, ok: bool, detail: str = ""):
        items.append(
            {
                "id": item_id,
                "stage": stage,
                "level": level if not ok else "ok",
                "title": title,
                "pass": ok,
                "detail": detail,
            }
        )

    # —— C 业务骨架 ——
    for name in ("ledc.c", "ledc.h", "ledc_mode.c", "ledc_mode.h"):
        path = os.path.join(periph, name)
        ok = os.path.isfile(path)
        add(
            f"file_{name}",
            "C",
            "error" if logo_ledc else "info",
            f"存在 {name}",
            ok if logo_ledc else True,
            "" if ok else "LOGO=LEDC 时需从金机拷贝并加入 Keil",
        )

    poll_targets = [
        (os.path.join(demo, "main", "mouse_hw.c"), "mouse_hw 调用 ledc_polling"),
    ]
    if sdk:
        poll_targets.extend(
            [
                (os.path.join(sdk, "mode_24g", "main_24g.c"), "main_24g 调用 ledc_polling"),
                (os.path.join(sdk, "mode_usb", "main_usb.c"), "main_usb 调用 ledc_polling"),
            ]
        )
    else:
        add("sdk_root", "C", "warn", "定位 SDK 根目录", False, "未找到含 hal/ 的 SDK 根，跳过 mode_24g/usb 检查")

    for path, title in poll_targets:
        ok = _file_contains(path, r"\bledc_polling\s*\(")
        add(
            f"poll_{os.path.basename(path)}",
            "C",
            "error" if logo_ledc else "info",
            title,
            ok if logo_ledc else True,
            "" if ok else f"缺少 ledc_polling：{path}",
        )

    key_io = os.path.join(periph, "key_io.c")
    add(
        "ledc_mode_switch",
        "C",
        "warn",
        "key_io 含 ledc_mode_switch（组合键切灯效）",
        _file_contains(key_io, r"\bledc_mode_switch\s*\("),
        "" if _file_contains(key_io, r"\bledc_mode_switch\s*\(") else "组合键灯效依赖此函数",
    )
    add(
        "cmd_idle_cfg",
        "E",
        "warn",
        "改灯后使用 Cmd_Idle_Cfg（无线立即重载）",
        _file_contains(key_io, r"Cmd_Idle_Cfg")
        or _file_contains(
            os.path.join(sdk or "", "mode_usb", "hid_process.c") if sdk else "",
            r"Cmd_Idle_Cfg",
        ),
        "仅 ledc_write0 时，2.4G RF idle 未轮询会导致组合键「无响应」",
    )

    # —— D HAL / 工程 ——
    rte = os.path.join(demo, "config", "RTE_om6239.h")
    rte_ok = _file_contains(rte, r"#define\s+RTE_LEDC\s+1\b")
    add(
        "rte_ledc",
        "D",
        "error" if logo_ledc else "info",
        "RTE_LEDC=1",
        rte_ok if logo_ledc else True,
        "" if rte_ok else f"请打开 {rte}",
    )

    uv = os.path.join(demo, "keil5", "SE71M.uvprojx")
    if not os.path.isfile(uv):
        # 容错其它工程名
        keil5 = os.path.join(demo, "keil5")
        if os.path.isdir(keil5):
            for n in os.listdir(keil5):
                if n.lower().endswith(".uvprojx"):
                    uv = os.path.join(keil5, n)
                    break
    uv_ok = _file_contains(uv, r"ledc\.c") and _file_contains(uv, r"ledc_mode\.c")
    add(
        "uvproj_ledc",
        "D",
        "warn" if logo_ledc else "info",
        "Keil 工程包含 ledc.c / ledc_mode.c",
        uv_ok if logo_ledc else True,
        "" if uv_ok else f"检查 {uv}",
    )

    ledc_c = os.path.join(periph, "ledc.c")
    sel_ok = _file_contains(ledc_c, r"drv_pmu_ledc_sel\s*\(|PMU_LEDC_SEL_IO_")
    add(
        "drv_ledc_sel",
        "D",
        "warn" if logo_ledc else "info",
        "ledc.c 调用 drv_pmu_ledc_sel",
        sel_ok if logo_ledc else True,
        "" if sel_ok else "无 SEL 则灯带数据脚不会接到封装脚",
    )

    unlock_ok = False
    if sdk:
        for rel in (
            os.path.join("hal", "driver", "om6239", "drv_pmu.c"),
            os.path.join("hal", "driver", "om6239", "drv_pmu.h"),
            os.path.join("hal", "driver", "common", "drv_pmu.c"),
            os.path.join("hal", "driver", "common", "drv_pmu.h"),
        ):
            if _file_contains(os.path.join(sdk, rel), r"0x5A5A"):
                unlock_ok = True
                break
    add(
        "pinmux_unlock",
        "D",
        "warn" if logo_ledc else "info",
        "HAL 含 PINMUX 解锁 0x5A5A（drv_pmu_ledc_sel）",
        unlock_ok if logo_ledc else True,
        "" if unlock_ok else "写 LEDC SEL 前需解锁，否则选脚不生效",
    )

    pins = _parse_user_config_pins(os.path.join(periph, "user_config.h"))
    coll = _ledc_wheel_collision_from_pins(pins, periph)
    add(
        "ledc_wheel",
        "B/D",
        "error" if coll else "ok",
        "LEDC_SEL 与滚轮脚无冲突",
        coll is None,
        coll
        or (f"滚轮 {pins.get('WHEEL_A_PIN')}/{pins.get('WHEEL_B_PIN')}，SEL={_infer_ledc_mux_pin(pins, periph)[0]}"),
    )

    if has_key_c0:
        uc = (
            open(os.path.join(periph, "user_config.h"), encoding="utf-8", errors="replace").read()
            if os.path.isfile(os.path.join(periph, "user_config.h"))
            else ""
        )
        add(
            "key_c0",
            "B",
            "warn",
            "user_config 定义 KEY_C0_PIN（矩阵列）",
            "KEY_C0_PIN" in uc,
            "" if "KEY_C0_PIN" in uc else "CH04 类矩阵键需要 KEY_C0",
        )

    # RGB 板：明确不要求 ledc；若工程仍依赖 LEDC_PIN 动画则 warn
    if not logo_ledc:
        add(
            "rgb_no_ledc_required",
            "C",
            "ok",
            "RGB LOGO 板：不强制 ledc* 文件",
            True,
            "请用 board_pack 的 rgb_logo_pack，勿对 RGB 板跑 CH04 port_apply 整包",
        )
        ledc_pin_used = _file_contains(os.path.join(periph, "user_config.h"), r"#define\s+LEDC_PIN\b")
        add(
            "rgb_ledc_pin_absent",
            "B",
            "warn",
            "RGB 板 user_config 不宜再定义 LEDC_PIN",
            not ledc_pin_used,
            "" if not ledc_pin_used else "发现 LEDC_PIN：确认是否误用灯带脚位",
        )

    # —— 编译伴生契约（仅当 mouse_hw 实际调用时强制）——
    main_dir = os.path.join(demo, "main")
    mouse_h = os.path.join(main_dir, "mouse.h")
    mouse_hw = os.path.join(main_dir, "mouse_hw.c")
    sensor_h = os.path.join(periph, "sensor.h")
    lvd_h = os.path.join(periph, "lvd.h")

    decl_const = _file_contains(mouse_h, r"extern\s+const\s+char\s+mouse_name\s*\[")
    decl_rw = _file_contains(mouse_h, r"extern\s+char\s+mouse_name\s*\[")
    def_const = _file_contains(mouse_hw, r"\bconst\s+char\s+mouse_name\s*\[")
    def_rw = _file_contains(mouse_hw, r"(?:^|[\s;])char\s+mouse_name\s*\[")
    if def_rw and not def_const:
        mouse_ok = decl_rw and not decl_const
        add(
            "mouse_name_rw",
            "C",
            "error",
            "mouse_name 声明与定义同为可写（非 const）",
            mouse_ok,
            "" if mouse_ok else (f"mouse_hw.c 为 char mouse_name[]，但 mouse.h 仍为 const：{mouse_h}"),
        )
    elif def_const:
        mouse_ok = decl_const
        add(
            "mouse_name_rw",
            "C",
            "error",
            "mouse_name 声明与定义 const 一致",
            mouse_ok,
            "" if mouse_ok else f"定义带 const 但声明不一致：{mouse_h}",
        )

    hw_calls_deep = _file_contains(mouse_hw, r"\bsensor_deepsleep_wakeup\s*\(")
    deep_ok = _file_contains(sensor_h, r"\bsensor_deepsleep_wakeup\s*\(")
    if hw_calls_deep:
        add(
            "sensor_deepsleep_decl",
            "C",
            "error",
            "sensor.h 声明 sensor_deepsleep_wakeup",
            deep_ok,
            "" if deep_ok else f"mouse_hw 调用此函数，缺声明：{sensor_h}",
        )

    hw_calls_charg = _file_contains(mouse_hw, r"\bcharg_led_sleep_process\s*\(")
    charg_ok = _file_contains(lvd_h, r"\bcharg_led_sleep_process\s*\(")
    if hw_calls_charg:
        add(
            "charg_led_sleep_decl",
            "C",
            "error",
            "lvd.h 声明 charg_led_sleep_process",
            charg_ok,
            "" if charg_ok else f"mouse_hw 调用此函数，缺声明：{lvd_h}",
        )

    n_fail = sum(1 for i in items if not i["pass"] and i["level"] == "error")
    n_warn = sum(1 for i in items if not i["pass"] and i["level"] == "warn")
    return {
        "ok": True,
        "periph": periph,
        "sdk": sdk or "",
        "feat": {"logo_ledc": logo_ledc, "has_key_c0": has_key_c0},
        "summary": {"error": n_fail, "warn": n_warn, "total": len(items)},
        "items": items,
        "message": f"换板体检：error={n_fail} warn={n_warn}（共 {len(items)} 项）",
    }


def _backup_file(bak_dir: str, path: str) -> None:
    os.makedirs(bak_dir, exist_ok=True)
    shutil.copy2(path, os.path.join(bak_dir, os.path.basename(path)))


def _patch_key_io_h(text: str, feat: dict) -> tuple[str, list[str]]:
    notes: list[str] = []
    has_dpi_pair = bool(feat.get("has_dpi_pair"))
    has_extra = bool(feat.get("has_extra_keys"))

    block = (
        "#define KEY_MODE_R0         (OM_GPIO0->DATA & (1<<KEY_R0_PIN))\n"
        "#define KEY_MODE_R1         (OM_GPIO0->DATA & (1<<KEY_R1_PIN))\n"
        "#define KEY_MODE_R2         (OM_GPIO0->DATA & (1<<KEY_R2_PIN))\n"
        "#ifdef KEY_B_PIN\n"
        "#define KEY_MODE_R3         (OM_GPIO0->DATA & (1<<KEY_B_PIN))\n"
        "#else\n"
        "#define KEY_MODE_R3         (1)\n"
        "#endif\n"
        "#ifdef KEY_P_PIN\n"
        "#define KEY_MODE_R4         (OM_GPIO0->DATA & (1<<KEY_P_PIN))\n"
        "#else\n"
        "#define KEY_MODE_R4         (1)\n"
        "#endif\n"
        "#if defined(KEY_DPI_SUB_PIN)\n"
        "#define KEY_MODE_R5         (OM_GPIO0->DATA & (1<<KEY_DPI_SUB_PIN))\n"
        "#elif defined(KEY_DPI_PIN)\n"
        "#define KEY_MODE_R5         (OM_GPIO0->DATA & (1<<KEY_DPI_PIN))\n"
        "#else\n"
        "#define KEY_MODE_R5         (1)\n"
        "#endif\n"
        "#if defined(KEY_DPI_ADD_PIN)\n"
        "#define KEY_MODE_R7         (OM_GPIO0->DATA & (1<<KEY_DPI_ADD_PIN))\n"
        "#elif defined(KEY_DPI_PIN)\n"
        "#define KEY_MODE_R7         (OM_GPIO0->DATA & (1<<KEY_DPI_PIN))\n"
        "#else\n"
        "#define KEY_MODE_R7         (1)\n"
        "#endif\n"
        "#ifdef KEY_PAIR_PIN\n"
        "#define KEY_MODE_PAIR       (OM_GPIO0->DATA & (1<<KEY_PAIR_PIN))\n"
        "#else\n"
        "#define KEY_MODE_PAIR       (1)\n"
        "#endif"
    )
    pat = re.compile(
        r"#define\s+KEY_MODE_R0\s+\(OM_GPIO0->DATA\s*&\s*\(1<<KEY_R0_PIN\)\)\s*\n"
        r"#define\s+KEY_MODE_R1\s+\(OM_GPIO0->DATA\s*&\s*\(1<<KEY_R1_PIN\)\)\s*\n"
        r"#define\s+KEY_MODE_R2\s+\(OM_GPIO0->DATA\s*&\s*\(1<<KEY_R2_PIN\)\)\s*\n"
        r"[\s\S]*?"
        r"#define\s+KEY_MODE_PAIR\s+\([^\n]+\)",
        re.M,
    )
    if "#ifdef KEY_B_PIN" not in text and "KEY_MODE_R0" in text:
        new, n = pat.subn(block, text, count=1)
        if n:
            text = new
            notes.append("KEY_MODE_* → #ifdef 侧键/DPI/PAIR（防缺宏）")

    if has_extra and not has_dpi_pair:
        new, n1 = re.subn(
            r"#define\s+KEY_MODE_R5\s+\(OM_GPIO0->DATA\s*&\s*\(1<<KEY_DPI_SUB_PIN\)\)",
            "#define KEY_MODE_R5         (OM_GPIO0->DATA & (1<<KEY_DPI_PIN))",
            text,
            count=1,
        )
        if n1:
            text = new
            notes.append("KEY_MODE_R5: KEY_DPI_SUB_PIN → KEY_DPI_PIN")
        new, n2 = re.subn(
            r"#define\s+KEY_MODE_R7\s+\(OM_GPIO0->DATA\s*&\s*\(1<<KEY_DPI_ADD_PIN\)\)",
            "#define KEY_MODE_R7         (OM_GPIO0->DATA & (1<<KEY_DPI_PIN))",
            text,
            count=1,
        )
        if n2:
            text = new
            notes.append("KEY_MODE_R7: KEY_DPI_ADD_PIN → KEY_DPI_PIN")

    return text, notes


def _patch_key_io_c(text: str, feat: dict) -> tuple[str, list[str]]:
    notes: list[str] = []
    has_pair = bool(feat.get("has_key_pair"))
    has_key_c0 = bool(feat.get("has_key_c0"))
    mode_dual = bool(feat.get("mode_dual"))
    mode_single = bool(feat.get("mode_single"))

    if has_key_c0 and "gpio_dir_in(KEY_C0_PIN)" not in text:
        matrix_scan = (
            "void key_io_scan(void)\n"
            "{\n"
            "    key_status = 0;\n"
            "\n"
            "    /* PinMux sync: 矩阵列 KEY_C0 */\n"
            "    gpio_dir_in(KEY_C0_PIN);\n"
            "    gpio_set_pu(KEY_C0_PIN, PU_30K);\n"
            "    delayus(3);\n"
            "    if (gpio_read(KEY_C0_PIN))\n"
            "    {\n"
            "        if(0 == KEY_MODE_R0)\n"
            "            key_status |= bkey_l;\n"
            "        if(0 == KEY_MODE_R1)\n"
            "            key_status |= bkey_r;\n"
            "        if(0 == KEY_MODE_R2)\n"
            "            key_status |= bkey_m;\n"
            "    }\n"
            "\n"
            "    gpio_dir_out(KEY_C0_PIN);\n"
            "    gpio_clear(KEY_C0_PIN);\n"
            "    delayus(3);\n"
            "    if(0 == KEY_MODE_R0 && !(key_status & bkey_l))\n"
            "        key_status |= bkey_4;\n"
            "    if(0 == KEY_MODE_R1 && !(key_status & bkey_r))\n"
            "        key_status |= bkey_5;\n"
            "    if(0 == KEY_MODE_R2 && !(key_status & bkey_m))\n"
            "        key_status |= bkey_dpi;\n"
            "#ifdef KEY_PAIR_PIN\n"
            "    if(0 == KEY_MODE_PAIR)\n"
            "        key_status |= bkey_pair;\n"
            "#endif\n"
            "}"
        )
        pat = re.compile(r"void\s+key_io_scan\s*\(\s*void\s*\)\s*\{[\s\S]*?\n\}", re.M)
        new, n = pat.subn(matrix_scan, text, count=1)
        if n:
            text = new
            notes.append("key_io_scan: 独立侧键 → KEY_C0 矩阵扫描")

    if not has_pair and "gpio_dir_in(KEY_C0_PIN)" not in text:
        pat = re.compile(
            r"(^[ \t]*if\s*\(\s*0\s*==\s*KEY_MODE_PAIR\s*\)\s*\n"
            r"[ \t]*key_status\s*\|\=\s*bkey_pair\s*;)",
            re.M,
        )
        already = re.search(
            r"#ifdef KEY_PAIR_PIN\s*\n\s*if\s*\(\s*0\s*==\s*KEY_MODE_PAIR",
            text,
        )
        if not already:
            new, n = pat.subn(
                "#ifdef KEY_PAIR_PIN\n    if(0 == KEY_MODE_PAIR)\n        key_status |= bkey_pair;\n#endif",
                text,
                count=1,
            )
            if n:
                text = new
                notes.append("key_io_scan: PAIR 判断加 #ifdef")

    if mode_dual:
        dual_block = (
            "device_type_t device_temp;\n"
            "\n"
            "    /* PinMux sync: 双模式脚 MODE_24G / MODE_BLE */\n"
            "    if (gpio_read(MODE_24G_PIN))\n"
            "    {\n"
            "        device_temp = iDEVICE_TYPE_24G;\n"
            "    }\n"
            "    else\n"
            "    {\n"
            "        if (bt_index == 0)\n"
            "            device_temp = iDEVICE_TYPE_BT0;\n"
            "        else if (bt_index == 1)\n"
            "            device_temp = iDEVICE_TYPE_BT1;\n"
            "        else\n"
            "            device_temp = iDEVICE_TYPE_BT2;\n"
            "    }"
        )
        pat = re.compile(
            r"device_type_t\s+device_temp\s*;\s*"
            r"(?:/\*[^*]*\*/\s*)*"
            r"if\s*\(\s*MODE_BLE_CHECK\s*==\s*gpio_read\s*\(\s*MODE_BLE_24G_PIN\s*\)\s*\)\s*"
            r"\{[\s\S]*?\}\s*"
            r"else\s*(?://[^\n]*)?\s*"
            r"\{[\s\S]*?device_temp\s*=\s*iDEVICE_TYPE_24G\s*;[\s\S]*?\}",
            re.M,
        )
        new, n = pat.subn(dual_block, text, count=1)
        if n:
            text = new
            notes.append("scan_mode_swtich: MODE_BLE_24G → 双模式脚")
        elif "MODE_BLE_24G_PIN" in text and "gpio_read(MODE_24G_PIN)" not in text:
            notes.append("warn: 未能自动改写 scan_mode_swtich（请人工核对）")

    if mode_single:
        single_block = (
            "device_type_t device_temp;\n"
            "\n"
            "    /* PinMux sync: 单模式脚 MODE_BLE_24G */\n"
            "    if(MODE_BLE_CHECK == gpio_read(MODE_BLE_24G_PIN))\n"
            "    {\n"
            "        if(bt_index == 0)\n"
            "            device_temp = iDEVICE_TYPE_BT0;\n"
            "        else if(bt_index == 1)\n"
            "            device_temp = iDEVICE_TYPE_BT1;\n"
            "        else\n"
            "            device_temp = iDEVICE_TYPE_BT2;\n"
            "    }\n"
            "    else\n"
            "    {\n"
            "        device_temp = iDEVICE_TYPE_24G;\n"
            "    }"
        )
        pat = re.compile(
            r"device_type_t\s+device_temp\s*;\s*"
            r"(?:/\*[^*]*\*/\s*)*"
            r"if\s*\(\s*gpio_read\s*\(\s*MODE_24G_PIN\s*\)\s*\)\s*"
            r"\{[\s\S]*?iDEVICE_TYPE_24G[\s\S]*?\}\s*"
            r"else\s*"
            r"\{[\s\S]*?bt_index[\s\S]*?\}",
            re.M,
        )
        new, n = pat.subn(single_block, text, count=1)
        if n:
            text = new
            notes.append("scan_mode_swtich: 双模式脚 → MODE_BLE_24G")
        else:
            # S205 三档拨杆结构（uint8_t ble_low / g24_low + if/else 链）：
            # 单脚工程没配 MODE_BLE_PIN/MODE_24G_PIN，必须改回单脚 MODE_BLE_24G。
            pat3 = re.compile(
                r"[ \t]*uint8_t\s+ble_low\s*=[\s\S]*?"
                r"默认 2\.4G[\s\S]*?\}",
                re.M,
            )
            single3 = (
                "    /* PinMux sync: 单模式脚 MODE_BLE_24G */\n"
                "    if(MODE_BLE_CHECK == gpio_read(MODE_BLE_24G_PIN))\n"
                "    {\n"
                "        if(bt_index == 0)\n"
                "            device_temp = iDEVICE_TYPE_BT0;\n"
                "        else if(bt_index == 1)\n"
                "            device_temp = iDEVICE_TYPE_BT1;\n"
                "        else\n"
                "            device_temp = iDEVICE_TYPE_BT2;\n"
                "    }\n"
                "    else\n"
                "    {\n"
                "        device_temp = iDEVICE_TYPE_24G;\n"
                "    }"
            )
            new, n3 = pat3.subn(single3, text, count=1)
            if n3:
                text = new
                notes.append("scan_mode_swtich: S205 三档拨杆 → 单脚 MODE_BLE_24G")

    return text, notes


def _patch_sleep_c(text: str, feat: dict) -> tuple[str, list[str]]:
    notes: list[str] = []
    mode_dual = bool(feat.get("mode_dual"))
    mode_single = bool(feat.get("mode_single"))

    dual_sleep = (
        "if (gpio_read(MODE_24G_PIN))\n"
        "        gpio_set_pu(MODE_24G_PIN, PU_30K);\n"
        "    else\n"
        "        gpio_set_pd(MODE_24G_PIN);\n"
        "    if (gpio_read(MODE_BLE_PIN))\n"
        "        gpio_set_pu(MODE_BLE_PIN, PU_30K);\n"
        "    else\n"
        "        gpio_set_pd(MODE_BLE_PIN);"
    )
    single_sleep = (
        "if(MODE_BLE_CHECK == gpio_read(MODE_BLE_24G_PIN))\n"
        "        gpio_set_pd(MODE_BLE_24G_PIN);\n"
        "    else\n"
        "        gpio_set_pu(MODE_BLE_24G_PIN,PU_30K);"
    )

    if mode_dual:
        pat = re.compile(
            r"if\s*\(\s*MODE_BLE_CHECK\s*==\s*gpio_read\s*\(\s*MODE_BLE_24G_PIN\s*\)\s*\)\s*\n"
            r"[ \t]*gpio_set_pd\s*\(\s*MODE_BLE_24G_PIN\s*\)\s*;\s*\n"
            r"[ \t]*else\s*\n"
            r"[ \t]*gpio_set_pu\s*\(\s*MODE_BLE_24G_PIN\s*,\s*PU_30K\s*\)\s*;",
            re.M,
        )
        new, n = pat.subn(dual_sleep, text, count=1)
        if n:
            text = new
            notes.append("periph_gpio_sleep_set: 单模式 sleep → 双模式脚")

    if mode_single:
        pat = re.compile(
            r"if\s*\(\s*gpio_read\s*\(\s*MODE_24G_PIN\s*\)\s*\)\s*\n"
            r"[ \t]*gpio_set_pu\s*\(\s*MODE_24G_PIN\s*,\s*PU_30K\s*\)\s*;\s*\n"
            r"[ \t]*else\s*\n"
            r"[ \t]*gpio_set_pd\s*\(\s*MODE_24G_PIN\s*\)\s*;\s*\n"
            r"[ \t]*if\s*\(\s*gpio_read\s*\(\s*MODE_BLE_PIN\s*\)\s*\)\s*\n"
            r"[ \t]*gpio_set_pu\s*\(\s*MODE_BLE_PIN\s*,\s*PU_30K\s*\)\s*;\s*\n"
            r"[ \t]*else\s*\n"
            r"[ \t]*gpio_set_pd\s*\(\s*MODE_BLE_PIN\s*\)\s*;",
            re.M,
        )
        new, n = pat.subn(single_sleep, text, count=1)
        if n:
            text = new
            notes.append("periph_gpio_sleep_set: 双模式 sleep → 单模式脚")

    return text, notes


def _sync_rte_ledc(periph: str, feat: dict, bak_dir: str) -> tuple[list[dict], list[str]]:
    """LOGO=LEDC 时打开 config/RTE_om6239.h 的 RTE_LEDC，否则驱动头文件为空壳。"""
    actions: list[dict] = []
    written: list[str] = []
    if not feat.get("logo_ledc"):
        return actions, written

    rte = os.path.join(os.path.dirname(periph), "config", "RTE_om6239.h")
    if not os.path.isfile(rte):
        actions.append(
            {
                "file": "RTE_om6239.h",
                "rule": "warn",
                "detail": "未找到 config/RTE_om6239.h，无法打开 RTE_LEDC",
                "applied": False,
            }
        )
        return actions, written

    try:
        old = open(rte, encoding="utf-8", errors="replace").read()
    except OSError as e:
        actions.append(
            {
                "file": "RTE_om6239.h",
                "rule": "error",
                "detail": str(e),
                "applied": False,
            }
        )
        return actions, written

    new, n = re.subn(
        r"(#define\s+RTE_LEDC\s+)\d+",
        r"\g<1>1",
        old,
        count=1,
    )
    if n and new != old:
        _backup_file(bak_dir, rte)
        open(rte, "w", encoding="utf-8", newline="\n").write(new)
        written.append(rte)
        actions.append(
            {
                "file": "RTE_om6239.h",
                "rule": "patch",
                "detail": "RTE_LEDC → 1（启用 drv_ledc 类型/API）",
                "applied": True,
            }
        )
    else:
        actions.append(
            {
                "file": "RTE_om6239.h",
                "rule": "noop",
                "detail": "RTE_LEDC 已为 1 或未匹配到宏",
                "applied": False,
            }
        )
    return actions, written


def _sync_logo_ledc(periph: str, feat: dict, bak_dir: str) -> tuple[list[dict], list[str]]:
    actions: list[dict] = []
    written: list[str] = []
    if not feat.get("logo_ledc"):
        return actions, written

    led_c = os.path.join(periph, "led.c")
    ledc_c = os.path.join(periph, "ledc.c")
    if os.path.isfile(led_c):
        try:
            body = open(led_c, encoding="utf-8", errors="replace").read()
        except OSError:
            body = ""
        if "LED_R_PIN" in body and not os.path.isfile(ledc_c):
            actions.append(
                {
                    "file": "led.c",
                    "rule": "warn",
                    "detail": "LOGO=LEDC 但 led.c 仍引用 LED_R/G/B 且无 ledc.c：需从金标准拷贝 ledc* 并改 Keil 工程",
                    "applied": False,
                }
            )

    golden = (feat.get("golden_periph") or "").strip()
    if not golden or not os.path.isdir(golden):
        return actions, written

    for name in ("led.c", "led.h", "ledc.c", "ledc.h", "ledc_mode.c", "ledc_mode.h"):
        src = os.path.join(golden, name)
        dst = os.path.join(periph, name)
        if not os.path.isfile(src):
            continue
        need = not os.path.isfile(dst)
        if not need and name == "led.c":
            try:
                need = "LED_R_PIN" in open(dst, encoding="utf-8", errors="replace").read()
            except OSError:
                need = False
        if need:
            if os.path.isfile(dst):
                _backup_file(bak_dir, dst)
            shutil.copy2(src, dst)
            written.append(dst)
            actions.append(
                {
                    "file": name,
                    "rule": "copy",
                    "detail": f"从金标准拷贝 {name}",
                    "applied": True,
                }
            )
    return actions, written


def plan_board_contracts(periph: str, feat: dict) -> list[tuple[str, str]]:
    """只计算不写盘：返回按板型需要改写的源码 [(绝对路径, 新内容)]。

    供生成管线把源码改写纳入同一个 FileTransaction，保证回滚一致。
    仅覆盖 key_io.h / key_io.c 两份 generator 不生成的板型契约源码；
    user_config.c 的 GPIO 表与 sleep 段由 generator.build_outputs 按当前 pins 生成，
    不在这里改写（否则会用旧骨架文本覆盖生成结果）。
    LEDC 文件注入由 plugins 链路单独负责，不在这里重复。
    """
    planned: list[tuple[str, str]] = []
    targets = [
        (os.path.join(periph, "key_io.h"), _patch_key_io_h),
        (os.path.join(periph, "key_io.c"), _patch_key_io_c),
    ]
    for path, patcher in targets:
        if not os.path.isfile(path):
            continue
        try:
            old = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        new, _notes = patcher(old, feat)
        if new != old:
            planned.append((path, new))
    return planned


def sync_board_contracts(periph: str, feat: dict, bak_dir: str) -> dict:
    """按板型同步 key_io / sleep /（可选）LEDC 文件契约。"""
    actions: list[dict] = []
    written: list[str] = []

    targets = [
        ("key_io.h", os.path.join(periph, "key_io.h"), _patch_key_io_h),
        ("key_io.c", os.path.join(periph, "key_io.c"), _patch_key_io_c),
        ("user_config.c", os.path.join(periph, "user_config.c"), _patch_sleep_c),
    ]

    for label, path, patcher in targets:
        if not os.path.isfile(path):
            actions.append(
                {
                    "file": label,
                    "rule": "skip",
                    "detail": "文件不存在",
                    "applied": False,
                }
            )
            continue
        try:
            old = open(path, encoding="utf-8", errors="replace").read()
        except OSError as e:
            actions.append(
                {
                    "file": label,
                    "rule": "error",
                    "detail": str(e),
                    "applied": False,
                }
            )
            continue
        new, notes = patcher(old, feat)
        if new != old:
            _backup_file(bak_dir, path)
            open(path, "w", encoding="utf-8", newline="\n").write(new)
            written.append(path)
            for n in notes:
                actions.append(
                    {
                        "file": label,
                        "rule": "patch",
                        "detail": n,
                        "applied": True,
                    }
                )
        else:
            actions.append(
                {
                    "file": label,
                    "rule": "noop",
                    "detail": "无需改写或未匹配到可替换模板",
                    "applied": False,
                }
            )

    logo_actions, logo_written = _sync_logo_ledc(periph, feat, bak_dir)
    actions.extend(logo_actions)
    written.extend(logo_written)

    rte_actions, rte_written = _sync_rte_ledc(periph, feat, bak_dir)
    actions.extend(rte_actions)
    written.extend(rte_written)

    return {"ok": True, "actions": actions, "written": written}
