from pathlib import Path

from operations import FileTransaction, rollback_manifest


def test_transaction_manifest_and_rollback_existing_file(tmp_path: Path):
    target = tmp_path / "sdk"
    path = target / "projects" / "mouse_demo" / "periph" / "user_config.h"
    path.parent.mkdir(parents=True)
    path.write_text("before\n", encoding="utf-8")

    transaction = FileTransaction.create(target, "pinmux", stamp="test")
    result = transaction.write_text(path, "after\n")
    manifest = transaction.commit()

    assert result.status == "changed"
    assert result.verified
    assert manifest.is_file()
    assert path.read_text(encoding="utf-8") == "after\n"

    rollback = rollback_manifest(manifest)

    assert rollback["ok"]
    assert path.read_text(encoding="utf-8") == "before\n"


def test_rollback_removes_file_created_by_transaction(tmp_path: Path):
    target = tmp_path / "sdk"
    target.mkdir()
    path = target / "generated" / "board_features.h"

    transaction = FileTransaction.create(target, "pinmux", stamp="test")
    transaction.write_text(path, "#define BOARD_LOGO_RGB 1\n")
    manifest = transaction.commit()

    assert path.is_file()
    rollback_manifest(manifest)
    assert not path.exists()
