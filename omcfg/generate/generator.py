"""把配置组装成各目标文本（4 个生成文件 + Keil 工程），不负责落盘。"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from .. import model
from ..targets import sdk, uvprojx
from . import templates

BLOCKS_H = ("pins", "project_ids", "project_version", "project_names")
BLOCK_C = "gpio_table"
BLOCK_FEATURES = "features"
BLOCK_SLEEP = sdk.SLEEP_BLOCK


@dataclass
class GeneratedFile:
    path: Path
    before: str
    after: str
    encoding: str
    newline: str
    bom: bool
    exists: bool
    blocks: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.before != self.after

    def render(self) -> bytes:
        text = self.after.replace("\r\n", "\n").replace("\r", "\n").replace("\n", self.newline)
        data = text.encode(self.encoding)
        if self.bom:
            data = b"\xef\xbb\xbf" + data
        return data

    def diff(self, context: int = 3) -> str:
        return "\n".join(
            difflib.unified_diff(
                self.before.splitlines(),
                self.after.splitlines(),
                fromfile=str(self.path),
                tofile=str(self.path),
                lineterm="",
                n=context,
            )
        )


def _new_source(path: Path, newline: str, encoding: str = "utf-8") -> sdk.SourceFile:
    return sdk.SourceFile(path=path, text="", encoding=encoding, newline=newline, bom=False)


def _wrap(name: str, payload: str) -> str:
    return sdk.marker_begin(name) + "\n" + payload.strip("\n") + "\n" + sdk.marker_end(name)


def _empty_user_code(name: str) -> str:
    return sdk.user_code_begin(name) + "\n" + sdk.user_code_end(name) + "\n"


def sdk_warning(config: dict, sdk_root: Path | str) -> tuple[str, str] | None:
    """配置项目名/客户与 SDK 现有宏不一致时返回 (message, hint)。"""
    project = model.project(config)
    message = sdk.project_mismatch(sdk_root, project.get("name"), project.get("customer"))
    if not message:
        return None
    return (
        f"配置与 SDK 现有工程不一致：{message}",
        "若是在副本上换板可继续；否则确认 --sdk/--config 配对（CH04↔CH04、KC536↔KC536）",
    )


def build_outputs(config: dict, sdk_root: Path | str) -> list[GeneratedFile]:
    root = sdk.resolve_sdk(sdk_root)
    pins = model.resolved_pins(config)
    payloads = {
        "pins": templates.render_pins(config, pins),
        "project_ids": templates.render_project_ids(config),
        "project_version": templates.render_project_version(config),
        "project_names": templates.render_project_names(config),
    }
    table = templates.render_gpio_table(config, pins)
    features = templates.render_features(config, pins)
    sleep = templates.render_sleep(config, pins)

    outputs: list[GeneratedFile] = []

    header = sdk.read_source(root / sdk.USER_CONFIG_H)
    if sdk.legacy_markers(header.text):
        raise sdk.TargetError(f"{header.path} 仍含旧 OM_PINMUX_GENERATED 标记，请先人工迁移")
    text = header.text
    for name in BLOCKS_H:
        text = sdk.replace_block(text, name, payloads[name], header.path)
    sdk.check_user_code(header.text, sdk.USER_CODE_H, header.path)
    sdk.ensure_encodable(text, header.encoding)
    outputs.append(
        GeneratedFile(
            header.path,
            header.text,
            text,
            header.encoding,
            header.newline,
            header.bom,
            True,
            list(BLOCKS_H),
        )
    )

    source_c = sdk.read_source(root / sdk.USER_CONFIG_C)
    if sdk.legacy_markers(source_c.text):
        raise sdk.TargetError(f"{source_c.path} 仍含旧 OM_PINMUX_GENERATED 标记，请先人工迁移")
    text_c = sdk.replace_block(source_c.text, BLOCK_C, table, source_c.path)
    text_c = sdk.replace_block(text_c, BLOCK_SLEEP, sleep, source_c.path)
    sdk.check_user_code(source_c.text, sdk.USER_CODE_C, source_c.path)
    sdk.ensure_encodable(text_c, source_c.encoding)
    outputs.append(
        GeneratedFile(
            source_c.path,
            source_c.text,
            text_c,
            source_c.encoding,
            source_c.newline,
            source_c.bom,
            True,
            [BLOCK_C],
        )
    )

    path = root / sdk.BOARD_FEATURES_H
    if path.is_file():
        src = sdk.read_source(path)
        if sdk.legacy_markers(src.text):
            raise sdk.TargetError(f"{src.path} 仍含旧 OM_PINMUX_GENERATED 标记，请先人工迁移")
        after = sdk.replace_block(src.text, BLOCK_FEATURES, features, path)
        sdk.check_user_code(src.text, sdk.USER_CODE_FEATURES, path)
        outputs.append(GeneratedFile(path, src.text, after, src.encoding, src.newline, src.bom, True, [BLOCK_FEATURES]))
    else:
        after = _wrap(BLOCK_FEATURES, features) + "\n\n" + _empty_user_code(sdk.USER_CODE_FEATURES)
        outputs.append(
            GeneratedFile(
                path,
                "",
                after,
                header.encoding,
                header.newline,
                header.bom,
                False,
                [BLOCK_FEATURES],
            )
        )

    retired = root / sdk.SLEEP_TEMPLATE
    if retired.is_file():
        src = sdk.read_source(retired)
        pointer = (
            "/* 本文件已退场：periph_gpio_sleep_set() 由 omcfg 生成到 user_config.c 的"
            " OMCFG sleep 块，不再参与编译。 */\n"
        )
        outputs.append(GeneratedFile(retired, src.text, pointer, src.encoding, src.newline, src.bom, True, []))

    project = uvprojx.project_path(config, root)
    if project is not None:
        project_source = sdk.read_source(project)
        after_project = uvprojx.update_project(project_source.text, config, project)
        outputs.append(
            GeneratedFile(
                project,
                project_source.text,
                after_project,
                project_source.encoding,
                project_source.newline,
                project_source.bom,
                True,
                ["keil_project"],
            )
        )

    return outputs
