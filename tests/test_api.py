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


RAW_HEADER = "\n".join(
    [
        "//* 按键配置 */",
        "#define KEY_R0_PIN              (P34)",
        "#define UART_PIN (KEY_R0_PIN)",
        "#define iPROJECT_ID_H  0x071",
        "#define iPROJECT_ID_L  0x0023",
        "#define iREAL_VERSION_ID        5",
        '#define iCONSUMER_NAME "BYC"',
        '#define iPROJECT_NAME  "KC536"',
        "",
    ]
)

RAW_SOURCE = "\n".join(
    [
        "const user_gpio_config_t gpio_config_table[] = {",
        "    {0}",
        "};",
        "void periph_gpio_sleep_set()",
        "{",
        "}",
        "",
    ]
)


def _make_raw_sdk(tmp_path: Path, name: str = "sdk") -> Path:
    periph = tmp_path / name / "projects/mouse_demo/periph"
    periph.mkdir(parents=True)
    (periph / "user_config.h").write_text(RAW_HEADER, encoding="utf-8")
    (periph / "user_config.c").write_text(RAW_SOURCE, encoding="utf-8")
    return tmp_path / name


def test_load_uninitialized_reports_init_state(tmp_path):
    sdk_root = _make_raw_sdk(tmp_path, "SE71M_0023_KC536_V1_20260909")
    api = Api()
    result = api.load(str(sdk_root))
    assert result["ok"] is False
    assert result["needs_init"] is True
    assert any("project.omcfg" in item for item in result["missing"])
    assert any("标记块" in item for item in result["missing"])
    assert result["suggested"].endswith("KC536.omcfg")
    assert {item["name"] for item in result["configs"]} >= {"KC536", "CH04"}


def test_api_initialize_then_reopen_is_clean(tmp_path):
    sdk_root = _make_raw_sdk(tmp_path)
    api = Api()
    assert api.load(str(sdk_root))["needs_init"] is True
    initialized = api.initialize(str(sdk_root), str(CONFIGS / "KC536.omcfg"))
    assert initialized["ok"] is True
    assert initialized["message"].startswith("初始化完成")
    assert api.load(str(sdk_root))["ok"] is True
    assert "needs_init" not in api.load(str(sdk_root))
    assert (sdk_root / "projects/mouse_demo/project.omcfg").is_file()
    header = (sdk_root / "projects/mouse_demo/periph/user_config.h").read_text(encoding="utf-8")
    assert "/* OMCFG BEGIN pins */" in header
    assert "/* USER CODE BEGIN user_config_h */" in header

    again = api.initialize(str(sdk_root), str(CONFIGS / "KC536.omcfg"))
    assert again["ok"] is True
    assert any(item["role"] == "KEY_R0_PIN" for item in again["pins"])


def test_api_initialize_half_marker_is_actionable(tmp_path):
    sdk_root = _make_raw_sdk(tmp_path)
    header_path = sdk_root / "projects/mouse_demo/periph/user_config.h"
    header_path.write_text(
        RAW_HEADER + "/* OMCFG BEGIN pins */\n",
        encoding="utf-8",
    )
    api = Api()
    assert api.load(str(sdk_root))["needs_init"] is True
    result = api.initialize(str(sdk_root), str(CONFIGS / "KC536.omcfg"))
    assert result["ok"] is False
    assert result["needs_init"] is True
    assert "只出现一半" in result["error"]
    assert "人工修掉" in result["hint"]
    assert header_path.read_text(encoding="utf-8") == RAW_HEADER + "/* OMCFG BEGIN pins */\n"


def test_api_initialize_invalid_config_does_not_write(tmp_path):
    sdk_root = _make_raw_sdk(tmp_path)
    config = model.load_config(CONFIGS / "KC536.omcfg")
    config["pins"]["KEY_R0_PIN"] = "P99"
    bad_config = tmp_path / "bad.omcfg"
    bad_config.write_text(model.dump_config(config), encoding="utf-8")
    result = Api().initialize(str(sdk_root), str(bad_config))
    assert result["ok"] is False
    assert result["needs_init"] is True
    assert "配置校验未通过" in result["error"]
    assert not (sdk_root / "projects/mouse_demo/project.omcfg").exists()


def test_preview_uninitialized_returns_init_hint(tmp_path):
    sdk_root = _make_raw_sdk(tmp_path)
    result = Api().preview(str(sdk_root))
    assert result["needs_init"] is True
    assert "初始化" in result["hint"]


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
