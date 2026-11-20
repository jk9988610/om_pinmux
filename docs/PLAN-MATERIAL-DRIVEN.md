# 规划：从「选功能」到「选物料」的引脚配置模型

> 状态：**P0–P3 全部完成**，并追加 **P4 修正：统计去契约化**（P0 需求组显示修复；P1 扫描管线；
> P2 选料 GUI + 契约驱动；P3 物料参数进生成模板 + S205 端到端 Keil 0/0；P4 删除所有统计默认，
> 选料改为纯显式选择，RGB 数量自由填写，极性移到板型步骤由用户按原理图决定）。
> 本文记录调研结论、目标模型、统计方案与落地路线。P4 之后统计仅作内部资料，不进入用户契约。

---

## 1. 为什么必须换模型：来自用户的真实约束

软件工程师拿到的是**硬件已经画好的原理图和 PCB**：引脚归谁用由硬件决定，不由软件选；
同一功能在不同项目里可能换物料，同一物料在不同项目里接法也不同。因此：

1. **原理图不关心功能名，只关心物理连接**：网络名可能叫 `LED_D1`、`MODE_WIRED`、`H_ENCODER_A`，
   工具里按「功能角色」找脚会找不到对应物。
2. **物料决定引脚语义**：
   - 光电传感器 **S203** = 四线 SPI（SCLK/MOSI/MISO/NCS），**两线物料**只有 SDIO，
     DPI 表、中断脚随之不同；
   - 灯带可能是 WS2812 也可能根本不装（不装 LEDC 就没有 LEDC 需求）；
   - NTC/充电管理 **4056H** 决定充电检测脚与充电指示逻辑。
3. **数量与电气属性是物料参数，不是功能参数**：
   - RGB 三色灯**数量**（1 颗 / 3 颗 / 6 颗）；
   - **高电平点亮还是低电平点亮** = 看引脚另一端接地还是接 VCC（S205 是 P04/P05/P06 另一端接 VCC → 低电平点亮）；
   - 拨杆开关**两段（开/关）还是三段**（2.4G 档 / BAT 档 / 蓝牙档，从上到下，2.4G 与蓝牙档电池供电、BAT 档电池不供电）；
   - **蓝牙通道数量**、**是否有 mode 键**（程序里叫 pair 键，实物叫 mode 键）。

结论：**「需求」的真实载体是物料清单（BOM）+ 原理图的物理连接**，不是抽象功能角色。
功能角色可以保留为「物料能力的投影」，但配置入口必须是物料。

---

## 2. 目标模型：选料 → 自动推导角色与约束

```
BOM / 关键物料型号  +  原理图网络名  →  角色集合 + 约束 + 板型选项 + 移植文件
```

### 2.1 分层

- **关键物料（需选型号）**：只对少数决定引脚语义的器件选型号，其余用默认/统计众数：
  - 光电传感器：S203 / S205 / KA8 / MX8650A / S201B …（决定两线/四线、DPI 表、中断脚）
  - 灯带：WS2812 / 3528 ARGB / 不装（决定 LEDC 插件是否启用、DIN/CTRL 脚）
  - 充电管理：4056H / 其它（决定充电检测脚）
  - 模式拨杆：两段 / 三段（决定 2.4G/BLE/BAT 模式脚数量与含义）
  - RGB 灯：数量 + 高低电平极性（决定 RGB 宏展开与 `led_on/off` 极性）
- **普通物料（保留统计默认型号，不逐个选）**：电阻、电容、普通按键、USB 接口等。
  「根据需求选物料」不是本工具职责——拿到原理图时物料已定型，工具只做**识别与确认**。

### 2.2 与现有插件机制的关系

现有 `plugins.json` 契约（勾选 LEDC → 改 board + 腾脚 + 注入文件）是正确方向：
物料选项可以**复用插件契约**，让「灯带型号 = WS2812」等价于「启用 LEDC 插件」。
光电传感器型号则扩展为新的契约族：型号 → 角色子集（两线只保留 SDIO，四线展开 SPI 四脚）。

### 2.3 保留功能视图

需求组、约束栏、脚位图三视图保留，但数据源从 `demand_groups`（功能分组）改为
「物料 → 角色」映射；功能组退化为筛选器。这样 S205 这种「没有 LEDC、没有 pair 键」的项目
在选料后自然不会看到 LEDC / pair 需求。

---

## 3. 调研已做的验证（本轮实地核对）

### 3.1 PcbDoc 能否读到物料型号：**能**

`E:/M_2026/516_BM2017/description/BYKC_BM2017_OM6239_V0.PcbDoc`（7.5 MB）
与 `E:/M_2026/524_LJ-V08/description/BYKC_LJ_V08_OM6238_V0.PcbDoc`（9 MB）按 UTF-16LE
解码后，元件位号与型号（Comment）以明文串保存，可直接提取。实测：

- 516_BM2017：`4056H`、`3528 ARGB`（LED1–LED7）、`6206 3V` / `6206 2V/N`（LDO）、
  `8050`（三极管）、`5819`（肖特基）、`SA8206A`、`OM6239`；
- 524_LJ-V08：`4056H`、`SOP24` / `SOP16` 封装串、`6206 3.3V`、TYPE-C 等。

**结论**：物料型号可以从 PcbDoc 自动抽取，不必手工录入。需做一个稳定的
`pcbdoc_bom_extract.py`（解析 Unicode 串 + 位号/型号配对，去噪），作为统计管线第一步。

### 3.2 S205 试验工程事实核对（全部来自源码 `projects/mouse_demo/periph/user_config.h`）

| 用户陈述 | 源码核对 | 结论 |
|---|---|---|
| 没有 LEDC | `RTE_LEDC 0`（RTE_om6239.h:175） | ✅ |
| 没有 pair 键（= mode 键） | `KEY_PAIR_PIN` 被注释（user_config.h:92） | ✅ |
| 光电是 S205 | `iSENSOR_TYPE_S205 16`、`iSENSOR_TYPE_S203 14` | ✅ |
| P04/P05/P06 另一端接 VCC，低电平点亮 | `led_r_on() = gpio_clear(P04)` 等（142–147） | ✅ 低电平点亮 |
| 滚轮编码器 A=P24 B=P25 | `WHEEL_A_PIN P24` / `WHEEL_B_PIN P25`（111–112） | ✅ |
| 充电指示灯 P00 | 源码里 `USB_5V (P00)`（176），`LED_CHG_PIN` 注释掉（140） | ⚠️ 需向用户确认：P00 在代码里是 USB_5V 检测，充电灯是否复用待查原理图 |

补充事实：`LED_MODE_R/G/B = P04/P05/P06` 且 `LED_R/G/B` 直接别名到 mode 灯（171–173）——
即 S205 的「业务灯」与「模式灯」是同一组物理脚，这是物料驱动模型需要表达的关键耦合。

### 3.3 已有统计资产

`omcfg/data/role_catalog.json` 的 `generated_from` 记载：
「E:/history + E:/M_2026 全量扫描（93 独立项目，66 宏名）」，policy 按项目数分 core/main/extended。
说明统计已有先例；本次目标是**在原有宏名统计之上，新增物料维度**（型号、数量、极性、脚位语义）。

---

## 4. 统计方案（下次执行，以项目编号为时间线）

### 4.1 范围与单位

- 根目录：`E:/M_2026`、`E:/history`；
- 时间线主键：**项目号**（目录名里的数字，如 512 / 516 / 524 / 457 / 489 …），
  同一项目的多个版本（V1/V0、software/description）合并为一条记录，取最新时间戳为该项目「当前状态」；
- 每个项目产出一条 `project record`：编号、时间、物料型号表、宏名→脚位表、关键参数表。

### 4.2 统计维度（按经验判断，落到物料而非功能）

1. **物料型号频次**（按项目号排序，看演进）：
   - 光电传感器型号：S203 / S205 / KA8 / KA5857 / MX8650A / S201B / OM18 …；
   - 灯带型号：WS2812 / 3528 ARGB / 不装；
   - 充电管理：4056H / 其它；LDO：6206 3V / 3.3V；
   - **两线 vs 四线光电**（关键：决定 DPI 表、NCS/MISO/MOSI 是否存在）；
2. **RGB 参数**：数量（1/3/6）、极性（低电平点亮 = 接 VCC / 高电平点亮 = 接地）；
3. **拨杆开关**：两段 / 三段，三段时 2.4G/BAT/BLE 各档脚位、蓝牙通道数；
4. **mode 键**（程序 pair）：存在 / 不存在，脚位；
5. **关键脚位分布**：P00（USB_5V / 充电灯）、P04/P05/P06（RGB 或模式灯）、P24/P25（编码器 A/B）、
   P01/P36（LEDC 相关），统计每个脚在各项目里被哪种物料占用，识别稳定映射与漂移；
6. **共现关系**：某物料型号 ↔ 某组宏名 ↔ 某板型选项（neo cluster），作为推导规则来源。

### 4.3 数据源与优先级

1. `description/*.PcbDoc`：物料型号（位号 + Comment），UTF-16LE 串提取；
2. `description/*.SchDoc` / PDF：网络名、引脚另一端接 VCC/GND（极性判断）—— 需人工抽查校准；
3. `software/trunk/**/periph/user_config.h`：宏名 → 脚位、`led_on/off` 极性、`RTE_LEDC` 等板级开关（最可靠，机器可解析）；
4. `software/**/sensor_type_check.h`：传感器型号枚举，交叉验证 PcbDoc 提取结果。

### 4.4 产出物

- `omcfg/data/material_catalog.json`：物料型号 → 角色/约束/板型选项/文件 的契约库（与 plugins.json 同构，可扩展）；
- `docs/MATERIAL-STATS.md`：按项目号时间线的统计报告（频次表、演进表、共现表）；
- `scripts/scan_projects.py`：可重复运行的扫描器（PcbDoc 提取 + 源码宏解析 + 生成上面两份数据）。

### 4.5 验收用例

- **S205（512）**：选「光电 S205 / 无灯带 / RGB 3 颗低电平 / 三段拨杆 / 无 mode 键」→
  不出现 LEDC、不出现 pair 键，RGB 落在 P04/P05/P06，编码器 A/B = P24/P25，生成头与现有 S205 一致；
- **CH04（457）**：选「灯带 WS2812 / 光电 S203 四线 / NTC 4056H」→ LEDC 插件启用，SPI 四脚出现；
- **BM2017（516）/ LJ-V08（524）**：以 PcbDoc 抽取的物料表（4056H、3528 ARGB 等）反推配置，验证提取→推导闭环。

---

## 5. 落地路线（后续回合）

- **P0（本轮已完成）**：需求组显示修复——14 组覆盖全部 60 角色，去掉 v1 隐藏。
- **P1（已完成）**：`scripts/pcbdoc_bom.py`（PcbDoc 位号↔型号提取，UTF-16LE 记录式解析）、
  `scripts/source_scan.py`（宏/极性/LEDC/传感器/模式脚解析）、`scripts/scan_projects.py`（按项目号
  归一取最新构建，产出三份数据）。实测：114 构建目录 → 30 项目，13 个含 PcbDoc BOM；
  四校准项目全部通过——S205 无 LEDC/pair、RGB P04/P05/P06 低电平、编码器 P24/P25；
  CH04 LEDC 6 RGB + pair P24 + 高电平；BM2017/LJ-V08 物料表（4056H/3528 ARGB/6206）正确。
  回归测试 `tests/test_material_scan.py`（8 项）。产出物：`omcfg/data/material_catalog.json`、
  `omcfg/data/project_scan.json`、`docs/MATERIAL-STATS.md`。
- **P2（已完成）**：`omcfg/data/material_catalog.json` 升级为 v2 契约（categories/options/effects），
  新增 `omcfg/materials.py`（与 plugins.py 同构的选料推导引擎）。新建流程插入第 2 步「选料」：
  光电/灯带/充电选型号，RGB 数量/极性、拨杆段数、蓝牙通道、mode 键用统计默认或按需改。
  选料写入 `project.materials`，契约驱动 board 选项（传感器总线/灯效/极性）、`required_roles`
  （四线 SPI 脚、灯带 DIN、无 mode 键去 KEY_PAIR）与插件开关（WS2812→LEDC）。7 步向导索引
  全量同步；`scripts/check_material_view.js` 断言渲染与索引一致。回归 `tests/test_materials.py`。
- **P3（已完成）**：RGB 数量/极性、拨杆段数、蓝牙通道、mode 键有无从选料写入 board，
  `board_features.h` 输出 `BOARD_RGB_COUNT`/`BOARD_SWITCH_SEGMENTS`/`BOARD_BLE_CHANNELS`/
  `BOARD_MODE_KEY_PRESENT` 数值宏，业务代码不再写死；`validate` 拦截非法段数/通道数；
  无 mode 键时用 biz_sync 幂等补丁给 key_io 的 PAIR 引用加 `#ifdef` 保证可编译。
  **S205 画像端到端实测**：选料（无灯带/无 mode 键/RGB 3 低电平/两线光电）→ 配脚 → 写盘 →
  Keil **0 Error / 0 Warning**，生成头含 `gpio_clear` 低电平点亮、无 LEDC、两线 SDIO。

---

## 6. 本轮已完成（需求组显示修复）

- 根因：`role_catalog.json` 的 `demand_groups` 只定义 4 组、覆盖 9/60 角色，其余 51 个角色
  （含 LED_R/G/B、SENSOR_MOSI、KEY_L、光编码器等）从未进入任何组；且 `colGroups()` 用
  `v1 !== false` 再隐藏一批。
- 修复：`demand_groups` 扩展为 **14 组覆盖全部 60 角色**；`colGroups()` 去掉 v1 过滤；
  `groupMacs()` 支持 role_id 与直接宏名（USB_5V 无 role_id）。
- 验证：`scripts/check_constraint_view.js` 断言 14 组全部渲染、逐组可覆盖 60 角色、网络名可搜索、无推荐导向。

## 7. 本轮已完成（P2 选料 + P3 参数化，路线执行）

- 数据分层：`material_scan.json` 为扫描器原始产物，`material_catalog.json` 为人工校准 v2 契约，
  扫描器不再覆盖契约（此前 pytest 跑扫描器会把 v2 冲回 v1，已修复）。
- 7 步向导：身份 → **选料** → 板型 → 插件 → 配脚 → 校验 → 生成；选料卡由目录数据驱动，
  型号点击即时落盘并联动健康卡/板型/插件。
- 选料引擎 `materials.py`：normalize/apply_effects/apply/status/required_roles/removed_roles，
  幂等；无 mode 键用 biz_sync 补丁保护 key_io 的 PAIR 引用。
- 生成参数化：`model.switch_segments/ble_channels/mode_key_present` + `board_features.h` 数值宏；
  `validate` 拦截非法 2/3 段与 1/2 通道。
- 验证：`tests/test_materials.py` 11 项（含前端脚本包装 + S205 Keil 0/0），
  `node scripts/check_material_view.js` PASS，eslint 0 error。
