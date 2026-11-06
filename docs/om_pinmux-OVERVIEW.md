# om_pinmux 项目概览（OM6239 PinMux / 换板助手）

> **已废弃（2026-11-06）**：本文描述的是旧链路（`launch.py`、`index.html`、`survey/`、
> 金机对照等），相关模块已在 P1 中删除。现行方案与验收请以
> [ROADMAP-LIGHTWEIGHT-CUBEMX.md](ROADMAP-LIGHTWEIGHT-CUBEMX.md) 为准；
> 本文仅作历史参考，不再维护。

- 代码位置：`E:\tools\om_pinmux`
- 版本：`0.1.0`（[pyproject.toml](pyproject.toml)）
- 本文档基于 2026-11-06 的源码阅读与实机运行结果；只描述现状，不提出未经验证的能力。
- 阅读范围：全部 Python 模块、`index.html`、`boards/`、`chip/`、`survey/`、`synth/BD319`、`reports/`、`tests/`。

---

## 1. 项目定位与目标用户

`om_pinmux` 是一个**单芯片（OM6239，QFN32 / 26 个可用 GPIO）的鼠标板脚位与板级特征写入工具**。README 第 1–3 行把它定义为“硬件脚位 / 板级特征写入工具，业务协议（RF/HID 映射）不在范围内”。

它解决的是换板 bring-up 中最容易反复出错的一段流程：

1. 按原理图把功能（按键矩阵、滚轮、模式脚、传感器、LED/LOGO、USB、电源检测）落到具体 `Pxx`；
2. 检查引脚冲突、复用选择、板型一致性；
3. 生成并写回 SDK 工程里的 `user_config.h` / `user_config.c` / `board_features.h` / sleep 模板；
4. 同步 `key_io` 等业务契约的 `#ifdef` 分支；
5. 把新板与“金机（golden）SDK”做文件级对照，并做换板体检；
6. 写入前自动备份，可按 manifest 回滚。

目标用户是**负责接新板/换板、要改 `projects/mouse_demo/periph` 的固件工程师**，不是终端用户，也不是通用配置工具。当前只支持 OM6239 一颗芯片（`chip/om6239.json` 顶部注释：仅服务 OM6239）。

---

## 2. 目录与入口

```
E:\tools\om_pinmux
├─ om_pinmux.py            CLI 统一入口（7 个子命令）
├─ launch.py               pywebview 桌面壳 + 后端 API（50.7 KB）
├─ index.html              前端单页（91.6 KB，脚位图/角色列表/参数表单/生成）
├─ layout_lab.html         布局实验页（9.2 KB，独立小工具）
├─ biz_sync.py             业务契约扫描与改写（key_io / sleep / RTE）
├─ board_pack.py           板级包策略（补丁/供体拷贝/uvproj 条目）
├─ port_apply.py           按金机做换板移植（拷贝→biz_sync→uvproj→体检）
├─ golden_diff.py          金机关注文件清单 / 目录对比 / 全文 diff 导出
├─ synth_golden.py         “宏观金机”归档（期望脚位、features、checklist）
├─ survey.py               开板调查表：blank / check / export
├─ validation.py           板描述静态校验
├─ operations.py           文件事务（备份 + manifest + rollback）
├─ boards/                 7 份板描述（A02、BD316、BD319、CH04、HTW17、KC536、MW650）
├─ chip/om6239.json        芯片封装脚/复用表/经验教训
├─ schemas/board-desc-v2.schema.json   （0 字节，见 §6.3）
├─ survey/                 QUESTIONNAIRE.md、questions.json、answers_blank/demo.json、multi_board_matrix.md
├─ synth/BD319/            归档产物：board_desc.json、board_features.h、expected_user_config.h、
│                          policy.json、checklist_expect.json、MANIFEST.md
├─ reports/                历史写入测试报告（bd319_write_test_result.json，19.9 KB）
├─ tests/                  test_validation.py、test_uvproj.py、test_operations.py、
│                          test_wheel_soft_gpio.py（0 字节）
├─ assets/                 （空目录）
└─ launch.bat / launch.ps1 / launch_maximize.bat / 打开引脚工具.bat
```

两个入口：

| 入口 | 代码位置 | 说明 |
|---|---|---|
| 桌面 GUI（主力） | [launch.py](launch.py#L387) `class WindowApi`，后端方法 L600–L1130；前端 [index.html](index.html) | `launch.bat` / `打开引脚工具.bat` 启动；窗口位置、已绑定工程记在 `pinmux_state.json` |
| CLI | [om_pinmux.py](om_pinmux.py#L44) `main()` | 7 个子命令：`validate / synth / apply / port / compare / rollback / survey`（L48–L88） |

`om_pinmux.py` 定义了统一退出码（L18–22）：`0` 成功、`1` 校验失败、`2` 环境/参数错误、`3` 写入失败、`4` 已回滚。实际行为见 §6.3 第 6 条。

---

## 3. 功能清单（逐项：做什么 / 代码在哪）

### F1 板描述静态校验
做什么：对 `boards/*.json` 做结构与板型安全规则检查，输出 `ok/errors/warnings`。
代码：[validation.py](validation.py#L74) `validate_board()`；CLI 在 [om_pinmux.py](om_pinmux.py#L108) `validate`。
规则（均在 L79–L171）：
- `schema` 必须为 `om6239-board-desc/v2`，`chip` 必须为 `OM6239`；
- `meta` 必填 `projName/modePins/logoType/ledPolarity`，枚举值受控；
- 每个 `pins.*` 必须是 `Pxx`，且必须落在芯片封装可用 GPIO 内（`chip/om6239.json` 的 `package_pins`，内部/非封装脚如 P14 除外）；
- 独占功能同脚重复分配报错（`LED_*` 例外，允许 RGB 与 MODE 复用同通道）；
- `features.BOARD_LOGO_*`、`BOARD_MODE_DUAL/SINGLE` 必须与 `meta` 一致；
- 双模式板必须有 `MODE_24G_PIN + MODE_BLE_PIN`，且不可再出现 `MODE_BLE_24G_PIN`；
- USB 脚必须等于芯片固定脚；
- 滚轮 A/B 必须是芯片支持的 ENCODER 对，且 `derived.WHEEL_IO_SELECT == meta.wheelMux`；
- LEDC 板：SEL 脚不得与滚轮重叠；RGB 板出现 LEDC 脚仅告警；
- `derived.LVD_CHECK_INDEX` 必须等于 `POF_LVD_PIN_{LVD_PIN}`。

### F2 GUI 引脚编辑与实时校验
做什么：左侧按“功能角色”选脚，中间画芯片封装图，右侧改项目参数和每个脚的 GPIO 模式，底部实时输出校验/复用推导/生成结果。
代码：[index.html](index.html) `runValidation()` L1531、`generateDiff()` L1469、`conflicts()`、`deriveMux()`；芯片常量 `CHIP` L608、模板 `PRESETS` L714（内置 BD319/CH04/KC536/blank）、从 `.h` 导入解析 L1253。
注意：这是一套**独立的 JS 校验实现**，与 `validation.py` 不是同一份代码（见 §6.3 第 1 条）。

### F3 代码生成（4 类产物）
做什么与代码（全部在前端）：
| 产物 | 函数 | 内容 |
|---|---|---|
| `user_config.h` 脚位块 | [generateH()](index.html#L1307) | `#define X (Pxx)` 脚位宏、`PIN_WAKE_UP_MASK`、`KEY_PIN_WAKE_UP_EN/DIS`、`WHEEL_IO_SELECT`、`SENSOR_DIR_DEFINE`、LED 开关宏、`LED_MODE_*` 映射 |
| `gpio_config_table[]` | [generateCTable()](index.html#L1451) | 每个脚的 `USER_GPIO_MODE_*` / 上下拉 / 初始电平 |
| `board_features.h` | [generateFeaturesH()](index.html#L1699) | `BOARD_HAS_*`、`BOARD_MODE_*`、`BOARD_LOGO_*`、LED 极性等 |
| sleep 模板 | [generateSleepTemplate()](index.html#L1740) | `periph_gpio_sleep_set.pinmux.c` 内容 |
| 汇总/下载 | [generateCode()](index.html#L1798) | 组装以上内容 |

### F4 写回 SDK 工程（带备份 + 回滚）
做什么：把生成块写进目标 `periph/user_config.h/.c`，可选写 `board_features.h` 与 sleep 文件，改项目 ID 宏，再把 `key_io` 契约同步进去，最后生成事务 manifest。
代码：[launch.py](launch.py#L813) `write_user_config()`：
- 用标记块 `BEGIN_H/END_H`、`BEGIN_C/END_C` 替换，缺失时按 `//* 按键配置 */`、`gpio_config_table` 锚点插入（L862–L883）；
- `_dedupe_pin_section` / `_dedupe_gpio_table` 去重（L868、L883）；
- `patch_project_id()` 只改原文件宏，不覆盖（L860–L869）；
- [operations.py](operations.py#L55) `FileTransaction`：逐文件备份、记录 `before_sha1`、写 `manifest.json`（L115–L127）；
- 回滚：[operations.py](operations.py#L130) `rollback_manifest()` + CLI `rollback --manifest`。

### F5 业务契约同步（本项目最“值钱”的部分）
做什么：按板型把 `key_io.h/c` 与 sleep 代码里的单/双模式脚、PAIR/DPI 分支改成与 `board_features` 一致。
代码：[biz_sync.py](biz_sync.py#L808) `sync_board_contracts()`；具体改写 L436 `_patch_key_io_h`、L512 `_patch_key_io_c`、L654 `_patch_sleep_c`、L709 `_sync_rte_ledc`、L758 `_sync_logo_ledc`。
实测（临时 SDK 副本）：返回 `actions` 6 条，含 key_io.h 三处、key_io.c 两处、user_config.c 一处。

### F6 板级包策略（补丁 + 供体拷贝）
做什么：按板型选择 13 项策略中的若干项，把 KC536/CH04 底包补成目标板可用的形态。
代码：[board_pack.py](board_pack.py#L31) `POLICY_DEFS`（13 项，L31 起）；`apply_board_pack()` L308；`_patch_file()` L241：
- `senscan_12bit`：`SENSCAN_DATA_FORMAT_8BIT → 12BIT`；
- `rf_callback`：`extern void rf_respone_callback(uint8_t *RxPayload); → ();`；
- `stack_240`：`__STACK_SIZE → 0x240`；
- `usb_tx_flag`：把发送 flag 清零从函数末尾改到入口（带两种旧形态识别）；
- 其余为 donor copy（`sensor_type_check`、`rgb_logo_pack`、`ledc_pack`、USB 字符串、startup PID、FCC 灯）。
RGB 板与 LEDC 板默认都开 8 项，差别只在 `rgb_logo_pack` / `ledc_pack` 互换（`default_policy()` L168；实测 `apply --board BD319 --dry-run` 输出“8 项策略将应用”）。每项策略的默认开关和“为什么”写在 policy 标题里（例如“勿用供体 8BIT 覆盖，曾导致开机卡死”）。

### F7 无人换板移植 `port_apply`
做什么：以一台金机 SDK 为基准，对目标 SDK 做受控拷贝 → 同步业务契约 → 补 uvproj → 体检 → 出报告。
代码：[port_apply.py](port_apply.py#L341) `run()`；关注文件清单在 [golden_diff.py](golden_diff.py#L18) `PORT_FOCUS_RELS`（user_config、key_io、RTE、led、main、flash、sensor、24g/usb、drv_*、栈 sct、`SE71M.uvprojx` 等）；拷贝计划 `plan_copies()` L117（`overwrite/create/skip_missing_src/same`）；uvproj 补条目 `ensure_uvproj_ledc()` L204；报告 `format_report()` L273。

### F8 换板体检（检查清单）
做什么：按板型 + 目标工程现状动态生成 16–17 项检查，覆盖 LEDC 文件/轮询函数/RTE/uvproj/SEL 与滚轮冲突/矩阵 KEY_C0/`mouse_name` 一致性等。
代码：[biz_sync.py](biz_sync.py#L200) `scan_port_checklist()`。GUI 入口 `WindowApi.scan_port_checklist` L656。
实测（对 `SE71M_0486_BD319_v1_20260915` 目录）：`error=8 warn=6 total=16`，8 个 error 全部来自“该目录其实带 ledc.c/ledc_mode.c 等 LEDC 文件，而 BD319 是 RGB 板”——说明体检逻辑能抓住“底包与板型不符”。

### F9 宏观金机归档与对照
做什么：为一块板生成“期望脚位宏 / 期望 features / 期望 checklist”，并可与目标 `user_config.h` 做宏集合对照。
代码：[synth_golden.py](synth_golden.py#L195) `synth_board()` 输出 6 个文件；`generate_expected_user_config_h()` L73；`build_checklist_expect()` L130；`inventory_synth_vs_target()` L265。
实测 `synth --board BD319 --out <temp>` 产出：`board_desc.json`、`board_features.h`、`expected_user_config.h`、`policy.json`、`checklist_expect.json`、`MANIFEST.md`。

### F10 开板调查表（非业务）
做什么：用 9 个章节（身份/模式/按键/滚轮/传感器/LED/电源/配对/冒烟）把“原理图上看到的连接”结构化，产出 `boards/*.json`。
代码：[survey.py](survey.py) `issues()` L67、`answers_to_board()` L219、`export_board()` L377、`check_answers()` L399；题库 [survey/questions.json](survey/questions.json)（9 节共 57 问）；说明 [survey/QUESTIONNAIRE.md](survey/QUESTIONNAIRE.md)。
实测：空白答案 `error=7 warn=3 info=3`；示例答案 `ok`；`export` 生成 28 个 `pins` 的 v2 板 JSON。

### F11 桌面 GUI 与工程绑定
做什么：选工程目录、恢复上次绑定、扫描脚位宏引用、体检、应用板级包、生成金机、导出 diff、保存板 JSON。
代码：[launch.py](launch.py#L387) `WindowApi`：`get_project_info` L600、`pick_project_dir` L612、`scan_biz_refs` L642、`scan_port_checklist` L656、`export_golden_diff` L770、`sync_biz_contracts` L792、`write_user_config` L813、`save_board_json` L955、`get_policy_catalog` L982、`synth_golden_board` L1027、`apply_board_pack` L1062。
绑定判定：找 `<root>/projects/mouse_demo/periph/user_config.h`（L626–L631）。

---

## 4. 使用方式

### 4.1 环境准备（本机实测）
- 系统：Windows；Python **3.12.10**。
- 唯一运行依赖：`pywebview>=5.0`（[requirements.txt](requirements.txt)），本机已装 **6.2.1**；GUI 使用 `edgechromium` 后端。
- 开发依赖在 `pyproject.toml` 的 `[project.optional-dependencies] dev`：`pytest>=8.0`、`ruff>=0.6`；未提供 lock 文件。
- 没有 `pip install -e .` 的必要即可运行（模块同目录平铺）；`pyproject.toml` 也注册了 `om-pinmux` 命令。

### 4.2 CLI 子命令与参数

| 命令 | 关键参数 | 作用 |
|---|---|---|
| `validate` | `--board NAME` 或 `--all`、`--json` | 校验单个/全部板描述 |
| `synth` | `--board`（默认 BD319）、`--pictures`、`--out` | 生成宏观金机归档 |
| `apply` | `--target <SDK根>`（必填）、`--board`、`--donor`、`--policy-json`、`--dry-run` | 应用板级包 |
| `port` | `--target`、`--golden`（均必填）、`--board`（默认 CH04）、`--report-dir`、`--dry-run` | 换板移植 |
| `compare` | `--golden`、`--target` | 输出关注文件清单（SAME/DIFF/仅一侧） |
| `rollback` | `--manifest <manifest.json>` | 按事务回滚 |
| `survey` | `blank` / `check` / `export`，`--answers`、`--out`、`--force` | 调查表 |

### 4.3 实测命令与真实结果（2026-11-06）

| # | 命令 | 结果 |
|---|---|---|
| 1 | `python om_pinmux.py validate --all` | 7 块板中 **5 通过、2 失败**：`BD316` 报 `P12` 同时被 `SENSOR_SDIO_PIN` 与 `SENSOR_MOSI_PIN` 占用；`MW650` 报 `modePins="wired"` 非法、缺 `MODE_BLE_24G_PIN`、features 不一致。但进程退出码为 **2**（应为 1，见 §6.3-6） |
| 2 | `python om_pinmux.py validate --board BD319` | `ok`，0 error 0 warn |
| 3 | `python -m pytest -q` | 共 8 个用例（空文件 `test_wheel_soft_gpio.py` 贡献 0 个），**1 失败**：`test_all_tracked_boards_are_valid`。原因就是上面的 BD316/MW650。测试套件当前是红的 |
| 4 | `python om_pinmux.py survey check --answers survey\answers_blank.json` | `error=7 warn=3 info=3`，`ok=false`（提示未填项）；退出码同样是 2 |
| 5 | `python om_pinmux.py survey check --answers survey\answers_demo.json` | `ok=true`，error=0 |
| 6 | `python om_pinmux.py survey export --answers survey\answers_demo.json --out %TEMP%\omtest_board.json` | 生成 `schema=om6239-board-desc/v2`，`pins` 28 项，`meta.projName=DEMO`，无 `nets` |
| 7 | `python om_pinmux.py synth --board BD319 --out %TEMP%\om_synth_out` | 成功，6 个文件（见 F9） |
| 8 | `python om_pinmux.py compare --golden <BD319 SDK> --target <483 HYC SDK>` | `SAME=7 DIFF=28`，说明对照逻辑能识别真实差异 |
| 9 | `python om_pinmux.py compare --golden <SE71M_0486_BD319...> --target <SE71M_0023_KC536...>` | `SAME=35 DIFF=0`（本机这两个 SDK 目录内容相同，`user_config.h` 的 SHA1 也一致；即“BD319 目录”实际是 KC536 底包副本，不是真实 BD319 工程） |
| 10 | `python -c "...inventory_synth_vs_target('BD319', <BD319 SDK>)"` | `SAME=0 DIFF=22 仅合成=4 仅目标=5`。synth 的 `expected_user_config.h` 写成裸数字（`26`、`00`），SDK 里是 `(P26)`/`(P00)`，口径不一致（见 §6.3-2） |
| 11 | `python om_pinmux.py apply --target <BD319 SDK> --board BD319 --dry-run` | 输出“`[dry-run] 8 项策略将应用于 ...`”，退出码 0 |
| 12 | `python om_pinmux.py port --target <KC536 副本> --golden <BD319> --board BD319 --dry-run` | 打印逐文件计划：`[same]` 多数、`[skip_missing_src]` 4 个 ledc 文件、备份目录 `_port_bak_<时间戳>` |
| 13 | 同上，去掉 `--dry-run`（在 `%TEMP%` 的 KC536 副本上执行，未动项目与原始 SDK） | 成功：`biz_sync ok`（6 actions）、uvproj **“已添加: ledc.c, ledc_mode.c, drv_ledc.c”**、体检 `error=0 warn=2 total=17`；报告末尾把 `key_io.c`、`user_config.c` 标成“非预期 DIFF”（白名单只认 `key_io.h`） |

> 说明：第 13 条是整个仓库里证据最强的一次端到端运行——它在真实 SDK 结构上完成了“拷贝→契约同步→uvproj 修改→体检→报告”，同时也暴露了两个真实缺陷（见 §6.3-3、§6.3-4）。

### 4.4 GUI 使用

1. 双击 `launch.bat`（或 `打开引脚工具.bat`），或 `powershell -File launch.ps1`；
2. “选工程”绑定到 SDK 根 / `mouse_demo` / `periph`（要求存在 `periph/user_config.h`）；
3. 选板（BD319/CH04/KC536/blank）→ 逐功能选脚 → “生成 / 校验”；
4. “写入引脚配置”：写 `user_config.h/.c`、可选 `board_features.h` 与 sleep 文件，随后自动同步 `key_io`，并给出备份目录与 manifest 路径；
5. 其余按钮：体检、金机对照、导出 diff、应用板级包、生成金机、保存板 JSON。

运行证据：[launch.log](launch.log) 记录 `2026-11-06 09:05:29 启动 webview (edgechromium)`；`2026-09-24 17:39:45` 有对 `D:\BD319test\...\periph` 的真实写入，写入了 6 个文件、生成 `_pinmux_bak_20260924_173945` 与 `manifest.json`，并列出 6 条业务契约改写。
（本次只读核查未主动弹出 GUI 窗口，避免占用桌面；是否可启动已由依赖安装情况 + 既有运行日志确认。）

### 4.5 典型输入 / 输出示例

输入（`boards/BD319.json` 节选，29 个 `pins`）：

```json
"meta": { "projName": "BD319", "projIdL": "0x0485", "projIdH": "0x071", "modePins": "dual", "logoType": "rgb" },
"pins": { "KEY_R0_PIN": "P26", "KEY_R1_PIN": "P20", "WHEEL_A_PIN": "P24", "SENSOR_SDIO_PIN": "P12", "LED_R_PIN": "P04" },
"derived": { "LVD_CHECK_INDEX": "POF_LVD_PIN_P33", "WHEEL_IO_SELECT": "ENCODER_PINMUX_SEL_IO_24_25" }
```

输出（写入 `user_config.h` 标记块的形态，见 [index.html:1317](index.html#L1317) 与实际 SDK 文件）：

```c
#define BAT_CHG_PIN            (P31)
#define KEY_B_PIN              (P00)
#define WHEEL_IO_SELECT        ENCODER_PINMUX_SEL_IO_24_25
#define PIN_WAKE_UP_MASK       (1<<26) | (1<<20) | ... | (1<<SENSOR_MOTION_PIN)
```

另有 `gpio_config_table[]`（`user_config.c`）、`board_features.h`（`BOARD_HAS_*`）、`periph_gpio_sleep_set.pinmux.c`。

---

## 5. 技术架构与数据来源

### 5.1 分层

```
数据层      chip/om6239.json（封装脚/复用/教训） + boards/*.json（板级唯一描述）
校验层      validation.py（Python，板级静态规则）
            index.html runValidation()（JS，GUI 实时规则）
生成层      index.html generateH/generateCTable/generateFeaturesH/generateSleepTemplate
写入层      launch.py write_user_config → operations.py FileTransaction（备份/manifest/回滚）
业务层      biz_sync.py（契约扫描 + key_io/sleep/RTE 改写 + 体检）
移植层      port_apply.py + golden_diff.py（金机拷拷/对照/uvproj/报告）
归档层      synth_golden.py（宏观金机期望值）
入口层      om_pinmux.py（CLI） / launch.py + index.html（GUI）
```

关键事实：**真正的代码生成在浏览器端 JS**（`index.html`），Python 端只负责“校验、写回、同步、对照、报告”。因此 CLI 无法从板 JSON 直接生成代码，必须经过 GUI 的 `generateCode()`；这也是后续做批量化/CI 的主要结构障碍。

### 5.2 芯片数据（`chip/om6239.json`）

- `package_pins`：32 个封装脚（`pkg/side/idx/alt`），`gpio_count=26`；
- `internal_not_on_package`：6 个内部/非封装脚（如 P14）；
- `fixed_package`：VDD/VBUS/XTAL/BOOT/RF 等固定脚说明；
- `mux`：`LEDC_SEL`、`UART_SEL`、`ENCODER`、`LVD`、`USB` 的寄存器字段与可选码（如 `PMU_LEDC_SEL_IO_01/05/21/...`）；
- `lessons`：4 条踩坑记录（如 LEDC SEL 占用滚轮脚会导致灯带+滚轮同时失效）。
- 数据来源标注为 `OM6239_DataSheet_V0.1_BYKC_20250211.pdf`，由人工摘录，不含完整寄存器/电气参数。

### 5.3 板数据（`boards/*.json`，schema `om6239-board-desc/v2`）

字段：`schema / chip / meta / features / pins / nets / unused_package_gpio / derived / notes / source`。
- `meta`：项目身份与板型（`projName/consumerName/projIdL/projIdH/verId/modePins/logoType/ledPolarity/sensorDir/wheelMux/pairing24g/pairingBle/...`）；
- `features`：`BOARD_HAS_KEY_C0`、`BOARD_HAS_EXTRA_KEYS`、`BOARD_HAS_DPI_PAIR`、`BOARD_HAS_SENSOR_NCS`、`BOARD_MODE_DUAL_PIN`、`BOARD_LOGO_LEDC/RGB`、`BOARD_LED_ACTIVE_HIGH` 等；
- `pins`：25–30 个宏→Pxx；`derived`：LVD 索引、滚轮 mux、软滚轮标志；
- `notes`：该板专属注意事项（如“无 KEY_PAIR：key_io 需 #ifdef”）；
- `source`：指向 `E:/M_2026_T/description/<板>`（BD319 指向 `mcu_om6239_main + modules`）。

**数据是人工整理的**：`synth/BD319/MANIFEST.md` 指向 `E:\pictures\BD319` 的原理图截图与 `README.md` 模块索引；工具本身不解析 PDF/原理图，也不从 SDK 反向抽取脚位。`survey/questions.json` + 答案 JSON 是给非开发人员的结构化替代输入。

### 5.4 同一事实存在多份副本（重要架构风险）

| 数据 | 副本位置 |
|---|---|
| 引脚宏清单（36 个） | [biz_sync.py:14](biz_sync.py#L14) `PIN_MACROS`、`index.html` 的 `ROLE_DEFS`/`CHIP`、`boards/*.json` 的 `pins`、`synth_golden.py` 的 `_pin_num` 命名约定 |
| 芯片封装/复用 | `chip/om6239.json` 与 `index.html` 的 `const CHIP`（L608） |
| 板型模板 | `boards/*.json` 与 `index.html` 的 `PRESETS`（L714，BD319/CH04/KC536 硬编码） |

例如 `MW650` 在调查表里是合法的 `wired` 模式，但 `validation.py` 只接受 `single/dual`，于是同一仓库内“数据能生成、校验器不认”。这不是数据错误，而是**模型分叉**。

### 5.5 生成与写入链路

```
boards/X.json（或 GUI 状态）
  → index.html generateH/CTable/FeaturesH/Sleep
  → launch.write_user_config：标记块替换 + 去重 + 项目 ID 补丁
  → biz_sync.sync_board_contracts：key_io.h/c、sleep、RTE、LOGO
  → operations.FileTransaction.commit：manifest.json
（另一条线）port_apply：golden→target 拷贝 → biz_sync → uvproj → 体检 → 报告
```

---

## 6. 当前完成度与局限

### 6.1 真实可用（有运行证据）

1. **GUI 写入闭环**：真实写入过 `D:\BD319test`（[launch.log](launch.log) 2026-09-24），包含 6 个文件、备份目录、manifest 和业务契约改写；回滚能力有单测（[tests/test_operations.py](tests/test_operations.py#L6)、L27）。
2. **业务契约同步**：`key_io` 单/双模式、PAIR/DPI 分支的自动改写，在端到端实测中产生 6 个 action。
3. **换板体检**：能对真实 SDK 做 16–17 项检查，并正确指出“RGB 板目录里存在 LEDC 文件”。
4. **金机对照**：`compare` 对真实不同的两块 SDK 输出 `SAME=7 DIFF=28`，不是空跑。
5. **板描述校验**：schema / 封装白名单 / 同脚冲突 / 模式脚 / USB 固定脚 / 滚轮 mux / LVD 等一组静态规则，确实拦下了 BD316 的 P12 复用冲突。
6. **调查表→板 JSON**：9 节 57 问，能生成 v2 JSON 并通过自检（demo 答案）。
7. **板级包**：13 项策略 + 供体拷贝 + 4 种文本补丁；RGB 板默认 8 项，可 dry-run。

### 6.2 雏形 / 未验证

| 能力 | 现状 | 证据 |
|---|---|---|
| Keil 工程生成 | 不生成 `.uvprojx`；只在 `port_apply` 里**追加** `ledc.c/ledc_mode.c/drv_ledc.c` 三个源文件条目 | [port_apply.py:204](port_apply.py#L204) `ensure_uvproj_ledc`；实测报告“已添加: ledc.c, ledc_mode.c, drv_ledc.c” |
| 编译验证 | 无，任何一步都不调用 Keil/armcc，也不解析编译产物 | 全仓库无构建调用 |
| synth 期望值对照 | 生成的宏是裸数字，SDK 是 `(Pxx)`，对照恒为 DIFF | 实测 `SAME=0 DIFF=22`；[synth_golden.py:35](synth_golden.py#L35) `_pin_num` |
| 传感器模型 | 只有 `sensorDir`（时钟相位）与脚位；没有型号/DPI 档位/帧率/寄存器配置 | `boards/*.json` 无 sensor 对象 |
| USB 描述符 | 只有 `projIdL/H/verId` 与固定 USB 脚；VID/PID/字符串靠 donor 拷贝 | `board_pack` 的 `product_usb_strings` 默认关闭 |
| 时钟树 | 无 | `chip/om6239.json` 无时钟源/PLL/分频模型 |
| LED 效果 | 只有“RGB vs LEDC”与开关宏；无灯效表 | `generateH` 只生成 `led_*_on/off` |
| 外设复用分配 | 只有 LEDC/UART/ENCODER/LVD/USB 的“选哪组脚”表，没有通用 UART/SPI/I2C 引脚功能矩阵 | `chip/om6239.json` 的 `mux` 仅 5 类 |
| JSON Schema | `schemas/board-desc-v2.schema.json` **0 字节** | 目录实测 |
| GUI 自动化测试 | 无；`tests/` 只覆盖 validation/uvproj/operations | 4 个测试文件，其中一个空文件 |
| CI | 有 `quality.yml`（ruff + pytest），但当前套件本身是红的 | §4.3-3 |

### 6.3 已确认的缺陷（按影响排序）

1. **生成逻辑双份**：JS `generateH/CTable` 与 Python 侧没有等价实现；`biz_sync.PIN_MACROS` 又是第三份宏清单。任何新增脚位宏都要改多处，漏改不会被编译器发现。
2. **synth 期望脚位格式错误**：`expected_user_config.h` 输出 `26`、`00`，而 SDK 约定是 `(P26)`、`(P00)`；`inventory_synth_vs_target` 因此恒报 DIFF（实测 22 条）。这会让“金机对照”失去判据。
3. **`port_apply` 无条件补 LEDC 工程条目**：BD319（RGB 板）实测中，4 个 ledc 源文件是 `skip_missing_src`，但 uvprojx 仍被加入 `ledc.c/ledc_mode.c/drv_ledc.c`，工程会引用不存在的文件。`MANIFEST.md` 里“RGB 板不要用 CH04 port_apply”的警告正是这个问题的旁证。
4. **报告白名单过窄**：`EXPECTED_FOCUS_DIFF_RELS` 只允许 `key_io.h` 为预期 DIFF，但 `biz_sync` 也会改 `key_io.c`、`user_config.c`，端到端报告因此把这两个文件标成“非预期 DIFF（需处理）”。
5. **数据模型与校验器不同步**：`MW650` 的 `wired` 模式由调查表支持、被 `answers_to_board` 生成，却被 `validation.py` 判为非法；`BD316` 的 `SENSOR_MOSI/SDIO` 同脚写法也未被上游拦截。
6. **退出码语义不符**：`_exit_code()`（[om_pinmux.py:32](om_pinmux.py#L32)）只认 `validation`/`error_count`；`validate --all` 与 `survey check` 的失败结果两个字段都没有，实测返回 `2`（环境错误），脚本无法区分“校验失败”和“工具坏了”。
7. **CLI 的 `apply`/`port` 没有事务 manifest**：只有 GUI 的 `write_user_config` 用 `FileTransaction`；CLI 备份是裸时间戳目录（`_port_bak_<stamp>`、`_pinmux_bak_<stamp>`），无法用 `rollback --manifest` 回滚（实测 grep：`port_apply.py`/`board_pack.py` 中无 `manifest`）。
8. **测试/CI 现状**：`test_all_tracked_boards_are_valid` 失败；`test_wheel_soft_gpio.py` 为空文件；CI 因此不能作为质量门。

---

## 7. 与 STM32CubeMX 的对齐方向

### 7.1 先对齐“思想”，不是对齐 `.ioc`

用户提供的建设建议里最关键的三条，本项目和它们的对应关系是：

| 建议中的原则 | 本项目现状 |
|---|---|
| 配置与代码分离、唯一真相源 | `boards/*.json`（v2）+ `chip/om6239.json` 已是雏形；但引脚宏在 JS、Python、boards 里各有副本，尚未成为唯一源 |
| 单向生成：配置 → 生成器 → 代码/工程 | 已有“配置 → `user_config` 标记块 / `board_features.h` / sleep”的生成，但生成器在 JS、无法 CLI 复用；工程文件只做了 uvproj 追加 |
| 生成器 = 芯片数据库 + 校验引擎 + 模板输出 | 芯片库很薄（只有封装/复用/4 条教训）；校验是“板级静态规则”；模板是 JS 字符串拼接，不是模板引擎 |

因此，**不建议另起 `.ioc` 或 `.omcfg` 并推翻现有 JSON**。更合理的路径是：先把 `boards/*.json` 升格为项目级配置载体（补传感器/USB/时钟/LED 字段），再把它渲染成代码；`.omcfg`（YAML）可以作为“人写的入口格式”，由 `survey`/GUI 生成 JSON，二者只保留一份中间模型。

### 7.2 阶段一：底层数据模型与校验（近期，优先级最高）

| 事项 | 现状差距 | 落地成本 | 验收标准 |
|---|---|---|---|
| 单一数据源 | 4 份引脚宏副本；JS `CHIP/PRESETS` 与 `chip/*.json`、`boards/*.json` 重复 | **M**：需把 JS 改为启动时读 JSON（GUI 可走 `WindowApi` 读文件），并把 `PIN_MACROS` 从板数据派生 | `boards` 改一个脚位，GUI/CLI/synth 全部一致 |
| JSON Schema 落地 | `schemas/*.schema.json` 为 0 字节，校验全靠手写 | **S**：补 schema + 在 `validation.py` 里用 `jsonschema` 校验（新增 1 个依赖），保留现有语义规则 | 非法板 JSON 在 schema 层即被拒绝 |
| 校验器与调查表同步 | `wired` 模式不合法；同脚冲突未被上游拦住 | **S**：`validation.py` 增加 `wired`（并明确其 mode 宏），`survey.py` 在 `answers_to_board` 时复用 `validate_board` | `validate --all` 全绿，`pytest` 全绿 |
| 复用/依赖校验 | 只查“同脚冲突”和 5 类 mux；不查外设→时钟/引脚依赖 | **M**：以 `chip/om6239.json` 的 `mux` 为索引，补 UART/SPI/I2C/PWM 的可用脚集合与互斥 | 选 UART 脚时能提示与 LEDC/滚轮冲突 |
| 修正 synth 口径与报告白名单 | 裸数字 vs `(Pxx)`；`key_io.c/user_config.c` 被误报 | **S**：`generate_expected_user_config_h` 输出 `(Pxx)`；`EXPECTED_FOCUS_DIFF_RELS` 纳入 `biz_sync` 实际会写的文件 | synth 对照 `SAME` 数量与真实差异一致 |
| 退出码与 CI | `validate --all` 返回 2；套件红 | **S**：`_exit_code` 识别 `results`/`summary.error`；修 BD316/MW650 或标注为“归档样例不参与全量校验” | CI 绿灯，退出码可脚本判定 |

### 7.3 阶段二：配置规范与代码/工程生成（中期）

| 事项 | 现状差距 | 落地成本 | 说明 |
|---|---|---|---|
| Python 侧生成器（Jinja2） | 生成全在 `index.html`；CLI 不能生成 | **L**：把 `generateH/CTable/FeaturesH/Sleep` 迁移为 Python 模板（或先做“导出中间 JSON → Python 渲染”），GUI 改为调用后端 | 这是“单向生成”的关键；迁移时用现有 `synth/BD319` 和 `reports/bd319_write_test_result.json` 做回归基线 |
| `project_config.h` 统一入口 | 现在宏散落在 `user_config.h` / `board_features.h` | **M**：新增聚合头（`#include` 现有两文件），业务代码逐步切到聚合头 | 对标 CubeMX 的 `main.h` 角色，不破坏现有包含关系 |
| 按键映射表 / DPI 档位表 / LED 效果表 | `key_io` 是手写零散 `#ifdef`；无 DPI 表；无灯效表 | **M**：需要业务侧先定义表结构（DPI 档位、灯效 id），再生成表文件；`boards/*.json` 增加 `keymap/dpi/led` 段 | 不定义表结构就生成，会产出不可维护的代码 |
| Keil `.uvprojx` 生成/更新 | 只追加 3 个 LEDC 条目，且无条件执行 | **M**：抽出 `uvproj` 模板（source group / include path / define），按 board 特性增删；先修“RGB 板不注入 LEDC” | 用两套真实工程做 diff 回归 |
| 驱动裁剪 | 无 | **M**：以 policy/features 驱动 source group 白名单；需先清点 SDK 文件依赖 | 与 uvproj 生成一起做更划算 |
| USER CODE 区 | 已有“标记块 + 去重 + fallback 锚点”的雏形（`BEGIN_H/END_H`） | **S**：把标记命名、嵌套、冲突策略规范化并在文档中固定 | 现有实现已经是可复用资产 |
| 编译/冒烟闭环 | 无 | **L**：调用 Keil 命令行（`UV4 -b`）或 armcc，产出编译日志并回填体检报告 | 没有这一步，“生成即正确”无法保证 |

### 7.4 阶段三：图形化配置界面（远期）

现有 GUI（`index.html`，91.6 KB）已经具备 CubeMX 式界面的**骨架**：芯片封装图、左侧功能角色列表、右侧参数表单、底部校验输出、模板导入、工程绑定。缺的是：

| CubeMX 能力 | 本项目现状 | 差距/成本 |
|---|---|---|
| 引脚图点击分配 + 复用下拉 | 已有封装图与角色选择（`CHIP`/`chipMeta`/`roleVisible`） | 差距小；需要把 `CHIP` 换成 `chip/om6239.json`（**S**） |
| 时钟树配置页 | 无 | 需要先有芯片时钟模型（**L**） |
| 外设参数页（UART/SPI/USB/定时器） | 无 | 需要外设模型 + 生成模板（**L**） |
| `.omcfg` 打开/保存/另存 | 只有 JSON 导入导出与“保存 board” | **M**：增加 YAML 读写与 schema 迁移 |
| 生成预览/差异 | 有“生成 / 校验”文本框，无文件级 diff | **S**：接 `golden_diff.export_unified_diff` 做预览 |
| 工程级（多板/多工程）视图 | 单工程绑定（`pinmux_state.json`） | **M** |

结论：GUI 不必重写；把数据层与生成层搬到后端，前端就能自然演进成“CubeMX 风格”的配置页。

---

## 8. 风险与建议

### 风险

1. **数据漂移**（高）：同一引脚宏存在 3–4 份定义，`MW650` 已经证明“问卷能生成、校验器不认”。这类问题不会在编译期暴露。
2. **工程文件破坏**（高）：`port_apply` 无条件补 LEDC 条目，已实测让 RGB 板 uvprojx 引用不存在的源文件；若直接用于真实工程，Keil 打开即报错。
3. **文本补丁脆弱**（中高）：`_patch_file` 依赖正则/固定锚点（`m_data_flag &= ~bmouse_data_send`、`__STACK_SIZE 0x...`），SDK 版本一变就可能“noop”或误改，且无编译验证兜底。
4. **对照失真**（中）：synth 期望值格式错误 + 报告白名单过窄，会让工程师逐渐忽略报告，等于丢失质量信号。
5. **回滚覆盖不全**（中）：CLI `apply/port` 的备份没有 manifest，无法一键回滚；GUI 写入有 manifest，但 `port_apply` 不走它。
6. **单芯片、单工程结构假设**（中）：所有路径都硬编码 `projects/mouse_demo/periph` 与 `keil5/SE71M.uvprojx`；换 SDK 目录结构就要改代码。
7. **质量门缺失**（中）：CI 红、`test_wheel_soft_gpio.py` 空、无 GUI 测试、无编译验证。

### 建议（按顺序）

1. **先修“一致性”，再谈生成**：让 `boards/*.json` 成为唯一数据源；`index.html` 的 `CHIP`/`PRESETS`、`biz_sync.PIN_MACROS`、`synth_golden` 的命名约定全部从它派生；补 schema 并在 CI 强制校验。验收：`validate --all` 全绿、`pytest` 全绿、GUI 与 CLI 对同一板输出一致。
2. **立刻修三个已证实的缺陷**：`port_apply` 按 `logoType` 决定是否注入 LEDC；`expected_user_config.h` 改 `(Pxx)`；报告白名单纳入 `key_io.c`/`user_config.c`。这三项都是单文件、低风险改动，却能立刻恢复对照与工程的可信度。
3. **把生成器搬到 Python（Jinja2）**，保留 GUI 作为“前端 + 后端调用”。迁移前先用现有 `synth/BD319` 与 `reports/bd319_write_test_result.json` 建立黄金输出回归。没有这一步，CLI/CI/批量换板都无法成立。
4. **给 CLI 也接 `FileTransaction`**，并让 `port_apply` 产出的备份目录带 `manifest.json`；这样“写坏了”始终可回滚。
5. **补配置边界再扩字段**：先定义 `keymap`、`dpi_levels`、`led_effects`、`usb` 四段的表结构（可先只做 schema + 常量表），再让 `board_pack`/生成器消费；不要先生成“没有语义的空壳”。
6. **增加编译冒烟**（Keil 命令行可选，先支持 `UV4 -b` 或至少“源文件存在性 + include 路径”静态检查），把结果写回体检报告。在完成之前，报告里应明确写“未编译验证”，避免误读为“已可用”。

---

## 附录 A：本轮实测的边界与未做之事

- 未修改仓库内任何代码或配置；仅在 `%TEMP%` 下创建运行产物（`om_pinmux_e2e`、`om_synth_out`、`omtest_board.json` 等）。
- `port` 非 dry-run 只在 **KC536 的临时副本**上执行，未触碰 `E:\M_2026` 原始 SDK 与 `E:\tools\om_pinmux`。
- 未主动弹出 GUI（避免占用桌面）；GUI 可运行性由 `pywebview 6.2.1` + 既有 `launch.log` 启动/写入记录佐证。
- 未执行 `rollback`（需要真实写入产生的 manifest；仓库内 `reports/` 未保存该 manifest，GUI 日志里的 `D:\BD319test` 备份已不在当前可访问范围）。
- 未做编译验证（本机未尝试 Keil 命令行；这也是项目本身的缺口）。
