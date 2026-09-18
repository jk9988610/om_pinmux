# -*- coding: utf-8 -*-
"""
有金机的无人换板：备份 → 拷 PORT_FOCUS → biz_sync → uvproj 补 ledc → 体检报告。

示例:
  python port_apply.py --target F:\\SE71M_0023_KC536_20260917 --golden <本仓SDK> --board CH04
  python port_apply.py --target ... --golden ... --board CH04 --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import biz_sync
import golden_diff
import validation

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
BOARDS_DIR = os.path.join(TOOL_DIR, "boards")

# Keil 工程额外关注（不在 PORT_FOCUS 内但编译必需）
EXTRA_RELS = [
    "projects/mouse_demo/keil5/SE71M.uvprojx",
]

UVPROJ_LEDC_FILES = [
    {
        "group": "periph",
        "name": "ledc.c",
        "path": r"..\periph\ledc.c",
        "ftype": "1",
        "after": "mode_ind.c",
    },
    {
        "group": "periph",
        "name": "ledc_mode.c",
        "path": r"..\periph\ledc_mode.c",
        "ftype": "1",
        "after": "ledc.c",
    },
    {
        "group": "driver",
        "name": "drv_ledc.c",
        "path": r"..\..\..\hal\driver\om6239\drv_ledc.c",
        "ftype": "1",
        "after": "drv_wdt.c",
    },
]


def _norm_rel(rel: str) -> str:
    return rel.replace("\\", "/").lstrip("/")


def load_board(board: str) -> dict:
    path = os.path.join(BOARDS_DIR, f"{board}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"板描述不存在: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def board_to_feat(board: dict, golden_periph: str) -> dict:
    meta = board.get("meta") or {}
    feat_flags = board.get("features") or {}
    logo_ledc = bool(
        feat_flags.get("BOARD_LOGO_LEDC")
        or (meta.get("logoType") or "").lower() == "ledc"
    )
    return {
        "has_key_pair": "KEY_PAIR_PIN" in (board.get("pins") or {}),
        "has_key_c0": bool(meta.get("hasKeyC0") or feat_flags.get("BOARD_HAS_KEY_C0")),
        "has_dpi_pair": bool(meta.get("hasDpiPair") or feat_flags.get("BOARD_HAS_DPI_PAIR")),
        "has_extra_keys": bool(
            meta.get("hasExtraKeys") or feat_flags.get("BOARD_HAS_EXTRA_KEYS")
        ),
        "mode_dual": (meta.get("modePins") or "") == "dual"
        or bool(feat_flags.get("BOARD_MODE_DUAL_PIN")),
        "mode_single": (meta.get("modePins") or "") == "single"
        or bool(feat_flags.get("BOARD_MODE_SINGLE_PIN")),
        "logo_ledc": logo_ledc,
        "logo_rgb": not logo_ledc,
        "golden_periph": golden_periph,
    }


def resolve_sdk(hint: str) -> str:
    sdk = golden_diff.find_sdk_root(hint)
    if not sdk:
        raise FileNotFoundError(f"无法定位 SDK 根（需含 projects/ 或 mode_24g/）: {hint}")
    return sdk


def periph_of(sdk: str) -> str:
    p = os.path.join(sdk, "projects", "mouse_demo", "periph")
    if not os.path.isdir(p):
        raise FileNotFoundError(f"缺少 periph: {p}")
    return p


def focus_rels() -> list[str]:
    rels = [_norm_rel(r) for r in golden_diff.PORT_FOCUS_RELS]
    for r in EXTRA_RELS:
        r = _norm_rel(r)
        if r not in rels:
            rels.append(r)
    return rels


def plan_copies(golden: str, target: str) -> list[dict]:
    items = []
    for rel in focus_rels():
        src = os.path.join(golden, *rel.split("/"))
        dst = os.path.join(target, *rel.split("/"))
        if not os.path.isfile(src):
            items.append({"rel": rel, "action": "skip_missing_src", "src": src, "dst": dst})
            continue
        same = False
        if os.path.isfile(dst):
            same = golden_diff._file_sha1(src) == golden_diff._file_sha1(dst)
        items.append({
            "rel": rel,
            "action": "same" if same else ("create" if not os.path.isfile(dst) else "overwrite"),
            "src": src,
            "dst": dst,
        })
    return items


def backup_existing(target: str, bak_root: str, items: list[dict], dry_run: bool) -> list[str]:
    backed = []
    for it in items:
        if it["action"] not in ("overwrite", "create"):
            continue
        dst = it["dst"]
        if not os.path.isfile(dst):
            continue
        rel = it["rel"]
        out = os.path.join(bak_root, *rel.split("/"))
        if dry_run:
            backed.append(out)
            continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copy2(dst, out)
        backed.append(out)
    return backed


def apply_copies(items: list[dict], dry_run: bool) -> list[str]:
    written = []
    for it in items:
        if it["action"] not in ("overwrite", "create"):
            continue
        if dry_run:
            written.append(it["dst"])
            continue
        os.makedirs(os.path.dirname(it["dst"]), exist_ok=True)
        shutil.copy2(it["src"], it["dst"])
        written.append(it["dst"])
    return written


def _xml_text(parent: ET.Element, tag: str) -> str:
    child = parent.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _find_group(root: ET.Element, group_name: str) -> ET.Element | None:
    for group in root.findall(".//Group"):
        if _xml_text(group, "GroupName") == group_name:
            return group
    return None


def _append_uvproj_file(files: ET.Element, spec: dict) -> None:
    entry = ET.SubElement(files, "File")
    ET.SubElement(entry, "FileName").text = spec["name"]
    ET.SubElement(entry, "FileType").text = spec["ftype"]
    ET.SubElement(entry, "FilePath").text = spec["path"]


def _indent_xml(element: ET.Element, level: int = 0) -> None:
    """Keep generated Keil XML reviewable on Python versions without ET.indent."""
    indent = "  "
    children = list(element)
    if children:
        if not element.text or not element.text.strip():
            element.text = "\n" + indent * (level + 1)
        for child in children:
            _indent_xml(child, level + 1)
        if not children[-1].tail or not children[-1].tail.strip():
            children[-1].tail = "\n" + indent * level
    if level and (not element.tail or not element.tail.strip()):
        element.tail = "\n" + indent * level


def ensure_uvproj_ledc(uvproj_path: str, dry_run: bool = False) -> dict:
    """使用 XML 解析幂等地补齐 ledc.c / ledc_mode.c / drv_ledc.c 工程节点。"""
    path = os.path.abspath(uvproj_path)
    if not os.path.isfile(path):
        return {"ok": False, "message": f"无 uvprojx: {path}", "added": []}
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        return {"ok": False, "message": f"uvprojx XML 解析失败: {exc}", "added": []}

    root = tree.getroot()
    added: list[str] = []
    for spec in UVPROJ_LEDC_FILES:
        group = _find_group(root, spec["group"])
        if group is None:
            return {
                "ok": False,
                "message": f"找不到 Group {spec['group']} 以插入 {spec['name']}",
                "added": added,
            }
        files = group.find("Files")
        if files is None:
            return {
                "ok": False,
                "message": f"Group {spec['group']} 缺少 Files 节点",
                "added": added,
            }
        existing = [
            item for item in files.findall("File")
            if _xml_text(item, "FileName") == spec["name"]
        ]
        if existing:
            matching = any(
                _xml_text(item, "FilePath").replace("/", "\\") == spec["path"]
                for item in existing
            )
            if not matching:
                return {
                    "ok": False,
                    "message": f"{spec['name']} 已存在但路径不匹配，请人工确认",
                    "added": added,
                }
            continue
        _append_uvproj_file(files, spec)
        added.append(spec["name"])

    if not added:
        return {"ok": True, "message": "uvproj 已含 ledc 文件", "added": []}
    if dry_run:
        return {"ok": True, "message": f"将添加: {', '.join(added)}", "added": added}

    _indent_xml(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    try:
        verified_root = ET.parse(path).getroot()
        for spec in UVPROJ_LEDC_FILES:
            group = _find_group(verified_root, spec["group"])
            files = group.find("Files") if group is not None else None
            if files is None or not any(
                _xml_text(item, "FileName") == spec["name"]
                and _xml_text(item, "FilePath").replace("/", "\\") == spec["path"]
                for item in files.findall("File")
            ):
                return {"ok": False, "message": f"写后验证失败: {spec['name']}", "added": added}
    except ET.ParseError as exc:
        return {"ok": False, "message": f"写后 XML 校验失败: {exc}", "added": added}
    return {"ok": True, "message": f"已添加: {', '.join(added)}", "added": added}


def format_report(
    target: str,
    golden: str,
    bak_root: str,
    copy_items: list[dict],
    sync_result: dict | None,
    uv_result: dict,
    checklist: dict,
    inventory: dict,
) -> str:
    lines = [
        "=== KC536→CH04 port_apply 报告 ===",
        f"time: {datetime.now().isoformat(timespec='seconds')}",
        f"target: {target}",
        f"golden: {golden}",
        f"backup: {bak_root}",
        "",
        "--- 验收闸门 ---",
        "1) 关注清单：仅 key_io.h 可为预期 DIFF（biz_sync）；其它 DIFF/仅金机 → 查拷贝",
        "2) Keil 编译：0 Error（本报告体检含 mouse_name / sensor_deepsleep / charg_led 契约）",
        "3) 实机冒烟：模式/灯效/滚轮/休眠",
        "全文树 .diff 不作成败判据（产品 ID、USB 字符串、传感器表、FCC 灯等允许保留）",
        "",
        "--- 拷贝计划 ---",
    ]
    for it in copy_items:
        lines.append(f"  [{it['action']}] {it['rel']}")
    lines.append("")
    if sync_result:
        lines.append("--- biz_sync ---")
        lines.append(json.dumps(sync_result, ensure_ascii=False, indent=2)[:4000])
        lines.append("")
    lines.append("--- uvproj ---")
    lines.append(json.dumps(uv_result, ensure_ascii=False))
    lines.append("")
    lines.append("--- 换板体检 ---")
    if checklist.get("ok"):
        s = checklist.get("summary") or {}
        lines.append(
            f"error={s.get('error')} warn={s.get('warn')} total={s.get('total')}"
        )
        for it in checklist.get("items") or []:
            if it.get("pass"):
                continue
            lines.append(
                f"  [{it.get('level')}/{it.get('stage')}] {it.get('title')}"
                + (f" — {it.get('detail')}" if it.get("detail") else "")
            )
    else:
        lines.append(checklist.get("message") or str(checklist))
    lines.append("")
    lines.append("--- 金机清单 ---")
    lines.append(golden_diff.format_inventory_text(inventory))
    # 关注面异常提示（排除预期 DIFF）
    unexpected = [
        r for r in (inventory.get("diff") or [])
        if r not in golden_diff.EXPECTED_FOCUS_DIFF_RELS
    ]
    if inventory.get("only_golden") or unexpected:
        lines.append("")
        lines.append("--- 关注面异常（需处理） ---")
        for r in inventory.get("only_golden") or []:
            lines.append(f"  仅金机: {r}")
        for r in unexpected:
            lines.append(f"  非预期 DIFF: {r}")
    return "\n".join(lines)


def run(
    target_hint: str,
    golden_hint: str,
    board_name: str,
    dry_run: bool = False,
    report_dir: str = "",
) -> dict:
    target = resolve_sdk(target_hint)
    golden = resolve_sdk(golden_hint)
    board = load_board(board_name)
    validation_result = validation.validate_board(board)
    if not validation_result["ok"]:
        return {
            "ok": False,
            "message": f"板描述校验失败: {board_name}",
            "validation": validation_result,
        }
    g_periph = periph_of(golden)
    t_periph = periph_of(target)
    feat = board_to_feat(board, g_periph)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_root = os.path.join(target, f"_port_bak_{stamp}")
    copy_items = plan_copies(golden, target)

    if dry_run:
        print(f"[dry-run] target={target}")
        print(f"[dry-run] golden={golden}")
        print(f"[dry-run] backup→{bak_root}")
        for it in copy_items:
            print(f"  [{it['action']}] {it['rel']}")
        uv_path = os.path.join(target, "projects", "mouse_demo", "keil5", "SE71M.uvprojx")
        uv_result = ensure_uvproj_ledc(uv_path, dry_run=True)
        print(f"[dry-run] uvproj: {uv_result.get('message')}")
        print(f"[dry-run] feat: {json.dumps(feat, ensure_ascii=False)}")
        return {"ok": True, "dry_run": True, "bak_root": bak_root, "items": copy_items}

    os.makedirs(bak_root, exist_ok=True)
    backup_existing(target, bak_root, copy_items, dry_run=False)
    written = apply_copies(copy_items, dry_run=False)

    # uvproj may have been overwritten by copy; ensure ledc entries still present
    uv_path = os.path.join(target, "projects", "mouse_demo", "keil5", "SE71M.uvprojx")
    if os.path.isfile(uv_path) and not any(
        it["rel"].endswith("SE71M.uvprojx") and it["action"] in ("overwrite", "create")
        for it in copy_items
    ):
        # only backup if we're about to edit a file not already backed via focus copy
        pass
    # Always re-ensure after copy (CH04 uvproj already has entries → noop)
    uv_bak = os.path.join(bak_root, "projects", "mouse_demo", "keil5")
    if os.path.isfile(uv_path) and not os.path.isfile(
        os.path.join(uv_bak, "SE71M.uvprojx")
    ):
        os.makedirs(uv_bak, exist_ok=True)
        shutil.copy2(uv_path, os.path.join(uv_bak, "SE71M.uvprojx"))
    uv_result = ensure_uvproj_ledc(uv_path, dry_run=False)

    sync_bak = os.path.join(bak_root, "_biz_sync")
    os.makedirs(sync_bak, exist_ok=True)
    sync_result = biz_sync.sync_board_contracts(t_periph, feat, sync_bak)

    checklist = biz_sync.scan_port_checklist(t_periph, feat)
    inventory = golden_diff.inventory_focus(golden, target)

    report_text = format_report(
        target, golden, bak_root, copy_items, sync_result,
        uv_result, checklist, inventory,
    )

    if not report_dir:
        report_dir = os.path.join(TOOL_DIR, "reports")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"port_{board_name}_{stamp}.txt")
    # also drop a copy on target root
    target_report = os.path.join(target, f"port_apply_{stamp}.txt")
    for path in (report_path, target_report):
        open(path, "w", encoding="utf-8", newline="\n").write(report_text)

    err_n = (checklist.get("summary") or {}).get("error", -1)
    print(report_text)
    print(f"\n报告: {report_path}")
    print(f"目标报告: {target_report}")
    print(f"备份: {bak_root}")
    print(f"已写文件数: {len(written)}")

    return {
        "ok": err_n == 0,
        "bak_root": bak_root,
        "report_path": report_path,
        "target_report": target_report,
        "written": written,
        "uvproj": uv_result,
        "sync": sync_result,
        "checklist": checklist,
        "inventory": inventory,
        "error_count": err_n,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="有金机无人换板（PORT_FOCUS 对齐）")
    ap.add_argument("--target", required=True, help="目标 SDK 根（如 KC536）")
    ap.add_argument("--golden", required=True, help="金机 SDK 根（如 CH04）")
    ap.add_argument("--board", default="CH04", help="boards/<name>.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report-dir", default="", help="报告目录，默认 tools/om_pinmux/reports")
    args = ap.parse_args(argv)

    try:
        result = run(
            args.target, args.golden, args.board,
            dry_run=args.dry_run, report_dir=args.report_dir,
        )
    except Exception as e:
        print(f"失败: {e}", file=sys.stderr)
        return 2

    if args.dry_run:
        return 0
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
