# -*- coding: utf-8 -*-
"""
宏观金机：由 boards/<BOARD>.json + 可选原理图目录生成 synth/<BOARD>/。

不是伪造整棵 SDK，而是板契约 + 策略包 + 预期头文件，供清单对照与 board_pack 使用。

示例:
  python synth_golden.py --board BD319 --pictures E:\\pictures\\BD319
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

import board_pack
import validation

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
BOARDS_DIR = os.path.join(TOOL_DIR, "boards")
SYNTH_ROOT = os.path.join(TOOL_DIR, "synth")

# synth 清单对比用的相对路径（相对 synth/<board>/）
SYNTH_FOCUS_RELS = [
    "board_desc.json",
    "board_features.h",
    "expected_user_config.h",
    "policy.json",
    "checklist_expect.json",
]


def _pin_num(pxx: str) -> str:
    pxx = (pxx or "").strip().upper()
    if pxx.startswith("P") and len(pxx) >= 2:
        return pxx[1:]
    return pxx


def generate_features_h(board: dict) -> str:
    meta = board.get("meta") or {}
    feat = board.get("features") or {}
    logo_ledc = board_pack.board_logo_ledc(board)
    lines = [
        "/**",
        " * board_features.h — 由 om_pinmux synth_golden 生成",
        f" * board: {(meta.get('projName') or 'BOARD')}",
        " * 业务代码请用 #if BOARD_HAS_xxx / BOARD_LOGO_* 包住板差异。",
        " */",
        "#ifndef BOARD_FEATURES_H_",
        "#define BOARD_FEATURES_H_",
        "",
        f"#define BOARD_HAS_KEY_C0           {1 if feat.get('BOARD_HAS_KEY_C0') or meta.get('hasKeyC0') else 0}",
        f"#define BOARD_HAS_EXTRA_KEYS       {1 if feat.get('BOARD_HAS_EXTRA_KEYS') or meta.get('hasExtraKeys') else 0}",
        f"#define BOARD_HAS_DPI_PAIR         {1 if feat.get('BOARD_HAS_DPI_PAIR') or meta.get('hasDpiPair') else 0}",
        f"#define BOARD_HAS_LED_LOW          {1 if feat.get('BOARD_HAS_LED_LOW') or meta.get('hasLedLow') else 0}",
        f"#define BOARD_HAS_SENSOR_NCS       {1 if feat.get('BOARD_HAS_SENSOR_NCS') or meta.get('hasSensorNcs') else 0}",
        f"#define BOARD_MODE_DUAL_PIN        {1 if feat.get('BOARD_MODE_DUAL_PIN') or (meta.get('modePins')=='dual') else 0}",
        f"#define BOARD_MODE_SINGLE_PIN      {1 if feat.get('BOARD_MODE_SINGLE_PIN') or (meta.get('modePins')=='single') else 0}",
        f"#define BOARD_LOGO_LEDC            {1 if logo_ledc else 0}",
        f"#define BOARD_LOGO_RGB             {0 if logo_ledc else 1}",
        f"#define BOARD_LED_ACTIVE_HIGH      {1 if (meta.get('ledPolarity') or 'active_high') == 'active_high' else 0}",
        f"#define BOARD_LED_ACTIVE_LOW       {1 if (meta.get('ledPolarity') or '') == 'active_low' else 0}",
        "",
        "#endif /* BOARD_FEATURES_H_ */",
        "",
    ]
    return "\n".join(lines)


def generate_expected_user_config_h(board: dict) -> str:
    """生成预期脚位宏片段（标记块内容），供对照，不替代完整工程头文件。"""
    meta = board.get("meta") or {}
    pins = board.get("pins") or {}
    derived = board.get("derived") or {}
    lines = [
        "/* >>> OM_PINMUX_GENERATED begin */",
        f"/* synth expected pins for {(meta.get('projName') or 'BOARD')} */",
        f"#define iPROJECT_NAME             \"{meta.get('projName') or 'BOARD'}\"",
        f"#define iCONSUMER_NAME            \"{meta.get('consumerName') or 'App'}\"",
        f"#define iPROJECT_ID_L             {meta.get('projIdL') or '0x0000'}",
        f"#define iPROJECT_ID_H             {meta.get('projIdH') or '0x071'}",
        f"#define iREAL_VERSION_ID          {meta.get('verId') or 1}",
        "",
    ]
    for name, pxx in pins.items():
        if name.endswith("_PIN") or name in ("USB_5V",):
            # USB_5V 在工程里常是宏到脚号
            if name == "USB_5V":
                lines.append(f"#define USB_5V                    {_pin_num(pxx)}")
            else:
                lines.append(f"#define {name:<24} {_pin_num(pxx)}")
    if derived.get("LVD_CHECK_INDEX"):
        lines.append(f"#define LVD_CHECK_INDEX           {derived['LVD_CHECK_INDEX']}")
    if derived.get("WHEEL_IO_SELECT"):
        lines.append(f"#define WHEEL_IO_SELECT           {derived['WHEEL_IO_SELECT']}")
    if "WHEEL_SOFT_GPIO" in derived:
        val = "1" if derived["WHEEL_SOFT_GPIO"] else "0"
        lines.append(f"#define WHEEL_SOFT_GPIO           {val}")
    if meta.get("sensorDir"):
        lines.append(f"#define SENSOR_DIR                {meta['sensorDir']}")
    lines.append("/* <<< OM_PINMUX_GENERATED end */")
    lines.append("")
    return "\n".join(lines)


def _collect_picture_notes(pictures_dir: str) -> list[str]:
    notes: list[str] = []
    if not pictures_dir or not os.path.isdir(pictures_dir):
        return notes
    readme = os.path.join(pictures_dir, "README.md")
    if os.path.isfile(readme):
        text = open(readme, encoding="utf-8", errors="replace").read()
        notes.append(f"原理图索引: {readme}")
        # 摘取前若干非空行
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("#"):
                notes.append(s)
            if len(notes) > 24:
                break
    for name in sorted(os.listdir(pictures_dir)):
        if name.lower().endswith(".md") and name.upper() != "README.MD":
            notes.append(f"模块说明: {name}")
    return notes


def build_checklist_expect(board: dict) -> dict:
    logo_ledc = board_pack.board_logo_ledc(board)
    meta = board.get("meta") or {}
    pins = board.get("pins") or {}
    return {
        "logo_ledc": logo_ledc,
        "logo_rgb": not logo_ledc,
        "require_ledc_files": logo_ledc,
        "mode_dual": (meta.get("modePins") or "") == "dual",
        "has_key_pair": "KEY_PAIR_PIN" in pins,
        "has_extra_keys": bool(meta.get("hasExtraKeys")),
        "has_key_c0": bool(meta.get("hasKeyC0")),
        "wheel_a": pins.get("WHEEL_A_PIN"),
        "wheel_b": pins.get("WHEEL_B_PIN"),
        "forbid_ch04_port_apply": not logo_ledc,
        "notes": [
            "RGB 板勿对 CH04 跑 port_apply 整包拷 ledc*",
            "宏观金机只校验契约与策略，不替代实机冒烟",
        ],
    }


def generate_manifest(board: dict, pictures_dir: str, out_dir: str) -> str:
    meta = board.get("meta") or {}
    pins = board.get("pins") or {}
    logo_ledc = board_pack.board_logo_ledc(board)
    pic_notes = _collect_picture_notes(pictures_dir)
    lines = [
        f"# 宏观金机：{meta.get('projName') or 'BOARD'}",
        "",
        f"- 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        f"- 输出目录: `{out_dir}`",
        f"- LOGO: {'LEDC' if logo_ledc else 'RGB'}",
        f"- 模式脚: {meta.get('modePins')}",
        "",
        "## 禁止事项",
        "",
        "- 无整仓金机时不要用 CH04 `port_apply` 整包覆盖 RGB 板（会错误引入 ledc*）。",
        "- USB 字符串 / startup 产品字 / FCC 灯默认不写入（策略默认关）。",
        "",
        "## 脚位表（pins）",
        "",
        "| 宏 | Pxx |",
        "|----|-----|",
    ]
    for k, v in pins.items():
        lines.append(f"| `{k}` | {v} |")
    lines.append("")
    lines.append("## 原理图")
    lines.append("")
    if pictures_dir:
        lines.append(f"- 目录: `{pictures_dir}`")
    for n in pic_notes:
        lines.append(f"- {n}")
    lines.append("")
    lines.append("## 下一步")
    lines.append("")
    lines.append("1. om_pinmux 选工程 → 选本板 → 核对脚位/策略")
    lines.append("2. 「写入工程」脚位 + 「应用板级包」")
    lines.append("3. 可选供体 SDK 拷 RGB 业务文件")
    lines.append("4. 体检 → Keil → 冒烟")
    lines.append("")
    return "\n".join(lines)


def synth_board(
    board_name: str,
    pictures_dir: str = "",
    out_root: str = "",
) -> dict:
    board_path = os.path.join(BOARDS_DIR, f"{board_name}.json")
    if not os.path.isfile(board_path):
        return {"ok": False, "message": f"缺少板描述: {board_path}"}
    board = json.load(open(board_path, encoding="utf-8"))
    validation_result = validation.validate_board(board)
    if not validation_result["ok"]:
        return {
            "ok": False,
            "message": f"板描述校验失败: {board_path}",
            "validation": validation_result,
        }
    logo_ledc = board_pack.board_logo_ledc(board)
    policy_enabled = board_pack.default_policy(logo_ledc)

    out_dir = out_root or os.path.join(SYNTH_ROOT, board_name)
    os.makedirs(out_dir, exist_ok=True)

    # enrich notes from pictures
    board = dict(board)
    notes = list(board.get("notes") or [])
    for n in _collect_picture_notes(pictures_dir):
        if n not in notes:
            notes.append(n)
    board["notes"] = notes
    if pictures_dir:
        board["pictures"] = os.path.abspath(pictures_dir)

    files = {
        "board_desc.json": json.dumps(board, ensure_ascii=False, indent=2) + "\n",
        "board_features.h": generate_features_h(board),
        "expected_user_config.h": generate_expected_user_config_h(board),
        "policy.json": json.dumps(
            {
                "board": board_name,
                "logo_ledc": logo_ledc,
                "enabled": policy_enabled,
                "catalog": board_pack.policy_catalog(logo_ledc),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "checklist_expect.json": json.dumps(
            build_checklist_expect(board), ensure_ascii=False, indent=2
        )
        + "\n",
        "MANIFEST.md": generate_manifest(board, pictures_dir, out_dir),
    }
    written = []
    for name, text in files.items():
        path = os.path.join(out_dir, name)
        open(path, "w", encoding="utf-8", newline="\n").write(text)
        written.append(path)

    return {
        "ok": True,
        "board": board_name,
        "out_dir": out_dir,
        "logo_ledc": logo_ledc,
        "written": written,
        "policy": policy_enabled,
        "message": f"宏观金机已生成: {out_dir}",
    }


def inventory_synth_vs_target(board_name: str, target_hint: str) -> dict:
    """
    宏观对照：把 synth 期望脚位宏集合与目标 user_config.h 中宏做集合对比。
    """
    import port_apply

    synth_dir = os.path.join(SYNTH_ROOT, board_name)
    exp_h = os.path.join(synth_dir, "expected_user_config.h")
    if not os.path.isfile(exp_h):
        return {"ok": False, "message": f"请先 synth_golden: 缺少 {exp_h}"}
    try:
        target = port_apply.resolve_sdk(target_hint)
    except FileNotFoundError as e:
        return {"ok": False, "message": str(e)}
    uc = os.path.join(target, "projects", "mouse_demo", "periph", "user_config.h")
    if not os.path.isfile(uc):
        return {"ok": False, "message": f"缺少 {uc}"}

    def macros(path: str) -> dict[str, str]:
        import re
        text = open(path, encoding="utf-8", errors="replace").read()
        out = {}
        for m in re.finditer(
            r"#define\s+(KEY_\w+_PIN|WHEEL_\w+_PIN|MODE_\w+_PIN|SENSOR_\w+_PIN|"
            r"LED_\w+_PIN|LEDC_\w+_PIN|USB_5V|BAT_CHG_PIN|LVD_PIN|LVD_CHECK_INDEX|"
            r"WHEEL_IO_SELECT|SENSOR_DIR)\s+(\S+)",
            text,
        ):
            out[m.group(1)] = m.group(2).strip()
        return out

    a = macros(exp_h)
    b = macros(uc)
    same, diff, only_s, only_t = [], [], [], []
    for k in sorted(set(a) | set(b)):
        if k not in b:
            only_s.append(k)
        elif k not in a:
            only_t.append(k)
        elif a[k] == b[k]:
            same.append(f"{k}={a[k]}")
        else:
            diff.append(f"{k}: synth={a[k]} target={b[k]}")

    text_lines = [
        f"=== 宏观金机脚位对照 {board_name} ===",
        f"synth: {synth_dir}",
        f"target: {target}",
        f"SAME={len(same)} DIFF={len(diff)} 仅合成={len(only_s)} 仅目标={len(only_t)}",
        "",
    ]
    if diff:
        text_lines.append("--- DIFF ---")
        text_lines.extend(f"  ~ {x}" for x in diff)
    if only_s:
        text_lines.append("--- 仅合成有 ---")
        text_lines.extend(f"  + {x}" for x in only_s)
    if only_t:
        text_lines.append("--- 仅目标有 ---")
        text_lines.extend(f"  - {x}" for x in only_t)
    text_lines.append(f"\n--- SAME ({len(same)}) ---")
    text_lines.extend(f"  = {x}" for x in same[:40])

    return {
        "ok": True,
        "same": same,
        "diff": diff,
        "only_synth": only_s,
        "only_target": only_t,
        "text": "\n".join(text_lines),
        "message": (
            f"宏观对照: SAME={len(same)} DIFF={len(diff)} "
            f"仅合成={len(only_s)} 仅目标={len(only_t)}"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成宏观金机 synth/<board>/")
    ap.add_argument("--board", default="BD319")
    ap.add_argument("--pictures", default="", help="原理图说明目录，如 E:\\pictures\\BD319")
    ap.add_argument("--out", default="", help="输出目录（默认 tools/om_pinmux/synth/<board>）")
    args = ap.parse_args(argv)
    pics = args.pictures
    if not pics:
        cand = os.path.join("E:\\pictures", args.board)
        if os.path.isdir(cand):
            pics = cand
    r = synth_board(args.board, pictures_dir=pics, out_root=args.out)
    print(json.dumps({k: v for k, v in r.items() if k != "written"}, ensure_ascii=False, indent=2))
    if r.get("written"):
        print("written:")
        for p in r["written"]:
            print(" ", p)
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
