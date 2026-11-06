"""omcfg 命令行：init / check / gen / rollback。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import model, validate
from .generate import generator
from .targets import sdk
from .transaction import FileTransaction, rollback_manifest

EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_ENVIRONMENT = 2
EXIT_WRITE = 3
EXIT_ROLLED_BACK = 4


def _read_config(path: Path) -> dict:
    return model.load_config(path)


def _print_report(report: validate.Report, config: dict) -> None:
    for issue in report.errors + report.warnings:
        print(issue.render())
    print(validate.summary(config, report))


def cmd_check(args: argparse.Namespace) -> int:
    paths: list[Path] = [Path(item) for item in args.paths]
    if args.all:
        paths = sorted(Path(args.all).glob("*.omcfg"))
    if not paths:
        print("没有可检查的配置；用 check <file...> 或 check --all configs", file=sys.stderr)
        return EXIT_ENVIRONMENT
    failed = False
    for path in paths:
        print(f"== {path} ==")
        try:
            config = _read_config(path)
        except (OSError, ValueError, Exception) as exc:  # yaml 解析错误
            print(f"[ERROR] {path}: 读取失败: {exc}", file=sys.stderr)
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
    if starts:
        end = _anchor_index(lines[start:], end_needle, starts, path, block) + start
    else:
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
    return _insert_block(
        text,
        path,
        generator.BLOCK_C,
        "const user_gpio_config_t gpio_config_table[] = {",
        "};",
        starts=False,
    )


def cmd_init(args: argparse.Namespace) -> int:
    try:
        root = sdk.resolve_sdk(args.sdk)
        config_source = Path(args.config)
        if not config_source.is_file():
            raise sdk.TargetError(f"配置不存在: {config_source}")
        config = _read_config(config_source)
        report = validate.validate_config(config)
        if not report.ok:
            _print_report(report, config)
            return EXIT_VALIDATION
        transaction = FileTransaction.create(root, "omcfg_init")
        config_target = model.default_config_path(root)
        if config_target.is_file():
            if config_target.read_bytes() != config_source.read_bytes():
                if not args.force:
                    raise sdk.TargetError(f"{config_target} 已存在且内容不同；确认覆盖请加 --force")
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
                    sdk.SourceFile(
                        path, after, source.encoding, source.newline, source.bom
                    ).render(),
                    "插入 OMCFG/USER CODE 标记",
                )
                print(f"已插入标记: {path}")
            else:
                print(f"标记已存在: {path}")

        for relative, user_code in (
            (sdk.BOARD_FEATURES_H, sdk.USER_CODE_FEATURES),
            (sdk.SLEEP_TEMPLATE, sdk.USER_CODE_SLEEP),
        ):
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
                    sdk.SourceFile(
                        path, after, source.encoding, source.newline, source.bom
                    ).render(),
                    "补 USER CODE 保护区",
                )
                print(f"已补 USER CODE 保护区: {path}")
        if transaction.actions:
            manifest = transaction.commit()
            print(f"事务 manifest: {manifest}")
        else:
            print("没有文件变化")
        print(f"下一步: python -m omcfg gen --config {config_target} --sdk {root} --dry-run")
        return EXIT_OK
    except sdk.TargetError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT
    except OSError as exc:
        print(f"[ERROR] 写入失败: {exc}", file=sys.stderr)
        return EXIT_WRITE


def cmd_gen(args: argparse.Namespace) -> int:
    try:
        root = sdk.resolve_sdk(args.sdk)
        config_path = Path(args.config) if args.config else model.default_config_path(root)
        if not config_path.is_file():
            raise sdk.TargetError(f"配置不存在: {config_path}")
        config = _read_config(config_path)
    except sdk.TargetError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT
    except Exception as exc:
        print(f"[ERROR] 读取配置失败: {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT

    report = validate.validate_config(config)
    _print_report(report, config)
    if not report.ok:
        return EXIT_VALIDATION

    try:
        outputs = generator.build_outputs(config, root)
    except sdk.TargetError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT

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

    transaction = FileTransaction.create(root, "omcfg_apply")
    try:
        for item in changed:
            transaction.write_bytes(item.path, item.render(), "按标记块写入生成内容")
        manifest = transaction.commit()
    except OSError as exc:
        print(f"[ERROR] 写入失败，回滚备份: {exc}", file=sys.stderr)
        for entry in transaction.entries:
            target = transaction.target_root / entry["path"]
            backup = transaction.backup_root / entry["backup"] if entry.get("backup") else None
            if entry.get("existed") and backup and backup.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(backup.read_bytes())
            elif not entry.get("existed") and target.exists():
                target.unlink()
        return EXIT_WRITE
    print(f"已写入 {len(changed)} 个文件；manifest: {manifest}")
    return EXIT_OK


def cmd_rollback(args: argparse.Namespace) -> int:
    try:
        result = rollback_manifest(args.manifest)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] 回滚失败: {exc}", file=sys.stderr)
        return EXIT_WRITE
    print(f"已恢复 {len(result['restored'])} 个文件: {result['manifest']}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omcfg", description="OM6239 项目配置生成器（P1）")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="安装 project.omcfg 并插入 OMCFG 标记块（一次性）")
    init.add_argument("--config", required=True)
    init.add_argument("--sdk", required=True)
    init.add_argument("--force", action="store_true", help="允许覆盖内容不同的 project.omcfg")

    check = sub.add_parser("check", help="校验配置")
    check.add_argument("paths", nargs="*")
    check.add_argument("--all", metavar="DIR", help="检查目录下所有 *.omcfg")

    gen = sub.add_parser("gen", help="生成 4 个文件；默认 dry-run")
    gen.add_argument("--config")
    gen.add_argument("--sdk", required=True)
    gen.add_argument("--dry-run", action="store_true", help="只打印 diff（默认行为）")
    gen.add_argument("--apply", action="store_true", help="真正写入")

    rollback = sub.add_parser("rollback", help="按 manifest 回滚")
    rollback.add_argument("--manifest", required=True)
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
    if args.command == "rollback":
        return cmd_rollback(args)
    parser.error("未知命令")
    return EXIT_ENVIRONMENT
