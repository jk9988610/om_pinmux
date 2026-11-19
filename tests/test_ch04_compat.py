"""CH04 旧工程兼容性：build_required 必须按源码实际引用判定。"""

from __future__ import annotations

import copy
from pathlib import Path

from omcfg import blank, model, rules

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_KEYS = ("KEY_B_PIN", "KEY_P_PIN", "KEY_DPI_PIN")


def test_ch04_unused_key_modes_are_not_required(ch04_baseline: Path) -> None:
    """CH04 的 key_io.c 不编译 R3/R4/R7，健康卡不应误报缺脚。"""
    config = model.load_config(ROOT / "configs" / "CH04.omcfg")
    active = rules.active_key_mode_roles(ch04_baseline, config)
    assert active is not None
    for role in REQUIRED_KEYS:
        assert role not in active, f"{role} 未在 CH04 源码使用，却被判为硬依赖"
    missing = blank.missing_roles(config, ch04_baseline)
    for role in REQUIRED_KEYS:
        assert role not in missing, f"CH04 健康卡误报缺脚: {role}"


def test_kc536_key_modes_are_still_required() -> None:
    """KC536 的 key_io.c 确实使用 R3/R4/R7，不能因为上面的修复被放宽。"""
    sdk = ROOT / "baseline" / "sdk"
    config = model.load_config(ROOT / "configs" / "KC536.omcfg")
    active = rules.active_key_mode_roles(sdk, config)
    assert active is not None
    for role in REQUIRED_KEYS:
        assert role in active, f"KC536 源码使用 {role}，必须保留硬依赖"

    empty = copy.deepcopy(config)
    empty["pins"] = {}
    missing = blank.missing_roles(empty, sdk)
    for role in REQUIRED_KEYS:
        assert role in missing, f"KC536 空白草稿应要求 {role}"
