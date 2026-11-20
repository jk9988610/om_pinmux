"""软件工程师视角：照原理图网络名逐脚配置，不用「一键推荐」。

用户画像（来自真实反馈）：硬件工程师画好原理图，网络名定死（LED_R、
SENSOR_MOSI、KEY_L、光编码器…）；软件工程师只负责把这些网络按原理图
配到指定物理脚。工具必须满足：

1. 约束栏能看到原理图上的**所有**网络，包括被 v1=false 标记的角色
   （LED_R/G/B、SENSOR_MOSI/MISO/NCS、KEY_L/M/R、H_ENCODER_A/B 等）；
   这些角色此前被前端 v1 过滤藏掉，用户根本找不到。
2. 按网络名/宏名/role_id 都能搜索定位，不必猜工具内部叫什么。
3. 不点任何「推荐配置」，仅凭原理图指定脚位也能写入工程配置。

前端的可见性/搜索由 scripts/check_constraint_view.js 用真实 app.js + 仓库内
数据源渲染验证；本文件验证后端凭原理图配脚能真正落盘、生成、通过编译。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from omcfg.api import Api

REPO = Path(__file__).resolve().parent.parent
CHECK = REPO / "scripts" / "check_constraint_view.js"
UV4 = Path(os.environ.get("OMCFG_UV4", r"C:\Keil_v5\UV4\UV4.exe"))

# 原理图网络名 -> 硬件指定的物理脚。全部取自各角色 allowed_pins，且互不冲突。
# LED_R/G/B、SENSOR_MOSI/MISO/NCS、KEY_L 都是原先被 v1=false 隐藏的角色。
SCHEMATIC = {
    "LED_R_PIN": "P04",
    "LED_G_PIN": "P05",
    "LED_B_PIN": "P06",
    "SENSOR_MOSI_PIN": "P10",
    "SENSOR_MISO_PIN": "P11",
    "SENSOR_NCS_PIN": "P12",
    "KEY_L_PIN": "P13",
    "H_ENCODER_A_PIN": "P20",
    "H_ENCODER_B_PIN": "P21",
}


def _caps_roles() -> dict:
    return Api().role_capabilities()["roles"]


def test_constraint_view_shows_all_schematic_roles() -> None:
    """界面层：约束栏全量可见、可按网络名搜索、无推荐配置导向。"""
    node = shutil.which("node")
    if not node:
        import pytest

        pytest.skip("node 不可用，跳过前端约束栏检查")
    proc = subprocess.run(
        [node, str(CHECK)],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout, proc.stdout + proc.stderr


def test_schematic_roles_are_all_visible_and_legal() -> None:
    """用户要配的这些原理图网络，必须都在能力表里且指定脚合法。"""
    roles = _caps_roles()
    for mac, pin in SCHEMATIC.items():
        assert mac in roles, f"原理图网络 {mac} 不在角色能力表里"
        allowed = roles[mac].get("allowed_pins") or []
        assert pin in allowed, f"原理图指定脚 {pin} 不是 {mac} 的合法脚；合法脚: {allowed}"


def test_apply_schematic_without_recommendation(tmp_path) -> None:
    """全程不点推荐，把原理图网络配到指定脚，草稿能落盘 omcfg。"""
    api = Api()
    name = "BySchematic"
    sdk = str((tmp_path / name).resolve())
    r = api.blank_new(name, sdk, id_low=0x0801)
    assert r["ok"], r

    # 只保存原理图指定的脚位，一次也不调用 blank_fill_recommended
    saved = api.blank_save(sdk, dict(SCHEMATIC))
    assert saved["ok"], saved
    assert saved["changed"] >= 1

    # 草稿落盘到 project.omcfg：每个网络都指向原理图指定的脚
    omcfg = Path(sdk) / "projects/mouse_demo/project.omcfg"
    cfg_text = omcfg.read_text(encoding="utf-8", errors="replace")
    for mac, pin in SCHEMATIC.items():
        assert re.search(rf"^\s*{mac}:\s*{pin}\s*$", cfg_text, re.M), (
            f"{mac} 未按原理图配到 {pin}（配置未落盘）"
        )

    # 回读状态：已分配计数应等于原理图网络数，且无脚位冲突
    st = api.blank_status(sdk)
    assert st.get("assigned") == len(SCHEMATIC), (
        f"已分配 {st.get('assigned')} 个，期望 {len(SCHEMATIC)} 个"
    )
    assert not st.get("conflicts"), f"原理图配脚产生冲突: {st.get('conflicts')}"


def test_keil_build_with_schematic_overrides(tmp_path) -> None:
    """真实场景：先有可编译基线，再按原理图把部分网络改到指定脚，仍应 0 Error。

    软件工程师不会从零手配 28 个脚；他拿一份能编译的工程，把原理图改动过的
    网络逐个改到硬件指定的脚。这里模拟这个动作：推荐方案配齐 → 用原理图脚位
    覆盖 → 生成头反映新脚位 → Keil 编译。
    """
    if not UV4.is_file():
        import pytest

        pytest.skip(f"未找到 Keil UV4: {UV4}")

    api = Api()
    name = "SchematicKeil"
    sdk = str((tmp_path / name).resolve())
    assert api.blank_new(name, sdk, id_low=0x0802)["ok"]
    # 先得到一份完整可编译基线（仅为配齐必需脚，不代表用户认可这些脚）
    assert api.blank_fill_recommended(sdk)["ok"]

    # 按原理图把 LED_R 改到空闲脚 P36（推荐方案里 P36 未占用，不冲突）。
    # 这模拟工程师在可编译基线上改一个网络：工具应据此重写生成头。
    override = {"LED_R_PIN": "P36"}
    saved = api.blank_save(sdk, override)
    assert saved["ok"], saved
    applied = api.blank_apply(sdk)
    assert applied["ok"], applied

    # 生成头必须反映原理图脚位 P36，而不是推荐脚 P04
    header = Path(sdk) / "projects/mouse_demo/periph/user_config.h"
    text = header.read_text(encoding="utf-8", errors="replace")
    assert re.search(r"#define\s+LED_R_PIN\s+\(P36\)", text), (
        "LED_R_PIN 生成头未按原理图写成 (P36)"
    )
    assert not re.search(r"#define\s+LED_R_PIN\s+\(P04\)", text), (
        "LED_R_PIN 仍停留在推荐脚 P04，覆盖未生效"
    )

    uvproj = Path(sdk) / "projects/mouse_demo/keil5/SE71M.uvprojx"
    assert uvproj.is_file(), uvproj
    log = tmp_path / "keil.log"
    proc = subprocess.run(
        [str(UV4), "-r", str(uvproj), "-o", str(log)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    if log.is_file():
        content = log.read_text(encoding="utf-8", errors="replace")
        assert "0 Error" in content or "Error" not in content, content[-800:]
