"""finalize_ledc_sel：按 LEDC_PIN 校正 ledc.c / drv_ledc.c 的 PMU_LEDC_SEL_IO_xx。"""

from pathlib import Path

from omcfg.api import Api

MIN_CFG = (
    "schema: om6239-project/v1\n"
    "chip: OM6239\n"
    "project:\n"
    "  name: TEST\n"
    "  customer: TEST\n"
    '  ble_names: ["TEST Bt1", "TEST Bt2"]\n'
    "  id:\n"
    '    low: "0x0001"\n'
    '    high: "0x071"\n'
    "    version: 1\n"
    "board:\n"
    "  mode_pins: dual\n"
    "  logo: ledc\n"
    "  led_polarity: active_high\n"
    "  sensor:\n"
    "    bus: sdio_3wire\n"
    "    dir_clock: 6\n"
    "  wheel: ENCODER_PINMUX_SEL_IO_00_01\n"
    "pins:\n"
    "  LEDC_PIN: {ledc_pin}\n"
    "  LEDC_CTRL_PIN: P34\n"
)


def _make_workspace(tmp_path: Path, ledc_pin: str) -> Path:
    periph = tmp_path / "projects" / "mouse_demo" / "periph"
    periph.mkdir(parents=True)
    drv = tmp_path / "hal" / "driver" / "om6239"
    drv.mkdir(parents=True)
    (tmp_path / "projects" / "mouse_demo" / "project.omcfg").write_text(
        MIN_CFG.format(ledc_pin=ledc_pin), encoding="utf-8"
    )
    body = "static void init(void) {\n    drv_pmu_ledc_sel(PMU_LEDC_SEL_IO_05);\n}\n"
    (periph / "ledc.c").write_text(body, encoding="utf-8")
    (drv / "drv_ledc.c").write_text(body, encoding="utf-8")
    return tmp_path


def test_no_project_omcfg_returns_ok(tmp_path):
    r = Api().finalize_ledc_sel(str(tmp_path))
    assert r["ok"]
    assert r["changed"] == []


def test_ledc_pin_p05_no_change(tmp_path):
    ws = _make_workspace(tmp_path, "P05")
    r = Api().finalize_ledc_sel(str(ws))
    assert r["ok"]
    assert r["changed"] == []
    assert r["sel"] == "PMU_LEDC_SEL_IO_05"


def test_ledc_pin_p01_replaces_both_files(tmp_path):
    ws = _make_workspace(tmp_path, "P01")
    r = Api().finalize_ledc_sel(str(ws))
    assert r["ok"]
    assert r["sel"] == "PMU_LEDC_SEL_IO_01"
    assert "projects/mouse_demo/periph/ledc.c" in r["changed"]
    assert "hal/driver/om6239/drv_ledc.c" in r["changed"]
    assert "PMU_LEDC_SEL_IO_01" in (ws / "projects/mouse_demo/periph/ledc.c").read_text(encoding="utf-8")
    assert "PMU_LEDC_SEL_IO_01" in (ws / "hal/driver/om6239/drv_ledc.c").read_text(encoding="utf-8")


def test_ledc_pin_p21_reports_error(tmp_path):
    """P21 在 chip json 里 sdk_supported=false，finalize 应报错。"""
    ws = _make_workspace(tmp_path, "P21")
    r = Api().finalize_ledc_sel(str(ws))
    assert not r["ok"]
    assert "P21" in r["error"]
