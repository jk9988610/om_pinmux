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

## 新工程一键生成（推荐）

从源 SDK + 一份配置直接生成**可编译的新工程**，不再手工 `robocopy` 再逐文件改。

### 1. 准备新配置

```powershell
copy configs\KC536.omcfg myboard.omcfg
```

编辑 `myboard.omcfg` 的工程标识；引脚/板型保持与源 SDK 一致即可：

```yaml
project:
  name: KC536X
  customer: BYC
  ble_names: ["KC536X Bt1"]   # 可选；BT0/BT1 双广播名可写 2 项
  id: { low: "0x0101", high: "0x071", version: 6 }
```

### 2. 一条命令生成

```powershell
python -m omcfg new --sdk E:\SDK\KC536 --target D:\work\KC536X --config myboard.omcfg
```

它依次完成：复制骨架（剔除产物）→ 安装 `project.omcfg` → 改写工程标识 →
插入 `OMCFG`/`USER CODE` 标记 → `gen --apply`。实测输出：

```text
新工程: D:\work\KC536X（复制 202 个文件）
不复制: out/, _build/, lib_build/, ..., .omcfg_bak_*/, *.dep, *.uvoptx, ...
标识改写（源 -> 新）:
  projects/mouse_demo/periph/user_config.h  iPROJECT_NAME  '"KC536"' -> '"KC536X"'
  projects/mouse_demo/periph/user_config.h  iPROJECT_ID_L  '0x0023' -> '0x0101'
  projects/mouse_demo/periph/user_config.h  iREAL_VERSION_ID  '5' -> '6'
  projects/mouse_demo/main/mouse_hw.c  mouse_name  'BT5.1Mouse' -> 'KC536X Bt1'
```

> SDK 里 `periph\userdefined_key_20260724.o`、`mode_24g\rf_protocol_20260704.o` 是
> `.uvprojx` 直接引用的预编译输入，会保留；它们不是本次编译产物，删除会导致链接失败。

- **目标必须不存在**：已存在直接 `[ERROR] 目标路径已存在`，退出码 2，不覆盖任何文件。
- 源工程与配置的 `project.name` 不一致是正常输入；命令结束后会列出实际改写项。
- `--name X` 可覆盖 `project.name`；配置未写 `ble_names` 时按 `X Bt1`/`X Bt2` 派生。
  配置里显式写了 `ble_names` 时以配置为准。
- 除生成区外，BLE 广播名落在 `main/mouse_hw.c`（`mouse_name` 初值）和
  `main/ex2_app_mouse.c`（`memcpy(mouse_name, ...)`，CH04 双名）；`gen` 不会改这两处，
  后续改名请重新执行 `new` 或手工修改。

### 3. 编译

```powershell
python -m omcfg check D:\work\KC536X\projects\mouse_demo\project.omcfg
UV4 -r D:\work\KC536X\projects\mouse_demo\keil5\SE71M.uvprojx -o build.log
```

实测：KC536 → KC536X 生成后 `0 Error(s), 0 Warning(s)`，Code=38576；
`user_config.h/.c` 与源工程相比，除标记/保护区行外只有 `iPROJECT_NAME`、
`iPROJECT_ID_L`、`iREAL_VERSION_ID` 三行不同，`user_config.c` 正文零差异。

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

## 图形界面：打开 → 初始化 → 改引脚 → 预览 → 应用

```powershell
launch.bat
```

界面只做展示与提交，所有校验、初始化、生成、事务都由后端 `omcfg` 完成，前端不拼宏、
不复制规则。直接打开**未初始化**的真实 SDK 也不会再让你回命令行。

### 1. 打开工程

在顶部输入 SDK 根目录（示例 `D:\work\SE71M_0023_KC536_V1_20260909`），回车或点「打开」。

- 已初始化：直接显示 28 个引脚与问题列表。
- 未初始化：弹出「初始化工程」面板，列出缺失项（缺 `project.omcfg`、缺哪个标记块）。

### 2. 初始化（仅未初始化时出现）

- 配置框会自动匹配仓库 `configs/` 里与 SDK 目录名同名的模板（如目录含 `KC536`
  就建议 `configs\KC536.omcfg`），也可以下拉选其它模板或直接填绝对路径。
- 点「初始化」并确认：安装 `project.omcfg`、插入 `OMCFG`/`USER CODE` 标记，
  **不改引脚正文**，随后自动进入正常编辑界面。
- 重复初始化是幂等的；再次打开同一工程不再出现该面板。
- 若失败，面板保留并给出可照做的提示，例如：

```text
...\user_config.h 的 'pins' 标记只出现一半，请人工修掉后再 init；
检查文件是否只读/被 Keil 占用；若提示标记块残缺，请按上方缺失项人工修掉后重试
```

### 3. 改引脚并保存

在引脚表把 `KEY_R0_PIN` 从 `P34` 改为 `P36`，点「保存引脚」；只写
`project.omcfg`，不碰源码。

### 4. 预览 diff

点「预览 diff」，右侧显示待写入文件的统一 diff；确认改动只落在目标引脚。

### 5. 应用

点「应用」，按标记块写回源码并生成 `.omcfg_bak_*` manifest。

### 6. 回滚

GUI 保持薄视图，没有回滚按钮；用「应用」后生成的 manifest 走 CLI：

```powershell
python -m omcfg rollback --manifest D:\work\SE71M_0023_KC536_V1_20260909\.omcfg_bak_<时间戳>
```

### 实测记录（真实 KC536 副本，2026-11-06）

```text
打开未初始化副本 → 面板出现，缺失项 8 条，建议配置自动带出 KC536.omcfg
点初始化 → 面板关闭，引脚 28 行，状态“初始化完成”
KEY_R0_PIN: P34 -> P36 → 保存 → 预览（diff 含 KEY_R0_PIN）→ 应用（已写入 3 个文件）
再次打开 → 不再提示初始化
UV4 -r → 0 Error(s), 0 Warning(s)，Code=38580
```

若启动时报 WebView2 缺失，请安装 Microsoft Edge WebView2 Runtime；后端 CLI 不受影响。

## CLI 参考

每个子命令都有可用的 `--help`（含示例）：

```powershell
python -m omcfg --help
python -m omcfg new --help
python -m omcfg init --help
python -m omcfg check --help
python -m omcfg gen --help
python -m omcfg rollback --help
```

| 命令 | 关键参数 | 行为 |
|---|---|---|
| `new` | `--sdk DIR --target DIR --config FILE [--name NAME]` | 复制骨架并剔除产物 → 改工程标识 → `init` → `gen --apply`；目标必须不存在 |
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
| `new` 目标已存在 | 2 | `[ERROR] 目标路径已存在: ...` + `提示: new 不覆盖任何现有目录；换一个不存在的路径，或确认旧目录无用后手工删除再执行` |
| `new` 目标位于源 SDK 内 | 2 | `[ERROR] 目标路径不能位于源 SDK 内: ...` + `提示: 把 --target 换到源 SDK 之外，避免复制自身造成递归` |
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
  ble_names: ["BT5.1Mouse"]   # 可选：new 命令据此改写 BLE 广播名
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
- 唯一例外：`new` 在成功生成后会删除它自己刚产生的 `.omcfg_bak_*`，让新工程基线
  不携带历史备份；源工程里已有的 `.omcfg_bak_*` 本来就不会被复制。

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
- `new` 之后再次修改 `ble_names` 不会自动同步 BLE 源文件（需重跑 `new` 或手工改）。
- 业务协议（RF/HID 映射）改写：不在本工具范围。
