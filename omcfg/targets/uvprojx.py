"""Keil .uvprojx 的外科式更新：只动 periph 组文件条目与 include 路径。

不用 ElementTree 重写整个 XML，避免把用户的编译选项/格式一并改掉；
所有改动都在 `<Groups>` 内按现有缩进插入/删除 `<File>` 块。
"""

from __future__ import annotations

import re
from pathlib import Path

from .. import model
from . import sdk

GROUPS_OPEN = "<Groups>"
GROUPS_CLOSE = "</Groups>"
GROUP_RE = re.compile(r"[ \t]*<Group>\n.*?[ \t]*</Group>\n", re.S)
GROUP_NAME_RE = re.compile(r"<GroupName>(.*?)</GroupName>")
FILES_RE = re.compile(r"(?P<open>[ \t]*<Files>\n)(?P<inner>.*?)(?P<close>[ \t]*</Files>)", re.S)
FILE_RE = re.compile(r"[ \t]*<File>\n.*?[ \t]*</File>\n", re.S)
FILE_NAME_RE = re.compile(r"<FileName>(.*?)</FileName>")
INCLUDE_RE = re.compile(r"(<IncludePath>)([^<]*)(</IncludePath>)")

# periph 组内必须存在的条目；路径沿用 SDK 现有写法。
PERIPH_REQUIRED = (
    ("user_config.c", "1"),
    ("board_features.h", "5"),
    ("periph_gpio_sleep_set.pinmux.c", "1"),
)
LEDC_SOURCES = ("ledc.c", "ledc_mode.c")


def project_path(config: dict, sdk_root: Path | str) -> Path | None:
    """按 codegen.keil_project 定位工程文件；不存在时返回 None（跳过工程更新）。"""
    codegen = config.get("codegen") or {}
    relative = str(codegen.get("keil_project") or "").strip()
    if not relative:
        relative = sdk.KEIL_PROJECT.as_posix()
    path = Path(sdk_root) / relative
    return path if path.is_file() else None


def update_project(text: str, config: dict, path: Path) -> str:
    text = _ensure_include_path(text, path)
    return _rewrite_periph_group(text, config, path)


def _ensure_include_path(text: str, path: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        content = match.group(2)
        if not content.strip():
            return match.group(0)
        tokens = {item.replace("\\", "/") for item in content.split(";") if item}
        if "../periph" in tokens:
            return match.group(0)
        head = content.rstrip(";")
        return f"{match.group(1)}{head};../periph{match.group(3)}"

    return INCLUDE_RE.sub(replace, text)


def _rewrite_periph_group(text: str, config: dict, path: Path) -> str:
    if text.count(GROUPS_OPEN) != 1:
        raise sdk.TargetError(
            f"{path} 中 <Groups> 出现 {text.count(GROUPS_OPEN)} 次，无法定位源码分组"
        )
    groups_start = text.index(GROUPS_OPEN)
    inner_start = groups_start + len(GROUPS_OPEN)
    groups_end = text.find(GROUPS_CLOSE, groups_start)
    if groups_end == -1:
        raise sdk.TargetError(f"{path} 缺少 </Groups>，工程文件结构不完整")
    groups_inner = text[inner_start:groups_end]

    periph = [
        match
        for match in GROUP_RE.finditer(groups_inner)
        if _group_name(match.group(0)) == "periph"
    ]
    if len(periph) != 1:
        raise sdk.TargetError(
            f"{path} 中名为 periph 的 <Group> 有 {len(periph)} 个，无法安全更新"
        )
    match = periph[0]
    new_group = _rewrite_group(match.group(0), config, path)
    new_inner = groups_inner[: match.start()] + new_group + groups_inner[match.end() :]
    return text[:inner_start] + new_inner + text[groups_end:]


def _group_name(group_text: str) -> str:
    match = GROUP_NAME_RE.search(group_text)
    return match.group(1).strip() if match else ""


def _rewrite_group(group_text: str, config: dict, path: Path) -> str:
    files = FILES_RE.search(group_text)
    if not files:
        raise sdk.TargetError(f"{path} 的 periph <Group> 缺少 <Files> 段，无法登记源文件")
    blocks = FILE_RE.findall(files.group("inner"))
    file_indent, child_indent = _indents(blocks)

    removals = set() if model.board(config).get("logo") == "ledc" else set(LEDC_SOURCES)
    kept: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        name_match = FILE_NAME_RE.search(block)
        if not name_match:
            kept.append(block)
            continue
        name = name_match.group(1).strip()
        if name in removals:
            continue
        kept.append(block)
        seen.add(name)

    for name, file_type in PERIPH_REQUIRED:
        if name in seen:
            continue
        kept.append(_file_block(name, file_type, file_indent, child_indent))

    new_inner = "".join(kept)
    return group_text[: files.start("inner")] + new_inner + group_text[files.end("inner") :]


def _indents(blocks: list[str]) -> tuple[str, str]:
    file_indent = "            "
    child_indent = "              "
    if not blocks:
        return file_indent, child_indent
    head = re.match(r"([ \t]*)<File>", blocks[0])
    if head:
        file_indent = head.group(1)
    child = re.search(r"\n([ \t]*)<FileName>", blocks[0])
    if child:
        child_indent = child.group(1)
    return file_indent, child_indent


def _file_block(name: str, file_type: str, file_indent: str, child_indent: str) -> str:
    file_path = f"..\\periph\\{name}"
    return (
        f"{file_indent}<File>\n"
        f"{child_indent}<FileName>{name}</FileName>\n"
        f"{child_indent}<FileType>{file_type}</FileType>\n"
        f"{child_indent}<FilePath>{file_path}</FilePath>\n"
        f"{file_indent}</File>\n"
    )
