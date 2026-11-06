# OM6239 PinMux (`om_pinmux`)

轻量配置驱动的引脚/板级特征生成器：`.omcfg` 是唯一真相，Python 校验并生成代码，只按
标记块写回 SDK，写入前有事务备份、写入后可回滚。业务协议（RF/HID 映射）不在范围内。

本文所有命令均在真实 SDK 副本上验证过（2026-11-06，CH04 与 KC536，Keil UV4
`0 Error(s), 0 Warning(s)`）。第一次上手不需要读源码。

## 环境要求

- Windows + Python 3.10+（PowerShell 或 cmd 均可）。
- `pip install -r requirements.txt`（`pyyaml`；GUI 另需 `pywebview`）。
- 编译验证需要 Keil `UV4.exe`（默认 `C:\Keil_v5\UV4\UV4.exe`）。
- 准备一份 **SDK 副本**。工具会直接改副本里的源码，原工程请保持不变。

## 从零到编译：5 步

以下 `<副本>` 替换为你的 SDK 副本根目录，例如 `D:\work\KC536_copy`。

### 0. 复制 SDK

```powershell
robocopy "E:\M_2026\0_T\software\trunk\SE71M_0023_KC536_V1_20260909" "D:\work\KC536_copy" /MIR
```

> `robocopy` 退出码 1 表示“已复制文件”，属于成功；0 表示无变化。

### 1. 校验板模板

```powershell
python -m omcfg check --all configs
```

预期：`configs/CH04.omcfg`、`configs/KC536.omcfg` 各 `errors: 0`；`configs/BD319.omcfg`
有 1 条 `KEY_PAIR` 历史 warning（不是 error）。全部通过时退出码 0。

### 2. 初始化副本（一次性）

```powershell
python -m omcfg init --config configs\KC536.omcfg --sdk D:\work\KC536_copy
```

它做两件事：把模板安装为 `<副本>\projects\mouse_demo\project.omcfg`；在
`user_config.h` / `user_config.c` 的已知位置插入 `OMCFG` 与 `USER CODE` 标记。
预期输出（文件路径随副本变化）：

```text
已插入标记: D:\work\KC536_copy\projects\mouse_demo\periph\user_config.h
已插入标记: D:\work\KC536_copy\projects\mouse_demo\periph\user_config.c
事务 manifest: D:\work\KC536_copy\.omcfg_bak_20261106_125530_313019\manifest.json
下一步: python -m omcfg gen --sdk D:\work\KC536_copy --dry-run
```

重复 `init` 是安全的；若 `project.omcfg` 已存在且内容不同，会拒绝并提示加 `--force`。

### 3. 先看 diff（dry-run）

```powershell
python -m omcfg gen --sdk D:\work\KC536_copy --dry-run
```

输出是统一 diff（`---`/`+++`/`@@`）。KC536 在未改配置时 `user_config.h/.c` 正文
`无变化`（与参考工程逐字节一致），只有 `board_features.h` 与 `.uvprojx` 需要补条目；
CH04 会多出 `user_config.h/.c` 的实际差异。末尾会给出：

```text
dry-run: N 个文件待写入；确认后加 --apply
```

`gen` 默认就是 dry-run，`--dry-run` 只是显式写法；与 `--apply` 互斥。

### 4. 写入

```powershell
python -m omcfg gen --sdk D:\work\KC536_copy --apply
```

预期末尾：

```text
已写入 N 个文件；manifest: D:\work\KC536_copy\.omcfg_bak_20261106_125543_747567\manifest.json
回滚: python -m omcfg rollback --manifest D:\work\KC536_copy\.omcfg_bak_20261106_125543_747567\manifest.json
```

写入按标记块精确替换，不动 `USER CODE` 保护区；同一份配置重复 `--apply` 无实质变化。

### 5. 编译

```powershell
$uv = "C:\Keil_v5\UV4\UV4.exe"
$proj = "D:\work\KC536_copy\projects\mouse_demo\keil5\SE71M.uvprojx"
$log = "D:\work\KC536_copy\build.log"
$p = Start-Process -FilePath $uv -ArgumentList @("-r", $proj, "-o", $log) -Wait -PassThru
"exit=$($p.ExitCode)"
Select-String -Path $log -Pattern "Error\(s\)|Warning\(s\)|Program Size"
```

预期（`-r` 为全量重编）：

```text
".\out\SE71M.axf" - 0 Error(s), 0 Warning(s).
Program Size: Code=38580 RO-data=1756 RW-data=172 ZI-data=2244
```

实测尺寸（均 `0 Error / 0 Warning`）：

| 板 | `--apply` 后 | `rollback` 后 |
|---|---|---|
| KC536 | Code=38580 RO=1756 RW=172 ZI=2244 | 同左 |
| CH04 | Code=39428 RO=2120 RW=208 ZI=2292 | Code=39420 RO=2120 RW=208 ZI=2292 |

### 6. 回滚（可选，随时可做）

```powershell
python -m omcfg rollback --manifest D:\work\KC536_copy\.omcfg_bak_20261106_125543_747567
```

`--manifest` 可传 `manifest.json`，也可直接传它所在的 `.omcfg_bak_*` 目录。
预期 `已恢复 N 个文件`，随后 `gen --dry-run` 的输出与 `--apply` 之前完全一致
（本次实测两次 dry-run 输出哈希相同；新建文件会被删除，已有文件按 SHA1 还原）。

## 日常改配置

1. 编辑 `<副本>\projects\mouse_demo\project.omcfg`（或 GUI）。
2. `python -m omcfg check <副本>\projects\mouse_demo\project.omcfg`。
3. `gen --dry-run` 确认 diff 只落在预期字段。
4. `gen --apply`，再编译。

## 图形界面（薄视图）

```powershell
launch.bat
```

界面只做展示与提交：打开 SDK → 改引脚 → 保存引脚 → 预览 diff → 应用。所有校验、
生成、事务都由后端 `omcfg` 完成，前端不拼宏、不复制规则。

已在 Windows + pywebview/WebView2 环境实测通过一次完整闭环（KC536 副本，28 个引脚）：

```text
打开完成；问题 0 条
KEY_R0_PIN: P34 -> P36
已保存 project.omcfg；接着点「预览 diff」
预览完成；问题 0 条（diff 含 KEY_R0_PIN）
已写入 3 个文件
```

若启动时报 WebView2 缺失，请安装 Microsoft Edge WebView2 Runtime；后端 CLI 不受影响。

## CLI 参考

每个子命令都有可用的 `--help`（含示例）：

```powershell
python -m omcfg --help
python -m omcfg init --help
python -m omcfg check --help
python -m omcfg gen --help
python -m omcfg rollback --help
```

| 命令 | 关键参数 | 行为 |
|---|---|---|
| `init` | `--config FILE --sdk DIR [--force]` | 安装 `project.omcfg`，插入 `OMCFG`/`USER CODE` 标记；一次性 |
| `check` | `FILE...` 或 `--all DIR` | 只校验，不写盘；有 error 返回 1 |
| `gen` | `--sdk DIR [--config FILE] [--dry-run\|--apply]` | 默认 dry-run；`--apply` 走事务并产出 manifest |
| `rollback` | `--manifest FILE_OR_DIR` | 按 manifest 恢复文件；可多次、按时间倒序撤销 |

## 常见误用与提示（均为实测）

| 误用 | 退出码 | 实际提示（节选） |
|---|---|---|
| SDK 路径不存在 | 2 | `[ERROR] SDK 目录不存在: ...` + `提示: --sdk 指向 SDK 根目录（其下应有 projects/mouse_demo/periph），不是 keil5 子目录` |
| 指向普通目录/子目录 | 2 | `[ERROR] 不是预期的 SDK：缺少 projects/mouse_demo/periph` + `提示: 确认这是 mouse_demo 工程的 SDK 根目录；改板请先复制一份 SDK 再操作` |
| 未 init 就 apply（无配置） | 2 | `[ERROR] 配置不存在: ...project.omcfg` + `提示: 先运行 python -m omcfg init 安装 project.omcfg，或用 --config configs/KC536.omcfg 指定板模板` |
| 有配置但副本缺标记 | 2 | `[ERROR] ...user_config.h 缺少 OMCFG 标记块 'pins'。` + `先运行: python -m omcfg init --config <config> --sdk <SDK>` |
| rollback 找不到 manifest | 2 | `[ERROR] manifest 不存在: ...` + `提示: manifest 位于 <SDK>/.omcfg_bak_<时间戳>/manifest.json；也可以直接把该目录传给 --manifest` |
| manifest 损坏/不是本工具的 | 2 | `[ERROR] manifest 不受支持` 或 `manifest 解析失败` + `提示: 确认它由当前版本的 init/gen/apply 生成` |
| 配置缺字段（如 `project.name`） | 1 | `[ERROR] project.name: 不能为空` + `提示: 补 project.name（如 KC536），可对照 configs/*.omcfg`，并汇总 `errors: 1` |
| YAML 语法错误 | 2 | `[ERROR] ...: YAML 解析失败: ...` + `提示: 检查缩进、冒号和引号；可对照 configs/KC536.omcfg` |
| 配置与 SDK 不是同一块板 | 0（warning） | `[WARNING] project: 配置与 SDK 现有工程不一致：project.name=CH04，SDK 现有 iPROJECT_NAME="KC536"` + `提示: 若是在副本上换板可继续；否则确认 --sdk/--config 配对` |
| `--dry-run` 与 `--apply` 同时给 | 2 | `omcfg gen: error: argument --apply: not allowed with argument --dry-run` |
| `check` 路径不存在 | 2 | `[ERROR] 配置不存在: ...` + `提示: 确认路径；仓库内的板模板在 configs/*.omcfg` |

## CLI 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 / 校验通过 / dry-run 无变化 / 仅 warning |
| 1 | 配置校验失败（`check`、`gen`、`init`） |
| 2 | 环境、配置解析或标记块错误（含 manifest 缺失/损坏） |
| 3 | 写盘失败（文件被占用、权限不足） |
| 4 | 历史预留（已回滚），当前命令不会返回 |

## 唯一配置源

`<SDK根>/projects/mouse_demo/project.omcfg`（YAML）。仓库内 `configs/*.omcfg` 是板模板，
`init` 时复制为工程配置。

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

`features`、唤醒掩码、`LVD_CHECK_INDEX`、`WHEEL_IO_SELECT`、模式脚等由 `pins`/`board`
派生，不写进配置。

## 生成物与标记块

生成 3 个源码文件 + Keil 工程：

- `projects/mouse_demo/periph/user_config.h`
- `projects/mouse_demo/periph/user_config.c`（含 `gpio_table` 与睡眠初始化）
- `projects/mouse_demo/periph/board_features.h`（缺失时整文件新建）
- `projects/mouse_demo/keil5/SE71M.uvprojx`（补 `board_features.h` 条目）

若历史副本里仍有 `periph_gpio_sleep_set.pinmux.c`，它会被改写为“已退场”的注释，且
不再参与编译（`uvprojx` 中的条目已移除）。

写回只认精确标记，缺标记直接报错，不猜位置：

```c
/* OMCFG BEGIN pins */
/* OMCFG END pins */
```

块名：`pins`、`project_ids`、`project_version`、`project_names`（`user_config.h`）；
`gpio_table`、`sleep`（`user_config.c`）；`features`（`board_features.h`）。

## 事务备份与保留策略

- 位置：`<SDK根>\.omcfg_bak_<YYYYmmdd_HHMMSS_微秒>\`（每次 `init`/`gen --apply`/GUI
  保存或应用各建一个目录，微秒后缀避免同秒冲突）。
- 内容：`manifest.json` + 原文件备份。manifest 记录 `schema`、`operation`、
  `target_root`、每个文件的 `path`/`existed`/`before_sha1`/`backup`，以及写入动作的
  前后 SHA1 与校验结果；新建文件 `existed=false`，回滚时删除。
- 策略：**不自动清理**。确认编译通过后可手工删除旧 `.omcfg_bak_*`；回滚按时间倒序
  （先撤 `apply`，再撤 `init`）即可停在任一步。备份只在 SDK 副本内产生，不碰原工程。

## 数据与文档

- `chip/om6239.json`：芯片引脚与复用约束，校验器只读它。
- `docs/ROADMAP-LIGHTWEIGHT-CUBEMX.md`：重构路线、阶段验收与设计决策。
- `launch*.bat`：GUI 启动方式。

## 测试

```powershell
python -m pytest
python -m ruff check .
python -m omcfg check --all configs
```

## 明确不在本轮范围

- 4 线板（HYC-275QLH）模板与端到端支持：延后。
- 新工程一键生成（复制 SDK + init + 编译）：延后。
- 业务协议（RF/HID 映射）改写：不在本工具范围。
