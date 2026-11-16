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
KEIL_PROJECT = Path("projects/mouse_demo/keil5/SE71M.uvprojx")

USER_CODE_H = "user_config_h"
USER_CODE_C = "user_config_c"
USER_CODE_FEATURES = "board_features_h"
SLEEP_BLOCK = "sleep"


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


class UserCodeError(TargetError):
    """USER CODE 保护区缺失/重复/只出现一半。"""

    def __init__(self, path: Path, name: str, detail: str):
        self.path = path
        self.name = name
        super().__init__(
            f"{path} 的 USER CODE 保护区 '{name}' {detail}。\n"
            f"  生成器只改写 OMCFG 生成区，不会猜测插入位置。\n"
            f"  先运行: python -m omcfg init --config <config> --sdk <SDK>"
        )


def marker_begin(name: str) -> str:
    return f"/* OMCFG BEGIN {name} */"


def marker_end(name: str) -> str:
    return f"/* OMCFG END {name} */"


def user_code_begin(name: str) -> str:
    return f"/* USER CODE BEGIN {name} */"


def user_code_end(name: str) -> str:
    return f"/* USER CODE END {name} */"


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


def find_user_code(text: str, name: str, path: Path) -> tuple[int, int]:
    begin = user_code_begin(name)
    end = user_code_end(name)
    begin_count = text.count(begin)
    end_count = text.count(end)
    if begin_count == 0 and end_count == 0:
        raise UserCodeError(path, name, "不存在")
    if begin_count != 1 or end_count != 1:
        raise UserCodeError(path, name, f"标记不完整（BEGIN {begin_count} 次，END {end_count} 次）")
    start = text.index(begin)
    stop = text.index(end, start) + len(end)
    if text.find(begin, stop) != -1:
        raise UserCodeError(path, name, "出现多次")
    return start, stop


def check_user_code(text: str, name: str, path: Path) -> None:
    find_user_code(text, name, path)


def append_user_code(text: str, name: str, path: Path) -> str:
    """在文件末尾追加空 USER CODE 保护区；已存在则原样返回。"""
    begin = user_code_begin(name)
    end = user_code_end(name)
    if begin in text or end in text:
        check_user_code(text, name, path)
        return text
    prefix = text if text.endswith("\n") or not text else text + "\n"
    return prefix + begin + "\n" + end + "\n"


def wrap_function_block(text: str, name: str, signature: str, path: Path) -> str:
    """把 user_config.c 里已有的函数（连同紧邻的文档注释）包进 OMCFG 标记块。

    只插标记行、不改正文；函数不存在时在文件末尾补一个空块，交给 gen 填写。
    """
    if marker_begin(name) in text or marker_end(name) in text:
        find_block(text, name, path)
        return text
    lines = text.splitlines(keepends=True)
    decl = next((i for i, line in enumerate(lines) if signature in line), None)
    if decl is None:
        prefix = text if text.endswith("\n") or not text else text + "\n"
        return prefix + marker_begin(name) + "\n" + marker_end(name) + "\n"
    end = _brace_end(lines, decl, path)
    start = _doc_comment_start(lines, decl)
    return (
        "".join(lines[:start])
        + marker_begin(name)
        + "\n"
        + "".join(lines[start : end + 1])
        + marker_end(name)
        + "\n"
        + "".join(lines[end + 1 :])
    )


def _brace_end(lines: list[str], decl: int, path: Path) -> int:
    depth = 0
    opened = False
    for index in range(decl, len(lines)):
        for char in lines[index]:
            if char == "{":
                depth += 1
                opened = True
            elif char == "}":
                depth -= 1
                if opened and depth == 0:
                    return index
    raise TargetError(f"{path} 中函数声明后找不到配对的大括号，拒绝插入 '{SLEEP_BLOCK}' 标记")


def _doc_comment_start(lines: list[str], decl: int) -> int:
    index = decl - 1
    if index < 0 or lines[index].strip() != "*/":
        return decl
    while index >= 0 and not lines[index].lstrip().startswith("/*"):
        index -= 1
    return index if index >= 0 else decl


def resolve_sdk(sdk_root: Path | str) -> Path:
    root = Path(sdk_root).expanduser().resolve()
    if not root.is_dir():
        raise TargetError(
            f"SDK 目录不存在: {root}\n"
            f"  提示: --sdk 指向 SDK 根目录（其下应有 projects/mouse_demo/periph），"
            f"不是 keil5 子目录"
        )
    periph = root / PERIPH
    if not periph.is_dir():
        raise TargetError(
            f"不是预期的 SDK：缺少 {PERIPH.as_posix()}（{root}）\n"
            f"  提示: 确认这是 mouse_demo 工程的 SDK 根目录；改板请先复制一份 SDK 再操作"
        )
    if not (root / USER_CONFIG_H).is_file() or not (root / USER_CONFIG_C).is_file():
        raise TargetError(
            f"SDK 缺少 user_config.h / user_config.c（{periph}）\n"
            f"  提示: 该目录不是完整的 mouse_demo 工程，检查是否复制中断"
        )
    return root


DEFINE_STR_RE = re.compile(r'^\s*#define\s+(?P<name>iPROJECT_NAME|iCONSUMER_NAME)\s+"(?P<value>[^"]*)"', re.M)


def existing_project(root: Path | str) -> dict[str, str]:
    """读取 SDK 现有 user_config.h 中的项目名/客户名，用于配置与板匹配检查。"""
    path = Path(root) / USER_CONFIG_H
    if not path.is_file():
        return {}
    text = read_source(path).text
    return {match.group("name"): match.group("value") for match in DEFINE_STR_RE.finditer(text)}


def project_mismatch(root: Path | str, name: object, customer: object) -> str | None:
    """配置 project 段与 SDK 现有宏不一致时返回说明，一致或无法判定时返回 None。"""
    current = existing_project(root)
    problems: list[str] = []
    expected_name = str(name or "").strip()
    expected_customer = str(customer or "").strip()
    actual_name = current.get("iPROJECT_NAME", "")
    actual_customer = current.get("iCONSUMER_NAME", "")
    if expected_name and actual_name and expected_name != actual_name:
        problems.append(f'project.name={expected_name}，SDK 现有 iPROJECT_NAME="{actual_name}"')
    if expected_customer and actual_customer and expected_customer != actual_customer:
        problems.append(f'project.customer={expected_customer}，SDK 现有 iCONSUMER_NAME="{actual_customer}"')
    return "；".join(problems) or None


def target_path(sdk_root: Path | str, relative: Path) -> Path:
    return Path(sdk_root) / relative
