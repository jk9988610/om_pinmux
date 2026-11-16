# HANDOFF — pinmux_5 交接文档

> 日期：2026-11-16
> 上一棒：pinmux_4（颜色表参数化，但实际未落地）
> 读者：pinmux_7（大工程开始前）
> 状态：**主线功能层已收口**。LEDC 接入 GUI + §4 keys PAIR 可选 + A+B 技术债清理 + B+A 卫生清理全部完成。下一棒进入 ROADMAP §0.2 结构性重构（大工程）。

---

## 0. 三十秒速览

- 工程根：`E:\tools\om_pinmux`（WORKSPACE），git 仓库，origin = `git@github.com:jk9988610/om_pinmux.git`
- 分支：`fix_old_msg`（工作线）/ `main`（发布线），两线同步，本地=远程
- 工具：`python -m omcfg {init,check,gen,new,rollback,smoke}` + pywebview GUI（`launch.bat`）
- 回归：`python -m pytest`（154 passed）+ `python -m omcfg smoke`（三形态全 PASS）  ⚠️ pinmux_7 勘误：原记 155 为笔误，实测 154（原测试数 148→147 记错，非测试被删；test_schema_board_fields.py 7 个不变）
- 本次交付：见 §2
- 下一棒任务：§6 ROADMAP §0.2 结构性重构，优先级见 §6.2

---

## 1. 产品定位（决定性方向，全文基于此）

**是什么**：OM6239 芯片的**配置驱动固件生成器**——不是 IDE，不是通用 pinmux 工具。
用户给一份 `.omcfg`（YAML），工具吐出可编译可烧录的 Keil 工程。

**给谁用**：
- 内部 FAE：客户提需求，30 分钟内出第一版
- 硬件工程师：验证原理图 pinmux 是否可实现
- 客户：自己板子自己配

**怎么用**（两条主路径 + GUI）：

| 路径 | 命令 | 场景 |
|---|---|---|
| 新建 | `python -m omcfg new --name XXX` → 编辑 → `python -m omcfg gen --apply` | 从内置 baseline 长出，配引脚 → 生成 |
| 改现有 | `python -m omcfg init`（从现有工程推导）→ 编辑 → `gen --apply` | 客户已有 CH04 想改成自家板 |
| GUI | pywebview 打开，两栏配置，点生成 | 非 CLI 用户 |

**核心承诺**（差异化点）：
1. **0 Error 0 Warning** 是硬保证（`smoke` 三形态回归）
2. **事务回滚**（生成错了一键还原，不污染原工程）
3. **配置即真相**（`.omcfg` 是唯一源，模板只是"另存为"起点）

**不做什么**（ROADMAP §1.2）：
- 不做 middleware / RTOS / 多芯片通用
- 不做 PLL 求解器
- 不做 USB 协议栈配置

---

## 2. 本轮交付（pinmux_5 完成）

### 2.1 LEDC 接入 GUI（`dad2f82` + `184421f`）

- 后端 `Api.prepare_workspace_with_modules(template, workspace, ["ledc"])` 聚合
- 前端 `ensureWizard` 加"灯带（LEDC）"勾选框；`prepare` 分支传 modules
- 配引脚面板：LEDC 角色在 `state.ledcPrepared=false` 时灰显"未启用"
- `finalize_ledc_sel`：按 `LEDC_PIN` 动态替换 `ledc.c` / `drv_ledc.c` 的 `PMU_LEDC_SEL_IO_xx`
- `drv_ledc.c` 覆盖：`prepare_workspace_with_modules` 里 inject 后强覆盖（修 KC536 模板 IO_01 遗留）

### 2.2 §4 keys PAIR 可选（`6516deb`）

- baseline `key_io.h` / `key_io.c` 用 `#ifdef KEY_PAIR_PIN` 包 PAIR 代码
- `.omcfg` 的 `pins` 省略 `KEY_PAIR_PIN` → 自动去掉 PAIR 宏 / 唤醒掩码
- `configs/CH04_6k.omcfg` 样例（CH04 派生 6 键版）
- `rules.py` `key_io.refs` 用 `_strip_ifdef_block` 排除条件引用

### 2.3 A+B 技术债（`9a12711`）

- A：`finalize_ledc_sel` + CLI `cmd_gen` + GUI `generate` 调用
- B：`chip/om6239.json` `sdk_supported` 字段，P01/P05 可用，P21/P33 标 false
- `pinmap._ledc_pin_set` 过滤 `sdk_supported=false` 的选项
- `configs/CH04_p01.omcfg` 样例（LEDC_PIN=P01，WHEEL_A/B 挪到 P05/P06）

### 2.4 B+A 卫生清理（本轮最后一个 commit）

- 删 `dpi_color_tab[]`（baseline + 模板）
- 修 `flash_process.c:79/82` 注释笔误
- schema 补全 `board.uart_pin` / `board.ledc_rgb_number` / `board.sensor.{dpi_levels,dpi_default,v2_en}`
- validate 加 `ledc_rgb_number` 1..64 校验
- `tests/test_schema_board_fields.py` 7 用例

---

## 3. 主线状态对照

| 阶段 | 目标 | 状态 |
|---|---|---|
| 一期 | 内置 SDK + 命名即建工程 | ✅ |
| 二期 | 引脚配置 + 冲突检测 | ✅ |
| 二期补 | LEDC 接入 + keys PAIR + A+B 技术债 | ✅ 本轮 |
| **三期** | **外设参数 + 模块连带校验** | **半完成**（schema 补全了"已用字段"，未实现 `uart_baudrate` / `spi_mode` / `usb_id` / `usb_version`） |
| **§0.2** | **结构性重构（删 index.html 生成逻辑 + 三个子系统）** | **未动** ← 下一棒主战场 |

### 3.1 HANDOFF_pinmux_3 §6 完成状态

| 任务 | 状态 |
|---|---|
| A rewrite_identity 事务化 | ✅ |
| B 颜色表参数化 | ⚠️ **HANDOFF_pinmux_4 声称完成但实际未落地**（见 §5.1） |
| C LEDC_PIN=P34 诚实化 | ✅ |
| D KEY_C0_PIN 缺口 | ✅（核实无需做） |
| E smoke --skip-locked | ✅ |

### 3.2 HANDOFF_pinmux_4 §6 遗留（部分已顺手清）

| 项 | 状态 |
|---|---|
| `dpi_color_tab[]` 死代码 | ✅ 本轮删 |
| flash 表注释笔误 | ✅ 本轮改 |
| DPI6/7 硬件不可达 | ⚠️ 仍在（触发条件：客户需 8 档 DPI） |
| DPI7 颜色语义不一致 | ⚠️ 仍在（与上条一并） |
| 换行符双轨 | ⚠️ TPL=CRLF、BASE=LF 保持未统一，`newline=""` 读写已记 |

---

## 4. 工作台约定（铁律，踩过的坑）

1. **受管文件绝不 `open(w)`**，走 `patch` / `patch_range` / `FileTransaction`
2. **多处改动包 `patch_batch()`**，任一步失败整批回滚
3. **`patch` 的 `old` 必须完整整行**，不能是行中片段
4. **`old` 多次出现要选唯一锚点**
5. **PowerShell here-string 里 `\"` 是字面两个字符**，写进 Python f-string 表达式会 SyntaxError；用临时 .py 文件走 Python 注入（本轮踩过）
6. **`json.dumps(indent=2)` 会重排原紧凑格式**，改 chip json 要么保持原格式，要么一次性全换
7. **`.bak*` 备份不要放 `baseline/sdk/`**，`artifacts.is_artifact_path` 不排除 `*.bak`，会算进 META 导致 verify 红；放仓库根 `_bak/`（已在 .gitignore）
8. **META 重算用 `baseline.tree_digest` / `file_digest` + `artifacts.is_artifact_path` 排除**，不要 `rglob` 硬算

---

## 5. 已知坑与遗留

### 5.1 颜色表参数化未完成（HANDOFF_pinmux_4 误报）

**HANDOFF_pinmux_4 §0 说"任务 B 已完成并验收通过"**，但实际探查：
- `.omcfg` 无 `board.ledc_colors` 字段
- `templates.py` 无 `render_ledc_colors`
- `baseline ledc.c` 的 `dpi_rgb_tab[8][3]` 硬编码（L51 注释里预留了 `#ifdef LEDC_COLOR_TAB_INIT` 的设想，但代码没实现）
- `tests/test_ledc_colors.py` 只校验两个 `ledc.c` 一致，不从配置生成

**pinmux_7 需要确认**：这个是否要做？如果要，按原 HANDOFF_pinmux_3 §6 任务 B 的描述做（探测 492/516/524 的 `dpi_rgb_tab` 差异 → 设计 `board.ledc_colors` → templates 生成 → baseline `#ifdef` 读取 → Keil 编译 + 烧录看灯色）。

### 5.2 `chip/om6239.json` 在 `9a12711` 被格式化噪音污染

diff 显示 467 行变化，实际业务变化 ≤20 行。原因：`json.dumps(indent=2)` 重排原紧凑格式。
`docs/STRUCTURAL-SWITCH-CHECKLIST.md` 已追加说明。
**不要再用 `json.dumps` 重写 chip json**。

### 5.3 §1 sensor 4w / §2 switch 单双脚 / §3 led 极性 / §4 keys PAIR / §5 wheel 相序

`docs/STRUCTURAL-SWITCH-CHECKLIST.md` 新增"自动化状态"节，全部标注为**已支持**（配置驱动），不再需要人工改代码。

### 5.4 DPI6/7 硬件不可达

`dpi_value_tbl[6..7]=0xFF`，切档循环跳过。触发条件：客户需要 8 档 DPI，需扩展 `sensor_dpi_ini`。**不属本轮**。

---

## 6. 下一棒任务（pinmux_7）

### 6.1 先修/确认（1-2 小时）

1. **确认颜色表参数化是否要做**（§5.1）
2. **确认 HANDOFF_pinmux_4 §1 之后是否还有我们没看过的内容**（原文件在编辑器比对，别盲目覆盖）

### 6.2 主战场：ROADMAP §0.2 结构性重构（大工程，按风险从低到高）

| 序 | 任务 | 工作量 | 风险 | 说明 |
|---|---|---|---|---|
| 1 | **删 `index.html` 里的生成/校验逻辑** | 中 | 低 | 91 KB HTML 是"第四份真相"，和 Python/JSON 重复；删完 GUI 只留"视图+表单"。**先做这个，因为最容易验证（GUI 手动走一遍，功能全走 Python）** |
| 2 | **删金机对照子系统**（`golden_diff` / `synth_golden` / `synth/` / `reports/`） | 中 | 低 | 基线正确性由 git + 编译承担。跑 `python -m pytest` + `smoke` 验证不破坏 |
| 3 | **删供体移植子系统** | 大 | 中 | ⚠️ **pinmux_7 勘误（2026-11-16 已完成）**：`port_apply`/`board_pack` 早已不存在；实际删除 `omcfg/workflow.py` + `omcfg/policy.py`（闭环死链，cli/api 零 import、无 CLI、无 GUI、无测试），`omcfg/biz_sync.py` 保留（孤儿但保留，待 pinmux_8 收敛为 contracts.py）。已完成验证：154 passed + smoke 三 PASS 逐字一致 + GUI 全流程走通 |
| 4 | **删问卷子系统**（`survey` + `survey/`） | 中 | 低 | 数据已进 `.omcfg` 模板 |
| 5 | **三期补全**：实现 `uart_baudrate` / `spi_mode` / `usb_id` / `usb_version` 的 generator + schema + rules | 中 | 中 | 每加一个，Keil 编译 + 硬件验证一次 |

**推荐顺序**：1 → 2 → 4 → 3 → 5。理由：1/2/4 是纯删除（低风险），3 涉及供体移植需要真实工程验证，5 是纯新增（可最后做，也可以并行）。

### 6.3 红线（绝不碰）

- 不改 `inject_ledc_files` / `generate_project` / `apply` 内部逻辑
- 不动 `E:\M_2026\0_T\...KC536...` 和 `E:\M_2026\516_BM2017\...` 原始目录
- 不改 `role_catalog.json` / `chip/om6239.json`（除非有明确业务理由 + 保留原格式）
- 卡住先贴现象 + 已尝试命令，**不要猜**

---

## 7. 常用命令速查

```powershell
# 回归
cd E:\tools\om_pinmux
taskkill /F /IM UV4.exe 2>$null
python -m pytest -q
python -m omcfg smoke

# 新建工程（CLI）
python -m omcfg new --name MY_PROJ --target E:\tmp\newproj\MY_PROJ

# 从现有工程推导
python -m omcfg init --sdk E:\path\to\sdk --config configs\CH04.omcfg

# 生成（apply）
python -m omcfg gen --sdk E:\path\to\sdk --apply
python -m omcfg check --sdk E:\path\to\sdk

# GUI
launch.bat

# 备份（推荐放 _bak/，不要放 baseline/sdk/）
Copy-Item path\to\file "_bak\file.bak-xxx"

```
---

## 8.交接仪式
- 读本文件 §0-§3（10 分钟）：产品定位 + 主线状态 + 本轮交付

- 读 §4-§5（5 分钟）：工作台约定 + 坑位

- 读 §6（5 分钟）：下一棒任务

- 跑一次回归：python -m pytest -q + python -m omcfg smoke，确认 154 passed + 三 PASS（pinmux_7 勘误：原记 155 为笔误）

- 挑任务：从 §6.2 序 1 开始，先做"删 index.html 生成逻辑"

- 卡住：贴现象 + 命令 + 已尝试方案，不猜