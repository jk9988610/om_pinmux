"""Unified command-line entry point for OM6239 PinMux services."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import board_pack
import golden_diff
import operations
import port_apply
import synth_golden
import validation

EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_ENVIRONMENT = 2
EXIT_WRITE_FAILURE = 3
EXIT_ROLLED_BACK = 4


def _print_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return
    print(result.get("message") or json.dumps(result, ensure_ascii=False, indent=2, default=str))


def _exit_code(result: dict[str, Any], write_operation: bool = False) -> int:
    if result.get("ok"):
        return EXIT_OK
    if result.get("rolled_back"):
        return EXIT_ROLLED_BACK
    if write_operation:
        return EXIT_WRITE_FAILURE
    if result.get("validation") or result.get("error_count") is not None:
        return EXIT_VALIDATION
    return EXIT_ENVIRONMENT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="om-pinmux", description="OM6239 PinMux 工具统一命令行")
    sub = parser.add_subparsers(dest="command", required=True)

    validate_cmd = sub.add_parser("validate", help="校验板描述")
    validate_cmd.add_argument("--board", default="", help="板名或 JSON 路径")
    validate_cmd.add_argument("--all", action="store_true", help="校验所有 boards/*.json")
    validate_cmd.add_argument("--json", action="store_true")

    synth_cmd = sub.add_parser("synth", help="生成宏观金机")
    synth_cmd.add_argument("--board", default="BD319")
    synth_cmd.add_argument("--pictures", default="")
    synth_cmd.add_argument("--out", default="")
    synth_cmd.add_argument("--json", action="store_true")

    apply_cmd = sub.add_parser("apply", help="应用板级包")
    apply_cmd.add_argument("--target", required=True)
    apply_cmd.add_argument("--board", default="BD319")
    apply_cmd.add_argument("--donor", default="")
    apply_cmd.add_argument("--policy-json", default="")
    apply_cmd.add_argument("--dry-run", action="store_true")
    apply_cmd.add_argument("--json", action="store_true")

    port_cmd = sub.add_parser("port", help="按金机执行 port_apply")
    port_cmd.add_argument("--target", required=True)
    port_cmd.add_argument("--golden", required=True)
    port_cmd.add_argument("--board", default="CH04")
    port_cmd.add_argument("--report-dir", default="")
    port_cmd.add_argument("--dry-run", action="store_true")
    port_cmd.add_argument("--json", action="store_true")

    compare_cmd = sub.add_parser("compare", help="输出金机关注文件清单")
    compare_cmd.add_argument("--golden", required=True)
    compare_cmd.add_argument("--target", required=True)
    compare_cmd.add_argument("--json", action="store_true")

    rollback_cmd = sub.add_parser("rollback", help="按 manifest 回滚写入事务")
    rollback_cmd.add_argument("--manifest", required=True)
    rollback_cmd.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            if not args.all and not args.board:
                parser.error("validate 需要 --board 或 --all")
            if args.all:
                results = [validation.validate_board_file(path) for path in sorted(validation.BOARDS_DIR.glob("*.json"))]
                result = {"ok": all(item["ok"] for item in results), "results": results}
            else:
                path = args.board
                result = validation.validate_board_file(path if path.endswith(".json") else validation.BOARDS_DIR / f"{path}.json")
            _print_result(result, args.json)
            return _exit_code(result)
        if args.command == "synth":
            result = synth_golden.synth_board(args.board, args.pictures, args.out)
            _print_result(result, args.json)
            return _exit_code(result, write_operation=True)
        if args.command == "apply":
            policy = json.loads(args.policy_json) if args.policy_json else None
            result = board_pack.apply_board_pack(args.target, args.board, policy, args.donor, dry_run=args.dry_run)
            _print_result(result, args.json)
            return _exit_code(result, write_operation=not args.dry_run)
        if args.command == "port":
            result = port_apply.run(args.target, args.golden, args.board, args.dry_run, args.report_dir)
            _print_result(result, args.json)
            return _exit_code(result, write_operation=not args.dry_run)
        if args.command == "compare":
            golden = port_apply.resolve_sdk(args.golden)
            target = port_apply.resolve_sdk(args.target)
            result = golden_diff.inventory_focus(golden, target)
            _print_result(result, args.json)
            return _exit_code(result)
        result = operations.rollback_manifest(args.manifest)
        _print_result(result, args.json)
        return EXIT_OK
    except json.JSONDecodeError as exc:
        _print_result({"ok": False, "message": f"JSON 参数无效: {exc}"}, getattr(args, "json", False))
        return EXIT_ENVIRONMENT
    except (OSError, ValueError, FileNotFoundError) as exc:
        _print_result({"ok": False, "message": str(exc)}, getattr(args, "json", False))
        return EXIT_ENVIRONMENT


if __name__ == "__main__":
    raise SystemExit(main())
