# 轻量 CubeMX 式配置工具：指导文档（Plan）

> 目标：把 om_pinmux 收敛成“一个配置源 → 校验 → 生成代码/工程”的轻量工具，像 CubeMX 一样直白，但只服务 OM6239 一颗芯片、一套鼠标 SDK。
> 本文只定方向与实施计划，不含代码改动。实测依据来自 2026-11-06 的源码与运行记录（见 `docs/om_pinmux-OVERVIEW.md`）。

---

## 0. 结论：改进现有 om_pinmux（结构性重构），不是从零重写

**核心理由：真正值钱的资产（芯片脚位库、7 块板的真实数据、`key_io` 契约改写、备份/回滚）都可以复用；真正的包袱（把生成逻辑写进 91 KB 的 `index.html`、四份引脚宏清单、金机对照/供体移植/问卷三个子系统）必须删掉。重写会把这些资产重新做一遍，改造则只需换掉核心四块。**

### 0.1 判断依据

| 现有资产 | 价值 | 处置 |
|---|---|---|
| `chip/om6239.json`（32 封装脚、26 GPIO、5 类 mux、LEDC/滚轮冲突教训） | 唯一一份芯片事实，验证过 | 保留，补字段（UART/SPI/I2C/PWM 可用脚） |
| `boards/*.json`（7 块板，25–30 脚/板，含 `source` 与板型注意事项） | 人工对照原理图整理的真实数据 | 转成 `.omcfg` 模板，字段做删减（见 §2.4） |
| `validation.py` 的规则语义（同脚冲突、模式脚、USB 固定脚、编码器对、LVD 派生） | 规则是从踩坑里长出来的，有测试 | 保留语义，改成由芯片数据驱动（§3） |
| `biz_sync.py` 的 `key_io.h/c` 改写（单/双模式、PAIR、DPI 分支） | 换板最痛的一步，端到端实测生效（6 个 action） | 保留，但只留 `key_io`/sleep 契约，删 RTE/LEDC 同步、删 17 项体检 |
| `operations.py`（备份 + manifest + rollback） | 直接改 SDK 的安全网 | 原样保留，并让 CLI 也走它 |
| `index.html` 的芯片封装图 / 角色列表 / 参数表单 | 交互雏形可用 | 保留视觉与交互，删掉其中全部生成与校验逻辑 |
| `golden_diff.py` + `synth_golden.py` + `synth/` + `reports/` | 试图用“金机基线”保证正确性 | **删除/归档**；基线应由 git + 编译承担（§6） |
| `port_apply.py` + `board_pack.py` 13 项策略/供体拷贝 | KC536→CH04 特定迁移流程 | **归档**；只抽 3 个 opt-in 文本补丁（§6） |
| `survey.py` + `survey/`（9 节 57 问） | 收集板数据的过渡手段 | 归档；数据进 `.omcfg` 模板即可 |
| `index.html` 里的 `CHIP`(L608)/`PRESETS`(L714)/`generate*`(L1307–L1862) | 与 Python/JSON 重复的第四份真相 | **删除**，这是最大的包袱 |
| `tests/`（8 用例，1 个红；`test_wheel_soft_gpio.py` 为 0 字节） | 有测试框架但覆盖错位 | 重写为 schema/生成/事务/uvproj 四组 |

### 0.2 若选“改进”，边界在哪

- **保留仓库与目录**（不另起新项目），保留 `launch.bat`/pywebview 外壳、`chip/om6239.json`、`boards` 数据、`operations.py`、`key_io` 契约逻辑。
- **重写四块核心**：配置模型、校验、生成、CLI；GUI 只保留“视图 + 表单”，所有生成/校验调用后端。
- **删除三个子系统**：金机对照体系（`golden_diff`/`synth_golden`/`synth`/`reports`）、供体移植体系（`port_apply` + `board_pack` 的 donor/policy）、问卷体系（`survey`）。
- **硬边界**：不允许再出现第二份引脚宏/板型真相；不允许任何生成逻辑留在 HTML/JS；不允许“猜锚点”式插入（见 §7-3）。
- **兼容期**：重构期间旧模块先冻结（不加功能），新链路在真实工程副本上验证通过后再删旧文件；删除动作单独一个 commit，便于回退。

---

## 1. 产品形态：要什么、不要什么

### 1.1 必须有（对标 CubeMX 的最小集合）

| 能力 | 具体形态（不是口号） |
|---|---|
| 引脚与复用配置 | 封装图点击选脚；每个脚可选功能（GPIO 输入/输出、矩阵行列、滚轮 A/B、模式脚、传感器、LED、USB、UART/SPI）；复用类功能（LEDC/UART/SPI/ENCODER）必须从 `mux` 候选里选，不能手填任意 `Pxx` |
| 外设启用开关 | UART/SPI/USB/LEDC 各一个 `enabled`；关闭时其引脚回到 GPIO 或标为 unused；开启时必须填齐必需脚 |
| 外设参数 | UART：波特率/引脚；SPI：模式/引脚；USB：固定脚 + `id/version`；传感器：`sdio_3wire`/`spi_4wire` + 时钟相位；LED：RGB/LEDC + 极性 |
| 时钟 | 只做“有数据支撑的部分”：系统时钟频率、传感器时钟相位；**不做 PLL 求解器**（芯片数据里没有完整时钟树，先别假装有） |
| 冲突与合法性校验 | 每次保存/生成前跑同一套规则：脚不存在、独占冲突、模式脚组合、编码器对、LEDC SEL 撞滚轮、USB 固定脚、外设依赖（启用 UART 但没填 TX/RX） |
| 配置文件唯一真相源 | 一个 `project.omcfg`（YAML），GUI/CLI/生成器都只读它；模板只是“另存为”的起点，运行时不参与合并 |
| 生成初始化代码 | `user_config.h`（脚位宏 + 唤醒掩码）、`user_config.c`（gpio 表 + 睡眠初始化函数）、`board_features.h`；全部写进带标记的块；睡眠函数在 `user_config.c` 内是唯一强定义，不再另起 `.pinmux.c` |
| 生成/更新 Keil 工程 | 从模板生成 `.uvprojx`：源文件分组、include 路径、宏定义按配置增删；不再“无条件追加 ledc” |
| 用户代码保护区 | 生成文件里固定 `/* USER CODE BEGIN x */ … /* USER CODE END x */`；生成器只改标记外内容，标记缺失/重复直接报错退出，**不再用 fallback 锚点猜位置** |

### 1.2 明确不做（每项一句理由）

| 不做 | 理由 |
|---|---|
| middleware / 组件生态（USB 协议栈、文件系统、LwIP 等包管理） | 我们只有一套现成 SDK，业务库不该进配置器，否则立刻变成“半个 IDE” |
| RTOS 配置 | 产品无 RTOS，配置项永远用不上 |
| 多厂商/大芯片库 | 只服务 OM6239；通用化会把数据模型做成空壳 |
| 多工程/多项目管理、团队协作、云端 | 单机单人单工程，加这些只会增加状态 |
| 实时预览（边改边渲染完整代码） | 生成只需毫秒，预览会逼出第二套渲染器；用 `diff` 看结果更可靠 |
| 图形时钟树 / PLL 自动求解 | 芯片数据缺时钟树拓扑，做出来就是假精度 |
| 金机基线/金机 diff | 与 git diff 重复，且已实测口径错误（synth 输出 `26` vs SDK `(P26)`，SAME=0） |
| 供体 SDK 整包拷贝（donor transplant） | 这是一次性迁移动作，不是持续配置行为；留在配置器里会误导“换板=拷文件” |
| 自动生成业务协议（RF/HID 映射、灯效状态机） | 业务代码不是配置；最多生成常量表（P3 再议） |
| 插件/脚本扩展系统 | 单芯片单 SDK，扩展点只会被用来绕开校验 |

---

## 2. 配置文件规范（`.omcfg`）

### 2.1 位置与唯一源

- 格式：**YAML**，后缀 `.omcfg`，编码 UTF-8，2 空格缩进，键名固定英文。
- 位置：随工程走，`<SDK>/projects/mouse_demo/project.omcfg`（对标 `.ioc` 放在工程目录）。
- 工具仓库里的 `configs/*.omcfg` **只是模板**（由现有 7 块板转换而来），GUI“另存为”后即与模板无关。
- 运行参数（SDK 路径、Keil 路径、上次打开的工程）放在 `pinmux_state.json`，**不进 `.omcfg`**，避免机器相关路径污染配置 diff。
- 依赖：`pyyaml` + `jsonschema`（两个纯 Python 小依赖）。前端不解析 YAML，只和后端交换 JSON。

### 2.2 字段边界

**只放“项目级可变参数”**：

- 芯片型号（固定 OM6239）、项目身份（名/客户/ID/版本/BLE 广播名）；
- 板型事实（模式脚组合、LOGO 类型、LED 极性、传感器总线与时钟相位、滚轮 mux）；
- 每个功能脚的 `Pxx` + GPIO 模式/上下拉/初始电平；
- 外设启用与参数（UART/SPI/USB/LEDC）；
- 生成目标（输出目录、Keil 工程相对路径、opt-in 兼容补丁名）。

**不放**（各自留在该在的地方）：

- 寄存器地址/位定义、驱动函数签名 → 留在 SDK 驱动库与 `chip/om6239.json`；
- 原理图网名 `nets`、`unused_package_gpio`、`source` 说明 → 只作为模板注释保留，不参与生成；
- `features.BOARD_*`、唤醒掩码、`LVD_CHECK_INDEX`、`WHEEL_IO_SELECT`、LED 开关宏 → **全部派生**，不写进配置（这是当前最大的重复来源）；
- 业务协议、灯效状态机、键位功能映射（v1 不做；P3 若做只生成常量表）。

### 2.3 最小可用 schema 草案

```yaml
# project.omcfg —— 唯一真相源
schema: om6239-project/v1
chip: OM6239

project:
  name: BD319
  customer: App
  ble_names: ["BD319 Bt1", "BD319 Bt2"]     # 可选；new 命令改写 BLE 广播名
  id: { low: 0x0485, high: 0x071, version: 1 }
  usb: { vid: 0x1234, pid: 0x5678 }        # 仅当 usb.enabled

board:
  mode_pins: dual          # single | dual | wired
  logo: rgb                # rgb | ledc | none
  led_polarity: active_high
  sensor: { bus: sdio_3wire, dir_clock: 6, v2_en: false }  # sdio_3wire | spi_4wire
  wheel: ENCODER_PINMUX_SEL_IO_24_25         # 或 SOFT_GPIO

# 键名直接沿用 C 宏名，生成时不再做名字映射
pins:
  KEY_R0_PIN: { pin: P26, gpio: { mode: input_pullup, pull: pu_30k, init: high } }
  KEY_R1_PIN: { pin: P20, gpio: { mode: input_pullup, pull: pu_30k, init: high } }
  KEY_R2_PIN: { pin: P21, gpio: { mode: input_pullup, pull: pu_30k, init: high } }
  WHEEL_A_PIN: { pin: P24, gpio: { mode: input_floating } }
  WHEEL_B_PIN: { pin: P25, gpio: { mode: input_floating } }
  SENSOR_MOTION_PIN: { pin: P07, gpio: { mode: input_floating } }
  SENSOR_SCLK_PIN: { pin: P11 }
  SENSOR_SDIO_PIN: { pin: P12 }
  LED_R_PIN: { pin: P04 }
  USB_5V: { pin: P32 }

peripherals:
  # P3 变异清单结论：以下段暂不落地（真实工程取值无差异，见 P3 决策记录）
  usb:  { enabled: true }                       # 脚固定 P02/P03
  uart: { enabled: false, tx: null, rx: null, baud: 115200 }
  spi:  { enabled: false, sck: null, miso: null, mosi: null, cs: null }
  ledc: { enabled: false, ctrl: null }

codegen:
  output: periph
  keil_project: projects/mouse_demo/keil5/SE71M.uvprojx
  compat: []                                    # 可选：senscan_12bit / stack_240
```

必填/可空/派生一览：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema` / `chip` | string | 是 | 固定值，版本化 |
| `project.name` / `customer` | string | 是 | 生成宏 `iPROJECT_NAME` / `iCONSUMER_NAME` |
| `project.ble_names` | list[str] | 否 | 1~2 个；仅 `new` 改写 `mouse_hw.c`/`ex2_app_mouse.c` 的广播名 |
| `project.id.low/high/version` | int(0x)/int | 是 | 生成 `iPROJECT_ID_L/H`、`iREAL_VERSION_ID` |
| `board.mode_pins` | enum | 是 | 决定生成 `MODE_24G_PIN+MODE_BLE_PIN` 或 `MODE_BLE_24G_PIN` 或无线关闭 |
| `board.logo` / `led_polarity` | enum | 是 | 决定 RGB/LEDC 宏与 `led_*_on/off` 极性 |
| `board.sensor` | object | 是 | `bus` 决定校验 SDIO 还是 MOSI/MISO/NCS；`v2_en` 为真时生成 `SENSOR_2V_IN_EN` |
| `board.wheel` | enum | 是 | 决定 `WHEEL_IO_SELECT`；`SOFT_GPIO` 时要求成对脚 |
| `pins.*.pin` | `Pxx` | 是 | 必须在封装 GPIO 白名单 |
| `pins.*.gpio` | object | 否 | 缺省按“按键=上拉输入/灯=推挽输出”给默认值 |
| `peripherals.*` | object | 是 | 未出现的段等价于 `enabled: false` |
| `codegen.*` | string | 是 | 相对 SDK 路径，不写绝对路径 |
| 派生字段 | — | 否 | `features`、`PIN_WAKE_UP_MASK`、`LVD_CHECK_INDEX`、`WHEEL_IO_SELECT`、`BOARD_*` |

### 2.4 现有板数据迁移映射（`boards/*.json` → `configs/*.omcfg`）

| 旧字段 | 新位置 | 处理 |
|---|---|---|
| `meta.projName/consumerName/projIdL/projIdH/verId` | `project` | 直接搬 |
| `meta.modePins/logoType/ledPolarity/sensorDir/wheelMux` | `board` | 直接搬（`sensorDir` → `board.sensor.dir_clock`） |
| `meta.hasKeyC0/hasExtraKeys/hasDpiPair/hasSensorNcs/hasLedLow` | 无 | **删**：由 `pins` 里是否存在 `KEY_C0_PIN/KEY_DPI_PAIR.../SENSOR_NCS_PIN/LED_LOW_PIN` 派生 |
| `features.*` | 无 | **删**：全部派生 |
| `pins.*` | `pins.*` | 直接搬（键名保留 C 宏名） |
| `derived.LVD_CHECK_INDEX / WHEEL_IO_SELECT / WHEEL_SOFT_GPIO` | 无 | **删**：派生 |
| `nets` / `unused_package_gpio` / `source` / `notes` | 无 | 删；`notes` 可转成模板顶部注释 |
| `gpio`（BD319 里每脚的默认模式） | `pins.*.gpio` | 直接搬 |

---

## 3. 架构分层

### 3.1 目标目录（同一仓库内新增，旧模块验证通过后删除）

```
E:\tools\om_pinmux\
├─ omcfg/                     # 新核心（纯 Python，可被 CLI 与 GUI 共用）
│  ├─ model.py                # 读/写 .omcfg、默认值、派生字段
│  ├─ validate.py             # schema + 业务规则（数据驱动）
│  ├─ generate/
│  │  ├─ generator.py         # 编排：选模板 → 渲染 → 标记块替换 → diff
│  │  └─ templates/           # user_config.h.j2 / user_config.c.j2 / board_features.h.j2 / sleep.c.j2
│  ├─ targets/
│  │  ├─ sdk.py               # 定位 projects/mouse_demo/periph、校验目录结构
│  │  └─ uvprojx.py           # 从模板生成/更新 Keil 工程（源分组/include/宏）
│  ├─ newproject.py           # 新工程一键生成：骨架复制排除、标识改写、备份清理
│  ├─ initproject.py          # init 共有逻辑：缺标记检测、安装配置、插入标记块
│  ├─ derive.py               # 从 user_config.h/.c 推导配置初稿（新板首次接入）
│  ├─ contracts.py            # 由 biz_sync 收敛而来：只改 key_io.h/c + sleep
│  ├─ compat.py               # 3 个 opt-in 文本补丁（senscan_12bit/stack_240/usb_tx_flag）
│  ├─ transaction.py          # 由 operations.py 平移
│  ├─ cli.py                  # check / gen / write / init / ui
│  └─ api.py                  # pywebview 桥（只做参数校验 + 调 cli/model）
├─ chip/om6239.json           # 保留，补 mux 字段
├─ configs/                   # 模板（7 块板 + blank）
├─ web/                       # 新前端：index.html(<20KB) + app.js + style.css
├─ tests/                     # schema / 规则 / 生成 / 事务 / uvproj
├─ docs/
└─ launch.bat, launch.ps1, pinmux_state.json
```

### 3.2 依赖方向（单向，禁止回指）

```
chip/om6239.json ─┐
configs/*.omcfg ──┴→ model.py → validate.py → generate/ + targets/
                                              ↓
                                            cli.py → api.py → web/
```

- `model/validate/generate/targets/contracts` **不得** import `api`、`web`、`launch`；
- `api.py` 只能是薄壳：`load_config / save_config / check / gen_preview / gen_apply` 5 个方法左右；
- `web/` 不发号施令：它只提交 JSON 配置、展示后端返回的 issues/diff。

### 3.3 硬规则

1. **核心逻辑必须能在 CLI 里跑**：任何一个 GUI 按钮对应的动作，都必须有一条 `python -m omcfg …` 等价命令；否则就是没搬干净。
2. **生成器只认配置对象**，不读 UI 状态、不读 board JSON；模板里不出现条件硬编码（条件来自 `model` 的派生结果）。
3. **校验只有一份**：GUI 每次保存/生成前调 `validate.py`；前端不再写第二套 `runValidation()`。
4. **写文件只有一条路**：`generate/generator.py` 产出“目标文本 + diff”，`transaction.py` 落盘并写 manifest；GUI 与 CLI 都走这条路。

---

## 4. 实施路线（3 阶段，每阶段有硬验收）

> 每个阶段结束都必须满足“命令能跑 + 工程能编 + diff 可看”。不满足就不进下一阶段。

### P1：最小闭环（配置 → 校验 → 生成 → 写回），CLI 先行

**范围**
- 新增 `omcfg/`：`model.py`、`validate.py`、`generate/`、`transaction.py`、`cli.py`；
- 只做 4 类产物：`user_config.h`、`user_config.c`、`board_features.h`、`periph_gpio_sleep_set.pinmux.c`；P2 起睡眠实现并入 `user_config.c`（见 P2 决策记录），只剩 3 个文件；
- 只做 3 类配置：`pins`、`board`、`project`；
- 迁移 BD319 与 CH04 两块板做模板；其余 5 块先不动；
- 旧 GUI **冻结只读**（不再生成/写入），避免双实现。
- 删除/停用：`golden_diff`、`synth_golden`、`port_apply` 全链路（它们不参与 P1）。

**验收（可执行）**
```bat
:: 1) schema + 规则，0 error
python -m omcfg check configs\BD319.omcfg
:: 2) 生成预览（只输出 unified diff，不落盘）
python -m omcfg gen --config configs\BD319.omcfg --sdk <真实SDK副本> --dry-run
:: 3) 落盘（走 transaction，产出 manifest）
python -m omcfg gen --config configs\BD319.omcfg --sdk <真实SDK副本> --apply
:: 4) 只改标记块：diff 里除标记块外为空
git -C <真实SDK副本> diff --stat
:: 5) 能编过（Keil 命令行；无 CLI 则 uVision 手工编译并保存日志）
UV4 -b <uvprojx> -o build.log
```
- **通过标准**：`check` 退出码 0；`--dry-run` 的 diff 与手工基线一致；`--apply` 后 `build.log` 0 error；manifest 可 `rollback` 复现。
- **本阶段放弃**：GUI 重写、`.uvprojx` 生成、外设参数页、时钟页、兼容补丁。
- **本阶段必须删**：`index.html` 里的 `CHIP`/`PRESETS`/`generate*`（L608/L714/L1307–L1862），以及 `biz_sync.PIN_MACROS`（改由 model 派生）。

### P2：工程文件 + 用户代码保护区 + 薄 GUI

**范围**
- `targets/uvprojx.py`：用模板生成 `.uvprojx`（源分组、include 路径、宏），按 `board.logo`/`peripherals` 增删源文件；**不再无条件加 ledc**；
- 睡眠初始化实现并入 `user_config.c` 的 `/* OMCFG BEGIN sleep */` 块，由配置生成**唯一强定义**；`periph_gpio_sleep_set.pinmux.c` 退场：不再生成、从 `.uvprojx` periph 组移除，旧副本中的遗留文件改写成指向 `user_config.c` 的注释；
- 禁止用 `#if 0` 或另起源文件绕过重复符号；板型差异（LOGO、双/单模式脚）在生成阶段展开，最终产物里不得靠预处理器屏蔽来通过编译；
- 用户代码保护区：`user_config.h/.c` 与 `board_features.h` 固定 `/* USER CODE BEGIN x */ … /* USER CODE END x */`；缺失 → 报错并提示 `omcfg init`；
- 标记块规范：`/* OMCFG BEGIN <name> */` … `/* OMCFG END <name> */`；缺失/重复 → 报错退出，不猜锚点；
- `api.py` + `web/`：前端瘦身到“封装图 + 表单 + issues + diff”，所有动作调后端；
- 迁移剩余 5 块板（MW650 的 `wired` 必须在校验器中被正式支持，否则不迁）；
- 删除正式生效：`golden_diff.py`、`synth_golden.py`、`port_apply.py`、`synth/`、`reports/`、`layout_lab.html`、`assets/`。

**验收**
```bat
python -m omcfg gen --config configs\CH04.omcfg --sdk <KC536副本> --apply
UV4 -b <uvprojx> -o build.log                 :: 0 error
python -m omcfg check --all configs\*.omcfg   :: 7/7 通过
python -m pytest                              :: 全绿
```
- **diff 验收**：生成的 `.uvprojx` 与仓库里现有那份，差异只能是“源文件/路径/宏”；不出现“引用不存在文件”（P1 实测过的 `ledc.c` 问题必须消失）。
- **GUI 一致性验收**：同一配置在 GUI 保存后，CLI 再次 `gen --dry-run` 输出“无变化”。
- **本阶段延后**：外设参数（UART/SPI/USB）、兼容补丁、时钟页。

**P2 决策记录：睡眠初始化函数的归属（取代 `#if 0` 过渡方案）**
- 问题：`periph_gpio_sleep_set()` 只在 `user_config.c` 中定义；把参考实现放进独立 `.pinmux.c` 会重复符号，`#if 0` 只是屏蔽编译、不是解决归属。
- 结论：函数体由 `templates.render_sleep()` 按 `board.logo` / `board.mode_pins` / `LED_LOW_PIN` 展开，写入 `user_config.c` 的 `OMCFG sleep` 块；`omcfg init` 把 SDK 原有手写实现（含文档注释）原样包进该块，重生成后成为唯一强定义。
- 生成内容逐行复刻两块板既有写法：KC536 的 `user_config.c` 除新增标记行外零差异；CH04 同样是零功能差异。
- `periph_gpio_sleep_set.pinmux.c` 不再生成、不再列入 `.uvprojx`；旧副本残留文件由 `gen` 改写为一行退场说明。禁止再以 `#if 0` 或另起源文件的方式恢复该文件。

### P3：外设参数（按真实变异收敛）

**P3 决策记录：先做变异清单，再决定配置面（2026-11-06）**

对 6 个真实 SDK 家族（20 份 `user_config.h`、22 份 `usb_descriptor.h`，含 CH04/KC536/BD319/V196/S205/BJ2017/LJ-V08）做宏级对比，结论：

- **进配置**：
  - `board.sensor.bus: spi_4wire` 完整生成 `SENSOR_MOSI_PIN`、`SENSOR_MISO_PIN`、`SENSOR_NCS_PIN`（5 块真实板/6 个工程；原生成器只输出 NCS，属“配置项存在但生成不完整”）；
  - `board.sensor.v2_en`（布尔，默认 false）→ 生成 `SENSOR_2V_IN_EN (1<<7|1<<6)`（与 SPI 4-wire 板型同步出现，`sensor.c` 直接使用该宏）；
  - `board.ledc_rgb_number` 沿用 P2 字段，真实取值为 6/7/10，默认 6。
- **不进配置**（有差异但无复用价值）：
  - USB VID/PID：22/22 均为 `0x32C2`/`0x0024`，序列号字符串也一致；只有厂商文案有 2 种写法，不是电气/协议差异；
  - `RF_RATE`/`RF_PROTOCOL`/`RF_CONN`/`iAPP_ID_H`：20 个工程取值一致；
  - 休眠策略：`MOUSE_ENTER_SLEEP_TIME_MINUTE=60`、二级休眠计数 10，22/22 一致；
  - DPI 档位：`iDPI_MODE0..4_VLAUE` 22/22 全为 2，`DEFAULT_DPI_GRADE` 仅 1 个工程为 2；
  - LED 灯效索引：`iLED_*` 常量一致，极性已由 `board.led_polarity` 表达；
  - UART：只有调试脚 `UART_PIN`（已配置），无独立 TX/RX 板型，波特率无差异；
  - `OLED_POWER_PIN`/`LOGO_CTRL_PIN`/`LED_MODE_CD` 等：单工程出现，无复用价值。
- **黑名单**：
  - `peripherals` 段（UART/SPI/USB/LEDC 启用与参数）**不做**：没有真实取值差异，落地只会变成“配置项存在但没人用”的空壳（与 P1“一次覆盖所有外设”的警告一致）；
  - `compat.py` 三项补丁（`senscan_12bit`/`stack_240`/`usb_tx_flag`）**不做**：属于 KC536→CH04 一次性迁移残留，不是产品维度。

**验收（已完成）**
- CH04/KC536 副本 `check → init → gen --apply → UV4 -b` 均 0 Error / 0 Warning；KC536 `user_config.h/.c` 正文零差异（仅新增 10/6 行标记与保护区行）。
- CH04 改 `ledc_rgb_number: 6 → 10` 后重生成，diff 仅 `LEDC_RGB_NUMBER` 一行；重新编译 0 Error，且 Code/ZI 变化，证明字段被真实使用而非空壳。
- `pytest`、`ruff`、`check --all` 全绿；保护区手写行重生成后保留。

**P4：常规路径打磨（SDIO 3 线板，2026-11-06）**

目标是把“日常使用链路”做扎实，不扩功能面；4 线板（HYC-275QLH）明确延后。

- **CLI**：`init/check/gen/rollback` 均有带示例的 `--help`；错误统一为
  `[ERROR] 现象 + 提示: 可照做的下一步`。退出码固定为 0 成功、1 校验失败、
  2 环境/标记块/manifest 错误、3 写盘失败；4 为历史预留，不再返回。
- **回滚入口**：`rollback --manifest` 同时接受 `manifest.json` 和它所在的
  `.omcfg_bak_*` 目录；manifest/备份缺失、JSON 损坏均给出定位提示，返回 2。
- **配置与板不匹配**：比较 `project.name/customer` 与 SDK 现有
  `iPROJECT_NAME/iCONSUMER_NAME`，只报 warning、不阻断——因为“在副本上换板”是
  合法用法；提示要求确认 `--sdk/--config` 配对。
- **GUI 薄视图**：新增唯一后端方法 `Api.save_pins()`，前端只把脚位 `<input>` 的
  值提交回来；校验、YAML 文本精确替换（保留注释与排版）、事务写入都在 Python。
  实测闭环：打开 → 改 `KEY_R0_PIN` → 保存 → 预览 diff → 应用。禁止把校验或
  生成逻辑搬回 JS。
- **事务目录**：时间戳增加微秒，避免同秒内 `init` 后紧跟 `gen --apply` 时目录
  冲突；manifest 位置与保留策略不变（不自动清理）。
- **验收**：CH04/KC536 副本 `check → init → gen --apply → UV4 -r` 均
  `0 Error / 0 Warning`（CH04 Code=39428，KC536 Code=38580）；`rollback` 后
  4 个文件的 SHA1 与 apply 前一致、新建文件被删除，二次 `gen --dry-run` 输出与
  apply 前逐字节相同；失败路径 8 种均有退出码与提示记录；`pytest`、`ruff`、
  `check --all` 全绿。
- **不做**：4 线板模板、新工程一键生成（复制 SDK + init + 编译）。

**P5：新工程一键生成（2026-11-06）**

- 新增 `omcfg new --sdk <源SDK> --target <新目录> --config <配置> [--name <名>]`，
  一次完成“复制骨架 → 安装配置 → 改工程标识 → `init` → `gen --apply`”。
- **复制排除**（`newproject.py` 的固定清单）：`out/`、`_build/`、`lib_build/`、
  `.git/`、`.vscode/`、`.cache/`、`.omcfg_bak_*/`、`*.dep/d/crf/axf/hex/bin/lst/map/lnp/htm`、
  `*.uvoptx`、`*.uvguix.*`、`*.log`、`JLinkLog.txt`、`JLinkSettings.ini`、
  `compile_commands.json`、`SE71M.BAT`（Keil 生成，含本机绝对路径）。**例外**：SDK 自带的 `userdefined_key_20260724.o`、
  `rf_protocol_20260704.o` 是 `.uvprojx` 直接引用的预编译输入，必须保留，否则链接失败。
- **工程标识改写**：
  - `user_config.h` 的 `iPROJECT_NAME`、`iCONSUMER_NAME`、`iPROJECT_ID_H/L`、
    `iREAL_VERSION_ID` 由既有生成块按配置落盘；
  - `main/mouse_hw.c` 的 `mouse_name` 初值、`main/ex2_app_mouse.c` 的
    `memcpy(mouse_name, ...)` 由 `project.ble_names` 精确改写（不猜锚点）。
  - 源工程与配置的 `project.name` 不同是**正常输入**；命令结束打印每条
    `文件 宏/变量 '旧' -> '新'` 证据。
- **安全边界**：目标已存在或位于源 SDK 内 → 拒绝并给可操作提示，退出码 2，绝不覆盖；
  成功后删除本次生成产生的 `.omcfg_bak_*`，新工程不携带历史事务目录。
- **验收**：KC536 → KC536X 新工程 `UV4 -r` 为 `0 Error / 0 Warning`；新工程
  `user_config.h/.c` 与源工程去掉标记/保护区行后，仅 3 行标识不同，`.c` 正文零差异；
  目录清单无 `out/`、`.dep`、`.omcfg_bak_*`；同一目标重复执行返回 2；CH04/KC536
  副本 `check → init → gen --apply → UV4 -r` 仍为 `0 Error / 0 Warning`。
- **边界**：`gen` 不负责 BLE 广播名；生成后再改 `ble_names` 需重跑 `new` 或手工改。

**P6：GUI 打开未初始化 SDK（2026-11-06）**

- 初始化逻辑从 `cli.py` 抽到 `omcfg/initproject.py`：`missing_markers()` 检测配置与
  `OMCFG`/`USER CODE` 标记完整性，`init_project()` 供 CLI、`new`、GUI 三处共用。
- `Api.load()` 未初始化时返回 `needs_init + missing + configs + suggested`，不再只报
  “先运行 omcfg init”；`Api.initialize()` 选配置后原地完成初始化并重新 `load`。
- 配置候选来自仓库 `configs/*.omcfg`；按 SDK 目录名做**大小写无关的子串匹配**给出
  建议项（如目录含 `KC536` → `configs/KC536.omcfg`），只做预选，必须用户点确认。
- GUI 新增「初始化工程」面板：缺什么列什么，初始化按钮调用后端；失败保留面板与
  提示，不弹栈/不白屏；编辑/保存/预览/应用在初始化前禁用。
- 边界：不从工程现状反向推导 `.omcfg`（由 P7 补齐）；GUI 不提供回滚按钮，
  回滚仍走 CLI manifest。

**P7：配置预选修正 + 新板配置初稿推导（2026-11-06）**

- **问题**：未初始化 SDK 的配置框回退到 `data.config`（即初始化后写入的
  `projects/mouse_demo/project.omcfg`），把它当输入配置，形成鸡生蛋；E606 新板在
  `configs/` 无模板时必然失败，且错误后初始化面板被隐藏，用户无从恢复。
- **预选规则**：`Api.load()` 只预填真实存在的文件 —— 工程内已有 `project.omcfg` 优先，
  其次 `configs/` 目录名匹配项；两者都没有则留空并提示选择/生成。`initialize()` 若收到
  目标路径会明确说明“这是初始化后写入的位置，不是输入配置”，所有初始化失败都保留
  `needs_init` 状态，面板不消失。
- **新板正路径**：新增 `omcfg/derive.py`，只读 `user_config.h/.c`：
  引脚宏 → `pins`；`gpio_config_table` → 模式/上下拉/电平；`iPROJECT_*`/`iCONSUMER_NAME`
   → `project`；`MODE_*`/`LED_*`/`SENSOR_*`/`WHEEL_*`/`UART_PIN` → `board`。GUI 新增
  「从工程现状生成配置」按钮，`Api.initialize_derived()` 推导→校验→临时文件→复用
  `initproject.init_project()`，初稿落到 SDK 内 `project.omcfg`（不写仓库 `configs/`）。
- **验收**：E606 真实副本 GUI 全流程通过；初始化后 `user_config.h/.c` 与现状零差异，
  仅新增 `board_features.h` 并登记 uvprojx；改 `KEY_R0_PIN` 后预览/应用正常，
  `gen --dry-run` 一致，`UV4 -r` 0/0；KC536/CH04 副本 GUI 回归通过；pytest/ruff/
  `check --all` 全绿。
- **边界**：推导是“现状快照”，不判断设计是否合理；`ble_names`（BLE 广播名）不在推导
  范围，仍由 `new` 的 `project.ble_names` 控制；`configs/` 不自动落盘，需要复用时手工
  从 SDK 的 `project.omcfg` 复制。

---

## 5. 砍并清单（逐项去留）

| 模块/文件 | 现状规模 | 处置 | 理由（一句话） |
|---|---|---|---|
| `chip/om6239.json` | 芯片事实 | **保留 + 补字段** | 唯一芯片真相，校验和生成都要它；补 UART/SPI/I2C/PWM 可用脚 |
| `boards/*.json`（7 份） | 25–30 脚/板 | **转为 `configs/*.omcfg` 模板，原目录删除** | JSON 是“板档案”，不是“项目配置”；字段层级与 `.omcfg` 不同，保留只会双源 |
| `validation.py` | 211 行 | **改造为 `omcfg/validate.py`** | 规则语义可复用；改成数据驱动 + JSON Schema |
| `biz_sync.py` | 32 KB | **拆分保留 `key_io`/sleep 契约，其余删** | `key_io` 改写是真痛点；`_sync_rte_ledc`/`_sync_logo_ledc`/17 项体检是 KC536 底包专属，泛化不了 |
| `operations.py` | 170 行 | **平移为 `omcfg/transaction.py`** | 备份/manifest/rollback 是安全网，且已有单测 |
| `board_pack.py` | 18.5 KB，13 策略 | **归档；只抽 3 个文本补丁到 `compat.py`** | donor 拷贝与 13 项策略是“KC536→CH04 一次性迁移”，不是配置器能力；补丁保留是因为真实踩坑（12BIT/栈/usb flag） |
| `port_apply.py` | 16.4 KB | **删除；uvproj 逻辑重写进 `targets/uvprojx.py`** | 其核心是“整包拷金机”，与“配置生成”冲突；且已实测无条件注入 `ledc.c` 造成工程引用缺失文件 |
| `golden_diff.py` | 11.4 KB | **删除** | 与 `git diff` 重复；白名单只认 `key_io.h`，实测把 `key_io.c/user_config.c` 误报为异常 |
| `synth_golden.py` + `synth/BD319` | 13.8 KB + 6 产物 | **删除（可 git 归档）** | 期望脚位写成裸 `26`，SDK 是 `(P26)`，实测 `SAME=0 DIFF=22`，作为基线不可用 |
| `reports/` | 60 KB | **归档/删除** | 历史一次性取证；保留会让人误以为有持续基线 |
| `survey.py` + `survey/` | 18.1 KB + 57 问 | **归档** | 问卷是“没有配置器时的替代品”；有了 `.omcfg` + GUI 表单就没有存在意义 |
| `index.html` | 91.6 KB | **重写为 `web/`（目标 <20 KB HTML+JS）** | 现在它同时是 UI + 第二校验器 + 生成器 + 模板库；必须只留视图 |
| `launch.py` | 50.7 KB | **拆为 `api.py`(薄) + `app.py`(启动)** | 里面混了 golden/synth/apply_pack 等已删能力的入口，路由不清理会继续绑死旧链路 |
| `om_pinmux.py` | 7 个子命令 | **改为 `omcfg/cli.py`：`init/check/gen/rollback`（GUI 由 `app.py` 启动）** | 旧 `port/compare` 删除；rollback 独立成子命令，退出码与 manifest 语义更清晰 |
| `layout_lab.html` | 9.2 KB | **删除** | 布局实验页，无功能价值 |
| `assets/` | 空目录 | **删除** | 无内容 |
| `schemas/board-desc-v2.schema.json` | 0 字节 | **删除，新增 `schemas/omcfg-v1.schema.json`（实文件）** | 0 字节 schema 是“有形式无实质”的证据 |
| `tests/`（8 用例，1 红，1 空文件） | — | **重写 4 组：schema / 规则 / 生成 golden / 事务+uvproj** | 现有测试把“7 块板全合法”当作硬门槛，反而挡住了真实差异（MW650/BD316） |
| `README.md` | 1.3 KB | **重写为 3 步快速上手** | 现在写的是“问卷先行”，与新产品形态相反 |
| `pinmux_state.json` / `launch*.bat` / `.github/workflows/quality.yml` | — | **保留** | 运行状态、启动方式、CI 仍需要，只是接新测试 |

---

## 6. 实施顺序建议（可直接照做）

1. 新建 `omcfg/` 包与 `schemas/omcfg-v1.schema.json`；把 `chip/om6239.json` 读进 `model.py`（此时不删任何旧文件）。
2. 写 `configs/BD319.omcfg`、`configs/CH04.omcfg`（按 §2.4 迁移），跑 `check`，把规则差异（`wired`、同脚冲突）补进 `validate.py`。
3. 写 4 个 Jinja2 模板 + 标记块替换 + `--dry-run` diff；在真实 SDK 副本上 `--apply` 并编译。
4. 通过后，删 `index.html` 的生成/校验/常量段，接 `api.py`；再删金机/移植/问卷三套文件。
5. 最后做 `.uvprojx` 生成与外设参数，并补测试与 CI。

> 删除动作单独 commit，保证“重构可回退到旧链路”。

---

## 7. 风险与反模式（最容易把工具做成“又一个重工具”的做法）

1. **配置里塞派生字段**：把 `features`、唤醒掩码、`LVD_CHECK_INDEX` 再存一遍 → 立刻出现两组真相。**避免**：写入前用 `model` 派生，schema 里显式标注 `derived: true` 的字段禁止出现。
2. **保留金机对照当“保险”**：会得到两套基线（git 与 synth），而 synth 口径已实测错误。**避免**：正确性只由 `git diff + 编译` 证明；需要历史对照时用 git tag。
3. **继续用“锚点猜测”插入代码**：现有 `write_user_config` 的 `fallback_anchor` 会在标记丢失时把代码塞到 `//* 按键配置 */` 附近，静默写错位置。**避免**：标记缺失即失败，错误信息给出“如何初始化标记块”。
4. **GUI 与 CLI 各有实现**：只要 GUI 里还有一段生成逻辑，就一定会和 CLI 漂移。**避免**：`web/` 里禁止出现 `#define`/模板字符串拼接，CI 加一条 grep 检查。
5. **一次覆盖所有外设**：UART/SPI/USB/时钟全上，数据模型会被迫抽象成空壳。**避免**：P1 只做 pins/board/project；每个外设必须在 P3 前有真实编译样例。
6. **补丁无限制增长**：`board_pack` 的 13 项策略就是这么长出来的。**避免**：新补丁必须（a）配置里显式开启，(b) 有单测，(c) 不匹配时 warning 而非静默 noop。
7. **无编译门**：只对比文本、不编译，等于把风险留给下一个工程师。**避免**：每个阶段验收必须包含一次真实 Keil 构建；没有 Keil CLI 也要留人工构建日志。
8. **为“通用”而通用**：多芯片/多 SDK/插件系统。**避免**：单芯片硬编码，路径集中到 `targets/sdk.py` 一处，换 SDK 只改这一处。
9. **删得太早**：重构未在真实工程验证就删旧模块，会同时失去参照。**避免**：旧模块冻结、验证通过、再删除，分 commit。

---

## 8. 一页速查

- **结论**：改进（结构性重构）。保留数据/事务/契约改写/GUI 壳，重写模型-校验-生成-CLI，删除金机/供体/问卷。
- **唯一源**：`<SDK>/projects/mouse_demo/project.omcfg`；模板只是起点。
- **核心命令**：`python -m omcfg new|check|init|gen --dry-run|gen --apply|rollback`。
- **验收三件套**：`check` 0 error、`UV4 -b` 0 error、`git diff` 只动标记块。
- **首阶段只做**：pins + board + project → 3 个源码文件 + Keil 工程条目 → 真实 SDK 副本编译通过。
