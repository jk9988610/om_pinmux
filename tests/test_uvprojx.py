"""uvprojx 外科更新、USER CODE 与 LEDC 像素数配置化的单测。"""

from __future__ import annotations

import re
from pathlib import Path

from omcfg import model
from omcfg.generate import generator, templates
from omcfg.targets import uvprojx

CONFIGS = Path(__file__).resolve().parent.parent / "configs"

UVPROJX = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<Project xmlns="http://www.keil.com/uvision">
  <Targets>
    <Target>
      <TargetName>SE71M</TargetName>
      <TargetOption>
        <TargetCommonOption>
          <IncludePath></IncludePath>
        </TargetCommonOption>
        <TargetArmAds>
          <Cads>
            <IncludePath>../main</IncludePath>
          </Cads>
        </TargetArmAds>
      </TargetOption>
      <Groups>
        <Group>
          <GroupName>main</GroupName>
          <Files>
            <File>
              <FileName>main.c</FileName>
              <FileType>1</FileType>
              <FilePath>../main/main.c</FilePath>
            </File>
          </Files>
        </Group>
        <Group>
          <GroupName>periph</GroupName>
          <Files>
            <File>
              <FileName>user_config.c</FileName>
              <FileType>1</FileType>
              <FilePath>..\\periph\\user_config.c</FilePath>
              <FileOption>
                <CommonProperty>
                  <IncludeInBuild>1</IncludeInBuild>
                </CommonProperty>
              </FileOption>
            </File>
            <File>
              <FileName>ledc.c</FileName>
              <FileType>1</FileType>
              <FilePath>..\\periph\\ledc.c</FilePath>
            </File>
            <File>
              <FileName>ledc_mode.c</FileName>
              <FileType>1</FileType>
              <FilePath>..\\periph\\ledc_mode.c</FilePath>
            </File>
            <File>
              <FileName>periph_gpio_sleep_set.pinmux.c</FileName>
              <FileType>1</FileType>
              <FilePath>..\\periph\\periph_gpio_sleep_set.pinmux.c</FilePath>
            </File>
          </Files>
        </Group>
      </Groups>
    </Target>
  </Targets>
</Project>
"""

HEADER = "\n".join(
    [
        "//* 按键配置 */",
        "#define KEY_R0_PIN              (P34)",
        "/* OMCFG BEGIN pins */",
        "old",
        "/* OMCFG END pins */",
        "/* OMCFG BEGIN project_ids */",
        "old",
        "/* OMCFG END project_ids */",
        "/* OMCFG BEGIN project_version */",
        "old",
        "/* OMCFG END project_version */",
        "/* OMCFG BEGIN project_names */",
        "old",
        "/* OMCFG END project_names */",
        "/* USER CODE BEGIN user_config_h */",
        "/* USER CODE END user_config_h */",
        "",
    ]
)

SOURCE = "\n".join(
    [
        "const user_gpio_config_t gpio_config_table[] = {",
        "/* OMCFG BEGIN gpio_table */",
        "old",
        "/* OMCFG END gpio_table */",
        "};",
        "/* OMCFG BEGIN sleep */",
        "old",
        "/* OMCFG END sleep */",
        "/* USER CODE BEGIN user_config_c */",
        "/* USER CODE END user_config_c */",
        "",
    ]
)


def _config(name: str = "CH04.omcfg") -> dict:
    return model.load_config(CONFIGS / name)


def test_ledc_board_adds_generated_files(tmp_path):
    path = tmp_path / "SE71M.uvprojx"
    path.write_text(UVPROJX, encoding="utf-8")
    after = uvprojx.update_project(UVPROJX, _config(), path)
    assert "<FileName>board_features.h</FileName>" in after
    assert "<FileName>periph_gpio_sleep_set.pinmux.c</FileName>" not in after
    assert "<FileType>5</FileType>" in after
    assert "<FileName>ledc.c</FileName>" in after
    assert "<FileName>ledc_mode.c</FileName>" in after
    assert "<IncludeInBuild>1</IncludeInBuild>" in after


def test_rgb_board_removes_ledc_sources(tmp_path):
    path = tmp_path / "SE71M.uvprojx"
    path.write_text(UVPROJX, encoding="utf-8")
    after = uvprojx.update_project(UVPROJX, _config("KC536.omcfg"), path)
    assert "<FileName>ledc.c</FileName>" not in after
    assert "<FileName>ledc_mode.c</FileName>" not in after
    assert "<FileName>periph_gpio_sleep_set.pinmux.c</FileName>" not in after
    assert "<FileName>user_config.c</FileName>" in after
    assert "<FileName>board_features.h</FileName>" in after


def test_update_project_is_idempotent(tmp_path):
    path = tmp_path / "SE71M.uvprojx"
    path.write_text(UVPROJX, encoding="utf-8")
    once = uvprojx.update_project(UVPROJX, _config(), path)
    assert uvprojx.update_project(once, _config(), path) == once


def test_include_path_gets_periph(tmp_path):
    path = tmp_path / "SE71M.uvprojx"
    path.write_text(UVPROJX, encoding="utf-8")
    after = uvprojx.update_project(UVPROJX, _config(), path)
    assert "<IncludePath>../main;../periph</IncludePath>" in after
    assert "<IncludePath></IncludePath>" in after


def test_generator_wires_project_file(tmp_path):
    root = tmp_path / "sdk"
    periph = root / "projects/mouse_demo/periph"
    keil = root / "projects/mouse_demo/keil5"
    periph.mkdir(parents=True)
    keil.mkdir(parents=True)
    (periph / "user_config.h").write_text(HEADER, encoding="utf-8")
    (periph / "user_config.c").write_text(SOURCE, encoding="utf-8")
    (keil / "SE71M.uvprojx").write_text(UVPROJX, encoding="utf-8")

    config = _config()
    outputs = {item.path.name: item for item in generator.build_outputs(config, root)}
    project = outputs["SE71M.uvprojx"]
    assert project.changed
    assert "<FileName>board_features.h</FileName>" in project.after
    assert "<FileName>periph_gpio_sleep_set.pinmux.c</FileName>" not in project.after

    source = outputs["user_config.c"]
    assert "void periph_gpio_sleep_set()" in source.after
    assert "#if" not in source.after
    assert "periph_gpio_sleep_set.pinmux.c" not in outputs


def test_retired_sleep_file_becomes_pointer(tmp_path):
    root = tmp_path / "sdk"
    periph = root / "projects/mouse_demo/periph"
    periph.mkdir(parents=True)
    (periph / "user_config.h").write_text(HEADER, encoding="utf-8")
    (periph / "user_config.c").write_text(SOURCE, encoding="utf-8")
    stale = periph / "periph_gpio_sleep_set.pinmux.c"
    stale.write_text("#if 0\nvoid periph_gpio_sleep_set() {}\n#endif\n", encoding="utf-8")

    outputs = {item.path.name: item for item in generator.build_outputs(_config(), root)}
    retired = outputs["periph_gpio_sleep_set.pinmux.c"]
    assert retired.changed
    assert "已退场" in retired.after
    assert "#if" not in retired.after


def test_ledc_rgb_number_reads_config():
    config = _config()
    pins = model.resolved_pins(config)
    assert re.search(r"#define LEDC_RGB_NUMBER\s+6$", templates.render_pins(config, pins), re.M)
    config["board"]["ledc_rgb_number"] = 12
    rendered = templates.render_pins(config, pins)
    assert re.search(r"#define LEDC_RGB_NUMBER\s+12$", rendered, re.M)
