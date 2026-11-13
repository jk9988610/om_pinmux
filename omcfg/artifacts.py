"""编译产物/编辑器状态/旧事务备份的排除规则：基线摘要与新工程复制共用。

这两处必须使用同一套排除规则，否则：
- 基线摘要会把 Keil 编译产物算进去，编译一次就与 META.json 失配；
- 新工程复制会漏掉某些产物。
"""

from __future__ import annotations

import fnmatch
from pathlib import PurePosixPath

# 不进入新工程的目录/文件：编译产物、编辑器/调试器状态、旧事务备份。
EXCLUDED_DIRS = (".git", ".vscode", ".cache", "out", "_build", "lib_build")
# SE71M.BAT 是 Keil 每次编译生成的批处理，内含生成机器的绝对路径。
EXCLUDED_FILE_NAMES = (
    "JLinkLog.txt",
    "JLinkSettings.ini",
    "compile_commands.json",
    "SE71M.BAT",
)
# 注意不排除 *.o：SDK 里 userdefined_key_20260724.o / rf_protocol_20260704.o
# 是 uvprojx 直接引用的预编译输入，不是本次编译的产物。
EXCLUDED_SUFFIXES = (
    ".dep",
    ".d",
    ".crf",
    ".axf",
    ".hex",
    ".bin",
    ".lst",
    ".map",
    ".lnp",
    ".htm",
    ".uvoptx",
    ".log",
)


def is_artifact(name: str) -> bool:
    """单个文件/目录名是否是产物或状态文件。"""
    return (
        name in EXCLUDED_DIRS
        or name in EXCLUDED_FILE_NAMES
        or name.startswith(".omcfg_bak_")
        or name.endswith(EXCLUDED_SUFFIXES)
        or fnmatch.fnmatchcase(name, "*.uvguix.*")
    )


def is_artifact_path(relative: str) -> bool:
    """相对路径（POSIX 风格）中任一段命中产物规则即为 True。"""
    return any(is_artifact(part) for part in PurePosixPath(relative).parts)
