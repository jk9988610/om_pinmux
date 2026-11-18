# -*- coding: utf-8 -*-
"""可拔插功能插件：勾选 = 改 board 选项 + 腾脚 + 注入文件，取消则反向撤销。

插件契约在 omcfg/data/plugins.json。所有知识（文件、角色、腾脚、board 效果）
都在契约里，本模块只做通用执行，不为某个插件写死逻辑。
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from . import model
from .targets import sdk as sdk_target

PLUGINS_FILE = Path(__file__).parent / "data" / "plugins.json"


def load_contracts() -> dict[str, dict[str, Any]]:
    """返回 {plugin_id: contract}。"""
    data = json.loads(PLUGINS_FILE.read_text(encoding="utf-8"))
    return data.get("plugins", {})


def contract(plugin_id: str) -> dict[str, Any] | None:
    return load_contracts().get(plugin_id)


def enabled(config: dict[str, Any]) -> list[str]:
    """当前工程启用的插件 id 列表（配置顶层 plugins 字段）。"""
    raw = config.get("plugins") or []
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw]


def is_enabled(config: dict[str, Any], plugin_id: str) -> bool:
    return plugin_id in enabled(config)


def available_plugins() -> list[dict[str, Any]]:
    """给 GUI 的插件清单：带启用状态无关的静态信息。"""
    out = []
    for pid, c in load_contracts().items():
        out.append({
            "id": pid,
            "display_name": c.get("display_name", pid),
            "require_group": c.get("require_group", ""),
            "roles": c.get("roles", []),
            "board_effect": c.get("board_effect", {}),
            "note": c.get("note", ""),
        })
    return out


def _config_path(root: Path) -> Path:
    return model.default_config_path(root)


def _read_config(root: Path) -> tuple[dict[str, Any], Any]:
    path = _config_path(root)
    source = sdk_target.read_source(path)
    return model.load_config_text(source.text), source


def _write_config(root: Path, config: dict[str, Any], source: Any, message: str) -> dict[str, Any]:
    from .transaction import FileTransaction

    path = _config_path(root)
    text = model.dump_config(config)
    if text == source.text:
        return {"ok": True, "changed": 0, "message": "配置没有变化"}
    sdk_target.ensure_encodable(text, source.encoding)
    tx = FileTransaction.create(root, "omcfg_plugin")
    tx.write_bytes(
        path,
        sdk_target.SourceFile(path, text, source.encoding, source.newline, source.bom).render(),
        message,
    )
    manifest = tx.commit()
    return {"ok": True, "changed": 1, "manifest": str(manifest) if manifest else "", "message": message}


def _template_dir(plugin_id: str, c: dict[str, Any]) -> Path:
    """插件文件源目录：内置 omcfg/templates/<id>（契约 source 可覆盖）。"""
    src = c.get("source") or f"omcfg/templates/{plugin_id}"
    p = Path(src)
    return p if p.is_absolute() else Path(__file__).parent.parent / p


def _inject_files(root: Path, plugin_id: str, c: dict[str, Any]) -> dict[str, Any]:
    """把插件文件从内置模板注入工程 periph 目录。"""
    from . import ledc_injector

    tdir = _template_dir(plugin_id, c)
    periph = root / "projects" / "mouse_demo" / "periph"
    copied, skipped = [], []
    for name in c.get("files", []):
        src = tdir / name
        dst = periph / name
        if not src.is_file():
            return {"ok": False, "error": f"插件模板缺失: {src}"}
        if dst.is_file():
            skipped.append(name)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(name)
    uv = {"ok": True, "added": [], "skipped": [], "reason": "无新文件"}
    rte = {"ok": True, "changed": []}
    if copied:
        uv = ledc_injector.update_uvprojx(str(root))
        rte = ledc_injector.enable_ledc_rte(str(root))
    return {"ok": True, "copied": copied, "skipped": skipped, "uvprojx": uv, "rte": rte}


def _remove_file_blocks(text: str, names: list[str]) -> tuple[str, int]:
    """从 uvprojx 文本里移除指定 <FileName> 的 <File> 块。"""
    removed = 0
    for name in names:
        pat = re.compile(
            r"[ \t]*<File>\s*\r?\n"
            r"[ \t]*<FileName>" + re.escape(name) + r"</FileName>.*?"
            r"[ \t]*</File>\s*\r?\n?",
            re.DOTALL,
        )
        text, n = pat.subn("", text, count=1)
        removed += n
    return text, removed


def _remove_files(root: Path, plugin_id: str, c: dict[str, Any]) -> dict[str, Any]:
    periph = root / "projects" / "mouse_demo" / "periph"
    removed = []
    for name in c.get("files", []):
        p = periph / name
        if p.is_file():
            p.unlink()
            removed.append(name)
    # uvprojx 撤销登记
    uv = root / "projects" / "mouse_demo" / "keil5" / "SE71M.uvprojx"
    uv_removed = []
    if uv.is_file():
        raw = uv.read_bytes()
        bom = raw[:3] == b"\xef\xbb\xbf"
        enc = "utf-8-sig" if bom else "utf-8"
        text = raw.decode(enc, errors="replace")
        # .c 文件在 uvprojx 里有 <File> 块；.h 通常没有
        c_names = [n for n in c.get("files", []) if n.endswith(".c")]
        text, n = _remove_file_blocks(text, c_names)
        if n:
            uv.write_text(text, encoding=enc)
            uv_removed = c_names
    return {"ok": True, "removed": removed, "uvprojx_removed": uv_removed}


def _apply_board_effect(config: dict[str, Any], effect: dict[str, Any]) -> None:
    board = config.setdefault("board", {})
    board.update(effect)


def _auto_reassign(config: dict[str, Any], c: dict[str, Any]) -> list[str]:
    """按契约腾出被插件占用的脚（如 LED_MODE_B P01→P36）。返回变更说明。"""
    notes = []
    for rule in c.get("auto_reassign", []):
        role = rule.get("role")
        frm, to = rule.get("from"), rule.get("to")
        if not role or not to:
            continue
        entry = config.get("pins", {}).get(role)
        cur = entry.get("pin") if isinstance(entry, dict) else entry
        if frm and cur != frm:
            continue  # 没占着冲突脚，不动
        if isinstance(entry, dict):
            entry["pin"] = to
        else:
            config["pins"][role] = to
        notes.append(f"{role}: {cur}->{to}")
    return notes


def enable(root: Path | str, plugin_id: str) -> dict[str, Any]:
    """勾选插件：改 board + 腾脚 + 写 plugins 字段 + 注入文件。"""
    root = Path(root)
    c = contract(plugin_id)
    if not c:
        return {"ok": False, "error": f"未知插件: {plugin_id}"}
    config, source = _read_config(root)
    if is_enabled(config, plugin_id):
        return {"ok": True, "changed": 0, "message": f"插件 {plugin_id} 已启用", "already": True}

    notes = []
    # 1. board 效果
    if c.get("board_effect"):
        _apply_board_effect(config, c["board_effect"])
        notes.append("board 选项已更新")
    # 2. 腾脚（给插件角色让出合法脚）
    notes += _auto_reassign(config, c)
    # 3. plugins 字段持久化
    plist = enabled(config)
    plist.append(plugin_id)
    config["plugins"] = sorted(set(plist))
    # 4. 写配置
    saved = _write_config(root, config, source, f"启用插件 {plugin_id}")
    if not saved["ok"]:
        return saved
    # 5. 注入文件
    inj = _inject_files(root, plugin_id, c)
    if not inj["ok"]:
        return inj
    return {
        **saved,
        "plugin": plugin_id,
        "files": inj,
        "reassigned": notes,
        "message": (f"已启用「{c.get('display_name', plugin_id)}」：注入 "
                    f"{len(inj['copied'])} 个文件，解锁角色 "
                    f"{', '.join(c.get('roles', []))}"
                    + ("；已腾挪冲突脚：" + ", ".join(notes) if notes else "")),
    }


def disable(root: Path | str, plugin_id: str) -> dict[str, Any]:
    """取消插件：移除文件 + 撤销登记 + 改回 board + 清 plugins 字段 + 解除插件角色。"""
    root = Path(root)
    c = contract(plugin_id)
    if not c:
        return {"ok": False, "error": f"未知插件: {plugin_id}"}
    config, source = _read_config(root)
    if not is_enabled(config, plugin_id):
        return {"ok": True, "changed": 0, "message": f"插件 {plugin_id} 未启用", "already": True}

    # 1. 移除文件
    rm = _remove_files(root, plugin_id, c)
    # 2. 清插件角色（从 pins 里删）
    for role in c.get("roles", []):
        config.get("pins", {}).pop(role, None)
    # 3. board 还原
    if c.get("board_effect_off"):
        _apply_board_effect(config, c["board_effect_off"])
    # 4. plugins 字段
    config["plugins"] = [p for p in enabled(config) if p != plugin_id]
    if not config["plugins"]:
        config.pop("plugins", None)
    # 5. 写配置
    saved = _write_config(root, config, source, f"停用插件 {plugin_id}")
    if not saved["ok"]:
        return saved
    return {
        **saved,
        "plugin": plugin_id,
        "files_removed": rm,
        "message": (f"已停用「{c.get('display_name', plugin_id)}」：移除 "
                    f"{len(rm['removed'])} 个文件，解除角色 "
                    f"{', '.join(c.get('roles', []))}"),
    }


def status(root: Path | str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """插件状态：已启用/可启用，以及每个插件的角色是否被约束栏过滤。"""
    if config is None:
        config, _ = _read_config(Path(root))
    cur = enabled(config)
    out = []
    for pid, c in load_contracts().items():
        out.append({
            "id": pid,
            "display_name": c.get("display_name", pid),
            "enabled": pid in cur,
            "roles": c.get("roles", []),
            "require_group": c.get("require_group", ""),
        })
    return {"plugins": out, "enabled": cur}


def visible_roles(config: dict[str, Any], all_roles: dict[str, Any]) -> dict[str, Any]:
    """按已启用插件过滤角色表：插件专属角色仅在插件启用时可见。"""
    cur = enabled(config)
    reserved: set[str] = set()
    for pid in cur:
        c = contract(pid)
        if c:
            reserved.update(c.get("unlock_roles", c.get("roles", [])))
    # 判断一个角色是否为"插件专属"：出现在任一插件契约的 roles 里
    plugin_roles: set[str] = set()
    for c in load_contracts().values():
        plugin_roles.update(c.get("roles", []))
    return {
        mac: meta for mac, meta in all_roles.items()
        if mac not in plugin_roles or mac in reserved
    }
