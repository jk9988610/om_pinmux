#!/usr/bin/env python3
"""检测来源真实 SDK 是否相对基线快照漂移。

背景：baseline/sdk 是 2026-09-09 KC536 SDK 的冻结快照，且为 S205 传感器、
灯效策略、版本号做过**有意适配**，不会自动跟随外部 SDK。本脚本用与基线
摘要相同的产物过滤口径（排除 Keil 产物 / .cache 索引 / 事务备份），比对
来源 SDK 的源码摘要与文件数，变化就明确告警——把「基线静默落后」变成
「主动发现」。

用法：
    python scripts/check_sdk_drift.py
    OMCFG_REAL_SDK=D:\\other\\sdk python scripts/check_sdk_drift.py   # 指定来源

退出码：0=未漂移；1=已漂移；2=未记录快照/无法检测。
不依赖 GUI / node / Keil。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from omcfg import baseline  # noqa: E402


def main() -> int:
    data = baseline.meta()
    source = (
        Path(os.environ["OMCFG_REAL_SDK"])
        if os.environ.get("OMCFG_REAL_SDK")
        else Path(data.get("source_sdk") or "")
    )
    print("来源 SDK 漂移检测")
    print(f"  路径      : {source}")
    print(f"  快照摘要  : {data.get('source_tree_sha256') or '(未记录)'}")
    print(f"  快照文件数: {data.get('source_file_count') if data.get('source_file_count') is not None else '(未记录)'}")

    if not data.get("source_tree_sha256"):
        print("\n⚠ META.json 未记录 source_tree_sha256，无法检测漂移")
        return 2

    problems = baseline.source_sdk_problems()
    if not problems:
        print("\n✓ 来源 SDK 与基线快照一致（未漂移）")
        return 0

    print("\n✗ 来源 SDK 已变化，基线可能落后，请评估是否更新 baseline/sdk：")
    for item in problems:
        print(f"  - {item}")
    print("\n更新基线后请重算 META：tree_sha256 / size_bytes / source_tree_sha256 / source_file_count")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
