# -*- coding: utf-8 -*-
"""自助餐策略清单：13 个策略，从旧版 board_pack.POLICY_DEFS 迁移。

字段说明：
  id / title / kind
  default_rgb / default_ledc — 按板型给默认勾选（RGB 板 vs LEDC 板）
  rel / patch                — kind='patch' 时用
  rels                       — kind='copy'/'sync' 时用（相对 SDK 根的路径元组）
  requires                   — 策略间依赖，第一版全空

kind 取值：
  ui_pins        — 由 UI 改引脚（阶段 1 末尾做）
  biz_sync       — 调 biz_sync.sync_board_contracts 同步 key_io/sleep 契约
  patch          — 正则补丁（rel + patch）
  donor_copy     — 从供体拷文件（rels）
  donor_or_patch — 有供体拷、无供体 patch
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Policy:
    id: str
    title: str
    kind: str
    default_rgb: bool
    default_ledc: bool
    rel: str = ""
    patch: str = ""
    rels: tuple = ()
    requires: tuple = ()


POLICIES: tuple = (
    Policy(
        id="project_id",
        title="工程身份（ID/名字/BLE 名）同改 user_config/startup/mouse_hw",
        kind="board_patch",
        default_rgb=True, default_ledc=True,
        rels=(
            "projects/mouse_demo/periph/user_config.h",
            "hal/device/om6239/GCC/startup_om6239.S",
            "projects/mouse_demo/main/mouse_hw.c",
        ),
    ),
    Policy(
        id="sensor",
        title="传感器引脚/方向/SPI 模式（同 interface 值替换；interface 切换需人工）",
        kind="board_patch",
        default_rgb=True, default_ledc=True,
        rels=(
            "projects/mouse_demo/periph/user_config.h",
            "hal/driver/om6239/drv_senscan.c",
        ),
    ),
    Policy(
        id="wheel",
        title="滚轮 A/B 引脚与 ENCODER 组（三行值替换；A/B 对调表达方向）",
        kind="board_patch",
        default_rgb=True, default_ledc=True,
        rels=("projects/mouse_demo/periph/user_config.h",),
    ),
    Policy(
        id="switch",
        title="拨杆模式脚（单/双脚 + 上下拉；极性变更需人工）",
        kind="board_patch",
        default_rgb=True, default_ledc=True,
        rels=(
            "projects/mouse_demo/periph/user_config.h",
            "projects/mouse_demo/periph/user_config.c",
            "projects/mouse_demo/periph/key_io.c",
        ),
    ),
    Policy(
        id="led",
        title="LED 模式灯引脚 + 极性（v1：只改 LED_MODE_RGB 引脚与 init_level）",
        kind="board_patch",
        default_rgb=True, default_ledc=True,
        rels=(
            "projects/mouse_demo/periph/user_config.h",
            "projects/mouse_demo/periph/user_config.c",
        ),
    ),
    Policy(
        id="power",
        title="电源脚：USB_5V / BAT_CHG / LVD（v1：只改引脚与 LVD 派生；wake 宏留给 biz_sync）",
        kind="board_patch",
        default_rgb=True, default_ledc=True,
        rels=("projects/mouse_demo/periph/user_config.h",),
    ),
    Policy(
        id="pins_user_config",
        title="写入脚位 user_config（由 UI 生成块）",
        kind="ui_pins",
        default_rgb=True, default_ledc=True,
    ),
    Policy(
        id="biz_sync_contracts",
        title="同步 key_io / sleep 契约",
        kind="biz_sync",
        default_rgb=True, default_ledc=True,
    ),
    Policy(
        id="senscan_12bit",
        title="drv_senscan DATA_FORMAT 改 12BIT（KC536 底包必开；勿用供体 8BIT 覆盖）",
        kind="patch",
        default_rgb=True, default_ledc=True,
        rel="hal/driver/om6239/drv_senscan.c",
        patch="senscan_12bit",
    ),
    Policy(
        id="usb_tx_flag_timing",
        title="usb_user_process 鼠标发送 flag 提前清零",
        kind="donor_or_patch",
        default_rgb=True, default_ledc=True,
        rel="mode_usb/usb_user_process.c",
        patch="usb_tx_flag",
    ),
    Policy(
        id="rf_callback_hdr",
        title="rf_data_process.h 回调声明改无参（与 KC536 底包一致）",
        kind="patch",
        default_rgb=True, default_ledc=True,
        rel="mode_24g/rf_data_process.h",
        patch="rf_callback",
    ),
    Policy(
        id="sensor_type_check",
        title="sensor_type_check.c/.h（需供体）",
        kind="donor_copy",
        default_rgb=True, default_ledc=True,
        rels=(
            "projects/mouse_demo/periph/sensor_type_check.c",
            "projects/mouse_demo/periph/sensor_type_check.h",
        ),
    ),
    Policy(
        id="stack_sct",
        title="om6239_ac6.sct 栈改 0x240（KC536/CH04 底包；勿用供体 0x280 覆盖）",
        kind="patch",
        default_rgb=True, default_ledc=True,
        rel="hal/device/om6239/ARM/om6239_ac6.sct",
        patch="stack_240",
    ),
    Policy(
        id="senscan_donor",
        title="drv_senscan.c 从供体拷贝（默认关；会盖 12BIT，易开机卡死）",
        kind="donor_copy",
        default_rgb=False, default_ledc=False,
        rels=("hal/driver/om6239/drv_senscan.c",),
    ),
    Policy(
        id="ledc_pack",
        title="LEDC 灯带包（ledc*/RTE/uvproj）— RGB 板应关闭",
        kind="donor_copy",
        default_rgb=False, default_ledc=True,
        rels=(
            "projects/mouse_demo/periph/ledc.c",
            "projects/mouse_demo/periph/ledc.h",
            "projects/mouse_demo/periph/ledc_mode.c",
            "projects/mouse_demo/periph/ledc_mode.h",
            "hal/driver/om6239/drv_ledc.c",
            "hal/driver/om6239/drv_ledc.h",
            "hal/driver/om6239/drv_pmu.h",
            "hal/driver/om6239/drv_isr.c",
        ),
    ),
    Policy(
        id="rgb_logo_pack",
        title="RGB LOGO 业务（led/mode_ind 等，需供体）",
        kind="donor_copy",
        default_rgb=True, default_ledc=False,
        rels=(
            "projects/mouse_demo/periph/led.c",
            "projects/mouse_demo/periph/led.h",
            "projects/mouse_demo/periph/mode_ind.c",
            "projects/mouse_demo/periph/lvd.c",
            "projects/mouse_demo/periph/lvd.h",
            "projects/mouse_demo/periph/sensor.c",
            "projects/mouse_demo/periph/sensor.h",
            "projects/mouse_demo/main/mouse.h",
            "projects/mouse_demo/main/mouse_hw.c",
            "projects/mouse_demo/main/main.h",
            "mode_24g/sleep.c",
            "mode_24g/sleep.h",
            "mode_24g/main_24g.c",
            "mode_usb/main_usb.c",
        ),
    ),
    Policy(
        id="product_usb_strings",
        title="USB 描述符字符串（产品字，默认关）",
        kind="donor_copy",
        default_rgb=False, default_ledc=False,
        rels=("mode_usb/usb_descriptor.h",),
    ),
    Policy(
        id="startup_pid",
        title="startup 产品字（默认关）",
        kind="donor_copy",
        default_rgb=False, default_ledc=False,
        rels=("hal/device/om6239/GCC/startup_om6239.S",),
    ),
    Policy(
        id="fcc_leds",
        title="FCC 指示灯逻辑（默认关）",
        kind="donor_copy",
        default_rgb=False, default_ledc=False,
        rels=("mode_24g/rf_fcc_key_ctrl.c",),
    ),
)

_POLICY_BY_ID = {p.id: p for p in POLICIES}


def get_policy(pid: str):
    """按 id 取策略；不存在返回 None。"""
    return _POLICY_BY_ID.get(pid)


def default_policy(logo_ledc: bool) -> dict:
    """按板型（RGB vs LEDC）返回默认勾选状态。"""
    return {
        p.id: bool(p.default_ledc if logo_ledc else p.default_rgb)
        for p in POLICIES
    }
