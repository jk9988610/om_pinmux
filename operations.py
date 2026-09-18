"""Auditable file transaction primitives for SDK-changing operations."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass
class ActionResult:
    """A normalized outcome for a patch, copy, or generated-file operation."""

    status: str
    path: str
    detail: str
    match_count: int = 0
    before_sha1: str | None = None
    after_sha1: str | None = None
    verified: bool = False

    @property
    def ok(self) -> bool:
        return self.status in {"changed", "already_compliant", "skipped"}

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "path": self.path,
            "detail": self.detail,
            "match_count": self.match_count,
            "before_sha1": self.before_sha1,
            "after_sha1": self.after_sha1,
            "verified": self.verified,
            "ok": self.ok,
        }


def sha1_file(path: str | Path) -> str | None:
    target = Path(path)
    if not target.is_file():
        return None
    digest = hashlib.sha1()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class FileTransaction:
    """Back up changed files and write a manifest that can restore the operation."""

    target_root: Path
    backup_root: Path
    operation: str
    actions: list[ActionResult] = field(default_factory=list)
    entries: list[dict] = field(default_factory=list)

    @classmethod
    def create(cls, target_root: str | Path, operation: str, stamp: str | None = None) -> "FileTransaction":
        root = Path(target_root).resolve()
        stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        return cls(root, root / f"_{operation}_bak_{stamp}", operation)

    def _relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.target_root).as_posix()

    def backup(self, path: str | Path) -> None:
        target = Path(path).resolve()
        relative = self._relative(target)
        if any(entry["path"] == relative for entry in self.entries):
            return
        existed = target.is_file()
        backup = self.backup_root / relative
        if existed:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        self.entries.append({
            "path": relative,
            "existed": existed,
            "before_sha1": sha1_file(target),
            "backup": backup.relative_to(self.backup_root).as_posix() if existed else "",
        })

    def write_text(self, path: str | Path, text: str) -> ActionResult:
        target = Path(path).resolve()
        self.backup(target)
        before = sha1_file(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        after = sha1_file(target)
        result = ActionResult("changed" if before != after else "already_compliant", str(target), "已写入事务", before_sha1=before, after_sha1=after, verified=after is not None)
        self.actions.append(result)
        return result

    def copy_file(self, source: str | Path, path: str | Path) -> ActionResult:
        target = Path(path).resolve()
        self.backup(target)
        before = sha1_file(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        after = sha1_file(target)
        result = ActionResult("changed" if before != after else "already_compliant", str(target), f"复制自 {source}", before_sha1=before, after_sha1=after, verified=after is not None)
        self.actions.append(result)
        return result

    def manifest_path(self) -> Path:
        return self.backup_root / "manifest.json"

    def commit(self) -> Path:
        self.backup_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "om6239-file-transaction/v1",
            "operation": self.operation,
            "created": datetime.now().isoformat(timespec="seconds"),
            "target_root": str(self.target_root),
            "backup_root": str(self.backup_root),
            "entries": self.entries,
            "actions": [action.as_dict() for action in self.actions],
        }
        self.manifest_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self.manifest_path()


def rollback_manifest(manifest_path: str | Path) -> dict:
    """Restore files recorded by a committed transaction manifest."""
    manifest = Path(manifest_path).resolve()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("schema") != "om6239-file-transaction/v1":
        raise ValueError("不支持的事务 manifest")
    root = Path(payload["target_root"])
    backup_root = Path(payload["backup_root"])
    restored: list[str] = []
    for entry in reversed(payload.get("entries", [])):
        target = root / entry["path"]
        if entry.get("existed"):
            backup = backup_root / entry["backup"]
            if not backup.is_file():
                raise FileNotFoundError(f"缺少备份文件: {backup}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
        elif target.exists():
            target.unlink()
        restored.append(str(target))
    return {"ok": True, "manifest": str(manifest), "restored": restored}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="回滚 OM6239 文件写入事务")
    parser.add_argument("--rollback", required=True, help="事务 manifest.json 路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)
    try:
        result = rollback_manifest(args.rollback)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"ok": False, "message": str(exc)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("message") or f"已恢复 {len(result.get('restored', []))} 个文件")
    return 0 if result.get("ok") else 4


if __name__ == "__main__":
    raise SystemExit(main())
