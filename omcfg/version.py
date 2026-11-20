"""固件版本号：真相源 project.omcfg 的 project.id.version，生成写盘时 +1 并同步两处。

两处同步：
  1. user_config.h 的 iREAL_VERSION_ID —— 由 generator/templates 按 config 生成，无需本模块写。
  2. startup_om6239.S 的 `.long 0x040002NN` —— 静态文件，不由生成器产出，需本模块精确改写。

映射关系（来自 S205/KC536 原件核对）：startup 低字节 = 版本号，即
    version=1 → 0x04000201；version=5 → 0x04000205
S205 原件 version=1 但 startup 仍是 0x04000205（未同步），工具在生成时把它们对齐。

触发点由调用方决定（GUI 的 apply / blank_apply 写盘前）。所有写盘走 FileTransaction，
与生成文件同一事务，可整体回滚。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import model
from .targets import sdk
from .transaction import FileTransaction

STARTUP_REL = "hal/device/om6239/GCC/startup_om6239.S"
# 精确匹配向量表里的固件版本字；只替换低字节两位，保留对齐空格与注释。
_STARTUP_RE = re.compile(r"(?P<head>\.long\s+0x040002)(?P<ver>[0-9A-Fa-f]{2})(?P<tail>\b)")

MAX_VERSION = 0xFF  # startup 低字节容量，超过则无法表达


def bump(
    root: Path | str, config: dict, transaction: FileTransaction
) -> tuple[int, int]:
    """版本号 +1，把 .omcfg 与 startup 的改动写入事务。

    返回 (new_version, writes)。writes = 实际写盘文件数（0 表示启动文件缺该模式或无需改）。
    调用方须用**更新后的 config** 生成 user_config.h，才能让 iREAL_VERSION_ID 同步。
    """
    root_path = Path(root)
    raw = model.project_id(config).get("version", "")
    try:
        current = int(str(raw), 0)
    except ValueError:
        current = 0
    new_version = current + 1
    if not 1 <= new_version <= MAX_VERSION:
        raise ValueError(f"固件版本号超出 1..{MAX_VERSION}（startup 低字节容量）: {new_version}")

    # 1) 真相源：.omcfg project.id.version（文本改写，保留注释与排版）
    cfg_path = model.default_config_path(root_path)
    cfg_source = sdk.read_source(cfg_path)
    cfg_text = model.set_project_id_version_text(cfg_source.text, new_version)
    if cfg_text != cfg_source.text:
        transaction.write_bytes(
            cfg_path,
            sdk.SourceFile(cfg_path, cfg_text, cfg_source.encoding, cfg_source.newline, cfg_source.bom).render(),
            f"固件版本号 {current} → {new_version}",
        )

    # 2) startup 向量表版本字（静态文件，不进 generator）
    writes = 0
    startup_path = root_path / STARTUP_REL
    if startup_path.is_file():
        source = sdk.read_source(startup_path)
        replaced, n = _STARTUP_RE.subn(
            lambda m: f"{m.group('head')}{new_version:02X}{m.group('tail')}", source.text
        )
        if n and replaced != source.text:
            transaction.write_bytes(
                startup_path,
                sdk.SourceFile(
                    startup_path, replaced, source.encoding, source.newline, source.bom
                ).render(),
                f"启动版本号 {current} → {new_version}",
            )
            writes = n
    return new_version, writes
