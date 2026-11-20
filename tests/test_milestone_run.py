"""后台测试里程碑运行器回归：配置管理 + 汇总逻辑 + 真跑一个里程碑。

不依赖 Keil；只跑最小文件组验证「超时抓取输出 / 状态跨进程共享 / 改时间删项」。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import milestone_run as mr  # noqa: E402


SCRIPT = REPO / "scripts" / "milestone_run.py"


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=REPO,
        capture_output=True, text=True, timeout=60,
    )


def test_config_structure() -> None:
    cfg = mr._load_config()
    assert cfg["version"] >= 1
    ids = [m["id"] for m in cfg["milestones"]]
    assert len(ids) == len(set(ids)), "里程碑 id 不可重复"
    # 初始约定从快到慢（note 有说明）；用户改时间后顺序可变，不强制校验。
    for m in cfg["milestones"]:
        assert m["files"] and m["expect_sec"] > 0
        for f in m["files"]:
            assert (REPO / "tests" / f).is_file(), f"测试文件不存在: {f}"


def test_set_time_remove_restore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """改时间/删项/恢复都落回配置，且不破坏其他项。"""
    import tempfile

    cfg_path = tmp_path / "milestones.json"
    original = mr._load_config()
    cfg_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(mr, "CONFIG", cfg_path)

    mr.cmd_set_time(type("A", (), {"id": "core", "sec": 99})())
    assert mr._find(mr._load_config(), "core")["expect_sec"] == 99

    mr.cmd_remove(type("A", (), {"id": "core", "hard": False})())
    assert mr._find(mr._load_config(), "core")["enabled"] is False
    assert "core" not in [m["id"] for m in mr._enabled(mr._load_config())]

    mr.cmd_restore(type("A", (), {"id": "core"})())
    assert mr._find(mr._load_config(), "core")["enabled"] is True


def test_add_duplicate_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = tmp_path / "milestones.json"
    cfg_path.write_text(json.dumps(mr._load_config(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(mr, "CONFIG", cfg_path)
    args = type("A", (), {"id": "core", "name": "重复", "sec": 10, "files": ["test_model.py"]})()
    assert mr.cmd_add(args) == 2


def test_run_single_milestone_writes_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """真跑 pytest 最小组，验证状态文件含 pass 结果与日志。"""
    tmp_state = tmp_path / "state.json"
    monkeypatch.setattr(mr, "STATE", tmp_state)
    monkeypatch.chdir(REPO)
    cfg = {
        "milestones": [{
            "id": "quick", "name": "快速组", "expect_sec": 60,
            "enabled": True, "files": ["test_model.py"],
        }]
    }
    monkeypatch.setattr(mr, "_load_config", lambda: cfg)

    mr._worker(["quick"])

    st = json.loads(tmp_state.read_text(encoding="utf-8"))
    assert st["running"] is False
    assert len(st["milestones"]) == 1
    rec = st["milestones"][0]
    assert rec["status"] == "pass", rec
    assert rec["summary"], "应给出通过摘要"
    assert rec["lines"], "应保留 pytest 输出行"


def test_timeout_captures_partial_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """超时项标记 timeout 且保留已产生输出，不阻断后续里程碑。"""
    tmp_state = tmp_path / "state.json"
    monkeypatch.setattr(mr, "STATE", tmp_state)
    monkeypatch.chdir(REPO)
    # expect_sec=0 让第一项立即超时；第二项正常跑完 —— 验证不阻断。
    cfg = {
        "milestones": [
            {"id": "instant_timeout", "name": "立即超时", "expect_sec": 0,
             "enabled": True, "files": ["test_model.py"]},
            {"id": "after", "name": "后续项", "expect_sec": 60,
             "enabled": True, "files": ["test_model.py"]},
        ]
    }
    monkeypatch.setattr(mr, "_load_config", lambda: cfg)

    mr._worker(["instant_timeout", "after"])

    st = json.loads(tmp_state.read_text(encoding="utf-8"))
    assert len(st["milestones"]) == 2
    assert st["milestones"][0]["status"] == "timeout"
    assert st["milestones"][1]["status"] == "pass"
    assert st["running"] is False


def test_classify_status() -> None:
    """超时/通过/失败/环境拦截分类正确，且不掩盖真实 assert 失败。"""
    assert mr._classify_status(0, False, ["....."]) == "pass"
    assert mr._classify_status(1, True, ["...."]) == "timeout"
    assert mr._classify_status(1, False, ["FAILED tests/t.py::t - AssertionError"]) == "fail"
    env = ["[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED]", "SystemExit: 1"]
    assert mr._classify_status(1, False, env) == "env-blocked"
    # 只有 SystemExit 无 safe-delete 标记（可能是代码主动退出）仍算 fail。
    assert mr._classify_status(1, False, ["SystemExit: 2"]) == "fail"


def test_parse_durations() -> None:
    """pytest --durations 输出解析成降序耗时榜单。"""
    lines = [
        "=========================== slowest durations ============================",
        "8.42s  call      tests/test_a.py::test_slow",
        "1.20s  setup     tests/test_a.py::test_slow",
        "0.31s  teardown  tests/test_b.py::test_fast",
        "",
    ]
    got = mr._parse_durations(lines)
    assert len(got) == 3
    assert got[0]["case"] == "tests/test_a.py::test_slow" and got[0]["phase"] == "call"
    assert got[0]["sec"] > got[-1]["sec"]
    assert mr._parse_durations(["no durations here"]) == []


def test_diagnose_slow() -> None:
    """慢因诊断能指出卡点、瓶颈用例与超时长。"""
    times = [{"sec": 42.0, "phase": "call", "case": "tests/x.py::test_keil_build"}]
    d = mr._diagnose_slow(times, "timeout", 30, 75, "tests/x.py::test_stuck")
    assert "超时 45.0s" in d and "test_stuck" in d and "test_keil_build" in d
    d2 = mr._diagnose_slow(times, "pass", 60, 45)
    assert "瓶颈" in d2 and "test_keil_build" in d2
    assert "进程被终止" in mr._diagnose_slow([], "timeout", 30, 40)


def test_render_progress() -> None:
    """进度快照含状态图标、进度条、超时长与卡点，纯文本可读。"""
    st = {
        "running": True, "started_at": "2026-01-01T00-00-00", "finished_at": "",
        "lines": ["▶ core 开始"],
        "milestones": [
            {
                "id": "core", "name": "核心", "status": "running", "elapsed": 75.0,
                "expect_sec": 60, "overtime": 15.0, "stuck_at": "tests/x.py::test_a",
                "slow_reason": "瓶颈 test_a", "summary": "",
            },
            {
                "id": "parity", "name": "一致性", "status": "running", "elapsed": 30.0,
                "expect_sec": 60, "overtime": 0, "stuck_at": "", "slow_reason": "", "summary": "",
            },
        ],
    }
    text = mr._render_progress(st)
    assert "里程碑 0/2 完成" in text
    assert "core" in text and "+15.0s" in text
    assert "卡点: tests/x.py::test_a" in text
    assert "█" in text and "░" in text  # parity 半程进度条双色


def test_timeout_records_overtime_and_diagnosis(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """超时项落库时带 overtime / stuck_at / slow_reason。"""
    state_path = tmp_path / "s.json"
    monkeypatch.setattr(mr, "STATE", state_path)
    monkeypatch.chdir(REPO)
    cfg = {"milestones": [{
        "id": "instant_timeout", "name": "立即超时", "expect_sec": 0,
        "enabled": True, "files": ["test_model.py"],
    }]}
    monkeypatch.setattr(mr, "_load_config", lambda: cfg)
    mr._worker(["instant_timeout"])
    rec = json.loads(state_path.read_text(encoding="utf-8"))["milestones"][0]
    assert rec["status"] == "timeout"
    assert rec["overtime"] >= 0
    assert isinstance(rec["case_times"], list)
    assert rec["slow_reason"], "超时应给出慢因诊断"


def test_cli_list_and_report_without_state() -> None:
    """CLI 基本命令在干净环境不崩（不依赖是否跑过）。"""
    r = _cli("list")
    assert r.returncode == 0 and "core" in r.stdout
    r = _cli("status", "--tail", "3")
    assert r.returncode == 0 and "状态" in r.stdout
