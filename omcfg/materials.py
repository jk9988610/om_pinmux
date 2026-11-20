# -*- coding: utf-8 -*-
"""选料驱动：物料型号 -> 角色/约束/板型/插件/参数。

契约在 omcfg/data/material_catalog.json（v3）。本模块只做通用执行与推导：
- 读取目录里的 categories/options/params；
- 把**用户显式选中**的物料翻译成 required_roles / remove_roles /
  board 选项 / 插件开关 / 参数；
- 落盘选料并按契约改 board、腾角色、切插件、注入或移除文件。

重要原则：目录不再携带统计默认值。未选择的分类不产生任何副作用，
统计资料只留在 material_scan.json / docs 供内部参考，绝不替用户做决定。
RGB 点亮极性由原理图决定，属于 board 选项，不由选料自动推导。

不为某个物料型号写死逻辑：新增物料只改 catalog，不动本文件。
与 plugins.py 同构，复用其 enable/disable 做插件切换。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import model
from .targets import sdk as sdk_target

CATALOG_PATH = Path(__file__).parent / "data" / "material_catalog.json"

# 空字符串 = 用户显式清除该项；None = 未触碰，保持工程原值。
CLEAR = ""


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def categories() -> list[dict[str, Any]]:
    """给 GUI 的物料分类清单（不含任何默认选择）。"""
    return load_catalog().get("categories", [])


def _iter_options(cat: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {o["id"]: o for o in cat.get("options", [])}


def _iter_params(cat: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["id"]: p for p in cat.get("params", [])}


def default_selections() -> tuple[dict[str, str], dict[str, Any]]:
    """历史接口：v3 起选料没有默认值，返回空集合。

    保留函数名是为了兼容旧脚本；新代码应直接读 project.materials，
    未选择的分类即「未指定」，不推导任何角色或板型。
    """
    return {}, {}


def normalize(
    selected_in: dict[str, Any] | None, params_in: dict[str, Any] | None
) -> tuple[dict[str, str], dict[str, Any], list[str]]:
    """校验用户显式选择。返回 (selected, params, errors)。

    - 目录里未出现的分类 / 参数：不写入，保持工程原值；
    - 传入 CLEAR（空字符串）：清除该项（从结果里移除，并记录清除动作由
      board_key 反向还原）；
    - 未知型号 / 非法参数：报错并忽略该项，绝不回退到某个"统计默认"。
    """
    merged_sel: dict[str, str] = {}
    merged_params: dict[str, Any] = {}
    errors: list[str] = []
    selected_in = selected_in or {}
    params_in = params_in or {}
    for cat in categories():
        cid = cat["id"]
        opts = _iter_options(cat)
        if opts:
            incoming = selected_in.get(cid)
            if incoming == CLEAR:
                merged_sel.pop(cid, None)
            elif incoming is not None:
                if incoming not in opts:
                    errors.append(f"{cid}: 未知型号 {incoming}")
                else:
                    merged_sel[cid] = str(incoming)
            chosen = opts.get(merged_sel.get(cid, ""), {})
            # 型号自带的 params 只在型号被选中时生效。
            for key, value in (chosen.get("effects") or {}).get("params", {}).items():
                merged_params[key] = value
        for pid, pdef in _iter_params(cat).items():
            if pid not in params_in:
                continue
            if params_in[pid] == CLEAR:
                # 清除显式参数，但型号自带的 params 优先（用户改型号时不会被旧值覆盖）。
                merged_params.pop(pid, None)
                continue
            coerced = _coerce(params_in[pid], pdef, errors, pid)
            if coerced is not None:
                merged_params[pid] = coerced
    return merged_sel, merged_params, errors


def _coerce(value: Any, pdef: dict[str, Any], errors: list[str], pid: str) -> Any:
    ptype = pdef.get("type")
    allowed = pdef.get("allowed")
    if ptype == "int" or (isinstance(value, str) and value.lstrip("-").isdigit()):
        try:
            value = int(value)
        except (TypeError, ValueError):
            errors.append(f"{pid}: 需要整数，收到 {value!r}")
            return None
    minimum, maximum = pdef.get("min"), pdef.get("max")
    if isinstance(value, int):
        if minimum is not None and value < minimum:
            errors.append(f"{pid}: 不能小于 {minimum}，收到 {value!r}")
            return None
        if maximum is not None and value > maximum:
            errors.append(f"{pid}: 不能大于 {maximum}，收到 {value!r}")
            return None
    if allowed is not None and value not in allowed:
        errors.append(f"{pid}: 只允许 {allowed}，收到 {value!r}")
        return None
    return value


def apply_effects(selected: dict[str, str], params: dict[str, Any]) -> dict[str, Any]:
    """把**显式选料**翻译成聚合副作用（不落盘、不改工程）。"""
    board: dict[str, Any] = {}
    required: list[str] = []
    remove: list[str] = []
    plugin_toggles: list[dict[str, Any]] = []
    merged_params: dict[str, Any] = dict(params)
    for cat in categories():
        opts = _iter_options(cat)
        chosen = opts.get(selected.get(cat["id"], ""), {})
        eff = chosen.get("effects") or {}
        board.update(eff.get("board", {}))
        for role in eff.get("required_roles", []):
            if role not in required:
                required.append(role)
        for role in eff.get("remove_roles", []):
            if role not in remove:
                remove.append(role)
        for key, value in eff.get("params", {}).items():
            merged_params[key] = value
        if eff.get("plugin"):
            plugin_toggles.append(dict(eff["plugin"]))
    # 用户显式填写的 params 才映射到 board。极性不在此列：它由原理图决定。
    for cat in categories():
        for pid, pdef in _iter_params(cat).items():
            bkey = pdef.get("board_key")
            if bkey and pid in merged_params:
                board[bkey] = merged_params[pid]
    return {
        "board": board,
        "required_roles": required,
        "remove_roles": remove,
        "plugin_toggles": plugin_toggles,
        "params": merged_params,
    }


def board_keys_for_params() -> dict[str, str]:
    """param_id -> board_key，用于清除参数时反向还原工程值。"""
    out: dict[str, str] = {}
    for cat in categories():
        for pid, pdef in _iter_params(cat).items():
            if pdef.get("board_key"):
                out[pid] = pdef["board_key"]
    return out


def _read_config(root: Path) -> tuple[dict[str, Any], Any]:
    path = model.default_config_path(root)
    source = sdk_target.read_source(path)
    return model.load_config_text(source.text), source


def read_selection(config: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    """从 project.materials 读取用户显式选择；没有则空，不注入任何默认。"""
    store = model.project(config).get("materials") or {}
    if not isinstance(store, dict):
        return {}, {}
    selected = {str(k): str(v) for k, v in (store.get("selected") or {}).items() if v not in (None, CLEAR)}
    params = dict(store.get("params") or {})
    # 以当前选料为准重新合并型号自带 params（避免旧值残留）。
    for cat in categories():
        chosen = _iter_options(cat).get(selected.get(cat["id"], ""), {})
        for key, value in (chosen.get("effects") or {}).get("params", {}).items():
            params[key] = value
    return selected, params


def status(root: Path | str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """当前选料状态 + 可用目录 + 推导副作用（供 GUI 展示）。"""
    root = Path(root)
    if config is None:
        config, _ = _read_config(root)
    selected, params = read_selection(config)
    eff = apply_effects(selected, params)
    return {
        "ok": True,
        "categories": categories(),
        "selected": selected,
        "params": params,
        "effects": eff,
        "board": model.board(config),
    }


def required_roles(config: dict[str, Any]) -> list[str]:
    """当前选料带来的额外必需角色（供 validate/blank 叠加）。"""
    if not model.project(config).get("materials"):
        return []
    selected, params = read_selection(config)
    return list(apply_effects(selected, params)["required_roles"])


def removed_roles(config: dict[str, Any]) -> list[str]:
    """当前选料明确移除的角色（充电管理=none / 无 mode 键）。"""
    if not model.project(config).get("materials"):
        return []
    selected, params = read_selection(config)
    return list(apply_effects(selected, params)["remove_roles"])


def material_params(config: dict[str, Any]) -> dict[str, Any]:
    """当前选料解析出的参数（RGB 数量、拨杆段数、蓝牙通道、传感器型号等）。"""
    selected, params = read_selection(config)
    return dict(apply_effects(selected, params)["params"])


def _write_config(root: Path, config: dict[str, Any], source: Any, message: str) -> dict[str, Any]:
    from .transaction import FileTransaction

    path = model.default_config_path(root)
    text = model.dump_config(config)
    if text == source.text:
        return {"ok": True, "changed": 0, "message": "选料没有变化"}
    sdk_target.ensure_encodable(text, source.encoding)
    tx = FileTransaction.create(root, "omcfg_material")
    tx.write_bytes(
        path,
        sdk_target.SourceFile(path, text, source.encoding, source.newline, source.bom).render(),
        message,
    )
    manifest = tx.commit()
    return {"ok": True, "changed": 1, "manifest": str(manifest) if manifest else "", "message": message}


def _guard_key_pair_source(root: Path) -> list[str]:
    """无 mode 键时给 key_io.c/.h 的 PAIR 引用加 #ifdef 保护，保证可编译。

    复用 biz_sync 的幂等补丁：若已带保护则不再改。返回变更说明。
    """
    from . import biz_sync

    periph = root / "projects" / "mouse_demo" / "periph"
    notes: list[str] = []
    for name, patch, feat in (
        ("key_io.h", biz_sync._patch_key_io_h, {}),
        ("key_io.c", biz_sync._patch_key_io_c, {"has_key_pair": False}),
    ):
        path = periph / name
        if not path.is_file():
            continue
        src = sdk_target.read_source(path)
        new, these = patch(src.text, feat)
        if new != src.text:
            sdk_target.ensure_encodable(new, src.encoding)
            path.write_bytes(
                sdk_target.SourceFile(path, new, src.encoding, src.newline, src.bom).render()
            )
            notes.append(f"{name}: " + ", ".join(these))
    return notes


def apply(root: Path | str, selected: dict[str, Any] | None, params: dict[str, Any] | None) -> dict[str, Any]:
    """落盘选料：写 project.materials + 应用 board + 移除角色 + 切插件 + 源码保护。"""
    from . import plugins

    root = Path(root)
    sel, par, errors = normalize(selected, params)
    if errors:
        return {"ok": False, "error": "选料参数非法", "details": errors}
    eff = apply_effects(sel, par)

    config, source = _read_config(root)
    _, old_params = read_selection(config)
    notes: list[str] = []

    # 1. 写 project.materials（只存用户显式选择；空 dict 表示未选料）
    proj = config.setdefault("project", {})
    if sel or par:
        proj["materials"] = {"selected": sel, "params": par}
    else:
        proj.pop("materials", None)

    # 2. 应用 board 选项（RGB 数量/拨杆段数/蓝牙通道/传感器总线）。
    #    点亮极性不在这里：它由 board 步骤按原理图显式设置。
    board = config.setdefault("board", {})
    for key, value in eff["board"].items():
        if key == "sensor.bus":
            board.setdefault("sensor", {})["bus"] = value
        else:
            board[key] = value
    if eff["board"]:
        notes.append("board 选项已按选料更新")

    # 用户清掉的参数：只在 board 当前值确实由旧选料写入时才还原，避免覆盖
    # 用户在「板型选项」步骤手工设置的值。
    for pid, bkey in board_keys_for_params().items():
        if pid in par or pid in eff["params"]:
            continue
        if pid not in old_params:
            continue
        if isinstance(bkey, str) and "." in bkey:
            prefix, leaf = bkey.split(".", 1)
            holder = board.get(prefix)
            if isinstance(holder, dict) and holder.get(leaf) == old_params[pid]:
                holder.pop(leaf, None)
                notes.append(f"还原板型 {bkey}")
        elif board.get(bkey) == old_params[pid]:
            board.pop(bkey, None)
            notes.append(f"还原板型 {bkey}")

    # 3. 移除物料不需要的角色（充电=none、无 mode 键）
    pins = config.get("pins", {})
    for role in eff["remove_roles"]:
        if role in pins:
            pins.pop(role)
            notes.append(f"解除角色 {role}")

    # 4. 蓝牙通道 -> 广播名数量
    channels = par.get("ble_channels")
    names = proj.get("ble_names")
    if isinstance(channels, int) and isinstance(names, list) and names:
        base = names[0]
        proj["ble_names"] = [f"{base}"] + ([f"{base}2"] if channels >= 2 else [])
        notes.append(f"蓝牙广播名调整为 {len(proj['ble_names'])} 个")

    saved = _write_config(root, config, source, "GUI 应用选料")
    if not saved["ok"]:
        return saved

    # 5. 切插件（复用 plugins.enable/disable，契约驱动注入/移除文件）
    plugin_results = []
    cur_enabled = plugins.enabled(config)
    for toggle in eff["plugin_toggles"]:
        pid, want = toggle.get("id"), bool(toggle.get("enable"))
        if not pid:
            continue
        if (pid in cur_enabled) == want:
            continue
        r = plugins.enable(root, pid) if want else plugins.disable(root, pid)
        plugin_results.append({"id": pid, "enable": want, "ok": r.get("ok", False)})
        if not r.get("ok"):
            notes.append(f"插件 {pid} 切换失败: {r.get('error', '未知')}")

    # 6. 无 mode 键 -> 源码 PAIR 引用加保护（保证 Keil 可编译）
    guard_notes: list[str] = []
    if "mode_key" in par and par["mode_key"] is False:
        guard_notes = _guard_key_pair_source(root)
        notes += guard_notes

    latest, _ = _read_config(root)
    return {
        **saved,
        "selected": sel,
        "params": par,
        "effects": eff,
        "plugins": plugin_results,
        "guarded": guard_notes,
        "status": status(root, latest),
        "message": "选料已应用：" + ("；".join(notes) if notes else "无变化"),
    }
