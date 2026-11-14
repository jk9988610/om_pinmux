"""omcfg 命令行：init / check / gen / rollback。

退出码：0 成功；1 配置校验失败；2 环境/标记块/manifest 错误；3 写盘失败。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

from . import baseline, model, newproject, rules, smoke, validate

from .generate import generator
from .initproject import init_project, missing_markers
from .targets import sdk, uvprojx
from .transaction import FileTransaction, rollback_manifest

EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_ENVIRONMENT = 2
EXIT_WRITE = 3
# 4 历史预留（已回滚），当前命令不会返回；保留常量避免误以为是新错误。
EXIT_ROLLED_BACK = 4

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs"


def _id_records(paths: list[Path]) -> list[dict]:
    records: list[dict] = []
    seen: set[tuple[int, int, str]] = set()
    for path in paths:
        if not path.is_file():
            continue
        try:
            config = model.load_config(path)
            project = model.project_id(config)
            low = int(str(project["low"]), 0)
            high = int(str(project["high"]), 0)
            name = str(model.project(config).get("name", ""))
        except Exception:
            continue
        key = (low, high, name)
        if key in seen:
            continue
        seen.add(key)
        records.append({"low": low, "high": high, "name": name, "path": path})
    return records


def _id_paths(target: Path, scans: list[str]) -> list[Path]:
    paths: set[Path] = {baseline.CONFIG_PATH}
    paths.update(CONFIGS_DIR.glob("*.omcfg"))
    paths.update(target.parent.glob("*/projects/mouse_demo/project.omcfg"))
    for item in scans:
        paths.update(Path(item).expanduser().glob("*/projects/mouse_demo/project.omcfg"))
    return sorted(path.resolve() for path in paths)


def _free_id(records: list[dict]) -> int:
    used = {record["low"] for record in records}
    candidate = 1
    while candidate in used:
        candidate += 1
    return candidate


def _error(message: str, hint: str = "") -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    if hint:
        print(f"        提示: {hint}", file=sys.stderr)


def _read_config(path: Path) -> dict:
    return model.load_config(path)


def _print_report(report: validate.Report, config: dict) -> None:
    for issue in report.errors + report.warnings:
        print(issue.render())
    print(validate.summary(config, report))


def _add_mismatch_warning(report: validate.Report, config: dict, root: Path) -> None:
    warning = generator.sdk_warning(config, root)
    if warning:
        report.add_warning("project", warning[0], warning[1])


def cmd_check(args: argparse.Namespace) -> int:
    if args.rules:
        if args.paths or args.all or args.sdk:
            _error("--rules 不能与配置路径/--all/--sdk 组合", "单独运行 check --rules 查看规则清单")
            return EXIT_ENVIRONMENT
        print(rules.render_rules())
        return EXIT_OK
    if args.all and args.sdk:
        _error("--all 与 --sdk 互斥", "板模板只对自身配置做同步审计；指定 --sdk 时只检查一份配置")
        return EXIT_ENVIRONMENT
    root: Path | None = None
    if args.sdk:
        try:
            root = sdk.resolve_sdk(args.sdk)
        except Exception as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return EXIT_ENVIRONMENT
        missing = missing_markers(root, require_config=False)
        if missing:
            _error(
                f"SDK 尚未初始化（缺少标记块: {', '.join(missing)}）",
                "先运行 python -m omcfg init --config <配置> --sdk <SDK>",
            )
            return EXIT_ENVIRONMENT
        if len(args.paths) > 1:
            _error(
                "--sdk 只接受一个配置路径",
                "省略路径则用 <SDK>/projects/mouse_demo/project.omcfg",
            )
            return EXIT_ENVIRONMENT
        paths = [Path(args.paths[0])] if args.paths else [model.default_config_path(root)]
    elif args.all:
        directory = Path(args.all)
        if not directory.is_dir():
            _error(
                f"目录不存在: {directory}",
                "check --all 指向存放 *.omcfg 的目录，例如: check --all configs",
            )
            return EXIT_ENVIRONMENT
        paths = sorted(directory.glob("*.omcfg"))
    else:
        paths = [Path(item) for item in args.paths]
    if not paths:
        _error(
            "没有可检查的配置",
            "用 check <file.omcfg ...>、check --all configs 或 check --sdk <SDK>",
        )
        return EXIT_ENVIRONMENT
    failed = False
    for path in paths:
        print(f"== {path} ==")
        if not path.is_file():
            _error(
                f"配置不存在: {path}",
                "确认路径；仓库内的板模板在 configs/*.omcfg",
            )
            return EXIT_ENVIRONMENT
        try:
            config = _read_config(path)
        except yaml.YAMLError as exc:
            _error(
                f"{path}: YAML 解析失败: {exc}",
                "检查缩进、冒号和引号；可对照 configs/KC536.omcfg",
            )
            return EXIT_ENVIRONMENT
        except ValueError as exc:
            _error(f"{path}: {exc}", "配置顶层应为 schema/chip/project/board/pins 映射")
            return EXIT_ENVIRONMENT
        except OSError as exc:
            _error(f"{path}: 读取失败: {exc}", "确认文件未被占用、当前用户可读")
            return EXIT_ENVIRONMENT
        report = validate.validate_config(config)
        if root is not None:
            audit = rules.audit(config, root, strict=True)
            report.errors.extend(audit.errors)
            report.warnings.extend(audit.warnings)
        _print_report(report, config)
        failed = failed or not report.ok
    return EXIT_VALIDATION if failed else EXIT_OK


def cmd_init(args: argparse.Namespace) -> int:
    try:
        root = sdk.resolve_sdk(args.sdk)
        config_source = Path(args.config)
        if not config_source.is_file():
            raise sdk.TargetError(
                f"配置不存在: {config_source}\n"
                f"  提示: 板模板在 configs/*.omcfg（如 configs/KC536.omcfg、configs/CH04.omcfg）"
            )
        try:
            config = _read_config(config_source)
        except yaml.YAMLError as exc:
            _error(
                f"{config_source}: YAML 解析失败: {exc}",
                "检查缩进、冒号和引号；可对照 configs/KC536.omcfg",
            )
            return EXIT_ENVIRONMENT
        except ValueError as exc:
            _error(f"{config_source}: {exc}", "配置顶层应为 schema/chip/project/board/pins 映射")
            return EXIT_ENVIRONMENT
        report = validate.validate_config(config)
        if not report.ok:
            _print_report(report, config)
            return EXIT_VALIDATION
        init_project(root, config_source, args.force)
        return EXIT_OK
    except sdk.TargetError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT
    except OSError as exc:
        _error(f"写入失败: {exc}", "确认 SDK 副本不在编译中、文件未被占用")
        return EXIT_WRITE


def _apply_outputs(
    root: Path,
    outputs: list[generator.GeneratedFile],
    operation: str = "omcfg_apply",
    tx=None,
) -> tuple[int, Path | None]:
    """把 changed 输出写盘并产出 manifest；new 与 gen 共用。

    tx 传入时并入外部事务（caller 负责 commit / 回滚），本地不 commit。
    """
    changed = [item for item in outputs if item.changed]
    if not changed:
        print("生成结果与 SDK 现状一致")
        return EXIT_OK, None
    owns_tx = tx is None
    transaction = tx if tx is not None else FileTransaction.create(root, operation)
    try:
        for item in changed:
            transaction.write_bytes(item.path, item.render(), "按标记块写入生成内容")
        manifest = transaction.commit() if owns_tx else None
    except OSError as exc:
        _error(f"写入失败，已按备份回滚: {exc}", "确认 SDK 副本未被 Keil 打开或占用")
        if owns_tx:
            for entry in transaction.entries:
                target = transaction.target_root / entry["path"]
                backup = transaction.backup_root / entry["backup"] if entry.get("backup") else None
                if entry.get("existed") and backup and backup.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(backup.read_bytes())
                elif not entry.get("existed") and target.exists():
                    target.unlink()
        return EXIT_WRITE, None
    if owns_tx:
        print(f"已写入 {len(changed)} 个文件；manifest: {manifest}")
    else:
        print(f"已写入 {len(changed)} 个文件（并入外部事务）")
    return EXIT_OK, manifest


def cmd_gen(args: argparse.Namespace) -> int:
    try:
        root = sdk.resolve_sdk(args.sdk)
    except sdk.TargetError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT
    config_path = Path(args.config) if args.config else model.default_config_path(root)
    if not config_path.is_file():
        _error(
            f"配置不存在: {config_path}",
            "先运行 python -m omcfg init 安装 project.omcfg，"
            "或用 --config configs/KC536.omcfg 指定板模板",
        )
        return EXIT_ENVIRONMENT
    try:
        config = _read_config(config_path)
    except yaml.YAMLError as exc:
        _error(
            f"{config_path}: YAML 解析失败: {exc}",
            "检查缩进、冒号和引号；可对照 configs/KC536.omcfg",
        )
        return EXIT_ENVIRONMENT
    except ValueError as exc:
        _error(f"{config_path}: {exc}", "配置顶层应为 schema/chip/project/board/pins 映射")
        return EXIT_ENVIRONMENT
    except OSError as exc:
        _error(f"{config_path}: 读取失败: {exc}", "确认文件未被占用、当前用户可读")
        return EXIT_ENVIRONMENT

    report = validate.validate_config(config)
    _add_mismatch_warning(report, config, root)
    _print_report(report, config)
    if not report.ok:
        return EXIT_VALIDATION

    try:
        outputs = generator.build_outputs(config, root)
    except sdk.TargetError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT
    except OSError as exc:
        _error(f"读取生成目标失败: {exc}", "确认 SDK 副本完整、文件未被其他程序占用")
        return EXIT_WRITE

    changed = [item for item in outputs if item.changed]
    for item in outputs:
        if not item.changed:
            print(f"无变化: {item.path}")
            continue
        print(item.diff())
    if not changed:
        print("生成结果与 SDK 现状一致")
        return EXIT_OK

    if not args.apply:
        print(f"dry-run: {len(changed)} 个文件待写入；确认后加 --apply")
        return EXIT_OK

    code, manifest = _apply_outputs(root, outputs)
    if manifest:
        print(f"回滚: python -m omcfg rollback --manifest {manifest}")
    return code


def cmd_new(args: argparse.Namespace) -> int:
    """命名即建工程：从内置基线复制，身份与默认参数由工具生成。"""
    name = args.name.strip()
    problem = baseline.name_problem(name)
    if problem:
        _error(problem, "例如 --name KC536X；工程名会写入 iPROJECT_NAME 并派生 BLE 广播名")
        return EXIT_VALIDATION
    target = (
        Path(args.target).expanduser().resolve()
        if args.target
        else (Path.cwd() / name).resolve()
    )
    if target.exists():
        _error(
            f"目标路径已存在: {target}",
            "new 不覆盖任何现有目录；换一个不存在的路径，"
            "或确认旧目录无用后手工删除再执行",
        )
        return EXIT_ENVIRONMENT

    id_low: int | None = None
    if args.id:
        try:
            id_low = int(args.id, 0)
        except ValueError:
            _error(f"无法解析 --id: {args.id}", "接受 0x0457 或 1111 这类写法")
            return EXIT_VALIDATION
        if not 1 <= id_low <= 0xFFFF:
            _error(f"--id 超出范围: {id_low}", "项目号低 16 位范围是 1..0xFFFF（0x0000 保留）")
            return EXIT_VALIDATION

    try:
        source, config_source = baseline.ensure_ready()
    except baseline.BaselineError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT
    if source == target or source in target.parents:
        _error(
            f"目标路径不能位于内置基线内: {target}",
            "把 --target 换到 baseline/sdk 之外，避免复制自身造成递归",
        )
        return EXIT_ENVIRONMENT

    config = baseline.config_for_name(name, config_source, id_low)
    project_id = model.project_id(config)
    low = int(str(project_id["low"]), 0)
    high = int(str(project_id["high"]), 0)
    records = _id_records(_id_paths(target, args.scan or []))
    duplicates = [item for item in records if item["low"] == low and item["high"] == high]
    if duplicates:
        _error(
            f"项目号 {project_id['low']} / {project_id['high']} 已被占用",
            "同一项目号会让烧录/配对身份无法区分；请手工指定 --id（未占用的低 16 位）",
        )
        for item in duplicates:
            print(f"        - {item['name'] or '(未命名)'}: {item['path']}", file=sys.stderr)
        suggestion = _free_id(records)
        print(f"        可改用: --id 0x{suggestion:04X}", file=sys.stderr)
        return EXIT_VALIDATION

    config_payload = (model.dump_config(config) + "\n").encode("utf-8")
    report = validate.validate_config(config)
    _print_report(report, config)
    if not report.ok:
        return EXIT_VALIDATION

    print(f"内置基线: {source}")
    print(f"新工程: {target}（目录由工具生成）")
    print(f"工程名: {name}")
    source_note = "手工指定" if id_low is not None else "按名称派生"
    print(
        f"项目号: {project_id['low']} / {project_id['high']} / v{project_id['version']}"
        f"（{source_note}）"
    )
    print(f"BLE 广播名: {' / '.join(model.ble_names(config))}")

    transaction = FileTransaction.create(target, "omcfg_new")
    new_manifest: Path | None = None
    try:
        copied = newproject.copy_skeleton(source, target)
        print(f"新工程: {target}（复制 {copied} 个文件）")
        print(f"不复制: {newproject.NOT_COPIED_SUMMARY}")
        config_target = model.default_config_path(target)
        config_target.parent.mkdir(parents=True, exist_ok=True)
        transaction.write_bytes(config_target, config_payload, "写入项目配置")
        rewrites = newproject.rewrite_identity(target, config, tx=transaction)
        init_project(
            target, config_target, force=False, verbose=False, announce_next=False, tx=transaction
        )
        outputs = generator.build_outputs(config, target)
        code, _manifest = _apply_outputs(target, outputs, "omcfg_new", tx=transaction)
        if code != EXIT_OK:
            raise sdk.TargetError("生成内容写入失败")
        new_manifest = transaction.commit()
    except sdk.TargetError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        shutil.rmtree(target, ignore_errors=True)
        print(f"        已清理未完成的目标目录: {target}", file=sys.stderr)
        return EXIT_ENVIRONMENT
    except OSError as exc:
        _error(f"写入失败: {exc}", "确认目标目录可写、未被其他程序占用")
        shutil.rmtree(target, ignore_errors=True)
        return EXIT_WRITE

    macros = newproject.identity_macro_records(source, target)
    records = macros + rewrites
    if args.keep_backup and new_manifest is not None:
        print(f"事务 manifest 已保留，可回滚: {new_manifest}")
    else:
        newproject.remove_backups(target)
        print("生成后的 .omcfg_bak_* 已清理（新工程基线不携带历史备份）")

    if records:
        print("标识改写（源 -> 新）:")
        for record in records:
            print(f"  {record.render()}")
    else:
        print("标识改写: 与源工程一致，未改写")
    print(f"下一步: python -m omcfg check {config_target}")
    project = uvprojx.project_path(config, target)
    if project:
        print(f"编译: UV4 -r {project} -o build.log")
    return EXIT_OK


def cmd_smoke(args: argparse.Namespace) -> int:
    """重建三 logo 形态冒烟工程。"""
    out = Path(args.out).expanduser().resolve()
    results = smoke.run_smoke(out, skip_locked=getattr(args, "skip_locked", False))
    return EXIT_OK if all(r["ok"] for r in results) else EXIT_VALIDATION


def _locate_manifest(value: str) -> Path:

    path = Path(value).expanduser()
    if path.is_dir():
        candidate = path / "manifest.json"
        if candidate.is_file():
            return candidate
    return path


def cmd_rollback(args: argparse.Namespace) -> int:
    manifest = _locate_manifest(args.manifest)
    if not manifest.is_file():
        _error(
            f"manifest 不存在: {manifest}",
            "manifest 位于 <SDK>/.omcfg_bak_<时间戳>/manifest.json；"
            "也可以直接把该目录传给 --manifest",
        )
        return EXIT_ENVIRONMENT
    try:
        result = rollback_manifest(manifest)
    except json.JSONDecodeError as exc:
        _error(
            f"manifest 解析失败: {manifest}: {exc}",
            "该文件不是 omcfg 事务 manifest，或已损坏；换用 .omcfg_bak_<时间戳> 下的 manifest.json",
        )
        return EXIT_ENVIRONMENT
    except FileNotFoundError as exc:
        _error(f"备份文件缺失: {exc}", "备份目录被手工删除时无法回滚；改用 git 或原 SDK 对照恢复")
        return EXIT_ENVIRONMENT
    except ValueError as exc:
        _error(f"manifest 不受支持: {exc}", "确认它由当前版本的 init/gen/apply 生成")
        return EXIT_ENVIRONMENT
    except OSError as exc:
        _error(f"回滚写入失败: {exc}", "确认 SDK 副本未被 Keil 打开或占用")
        return EXIT_WRITE
    print(f"已恢复 {len(result['restored'])} 个文件: {result['manifest']}")
    print(f"目标工程: {result['target_root']}")
    print(f"复查: python -m omcfg gen --sdk {result['target_root']} --dry-run")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omcfg",
        description="OM6239 轻量配置生成器：校验 .omcfg，并按标记块写回 SDK 工程。",
        epilog=(
            "快速上手（在副本上）:\n"
            "  python -m omcfg check --all configs\n"
            "  python -m omcfg new --name <新工程名>\n"
            "  python -m omcfg init --config configs\\KC536.omcfg --sdk <SDK副本>\n"
            "  python -m omcfg gen --sdk <SDK副本> --dry-run\n"
            "  python -m omcfg gen --sdk <SDK副本> --apply\n"
            "  python -m omcfg rollback --manifest <SDK副本>\\.omcfg_bak_<时间戳>\\manifest.json\n"
            "\n"
            "退出码: 0 成功 / 1 配置校验失败 / 2 环境、配置解析或 manifest 错误 / 3 写盘失败"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(
        dest="command", required=True, metavar="{init,check,gen,new,rollback,smoke}"

    )

    init = sub.add_parser(
        "init",
        help="安装 project.omcfg 并插入 OMCFG/USER CODE 标记（一次性）",
        description=(
            "把板模板安装为 <SDK>/projects/mouse_demo/project.omcfg，"
            "并在生成目标里插入标记块。"
        ),
        epilog=(
            "示例:\n"
            "  python -m omcfg init --config configs\\CH04.omcfg --sdk E:\\copy\\CH04_SDK\n"
            "重复执行是安全的；已有内容不同的 project.omcfg 需加 --force。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    init.add_argument(
        "--config",
        required=True,
        metavar="FILE",
        help="板模板或已有工程配置，如 configs/KC536.omcfg",
    )
    init.add_argument(
        "--sdk",
        required=True,
        metavar="DIR",
        help="SDK 根目录（其下有 projects/mouse_demo/periph）",
    )
    init.add_argument(
        "--force", action="store_true", help="覆盖内容不同的 project.omcfg（默认拒绝）"
    )

    check = sub.add_parser(
        "check",
        help="校验配置（不写盘）",
        description="解析 .omcfg 并跑引脚/板型规则；退出码 1 表示存在 error。",
        epilog=(
            "示例:\n"
            "  python -m omcfg check configs\\KC536.omcfg\n"
            "  python -m omcfg check --all configs"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    check.add_argument("paths", nargs="*", metavar="FILE", help="一个或多个 .omcfg 路径")
    check.add_argument("--all", metavar="DIR", help="检查目录下所有 *.omcfg")
    check.add_argument(
        "--sdk",
        metavar="DIR",
        help="对该 SDK 副本做跨 key_io/ledc/user_config 的同步审计（严格模式）",
    )
    check.add_argument("--rules", action="store_true", help="打印模块连带规则清单后退出")

    gen = sub.add_parser(
        "gen",
        help="生成配置代码与 Keil 工程；默认 dry-run",
        description="按 project.omcfg 渲染标记块内容；默认只打印 unified diff。",
        epilog=(
            "示例:\n"
            "  python -m omcfg gen --sdk <SDK副本> --dry-run\n"
            "  python -m omcfg gen --sdk <SDK副本> --apply\n"
            "--apply 会写入 .omcfg_bak_<时间戳>/manifest.json，可用 rollback 撤销。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    gen.add_argument(
        "--config",
        metavar="FILE",
        help="配置路径；缺省用 <SDK>/projects/mouse_demo/project.omcfg",
    )
    gen.add_argument(
        "--sdk",
        required=True,
        metavar="DIR",
        help="SDK 根目录（其下有 projects/mouse_demo/periph）",
    )
    dry = gen.add_mutually_exclusive_group()
    dry.add_argument("--dry-run", action="store_true", help="只打印 diff，不落盘（默认行为）")
    dry.add_argument(
        "--apply", action="store_true", help="真正写入标记块，并生成可回滚 manifest"
    )

    new = sub.add_parser(
        "new",
        help="从内置基线按名称生成可编译的新工程（复制 → 改标识 → init → gen）",
        description=(
            "从工具内置基线（baseline/sdk）复制骨架，按工程名生成 ID/BLE 广播名并改写 "
            "iPROJECT_NAME、iPROJECT_ID_L/H、iREAL_VERSION_ID，完成 init 与 gen --apply。"
        ),
        epilog=(
            "示例:\n"
            "  python -m omcfg new --name MyMouse\n"
            "  python -m omcfg new --name MyMouse --target D:\\work\\MyMouse\n"
            "工程名、目录、项目号、BLE 广播名由工具生成；源 SDK 来自工具内置基线，"
            "无需再指定 --sdk/--config。目标路径必须不存在，命令不覆盖现有目录。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    new.add_argument(
        "--name",
        required=True,
        metavar="NAME",
        help="工程名（写入 iPROJECT_NAME，并派生 BLE 广播名）",
    )
    new.add_argument(
        "--target",
        metavar="DIR",
        help="新工程目录；缺省为当前目录下的 <NAME>（必须不存在）",
    )
    new.add_argument(
        "--id",
        metavar="ID",
        help="手工指定项目号低 16 位（0x0457 或十进制）；缺省按名称派生",
    )
    new.add_argument(
        "--scan",
        action="append",
        metavar="DIR",
        help="额外的已生成工程父目录，用于项目号碰撞检查（可重复）",
    )
    new.add_argument(
        "--keep-backup",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="保留 new 的事务备份与 manifest（默认保留，便于 rollback；--no-keep-backup 关闭）",
    )

    rollback = sub.add_parser(
        "rollback",
        help="按 manifest 回滚到写入前状态",
        description="读取 .omcfg_bak_<时间戳>/manifest.json，恢复其中记录的文件。",
        epilog=(
            "示例:\n"
            "  python -m omcfg rollback --manifest <SDK副本>\\.omcfg_bak_20261106_120000\n"
            "  python -m omcfg rollback --manifest <SDK副本>\\.omcfg_bak_<时间戳>\\manifest.json\n"
            "按时间倒序多次回滚可逐步撤销 init/gen 的操作。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    rollback.add_argument(
        "--manifest",
        required=True,
        metavar="FILE_OR_DIR",
        help="manifest.json 或其所在 .omcfg_bak_* 目录",
    )
    smoke_cmd = sub.add_parser(
        "smoke",
        help="重建三种 logo 形态的冒烟工程（TEST_CLI / TEST_NOCTRL / TEST_NONE）",
        description="重建三种 logo 形态的冒烟工程，供 Keil 批量编译 + 烧录。",
        epilog=(
            "示例:\n"
            "  python -m omcfg smoke\n"
            "  python -m omcfg smoke --out D:\\tmp\\smoke"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    smoke_cmd.add_argument(
        "--out",
        default="_test_gen",
        metavar="DIR",
        help="冒烟工程输出目录（默认 _test_gen）",
    )
    smoke_cmd.add_argument(
        "--skip-locked",
        action="store_true",
        help="旧工程被 Keil 占用时跳过该场景（记 [SKIP]），继续重建其余工程",
    )

    return parser



def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init":
        return cmd_init(args)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "gen":
        return cmd_gen(args)
    if args.command == "new":
        return cmd_new(args)
    if args.command == "rollback":
        return cmd_rollback(args)
    if args.command == "smoke":
        return cmd_smoke(args)

    parser.error("未知命令")
    return EXIT_ENVIRONMENT
