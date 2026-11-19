# OM6239 配置工具 · UI 设计规划（导向性重构）

> 版本：v1（2026-11-18）
> 定位：**设计规划 + 可评审原型**，不含生产代码改动。配套高保真原型：`docs/ui-prototype.html`（单文件、可点击走通全流程）。
> 触发问题：用户反馈「当前的 UI 设计导向性很弱」。

---

## 0. 一页速览

| 项 | 结论 |
|---|---|
| 病根 | 界面是**「工具箱」**不是**「流程」**：三条互斥路径（打开已有工程 / 按角色配脚 / 空白起步）同时平铺在首屏，用户自己拼顺序；没有「我在哪、还差什么、下一步点哪」。 |
| 药方 | 收敛成**单一任务流**：首屏先选路径 → 进入工作台（常驻步骤条 + 唯一主 CTA + 右侧工程健康卡）→ 一次只显示当前步。 |
| 后端 | **零改动**。`omcfg/api.py` 现有 25 个方法已覆盖全部步骤，本规划 P0/P1 纯前端重组。 |
| 附带解决 | ① 用户上轮追问的「需求组 / 约束栏 / 脚位图是什么关系」→ 做成显式说明条 + 三视图联动；② 用户愿景「可拔插插件」→ 从折叠深处提到独立步骤的一等公民卡片。 |
| 首个里程碑 | P0：启动页 + 工作台骨架 + 步骤条 + 健康卡 + 底部操作栏，把 `web/app.js` 里三个互相覆盖的 IIFE 收敛为「状态机 + 步骤视图」。 |

---

## 1. 现状诊断：导向性弱在哪里（带代码证据）

现有界面由 `web/index.html`（59 行骨架）+ `web/app.js`（1091 行，**三个独立 IIFE 动态插入 DOM**）+ `web/style.css`（125 行）组成。逐条定位：

| # | 症状 | 代码证据 | 对用户的实际后果 |
|---|---|---|---|
| 1 | **三条互斥流程同时平铺** | `index.html:10-19` 顶部 8 个按钮（打开/检查/保存引脚/预览/应用…）是「已有工程」链路；`app.js:366-371` 插 `roles-bar`（按角色配引脚）；`app.js:848-859` 又插「空白起步（向导）」；`index.html:35-56` 主区还有两张只读表 | 首屏 **10+ 个可点元素、无主次**。用户不知道该先点「打开」还是「空白起步」——两条路径互斥却并列 |
| 2 | **没有「我在哪 / 下一步」** | `app.js:889-895` 的 ①②③④⑤ 是 5 个并排 `<button>`，仅靠 `disabled` 表达状态；无步骤条、无当前步高亮、无完成度 | 用户不知道哪步做完了、为什么 ④ 是灰的；做完 ③ 该回到向导还是直接应用，全靠 README 文字说明 |
| 3 | **首屏是「报告查看器」不是「配置器」** | `index.html:36-55`：`封装脚位`表 / `片内保留脚`表 / `未分配功能` / `问题` / `diff` 五个区块 | 第一眼看到的是**只读数据**而非行动召唤；视觉重心在「脚号/脚名/当前功能」表格，不在「开始配置」 |
| 4 | **状态反馈五处分散** | `#status`(`index.html:20`)、`#roles-hint`(`app.js:370`)、`#roles-save-hint`(`app.js:383`)、`#bw-msg`(`app.js:898`)、`#bw-progress`(`app.js:897`) | 没有一处统一回答「这个工程现在能不能生成、还差几个必需脚」；用户要自己跨五个角落拼信息 |
| 5 | **概念关系没讲清** | 需求组 `app.js:512`、约束栏 `app.js:597`（按 `allowed_pins` 数量分档）、脚位图 `app.js:703` 是三个割裂区块，中间**没有一句话** | 上一轮对话里用户专门问过「约束栏的内容是需求组的什么关系」——说明 UI 自己没回答这个问题 |
| 6 | **视觉无层级 / 无设计系统** | 仅 `#apply` 是 `.primary`(`index.html:18`)；三个面板全靠 `style.cssText` 内联（`app.js:368,375,864` 等 30+ 处），色值散落 | 破坏性写盘（应用/保存）与只读（检查）长得一样；无法统一改主题，改一处要翻遍 JS 字符串 |
| 7 | **冷启动无引导** | `index.html:20` 只有一行灰字「输入 SDK 路径后回车…」 | 没有欢迎页、没有路径选择、没有最近工程；新用户打开即面对一张空表 |
| 8 | **插件入口藏在折叠里** | LEDC 勾选框要**展开**需求组卡片才见到（`app.js:545-562`），且无「启用会带来什么」说明 | 用户明确愿景「就在需求组勾选 LEDC，约束栏给参数 + 移植文件」；现在这个一等能力被埋在二级折叠里 |
| 9 | **面板互相覆盖** | `roles-panel` 与 `bw-panel` 都 `insertBefore(panel, status.nextSibling)`（`app.js:386,901`），可同时展开 | 两个大面板叠在 status 下方，滚动混乱，进一步稀释焦点 |
| 10 | **术语未翻译** | 角色显示 `LEDC_PIN` / `KEY_R0_PIN`，板型显示 `ENCODER_PINMUX_SEL_IO_20_21`（`app.js:933`） | 宏名是工程视角，不是任务视角；配脚时用户得在脑子里做一次映射 |

**一句话**：现在 UI 把「所有能力」一次性摊开，把「排序、判断完成度、决定下一步」的认知负担全留给用户。导向性 = 替用户承担这三项。

---

## 2. 设计目标（可度量）

| 编号 | 目标 | 验收口径 |
|---|---|---|
| G1 | 首屏 3 秒内知道「我要做什么」 | 冷启动只出现 **2 张路径卡 + 1 个主 CTA**，可点元素 ≤ 5 |
| G2 | 任意时刻知道「我在哪 / 还差什么 / 下一步点哪」 | 常驻步骤条（当前步高亮）+ 完成度 + **唯一**「下一步」按钮，且按钮副标题写明「下一步会做什么」 |
| G3 | 禁用态必须解释 | 任何 `disabled` 都附带原因（如「还差 3 个必需脚」），不允许无声置灰 |
| G4 | 概念自解释 | 三视图工作区顶部一句话说明关系；选中任一视图，另两处联动高亮 |
| G5 | 插件是一等公民 | 独立步骤的卡片：开关 + 价值说明 + **影响预告**（注入几个文件 / 新增几个角色 / 自动腾哪只脚）+ 启用后健康卡立刻变化 |
| G6 | 状态唯一来源 | 一个「工程健康卡」聚合：完成度、已配/总数、缺必需、冲突、插件、可生成 |
| G7 | 破坏性操作分级 | 写盘（应用）是唯一强调色，且被「预览 diff」gate 住；写后给 manifest 与回滚提示 |
| G8 | 不牺牲既有能力 | 所有现有 API 行为不变；`pytest` / `ruff` / `node --check` / `eslint` 不退化 |

---

## 3. 核心方案：从「工具箱」到「单一任务流」

### 3.1 首屏：先选路径（解决症状 1、7）

```
┌─────────────────────────────────────────────────────────────┐
│  OM6239 板级配置器      [? 帮助]  [◐ 主题]                    │
│  一份 .omcfg 管住引脚、板型与功能插件，生成即可编译的 SDK 工程   │
│                                                             │
│   ┌───────────────────────┐   ┌───────────────────────┐    │
│   │  ＋  从空白新建         │   │  ⌂  打开已有工程       │    │
│   │  CubeMX 式：选功能 →   │   │  检查 / 微调脚位 →     │    │
│   │  配引脚 → 生成         │   │  预览 → 应用           │    │
│   │  [ 开始新建  → ]       │   │  [ 选择 SDK  → ]       │    │
│   │  ★ 推荐                │   │                        │    │
│   └───────────────────────┘   └───────────────────────┘    │
│   最近工程：KC536X2 · E:\work\…        OM_PIN_02 · …         │
└─────────────────────────────────────────────────────────────┘
```

两条路径互斥，选完才进入工作台。用户不再需要自己判断「该用哪套按钮」。

### 3.2 工作台四区框架（解决症状 2、3、4、6、9）

| 区 | 位置 | 内容 | 常驻 |
|---|---|---|---|
| ① 上下文头 | 顶 | 项目名 · SDK 路径（可切换）· 已保存/未保存标记 · 帮助 | ✅ |
| ② 步骤条 + 导航 | 左 | 步骤列表（完成✓ / 当前● / 未达○ + 可回点）· 当前路径标识 | ✅ |
| ③ 工作区 | 中 | **只渲染当前一步**的内容；顶部一句「这一步在做什么」 | 按步 |
| ④ 工程健康卡 | 右 | 完成度环 · 已配 N/M 脚 · 缺必需 K · 冲突 C · 插件清单 · 「可生成：是/否」· 上下文帮助 | ✅ |
| ⑤ 操作栏 | 底 | 「← 上一步」｜「保存草稿」｜**「下一步：〈动作名〉 →」**（唯一主 CTA，副标题写下一步做什么） | ✅ |

关键：**③ 区一次只出现一个步骤**，三个旧 IIFE 面板不再是「同时可展开的浮层」，而是被状态机调度的步骤视图。

### 3.3 步骤条与 gate（解决症状 2、3）

- 状态：`done`（勾、可回点）/ `current`（高亮）/ `locked`（灰，但 hover 显示「还需 …」）。
- **Gate 规则**（前置条件不满足则「下一步」禁用并写明原因，而非静默置灰）：

| 步骤 | 放行条件 | 不满足时的提示 |
|---|---|---|
| 项目身份 → 板型 | 项目名/输出目录/项目号合法 | 「请填项目名与输出目录」 |
| 板型 → 插件 | 板型枚举已选 | — |
| 插件 → 配引脚 | 无（插件可跳过） | — |
| 配引脚 → 校验 | 必需脚齐全、无冲突 | 「还差 3 个必需脚：WHEEL_A/B、SENSOR_MOTION」 |
| 校验 → 预览 | `validate_errors == 0` | 「有 2 条错误，请先修复」 |
| 预览 → 应用 | 已生成 diff | 「请先预览 diff」 |
| 应用 | 二次确认 | 显示「将写入 N 个文件，可用 manifest 回滚」 |

- 允许**回退**到任意已完成步；不允许跳过 gate。
- 「一键按推荐配置」降级为配引脚步骤里的**一个可选动作**（不是主线），因为用户明确说过「我不想按推荐配置，新工程就是要区别于 SDK」。

### 3.4 两条流程的步骤定义

**路径 A · 从空白新建（主推，6 步）**

| 步 | 名称 | 用户做什么 | 后端 API |
|---|---|---|---|
| 1 | 项目身份 | 名 / 客户 / 项目号 / 版本 / 输出目录 | `blank_new` |
| 2 | 板型选项 | 模式脚 / 灯效 / 滚轮（人话标签 + 宏名次要显示） | `blank_options` → `blank_set_board` |
| 3 | 功能插件 | 勾选插件（LEDC），看影响预告 | `plugin_status` → `plugin_toggle` |
| 4 | 引脚分配 | 三视图联动配脚 | `plugin_status` / `blank_save` / `blank_fill_recommended`(可选) |
| 5 | 校验与预览 | 看问题清单 + diff | `blank_status` / `check` / `preview` |
| 6 | 生成应用 | 写盘 + 结果 / 回滚入口 | `blank_apply` / `open_folder` |

**路径 B · 打开已有工程（4 步）**

| 步 | 名称 | 后端 API |
|---|---|---|
| 1 | 选择并打开 SDK | `choose_folder` / `load` / `initialize` / `initialize_derived` |
| 2 | 检查与调整（同一套三视图工作区） | `check` / `role_capabilities` / `plugin_status` / `save_pinmap` / `plugin_toggle` |
| 3 | 预览 diff | `preview` |
| 4 | 应用 | `apply` |

> 两条路径**共用**「三视图配脚工作区」与「预览 / 应用」组件，只是步骤编排与保存 API 不同（草稿态 `blank_save` vs 严格 `save_pinmap`）。现有代码里 `window.__omBlankMode` 的分支正好是这两种语义，收敛到状态机的一处配置即可。

---

## 4. 信息架构

```
启动页 Start
├─ 路径 A：从空白新建 ──────────┐
└─ 路径 B：打开已有工程 ────────┤
                               ▼
                    工作台 Workbench（四区框架）
                    ├─ 步骤条 Stepper ── 调度 ──┐
                    ├─ 工程健康卡 HealthCard ←──┤ 状态订阅
                    ├─ 操作栏 ActionBar ────────┤
                    └─ 步骤视图 StageView ──────┘
                         ├─ IdentityView      项目身份
                         ├─ BoardView         板型 + 插件卡
                         ├─ PinWorkspaceView  三视图配脚
                         │    ├─ DemandGroups   需求组（按功能 grouping）
                         │    ├─ ConstraintList 约束栏（按 allowed_pins 分档）
                         │    └─ PinMatrix      脚位图（32 格物理位置）
                         ├─ ValidateView      问题清单（可「去修复」跳回配脚）
                         ├─ PreviewView       文件清单 + diff
                         └─ ApplyView         结果 / manifest / 回滚
```

---

## 5. 关键界面规格

### 5.1 工程健康卡（导向锚点，常驻右栏）

```
┌──────────────────────────┐
│ 工程健康            ● 草稿 │
│      ╭──────╮             │
│      │ 18/28│  64%        │   ← 完成度环
│      ╰──────╯             │
│  已配脚      18 / 28      │
│  缺必需      3  ⚠         │   ← 点击跳转到对应角色
│  冲突        0  ✓         │
│  校验错误    0  ✓         │
│  ─────────────────────    │
│  插件  灯带 ✓ 已启用       │
│  ─────────────────────    │
│  可生成：否                │
│  ⓘ 补齐 3 个必需脚后即可  │
│    进入「校验与预览」       │   ← 这就是「下一步」的文字版
└──────────────────────────┘
```

一次 API 聚合即可拿到：`blank_status`（assigned/total/missing/conflicts/complete）+ `plugin_status`（enabled）+ `check`（errors/warnings）。**P0 可并行调这三个方法，不必改后端。**

### 5.2 步骤 3 · 功能插件卡（把用户愿景做成显性入口）

```
┌─────────────────────────────────────────────────────────┐
│ 功能插件    在 KC536 底座上按需扩展，随时可拔除             │
├─────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────┐ │
│ │ [ ✓ ]  灯带 LEDC              已启用                 │ │
│ │        可驱动 WS2812 灯带，替代/共存于 RGB 灯效        │ │
│ │        启用后将：                                    │ │
│ │          · 注入 4 个文件（ledc.c/.h、ledc_mode.c/.h） │ │
│ │          · 新增 2 个可配角色（DIN / CTRL）            │ │
│ │          · 自动腾让 LED_MODE_B：P01 → P36             │ │
│ │          · board.logo 设为 ledc                      │ │
│ │        ⚠ 会改动现有脚位   [ 查看契约 ]                │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

- 影响预告直接来自 `omcfg/data/plugins.json`（`files` / `roles` / `auto_reassign` / `board_effect`），**数据驱动，不写死在 UI**。
- 勾选后：立刻刷新健康卡（+2 个待配角色）+ 步骤 4 角色表出现 LEDC 两项；取消则对称撤销。
- 与用户原话对齐：「不在其他地方勾选，就在需求组勾选」→ 需求组卡片本身也保留同一开关（两处共享同一状态），但独立步骤提供完整的解释与预告。

### 5.3 步骤 4 · 三视图工作区（回答用户上轮的问题）

**顶部固定说明条**（这是本次规划里对「概念没讲清」的直接修复）：

> **需求组、约束栏、脚位图是同一批角色的三种视图**：需求组按「我要什么功能」分组，约束栏按「芯片允许这个功能落在几只脚上」分档，脚位图按「物理位置」摆放。选中其一，另外两处会同步高亮。

| 视图 | 数据源 | 组织方式 | 交互 |
|---|---|---|---|
| 需求组 | `options.json` → `demand_groups`（`ledc.strip` / `wheel` / `mode.switch` / `key.main`） | 按功能分组，显示 `x/y 已配` + 插件开关 | 点组 → 中栏筛出该组角色 → 右栏高亮其合法脚 |
| 约束栏 | `role_capabilities().roles[*].allowed_pins` 数量 | 硬约束(1) / 窄(≤4) / 中(≤10) / 宽(<24) / 无(≥24) | 点角色 → 右栏只高亮该角色合法脚 + 显示「推荐 Pxx / 必需」 |
| 脚位图 | `pinmap.package` 32 脚 `P00..P37` | 4×8 物理矩阵 | 选中角色后，绿=可配 / 深绿=已占 / 黄=冲突 / 灰=不合法；点格即分配，三处计数即时更新 |

**联动契约**：`selectedRole` 是唯一交互状态；`selectedGroup` 只是「筛选器」。这句话要写进 UI，也要写进代码注释——它同时回答了「约束栏是需求组的什么关系」：**两者是同一集合上的正交分类，不是父子、不是包含**。

**上下文条**：`当前正在配：滚轮 A（WHEEL_A_PIN）· 合法脚 8 个 · 推荐 P24 · 与 WHEEL_B 必须成对`。让用户永远知道自己在干什么。

### 5.4 步骤 5 · 校验

- 问题按 `error` / `warning` 分组卡片，每条带 **「去修复 →」** 按钮，点击跳回步骤 4 并自动选中相关角色（把「问题列表」从终点变成导航）。
- 空状态：`0 error · 0 warning · 可进入预览`，直接把「下一步」点亮。

### 5.5 步骤 6 · 预览与应用

- 预览：文件清单（N 个将变更）+ 语法着色 diff + 顶部明确「**这一步不写盘**」。
- 应用：确认摘要 → 写盘 → 成功页（写入 N 文件 · manifest 路径 · 回滚命令 · 打开目录 · 提示用 Keil 编译验证）。破坏性操作全程只有这一处用强调色。

---

## 6. 状态机

```
START ──选路径A──▶ WIZ_NEW ──▶ STEP[1..6] ──▶ APPLYING ──▶ DONE
      ──选路径B──▶ WIZ_OPEN ──▶ STEP[1..4] ──▶ APPLYING ──▶ DONE
                      ▲                          │
                      └──── 回退 / 去修复 ←──────┘
                      ┌──── gate 阻断 ──────────┐
                      ▼                          │
                 GATE_BLOCKED（显示原因，停留当前步）
```

前端状态对象（建议收敛到一处，替换三个 IIFE 各自的局部变量）：

```js
const state = {
  route: "new" | "open",
  step: 1,
  sdk: null,
  blankMode: false,
  health: { assigned, total, missing, conflicts, errors, complete },
  plugins: { enabled: [], available: [] },
  selectedRole: null,
  selectedGroup: null,
  dirty: false,
};
```

**单一渲染入口** `render()` 依据 `route + step` 决定挂载哪个 StageView，避免现在三个 IIFE 各自 `insertBefore` 抢 DOM 位置（`app.js:386,901`）的问题。

---

## 7. 视觉规范

### 7.1 Design Tokens（把散落的内联色值收回 `style.css`）

```css
:root{
  --bg:#f5f6f8; --surface:#fff; --surface-2:#fafbfc;
  --line:#dfe2e8; --line-strong:#c9d2df;
  --text:#1f2430; --text-2:#5b6472; --text-3:#8a93a2;
  --brand:#2f6fed; --brand-weak:#eaf1ff;
  --ok:#2e7d32; --ok-weak:#e8f5e9;
  --warn:#a15c00; --warn-weak:#fff4e0;
  --err:#c62828;  --err-weak:#fdecec;
  --radius:6px; --radius-sm:4px;
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-6:24px;
  --fs-display:20px; --fs-h1:16px; --fs-h2:14px; --fs-body:13px; --fs-cap:11px;
}
[data-theme="dark"]{ /* 同名字段反相，P2 落地 */ }
```

### 7.2 层级规则

- **唯一强调色**：只给「下一步」与「应用」；其余动作一律中性按钮。
- 破坏性写盘再加一层：实心强调 + 二次确认条（不用原生 `confirm`）。
- 状态色语义固定：绿=已完成/可生成，琥珀=待处理/警告，红=错误/阻断，蓝=信息/当前步。
- 脚位矩阵颜色沿用现有语义（绿=可配、深绿=已占、黄=冲突、灰=不合法），**不要另造一套**。

### 7.3 组件清单

| 组件 | 用途 | 对应现状 |
|---|---|---|
| `PathCard` | 启动页路径选择 | 新增 |
| `Stepper` | 左栏步骤导航 | 替代 `bw-*` 五个并排按钮 |
| `HealthCard` | 右栏完成度与阻断原因 | 聚合 `#status` + `#bw-progress` + `#roles-hint` |
| `ActionBar` | 底部上一步/保存/下一步 | 替代分散的 `bw-*` / `save-roles` |
| `PluginCard` | 插件开关 + 影响预告 | 升级需求组里的裸 checkbox |
| `DemandGroupCard` | 需求组 | 现有 `renderDemandGroups` |
| `ConstraintRow` | 约束栏角色行 | 现有 `makeRoleButton` |
| `PinMatrix` / `PinCell` | 32 脚矩阵 | 现有 `renderPinMatrix` |
| `IssueCard` | 问题 + 去修复 | 现有 `renderIssues` |
| `DiffViewer` | 文件清单 + diff | 现有 `#diff` |
| `ContextHelp` | 「这一步在做什么」 | 新增 |

### 7.4 硬要求

- **删除所有 `style.cssText` 内联样式**，统一走 class（`web/app.js` 现有 30+ 处）。这是主题化与可维护性的前提。
- 术语人话化：主标签用 `display_name`（如「滚轮 A」「灯带数据」），宏名降级为次级灰字 / 可复制。
- 不引入构建工具、不引入前端框架：仍是 `index.html + style.css + app.js`（可拆 `wizard.js` / `views.js`，用原生 ESM 或 IIFE 分文件），pywebview 直接加载。

---

## 8. 交互原则（写进代码评审清单）

1. **每屏唯一主 CTA**，且文案是动词 + 下一步对象（「下一步：配置引脚 →」），不是「确定」。
2. **禁用必给理由**：`disabled` 与提示文案成对出现，禁止静默置灰。
3. **即时反馈**：任何脚位/插件改动后，健康卡与三处计数同帧更新（本地先算，再异步保存）。
4. **渐进披露**：一次只显示当前步；高级项（宏名、契约 JSON、回滚命令）折叠。
5. **危险操作 gate + 可回滚**：预览是应用的必经前置；写后必给 manifest 与回滚入口。
6. **不用原生 `confirm` / `alert`**（现有 `app.js:274,291,342,486,739,742,1066` 等处），改应用内确认条 / toast，减少打断感。
7. **空状态即引导**：空白工程不显示空表，而显示「0/28 已配 → 下一步：选板型」。
8. **不把生成逻辑搬回 JS**：沿用 `docs/ROADMAP-LIGHTWEIGHT-CUBEMX.md` §7-4 硬规则，前端只提交 JSON、展示后端返回的 issues/diff。

---

## 9. 与现有后端的映射（关键结论：P0/P1 不改 Python）

`omcfg/api.py` 现有 25 个方法已完整覆盖向导所需，**本规划是纯前端重组**，风险低：

| UI 动作 | 现有 API | 备注 |
|---|---|---|
| 启动页 · 最近工程 | 前端 `localStorage` | 已有 `omcfg.sdk` / `om_pinmux.blankwiz` 键 |
| A1 项目身份 | `blank_new(name,target,customer,version,id_low)` | |
| A2 板型 | `blank_options()` → `blank_set_board(sdk,updates)` | 返回 `board_enums` / `board_defaults` |
| A3 插件 | `plugin_status(sdk)` / `plugin_toggle(sdk,id,enable)` | `available_plugins()` 已随 `blank_options` 返回 |
| A4 配脚 | `plugin_status(sdk)`(过滤角色) / `role_capabilities()` / `blank_save(sdk,assignments)` | 可选 `blank_fill_recommended` |
| A4 三视图 | `load(sdk)` → `pinmap.package` / `role_capabilities().roles` / `demand_groups` | 已具备 |
| A5 校验预览 | `blank_status(sdk)` / `check(sdk)` / `preview(sdk)` | `blank_status` 已含 `missing_detail` / `validate_errors` |
| A6 应用 | `blank_apply(sdk)` / `open_folder(path)` | |
| B1 打开 | `choose_folder` / `load` / `initialize` / `initialize_derived` | `needs_init` 分支现成 |
| B2 调整 | `check` / `save_pinmap` / `plugin_toggle` | 严格模式 |
| B3/B4 | `preview` / `apply` | |

**唯一可选的后端优化（P3，非必需）**：新增 `wizard_state(sdk)` 把 `blank_status + plugin_status + check` 聚合成一次调用，减少健康卡的往返；不做也不影响功能。

**明确不动**：`omcfg/generate/*`、`validate.py`、`rules.py`、`plugins.py`、`baseline/*`、`tests/*`、CLI。生成链路与已验证的「Keil 0 Error / 0 Warning」结论不受影响。

---

## 10. 分阶段实施路线

| 阶段 | 范围 | 交付 | 验收 |
|---|---|---|---|
| **P0 · 导向骨架** | 启动页 + 工作台四区 + Stepper + HealthCard + ActionBar + 状态机；三个 IIFE 收敛为「状态机 + 步骤视图」；CSS token 化、清除 `style.cssText` | `web/index.html` / `style.css` / `app.js` 重构，1 个 commit | 冷启动 ≤5 个可点元素；任意时刻可见「下一步」；两条路径都能走到底并产出 Keil 0/0 工程；`pytest` 180 passed、`ruff`、`node --check`、`eslint` 不退化 |
| **P1 · 概念与联动** | 三视图说明条 + 联动高亮 + 上下文条；插件独立步骤（影响预告、开关双向同步）；问题「去修复」跳转 | 前端 1 个 commit | 选组→中栏筛选→右栏高亮三者一致；插件勾选后健康卡 +2 角色、取消后归零；jsdom 端到端覆盖 |
| **P2 · 体验打磨** | 应用内确认/toast 替代原生弹窗、diff 语法着色、成功页/manifest/回滚、最近工程、快捷键、暗色主题、空状态引导 | 前端 1 个 commit | 无原生 `confirm/alert` 残留；暗色对比度可读；完整链路回归 |
| **P3 · 可选** | `wizard_state` 聚合 API；步骤级埋点/耗时；帮助文档内联 | 前后端各 1 commit | 健康卡单次往返；无功能回归 |

**每个阶段单独 commit**，保证可回退到上一版 UI；任何阶段都不得改动 Python 生成链路。

---

## 11. 风险与硬边界

| 风险 | 缓解 |
|---|---|
| 三个 IIFE 收敛时丢功能（草稿态保存、插件联动、向导五步） | 逐项对照 §9 API 映射表做等价迁移；保留 `window.__omBlankMode` 语义分支；先写 jsdom 回归用例再重构 |
| 前端又长出第二套校验/生成逻辑 | CI 加 grep 门禁：`web/*.js` 不得出现 `#define` / 模板字符串拼接（沿用 ROADMAP §7-4） |
| 插件启用涉及文件与 Keil 登记 | UI 只调 `plugin_toggle`，文件事务仍由 `plugins.py` + `FileTransaction` 负责，前端不碰文件系统 |
| 草稿态被完整性校验误拦 | 继续走 `blank_save`（不卡必需脚），完整性只体现在 `health.complete`，不阻断保存 |
| 改版后用户找不到旧入口 | 路径 B 完整保留「打开已有工程」全部能力；帮助面板附旧版操作对照表 |
| 主题化引入回归 | token 只做同值替换，P0 不改任何视觉结果，仅把内联样式搬进 CSS |

---

## 12. 文件落点

| 文件 | 动作 |
|---|---|
| `docs/UI-DESIGN-PLAN.md` | 本规划（新增） |
| `docs/ui-prototype.html` | 高保真可交互原型（新增，独立文件，不参与 pywebview 打包） |
| `web/index.html` | P0 重写骨架（启动页 + 四区容器） |
| `web/style.css` | P0 token 化 + 组件样式 |
| `web/app.js` | P0 收敛为状态机 + 步骤视图（可拆 `views.js`） |
| `README.md` | P2 更新「图形界面」章节为向导式说明 |
| `omcfg/*` | **不改** |

---

## 13. P0 实施记录（2026-11-18）

P0 已按本规划落地：`web/index.html` 改为启动页 + 四区工作台骨架，`web/style.css` 建立设计 token 与组件 class（清除全部 `style.cssText`），`web/app.js` 把原来三个独立 IIFE 收敛为**单一状态机 + 步骤视图**。两条路径、gate、《需求组/约束栏/脚位图》联动、插件影响预告、健康卡、预览与应用成功页均已接通真实 `Api`。

**与原规划的一处偏差（需记录）**：§9 原写「后端零改动」。实施中发现插件卡的「影响预告」需要 `files` / `unlock_roles` / `auto_reassign`，而 `plugins.available_plugins()` 与 `plugins.status()` 原本只返回静态 6 个字段。为守住「新增插件只改 `plugins.json`、不改 UI」的数据驱动原则，在这两个**只读**方法里补齐了契约字段；没有改动 `enable/disable`、生成链路、校验、CLI 或任何测试语义。这是唯一一处后端改动。

**验证记录**：
- jsdom + mock Api：26 项断言全绿，0 error（两条路径走到底、gate 原因、插件增减、三视图联动、成功页）。
- jsdom + **真实 Api 只读桥接**（基线 SDK）：10 项全绿，读到 58 角色 / 4 需求组 / 3 张可见需求组卡（LEDC 未启用时隐藏）/ 32 脚矩阵，无 console error。
- `pytest` 全绿（8 项 CH04 取证用例按既定 skip）；`ruff` All passed；`node --check` OK；`eslint` 0 error（no-unused-vars 警告来自内联 onclick 调用，属预期）。

## 14. P1 实施记录（2026-11-19）

P0 已吸收了规划中大部分 P1 内容（概念说明条、三视图联动、上下文条、插件影响预告），本次补齐两处真实缺口：

1. **需求组内插件开关**：未启用插件的需求组不再隐藏，卡片上直接提供勾选入口；与步骤 3 的插件卡共用 `togglePlugin(id)`，双向同步。启用后自动选中该需求组，解锁角色立刻可见；取消后角色与配额归零。插件展示改为数据驱动，不再硬编码 `ledc`。
2. **问题「去修复」真正定位**：缺必需项跳回配脚步骤、选中该角色并按 `suggested_pin` 高亮目标脚；冲突项从后端 `conflicts` 中提取脚号定位；校验错误尝试从 `issues` 中取关联角色。脚位图新增 `.focus` 脉冲高亮。

同时清除 `app.js` 中最后一批内联 `style=`，健康卡插件行改为遍历契约清单（新增插件无需改 UI）。

**验证**：jsdom 20 项断言全绿（含双向同步、组→角色→脚位图联动、去修复定位与高亮、无内联样式）。

## 15. P2 实施记录（2026-11-19）

1. **应用内确认**：写盘改为两段式——底部主 CTA 只弹出确认条，必须再点「确认写入」才真正调用 `blank_apply/apply`；主按钮此时变「等待确认…」并禁用，确认条可「取消」，Esc 也可取消。原生 `confirm/alert` 已全部移除。
2. **最近工程**：`om_pinmux.recent` 保留最多 5 条（兼容旧 `omcfg.sdk` 单条键），启动页与「打开工程」页共用 chip 列表，支持单条移除。
3. **快捷键**：`Alt+←/→` 切步、`Ctrl/⌘+S` 保存脚位、`Ctrl/⌘+P` 预览、`Esc` 关弹窗 / 取消写入、`?` 帮助；写入帮助弹窗。
4. **diff 着色**：统一 diff 之上做轻量 C 语法着色（预处理指令 / 字符串 / 注释 / 脚号 / 数字），逐段转义后再拼 HTML，保留 `+/-` 行底色。

**过程中修掉两个真 bug**：inline `onclick` 路径未转义反斜杠，导致最近工程「打开 / 移除」参数变成 `E:workMyMouse`；移除后旧 `omcfg.sdk` 键又把该条回填。两处均已修复并纳入回归。

**验证**：jsdom 35 项断言全绿（两段式写盘、最近工程增删、快捷键、diff 着色、P1 全部链路）；真实 Api 只读桥接 14 项全绿（58 角色 / 4 需求组 / 32 脚矩阵 / 插件契约字段）。

## 16. 真实端到端验收与顺序 bug 修复（2026-11-19）

用真实 `Api`（非 mock）驱动前端 `app.js` 走完「从空白新建」6 步：blank_new →
blank_set_board → plugin_toggle(ledc) → blank_fill_recommended → preview → 两段式
blank_apply，产出工程 `om_pinmux_e2e/OM_E2E_20261119`，Keil UV4 `-r` 全量重编
**0 Error / 0 Warning**（Code=38900 RO=1772 RW=172 ZI=2252）。

**过程中抓到一个真 bug**：GUI 默认顺序是先勾插件、后一键推荐，而此前的测试顺序
相反（先补齐再勾插件），从未覆盖。该顺序下：

1. 草稿阶段没有脚，`enable()` 的 `auto_reassign`（LED_MODE_B P01→P36）无角色可腾；
2. 一键推荐按 KC536 基线把 `LED_MODE_B` 填回 P01、`LED_G` 填回 P05，与 LEDC 冲突；
3. `validate.required_roles` 只看 `board.logo=ledc → LEDC_PIN`，漏掉契约的
   `keep_roles`（led.c 无条件引用的 LED_R/G/B）和 `pair_with` 的 `LEDC_CTRL_PIN`
   （ledc.c 无条件引用）→ 生成头缺 4 个宏 → Keil **16 error**。

修复（数据驱动，未来插件通用）：

- `validate._required_roles` 消费已启用插件契约的 `required_roles` / `keep_roles` /
  `pair_with`，不再依赖 `board.logo` 硬编码。
- `plugins.reconcile_pins()`：配脚后重新执行 `auto_reassign`，并为契约必需但未配/
  冲突的角色按 `allowed_pins` 找空闲脚（幂等）。
- `blank_save(..., reconcile=True)`：仅一键推荐写盘时触发协调，草稿手存不受影响。
- 回归用例 `test_enable_then_fill_recommended_is_buildable` 固化该顺序。

修复后关键宏：`LED_MODE_B=P36`、`LEDC_PIN=P01`、`LEDC_CTRL_PIN=P33`、
`LED_R/G/B=P04/P05/P06`，blank_status `complete=true / 无缺脚 / 无冲突 / 0 校验错误`。

## 17. 端到端回归固化（2026-11-19）

§16 的验收与顺序 bug 修复已固化为项目资产，不再依赖一次性临时脚本：

- `tests/test_e2e_pipeline.py`：纯真实 `Api`（不依赖 pywebview / jsdom / node_modules），
  覆盖三种操作顺序——① 先勾插件后一键推荐（GUI 默认）、② 先推荐后插件并手工配
  DIN/CTRL、③ 取消插件对称撤销；断言生成头 `BUILD_REQUIRED_MACROS` 齐全、完整性、
  无冲突、文件注入/清理正确。第 4 个用例在有 Keil UV4 时（`OMCFG_UV4` 可覆盖路径）
  全量重编并断言 `0 Error / 0 Warning`，无 UV4 自动跳过，不把外部 exe 当硬依赖。
- `scripts/e2e_check.py`：一键命令行验收，从零产出工程、逐阶段打印结果、生成头与
  完整性断言、可选 Keil 编译报告。用于人工复现与 CI。

该回归是「新增插件必须写全契约（keep_roles / pair_with / required_roles）」的守门人：
任何插件若在源码里硬引用了未声明的角色，端到端用例会立刻在编译阶段暴露。

## 附：原型说明

`docs/ui-prototype.html` 为自包含单文件（无外部依赖、无 pywebview），用 mock 数据演示：

- 启动页两条路径选择；
- 工作台四区框架、常驻步骤条与工程健康卡；
- 底部唯一主 CTA（带「下一步做什么」副标题）与 gate 阻断提示；
- 板型选项 + 插件卡（勾选后健康卡与角色表即时变化、影响预告）；
- 需求组 / 约束栏 / 脚位图三视图联动与概念说明条；
- 校验（去修复跳转）、预览 diff、应用成功页；
- 深浅主题切换、可回退任意已完成步骤。

原型用于**评审交互与信息架构**，不是生产代码；生产落地按 §10 的 P0 开始。
