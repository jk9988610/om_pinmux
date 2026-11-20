"""GUI 回归：浏览选目录后按钮应立即高亮，且 Windows 路径单/双反斜杠等价。

对应的前端检查脚本 scripts/check_web_browseout.js 用 Node vm 加载真实 app.js，
以极简 DOM stub 驱动 browseOut()，断言底部按钮状态与路径归一结果。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check_web_browseout.js"


def test_browse_out_refreshes_next_button_and_normalizes_path() -> None:
    node = shutil.which("node")
    if not node:
        import pytest

        pytest.skip("node 不可用，跳过前端回归检查")

    proc = subprocess.run(
        [node, str(CHECK)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout, proc.stdout + proc.stderr
