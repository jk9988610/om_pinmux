"""内置 SDK 基线：定位、完整性检查、按工程名派生身份与配置。

基线只此一份：`baseline/sdk` 是清理后的 SDK 源码，`baseline/project.omcfg` 是
其板级配置。`new` 从这里生成，不再依赖外部 SDK 路径。
"""

from __future__ import annotations

import binascii
import hashlib
import json
from pathlib import Path

from . import model
from .targets import sdk

ROOT = Path(__file__).resolve().parent.parent / "baseline"
SDK_DIR = ROOT / "sdk"
CONFIG_PATH = ROOT / "project.omcfg"
META_PATH = ROOT / "META.json"

# BLE 广播名是 "<NAME> Bt2"，给 28 字符上限留 4 个字符余量。
MAX_NAME_LENGTH = 24
INVALID_NAME_CHARS = set('/\\:*?"<>|\t\r\n')

BASELINE_FILES = (
    "projects/mouse_demo/periph/user_config.h",
    "projects/mouse_demo/periph/user_config.c",
    "projects/mouse_demo/keil5/SE71M.uvprojx",
)


class BaselineError(RuntimeError):
    """内置基线缺失或不可用。"""


def name_problem(name: str) -> str | None:
    """返回工程名的问题说明；合法时返回 None。"""
    text = name.strip()
    if not text:
        return "工程名不能为空"
    if len(text) > MAX_NAME_LENGTH:
        return f"工程名过长（{len(text)} 字符），上限 {MAX_NAME_LENGTH}"
    bad = sorted({char for char in text if char in INVALID_NAME_CHARS})
    if bad:
        return f"工程名不能包含 {' '.join(repr(char) for char in bad)}"
    if text.startswith("."):
        return "工程名不能以点开头（会被当成隐藏目录或相对路径）"
    return None


def derive_id(name: str) -> str:
    """按工程名派生 16 位项目号；避开 0x0000。"""
    number = binascii.crc32(name.encode("utf-8")) & 0xFFFF
    return f"0x{number or 1:04X}"


def config_for_name(name: str, config_path: Path | str | None = None) -> dict:
    """读取基线配置，写入工程名、派生 ID 与 BLE 广播名。"""
    path = Path(config_path) if config_path else CONFIG_PATH
    config = model.load_config(path)
    project = model.project(config)
    project["name"] = name
    project["ble_names"] = [f"{name} Bt1", f"{name} Bt2"]
    base_id = model.project_id(config)
    project["id"] = {
        "low": derive_id(name),
        "high": base_id.get("high") or "0x071",
        "version": 1,
    }
    return config


def check(sdk_dir: Path | str | None = None, config_path: Path | str | None = None,
          meta_path: Path | str | None = None) -> list[str]:
    """列出内置基线的问题；空列表即可用。"""
    root = Path(sdk_dir) if sdk_dir else SDK_DIR
    config = Path(config_path) if config_path else CONFIG_PATH
    meta = Path(meta_path) if meta_path else META_PATH
    problems: list[str] = []
    for relative in BASELINE_FILES:
        if not (root / relative).is_file():
            problems.append(f"缺少 {root / relative}")
    if not config.is_file():
        problems.append(f"缺少基线配置 {config}")
    if not meta.is_file():
        problems.append(f"缺少基线清单 {meta}")
    return problems


def resolve(sdk_dir: Path | str | None = None, config_path: Path | str | None = None,
            meta_path: Path | str | None = None) -> tuple[Path, Path]:
    """校验并返回 (SDK 目录, 基线配置)；不完整时抛 BaselineError。"""
    root = Path(sdk_dir) if sdk_dir else SDK_DIR
    config = Path(config_path) if config_path else CONFIG_PATH
    problems = check(root, config, meta_path)
    if problems:
        raise BaselineError(
            "内置 SDK 基线不完整：\n  " + "\n  ".join(problems) + "\n"
            "  说明: 基线随工具仓库分发，请确认 baseline/ 未被删改；"
            "重建方式见 baseline/META.json 的 source_sdk。"
        )
    return root, config


def tree_digest(root: Path | str) -> str:
    """按相对路径 + 文件 SHA256 计算文件树摘要，用于基线完整性校验。"""
    entries: list[str] = []
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append(f"{relative}\0{digest}")
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def file_digest(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def meta(sdk_dir: Path | str | None = None, meta_path: Path | str | None = None) -> dict:
    path = Path(meta_path) if meta_path else META_PATH
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def verify_meta(sdk_dir: Path | str | None = None, config_path: Path | str | None = None,
                meta_path: Path | str | None = None) -> list[str]:
    """比对 META.json 与当前基线内容；返回差异说明。"""
    root = Path(sdk_dir) if sdk_dir else SDK_DIR
    config = Path(config_path) if config_path else CONFIG_PATH
    data = meta(root, meta_path)
    problems: list[str] = []
    actual_files = sum(1 for path in root.rglob("*") if path.is_file())
    if data.get("file_count") != actual_files:
        problems.append(f"文件数 {actual_files} != META {data.get('file_count')}")
    if data.get("tree_sha256") and data["tree_sha256"] != tree_digest(root):
        problems.append("SDK 文件树摘要与 META.json 不一致")
    if data.get("config_sha256") and data["config_sha256"] != file_digest(config):
        problems.append("baseline/project.omcfg 摘要与 META.json 不一致")
    return problems


def ensure_ready(sdk_dir: Path | str | None = None) -> tuple[Path, Path]:
    """new 命令入口：基线完整且 SDK 结构合法。"""
    root, config = resolve(sdk_dir)
    try:
        sdk.resolve_sdk(root)
    except sdk.TargetError as exc:
        raise BaselineError(f"内置基线不是完整 SDK：{exc}") from exc
    return root, config
