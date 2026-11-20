"""固件版本号：生成写盘时 +1，.omcfg / user_config.h / startup 三处同步。

真相源是 project.omcfg 的 project.id.version；user_config.h 的 iREAL_VERSION_ID
由 generator 按 config 生成；startup 的 .long 0x040002NN 低字节 = 版本号（静态文件，
由 version 模块精确改写）。映射关系核对自 S205/KC536 原件。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omcfg import model
from omcfg.api import Api
from omcfg.version import STARTUP_REL

UC_REL = "projects/mouse_demo/periph/user_config.h"


def _new_draft(tmp_path: Path, name: str = "Ver") -> Path:
    sdk_root = tmp_path / name
    api = Api()
    assert api.blank_new(name, str(sdk_root), version=1, id_low=0x0601)["ok"]
    assert api.blank_fill_recommended(str(sdk_root))["ok"]
    return sdk_root


def _uc_version(root: Path) -> str:
    text = (root / UC_REL).read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.strip().startswith("#define iREAL_VERSION_ID"))
    return line.split()[2]


def _startup_version(root: Path) -> str:
    text = (root / STARTUP_REL).read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if "0x040002" in l)
    return line.strip().split()[1]  # 0x040002NN


def test_initial_state_before_apply(tmp_path):
    """新建工程：配置版本=1，startup 初始 0x04000201（基线骨架已同步）。"""
    root = _new_draft(tmp_path)
    cfg = model.load_config(model.default_config_path(root))
    assert model.project_id(cfg)["version"] == "1"
    assert _startup_version(root) == "0x04000201"


def test_apply_bumps_all_three(tmp_path):
    root = _new_draft(tmp_path)
    result = Api().blank_apply(str(root))
    assert result["ok"], result
    assert result["version"] == 2
    cfg = model.load_config(model.default_config_path(root))
    assert model.project_id(cfg)["version"] == "2"
    assert _uc_version(root) == "2"
    assert _startup_version(root) == "0x04000202"


def test_repeated_apply_keeps_incrementing(tmp_path):
    root = _new_draft(tmp_path)
    for expected in (2, 3, 4):
        r = Api().blank_apply(str(root))
        assert r["ok"] and r["version"] == expected
        assert _uc_version(root) == str(expected)
        assert _startup_version(root) == f"0x040002{expected:02X}"


def test_apply_then_rollback_restores_version(tmp_path):
    """版本号写入纳入事务：回滚后 .omcfg / startup 都应回到旧值。"""
    from omcfg.transaction import rollback_manifest

    root = _new_draft(tmp_path)
    r = Api().blank_apply(str(root))
    assert r["ok"] and r.get("manifest")
    rollback_manifest(Path(r["manifest"]))
    cfg = model.load_config(model.default_config_path(root))
    assert model.project_id(cfg)["version"] == "1"
    assert _startup_version(root) == "0x04000201"


def test_startup_missing_pattern_does_not_break_apply(tmp_path):
    """启动文件缺版本字时不硬造，apply 仍能完成（.omcfg 与 user_config.h 照常同步）。"""
    root = _new_draft(tmp_path, "NoPattern")
    startup = root / STARTUP_REL
    text = startup.read_text(encoding="utf-8").replace("0x04000201", "0x00000000")
    startup.write_text(text, encoding="utf-8")
    r = Api().blank_apply(str(root))
    assert r["ok"], r
    assert _uc_version(root) == "2"
    assert "0x00000000" in startup.read_text(encoding="utf-8")


def test_version_over_range_rejected(tmp_path):
    """超出 startup 低字节容量时拒绝生成，不留半写状态。"""
    root = _new_draft(tmp_path, "Overflow")
    cfg_path = model.default_config_path(root)
    before = cfg_path.read_bytes()
    cfg = model.load_config(cfg_path)
    cfg["project"]["id"]["version"] = 255  # +1 = 256 越界
    from omcfg import version as version_mod
    from omcfg.transaction import FileTransaction

    tx = FileTransaction.create(root, "test_overflow")
    with pytest.raises(ValueError, match="1..255"):
        version_mod.bump(root, cfg, tx)
    assert cfg_path.read_bytes() == before, "越界时不得写盘"
