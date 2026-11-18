# OM6239 PinMux (`om_pinmux`)

轻量配置驱动的引脚/板级特征生成器：`.omcfg` 是唯一真相，Python 校验并生成代码，只按
标记块写回 SDK，写入前有事务备份、写入后可回滚。业务协议（RF/HID 映射）不在范围内。

本文所有命令均在真实 SDK 副本上验证过（2026-11-06，CH04 与 KC536，Keil UV4
`0 Error(s), 0 Warning(s)`）。第一次上手不需要读源码。

## 环境要求

- Windows + Python 3.10+（PowerShell 或 cmd 均可）。
- `pip install -r requirements.txt`（`pyyaml`；GUI 另需 `pywebview`）。
- 编译验证需要 Keil `UV4.exe`（默认 `C:\Keil_v5\UV4\UV4.exe`）。
- 新建工程不需要外部 SDK；工具仓库内置 `baseline/sdk`（清理并已生成的 KC536 SDK，
  203 个文件，single/RGB/滚轮 20-21）。接入已有工程时才需要准备那份 SDK 的**副本**。
- 想从空白工程用选项逐步构建（CubeMX 式），用 `python -m omcfg blank`；见下方
  「空白起步」一节。它复用同一份 KC536 骨架与生成/回滚链路。

## 新工程一键生成（推荐）

只给工程名，工具从内置基线生成**可编译的新工程**：目录、项目号、BLE 广播名、默认板
参数全部由工具生成。

```powershell
python -m omcfg new --name KC536X
# 或指定落点
python -m omcfg new --name KC536X --target D:\work\KC536X
# 手工指定项目号（默认按名称派生；碰到占用会拒绝并给出建议值）
python -m omcfg new --name KC536X --id 0x0457
```

它依次完成：读取 `baseline/sdk` + `baseline/project.omcfg` → 按名称派生 ID/BLE 名 →
复制骨架（剔除产物）→ 安装 `project.omcfg` → 改写工程标识 → 插入
`OMCFG`/`USER CODE` 标记 → `gen --apply`。实测输出形如：

```text
内置基线: E:\tools\om_pinmux\baseline\sdk
新工程: D:\work\KC536X（目录由工具生成）
工程名: KC536X
项目号: 0x???? / 0x071 / v1（按名称派生）
BLE 广播名: KC536X Bt1 / KC536X Bt2
新工程: D:\work\KC536X（复制 203 个文件）
标识改写（源 -> 新）:
  projects/mouse_demo/periph/user_config.h  iPROJECT_NAME  '"CH04"' -> '"KC536X"'
  ...
```

> 基线里 `periph\userdefined_key_20260724.o`、`mode_24g\rf_protocol_20260704.o` 是
> `.uvprojx` 直接引用的预编译输入，会保留；它们不是本次编译产物，删除会导致链接失败。

- **目标必须不存在**：已存在直接 `[ERROR] 目标路径已存在`，退出码 2，不覆盖任何文件。
  缺省落点是当前目录下的 `<NAME>`。
- **不再需要 `--sdk` / `--config`**：新建只有一条路径。已有 SDK 首次接入仍用
  `init`（见下文“从零到编译”），两者不会并存。
- 工程名限制：非空、≤24 字符、不含 `/ \ : * ? " < > |` 与换行、不以 `.` 开头。
- 项目号默认按名称的 CRC32 低 16 位派生（`0x0000` 改用 `0x0001`），高 16 位继承
  基线（`0x071`），版本固定 `1`；可用 `--id 0x0457`（或十进制）手工指定低 16 位。
- 生成前先把 `(low, high, name)` 与 `baseline/project.omcfg`、`configs/*.omcfg`、
  目标父目录下已生成的 `*/projects/mouse_demo/project.omcfg`、以及 `--scan` 目录
  比对。重复时**一律拒绝**（退出码 1），列出占用者并给出未占用的 `--id` 建议。
  理由：项目号用于烧录/配对身份区分，只警告会产出两块同 ID 实物，事后无法自动
  分辨，只能返工；拒绝发生在写盘前，成本最低。
- BLE 广播名固定派生为 `<NAME> Bt1` / `<NAME> Bt2`；除生成区外落在
  `main/mouse_hw.c`（`mouse_name` 初值）和 `main/ex2_app_mouse.c`
  （`memcpy(mouse_name, ...)`）。后续改名请重新执行 `new` 或手工修改。
- 基线来源、许可证（SDK 自带 `LICENSE.md`，OM-SLA01）与文件树摘要见
  `baseline/META.json`；更新方式见 [docs/PLAN-INTERNAL-SDK.md](docs/PLAN-INTERNAL-SDK.md) §3.1。

### 编译

```powershell
python -m omcfg check D:\work\KC536X\projects\mouse_demo\project.omcfg
UV4 -r D:\work\KC536X\projects\mouse_demo\keil5\SE71M.uvprojx -o build.log
```

## 空白起步：从选项构建工程（CubeMX 式）

### 图形界面（推荐）：双击 `launch.bat`

启动页只有两条路径：**从空白新建工程**（推荐）或 **打开已有工程**。选定后进入向导：
左侧步骤条回答「我在哪」，右侧工程健康卡回答「还差什么」，底部唯一主按钮回答「下一步做什么」。
任何禁用态都会写出具体原因（例如「还差 3 个必需脚」），不会静默置灰。

**从空白新建（6 步）**

| 步骤 | 操作 | 说明 |
|---|---|---|
| 1 | 填项目名 / 项目号 / 客户 / 版本 / 输出根目录，点「下一步」 | 从内置 KC536 骨架复制一份引脚为空的草稿工程；目标目录必须不存在 |
| 2 | 点选模式 / 灯效 / 滚轮，点「下一步」 | 板型决定哪些角色必需；改动即时写入配置 |
| 3 | （可选）打开「灯带 LEDC」插件开关，点「下一步」 | 勾选即注入 4 个文件、解锁 2 个角色、自动腾让 P01→P36；取消会对称撤销 |
| 4 | 选需求组 → 选角色 → 脚位图点绿格分配，点「下一步」 | 需求组 / 约束栏 / 脚位图是同一批角色的三种视图，选中即联动；缺必需脚或有冲突时「下一步」禁用并写明原因 |
| 5 | 点「生成预览」，点「下一步」 | 只计算 diff，不写盘 |
| 6 | 点「生成工程（写盘）」 | 事务写回，给出 manifest 路径与回滚命令 |

右侧健康卡实时显示 `已配 X/Y · 缺必需 N · 冲突 N · 可生成 是/否`，缺项可点击直接跳回配脚。
草稿态允许保存中间结果；「一键按推荐配置」是第 4 步的**可选**动作（整组覆盖、保证编码器成对），
不勾选也能走完向导 —— 新工程本就不需要与 KC536 脚位一致。
GUI 产出的工程实测 Keil **0 Error / 0 Warning**。

**打开已有工程（4 步）**：选择 SDK（缺标记时引导初始化或从现状推导配置）→
检查与调整（同一套三视图工作区，严格校验）→ 预览 diff → 应用。

界面设计依据见 `docs/UI-DESIGN-PLAN.md`，可交互原型见 `docs/ui-prototype.html`。

### 命令行：等价的 `blank` 子命令族

`new` 从 KC536 现状快照出发（引脚已满）。如果想要**空白工程、逐项勾选功能**，
用 `blank` 子命令族。它用同一份 KC536 SDK 骨架，装一份引脚为空的草稿配置，
你按选项把角色一个个放到脚上，补齐后走同一条 `gen`/事务链路。

```powershell
python -m omcfg blank new --name MyMouse          # 建空白工程（引脚 0 个）
python -m omcfg blank options                      # 列出 v1 功能角色 + 推荐脚/备选/合法脚
python -m omcfg blank options --all                # 列出全部角色
python -m omcfg blank assign --sdk <DIR> --role KEY_R0_PIN --pin P10
python -m omcfg blank remove --sdk <DIR> --role KEY_R0_PIN
python -m omcfg blank status --sdk <DIR>           # 还缺哪些必需脚、能否生成
python -m omcfg blank build --sdk <DIR>            # dry-run 预览
python -m omcfg blank build --sdk <DIR> --apply    # 生成源码并写回（可 rollback）
```

- **选项数据**在 `omcfg/data/options.json`：每个角色带 `suggested_pin`（取 KC536
  基线现状）、`alternate_pins`（其他模板出现过的脚）、`allowed_pins`（芯片 mux
  约束）、`required` / `build_required`（必需与 key_io 硬依赖）。GUI 的
  `role_capabilities()` 与 CLI 共用这份数据。
- **可生成条件**：`validate.required_roles` 按板型推导的必需脚 + `key_io.h`
  无条件展开的 `KEY_B/KEY_P/KEY_DPI/KEY_PAIR` 全部落位，且无冲突。
  `blank status` 会列出缺项；缺项时用 `build` 会被拒绝（退 1）。
- 空白起步交付的工程，按推荐脚补齐后与 KC536 现状等价，Keil 实测
  **0 Error / 0 Warning**。手动改板型选项（`blank` 的 board 配置或 GUI）
  只影响必需角色集合，不碰生成/回滚链路。

## 功能插件：像 CubeMX 一样勾选扩展（可拔插）

KC536 是干净底座；新板需要的功能（如灯带 LEDC）通过**插件**勾选获得，
不手改源码。插件契约在 `omcfg/data/plugins.json`，勾选 = 改板型选项 +
腾让冲突脚 + 从内置模板注入文件 + 解锁一组角色，全部随工程持久化。

**GUI 用法**：打开「按角色配引脚」面板 → 需求组里带勾选框的项（当前是
「灯带」）即插件。勾上后自动：把 `board.logo` 设为 `ledc`、把占用 DIN
合法脚的 `LED_MODE_B` 腾到 P36、注入 `ledc.c/.h`、`ledc_mode.c/.h` 四个
文件并登记 Keil 工程；约束栏随即出现 `LEDC_PIN`(DIN) 和 `LEDC_CTRL_PIN`
两个角色供配脚。**取消勾选**会干净撤销：删文件、撤登记、还原 logo、
解除角色。

**程序化调用**：插件通过 `omcfg.api.Api` 暴露（`plugin_status` /
`plugin_toggle(sdk, "ledc", True|False)`），GUI 与脚本共用；当前没有 CLI
子命令。所有插件行为由 `plugins.json` 数据驱动，新增插件只需加一条契约 +
对应模板目录，无需改 GUI 代码。

关键约束（已封装进插件契约，不用手工处理）：
- `LEDC_PIN` 只有 P01/P05 两个合法脚，与 RGB 占用冲突——勾选时自动腾脚。
- KC536 的 `led.c`/`user_config.c` 无条件引用 `LED_R/G/B`，灯带模式下
  这三个宏仍会生成（需要保留对应脚位）。
- 内置 `ledc.h` 自带 `GPIO_SET/GPIO_CLEAR` 大小写兼容，跨工程即插即用。

实测：空白工程 → 补齐 → 勾 LEDC → 配 DIN/CTRL → 生成 → Keil
**0 Error / 0 Warning**；取消插件后无文件残留。

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

预期：`configs/CH04.omcfg`、`configs/KC536.omcfg` 各 `errors: 0`、`warnings: 0`。
全部通过时退出码 0。

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

- 已初始化：直接显示 32 行封装脚位表、6 个片内/保留脚与未分配功能列表。
- 未初始化：弹出「初始化工程」面板，列出缺失项（缺 `project.omcfg`、缺哪个标记块）。
  配置框**只预填真实存在的文件**：工程内已有 `project.omcfg` 就预填它，否则匹配
  `configs/` 同名模板；两者都没有就留空并提示。

### 2. 初始化（仅未初始化时出现）

两条路，按工程现状选：

1. **仓库已有模板**：`configs/` 里与 SDK 目录名同名的 `.omcfg` 会自动匹配
   （如目录含 `KC536` → `configs\KC536.omcfg`），确认后点「初始化」。
2. **新板首次接入**（`configs/` 里没有对应模板）：点「从工程现状生成配置」，
   后端读取当前 `user_config.h/.c` 推导引脚、模式、上下拉、电平、工程标识，
   生成初稿 `project.omcfg` 并直接初始化。初稿是**现状快照**，不是重新设计，
   `gen --dry-run` 应对 `user_config.h/.c` 零差异；生成后可在 GUI 里继续改引脚。

初始化只安装 `project.omcfg`、插入 `OMCFG`/`USER CODE` 标记，**不改引脚正文**，
随后自动进入正常编辑界面。重复初始化是幂等的；再次打开同一工程不再出现该面板。

失败时面板保留并给出可照做的提示，例如：

```text
配置不存在: ...\projects\mouse_demo\project.omcfg；
该路径是初始化后写入 project.omcfg 的位置，不是输入配置；
请从 configs/ 选择 .omcfg，或点「从工程现状生成配置初稿」
```

```text
...\user_config.h 的 'pins' 标记只出现一半，请人工修掉后再 init；
检查文件是否只读/被 Keil 占用；若提示标记块残缺，请按上方缺失项人工修掉后重试
```

### 3. 改引脚并保存

引脚区以**封装脚号 1–32** 为主键（不是宏列表）：

| 列 | 内容 |
|---|---|
| 脚号 / 脚名 / 边 | 来自 `chip/om6239.json` 的 `package_pins`，如 `1 / P32 / left` |
| 当前功能 | 该脚已分配的角色（取自 `pins`），多角色时显示为只读 |
| 可选功能 | 该脚在 `mux` 里具备的复用能力 + 当前可分配的角色下拉 |
| 状态 | 空闲 / 已分配 / 固定（VDD、USB、Flash、XTAL 等）/ 复用受限 |

副表「片内 / 保留脚」列出 `P14–P17`、`P35`、`P37` 及其固定用途；下方
「未分配功能」列出配置里还没落脚的必需/可选角色，并提示缺少哪个。

操作方式：在某个脚的下拉里选功能即可分配；同一角色被选到新脚时，旧脚的下拉
自动清空（移动）；选「（解除）」即解除分配。必需角色可移动、但在别处未重新选择
时不允许解除（提示“必需/驱动引用：可移动，不可解除”）。点「保存引脚」只写
`project.omcfg` 的 `pins` 段，不碰源码；校验错误在保存时直接返回，不落盘。

例如把 `KEY_R0_PIN` 从 `P32` 改到空闲的 `P10`：保存 → 预览 → 应用，源码侧
只有 `user_config.h` 的一行 `#define KEY_R0_PIN (P10)` 变化。

### 4. 预览 diff

点「预览 diff」，右侧显示待写入文件的统一 diff；确认改动只落在目标引脚。

### 5. 应用

点「应用」，按标记块写回源码并生成 `.omcfg_bak_*` manifest。

### 6. 回滚

GUI 保持薄视图，没有回滚按钮；用「应用」后生成的 manifest 走 CLI：

```powershell
python -m omcfg rollback --manifest D:\work\SE71M_0023_KC536_V1_20260909\.omcfg_bak_<时间戳>
```

### 实测记录（真实副本，2026-11-06）

```text
[KC536] 打开未初始化副本 → 面板出现，缺失项 8 条，建议配置自动带出 KC536.omcfg
[KC536] 点初始化 → 面板关闭，引脚 28 行，状态“初始化完成”
[KC536] KEY_R0_PIN: P34 -> P36 → 保存 → 预览（diff 含 KEY_R0_PIN）→ 应用（已写入 3 个文件）
[KC536] 再次打开 → 不再提示初始化；UV4 -r → 0 Error(s), 0 Warning(s)

[E606] 打开未初始化副本 → 面板出现，配置框留空（不再预填工程内 project.omcfg）
[E606] 手动填入 project.omcfg → 提示“该路径是初始化后写入的位置，不是输入配置”，面板保留
[E606] 点「从工程现状生成配置」→ 推导 28 个引脚并初始化，面板关闭
[E606] KEY_R0_PIN: P34 -> P36 → 保存 → 预览（diff 含 KEY_R0_PIN）→ 应用（已写入 3 个文件）
[E606] 再次打开 → 不再提示初始化；gen --dry-run 与现状一致；UV4 -r → 0 Error(s), 0 Warning(s)
```

若启动时报 WebView2 缺失，请安装 Microsoft Edge WebView2 Runtime；后端 CLI 不受影响。

## 引脚视图与冲突检测

### 数据模型

- **芯片事实**：`chip/om6239.json` 的 `package_pins`（脚号 ↔ `Pxx` ↔ `alt`）、
  `mux`（`LEDC_SEL`/`ENCODER`/`LVD`/`USB` 的合法组合）、`reserved_pins`
  （`P14–P17`、`P35`、`P37`）、`internal_flash`（`FLASH_CS/SCLK/MOSI/MISO` 的固定脚）。
- **配置真相**：`.omcfg` 的 `pins`（角色 → `Pxx`）。界面上的脚位表只是它的投影，
  不产生第二份数据；保存后仍由既有 `gen` 标记块链路写回源码。
- **后端 `omcfg/pinmap.py`**：`rows()` 输出 32 个封装脚 + 片内脚 + 未分配角色；
  `assignable_roles()` 给出某脚当前可分配的角色；`allowed_pins()` 给出某角色的
  候选脚；`role_pin_problem()` 判断“该脚是否具备该功能”并给出原因。
- **保存**：GUI 调 `Api.save_pinmap()`，可传全量或部分映射，`""` 表示解除；
  一次校验、一个事务。`board.wheel` 由 `WHEEL_A/B` 的脚对自动回写，无需手填。

### 四类冲突（`check` / GUI 保存 / `gen` 共用同一套校验）

| 类型 | 真实输出（节选） | 退出码 |
|---|---|---|
| 同脚多功能 | `[ERROR] pins: P32 被重复分配: KEY_R0_PIN, KEY_R1_PIN` | 1 |
| 缺必需脚 | `[ERROR] pins.MODE_BLE_PIN: 当前板型需要 MODE_BLE_PIN，但配置缺少` | 1 |
| 复用矩阵非法 | `[ERROR] board.wheel: WHEEL_A/B 必须是 ENCODER 四对之一（当前 P00+P06）` | 1 |
| 复用矩阵非法（LEDC） | `[ERROR] pins.A_LED_PIN.pin: P34 不具备 LEDC 功能（LEDC_SEL 只能 P01/P05/P21/P33）` | 1 |
| 保留脚被占用 | `[ERROR] pins.SENSOR_SCLK_PIN.pin: P14 是片内 Flash 保留脚，只允许 FLASH_MISO_PIN` | 1 |
| 固定脚被占用 | `[ERROR] pins.SENSOR_SDIO_PIN.pin: P02 固定为 USB 差分脚，不能接 SENSOR_SDIO_PIN` | 1 |

固定脚/保留脚的具体集合直接读芯片数据：`USB_DN/DP = P02/P03`，`LVD ∈ P23/P33`，
`LEDC_CTRL ∈ P01/P05/P21/P33`，`ENCODER` 四对 `P00/P01`、`P05/P06`、`P20/P21`、
`P24/P25`。`SCLK/SDIO/UART` 在 SDK 里是软件 GPIO 位翻转，`alt` 只作界面提示，
不作硬约束。

### 模块连带规则（`python -m omcfg check --rules`）

规则是 `omcfg/rules.py` 里的一张可读清单，不是规则引擎。`check --sdk <SDK>`
会对每条规则做静态审计（跨 `user_config` / `key_io` / `ledc`），strict 模式下
error 计入退出码；GUI 保存与 `gen` 只提示、不阻塞。

```text
id              level   files                       summary
pins.macro      error   user_config.h pins 块       角色宏值必须等于配置脚位
pins.gpio_table error   user_config.c gpio_table    每个已分配角色必须出现在 GPIO 表
pins.wake       error   user_config.h               唤醒掩码与 EN/DIS 的角色集合必须一致
key_io.refs     error   key_io.h / key_io.c         key_io 必须引用配置中的按键角色
led.polarity    error   user_config.h               灯极性与 led_*_on() 的 gpio 操作一致
led.driver      warning ledc.c                      LEDC_SEL 驱动选择与灯脚提示
led.sleep       error   user_config.c sleep 块      sleep 断电列表必须覆盖灯脚
dpi.table       warning sensor.c                    DPI 档位表与配置一致
dpi.persist     warning flash_process.c             DPI 持久化表存在且回退到出厂表
dpi.default     warning sensor.h                    默认 DPI 档位与配置一致
```

命中示例（真实命令输出）：

```text
[WARNING] pins.macro: pins.KEY_R0_PIN: 配置为 P10，user_config.h 为 P32
        提示: 说明修改绕过生成；执行 python -m omcfg gen --sdk <SDK> --apply
[ERROR] pins.wake: PIN_WAKE_UP_MASK: 唤醒角色 [...] 与配置 [...] 不一致
        提示: 改脚位后必须同步唤醒掩码；执行 gen --apply
[ERROR] key_io.refs: pins.KEY_C0_PIN: key_io.c 无条件使用 KEY_C0_PIN，但配置已解除
```

### 二期实测记录（真实副本，2026-11-06）

```text
[OM_PIN_02] new --name OM_PIN_02 → 项目号 0x8525 / 0x071 / v1；UV4 -b 0 Error/0 Warning
[OM_PIN_02] save_pinmap({"KEY_R0_PIN": "P10"}) → ok=true, changed=1（伴随 pins.macro warning）
[OM_PIN_02] gen --apply → 源码只有 user_config.h 的 #define KEY_R0_PIN (P10) 一行变化
[OM_PIN_02] UV4 -b → 0 Error(s), 0 Warning(s)（Code=39436 RO=2120 RW=208 ZI=2292）
[OM_PIN_02] 与改脚前快照 diff：user_config.h（宏一行）、project.omcfg（P32→P10）、SE71M.bin
[冲突] 同脚/缺必需脚/复用矩阵/保留脚四种，check 均退出 1，提示可照做
[反向] 手删 PIN_WAKE_UP_MASK 中 KEY_PAIR_PIN → check --sdk 报 pins.wake，退出 1
[反向] 配置改 P06 但未 gen → pins.macro 报“配置为 P06，user_config.h 为 P10”，退出 1
[幂等] 全量映射连续保存两次 → changed 0 0；gen --dry-run 无变化
[ID] new --id 0x0457（已占用）→ 拒绝并列出占用者，建议 --id 0x0001，退出 1
```

## CLI 参考

每个子命令都有可用的 `--help`（含示例）：

```powershell
python -m omcfg --help
python -m omcfg new --help
python -m omcfg init --help
python -m omcfg check --help
python -m omcfg gen --help
python -m omcfg blank --help
python -m omcfg rollback --help
```

| 命令 | 关键参数 | 行为 |
|---|---|---|
| `new` | `--name NAME [--target DIR] [--id 0xXXXX] [--scan DIR]` | 从内置基线复制骨架并剔除产物 → 改工程标识 → `init` → `gen --apply`；目标必须不存在；项目号默认按名称派生，可用 `--id` 手工指定，重复一律拒绝 |
| `blank` | `new/options/assign/remove/status/build` | 空白起步：建引脚为空的草稿工程，按选项逐项分配脚位，补齐后生成；见「空白起步」一节 |
| `init` | `--config FILE --sdk DIR [--force]` | 安装 `project.omcfg`，插入 `OMCFG`/`USER CODE` 标记；一次性 |
| `check` | `FILE...`、`--all DIR`、`--sdk DIR`、`--rules` | 只校验，不写盘；`--sdk` 追加跨文件同步审计（严格）；`--rules` 打印连带规则清单；有 error 返回 1 |
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
| `new` 项目号重复 | 1 | `[ERROR] 项目号 0x0457 / 0x071 已被占用` + 列出占用者 + `可改用: --id 0x0001` |
| `--id` 越界/无法解析 | 1 | `[ERROR] --id 超出范围: 0` 或 `[ERROR] 无法解析 --id: abc` + `提示: 范围是 1..0xFFFF` |
| 同脚被两个角色占用 | 1 | `[ERROR] pins: P32 被重复分配: KEY_R0_PIN, KEY_R1_PIN` + `提示: 一个封装脚只能有一个功能` |
| 复用矩阵非法 | 1 | `[ERROR] board.wheel: WHEEL_A/B 必须是 ENCODER 四对之一（当前 P00+P06）` |
| 保留脚被占用 | 1 | `[ERROR] pins.SENSOR_SCLK_PIN.pin: P14 是片内 Flash 保留脚，只允许 FLASH_MISO_PIN` |
| `check --all` 与 `--sdk` 同时给 | 2 | `[ERROR] --all 与 --sdk 互斥` + `提示: 板模板只对自身配置做同步审计` |
| 改配置绕过生成 | 1（`check --sdk`） | `[WARNING]/[ERROR] pins.macro: 配置为 P10，user_config.h 为 P32` + `提示: 执行 gen --apply` |
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
  sensor:
    bus: sdio_3wire
    dir_clock: 6
    dpi_levels: [1200, 1600, 2400, 3600, 4800, 6400]   # 可选：DPI 档位（≤8 档，200 的倍数）
    dpi_default: 1                                      # 可选：默认档位下标（从 0 开始）
  wheel: ENCODER_PINMUX_SEL_IO_20_21
pins:
  KEY_R0_PIN: P34
  ...
```

`features`、唤醒掩码、`LVD_CHECK_INDEX`、`WHEEL_IO_SELECT`、模式脚等由 `pins`/`board`
派生，不写进配置。`board.sensor.dpi_levels`/`dpi_default` 是可选的元数据，用来和
`gen` 之外手工维护的 `sensor.c`/`sensor.h` 做一致性提示，不参与 `sensor.c` 生成。

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

- `chip/om6239.json`：芯片引脚与复用约束（含 `reserved_pins`/`internal_flash`），校验器只读它。
- `omcfg/pinmap.py`：按封装脚位视图、候选功能推导与“该脚是否具备该功能”判断。
- `omcfg/rules.py`：模块连带规则清单（`check --rules`）与跨 `user_config`/`key_io`/`ledc` 审计。
- `baseline/`：内置 SDK 基线（`sdk/` + `project.omcfg` + `META.json`），`new` 的唯一来源。
- `docs/PLAN-INTERNAL-SDK.md`：内置 SDK、命名即建、引脚数据模型与三期路线。
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
