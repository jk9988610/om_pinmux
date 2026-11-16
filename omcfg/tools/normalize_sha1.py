#!/usr/bin/env python3
"""行尾归一化 SHA1：证明两份文本"仅换行符不同"。

归一化规则（最小侵入）：
  - CRLF -> LF，孤立 CR -> LF
  - 不删注释、不压缩空白、不展开宏
  - 因此：归一化 SHA1 相等 <=> 除换行符外逐字节一致

用法:
  python omcfg/tools/normalize_sha1.py <file>
  python omcfg/tools/normalize_sha1.py <file_a> <file_b>   # 自动比较

退出码:
  0 = 归一化后逐字节相等（或单文件模式成功）
  1 = 归一化后仍不一致（存在换行符之外的真实差异）
  2 = 文件缺失
"""

import argparse
import hashlib
import sys
from pathlib import Path


def count_newlines(data):
    crlf = data.count(b"\r\n")
    return {"crlf": crlf, "lf": data.count(b"\n") - crlf, "cr": data.count(b"\r") - crlf}


def normalize(data):
    """本函数只做 CRLF→LF，不删注释、不压空白、不展开宏。
    任何未来的「归一化」扩展必须在这里显式声明，不得静默加规则。
    """
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha1(data):
    return hashlib.sha1(data).hexdigest()


def describe(nl):
    parts = []
    if nl["crlf"]:
        parts.append(f"CRLF={nl['crlf']}")
    if nl["lf"]:
        parts.append(f"LF={nl['lf']}")
    if nl["cr"]:
        parts.append(f"CR={nl['cr']}")
    return ", ".join(parts) if parts else "(无换行符)"


def analyze(path):
    raw = path.read_bytes()
    norm = normalize(raw)
    return {
        "path": str(path),
        "size_raw": len(raw),
        "sha1_raw": sha1(raw),
        "sha1_norm": sha1(norm),
        "newlines": count_newlines(raw),
        "norm": norm,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="行尾归一化 SHA1（仅消除 CRLF/LF 差异）")
    ap.add_argument("files", nargs="+", metavar="FILE")
    args = ap.parse_args(argv)

    infos = []
    for f in args.files:
        p = Path(f)
        if not p.is_file():
            print(f"[ERR] 文件不存在: {p}", file=sys.stderr)
            return 2
        infos.append(analyze(p))

    print("=" * 70)
    print("原始 / 归一化 SHA1")
    print("=" * 70)
    for i in infos:
        print(f"  {i['path']}")
        print(f"    换行        : {describe(i['newlines'])}")
        print(f"    原始 SHA1   : {i['sha1_raw']}  ({i['size_raw']} B)")
        print(f"    归一化 SHA1 : {i['sha1_norm']}")

    if len(infos) == 2:
        a, b = infos
        print()
        print("=" * 70)
        print("比较结论")
        print("=" * 70)
        raw_eq = a["sha1_raw"] == b["sha1_raw"]
        norm_eq = a["sha1_norm"] == b["sha1_norm"]
        byte_eq = a["norm"] == b["norm"]
        print(f"  原始 SHA1 相等     : {raw_eq}")
        print(f"  归一化 SHA1 相等   : {norm_eq}")
        print(f"  归一化后逐字节相等 : {byte_eq}")
        if norm_eq and byte_eq:
            if raw_eq:
                print("  → 两份文件逐字节完全一致（含换行符）")
            else:
                print("  → 两份文件仅换行符不同；内容（含注释/空白/代码）逐字节一致")
            return 0
        print("  → 归一化后仍不一致：存在换行符之外的真实差异，需人工核查")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
