"""SDK 目录定位、源文件编码/换行保持、标记块精确替换。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MARKER_RE = re.compile(r"^\s*/\* OMCFG (?:BEGIN|END) [A-Za-z0-9_]+ \*/\s*$")
LEGACY_MARKER = "OM_PINMUX_GENERATED"

USER_CONFIG_H = Path("projects/mouse_demo/periph/user_config.h")
USER_CONFIG_C = Path("projects/mouse_demo/periph/user_config.c")
BOARD_FEATURES_H = Path("projects/mouse_demo/periph/board_features.h")
SLEEP_TEMPLATE = Path("projects/mouse_demo/periph/periph_gpio_sleep_set.pinmux.c")
PERIPH = Path("projects/mouse_demo/periph")


class TargetError(RuntimeError):
    """目标目录或文件不满足写回前提。"""


class MissingBlockError(TargetError):
    def __init__(self, path: Path, block: str, detail: str = ""):
        self.path = path
        self.block = block
        super().__init__(
            f"{path} 缺少 OMCFG 标记块 '{block}'。{detail}\n"
            f"  先运行: python -m omcfg init --config <config> --sdk <SDK>"
        )


class DuplicateBlockError(TargetError):
    def __init__(self, path: Path, block: str):
        self.path = path
        self.block = block
        super().__init__(f"{path} 中标记块 '{block}' 出现多次，拒绝猜测替换位置")


def marker_begin(name: str) -> str:
    return f"/* OMCFG BEGIN {name} */"


def marker_end(name: str) -> str:
    return f"/* OMCFG END {name} */"


@dataclass
class SourceFile:
    path: Path
    text: str
    encoding: str
    newline: str
    bom: bool

    def render(self) -> bytes:
        text = self.text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\n", self.newline)
        data = text.encode(self.encoding)
        if self.bom:
            data = b"\xef\xbb\xbf" + data
        return data


def read_source(path: Path | str) -> SourceFile:
    target = Path(path)
    raw = target.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    body = raw[3:] if bom else raw
    last_error: Exception | None = None
    for encoding in ("utf-8", "gbk"):
        try:
            text = body.decode(encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise TargetError(f"{target} 既不是 UTF-8 也不是 GBK：{last_error}")
    newline = "\r\n" if b"\r\n" in raw else "\n"
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return SourceFile(target, normalized, encoding, newline, bom)


def write_source(source: SourceFile, text: str) -> None:
    source.text = text
    data = source.render()
    source.path.parent.mkdir(parents=True, exist_ok=True)
    source.path.write_bytes(data)


def ensure_encodable(text: str, encoding: str) -> None:
    try:
        text.encode(encoding)
    except UnicodeEncodeError as exc:
        raise TargetError(f"生成内容无法用 {encoding} 编码：{exc}") from exc


def has_any_marker(text: str) -> bool:
    return bool(MARKER_RE.search(text))


def strip_marker_lines(text: str) -> str:
    lines = [line for line in text.split("\n") if not MARKER_RE.match(line)]
    return "\n".join(lines)


def legacy_markers(text: str) -> bool:
    return LEGACY_MARKER in text


def find_block(text: str, name: str, path: Path) -> tuple[int, int]:
    begin = marker_begin(name)
    end = marker_end(name)
    begin_count = text.count(begin)
    end_count = text.count(end)
    if begin_count == 0 or end_count == 0:
        raise MissingBlockError(path, name)
    if begin_count > 1 or end_count > 1:
        raise DuplicateBlockError(path, name)
    start = text.index(begin)
    stop = text.index(end, start) + len(end)
    if text.find(begin, stop) != -1:
        raise DuplicateBlockError(path, name)
    return start, stop


def replace_block(text: str, name: str, payload: str, path: Path) -> str:
    start, stop = find_block(text, name, path)
    core = payload.strip("\n")
    if marker_begin(name) in core or marker_end(name) in core:
        raise TargetError(f"生成内容里混入了标记文本 '{name}'，拒绝写入")
    return text[:start] + marker_begin(name) + "\n" + core + "\n" + marker_end(name) + text[stop:]


def resolve_sdk(sdk_root: Path | str) -> Path:
    root = Path(sdk_root).expanduser().resolve()
    if not root.is_dir():
        raise TargetError(f"SDK 目录不存在: {root}")
    periph = root / PERIPH
    if not periph.is_dir():
        raise TargetError(f"不是预期的 SDK：缺少 {PERIPH.as_posix()}（{root}）")
    if not (root / USER_CONFIG_H).is_file() or not (root / USER_CONFIG_C).is_file():
        raise TargetError(f"SDK 缺少 user_config.h / user_config.c（{periph}）")
    return root


def target_path(sdk_root: Path | str, relative: Path) -> Path:
    return Path(sdk_root) / relative
