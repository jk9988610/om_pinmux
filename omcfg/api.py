"""pywebview 薄桥：只转调 model/validate/generator，不复制任何生成逻辑。"""

from __future__ import annotations

from pathlib import Path

from . import initproject, model, validate
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
    suggested = next((item["path"] for item in configs if item["suggested"]), "")
    return {
        "ok": False,
        "needs_init": True,
        "sdk": str(root),
        "config": str(model.default_config_path(root)),
        "missing": missing,
        "configs": configs,
        "suggested": suggested,
        "error": "工程尚未初始化（缺少 OMCFG 标记块或配置）",
        "hint": "选择配置后点「初始化」；初始化只插入标记并安装 project.omcfg，不改引脚正文",
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

    def initialize(self, sdk_path: str, config_path: str) -> dict:
        """GUI 初始化入口：选配置 → 插入标记/填保护区 → 自动回到正常编辑流程。"""
        if not str(config_path or "").strip():
            return _error(
                "请选择一份 .omcfg 配置", "在配置下拉框选择，或直接填写配置文件的绝对路径"
            )
        try:
            root = sdk.resolve_sdk(sdk_path)
        except Exception as exc:
            return _error(
                _first_line(exc),
                "确认路径是 SDK 根目录（应包含 projects/mouse_demo/periph/user_config.h）",
            )
        source = Path(config_path).expanduser()
        if not source.is_file():
            return _error(
                f"配置不存在: {source}", "从 configs/ 里选一份，或填写已存在的 .omcfg 路径"
            )
        try:
            config = model.load_config(source)
            report = validate.validate_config(config)
            if not report.ok:
                result = _payload(root, config, report)
                result.update(
                    {
                        "needs_init": True,
                        "configs": _config_candidates(root),
                        "missing": initproject.missing_markers(root),
                        "error": "配置校验未通过，未执行初始化",
                        "hint": "修正配置里高亮的字段后重试",
                    }
                )
                return result
            # 用户已点「初始化」并明确选择配置：允许覆盖旧的 project.omcfg。
            initproject.init_project(root, source, force=True, verbose=False)
            result = self.load(sdk_path)
            if result.get("ok"):
                result["message"] = "初始化完成，可以改引脚并预览 diff"
            return result
        except Exception as exc:
            try:
                missing = initproject.missing_markers(root)
            except Exception:
                missing = []
            result = _needs_init(root, missing)
            result["error"] = _first_line(exc)
            result["hint"] = (
                "检查文件是否只读/被 Keil 占用；若提示标记块残缺，"
                "请按上方缺失项人工修掉后重试"
            )
            return result

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
