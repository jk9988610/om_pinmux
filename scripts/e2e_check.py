#!/usr/bin/env python3
"""一键端到端验收：真实 Api 从零建工程 → 写盘 → Keil 全量重编。

用法：
    python scripts/e2e_check.py                 # 默认在临时目录产出，跑完保留供检查
    python scripts/e2e_check.py --out D:\\e2e    # 指定输出根目录
    python scripts/e2e_check.py --no-keil        # 只验证生成产物，不编译
    python scripts/e2e_check.py --keep           # 保留工程（默认也保留，便于 Keil 复现）

依赖：Python 3.10+；Keil 编译可选（UV4 路径可用 OMCFG_UV4 覆盖）。
不依赖 pywebview / jsdom / node_modules——纯后端 Api，可进 CI。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from omcfg.api import Api  # noqa: E402

BUILD_MACROS = (
    "WHEEL_A_PIN", "WHEEL_B_PIN",
    "LED_R_PIN", "LED_G_PIN", "LED_B_PIN",
    "LEDC_PIN", "LEDC_CTRL_PIN",
)


def line(msg: str = "") -> None:
    print(msg, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="om_pinmux 一键端到端验收")
    ap.add_argument("--out", default="", help="输出根目录（默认系统临时目录）")
    ap.add_argument("--no-keil", action="store_true", help="跳过 Keil 编译")
    ap.add_argument("--name", default="E2E_Check", help="工程名")
    args = ap.parse_args()

    base = Path(args.out).resolve() if args.out else Path(tempfile.gettempdir()) / "om_pinmux_e2e"
    sdk = str(base / args.name)
    if Path(sdk).exists():
        line(f"✕ 目标已存在，先删除或换 --out/--name: {sdk}")
        return 2

    api = Api()
    steps = [
        ("建空白工程", lambda: api.blank_new(args.name, sdk, id_low=0x0701)),
        ("启用 LEDC 插件", lambda: api.plugin_toggle(sdk, "ledc", True)),
        ("一键按推荐配脚（含契约协调）", lambda: api.blank_fill_recommended(sdk)),
        ("生成预览 diff", lambda: api.preview(sdk)),
        ("写盘生成", lambda: api.blank_apply(sdk)),
    ]
    line(f"工程目录: {sdk}\n")
    for label, fn in steps:
        r = fn()
        if not r or not r.get("ok"):
            line(f"✕ {label} 失败: {r}")
            return 1
        detail = ""
        if r.get("changed"):
            detail = f"（变更 {r['changed']} 处）"
        if label == "启用 LEDC 插件" and r.get("files", {}).get("copied"):
            detail = f"（注入 {len(r['files']['copied'])} 文件）"
        line(f"✓ {label}{detail}")

    # 生成头断言
    header = Path(sdk) / "projects/mouse_demo/periph/user_config.h"
    if not header.is_file():
        line(f"✕ 生成头缺失: {header}")
        return 1
    text = header.read_text(encoding="utf-8", errors="replace")
    missing = [m for m in BUILD_MACROS if f"#define {m}" not in text]
    if missing:
        line(f"✕ 生成头缺宏: {', '.join(missing)}")
        return 1
    line("\n✓ 生成头必需宏齐全: " + ", ".join(BUILD_MACROS))

    st = api.blank_status(sdk)
    if not st.get("complete") or st.get("missing") or st.get("conflicts"):
        line(f"✕ 工程未就绪: {st}")
        return 1
    line("✓ 工程完整、无缺脚、无冲突")

    if args.no_keil:
        line("\n（--no-keil：跳过编译）")
        return 0

    uv4 = Path(os.environ.get("OMCFG_UV4", r"C:\Keil_v5\UV4\UV4.exe"))
    proj = Path(sdk) / "projects/mouse_demo/keil5/SE71M.uvprojx"
    if not uv4.is_file():
        line(f"\n⚠ 未找到 Keil UV4（{uv4}），跳过编译；可用 OMCFG_UV4 指定路径")
        return 0
    if not proj.is_file():
        line(f"✕ Keil 工程缺失: {proj}")
        return 1

    log = base / (args.name + "_build.log")
    line(f"\nKeil 全量重编: {proj.name}")
    proc = subprocess.run(
        [str(uv4), "-r", str(proj), "-o", str(log)],
        capture_output=True, text=True, timeout=300, check=False,
    )
    content = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    summary = [ln.strip() for ln in content.splitlines() if "Error(s)" in ln or "Program Size" in ln]
    for ln in summary:
        line("  " + ln)
    if "0 Error(s), 0 Warning(s)" in content:
        line("\n✓ Keil 编译通过：0 Error / 0 Warning")
        return 0
    line(f"\n✕ Keil 编译失败（exit={proc.returncode}），日志: {log}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
