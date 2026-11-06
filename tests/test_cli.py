from pathlib import Path

from omcfg import cli, model

CONFIGS = Path(__file__).resolve().parent.parent / "configs"

HEADER_WITH_MARKERS = "\n".join(
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
        "tail",
        "",
    ]
)

SOURCE_WITH_MARKERS = "\n".join(
    [
        "const user_gpio_config_t gpio_config_table[] = {",
        "/* OMCFG BEGIN gpio_table */",
        "old",
        "/* OMCFG END gpio_table */",
        "};",
        "",
    ]
)


def _make_sdk(tmp_path: Path, with_markers: bool = True) -> Path:
    periph = tmp_path / "sdk" / "projects" / "mouse_demo" / "periph"
    periph.mkdir(parents=True)
    header = HEADER_WITH_MARKERS if with_markers else "head\ntail\n"
    source = SOURCE_WITH_MARKERS if with_markers else "table\ntail\n"
    (periph / "user_config.h").write_text(header, encoding="utf-8")
    (periph / "user_config.c").write_text(source, encoding="utf-8")
    return tmp_path / "sdk"


def test_gen_apply_and_idempotent(tmp_path, capsys):
    sdk_root = _make_sdk(tmp_path)
    assert (
        cli.main(
            ["gen", "--config", str(CONFIGS / "KC536.omcfg"), "--sdk", str(sdk_root), "--apply"]
        )
        == 0
    )
    header = (sdk_root / "projects/mouse_demo/periph/user_config.h").read_text(encoding="utf-8")
    assert "#define KEY_R0_PIN" in header
    assert "iPROJECT_ID_L" in header
    assert (
        cli.main(
            ["gen", "--config", str(CONFIGS / "KC536.omcfg"), "--sdk", str(sdk_root), "--dry-run"]
        )
        == 0
    )
    assert "生成结果与 SDK 现状一致" in capsys.readouterr().out


def test_missing_markers_exit_2(tmp_path, capsys):
    sdk_root = _make_sdk(tmp_path, with_markers=False)
    code = cli.main(
        ["gen", "--config", str(CONFIGS / "KC536.omcfg"), "--sdk", str(sdk_root), "--apply"]
    )
    assert code == cli.EXIT_ENVIRONMENT
    assert "缺少 OMCFG 标记块" in capsys.readouterr().err


def test_bad_config_exit_1(tmp_path, capsys):
    config = model.load_config(CONFIGS / "KC536.omcfg")
    config["pins"]["LED_R_PIN"] = "P34"
    bad = tmp_path / "bad.omcfg"
    bad.write_text(model.dump_config(config), encoding="utf-8")
    assert cli.main(["check", str(bad)]) == cli.EXIT_VALIDATION
    assert "重复分配" in capsys.readouterr().out


def test_init_inserts_markers_and_is_idempotent(tmp_path, capsys):
    sdk_root = tmp_path / "sdk"
    periph = sdk_root / "projects" / "mouse_demo" / "periph"
    periph.mkdir(parents=True)
    (periph / "user_config.h").write_text(
        "//* 按键配置 */\n#define KEY_R0_PIN              (P34)\n#define UART_PIN (KEY_R0_PIN)\n"
        "#define iPROJECT_ID_H  0x071\n#define iPROJECT_ID_L  0x0023\n"
        '#define iREAL_VERSION_ID 5\n#define iCONSUMER_NAME "BYC"\n'
        '#define iPROJECT_NAME  "KC536"\n',
        encoding="utf-8",
    )
    (periph / "user_config.c").write_text(
        "const user_gpio_config_t gpio_config_table[] = {\n    old\n};\n", encoding="utf-8"
    )
    args = ["init", "--config", str(CONFIGS / "KC536.omcfg"), "--sdk", str(sdk_root)]
    assert cli.main(args) == 0
    assert cli.main(args) == 0
    assert cli.main(["gen", "--sdk", str(sdk_root), "--dry-run"]) == 0


def test_rollback_command(tmp_path):
    sdk_root = _make_sdk(tmp_path)
    assert (
        cli.main(
            ["gen", "--config", str(CONFIGS / "BD319.omcfg"), "--sdk", str(sdk_root), "--apply"]
        )
        == 0
    )
    manifest = next((sdk_root).glob(".omcfg_bak_*/manifest.json"))
    assert cli.main(["rollback", "--manifest", str(manifest)]) == 0
    assert "old" in (sdk_root / "projects/mouse_demo/periph/user_config.h").read_text(
        encoding="utf-8"
    )
