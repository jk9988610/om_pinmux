import re
from pathlib import Path

# 匹配：if/for/while/try/except xxx: 后面直接跟语句 E701
pat_e701 = re.compile(r"^(\s*)(if|for|while|try|except)(.*?):\s*(.+)$")
# 匹配分号分隔 E702
pat_semi = re.compile(r"(.+?);\s*(.+?)")


def split_semi(line: str):
    """把 a; b; c 拆成多行，保持缩进"""
    parts = [p.strip() for p in line.split(";")]
    indent = re.match(r"^(\s*)", line).group(1)
    return "\n".join([indent + p for p in parts if p])


def process_file(p: Path):
    src = p.read_text(encoding="utf-8")
    lines = src.splitlines()
    out = []
    for line in lines:
        m = pat_e701.match(line)
        if m:
            indent, kw, cond, stmt = m.groups()
            out.append(f"{indent}{kw}{cond}:")
            out.append(f"{indent}    {stmt}")
            continue
        # 处理分号，注意：只处理简单行，复杂嵌套不碰
        if ";" in line and not any(x in line for x in ["#", "'''", '"""']):
            out.append(split_semi(line))
            continue
        out.append(line)
    new_text = "\n".join(out) + "\n"
    if new_text != src:
        p.write_text(new_text, encoding="utf-8")
        print(f"fixed: {p}")


if __name__ == "__main__":
    targets = [
        "omcfg/api.py",
        "omcfg/smoke.py",
        "omcfg/tools/normalize_sha1.py",
        "tests/test_ledc_colors.py",
    ]
    for f in targets:
        process_file(Path(f))
