r"""测试夹具：CH04 基线是功能超集（LEDC/双模式/pair 保护），当前内置基线为 KC536。

部分测试验证的是 CH04 专属能力，KC536 基线不具备这些文件/结构。这些测试通过
环境变量 OMCFG_CH04_BASELINE 指向一份 CH04 基线（换基线前的备份）取证；
未配置时跳过并说明原因，而不是删除测试或放宽断言。

配置方式（PowerShell）：
    $env:OMCFG_CH04_BASELINE = "E:\tools\om_pinmux_baseline_backup_ch04_20261118_100842\sdk"
    python -m pytest
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ENV_NAME = "OMCFG_CH04_BASELINE"


def ch04_sdk_path() -> Path | None:
    value = os.environ.get(ENV_NAME, "").strip()
    if not value:
        return None
    path = Path(value)
    return path if path.is_dir() else None


def pytest_runtest_logstart(nodeid: str, location: tuple[str, int, str]) -> None:
    """里程碑运行器专用：用例开始时打印 RUN 行，供超时定位卡点。

    仅当 OMCFG_TEST_PROGRESS=1 时生效（由 milestone_run.py 设置），
    普通 pytest 运行完全不受影响。
    """
    if os.environ.get("OMCFG_TEST_PROGRESS") == "1":
        print(f">>>RUN {nodeid}", flush=True)


@pytest.fixture(scope="session")
def ch04_baseline() -> Path:
    """CH04 SDK 根目录（periph 的父级工程的 SDK 根）。未配置则跳过。"""
    path = ch04_sdk_path()
    if path is None:
        pytest.skip(
            f"需要 CH04 基线：设置环境变量 {ENV_NAME} 指向 CH04 SDK 根目录"
            "（换 KC536 基线前的备份 sdk/）；KC536 基线不含 LEDC/双模式/pair 保护"
        )
    return path
