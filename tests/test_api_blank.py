"""空白起步 GUI 链路的 API 层测试：建工程 → 草稿保存 → 填充 → 预览 → 应用。

只测数据/编排逻辑（不编译），编译验证由手工端到端完成。
"""

from pathlib import Path

from omcfg import model
from omcfg.api import Api


def test_blank_options_ready():
    result = Api().blank_options()
    assert result["ok"] is True
    assert len(result["roles"]) >= 50
    assert "mode_pins" in result["board_enums"]
    assert "logo" in result["board_enums"]
    assert "wheel" in result["board_defaults"]


def test_blank_new_creates_empty_draft(tmp_path):
    target = tmp_path / "Mouse"
    result = Api().blank_new("TestMouse", str(target), customer="ACME", version=2, id_low=0x0610)
    assert result["ok"] is True, result
    assert Path(result["sdk"]) == target
    assert result["copied"] >= 1
    config = model.load_config(model.default_config_path(target))
    assert config["pins"] == {}, "空白工程引脚表应为空"
    assert config["project"]["name"] == "TestMouse"
    assert config["project"]["customer"] == "ACME"
    assert config["project"]["id"]["low"] == "0x0610"
    assert config["project"]["id"]["version"] == 2
    # 标记块已插入（可直接 gen）
    from omcfg import initproject

    assert initproject.is_initialized(target)


def test_blank_new_rejects_existing_and_bad_name(tmp_path):
    api = Api()
    target = tmp_path / "Mouse"
    target.mkdir()
    assert api.blank_new("Mouse", str(target))["ok"] is False, "目标已存在应拒绝"
    assert api.blank_new("", str(tmp_path / "Empty"))["ok"] is False, "空名字应拒绝"
    assert api.blank_new(".hidden", str(tmp_path / "Hidden"))["ok"] is False, "点开头应拒绝"


def test_blank_save_draft_allows_incomplete(tmp_path):
    sdk = str(tmp_path / "Mouse")
    assert Api().blank_new("Mouse", sdk)["ok"]
    api = Api()
    # 草稿态单脚保存：完整性不满足也应写入成功。
    saved = api.blank_save(sdk, {"KEY_R0_PIN": "P10"})
    assert saved["ok"] is True, saved
    assert saved["changed"] == 1
    assert saved["status"]["assigned"] == 1
    assert saved["status"]["complete"] is False
    config = model.load_config(model.default_config_path(Path(sdk)))
    assert model.pin_entries(config)["KEY_R0_PIN"]["pin"] == "P10"


def test_blank_save_rejects_illegal_pin(tmp_path):
    sdk = str(tmp_path / "Mouse")
    Api().blank_new("Mouse", sdk)
    saved = Api().blank_save(sdk, {"KEY_R0_PIN": "P99"})
    assert saved["ok"] is False
    assert "P99" in (saved.get("error") or "")


def test_blank_status_progress(tmp_path):
    sdk = str(tmp_path / "Mouse")
    Api().blank_new("Mouse", sdk)
    api = Api()
    empty = api.blank_status(sdk)
    assert empty["ok"] and empty["assigned"] == 0 and not empty["complete"]
    assert len(empty["missing"]) >= 20
    api.blank_fill_recommended(sdk)
    filled = api.blank_status(sdk)
    assert filled["complete"] is True, filled
    assert filled["conflicts"] == []
    assert filled["validate_errors"] == 0


def test_blank_fill_then_apply(tmp_path):
    sdk = str(tmp_path / "Mouse")
    Api().blank_new("Mouse", sdk)
    api = Api()
    filled = api.blank_fill_recommended(sdk)
    assert filled["ok"] and filled["status"]["complete"], filled
    assert len(filled["filled"]) >= 24
    previewed = api.preview(sdk)
    assert previewed["ok"] and previewed["changed"] >= 1
    applied = api.blank_apply(sdk)
    assert applied["ok"] is True, applied
    assert applied["changed"] >= 1
    assert applied["manifest"], "应用应产生回滚 manifest"


def test_blank_apply_refuses_incomplete(tmp_path):
    sdk = str(tmp_path / "Mouse")
    Api().blank_new("Mouse", sdk)
    applied = Api().blank_apply(sdk)
    assert applied["ok"] is False
    assert "缺必需脚" in (applied.get("error") or "")


def test_blank_set_board_and_fill(tmp_path):
    sdk = str(tmp_path / "Mouse")
    Api().blank_new("Mouse", sdk)
    api = Api()
    # 改成 wired 双模式会改变必需角色集合；选项仍可写入且填充后自洽。
    changed = api.blank_set_board(sdk, {"mode_pins": "wired", "logo": "rgb"})
    assert changed["ok"] is True, changed
    assert changed["board"]["mode_pins"] == "wired"
    rejected = api.blank_set_board(sdk, {"not_an_option": "x"})
    assert rejected["ok"] is False


def test_required_roles_follow_mode_pins(tmp_path):
    """用户场景：板型选双脚后，单脚角色不能再被标成必需。

    前端「必需」标签读 blank_status().required，这里断言它随板型切换而变。
    """
    sdk = str(tmp_path / "ModeTags")
    api = Api()
    assert api.blank_new("ModeTags", sdk)["ok"]

    assert api.blank_set_board(sdk, {"mode_pins": "single"})["ok"]
    single = set(api.blank_status(sdk)["required"])
    assert "MODE_BLE_24G_PIN" in single
    assert "MODE_24G_PIN" not in single and "MODE_BLE_PIN" not in single

    assert api.blank_set_board(sdk, {"mode_pins": "dual"})["ok"]
    dual = set(api.blank_status(sdk)["required"])
    assert {"MODE_24G_PIN", "MODE_BLE_PIN"} <= dual
    assert "MODE_BLE_24G_PIN" not in dual

    assert api.blank_set_board(sdk, {"mode_pins": "wired"})["ok"]
    wired = set(api.blank_status(sdk)["required"])
    assert "MODE_WIRED_PIN" in wired
    assert "MODE_BLE_24G_PIN" not in wired and "MODE_24G_PIN" not in wired


def test_blank_fill_idempotent(tmp_path):
    sdk = str(tmp_path / "Mouse")
    Api().blank_new("Mouse", sdk)
    api = Api()
    first = api.blank_fill_recommended(sdk)
    assert first["ok"] and first["status"]["complete"]
    before = model.load_config(model.default_config_path(Path(sdk)))["pins"]
    second = api.blank_fill_recommended(sdk)
    assert second["ok"]
    after = model.load_config(model.default_config_path(Path(sdk)))["pins"]
    assert before == after, "重复填充应幂等"
