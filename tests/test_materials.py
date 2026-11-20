"""选料（物料驱动）测试：显式契约、推导、落盘、required_roles 与生成参数。

覆盖规划 P2/P3/P4：
- 目录数据驱动：新增型号只改 catalog；**v3 起目录不含统计默认值**；
- 只有用户显式选中的物料才产生角色/板型/插件副作用；
- RGB 数量是自由整数，点亮极性不属于选料（由原理图在板型步骤决定）；
- 选料写出 project.materials，推导 board/插件/角色/参数；
- S205 画像端到端：无 LEDC / 无 mode 键 / RGB 低电平 / 两线光电，生成头正确。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omcfg import blank, materials, model, validate
from omcfg.api import Api


def _new_sdk(tmp_path: Path, name: str, pid: int) -> str:
    sdk = str((tmp_path / name).resolve())
    assert Api().blank_new(name, sdk, id_low=pid)["ok"]
    return sdk


def _s205_profile():
    selected = {
        "sensor": "S205", "led_strip": "none", "charger": "4056H", "mode_key": "absent",
    }
    params = {"rgb_count": 3, "switch_segments": 3, "ble_channels": 2}
    return selected, params


def _ch04_profile():
    selected = {
        "sensor": "S203", "led_strip": "WS2812", "charger": "4056H", "mode_key": "present",
    }
    params = {"rgb_count": 6, "switch_segments": 3, "ble_channels": 2}
    return selected, params


def test_material_step_frontend_renders():
    """前端：选料步骤渲染全部物料卡，且步骤索引一致（加载真实 app.js）。"""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node 不可用，跳过前端检查")
    root = Path(__file__).resolve().parent.parent
    check = root / "scripts" / "check_material_view.js"
    proc = subprocess.run(
        [node, str(check)], cwd=root, capture_output=True, text=True,
        encoding="utf-8", timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout, proc.stdout + proc.stderr


def test_catalog_is_v3_with_all_categories_and_no_defaults():
    cat = materials.load_catalog()
    assert cat["schema"] == "om6239-material-catalog/v3"
    assert "params_default" not in cat
    ids = {c["id"] for c in cat["categories"]}
    assert {"sensor", "led_strip", "charger", "rgb", "mode_switch", "mode_key", "ble"} <= ids
    for c in cat["categories"]:
        assert "default" not in c, f"{c['id']} 不应有默认值"
    by_id = {c["id"]: c for c in cat["categories"]}
    assert by_id["sensor"]["key"] is True and by_id["sensor"]["options"]
    assert by_id["rgb"]["key"] is False and by_id["rgb"]["params"]
    p = by_id["rgb"]["params"][0]
    assert p["id"] == "rgb_count" and p["type"] == "int"
    assert "allowed" not in p  # 不再把历史取值集合当成可选范围


def test_no_statistics_defaults_leak_into_roles():
    """核心回归：什么都没选，就不能凭空多出必需角色或改板型。"""
    sel, par = materials.default_selections()
    assert sel == {} and par == {}
    sel, par, err = materials.normalize({}, {})
    assert err == [] and sel == {} and par == {}
    eff = materials.apply_effects(sel, par)
    assert eff["required_roles"] == []
    assert eff["remove_roles"] == []
    assert eff["board"] == {}
    assert "mode_key" not in eff["params"]


def test_normalize_rejects_bad_values_without_fallback():
    sel, par, err = materials.normalize(
        {"sensor": "NOPE"}, {"rgb_count": 999, "ble_channels": 7}
    )
    assert err and any("sensor" in e for e in err)
    assert any("rgb_count" in e for e in err)
    assert "sensor" not in sel  # 不再回退到任何"统计默认"
    assert "rgb_count" not in par and "ble_channels" not in par


def test_rgb_count_is_free_integer():
    """用户可填任意 1..64 整数，不受历史分布里的 1/3/5/6/7/10 限制。"""
    for n in (1, 2, 4, 8, 12, 32, 64):
        _, par, err = materials.normalize({}, {"rgb_count": n})
        assert err == [] and par["rgb_count"] == n
    for bad in (0, 65, -1):
        _, par, err = materials.normalize({}, {"rgb_count": bad})
        assert err and "rgb_count" not in par


def test_polarity_is_not_a_material_effect():
    """选料/数量都不会改点亮极性；极性由用户在板型步骤按原理图选择。"""
    sel, par, _ = materials.normalize(*_s205_profile())
    eff = materials.apply_effects(sel, par)
    assert "led_polarity" not in eff["board"]
    assert "rgb_polarity" not in eff["params"]
    assert all(p["id"] != "rgb_polarity" for c in materials.categories() for p in c.get("params", []))


def test_apply_effects_four_wire_sensor_and_ledc():
    sel, par, _ = materials.normalize(*_ch04_profile())
    eff = materials.apply_effects(sel, par)
    assert eff["board"]["sensor.bus"] == "spi_4wire"
    assert eff["board"]["logo"] == "ledc"
    assert {"SENSOR_MOSI_PIN", "SENSOR_MISO_PIN", "SENSOR_NCS_PIN"} <= set(eff["required_roles"])
    assert "LEDC_PIN" in eff["required_roles"]
    assert {"id": "ledc", "enable": True} in eff["plugin_toggles"]


def test_apply_effects_no_mode_key_removes_pair():
    sel, par, _ = materials.normalize(*_s205_profile())
    eff = materials.apply_effects(sel, par)
    assert "KEY_PAIR_PIN" in eff["remove_roles"]
    assert eff["params"]["mode_key"] is False
    assert {"id": "ledc", "enable": False} in eff["plugin_toggles"]


def test_unselected_category_does_not_touch_existing_roles(tmp_path):
    """只选传感器，不应顺带移除 KEY_PAIR 或添加 BAT_CHG。"""
    sdk = _new_sdk(tmp_path, "MatOnlySensor", 0x0610)
    api = Api()
    assert api.material_apply(sdk, {"sensor": "S205"}, {})["ok"]
    config = model.load_config(model.default_config_path(Path(sdk)))
    store = config["project"]["materials"]
    assert store["selected"] == {"sensor": "S205"}
    assert "mode_key" not in store["selected"]
    assert "charger" not in store["selected"]
    assert "KEY_PAIR_PIN" not in materials.removed_roles(config)
    assert "BAT_CHG_PIN" not in materials.required_roles(config)


def test_clear_selection_removes_effect(tmp_path):
    sdk = _new_sdk(tmp_path, "MatClear", 0x0611)
    api = Api()
    assert api.material_apply(sdk, {"charger": "4056H"}, {})["ok"]
    config = model.load_config(model.default_config_path(Path(sdk)))
    assert "BAT_CHG_PIN" in materials.required_roles(config)
    assert api.material_apply(sdk, {"charger": ""}, {})["ok"]
    config = model.load_config(model.default_config_path(Path(sdk)))
    assert materials.required_roles(config) == []


def test_material_apply_persists_and_drives_board(tmp_path):
    sdk = _new_sdk(tmp_path, "MatPersist", 0x0601)
    api = Api()
    sel, par = _s205_profile()
    r = api.material_apply(sdk, sel, par)
    assert r["ok"], r
    config = model.load_config(model.default_config_path(Path(sdk)))
    store = config["project"]["materials"]
    assert store["selected"]["sensor"] == "S205"
    assert store["params"]["rgb_count"] == 3
    b = model.board(config)
    assert b["sensor"]["bus"] == "sdio_3wire"
    assert b["ledc_rgb_number"] == 3
    assert b["switch_segments"] == 3 and b["ble_channels"] == 2
    # 极性保持 KC536 基线初值，选料没有碰它。
    assert b["led_polarity"] == "active_low"
    assert len(r.get("guarded", [])) >= 1


def test_material_apply_enables_ledc_plugin(tmp_path):
    sdk = _new_sdk(tmp_path, "MatLedu", 0x0602)
    api = Api()
    sel, par = _ch04_profile()
    r = api.material_apply(sdk, sel, par)
    assert r["ok"], r
    assert any(p["id"] == "ledc" and p["enable"] and p["ok"] for p in r["plugins"])
    periph = Path(sdk) / "projects/mouse_demo" / "periph"
    assert (periph / "ledc.c").is_file()
    assert (periph / "ledc.h").is_file()
    config = model.load_config(model.default_config_path(Path(sdk)))
    assert "ledc" in (config.get("plugins") or [])


def test_material_apply_is_idempotent(tmp_path):
    sdk = _new_sdk(tmp_path, "MatIdem", 0x0603)
    api = Api()
    sel, par = _s205_profile()
    r1 = api.material_apply(sdk, sel, par)
    r2 = api.material_apply(sdk, sel, par)
    assert r1["ok"] and r2["ok"]
    assert r2.get("changed", 1) == 0
    assert r2.get("guarded", []) == []


def test_material_drives_required_roles(tmp_path):
    sdk = _new_sdk(tmp_path, "MatReq", 0x0604)
    api = Api()
    sel, par = _ch04_profile()
    api.material_apply(sdk, sel, par)
    config = model.load_config(model.default_config_path(Path(sdk)))
    required = validate.required_roles(config)
    assert {"SENSOR_MOSI_PIN", "SENSOR_MISO_PIN", "SENSOR_NCS_PIN", "LEDC_PIN", "KEY_PAIR_PIN"} <= set(required)
    from omcfg import plugins as _plugins
    assert "LEDC_PIN" in required or "LEDC_PIN" in _plugins.contract("ledc")["required_roles"]

    sel2, par2 = _s205_profile()
    api.material_apply(sdk, sel2, par2)
    config2 = model.load_config(model.default_config_path(Path(sdk)))
    assert "KEY_PAIR_PIN" not in validate.required_roles(config2)
    assert "KEY_PAIR_PIN" not in blank.build_required_roles(Path(sdk), config2)


def test_generated_board_features_have_material_params(tmp_path):
    sdk = _new_sdk(tmp_path, "MatFeat", 0x0605)
    api = Api()
    sel, par = _s205_profile()
    api.material_apply(sdk, sel, par)
    api.blank_fill_recommended(sdk)
    assert api.blank_apply(sdk)["ok"]
    feat = (Path(sdk) / "projects/mouse_demo/periph/board_features.h").read_text(
        encoding="utf-8", errors="replace"
    )
    assert "#define BOARD_RGB_COUNT             3" in feat
    assert "#define BOARD_SWITCH_SEGMENTS       3" in feat
    assert "#define BOARD_BLE_CHANNELS          2" in feat
    assert "#define BOARD_MODE_KEY_PRESENT      0" in feat


def test_invalid_board_param_rejected_by_validate():
    config = blank.empty_config("Bad")
    config["board"]["switch_segments"] = 5
    config["board"]["ble_channels"] = 9
    report = validate.validate_config(config)
    paths = [e.path for e in report.errors]
    assert any("switch_segments" in p for p in paths)
    assert any("ble_channels" in p for p in paths)


def test_s205_profile_end_to_end_keil(tmp_path):
    """S205 画像：选料 → 配脚 → 写盘 → 生成头含低电平逻辑，Keil 0/0。"""
    api = Api()
    sdk = _new_sdk(tmp_path, "S205E2E", 0x0512)
    sel, par = _s205_profile()
    assert api.material_apply(sdk, sel, par)["ok"]
    assert api.blank_fill_recommended(sdk)["ok"]
    st = api.blank_status(sdk)
    assert st["complete"] and not st["missing"] and not st["conflicts"]
    assert api.preview(sdk)["ok"]
    assert api.blank_apply(sdk)["ok"]

    header = (Path(sdk) / "projects/mouse_demo/periph/user_config.h").read_text(
        encoding="utf-8", errors="replace"
    )
    assert "#define led_r_on()            (gpio_clear(LED_MODE_R_PIN))" in header
    assert "LEDC_RGB_NUMBER" not in header
    assert "#define WHEEL_A_PIN" in header
    assert "#define SENSOR_SDIO_PIN" in header

    uv4 = Path(r"C:\Keil_v5\UV4\UV4.exe")
    proj = Path(sdk) / "projects/mouse_demo/keil5/SE71M.uvprojx"
    if not uv4.is_file() or not proj.is_file():
        pytest.skip("未找到 Keil UV4 或工程文件")
    import subprocess

    log = tmp_path / "s205_build.log"
    subprocess.run(
        [str(uv4), "-r", str(proj), "-o", str(log)],
        capture_output=True, text=True, timeout=300, check=False,
    )
    content = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    assert "0 Error(s), 0 Warning(s)" in content, content[-1200:]
