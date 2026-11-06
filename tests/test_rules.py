from pathlib import Path

from omcfg import model, rules
from omcfg.generate import templates

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = ROOT / "configs"
BASELINE = ROOT / "baseline"


def _load(name: str = "CH04") -> dict:
    return model.load_config(CONFIGS / f"{name}.omcfg")


def _write_sdk(root: Path, config: dict) -> Path:
    periph = root / "projects/mouse_demo/periph"
    periph.mkdir(parents=True)
    pins = model.resolved_pins(config)
    (periph / "user_config.h").write_text(templates.render_pins(config, pins), encoding="utf-8")
    source = (
        "/* OMCFG BEGIN gpio_table */\n"
        + templates.render_gpio_table(config, pins)
        + "\n/* OMCFG END gpio_table */\n\n"
        + "/* OMCFG BEGIN sleep */\n"
        + templates.render_sleep(config, pins)
        + "\n/* OMCFG END sleep */\n"
    )
    (periph / "user_config.c").write_text(source, encoding="utf-8")
    return root


def test_ch04_baseline_strict_audit_has_no_errors():
    config = model.load_config(BASELINE / "project.omcfg")
    report = rules.audit(config, BASELINE / "sdk", strict=True)
    assert not report.errors, [issue.render() for issue in report.errors]


def test_pin_change_without_regenerate_is_macro_error():
    config = _load()
    config["pins"]["KEY_R0_PIN"] = "P10"
    report = rules.audit(config, BASELINE / "sdk", strict=True)
    assert any("pins.macro" in issue.path for issue in report.errors)


def test_wake_mask_missing_key_is_reported(tmp_path):
    config = _load()
    root = _write_sdk(tmp_path / "sdk", config)
    header = root / "projects/mouse_demo/periph/user_config.h"
    text = header.read_text(encoding="utf-8")
    header.write_text(text.replace("|(1<<KEY_PAIR_PIN)", ""), encoding="utf-8")
    report = rules.audit(config, root, strict=True)
    assert any("pins.wake" in issue.path for issue in report.errors)


def test_polarity_mismatch_is_reported(tmp_path):
    config = _load()
    root = _write_sdk(tmp_path / "sdk", config)
    changed = _load()
    changed["board"]["led_polarity"] = "active_low"
    report = rules.audit(changed, root, strict=True)
    assert any("led.polarity" in issue.path for issue in report.errors)


def test_key_io_unconditional_key_c0_is_error(tmp_path):
    config = _load()
    del config["pins"]["KEY_C0_PIN"]
    root = _write_sdk(tmp_path / "sdk", config)
    (root / "projects/mouse_demo/periph/key_io.c").write_text(
        "void scan(void) { gpio_dir_in(KEY_C0_PIN); }\n", encoding="utf-8"
    )
    report = rules.audit(config, root, strict=True)
    assert any("KEY_C0_PIN" in issue.path for issue in report.errors)


def test_dpi_table_mismatch_is_warning(tmp_path):
    config = _load()
    root = _write_sdk(tmp_path / "sdk", config)
    periph = root / "projects/mouse_demo/periph"
    (periph / "sensor.c").write_text(
        "unsigned char const sensor_dpi_ini[] = {\n"
        "    1200L/200L-1,\n    1600L/200L-1,\n    2000L/200L-1,\n};\n",
        encoding="utf-8",
    )
    (periph / "sensor.h").write_text("#define DEFAULT_DPI_GRADE 1\n", encoding="utf-8")
    report = rules.audit(config, root, strict=True)
    assert not report.errors
    assert any("dpi.table" in issue.path for issue in report.warnings)


def test_rules_list_is_readable():
    text = rules.render_rules()
    for rule in rules.RULES:
        assert rule.id in text
