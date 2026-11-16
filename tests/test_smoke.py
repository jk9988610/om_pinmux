"""smoke 场景配置与验证函数（纯函数测试，不跑 end-to-end）。"""

from __future__ import annotations

from omcfg import smoke


def test_scenarios_cover_three_logo_modes():
    names = [s.name for s in smoke.SCENARIOS]
    assert names == ["TEST_CLI", "TEST_NOCTRL", "TEST_NONE"]
    ids = [s.id_low for s in smoke.SCENARIOS]
    assert len(set(ids)) == 3


def test_drop_ctrl_removes_only_ctrl_pin():
    src = "  LEDC_PIN: P34\n  LEDC_CTRL_PIN: P05\n  USB_5V: P25\n"
    out = smoke._drop_ctrl(src)
    assert "LEDC_CTRL_PIN" not in out
    assert "LEDC_PIN: P34" in out
    assert "USB_5V: P25" in out


def test_logo_none_clears_logo_section():
    src = "  logo: ledc\n  ledc_rgb_number: 6\n  LEDC_PIN: P34\n  LEDC_CTRL_PIN: P05\n  USB_5V: P25\n"
    out = smoke._logo_none(src)
    assert "logo: none" in out
    assert "ledc_rgb_number" not in out
    assert "LEDC_PIN" not in out
    assert "LEDC_CTRL_PIN" not in out
    assert "USB_5V: P25" in out


def test_check_markers_passes_for_matching_scenario(tmp_path):
    proj = tmp_path / "sdk"
    periph = proj / "projects/mouse_demo/periph"
    periph.mkdir(parents=True)
    (periph / "user_config.h").write_text("#define LEDC_PIN (P34)\n", encoding="utf-8")
    (periph / "ledc.h").write_text("#if defined(LEDC_PIN)\n#endif\n", encoding="utf-8")
    sc = smoke.Scenario(
        name="X",
        id_low="0x0001",
        modify=None,
        expect_have=["#define LEDC_PIN", "#if defined(LEDC_PIN)"],
        expect_not_have=["#define LED_R_PIN"],
    )
    assert smoke._check_markers(proj, sc) == []


def test_check_markers_reports_missing_and_unexpected(tmp_path):
    proj = tmp_path / "sdk"
    periph = proj / "projects/mouse_demo/periph"
    periph.mkdir(parents=True)
    (periph / "user_config.h").write_text("#define LED_R_PIN (P04)\n", encoding="utf-8")
    sc = smoke.Scenario(
        name="X",
        id_low="0x0001",
        modify=None,
        expect_have=["#define LEDC_PIN"],
        expect_not_have=["#define LED_R_PIN"],
    )
    problems = smoke._check_markers(proj, sc)
    assert any("缺少" in p for p in problems)
    assert any("不应有" in p for p in problems)


def test_locked_files_reports_permission_error(tmp_path, monkeypatch):
    """_locked_files：open("r+b") 抛 PermissionError 的文件应被列入。"""
    from pathlib import Path as _P

    root = tmp_path / "root"
    root.mkdir()
    (root / "ok.txt").write_text("x", encoding="utf-8")
    locked = root / "locked.txt"
    locked.write_text("x", encoding="utf-8")

    real_open = _P.open

    def fake_open(self, mode="r", *args, **kwargs):
        if self == locked and "b" in mode and ("+" in mode or "w" in mode):
            raise PermissionError("in use")
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(_P, "open", fake_open)
    result = smoke._locked_files(root)
    assert "locked.txt" in result
    assert "ok.txt" not in result


def test_rmtree_with_retry_retries_then_succeeds(tmp_path, monkeypatch):
    """_rmtree_with_retry：首次 PermissionError，第二次成功删除。"""
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("x", encoding="utf-8")

    calls = {"n": 0}
    real_rmtree = smoke.shutil.rmtree

    def fake_rmtree(path, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 2:
            raise PermissionError("busy")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(smoke.shutil, "rmtree", fake_rmtree)
    ok, locked = smoke._rmtree_with_retry(root, attempts=3, delay=0)
    assert ok is True
    assert locked == []
    assert not root.exists()
    assert calls["n"] == 2


def test_run_smoke_skip_locked_marks_skipped(tmp_path, monkeypatch):
    """run_smoke(skip_locked=True)：被锁场景记 skipped，不拖垮其余。"""
    out_dir = tmp_path / "smoke"
    out_dir.mkdir()
    sc = smoke.Scenario(name="X", id_low="0x0001", modify=None, expect_have=[], expect_not_have=[])
    (out_dir / sc.name).mkdir()

    monkeypatch.setattr(smoke, "_rmtree_with_retry", lambda p, **kw: (False, ["a.c", "b.c"]))
    monkeypatch.setattr(smoke, "_run_cli", lambda argv: 0)

    results = smoke.run_smoke(out_dir, scenarios=[sc], verbose=False, skip_locked=True)
    assert len(results) == 1
    assert results[0]["skipped"] is True
    assert results[0]["ok"] is False
    assert any("已跳过" in p for p in results[0]["problems"])


def test_run_smoke_locked_fails_without_skip_flag(tmp_path, monkeypatch):
    """run_smoke(skip_locked=False)：被锁场景仍判 FAIL，带锁定文件名。"""
    out_dir = tmp_path / "smoke"
    out_dir.mkdir()
    sc = smoke.Scenario(name="X", id_low="0x0001", modify=None, expect_have=[], expect_not_have=[])
    (out_dir / sc.name).mkdir()

    monkeypatch.setattr(smoke, "_rmtree_with_retry", lambda p, **kw: (False, ["a.c", "b.c"]))
    monkeypatch.setattr(smoke, "_run_cli", lambda argv: 0)

    results = smoke.run_smoke(out_dir, scenarios=[sc], verbose=False, skip_locked=False)
    assert len(results) == 1
    assert results[0]["skipped"] is False
    assert results[0]["ok"] is False
    assert any("无法删除" in p for p in results[0]["problems"])
    assert any("a.c" in p and "b.c" in p for p in results[0]["problems"])


def test_rmtree_precheck_locked_does_not_start_delete(tmp_path, monkeypatch):
    """_rmtree_with_retry：预检有锁时直接返回，不开始 rmtree（防残缺）。"""
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr(smoke, "_locked_files", lambda p: ["a.txt"])
    rmtree_called = {"n": 0}
    monkeypatch.setattr(smoke.shutil, "rmtree", lambda *a, **kw: rmtree_called.__setitem__("n", rmtree_called["n"] + 1))

    ok, locked = smoke._rmtree_with_retry(root, attempts=3, delay=0)
    assert ok is False
    assert locked == ["a.txt"]
    assert rmtree_called["n"] == 0, "预检有锁时不应调用 rmtree"
    assert root.is_dir(), "预检有锁时目录应完好"
