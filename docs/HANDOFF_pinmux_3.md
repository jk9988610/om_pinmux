# HANDOFF — pinmux_3 交接文档

> 日期：2026-11-14
> 上一棒：pinmux_2（LEDC 三形态 + smoke 回归）
> 读者：pinmux_3
> 状态：工具已可端到端生成三种 logo 形态可编译可烧录工程；125 pytest 全绿；遗留 5 项可选增强

---

## 0. 三十秒速览

- 工程根：`E:\tools\om_pinmux`（WORKSPACE），是 git 仓库
- 核心：`omcfg/` 工具包 + `baseline/sdk/` 内置 SDK 基线（207 源文件，从 457_CH04 派生）
- 命令：`python -m omcfg {init,check,gen,new,rollback,smoke}`
- 回归：`python -m pytest` + `python -m omcfg smoke`（重建三工程）
- 已硬件验证：TEST_CLI（灯带亮+MOS）、TEST_NOCTRL（灯带亮无 MOS）、TEST_NONE（灯带不亮）
- 下一棒任务：见 §6，优先级从高到低

---

## 1. 工作台约定（必读，都是踩过的坑）

脚本通过 workbench 执行，`exec` 在预置命名空间，可用 `ROOT` / `WORKSPACE` / `patch` / `patch_range` / `patch_batch` / `read`。

### 铁律
1. **受管文件绝不 `open(w)`**，走 `patch` / `patch_range`（自动备份 + 语法校验）。
2. **多处改动包 `patch_batch()`**，任一步失败整批回滚。
3. **`patch` 的 `old` 必须完整整行**，不能是行中片段。
4. **`old` 多次出现要选唯一锚点**，别用短串。
5. **三引号 `new` 里的 `\n` / `\t` 要双写** `\\n` / `\\t`；含正则的 `new` 用 `r'''...'''`。
6. **`patch_range` 的 `start`/`end` 是「行内容字符串」不是行号**（踩过：传整数报 `'int' object has no attribute 'strip'`）。
7. **`patch()` 每次写入会在末尾追加 `\n`**，所以「修末尾换行数」用 `patch` 会越修越多，必须 `write_bytes` 二进制处理。
8. **`patch_batch` 的事务消息可能与实际回滚状态矛盾**，改完用二进制读 + SHA1 验证真实状态。
9. **`read_text` 默认 UTF-8**，遇 GBK 文件炸。探测先读 bytes 判编码。

### 校验模式
- 改完用纯文本子串检查，`print("OK"/"MISS")`
- 不要对 `.c/.h` 做 `compile()` 校验（C 文件会报假错）
- `.py` 用 `py_compile.compile(path, doraise=True)`

### 流程
- **先只读探测，再改**。探测脚本和修改脚本分开给。
- 一次一个语义单元，不一口气改 10 个文件。
- `.c/.h` 改动提醒用户「先 Keil 编译再测」。

---

## 2. 项目结构速查
```md
E:\tools\om_pinmux
├── baseline/
│ ├── sdk/ # 内置 SDK 基线（207 源文件，CH04 派生）
│ ├── project.omcfg # 基线板级配置（CH04）
│ └── META.json # file_count=207, tree_sha256 已对齐
├── omcfg/
│ ├── artifacts.py # 【新】产物排除规则（唯一来源）
│ ├── baseline.py # tree_digest/verify_meta 已忽略产物
│ ├── newproject.py # _excluded 委托 artifacts
│ ├── rules.py # key_io.refs 改为扫 .c 实际使用
│ ├── validate.py # LEDC_CTRL_PIN 可选
│ ├── smoke.py # 【新】三工程冒烟
│ ├── cli.py # 新增 smoke 子命令
│ ├── model.py / pinmap.py / derive.py / transaction.py
│ ├── initproject.py
│ ├── generate/generator.py + templates.py # logo 三分支
│ ├── targets/sdk.py + uvprojx.py
│ ├── policy.py / workflow.py / biz_sync.py # 历史欠账已入仓
│ └── templates/ledc/ # 6 个 LEDC donor 模板（492 主流版）
├── configs/ # KC536.omcfg, CH04.omcfg
├── tests/ # 125 pytest（含 test_artifacts/test_logo_variants/test_smoke）
├── _test_gen/ # 三个冒烟工程（已 gitignore）
│ ├── TEST_CLI/ id=0x8888 logo=ledc 有 CTRL
│ ├── TEST_NOCTRL/ id=0x7777 logo=ledc 无 CTRL
│ └── TEST_NONE/ id=0x6666 logo=none
└── docs/

```

## 3. 命令速查

### CLI
```pwsh

python -m omcfg new    --name X --target <dir> [--id 0xNNNN] [--scan <dir>]
python -m omcfg init   --config <omcfg> --sdk <dir> [--force]
python -m omcfg gen    --sdk <dir> [--config <omcfg>] [--apply]   # 默认 dry-run
python -m omcfg check  <omcfg ...> | --all <dir> | --sdk <dir>
python -m omcfg rollback --manifest <bak/manifest.json>
python -m omcfg smoke  [--out <dir>]                               # 重建三工程
退出码：0 成功 / 1 配置校验失败 / 2 环境错误 / 3 写盘失败 / 4 历史预留
```

```pwsh
python -m pytest                                # 125 passed 才合格
python -m omcfg smoke                           # 三工程全 PASS
python -m pytest                                # 125 passed 才合格

```
环境变量（防中文乱码）
```py
env = dict(os.environ)
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"
```

## 4. 关键事实（不用重新探测）

- 事实	值
- baseline 来源	457_CH04（commit 212aa96），但 LEDC 件套已升级到 492 主流
- baseline META	file_count=207, size_bytes=5694176, tree_sha256=03d118c0...
- CH04 的 LEDC_PIN	P34 是死代码，PMU 只支持 GPIO01/05/17/27，实际走 GPIO5- （PMU_LEDC_SEL_IO_05）
- 三工程 id	TEST_CLI=0x8888 / TEST_NOCTRL=0x7777 / TEST_NONE=0x6666
- ledc.h 新结构	#if defined(LEDC_PIN) 真声明，#else 空宏 shim，兜底 #ifndef - LEDC_RGB_NUMBER 在 main.h 之后 ledc_mode.h 之前
- LEDC_POWER_SET	#ifdef LEDC_CTRL_PIN 有 MOS，#else 展开 ((void)(x))
- templates.render_pins LOGO 段	ledc 生成 LEDC 四宏 / rgb 生成 RGB 三脚 / none 都- 不生成
- rules.key_io.refs	从 .c 实际用的 KEY_MODE_Rx 映射 + .c 直用的 KEY_x_PIN，不再- 扫 .h 定义体
- Issue.path 格式	"规则id: 字段路径"（如 "key_io.refs: pins.KEY_P_PIN"），断言用 in - w.render() 不用精确匹配
- artifacts.is_artifact	唯一来源，baseline.tree_digest 和 newproject.- copy_skeleton 共用
- uvprojx ledc 源	ledc.c / ledc_mode.c / drv_ledc.c，logo != ledc 时前两个被移除，- drv_ledc.c 保留

## 5. 已完成的验证（不用重做）

- baseline CH04：Keil 编译 0 error 0 warning，Code=39912
- TEST_CLI：编译通过 + 硬件验证（灯带亮、DPI 灯效、MOS 正常）
- TEST_NOCTRL：编译通过 + 硬件验证（灯带亮、MOS 不控）
- TEST_NONE：编译通过 + 硬件验证（灯带不亮、鼠标/按键正常）
- pytest 125 passed
- smoke 三工程全 PASS


## 6. 遗留任务（按优先级）
```
任务 A：rewrite_identity 事务化（中优先）— ✅ 已完成 2026-11-14（128 pytest 全绿 + 真实基线端到端 rollback 验证）
问题：new 的 BLE 名改写（mouse_hw.c / ex2_app_mouse.c）走 _rewrite 直接写文件，不进 FileTransaction。后果：rollback 只能撤销 build_outputs 写的文件，撤销不了 BLE 名/id 改写。

做法：

探测 omcfg/newproject.py的 _rewrite / rewrite_identity / identity_macro_records

探测 omcfg/transaction.py 的 FileTransaction API（有 create / write_text / commit）

改 rewrite_identity 接受可选 tx: FileTransaction 参数，有 tx 就走 tx.write_text，没有保持原行为（向后兼容 test_newproject.py 现有 7 个用例）

cli.cmd_new 里创建 tx，传给 rewrite_identity 和 _apply_outputs

tests/test_newproject.py 加用例：new 后 rollback 能恢复 BLE 名

验证：

python
# 冒烟
python -m omcfg new --name TEST_RB --target _test_gen/TEST_RB --id 0x5555
python -m omcfg rollback --manifest _test_gen/TEST_RB/.omcfg_bak_*/manifest.json
# 检查 mouse_hw.c 的 mouse_name 是否恢复 CH-04 Bt1
python -m pytest
```

```md
任务 B：颜色表参数化（中优先，高风控）
问题：ledc.c 里 dpi_rgb_tab[8][3] 是硬编码，不同板 DPI 灯色不同（492 是黄/紫/青/白，524 改过）。改错灯色不对但能编译，难测。

做法：

探测 E:\M_2026\M_2026_T\492_HTS092\...\ledc.c、516_BM2017\...\ledc.c、524_LJ-V08\...\ledc.c 的 dpi_rgb_tab 差异

设计 project.omcfg 新字段 board.ledc_colors（8×3 数组或前 N 行覆盖）

omcfg/validate.py 加校验（每行 3 个 0-255 整数，最多 8 行）

omcfg/generate/templates.py 加 render_ledc_colors（或扩 render_pins），生成 #define LEDC_COLOR_TAB{...} 到 user_config.h

baseline/sdk/.../ledc.c 的 dpi_rgb_tab 改为 #include "user_config.h" 后读宏，无宏时用默认值（
#ifdef LEDC_COLOR_TAB
）

tests/
 加用例：board.ledc_colors 生成正确、不配置时走默认

风控：改 ledc.c 是 C 代码，改完要 Keil 编译 + 烧录看灯色。一次只改一个板（CH04）验证通过再推广。
```

```c
任务 C：~~LEDC_PIN=P34 诚实化~~ — ✅ 已完成 2026-11-14（软件 + 硬件验证）

真相：原诊断只说对了一半。真正的问题是 **LEDC_PIN / LEDC_CTRL_PIN 两个角色的语义搞反了**，不是「P34 不在 PMU 可选项」。

CH04 硬件事实（用户确认）：
- P05 = WS2812 DIN 数据脚（`PMU_LEDC_SEL_IO_05` 选的就是它）
- P34 = MOS 控制脚（控制灯带接地，开关灯）

旧配置为什么能工作（巧合叠加，不是设计正确）：
- `LEDC_CTRL_PIN=P05`：P05 在 GPIO 表被初始化成 `OUTPUT_PP+HIGH`，PMU 选 IO_05 后数据能出
- `LEDC_PIN=P34`：P34 在 GPIO 表被拉高，MOS 导通
- `LEDC_POWER_SET(x)` 操作的是 P05（数据脚），**是假控制**；真 MOS 靠 GPIO 表初始 HIGH 常开

本次改动：
1. `configs/CH04.omcfg` + `baseline/project.omcfg`：`LEDC_PIN=P05` / `LEDC_CTRL_PIN=P34` 交换
2. `omcfg/pinmap.py`：LEDC 功能约束（LEDC_SEL 只能 P01/P05/P21/P33）从 `LEDC_CTRL_PIN` 挪到 `LEDC_PIN`
3. `omcfg/rules.py`：`led.driver` 规则比对 `PMU_LEDC_SEL_IO_xx` 与 `LEDC_PIN`（原比对 `LEDC_CTRL_PIN` 是错的）
4. `gen --apply` 重生成 baseline/sdk 的 `user_config.h/.c`，更新 `META.json` 三项 sha/size
5. `smoke` 重建三工程，**TEST_CLI DPI 灯效切换正常**（硬件验证通过）

关键教训（下一棒必读）：
- **524 的 `NO_GPIO_TABLE` 不适用于 CH04**。曾照搬 524 的「LEDC_PIN 不配 GPIO，交 LEDC 外设独占」，把 `LEDC_PIN` 加进 `NO_GPIO_TABLE`，导致 P05 不初始化、数据出不去、DPI 灯效全失。**已撤销**。
- 524 的 `LEDC_PIN=P01` 可能是 LEDC 专用 pad；CH04 的 `P05` 是普通 GPIO，必须进 GPIO 表初始化。
- `drv_pmu_ledc_sel` 只设 PMU 寄存器 `PINMUX_SEL` 选输出来源，**不配置 GPIO pad 功能**。

遗留（另开任务，不属于 C）：
- `key_io.c:412` 的开关灯逻辑 `bled_bright_en = !bled_bright_en` 在 baseline 里被注释，CH04 当前无用户可触发的关灯操作。要恢复需单独做。
- `render_sleep` 的 `gpio_dir_in(LEDC_PIN)` / `gpio_set_pd(LEDC_PIN)` 保留（`rules.py` 的 `led.sleep` 规则要求）。

````

```c

任务 D：~~KEY_C0_PIN 缺口~~ — ✅ 已核实无需做（2026-11-14）

真相：原诊断有误，两句话都不成立。

1. baseline 的 key_io.c 已无条件使用 KEY_C0_PIN（59/60/62/73/74 行），并非「457 版不含它」
2. check configs/CH04.omcfg --sdk baseline/sdk 实测 RC=0，0 error 0 warning，不报「未引用」

原因：rules.py 的 model.ROLE_ORDER 已含 KEY_C0_PIN；ROLE_REF_RE = \b(KEY_[A-Z0-9_]+)\b 能匹配；行 227 兜底在现行实现下是死代码。

补充：524 的 key_io.c 与 baseline diff 545 行，含大量「524 项目专用」改动（3 键长按 3s 恢复出厂、中键 500ms + 侧键切灯效、3 次扫描去抖、R0/R1/R2 显式上拉、delayus 3→20）。**不移植到 baseline**——baseline 是 CH04 基线，TEST_CLI 已硬件验证按键正常，移植会改变按键行为、需全套硬件复测。

任务 E：smoke --skip-locked + rmtree 重试（低优先）— ✅ 已完成 2026-11-14（`_locked_files` 近似列锁 + `_rmtree_with_retry` 3 次重试 + `--skip-locked` 记 [SKIP]；4 个新用例，132 pytest 全绿）
问题：Keil 开着工程时 smoke 的 rmtree 报 PermissionError，虽已优雅提示不崩，但三工程无法全重建。

做法：

omcfg/smoke.py 的 run_smoke 加 --skip-locked 参数（或自动跳过）

rmtree 失败重试 3 次（间隔 1s），扛杀毒瞬时锁

精确列出被锁文件而非只报目录
```


## 7. 红线（绝不碰）
```md
不改 E:\M_2026\* 和 E:\history\*——纯只读参考

不用 `open(w)` 写文件——工作台脚本走 `patch` / `patch_batch`；omcfg 工具内部走 `tx.write_text`（`FileTransaction`）。两个语境不混用。

不做结构切换（interface / 单双脚 / LED 极性），一律 PolicyError

不碰 key_io.c 的极性硬编码——只读校验

不改 omcfg/biz_sync.py——旧架构，等统一改造

不改 docs/PLAN-INTERNAL-SDK.md / ROADMAP-LIGHTWEIGHT-CUBEMX.md——历史记录

git 操作由用户手动执行，不默认自动 commit
```

## 8. 交接仪式（第一件事）

读本文件（10 分钟）

跑一遍回归确认现状：
```python
import subprocess, sys, os

env = dict(os.environ)
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"
r = subprocess.run(
    [sys.executable, "-X", "utf8", "-m", "pytest", "-q", "--no-header"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    env=env,
    timeout=600,
    cwd=r"E:\tools\om_pinmux",
)
print(r.stdout[-1500:])
```
```
预期 125 passed

跑一遍 smoke：python -m omcfg smoke（先确认 Keil 没开着 _test_gen 里的工程）

读 docs/HANDOFF-pinmux2.md（如果存在）了解更早的上下文

挑任务：建议 A → D → E → C → B（B 风控高留最后）

遇到设计决策（新字段、新 kind、结构切换），先问用户/上级，不自行决定
```

