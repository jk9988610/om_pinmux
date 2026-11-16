import pytest

from omcfg.targets import sdk
from omcfg.transaction import FileTransaction, rollback_manifest


def test_gbk_crlf_block_roundtrip(tmp_path):
    path = tmp_path / "user_config.c"
    original = (
        "/* 中文注释 */\r\n/* OMCFG BEGIN gpio_table */\r\nold\r\n/* OMCFG END gpio_table */\r\ntail\r\n"
    ).encode("gbk")
    path.write_bytes(original)
    source = sdk.read_source(path)
    assert source.encoding == "gbk"
    assert source.newline == "\r\n"
    after = sdk.replace_block(source.text, "gpio_table", "新内容\n第二行", path)
    path.write_bytes(sdk.SourceFile(path, after, source.encoding, source.newline, source.bom).render())
    raw = path.read_bytes()
    assert raw.decode("gbk").replace("\r\n", "\n").splitlines() == [
        "/* 中文注释 */",
        "/* OMCFG BEGIN gpio_table */",
        "新内容",
        "第二行",
        "/* OMCFG END gpio_table */",
        "tail",
    ]
    assert b"\n" not in raw.replace(b"\r\n", b"")


def test_missing_and_duplicate_markers(tmp_path):
    path = tmp_path / "a.h"
    path.write_text("no markers\n", encoding="utf-8")
    with pytest.raises(sdk.MissingBlockError):
        sdk.replace_block(path.read_text(encoding="utf-8"), "pins", "x", path)

    duplicate = "/* OMCFG BEGIN pins */\n/* OMCFG END pins */\n/* OMCFG BEGIN pins */\n/* OMCFG END pins */\n"
    with pytest.raises(sdk.DuplicateBlockError):
        sdk.replace_block(duplicate, "pins", "x", path)


def test_rollback_restores_exact_bytes(tmp_path):
    target = tmp_path / "sdk" / "projects" / "mouse_demo" / "periph" / "user_config.h"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"original\r\n")
    transaction = FileTransaction.create(tmp_path / "sdk", "test")
    transaction.write_text(target, "changed\n")
    manifest = transaction.commit()
    assert target.read_bytes() == b"changed\r\n"
    rollback_manifest(manifest)
    assert target.read_bytes() == b"original\r\n"


def test_rollback_removes_created_file(tmp_path):
    target = tmp_path / "sdk" / "features.h"
    target.parent.mkdir(parents=True)
    transaction = FileTransaction.create(tmp_path / "sdk", "test")
    transaction.write_bytes(target, b"new\n")
    manifest = transaction.commit()
    assert target.is_file()
    rollback_manifest(manifest)
    assert not target.exists()
