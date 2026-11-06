"""pywebview 薄桥：只转调 model/validate/generator，不复制任何生成逻辑。"""

from __future__ import annotations

from pathlib import Path

from . import model, validate
from .generate import generator
from .targets import sdk
from .transaction import FileTransaction


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
            config_path = model.default_config_path(root)
            if not config_path.is_file():
                return {"ok": False, "error": f"缺少 {config_path}；先运行 omcfg init"}
            config = model.load_config(config_path)
            report = validate.validate_config(config)
            _add_warning(root, config, report)
            return _payload(root, config, report)
        except Exception as exc:  # 本地 GUI 边界，统一转为可见错误
            return {"ok": False, "error": str(exc)}

    def check(self, sdk_path: str) -> dict:
        return self.load(sdk_path)

    def save_pins(self, sdk_path: str, updates: list[dict] | None = None) -> dict:
        """把前端提交的引脚修改写回 project.omcfg；校验失败时不落盘。"""
        try:
            root = sdk.resolve_sdk(sdk_path)
            config_path = model.default_config_path(root)
            if not config_path.is_file():
                return {"ok": False, "error": f"缺少 {config_path}；先运行 omcfg init"}
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
            return {"ok": False, "error": str(exc)}

    def preview(self, sdk_path: str) -> dict:
        try:
            root = sdk.resolve_sdk(sdk_path)
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
            return {"ok": False, "error": str(exc)}

    def apply(self, sdk_path: str) -> dict:
        try:
            root = sdk.resolve_sdk(sdk_path)
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
            return {"ok": False, "error": str(exc)}
