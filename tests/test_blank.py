"""空白起步（CubeMX 式）流程测试：纯数据操作 + CLI 端到端。"""

import pytest

from omcfg import blank, cli, model


def test_empty_config_has_no_pins():
    cfg = blank.empty_config("T")
    assert cfg["project"]["name"] == "T"
    assert cfg["pins"] == {}
    assert cfg["board"]["mode_pins"] == "single"
    assert len(blank.missing_roles(cfg)) >= 24
    assert not blank.is_complete(cfg)


def test_options_cover_all_required_roles():
    opts = blank.load_options()
    assert len(opts) >= 59
    cfg = blank.empty_config("T")
    for role in blank.missing_roles(cfg):
        assert role in opts, f"必需角色 {role} 不在 options.json"
        assert opts[role].get("suggested_pin"), f"必需角色 {role} 无推荐脚"


def test_assign_and_unassign():
    cfg = blank.empty_config("T")
    blank.assign(cfg, "KEY_R0_PIN", "P10")
    assert cfg["pins"]["KEY_R0_PIN"] == "P10"
    blank.unassign(cfg, "KEY_R0_PIN")
    assert "KEY_R0_PIN" not in cfg["pins"]


def test_assign_rejects_illegal_pin():
    cfg = blank.empty_config("T")
    # P14 是片内 Flash 保留脚，不能给普通按键
    with pytest.raises(ValueError):
        blank.assign(cfg, "KEY_R0_PIN", "P14")
    assert "KEY_R0_PIN" not in cfg["pins"]


def test_assign_rejects_duplicate_pin():
    cfg = blank.empty_config("T")
    blank.assign(cfg, "KEY_R0_PIN", "P10")
    with pytest.raises(ValueError):
        blank.assign(cfg, "KEY_R1_PIN", "P10")


def test_key_io_hard_dependencies_are_required():
    cfg = blank.empty_config("T")
    required = set(blank.missing_roles(cfg))
    # 这些是 key_io.h 无条件展开的宏，不配会编译失败
    for role in ("KEY_B_PIN", "KEY_P_PIN", "KEY_DPI_PIN", "KEY_PAIR_PIN"):
        assert role in required


def test_fill_by_suggestion_becomes_complete():
    cfg = blank.empty_config("T")
    opts = blank.load_options()
    for role in blank.missing_roles(cfg):
        blank.assign(cfg, role, opts[role]["suggested_pin"])
    assert blank.is_complete(cfg)
    report = __import__("omcfg.validate", fromlist=["x"]).validate_config(cfg)
    assert not report.errors


def test_cli_blank_new_and_build(tmp_path, capsys):
    """端到端：建空白工程 → 按推荐脚补齐 → status 可生成 → build dry-run。"""
    target = tmp_path / "BlankE2E"
    assert cli.main(["blank", "new", "--name", "BlankE2E", "--target", str(target)]) == 0
    config_path = model.default_config_path(target)
    assert config_path.is_file()
    cfg = model.load_config(config_path)
    assert cfg["pins"] == {}

    opts = blank.load_options()
    for role in blank.missing_roles(cfg):
        blank.assign(cfg, role, opts[role]["suggested_pin"])
    config_path.write_text(model.dump_config(cfg) + "\n", encoding="utf-8")

    assert cli.main(["blank", "status", "--sdk", str(target)]) == 0
    capsys.readouterr()
    assert cli.main(["blank", "build", "--sdk", str(target)]) == 0
    out = capsys.readouterr().out
    assert "dry-run" in out or "一致" in out
