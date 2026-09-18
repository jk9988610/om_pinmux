# -*- coding: utf-8 -*-
"""
板级包：策略勾选 → 备份 → 写入/补丁/从供体拷贝 → 体检。

用于无整仓金机（或 RGB 板勿拷 CH04 LEDC）时的 KC536→BD319 等改造。

示例:
  python board_pack.py --target F:\\SE71M_0023_KC536_to_BD319 --board BD319 \\
      --donor E:\\M_2026\\486_BD319\\software\\SE71M_0485_BD319_v1_20260915 --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime

import biz_sync
import golden_diff
import port_apply
import validation

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
BOARDS_DIR = os.path.join(TOOL_DIR, "boards")
SYNTH_ROOT = os.path.join(TOOL_DIR, "synth")

# 策略定义：id → 说明 + 默认(rgb/ledc) + 动作
POLICY_DEFS = [
    {
        "id": "pins_user_config",
        "title": "写入脚位 user_config（由 UI/板 JSON 生成块）",
        "default_rgb": True,
        "default_ledc": True,
        "kind": "ui_pins",  # 由 GUI write_user_config 或 CLI 跳过（需 pins_h）
    },
    {
        "id": "biz_sync_contracts",
        "title": "同步 key_io / sleep 契约",
        "default_rgb": True,
        "default_ledc": True,
        "kind": "biz_sync",
    },
    {
        "id": "senscan_12bit",
        "title": "drv_senscan DATA_FORMAT → 12BIT（KC536 底包必开；勿用供体 8BIT 覆盖，曾导致开机卡死）",
        "default_rgb": True,
        "default_ledc": True,
        "kind": "patch",
        "rel": "hal/driver/om6239/drv_senscan.c",
        "patch": "senscan_12bit",
    },
    {
        "id": "usb_tx_flag_timing",
        "title": "usb_user_process 鼠标发送 flag 提前清零",
        "default_rgb": True,
        "default_ledc": True,
        "kind": "donor_or_patch",
        "rel": "mode_usb/usb_user_process.c",
        "patch": "usb_tx_flag",
    },
    {
        "id": "rf_callback_hdr",
        "title": "rf_data_process.h 回调声明 → 无参（与 KC536 底包一致）",
        "default_rgb": True,
        "default_ledc": True,
        "kind": "patch",
        "rel": "mode_24g/rf_data_process.h",
        "patch": "rf_callback",
    },
    {
        "id": "sensor_type_check",
        "title": "sensor_type_check.*（需供体）",
        "default_rgb": True,
        "default_ledc": True,
        "kind": "donor_copy",
        "rels": [
            "projects/mouse_demo/periph/sensor_type_check.c",
            "projects/mouse_demo/periph/sensor_type_check.h",
        ],
    },
    {
        "id": "stack_sct",
        "title": "om6239_ac6.sct 栈 → 0x240（KC536/CH04 底包；勿用供体 0x280 整文件覆盖）",
        "default_rgb": True,
        "default_ledc": True,
        "kind": "patch",
        "rel": "hal/device/om6239/ARM/om6239_ac6.sct",
        "patch": "stack_240",
    },
    {
        "id": "senscan_donor",
        "title": "drv_senscan.c 从供体拷贝（默认关；会盖掉 12BIT，易开机卡死）",
        "default_rgb": False,
        "default_ledc": False,
        "kind": "donor_copy",
        "rels": ["hal/driver/om6239/drv_senscan.c"],
    },
    {
        "id": "ledc_pack",
        "title": "LEDC 灯带包（ledc*/RTE/uvproj）— RGB 板应关闭",
        "default_rgb": False,
        "default_ledc": True,
        "kind": "donor_copy",
        "rels": [
            "projects/mouse_demo/periph/ledc.c",
            "projects/mouse_demo/periph/ledc.h",
            "projects/mouse_demo/periph/ledc_mode.c",
            "projects/mouse_demo/periph/ledc_mode.h",
            "hal/driver/om6239/drv_ledc.c",
            "hal/driver/om6239/drv_ledc.h",
            "hal/driver/om6239/drv_pmu.h",
            "hal/driver/om6239/drv_isr.c",
        ],
    },
    {
        "id": "rgb_logo_pack",
        "title": "RGB LOGO 业务（led/mode_ind 等，需供体）",
        "default_rgb": True,
        "default_ledc": False,
        "kind": "donor_copy",
        "rels": [
            "projects/mouse_demo/periph/led.c",
            "projects/mouse_demo/periph/led.h",
            "projects/mouse_demo/periph/mode_ind.c",
            "projects/mouse_demo/periph/lvd.c",
            "projects/mouse_demo/periph/lvd.h",
            "projects/mouse_demo/periph/sensor.c",
            "projects/mouse_demo/periph/sensor.h",
            "projects/mouse_demo/main/mouse.h",
            "projects/mouse_demo/main/mouse_hw.c",
            "projects/mouse_demo/main/main.h",
            "mode_24g/sleep.c",
            "mode_24g/sleep.h",
            "mode_24g/main_24g.c",
            "mode_usb/main_usb.c",
        ],
    },
    {
        "id": "product_usb_strings",
        "title": "USB 描述符字符串（产品字，默认关）",
        "default_rgb": False,
        "default_ledc": False,
        "kind": "donor_copy",
        "rels": ["mode_usb/usb_descriptor.h"],
    },
    {
        "id": "startup_pid",
        "title": "startup 产品字（默认关）",
        "default_rgb": False,
        "default_ledc": False,
        "kind": "donor_copy",
        "rels": ["hal/device/om6239/GCC/startup_om6239.S"],
    },
    {
        "id": "fcc_leds",
        "title": "FCC 指示灯逻辑（默认关）",
        "default_rgb": False,
        "default_ledc": False,
        "kind": "donor_copy",
        "rels": ["mode_24g/rf_fcc_key_ctrl.c"],
    },
]


def default_policy(logo_ledc: bool) -> dict[str, bool]:
    out = {}
    for p in POLICY_DEFS:
        out[p["id"]] = bool(p["default_ledc"] if logo_ledc else p["default_rgb"])
    return out


def policy_catalog(logo_ledc: bool) -> list[dict]:
    """供 UI：带当前默认勾选的策略列表。"""
    d = default_policy(logo_ledc)
    rows = []
    for p in POLICY_DEFS:
        rows.append({
            "id": p["id"],
            "title": p["title"],
            "enabled": d[p["id"]],
            "kind": p["kind"],
            "needs_donor": p["kind"] in ("donor_copy", "donor_or_patch"),
        })
    return rows


def load_board(name: str) -> dict:
    return port_apply.load_board(name)


def board_logo_ledc(board: dict) -> bool:
    meta = board.get("meta") or {}
    feat = board.get("features") or {}
    return bool(
        feat.get("BOARD_LOGO_LEDC")
        or (meta.get("logoType") or "").lower() == "ledc"
    )


def merge_policy(board: dict, override: dict | None = None) -> dict[str, bool]:
    base = default_policy(board_logo_ledc(board))
    # synth policy.json 可覆盖
    if override:
        for k, v in override.items():
            if k in base:
                base[k] = bool(v)
    return base


def _backup_file(bak_root: str, target_sdk: str, rel: str) -> None:
    dst = os.path.join(target_sdk, *rel.split("/"))
    if not os.path.isfile(dst):
        return
    out = os.path.join(bak_root, *rel.split("/"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    shutil.copy2(dst, out)


def _copy_rel(src_sdk: str, dst_sdk: str, rel: str, bak_root: str) -> str:
    src = os.path.join(src_sdk, *rel.split("/"))
    if not os.path.isfile(src):
        return f"skip(missing src): {rel}"
    _backup_file(bak_root, dst_sdk, rel)
    dst = os.path.join(dst_sdk, *rel.split("/"))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return f"copied: {rel}"


def _read(path: str) -> str:
    return open(path, encoding="utf-8", errors="replace").read()


def _write(path: str, text: str) -> None:
    open(path, "w", encoding="utf-8", newline="\n").write(text)


def _patch_file(target_sdk: str, rel: str, patch_id: str, bak_root: str) -> str:
    path = os.path.join(target_sdk, *rel.split("/"))
    if not os.path.isfile(path):
        return f"skip(missing): {rel}"
    old = _read(path)
    new = old
    if patch_id == "senscan_12bit":
        new = re.sub(
            r"SENSCAN_DATA_FORMAT_8BIT",
            "SENSCAN_DATA_FORMAT_12BIT",
            old,
        )
    elif patch_id == "rf_callback":
        new = re.sub(
            r"extern\s+void\s+rf_respone_callback\s*\(\s*uint8_t\s*\*\s*RxPayload\s*\)\s*;",
            "extern void rf_respone_callback();",
            old,
        )
    elif patch_id == "stack_240":
        new = re.sub(
            r"#define\s+__STACK_SIZE\s+0x[0-9A-Fa-f]+",
            "#define __STACK_SIZE    0x00000240",
            old,
        )
    elif patch_id == "usb_tx_flag":
        # 若仍是「末尾清零」形态，改成金机「入口处清零」
        if "m_data_flag &= ~bmouse_data_send" in old and "// m_data_flag &= ~bmouse_data_send" in old:
            # 已是注释掉入口、末尾清零的旧形态 → 打开入口并去掉末尾重复
            new = old.replace(
                "// m_data_flag &= ~bmouse_data_send;",
                "m_data_flag &= ~bmouse_data_send;",
                1,
            )
            # 删除块末多余清零（仅当入口已启用）
            new = re.sub(
                r"(\n\s*mouse_data_z\s*=\s*0;\s*\n\s*\}\s*\n)\s*m_data_flag\s*&=\s*~bmouse_data_send\s*;\s*\n(\s*\}\s*\n\s*\})",
                r"\1\2",
                new,
                count=1,
            )
        elif re.search(
            r"if\s*\(\s*m_data_flag\s*&\s*bmouse_data_send\s*\)\s*\{\s*\n\s*if\s*\(",
            old,
        ):
            # 入口无清零：在 if(m_data_flag&bmouse_data_send){ 后插入
            new = re.sub(
                r"(if\s*\(\s*m_data_flag\s*&\s*bmouse_data_send\s*\)\s*\{\s*\n)",
                r"\1            m_data_flag &= ~bmouse_data_send;\n",
                old,
                count=1,
            )
            new = re.sub(
                r"(\n\s*mouse_data_z\s*=\s*0;\s*\n\s*\}\s*\n)\s*m_data_flag\s*&=\s*~bmouse_data_send\s*;\s*\n(\s*\})",
                r"\1\2",
                new,
                count=1,
            )
    else:
        return f"skip(unknown patch): {patch_id}"

    if new == old:
        return f"noop: {rel}"
    _backup_file(bak_root, target_sdk, rel)
    _write(path, new)
    return f"patched({patch_id}): {rel}"


def apply_board_pack(
    target_hint: str,
    board_name: str,
    policy: dict[str, bool] | None = None,
    donor_hint: str = "",
    features_h: str = "",
    dry_run: bool = False,
    pins_payload: dict | None = None,
) -> dict:
    """
    pins_payload: 可选，与 write_user_config 相同字段（pins_h/gpio_c/meta/…），
    CLI 通常不传（只做补丁/供体拷）；GUI 可先 write_user_config 再调本函数。
    """
    target = port_apply.resolve_sdk(target_hint)
    board = load_board(board_name)
    validation_result = validation.validate_board(board)
    if not validation_result["ok"]:
        return {
            "ok": False,
            "message": f"板描述校验失败: {board_name}",
            "validation": validation_result,
        }
    logo_ledc = board_logo_ledc(board)

    # synth policy overlay
    synth_pol_path = os.path.join(SYNTH_ROOT, board_name, "policy.json")
    override = None
    if os.path.isfile(synth_pol_path):
        override = json.load(open(synth_pol_path, encoding="utf-8"))
        if isinstance(override, dict) and "enabled" in override:
            override = override["enabled"]
    pol = merge_policy(board, override)
    if policy:
        for k, v in policy.items():
            if k in pol:
                pol[k] = bool(v)

    donor = ""
    if donor_hint:
        try:
            donor = port_apply.resolve_sdk(donor_hint)
        except FileNotFoundError as e:
            return {"ok": False, "message": str(e)}

    t_periph = port_apply.periph_of(target)
    feat = port_apply.board_to_feat(board, t_periph)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_root = os.path.join(target, f"_board_bak_{stamp}")
    actions: list[dict] = []
    warnings: list[str] = []

    if dry_run:
        plan = []
        for p in POLICY_DEFS:
            if not pol.get(p["id"]):
                continue
            plan.append({"id": p["id"], "kind": p["kind"], "title": p["title"]})
        return {
            "ok": True,
            "dry_run": True,
            "target": target,
            "board": board_name,
            "logo_ledc": logo_ledc,
            "donor": donor or "",
            "policy": pol,
            "plan": plan,
            "message": f"[dry-run] {len(plan)} 项策略将应用于 {target}",
        }

    os.makedirs(bak_root, exist_ok=True)

    # features.h from synth if not provided
    if not features_h:
        synth_feat = os.path.join(SYNTH_ROOT, board_name, "board_features.h")
        if os.path.isfile(synth_feat):
            features_h = _read(synth_feat)

    if features_h:
        feat_path = os.path.join(t_periph, "board_features.h")
        if os.path.isfile(feat_path):
            _backup_file(bak_root, target, "projects/mouse_demo/periph/board_features.h")
        _write(feat_path, features_h)
        actions.append({"id": "board_features", "detail": "wrote board_features.h", "ok": True})

    if pins_payload and pol.get("pins_user_config"):
        # 轻量：仅当 CLI 传入时；GUI 应先调 write_user_config
        actions.append({
            "id": "pins_user_config",
            "detail": "pins_payload 应由 GUI write_user_config 处理；此处跳过",
            "ok": True,
            "skipped": True,
        })

    for pdef in POLICY_DEFS:
        pid = pdef["id"]
        if not pol.get(pid):
            continue
        kind = pdef["kind"]
        if kind == "ui_pins":
            continue
        if kind == "biz_sync":
            sync_bak = os.path.join(bak_root, "_biz_sync")
            os.makedirs(sync_bak, exist_ok=True)
            sync_r = biz_sync.sync_board_contracts(t_periph, feat, sync_bak)
            actions.append({
                "id": pid,
                "detail": sync_r.get("message") or "biz_sync",
                "ok": bool(sync_r.get("ok", True)),
                "written": sync_r.get("written") or [],
            })
            continue
        if kind == "patch":
            detail = _patch_file(target, pdef["rel"], pdef["patch"], bak_root)
            actions.append({"id": pid, "detail": detail, "ok": True})
            continue
        if kind == "donor_copy":
            if not donor:
                warnings.append(f"{pid}: 无供体，跳过拷贝")
                actions.append({"id": pid, "detail": "no donor", "ok": True, "skipped": True})
                continue
            notes = []
            for rel in pdef.get("rels") or []:
                notes.append(_copy_rel(donor, target, rel, bak_root))
            actions.append({"id": pid, "detail": "; ".join(notes), "ok": True})
            continue
        if kind == "donor_or_patch":
            if donor and os.path.isfile(os.path.join(donor, *pdef["rel"].split("/"))):
                detail = _copy_rel(donor, target, pdef["rel"], bak_root)
            else:
                detail = _patch_file(target, pdef["rel"], pdef["patch"], bak_root)
            actions.append({"id": pid, "detail": detail, "ok": True})
            continue

    # LEDC uvproj only when ledc_pack on
    if pol.get("ledc_pack"):
        uv = os.path.join(target, "projects", "mouse_demo", "keil5", "SE71M.uvprojx")
        if os.path.isfile(uv):
            uv_r = port_apply.ensure_uvproj_ledc(uv, dry_run=False)
            actions.append({"id": "uvproj_ledc", "detail": uv_r.get("message"), "ok": True})

    checklist = biz_sync.scan_port_checklist(t_periph, feat)
    err_n = (checklist.get("summary") or {}).get("error", -1)

    report = {
        "ok": err_n == 0,
        "target": target,
        "board": board_name,
        "bak_root": bak_root,
        "donor": donor or "",
        "policy": pol,
        "actions": actions,
        "warnings": warnings,
        "checklist": checklist,
        "error_count": err_n,
        "message": (
            f"板级包已应用 board={board_name} error={err_n} "
            f"warn_actions={len(warnings)} backup={bak_root}"
        ),
    }

    report_dir = os.path.join(TOOL_DIR, "reports")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"board_pack_{board_name}_{stamp}.txt")
    lines = [
        f"=== board_pack {board_name} ===",
        f"time: {datetime.now().isoformat(timespec='seconds')}",
        f"target: {target}",
        f"donor: {donor or '(none)'}",
        f"backup: {bak_root}",
        "",
        "--- policy ---",
        json.dumps(pol, ensure_ascii=False, indent=2),
        "",
        "--- actions ---",
    ]
    for a in actions:
        lines.append(f"  [{a.get('id')}] {a.get('detail')}")
    if warnings:
        lines.append("")
        lines.append("--- warnings ---")
        lines.extend(f"  ! {w}" for w in warnings)
    lines.append("")
    lines.append("--- checklist ---")
    s = checklist.get("summary") or {}
    lines.append(f"error={s.get('error')} warn={s.get('warn')} total={s.get('total')}")
    for it in checklist.get("items") or []:
        if not it.get("pass"):
            lines.append(
                f"  [{it.get('level')}] {it.get('title')}"
                + (f" — {it.get('detail')}" if it.get("detail") else "")
            )
    text = "\n".join(lines)
    open(report_path, "w", encoding="utf-8", newline="\n").write(text)
    open(
        os.path.join(target, f"board_pack_{stamp}.txt"),
        "w", encoding="utf-8", newline="\n",
    ).write(text)
    report["report_path"] = report_path
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="板级策略包写入（宏观金机 / 无整仓拷贝）")
    ap.add_argument("--target", required=True, help="目标 SDK 根")
    ap.add_argument("--board", default="BD319", help="boards/<name>.json")
    ap.add_argument("--donor", default="", help="可选供体 SDK（如现有 BD319 工程）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--policy-json",
        default="",
        help='覆盖策略 JSON，如 {"ledc_pack":false,"rgb_logo_pack":true}',
    )
    args = ap.parse_args(argv)
    override = None
    if args.policy_json:
        override = json.loads(args.policy_json)
    r = apply_board_pack(
        args.target,
        args.board,
        policy=override,
        donor_hint=args.donor,
        dry_run=args.dry_run,
    )
    print(json.dumps(r, ensure_ascii=False, indent=2)[:8000])
    if args.dry_run:
        return 0
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
