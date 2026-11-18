"""§4 keys PAIR 可选：CH04 有 PAIR / CH04_6K 无 PAIR 的 model 与 baseline 校验。"""

from pathlib import Path

from omcfg import model

CONFIGS = Path(__file__).resolve().parent.parent / "configs"


def _load(name):
    import yaml

    text = (CONFIGS / f"{name}.omcfg").read_text(encoding="utf-8")
    return yaml.safe_load(text)


def test_ch04_with_pair_keeps_pair_in_pins():
    config = _load("CH04")
    pins = model.pin_entries(config)
    assert "KEY_PAIR_PIN" in pins
    assert "KEY_PAIR_PIN" in model.wake_keys(config, pins)


def test_ch04_6k_no_pair_in_pins():
    config = _load("CH04_6k")
    pins = model.pin_entries(config)
    assert "KEY_PAIR_PIN" not in pins
    assert model.wake_keys(config, pins) == ["KEY_R0_PIN", "KEY_R1_PIN", "KEY_R2_PIN"]


def test_baseline_key_io_has_ifdef_guard(ch04_baseline):
    base = ch04_baseline / "projects" / "mouse_demo" / "periph"
    for name in ("key_io.h", "key_io.c"):
        text = (base / name).read_text(encoding="utf-8")
        assert "#ifdef KEY_PAIR_PIN" in text, f"{name} 缺少 #ifdef KEY_PAIR_PIN"


def test_baseline_key_io_ifdef_balanced(ch04_baseline):
    base = ch04_baseline / "projects" / "mouse_demo" / "periph"
    for name in ("key_io.h", "key_io.c"):
        text = (base / name).read_text(encoding="utf-8")
        count_ifdef = text.count("#ifdef KEY_PAIR_PIN")
        count_endif = text.count("#endif")
        assert count_ifdef == 1, f"{name} #ifdef KEY_PAIR_PIN 出现 {count_ifdef} 次（应为 1）"
        assert count_endif >= 1, f"{name} 无 #endif"
