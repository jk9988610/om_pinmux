# -*- coding: utf-8 -*-
"""LEDC 文件注入器：从 source_pool 注入 4 个 LEDC 文件到工作区。

所有 LEDC 工程（516/HTS092/524/CH04）的 ledc.c 都引用了 key_io.h / sensor.h /
lvd.h / led.h / flash_process.h 和 key_io_scan()。这些在 KC536 基线里都有，
所以不需要清洗。如果未来 KC536 版本删除了某依赖，注入器会自动注释相关行。
"""

import os
import re
import shutil

# LEDC 需要的 4 个文件（按 16 个工程统计，ledc.c/h 100%，ledc_mode.c/h 15/16）
LEDC_FILES = [
    "projects/mouse_demo/periph/ledc.c",
    "projects/mouse_demo/periph/ledc.h",
    "projects/mouse_demo/periph/ledc_mode.c",
    "projects/mouse_demo/periph/ledc_mode.h",
]

# 清洗规则：只在目标工程缺失依赖时生效
# 每条：(依赖检测文件相对路径, 依赖检测正则, 目标文件相对路径, 清洗正则, 替换文本)
SANITIZE_RULES = [
    (
        "projects/mouse_demo/periph/key_io.c",
        r"void\s+key_io_scan\s*\(",
        "projects/mouse_demo/periph/ledc.c",
        r"^(\s*)key_io_scan\(\);(\s*)$",
        r"// key_io_scan();  // [OMCFG-AUTO] 该工程 key_io.c 无 key_io_scan() 定义，已注释",
    ),
]


def _has_dependency(workspace, rel_path, pattern):
    p = os.path.join(workspace, rel_path.replace("/", os.sep))
    if not os.path.isfile(p):
        return False
    t = open(p, encoding="utf-8", errors="replace").read()
    return bool(re.search(pattern, t))


def sanitize(workspace):
    """检查依赖，缺失则注释相关行。返回清洗记录列表。"""
    changes = []
    for dep_file, dep_pat, target_file, san_pat, repl in SANITIZE_RULES:
        if _has_dependency(workspace, dep_file, dep_pat):
            continue
        tp = os.path.join(workspace, target_file.replace("/", os.sep))
        if not os.path.isfile(tp):
            continue
        t = open(tp, encoding="utf-8", errors="replace").read()
        new_t, n = re.subn(san_pat, repl, t, flags=re.M)
        if n > 0:
            open(tp, "w", encoding="utf-8").write(new_t)
            changes.append({"file": target_file, "lines_affected": n, "reason": "missing " + dep_file})
    return changes


def update_uvprojx(workspace):
    """更新 uvprojx：
    - periph 组加 ledc.c / ledc_mode.c
    - driver 组加 drv_ledc.c（KC536 driver 组原本没有）

    Returns: {"ok": bool, "added": [...], "skipped": [...], "reason": str}
    """
    uv = os.path.join(workspace, "projects", "mouse_demo", "keil5", "SE71M.uvprojx")
    if not os.path.isfile(uv):
        return {"ok": False, "reason": "uvprojx 不存在", "added": [], "skipped": []}

    raw = open(uv, "rb").read()
    bom = raw[:3] == b"\xef\xbb\xbf"
    enc = "utf-8-sig" if bom else "utf-8"
    text = raw.decode(enc, errors="replace")
    nl = "\r\n" if "\r\n" in text else "\n"

    added, skipped = [], []

    def _insert_file(group_name, file_name, file_type, file_path):
        """在指定组 </Files> 前插入一个 <File> 块。返回 True/False。"""
        nonlocal text
        if "<FileName>" + file_name + "</FileName>" in text:
            skipped.append(file_name)
            return False
        # 定位组
        pat = r"(<GroupName>" + re.escape(group_name) + r"</GroupName>\s*<Files>.*?)(\s*</Files>)"
        mm = re.search(pat, text, re.DOTALL)
        if not mm:
            return False
        indent = " " * 12
        block = (
            indent
            + "<File>"
            + nl
            + indent
            + "  <FileName>"
            + file_name
            + "</FileName>"
            + nl
            + indent
            + "  <FileType>"
            + str(file_type)
            + "</FileType>"
            + nl
            + indent
            + "  <FilePath>"
            + file_path
            + "</FilePath>"
            + nl
            + indent
            + "</File>"
        )
        insert_pos = mm.start(2)
        text = text[:insert_pos] + nl + block + text[insert_pos:]
        added.append(file_name)
        return True

    # 1. periph 组：ledc.c, ledc_mode.c
    _insert_file("periph", "ledc.c", 1, "..\\periph\\ledc.c")
    _insert_file("periph", "ledc_mode.c", 1, "..\\periph\\ledc_mode.c")

    # 2. driver 组：drv_ledc.c
    # 先探测 driver 组里已有文件路径前缀（通常是 ..\..\..\hal\driver\common\drv_xxx.c）
    drv_path = "..\\..\\..\\hal\\driver\\om6239\\drv_ledc.c"
    mm = re.search(r"<GroupName>driver</GroupName>\s*<Files>(.*?)</Files>", text, re.DOTALL)
    if mm:
        # 从已有文件推前缀
        fm = re.search(r"<FilePath>([^<]+)</FilePath>", mm.group(1))
        if fm:
            sample = fm.group(1)
            # 例如 ..\..\..\hal\driver\common\drv_gpio.c → 取 ..\..\..\hal\driver\ 前缀
            if "drv_" in sample and "\\" in sample:
                parts = sample.rsplit("\\", 1)
                if len(parts) == 2 and parts[0].endswith("common"):
                    base = parts[0][: -len("common")]
                    drv_path = base + "om6239\\drv_ledc.c"
    _insert_file("driver", "drv_ledc.c", 1, drv_path)

    if not added:
        return {"ok": True, "added": [], "skipped": skipped, "reason": "已存在"}

    open(uv, "w", encoding=enc).write(text)
    return {"ok": True, "added": added, "skipped": skipped, "reason": ""}


def enable_ledc_rte(workspace):
    """把工作区 projects/mouse_demo/config/RTE_om6239.h 的 RTE_LEDC 改为 1。

    KC536 的 RTE_LEDC=0，导致 drv_ledc.h 里 ledc_config_t / drv_ledc_* 被 #if 跳过。
    注入 LEDC 文件后必须同步打开这个开关。
    """
    import re as _re

    candidates = [
        os.path.join(workspace, "projects", "mouse_demo", "config", "RTE_om6239.h"),
        os.path.join(workspace, "hal", "driver", "config_template", "RTE_om6239.h"),
    ]
    changed = []
    for rte in candidates:
        if not os.path.isfile(rte):
            continue
        raw = open(rte, "rb").read()
        bom = raw[:3] == b"\xef\xbb\xbf"
        enc = "utf-8-sig" if bom else "utf-8"
        text = raw.decode(enc, errors="replace")
        # 精确匹配 #define RTE_LEDC 后面的值（保留前导空白和尾部注释）
        new_text, n = _re.subn(
            r"(#define\s+RTE_LEDC\s+)0(\s*)",
            r"\g<1>1\g<2>",
            text,
        )
        if n > 0 and new_text != text:
            open(rte, "w", encoding=enc).write(new_text)
            changed.append(os.path.relpath(rte, workspace))
    return {"ok": True, "changed": changed}


def inject(source_pool, workspace, force=False):
    """从 source_pool 注入 4 个 LEDC 文件到 workspace。

    Args:
        source_pool: 源工程路径（推荐 516 或 HTS092）
        workspace: 目标工作区路径
        force: True 时覆盖已有文件，False 时跳过

    Returns:
        {"ok": bool, "copied": [...], "skipped": [...], "sanitized": [...]}
    """
    copied, skipped = [], []
    for rel in LEDC_FILES:
        src = os.path.join(source_pool, rel.replace("/", os.sep))
        dst = os.path.join(workspace, rel.replace("/", os.sep))
        if not os.path.isfile(src):
            return {"ok": False, "error": "源文件缺失: " + src}
        if os.path.isfile(dst) and not force:
            skipped.append(rel)
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)
    sanitized = sanitize(workspace) if copied else []
    uv_result = update_uvprojx(workspace) if copied else {"ok": True, "added": [], "skipped": [], "reason": "无新文件"}
    rte_result = enable_ledc_rte(workspace) if copied else {"ok": True, "changed": []}
    return {
        "ok": True,
        "copied": copied,
        "skipped": skipped,
        "sanitized": sanitized,
        "uvprojx": uv_result,
        "rte": rte_result,
    }
