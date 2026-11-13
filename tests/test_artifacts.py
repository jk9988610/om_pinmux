"""artifacts 排除规则：基线摘要忽略编译产物。"""

from __future__ import annotations

import json

from omcfg import artifacts, baseline


def test_is_artifact_matches_known_products():
    assert artifacts.is_artifact("out")
    assert artifacts.is_artifact("SE71M.axf")
    assert artifacts.is_artifact("SE71M.uvguix.123mc")
    assert artifacts.is_artifact(".omcfg_bak_20260101_000000")
    assert not artifacts.is_artifact("userdefined_key_20260724.o")
    assert not artifacts.is_artifact("user_config.h")


def test_is_artifact_path_ignores_nested_dirs():
    assert artifacts.is_artifact_path("projects/x/out/a.o")
    assert artifacts.is_artifact_path("_build/x.dis")
    assert artifacts.is_artifact_path("keil5/SE71M.uvoptx")
    assert not artifacts.is_artifact_path("projects/x/periph/ledc.c")


def test_tree_digest_ignores_artifacts(tmp_path):
    (tmp_path / "a.c").write_text("src", encoding="utf-8")
    clean = baseline.tree_digest(tmp_path)
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "a.o").write_text("obj", encoding="utf-8")
    (tmp_path / "SE71M.axf").write_text("bin", encoding="utf-8")
    (tmp_path / "SE71M.uvguix.123").write_text("gui", encoding="utf-8")
    assert baseline.tree_digest(tmp_path) == clean


def test_verify_meta_ignores_artifacts(tmp_path):
    sdk = tmp_path / "sdk"
    periph = sdk / "projects/mouse_demo/periph"
    periph.mkdir(parents=True)
    (periph / "user_config.h").write_text("h", encoding="utf-8")
    (periph / "user_config.c").write_text("c", encoding="utf-8")
    keil = sdk / "projects/mouse_demo/keil5"
    keil.mkdir(parents=True)
    (keil / "SE71M.uvprojx").write_text("p", encoding="utf-8")
    config = tmp_path / "project.omcfg"
    config.write_text("schema: x\n", encoding="utf-8")
    meta_path = tmp_path / "META.json"
    meta_path.write_text(
        json.dumps(
            {
                "file_count": 3,
                "tree_sha256": baseline.tree_digest(sdk),
                "config_sha256": baseline.file_digest(config),
            }
        ),
        encoding="utf-8",
    )
    assert baseline.verify_meta(sdk, config, meta_path) == []
    # 加产物后仍为空
    (sdk / "out").mkdir()
    (sdk / "out" / "x.o").write_text("o", encoding="utf-8")
    (sdk / "SE71M.axf").write_text("bin", encoding="utf-8")
    assert baseline.verify_meta(sdk, config, meta_path) == []
