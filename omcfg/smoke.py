r"""三 logo 形态的冒烟工程：一键重建 TEST_CLI / TEST_NOCTRL / TEST_NONE。

用途：改过 baseline 后，一条命令重建三个工程，供 Keil 批量编译 + 烧录。
每个场景生成后自动断言关键宏，失败立即报告并保留现场。

用法（CLI）：
    python -m omcfg smoke
    python -m omcfg smoke --out D:\tmp\smoke
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class Scenario:
    name: str
    id_low: str
    modify: Callable[[str], str] | None
    expect_have: list[str] = field(default_factory=list)
    expect_not_have: list[str] = field(default_factory=list)
    hardware: str = ""


def _logo_none(cfg_text: str) -> str:
    """logo: ledc -> none，并删掉 LEDC 相关 board/pins 行。"""
    cfg_text = re.sub(r'^  logo: ledc\s*$', '  logo: none', cfg_text, flags=re.M)
    cfg_text = re.sub(r'^  ledc_rgb_number:.*\n', '', cfg_text, flags=re.M)
    cfg_text = re.sub(r'^  LEDC_(CTRL_)?PIN:.*\n', '', cfg_text, flags=re.M)
    return cfg_text


def _drop_ctrl(cfg_text: str) -> str:
    """删 LEDC_CTRL_PIN 行（保留 LEDC_PIN）。"""
    return re.sub(r'^  LEDC_CTRL_PIN:.*\n', '', cfg_text, flags=re.M)


def _run_cli(argv: list[str]) -> int:
    """跑一条 CLI 命令；stdout/stderr 全程捕获，失败时原样打印。

    cli.main 内部会 print 大量进度信息，冒烟汇总不希望被淹没；
    但失败时必须能看到完整 stderr（含 traceback），否则排查无从下手。
    """
    import contextlib
    import io

    from . import cli

    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argv)
    except SystemExit as exc:
        rc = int(exc.code or 0)
    except Exception:
        import traceback
        traceback.print_exc(file=err)
        rc = -1
    if rc != 0:
        print(err.getvalue(), end="")
    return rc


SCENARIOS = [

    Scenario(
        name="TEST_CLI",
        id_low="0x8888",
        modify=None,
        expect_have=[
            "#define LEDC_PIN",
            "#define LEDC_CTRL_PIN",
            "#define LEDC_RGB_NUMBER",
            "#if defined(LEDC_PIN)",
        ],
        expect_not_have=["#define LED_R_PIN"],
        hardware="灯带亮 + DPI 灯效 + MOS 正常",
    ),
    Scenario(
        name="TEST_NOCTRL",
        id_low="0x7777",
        modify=_drop_ctrl,
        expect_have=["#define LEDC_PIN", "#define LEDC_RGB_NUMBER"],
        expect_not_have=["#define LEDC_CTRL_PIN"],
        hardware="灯带亮 + MOS 不控",
    ),
    Scenario(
        name="TEST_NONE",
        id_low="0x6666",
        modify=_logo_none,
        expect_have=["LOGO灯配置"],
        expect_not_have=[
            "#define LEDC_PIN",
            "#define LEDC_CTRL_PIN",
            "#define LEDC_RGB_NUMBER",
            "#define LED_R_PIN",
        ],
        hardware="灯带不亮 + 鼠标/按键正常",
    ),
]


def _check_markers(project_root: Path, scenario: Scenario) -> list[str]:
    """返回问题列表（空 = 通过）。"""
    uh = project_root / "projects/mouse_demo/periph/user_config.h"
    lh = project_root / "projects/mouse_demo/periph/ledc.h"
    if not uh.is_file():
        return [f"缺少 {uh}"]
    uh_text = uh.read_text(encoding="utf-8", errors="replace")
    lh_text = lh.read_text(encoding="utf-8", errors="replace") if lh.is_file() else ""
    combined = uh_text + "\n" + lh_text
    problems: list[str] = []
    for key in scenario.expect_have:
        if key not in combined:
            problems.append(f"缺少 {key!r}")
    # 反向断言只查 user_config.h：ledc.h 里的 #ifndef LEDC_RGB_NUMBER 兜底宏是设计需要，
    # 不该被当作「不应有」命中。
    for key in scenario.expect_not_have:
        if key in uh_text:
            problems.append(f"user_config.h 不应有 {key!r}")
    return problems



_RMTREE_ATTEMPTS = 3
_RMTREE_DELAY = 1.0


def _locked_files(root: Path) -> list[str]:
    """列出 root 下「打不开 r+b」的文件（近似被锁，非精确句柄枚举）。

    只读文件也会被误报；实际排查够用，不引入 psutil 依赖。
    """
    locked: list[str] = []
    root = Path(root)
    if not root.is_dir():
        return locked
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            path.open("r+b").close()
        except (PermissionError, OSError):
            try:
                locked.append(path.relative_to(root).as_posix())
            except ValueError:
                locked.append(path.as_posix())
    return locked


def _rmtree_with_retry(
    path: Path, attempts: int = _RMTREE_ATTEMPTS, delay: float = _RMTREE_DELAY
) -> tuple[bool, list[str]]:
    """删除目录；遇 PermissionError 重试 attempts 次（间隔 delay 秒）。

    返回 (成功, 锁定文件相对路径列表)。
    先预检锁文件，有锁则不开始删——避免 rmtree 删一半留下残缺目录。
    非 PermissionError 的 OSError 直接上抛，不重试。
    """
    import time

    path = Path(path)
    if not path.exists():
        return True, []
    # 预检：有打不开的文件就不开始删，防止 rmtree 删一半失败
    pre_locked = _locked_files(path)
    if pre_locked:
        return False, pre_locked
    for i in range(attempts):
        try:
            shutil.rmtree(path)
            return True, []
        except PermissionError:
            if i < attempts - 1:
                time.sleep(delay)
        except OSError:
            raise
    locked = _locked_files(path) if path.exists() else []
    return False, locked


def run_smoke(out_dir: Path | str, scenarios: list[Scenario] | None = None,
              verbose: bool = True, skip_locked: bool = False) -> list[dict]:
    """重建全部冒烟工程；返回每个场景的结果 dict 列表。"""

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    chosen = scenarios if scenarios is not None else SCENARIOS
    results: list[dict] = []

    for sc in chosen:
        if verbose:
            print("=" * 70)
            print(f"[{sc.name}]")
            print("=" * 70)
        target = out_dir / sc.name
        result = {"name": sc.name, "target": target, "ok": False,
                  "steps": [], "problems": [], "hardware": sc.hardware,
                  "skipped": False}

        if target.exists():
            ok, locked = _rmtree_with_retry(target)
            if not ok:
                if skip_locked:
                    result["skipped"] = True
                    result["problems"].append(
                        f"旧工程被占用，已跳过：{target}（锁定 {len(locked)} 个文件）"
                    )
                    results.append(result)
                    if verbose:
                        print(f"  [SKIP] {target} 被占用，跳过")
                        for name in locked[:
                            10]:
                            print(f"         锁定: {name}")
                    continue
                msg = (
                    f"无法删除旧工程 {target}（重试 {_RMTREE_ATTEMPTS} 次仍失败）。"
                    f"锁定 {len(locked)} 个文件："
                    + (", ".join(locked[:10]) if locked else "(未能枚举)")
                    + "。请关闭 Keil / 资源管理器 / 任何占用该目录的程序后重试，"
                    "或改用 --out 指定另一个输出目录，或加 --skip-locked。"
                )
                result["problems"].append(msg)
                results.append(result)
                if verbose:
                    print(f"  [FAIL] {msg}")
                continue
            result["steps"].append("清理旧工程")


        rc = _run_cli([
            "new", "--name", sc.name, "--target", str(target),
            "--id", sc.id_low, "--scan", str(out_dir),
            "--no-keep-backup",
        ])

        if rc != 0:
            result["problems"].append(f"new 返回 {rc}")
            results.append(result)
            if verbose:
                print(f"  [FAIL] new rc={rc}")
            continue
        result["steps"].append("new")

        cfg = target / "projects/mouse_demo/project.omcfg"
        if sc.modify:
            old = cfg.read_text(encoding="utf-8")
            new = sc.modify(old)
            if new != old:
                cfg.write_text(new, encoding="utf-8")
                result["steps"].append("modify config")

        rc = _run_cli(["gen", "--sdk", str(target), "--config", str(cfg), "--apply"])

        if rc != 0:
            result["problems"].append(f"gen 返回 {rc}")
            results.append(result)
            if verbose:
                print(f"  [FAIL] gen rc={rc}")
            continue
        result["steps"].append("gen --apply")
        # 冒烟工程是重建产物，不留 gen 事务备份（避免 _test_gen 里堆积 .omcfg_bak_*）
        for _bak in target.glob(".omcfg_bak_*"):
            if _bak.is_dir():
                shutil.rmtree(_bak, ignore_errors=True)

        rc = _run_cli(["check", "--sdk", str(target), str(cfg)])

        if rc != 0:
            result["problems"].append(f"check 返回 {rc}")
            results.append(result)
            if verbose:
                print(f"  [FAIL] check rc={rc}")
            continue
        result["steps"].append("check --sdk")

        problems = _check_markers(target, sc)
        result["problems"] = problems
        result["ok"] = not problems
        result["steps"].append("verify markers")
        results.append(result)
        if verbose:
            if problems:
                print(f"  [FAIL] {problems}")
            else:
                print(f"  [PASS] {sc.hardware}")

    if verbose:
        print("\n" + "=" * 70)
        print("汇总")
        print("=" * 70)
        for r in results:
            if r.get("skipped"):
                status = "SKIP"
            else:
                status = "PASS" if r["ok"] else "FAIL"
            proj = r["target"] / "projects/mouse_demo/keil5/SE71M.uvprojx"
            print(f"  [{status}] {r['name']:<14} {proj}")
        print("\n下一步：Keil 打开上述 .uvprojx 逐个编译，按各场景硬件要点烧录验证。")

    return results
