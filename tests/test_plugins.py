"""插件契约与勾选/取消的端到端测试（LEDC 为第一个实例）。"""

from pathlib import Path

from omcfg import model, plugins
from omcfg.api import Api


def _make_sdk(tmp_path: Path) -> str:
    sdk = str((tmp_path / "Proj").resolve())
    api = Api()
    r = api.blank_new("Proj", sdk, id_low=0x0701)
    assert r["ok"], r
    assert api.blank_fill_recommended(sdk)["status"]["complete"]
    return sdk


def test_contract_shape():
    contracts = plugins.load_contracts()
    assert "ledc" in contracts
    c = contracts["ledc"]
    assert c["require_group"] == "ledc.strip"
    assert set(c["files"]) == {"ledc.c", "ledc.h", "ledc_mode.c", "ledc_mode.h"}
    assert "LEDC_PIN" in c["roles"]
    assert c["board_effect"]["logo"] == "ledc"


def test_visible_roles_filtered_by_plugin():
    all_roles = {
        "LEDC_PIN": {}, "LEDC_CTRL_PIN": {}, "KEY_R0_PIN": {}, "LED_R_PIN": {}
    }
    cfg = model.load_config("baseline/project.omcfg")
    off = plugins.visible_roles(cfg, all_roles)
    assert "LEDC_PIN" not in off and "LEDC_CTRL_PIN" not in off
    cfg["plugins"] = ["ledc"]
    on = plugins.visible_roles(cfg, all_roles)
    assert "LEDC_PIN" in on and "LEDC_CTRL_PIN" in on


def test_enable_injects_files_and_reassigns(tmp_path):
    sdk = _make_sdk(tmp_path)
    r = plugins.enable(Path(sdk), "ledc")
    assert r["ok"], r
    periph = Path(sdk) / "projects/mouse_demo/periph"
    for name in ("ledc.c", "ledc.h", "ledc_mode.c", "ledc_mode.h"):
        assert (periph / name).is_file(), name
    cfg = model.load_config(model.default_config_path(Path(sdk)))
    assert cfg["board"]["logo"] == "ledc"
    assert plugins.is_enabled(cfg, "ledc")
    mode_b = cfg["pins"]["LED_MODE_B_PIN"]
    pin = mode_b.get("pin") if isinstance(mode_b, dict) else mode_b
    assert pin == "P36"  # 腾出 P01


def test_enable_is_idempotent(tmp_path):
    sdk = _make_sdk(tmp_path)
    assert plugins.enable(Path(sdk), "ledc")["ok"]
    again = plugins.enable(Path(sdk), "ledc")
    assert again["ok"] and again.get("already")
    assert not again.get("files", {}).get("copied")


def test_disable_cleans_up(tmp_path):
    sdk = _make_sdk(tmp_path)
    plugins.enable(Path(sdk), "ledc")
    r = plugins.disable(Path(sdk), "ledc")
    assert r["ok"], r
    periph = Path(sdk) / "projects/mouse_demo/periph"
    for name in ("ledc.c", "ledc.h", "ledc_mode.c", "ledc_mode.h"):
        assert not (periph / name).exists(), name
    cfg = model.load_config(model.default_config_path(Path(sdk)))
    assert cfg["board"]["logo"] == "rgb"
    assert not plugins.is_enabled(cfg, "ledc")
    assert "LEDC_PIN" not in cfg["pins"]


def test_unknown_plugin_rejected(tmp_path):
    sdk = _make_sdk(tmp_path)
    assert not plugins.enable(Path(sdk), "nope")["ok"]
    assert not plugins.disable(Path(sdk), "nope")["ok"]


def test_api_plugin_toggle_roundtrip(tmp_path):
    sdk = _make_sdk(tmp_path)
    api = Api()
    on = api.plugin_toggle(sdk, "ledc", True)
    assert on["ok"] and "ledc" in on["status"]["enabled"]
    assert "LEDC_PIN" in on["roles"]
    off = api.plugin_toggle(sdk, "ledc", False)
    assert off["ok"] and "ledc" not in off["status"]["enabled"]
    assert "LEDC_PIN" not in off["roles"]


def test_plugin_status_reports_state(tmp_path):
    sdk = _make_sdk(tmp_path)
    st = Api().plugin_status(sdk)
    assert st["ok"]
    ledc = next(p for p in st["plugins"] if p["id"] == "ledc")
    assert ledc["enabled"] is False
    plugins.enable(Path(sdk), "ledc")
    st2 = Api().plugin_status(sdk)
    ledc2 = next(p for p in st2["plugins"] if p["id"] == "ledc")
    assert ledc2["enabled"] is True
