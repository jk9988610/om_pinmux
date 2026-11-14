# -*- coding: utf-8 -*-
"""自助餐工作流：策略清单 + 执行引擎 + feat 推导。

与 omcfg 配置驱动路径（init/gen/check）并存，共享 transaction/rules/pinmap。
不依赖 project.omcfg，直接读 SDK 现状。
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from . import biz_sync, policy
from .targets import sdk
from .transaction import FileTransaction


# ============ feat 推导（总工规则表） ============

def _feat_from_sdk(sdk_root):
    """按规则表从 SDK 现状推导 feat。全部 bool，推导失败=False，不抛异常。

    has_key_pair / has_key_c0：有定义 + 被 key_io.c 或 key_io.h 引用
    mode_dual / mode_single：有定义 + 被引用，且互斥
    logo_ledc：LEDC_PIN 有定义 + ledc.c 存在
    """
    root = Path(sdk_root)
    periph = root / sdk.PERIPH
    try:
        refs = biz_sync.scan_project_refs(str(periph))
    except Exception:
        refs = {}
    pins = refs.get("pins") or {}
    macro_files = refs.get("macro_files") or {}

    def has_def(m):
        return m in pins

    def used_anywhere(m):
        return bool(macro_files.get(m))

    def used_in_key_io(m):
        files = macro_files.get(m) or []
        return any(f in ("key_io.c", "key_io.h") for f in files)

    has_key_pair = has_def("KEY_PAIR_PIN") and used_in_key_io("KEY_PAIR_PIN")
    has_key_c0 = has_def("KEY_C0_PIN") and used_in_key_io("KEY_C0_PIN")
    has_dpi_pair = has_def("KEY_DPI_SUB_PIN") or has_def("KEY_DPI_ADD_PIN")
    extra_cnt = sum(1 for m in ("KEY_B_PIN", "KEY_P_PIN", "KEY_DPI_PIN") if has_def(m))
    has_extra_keys = extra_cnt >= 2

    # 模式判定（用户澄清 + boards/*.json + biz_sync 用法三方印证）：
    #   dual   = MODE_24G_PIN + MODE_BLE_PIN 两个独立脚都有（各表示一个挡位）
    #   single = 只有 MODE_BLE_24G_PIN（一个脚电平切换），或只有 MODE_24G_PIN
    #   都没有 = wired（dual=False, single=False）
    #   互斥，dual 优先
    has_24g = has_def("MODE_24G_PIN") and used_anywhere("MODE_24G_PIN")
    has_ble = has_def("MODE_BLE_PIN") and used_anywhere("MODE_BLE_PIN")
    has_combo = has_def("MODE_BLE_24G_PIN") and used_anywhere("MODE_BLE_24G_PIN")
    mode_dual = bool(has_24g and has_ble)
    if mode_dual:
        mode_single = False
    else:
        mode_single = bool(has_combo or has_24g)

    logo_ledc = has_def("LEDC_PIN") and (periph / "ledc.c").is_file()
    logo_rgb = not logo_ledc

    return {
        "has_key_pair": bool(has_key_pair),
        "has_key_c0": bool(has_key_c0),
        "has_dpi_pair": bool(has_dpi_pair),
        "has_extra_keys": bool(has_extra_keys),
        "mode_dual": bool(mode_dual),
        "mode_single": bool(mode_single),
        "logo_ledc": bool(logo_ledc),
        "logo_rgb": bool(logo_rgb),
        "golden_periph": str(periph),
    }


# ============ 策略可用性（售罄判断） ============

def _policy_available(pdef, root):
    """按 sdk 现状判断策略是否可用（售罄=False）。不藏菜，标售罄。"""
    if pdef.kind in ("ui_pins", "biz_sync"):
        return True
    if pdef.kind in ("patch", "donor_or_patch"):
        return bool(pdef.rel) and (root / pdef.rel).is_file()
    if pdef.kind == "board_patch":
        return bool(pdef.rels) and any((root / rel).is_file() for rel in pdef.rels)
    if pdef.kind == "donor_copy":
        # 全部 rels 已存在 → 售罄；任一缺失 → 需要拷
        if not pdef.rels:
            return False
        return any(not (root / rel).is_file() for rel in pdef.rels)
    return True


# ============ 策略清单 ============

def list_policies(sdk_root):
    """列出全部 13 个策略 + 默认勾选 + 可用性。"""
    root = sdk.resolve_sdk(sdk_root)
    feat = _feat_from_sdk(root)
    rows = []
    for p in policy.POLICIES:
        default = bool(p.default_ledc if feat["logo_ledc"] else p.default_rgb)
        rows.append({
            "id": p.id,
            "title": p.title,
            "kind": p.kind,
            "default": default,
            "available": _policy_available(p, root),
            "needs_donor": p.kind in ("donor_copy", "donor_or_patch"),
            "rel": p.rel,
            "rels": list(p.rels),
        })
    return {
        "ok": True,
        "sdk_root": str(root),
        "feat": feat,
        "policies": rows,
        "policy_count": len(rows),
        "available_count": sum(1 for r in rows if r["available"]),
    }


# ============ board 驱动策略：project_id ============

class PolicyError(Exception):
    """策略执行失败。"""


def _validate_project_id(board):
    """校验 board['project'] 段，返回错误列表（空=通过）。"""
    errs = []
    p = board.get("project") or {}
    id_h = p.get("id_h")
    id_l = p.get("id_l")
    name = p.get("name")
    consumer = p.get("consumer")
    ver = p.get("version", 1)
    ble = p.get("ble") or {}
    channels = ble.get("channels", 1)
    names = ble.get("names") or ([name] if name else [])

    if not isinstance(id_h, int) or not (0 <= id_h <= 0xFFF):
        errs.append("project.id_h 必须是 0x000-0xFFF 的整数")
    if not isinstance(id_l, int) or not (0 <= id_l <= 0xFFFF):
        errs.append("project.id_l 必须是 0x0000-0xFFFF 的整数")
    if not name or chr(34) in str(name):
        errs.append("project.name 非空且不含双引号")
    if not consumer or chr(34) in str(consumer):
        errs.append("project.consumer 非空且不含双引号")
    if not isinstance(ver, int) or not (1 <= ver <= 0x7F):
        errs.append("project.version 必须是 1-0x7F 的整数（0x80 位被占用）")
    if channels not in (1, 2):
        errs.append("project.ble.channels 必须是 1 或 2")
    if channels == 2:
        errs.append("project.ble.channels=2（双通道）暂不支持，请先按单通道填（TODO 参照 524 的 0a491d7 实现双通道）")
    if len(names) != channels:
        errs.append("project.ble.names 长度必须等于 channels")
    for n in names:
        s = str(n) if n is not None else ""
        if not s or chr(34) in s or len(s) > 29:
            errs.append("BLE 名 %r 非法（空/含双引号/超 29 字符）" % (n,))
    return errs


def _read_text_auto(path):
    """读文件并自动检测编码（UTF-8 优先，失败回退 GBK）。"""
    raw = path.read_bytes()
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8"


def _plan_project_id(board, root):
    r"""返回 [(file_rel, [(pattern, repl, label), ...]), ...]。

    不读文件；pattern 是正则，repl 里用 \g<1> 引用第一个捕获组。
    幂等性由 apply 阶段比对文本决定。
    """
    p = board["project"]
    id_h = p["id_h"]
    id_l = p["id_l"]
    name = p["name"]
    consumer = p["consumer"]
    ver = p.get("version", 1)
    ble = p.get("ble") or {}
    names = ble.get("names") or [name]
    ble_name = names[0]

    startup_id = "0x00%02X%04X" % (id_h & 0xFF, id_l)

    uc_patches = [
        (r"(#define\s+iPROJECT_ID_H\s+)0x[0-9A-Fa-f]+",
         r"\g<1>0x%03X" % id_h, "iPROJECT_ID_H"),
        (r"(#define\s+iPROJECT_ID_L\s+)0x[0-9A-Fa-f]+",
         r"\g<1>0x%04X" % id_l, "iPROJECT_ID_L"),
        (r"(#define\s+iREAL_VERSION_ID\s+)\d+",
         r"\g<1>%d" % ver, "iREAL_VERSION_ID"),
        (r'(#define\s+iCONSUMER_NAME\s+)"[^"]*"',
         r'\g<1>"%s"' % consumer, "iCONSUMER_NAME"),
        (r'(#define\s+iPROJECT_NAME\s+)"[^"]*"',
         r'\g<1>"%s"' % name, "iPROJECT_NAME"),
    ]
    st_patches = [
        (r"(\.long\s+)0x007[01][0-9A-Fa-f]{4}",
         r"\g<1>" + startup_id, "startup_id"),
    ]
    mh_patches = [
        (r'(mouse_name\[MOUSE_NAME_MAX_LEN\]\s*=\s*)"[^"]*"',
         r'\g<1>"%s"' % ble_name, "mouse_name"),
    ]
    return [
        ("projects/mouse_demo/periph/user_config.h", uc_patches),
        ("hal/device/om6239/GCC/startup_om6239.S", st_patches),
        ("projects/mouse_demo/main/mouse_hw.c", mh_patches),
    ]


def _apply_project_id(board, root, tx):
    """按 plan 改 3 个文件，全部走 tx.write_text（自动备份 + manifest）。"""
    plan = _plan_project_id(board, root)
    applied = []
    for file_rel, patches in plan:
        path = root / file_rel
        if not path.is_file():
            raise PolicyError("缺少文件: %s" % file_rel)
        text, enc = _read_text_auto(path)
        new_text = text
        for pattern, repl, label in patches:
            new_text, n = re.subn(pattern, repl, new_text, count=1)
            if n == 0:
                raise PolicyError("%s 锚点未匹配: %s" % (file_rel, label))
        if new_text != text:
            tx.write_text(path, new_text, encoding=enc)
            applied.append(file_rel)
    return applied


# ============ board 驱动策略：sensor ============

_SENSOR_INTERFACES = ("4w", "2w+ncs", "2w")
_SENSOR_DIRS = ("CLOCK_0", "CLOCK_3", "CLOCK_6", "CLOCK_9")
_SENSOR_DATA_FORMATS = ("8bit", "12bit")


def _validate_sensor(board):
    errs = []
    s = board.get("sensor") or {}
    iface = s.get("interface")
    dir_ = s.get("dir")
    ncs = s.get("ncs")
    sdio = s.get("sdio")
    mosi = s.get("mosi")
    miso = s.get("miso")
    sclk = s.get("sclk")
    motion = s.get("motion")
    data_format = s.get("data_format")

    if iface not in _SENSOR_INTERFACES:
        errs.append("sensor.interface 必须是 %r 之一" % (_SENSOR_INTERFACES,))
        return errs
    if dir_ not in _SENSOR_DIRS:
        errs.append("sensor.dir 必须是 %r 之一" % (_SENSOR_DIRS,))
    if not sclk:
        errs.append("sensor.sclk 必填")
    if not motion:
        errs.append("sensor.motion 必填")

    if iface == "4w":
        if not mosi or not miso:
            errs.append("interface=4w 时 mosi/miso 必填")
        if not ncs:
            errs.append("interface=4w 时 ncs 必填")
        if sdio:
            errs.append("interface=4w 时 sdio 必须为 null")
    elif iface == "2w+ncs":
        if not sdio:
            errs.append("interface=2w+ncs 时 sdio 必填")
        if not ncs:
            errs.append("interface=2w+ncs 时 ncs 必填")
        if mosi or miso:
            errs.append("interface=2w+ncs 时 mosi/miso 必须为 null")
    elif iface == "2w":
        if not sdio:
            errs.append("interface=2w 时 sdio 必填")
        if ncs:
            errs.append("interface=2w 时 ncs 必须为 null")
        if mosi or miso:
            errs.append("interface=2w 时 mosi/miso 必须为 null")

    if data_format is not None and data_format not in _SENSOR_DATA_FORMATS:
        errs.append("sensor.data_format 必须是 %r 或 null" % (_SENSOR_DATA_FORMATS,))

    pins = [p for p in (ncs, sclk, sdio, mosi, miso, motion) if p]
    if len(pins) != len(set(pins)):
        errs.append("传感器引脚有重复: %r" % (pins,))

    return errs


def _plan_sensor(board, root):
    s = board["sensor"]
    iface = s["interface"]
    dir_ = s.get("dir")
    ncs = s.get("ncs")
    sdio = s.get("sdio")
    mosi = s.get("mosi")
    miso = s.get("miso")
    sclk = s.get("sclk")
    motion = s.get("motion")
    v2_en = s.get("v2_en")
    data_format = s.get("data_format")

    uc_patches = []
    if ncs:
        uc_patches.append((r"(#define\s+SENSOR_NCS_PIN\s+)\([^)]+\)",
                           r"\g<1>(%s)" % ncs, "SENSOR_NCS_PIN"))
    if sclk:
        uc_patches.append((r"(#define\s+SENSOR_SCLK_PIN\s+)\([^)]+\)",
                           r"\g<1>(%s)" % sclk, "SENSOR_SCLK_PIN"))
    if sdio:
        uc_patches.append((r"(#define\s+SENSOR_SDIO_PIN\s+)\([^)]+\)",
                           r"\g<1>(%s)" % sdio, "SENSOR_SDIO_PIN"))
    if mosi:
        uc_patches.append((r"(#define\s+SENSOR_MOSI_PIN\s+)\([^)]+\)",
                           r"\g<1>(%s)" % mosi, "SENSOR_MOSI_PIN"))
    if miso:
        uc_patches.append((r"(#define\s+SENSOR_MISO_PIN\s+)\([^)]+\)",
                           r"\g<1>(%s)" % miso, "SENSOR_MISO_PIN"))
    if motion:
        uc_patches.append((r"(#define\s+SENSOR_MOTION_PIN\s+)\([^)]+\)",
                           r"\g<1>(%s)" % motion, "SENSOR_MOTION_PIN"))
    if dir_:
        uc_patches.append((r"(#define\s+SENSOR_DIR_DEFINE\s+)SENSOR_DIR_CLOCK_\d",
                           r"\g<1>SENSOR_DIR_%s" % dir_, "SENSOR_DIR_DEFINE"))
    if v2_en:
        uc_patches.append((r"(#define\s+SENSOR_2V_IN_EN\s+)(\([^)]+\))",
                           r"\g<1>%s" % v2_en, "SENSOR_2V_IN_EN"))

    ds_patches = []
    if iface in ("2w", "2w+ncs"):
        ds_patches.append((r"(SENSACN_CSR_SPI_MODE,\s+)SENSCAN_SPI_MODE_\w+",
                           r"\g<1>SENSCAN_SPI_MODE_2_WIRE", "SPI_MODE"))
        sdio_macro = "SENSOR_SDIO_PIN"
        miso_macro = "SENSOR_SDIO_PIN"
    else:
        ds_patches.append((r"(SENSACN_CSR_SPI_MODE,\s+)SENSCAN_SPI_MODE_\w+",
                           r"\g<1>SENSCAN_SPI_MODE_4_WIRE", "SPI_MODE"))
        sdio_macro = "SENSOR_MOSI_PIN"
        miso_macro = "SENSOR_MISO_PIN"

    if data_format == "8bit":
        ds_patches.append((r"(SENSACN_CSR_DATA_FORMAT,\s+)SENSCAN_DATA_FORMAT_\w+",
                           r"\g<1>SENSCAN_DATA_FORMAT_8BIT", "DATA_FORMAT"))
    elif data_format == "12bit":
        ds_patches.append((r"(SENSACN_CSR_DATA_FORMAT,\s+)SENSCAN_DATA_FORMAT_\w+",
                           r"\g<1>SENSCAN_DATA_FORMAT_12BIT", "DATA_FORMAT"))

    ds_patches.extend([
        (r"(#define\s+mSENSOR_SDIO_OUT\s+OM_GPIO0->OUTENSET\s+=\s+)\(1<<SENSOR_\w+\)",
         r"\g<1>(1<<%s)" % sdio_macro, "mSENSOR_SDIO_OUT"),
        (r"(#define\s+mSENSOR_SDIO_IN\s+OM_GPIO0->OUTENCLR\s+=\s+)\(1<<SENSOR_\w+\)",
         r"\g<1>(1<<%s)" % sdio_macro, "mSENSOR_SDIO_IN"),
        (r"(#define\s+mSENSOR_SDIO_H\s+OM_GPIO0->DATAOUTSET\s+=\s+GPIO_MASK\()SENSOR_\w+(\))",
         r"\g<1>%s\g<2>" % sdio_macro, "mSENSOR_SDIO_H"),
        (r"(#define\s+mSENSOR_SDIO_L\s+OM_GPIO0->DATAOUTCLR\s+=\s+GPIO_MASK\()SENSOR_\w+(\))",
         r"\g<1>%s\g<2>" % sdio_macro, "mSENSOR_SDIO_L"),
        (r"(#define\s+mSENSOR_SDIO\s+)\(OM_GPIO0->DATA\s+&\s+\(1<<SENSOR_\w+\)\)",
         r"\g<1>(OM_GPIO0->DATA & (1<<%s))" % miso_macro, "mSENSOR_SDIO"),
    ])

    return [
        ("projects/mouse_demo/periph/user_config.h", uc_patches),
        ("hal/driver/om6239/drv_senscan.c", ds_patches),
    ]


def _apply_sensor(board, root, tx):
    s = board["sensor"]
    iface = s["interface"]
    uc_path = root / "projects/mouse_demo/periph/user_config.h"
    ds_path = root / "hal/driver/om6239/drv_senscan.c"
    if not uc_path.is_file():
        raise PolicyError("缺少文件: %s" % uc_path)
    if not ds_path.is_file():
        raise PolicyError("缺少文件: %s" % ds_path)

    uc_text, uc_enc = _read_text_auto(uc_path)
    ds_text, ds_enc = _read_text_auto(ds_path)

    has_ncs = bool(re.search(r"#define\s+SENSOR_NCS_PIN\s", uc_text))
    has_mosi = bool(re.search(r"#define\s+SENSOR_MOSI_PIN\s", uc_text))
    has_miso = bool(re.search(r"#define\s+SENSOR_MISO_PIN\s", uc_text))
    has_sdio = bool(re.search(r"#define\s+SENSOR_SDIO_PIN\s", uc_text))

    if iface == "4w":
        if not (has_ncs and has_mosi and has_miso):
            raise PolicyError(
                "interface=4w 需要 user_config.h 已有 SENSOR_NCS/MOSI/MISO_PIN；"
                "interface 切换需人工，本策略只做同 interface 值替换")
        if has_sdio:
            raise PolicyError(
                "interface=4w 但 user_config.h 里有 SENSOR_SDIO_PIN；"
                "interface 切换需人工，本策略只做同 interface 值替换")
    elif iface == "2w+ncs":
        if not (has_ncs and has_sdio):
            raise PolicyError(
                "interface=2w+ncs 需要 user_config.h 已有 SENSOR_NCS/SDIO_PIN；"
                "interface 切换需人工，本策略只做同 interface 值替换")
        if has_mosi or has_miso:
            raise PolicyError(
                "interface=2w+ncs 但 user_config.h 里有 SENSOR_MOSI/MISO_PIN；"
                "interface 切换需人工，本策略只做同 interface 值替换")
    elif iface == "2w":
        if not has_sdio:
            raise PolicyError(
                "interface=2w 需要 user_config.h 已有 SENSOR_SDIO_PIN；"
                "interface 切换需人工，本策略只做同 interface 值替换")
        if has_ncs or has_mosi or has_miso:
            raise PolicyError(
                "interface=2w 但 user_config.h 里有 SENSOR_NCS/MOSI/MISO_PIN；"
                "interface 切换需人工，本策略只做同 interface 值替换")

    plan = _plan_sensor(board, root)
    applied = []
    for file_rel, patches in plan:
        if file_rel.endswith("user_config.h"):
            text, enc = uc_text, uc_enc
        else:
            text, enc = ds_text, ds_enc
        new_text = text
        for pattern, repl, label in patches:
            new_text, n = re.subn(pattern, repl, new_text, count=1)
            if n == 0:
                if label == "SENSOR_2V_IN_EN":
                    continue
                raise PolicyError("%s 锚点未匹配: %s" % (file_rel, label))
        if new_text != text:
            path = root / file_rel
            tx.write_text(path, new_text, encoding=enc)
            applied.append(file_rel)
    return applied


# ============ board 驱动策略：wheel ============

_WHEEL_SEL_RE = re.compile(r"^ENCODER_PINMUX_SEL_IO_(\d{2})_(\d{2})$")
_PIN_RE = re.compile(r"^P\d{2}$")


def _validate_wheel(board):
    errs = []
    w = board.get("wheel") or {}
    a = w.get("a")
    b = w.get("b")
    sel = w.get("select")

    if not a or not _PIN_RE.match(str(a)):
        errs.append("wheel.a 必须是 Pxx 格式")
    if not b or not _PIN_RE.match(str(b)):
        errs.append("wheel.b 必须是 Pxx 格式")
    if a and b and a == b:
        errs.append("wheel.a 和 wheel.b 不能相同")
    if not sel:
        errs.append("wheel.select 必填")
        return errs

    m = _WHEEL_SEL_RE.match(str(sel))
    if not m:
        errs.append("wheel.select 必须是 ENCODER_PINMUX_SEL_IO_XX_YY 格式")
        return errs

    gx, gy = "P" + m.group(1), "P" + m.group(2)
    group = {gx, gy}
    if a and b:
        if {a, b} != group:
            errs.append(
                "wheel.a/b 必须恰好是 select 组的两个脚：%r vs %r" % ({a, b}, group))
    return errs


def _plan_wheel(board, root):
    w = board["wheel"]
    a = w["a"]
    b = w["b"]
    sel = w["select"]

    uc_patches = [
        (r"(#define\s+WHEEL_A_PIN\s+)\(P\d+\)",
         r"\g<1>(%s)" % a, "WHEEL_A_PIN"),
        (r"(#define\s+WHEEL_B_PIN\s+)\(P\d+\)",
         r"\g<1>(%s)" % b, "WHEEL_B_PIN"),
        (r"(#define\s+WHEEL_IO_SELECT\s+)\w+",
         r"\g<1>%s" % sel, "WHEEL_IO_SELECT"),
    ]
    return [("projects/mouse_demo/periph/user_config.h", uc_patches)]


def _apply_wheel(board, root, tx):
    uc_path = root / "projects/mouse_demo/periph/user_config.h"
    if not uc_path.is_file():
        raise PolicyError("缺少文件: %s" % uc_path)
    text, enc = _read_text_auto(uc_path)
    plan = _plan_wheel(board, root)
    new_text = text
    for file_rel, patches in plan:
        for pattern, repl, label in patches:
            new_text, n = re.subn(pattern, repl, new_text, count=1)
            if n == 0:
                raise PolicyError("%s 锚点未匹配: %s" % (file_rel, label))
    applied = []
    if new_text != text:
        tx.write_text(uc_path, new_text, encoding=enc)
        applied.append("projects/mouse_demo/periph/user_config.h")
    return applied


# ============ board 驱动策略：switch ============

_SWITCH_PULLS = ("PU_30K", "PU_150K", "PD_150K")
_SWITCH_LEVELS = ("high", "low")


def _switch_mode_from_pull(pull):
    if pull in ("PU_30K", "PU_150K"):
        return "USER_GPIO_MODE_INPUT_PULLUP"
    if pull == "PD_150K":
        return "USER_GPIO_MODE_INPUT_PULLDOWN"
    return None


def _switch_level_from_pull(pull):
    if pull in ("PU_30K", "PU_150K"):
        return "low"
    if pull == "PD_150K":
        return "high"
    return None


def _validate_switch(board):
    errs = []
    s = board.get("switch") or {}
    mode_24g = s.get("mode_24g")
    mode_ble = s.get("mode_ble")
    pull = s.get("pull")
    active = s.get("active_level")

    if not mode_24g or not _PIN_RE.match(str(mode_24g)):
        errs.append("switch.mode_24g 必须是 Pxx 格式")
    if mode_ble is not None:
        if not _PIN_RE.match(str(mode_ble)):
            errs.append("switch.mode_ble 必须是 Pxx 或 null")
        elif mode_ble == mode_24g:
            errs.append("switch.mode_ble 不能与 mode_24g 相同")
    if pull not in _SWITCH_PULLS:
        errs.append("switch.pull 必须是 %r 之一" % (_SWITCH_PULLS,))
        return errs
    derived = _switch_level_from_pull(pull)
    if active is not None:
        if active not in _SWITCH_LEVELS:
            errs.append("switch.active_level 必须是 %r 或 null" % (_SWITCH_LEVELS,))
        elif derived and active != derived:
            errs.append(
                "switch.active_level=%r 与 pull=%r 推导的 %r 不一致"
                % (active, pull, derived))
    return errs


def _plan_switch(board, root):
    s = board["switch"]
    mode_24g = s["mode_24g"]
    mode_ble = s.get("mode_ble")
    pull = s["pull"]
    is_dual = mode_ble is not None

    mode_str = _switch_mode_from_pull(pull)
    init_str = "PIN_HIGH_LEV"

    uc = [
        (r"(#define\s+MODE_24G_PIN\s+)\(P\d+\)",
         r"\g<1>(%s)" % mode_24g, "MODE_24G_PIN"),
    ]
    if is_dual:
        uc.append((r"(#define\s+MODE_BLE_PIN\s+)\(P\d+\)",
                   r"\g<1>(%s)" % mode_ble, "MODE_BLE_PIN"))

    ucc = []
    macros = ["MODE_24G_PIN"] + (["MODE_BLE_PIN"] if is_dual else [])
    for macro in macros:
        ucc.extend([
            (r"(\{%s,\s+)USER_GPIO_MODE_\w+" % macro,
             r"\g<1>%s" % mode_str, "%s mode" % macro),
            (r"(\{%s,\s+USER_GPIO_MODE_\w+,\s+)(?:PU_\w+|PD_\w+)" % macro,
             r"\g<1>%s" % pull, "%s pull" % macro),
            (r"(\{%s,\s+USER_GPIO_MODE_\w+,\s+(?:PU_\w+|PD_\w+),\s+)PIN_\w+" % macro,
             r"\g<1>%s" % init_str, "%s level" % macro),
        ])

    return [
        ("projects/mouse_demo/periph/user_config.h", uc),
        ("projects/mouse_demo/periph/user_config.c", ucc),
    ]


def _apply_switch(board, root, tx):
    s = board["switch"]
    mode_ble = s.get("mode_ble")
    pull = s["pull"]
    active = s.get("active_level") or _switch_level_from_pull(pull)
    is_dual = mode_ble is not None

    uc_path = root / "projects/mouse_demo/periph/user_config.h"
    ucc_path = root / "projects/mouse_demo/periph/user_config.c"
    kio_path = root / "projects/mouse_demo/periph/key_io.c"
    for p in (uc_path, ucc_path, kio_path):
        if not p.is_file():
            raise PolicyError("缺少文件: %s" % p)

    uc_text, uc_enc = _read_text_auto(uc_path)
    ucc_text, ucc_enc = _read_text_auto(ucc_path)
    kio_text, _ = _read_text_auto(kio_path)

    has_ble = bool(re.search(r"#define\s+MODE_BLE_PIN\s", uc_text))
    has_24g = bool(re.search(r"#define\s+MODE_24G_PIN\s", uc_text))
    if not has_24g:
        raise PolicyError("user_config.h 缺少 MODE_24G_PIN 定义")
    if is_dual and not has_ble:
        raise PolicyError(
            "board 是双脚，但 user_config.h 无 MODE_BLE_PIN；形态切换需人工")
    if not is_dual and has_ble:
        raise PolicyError(
            "board 是单脚，但 user_config.h 有 MODE_BLE_PIN；形态切换需人工")

    expected = "1" if active == "high" else "0"
    for macro in (["MODE_24G_PIN"] + (["MODE_BLE_PIN"] if is_dual else [])):
        for m in re.finditer(r"([01])\s*==\s*gpio_read\(%s\)" % macro, kio_text):
            if m.group(1) != expected:
                raise PolicyError(
                    "key_io.c 里 %s 极性是 %s ==，与 board 推导的 %s == 不一致；"
                    "极性变更需人工同步 key_io.c" % (macro, m.group(1), expected))
        if re.search(r"if\s*\(\s*gpio_read\(%s\)\s*\)" % macro, kio_text):
            if active != "high":
                raise PolicyError(
                    "key_io.c 里 %s 是 if (gpio_read(...)) 形式（隐含高有效），"
                    "与 board 推导的 %s 不一致；极性变更需人工" % (macro, active))

    plan = _plan_switch(board, root)
    text_map = {
        "projects/mouse_demo/periph/user_config.h": (uc_text, uc_enc),
        "projects/mouse_demo/periph/user_config.c": (ucc_text, ucc_enc),
    }
    applied = []
    for file_rel, patches in plan:
        text, enc = text_map[file_rel]
        new_text = text
        for pattern, repl, label in patches:
            new_text, n = re.subn(pattern, repl, new_text, count=1)
            if n == 0:
                raise PolicyError("%s 锚点未匹配: %s" % (file_rel, label))
        if new_text != text:
            tx.write_text(root / file_rel, new_text, encoding=enc)
            applied.append(file_rel)
    return applied


# ============ board 驱动策略：led（v1） ============

_LED_LEVELS = ("high", "low")


def _detect_led_polarity(uc_text):
    """从 led_24g_off / led_bt0_off 推导当前极性。

    off=gpio_clear → 灭用 clear → 亮用 set → high
    off=gpio_set   → 灭用 set → 亮用 clear → low
    """
    for macro in ("led_24g_off", "led_bt0_off", "led_ble_off"):
        m = re.search(
            r"#define\s+%s\(\)\s+\(gpio_(set|clear)\(" % macro, uc_text)
        if m:
            return "high" if m.group(1) == "clear" else "low"
    if re.search(r"#define\s+mode_led_all_off\(\)\s+\(OM_GPIO0->DATAOUTSET", uc_text):
        return "low"
    if re.search(r"#define\s+mode_led_all_off\(\)\s+\(OM_GPIO0->DATAOUTCLR", uc_text):
        return "high"
    return None


def _led_init_level(active_level):
    """亮=set → 灭=clear → 初始化应为低电平（灭）。"""
    return "PIN_LOW_LEV" if active_level == "high" else "PIN_HIGH_LEV"


def _validate_led(board):
    errs = []
    led = board.get("led") or {}
    active = led.get("active_level")
    rgb = led.get("mode_rgb") or []

    if active not in _LED_LEVELS:
        errs.append("led.active_level 必须是 %r 之一" % (_LED_LEVELS,))
    if not isinstance(rgb, list) or len(rgb) != 3:
        errs.append("led.mode_rgb 必须是 3 元素列表（R/G/B）")
        return errs
    for i, p in enumerate(rgb):
        if not p or not _PIN_RE.match(str(p)):
            errs.append("led.mode_rgb[%d]=%r 必须是 Pxx 格式" % (i, p))
    if len(set(rgb)) != 3:
        errs.append("led.mode_rgb 三个引脚不能重复: %r" % (rgb,))
    return errs


def _plan_led(board, root):
    led = board["led"]
    rgb = led["mode_rgb"]
    active = led["active_level"]
    init = _led_init_level(active)
    r, g, b = rgb

    uc = [
        (r"(#define\s+LED_MODE_R_PIN\s+)\(P\d+\)", r"\g<1>(%s)" % r, "LED_MODE_R_PIN"),
        (r"(#define\s+LED_MODE_G_PIN\s+)\(P\d+\)", r"\g<1>(%s)" % g, "LED_MODE_G_PIN"),
        (r"(#define\s+LED_MODE_B_PIN\s+)\(P\d+\)", r"\g<1>(%s)" % b, "LED_MODE_B_PIN"),
    ]
    ucc = []
    for macro in ("LED_MODE_R_PIN", "LED_MODE_G_PIN", "LED_MODE_B_PIN"):
        ucc.append((
            r"(\{%s,\s+USER_GPIO_MODE_\w+,\s+\w+,\s+)PIN_\w+" % macro,
            r"\g<1>%s" % init,
            "%s init" % macro,
        ))
    return [
        ("projects/mouse_demo/periph/user_config.h", uc),
        ("projects/mouse_demo/periph/user_config.c", ucc),
    ]


def _apply_led(board, root, tx):
    uc_path = root / "projects/mouse_demo/periph/user_config.h"
    ucc_path = root / "projects/mouse_demo/periph/user_config.c"
    for p in (uc_path, ucc_path):
        if not p.is_file():
            raise PolicyError("缺少文件: %s" % p)

    uc_text, uc_enc = _read_text_auto(uc_path)
    ucc_text, ucc_enc = _read_text_auto(ucc_path)

    current = _detect_led_polarity(uc_text)
    want = board["led"]["active_level"]
    if current is None:
        raise PolicyError(
            "无法从 user_config.h 推导当前 LED 极性（led_24g_off / mode_led_all_off 均未找到）")
    if current != want:
        raise PolicyError(
            "LED 极性从 %s 改为 %s 需人工（涉及 led_*_on/off、mode_led_all_off/on 及调用点）"
            % (current, want))

    plan = _plan_led(board, root)
    text_map = {
        "projects/mouse_demo/periph/user_config.h": (uc_text, uc_enc),
        "projects/mouse_demo/periph/user_config.c": (ucc_text, ucc_enc),
    }
    applied = []
    for file_rel, patches in plan:
        text, enc = text_map[file_rel]
        new_text = text
        for pattern, repl, label in patches:
            new_text, n = re.subn(pattern, repl, new_text, count=1)
            if n == 0:
                raise PolicyError("%s 锚点未匹配: %s" % (file_rel, label))
        if new_text != text:
            tx.write_text(root / file_rel, new_text, encoding=enc)
            applied.append(file_rel)
    return applied


# ============ board 驱动策略：power（v1） ============


def _validate_power(board):
    errs = []
    p = board.get("power") or {}
    usb = p.get("usb_5v")
    bat = p.get("bat_chg")
    lvd = p.get("lvd")

    if not usb or not _PIN_RE.match(str(usb)):
        errs.append("power.usb_5v 必须是 Pxx 格式")
    if bat is not None:
        if not _PIN_RE.match(str(bat)):
            errs.append("power.bat_chg 必须是 Pxx 或 null")
    if not lvd or not _PIN_RE.match(str(lvd)):
        errs.append("power.lvd 必须是 Pxx 格式")

    pins = [x for x in (usb, bat, lvd) if x]
    if len(pins) != len(set(pins)):
        errs.append("power 的 usb_5v/bat_chg/lvd 不能重复: %r" % (pins,))
    return errs


def _plan_power(board, root):
    p = board["power"]
    usb = p["usb_5v"]
    bat = p.get("bat_chg")
    lvd = p["lvd"]

    patches = [
        (r"(#define\s+USB_5V\s+)\(P\d+\)",
         r"\g<1>(%s)" % usb, "USB_5V"),
        (r"(#define\s+LVD_PIN\s+)\(P\d+\)",
         r"\g<1>(%s)" % lvd, "LVD_PIN"),
        (r"(\(POF_LVD_PIN_)P\d{2}(\))",
         r"\g<1>%s\g<2>" % lvd, "LVD_CHECK_INDEX"),
    ]
    if bat is not None:
        patches.insert(1, (r"(#define\s+BAT_CHG_PIN\s+)\(P\d+\)",
                           r"\g<1>(%s)" % bat, "BAT_CHG_PIN"))
    return [("projects/mouse_demo/periph/user_config.h", patches)]


def _apply_power(board, root, tx):
    uc_path = root / "projects/mouse_demo/periph/user_config.h"
    if not uc_path.is_file():
        raise PolicyError("缺少文件: %s" % uc_path)
    text, enc = _read_text_auto(uc_path)

    bat_board = board["power"].get("bat_chg")
    bat_file = bool(re.search(r"#define\s+BAT_CHG_PIN\s+\(P\d+\)", text))
    if bat_board is None and bat_file:
        raise PolicyError(
            "board.power.bat_chg=null 但文件有 BAT_CHG_PIN；删宏需同步 lvd.c，需人工")
    if bat_board is not None and not bat_file:
        raise PolicyError(
            "board.power.bat_chg 有值但文件无 BAT_CHG_PIN；加宏需同步 lvd.c，需人工")

    plan = _plan_power(board, root)
    new_text = text
    for file_rel, patches in plan:
        for pattern, repl, label in patches:
            new_text, n = re.subn(pattern, repl, new_text, count=1)
            if n == 0:
                raise PolicyError("%s 锚点未匹配: %s" % (file_rel, label))
    applied = []
    if new_text != text:
        tx.write_text(uc_path, new_text, encoding=enc)
        applied.append("projects/mouse_demo/periph/user_config.h")
    return applied


# ============ board 驱动策略：keys（v1） ============


def _validate_keys(board):
    """校验 board['keys']，返回错误列表（空=通过）。

    活跃键定义：user_config.h 里 #define 存在的 KEY_*_PIN（不含被注释的）。
    数量一致性：board 声明的键集合必须与文件活跃键集合完全相等（名字+数量）。
    例：495/512/516 现状——文件活跃 {R0,R1,R2,B,P,DPI} 6 个，board 必须声明同样 6 个；
        524 现状——文件活跃 {R0,R1,R2,C0} 4 个，board 声明 {r0,r1,r2} 3 个会因
        C0 未声明而拒绝（v1 不支持 C0）。
    """
    errs = []
    k = board.get("keys") or {}
    r0 = k.get("r0")
    r1 = k.get("r1")
    r2 = k.get("r2")
    b = k.get("b")
    p = k.get("p")
    dpi = k.get("dpi")

    for name, val in [("r0", r0), ("r1", r1), ("r2", r2)]:
        if not val or not _PIN_RE.match(str(val)):
            errs.append("keys.%s 必须是 Pxx 格式" % name)

    opt = [b, p, dpi]
    n_opt = sum(1 for x in opt if x)
    if 0 < n_opt < 3:
        errs.append("keys.b/p/dpi 必须全有或全无（当前 %d/3）" % n_opt)
    for name, val in [("b", b), ("p", p), ("dpi", dpi)]:
        if val is not None and not _PIN_RE.match(str(val)):
            errs.append("keys.%s 必须是 Pxx 或 null" % name)

    pins = [x for x in (r0, r1, r2, b, p, dpi) if x]
    if len(pins) != len(set(pins)):
        errs.append("keys 的引脚不能重复: %r" % (pins,))

    if k.get("c0"):
        errs.append("keys.c0 v1 不支持（524 特殊形态，OUTPUT_PP 飞线设计），需人工")
    if k.get("pair"):
        errs.append("keys.pair v1 不支持（条件编译），需人工")

    return errs


def _plan_keys(board, root):
    """返回 [(file_rel, [(pattern, repl, label), ...]), ...]。

    v1 只改 user_config.h 的 KEY_*_PIN (Pxx) 值；gpio_config_table[] 不动——
    因为该表第一字段是宏名（KEY_R0_PIN 等），宏值变了表自动跟随。
    """
    k = board["keys"]
    patches = []
    for name in ("r0", "r1", "r2", "b", "p", "dpi"):
        pin = k.get(name)
        if not pin:
            continue
        macro = "KEY_%s_PIN" % name.upper()
        patches.append((
            r"(#define\s+%s\s+)\(P\d+\)" % macro,
            r"\g<1>(%s)" % pin,
            macro,
        ))
    return [("projects/mouse_demo/periph/user_config.h", patches)]


def _apply_keys(board, root, tx):
    uc_path = root / "projects/mouse_demo/periph/user_config.h"
    ucc_path = root / "projects/mouse_demo/periph/user_config.c"
    for p in (uc_path, ucc_path):
        if not p.is_file():
            raise PolicyError("缺少文件: %s" % p)

    uc_text, uc_enc = _read_text_auto(uc_path)
    ucc_text, _ = _read_text_auto(ucc_path)

    # 文件活跃键集合（#define 存在，未被 // 注释）
    active_macros = set()
    for m in re.finditer(r"^\s*#define\s+(KEY_\w+_PIN)\s+\(P\d+\)", uc_text, re.M):
        active_macros.add(m.group(1))

    # board 声明的键集合
    k = board["keys"]
    want_macros = set()
    for name in ("r0", "r1", "r2", "b", "p", "dpi"):
        if k.get(name):
            want_macros.add("KEY_%s_PIN" % name.upper())

    # 数量+名字一致性：board 集合 == 文件集合
    missing = want_macros - active_macros
    extra = active_macros - want_macros
    if missing:
        raise PolicyError(
            "board 声明但文件无定义的键: %r；v1 不做增删行，需人工" % (sorted(missing),))
    if extra:
        raise PolicyError(
            "文件有定义但 board 未声明的键: %r；v1 不做增删行，"
            "若为 KEY_C0_PIN 或 KEY_PAIR_PIN 属 v1 不支持范围，需人工" % (sorted(extra),))

    # 语义等价：gpio_config_table[] 里每个 KEY 行第一字段必须是宏名（不是数字）
    for macro in sorted(active_macros):
        pat = r"\{%s,\s+USER_GPIO_MODE_\w+" % macro
        if not re.search(pat, ucc_text):
            raise PolicyError(
                "gpio_config_table[] 缺少 %s 行（第一字段应为宏名）；"
                "表结构不完整，需人工" % macro)

    plan = _plan_keys(board, root)
    applied = []
    for file_rel, patches in plan:
        text = uc_text
        new_text = text
        for pattern, repl, label in patches:
            new_text, n = re.subn(pattern, repl, new_text, count=1)
            if n == 0:
                raise PolicyError("%s 锚点未匹配: %s" % (file_rel, label))
        if new_text != text:
            tx.write_text(uc_path, new_text, encoding=uc_enc)
            applied.append("projects/mouse_demo/periph/user_config.h")
    return applied


def _apply_board_policy(pdef, board, root, tx):
    """board_patch kind 的分发。"""
    if pdef.id == "project_id":
        return _apply_project_id(board, root, tx)
    if pdef.id == "sensor":
        return _apply_sensor(board, root, tx)
    if pdef.id == "wheel":
        return _apply_wheel(board, root, tx)
    if pdef.id == "switch":
        return _apply_switch(board, root, tx)
    if pdef.id == "led":
        return _apply_led(board, root, tx)
    if pdef.id == "power":
        return _apply_power(board, root, tx)
    if pdef.id == "keys":
        return _apply_keys(board, root, tx)
    raise PolicyError("未知 board_patch 策略: %s" % pdef.id)


def apply_policies(sdk_root, board, selected_ids, operation="apply_policies"):
    """自助餐执行引擎：按 selected_ids 依次执行策略，全部写入一个 FileTransaction。"""
    root = sdk.resolve_sdk(sdk_root)
    tx = FileTransaction.create(root, operation)
    results = []
    for pid in selected_ids:
        pdef = policy.get_policy(pid)
        if pdef is None:
            results.append({"id": pid, "ok": False, "error": "未知策略"})
            continue
        try:
            if pdef.kind == "board_patch":
                if pdef.id == "project_id":
                    errs = _validate_project_id(board)
                elif pdef.id == "sensor":
                    errs = _validate_sensor(board)
                elif pdef.id == "wheel":
                    errs = _validate_wheel(board)
                elif pdef.id == "switch":
                    errs = _validate_switch(board)
                elif pdef.id == "led":
                    errs = _validate_led(board)
                elif pdef.id == "power":
                    errs = _validate_power(board)
                elif pdef.id == "keys":
                    errs = _validate_keys(board)
                else:
                    errs = []
                if errs:
                    results.append({"id": pid, "ok": False, "errors": errs})
                    continue
                applied = _apply_board_policy(pdef, board, root, tx)
                results.append({"id": pid, "ok": True, "applied": applied})
            elif pdef.kind == "biz_sync":
                feat = _feat_from_sdk(root)
                out = biz_sync.sync_board_contracts(
                    str(root / sdk.PERIPH), feat, str(tx.backup_root))
                results.append({"id": pid, "ok": True, "biz_sync": out})
            else:
                results.append({"id": pid, "ok": False,
                                "error": "kind=%s 尚未实现" % pdef.kind})
        except Exception as e:
            results.append({"id": pid, "ok": False, "error": repr(e)})
    manifest = tx.commit()
    return {"ok": True, "results": results, "manifest": str(manifest)}
