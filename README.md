# OM6239 PinMux (`om_pinmux`)

轻量配置驱动的引脚/板级特征生成器：`.omcfg` 是唯一真相，Python 校验并生成代码，只按标记块写回 SDK。
业务协议（RF/HID 映射）不在范围内。

## 快速上手

```bat
cd /d E:\tools\om_pinmux

:: 0) 安装依赖
pip install -r requirements.txt

:: 1) 一次性初始化：把配置装进工程、在已知区域插入 OMCFG 标记
python -m omcfg init --config configs\KC536.omcfg --sdk <SDK根>

:: 2) 校验配置（0 error 才继续）
python -m omcfg check <SDK根>\projects\mouse_demo\project.omcfg
python -m omcfg check --all configs

:: 3) 预览 diff（不落盘）
python -m omcfg gen --sdk <SDK根> --dry-run

:: 4) 写入（走事务，产出可回滚 manifest）
python -m omcfg gen --sdk <SDK根> --apply

:: 5) 需要时回滚
python -m omcfg rollback --manifest <SDK根>\.omcfg_bak_<时间戳>\manifest.json
```

生成 4 个产物：`user_config.h`、`user_config.c`、`board_features.h`、
`periph_gpio_sleep_set.pinmux.c`。

## 图形界面

双击 `launch.bat`（或 `打开引脚工具.bat`）启动 pywebview 薄壳；界面只负责展示
引脚表 / 问题 / diff，所有动作调用后端同一套 `omcfg` 核心。

## 唯一配置源

`<SDK根>/projects/mouse_demo/project.omcfg`（YAML）。仓库内 `configs/*.omcfg`
是板模板，`init` 时复制为工程配置。

```yaml
schema: om6239-project/v1
chip: OM6239
project:
  name: KC536
  customer: BYC
  id: { low: "0x0023", high: "0x071", version: 5 }
board:
  mode_pins: single
  logo: rgb
  led_polarity: active_low
  sensor: { bus: sdio_3wire, dir_clock: 6 }
  wheel: ENCODER_PINMUX_SEL_IO_20_21
pins:
  KEY_R0_PIN: P34
  ...
```

`features`、唤醒掩码、`LVD_CHECK_INDEX`、`WHEEL_IO_SELECT`、模式脚等全部由
`pins`/`board` 派生，不允许写进配置。

## 标记块

写回只认精确标记，缺标记直接报错（不猜位置）：

```c
/* OMCFG BEGIN pins */
/* OMCFG END pins */
```

块名：`pins`、`project_ids`、`project_version`、`project_names`（`user_config.h`），
`gpio_table`（`user_config.c`），`features`、`sleep`（生成文件存在时）。新文件缺失
则整文件创建。

## CLI 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 / 校验通过 / 无变化 |
| 1 | 配置校验失败 |
| 2 | 配置、环境或标记块错误 |
| 3 | 写盘失败 |
| 4 | 已回滚 |

## 数据与归档

- `chip/om6239.json`：芯片引脚与复用约束，校验器只读它。
- `boards/*.json`：历史板档案，运行时不读取。
- `docs/ROADMAP-LIGHTWEIGHT-CUBEMX.md`：重构路线与阶段验收。

## 测试

```bat
python -m pytest
python -m ruff check .
```
