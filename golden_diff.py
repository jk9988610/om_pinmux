# -*- coding: utf-8 -*-
"""
金机 / 目标工程目录对比（换板 A/B/C）。

- 默认：对本工具关心的相对路径做 hash 清单（SAME / DIFF / 仅金机 / 仅目标）
- 若本机有 E:\\tools\\compare：可调用其 engine 导出 unified .diff，或 --gui 打开并排对比
- 不替代完整目录对比 GUI；深度看行级差异仍建议用「打开目录对比」
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from datetime import datetime

# 换板时最常对照的相对路径（相对 SDK 根）
PORT_FOCUS_RELS = [
    # A/B 脚位与契约
    "projects/mouse_demo/periph/user_config.h",
    "projects/mouse_demo/periph/user_config.c",
    "projects/mouse_demo/periph/key_io.h",
    "projects/mouse_demo/periph/key_io.c",
    "projects/mouse_demo/config/RTE_om6239.h",
    # C 灯效 / 主循环
    "projects/mouse_demo/periph/led.c",
    "projects/mouse_demo/periph/led.h",
    "projects/mouse_demo/periph/ledc.c",
    "projects/mouse_demo/periph/ledc.h",
    "projects/mouse_demo/periph/ledc_mode.c",
    "projects/mouse_demo/periph/ledc_mode.h",
    "projects/mouse_demo/main/main.c",
    "projects/mouse_demo/main/main.h",
    "projects/mouse_demo/main/mouse_hw.c",
    "projects/mouse_demo/main/mouse.h",  # 伴生：mouse_name 声明须与 mouse_hw.c 可写一致
    "projects/mouse_demo/main/ex2_app_mouse.c",
    "projects/mouse_demo/flash/flash_process.c",
    "projects/mouse_demo/periph/lvd.c",
    "projects/mouse_demo/periph/lvd.h",  # 伴生：charg_led_sleep_process 等声明
    "projects/mouse_demo/periph/mode_ind.c",
    "projects/mouse_demo/periph/sensor.c",
    "projects/mouse_demo/periph/sensor.h",  # 伴生：sensor_deepsleep_wakeup 等声明
    "projects/mouse_demo/periph/sensor_type_check.c",  # 传感器变体/初始化表（compare6）
    "projects/mouse_demo/periph/sensor_type_check.h",
    # 模式
    "mode_24g/main_24g.c",
    "mode_24g/sleep.c",
    "mode_24g/sleep.h",
    "mode_24g/rf_data_process.c",
    "mode_24g/rf_data_process.h",  # 伴生：回调声明签名（compare6）
    "mode_usb/main_usb.c",
    "mode_usb/hid_process.c",
    "mode_usb/usb_user_process.c",  # USB 鼠标发送 flag 时机（compare6 功能项）
    # D HAL（LEDC SEL / 解锁 / senscan 位宽）
    "hal/driver/om6239/drv_ledc.c",
    "hal/driver/om6239/drv_ledc.h",
    "hal/driver/om6239/drv_pmu.c",
    "hal/driver/om6239/drv_pmu.h",
    "hal/driver/om6239/drv_isr.c",
    "hal/driver/om6239/drv_senscan.c",  # DATA_FORMAT 12bit（compare6）
    "hal/device/om6239/ARM/om6239_ac6.sct",  # 栈大小（compare6）
]

DEFAULT_COMPARE_ROOTS = [
    r"E:\tools\compare",
    os.path.join(os.path.expanduser("~"), "tools", "compare"),
]


def find_sdk_root(hint: str) -> str | None:
    hint = os.path.abspath(hint)
    # periph -> mouse_demo -> projects -> sdk
    if os.path.basename(hint).lower() == "periph":
        demo = os.path.dirname(hint)
        projects = os.path.dirname(demo)
        if os.path.basename(projects).lower() == "projects":
            return os.path.dirname(projects)
    p = hint
    for _ in range(8):
        if os.path.isdir(os.path.join(p, "hal")) and (
            os.path.isdir(os.path.join(p, "projects"))
            or os.path.isdir(os.path.join(p, "mode_24g"))
        ):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return None


def find_compare_tool(explicit: str = "") -> str:
    if explicit and os.path.isfile(os.path.join(explicit, "compare.py")):
        return os.path.abspath(explicit)
    env = (os.environ.get("OM_COMPARE_ROOT") or "").strip()
    if env and os.path.isfile(os.path.join(env, "compare.py")):
        return os.path.abspath(env)
    for root in DEFAULT_COMPARE_ROOTS:
        if os.path.isfile(os.path.join(root, "compare.py")):
            return os.path.abspath(root)
    return ""


def _file_sha1(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def inventory_focus(golden_sdk: str, target_sdk: str, extra_rels: list[str] | None = None) -> dict:
    """关注文件清单对比（不依赖 compare 工具）。"""
    golden_sdk = os.path.abspath(golden_sdk)
    target_sdk = os.path.abspath(target_sdk)
    rels = list(PORT_FOCUS_RELS)
    if extra_rels:
        for r in extra_rels:
            r = r.replace("\\", "/").lstrip("/")
            if r not in rels:
                rels.append(r)

    same, diff, only_g, only_t, missing_both = [], [], [], [], []
    for rel in rels:
        rel_n = rel.replace("\\", "/")
        pg = os.path.join(golden_sdk, *rel_n.split("/"))
        pt = os.path.join(target_sdk, *rel_n.split("/"))
        hg, ht = _file_sha1(pg), _file_sha1(pt)
        if hg is None and ht is None:
            missing_both.append(rel_n)
        elif hg is None:
            only_t.append(rel_n)
        elif ht is None:
            only_g.append(rel_n)
        elif hg == ht:
            same.append(rel_n)
        else:
            diff.append(rel_n)

    return {
        "ok": True,
        "golden_sdk": golden_sdk,
        "target_sdk": target_sdk,
        "summary": {
            "same": len(same),
            "diff": len(diff),
            "only_golden": len(only_g),
            "only_target": len(only_t),
            "listed": len(rels),
        },
        "same": same,
        "diff": diff,
        "only_golden": only_g,
        "only_target": only_t,
        "not_in_either": missing_both,
        "message": (
            f"关注文件: SAME={len(same)} DIFF={len(diff)} "
            f"仅金机={len(only_g)} 仅目标={len(only_t)}"
        ),
    }


# biz_sync 故意改写后允许与金机字节不一致（验收时不算失败）
EXPECTED_FOCUS_DIFF_RELS = {
    "projects/mouse_demo/periph/key_io.h",  # #ifdef 包侧键/DPI/PAIR
}


def format_inventory_text(inv: dict) -> str:
    if not inv or not inv.get("ok"):
        return (inv or {}).get("message") or "无对比结果"
    lines = [
        "=== 金机关注文件对比（非全文树）===",
        f"金机(参照): {inv.get('golden_sdk')}",
        f"目标(修改): {inv.get('target_sdk')}",
        inv.get("message", ""),
        "",
        "说明: SAME=字节一致  DIFF=两边都有但不同  仅金机=目标缺文件(优先补)  仅目标=金机没有",
        "验收: 关注清单 + Keil 编译 + 实机冒烟；不以全文树 .diff 为成败判据。",
        "预期 DIFF: key_io.h（biz_sync #ifdef）。其它关注 DIFF / 仅金机 → 先查拷贝。",
        "",
    ]
    s = inv.get("summary") or {}
    lines.append(
        f"统计: same={s.get('same')} diff={s.get('diff')} "
        f"only_golden={s.get('only_golden')} only_target={s.get('only_target')}"
    )
    if inv.get("only_golden"):
        lines.append("\n--- 仅金机有（目标可能要拷） ---")
        lines.extend(f"  + {r}" for r in inv["only_golden"])
    if inv.get("diff"):
        lines.append("\n--- 两边不同 ---")
        for r in inv["diff"]:
            note = "（预期：biz_sync）" if r in EXPECTED_FOCUS_DIFF_RELS else "（建议目录对比看行级）"
            lines.append(f"  ~ {r}  {note}")
    if inv.get("only_target"):
        lines.append("\n--- 仅目标有 ---")
        lines.extend(f"  - {r}" for r in inv["only_target"])
    if inv.get("same"):
        lines.append(f"\n--- SAME ({len(inv['same'])}) ---")
        for r in inv["same"][:40]:
            lines.append(f"  = {r}")
        if len(inv["same"]) > 40:
            lines.append(f"  ... 另有 {len(inv['same']) - 40} 个相同")
    lines.append(
        "\n全文树 diff：uvoptx/gitignore 噪音、startup 产品字、USB 描述符字符串、"
        "FCC 指示灯等仍可不强行抹平；"
        "但 drv_senscan/usb_user_process/sensor_type_check/栈散列表等已进关注面，应 SAME。"
    )
    lines.append(
        "深度行级 diff：点「打开目录对比」调用 E:\\tools\\compare，"
        "或「导出换板.diff」。"
    )
    return "\n".join(lines)


def open_compare_gui(
    golden_sdk: str,
    target_sdk: str,
    compare_root: str = "",
) -> dict:
    """
    启动目录对比 GUI。
    约定: dir_a=金机(参照/左), dir_b=目标(正在改/右)
    """
    tool = find_compare_tool(compare_root)
    if not tool:
        return {
            "ok": False,
            "message": "未找到 E:\\tools\\compare（可设环境变量 OM_COMPARE_ROOT）",
        }
    compare_py = os.path.join(tool, "compare.py")
    try:
        subprocess.Popen(
            [sys.executable, compare_py, "--gui", golden_sdk, target_sdk],
            cwd=tool,
            close_fds=True,
        )
        return {
            "ok": True,
            "message": f"已启动目录对比\n左(金机)={golden_sdk}\n右(目标)={target_sdk}",
            "compare_root": tool,
        }
    except OSError as e:
        return {"ok": False, "message": str(e)}


def export_unified_diff(
    golden_sdk: str,
    target_sdk: str,
    out_path: str,
    compare_root: str = "",
    ignore_whitespace: bool = True,
) -> dict:
    """用 compare.engine 导出全文 unified diff（与手动 compare 一致）。"""
    tool = find_compare_tool(compare_root)
    if not tool:
        return {
            "ok": False,
            "message": "未找到 compare 工具，无法导出行级 .diff；请安装/指定 E:\\tools\\compare",
        }
    if tool not in sys.path:
        sys.path.insert(0, tool)
    try:
        from engine import compute_diff  # type: ignore
        from export import export_unified_diff as _export  # type: ignore
    except ImportError as e:
        return {"ok": False, "message": f"导入 compare.engine 失败: {e}"}

    from pathlib import Path

    result = compute_diff(
        Path(golden_sdk),
        Path(target_sdk),
        ignore_whitespace=ignore_whitespace,
        ignore_comments=False,
    )
    if result.error:
        return {"ok": False, "message": result.error}
    try:
        _export(
            result,
            Path(out_path),
            ignore_whitespace=ignore_whitespace,
            ignore_comments=False,
        )
    except Exception as e:
        return {"ok": False, "message": str(e)}

    inv = inventory_focus(golden_sdk, target_sdk)
    summary_path = out_path + ".focus.txt"
    try:
        open(summary_path, "w", encoding="utf-8").write(format_inventory_text(inv))
    except OSError:
        summary_path = ""

    return {
        "ok": True,
        "message": f"已导出 {out_path}" + (f"\n关注摘要: {summary_path}" if summary_path else ""),
        "path": out_path,
        "focus_summary": summary_path,
        "inventory": inv,
        "change_count": len(result.changes),
    }


def default_export_path(target_sdk: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if os.path.isdir("F:\\"):
        return os.path.join("F:\\", f"pinmux_port_{stamp}.diff")
    base = os.path.dirname(target_sdk.rstrip("\\/")) or target_sdk
    return os.path.join(base, f"pinmux_port_{stamp}.diff")
