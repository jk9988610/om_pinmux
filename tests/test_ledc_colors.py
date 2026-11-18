import hashlib
import re
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
TPL = WS / "omcfg/templates/ledc/ledc.c"
EXPECTED = [
    [240, 0, 0],
    [0, 240, 0],
    [0, 0, 240],
    [240, 0, 240],
    [240, 240, 0],
    [0, 240, 240],
    [240, 240, 240],
    [0, 0, 0],
]


def _base(ch04_baseline: Path) -> Path:
    """CH04 基线的 ledc.c；当前内置基线 KC536 不含 LEDC，改用备份取证。"""
    return ch04_baseline / "projects/mouse_demo/periph/ledc.c"


def _read(p):
    with open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _sha1_norm(p):
    b = p.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha1(b).hexdigest()


def test_two_ledc_c_files_identical(ch04_baseline):
    """约束 3：两份内容一致（归一化换行符后 SHA1 相等）。"""
    assert _sha1_norm(TPL) == _sha1_norm(_base(ch04_baseline))


def test_newline_styles_preserved(ch04_baseline):
    assert "\r\n" in _read(TPL), "TPL 应保持 CRLF"
    assert "\r\n" not in _read(_base(ch04_baseline)), "BASE 应保持 LF"


def test_blue_channel_writes_blue_value(ch04_baseline):
    s = _read(_base(ch04_baseline))
    assert re.search(r"Rgb_data\[rgb_enable\*3\+2\]\s*=\s*blue_value", s)
    assert re.search(r"Rgb_data\[rgb_enable\*3\+2\]\s*=\s*green_value", s) is None


def test_dpi_rgb_tab_has_8x3_and_mask(ch04_baseline):
    for f in (TPL, _base(ch04_baseline)):
        s = _read(f)
        assert "uint8_t const dpi_rgb_tab[8][3]" in s
        assert "dpi_rgb_tab[dpi_grade&0x07]" in s
        assert re.search(r"dpi_rgb_tab\[dpi_grade\]", s) is None


def test_dpi_rgb_tab_values_match_ch04(ch04_baseline):
    """去注释后按 {r,g,b} 结构提取，避免注释里的数字被误抓。"""
    for f in (TPL, _base(ch04_baseline)):
        s = _read(f)
        m = re.search(r"uint8_t const dpi_rgb_tab\[8\]\[3\]\s*=\s*\{(.*?)\};", s, re.S)
        assert m, f"{f.name}: 找不到表定义"
        body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
        triples = re.findall(r"\{\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\}", body)
        got = [[int(a), int(b2), int(c)] for a, b2, c in triples]
        assert got == EXPECTED, f"{f.name}: {got}"


def test_four_call_sites_use_rgb_triplet(ch04_baseline):
    for f in (TPL, _base(ch04_baseline)):
        calls = re.findall(r"ledc_data_write\([^)]+\)", _read(f))
        real_calls = [c for c in calls if "dpi_rgb_tab[" in c]
        assert len(real_calls) == 4, f"{f.name}: {len(real_calls)} 个查表调用点"
