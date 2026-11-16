"""工程初始化：检测 OMCFG 标记状态，安装配置并插入标记块。

CLI 的 init 与 GUI 的初始化按钮共用这一份实现，避免两套逻辑漂移。
"""

from __future__ import annotations

from pathlib import Path

from . import model
from .generate import generator
from .targets import sdk
from .transaction import FileTransaction

HEADER_BLOCKS = generator.BLOCKS_H
SOURCE_BLOCKS = (generator.BLOCK_C, sdk.SLEEP_BLOCK)


def _block_problem(path: Path, text: str, block: str) -> str | None:
    begin = text.count(sdk.marker_begin(block))
    end = text.count(sdk.marker_end(block))
    if begin == 1 and end == 1:
        return None
    if begin and end:
        return f"{path} 的标记块 '{block}' 不完整（BEGIN {begin} 次，END {end} 次）"
    return f"{path} 缺少 OMCFG 标记块 '{block}'"


def _user_code_problem(path: Path, text: str, name: str) -> str | None:
    begin = text.count(sdk.user_code_begin(name))
    end = text.count(sdk.user_code_end(name))
    if begin == 1 and end == 1:
        return None
    return f"{path} 的 USER CODE 保护区 '{name}' 缺失或不完整（BEGIN {begin}，END {end}）"


def missing_markers(root: Path | str, require_config: bool = True) -> list[str]:
    """列出阻止 gen 工作的缺失项；空列表即已初始化。"""
    root_path = Path(root)
    config_path = model.default_config_path(root_path)
    problems: list[str] = []
    if require_config and not config_path.is_file():
        problems.append(f"工程尚无 project.omcfg（初始化后写入 {config_path}）")

    checks = (
        (sdk.USER_CONFIG_H, HEADER_BLOCKS, sdk.USER_CODE_H),
        (sdk.USER_CONFIG_C, SOURCE_BLOCKS, sdk.USER_CODE_C),
    )
    for relative, blocks, user_code in checks:
        path = root_path / relative
        if not path.is_file():
            problems.append(f"缺少文件 {path}")
            continue
        text = sdk.read_source(path).text
        if sdk.legacy_markers(text):
            problems.append(f"{path} 仍含旧 OM_PINMUX_GENERATED 标记，需人工迁移")
            continue
        for block in blocks:
            problem = _block_problem(path, text, block)
            if problem:
                problems.append(problem)
        problem = _user_code_problem(path, text, user_code)
        if problem:
            problems.append(problem)

    features = root_path / sdk.BOARD_FEATURES_H
    if features.is_file():
        text = sdk.read_source(features).text
        problem = _user_code_problem(features, text, sdk.USER_CODE_FEATURES)
        if problem:
            problems.append(problem)
    return problems


def is_initialized(root: Path | str) -> bool:
    return not missing_markers(root)


def _anchor_index(lines: list[str], needle: str, starts: bool, path: Path, block: str) -> int:
    hits = [i for i, line in enumerate(lines) if (line.startswith(needle) if starts else line.strip() == needle)]
    if len(hits) != 1:
        raise sdk.TargetError(f"{path} 中定位 '{needle}' 命中 {len(hits)} 次，拒绝插入 '{block}' 标记")
    return hits[0]


def _insert_block(text: str, path: Path, block: str, start_needle: str, end_needle: str, starts: bool = True) -> str:
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
    text = _insert_block(text, path, "project_ids", "#define iPROJECT_ID_H", "#define iPROJECT_ID_L")
    text = _insert_block(text, path, "project_version", "#define iREAL_VERSION_ID", "#define iREAL_VERSION_ID")
    text = _insert_block(text, path, "project_names", "#define iCONSUMER_NAME", "#define iPROJECT_NAME")
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


def init_project(
    root: Path | str,
    config_source: Path | str,
    force: bool = False,
    verbose: bool = True,
    announce_next: bool = True,
    tx: "FileTransaction | None" = None,
) -> Path | None:
    """安装配置并插入标记；成功返回 manifest 路径（无变化时 None）。

    CLI 与 GUI 共用。配置校验由调用方先做，这里只负责文件落盘与标记。
    """
    root_path = Path(root)
    source = Path(config_source)
    owns_tx = tx is None
    transaction = tx if tx is not None else FileTransaction.create(root_path, "omcfg_init")
    config_target = model.default_config_path(root_path)
    if config_target.is_file():
        if config_target.read_bytes() != source.read_bytes():
            if not force:
                raise sdk.TargetError(f"{config_target} 已存在且内容不同；确认覆盖请加 --force")
        elif verbose:
            print(f"配置已存在且一致: {config_target}")
    if not config_target.is_file() or config_target.read_bytes() != source.read_bytes():
        transaction.write_bytes(config_target, source.read_bytes(), "安装唯一配置源")

    for relative, handler, user_code in (
        (sdk.USER_CONFIG_H, _init_header, sdk.USER_CODE_H),
        (sdk.USER_CONFIG_C, _init_source, sdk.USER_CODE_C),
    ):
        path = root_path / relative
        source_file = sdk.read_source(path)
        if sdk.legacy_markers(source_file.text):
            raise sdk.TargetError(f"{path} 仍含旧 OM_PINMUX_GENERATED 标记，请先人工迁移")
        before = source_file.text
        after = handler(before, path)
        if sdk.strip_marker_lines(after) != sdk.strip_marker_lines(before):
            raise sdk.TargetError(f"{path} 插入标记后正文发生变化，已中止")
        after = sdk.append_user_code(after, user_code, path)
        if after != before:
            sdk.ensure_encodable(after, source_file.encoding)
            transaction.write_bytes(
                path,
                sdk.SourceFile(path, after, source_file.encoding, source_file.newline, source_file.bom).render(),
                "插入 OMCFG/USER CODE 标记",
            )
            if verbose:
                print(f"已插入标记: {path}")
        elif verbose:
            print(f"标记已存在: {path}")

    for relative, user_code in ((sdk.BOARD_FEATURES_H, sdk.USER_CODE_FEATURES),):
        path = root_path / relative
        if not path.is_file():
            continue
        source_file = sdk.read_source(path)
        if sdk.legacy_markers(source_file.text):
            raise sdk.TargetError(f"{path} 仍含旧 OM_PINMUX_GENERATED 标记，请先人工迁移")
        after = sdk.append_user_code(source_file.text, user_code, path)
        if after != source_file.text:
            sdk.ensure_encodable(after, source_file.encoding)
            transaction.write_bytes(
                path,
                sdk.SourceFile(path, after, source_file.encoding, source_file.newline, source_file.bom).render(),
                "补 USER CODE 保护区",
            )
            if verbose:
                print(f"已补 USER CODE 保护区: {path}")

    if transaction.actions:
        if owns_tx:
            manifest = transaction.commit()
            if verbose:
                print(f"事务 manifest: {manifest}")
        else:
            manifest = None
            if verbose:
                print("标识并入外部事务（caller 统一 commit）")
    else:
        manifest = None
        if verbose:
            print("没有文件变化")
    if verbose and announce_next:
        print(f"下一步: python -m omcfg gen --sdk {root_path} --dry-run")
    return manifest
