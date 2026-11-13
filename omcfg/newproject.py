"""新工程一键生成：复制骨架（剔除产物）、改写工程标识、清理内部备份。"""

from __future__ import annotations


import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import artifacts, model
from .targets import sdk


# 产物排除规则见 omcfg/artifacts.py（与 baseline 摘要共用）


NOT_COPIED_SUMMARY = (
    "out/, _build/, lib_build/, .git/, .vscode/, .cache/, .omcfg_bak_*/，"
    "*.dep, *.d, *.crf, *.axf, *.hex, *.bin, *.lst, *.map, *.lnp, *.htm, "
    "*.uvoptx, *.uvguix.*, *.log, JLinkLog.txt, JLinkSettings.ini, "
    "compile_commands.json, SE71M.BAT"
)

MOUSE_NAME_PATH = Path("projects/mouse_demo/main/mouse_hw.c")
ADV_NAME_PATH = Path("projects/mouse_demo/main/ex2_app_mouse.c")

MOUSE_NAME_ASSIGN_RE = re.compile(
    r'(?P<pre>mouse_name\s*\[[^\]]*\]\s*=\s*)"(?P<value>[^"]*)"'
)
MOUSE_NAME_MEMCPY_RE = re.compile(
    r'(?P<pre>memcpy\s*\(\s*mouse_name\s*,\s*)"(?P<first>[^"]*)"'
    r'(?P<mid>\s*,\s*sizeof\s*\(\s*)"(?P<second>[^"]*)"(?P<post>\s*\)\s*\))'
)

IDENTITY_MACROS = (
    "iPROJECT_NAME",
    "iCONSUMER_NAME",
    "iPROJECT_ID_H",
    "iPROJECT_ID_L",
    "iREAL_VERSION_ID",
)


@dataclass
class Rewrite:
    path: str
    symbol: str
    before: str
    after: str

    def render(self) -> str:
        return f"{self.path}  {self.symbol}  {self.before!r} -> {self.after!r}"


def _excluded(name: str) -> bool:
    return artifacts.is_artifact(name)



def _ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if _excluded(name)}


def copy_skeleton(source: Path | str, target: Path | str) -> int:
    """把源 SDK 复制到目标路径（目标必须不存在），返回复制文件数。"""
    dst = Path(target)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dst, ignore=_ignore, copy_function=shutil.copy2)
    return sum(1 for path in dst.rglob("*") if path.is_file())


def _rewrite(path: Path, transform, records: list[Rewrite]) -> None:
    if not path.is_file():
        return
    source = sdk.read_source(path)
    after, changes = transform(source.text)
    if after == source.text:
        return
    sdk.ensure_encodable(after, source.encoding)
    path.write_bytes(
        sdk.SourceFile(path, after, source.encoding, source.newline, source.bom).render()
    )
    records.extend(changes)


def _rewrite_mouse_name(text: str, name: str, display: str) -> tuple[str, list[Rewrite]]:
    records: list[Rewrite] = []

    def replace(match: re.Match[str]) -> str:
        before = match.group("value")
        if before != name:
            records.append(Rewrite(display, "mouse_name", before, name))
        return f'{match.group("pre")}"{name}"'

    after, count = MOUSE_NAME_ASSIGN_RE.subn(replace, text, count=1)
    return (after if count else text), records


def _rewrite_adv_names(text: str, names: list[str], display: str) -> tuple[str, list[Rewrite]]:
    records: list[Rewrite] = []
    index = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal index
        index += 1
        value = names[min(index - 1, len(names) - 1)]
        before = match.group("first")
        if before != value:
            records.append(Rewrite(display, f"mouse_name memcpy#{index}", before, value))
        return f'{match.group("pre")}"{value}"{match.group("mid")}"{value}"{match.group("post")}'

    return MOUSE_NAME_MEMCPY_RE.sub(replace, text), records


def rewrite_identity(root: Path | str, config: dict) -> list[Rewrite]:
    """按 project.ble_names 改写不属于生成区的 BLE 广播名。"""
    names = model.ble_names(config)
    if not names:
        return []
    root_path = Path(root)
    records: list[Rewrite] = []
    _rewrite(
        root_path / MOUSE_NAME_PATH,
        lambda text: _rewrite_mouse_name(text, names[0], MOUSE_NAME_PATH.as_posix()),
        records,
    )
    _rewrite(
        root_path / ADV_NAME_PATH,
        lambda text: _rewrite_adv_names(text, names, ADV_NAME_PATH.as_posix()),
        records,
    )
    return records


def _macros(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    text = sdk.read_source(path).text
    found: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#define "):
            continue
        parts = stripped.split(None, 2)
        if len(parts) < 3 or parts[1] not in IDENTITY_MACROS:
            continue
        found[parts[1]] = parts[2].split("/*", 1)[0].strip()
    return found


def identity_macro_records(source: Path | str, target: Path | str) -> list[Rewrite]:
    """对比源工程与新工程 user_config.h 的标识宏，给出改写证据。"""
    before = _macros(Path(source) / sdk.USER_CONFIG_H)
    after = _macros(Path(target) / sdk.USER_CONFIG_H)
    path = sdk.USER_CONFIG_H.as_posix()
    return [
        Rewrite(path, name, before[name], after[name])
        for name in IDENTITY_MACROS
        if name in before and name in after and before[name] != after[name]
    ]


def remove_backups(root: Path | str) -> list[Path]:
    """删除 new 命令自身产生的事务备份；源工程的旧备份本来就不复制。"""
    removed: list[Path] = []
    for path in sorted(Path(root).glob(".omcfg_bak_*")):
        if path.is_dir():
            shutil.rmtree(path)
            removed.append(path)
    return removed
