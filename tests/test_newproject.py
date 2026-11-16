"""new 子命令：内置基线、命名即建工程、骨架排除、标识改写。"""

from pathlib import Path

import pytest

from omcfg import baseline, cli, model, newproject

CONFIGS = Path(__file__).resolve().parent.parent / "configs"

HEADER = "\n".join(
    [
        "//* 按键配置 */",
        "#define KEY_R0_PIN              (P34)",
        "#define UART_PIN (KEY_R0_PIN)",
        "#define iPROJECT_ID_H  0x071               /* 项目平台编号:OM6239 */",
        "#define iPROJECT_ID_L  0x0023               /* 项目编号 */",
        "#define iREAL_VERSION_ID        5            /* 版本编号 */",
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
        "    if (device_type == iDEVICE_TYPE_BT0)",
        '        memcpy(mouse_name, "CH-04 Bt1", sizeof("CH-04 Bt1"));',
        "    else",
        '        memcpy(mouse_name, "CH-04 Bt2", sizeof("CH-04 Bt2"));',
        "}",
        "",
    ]
)


def _make_sdk(tmp_path: Path) -> Path:
    root = tmp_path / "baseline_sdk"
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
    project = root / "projects/mouse_demo/keil5"
    project.mkdir()
    (project / "SE71M.uvprojx").write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="UTF-8"?>',
                "<Project>",
                "  <Groups>",
                "    <Group>",
                "      <GroupName>periph</GroupName>",
                "      <Files>",
                "        <File>",
                "          <FileName>user_config.c</FileName>",
                "          <FileType>1</FileType>",
                "          <FilePath>..\\periph\\user_config.c</FilePath>",
                "        </File>",
                "      </Files>",
                "    </Group>",
                "  </Groups>",
                "</Project>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    # uvprojx 直接引用的预编译输入必须保留
    (periph / "userdefined_key_20260724.o").write_text("obj", encoding="utf-8")
    return root


@pytest.fixture
def fake_baseline(tmp_path, monkeypatch):
    """把模块级基线路径指到临时目录，避免每个用例复制 5 MB 真实基线。"""
    sdk_root = _make_sdk(tmp_path)
    config = tmp_path / "baseline.omcfg"
    config.write_bytes((CONFIGS / "KC536.omcfg").read_bytes())
    meta = tmp_path / "META.json"
    meta.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(baseline, "SDK_DIR", sdk_root)
    monkeypatch.setattr(baseline, "CONFIG_PATH", config)
    monkeypatch.setattr(baseline, "META_PATH", meta)
    return sdk_root


def test_new_copies_without_artifacts(fake_baseline, tmp_path, capsys):
    target = tmp_path / "new"
    code = cli.main(["new", "--name", "KC536X", "--target", str(target), "--no-keep-backup"])
    assert code == cli.EXIT_OK
    output = capsys.readouterr().out
    assert "内置基线:" in output
    assert "不复制:" in output
    assert "目录由工具生成" in output
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


def test_new_default_target_uses_name(fake_baseline, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code = cli.main(["new", "--name", "MyMouse"])
    assert code == cli.EXIT_OK
    assert (tmp_path / "MyMouse" / "projects/mouse_demo/project.omcfg").is_file()


def test_new_refuses_existing_target(fake_baseline, tmp_path, capsys):
    target = tmp_path / "existing"
    target.mkdir()
    (target / "keep.txt").write_text("user data", encoding="utf-8")
    code = cli.main(["new", "--name", "KC536X", "--target", str(target)])
    assert code == cli.EXIT_ENVIRONMENT
    stderr = capsys.readouterr().err
    assert "目标路径已存在" in stderr
    assert "不覆盖" in stderr
    assert (target / "keep.txt").read_text(encoding="utf-8") == "user data"


def test_new_rewrites_identity(fake_baseline, tmp_path, capsys):
    target = tmp_path / "new"
    code = cli.main(["new", "--name", "KC536X", "--target", str(target)])
    assert code == cli.EXIT_OK
    output = capsys.readouterr().out
    assert "iPROJECT_NAME" in output
    assert "iPROJECT_ID_L" in output
    assert "mouse_name" in output

    header = (target / "projects/mouse_demo/periph/user_config.h").read_text(encoding="utf-8")
    assert '"KC536X"' in header
    assert "iREAL_VERSION_ID        1" in header
    config = model.load_config(target / "projects/mouse_demo/project.omcfg")
    assert model.project(config)["name"] == "KC536X"
    assert model.ble_names(config) == ["KC536X Bt1", "KC536X Bt2"]
    assert model.project_id(config)["low"] == baseline.derive_id("KC536X")
    mouse = (target / "projects/mouse_demo/main/mouse_hw.c").read_text(encoding="utf-8")
    assert '"KC536X Bt1"' in mouse
    adv = (target / "projects/mouse_demo/main/ex2_app_mouse.c").read_text(encoding="utf-8")
    assert '"KC536X Bt1"' in adv
    assert '"KC536X Bt2"' in adv


def test_new_keep_backup_manifest_exists(fake_baseline, tmp_path, capsys):
    target = tmp_path / "new"
    code = cli.main(["new", "--name", "KC536X", "--target", str(target)])
    assert code == cli.EXIT_OK
    manifests = list(target.glob(".omcfg_bak_*/manifest.json"))
    assert len(manifests) == 1, f"默认应保留 1 个 manifest，实际: {manifests}"
    import json

    payload = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert payload["schema"] == "om6239-file-transaction/v1"
    paths = [entry["path"] for entry in payload["entries"]]
    assert any("mouse_hw.c" in p for p in paths), f"BLE 名改写未进事务: {paths}"
    assert any("ex2_app_mouse.c" in p for p in paths), f"BLE 广播名未进事务: {paths}"


def test_new_then_rollback_restores_ble_name(fake_baseline, tmp_path, capsys):
    from omcfg.transaction import rollback_manifest

    target = tmp_path / "new"
    code = cli.main(["new", "--name", "KC536X", "--target", str(target)])
    assert code == cli.EXIT_OK
    manifest = next(target.glob(".omcfg_bak_*/manifest.json"))
    mouse_path = target / "projects/mouse_demo/main/mouse_hw.c"
    assert "KC536X Bt1" in mouse_path.read_text(encoding="utf-8")
    rollback_manifest(manifest)
    assert "BT5.1Mouse" in mouse_path.read_text(encoding="utf-8")


def test_rewrite_identity_uses_tx(fake_baseline):
    """证明 rewrite_identity 在 tx 传入时走 tx.write_bytes，而非 path.write_bytes 直接落盘。"""
    from omcfg import model

    config = model.load_config(CONFIGS / "KC536.omcfg")

    adv_path = fake_baseline / "projects/mouse_demo/main/ex2_app_mouse.c"
    adv_before = adv_path.read_bytes()

    class FakeTx:
        def __init__(self):
            self.writes = []

        def write_bytes(self, path, data, detail="已写入事务"):
            self.writes.append(str(path))

    tx = FakeTx()
    newproject.rewrite_identity(fake_baseline, config, tx=tx)

    assert tx.writes, "rewrite_identity 必须走 tx.write_bytes"
    assert any("ex2_app_mouse.c" in p for p in tx.writes), f"应经 tx 改写 adv 名，实际写入: {tx.writes}"
    # FakeTx 不落盘；若内部绕过 tx 用 path.write_bytes 直接写，磁盘内容会变
    assert adv_path.read_bytes() == adv_before, "FakeTx 模式下磁盘不应被直接改写"


def test_new_rejects_invalid_name(fake_baseline, tmp_path, capsys):
    code = cli.main(["new", "--name", "bad\\name", "--target", str(tmp_path / "x")])
    assert code == cli.EXIT_VALIDATION
    assert "不能包含" in capsys.readouterr().err
    assert not (tmp_path / "x").exists()


def test_new_incomplete_baseline(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(baseline, "SDK_DIR", tmp_path / "missing")
    code = cli.main(["new", "--name", "KC536X", "--target", str(tmp_path / "x")])
    assert code == cli.EXIT_ENVIRONMENT
    stderr = capsys.readouterr().err
    assert "内置 SDK 基线不完整" in stderr
    assert not (tmp_path / "x").exists()


def test_copy_skeleton_keeps_required_objects(tmp_path):
    source = _make_sdk(tmp_path)
    target = tmp_path / "copy"
    copied = newproject.copy_skeleton(source, target)
    assert copied > 0
    assert (target / "projects/mouse_demo/periph/userdefined_key_20260724.o").is_file()
    assert not (target / "out").exists()
