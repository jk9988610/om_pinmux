"""把配置组装成 4 个产物的目标文本，不负责落盘。"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from .. import model
from ..targets import sdk
from . import templates

BLOCKS_H = ("pins", "project_ids", "project_version", "project_names")
BLOCK_C = "gpio_table"
BLOCK_FEATURES = "features"
BLOCK_SLEEP = "sleep"


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

    for relative, block, payload in (
        (sdk.BOARD_FEATURES_H, BLOCK_FEATURES, features),
        (sdk.SLEEP_TEMPLATE, BLOCK_SLEEP, sleep),
    ):
        path = root / relative
        if path.is_file():
            src = sdk.read_source(path)
            if sdk.legacy_markers(src.text):
                raise sdk.TargetError(f"{src.path} 仍含旧 OM_PINMUX_GENERATED 标记，请先人工迁移")
            after = sdk.replace_block(src.text, block, payload, path)
            outputs.append(
                GeneratedFile(
                    path, src.text, after, src.encoding, src.newline, src.bom, True, [block]
                )
            )
        else:
            after = _wrap(block, payload) + "\n"
            outputs.append(
                GeneratedFile(
                    path, "", after, header.encoding, header.newline, header.bom, False, [block]
                )
            )

    return outputs
