"""可审计的文件事务：备份、manifest、回滚。

由旧 operations.py 平移，增加编码/换行保持与二进制写入。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ActionResult:
    status: str
    path: str
    detail: str
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
    target_root: Path
    backup_root: Path
    operation: str
    actions: list[ActionResult] = field(default_factory=list)
    entries: list[dict] = field(default_factory=list)

    @classmethod
    def create(cls, target_root: str | Path, operation: str, stamp: str | None = None) -> "FileTransaction":
        root = Path(target_root).resolve()
        stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_root = root / f".omcfg_bak_{stamp}"
        while backup_root.exists():
            stamp += "_1"
            backup_root = root / f".omcfg_bak_{stamp}"
        return cls(root, backup_root, operation)

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
        self.entries.append(
            {
                "path": relative,
                "existed": existed,
                "before_sha1": sha1_file(target),
                "backup": backup.relative_to(self.backup_root).as_posix() if existed else "",
            }
        )

    def write_bytes(self, path: str | Path, data: bytes, detail: str = "已写入事务") -> ActionResult:
        target = Path(path).resolve()
        self.backup(target)
        before = sha1_file(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        after = sha1_file(target)
        result = ActionResult(
            "changed" if before != after else "already_compliant",
            str(target),
            detail,
            before_sha1=before,
            after_sha1=after,
            verified=after is not None,
        )
        self.actions.append(result)
        return result

    def write_text(
        self, path: str | Path, text: str, encoding: str = "utf-8", newline: str | None = None
    ) -> ActionResult:
        target = Path(path)
        if newline is None:
            newline = "\n"
            if target.is_file() and b"\r\n" in target.read_bytes():
                newline = "\r\n"
        body = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
        return self.write_bytes(path, body.encode(encoding))

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

    def manifest_path(self) -> Path:
        return self.backup_root / "manifest.json"


def rollback_manifest(manifest_path: str | Path) -> dict:
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
    return {
        "ok": True,
        "manifest": str(manifest),
        "target_root": str(root),
        "restored": restored,
    }
