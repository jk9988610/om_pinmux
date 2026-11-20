"""指示灯策略 + 工程身份映射的针对性回归。

覆盖本轮新增但原测试集零命中的三组能力：
  1. board.led_indicator 枚举写入（full/hint_only + 非法值拒绝）
  2. 模板输出 BOARD_LED_INDICATOR_ONLY 宏（含曾出错的"宏名与 1 之间空格"）
  3. blank_set_identity 改 ble_names 后同步 mouse_hw.c / ex2_app_mouse.c

不用真实 5 MB 基线做全量生成（那是 generate_parity 的职责），只测数据流闭环。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from omcfg import model
from omcfg.api import Api
from omcfg.generate import templates


@pytest.fixture
def draft(tmp_path):
    """真实骨架建一份空白草稿（含 mouse_hw.c / ex2_app_mouse.c 供身份改写）。"""
    sdk = tmp_path / "Draft"
    result = Api().blank_new("Draft", str(sdk), customer="BYC")
    assert result["ok"], result
    return sdk


def _load(sdk: Path):
    return model.load_config(model.default_config_path(sdk))


# --- 1. 板型枚举写入 -------------------------------------------------------

def test_board_enums_expose_new_options():
    caps = Api().blank_options()
    assert set(caps["board_enums"]["led_indicator"]) == {"full", "hint_only"}
    assert set(caps["board_enums"]["mode_24g_led"]) == {"B", "G", "R"}
    assert caps["board_defaults"]["led_indicator"] == "full"


def test_set_board_led_indicator_roundtrip(draft):
    api = Api()
    assert model.led_indicator(_load(draft)) == "full"  # 默认保 KC536
    changed = api.blank_set_board(str(draft), {"led_indicator": "hint_only"})
    assert changed["ok"], changed
    assert model.led_indicator(_load(draft)) == "hint_only"
    # 大小写归一 + 非法值拒绝
    assert api.blank_set_board(str(draft), {"led_indicator": "FULL"})["ok"]
    assert model.led_indicator(_load(draft)) == "full"
    bad = api.blank_set_board(str(draft), {"led_indicator": "blink"})
    assert bad["ok"] is False and "hint_only" in (bad.get("error") or "")


def test_led_indicator_falls_back_on_garbage():
    config = {"board": {"led_indicator": "nonsense"}}
    assert model.led_indicator(config) == "full"


# --- 2. 模板宏输出（曾出过 #define BOARD_LED_INDICATOR_ONLY1 缺空格） -------

def test_render_pins_hint_only_macro_has_space(draft):
    api = Api()
    pins = model.pin_entries(_load(draft))
    full_text = templates.render_pins(_load(draft), pins)
    assert "BOARD_LED_INDICATOR_ONLY" not in full_text, "full 不应输出守卫宏（KC536 字节一致）"

    api.blank_set_board(str(draft), {"led_indicator": "hint_only"})
    hint_text = templates.render_pins(_load(draft), pins)
    # pad 到 26 列 → 实际是两个空格；只要 >=1 个空格即可（曾出错的是零空格）
    assert re.search(r"#define BOARD_LED_INDICATOR_ONLY\s+1\b", hint_text), hint_text[-400:]
    assert "BOARD_LED_INDICATOR_ONLY1" not in hint_text, "宏名与 1 之间必须有空格"


# --- 3. 身份改写闭环 -------------------------------------------------------

def test_blank_new_ble_name_becomes_truth_source(tmp_path):
    sdk = tmp_path / "Named"
    result = Api().blank_new("Named", str(sdk), customer="APP", ble_name="S205-BLE")
    assert result["ok"], result
    assert result["ble_names"] == ["S205-BLE"]
    status = Api().blank_status(str(sdk))
    assert status["identity"] == {"customer": "APP", "ble_names": ["S205-BLE"]}


def test_set_identity_syncs_source(draft):
    api = Api()
    mhw = draft / "projects/mouse_demo/main/mouse_hw.c"
    adv = draft / "projects/mouse_demo/main/ex2_app_mouse.c"
    assert "BT5.1Mouse" in mhw.read_text(encoding="utf-8"), "夹具前提：基线原蓝牙名"

    result = api.blank_set_identity(
        str(draft), {"customer": "APP", "ble_names": ["S205-BLE", "S205-2"]}
    )
    assert result["ok"], result
    assert result["customer"] == "APP"
    assert result["ble_names"] == ["S205-BLE", "S205-2"]

    # 配置是真相源
    config = _load(draft)
    assert model.project(config)["customer"] == "APP"
    assert model.ble_names(config) == ["S205-BLE", "S205-2"]
    # 源码已同步：第一广播名写进 mouse_hw.c（唯一可改点，KC536 基线无 adv memcpy 模式）
    assert "S205-BLE" in mhw.read_text(encoding="utf-8")
    # ex2_app_mouse.c 在 KC536 基线里没有 memcpy(mouse_name, ...) 模式 → rewrite 不硬造、不改
    assert "S205-BLE" not in adv.read_text(encoding="utf-8")


def test_set_identity_rejects_oversize_ble_name(draft):
    bad = Api().blank_set_identity(str(draft), {"ble_names": ["X" * 29]})
    assert bad["ok"] is False and "28" in (bad.get("error") or "")
    bad_customer = Api().blank_set_identity(str(draft), {"customer": "  "})
    assert bad_customer["ok"] is False
    bad_key = Api().blank_set_identity(str(draft), {"unknown": "x"})
    assert bad_key["ok"] is False
