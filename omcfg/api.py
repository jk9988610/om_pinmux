"""pywebview 薄桥：只转调 model/validate/generator，不复制任何生成逻辑。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from . import derive, initproject, model, validate
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
        "issues": [issue.__dict__ for issue in report.errors + report.warnings],
    }


def _add_warning(root: Path, config: dict, report: validate.Report) -> None:
    warning = generator.sdk_warning(config, root)
    if warning:
        report.add_warning("project", warning[0], warning[1])


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

    def save_pins(self, sdk_path: str, updates: list[dict] | None = None) -> dict:
        """把前端提交的引脚修改写回 project.omcfg；校验失败时不落盘。"""
        try:
            root = sdk.resolve_sdk(sdk_path)
            missing = initproject.missing_markers(root)
            if missing:
                return _needs_init(root, missing)
            config_path = model.default_config_path(root)
            source = sdk.read_source(config_path)
            text = source.text
            for update in updates or []:
                role = str(update.get("role") or "").strip()
                pin = str(update.get("pin") or "").strip()
                if role and pin:
                    text = model.set_pin_text(text, role, pin)
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
