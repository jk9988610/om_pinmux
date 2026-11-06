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

from . import model, newproject, validate
from .generate import generator
from .targets import sdk, uvprojx
from .transaction import FileTransaction, rollback_manifest

EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_ENVIRONMENT = 2
EXIT_WRITE = 3
# 4 历史预留（已回滚），当前命令不会返回；保留常量避免误以为是新错误。
EXIT_ROLLED_BACK = 4


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
    if args.all:
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
            "用 check <file.omcfg ...> 或 check --all configs",
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
        _print_report(report, config)
        failed = failed or not report.ok
    return EXIT_VALIDATION if failed else EXIT_OK


def _anchor_index(lines: list[str], needle: str, starts: bool, path: Path, block: str) -> int:
    hits = [
        i
        for i, line in enumerate(lines)
        if (line.startswith(needle) if starts else line.strip() == needle)
    ]
    if len(hits) != 1:
        raise sdk.TargetError(
            f"{path} 中定位 '{needle}' 命中 {len(hits)} 次，拒绝插入 '{block}' 标记"
        )
    return hits[0]


def _insert_block(
    text: str, path: Path, block: str, start_needle: str, end_needle: str, starts: bool = True
) -> str:
    if sdk.marker_begin(block) in text or sdk.marker_end(block) in text:
        if sdk.marker_begin(block) in text and sdk.marker_end(block) in text:
            return text
        raise sdk.TargetError(f"{path} 的 '{block}' 标记只出现一半，请人工修掉后再 init")
    lines = text.split("\n")
    start = _anchor_index(lines, start_needle, starts, path, block)
    end = _anchor_index(lines[start:], end_needle, starts, path, block) + start
    lines.insert(end + 1, sdk.marker_end(block))
    lines.insert(start, sdk.marker_begin(block))
    return "\n".join(lines)


def _init_header(text: str, path: Path) -> str:
    text = _insert_block(text, path, "pins", "//* 按键配置 */", "#define UART_PIN")
    text = _insert_block(
        text, path, "project_ids", "#define iPROJECT_ID_H", "#define iPROJECT_ID_L"
    )
    text = _insert_block(
        text, path, "project_version", "#define iREAL_VERSION_ID", "#define iREAL_VERSION_ID"
    )
    text = _insert_block(
        text, path, "project_names", "#define iCONSUMER_NAME", "#define iPROJECT_NAME"
    )
    return text


def _init_source(text: str, path: Path) -> str:
    text = _insert_block(
        text,
        path,
        generator.BLOCK_C,
        "const user_gpio_config_t gpio_config_table[] = {",
        "};",
        starts=False,
    )
    return sdk.wrap_function_block(text, sdk.SLEEP_BLOCK, "void periph_gpio_sleep_set", path)


def _init_project(
    root: Path, config_source: Path, force: bool, announce_next: bool = True
) -> int:
    """安装配置并插入标记；init 与 new 共用，出错抛 sdk.TargetError。"""
    transaction = FileTransaction.create(root, "omcfg_init")
    config_target = model.default_config_path(root)
    if config_target.is_file():
        if config_target.read_bytes() != config_source.read_bytes():
            if not force:
                raise sdk.TargetError(
                    f"{config_target} 已存在且内容不同；确认覆盖请加 --force"
                )
        else:
            print(f"配置已存在且一致: {config_target}")
    if not config_target.is_file() or config_target.read_bytes() != config_source.read_bytes():
        transaction.write_bytes(config_target, config_source.read_bytes(), "安装唯一配置源")

    for relative, handler, user_code in (
        (sdk.USER_CONFIG_H, _init_header, sdk.USER_CODE_H),
        (sdk.USER_CONFIG_C, _init_source, sdk.USER_CODE_C),
    ):
        path = root / relative
        source = sdk.read_source(path)
        if sdk.legacy_markers(source.text):
            raise sdk.TargetError(f"{path} 仍含旧 OM_PINMUX_GENERATED 标记，请先人工迁移")
        before = source.text
        after = handler(before, path)
        if sdk.strip_marker_lines(after) != sdk.strip_marker_lines(before):
            raise sdk.TargetError(f"{path} 插入标记后正文发生变化，已中止")
        after = sdk.append_user_code(after, user_code, path)
        if after != before:
            sdk.ensure_encodable(after, source.encoding)
            transaction.write_bytes(
                path,
                sdk.SourceFile(path, after, source.encoding, source.newline, source.bom).render(),
                "插入 OMCFG/USER CODE 标记",
            )
            print(f"已插入标记: {path}")
        else:
            print(f"标记已存在: {path}")

    for relative, user_code in ((sdk.BOARD_FEATURES_H, sdk.USER_CODE_FEATURES),):
        path = root / relative
        if not path.is_file():
            continue
        source = sdk.read_source(path)
        if sdk.legacy_markers(source.text):
            raise sdk.TargetError(f"{path} 仍含旧 OM_PINMUX_GENERATED 标记，请先人工迁移")
        after = sdk.append_user_code(source.text, user_code, path)
        if after != source.text:
            sdk.ensure_encodable(after, source.encoding)
            transaction.write_bytes(
                path,
                sdk.SourceFile(path, after, source.encoding, source.newline, source.bom).render(),
                "补 USER CODE 保护区",
            )
            print(f"已补 USER CODE 保护区: {path}")
    if transaction.actions:
        manifest = transaction.commit()
        print(f"事务 manifest: {manifest}")
    else:
        print("没有文件变化")
    if announce_next:
        print(f"下一步: python -m omcfg gen --sdk {root} --dry-run")
    return EXIT_OK


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
        return _init_project(root, config_source, args.force)
    except sdk.TargetError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT
    except OSError as exc:
        _error(f"写入失败: {exc}", "确认 SDK 副本不在编译中、文件未被占用")
        return EXIT_WRITE


def _apply_outputs(
    root: Path, outputs: list[generator.GeneratedFile], operation: str = "omcfg_apply"
) -> tuple[int, Path | None]:
    """把 changed 输出写盘并产出 manifest；new 与 gen 共用。"""
    changed = [item for item in outputs if item.changed]
    if not changed:
        print("生成结果与 SDK 现状一致")
        return EXIT_OK, None
    transaction = FileTransaction.create(root, operation)
    try:
        for item in changed:
            transaction.write_bytes(item.path, item.render(), "按标记块写入生成内容")
        manifest = transaction.commit()
    except OSError as exc:
        _error(f"写入失败，已按备份回滚: {exc}", "确认 SDK 副本未被 Keil 打开或占用")
        for entry in transaction.entries:
            target = transaction.target_root / entry["path"]
            backup = transaction.backup_root / entry["backup"] if entry.get("backup") else None
            if entry.get("existed") and backup and backup.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(backup.read_bytes())
            elif not entry.get("existed") and target.exists():
                target.unlink()
        return EXIT_WRITE, None
    print(f"已写入 {len(changed)} 个文件；manifest: {manifest}")
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
    try:
        source = sdk.resolve_sdk(args.sdk)
    except sdk.TargetError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT

    target = Path(args.target).expanduser().resolve()
    if target.exists():
        _error(
            f"目标路径已存在: {target}",
            "new 不覆盖任何现有目录；换一个不存在的路径，"
            "或确认旧目录无用后手工删除再执行",
        )
        return EXIT_ENVIRONMENT
    if source in target.parents:
        _error(
            f"目标路径不能位于源 SDK 内: {target}",
            "把 --target 换到源 SDK 之外，避免复制自身造成递归",
        )
        return EXIT_ENVIRONMENT

    config_source = Path(args.config)
    if not config_source.is_file():
        _error(
            f"配置不存在: {config_source}",
            "板模板在 configs/*.omcfg；新项目请先复制一份模板并改 project.name/id/ble_names",
        )
        return EXIT_ENVIRONMENT
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
    except OSError as exc:
        _error(f"{config_source}: 读取失败: {exc}", "确认文件未被占用、当前用户可读")
        return EXIT_ENVIRONMENT

    if args.name is not None:
        name = args.name.strip()
        if not name:
            _error("--name 不能为空", "新工程名会写入 iPROJECT_NAME，例如 --name KC536X")
            return EXIT_VALIDATION
        project = model.project(config)
        project["name"] = name
        if not project.get("ble_names"):
            project["ble_names"] = [f"{name} Bt1", f"{name} Bt2"]
        config_payload = (model.dump_config(config) + "\n").encode("utf-8")
    else:
        config_payload = config_source.read_bytes()

    report = validate.validate_config(config)
    _print_report(report, config)
    if not report.ok:
        return EXIT_VALIDATION

    try:
        copied = newproject.copy_skeleton(source, target)
        config_target = model.default_config_path(target)
        config_target.parent.mkdir(parents=True, exist_ok=True)
        config_target.write_bytes(config_payload)
        rewrites = newproject.rewrite_identity(target, config)
        _init_project(target, config_target, force=False, announce_next=False)
        outputs = generator.build_outputs(config, target)
        code, _manifest = _apply_outputs(target, outputs, "omcfg_new")
        if code != EXIT_OK:
            raise sdk.TargetError("生成内容写入失败")
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
    newproject.remove_backups(target)

    print(f"新工程: {target}（复制 {copied} 个文件）")
    print(f"不复制: {newproject.NOT_COPIED_SUMMARY}")
    if records:
        print("标识改写（源 -> 新）:")
        for record in records:
            print(f"  {record.render()}")
    else:
        print("标识改写: 与源工程一致，未改写")
    print("生成后的 .omcfg_bak_* 已清理（新工程基线不携带历史备份）")
    print(f"下一步: python -m omcfg check {config_target}")
    project = uvprojx.project_path(config, target)
    if project:
        print(f"编译: UV4 -r {project} -o build.log")
    return EXIT_OK


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
            "  python -m omcfg new --sdk <源SDK> --target <新工程目录>"
            " --config configs\\KC536.omcfg\n"
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
        dest="command", required=True, metavar="{init,check,gen,new,rollback}"
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
        help="从源 SDK 一键生成可编译的新工程（复制 → 改标识 → init → gen）",
        description=(
            "复制源 SDK 骨架（剔除 out/、.dep、.omcfg_bak_* 等产物），按配置改写 "
            "iPROJECT_NAME、iPROJECT_ID_L/H、iREAL_VERSION_ID 与 BLE 广播名，"
            "完成 init 与 gen --apply。"
        ),
        epilog=(
            "示例:\n"
            "  copy configs\\KC536.omcfg myboard.omcfg  :: 改 project.name/id/ble_names\n"
            "  python -m omcfg new --sdk E:\\SDK\\KC536 --target D:\\work\\MyBoard "
            "--config myboard.omcfg\n"
            "目标路径必须不存在；命令不会覆盖任何现有目录。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    new.add_argument("--sdk", required=True, metavar="DIR", help="源 SDK 根目录（不修改源工程）")
    new.add_argument("--target", required=True, metavar="DIR", help="新工程目录（必须不存在）")
    new.add_argument(
        "--config", required=True, metavar="FILE", help="新工程配置（含 project.name/id/ble_names）"
    )
    new.add_argument(
        "--name",
        metavar="NAME",
        help="覆盖 project.name；未配置 ble_names 时按 '<NAME> Bt1/Bt2' 生成",
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
    parser.error("未知命令")
    return EXIT_ENVIRONMENT
