"""KC536 字节一致性：有真实 SDK 时跑，无则跳过。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from omcfg import cli, model
from omcfg.generate import generator

REAL_SDK = Path(
    os.environ.get(
        "OMCFG_REAL_SDK",
        r"E:\M_2026\0_T\software\trunk\SE71M_0023_KC536_V1_20260909",
    )
)
CONFIG = Path(__file__).resolve().parent.parent / "configs" / "KC536.omcfg"


@pytest.mark.skipif(not (REAL_SDK / "projects/mouse_demo/periph/user_config.h").is_file(), reason="无真实 SDK")
def test_kc536_generation_is_byte_identical(tmp_path):
    periph = tmp_path / "sdk" / "projects" / "mouse_demo" / "periph"
    periph.mkdir(parents=True)
    for name in ("user_config.h", "user_config.c"):
        shutil.copy2(REAL_SDK / "projects/mouse_demo/periph" / name, periph / name)
    sdk_root = tmp_path / "sdk"
    assert cli.main(["init", "--config", str(CONFIG), "--sdk", str(sdk_root)]) == 0
    config = model.load_config(sdk_root / "projects/mouse_demo/project.omcfg")
    outputs = {item.path.name: item for item in generator.build_outputs(config, sdk_root)}
    assert not outputs["user_config.h"].changed
    assert not outputs["user_config.c"].changed
