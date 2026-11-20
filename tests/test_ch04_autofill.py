"""CH04 灯带/矩阵键工程：后端判定、源码守护、端到端生成回归。

固化三处改动：
1. 矩阵键 KEY_C0 板型不再要求 KEY_B/P/DPI（与 biz_sync 改写对齐）；
2. ledc 插件不再 keep LED_R/G/B（led.c 已按 BOARD_LOGO_RGB 守护）；
3. CH04 从真实工程解析 → 填表 → 生成 → Keil 0/0 的端到端链路。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from omcfg import baseline, blank, model
from omcfg.api import Api

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import ch04_autofill as autofill  # noqa: E402

UV4 = Path(os.environ.get("OMCFG_UV4", r"C:\Keil_v5\UV4\UV4.exe"))
CH04_HEADER = (
    Path("E:/M_2026/M_2026_T/457_CH04/SE71M_0457_CH04_V4_20260829")
    / "projects/mouse_demo/periph/user_config.h"
)


# --- 1. 后端判定 ------------------------------------------------------------

def test_matrix_key_does_not_require_b_p_dpi():
    """配了 KEY_C0_PIN 后，KEY_B/P/DPI 不再是硬依赖。"""
    cfg = blank.empty_config("CH04")
    cfg["pins"]["KEY_C0_PIN"] = "P31"
    required = set(blank.build_required_roles(config=cfg))
    for role in ("KEY_B_PIN", "KEY_P_PIN", "KEY_DPI_PIN"):
        assert role not in required, f"矩阵键板型仍误报缺 {role}"


def test_plain_board_still_requires_b_p_dpi():
    """无 KEY_C0 的板型（KC536）仍必须要求三键，不能被上面的放宽影响。"""
    cfg = blank.empty_config("KC536")
    required = set(blank.build_required_roles(config=cfg))
    for role in ("KEY_B_PIN", "KEY_P_PIN", "KEY_DPI_PIN"):
        assert role in required, f"KC536 板型应保留 {role} 硬依赖"


def test_ledc_rgb_pins_not_required_in_generate():
    """灯带模式生成时不要求 LED_R/G/B，但 keep_roles 仍在（保证关插件回 RGB 不缺脚）。"""
    cfg = blank.empty_config("CH04")
    cfg["board"]["logo"] = "ledc"
    cfg["plugins"] = ["ledc"]
    cfg["pins"]["LEDC_PIN"] = "P05"
    cfg["pins"]["LEDC_CTRL_PIN"] = "P34"
    missing = set(blank.missing_roles(cfg))
    for role in ("LED_R_PIN", "LED_G_PIN", "LED_B_PIN"):
        assert role not in missing, f"灯带模式不应要求 {role}"
    # 推荐填充仍严格：这三脚会被填上
    strict = set(blank.missing_roles(cfg, include_ledc_rgb=True))
    for role in ("LED_R_PIN", "LED_G_PIN", "LED_B_PIN"):
        assert role in strict, f"推荐填充应保留 {role}"


def test_baseline_led_rgb_guarded():
    text = (baseline.SDK_DIR / "projects/mouse_demo/periph/led.c").read_text(encoding="utf-8")
    assert text.count("#if BOARD_LOGO_RGB") >= 2, "pwm_off/pwm_write 需按 LOGO 守护"


# --- 2. 解析事实 ------------------------------------------------------------

@pytest.mark.skipif(not CH04_HEADER.is_file(), reason="无 CH04 原始工程")
def test_parse_ch04_facts():
    req = autofill.parse_requirements(CH04_HEADER)
    assert req["name"] == "CH04"
    assert req["id_low"] == 0x0457
    assert req["version"] == 4
    assert req["customer"] == "App"
    assert req["ble_name"] == "CH-04 Bt1"
    assert req["mode_dual"] is True
    assert req["has_key_c0"] is True
    assert req["wheel"] == "ENCODER_PINMUX_SEL_IO_00_01"
    assert req["params"]["rgb_count"] == 6
    # LEDC 语义对调：DIN=P05 / 控制=P34
    assert req["pins"]["LEDC_PIN"] == "P05"
    assert req["pins"]["LEDC_CTRL_PIN"] == "P34"
    # 不硬造传感器型号
    assert "sensor" not in req["selections"]


# --- 3. 端到端 --------------------------------------------------------------

@pytest.mark.skipif(not CH04_HEADER.is_file(), reason="无 CH04 原始工程")
def test_ch04_fill_and_generate(tmp_path):
    """从真实工程解析 → 完整填表 → 生成 → 读产物断言，不依赖 Keil。"""
    root = tmp_path / "CH04"
    req = autofill.parse_requirements(CH04_HEADER)
    api = Api()
    assert api.blank_new("CH04", str(root), customer=req["customer"],
                         id_low=req["id_low"], version=req["version"],
                         ble_name=req["ble_name"])["ok"]
    assert api.material_apply(str(root), req["selections"], req["params"])["ok"]
    assert api.blank_set_board(str(root), {
        "mode_pins": "dual", "logo": "ledc", "wheel": req["wheel"],
        "ledc_rgb_number": req["params"]["rgb_count"], "led_polarity": "active_high",
        "switch_segments": 3, "ble_channels": 2, "sensor.dir_clock": req["dir_clock"],
        "mode_24g_led": req["mode_24g_led"], "led_indicator": req["led_indicator"],
    })["ok"]
    assert api.blank_save(str(root), req["pins"])["ok"]
    st = api.blank_status(str(root))
    assert st["complete"] and not st["missing"] and not st["conflicts"]
    assert api.blank_apply(str(root))["ok"]

    header = (root / "projects/mouse_demo/periph/user_config.h").read_text(encoding="utf-8")
    assert "#define LEDC_PIN                (P05)" in header
    assert "#define LEDC_CTRL_PIN           (P34)" in header
    assert 'iCONSUMER_NAME "App"' in header
    cfg = model.load_config(model.default_config_path(root))
    assert cfg["project"]["id"]["version"] == 5  # 原 4，apply +1
    feats = (root / "projects/mouse_demo/periph/board_features.h").read_text(encoding="utf-8")
    assert "BOARD_LOGO_LEDC             (1)" in feats
    assert "BOARD_HAS_KEY_C0            (1)" in feats


@pytest.mark.skipif(not (CH04_HEADER.is_file() and UV4.is_file()), reason="无 CH04 工程或 Keil UV4")
def test_ch04_keil_build(tmp_path):
    """有 Keil 时真编译，断言 0 Error / 0 Warning。"""
    root = tmp_path / "CH04Build"
    req = autofill.parse_requirements(CH04_HEADER)
    api = Api()
    api.blank_new("CH04", str(root), customer=req["customer"], id_low=req["id_low"],
                  version=req["version"], ble_name=req["ble_name"])
    api.material_apply(str(root), req["selections"], req["params"])
    api.blank_set_board(str(root), {
        "mode_pins": "dual", "logo": "ledc", "wheel": req["wheel"],
        "ledc_rgb_number": req["params"]["rgb_count"], "led_polarity": "active_high",
        "switch_segments": 3, "ble_channels": 2, "sensor.dir_clock": req["dir_clock"],
        "mode_24g_led": req["mode_24g_led"], "led_indicator": req["led_indicator"],
    })
    api.blank_save(str(root), req["pins"])
    assert api.blank_apply(str(root))["ok"]

    proj = root / "projects/mouse_demo/keil5/SE71M.uvprojx"
    log = tmp_path / "build.log"
    subprocess.run([str(UV4), "-r", str(proj), "-o", str(log)],
                   capture_output=True, text=True, timeout=300)
    content = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    assert "0 Error(s), 0 Warning(s)" in content, content[-500:]
