"""pywebview 薄桥：只转调 model/validate/generator，不复制任何生成逻辑。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from . import (
    baseline,
    biz_sync,
    blank,
    derive,
    initproject,
    materials,
    model,
    newproject,
    pinmap,
    plugins,
    rules,
    validate,
    version as version_mod,
)
from .generate import generator
from .targets import sdk
from .transaction import FileTransaction

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs"


def _error(message: str, hint: str = "") -> dict:
    return {"ok": False, "error": message, "hint": hint}


def _first_line(exc: Exception) -> str:
    return str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__


def _config_candidates(root: Path) -> list[dict[str, object]]:
    """仓库 configs/ 里的现成配置；按 SDK 目录名自动匹配建议项。"""
    items: list[dict[str, object]] = []
    name = root.name.lower()
    for path in sorted(CONFIGS_DIR.glob("*.omcfg")):
        items.append(
            {
                "path": str(path),
                "name": path.stem,
                "suggested": path.stem.lower() in name,
            }
        )
    return items


def _needs_init(root: Path, missing: list[str]) -> dict:
    configs = _config_candidates(root)
    target = model.default_config_path(root)
    existing = str(target) if target.is_file() else ""
    suggested = next((str(item["path"]) for item in configs if item["suggested"]), "")
    # 初始化后写入的位置不能当输入配置：只预填真实存在的文件。
    prefill = existing or suggested
    if suggested:
        hint = f"已按目录名匹配 {Path(suggested).name}；确认后点「初始化」，或改用其它配置"
    elif existing:
        hint = "工程内已有 project.omcfg，可直接用它初始化（只补标记块）"
    else:
        hint = "该工程尚无可用配置：从 configs/ 选择 .omcfg 后点「初始化」，或点「从工程现状生成配置初稿」"
    return {
        "ok": False,
        "needs_init": True,
        "sdk": str(root),
        "config": str(target),
        "existing_config": existing,
        "prefill": prefill,
        "missing": missing,
        "configs": configs,
        "suggested": suggested,
        "error": "工程尚未初始化（缺少 OMCFG 标记块或配置）",
        "hint": hint,
    }


def _payload(root: Path, config: dict, report: validate.Report) -> dict:
    pins = model.resolved_pins(config)
    pinmap_data = pinmap.editable(config)
    pinmap_data["protected_roles"] = sorted(set(validate.required_roles(config, pins)) | {"KEY_C0_PIN"})
    return {
        "ok": report.ok,
        "sdk": str(root),
        "config": str(model.default_config_path(root)),
        "summary": validate.summary(config, report),
        "project": {
            "name": model.project(config).get("name", ""),
            "customer": model.project(config).get("customer", ""),
            "id": model.project_id(config),
        },
        "pins": [
            {
                "role": role,
                "pin": item["pin"],
                "mode": item["mode"],
                "pull": item["pull"],
                "init": item["init"],
            }
            for role, item in pins.items()
        ],
        "features": {key: value for key, value in model.features(config, pins).items()},
        "pinmap": pinmap_data,
        "issues": [issue.__dict__ for issue in report.errors + report.warnings],
    }


def _add_warning(root: Path, config: dict, report: validate.Report) -> None:
    warning = generator.sdk_warning(config, root)
    if warning:
        report.add_warning("project", warning[0], warning[1])
    audit = rules.audit(config, root, strict=False)
    report.warnings.extend(audit.warnings)


def _sync_wheel(text: str) -> str:
    """WHEEL_A/B 改脚后按 ENCODER 四对自动回写 board.wheel。"""
    config = model.load_config_text(text)
    pins = model.resolved_pins(config)
    if model.board(config).get("wheel") == "SOFT_GPIO":
        return text
    pair = {pins.get("WHEEL_A_PIN", {}).get("pin"), pins.get("WHEEL_B_PIN", {}).get("pin")}
    if not all(pair):
        return text
    for item in model.load_chip().get("mux", {}).get("ENCODER", {}).get("sdk_macros", []):
        if set(item.get("pins", [])) == pair:
            if model.board(config).get("wheel") != item["macro"]:
                return model.set_board_value_text(text, "wheel", str(item["macro"]))
            return text
    return text


LEDC_SOURCE_POOL = r"E:\M_2026\516_BM2017\software\trunk\SE71M_0516_BM2017_V1_20261022"


class Api:
    def load(self, sdk_path: str) -> dict:
        try:
            root = sdk.resolve_sdk(sdk_path)
        except Exception as exc:
            # 本地 GUI 边界，统一转为可见错误
            return _error(
                _first_line(exc),
                "确认路径是 SDK 根目录（应包含 projects/mouse_demo/periph/user_config.h）",
            )
        try:
            missing = initproject.missing_markers(root)
            if missing:
                return _needs_init(root, missing)
            config = model.load_config(model.default_config_path(root))
            report = validate.validate_config(config)
            _add_warning(root, config, report)
            return _payload(root, config, report)
        except Exception as exc:
            return _error(
                f"配置读取失败: {exc}",
                "检查 projects/mouse_demo/project.omcfg 的 YAML 缩进与字段",
            )

    def _init_error(self, root: Path, message: str, hint: str) -> dict:
        """初始化失败时保留初始化面板，避免界面回到空白。"""
        try:
            missing = initproject.missing_markers(root)
        except Exception:
            missing = []
        result = _needs_init(root, missing)
        result["error"] = message
        result["hint"] = hint
        return result

    def initialize(self, sdk_path: str, config_path: str) -> dict:
        """GUI 初始化入口：选配置 → 插入标记/填保护区 → 自动回到正常编辑流程。"""
        if not str(config_path or "").strip():
            return _error(
                "请选择一份 .omcfg 配置",
                "在配置下拉框选择，或点「从工程现状生成配置初稿」",
            )
        try:
            root = sdk.resolve_sdk(sdk_path)
        except Exception as exc:
            return _error(
                _first_line(exc),
                "确认路径是 SDK 根目录（应包含 projects/mouse_demo/periph/user_config.h）",
            )
        source = Path(config_path).expanduser()
        target = model.default_config_path(root)
        if not source.is_file():
            try:
                same_as_target = source.resolve() == target.resolve()
            except OSError:
                same_as_target = False
            if same_as_target:
                hint = (
                    "该路径是初始化后写入 project.omcfg 的位置，不是输入配置；"
                    "请从 configs/ 选择 .omcfg，或点「从工程现状生成配置初稿」"
                )
            else:
                hint = "从 configs/ 选择 .omcfg，或点「从工程现状生成配置初稿」"
            return self._init_error(root, f"配置不存在: {source}", hint)
        try:
            config = model.load_config(source)
            report = validate.validate_config(config)
            if not report.ok:
                result = _needs_init(root, initproject.missing_markers(root))
                result.update(_payload(root, config, report))
                result["error"] = "配置校验未通过，未执行初始化"
                result["hint"] = "修正配置里高亮的字段后重试"
                return result
            # 用户已点「初始化」并明确选择配置：允许覆盖旧的 project.omcfg。
            initproject.init_project(root, source, force=True, verbose=False)
            result = self.load(sdk_path)
            if result.get("ok"):
                result["message"] = "初始化完成，可以改引脚并预览 diff"
            return result
        except Exception as exc:
            return self._init_error(
                root,
                _first_line(exc),
                "检查文件是否只读/被 Keil 占用；若提示标记块残缺，请按上方缺失项人工修掉后重试",
            )

    def initialize_derived(self, sdk_path: str) -> dict:
        """新板首次接入：读 user_config.h/.c 推导配置初稿，再走同一套 init。"""
        try:
            root = sdk.resolve_sdk(sdk_path)
        except Exception as exc:
            return _error(
                _first_line(exc),
                "确认路径是 SDK 根目录（应包含 projects/mouse_demo/periph/user_config.h）",
            )
        try:
            config = derive.derive_config(root)
        except Exception as exc:
            return self._init_error(
                root,
                f"无法从工程现状推导配置: {_first_line(exc)}",
                "确认 user_config.h/.c 完整、未被占用；也可复制邻近板配置到 configs/ 后手工改引脚再初始化",
            )
        report = validate.validate_config(config)
        if not report.ok:
            result = _needs_init(root, initproject.missing_markers(root))
            result.update(_payload(root, config, report))
            result["error"] = "从工程现状推导的配置未通过校验，未执行初始化"
            result["hint"] = "按上方 errors 调整 user_config.h/.c，或手工复制邻近板配置后再试"
            return result
        try:
            text = derive.render(config)
            with tempfile.TemporaryDirectory(prefix="omcfg_derive_") as tmp:
                source = Path(tmp) / "derived.omcfg"
                source.write_text(text, encoding="utf-8")
                initproject.init_project(root, source, force=True, verbose=False)
            result = self.load(sdk_path)
            if result.get("ok"):
                target = model.default_config_path(root)
                pins = len(model.pin_entries(config))
                result["message"] = f"已按工程现状生成配置初稿（{pins} 个引脚）并初始化；初稿写入 {target}"
                result["derived"] = {
                    "pins": pins,
                    "project": model.project(config).get("name", ""),
                    "config": str(target),
                }
            return result
        except Exception as exc:
            return self._init_error(
                root,
                f"初始化失败: {_first_line(exc)}",
                "检查文件是否只读/被 Keil 占用；若提示标记块残缺，请按上方缺失项人工修掉后重试",
            )

    def check(self, sdk_path: str) -> dict:
        return self.load(sdk_path)

    def save_pinmap(self, sdk_path: str, assignments: dict[str, str] | None = None) -> dict:
        """全量角色→脚位映射写回 project.omcfg；空值表示解除分配。"""
        try:
            root = sdk.resolve_sdk(sdk_path)
            missing = initproject.missing_markers(root)
            if missing:
                return _needs_init(root, missing)
            config_path = model.default_config_path(root)
            source = sdk.read_source(config_path)
            text = source.text
            unknown = sorted(set(assignments or {}) - set(model.ROLE_ORDER))
            if unknown:
                return _error(
                    f"未知功能宏: {', '.join(unknown)}",
                    "只能提交 ROLE_ORDER 里列出的功能；未知角色请手工改配置",
                )
            for role, pin in (assignments or {}).items():
                value = str(pin or "").strip()
                text = model.remove_pin_text(text, role) if not value else model.add_pin_text(text, role, value)
            text = _sync_wheel(text)
            config = model.load_config_text(text)
            report = validate.validate_config(config)
            _add_warning(root, config, report)
            if not report.ok:
                result = _payload(root, config, report)
                result["error"] = "修改未通过校验，未写入 project.omcfg"
                return result
            result = _payload(root, config, report)
            if text == source.text:
                result["changed"] = 0
                result["message"] = "引脚没有变化"
                return result
            sdk.ensure_encodable(text, source.encoding)
            transaction = FileTransaction.create(root, "omcfg_gui_save")
            transaction.write_bytes(
                config_path,
                sdk.SourceFile(config_path, text, source.encoding, source.newline, source.bom).render(),
                "GUI 修改引脚",
            )
            result["manifest"] = str(transaction.commit())
            result["changed"] = 1
            result["message"] = "已保存 project.omcfg；接着点「预览 diff」"
            return result
        except Exception as exc:
            return _error(str(exc), "确认工程已初始化、文件未被占用")

    def choose_folder(self, initial: str | None = None) -> str | None:
        """弹出原生文件夹选择框，返回选中路径；取消返回 None。"""
        import os

        import webview

        directory = initial if (initial and os.path.isdir(initial)) else ""
        if not webview.windows:
            return None
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG, directory=directory)
        if not result:
            return None
        return result[0]

    def role_capabilities(self) -> dict:
        """返回芯片全量角色能力表（不受当前工程限制）。

        选项元数据来自 omcfg/data/options.json（吸收 role_catalog + 芯片 mux +
        KC536 基线与各模板的脚位经验），供 GUI 选项面板与 CLI 向导共用。
        """
        import json as _json
        import os as _os

        from . import model as _model
        from . import pinmap as _pinmap

        chip = _model.load_chip()
        data_dir = _os.path.join(_os.path.dirname(__file__), "data")
        cat_path = _os.path.join(data_dir, "role_catalog.json")
        opt_path = _os.path.join(data_dir, "options.json")
        cat = _json.load(open(cat_path, encoding="utf-8"))

        # 优先用收敛后的 options.json；缺文件时回退到旧的即时拼装，保证兼容。
        if _os.path.isfile(opt_path):
            options = _json.load(open(opt_path, encoding="utf-8"))
            roles = {}
            for mac, opt in options.get("options", {}).items():
                roles[mac] = {
                    "role_id": opt.get("role_id", ""),
                    "aliases": [mac] + list(opt.get("aliases", [])),
                    "allowed_pins": opt.get("allowed_pins", []),
                    "v1": bool(opt.get("v1", False)),
                    "display_name": opt.get("display_name", mac),
                    "tier": opt.get("tier", ""),
                    "trend": opt.get("trend", ""),
                    "suggested_pin": opt.get("suggested_pin"),
                    "alternate_pins": opt.get("alternate_pins", []),
                    "fixed": bool(opt.get("fixed", False)),
                    "required": bool(opt.get("required", False)),
                    "default_gpio": opt.get("default_gpio"),
                    "pair_with": opt.get("pair_with"),
                    "exclusive_with": opt.get("exclusive_with", []),
                }
            return {"roles": roles, "demand_groups": cat.get("demand_groups", [])}

        roles = {}
        for r in cat.get("roles", []):
            aliases = list(r.get("aliases", {}).values())
            if not aliases:
                continue
            primary = aliases[0]
            try:
                allowed = _pinmap.allowed_pins(chip, primary)
            except Exception:
                allowed = set()
            roles[primary] = {
                "role_id": r.get("id"),
                "aliases": aliases,
                "allowed_pins": sorted(allowed),
                "v1": bool(r.get("v1", False)),
                "display_name": r.get("display_name", ""),
                "tier": r.get("tier", ""),
                "trend": r.get("trend", ""),
            }
        return {"roles": roles, "demand_groups": cat.get("demand_groups", [])}

    def prepare_workspace(self, template_path: str, workspace: str) -> dict:
        """复制模板到工作区（排除编译产物/缓存），并写元数据标记。"""
        import json as _json
        import os as _os
        import subprocess as _sp

        if not _os.path.isdir(template_path):
            return {"ok": False, "error": "模板不存在: " + template_path}
        if _os.path.exists(workspace):
            return {"ok": False, "error": "工作区已存在: " + workspace}
        _os.makedirs(_os.path.dirname(workspace) or ". ", exist_ok=True)
        excl_dirs = [".git", "Objects", "Listings", ".cache", "out", "_build", ".vscode"]
        excl_files = ["*.d", "*.axf", "*.hex", "*.map", "*.bin", "*.htm", "*.lnp", "*.dep", "*.log", "*.idx"]
        cmd = ["robocopy", template_path, workspace, "/E"]
        for d in excl_dirs:
            cmd += ["/XD", d]
        for f in excl_files:
            cmd += ["/XF", f]
        res = _sp.run(cmd, capture_output=True, text=True)
        if res.returncode >= 8:
            return {"ok": False, "error": "robocopy 失败 code=" + str(res.returncode), "stderr": res.stderr[-500:]}
        meta = {"template": template_path, "workspace": workspace}
        with open(_os.path.join(workspace, ".omcfg_meta.json"), "w", encoding="utf-8") as f:
            _json.dump(meta, f, ensure_ascii=False, indent=2)
        return {"ok": True, "workspace": workspace}

    def generate_project(
        self, workspace: str, target_path: str, proj_id: str, proj_name: str, consumer_name: str = "", version: int = 1
    ) -> dict:
        """从工作区生成工程：复制模板 + 覆盖改动 + 改 ID/名称 + 写 project.omcfg。"""
        import hashlib as _hl
        import json as _json
        import os as _os
        import re as _re
        import subprocess as _sp

        meta_path = _os.path.join(workspace, ".omcfg_meta.json")
        if not _os.path.isfile(meta_path):
            return {"ok": False, "error": "工作区缺少 .omcfg_meta.json，请先 prepare_workspace"}
        meta = _json.load(open(meta_path, encoding="utf-8"))
        template = meta["template"]
        if _os.path.exists(target_path):
            return {"ok": False, "error": "目标已存在: " + target_path}
        if not _re.match(r"^0x[0-9A-Fa-f]{1,4}$", proj_id):
            try:
                proj_id = "0x%04X" % int(proj_id, 16)
            except Exception:
                return {"ok": False, "error": "ID 格式错误: " + proj_id}
        excl_dirs = [".git", "Objects", "Listings", ".cache", "out", "_build", ".vscode"]
        excl_files = ["*.d", "*.axf", "*.hex", "*.map", "*.bin", "*.htm", "*.lnp", "*.dep", "*.log", "*.idx"]
        cmd = ["robocopy", template, target_path, "/E"]
        for d in excl_dirs:
            cmd += ["/XD", d]
        for f in excl_files:
            cmd += ["/XF", f]
        res = _sp.run(cmd, capture_output=True, text=True)
        if res.returncode >= 8:
            return {"ok": False, "error": "复制模板失败 code=" + str(res.returncode)}

        def _hash(p):
            try:
                return _hl.sha256(open(p, "rb").read()).hexdigest()
            except Exception:
                return None

        def _rel(root, p):
            r = _os.path.relpath(p, root).replace("\\", "/")
            parts = r.split("/")
            for i, x in enumerate(parts):
                if x in ("projects", "hal", "common", "components", "mode_24g", "mode_usb", "utils"):
                    return "/".join(parts[i:])
            return r

        tpl_files = {}
        for dp, dns, fs in _os.walk(template):
            dns[:] = [d for d in dns if d not in excl_dirs]
            for f in fs:
                if any(f.endswith(x.replace("*", "")) for x in excl_files):
                    continue
                p = _os.path.join(dp, f)
                tpl_files[_rel(template, p)] = _hash(p)
        changed, added = [], []
        for dp, dns, fs in _os.walk(workspace):
            dns[:] = [d for d in dns if d not in excl_dirs]
            for f in fs:
                if f == ".omcfg_meta.json":
                    continue
                if any(f.endswith(x.replace("*", "")) for x in excl_files):
                    continue
                p = _os.path.join(dp, f)
                rel = _rel(workspace, p)
                h = _hash(p)
                tgt = _os.path.join(target_path, rel)
                if rel not in tpl_files:
                    _os.makedirs(_os.path.dirname(tgt), exist_ok=True)
                    import shutil as _sh

                    _sh.copy2(p, tgt)
                    added.append(rel)
                    continue
                if tpl_files[rel] != h:
                    import shutil as _sh

                    _sh.copy2(p, tgt)
                    changed.append(rel)
        apply_info = {}
        omcfg_dst = _os.path.join(target_path, "projects", "mouse_demo", "project.omcfg")
        if _os.path.isfile(omcfg_dst):
            try:
                _ra = self.apply(target_path)
                apply_info = {"ok": bool(_ra.get("ok")), "changed": _ra.get("changed", 0), "error": _ra.get("error")}
            except Exception as _e:
                apply_info = {"ok": False, "error": str(_e)}

        # apply 会重建 uvprojx（按 config），把手工注入的 ledc.c/ledc_mode.c 覆盖掉。
        # 若 target 存在 ledc.c 且 uvprojx 未登记，重新注入。
        _ledc_c = _os.path.join(target_path, "projects", "mouse_demo", "periph", "ledc.c")
        _ledc_mode_c = _os.path.join(target_path, "projects", "mouse_demo", "periph", "ledc_mode.c")
        if _os.path.isfile(_ledc_c) or _os.path.isfile(_ledc_mode_c):
            # 1. 更新 uvprojx：periph 组加 ledc.c/ledc_mode.c，driver 组加 drv_ledc.c
            try:
                from . import ledc_injector as _ledc_inj

                _uv_res = _ledc_inj.update_uvprojx(target_path)
                apply_info["uvprojx_after_apply"] = _uv_res
            except Exception as _e:
                apply_info["uvprojx_after_apply"] = {"ok": False, "reason": str(_e)}
            # 2. 补 user_config.h 的 6 个宏（apply 会重建 user_config.h，必须 apply 后补）
            try:
                _uc = _os.path.join(target_path, "projects", "mouse_demo", "periph", "user_config.h")
                if _os.path.isfile(_uc):
                    _t = open(_uc, encoding="utf-8", errors="replace").read()
                    _mod = False
                    # 2a. GPIO_SET/GPIO_CLEAR 别名（KC536 只有小写 gpio_set/gpio_clear）
                    if "#define GPIO_SET" not in _t:
                        _anchor = "#define gpio_clear(pin)     (OM_GPIO0->DATAOUTCLR = (1<<(pin)))"
                        if _anchor in _t:
                            _inject = (
                                _anchor
                                + "\n"
                                + "#define GPIO_SET(pin)       (OM_GPIO0->DATAOUTSET = (1<<(pin)))\n"
                                + "#define GPIO_CLEAR(pin)     (OM_GPIO0->DATAOUTCLR = (1<<(pin)))"
                            )
                            _t = _t.replace(_anchor, _inject, 1)
                            _mod = True
                    # 2b. LEDC 引脚宏
                    if "#define LEDC_CTRL_PIN" not in _t:
                        _marker = "//* USB 5V以及充电检测配置 */"
                        if _marker in _t:
                            _inject = (
                                "//* LEDC 灯带配置 */\n"
                                "#define LEDC_CTRL_PIN           (P34)\n"
                                "#define LEDC_PIN                (P21)\n"
                                "#define LEDC_RGB_NUMBER         7\n"
                                "#define LEDC_RGB_DATA_SIZE      LEDC_RGB_NUMBER*3\n\n"
                            )
                            _t = _t.replace(_marker, _inject + _marker, 1)
                            _mod = True
                    if _mod:
                        open(_uc, "w", encoding="utf-8").write(_t)
                        apply_info["ledc_macros_added"] = True
                    else:
                        apply_info["ledc_macros_added"] = False
            except Exception as _e:
                apply_info["ledc_macros_error"] = str(_e)
        cfg_path = _os.path.join(target_path, "projects", "mouse_demo", "periph", "user_config.h")
        if _os.path.isfile(cfg_path):
            text = None
            for enc in ("utf-8", "gbk"):
                try:
                    text = open(cfg_path, encoding=enc).read()
                    break
                except Exception:
                    pass
            if text:
                text = _re.sub(r"(#define\s+iPROJECT_ID_L\s+)0x[0-9A-Fa-f]+", r"\g<1>" + proj_id, text)
                text = _re.sub(r'(#define\s+iPROJECT_NAME\s+)"[^"]*"', r'\g<1>"' + proj_name + '"', text)
                if consumer_name:
                    text = _re.sub(r'(#define\s+iCONSUMER_NAME\s+)"[^"]*"', r'\g<1>"' + consumer_name + '"', text)
                text = _re.sub(r"(#define\s+iREAL_VERSION_ID\s+)\d+", r"\g<1>" + str(version), text)
                open(cfg_path, "w", encoding="utf-8").write(text)
        # 清理事务备份目录
        import glob as _glob
        import shutil as _sh2

        cleaned = []
        for bak in _glob.glob(_os.path.join(target_path, ".omcfg_bak_*")):
            try:
                _sh2.rmtree(bak)
                cleaned.append(_os.path.basename(bak))
            except Exception:
                pass
        return {
            "ok": True,
            "target": target_path,
            "changed": changed,
            "added": added,
            "cleaned_backups": cleaned,
            "changed_count": len(changed),
            "added_count": len(added),
            "proj_id": proj_id,
            "proj_name": proj_name,
            "apply": apply_info,
        }

    def generate_project_to_root(
        self, workspace: str, output_root: str, proj_id: str, proj_name: str, consumer_name: str = "", version: int = 1
    ) -> dict:
        """在 output_root 下按项目规范生成新工程。

        目录结构: output_root/<id_nozero>_<name>/software/trunk/SE71M_<id4>_<name>_V<n>_<date>/
        并创建 description/ 和 sample/ 空目录。
        """
        import datetime as _dt
        import os as _os
        import re as _re

        if not _os.path.isdir(output_root):
            return {"ok": False, "error": "输出根目录不存在: " + output_root}
        id_str = (proj_id or "").strip()
        id_hex = id_str[2:] if id_str.lower().startswith("0x") else id_str
        try:
            id_int = int(id_hex, 16)
        except Exception:
            return {"ok": False, "error": "ID 格式错误: " + str(proj_id)}
        id_4digit = "%04X" % id_int
        id_nozero = id_4digit.lstrip("0") or "0"
        name = (proj_name or "").strip()
        if not name:
            return {"ok": False, "error": "项目名为空"}
        if not _re.match(r"^[A-Za-z0-9_\-]+$", name):
            return {"ok": False, "error": "项目名只能含字母数字下划线连字符: " + name}
        date_str = _dt.datetime.now().strftime("%Y%m%d")
        project_root_name = id_nozero + "_" + name
        project_root = _os.path.join(output_root, project_root_name)
        if _os.path.exists(project_root):
            return {"ok": False, "error": "项目根目录已存在: " + project_root}
        trunk_dir = _os.path.join(project_root, "software", "trunk")
        _os.makedirs(trunk_dir, exist_ok=True)
        target_name = "SE71M_" + id_4digit + "_" + name + "_V" + str(version) + "_" + date_str
        target_path = _os.path.join(trunk_dir, target_name)
        r = self.generate_project(workspace, target_path, proj_id, proj_name, consumer_name, version)
        if not r.get("ok"):
            return r
        # 按 LEDC_PIN 校正 ledc.c / drv_ledc.c 的 PMU_LEDC_SEL_IO_xx
        r["ledc_sel_fix"] = self.finalize_ledc_sel(target_path)
        desc_dir = _os.path.join(project_root, "description")
        sample_dir = _os.path.join(project_root, "sample")
        _os.makedirs(desc_dir, exist_ok=True)
        _os.makedirs(sample_dir, exist_ok=True)
        r["project_root"] = project_root
        r["target"] = target_path
        r["description_dir"] = desc_dir
        r["sample_dir"] = sample_dir
        return r

    def cleanup_workspace(self, workspace: str) -> dict:
        """删除工作区目录（重新准备工程前调用）。"""
        import os as _os
        import shutil as _sh

        if not _os.path.exists(workspace):
            return {"ok": True, "msg": "工作区不存在"}
        try:
            _sh.rmtree(workspace)
            return {"ok": True, "msg": "已清理"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def open_folder(self, path: str) -> dict:
        """用资源管理器打开目录。"""
        import os as _os
        import subprocess as _sp

        if not _os.path.isdir(path):
            return {"ok": False, "error": "目录不存在: " + path}
        try:
            if _os.name == "nt":
                _sp.Popen(["explorer", path])
            else:
                _sp.Popen(["xdg-open", path])
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def inject_ledc_files(self, workspace: str, source_pool: str, force: bool = False) -> dict:
        """从 source_pool 注入 4 个 LEDC 文件到工作区，自动清洗缺失依赖。"""
        import os as _os

        from . import ledc_injector

        if not _os.path.isdir(workspace):
            return {"ok": False, "error": "工作区不存在: " + workspace}
        if not _os.path.isdir(source_pool):
            return {"ok": False, "error": "源工程不存在: " + source_pool}
        return ledc_injector.inject(source_pool, workspace, force=force)

    def prepare_workspace_with_modules(self, template_path: str, workspace: str, modules: list) -> dict:
        """
        modules 示例: ["ledc"]
        返回: {ok, workspace, modules: {ledc: {...}}, error?}
        """
        mods = []
        for m in modules or []:
            s = str(m).strip().lower()
            if s and s not in mods:
                mods.append(s)

        agg = {"ok": False, "workspace": workspace, "modules": {}}

        try:
            r = self.prepare_workspace(template_path, workspace)
            if isinstance(r, dict) and not r.get("ok", True):
                agg.update(error="prepare_workspace failed", detail=r)
                return agg

            r = self.initialize_derived(workspace)
            if isinstance(r, dict) and not r.get("ok", True):
                agg.update(error="initialize_derived failed", detail=r)
                return agg

            for m in mods:
                if m == "ledc":
                    ir = self.inject_ledc_files(workspace, LEDC_SOURCE_POOL)
                    # 手动覆盖 drv_ledc.c：inject_ledc_files 只复制 4 个 periph 文件，
                    # 不含 drv_ledc.c。KC536 模板自带 drv_ledc.c 用 PMU_LEDC_SEL_IO_01（P01），
                    # 与注入源（PMU_LEDC_SEL_IO_05，P05）冲突，导致勾了灯带但 DIN 指向 P01。
                    _rel = "hal/driver/om6239/drv_ledc.c"
                    _src = os.path.join(LEDC_SOURCE_POOL, _rel.replace("/", os.sep))
                    _dst = os.path.join(workspace, _rel.replace("/", os.sep))
                    if os.path.isfile(_src) and os.path.isfile(_dst):
                        with open(_src, "rb") as _f1:
                            _src_bytes = _f1.read()
                        with open(_dst, "rb") as _f2:
                            _dst_bytes = _f2.read()
                        if _src_bytes != _dst_bytes:
                            with open(_dst, "wb") as _f3:
                                _f3.write(_src_bytes)
                            ir.setdefault("forced", []).append(_rel)
                    agg["modules"]["ledc"] = ir
                    if not ir.get("ok", False):
                        agg.update(error="ledc inject failed", detail=ir)
                        return agg
                else:
                    agg["modules"][m] = {"ok": False, "error": f"unknown module: {m}"}
                    agg.update(error=f"unknown module: {m}")
                    return agg

            agg["ok"] = True
            return agg

        except Exception as e:
            agg.update(ok=False, error=repr(e))
            return agg

    def finalize_ledc_sel(self, target_path: str) -> dict:
        """按 project.omcfg 的 LEDC_PIN 校正 ledc.c / drv_ledc.c 的 PMU_LEDC_SEL_IO_xx。

        在 generate_project_to_root 生成工程后调用：模板注入的 drv_ledc.c 默认用
        IO_05（注入源），但若用户改 LEDC_PIN 为 P01，需校正为 IO_01。不改
        generate_project / apply 内部逻辑，只做文本替换。

        返回: {ok, changed: [...], ledc_pin, sel, reason?}
        """
        import re as _re

        root = Path(target_path)
        config_path = root / "projects" / "mouse_demo" / "project.omcfg"
        if not config_path.is_file():
            return {"ok": True, "changed": [], "reason": "无 project.omcfg，跳过"}

        try:
            config = model.load_config(config_path)
        except Exception as exc:
            return {"ok": False, "error": "读 project.omcfg 失败: " + str(exc)}

        pins = model.pin_entries(config) or {}
        ledc_pin = (pins.get("LEDC_PIN") or {}).get("pin")
        if not ledc_pin:
            return {"ok": True, "changed": [], "reason": "无 LEDC_PIN，跳过"}

        chip = model.load_chip()
        hint = None
        for opt in chip.get("mux", {}).get("LEDC_SEL", {}).get("options", []):
            if ledc_pin in opt.get("pins", []) and opt.get("sdk_hint"):
                hint = opt["sdk_hint"]
                break
        if not hint:
            return {
                "ok": False,
                "error": f"LEDC_PIN={ledc_pin} 无对应 SDK 枚举"
                f"（chip/om6239.json mux.LEDC_SEL.options 的 sdk_hint 为空）",
            }

        pat = _re.compile(r"drv_pmu_ledc_sel\s*\(\s*PMU_LEDC_SEL_IO_\d+\s*\)")
        replacement = "drv_pmu_ledc_sel(" + hint + ")"

        changed: list[str] = []
        for rel in ("projects/mouse_demo/periph/ledc.c", "hal/driver/om6239/drv_ledc.c"):
            p = root / rel
            if not p.is_file():
                continue
            try:
                body = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            new_body, n = pat.subn(replacement, body)
            if n > 0 and new_body != body:
                p.write_text(new_body, encoding="utf-8", newline="")
                changed.append(rel)

        return {"ok": True, "changed": changed, "ledc_pin": ledc_pin, "sel": hint}

    def preview(self, sdk_path: str) -> dict:
        try:
            root = sdk.resolve_sdk(sdk_path)
            missing = initproject.missing_markers(root)
            if missing:
                return _needs_init(root, missing)
            config = model.load_config(model.default_config_path(root))
            report = validate.validate_config(config)
            _add_warning(root, config, report)
            result = _payload(root, config, report)
            if not report.ok:
                return result
            outputs = generator.build_outputs(config, root)
            result["diffs"] = [{"path": str(item.path), "diff": item.diff()} for item in outputs if item.changed]
            result["changed"] = len(result["diffs"])
            return result
        except Exception as exc:
            return _error(str(exc), "确认工程已初始化、文件未被占用")

    def apply(self, sdk_path: str) -> dict:
        try:
            root = sdk.resolve_sdk(sdk_path)
            missing = initproject.missing_markers(root)
            if missing:
                return _needs_init(root, missing)
            config = model.load_config(model.default_config_path(root))
            report = validate.validate_config(config)
            _add_warning(root, config, report)
            if not report.ok:
                result = _payload(root, config, report)
                result["error"] = "校验未通过，拒绝写入"
                return result
            # 固件版本号：真相源 .omcfg 的 project.id.version，每次写盘 +1。
            # 必须在 build_outputs 之前递增，让 user_config.h 的 iREAL_VERSION_ID 同步；
            # .omcfg / startup 的写入与生成文件进同一事务，整体可回滚。
            transaction = FileTransaction.create(root, "omcfg_gui_apply")
            new_version, _version_writes = version_mod.bump(root, config, transaction)
            config["project"].setdefault("id", {})["version"] = new_version
            result = _payload(root, config, report)
            outputs = [item for item in generator.build_outputs(config, root) if item.changed]
            # 板型契约源码（key_io / sleep）必须与 user_config.h 同步改写：
            # 双脚模式下骨架 key_io.c 写死的 MODE_BLE_24G_PIN 需要改成双模式判断，
            # 否则生成头没有该宏 → Keil undeclared identifier。纳入同一事务可整体回滚。
            pins = model.pin_entries(config)
            feat = {
                "has_key_pair": "KEY_PAIR_PIN" in pins,
                "has_key_c0": "KEY_C0_PIN" in pins,
                "mode_dual": model.board(config).get("mode_pins") == "dual",
                "mode_single": model.board(config).get("mode_pins") == "single",
                "has_dpi_pair": "KEY_DPI_SUB_PIN" in pins and "KEY_DPI_ADD_PIN" in pins,
                "has_extra_keys": any(r in pins for r in ("KEY_B_PIN", "KEY_P_PIN", "KEY_DPI_PIN")),
            }
            periph = root / "projects/mouse_demo/periph"
            planned = biz_sync.plan_board_contracts(str(periph), feat)
            for item in outputs:
                transaction.write_bytes(item.path, item.render(), "GUI 按标记块写入")
            for path, new_text in planned:
                # 保留源码原编码（read 时按 utf-8 解码，写回同编码），避免 BOM/换行被改写。
                transaction.write_text(path, new_text, encoding="utf-8", newline="\n")
            # BLE 广播名：project.ble_names 是真相源，生成阶段同步到 mouse_hw.c /
            # ex2_app_mouse.c（走 newproject 的精确改写器，支持事务、幂等）。
            identity_rewrites = newproject.rewrite_identity(root, config, tx=transaction)
            total = len(outputs) + len(planned) + len(identity_rewrites) + 2  # .omcfg + startup
            result["manifest"] = str(transaction.commit()) if total else ""
            result["changed"] = total
            result["version"] = new_version
            result["message"] = f"已写入 {total} 个文件；固件版本 → {new_version}"
            return result
        except Exception as exc:
            return _error(str(exc), "确认工程已初始化、文件未被占用")

    # ------------------------------------------------------------------
    # 空白起步（CubeMX 式向导）：仅薄转调 blank + baseline + generator，
    # 不复制任何生成/校验逻辑；草稿态写入 project.omcfg 不要求必需脚齐全。
    # ------------------------------------------------------------------

    def blank_options(self) -> dict:
        """向导选项数据：角色能力 + 板型枚举 + 默认值。与 CLI 共用 options.json。"""
        try:
            caps = self.role_capabilities()
            board = blank.default_board()
            return {
                "ok": True,
                "roles": caps.get("roles", {}),
                "demand_groups": caps.get("demand_groups", []),
                    "board_enums": {
                        "mode_pins": sorted(model.MODE_ENUM),
                        "logo": sorted(model.LOGO_ENUM),
                        "sensor.bus": sorted(model.BUS_ENUM),
                        "polarity": sorted(model.POLARITY_ENUM),
                        "wheel": sorted(model.WHEEL_ENUM),
                        "mode_24g_led": sorted(model.MODE_24G_LED_ENUM),
                        "led_indicator": sorted(model.LED_INDICATOR_ENUM),
                    },
                    "board_defaults": board,
                    "plugins": plugins.available_plugins(),
                    "material_categories": materials.categories(),
                }
        except Exception as exc:
            return _error(str(exc), "确认 omcfg/data/options.json 存在")

    def blank_new(
        self,
        name: str,
        target: str,
        customer: str = "BYC",
        version: int = 1,
        id_low: int | None = None,
        ble_name: str | None = None,
    ) -> dict:
        """从内置 KC536 骨架建一个引脚为空的草稿工程，目标目录必须不存在。
        ble_name 给定则覆盖默认 BLE 广播名（否则生成 <项目名> Bt1/Bt2）。"""
        try:
            name = (name or "").strip()
            problem = baseline.name_problem(name)
            if problem:
                return _error(problem, "例如 MyMouse")
            dest = Path(target).expanduser().resolve()
            if dest.exists():
                return _error(f"目标路径已存在: {dest}", "请换一个不存在的目录")
            low = int(id_low) if id_low else 1
            if not 1 <= low <= 0xFFFF:
                return _error(f"项目号超出范围: 0x{low:X}", "范围 0x0001..0xFFFF")

            source, _ = baseline.ensure_ready()
            config = blank.empty_config(name, customer=customer or "BYC", version=int(version or 1))
            config["project"]["id"]["low"] = f"0x{low:04X}"
            ble = (ble_name or "").strip()
            if ble:
                config["project"]["ble_names"] = [ble]
            payload = (model.dump_config(config) + "\n").encode("utf-8")

            transaction = FileTransaction.create(dest, "omcfg_blank_new")
            copied = newproject.copy_skeleton(source, dest)
            config_target = model.default_config_path(dest)
            config_target.parent.mkdir(parents=True, exist_ok=True)
            transaction.write_bytes(config_target, payload, "写入空白项目配置")
            initproject.init_project(
                dest, config_target, force=False, verbose=False, announce_next=False, tx=transaction
            )
            transaction.commit()

            status = blank.summary(config, dest)
            return {
                "ok": True,
                "sdk": str(dest),
                "name": name,
                "config": str(config_target),
                "copied": copied,
                "ble_names": model.ble_names(config),
                "status": status,
                "message": (
                    f"空白工程已建（骨架 {copied} 文件）；已配 0/{status['total_roles']} 脚，"
                    f"缺必需脚 {len(status['missing'])} 个 —— 这是空白起步的正常状态"
                ),
            }
        except Exception as exc:
            return _error(str(exc), "确认目标可写、内置基线完整")

    def blank_status(self, sdk_path: str) -> dict:
        """草稿构建进度：已分配/缺失/冲突/是否可生成。"""
        try:
            root = sdk.resolve_sdk(sdk_path)
            path = model.default_config_path(root)
            if not path.is_file():
                return _error(f"工程尚无 project.omcfg: {path}", "先用空白新建或初始化")
            config = model.load_config(path)
            status = blank.summary(config, root)
            board = model.board(config)
            pin_entries = model.pin_entries(config)
            report = validate.validate_config(config)
            status.update(
                {
                    "ok": True,
                    "sdk": str(root),
                    "board": board,
                    "identity": {
                        "customer": model.project(config).get("customer", ""),
                        "ble_names": model.ble_names(config),
                    },
                    "polarity_map": model.polarity_map(config),
                    "polarity_roles": [
                        {
                            "role": role,
                            "display": display,
                            "led": is_led,
                            "pin": pin_entries[role]["pin"],
                            "effective": model.role_polarity(config, role),
                        }
                        for role, display, is_led in model.POLARITY_ROLES
                        if role in pin_entries
                    ],
                    "missing_detail": [
                        {
                            "role": role,
                            "suggested": blank.load_options().get(role, {}).get("suggested_pin"),
                        }
                        for role in status["missing"]
                    ],
                    "validate_errors": len(report.errors),
                    "validate_warnings": len(report.warnings),
                }
            )
            return status
        except Exception as exc:
            return _error(str(exc), "确认 sdk 指向工程根目录")

    def blank_set_polarity(self, sdk_path: str, polarities: dict | None = None) -> dict:
        """逐脚设置灯/按键极性。只接受当前工程里已配脚的角色，空值恢复默认。

        极性是每只脚自己的电气属性（上拉低有效/下拉高有效、高/低电平点亮），
        按原理图逐项指定；不按数量、统计或选料批量套用。
        """
        try:
            root = sdk.resolve_sdk(sdk_path)
            config_path = model.default_config_path(root)
            source = sdk.read_source(config_path)
            config = model.load_config_text(source.text)
            pins = model.pin_entries(config)
            updates = polarities or {}
            unknown = sorted(set(updates) - set(model.POLARITY_LED_NAMES) - set(model.POLARITY_KEY_NAMES))
            if unknown:
                return _error(f"不支持极性的角色: {', '.join(unknown)}", "极性角色见 model.POLARITY_ROLES")
            rejected = sorted(role for role in updates if role not in pins)
            if rejected:
                return _error(
                    "这些角色还没配脚，无法设极性: " + ", ".join(rejected),
                    "请先在配脚步骤把角色分配到脚位",
                )
            text = source.text
            for role, value in updates.items():
                val = "" if value in (None, "") else str(value)
                text = model.set_polarity_value_text(text, role, val)
            if text != source.text:
                sdk.ensure_encodable(text, source.encoding)
                transaction = FileTransaction.create(root, "omcfg_blank_polarity")
                transaction.write_bytes(
                    config_path,
                    sdk.SourceFile(config_path, text, source.encoding, source.newline, source.bom).render(),
                    "GUI 设置逐脚极性",
                )
                transaction.commit()
            new_config = model.load_config_text(text)
            return {
                "ok": True,
                "polarity": model.polarity_map(new_config),
                "effective": {r: model.role_polarity(new_config, r) for r in updates},
                "message": "逐脚极性已保存",
            }
        except Exception as exc:
            return _error(str(exc), "确认工程已初始化")

    def blank_save(
        self,
        sdk_path: str,
        assignments: dict[str, str] | None = None,
        reconcile: bool = False,
    ) -> dict:
        """草稿态写引脚：只做芯片 mux/占用校验，不卡必需脚（允许逐步构建）。

        语义与 save_pinmap 一致（全量角色→脚映射，空值解除），但跳过完整性校验，
        这样空白工程可以一步步保存中间状态。真正写入前的完整性把关在 blank_apply。
        """
        try:
            root = sdk.resolve_sdk(sdk_path)
            missing_markers = initproject.missing_markers(root)
            if missing_markers:
                return _needs_init(root, missing_markers)
            config_path = model.default_config_path(root)
            source = sdk.read_source(config_path)
            text = source.text
            opts = blank.load_options()

            assignments = assignments or {}
            unknown = sorted(set(assignments) - set(opts))
            if unknown:
                return _error(f"未知功能角色: {', '.join(unknown)}", "角色须来自 options.json")

            # 预检：每个非空分配在芯片上合法；同脚不冲突（LED 别名对除外）。
            target: dict[str, str] = {}
            aliases = {
                frozenset(("LED_MODE_R_PIN", "LED_R_PIN")),
                frozenset(("LED_MODE_G_PIN", "LED_G_PIN")),
                frozenset(("LED_MODE_B_PIN", "LED_B_PIN")),
            }
            chip = model.load_chip()
            for role, pin in assignments.items():
                value = str(pin or "").strip().upper()
                if not value:
                    continue
                allowed = opts.get(role, {}).get("allowed_pins", [])
                if allowed and value not in allowed:
                    return _error(
                        f"{role} -> {value}: 不是该功能的合法脚",
                        "合法脚: " + ", ".join(allowed[:8]) + (" ..." if len(allowed) > 8 else ""),
                    )
                problem = pinmap.role_pin_problem(chip, role, value)
                if problem:
                    return _error(f"{role} -> {value}: {problem}", "用选项数据里的合法脚")
                if value in target and frozenset((target[value], role)) not in aliases:
                    return _error(f"{value} 同时分配给 {target[value]} 和 {role}", "一个脚只能一个功能")
                target[role] = value

            for role, pin in target.items():
                text = model.add_pin_text(text, role, pin)
            for role in set(assignments) - set(target):
                text = model.remove_pin_text(text, role)
            text = _sync_wheel(text)

            new_config = model.load_config_text(text)
            reconcile_notes: list[str] = []
            if reconcile:
                from . import plugins as _plugins

                reconcile_notes = _plugins.reconcile_pins(new_config)
                if reconcile_notes:
                    for role in list(target) + [n.split(":")[0] for n in reconcile_notes]:
                        val = new_config.get("pins", {}).get(role)
                        pin = (val.get("pin") if isinstance(val, dict) else val) or ""
                        if pin:
                            text = model.add_pin_text(text, role, str(pin))
                        else:
                            text = model.remove_pin_text(text, role)
                    new_config = model.load_config_text(text)
            result = _payload(root, new_config, validate.validate_config(new_config))
            status = blank.summary(new_config, root)
            result["status"] = status
            result["reconciled"] = reconcile_notes
            # 草稿态：ok 表示“写入成功”，完整性看 status.complete。
            result["ok"] = True
            if text == source.text:
                result["changed"] = 0
                result["message"] = "引脚没有变化"
                return result
            sdk.ensure_encodable(text, source.encoding)
            transaction = FileTransaction.create(root, "omcfg_blank_save")
            transaction.write_bytes(
                config_path,
                sdk.SourceFile(config_path, text, source.encoding, source.newline, source.bom).render(),
                "GUI 草稿态保存引脚",
            )
            transaction.commit()
            result["changed"] = 1
            result["message"] = "草稿引脚已保存；可继续配置，补齐后点「预览 diff」"
            return result
        except Exception as exc:
            return _error(str(exc), "确认工程已初始化、文件未被占用")

    def blank_fill_recommended(self, sdk_path: str) -> dict:
        """一键按 KC536 基线整套方案配置全部必需脚。

        推荐源是内置 KC536 基线的**整套协调方案**——脚位互不冲突、编码器成对、
        board 选项自洽，因此一键填充后保证可生成。采用整体方案而非逐角色贪心，
        避免"前面角色占了后面角色推荐脚"的连锁冲突。会覆盖必需角色现有的脚位；
        用户微调请放在填充之后。
        """
        try:
            root = sdk.resolve_sdk(sdk_path)
            config_path = model.default_config_path(root)
            config = model.load_config(config_path)
            opts = blank.load_options()

            _, base_config_path = baseline.ensure_ready()
            base_cfg = model.load_config(base_config_path)
            base_pins = {
                role: (value.get("pin") if isinstance(value, dict) else value)
                for role, value in base_cfg.get("pins", {}).items()
            }

            # 一键填充保持严格：logo=ledc 时也按 keep_roles 填 LED_R/G/B，
            # 保证之后取消灯带插件回到 RGB 时不会缺脚。
            required = set(blank.missing_roles(config, root, include_ledc_rgb=True))
            # 当前已分配的角色也纳入：整体的基线方案要保证同脚唯一，需要一起重写。
            already = set(model.pin_entries(config))
            rewrite = {role for role in (required | already) if role in base_pins}

            assignments: dict[str, str] = {}
            problems: list[str] = []
            for role in sorted(rewrite):
                assignments[role] = base_pins[role]

            # 基线没覆盖却仍缺的角色（如外部板型选项引入的），用 options 兜底。
            for role in sorted(required - set(assignments)):
                sug = opts.get(role, {}).get("suggested_pin")
                if sug and not blank.assign_problem(config, role, sug):
                    assignments[role] = sug
                else:
                    problems.append(f"{role}: 基线无推荐脚，请手动选")

            saved = (
                self.blank_save(sdk_path, assignments, reconcile=True)
                if assignments
                else {"ok": True, "changed": 0}
            )
            if not saved.get("ok"):
                return saved
            status = self.blank_status(sdk_path)
            return {
                "ok": True,
                "filled": assignments,
                "reconciled": saved.get("reconciled", []),
                "problems": problems,
                "changed": saved.get("changed", 0),
                "status": status,
                "message": (
                    f"已按推荐方案配置 {len(assignments)} 个角色；"
                    + ("全部必需脚已齐，可点「预览 diff」" if status["complete"] else
                       f"仍缺 {len(status['missing'])} 个，请手动选脚")
                ),
            }
        except Exception as exc:
            return _error(str(exc), "确认工程已初始化")

    def blank_set_identity(self, sdk_path: str, updates: dict | None = None) -> dict:
        """设置工程身份：customer（客户名）与 ble_names（BLE 广播名列表）。
        ble_names 改动时同步改写 mouse_hw.c / ex2_app_mouse.c 的广播名（幂等）。"""
        try:
            root = sdk.resolve_sdk(sdk_path)
            config_path = model.default_config_path(root)
            source = sdk.read_source(config_path)
            text = source.text
            updates = updates or {}
            allowed = {"customer", "ble_names"}
            for key in updates:
                if key not in allowed:
                    return _error(f"不支持的身份字段: {key}", f"允许 {sorted(allowed)}")

            customer = updates.get("customer")
            if customer is not None:
                customer = str(customer).strip()
                if not customer:
                    return _error("customer 不能为空", "例如 BYC / APP")

            raw_names = updates.get("ble_names")
            names: list[str] | None = None
            if raw_names is not None:
                if isinstance(raw_names, str):
                    names = [n.strip() for n in raw_names.split(",") if n.strip()]
                elif isinstance(raw_names, list):
                    names = [str(n).strip() for n in raw_names if str(n).strip()]
                if not names:
                    return _error("ble_names 至少需要一个广播名", "例如 S205-BLE 或 BT1,BT2")
                for n in names:
                    if len(n) > 28:
                        return _error(f"BLE 广播名超过 28 字符会被截断: {n}", "MOUSE_NAME_MAX_LEN=29")

            if customer is not None:
                text = model.set_project_field_text(text, "customer", customer)
            if names is not None:
                literal = "[" + ", ".join(f'"{n}"' for n in names) + "]"
                text = model.set_project_field_text(text, "ble_names", literal)

            if text != source.text:
                config = model.load_config_text(text)
                sdk.ensure_encodable(text, source.encoding)
                transaction = FileTransaction.create(root, "omcfg_blank_identity")
                transaction.write_bytes(
                    config_path,
                    sdk.SourceFile(config_path, text, source.encoding, source.newline, source.bom).render(),
                    "GUI 设置工程身份",
                )
                if names is not None:
                    newproject.rewrite_identity(root, config, tx=transaction)
                transaction.commit()
            else:
                config = model.load_config_text(text)
            return {
                "ok": True,
                "customer": model.project(config).get("customer", ""),
                "ble_names": model.ble_names(config),
                "message": "工程身份已保存；BLE 广播名已同步到源码（如有改动）",
            }
        except Exception as exc:
            return _error(str(exc), "确认工程已初始化、源码文件未被占用")

    def blank_set_board(self, sdk_path: str, updates: dict | None = None) -> dict:
        """设置空白草稿的板型选项（mode_pins/logo/wheel 等），保留行尾注释。"""
        try:
            root = sdk.resolve_sdk(sdk_path)
            config_path = model.default_config_path(root)
            source = sdk.read_source(config_path)
            text = source.text
            allowed = {
                "mode_pins", "logo", "wheel", "led_polarity",
                "switch_segments", "ble_channels", "ledc_rgb_number",
                "sensor.dir_clock", "mode_24g_led", "led_indicator",
            }
            for key, value in (updates or {}).items():
                if key not in allowed:
                    return _error(f"不支持的板型选项: {key}", f"允许 {sorted(allowed)}")
                if key == "mode_24g_led":
                    led = str(value).upper()
                    if led not in model.MODE_24G_LED_ENUM:
                        return _error(
                            f"mode_24g_led 仅支持 {sorted(model.MODE_24G_LED_ENUM)}: {value}",
                            f"允许 {sorted(model.MODE_24G_LED_ENUM)}",
                        )
                    value = led
                if key == "led_indicator":
                    indicator = str(value).lower()
                    if indicator not in model.LED_INDICATOR_ENUM:
                        return _error(
                            f"led_indicator 仅支持 {sorted(model.LED_INDICATOR_ENUM)}: {value}",
                            f"允许 {sorted(model.LED_INDICATOR_ENUM)}",
                        )
                    value = indicator
                if key == "sensor.dir_clock":
                    try:
                        clock = int(value)
                    except (TypeError, ValueError):
                        return _error(f"sensor.dir_clock 必须是整数: {value}", f"允许 {sorted(model.DIR_CLOCK_ENUM)}")
                    if clock not in model.DIR_CLOCK_ENUM:
                        return _error(
                            f"sensor.dir_clock 仅支持 {sorted(model.DIR_CLOCK_ENUM)}: {clock}",
                            f"允许 {sorted(model.DIR_CLOCK_ENUM)}",
                        )
                    value = clock
                text = model.set_board_value_text(text, key, str(value))
            config = model.load_config_text(text)
            if text != source.text:
                sdk.ensure_encodable(text, source.encoding)
                transaction = FileTransaction.create(root, "omcfg_blank_board")
                transaction.write_bytes(
                    config_path,
                    sdk.SourceFile(config_path, text, source.encoding, source.newline, source.bom).render(),
                    "GUI 设置板型选项",
                )
                transaction.commit()
            status = blank.summary(config, root)
            return {
                "ok": True,
                "board": model.board(config),
                "status": status,
                "message": "板型选项已保存；缺脚清单已按新选项更新",
            }
        except Exception as exc:
            return _error(str(exc), "确认工程已初始化")

    def blank_apply(self, sdk_path: str) -> dict:
        """补齐后生成：先检查草稿完整性，再复用现有 preview/apply 链路。"""
        try:
            root = sdk.resolve_sdk(sdk_path)
            config = model.load_config(model.default_config_path(root))
            status = blank.summary(config, root)
            if not status["complete"]:
                return _error(
                    "草稿尚未补齐，不能生成：缺必需脚 "
                    + ", ".join(status["missing"])
                    + ("；冲突 " + "; ".join(status["conflicts"]) if status["conflicts"] else ""),
                    "先按推荐脚填充或手动选脚，确认「可生成: 是」后再应用",
                )
            return self.apply(sdk_path)
        except Exception as exc:
            return _error(str(exc), "确认 sdk 指向工程根目录")

    def plugin_status(self, sdk_path: str) -> dict:
        """插件启用状态 + 当前工程可见角色（按插件过滤）。"""
        try:
            root = sdk.resolve_sdk(sdk_path)
            config = model.load_config(model.default_config_path(root))
            st = plugins.status(root, config)
            caps = self.role_capabilities()
            st["roles"] = plugins.visible_roles(config, caps.get("roles", {}))
            st["demand_groups"] = caps.get("demand_groups", [])
            st["ok"] = True
            return st
        except Exception as exc:
            return _error(str(exc), "确认 sdk 指向工程根目录")

    def plugin_toggle(self, sdk_path: str, plugin_id: str, enable: bool = True) -> dict:
        """勾选/取消插件：改 board + 腾脚 + 注入/移除文件。"""
        try:
            root = sdk.resolve_sdk(sdk_path)
            result = plugins.enable(root, plugin_id) if enable else plugins.disable(root, plugin_id)
            if not result.get("ok"):
                return result
            # 插件变更后刷新状态与校验
            config = model.load_config(model.default_config_path(root))
            result["status"] = plugins.status(root, config)
            result["roles"] = plugins.visible_roles(config, self.role_capabilities().get("roles", {}))
            result["build_status"] = blank.summary(config, root)
            return result
        except Exception as exc:
            return _error(str(exc), "确认工程已初始化")

    # ------------------------------------------------------------------
    # 选料（物料驱动）：只处理用户显式选择；契约驱动角色/插件/板型。
    # ------------------------------------------------------------------
    def material_options(self) -> dict:
        """物料目录：分类、型号、参数（新建向导选料步用；无默认值）。"""
        try:
            return {"ok": True, "categories": materials.categories()}
        except Exception as exc:
            return _error(str(exc), "确认 omcfg/data/material_catalog.json 存在")

    def material_status(self, sdk_path: str) -> dict:
        """当前工程选料状态 + 推导副作用。"""
        try:
            root = sdk.resolve_sdk(sdk_path)
            config = model.load_config(model.default_config_path(root))
            st = materials.status(root, config)
            config2 = model.load_config(model.default_config_path(root))
            st["build_status"] = blank.summary(config2, root)
            return st
        except Exception as exc:
            return _error(str(exc), "确认 sdk 指向工程根目录")

    def material_apply(
        self,
        sdk_path: str,
        selected: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """落盘选料：写 project.materials + 改 board + 切插件 + 腾角色 + 源码保护。"""
        try:
            root = sdk.resolve_sdk(sdk_path)
            result = materials.apply(root, selected, params)
            if not result.get("ok"):
                return result
            config = model.load_config(model.default_config_path(root))
            result["roles"] = plugins.visible_roles(
                config, self.role_capabilities().get("roles", {})
            )
            result["plugin_state"] = plugins.status(root, config)
            result["build_status"] = blank.summary(config, root)
            return result
        except Exception as exc:
            return _error(str(exc), "确认工程已初始化")

    # ---- 自动填表（可视化入口）：从已有工程解析硬件事实，一键重建 ----
    def autofill_discover(self, root: str) -> dict:
        """扫描目录下所有可填表工程（含 projects/mouse_demo/user_config.h）。"""
        from . import autofill

        try:
            items = autofill.discover(Path(root).expanduser())
            return {"ok": True, "projects": items, "count": len(items)}
        except Exception as exc:
            return _error(str(exc), "确认目录存在且可读")

    def autofill_parse(self, header: str) -> dict:
        """只读解析单个工程，返回硬件需求预览（不写盘）。"""
        from . import autofill

        try:
            req = autofill.parse(Path(header).expanduser())
            preview = {
                k: req[k] for k in (
                    "header", "project_root", "name", "id_low", "version", "customer",
                    "ble_name", "style", "wheel", "dir_clock", "mode_24g_led",
                    "led_indicator", "selections", "params", "ledc_note",
                )
            }
            preview["pin_count"] = len(req["pins"])
            preview["polarity_count"] = len(req["polarity"])
            preview["mode_dual"] = req["mode_dual"]
            preview["has_key_c0"] = req["has_key_c0"]
            preview["has_ledc"] = req["has_ledc"]
            return {"ok": True, "req": preview}
        except Exception as exc:
            return _error(str(exc), "确认 user_config.h 路径正确")

    def autofill_start(self, header: str, out: str, name: str = "", keil: bool = True) -> dict:
        """后台启动自动填表；用 autofill_status 轮询日志与结果。"""
        from . import autofill

        try:
            return autofill.start_job(
                Path(header).expanduser(), Path(out).expanduser(), name=name, keil=bool(keil)
            )
        except Exception as exc:
            return _error(str(exc), "确认参数正确")

    def autofill_status(self) -> dict:
        """返回填表任务当前状态（running / lines / result / error）。"""
        from . import autofill

        return autofill.job_status()
