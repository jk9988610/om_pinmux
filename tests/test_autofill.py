"""统一自动填表引擎 + 可视化入口回归。

引擎是命令行脚本与 GUI 共用的解析/执行层。重点保护：
- 类型识别（LEDC/KEY_C0 → CH04 风格，否则 S205 风格）；
- 解析忠于原工程事实（LEDC 对调、版本、极性、2.4G 灯）；
- 与已验证的 ch04_autofill/s205_autofill 脚本解析结果一致；
- Api 可视化接口（discover/parse/start/status）走通。
Keil 真编译由 scripts/*_autofill.py 端到端覆盖，这里不重复跑。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from omcfg import autofill  # noqa: E402
from omcfg.api import Api  # noqa: E402

S205_HEADER = Path(
    "E:/M_2026/512_S205/software/trunk/SE71M_0512_S205_V1_20261017"
    "/projects/mouse_demo/periph/user_config.h"
)
CH04_HEADER = Path(
    "E:/M_2026/M_2026_T/457_CH04/SE71M_0457_CH04_V4_20260829"
    "/projects/mouse_demo/periph/user_config.h"
)


@pytest.mark.parametrize("header,style", [(S205_HEADER, "S205"), (CH04_HEADER, "CH04")])
def test_engine_style_detection(header: Path, style: str) -> None:
    if not header.is_file():
        pytest.skip(f"真实工程不存在: {header}")
    req = autofill.parse(header)
    assert req["style"] == style
    assert req["pins"], "必须解析出脚位"
    assert req["id_low"] > 0


def test_ch04_ledc_swap_and_version() -> None:
    if not CH04_HEADER.is_file():
        pytest.skip("CH04 工程不存在")
    req = autofill.parse(CH04_HEADER)
    assert req["has_ledc"] and req["has_key_c0"]
    assert req["ledc_note"], "LEDC 两脚应对调"
    assert req["version"] == 4
    assert req["wheel"] == "ENCODER_PINMUX_SEL_IO_00_01"
    upd = autofill.board_updates(req)
    assert upd["logo"] == "ledc"
    assert upd["mode_pins"] == "dual"
    assert upd["sensor.dir_clock"] == 6


def test_s205_hint_only_and_24g_led() -> None:
    if not S205_HEADER.is_file():
        pytest.skip("S205 工程不存在")
    req = autofill.parse(S205_HEADER)
    assert req["led_indicator"] == "hint_only"
    assert req["mode_24g_led"] == "G"
    assert req["dir_clock"] == 9
    upd = autofill.board_updates(req)
    assert upd["logo"] == "rgb"
    assert upd["mode_24g_led"] == "G"


def test_engine_matches_verified_scripts() -> None:
    """引擎解析必须与已验证脚本逐字段一致（led_strip=none 省略等价）。"""
    import ch04_autofill as ch04
    import s205_autofill as s205

    keys = (
        "name", "id_low", "customer", "ble_name", "pins", "polarity", "mode_dual",
        "wheel", "dir_clock", "mode_24g_led", "led_indicator", "params",
    )
    for header, fn in ((S205_HEADER, s205.parse_requirements), (CH04_HEADER, ch04.parse_requirements)):
        if not header.is_file():
            continue
        old, new = fn(header), autofill.parse(header)
        for k in keys:
            assert old.get(k) == new.get(k), f"{header.name} 字段 {k} 与脚本不一致"
        for cat in ("charger", "sensor", "mode_key"):
            assert old["selections"].get(cat) == new["selections"].get(cat)


def test_api_discover_parse_and_background_run(tmp_path: Path) -> None:
    if not CH04_HEADER.is_file():
        pytest.skip("CH04 工程不存在")
    api = Api()
    d = api.autofill_discover(str(CH04_HEADER.parents[4]))
    assert d["ok"] and d["count"] >= 1
    item = next(p for p in d["projects"] if p["header"] == str(CH04_HEADER))
    assert not item.get("error")
    assert item["style"] == "CH04"

    pr = api.autofill_parse(item["header"])
    assert pr["ok"] and pr["req"]["pin_count"] >= 20

    started = api.autofill_start(item["header"], str(tmp_path), name="AutoTest", keil=False)
    assert started["ok"]
    deadline = time.time() + 90
    while True:
        st = api.autofill_status()
        if not st["running"]:
            break
        assert time.time() < deadline, "填表任务超时"
        time.sleep(0.5)
    res = st["result"] or {}
    assert res.get("ok"), res
    assert (tmp_path / "AutoTest" / "projects/mouse_demo/keil5/SE71M.uvprojx").is_file()
    assert st["lines"], "应产生实时日志"


def test_visual_entry_wired() -> None:
    """启动页有自动填表入口，且前端逻辑/样式存在。"""
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    js = (ROOT / "web/app.js").read_text(encoding="utf-8")
    css = (ROOT / "web/style.css").read_text(encoding="utf-8")
    assert "id=\"path-autofill\"" in html and "onclick=\"openAutofill()\"" in html
    assert "id=\"af-log\"" in html and "id=\"af-projects\"" in html
    for fn in ("openAutofill", "afScan", "afSelect", "afStart", "afPoll"):
        assert f"function {fn}(" in js
    assert ".af-wrap" in css


def test_frontend_js_syntax() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node 不可用")
    proc = subprocess.run(
        [node, "--check", str(ROOT / "web/app.js")],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
