"""真实端到端链路回归（不依赖 pywebview / jsdom / node）。

用真实 Api 从零建工程、配脚、写盘，读回生成文件断言宏正确，覆盖 GUI 里
可能出现的多种操作顺序。这是「这工具真的能产出工程」的硬证据，也是顺序
组合 bug（先勾插件后一键推荐）的回归防线。

Keil 编译单独成一个测试：有 UV4 才跑，无则跳过；不把外部 exe 变成
pytest 的硬依赖。手动一键验收（含编译报告）见 scripts/e2e_check.py。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from omcfg.api import Api

REPO = Path(__file__).resolve().parent.parent
UV4 = Path(os.environ.get("OMCFG_UV4", r"C:\Keil_v5\UV4\UV4.exe"))
# 源码无条件引用的宏：缺一个 Keil 就会报 undeclared identifier。
BUILD_REQUIRED_MACROS = (
    "WHEEL_A_PIN",
    "WHEEL_B_PIN",
    "LED_R_PIN",
    "LED_G_PIN",
    "LED_B_PIN",
    "LEDC_PIN",
    "LEDC_CTRL_PIN",
)


def _user_config(sdk: str) -> str:
    path = Path(sdk) / "projects/mouse_demo/periph/user_config.h"
    assert path.is_file(), f"生成头缺失: {path}"
    return path.read_text(encoding="utf-8", errors="replace")


def _fresh_sdk(tmp_path: Path, name: str = "E2E") -> str:
    sdk = str((tmp_path / name).resolve())
    r = Api().blank_new(name, sdk, id_low=0x0701)
    assert r["ok"], r
    return sdk


def _assert_buildable_header(sdk: str) -> None:
    text = _user_config(sdk)
    for macro in BUILD_REQUIRED_MACROS:
        assert f"#define {macro}" in text, f"生成头缺宏 {macro}"


def test_e2e_plugin_then_fill_recommended(tmp_path):
    """GUI 默认顺序：建空白 → 勾 LEDC → 一键推荐 → 生成。"""
    api = Api()
    sdk = _fresh_sdk(tmp_path)
    assert api.plugin_toggle(sdk, "ledc", True)["ok"]
    filled = api.blank_fill_recommended(sdk)
    assert filled["ok"], filled
    assert filled["status"]["complete"], filled["status"]
    assert not filled["status"]["missing"] and not filled["status"]["conflicts"]

    applied = api.blank_apply(sdk)
    assert applied["ok"], applied
    assert applied.get("manifest"), "写盘应产生 manifest 回滚点"
    _assert_buildable_header(sdk)
    text = _user_config(sdk)
    assert "(P36)" in text.split("LED_MODE_B_PIN")[1].split("\n")[0], "LED_MODE_B 应腾到 P36"


def test_e2e_fill_recommended_then_plugin(tmp_path):
    """另一种顺序：建空白 → 一键推荐 → 勾 LEDC → 手动配 DIN/CTRL → 生成。"""
    api = Api()
    sdk = _fresh_sdk(tmp_path)
    filled = api.blank_fill_recommended(sdk)
    assert filled["ok"] and filled["status"]["complete"], filled
    assert api.plugin_toggle(sdk, "ledc", True)["ok"]
    # 插件角色默认未配，手工补齐后应可生成。
    # enable() 已把 LED_MODE_B 从 P01 腾到 P36，故 LEDC_PIN 用 P01（P05 仍被 LED_G 占）。
    assert api.blank_save(sdk, {"LEDC_PIN": "P01", "LEDC_CTRL_PIN": "P33"})["ok"]
    assert api.blank_status(sdk)["complete"], api.blank_status(sdk)
    assert api.blank_apply(sdk)["ok"]
    _assert_buildable_header(sdk)


def test_e2e_plugin_disable_removes_files_and_macros(tmp_path):
    """取消插件应对称撤销：文件移除、插件宏消失、仍可生成。"""
    api = Api()
    sdk = _fresh_sdk(tmp_path)
    assert api.plugin_toggle(sdk, "ledc", True)["ok"]
    assert api.blank_fill_recommended(sdk)["ok"]
    assert api.blank_apply(sdk)["ok"]
    periph = Path(sdk) / "projects/mouse_demo/periph"
    assert (periph / "ledc.c").is_file()

    assert api.plugin_toggle(sdk, "ledc", False)["ok"]
    for name in ("ledc.c", "ledc.h", "ledc_mode.c", "ledc_mode.h"):
        assert not (periph / name).exists(), f"插件文件残留: {name}"
    # 取消插件只改配置/删文件，生成头要重新写盘才更新（与 GUI 流程一致）。
    assert api.blank_apply(sdk)["ok"], api.blank_status(sdk)
    text = _user_config(sdk)
    assert "#define LEDC_PIN" not in text and "#define LEDC_CTRL_PIN" not in text
    # 取消后 RGB 应恢复（logo 回到 rgb），仍可生成。
    for macro in ("LED_R_PIN", "LED_G_PIN", "LED_B_PIN"):
        assert f"#define {macro}" in text, f"取消插件后缺 {macro}"


@pytest.mark.skipif(not UV4.is_file(), reason=f"未找到 Keil UV4（{UV4}），跳过编译验收")
def test_e2e_keil_build(tmp_path):
    """真实 Keil 全量重编：从零产出工程，预期 0 Error / 0 Warning。"""
    api = Api()
    sdk = _fresh_sdk(tmp_path, "KeilE2E")
    assert api.plugin_toggle(sdk, "ledc", True)["ok"]
    assert api.blank_fill_recommended(sdk)["ok"]
    assert api.blank_apply(sdk)["ok"]

    proj = Path(sdk) / "projects/mouse_demo/keil5/SE71M.uvprojx"
    assert proj.is_file(), f"Keil 工程缺失: {proj}"
    log = tmp_path / "build.log"
    proc = subprocess.run(
        [str(UV4), "-r", str(proj), "-o", str(log)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert log.is_file(), f"Keil 未生成日志: {proc.stdout} {proc.stderr}"
    content = log.read_text(encoding="utf-8", errors="replace")
    assert "0 Error(s), 0 Warning(s)" in content, (
        f"Keil 编译未通过（exit={proc.returncode}）:\n" + content[-2000:]
    )
    # 清理 Keil 生成的中间产物，避免污染 tmp 之外的目录。
    out = Path(sdk) / "projects/mouse_demo/keil5/out"
    if out.is_dir():
        shutil.rmtree(out, ignore_errors=True)


# S205 场景：双脚模式 + 无 mode 键，KC536 骨架 key_io.c 写死单脚 MODE_BLE_24G_PIN，
# 若 apply() 不把源码契约同步纳入事务，Keil 会报 undeclared identifier。
S205_PINS = {
    "KEY_R0_PIN": "P26", "KEY_R1_PIN": "P20", "KEY_R2_PIN": "P21",
    "KEY_B_PIN": "P27", "KEY_P_PIN": "P34", "KEY_DPI_PIN": "P30",
    "WHEEL_A_PIN": "P24", "WHEEL_B_PIN": "P25",
    "SENSOR_NCS_PIN": "P10", "SENSOR_MOTION_PIN": "P07",
    "SENSOR_SCLK_PIN": "P11", "SENSOR_SDIO_PIN": "P12",
    "MODE_24G_PIN": "P31", "MODE_BLE_PIN": "P23",
    "LED_MODE_R_PIN": "P04", "LED_MODE_G_PIN": "P05", "LED_MODE_B_PIN": "P06",
    "LED_LOW_PIN": "P22", "LED_R_PIN": "P04", "LED_G_PIN": "P05", "LED_B_PIN": "P06",
    "USB_5V": "P00", "BAT_CHG_PIN": "P01", "LVD_PIN": "P33",
    "USB_DN_PIN": "P02", "USB_DP_PIN": "P03",
    "FLASH_CS_PIN": "P17", "FLASH_SCLK_PIN": "P15",
    "FLASH_MOSI_PIN": "P16", "FLASH_MISO_PIN": "P14",
}
S205_POLARITY = {
    "LED_MODE_R_PIN": "active_low", "LED_MODE_G_PIN": "active_low",
    "LED_MODE_B_PIN": "active_low", "LED_LOW_PIN": "active_high",
}
S205_SELECTIONS = {"sensor": "S205", "led_strip": "none", "charger": "4056H", "mode_key": "absent"}
S205_PARAMS = {"rgb_count": 3, "switch_segments": 3}


def _build_s205(tmp_path, name="S205Dual"):
    api = Api()
    sdk = str((tmp_path / name).resolve())
    assert api.blank_new(name, sdk, id_low=0x0512)["ok"]
    assert api.material_apply(sdk, S205_SELECTIONS, S205_PARAMS)["ok"]
    assert api.blank_set_board(
        sdk,
        {"mode_pins": "dual", "logo": "rgb", "wheel": "SOFT_GPIO", "switch_segments": 3, "ble_channels": 2},
    )["ok"]
    assert api.blank_save(sdk, S205_PINS)["ok"]
    assert api.blank_set_polarity(sdk, S205_POLARITY)["ok"]
    st = api.blank_status(sdk)
    assert st["complete"] and not st["missing"] and not st["conflicts"], st
    assert api.blank_apply(sdk)["ok"]
    return sdk


def test_dual_mode_rewrites_key_io_source(tmp_path):
    """双脚+无PAIR：apply() 必须把 key_io.c/h 源码契约同步改写（无需 Keil）。"""
    sdk = _build_s205(tmp_path)
    periph = Path(sdk) / "projects/mouse_demo/periph"
    key_io_c = (periph / "key_io.c").read_text(encoding="utf-8", errors="replace")
    key_io_h = (periph / "key_io.h").read_text(encoding="utf-8", errors="replace")
    assert "MODE_BLE_24G_PIN" not in key_io_c, "key_io.c 仍写死单脚 MODE_BLE_24G_PIN"
    assert "gpio_read(MODE_24G_PIN)" in key_io_c, "key_io.c 未改成双脚模式判断"
    assert "#ifdef KEY_PAIR_PIN" in key_io_h, "key_io.h 的 PAIR 宏未加编译保护"
    user_c = (periph / "user_config.c").read_text(encoding="utf-8", errors="replace")
    assert "MODE_24G_PIN" in user_c and "MODE_BLE_24G_PIN" not in user_c
    assert "KEY_PAIR_PIN" not in user_c


def test_dual_mode_keil_build(tmp_path):
    """双脚+无PAIR 真实工程必须 Keil 0/0（S205 自动填表脚本的回归防线）。"""
    sdk = _build_s205(tmp_path, "S205DualKeil")
    proj = Path(sdk) / "projects/mouse_demo/keil5/SE71M.uvprojx"
    assert proj.is_file()
    log = tmp_path / "dual_build.log"
    subprocess.run(
        [str(UV4), "-r", str(proj), "-o", str(log)],
        capture_output=True, text=True, timeout=300, check=False,
    )
    content = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    assert "0 Error(s), 0 Warning(s)" in content, content[-2000:]
    out = Path(sdk) / "projects/mouse_demo/keil5/out"
    if out.is_dir():
        shutil.rmtree(out, ignore_errors=True)
