"""new 子命令：骨架复制排除、标识改写、目标拒绝。"""

from pathlib import Path

from omcfg import cli, model

CONFIGS = Path(__file__).resolve().parent.parent / "configs"

HEADER = "\n".join(
    [
        "//* 按键配置 */",
        "#define KEY_R0_PIN              (P34)",
        "#define UART_PIN (KEY_R0_PIN)",
        "#define iPROJECT_ID_H  0x071               /* 项目平台编号:OM6239 */",
        "#define iPROJECT_ID_L  0x0023               /* 项目编号 */",
        '#define iREAL_VERSION_ID        5            /* 版本编号 */',
        '#define iCONSUMER_NAME "BYC"        /* 客户名字 */',
        '#define iPROJECT_NAME  "KC536"      /* 项目名字 */',
        "",
    ]
)

SOURCE = "\n".join(
    [
        "const user_gpio_config_t gpio_config_table[] = {",
        "    {0}",
        "};",
        "",
        "void periph_gpio_sleep_set()",
        "{",
        "}",
        "",
    ]
)

MOUSE_HW = ' char mouse_name[MOUSE_NAME_MAX_LEN] =  "BT5.1Mouse";  /* 蓝牙名称 */\n'

ADV_MOUSE = "\n".join(
    [
        "void adv_name(void)",
        "{",
        '    if (device_type == iDEVICE_TYPE_BT0)',
        '        memcpy(mouse_name, "CH-04 Bt1", sizeof("CH-04 Bt1"));',
        "    else",
        '        memcpy(mouse_name, "CH-04 Bt2", sizeof("CH-04 Bt2"));',
        "}",
        "",
    ]
)


def _make_sdk(tmp_path: Path) -> Path:
    root = tmp_path / "sdk"
    periph = root / "projects/mouse_demo/periph"
    main = root / "projects/mouse_demo/main"
    periph.mkdir(parents=True)
    main.mkdir(parents=True)
    (periph / "user_config.h").write_text(HEADER, encoding="utf-8")
    (periph / "user_config.c").write_text(SOURCE, encoding="utf-8")
    (main / "mouse_hw.c").write_text(MOUSE_HW, encoding="utf-8")
    (main / "ex2_app_mouse.c").write_text(ADV_MOUSE, encoding="utf-8")

    (root / "out").mkdir()
    (root / "out" / "junk.o").write_text("obj", encoding="utf-8")
    (root / ".omcfg_bak_20260101_000000").mkdir()
    (root / ".omcfg_bak_20260101_000000" / "manifest.json").write_text("{}", encoding="utf-8")
    (root / "keil5").mkdir()
    (root / "keil5" / "old.dep").write_text("dep", encoding="utf-8")
    (root / "keil5" / "SE71M.uvoptx").write_text("opt", encoding="utf-8")
    (root / "keil5" / "SE71M.uvguix.123").write_text("gui", encoding="utf-8")
    (root / "keil5" / "SE71M.BAT").write_text("stale paths", encoding="utf-8")
    (root / "keil5" / "keep.txt").write_text("keep", encoding="utf-8")
    (root / "compile_commands.json").write_text("[]", encoding="utf-8")
    # uvprojx 直接引用的预编译输入必须保留
    (periph / "userdefined_key_20260724.o").write_text("obj", encoding="utf-8")
    return root


def _run_new(sdk_root: Path, target: Path, config: Path, *extra: str) -> int:
    return cli.main(
        ["new", "--sdk", str(sdk_root), "--target", str(target), "--config", str(config), *extra]
    )


def _config_with_identity(tmp_path: Path) -> Path:
    config = model.load_config(CONFIGS / "KC536.omcfg")
    config["project"] = {
        "name": "KC536X",
        "customer": "BYC",
        "ble_names": ["KC536X Bt1"],
        "id": {"low": "0x0101", "high": "0x071", "version": 7},
    }
    path = tmp_path / "kc536x.omcfg"
    path.write_text(model.dump_config(config), encoding="utf-8")
    return path


def test_new_copies_without_artifacts(tmp_path, capsys):
    sdk_root = _make_sdk(tmp_path)
    target = tmp_path / "new"
    code = _run_new(sdk_root, target, CONFIGS / "KC536.omcfg")
    assert code == cli.EXIT_OK
    output = capsys.readouterr().out
    assert "不复制:" in output
    assert not (target / "out").exists()
    assert not (target / "compile_commands.json").exists()
    assert not (target / "keil5" / "old.dep").exists()
    assert not (target / "keil5" / "SE71M.uvoptx").exists()
    assert not (target / "keil5" / "SE71M.uvguix.123").exists()
    assert not (target / "keil5" / "SE71M.BAT").exists()
    assert (target / "projects/mouse_demo/periph/userdefined_key_20260724.o").is_file()
    assert list(target.glob(".omcfg_bak_*")) == []
    assert (target / "keil5" / "keep.txt").is_file()
    assert (target / "projects/mouse_demo/project.omcfg").is_file()
    assert (target / "projects/mouse_demo/periph/board_features.h").is_file()


def test_new_refuses_existing_target(tmp_path, capsys):
    sdk_root = _make_sdk(tmp_path)
    target = tmp_path / "existing"
    target.mkdir()
    (target / "keep.txt").write_text("user data", encoding="utf-8")
    code = _run_new(sdk_root, target, CONFIGS / "KC536.omcfg")
    assert code == cli.EXIT_ENVIRONMENT
    stderr = capsys.readouterr().err
    assert "目标路径已存在" in stderr
    assert "不覆盖" in stderr
    assert (target / "keep.txt").read_text(encoding="utf-8") == "user data"


def test_new_rewrites_identity(tmp_path, capsys):
    sdk_root = _make_sdk(tmp_path)
    target = tmp_path / "new"
    code = _run_new(sdk_root, target, _config_with_identity(tmp_path))
    assert code == cli.EXIT_OK
    output = capsys.readouterr().out
    assert "iPROJECT_NAME" in output
    assert "iPROJECT_ID_L" in output
    assert "mouse_name" in output

    header = (target / "projects/mouse_demo/periph/user_config.h").read_text(encoding="utf-8")
    assert '"KC536X"' in header
    assert "0x0101" in header
    assert "iREAL_VERSION_ID        7" in header
    mouse = (target / "projects/mouse_demo/main/mouse_hw.c").read_text(encoding="utf-8")
    assert '"KC536X Bt1"' in mouse


def test_new_name_override_derives_ble_name(tmp_path):
    sdk_root = _make_sdk(tmp_path)
    target = tmp_path / "new"
    config = model.load_config(CONFIGS / "KC536.omcfg")
    del config["project"]["ble_names"]
    config_path = tmp_path / "named.omcfg"
    config_path.write_text(model.dump_config(config), encoding="utf-8")
    code = cli.main(
        [
            "new",
            "--sdk",
            str(sdk_root),
            "--target",
            str(target),
            "--config",
            str(config_path),
            "--name",
            "KC536Y",
        ]
    )
    assert code == cli.EXIT_OK
    config = model.load_config(target / "projects/mouse_demo/project.omcfg")
    assert model.project(config)["name"] == "KC536Y"
    assert model.ble_names(config) == ["KC536Y Bt1", "KC536Y Bt2"]
    mouse = (target / "projects/mouse_demo/main/mouse_hw.c").read_text(encoding="utf-8")
    assert '"KC536Y Bt1"' in mouse


def test_new_missing_config_exit_2(tmp_path, capsys):
    sdk_root = _make_sdk(tmp_path)
    code = _run_new(sdk_root, tmp_path / "new", tmp_path / "nope.omcfg")
    assert code == cli.EXIT_ENVIRONMENT
    assert "配置不存在" in capsys.readouterr().err
