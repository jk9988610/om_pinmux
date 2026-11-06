from pathlib import Path

from omcfg import cli, model
from omcfg.api import Api

CONFIGS = Path(__file__).resolve().parent.parent / "configs"

HEADER = "\n".join(
    [
        "head",
        "/* OMCFG BEGIN pins */",
        "old",
        "/* OMCFG END pins */",
        "/* OMCFG BEGIN project_ids */",
        "old",
        "/* OMCFG END project_ids */",
        "/* OMCFG BEGIN project_version */",
        "old",
        "/* OMCFG END project_version */",
        "/* OMCFG BEGIN project_names */",
        "old",
        "/* OMCFG END project_names */",
        "/* USER CODE BEGIN user_config_h */",
        "/* USER CODE END user_config_h */",
        "",
    ]
)

SOURCE = "\n".join(
    [
        "const user_gpio_config_t gpio_config_table[] = {",
        "/* OMCFG BEGIN gpio_table */",
        "old",
        "/* OMCFG END gpio_table */",
        "};",
        "/* OMCFG BEGIN sleep */",
        "old",
        "/* OMCFG END sleep */",
        "/* USER CODE BEGIN user_config_c */",
        "/* USER CODE END user_config_c */",
        "",
    ]
)


def _make_sdk(tmp_path: Path) -> Path:
    periph = tmp_path / "sdk" / "projects" / "mouse_demo" / "periph"
    periph.mkdir(parents=True)
    (periph / "user_config.h").write_text(HEADER, encoding="utf-8")
    (periph / "user_config.c").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "sdk" / "projects" / "mouse_demo" / "keil5").mkdir(parents=True)
    return tmp_path / "sdk"


def test_gui_save_preview_apply(tmp_path):
    sdk_root = _make_sdk(tmp_path)
    assert (
        cli.main(["init", "--config", str(CONFIGS / "KC536.omcfg"), "--sdk", str(sdk_root)]) == 0
    )
    api = Api()
    loaded = api.load(str(sdk_root))
    assert loaded["ok"] is True
    assert any(item["role"] == "KEY_R0_PIN" for item in loaded["pins"])

    config_path = sdk_root / "projects/mouse_demo/project.omcfg"
    before = config_path.read_text(encoding="utf-8")
    saved = api.save_pins(str(sdk_root), [{"role": "KEY_R0_PIN", "pin": "P36"}])
    assert saved["ok"] is True
    assert saved["changed"] == 1
    after = config_path.read_text(encoding="utf-8")
    assert after == before.replace("KEY_R0_PIN: P34", "KEY_R0_PIN: P36")

    previewed = api.preview(str(sdk_root))
    assert previewed["ok"] is True
    assert previewed["changed"] >= 1
    assert "KEY_R0_PIN" in "\n".join(item["diff"] for item in previewed["diffs"])

    applied = api.apply(str(sdk_root))
    assert applied["ok"] is True
    assert applied["changed"] >= 1
    header = (sdk_root / "projects/mouse_demo/periph/user_config.h").read_text(encoding="utf-8")
    assert "(P36)" in header


def test_gui_rejects_invalid_pin_without_writing(tmp_path):
    sdk_root = _make_sdk(tmp_path)
    assert (
        cli.main(["init", "--config", str(CONFIGS / "KC536.omcfg"), "--sdk", str(sdk_root)]) == 0
    )
    api = Api()
    config_path = sdk_root / "projects/mouse_demo/project.omcfg"
    before = config_path.read_text(encoding="utf-8")
    result = api.save_pins(str(sdk_root), [{"role": "KEY_R0_PIN", "pin": "P99"}])
    assert result["ok"] is False
    assert "未通过校验" in result["error"]
    assert config_path.read_text(encoding="utf-8") == before
    assert model.load_config(config_path)["pins"]["KEY_R0_PIN"] == "P34"
