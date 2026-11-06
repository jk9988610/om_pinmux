from pathlib import Path

from omcfg import cli, derive, model, validate
from omcfg.api import Api
from omcfg.generate import templates

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
    saved = api.save_pinmap(str(sdk_root), {"KEY_R0_PIN": "P36"})
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
    assert result["prefill"].endswith("KC536.omcfg")
    assert result["existing_config"] == ""
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


def _make_config_sdk(tmp_path: Path, name: str, config: dict) -> Path:
    """用生成模板拼一个“没有标记块、但引脚已就绪”的 SDK，用于验证推导回环。"""
    root = tmp_path / name
    periph = root / "projects/mouse_demo/periph"
    periph.mkdir(parents=True)
    pins = model.resolved_pins(config)
    header = "\n".join(
        [
            templates.render_pins(config, pins),
            templates.render_project_ids(config),
            templates.render_project_version(config),
            templates.render_project_names(config),
            "",
        ]
    )
    table = templates.render_gpio_table(config, pins)
    sleep = templates.render_sleep(config, pins)
    (periph / "user_config.h").write_text(header, encoding="utf-8")
    (periph / "user_config.c").write_text(f"{table}\n\n{sleep}\n", encoding="utf-8")
    (periph / "sensor.c").write_text(
        "unsigned char const sensor_dpi_ini[] = {\n"
        "    1200L/200L-1,\n    1600L/200L-1,\n    2400L/200L-1,\n"
        "    3600L/200L-1,\n    4800L/200L-1,\n    6400L/200L-1,\n"
        "    0xFF,\n    0xFF,\n};\n",
        encoding="utf-8",
    )
    (periph / "sensor.h").write_text("#define DEFAULT_DPI_GRADE 1\n", encoding="utf-8")
    return root


def test_load_uninitialized_without_matching_config_leaves_prefill_empty(tmp_path):
    sdk_root = _make_raw_sdk(tmp_path, "SE71M_0525_E606_V1_20261106")
    result = Api().load(str(sdk_root))
    assert result["needs_init"] is True
    assert result["suggested"] == ""
    assert result["prefill"] == ""
    assert result["config"].endswith("projects\\mouse_demo\\project.omcfg")
    assert "从工程现状生成配置初稿" in result["hint"]


def test_initialize_target_path_gives_actionable_hint(tmp_path):
    sdk_root = _make_raw_sdk(tmp_path, "SE71M_0525_E606_V1_20261106")
    api = Api()
    target = api.load(str(sdk_root))["config"]
    result = api.initialize(str(sdk_root), target)
    assert result["ok"] is False
    assert result["needs_init"] is True
    assert "配置不存在" in result["error"]
    assert "初始化后写入" in result["hint"]
    assert not Path(target).exists()


def test_derive_roundtrip_matches_project_state(tmp_path):
    base = model.load_config(CONFIGS / "KC536.omcfg")
    sdk_root = _make_config_sdk(tmp_path, "SE71M_0023_KC536_V1", base)
    config = derive.derive_config(sdk_root)
    assert validate.validate_config(config).ok
    assert model.project_id(config) == model.project_id(base)
    assert model.resolved_pins(config) == model.resolved_pins(base)
    assert model.board(config)["wheel"] == model.board(base)["wheel"]
    assert model.sensor(config) == model.sensor(base)


def test_api_initialize_derived_installs_config(tmp_path):
    base = model.load_config(CONFIGS / "KC536.omcfg")
    sdk_root = _make_config_sdk(tmp_path, "SE71M_0525_E606_V1_20261106", base)
    api = Api()
    assert api.load(str(sdk_root))["needs_init"] is True
    result = api.initialize_derived(str(sdk_root))
    assert result["ok"] is True
    assert result["derived"]["pins"] == 28
    assert (sdk_root / "projects/mouse_demo/project.omcfg").is_file()
    header = (sdk_root / "projects/mouse_demo/periph/user_config.h").read_text(encoding="utf-8")
    assert "/* OMCFG BEGIN pins */" in header
    assert "/* OMCFG BEGIN project_names */" in header
    assert "needs_init" not in api.load(str(sdk_root))

    preview = api.preview(str(sdk_root))
    assert preview["ok"] is True
    assert [item["path"] for item in preview["diffs"]] == [
        str(sdk_root / "projects/mouse_demo/periph/board_features.h")
    ]


def test_api_initialize_derived_reports_underivable_state(tmp_path):
    sdk_root = _make_raw_sdk(tmp_path, "SE71M_0525_E606_V1_20261106")
    result = Api().initialize_derived(str(sdk_root))
    assert result["ok"] is False
    assert result["needs_init"] is True
    assert "无法从工程现状推导配置" in result["error"]
    assert "模式检测脚" in result["error"]
    assert "复制邻近板配置" in result["hint"]


def test_save_pinmap_removes_optional_role(tmp_path):
    sdk_root = _make_sdk(tmp_path)
    assert cli.main(["init", "--config", str(CONFIGS / "CH04.omcfg"), "--sdk", str(sdk_root)]) == 0
    result = Api().save_pinmap(str(sdk_root), {"KEY_C0_PIN": ""})
    assert result["ok"] is True
    config_path = sdk_root / "projects/mouse_demo/project.omcfg"
    assert "KEY_C0_PIN" not in model.load_config(config_path)["pins"]


def test_save_pinmap_is_idempotent(tmp_path):
    sdk_root = _make_sdk(tmp_path)
    assert cli.main(["init", "--config", str(CONFIGS / "CH04.omcfg"), "--sdk", str(sdk_root)]) == 0
    api = Api()
    first = api.save_pinmap(str(sdk_root), {"KEY_R0_PIN": "P10"})
    assert first["ok"] is True and first["changed"] == 1
    second = api.save_pinmap(str(sdk_root), {"KEY_R0_PIN": "P10"})
    assert second["ok"] is True
    assert second["changed"] == 0


def test_save_pinmap_rejects_unknown_role(tmp_path):
    sdk_root = _make_sdk(tmp_path)
    assert cli.main(["init", "--config", str(CONFIGS / "CH04.omcfg"), "--sdk", str(sdk_root)]) == 0
    result = Api().save_pinmap(str(sdk_root), {"NOT_A_ROLE": "P10"})
    assert result["ok"] is False
    assert "未知功能宏" in result["error"]


def test_sync_wheel_follows_encoder_pair():
    from omcfg import api as api_module

    text = (CONFIGS / "CH04.omcfg").read_text(encoding="utf-8")
    moved = text.replace("WHEEL_A_PIN: P00", "WHEEL_A_PIN: P20").replace(
        "WHEEL_B_PIN: P01", "WHEEL_B_PIN: P21"
    )
    after = api_module._sync_wheel(moved)
    assert "wheel: ENCODER_PINMUX_SEL_IO_20_21" in after
    config = model.load_config_text(after)
    assert model.board(config)["wheel"] == "ENCODER_PINMUX_SEL_IO_20_21"


def test_gui_rejects_invalid_pin_without_writing(tmp_path):
    sdk_root = _make_sdk(tmp_path)
    assert (
        cli.main(["init", "--config", str(CONFIGS / "KC536.omcfg"), "--sdk", str(sdk_root)]) == 0
    )
    api = Api()
    config_path = sdk_root / "projects/mouse_demo/project.omcfg"
    before = config_path.read_text(encoding="utf-8")
    result = api.save_pinmap(str(sdk_root), {"KEY_R0_PIN": "P99"})
    assert result["ok"] is False
    assert "未通过校验" in result["error"]
    assert config_path.read_text(encoding="utf-8") == before
    assert model.load_config(config_path)["pins"]["KEY_R0_PIN"] == "P34"
