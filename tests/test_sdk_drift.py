"""来源 SDK 漂移检测：一致 / 内容变化 / 文件增删 / 路径缺失。

用临时目录模拟「来源 SDK + 快照 META」，避免依赖真实 SDK 路径；
另有一条 skipif 集成用例，在有真实 SDK 时对照实际快照。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from omcfg import baseline

REAL_SDK = Path(
    os.environ.get(
        "OMCFG_REAL_SDK",
        r"E:\M_2026\0_T\software\trunk\SE71M_0023_KC536_V1_20260909",
    )
)


def _write_meta(path: Path, source: Path, digest: str, count: int) -> None:
    path.write_text(
        json.dumps(
            {
                "source_sdk": str(source),
                "source_tree_sha256": digest,
                "source_file_count": count,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@pytest.fixture
def drift_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.delenv("OMCFG_REAL_SDK", raising=False)
    source = tmp_path / "real_sdk"
    source.mkdir()
    (source / "a.c").write_text("int a;\n", encoding="utf-8")
    (source / "b.h").write_text("#define B 1\n", encoding="utf-8")
    meta_path = tmp_path / "META.json"
    monkeypatch.setattr(baseline, "META_PATH", meta_path)
    _write_meta(meta_path, source, baseline.tree_digest(source), 2)
    return source, meta_path


def test_no_drift_when_snapshot_matches(drift_env):
    assert baseline.source_sdk_problems() == []


def test_content_change_is_detected(drift_env):
    source, _ = drift_env
    (source / "a.c").write_text("int a = 1;\n", encoding="utf-8")
    problems = baseline.source_sdk_problems()
    assert any("摘要已变化" in item for item in problems), problems


def test_new_file_is_detected(drift_env):
    source, _ = drift_env
    (source / "c.c").write_text("int c;\n", encoding="utf-8")
    problems = baseline.source_sdk_problems()
    assert any("文件数已变化" in item for item in problems), problems


def test_artifacts_do_not_trigger_drift(drift_env):
    """编译产物 / .cache 索引变化不应误报。"""
    source, _ = drift_env
    (source / "out").mkdir()
    (source / "out" / "a.axf").write_bytes(b"binary")
    (source / ".cache").mkdir()
    (source / ".cache" / "index.idx").write_text("nonsense", encoding="utf-8")
    assert baseline.source_sdk_problems() == []


def test_missing_source_is_reported(tmp_path, monkeypatch):
    monkeypatch.delenv("OMCFG_REAL_SDK", raising=False)
    meta_path = tmp_path / "META.json"
    monkeypatch.setattr(baseline, "META_PATH", meta_path)
    _write_meta(meta_path, tmp_path / "not_there", "0" * 64, 1)
    problems = baseline.source_sdk_problems()
    assert any("不存在或不是目录" in item for item in problems), problems


def test_explicit_source_overrides_env(drift_env, monkeypatch):
    source, _ = drift_env
    monkeypatch.setenv("OMCFG_REAL_SDK", str(source.parent / "not_there"))
    assert baseline.source_sdk_problems(source) == []


@pytest.mark.skipif(not REAL_SDK.is_dir(), reason="无真实来源 SDK")
def test_real_sdk_matches_snapshot():
    assert baseline.source_sdk_problems(REAL_SDK) == []
