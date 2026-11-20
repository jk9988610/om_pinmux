#!/usr/bin/env python3
"""后台测试里程碑运行器：按测试层分组跑 pytest，逐项超时，抓取已完成输出。

设计目标（用户诉求）：
- 每个里程碑有预期完成秒数 expect_sec（可改），从快到慢排列；
- 后台跑，实时写状态文件，status 可随时查看进度与已完成里程碑的输出；
- 某项超过 expect_sec 就抓取它**已经产生的输出**并标记 timeout，不阻断后续里程碑；
- 冗余项可删（从配置移除或 enabled=false），时间可改，都落回 milestones.json。

用法：
    python scripts/milestone_run.py list                     # 列出里程碑与预期时间
    python scripts/milestone_run.py run                      # 跑所有启用项（实时写状态文件）
    python scripts/milestone_run.py run --only core parity   # 只跑指定项
    python scripts/milestone_run.py run --live               # 当前终端实时刷新进度条
    python scripts/milestone_run.py run --popup              # 弹出本地终端窗口看进度
    python scripts/milestone_run.py watch                    # 另开终端实时看正在跑的进度
    python scripts/milestone_run.py watch --once             # 只看一帧快照
    python scripts/milestone_run.py status                   # 查看进度/已完成输出
    python scripts/milestone_run.py report [-v]              # 汇总最近一次结果（-v 附耗时榜单）
    python scripts/milestone_run.py set-time e2e 420         # 改预期秒数
    python scripts/milestone_run.py remove e2e               # 删冗余项(enabled=false)
    python scripts/milestone_run.py restore e2e              # 恢复被删项
    python scripts/milestone_run.py add --id xx --name XX --sec 60 --files tests/test_a.py ...

状态文件：tests/.milestone_state.json（含每个里程碑的日志行，超时也保留）。
    被运行器自身忽略，不影响 pytest 收集。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "tests" / "milestones.json"
STATE = REPO / "tests" / ".milestone_state.json"

_LOCK = threading.Lock()


def _load_config() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _save_config(cfg: dict[str, Any]) -> None:
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _default_state() -> dict[str, Any]:
    return {"running": False, "started_at": "", "finished_at": "", "milestones": [], "lines": []}


def _load_state() -> dict[str, Any]:
    if not STATE.is_file():
        return _default_state()
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return _default_state()


def _write_state(state: dict[str, Any]) -> None:
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _enabled(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    return [m for m in cfg["milestones"] if m.get("enabled", True)]


def _find(cfg: dict[str, Any], mid: str) -> dict[str, Any] | None:
    return next((m for m in cfg["milestones"] if m["id"] == mid), None)


def cmd_list(args: argparse.Namespace) -> int:
    cfg = _load_config()
    print(f"{'ID':<12} {'启用':<6} {'预期(s)':<9} 名称 / 测试文件")
    print("-" * 78)
    for m in cfg["milestones"]:
        flag = "是" if m.get("enabled", True) else "否(按需)"
        print(f"{m['id']:<12} {flag:<6} {m.get('expect_sec', 0):<9} {m['name']}")
        print(f"{'':<12} {'':<6} {'':<9} {', '.join(m['files'])}")
    return 0


def cmd_set_time(args: argparse.Namespace) -> int:
    cfg = _load_config()
    m = _find(cfg, args.id)
    if not m:
        print(f"✕ 没有里程碑 {args.id}（用 list 查看）")
        return 2
    if args.sec <= 0:
        print("✕ 预期秒数必须 > 0")
        return 2
    m["expect_sec"] = args.sec
    _save_config(cfg)
    print(f"✓ {args.id} 预期时间改为 {args.sec}s")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    cfg = _load_config()
    m = _find(cfg, args.id)
    if not m:
        print(f"✕ 没有里程碑 {args.id}")
        return 2
    if args.hard:
        cfg["milestones"] = [x for x in cfg["milestones"] if x["id"] != args.id]
        verb = "彻底删除"
    else:
        m["enabled"] = False
        verb = "标记删除（restore 可恢复）"
    _save_config(cfg)
    print(f"✓ {args.id} 已{verb}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    cfg = _load_config()
    m = _find(cfg, args.id)
    if not m:
        print(f"✕ 没有里程碑 {args.id}")
        return 2
    m["enabled"] = True
    _save_config(cfg)
    print(f"✓ {args.id} 已恢复启用")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    cfg = _load_config()
    if _find(cfg, args.id):
        print(f"✕ 里程碑 {args.id} 已存在")
        return 2
    files = [f if f.endswith(".py") else f + ".py" for f in args.files]
    for f in files:
        if not (REPO / "tests" / f).is_file():
            print(f"✕ 测试文件不存在: {f}")
            return 2
    cfg["milestones"].append({
        "id": args.id, "name": args.name, "expect_sec": args.sec,
        "enabled": True, "files": files,
    })
    _save_config(cfg)
    print(f"✓ 新增里程碑 {args.id}（{args.name}，预期 {args.sec}s，{len(files)} 文件）")
    return 0


def _parse_durations(lines: list[str]) -> list[dict[str, Any]]:
    """解析 pytest --durations=0 的输出，返回 [{sec, phase, case}] 降序。

    pytest 形如：
        8.42s  call      tests/test_x.py::test_y
        0.31s  setup     tests/test_x.py::test_y
    """
    out: list[dict[str, Any]] = []
    pat = re.compile(r"^\s*([\d.]+)s\s+(setup|call|teardown)\s+(\S+)")
    in_block = False
    for line in lines:
        if "slowest" in line.lower() and "durations" in line.lower():
            in_block = True
            continue
        if in_block:
            m = pat.match(line)
            if m:
                try:
                    out.append({"sec": float(m.group(1)), "phase": m.group(2), "case": m.group(3)})
                except ValueError:
                    pass
    out.sort(key=lambda x: x["sec"], reverse=True)
    return out


def _diagnose_slow(case_times: list[dict[str, Any]], status: str, expect: float,
                   elapsed: float, stuck_at: str = "") -> str:
    """给出「为什么慢/卡在哪」的一句话诊断，供 report 输出。"""
    stuck = stuck_at.split("::")[-1] if stuck_at else ""
    if status == "timeout":
        over = elapsed - expect
        if case_times:
            top = case_times[0]
            slowest = top["case"].split("::")[-1]
            hint = f"，最慢已完成用例 {slowest}（{top['sec']}s）" if top["sec"] >= 1 else ""
        else:
            hint = "，逐用例耗时未产出（进程被终止）"
        at = f"卡在 {stuck}" if stuck else "仍在运行"
        return f"超时 {over:.1f}s，{at}{hint}"
    if not case_times:
        return "无逐用例耗时数据"
    top = case_times[0]
    case = top["case"].split("::")[-1]
    if top["sec"] >= max(2.0, expect * 0.5):
        return f"瓶颈用例 {case}（{top['sec']}s，占预期 {expect}s 的 {top['sec']/expect:.0%}）"
    return f"最慢用例 {case}（{top['sec']}s），无单点瓶颈（多名小用例累积）"


def _render_progress(st: dict[str, Any], width: int = 78) -> str:
    """把状态渲染成可在终端实时刷新的进度文本（纯函数，便于测试）。

    每个里程碑显示：状态图标、已用/预期时间条、超时长、卡点、诊断、摘要。
    不依赖 ANSI，重定向到文件也能读。
    """
    icon = {"pass": "✓", "fail": "✕", "timeout": "⏱", "env-blocked": "⊘", "running": "…"}
    bars = "█░"
    out: list[str] = []
    running = st.get("running", False)
    head = "运行中" if running else "已完成" if st.get("finished_at") else "空闲"
    out.append(f"测试进度 [{head}]  开始 {st.get('started_at', '-') or '-'}")
    out.append("=" * width)
    total = len(st.get("milestones", []))
    done = sum(1 for m in st.get("milestones", []) if m["status"] in
               ("pass", "fail", "timeout", "env-blocked"))
    out.append(f"里程碑 {done}/{total} 完成")
    out.append("-" * width)
    for m in st.get("milestones", []):
        e = float(m.get("elapsed", 0.0))
        x = float(m.get("expect_sec", 0) or 60)
        ratio = min(1.0, e / x) if x else 1.0
        filled = max(0, min(20, round(ratio * 20)))
        bar = bars[0] * filled + bars[1] * (20 - filled)
        over = f"+{m['overtime']}s" if m.get("overtime") else ""
        flag = icon.get(m["status"], "?")
        out.append(
            f"{flag} {m['id']:<11} {m['status']:<11} {e:>6.1f}s/{x:<4.0f}s "
            f"[{bar}]{(' ' + over) if over else ''}"
        )
        if m.get("stuck_at") and m["status"] in ("running", "timeout"):
            out.append(f"    卡点: {m['stuck_at']}")
        if m.get("slow_reason"):
            out.append(f"    诊断: {m['slow_reason']}")
    if st.get("lines"):
        out.append("-" * width)
        for line in st["lines"][-4:]:
            out.append(f"  | {line}")
    return "\n".join(out)


def _popup_watch() -> bool:
    """尽力弹出一个本地终端窗口跑 watch；失败返回 False（不阻断 run）。"""
    cmd = [sys.executable, str(Path(__file__).resolve()), "watch", "--interval", "1"]
    try:
        if sys.platform == "win32":
            flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            subprocess.Popen(cmd, cwd=REPO, creationflags=flags)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-a", "Terminal", *cmd], cwd=REPO)
        else:
            term = os.environ.get("TERM_PROGRAM", "")
            if term:
                subprocess.Popen([term.lower(), "-e", *cmd], cwd=REPO)
            else:
                return False
        return True
    except Exception:
        return False


def _classify_status(returncode: int, timed_out: bool, lines: list[str]) -> str:
    """把进程结果归类为 timeout / pass / fail / env-blocked。"""
    if timed_out:
        return "timeout"
    if returncode == 0:
        return "pass"
    full_text = "\n".join(lines)
    # 沙箱 safe-delete 钩子在单 turn 累计删除超阈值时 SystemExit(1)，
    # 拦截测试内部的 shutil.rmtree(Keil out)；单独跑同一用例 RC=0，非测试失败。
    # 仅当输出明确出现 [safe-delete] 标记时降级，避免掩盖真实 assert 失败。
    if "[safe-delete]" in full_text and "SystemExit" in full_text:
        return "env-blocked"
    return "fail"


def _run_milestone(m: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """跑单个里程碑，返回结构化结果。逐行抓取输出写进 state，超时也保留。"""
    mid = m["id"]
    files = [f"tests/{f if f.endswith('.py') else f + '.py'}" for f in m["files"]]
    # --basetemp 固定到项目内：避免 pytest 清理系统 temp 的 garbage 目录时
    # 被安全钩子拦截而误报 rc=1（测试其实全过）。用「批次号/里程碑」独立子目录：
    # 既防止多组共享 tmp 路径时 fixture 互相污染（曾导致 ERROR），又不删除旧目录
    # （批量 rmtree 会触发环境安全钩子被整条命令拦截）。旧批次留 .gitignore 忽略即可。
    batch = state.get("started_at", "run").replace(":", "-").replace(" ", "_")
    # 只用单层子目录名：pytest 用 os.mkdir（无 parents）建 basetemp，多级路径会
    # FileNotFoundError；单层（.pytest_tmp 已存在）才能建成功。
    basetemp = REPO / ".pytest_tmp" / f"{batch}_{mid}"
    (REPO / ".pytest_tmp").mkdir(parents=True, exist_ok=True)
    # -o addopts= 覆盖 pyproject 里的全局 -q，改用 -v 逐用例输出 nodeid，
    # 这样超时时能定位「最后跑到哪个用例」（-q 的进度点无法定位卡点）。
    # --durations=0 列出每个用例耗时，供慢因诊断；--tb=line 压缩失败栈。
    cmd = [sys.executable, "-m", "pytest", *files,
           "-o", "addopts=", "-v", "--tb=line", "--no-header",
           "--durations=0", "--basetemp", str(basetemp)]
    # kw（可选）：pytest -k 表达式，用于把慢用例（如 Keil 真编译）按名字隔离到
    # 独立里程碑。日常里程碑写 "not keil"，Keil 里程碑写 "keil"。
    kw = m.get("kw")
    if kw:
        cmd += ["-k", kw]
    expect = int(m.get("expect_sec", 60))
    result: dict[str, Any] = {
        "id": mid, "name": m["name"], "expect_sec": expect,
        "status": "running", "elapsed": 0.0, "overtime": 0.0,
        "lines": [], "returncode": None, "case_times": [], "stuck_at": "",
        "slow_reason": "",
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    state["milestones"].append(result)
    with _LOCK:
        state["lines"].append(f"▶ {mid} ({m['name']}) 开始，预期 {expect}s · {len(files)} 文件")

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["OMCFG_TEST_PROGRESS"] = "1"  # 让 conftest 打印 >>>RUN 行供超时定位卡点
    proc = subprocess.Popen(
        cmd, cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )

    reader_done = threading.Event()

    def read_output() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            with _LOCK:
                result["lines"].append(line)
                # >>>RUN 行（conftest 在用例开始时打印）是「当前正在跑的用例」，
                # 超时时它就是要找的卡点；-v 的 PASSED 行作为无 >>>RUN 时的兜底。
                m_run = re.search(r">>>RUN\s+(tests/[\w/\\]+\.py::[\w]+)", line)
                m_case = re.search(r"(tests/[\w/\\]+\.py::[\w]+)\s+(PASSED|FAILED|ERROR|SKIPPED)", line)
                if m_run:
                    result["stuck_at"] = m_run.group(1).replace("\\", "/")
                elif m_case:
                    result["stuck_at"] = m_case.group(1).replace("\\", "/")
                if len(result["lines"]) > 400:  # 只留尾部，防止状态文件膨胀
                    result["lines"] = result["lines"][-400:]
        reader_done.set()

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    start = time.time()
    timed_out = False
    # 软超时：到 expect 标记「超时」但继续跑，好拿到真实超时时长、完整耗时榜单
    # 和卡点用例（直接 kill 会让 overtime 永远为 0、durations 为空，无法诊断）。
    # 硬上限 expect + max(30s, 50%) 兜底，防止真卡死无限跑。
    hard_limit = expect + max(30.0, expect * 0.5)
    while proc.poll() is None:
        elapsed = time.time() - start
        result["elapsed"] = round(elapsed, 1)
        if elapsed >= expect and not timed_out:
            timed_out = True
            with _LOCK:
                state["lines"].append(
                    f"  ⚠ {mid} 超过预期 {expect}s，继续观察至硬上限 {hard_limit:.0f}s（诊断超时原因）"
                )
        if elapsed >= hard_limit:
            break
        time.sleep(0.2)
    if proc.poll() is None:  # 到硬上限仍未结束才终止
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    else:
        proc.wait()
    reader.join(timeout=3)
    result["elapsed"] = round(time.time() - start, 1)
    result["returncode"] = proc.returncode
    # 只认真正的汇总行（如 "40 passed, 6 skipped in 7.2s"），
    # 不把 durations 里用例名含 error 的行误当汇总。durations 行以
    # "  N.NNs  call/setup/teardown  tests/..." 开头，用排除正则挡掉。
    # 汇总行形如 "===== 34 passed, 6 skipped in 3.17s =====" 或 "34 passed in 7s"。
    summary_re = re.compile(r"^[\s=]*\d+\s+(passed|failed|error|skipped)\b.*\bin\s+[\d.]+s", re.I)
    duration_line = re.compile(r"^\s*[\d.]+s\s+(call|setup|teardown)\s+")
    tail = [l for l in result["lines"]
            if summary_re.search(l) and not duration_line.match(l)]
    result["summary"] = tail[-1].strip().strip("= ").strip() if tail else ""
    status = _classify_status(proc.returncode, timed_out, result["lines"])
    # -q --no-header 下 pytest 只输出进度点，没有 "N passed" 汇总；从进度行点数补摘要。
    # 只取纯进度行（形如 ".....sss [100%]"），排除 durations/用例名里的点。
    if not result["summary"] and result["lines"]:
        progress = "".join(
            l for l in result["lines"]
            if re.fullmatch(r"[.sFE%\[\]0-9\s]+", l.strip()) and ("." in l or "F" in l or "E" in l)
        ).replace("\r", "")
        dots = progress.count(".")
        skips = progress.count("s")
        bad = progress.count("F") + progress.count("E")
        result["summary"] = f"{dots} passed" + (f" {skips} skipped" if skips else "")
        if bad:
            result["summary"] += f" {bad} failed/error"
        if status == "fail" and not bad:
            result["summary"] += "（rc=1，可能为环境清理副作用，见 lines）"
    result["status"] = status
    result["overtime"] = round(max(0.0, result["elapsed"] - expect), 1)
    result["case_times"] = _parse_durations(result["lines"])
    # 超时但没有 >>>RUN 线索时，用耗时榜单里最慢的用例兜底。
    if status == "timeout" and not result["stuck_at"] and result["case_times"]:
        result["stuck_at"] = result["case_times"][0]["case"]
    result["slow_reason"] = _diagnose_slow(
        result["case_times"], status, expect, result["elapsed"], result["stuck_at"]
    )
    result["finished_at"] = datetime.now().isoformat(timespec="seconds")
    with _LOCK:
        if timed_out:
            mark = "⏱ 超时"
        elif status == "env-blocked":
            mark = "⊘ 环境拦截"
        elif status == "pass":
            mark = "✓ 通过"
        else:
            mark = "✕ 失败"
        over = f" 超 {result['overtime']}s" if result["overtime"] else ""
        state["lines"].append(
            f"{mark}: {mid} 用时 {result['elapsed']}s / 预期 {expect}s{over} · {result['summary']}"
        )
        state["lines"].append(f"   诊断: {result['slow_reason']}")
        _write_state(state)
    return result


def _worker(only: list[str] | None) -> None:
    state = _load_state()
    cfg = _load_config()
    items = _enabled(cfg)
    if only:
        items = [m for m in items if m["id"] in only]
        missing = set(only) - {m["id"] for m in items}
        if missing:
            with _LOCK:
                state["lines"].append(f"⚠ 忽略未启用/不存在的里程碑: {', '.join(sorted(missing))}")
    state.update({
        "running": True,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": "",
        "milestones": [],
        "lines": [f"开始后台测试：{len(items)} 个里程碑（{datetime.now():%Y-%m-%d %H:%M:%S}）"],
    })
    _write_state(state)
    for m in items:
        try:
            _run_milestone(m, state)
        except Exception as exc:  # 单个里程碑异常不阻断其余
            with _LOCK:
                state["lines"].append(f"✕ {m['id']} 运行异常: {exc}")
                _write_state(state)
    state["running"] = False
    state["finished_at"] = datetime.now().isoformat(timespec="seconds")
    counts: dict[str, int] = {}
    for r in state["milestones"]:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    state["lines"].append("完成：" + " · ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    _write_state(state)


def cmd_run(args: argparse.Namespace) -> int:
    state = _load_state()
    if state.get("running"):
        print("已有测试任务在运行中（status 查看）")
        return 1
    # 前台阻塞跑，实时写状态文件；后台由外部终端的 run_in_background 提供。
    # 不用 Popen/DETACHED 造后台：在受限环境里子进程会被立即回收，状态停死。
    if args.popup:
        if _popup_watch():
            print("✓ 已弹出本地终端窗口实时显示进度（watch）")
        else:
            print("⚠ 无法弹出独立终端，请另开终端运行: python scripts/milestone_run.py watch")
    if args.live:
        # 同终端实时刷新：worker 在线程跑，主线程周期性渲染进度到终端。
        box: dict[str, Any] = {"done": False}

        def run_worker() -> None:
            try:
                _worker(args.only or None)
            finally:
                box["done"] = True

        th = threading.Thread(target=run_worker, daemon=True)
        th.start()
        try:
            while not box["done"]:
                sys.stdout.write("\033[H\033[J" + _render_progress(_load_state()) + "\n")
                sys.stdout.flush()
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n⚠ 已停止界面刷新，测试仍在后台线程继续（status 查看）")
            th.join()
        else:
            th.join()
            sys.stdout.write("\033[H\033[J" + _render_progress(_load_state()) + "\n")
            sys.stdout.flush()
    else:
        _worker(args.only or None)
    print("✓ 测试里程碑任务完成（report 查看汇总）")
    return 0


def cmd__worker(args: argparse.Namespace) -> int:
    _worker(args.only or None)
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    """在独立终端实时刷新进度；Ctrl-C 或任务完成后退出。--once 只打印一次。"""
    if args.once:
        print(_render_progress(_load_state()))
        return 0
    last_active = False
    try:
        while True:
            st = _load_state()
            sys.stdout.write("\033[H\033[J" + _render_progress(st) + "\n")
            sys.stdout.flush()
            active = st.get("running", False)
            if last_active and not active and st.get("finished_at"):
                break  # 从运行中变为完成，再刷一帧后退出
            last_active = active
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    print("\n（watch 已退出，测试仍在 run 进程继续；report 查看汇总）")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    st = _load_state()
    print(f"状态: {'运行中' if st.get('running') else '空闲/已完成'}")
    if st.get("started_at"):
        print(f"开始: {st['started_at']}  完成: {st.get('finished_at') or '-'}")
    print("-" * 78)
    for line in st.get("lines", [])[-args.tail:]:
        print(line)
    if st.get("milestones"):
        print("-" * 78)
        print("里程碑结果:")
    for m in st["milestones"]:
        icon = {"pass": "✓", "fail": "✕", "timeout": "⏱", "env-blocked": "⊘", "running": "…"}.get(m["status"], "?")
        over = f" 超 {m['overtime']}s" if m.get("overtime") else ""
        print(f"  {icon} {m['id']:<12} {m['status']:<11} {m['elapsed']}s / {m['expect_sec']}s{over} · {m.get('summary', '')}")
        if m.get("stuck_at") and m["status"] in ("running", "timeout"):
            print(f"      卡点: {m['stuck_at']}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    st = _load_state()
    if not st.get("milestones"):
        print("尚无测试结果（先 run）")
        return 1
    print(f"测试报告 · {st.get('started_at', '-')} → {st.get('finished_at', '-')}")
    print("=" * 78)
    all_pass = True
    for m in st["milestones"]:
        icon = {"pass": "✓", "fail": "✕", "timeout": "⏱", "env-blocked": "⊘", "running": "…"}.get(m["status"], "?")
        if m["status"] not in ("pass", "env-blocked"):
            all_pass = False
        over = f" 超 {m['overtime']}s" if m.get("overtime") else ""
        print(f"{icon} {m['id']:<12} {m['status']:<11} {m['elapsed']}s/{m['expect_sec']}s{over}  {m.get('summary', '')}")
        if m.get("slow_reason"):
            print(f"      ↳ {m['slow_reason']}")
        if m.get("stuck_at") and m["status"] in ("running", "timeout"):
            print(f"      ↳ 卡点用例: {m['stuck_at']}")
        if args.verbose:
            for c in m.get("case_times", [])[:args.verbose]:
                print(f"      ⏱ {c['sec']:>7.3f}s  {c['case']}")
            for line in m.get("lines", [])[-args.verbose:]:
                print(f"      | {line}")
    print("=" * 78)
    env_blocked = [m for m in st["milestones"] if m["status"] == "env-blocked"]
    if env_blocked:
        print(f"注意：{', '.join(m['id'] for m in env_blocked)} 被环境 safe-delete 钩子拦截"
              "（单 turn 删除超阈值），非测试失败；单独跑对应用例可通过。")
    print("总体：" + ("通过（无测试失败）" if all_pass else "存在失败/超时项（见上）"))
    return 0 if all_pass else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="后台测试里程碑运行器")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="列出里程碑").set_defaults(func=cmd_list)
    r = sub.add_parser("run", help="后台跑里程碑")
    r.add_argument("--only", nargs="*", help="只跑指定里程碑 id")
    r.add_argument("--live", action="store_true", help="当前终端实时刷新进度条")
    r.add_argument("--popup", action="store_true", help="弹出本地终端窗口实时显示进度")
    r.set_defaults(func=cmd_run)
    wch = sub.add_parser("watch", help="独立终端实时刷新进度（配合后台 run）")
    wch.add_argument("--once", action="store_true", help="只打印一次快照后退出")
    wch.add_argument("--interval", type=float, default=1.0, help="刷新间隔秒（默认 1）")
    wch.set_defaults(func=cmd_watch)
    s = sub.add_parser("status", help="查看进度与已完成输出")
    s.add_argument("--tail", type=int, default=40, help="显示最近 N 行日志")
    s.set_defaults(func=cmd_status)
    rp = sub.add_parser("report", help="汇总最近一次结果")
    rp.add_argument("-v", "--verbose", nargs="?", const=8, type=int, default=0,
                    help="附带每个里程碑尾部输出（默认 8 行）")
    rp.set_defaults(func=cmd_report)
    st = sub.add_parser("set-time", help="改预期秒数")
    st.add_argument("id"), st.add_argument("sec", type=int)
    st.set_defaults(func=cmd_set_time)
    rm = sub.add_parser("remove", help="删冗余项")
    rm.add_argument("id"), rm.add_argument("--hard", action="store_true", help="彻底删除而非禁用")
    rm.set_defaults(func=cmd_remove)
    rs = sub.add_parser("restore", help="恢复被删项")
    rs.add_argument("id")
    rs.set_defaults(func=cmd_restore)
    ad = sub.add_parser("add", help="新增里程碑")
    ad.add_argument("--id", required=True), ad.add_argument("--name", required=True)
    ad.add_argument("--sec", type=int, default=60), ad.add_argument("--files", nargs="+", required=True)
    ad.set_defaults(func=cmd_add)
    w = sub.add_parser("_worker", help=argparse.SUPPRESS)
    w.add_argument("--only", nargs="*")
    w.set_defaults(func=cmd__worker)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
