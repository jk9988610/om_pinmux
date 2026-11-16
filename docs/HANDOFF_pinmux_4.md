先说明边界：我手上 `HANDOFF_pinmux_4.md` 的**原文**只有前面 §0 和 §1 开头（你最早贴给我的那段，§1 smoke 代码块处截断）。§1 之后我从未见过原文。以下是我作为 pinmux_4 在任务 B 完成后的**完整重构终版**——保留原文已有事实，补上本棒执行记录、坑位、验收结论。若原文件 §1 之后还有我没见过的内容，请在编辑器里比对，别盲目覆盖。

---

# HANDOFF — pinmux_4 交接文档

> 日期：2026-11-14
> 上一棒：pinmux_3（LEDC 语义修正 + 事务化 + smoke 抗锁）
> 读者：pinmux_5（若有）/ 项目收尾
> 状态：**任务 B（颜色表参数化）已完成并验收通过**。本棒无遗留任务。

---

## 0. 三十秒速览

- 工程根：`E:\tools\om_pinmux`，git 仓库
- 回归门槛：`python -m pytest` **139 passed** + `python -m omcfg smoke` **三工程全 PASS**
- 硬件已验证：TEST_CLI（灯带亮 + DPI 0–5 档灯色与修改前一致 + MOS 开关灯）、TEST_NOCTRL（灯带亮 + MOS 不控）、TEST_NONE（灯带不亮）
- 本棒唯一任务：**任务 B 颜色表参数化**——已完成（详见 §2）
- 上游文档（按顺序读）：
  1. `docs/HANDOFF_pinmux_3.md` —— 上一棒完整交接
  2. `docs/HANDOFF_pinmux_3_QA.md` —— pinmux_2 对 pinmux_3 的六问答复
  3. 本文件

---

## 1. 开工第一件事：确认现状

```python
import subprocess, sys, os

env = dict(os.environ)
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"

# 1. pytest（以 returncode 为准；汇总行在捕获环境可能不进 stdout）
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
print("RC =", r.returncode)
print(r.stdout[-1500:])
# 预期 RC=0，139 passed（133 原有 + 6 新增）

# 2. smoke（先确认 Keil 没开 _test_gen 里的工程）
r = subprocess.run(
    [sys.executable, "-X", "utf8", "-m", "omcfg", "smoke"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    env=env,
    timeout=600,
    cwd=r"E:\tools\om_pinmux",
)
print("RC =", r.returncode)
print(r.stdout[-1500:])
# 预期三工程全 PASS
```

---

## 2. 任务 B：颜色表参数化（路径 C）执行记录

### 2.1 拍板与范围

上级拍板**路径 C**：修 bug + 落表 + 4 调用点改三元组，**不改 omcfg 生成主干**，本期只做 CH04。

- 516/524 不纳入本期
- 其余 5 个 board（A02/BD316/HTW17/KC536/MW650）不登记 `ledc_colors`
- 未来若有第二个 board 需要精确控色，再评估升级到真参数化（路径 A）

### 2.2 改动文件（3 个主文件 + 2 个配套）

| 文件 | 改动 |
|---|---|
| `omcfg/templates/ledc/ledc.c` | ① 蓝色通道 bug：`Rgb_data[..+2] = green_value` → `blue_value`（:99）② 新增 `dpi_rgb_tab[8][3]`，带参数化入口注释 ③ 4 个调用点改三元组 + `dpi_grade&0x07` 掩码 |
| `baseline/sdk/projects/mouse_demo/periph/ledc.c` | 同上，与模板归一化后逐字节一致（同 commit） |
| `tests/test_ledc_colors.py` | 新增，6 条断言 |
| `baseline/META.json` | 仅同步 `tree_sha256`（`file_count` 仍 207，未动） |
| `omcfg/tools/normalize_sha1.py` | 新增，行尾归一化 SHA1 工具 |

### 2.3 表值（方案 α，保持 CH04 现状 + 补 6/7）

```c
uint8_t const dpi_rgb_tab[8][3] = {
    {240,   0,   0},   /* 0: 红（CH04 现状） */
    {  0, 240,   0},   /* 1: 绿（CH04 现状） */
    {  0,   0, 240},   /* 2: 蓝（CH04 现状） */
    {240,   0, 240},   /* 3: 紫（RED|BLUE 满亮，CH04 现状） */
    {240, 240,   0},   /* 4: 黄（RED|GREEN 满亮，CH04 现状） */
    {  0, 240, 240},   /* 5: 青（GREEN|BLUE 满亮，CH04 现状） */
    {240, 240, 240},   /* 6: 白（新增，防越界） */
    {  0,   0,   0},   /* 7: 黑（新增，保留） */
};
```

> 说明：拍板意见「验收门槛」表曾误把 3/4/5 写成 516 的紫(160,0,160)/青/橙，与「0–5 保持 CH04 现状」自相矛盾。已按"保持现状"执行方案 α，即 0–5 与 TEST_CLI 已验收行为逐位一致。

### 2.4 两个 bug 的因果闭环

- **蓝色通道**：修改前 4 个调用点全传 `240`，`green_value` 与 `blue_value` 写入值相同，bug 被掩盖。修后 0–5 档硬件表现逐档不变，反证修复无副作用；三元组启用精确色（如 `{240,120,0}`）时才真正生效。
- **越界**：`dpi_grade` 取值 0–7（`&0x07`），原表 6 项，索引 6/7 越界读脏内存。现表扩至 8 项 + 访问加 `&0x07`，双层防护。

### 2.5 硬件现象解释

硬件实测「红绿蓝紫黄青循环，无白/灭」是**预期行为**：`dpi_value_tbl[6..7]=0xFF`（无效档），`sensor.c:447` 切档循环跳过 `0xFF`。6/7 槽的"白/灭"代码就绪、硬件未配到。

---

## 3. 坑位提醒（本棒真实踩过）

1. **`Path.read_text()` 没有 `newline` 参数**。要保换行符必须 `open(path, "r", encoding="utf-8", newline="")`。本棒第一次同步两份 `ledc.c` 时差点把 baseline 的 LF 改成 CRLF。
2. **pytest 汇总行在 subprocess 捕获环境下常不进 stdout**。基线判定一律以 `returncode` + 点计数为准，别用 `"139 passed" in stdout` 这种脆断言。
3. **改 `baseline/` 下任何文件后必须同步 `META.json` 的 `tree_sha256`**。`file_count` 只在增删文件时变，且计数必须排除 `artifacts.is_artifact_path`（本棒第一次误数 306，正确值 207）。
4. **`ledc.c` 模板与 baseline 换行符不同源**（模板 CRLF、baseline LF）。同步修改用归一化 SHA1 比对，不要直接比原始 SHA1。
5. **`workbench.py` 不是 Python 解释器**。它需要一个 Python 文件作为 `FILE` 输入，不能 `python workbench.py <script.py>` 这样跑。要手工执行脚本直接 `python <script.py>`。
6. **`patch_range` 的 `start`/`end` 是「行内容字符串」不是行号**；且必须是**唯一单行锚点**，不能给多行。
7. **拍板表格可能自相矛盾**。本棒拍板意见的「验收门槛」表与「建议」段对 3/4/5 档颜色定义不一致，执行前必须逐条比对探测结果，不能照表直抄。

---

## 4. 验收结论

| 项 | 结果 |
|---|---|
| 两份 `ledc.c` SHA1(norm) | `7374c4c51c38…` **一致** |
| 换行符风格 | 保持（TPL=CRLF、BASE=LF） |
| `baseline/META.json` | `verify_meta = []` |
| pytest | **RC=0，139 passed**（133 + 6 新增） |
| smoke | **三工程全 PASS** |
| `_test_gen` 三工程抽查 | 表8x3 / 蓝修复 / 掩码 **三列全 True** |
| 硬件 TEST_CLI 0–5 | 红/绿/蓝/紫/黄/青，**与修改前一致** |
| 硬件 TEST_NOCTRL / TEST_NONE | 灯带亮 / 不亮，行为不变 |

---

## 5. 协调项 2：ledc.c 模板与 baseline 同源验证

- 原始 SHA1（不一致，仅换行符差异）
  - 模板     `omcfg/templates/ledc/ledc.c`                    = `0efdb7e07117...`（CRLF）
  - baseline `baseline/sdk/projects/mouse_demo/periph/ledc.c` = `7374c4c51c38...`（LF）

- 差异类别：**仅换行符**
  - 归一化规则：CRLF→LF、孤立 CR→LF；**不删注释、不压缩空白、不展开宏**
  - 归一化后两份文件**逐字节相等**（脚本同时校验 SHA1 与 bytes，排除碰撞）

- 归一化脚本：`omcfg/tools/normalize_sha1.py`
  - 用法：`python omcfg/tools/normalize_sha1.py <file_a> <file_b>`
  - 退出码 0 = 归一化后逐字节相等

- 归一化后 SHA1：`7374c4c51c38...`（两份相等）
  - 与 `_test_gen` 三工程生成物、baseline 原始 SHA1 相同
  - 说明：生成链路输出 LF，与 baseline 同源；模板为 CRLF，属平台差异

- 复现命令

```bash
python omcfg/tools/normalize_sha1.py \
  omcfg/templates/ledc/ledc.c \
  baseline/sdk/projects/mouse_demo/periph/ledc.c
```

- 第三人不看对话即可复现：上述命令输出 `归一化后逐字节相等 : True` 即闭环。

---

## 6. 遗留待办（均不属本棒范围，记录在案）

| 项 | 现状 | 触发条件 |
|---|---|---|
| DPI6/7 硬件不可达 | `dpi_value_tbl[6..7]=0xFF`（无效档），切档循环跳过 | 客户需要 8 档 DPI 时，另开任务扩展 `sensor_dpi_ini` |
| DPI7 颜色语义不一致 | 代码 `{0,0,0}`，`flash_process.c:82` 期望 `{240,63,127}` | 与上一条一并处理 |
| `dpi_color_tab[]` 死代码 | 保留未删（与 516/524 一致） | 下一棒顺手删 |
| flash 表注释笔误 | `flash_process.c:79` 注"橙"实为黄；`:82` 注"黄"实为偏粉橙 | 下次动 `flash_process.c` 时顺手改注释 |
| 换行符双轨 | TPL=CRLF、BASE=LF，本次保持未统一 | 未来任何人改这两份文件，必须用 `newline=""` 读写 |

---

**任务 B 完成，本棒收工。**