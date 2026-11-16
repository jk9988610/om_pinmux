# HANDOFF — pinmux_7 交接文档

> 日期：2026-11-16
> 上一棒：pinmux_6（审批 5 阶段流程）
> 读者：pinmux_8
> 状态：**ROADMAP §0.2 结构性重构（序 1/2/3/4）已完成**。序 1/2/4 实测为空操作（文档说有、实际不存在），序 3 实际删除 `workflow.py` + `policy.py`。序 5（三期补全）未动。下一棒主战场：序 5 + `biz_sync.py` 收敛 `contracts.py`。

---

## 0. 三十秒速览

- 工程根：`E:\tools\om_pinmux`，分支 `fix_old_msg`（`ahead 1` 未 push），`main` 未动
- 基线：**`154 passed`**（非 155，见 §5.1）+ smoke 三形态全 PASS
- 本轮 commit：`0c8c182 refactor(pinmux_7): 删除孤儿模块 workflow.py + policy.py，保留 biz_sync 待收敛`
- 回滚点：tag `before-workflow-policy-delete` / 分支 `backup-before-workflow-policy-delete`（均指向 `7eec1be`）
- 本轮交付：见 §2
- 下一棒任务：§6（序 5 三期补全 + biz_sync 收敛 + push）

---

## 1. 产品定位（不变，全文基于此）

OM6239 配置驱动固件生成器：`.omcfg`（YAML）→ 可编译可烧录 Keil 工程。核心承诺 **0 Error 0 Warning** + **事务回滚** + **配置即真相**。不做 middleware/RTOS/多芯片/PLL 求解器/USB 协议栈配置。详见 HANDOFF_pinmux_5 §1。

---

## 2. 本轮交付（pinmux_7 完成）

### 2.1 序 1（index.html 生成逻辑）——**空操作，文档纠偏**

- HANDOFF_pinmux_5 §6.2 序 1 称"91 KB HTML 是第四份真相" → **实测 `web/index.html` 仅 2.6 KB**，纯视图（header 按钮 + 两个 table 占位 + `<script src="app.js">`），零生成/零校验
- `web/app.js` 39.5 KB：`roleAllowedMap` / `currentAssignments` / `packageRows` 全部来自后端 `pinmap` 返回（grep 证实），`PIN_ROWS` 仅 `renderPinMatrix` 展示布局，不构成第二份真相
- 结论：序 1 无待删项，**91 KB 系旧文档误记**

### 2.2 序 2（金机对照子系统）——**空操作，清 pyc**

- `golden_diff.py` / `synth_golden.py` / `synth/` / `reports/` **源文件与目录全不存在**
- 仅剩 `__pycache__\golden_diff.cpython-312.pyc` / `synth_golden.cpython-312.pyc`，已删
- `docs/GOLDEN-SAMPLE-v1.md` 已 `git mv` 归档至 `docs/archive/`，顶部加历史存档注记
- ⚠️ 命名陷阱：`biz_sync.py` 的 `golden_periph`（外设参考目录，**活业务字段**）≠ `golden_diff`/`synth_golden`（已不存在）。同词不同义，勿误删

### 2.3 序 4（问卷子系统）——**空操作，清 pyc**

- `survey.py` / `survey/` **全不存在**，代码/CLI 零引用
- 仅剩 `__pycache__\survey.cpython-312.pyc`，已删

### 2.4 序 3（供体移植子系统）——**实际删除 workflow.py + policy.py**

原 ROADMAP 称删 `port_apply` + `board_pack` 的 donor/policy。实测：
- `port_apply.py` / `board_pack.py` **早已不存在**（`biz_sync.py` L355 仅一句错误提示文本）
- 实际待删对象是 **`omcfg/workflow.py`（1044 行）+ `omcfg/policy.py`（238 行）** 闭环死链：
  - 无外部 import（`cli.py` / `api.py` 零引用；`omcfg/__init__.py` 不导出；无 importlib 动态引用）
  - 无 CLI 入口（`pyproject.toml [project.scripts]` 仅 `om-pinmux = omcfg.cli:main`）
  - 无 GUI 方法（`api.py` 17 个公开方法无相关）
  - 无测试覆盖（`tests/` 19 文件零 import）
  - 根节点 `workflow.py` 无人引用 → `policy.py` / `biz_sync.py` 连带
- **`omcfg/biz_sync.py` 保留**（孤儿但保留）：`sync_board_contracts` 6 个 action（key_io.h / key_io.c / user_config.c / RTE / logo_ledc）有实测功能，待 pinmux_8 收敛为 `contracts.py`。文件头已加状态标注（`# 状态：…孤儿保留`）

### 2.5 文档勘误

- `docs/HANDOFF_pinmux_5.md`：L15/L221 `155 passed` → `154 passed`；L171 序 3 重写为实际删除内容
- `docs/ROADMAP-LIGHTWEIGHT-CUBEMX.md`：文末追加 §「pinmux_7 勘误（2026-11-16）」，集中列明 6 条过时描述与实测现状

### 2.6 验证

- `pytest`：**154 passed**（删前删后一致，无间接依赖）
- `smoke`：三 PASS（TEST_CLI / TEST_NOCTRL / TEST_NONE），与 `_bak/smoke_before.txt` **逐字一致**
- GUI 目检：`launch.bat` 不白屏、无 `ModuleNotFoundError`、新建→勾「灯带（LEDC）」→准备→生成全流程走通

---

## 3. 主线状态对照

| 阶段 | 目标 | 状态 |
|---|---|---|
| 一期 | 内置 SDK + 命名即建工程 | ✅ |
| 二期 | 引脚配置 + 冲突检测 | ✅ |
| 二期补 | LEDC 接入 + keys PAIR + A+B 技术债 | ✅ |
| **三期** | **外设参数 + 模块连带校验** | **半完成**（schema 已补字段，未实现 `uart_baudrate` / `spi_mode` / `usb_id` / `usb_version`）← **下一棒主战场** |
| §0.2 序 1/2/4 | 删 index.html 生成 / 金机对照 / 问卷 | ✅ 实测空操作收口 |
| §0.2 序 3 | 删供体移植子系统 | ✅ 删 workflow.py + policy.py，biz_sync 保留 |
| §0.2 序 5 | 三期补全 | ❌ 未动 |

---

## 4. 工作台约定（铁律，本轮新增）

沿用 HANDOFF_pinmux_5 §4 全部 8 条，**新增 5 条**：

9. **交接文档的"待办"必须带验证命令 + 实测输出**。序 1/2/4 三连空操作（文档说有、实际不存在）就是因旧文档只写结论不写证据。下一棒若写待办，附 `Get-ChildItem` / `Select-String` 命令与期望输出。
10. **文件编码/换行声明必须实测再依赖**。pinmux_6 批复称"biz_sync 是 LF"与实测相反（原文件纯 CRLF 859/0），导致阶段 C 首轮换行混合。改文件前先跑 `CRLF/LF-only/BOM` 三查。
11. **`git add` 不要混已删 / 已 mv / 仍存在三类路径**。任一路径不存在会让整条命令 fatal 退出，同条其余文件也不 add（本轮 E3 踩过，commit 漏 2 文件后 amend 补）。
12. **orphan 判定看"谁 import 我"，不是"我 import 谁"**。被删模块 import 别人不算问题；被别人 import 才是非孤儿的关键。
13. **时间不是孤儿判据**。`workflow.py` 最后改动仅 11 天前，但无外部 import 仍是孤儿。"最近改动 > 3 个月"判据表述有误，已废弃。

---

## 5. 已知坑与遗留

### 5.1 基线 154 非 155（文档笔误已勘误）

实测 `154 passed` + `154 tests collected`，点阵 72+72+10 自洽。HANDOFF_pinmux_5 记 155 为笔误（原测试数 148→147 记错，非测试被删；`test_schema_board_fields.py` 7 个不变）。**后续以 154 为准**，若看到 155 反而是异常。

### 5.2 `biz_sync.py` 孤儿保留，待 pinmux_8 收敛

当前零外部调用者（唯一消费者 `workflow.py` 已删）。文件头已加状态标注。pinmux_8 收敛为 `contracts.py` 并接入配置驱动路径，或明确废弃。**不要直接删**——6 个 action 有实测功能。

### 5.3 ROADMAP 的"3 个 opt-in 文本补丁"未落地为 `compat.py`

ROADMAP L197 规划 `compat.py`（senscan_12bit/stack_240/usb_tx_flag），**全仓无 `compat.py`**。实测：12BIT/STACK 是 baseline SDK 原生内容（`senscan_reg.h` / `om6239_ac6.sct` / `om6239_gcc.ld`），USB flag 无独立补丁逻辑。**未丢功能**，但规划与现实脱节，记一笔。

### 5.4 颜色表参数化（HANDOFF_pinmux_5 §5.1）——**延迟决策**

HANDOFF_pinmux_4 误报完成，pinmux_5 复核判定延迟。pinmux_7 复核同判：收益低、风险高（改 C 代码需烧录看灯色）、可延迟。**客户触发或三期补全时一并做**。

### 5.5 DPI6/7 硬件不可达（沿用）

`dpi_value_tbl[6..7]=0xFF`，切档循环跳过。触发条件：客户需 8 档 DPI。不属本轮。

### 5.6 未 push

`fix_old_msg` `ahead 1`（`0c8c182` 未推）。pinmux_8 接手时先确认是否 push，或由用户决定。

---

## 6. 下一棒任务（pinmux_8）

### 6.1 先做（收尾，30 分钟）

1. **push `fix_old_msg`**（`ahead 1`），确认 CI/远程状态
2. 读本文件 §0–§3 + §4 新增 5 条铁律 + §5
3. 跑回归：`pytest`（**154**）+ `smoke`（三 PASS），确认基线

### 6.2 主战场：序 5 三期补全（按风险从低到高）

| 序 | 任务 | 工作量 | 风险 | 说明 |
|---|---|---|---|---|
| 1 | `uart_baudrate` 实现 | 中 | 低 | schema 已有 `board.uart_pin`，补 generator + rules |
| 2 | `spi_mode` 实现 | 中 | 中 | 需 Keil 编译验证 |
| 3 | `usb_id` / `usb_version` 实现 | 中 | 中 | 需硬件验证 |
| 4 | **`biz_sync.py` 收敛 `contracts.py`** | 大 | 中 | 6 个 action 抽为 opt-in 配置驱动，或明确废弃 |
| 5 | 颜色表参数化（§5.4） | 大 | 高 | 仅客户触发时做 |

**推荐顺序**：1 → 2 → 3 → 4 →（5 仅客户触发）。每加一个，Keil 编译 + 硬件验证一次。

### 6.3 红线（绝不碰）

- 不改 `inject_ledc_files` / `generate_project` / `apply` 内部逻辑
- 不动 `E:\M_2026\...KC536...` 和 `E:\M_2026\M_2026_T\...CH04...` 原始目录（`gen` 对原始路径会因缺 OMCFG 标记块退出，是正常状态，不要 `init` 进去）
- 不改 `role_catalog.json` / `chip/om6239.json`（除明确业务理由 + 保原格式）
- 不碰 `biz_sync.py` 的 `golden_periph`（活业务字段，与已删 golden_diff 同名不同义）
- 卡住先贴现象 + 已尝试命令，**不要猜**

---

## 7. 常用命令速查

```powershell
# 回归
cd E:\tools\om_pinmux
taskkill /F /IM UV4.exe 2>$null
python -m pytest 2>&1 | Select-String "passed|failed|error"
python -m omcfg smoke 2>&1 | Select-Object -Last 12

# 新建工程
python -m omcfg new --name MY_PROJ --target E:\tmp\newproj\MY_PROJ

# 生成（dry-run / apply）
python -m omcfg gen --sdk <SDK根> --config configs\CH04.omcfg
python -m omcfg gen --sdk <SDK根> --config configs\CH04.omcfg --apply

# GUI
launch.bat

# 本轮回滚（若 pinmux_8 发现删错）
git checkout before-workflow-policy-delete -- omcfg/workflow.py omcfg/policy.py
# 或整体
git reset --hard before-workflow-policy-delete

# 备份（放 _bak/，已 gitignore）
Copy-Item path\to\file "_bak\file.bak-xxx"
```

---

## 8. 交接仪式

- 读 §0–§3（10 分钟）：产品定位 + 本轮交付 + 主线状态

- 读 §4–§5（5 分钟）：新增 5 条铁律 + 已知坑

- 读 §6（5 分钟）：下一棒任务

- 跑回归：pytest（154）+ smoke（三 PASS），确认基线

- 挑任务：从 §6.2 序 1（uart_baudrate）开始

- 卡住：贴现象 + 命令 + 已尝试方案，不猜
