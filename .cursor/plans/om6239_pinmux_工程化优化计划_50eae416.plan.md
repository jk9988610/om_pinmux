---
name: OM6239 PinMux 工程化优化计划
overview: 在已完成 Git 初始化的基础上，分三阶段将 OM6239 PinMux 从可用脚本工具逐步升级为可验证、可回滚、可维护、可自动化集成的工程化工具链。优先保障对 SDK 的写入安全与规则回归，再进行架构与接口统一，最后改善交互、性能与运维诊断能力。
todos:
  - id: p1-foundation
    content: 第一阶段：建立工程治理、校验与测试基础设施
    status: pending
  - id: p1-safe-write
    content: 第一阶段：实现补丁结果验证及写入事务/回滚机制
    status: pending
    dependencies:
      - p1-foundation
  - id: p2-architecture
    content: 第二阶段：拆分核心架构并统一 service 层
    status: pending
    dependencies:
      - p1-safe-write
  - id: p2-interfaces
    content: 第二阶段：统一 CLI、报告和 Keil XML 工程处理
    status: pending
    dependencies:
      - p2-architecture
  - id: p3-ux-security
    content: 第三阶段：完善前端安全、依赖交付和异步体验
    status: pending
    dependencies:
      - p2-interfaces
  - id: p3-observability
    content: 第三阶段：完善缓存、日志、诊断与发布治理
    status: pending
    dependencies:
      - p3-ux-security
isProject: true
phases:
  - name: 第一阶段：安全底座与回归保障
    todos:
      - id: p1-foundation
        content: 第一阶段：建立工程治理、校验与测试基础设施
        status: pending
      - id: p1-safe-write
        content: 第一阶段：实现补丁结果验证及写入事务/回滚机制
        status: pending
        dependencies:
          - p1-foundation
  - name: 第二阶段：架构与接口统一
    todos:
      - id: p2-architecture
        content: 第二阶段：拆分核心架构并统一 service 层
        status: pending
        dependencies:
          - p1-safe-write
      - id: p2-interfaces
        content: 第二阶段：统一 CLI、报告和 Keil XML 工程处理
        status: pending
        dependencies:
          - p2-architecture
  - name: 第三阶段：体验、性能与运维治理
    todos:
      - id: p3-ux-security
        content: 第三阶段：完善前端安全、依赖交付和异步体验
        status: pending
        dependencies:
          - p2-interfaces
      - id: p3-observability
        content: 第三阶段：完善缓存、日志、诊断与发布治理
        status: pending
        dependencies:
          - p3-ux-security
---

# OM6239 PinMux 工程化优化计划

## 目标

在不改变现有 OM6239 换板核心业务能力的前提下，优先降低工程写入风险，并逐步提升可测试性、可维护性、可审计性与交付稳定性。

---

## 第一阶段：安全底座与回归保障

### 1.1 工程治理与基础质量门禁

**目标**：将已初始化的 Git 仓库补全为可追溯、可重复验证的 Python 工程。

- 增加 `.gitignore`，忽略运行时会话、日志、缓存、虚拟环境、编译缓存和可再生产物。
  - 至少覆盖：`__pycache__/`、`*.py[cod]`、`.pytest_cache/`、`.venv/`、`pinmux_state.json`、`launch.log`。
  - 明确 `reports/` 与 `synth/` 的版本控制策略：保留基线还是仅保留生成器与源板描述。
- 引入 `pyproject.toml`，统一：
  - Python 支持版本；
  - 运行依赖与开发依赖；
  - pytest、ruff、black 等工具配置；
  - 项目版本号。
- 建立 CI（依照实际托管平台选择 GitHub Actions、GitLab CI 或内网 CI）：
  - Python 语法编译检查；
  - 静态检查；
  - 单元测试；
  - 板描述 schema/业务规则验证；
  - synth 生成结果的快照或一致性验证。
- 在报告中写入工具版本、Git commit（若可用）和执行时间。

**验收标准**：干净环境中可完成依赖安装、静态检查、测试与板描述校验；运行产物不会被误提交。

### 1.2 板描述与芯片描述的结构化校验

**目标**：在写工程前阻止错误的板配置进入执行流程。

- 为 `boards/*.json` 建立版本化 JSON Schema，例如 `schemas/board-desc-v2.schema.json`。
- 对 `chip/om6239.json`、策略 JSON 和 synth 产物建立基础结构校验。
- 补充业务交叉校验：
  - `logoType` 与 `BOARD_LOGO_LEDC` / `BOARD_LOGO_RGB` 一致；
  - USB 固定为 P02/P03；
  - 滚轮必须为芯片定义的合法 ENCODER 对；
  - LEDC SEL 不与滚轮冲突；
  - GPIO 不得使用未封装或保留脚；
  - 同一 GPIO 不得被独占角色重复占用；
  - LVD 脚与 `LVD_CHECK_INDEX` 对应；
  - 单/双模式脚定义一致。
- 在 GUI 加载、CLI 执行 `synth`、`board_pack`、`port_apply` 前复用同一验证服务。
- 新增独立命令：`validate-board` 或统一 CLI 下的 `validate --board <name>`。

**验收标准**：非法或矛盾的 board JSON 会在任何写入前返回字段级错误和修复建议。

### 1.3 测试基线与 SDK Fixture

**目标**：让现有换板经验规则具备回归保障。

- 建立 `tests/` 和最小脱敏 SDK fixture。
- 优先覆盖：
  - SDK/periph 定位；
  - user_config 标记块的生成、替换和幂等性；
  - 板描述校验；
  - LEDC SEL 与滚轮冲突；
  - `biz_sync` 中 key/sleep/mode 契约改写；
  - senscan、stack、rf callback、USB flag 等补丁；
  - `uvprojx` 文件项插入幂等性；
  - `synth_golden` 输出快照；
  - `board_pack` / `port_apply` 的 dry-run 与 apply 基础路径。
- 每条高风险规则至少覆盖：成功修改、已符合、未匹配、匹配多处、重复执行。

**验收标准**：规则变更会由测试明确发现行为回归；关键函数不再仅靠手工 SDK 验证。

### 1.4 可验证补丁与写入事务/回滚

**目标**：消除“部分写入”“规则未命中但显示成功”的风险。

- 定义统一 `PatchResult` / `ActionResult`：
  - `changed`、`already_compliant`、`skipped`、`failed`；
  - 匹配次数；
  - 修改前后 hash；
  - 验证结果；
  - 人类可读 detail。
- 改造 `biz_sync.py`、`board_pack.py` 的正则补丁：
  - 对应规则声明预期匹配次数；
  - 0 次或多次匹配时停止并报错，不能以 `ok=True` 掩盖；
  - 写后执行针对性验证。
- 所有修改先生成完整 plan/manifest：源文件、目标文件、动作、原始 hash、目标 hash、备份位置。
- 引入 staging 预检查流程：
  1. 定位并验证目标 SDK；
  2. 校验 board/strategy；
  3. 生成所有变更；
  4. 在 staging 中验证；
  5. 创建备份并提交；
  6. 任意失败自动回滚。
- 提供 `--rollback <manifest>`，并在 GUI 中可展示最近一次操作及回滚入口。

**验收标准**：中途异常后 SDK 可自动恢复原状；报告能逐文件说明实际修改、跳过或失败原因。

---

## 第二阶段：架构与接口统一

### 2.1 分离 UI 宿主、领域逻辑与文件系统操作

**目标**：降低 `launch.py` 和跨脚本耦合，便于测试和复用。

建议逐步形成以下结构：

```text
om_pinmux/
  app.py                 # WebView 启动和依赖装配
  ui_api.py              # 前端 API
  windows_window.py      # Windows ctypes/WebView 窗口控制
  session.py             # 会话状态
  project_locator.py     # SDK/periph 定位
  user_config_writer.py  # 标记块写入
  services/
    validation.py
    patching.py
    board_pack.py
    port_apply.py
    reporting.py
  domain/
    board.py
    chip.py
    policy.py
```

- GUI 和 CLI 调用同一 service/domain 层。
- 将 Windows/pywebview 依赖限制在 UI 宿主层。
- 将文件读写封装成可替换接口，以便测试中使用临时目录或 fake filesystem。
- 用具体异常和统一错误码替换宽泛 `except Exception`；完整 traceback 写日志，前端显示可操作的简明提示。

**验收标准**：领域逻辑可不启动 WebView 而单独测试；`launch.py` 只负责宿主与 API 装配。

### 2.2 统一 CLI、退出码与 JSON 报告

**目标**：让 GUI、人工命令和自动化系统获得同样的能力和结果格式。

- 建立顶级 CLI，例如：

```powershell
om-pinmux validate --board BD319 --target <sdk> --json
om-pinmux synth --board BD319 --pictures <dir> --json
om-pinmux apply --board BD319 --target <sdk> --donor <sdk> --dry-run --json
om-pinmux compare --golden <sdk> --target <sdk> --json
om-pinmux rollback --manifest <path> --json
```

- 保留可读文本报告，但每个命令均输出完整机器可读 JSON 报告。
- 统一退出码：
  - `0`：成功；
  - `1`：校验或体检失败；
  - `2`：参数、路径或环境错误；
  - `3`：补丁或写入失败；
  - `4`：已自动回滚或需要人工恢复。
- 不再截断结构化输出；大报告写文件，并在控制台输出路径与摘要。

**验收标准**：任意主流程可由 CLI 自动化执行，GUI 调用同一服务并展示同一份结果语义。

### 2.3 使用 XML 解析替代 `.uvprojx` 文本正则插入

**目标**：稳定、幂等地维护 Keil 工程文件。

- 用 `xml.etree.ElementTree` 或经批准的 XML 库解析 `.uvprojx`。
- 以 group、文件名、相对路径三者验证文件项是否存在。
- 确保 `ledc.c` / `ledc_mode.c` 加入 `periph`，`drv_ledc.c` 加入 `driver`。
- 处理重复节点、缺失 group、解析失败、编码和换行问题。
- 写入后重新解析验证，结果纳入 `ActionResult`。

**验收标准**：面对不同空格、换行或节点排序的 Keil 工程，均可安全识别并执行幂等更新。

---

## 第三阶段：体验、性能与运维治理

### 3.1 前端安全与 DOM 渲染整理

**目标**：降低本地 WebView 注入风险，提高前端渲染稳定性。

- 清查 `index.html` 中动态 `innerHTML`。
- 对后端消息、板描述字段、路径等不可信字符串使用 `textContent` / `createTextNode`。
- 必须生成 HTML 的场景统一使用 escape 工具或改为 DOM API。
- 前端错误展示采用统一组件，不直接拼接后端 message。

**验收标准**：板描述、路径或错误消息中的特殊字符不会被作为 HTML 解释。

### 3.2 依赖与交付方式可复现化

**目标**：避免 GUI 启动时隐式安装依赖带来的环境不确定性。

- 移除默认运行时 `pip install pywebview` 行为。
- 启动时检查依赖与 WebView2 环境，并给出明确的安装/修复命令。
- 如保留自动安装，仅通过显式 `--install-deps` 触发。
- 基于 `pyproject.toml` 提供开发环境初始化脚本。
- 根据现场部署需求评估 venv、离线 wheel 包或 PyInstaller 便携打包。

**验收标准**：离线、权限受限、多 Python 版本环境中，失败原因和修复方法明确且可重复。

### 3.3 大型 SDK 扫描的缓存与异步执行

**目标**：改善 GUI 在扫描、哈希和对比时的响应速度。

- 对源码引用扫描、关注文件 hash、SDK 定位建立 mtime/size 驱动的缓存。
- 复用单次操作中的 SDK 目录索引、文件 hash 和验证结果。
- 将耗时扫描放到后台线程/任务队列；GUI 显示进度、取消和结果摘要。
- 记录扫描文件数、耗时、缓存命中率，便于性能回归。

**验收标准**：重复执行扫描显著更快；长操作不会阻塞窗口交互。

### 3.4 日志、诊断包与发布治理

**目标**：让现场问题可审计、可复现、可安全外发。

- 使用标准 `logging` 替代零散 `print` 与手工日志写入。
- 每次 synth/apply/compare 分配 operation ID。
- JSON 报告统一记录：
  - 工具版本与 Git commit；
  - 板描述和策略 hash；
  - 目标 SDK 识别信息；
  - 文件修改前后 hash；
  - 备份、manifest 与回滚结果；
  - error/warn/info 分类。
- 支持脱敏诊断包（路径、产品标识可选脱敏），便于反馈工具问题。
- 建立版本号、CHANGELOG 和发布流程。

**验收标准**：一次现场操作可以仅凭报告、诊断包和对应工具版本完成复盘与问题定位。

---

## 推荐里程碑

1. **M1：安全可控**：完成 1.1~1.4；所有工程写入具备前置校验、明确结果和回滚能力。
2. **M2：可维护可集成**：完成 2.1~2.3；GUI/CLI 共用核心服务，Keil 工程操作稳定。
3. **M3：可交付可演进**：完成 3.1~3.4；具备稳定交付、性能可观测和现场诊断能力。

## 实施原则

- 每个阶段先补测试，再改造对应实现；每一项改造保持旧 CLI/GUI 流程可用或提供迁移说明。
- 任何自动写 SDK 的操作必须默认先验证、可 dry-run、可审计、可回滚。
- 不以全文 diff 作为唯一验收标准，持续保持“板契约/策略对齐 + Keil 0 Error + 实机冒烟”的领域验收闸门。