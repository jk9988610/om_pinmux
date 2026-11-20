"""Altium PcbDoc BOM (designator -> model/comment) extractor.

Altium Designer stores many short strings in PcbDoc as records:
    [1-byte param id][3 zero bytes][4-byte byte-length LE][UTF-16LE string + NUL]

Component designators (U2, LED1, R7 ...) and their Comment/model strings
(4056H, 3528 ARGB, 100K ...) appear as adjacent records.  This module walks
the records, filters noise, and pairs a designator with the nearest following
non-designator string as its model.

The pairing is heuristic (Altium has no public format spec), so results carry
a confidence flag; use ``validate_against_known`` in tests to catch drift.

Usage:
    from pcbdoc_bom import extract_bom
    bom = extract_bom("path/to/board.PcbDoc")
    # -> {"U2": "4056H", "LED1": "3528 ARGB", ...}
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

__all__ = ["extract_bom", "iter_records", "designator_of"]

# Parameter ids that carry human-visible strings in Altium's binary stream.
# We keep every id in range and filter by content instead of by id.
_MIN_LEN = 2
_MAX_LEN = 160

_DESIG_RE = re.compile(r"^(U|IC|LED|D|Q|SW|KEY|R|C|L|BT|J|P|FPC|TP|TEST|MK)\s*\d+[A-Z]?$", re.I)
_NOISE_RE = re.compile(
    r"^(PCB|Board|Nets|Components|Polygons|Dimensions|Coordinates|Connections|"
    r"Rules|FromTos|Arcs|Pads|Vias|Tracks|Texts|Fills|Regions|Classes|"
    r"EmbeddedFonts|EmbeddedBoards|DifferentialPairs|ComponentBodies|"
    r"Advanced Placer|Design Rule|Layer|Standard|Comment|Pattern|"
    r"\d{4}[-./]\d|\d+\.\d+|V\d+|(null)| nofill)",
    re.I,
)


def iter_records(data: bytes):
    """Yield ``(param_id, text, offset)`` for each string record found."""
    i = 0
    n = len(data)
    while i + 8 <= n:
        pid = data[i]
        if data[i + 1 : i + 4] != b"\x00\x00\x00":
            i += 1
            continue
        length = struct.unpack_from("<I", data, i + 4)[0]
        if not (_MIN_LEN <= length <= _MAX_LEN and length % 2 == 0):
            i += 1
            continue
        end = i + 8 + length
        if end > n:
            i += 1
            continue
        try:
            text = data[i + 8 : end].decode("utf-16-le").rstrip("\x00")
        except UnicodeDecodeError:
            i += 1
            continue
        if text and all(ch == "\x00" or ord(ch) >= 0x20 for ch in text):
            yield pid, text, i
            i = end
        else:
            i += 1


def designator_of(text: str) -> str | None:
    """Return the canonical designator if ``text`` looks like a component ref."""
    t = text.strip()
    if _DESIG_RE.match(t) and not _NOISE_RE.match(t):
        return t.upper()
    return None


def _looks_like_model(text: str) -> bool:
    t = text.strip()
    if not t or len(t) > 40:
        return False
    if _NOISE_RE.match(t) or designator_of(t):
        return False
    # model/comment strings almost always contain a digit or a known part prefix
    if re.match(r"^(SOP|DIP|QFN|LGA|SMD|TSSOP|SOIC|QFP)\d", t, re.I):
        return True
    return bool(re.search(r"\d", t)) or any(
        t.upper().startswith(prefix)
        for prefix in ("WS", "ARGB", "RGB", "TYPE", "MIC", "BAT", "SW", "KEY")
    )


def extract_bom(path: str | Path) -> dict[str, str]:
    """Extract ``{designator: model}`` from one PcbDoc file."""
    data = Path(path).read_bytes()
    records = [(pid, text) for pid, text, _ in iter_records(data)]

    bom: dict[str, str] = {}
    for idx, (_pid, text) in enumerate(records):
        desig = designator_of(text)
        if not desig:
            continue
        # look ahead a few records for the model comment
        for j in range(idx + 1, min(idx + 4, len(records))):
            cand = records[j][1].strip()
            if designator_of(cand):
                break  # hit next designator first -> this one has no model
            if _looks_like_model(cand):
                bom[desig] = cand
                break
    return bom


def known_models() -> dict[str, set[str]]:
    """Expected model substrings per project, used for precision calibration."""
    return {
        "516_BM2017": {"4056H", "3528 ARGB", "6206", "SA8206A"},
        "524_LJ-V08": {"4056H", "SOP24", "6206"},
    }


def validate_against_known(path: str | Path, project: str) -> dict:
    """Return calibration result: expected models found / missing."""
    bom = extract_bom(path)
    values = " | ".join(bom.values())
    expected = known_models().get(project, set())
    found = {e for e in expected if e.lower() in values.lower()}
    return {
        "project": project,
        "components": len(bom),
        "expected": sorted(expected),
        "found": sorted(found),
        "missing": sorted(expected - found),
        "ok": not (expected - found),
        "bom": bom,
    }


if __name__ == "__main__":
    import json
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else ""
    if not target:
        print("usage: python pcbdoc_bom.py <file.PcbDoc>")
        raise SystemExit(1)
    print(json.dumps(extract_bom(target), ensure_ascii=False, indent=2))
