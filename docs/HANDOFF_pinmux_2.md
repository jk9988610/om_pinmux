# HANDOFF_pinmux_2 — 线 B（brownfield）交接文档

> 日期：2026-11-14
> 作者：pinmux_1（总工程师）
> 读者：pinmux_2 / 后续接手线 B 的工程师
> 状态：7/8 个 board_patch 策略已完成并验证；ledc 由 pinmux_2 并行
> 命名规范：按统筹拍板统一为 HANDOFF_pinmux_N.md（下划线）

---

## 0. 本文件定位

**这是线 B 的交接文档。线 A（greenfield 配置驱动）的交接见 HANDOFF_pinmux_3.md / HANDOFF_pinmux_4.md。**

两条线并存，边界写死（统筹 2026-11-14 拍板）：

| 维度 | 线 A（greenfield） | 线 B（brownfield） |
|---|---|---|
| 入口 | `omcfg new --name X` | 打开现有 periph 目录 |
| 输入 | baseline + board.yaml | 现有 sdk 状态 |
| 适用 | 全新工程从 0 建 | 复制 KC536 后改板 |
| 不碰 | `project.omcfg` 之外的现有工程 | baseline 生成逻辑 |
| 输出 | 可编译的新工程 | 打了策略补丁的现有工程 |
| 严禁 | 侵入线 B 的 workflow.py | 侵入线 A 的 baseline 生成 |

**共用底层**（读共享、写独占）：`omcfg/transaction.py` / `omcfg/validate.py` / `omcfg/pinmap.py` / `omcfg/rules.py` / `omcfg/templates/ledc/`（六件套 donor）。

`templates/ledc/` 的特殊约束：**读之前算 SHA1，与 HANDOFF 记录的 baseline 归一化 SHA1 对照，不一致就报错停下**——防未来有人往模板里塞「项目专用」改动，把共用资产变成隐性分叉源。

---

## 1. 已完成 7 个 policy 速查

全部 `kind="board_patch"`，全部通过四项目幂等 + 非幂等 + 拒绝三组验证。

| policy id | 功能 | rels |
|---|---|---|
| `project_id` | 工程 ID / 名字 / BLE 名 | `user_config.h` + `startup_om6239.S` + `mouse_hw.c` |
| `sensor` | 传感器引脚 / 方向 / SPI 模式 / DATA_FORMAT | `user_config.h` + `drv_senscan.c` |
| `wheel` | 滚轮 A/B 引脚 + ENCODER 组 | `user_config.h` |
| `switch` | 拨杆单/双脚 + 上下拉 + 极性 | `user_config.h` + `user_config.c` + `key_io.c`（只读） |
| `led` | LED 模式灯引脚 + 极性 | `user_config.h` + `user_config.c` |
| `power` | USB_5V / BAT_CHG / LVD + LVD_CHECK_INDEX | `user_config.h` |
| `keys` | 按键引脚值替换 + 数量一致性 | `user_config.h` + `user_config.c`（只读检查） |

实现位置：
- `omcfg/policy.py` 的 `POLICIES` 前 7 项
- `omcfg/workflow.py` 的 `_validate_*` / `_plan_*` / `_apply_*` 各 7 组，加 `_apply_board_policy` 分发和 `apply_policies` 的 validate 分支

---

## 2. 三段式模板（新 policy 必须照抄）

### 2.1 `_validate_xxx(board)`

~~~python
def _validate_xxx(board):
    """纯校验，不读文件。返回错误列表（空 = 通过）。"""
    errs = []
    x = board.get("xxx") or {}
    # 1) 必填字段检查
    # 2) 格式检查（Pxx / 枚举 / 正则）
    # 3) 唯一性检查（同一字段内不重复）
    # 4) 交叉一致性检查（如 active_level 与 pull 推导是否一致）
    return errs
~~~
### 2.2 `_plan_xxx(board, root)`

~~~python
def _plan_xxx(board, root):
    """返回 [(file_rel, [(pattern, repl, label), ...]), ...]。
    不读文件，pattern 是正则，repl 用 \g<1> 保留前缀。
    """
    x = board["xxx"]
    patches = [
        (r"(#define\s+XXX_PIN\s+)\(P\d+\)", r"\g<1>(%s)" % x["pin"], "XXX_PIN"),
    ]
    return [("projects/mouse_demo/periph/user_config.h", patches)]
~~~
### 2.3 `_apply_xxx(board, root, tx)`

~~~python
def _apply_xxx(board, root, tx):
    """读文件 → 结构一致性检查 → 逐锚点 re.subn → tx.write_text。"""
    path = root / "projects/mouse_demo/periph/user_config.h"
    if not path.is_file():
        raise PolicyError("缺少文件: %s" % path)
    text, enc = _read_text_auto(path)

    # 结构切换检查（interface / 单双脚 / 极性 / bat_chg 增删等）
    # 不一致 → raise PolicyError("... 需人工")

    plan = _plan_xxx(board, root)
    new_text = text
    for file_rel, patches in plan:
        for pattern, repl, label in patches:
            new_text, n = re.subn(pattern, repl, new_text, count=1)
            if n == 0:
                raise PolicyError("%s 锚点未匹配: %s" % (file_rel, label))
    applied = []
    if new_text != text:
        tx.write_text(path, new_text, encoding=enc)
        applied.append("projects/mouse_demo/periph/user_config.h")
    return applied
~~~
### 2.4 注册三步

~~~python
# ① policy.py 的 POLICIES 里加（在 pins_user_config 之前）
(
    Policy(
        id="xxx",
        title="简短标题",
        kind="board_patch",
        default_rgb=True,
        default_ledc=True,
        rels=("projects/mouse_demo/periph/user_config.h",),
    ),
)

# ② workflow.py 的 _apply_board_policy 里加
if pdef.id == "xxx":
    return _apply_xxx(board, root, tx)

# ③ workflow.py 的 apply_policies 的 validate 分支里加
elif pdef.id == "xxx":
    errs = _validate_xxx(board)
~~~
---

## 3. 7 个已完成策略的实现要点

### 3.1 `project_id`

- **hex 公式**：`startup .long = 0x00{id_h 低2位}{id_l 4位}`，如 `id_h=0x070, id_l=0x0038 → 0x00700038`
- **startup 同改**：`iPROJECT_ID_H/L` 改了，`startup_om6239.S` 的 `.long` 必须同步——60.6% 不一致率的来源
- **BLE 名独立字段**：`board.project.ble.names[0]`，默认 = `project.name`，可覆盖
- **已知限制**：`ble.channels=2` 暂不支持，`validate` 拒绝

### 3.2 `sensor`

- **interface 三态**：`4w` / `2w+ncs` / `2w`
- **interface 切换拒绝**：先读文件检查当前宏组合，不一致 `PolicyError("interface 切换需人工")`
- **v2_en 所见即所得**：board 填带括号的就带，裸的就裸。替换正则双捕获
- **data_format 独立字段**：`8bit` / `12bit` / `null`，与 interface 无关，由型号决定

### 3.3 `wheel`

- **A/B 对调表达方向**：495 A=P20/B=P21，524 A=P21/B=P20，同 `IO_20_21`。不需要 `reversed` 字段
- **物理组一致性**：`_validate_wheel` 解析 `IO_XX_YY`，检查 `{a,b} == {PXX,PYY}`

### 3.4 `switch`

- **pull→level 映射**：`PU_30K/PU_150K → low`，`PD_150K → high`。`active_level` 可显式覆盖但必须与 pull 推导一致
- **key_io.c 只读校验**：检查三种写法（`1 == gpio_read` / `0 == gpio_read` / `if (gpio_read)`），不一致拒绝
- **形态切换拒绝**：单脚↔双脚是结构性变更，需人工

### 3.5 `led`

- **极性真相源是 `led_24g_off`**：不是 `led_r_on`（语义不稳定）
- **极性变更拒绝**：涉及 `led_*_on/off`、`mode_led_all_off/on` 及调用点，需人工
- **init_level 数学推导**：`active_level=high → PIN_LOW_LEV`，`low → PIN_HIGH_LEV`
- **v1 范围**：只改 `LED_MODE_R/G/B_PIN` 引脚 + init_level，不改 LOGO / LOW / CD

### 3.6 `power`

- **LVD_CHECK_INDEX 派生**：`LVD_PIN P33 → POF_LVD_PIN_P33`，改一个必须改另一个
- **bat_chg 一致性**：board 是 `null` 但文件有 → 拒绝；反之亦然
- **wake 宏不在 v1 范围**：多行格式敏感，留给 `biz_sync`

### 3.7 `keys`（v1）

- **范围**：只改 `KEY_R0/R1/R2/B/P/DPI_PIN` 引脚值；`gpio_config_table[]` 不动（表第一字段是宏名，值变自动跟随）
- **validate 管 board 内部一致性**：`b/p/dpi` 三者必须全有或全无（`n_opt=0` 放行，`1/2` 拒绝）
- **apply 管 board↔文件一致性**：board 声明的键集合必须等于文件活跃的键集合，缺/多都拒绝
- **语义等价检查**：`gpio_config_table[]` 每个 KEY 行第一字段必须是宏名（不是数字）
- **v1 不支持**：`KEY_C0_PIN`（524 飞线特殊形态，`OUTPUT_PP`）、`KEY_PAIR_PIN`（条件编译）、增删行
---

## 4. 验证脚本模板

**铁律：patch 之后立即验证，脚本第一段必须清缓存。**

~~~python
import sys, re

for mod in ("omcfg.workflow", "omcfg.policy", "omcfg.biz_sync"):
    if mod in sys.modules:
        del sys.modules[mod]
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)
import omcfg.workflow as wf
from pathlib import Path


class FakeTx:
    """只记录 write_text 调用，不写盘。"""

    def __init__(self):
        self.writes = []

    def write_text(self, path, text, encoding="utf-8", newline=None):
        self.writes.append((str(path), text, encoding))


REPOS = {
    "495_V196": r"E:\M_2026\495_V196\software\trunk\SE71M_0495_V196_V1_20260927",
    "512_S205": r"E:\M_2026\512_S205\software\trunk\SE71M_0512_S205_V1_20261017",
    "516_BM2017": r"E:\M_2026\516_BM2017\software\trunk\SE71M_0516_BM2017_V1_20261022",
    "524_LJ-V08": r"E:\M_2026\524_LJ-V08\software\trunk\SE71M_0524_LJ-V08_V1_20261103",
}

# A 段：四项目幂等（board 值 = 当前值时，FakeTx.writes 为空）
# B 段：非幂等改值（用全不同的假 board，验证 old → new，diff 只改目标行）
# C 段：拒绝场景（结构切换/形态切换/极性变更/格式非法/重复值 → PolicyError）
~~~

**断言原则**：
- `must` / `must_not` 只检查 `#define` 行，不全文扫描
- diff 只允许目标行变化
- `FakeTx.writes` 为空 = 幂等
---

## 5. 四项目验证矩阵

| 项目 | 起点 | sensor interface | sensor dir | switch | LED 极性 | power.bat_chg | keys |
|---|---|---|---|---|---|---|---|
| 495_V196 | KC536 Demo | 4w | CLOCK_6 | 双脚 P26/P34 | high | P00 | 6 键 |
| 512_S205 | KC536 Demo | 2w+ncs | CLOCK_9 | 双脚 P23/P31 | low | P01 | 6 键 |
| 516_BM2017 | 成品工程 | 2w | CLOCK_6 | 单脚 P05 | high | P04 | 6 键 |
| 524_LJ-V08 | LJ-A08 已改好 | 2w | CLOCK_0 | 单脚 P23 | high | null | 4 键（含 C0，v1 拒绝） |

**验证结论（7 个 policy 全部 PASS）**：

| policy | 幂等 | 非幂等 | 拒绝 |
|---|---|---|---|
| project_id | 4/4 | 7/7 锚点 | channels=2 |
| sensor | 4/4 | 6/6 场景 | interface 切换 ×2 |
| wheel | 4/4 | 2/2 场景 | A/B 不匹配 / A=B / 格式 / Pxx ×4 |
| switch | 4/4 | 1/1 场景 | 极性变更 / 形态切换 / level 矛盾 / 脚重复 ×4 |
| led | 4/4 | 2/2 场景 | 极性变更 ×2 / mode_rgb 重复 / 非 3 元素 ×4 |
| power | 4/4 | 2/2 场景 | bat_chg 删/加 ×2 / 三脚重复 ×3 |
| keys | 3/4（524 拒绝） | 1/1 场景 | 6 键/1 键部分填/c0/pair/脚重复/文件多宏 ×6 |

**54 项目统计（详见 todo `ecct0u`）**：
- `id_l` vs `startup_id` 不一致率 60.6%（20/33）
- LED 极性 hi 50% / lo 44.1% → 无默认值
- sensor interface 2w 58.8% / 4w 41.2% → 无压倒性主流
---

## 6. 工程纪律踩坑清单

| # | 坑 | 规避 |
|---|---|---|
| 1 | `new='''...'''` 里 `\b` 被解成退格符 `\x08` | **含正则的 `new` 用 `r'''...'''`**；改完扫 `\x08` 数量必须 0 |
| 2 | `import omcfg.workflow` 拿缓存旧版 | **验证脚本第一段 `del sys.modules[...]` 再 import** |
| 3 | `patch` 的 `old` 含 `\x08` 等不可见字符 | 用 `replace_lines` 按行号替换 |
| 4 | `must_not` 全文扫描误伤注释行 | **只查 `#define` 行** |
| 5 | `patch` / `patch_range` 对不存在的文件抛 `FileNotFoundError` | 新文件用 `open(w)`，但**立即 commit**（见第 9 条） |
| 6 | 多处改动不包 `patch_batch` | 多文件/多行改动一律 `with patch_batch():` |
| 7 | `patch` 的 `old` 在文件里出现多次 | 选唯一锚点 |
| 8 | `.c` / `.h` 不用 `py_compile.compile` 校验 | 只有 `.py` 才 compile |
| **9** | **`open(w)` 创建新文档后不 commit，工作区被后续操作冲掉** | **新文档创建后立即 `git add` + `git commit`** |
| **10** | **Windows 下 `git add a \` + 换行 + `b` 的续行写法，`\` 被当路径一部分** | **`git add` 用单行，不用续行符** |
---

## 7. 剩余待办

### 7.1 `policy_ledc`（pinmux_2 并行做）

**事实**：
- 516：`LEDC_PIN=P21, LEDC_CTRL_PIN=P34, count=7`
- 524：`LEDC_PIN=P01, LEDC_CTRL_PIN=P13, count=5`
- `RTE_om6239.h` 里 `RTE_LEDC=1`，`uvprojx` 加源文件
- 引脚冲突：524 的 `KEY_C0 P01→P00`，516 的 P05 拨杆 vs LEDC

**形态**：多文件（4–6 个）+ 冲突检查，`sensor` 的变体。

**注意**：LEDC 语义（P05=DIN 数据脚 / P34=MOS 控制脚）见 `HANDOFF_pinmux_4.md`，不要从旧假设出发。

### 7.2 `check --board` 规则 1–8（pinmux_2 并行做）

8 条规则：
1. `gpio_config_table[]` 宏在 `user_config.h` 有 `#define`
2. `led_*_on` 极性 ↔ init_level 数学一致
3. `WHEEL_IO_SELECT` ↔ `WHEEL_A/B` 物理组匹配
4. `sensor.interface` ↔ 实际脚组合一致
5. `LEDC_PIN`/`LEDC_CTRL_PIN` 不与任何功能脚冲突
6. `PIN_WAKE_UP_MASK` 与 `KEY_PIN_WAKE_UP_EN/DIS` 集合一致
7. `shared_pins` 声明的复用两宏值相等
8. `iPROJECT_ID_H/L` 与 `startup_om6239.S` 字符串一致

### 7.3 光电传感器数据表（todo `m77mvc`）

S203/S205/S301/PAW3311/FCT3075 的 interface / 引脚组合 / dir / DPI 表 / 2V_EN。

### 7.4 524 死代码（归 bringup_check，todo `6v3eea`）

524 `key_io.h` L39-43 引用 `KEY_B_PIN`/`KEY_P_PIN`/`KEY_DPI_PIN`/`KEY_PAIR_PIN`，全部未定义。**不归 om_pinmux**，归 bringup_check 的 `_scan_key_config_v2` 增强。

---

## 8. 红线（不许碰）

1. **不改 `user_config.h/c` 的行数**——只做值替换（`keys` 也一样）
2. **不做结构切换**：interface / 单双脚 / LED 极性 / bat_chg 增删 / 按键增删，一律 `PolicyError`
3. **不碰 `key_io.c` 的极性硬编码**——只读校验
4. **不用 `open(w)` 写受管文件**——一律 `tx.write_text`；新文档用 `open(w)` 后**立即 commit**
5. **不碰线 A 的 baseline 生成逻辑**——`baseline/`、`omcfg/baseline.py`、`omcfg/newproject.py`、`omcfg/initproject.py`
6. **不改 `docs/PLAN-INTERNAL-SDK.md` / `ROADMAP-LIGHTWEIGHT-CUBEMX.md` 内容**——只加页首标记
7. **不动 `E:\M_2026\*` 和 `E:\history\*`**——纯只读参考
8. **不在 om_pinmux 线做死代码扫描**——那是 bringup_check 的领域
---

## 9. 交接仪式（新窗口第一件事）

1. **读本文件**（10 分钟）
2. **读 `omcfg/policy.py` 的 POLICIES 前 7 项 + `omcfg/workflow.py` 的 7 组 `_apply_*`**（30 分钟）
3. **跑一次 `list_policies` 确认 7 个 board_patch 策略都在**：

~~~python
import sys

for m in ("omcfg.workflow", "omcfg.policy"):
    sys.modules.pop(m, None)
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)
import omcfg.workflow as wf

r = wf.list_policies(r"E:\M_2026\495_V196\software\trunk\SE71M_0495_V196_V1_20260927")
for row in r["policies"]:
    print(row["id"], row["kind"], row["available"])
~~~

   预期 7 个 `board_patch` 全 `available=True`。

4. **挑一个待办**：推荐 `policy_ledc`，它是 `sensor` 的变体，能复用 80% 模式
5. **写实现 → 跑验证模板（§4）→ 贴回 → pinmux_1 review**

---

## 10. 525 黄金样本回填（统筹选项 3）

525 是干净的 KC536 副本 + 插件测试载体，**不能直接回填**。

1. `robocopy E:\M_2026\525_E606 E:\tmp\525_golden /E`（临时副本）
2. 在 `E:\tmp\525_golden` 上跑 `apply_policies`
3. 验证通过后把 diff 作为「黄金样本」记录，**不动 525 本身**
4. 临时副本可保留或删除
---

## 11. 并行隔离约定（统筹第 4 节）

pinmux_1 和 pinmux_2 并行工作时，三条硬隔离：

### 隔离 1：`omcfg/policy.py` 分段提交

两个人都会往 `policy.py` 加策略定义，同时改必然冲突。

- **pinmux_1 先改**（`policy_keys`）→ commit → 通知 pinmux_2
- **pinmux_2 后改**（`policy_ledc`）→ commit → 通知 pinmux_1
- 谁后改谁先 `git pull` / 同步，冲突自己解决
- **不两个人同时改同一文件**

### 隔离 2：测试环境各自独立

- pinmux_1 用 `E:\tmp\test_pinmux_1\`（从 495 复制）
- pinmux_2 用 `E:\tmp\test_pinmux_2\`
- **525 本身不动**，留作插件测试载体
- `E:\tmp\525_golden\` 归 pinmux_1

### 隔离 3：`check --board` 与 `apply_policies` 互不等待

- `check --board` 只读，完成即可合入
- `apply_policies` 写操作，完成后再合入
- **唯一交汇点是 `policy.py`**

---

## 12. 与 pinmux_1 的分工

| 角色 | 负责 |
|---|---|
| **pinmux_1** | `apply_policies` 端到端 / 525 黄金样本（选项 3）/ 整体 review |
| **pinmux_2** | `policy_ledc` / `check --board` 规则 1–8 |

**协作方式**：
- pinmux_2 每次改完贴回 `patch` 输出 + 验证结果，pinmux_1 review 后合并
- 遇到设计决策（新字段、新 kind、结构切换），先问 pinmux_1
- 一次只做一个语义单元
- **完成一个语义单元立即 commit**，不攒着

---

## 13. 参考

- `docs/HANDOFF_pinmux_3.md` / `HANDOFF_pinmux_4.md`：线 A 交接（greenfield）
- `docs/PLAN-INTERNAL-SDK.md`：线 A 历史，含「为什么放弃金机/供体/问卷」论证
- `docs/ROADMAP-LIGHTWEIGHT-CUBEMX.md`：线 A 历史，含「资产 vs 包袱」盘点
- todo `ecct0u`：34 项目需求覆盖率基线
- todo `m1eeiw`：7 个 policy 的验证结论 + 并行隔离约定
- todo `e1qb21` / `m77mvc` / `6v3eea` / `6aka58`：剩余待办

---

**本文件由 pinmux_1 于 2026-11-14 写下。按统筹拍板统一命名规范，写完立即 commit，不留工作区未提交状态。**