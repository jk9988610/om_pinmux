"""OM6239 配置工具桌面入口（pywebview）。"""

from __future__ import annotations

import sys
from pathlib import Path

import webview

from omcfg.api import Api


def main() -> None:
    root = Path(__file__).resolve().parent
    api = Api()
    window = webview.create_window(
        "OM6239 配置",
        str(root / "web" / "index.html"),
        js_api=api,
        width=1180,
        height=780,
        maximized="--maximize" in sys.argv,
    )
    webview.start()
    del window


if __name__ == "__main__":
    main()
