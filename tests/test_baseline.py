"""内置基线：名称校验、ID 派生、配置生成、清单一致性。"""

from pathlib import Path

import pytest

from omcfg import baseline, model

CONFIGS = Path(__file__).resolve().parent.parent / "configs"


def test_name_problem():
    assert baseline.name_problem("") == "工程名不能为空"
    assert baseline.name_problem("KC536X") is None
    assert "过长" in baseline.name_problem("X" * (baseline.MAX_NAME_LENGTH + 1))
    assert "不能包含" in baseline.name_problem("a/b")
    assert "不能包含" in baseline.name_problem('a"b')
    assert "点开头" in baseline.name_problem(".hidden")


def test_derive_id_is_stable_and_nonzero():
    first = baseline.derive_id("MyMouse")
    assert first == baseline.derive_id("MyMouse")
    assert first.startswith("0x")
    assert int(first, 16) != 0
    assert first != baseline.derive_id("OtherMouse")


def test_config_for_name_sets_identity(tmp_path):
    config_path = tmp_path / "base.omcfg"
    config_path.write_bytes((CONFIGS / "CH04.omcfg").read_bytes())
    config = baseline.config_for_name("MyMouse", config_path)
    project = model.project(config)
    assert project["name"] == "MyMouse"
    assert model.ble_names(config) == ["MyMouse Bt1", "MyMouse Bt2"]
    assert model.project_id(config) == {
        "low": baseline.derive_id("MyMouse"),
        "high": "0x071",
        "version": "1",
    }


def test_builtin_baseline_matches_meta():
    problems = baseline.verify_meta()
    assert problems == []


def test_builtin_baseline_is_complete():
    assert baseline.check() == []
    assert (baseline.SDK_DIR / "LICENSE.md").is_file()
    assert (baseline.SDK_DIR / "projects/mouse_demo/keil5/SE71M.uvprojx").is_file()


@pytest.mark.parametrize("relative", ["userdefined_key_20260724.o", "rf_protocol_20260704.o"])
def test_builtin_prerequisites_present(relative):
    assert list(baseline.SDK_DIR.rglob(relative))
