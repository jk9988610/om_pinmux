# 内置 SDK 与“命名即建工程”计划

> 状态：一期已落地，二期已落地（2026-11-06）。适用：`omcfg` 当前架构。目标：把
> “从外部 SDK 复制”改成“从工具内置基线长出”，新建工程只输入一个名字，引脚分配成为
> 主要配置动作。本文只定方案；一、二期实施结果见文末“落地记录”。

## 0. 结论摘要

1. **SDK 内置用“仓库内基线目录”落地**：`baseline/sdk/` 放一份清理过、已初始化并
   生成过的 CH04 SDK（207 个文件、5.43 MB），`baseline/project.omcfg` 放该基线的板级配置，
   `baseline/META.json` 记录来源、提交、许可证和文件树摘要。不引入 zip 展开、
   下载器或外部 SDK 路径。理由是体积可接受、Git 可 diff、编译可复现、许可证可控。
2. **新建工程只给名字**：`python -m omcfg new --name <NAME>`。工程名、目录、ID、
   BLE 广播名、默认板参数由工具生成；`--target` 仅用于改落点。`--sdk/--config`
   从 `new` 移除，避免“外部复制”和“内置生成”两套并存。
3. **引脚配置按“脚位→功能”组织**：数据模型以 `chip/om6239.json` 的
   `package_pins` + `mux` 为准，配置仍落在 `.omcfg` 的 `pins` 映射；校验分
   “同脚多功能 / 必需脚缺失 / 复用矩阵不合法 / 模块连带文件缺失”四类。
4. **模块图谱变成校验规则**：把第 1 节的“必改组”落成 `rules`，生成时提示
   “改了这个引脚，还应同步哪些文件”，而不是只改宏。
5. **分三期**：一期内置基线 + 命名即建工程 + 编译通过；二期引脚配置与冲突检测；
   三期其余参数配置与模块连带校验。一期不跨到二期。

## 1. 事实基础：功能域 → 文件 → 典型改动

### 1.1 取证方法

对四个真实工程逐提交读取 `git log --name-status`（不是只看最新快照），按功能域
聚类“同一次提交里一起出现的文件”，再回看差异确认是**逻辑耦合**还是**顺带格式化**。

| 仓库 | 路径 | 提交数 | 取证区间 |
| --- | --- | --- | --- |
| V196 | `E:\M_2026\495_V196\software\trunk\SE71M_0495_V196_V1_20260927` | 24 | 2026-09-27 → 2026-10-24 |
| S205 | `E:\M_2026\512_S205\software\trunk\SE71M_0512_S205_V1_20261017` | 14 | 2026-10-17 → 2026-11-05 |
| BM2017 | `E:\M_2026\516_BM2017\software\trunk\SE71M_0516_BM2017_V1_20261022` | 40 | 2026-10-22 → 2026-11-05 |
| CH04 | `E:\M_2026\M_2026_T\SE71M_0457_CH04_V4_20260829` | 7 | 2026-09-04 → 2026-11-06 |

命名约定：`key_io.*` = `projects/mouse_demo/periph/key_io.*`；
`user_config.*` 同目录；`main.*` = `projects/mouse_demo/main/main.c`；
USB 文件在 `mode_usb/`；2.4G 在 `mode_24g/`。

### 1.2 图谱

“硬”= 同一次提交必须成组改，漏改会功能异常或编译/枚举失败；
“软”= 视需求可选的联动。

| 功能域 | 硬（必须同组） | 软（按需联动） | 证据（commit / 日期 / 说明） |
| --- | --- | --- | --- |
| **按键矩阵 / 拨杆 IO** | `user_config.h`（脚宏、上拉/下拉、唤醒掩码、LED 组宏）↔ `user_config.c`（`gpio_config_table`）↔ `key_io.h`（`KEY_MODE_*` 分组宏）↔ `key_io.c`（扫描/极性/模式判断） | `led*`、`mode_ind*`、`sleep.c`、`startup_om6239.S`、`hal_usb_decs.c` | **BM2017 `dd988b4`**（10-23，按原理图重写引脚表）：`user_config.h/.c` + `key_io.h/.c` + `hal_usb_decs.c` + `startup_om6239.S` 一次改完，修 USB 枚举/按键/热插拔。<br>**V196 `b762013`**（10-14，拨杆极性）：`key_io.c` + `user_config.c` 同时改，极性既在扫描判断也在 GPIO 配置。<br>**V196 `9c17b53`**（10-14，P26/P34 内部上拉）：只改 `user_config.c`，说明电气配置可独立于扫描逻辑。<br>**V196 `d067caf`**（10-14，2.4G 切模式失败）：只改 `key_io.c`，模式切换逻辑在按键层。 |
| **DPI** | `sensor.c/.h`（`sensor_dpi_ini` 默认档/档数）↔ `flash_process.c/.h`（持久化版本、加载/迁移）↔ `rf_data_process.c`（上报/默认档） | `mode_ind.c`、`ledc.c`/`led.c`、`key_io.c`（切档落盘）、`user_config.h`（档位宏） | **S205 `81f5a20`**（11-05，“DPI 默认值和需求”）：`sensor.c/.h` + `flash_process.c/.h` + `rf_data_process.c` 五文件同改，默认值与持久化必须对齐，否则旧 flash 值覆盖新默认。<br>**V196 `e89b0a6`**（10-14，4 档 4 色 4 闪）：`sensor.c` + `mode_ind.c`，档数与指示必须匹配。<br>**V196 `db2eab0`**（10-24，充电灯+DPI）：`sensor.c` + `mode_ind.c` + `lvd.c` + `rf_data_process.c`。<br>**S205 `40b2fe2`**（11-05，电池模式切 DPI 断电保持）：只改 `key_io.c`，切档写盘路径在按键层。<br>**BM2017 `325d5ac`**（11-03，6 档 + 默认 1600）：`sensor.c/.h` + `ledc.c` + BLE 名文件。 |
| **模式切换（24G/BLE/USB）** | `key_io.c`（`scan_mode_swtich`，唯一入口）↔ `user_config.h`（`MODE_*_PIN`、唤醒掩码）↔ `main.c`/`main_24g.c`/`main_usb.c`（进入各模式） | `mouse_hw.c`、`ex2_app_mouse.c`、`sleep.c`、`mode_ind.c`/`ledc.c`、`rf_data_process.c`、`hid_process.c` | **S205 `5517724`**（10-21，灯效状态机重构 + P04/P05/P06 独占 + 5V 边沿）：`key_io.c` + `main.c` + `rf_data_process.c` + `sleep.c` + `led.c` + `mode_ind.c/.h` + `mouse_hw.c` + `ex2_app_mouse.c` + `sensor.c` + `user_config.h`。<br>**BM2017 `6c9b6c3`**（10-23，BLE 按键交互）：`key_io.c` + `mouse.h` + `mouse_hw.c` + `ex2_app_mouse.c` + `mode_ind.h`。<br>**BM2017 `8270f47`**（10-24，切通道回连慢）：只改 `key_io.c`，明确“让 `scan_mode_swtich` 接管 RF 模式位”。<br>**CH04 `212aa96`**（11-06）：`key_io.c` + `main_24g.c` + `sleep.c` + `hid_process.c` + `ledc.c`，证明模式切换即使无 RGB 也要动 2.4G/USB/休眠。 |
| **USB 描述符 / 5V 检测** | `mode_usb/usb_descriptor.h` + `usb_cfg_info.h`（VID/PID/电源）↔ `usb_user_process.c`（报告描述符/端点）↔ `flash_process.c`（设置持久化）↔ `key_io.c` / `hal_usb_decs.c`（5V 检测与重枚举） | `drv_usb.c`、`main_usb.c`、`hid_process.c`、`uvprojx` 源文件组 | **V196 `cfb169f`**（10-13，USB 5V 按键修复）：`drv_usb.c` + `hal_usb_decs.c` + `usb_user_process.c` + `flash_process.c` + `key_io.c` 五文件同改。<br>**V196 `51614ed`**（10-13，标题“修光电传感器”）：仍然只改 `drv_usb.c` + `hal_usb_decs.c` + `usb_user_process.c` + `flash_process.c`，说明 USB 四件套已形成硬耦合。<br>**V196 `9e010e4`**（09-28）：`usb_descriptor.h` + `usb_cfg_info.h` + `usb_user_process.c` + `main_usb.c` + `hid_process.c` + `flash_process.c` 同批。<br>**BM2017 `cc2af3e`**（11-04，取消组合键屏蔽）：`main_usb.c` + `usb_user_process.c` + `mouse_hw.c` + `key_io.h/.c`。 |
| **LED 灯效** | 灯脚宏/极性/别名（`user_config.h`）↔ GPIO 表（`user_config.c`）↔ 驱动初始化（`led.c` 或 `ledc.c`）↔ 休眠断电列表（`sleep.c`） | `mode_ind.c`（模式/DPI 指示）、`key_io.c`（按键触发）、`lvd.c`（低电闪） | **V196 `17c0b59`**（10-13，三档拨杆/BAT ship/对码灯）：`key_io.c` + `led.c` + `mode_ind.c` + `user_config.c` + `sleep.c/.h`。<br>**V196 `8fd609a`**（10-13，简化 LED 宏高有效）：只改 `user_config.h`。<br>**BM2017 `90bfcd3`**（10-28，WS2812 回 P21）：`ledc.c` + `user_config.c`，移动灯脚必须两处同步。<br>**BM2017 `d72cc5a`**（10-27，P05 门控 + 阻断 LEDC 抢占 P05）：`key_io.c` + `ledc.c`，引脚冲突要同时改门控与驱动。<br>**S205 `e680db1`**（10-20，设置 IO）：`led.c/.h` + `lvd.c/.h` + `mode_ind.c/.h` + `user_config.c/.h` + `sleep.c` 等 15 文件。 |
| **传感器安装 / 驱动** | `sensor.c`（初始化、方向、档位表）↔ `user_config.h`（总线/方向宏）↔ `drv_senscan.c`（硬件扫描） | `sensor_type_check.c/.h`、`sensor_table.h`、`uvprojx` | **S205 `4f55854`**（10-22，安装旋转 90°）：`sensor.c` + `user_config.h` 的 `SENSOR_DIR_DEFINE` 同改。<br>**BM2017 `89fa95c`**（11-05，新增 FCT3075）：`sensor.c/.h` + `sensor_type_check.c/.h`，新增源文件还要进 `uvprojx`。<br>**S205 `e680db1`**：`drv_senscan.c` + `sensor.c` + `user_config.*` 同批。 |
| **工程标识 / BLE 名** | `user_config.h`（`iPROJECT_NAME`/`iCONSUMER_NAME`/`iPROJECT_ID_*`/`iREAL_VERSION_ID`）↔ `mouse_hw.c`（`mouse_name`）↔ `ex2_app_mouse.c`（广播名 `memcpy`） | `uvprojx` 工程显示名、`main.h` | **V196 `b39cf13`**（10-15，DPI 手动对码 + 充电灯）：`ex2_app_mouse.c` + `mouse_hw.c` + `key_io.c` + `led.c` + `mode_ind.c`。<br>**BM2017 `325d5ac`**（11-03）：`ex2_app_mouse.c` + `mouse_hw.c` + DPI/LED。<br>**V196 `8bc20e4`**（10-13，蓝牙名改 V196）：身份改写独立提交。 |
| **工程文件 / 构建** | `projects/mouse_demo/keil5/SE71M.uvprojx`（periph 组、include 路径） | `.uvoptx`（本地窗口状态，不纳入配置源）、预编译 `.o` | **CH04 `60a48d2`**、**V196 `9e010e4`** 都是整树同步；新增/删除 `.c` 必须同步 `uvprojx`，否则“源码在、编译不进”。<br>本仓库已固化：`uvprojx.py` 只做 periph 组与 `../periph` include 的外科式更新。 |

### 1.3 从图谱得到的三条硬规则

1. **脚位不是单个宏**：任何脚位移动都要同时满足
   `user_config.h` 宏 + `user_config.c` GPIO 表 + 唤醒/复用宏 + 驱动初始化 +
   `uvprojx` 文件组。BM2017 `dd988b4` 是最完整的反例教材。
2. **默认值不是单个数字**：DPI 默认档必须同时出现在 `sensor.c` 的档位表、
   `flash_process.c` 的持久化版本/加载逻辑、`rf_data_process.c` 的上报默认值。
   S205 `81f5a20` 五文件同改就是证据。
3. **引脚冲突必须跨层检查**：`P05` 既是 LEDC 候选脚又是拨杆门控脚，BM2017
   `d72cc5a` 必须 `key_io.c` 与 `ledc.c` 同改；LEDC 候选脚与滚轮脚重叠
   （`chip/om6239.json` 的 `LEDC_WHEEL_COLLISION`）要由工具在配置期拦住。

## 2. 产品形态与边界

目标操作序列：**命名 → 生成 → 引脚 → 参数 → 生成代码 → 编译**。

- 新建只输入工程名；工具生成目录、工程 ID、BLE 广播名、默认板参数。
- 引脚配置是主界面：以封装脚位为行，按脚选功能；不是让用户翻一堆宏。
- 传感器/灯/USB/模式等参数在引脚之后配置。
- 轻量：不引入数据库、不做原理图 OCR、不做完整 IDE；界面仍是薄视图，
  校验与生成在后端。
- 原理图对照 = “按脚位组织 + 显示复用能力 + 显示当前分配 + 可写网名备注”，
  不是自动识别原理图图片。

## 3. 关键设计

### 3.1 SDK 内置怎么落地

**方案对比**

| 方案 | 体积 | 首次使用 | 更新 | 可审查性 | 结论 |
| --- | --- | --- | --- | --- | --- |
| A. 仓库内基线源码目录 | +5.43 MB / 207 文件 | 直接复制，无展开 | 重新拷入 + 更新 `META.json` | Git 可逐文件 diff | **采用** |
| B. 基线压缩包（zip） | 约 1–2 MB | 首次解压到缓存 | 换包 + 清缓存 | 需解压后才能审查，缓存易脏 | 暂不采用 |
| C. 工具内置模板 + 首次展开 | 同 A 或 B | 多一层“模板→工程” | 模板与展开逻辑双维护 | 中 | 不采用 |
| D. 继续用外部 SDK 路径 | 0 | 依赖用户目录 | 无 | 差（路径漂移） | 废弃 |

取舍：5.43 MB 在仓库里可接受；源码基线能直接参与测试和编译验证；zip 只省 3–4 MB，
却引入缓存失效、首次失败态和不可 diff 三个问题。若仓库有体积红线，再切到 B，
接口不变（`baseline/sdk` 换成展开后的缓存目录）。

**目录设计**

```
baseline/
├── .gitattributes        # * -text：保留 SDK 原始字节，避免换行归一化破坏编译输入
├── META.json             # 来源 SDK、git commit、日期、许可证、文件数、树摘要
├── project.omcfg         # 基线板配置（CH04 引脚/参数；project 段只是占位）
└── sdk/                  # 清理后的 CH04 SDK（无 out/_build/.git/uvguix/日志）
    ├── LICENSE.md        # 原厂 OM-SLA01，随基线保留
    ├── projects/mouse_demo/...
    └── ...
```

`sdk/` 处于**已初始化并生成**的状态（含 `OMCFG` 标记块、`USER CODE` 保护区、
`board_features.h` 与 `uvprojx` 登记），因此新建时不会再重排引脚表，diff 只剩
身份宏与 `project.omcfg`。这也让基线本身成为一个“可编译样板”。

**来源与许可证**：基线取自 `E:\M_2026\M_2026_T\SE71M_0457_CH04_V4_20260829`
（CH04，`212aa96`），许可证为 SDK 自带 `LICENSE.md`（OM-SLA01）。要点：
允许随产品复制源码/二进制并保留版权声明；仅限与 OnMicro MCU 配合使用；
不得按开源许可证再分发。工具仓库若对外分发，必须带 `LICENSE.md` 并在
`META.json` 标注；内部使用无额外义务。

**更新机制（一期最小版）**：
1. 用 `newproject.copy_skeleton` 从新 SDK 生成候选基线（自动剔除构建产物）。
2. 人工审 diff（只应出现期望的 SDK 升级差异）。
3. 更新 `baseline/META.json` 的 `source_sdk/source_commit/date/file_count/size/tree_sha256`。
4. 跑 `pytest` 中的基线完整性测试（文件数、关键文件、树摘要）。
不做自动下载/自动升级，避免“工具偷偷换基线”。

### 3.2 新建流程

命令：`python -m omcfg new --name <NAME> [--target <DIR>]`

| 步骤 | 输入 | 输出 | 失败态 |
| --- | --- | --- | --- |
| 1. 名称校验 | `--name` | 合法工程名 | 空名、含路径分隔符/引号/换行、派生 BLE 名超过 28 字符 → `EXIT_VALIDATION`，提示改名 |
| 2. 目标定位 | `--target` 或默认 `./<NAME>` | 目标绝对路径 | 目标已存在 → 拒绝覆盖；目标位于 `baseline/sdk` 内 → 拒绝 |
| 3. 基线检查 | `baseline/sdk`、`baseline/project.omcfg`、`META.json` | 已校验的基线 | 缺文件/关键目录 → `EXIT_ENVIRONMENT`，提示“内置基线不完整，见 META.json/重新安装工具” |
| 4. 生成身份 | 名称 + 基线配置 | `project.name`、`id`、`ble_names` | ID 冲突（一期用 CRC16，冲突概率低；二期加注册表）→ 仅警告 |
| 5. 复制骨架 | 基线 SDK | 新工程目录 + `projects/mouse_demo/project.omcfg` | 复制中断/权限 → 回滚删除目标目录，报可操作路径 |
| 6. 标识改写 | `ble_names` | `mouse_hw.c`、`ex2_app_mouse.c` 的新广播名 | 找不到 `mouse_name`/`memcpy` 锚点 → 警告（不阻断），列出未改写文件 |
| 7. 初始化 + 生成 | `project.omcfg` | OMCFG 标记块、`board_features.h`、`uvprojx` 更新 | 标记缺失/只读/编码失败 → 删除未完成目录，报原因 |
| 8. 编译（可选） | `uvprojx` | `.axf`/日志 | 工具不自动调用 Keil；输出下一步命令，编译失败由用户看日志 |

身份生成规则（一期）：

- `project.name = NAME`；
- `project.customer` 继承基线（`App`），二期可在新建向导里改；
- `ble_names = ["<NAME> Bt1", "<NAME> Bt2"]`（基线为双广播；单广播板二期可改）；
- `id.low = CRC16(NAME) & 0xFFFF`（避开 0x0000），`id.high` 继承基线（`0x071`），
  `id.version = 1`；
- 目录 = 目标目录本身（不再套一层 `<NAME>/<NAME>`），SDK 根直接位于目标下。

### 3.3 引脚配置的数据模型

**事实源**：

- `chip/om6239.json` 的 `package_pins`：封装脚号 ↔ `Pxx` ↔ 可用 `alt`（PWM/ENCODER/LEDC/UART/SCLK/SDIO…）。
- `chip/om6239.json` 的 `mux`：`LEDC_SEL`、`UART_SEL`、`ENCODER`、`LVD`、`USB` 的合法组合与 `sdk_macro`。
- `configs/*.omcfg` 的 `pins`：角色 → `Pxx` + 可选 `gpio`/`note`。
- 板级现状（`user_config.h`/`user_config.c`）：已有上拉、唤醒、LED 分组，作为“当前分配”的初始值。

**配置形状（不新增第二份数据源）**：

```yaml
pins:
  KEY_R0_PIN: { pin: P32, note: "原理图 SW1" }
  LEDC_PIN:   { pin: P34, note: "灯带 DIN" }
```

`pins` 仍是唯一来源；界面上的“脚位视图”是它的投影：

```
封装脚 1  P32  [按键 R0 ▾]  当前: KEY_R0_PIN   复用: PWM
封装脚 2  P00  [滚轮 A ▾]   当前: WHEEL_A_PIN  复用: PWM/ENCODER
...
```

**可选项推导**：

1. 角色候选集 = 该角色在所有板配置里出现过的脚位（模板经验）+ 芯片 `alt` 允许的脚。
2. 对每个脚，过滤掉已被其他必选角色占用的脚（LED 别名对除外）。
3. 复用矩阵校验：`LEDC_PIN` 必须落在 `LEDC_SEL` 的 4 个候选之一；`ENCODER` 的
   A/B 必须成对落在同一 `sdk_macro` 组合；`UART_PIN` 必须落在 `UART_SEL` 组合；
   `USB_DN/DP` 固定 P02/P03。
4. `P14~P17`、`P35`、`P37` 等不在封装/BOOT 脚不允许分配。

### 3.4 冲突检测

四类，全部在 `check`/GUI 预览期拦截，不等到编译：

| 类型 | 判定 | 例子 | 级别 |
| --- | --- | --- | --- |
| 同脚多功能 | 两个角色映射到同一 `Pxx` | `KEY_PAIR_PIN=P24` 且 `WHEEL_A_PIN=P24` | error（LED 别名对白名单除外） |
| 必需脚缺失 | 板特性要求某角色但 `pins` 缺键 | `board.logo=ledc` 但无 `LEDC_PIN` | error |
| 复用矩阵不合法 | 组合不在 `chip/om6239.json` 的 `mux` | `LEDC_PIN=P34`（不在 LEDC_SEL 候选） | error |
| 电气/启动约束 | 固定脚或保留脚被占用 | `USB_DP` 不是 P03；`P37` 被当普通 IO | error |
| 模块连带缺失 | 改脚后应同步的文件不存在/未登记 | 有 `LEDC_PIN` 但 `uvprojx` 无 `ledc.c` | warning（一期）→ error（三期） |

### 3.5 原理图对照怎么体现

- **按引脚号组织**：主视图按 QFN32 脚号 1–32 排列（左/下/右/上四边），每行显示
  `脚号 / Pxx / 复用能力 / 当前角色 / 原理图网名备注`。
- **按脚选功能**：点某个脚，下拉只显示“该脚在 `mux` 中合法且未被占用”的角色；
  选完立即在 `.omcfg` 的 `pins` 里写 `{pin, note}`。
- **当前分配高亮**：已分配脚显示角色名；冲突脚红色；必需但未分配的角色在右侧
  “待分配”列表里常驻。
- **网名备注**：用户可把原理图网络名写进 `note`，生成时只作注释，不参与逻辑；
  不做图片识别。
- **导入现状**：首次打开已有工程时，从 `user_config.h/.c` 推导当前分配（复用
  `derive.py` 的思路），作为起点而不是空白表。

### 3.6 模块图谱如何驱动校验与提示

把 1.2 的“硬组”落成声明式规则。二期实际实现为 `omcfg/rules.py` 的常量清单
（10 条，见附录 C），**没有**引入 YAML 规则引擎：规则数量少且每条都要写解析代码，
Python 常量更易读、易测、易被 `check --rules` 直接打印；未来若要扩到几十条再考虑
外置文件。

```yaml
- id: PIN_MOVE_REQUIRES_BOARD_TABLE
  when: pins.*.pin changed
  require:
    - projects/mouse_demo/periph/user_config.h   # 宏/唤醒
    - projects/mouse_demo/periph/user_config.c   # gpio_config_table
    - projects/mouse_demo/periph/key_io.h        # KEY_MODE_*（若角色是按键/模式）
  message: "脚位改动需同步宏、GPIO 表与 key_io 分组宏（证据 BM2017 dd988b4）"
- id: DPI_DEFAULT_REQUIRES_FLASH_VERSION
  when: board.sensor.dpi_default or dpi_levels changed
  require_changes:
    - projects/mouse_demo/periph/sensor.c
    - projects/mouse_demo/flash/flash_process.c
    - mode_24g/rf_data_process.c
  message: "DPI 默认值需同步 sensor/flash/2.4G（证据 S205 81f5a20）"
- id: LED_PIN_REQUIRES_SLEEP_LIST
  when: pins.LED*.pin changed
  require_changes:
    - projects/mouse_demo/periph/sleep.c
```

执行方式：

- `gen --dry-run` 时比较“本次配置相对上次生成的差异”，命中规则就打印
  “连带文件建议”，并在 diff 里标出这些文件当前是否本来就有改动。
- `check` 只做静态一致性（如 `uvprojx` 是否登记 `ledc.c`）。
- GUI 在“应用”前展示同样的提示，不阻断可选联动；硬规则阻断。

### 3.7 与现有 `new` / `init` / `gen` 的关系

| 命令 | 去留 | 新职责 |
| --- | --- | --- |
| `new` | **保留并替换语义** | 唯一新建入口：从 `baseline/` 生成；只收 `--name`（`--target` 可选）。移除 `--sdk/--config/--name` 旧组合，避免两套。 |
| `init` | **保留** | 仅用于“已有外部 SDK 首次接入”：插标记块、落 `project.omcfg`。不再是新建的必经步骤（`new` 内部调用同一实现）。 |
| `gen` | **保留** | 从工程内唯一 `project.omcfg` 生成；`--sdk` 仍指目标工程根目录。 |
| `check` | **保留** | 增加引脚冲突与复用矩阵规则。 |
| `rollback` | **保留** | 不变。 |

不会出现两套并存：`new` 不再接受外部 SDK 作为源；文档与 GUI 都只描述
“新建=内置基线”。`init` 的存在是“接入已有工程”，不是第二条新建路径。

## 4. 分三期路线

### 一期：内置基线 + 命名即建工程（本次实施）

**范围**

- 新增 `baseline/`（SDK 基线、板配置、`META.json`、`.gitattributes`）。
- 新增 `omcfg/baseline.py`：基线定位、身份生成、完整性校验。
- 改造 `new`：`--name` 必填，`--target` 可选；移除 `--sdk/--config`。
- 更新 README、ROADMAP、测试。

**验收**

1. `python -m omcfg new --name OM_TEST_01 --target <workspace>\OM_TEST_01` 成功；
2. 目录清单：SDK 根直接位于目标下，无 `out/_build/.git/uvguix/日志`；
3. 标识证据：`user_config.h` 的 `iPROJECT_NAME/iPROJECT_ID_*/iREAL_VERSION_ID`、
   `mouse_hw.c` 的 `mouse_name`、`ex2_app_mouse.c` 的两个广播名全部变为新名；
4. 与基线 diff 只有“标识 + 初始化标记块 + `project.omcfg` + `board_features.h` +
   `uvprojx` 登记”差异；
5. `UV4 -b` 编译 `0 Error(s), 0 Warning(s)`；
6. `pytest`、`ruff`、`check --all` 全绿。

**非目标**：不做引脚编辑界面、不做参数配置、不做模块连带规则执行。

### 二期：引脚配置与冲突检测（已实施，见附录 C）

**范围**

- `.omcfg` 引脚视图的数据模型与候选推导（`chip/om6239.json` + 板现状）。
- GUI 按脚位表格、按脚选功能、冲突高亮、必需脚待分配。
- `check` 增加同脚/缺失/复用矩阵/保留脚规则。
- 改脚后重新生成，自动同步 `user_config.h/.c`、唤醒掩码、`key_io.h` 分组宏。

**验收**

1. 三个冲突样例（同脚、缺必需脚、LEDC 非法脚）在 `check` 与 GUI 都被拦住，且提示指向规则；
2. 改一个按键脚 → 预览 diff 同时出现 `user_config.h/.c`，`key_io.h` 在需要时更新；
3. 生成后 `UV4 -b` 0 Error，`pytest/ruff/check` 全绿；
4. 原理图对照页按脚号 1–32 展示复用与当前分配。

### 三期：其余参数 + 模块连带校验

**范围**

- 传感器（总线/方向/档位/默认值）、灯（类型/极性/数量）、USB（VID/PID/电源/报告）、
  模式（双/三档、唤醒）配置面板。
- `rules/modules.yaml` 与“改一处提示连带文件”的 diff 校验。
- 新板首次接入：从现有工程推导初稿配置（复用 `derive.py`），在 GUI 里确认后落盘。

**验收**

1. 改 DPI 默认值 → 提示并检查 `sensor.c`/`flash_process.c`/`rf_data_process.c` 三处；
2. 改灯脚 → 提示 `sleep.c` 断电列表与 `uvprojx` 驱动文件；
3. 改 USB VID/PID → 提示 `usb_descriptor.h`/`usb_cfg_info.h`/`flash_process.c` 同步；
4. 上述改动后编译 0 Error，回归全绿。

## 5. 风险与待拍板

> 2026-11-06 已拍板：①接受仓库内置源码基线；②基线更新暂人工（不自动下载/升级）；
> ③不加第二套基线；④项目号允许 `--id` 手工指定，并做碰撞检查（重复拒绝）；
> ⑤许可证在内部使用前提下随基线保留 `LICENSE.md`。

1. **仓库体积**：一期基线 +5.43 MB（207 文件）。是否接受？若不接受，切 zip 方案
   （约 1–2 MB），接口保持 `baseline/sdk`，但首次要展开、缓存要校验。
2. **基线更新方式**：当前“人工拷入 + 更新 META”是否可接受？是否需要
   `omcfg baseline update --from <SDK>`（自动剔除产物 + 生成 META）？
3. **基线选型**：一期用 CH04（LEDC、双模式、矩阵列）。是否需要一份“无灯/单模式”
   的最小基线作为第二套模板？这会重新引入多基线选择，需在二期决定。
4. **ID 生成**：CRC16 派生在批量建工程时可能碰撞；是否需要本地注册表
   （`baseline/id_registry.json`）或人工指定？
5. **许可证**：基线随工具仓库分发是否符合公司对外分发策略？若工具仅内部使用，
   按 OM-SLA01 保留 `LICENSE.md` 即可；若对外，需要法务确认。

## 附录 A 关键提交证据（可直接复核）

```text
V196  b762013 2026-10-14 拨杆极性：key_io.c, user_config.c
V196  9c17b53 2026-10-14 P26/P34 上拉：user_config.c
V196  d067caf 2026-10-14 2.4G 模式切换：key_io.c
V196  cfb169f 2026-10-13 USB 5V：drv_usb.c, hal_usb_decs.c, usb_user_process.c, flash_process.c, key_io.c
V196  51614ed 2026-10-13 USB 四件套 + flash_process.c
V196  17c0b59 2026-10-13 拨杆三档/对码灯：key_io.c, led.c, mode_ind.c, user_config.c, sleep.c
V196  e89b0a6 2026-10-14 DPI 档位：sensor.c, mode_ind.c
V196  db2eab0 2026-10-24 充电灯 + DPI：sensor.c, mode_ind.c, lvd.c, rf_data_process.c
S205  81f5a20 2026-11-05 DPI 默认值：sensor.c/.h, flash_process.c/.h, rf_data_process.c
S205  40b2fe2 2026-11-05 DPI 断电保持：key_io.c
S205  4f55854 2026-10-22 传感器旋转：sensor.c, user_config.h
S205  5517724 2026-10-21 模式/灯效：key_io.c, main.c, rf_data_process.c, sleep.c, led.c, mode_ind.*, mouse_hw.c, ex2_app_mouse.c, sensor.c, user_config.h
S205  e680db1 2026-10-20 设置 IO：key_io.*, led.*, lvd.*, mode_ind.*, sensor.c, user_config.*, startup_om6239.S, drv_senscan.c
BM2017 dd988b4 2026-10-23 重写引脚表：user_config.*, key_io.*, hal_usb_decs.c, startup_om6239.S
BM2017 325d5ac 2026-11-03 DPI 6 档 + BLE 名：sensor.*, ledc.c, ex2_app_mouse.c, mouse_hw.c
BM2017 90bfcd3 2026-10-28 LEDC 回 P21：ledc.c, user_config.c
BM2017 d72cc5a 2026-10-27 P05 门控：key_io.c, ledc.c
BM2017 89fa95c 2026-11-05 新传感器：sensor.*, sensor_type_check.*
BM2017 6c9b6c3 2026-10-23 BLE 按键交互：key_io.c, mouse.h, mouse_hw.c, ex2_app_mouse.c, mode_ind.h
BM2017 8270f47 2026-10-24 切通道回连：key_io.c（scan_mode_swtich）
BM2017 cc2af3e 2026-11-04 组合键：main_usb.c, usb_user_process.c, mouse_hw.c, key_io.*
CH04  212aa96 2026-11-06 模式/USB/灯：key_io.c, main_24g.c, sleep.c, hid_process.c, ledc.c
```

## 附录 B 一期实际落地记录（2026-11-06）

**基线**：`baseline/sdk` 207 文件 / 5,689,945 B，`tree_sha256=eb152183…`，
来源 CH04 `212aa96`，已初始化并生成（`OMCFG` 标记块、`board_features.h`、`uvprojx` 登记）。

**生成命令**

```powershell
python -m omcfg new --name OM_TEST_01 --target C:\...\temp_20261106_01\OM_TEST_01
```

输出：项目号 `0x15B0 / 0x071 / v1`，BLE `OM_TEST_01 Bt1 / OM_TEST_01 Bt2`，
复制 207 个文件，无 `.omcfg_bak_*` 残留。

**与基线 diff（源码范围，排除 `out/_build`）**

| 类型 | 文件 | 差异 |
| --- | --- | --- |
| 新增 | `projects/mouse_demo/project.omcfg` | 新工程配置（名称/ID/BLE/基线引脚） |
| 修改 | `periph/user_config.h` | 3 行：`iPROJECT_ID_L`、`iREAL_VERSION_ID`、`iPROJECT_NAME` |
| 修改 | `main/mouse_hw.c` | 1 行：`mouse_name` |
| 修改 | `main/ex2_app_mouse.c` | 2 行：两个广播名 `memcpy` |
| 修改 | `periph/board_features.h` | 1 行：`board:` 注释跟随工程名 |

没有引脚、功能宏、`uvprojx` 或其它源码差异。

**编译**

```text
UV4 -b ...\OM_TEST_01\projects\mouse_demo\keil5\SE71M.uvprojx
exit=0
Program Size: Code=39440 RO-data=2120 RW-data=208 ZI-data=2292
".\out\SE71M.axf" - 0 Error(s), 0 Warning(s).
```

**回归**：`pytest` 77 passed；`ruff` clean；`check --all configs` 两块板 0 error 0 warning。

## 附录 C 二期实际落地记录（2026-11-06）

**数据模型**

- `chip/om6239.json` 新增 `reserved_pins`（`P14–P17`、`P35`、`P37`）与
  `internal_flash`（`FLASH_CS/SCLK/MOSI/MISO` 固定脚）；`package_pins`/`mux` 沿用。
- 新增 `omcfg/pinmap.py`：`rows()`（32 封装脚 + 片内脚 + 未分配角色）、
  `assignable_roles()`、`allowed_pins()`、`constraint_pins()`、`role_pin_problem()`。
- `.omcfg` 的 `pins` 仍是唯一配置源；GUI/API 的脚位表是投影，不存第二份数据。
- `omcfg/api.py` 用 `save_pinmap()` 取代旧的 `save_pins()`：全量或部分映射、
  `""` 解除、未知角色拒绝、`WHEEL_A/B` 脚对自动回写 `board.wheel`，一次校验一次事务。

**四类冲突（`validate.py` + `pinmap.role_pin_problem`）**

| 类型 | 输出 | 退出码 |
| --- | --- | --- |
| 同脚多功能 | `[ERROR] pins: P32 被重复分配: KEY_R0_PIN, KEY_R1_PIN` | 1 |
| 缺必需脚 | `[ERROR] pins.MODE_BLE_PIN: 当前板型需要 MODE_BLE_PIN，但配置缺少` | 1 |
| 复用矩阵非法 | `[ERROR] board.wheel: WHEEL_A/B 必须是 ENCODER 四对之一（当前 P00+P06）` | 1 |
| 保留脚被占用 | `[ERROR] pins.SENSOR_SCLK_PIN.pin: P14 是片内 Flash 保留脚，只允许 FLASH_MISO_PIN` | 1 |

固定脚同样拦：`P02/P03` 只能接 USB 差分、`LVD ∈ P23/P33`、
`LEDC_CTRL ∈ P01/P05/P21/P33`。

**连带规则（`omcfg/rules.py`，`check --rules` 可打印）**

`pins.macro`、`pins.gpio_table`、`pins.wake`、`key_io.refs`、`led.polarity`、
`led.sleep` 为 error；`led.driver`、`dpi.table`、`dpi.persist`、`dpi.default`
为 warning。`check --sdk <SDK>` 用 strict 模式把 error 计入退出码，GUI 保存与
`gen` 用非 strict 只提示。

**真实验收（CH04 基线新工程 `OM_PIN_02`，项目号 `0x8525 / 0x071 / v1`）**

1. 改脚前 `UV4 -b`：0 Error/0 Warning（Code=39436 RO=2120 RW=208 ZI=2292）。
2. `save_pinmap({"KEY_R0_PIN": "P10"})` → `ok=true, changed=1`，伴随 `pins.macro` warning。
3. `gen --apply` 后源码只有 `user_config.h` 的 `#define KEY_R0_PIN (P10)` 一行变化；
   与改脚前快照 diff 仅 `user_config.h`、`project.omcfg`（P32→P10）与 `SE71M.bin`。
4. 改脚后 `UV4 -b`：0 Error/0 Warning（Code=39436）。
5. 反向验证：手删 `PIN_WAKE_UP_MASK` 里的 `KEY_PAIR_PIN` → `check --sdk` 报
   `pins.wake`，退出 1；配置改 P06 但未生成 → `pins.macro` 报“配置为 P06，
   user_config.h 为 P10”，退出 1。
6. 幂等：全量映射连续保存两次 `changed: 0 0`；`gen --dry-run` 无变化。
7. `new --id 0x0457`（已占用）→ 拒绝、列出占用者、建议 `--id 0x0001`，退出 1；
   理由：项目号是烧录/配对身份，冲突只能拒绝，不能警告后继续。
8. 回归：`pytest` 109 passed、`ruff` clean、`check --all configs` 退出 0
   （KC536 仅 `KEY_C0_PIN` warning）、基线 `check --sdk` strict 0 error。

**遗留**

- `ledc.c` 的 `drv_pmu_ledc_sel` 仍是硬编码，移动 `LEDC_CTRL_PIN` 只提示不生成，
  需三期加标记块。
- DPI 只做三处一致性提示（`sensor.c`/`flash_process.c`/`sensor.h`），不生成 `sensor.c`。
- 片外 Flash/`P35`/`P37` 的硬件用途未展开；`new` 后改 `ble_names` 仍需重跑或手工改。
