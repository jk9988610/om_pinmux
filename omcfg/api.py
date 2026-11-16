"""pywebview 薄桥：只转调 model/validate/generator，不复制任何生成逻辑。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from . import derive, initproject, model, pinmap, rules, validate
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
        hint = (
            "该工程尚无可用配置：从 configs/ 选择 .omcfg 后点「初始化」，"
            "或点「从工程现状生成配置初稿」"
        )
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
    pinmap_data["protected_roles"] = sorted(
        set(validate.required_roles(config, pins)) | {"KEY_C0_PIN"}
    )
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
        except Exception as exc:  # 本地 GUI 边界，统一转为可见错误
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
                "检查文件是否只读/被 Keil 占用；若提示标记块残缺，"
                "请按上方缺失项人工修掉后重试",
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
                "确认 user_config.h/.c 完整、未被占用；也可复制邻近板配置到 configs/ "
                "后手工改引脚再初始化",
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
                result["message"] = (
                    f"已按工程现状生成配置初稿（{pins} 个引脚）并初始化；初稿写入 {target}"
                )
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
                "检查文件是否只读/被 Keil 占用；若提示标记块残缺，"
                "请按上方缺失项人工修掉后重试",
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
                text = model.remove_pin_text(text, role) if not value else model.add_pin_text(
                    text, role, value
                )
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
                sdk.SourceFile(
                    config_path, text, source.encoding, source.newline, source.bom
                ).render(),
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
        result = webview.windows[0].create_file_dialog(
            webview.FOLDER_DIALOG, directory=directory
        )
        if not result:
            return None
        return result[0]
    def role_capabilities(self) -> dict:
        """返回芯片全量角色能力表（不受当前工程限制）。"""
        import json as _json
        import os as _os

        from . import model as _model
        from . import pinmap as _pinmap
        chip = _model.load_chip()
        cat_path = _os.path.join(_os.path.dirname(__file__), "data", "role_catalog.json")
        cat = _json.load(open(cat_path, encoding="utf-8"))
        roles = {}
        for r in cat.get("roles", []):
            rid = r.get("id")
            aliases = list(r.get("aliases", {}).values())
            if not aliases:
                continue
            primary = aliases[0]
            try:
                allowed = _pinmap.allowed_pins(chip, primary)
            except Exception:
                allowed = set()
            roles[primary] = {
                "role_id": rid,
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
        for d in excl_dirs: cmd += ["/XD", d]
        for f in excl_files: cmd += ["/XF", f]
        res = _sp.run(cmd, capture_output=True, text=True)
        if res.returncode >= 8:
            return {"ok": False, "error": "robocopy 失败 code=" + str(res.returncode), "stderr": res.stderr[-500:]}
        meta = {"template": template_path, "workspace": workspace}
        with open(_os.path.join(workspace, ".omcfg_meta.json"), "w", encoding="utf-8") as f:
            _json.dump(meta, f, ensure_ascii=False, indent=2)
        return {"ok": True, "workspace": workspace}

    def generate_project(self, workspace: str, target_path: str, proj_id: str,
                         proj_name: str, consumer_name: str = "", version: int = 1) -> dict:
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
        if not _re.match(r'^0x[0-9A-Fa-f]{1,4}$', proj_id):
            try: proj_id = "0x%04X" % int(proj_id, 16)
            except Exception: return {"ok": False, "error": "ID 格式错误: " + proj_id}
        excl_dirs = [".git", "Objects", "Listings", ".cache", "out", "_build", ".vscode"]
        excl_files = ["*.d", "*.axf", "*.hex", "*.map", "*.bin", "*.htm", "*.lnp", "*.dep", "*.log", "*.idx"]
        cmd = ["robocopy", template, target_path, "/E"]
        for d in excl_dirs: cmd += ["/XD", d]
        for f in excl_files: cmd += ["/XF", f]
        res = _sp.run(cmd, capture_output=True, text=True)
        if res.returncode >= 8:
            return {"ok": False, "error": "复制模板失败 code=" + str(res.returncode)}
        def _hash(p):
            try: return _hl.sha256(open(p, "rb").read()).hexdigest()
            except Exception: return None
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
                if any(f.endswith(x.replace("*", "")) for x in excl_files): continue
                p = _os.path.join(dp, f)
                tpl_files[_rel(template, p)] = _hash(p)
        changed, added = [], []
        for dp, dns, fs in _os.walk(workspace):
            dns[:] = [d for d in dns if d not in excl_dirs]
            for f in fs:
                if f == ".omcfg_meta.json": continue
                if any(f.endswith(x.replace("*", "")) for x in excl_files): continue
                p = _os.path.join(dp, f)
                rel = _rel(workspace, p)
                h = _hash(p)
                tgt = _os.path.join(target_path, rel)
                if rel not in tpl_files:
                    _os.makedirs(_os.path.dirname(tgt), exist_ok=True)
                    import shutil as _sh; _sh.copy2(p, tgt); added.append(rel); continue
                if tpl_files[rel] != h:
                    import shutil as _sh; _sh.copy2(p, tgt); changed.append(rel)
        apply_info = {}
        omcfg_dst = _os.path.join(target_path, "projects", "mouse_demo", "project.omcfg")
        if _os.path.isfile(omcfg_dst):
            try:
                _ra = self.apply(target_path)
                apply_info = {"ok": bool(_ra.get("ok")), "changed": _ra.get("changed", 0),
                              "error": _ra.get("error")}
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
                            _inject = (_anchor + "\n" +
                                       "#define GPIO_SET(pin)       (OM_GPIO0->DATAOUTSET = (1<<(pin)))\n" +
                                       "#define GPIO_CLEAR(pin)     (OM_GPIO0->DATAOUTCLR = (1<<(pin)))")
                            _t = _t.replace(_anchor, _inject, 1)
                            _mod = True
                    # 2b. LEDC 引脚宏
                    if "#define LEDC_CTRL_PIN" not in _t:
                        _marker = "//* USB 5V以及充电检测配置 */"
                        if _marker in _t:
                            _inject = ("//* LEDC 灯带配置 */\n"
                                       "#define LEDC_CTRL_PIN           (P34)\n"
                                       "#define LEDC_PIN                (P21)\n"
                                       "#define LEDC_RGB_NUMBER         7\n"
                                       "#define LEDC_RGB_DATA_SIZE      LEDC_RGB_NUMBER*3\n\n")
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
                try: text = open(cfg_path, encoding=enc).read(); break
                except Exception: pass
            if text:
                text = _re.sub(r'(#define\s+iPROJECT_ID_L\s+)0x[0-9A-Fa-f]+', r'\g<1>' + proj_id, text)
                text = _re.sub(r'(#define\s+iPROJECT_NAME\s+)"[^"]*"', r'\g<1>"' + proj_name + '"', text)
                if consumer_name:
                    text = _re.sub(r'(#define\s+iCONSUMER_NAME\s+)"[^"]*"', r'\g<1>"' + consumer_name + '"', text)
                text = _re.sub(r'(#define\s+iREAL_VERSION_ID\s+)\d+', r'\g<1>' + str(version), text)
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
        return {"ok": True, "target": target_path, "changed": changed, "added": added,
                "cleaned_backups": cleaned,
                "changed_count": len(changed), "added_count": len(added),
                "proj_id": proj_id, "proj_name": proj_name, "apply": apply_info}
    def generate_project_to_root(self, workspace: str, output_root: str, proj_id: str,
                                  proj_name: str, consumer_name: str = "", version: int = 1) -> dict:
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
        if not _re.match(r'^[A-Za-z0-9_\-]+$', name):
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
        for m in (modules or []):
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
            result["diffs"] = [
                {"path": str(item.path), "diff": item.diff()} for item in outputs if item.changed
            ]
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
            result = _payload(root, config, report)
            if not report.ok:
                result["error"] = "校验未通过，拒绝写入"
                return result
            outputs = [item for item in generator.build_outputs(config, root) if item.changed]
            transaction = FileTransaction.create(root, "omcfg_gui_apply")
            for item in outputs:
                transaction.write_bytes(item.path, item.render(), "GUI 按标记块写入")
            result["manifest"] = str(transaction.commit()) if outputs else ""
            result["changed"] = len(outputs)
            result["message"] = f"已写入 {len(outputs)} 个文件" if outputs else "没有文件变化"
            return result
        except Exception as exc:
            return _error(str(exc), "确认工程已初始化、文件未被占用")
