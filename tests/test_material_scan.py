"""P1 tests for the material-driven scanning pipeline.

Verifies the acceptance cases from docs/PLAN-MATERIAL-DRIVEN.md section 4.5,
using the real E:/M_2026 + E:/history data when available and synthetic
fixtures for the parser unit tests so CI without those roots still passes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

M2026 = Path("E:/M_2026")
HISTORY = Path("E:/history")


def test_pcbdoc_extract_known_models():
    """The extractor must recover known models from both calibration PcbDocs."""
    from pcbdoc_bom import validate_against_known

    cases = [
        (M2026 / "516_BM2017/description/BYKC_BM2017_OM6239_V0.PcbDoc", "516_BM2017"),
        (M2026 / "524_LJ-V08/description/BYKC_LJ_V08_OM6238_V0.PcbDoc", "524_LJ-V08"),
    ]
    for path, project in cases:
        if not path.is_file():
            pytest.skip(f"缺少校准文件 {path}")
        result = validate_against_known(path, project)
        assert result["ok"], f"{project} 型号提取缺失 {result['missing']}"


def test_pcbdoc_designator_model_pairing():
    """U2 must pair with 4056H, not with the previous/next designator."""
    from pcbdoc_bom import extract_bom

    path = M2026 / "516_BM2017/description/BYKC_BM2017_OM6239_V0.PcbDoc"
    if not path.is_file():
        pytest.skip(f"缺少校准文件 {path}")
    bom = extract_bom(path)
    assert bom.get("U2") == "4056H"
    assert any("3528 ARGB" == v for v in bom.values())


def test_source_scan_s205_facts():
    """S205: no LEDC, no pair key, RGB P04/P05/P06 active-low, encoder P24/P25."""
    from source_scan import scan_build

    build = M2026 / "512_S205/software/trunk/SE71M_0512_S205_V1_20261017"
    if not build.is_dir():
        pytest.skip(f"缺少 S205 工程 {build}")
    r = scan_build(build)

    assert r["ledc"]["enabled"] is False
    assert r["mode"]["pair_key"] is None
    assert r["pins"]["LED_R_PIN"] == "P04"
    assert r["pins"]["LED_G_PIN"] == "P05"
    assert r["pins"]["LED_B_PIN"] == "P06"
    assert all(p == "active_low" for p in r["polarity"].values())
    assert r["encoder"]["WHEEL_A_PIN"] == "P24"
    assert r["encoder"]["WHEEL_B_PIN"] == "P25"


def test_source_scan_ch04_facts():
    """CH04: LEDC enabled (6 RGB), pair key P24, active-high RGB."""
    from source_scan import scan_build

    build = HISTORY / "457_CH04/software/SE71M_0457_CH04_V4_20260829"
    if not build.is_dir():
        pytest.skip(f"缺少 CH04 工程 {build}")
    r = scan_build(build)

    assert r["ledc"]["enabled"] is True
    assert r["ledc"]["rgb_count"] == 6
    assert r["mode"]["pair_key"] == "P24"
    assert all(p == "active_high" for p in r["polarity"].values())


def test_source_scan_parse_defines_active_vs_commented():
    """Commented-out #define must be marked inactive (used for KEY_PAIR_PIN)."""
    from source_scan import parse_defines

    build = M2026 / "512_S205/software/trunk/SE71M_0512_S205_V1_20261017"
    uc = build / "projects/mouse_demo/periph/user_config.h"
    if not uc.is_file():
        pytest.skip(f"缺少 {uc}")
    macros = parse_defines(uc)
    assert "KEY_PAIR_PIN" in macros
    assert macros["KEY_PAIR_PIN"][1] is False  # commented out
    assert macros["KEY_R0_PIN"][1] is True


def test_scan_pipeline_outputs():
    """校验已提交的扫描产物有效（秒级）。

    真实全盘重扫（约 134s）已隔离到 test_scan_pipeline_rescan，由 opt-in 开关控制，
    不再在每次回归里重扫 E:/M_2026 + E:/history。产物是仓库内真相源，
    重扫属于数据更新操作，单独按需执行。
    """
    out = Path(__file__).resolve().parent.parent
    catalog = json.loads((out / "omcfg/data/material_scan.json").read_text(encoding="utf-8"))
    assert catalog["schema"] == "om6239-material-catalog/v1"
    assert len(catalog["materials"]) >= 3
    assert "params_default" in catalog
    assert catalog["params_default"]["rgb_polarity_default"] in ("active_low", "active_high")

    projects = json.loads((out / "omcfg/data/project_scan.json").read_text(encoding="utf-8"))
    assert len(projects["projects"]) >= 20
    assert sum(1 for r in projects["projects"] if r.get("bom")) >= 5

    stats = (out / "docs/MATERIAL-STATS.md").read_text(encoding="utf-8")
    assert "项目时间线" in stats and "关键参数分布" in stats
    assert "S205" in stats  # known deviation note


@pytest.mark.skipif(
    os.environ.get("OMCFG_RESCAN") != "1",
    reason="全盘重扫约 134s，设 OMCFG_RESCAN=1 时执行（数据更新用，非日常回归）",
)
def test_scan_pipeline_rescan():
    """真·全盘重扫并刷新产物：仅数据更新时手动跑，不进日常回归。"""
    from scan_projects import run

    if not M2026.is_dir() or not HISTORY.is_dir():
        pytest.skip("缺少 E:/M_2026 或 E:/history")
    out = Path(__file__).resolve().parent.parent
    result = run([str(M2026), str(HISTORY)], out)
    assert result["projects"] >= 20
    assert result["with_bom"] >= 5


def test_generated_catalog_sensor_contracts():
    """Sensor material contracts must map 4-wire models to SPI roles."""
    catalog_path = Path(__file__).resolve().parent.parent / "omcfg/data/material_scan.json"
    if not catalog_path.is_file():
        pytest.skip("未生成 material_scan.json")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    sensor_contracts = {
        k: v for k, v in catalog["materials"].items()
        if v.get("category") == "sensor"
    }
    assert sensor_contracts, "目录里应至少有一个传感器型号契约"
    for _model, contract in sensor_contracts.items():
        assert "SENSOR_SDIO_PIN" in contract["roles"]
        if contract["wire"] == 4:
            assert "SENSOR_SCLK_PIN" in contract["roles"]
            assert "SENSOR_NCS_PIN" in contract["roles"]


def test_scripts_are_syntax_valid():
    """All P1 scripts must be importable (catch syntax errors early)."""
    for name in ("pcbdoc_bom.py", "source_scan.py", "scan_projects.py"):
        path = SCRIPTS / name
        assert path.is_file(), f"缺少脚本 {name}"
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"{name} 编译失败: {proc.stderr}"
