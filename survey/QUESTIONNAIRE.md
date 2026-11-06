# OM6239 鼠标开板调查表（非业务）

> 目标：换板时先把**脚位 / 拓扑 / 配对触发 / 冲突**填清楚，再让 `om_pinmux` 写 `user_config`。  
> **不覆盖**：RF 协议细节、HID 报告映射（`userdefined_key*.o`）、客户定制灯效时序等业务。

## 怎么用（推荐）

```text
cd E:\tools\om_pinmux
python survey.py blank --out survey\answers_NEWBOARD.json
# 用编辑器按 questions.json / 本文件填写 answers
python survey.py check  --answers survey\answers_NEWBOARD.json
python survey.py export --answers survey\answers_NEWBOARD.json
# 然后 launch.ps1 → 选板 → 校验 → 写入工程
```

也可：`python om_pinmux.py survey blank|check|export ...`

## 填写顺序（对应 sections）

| 段 | 内容 | 容易踩坑 |
|----|------|----------|
| A | 板名、项目号、金机参考 | RGB 板勿整包套 CH04 LEDC |
| B | 模式脚 single / dual / wired | dual 不要再留 `MODE_BLE_24G_PIN` |
| C | 左中右/侧键/DPI/PAIR、UART 复用 | DPI 与 PAIR 同脚必须二选一；UART 复用键会坏 |
| D | 滚轮 A/B + 四选一 mux | 只能 00/01、05/06、20/21、24/25 |
| E | 传感器 3 线 SDIO 或 4 线 SPI | **禁止** SDIO 与 MOSI/MISO 混用 |
| F | LOGO=rgb/ledc、灯极性、LED_LOW | LEDC 不可与滚轮同脚；极性决定 on=set/clear |
| G | USB_5V / BAT_CHG / LVD | LVD 常见 P23/P33 |
| H | 24G/BLE 配对触发 | 无 PAIR → 优先 `first_24g_auto` + `ble_id_ff_auto` |
| I | 冒烟计划 | 键控灯 → HID → 无线配对 |

## 纸质/飞书可复制清单

- [ ] 原理图网名 ↔ Pxx 已对照完（键/模式/轮/传感/灯/电源）
- [ ] 模式拓扑已定：□单脚 □双脚 □有线检测
- [ ] 传感器：□3线SDIO □4线SPI（与驱动一致）
- [ ] LOGO：□RGB □LEDC □无；极性 □高有效 □低有效
- [ ] 独立 PAIR：□有脚 □无（无则勾自动配对策略）
- [ ] UART 是否复用按键：□否 □KEY_R0/R1/R2
- [ ] 滚轮 mux 与脚位一致
- [ ] 无脚冲突（DPI≠PAIR，LEDC≠WHEEL）
- [ ] 金机策略：RGB 不用 CH04 整包；12BIT senscan；stack 0x240
- [ ] 写入后冒烟五项打勾

## 多板对照（摘要）

详见 `survey/multi_board_matrix.md`。

| 板 | 模式 | PAIR | 传感 | LOGO/极性 | first_24g | UART复用 |
|----|------|------|------|-----------|-----------|----------|
| KC536 | single | 有 P27 | SDIO | RGB / 低有效 | 无 | KEY_R0 |
| A02 | dual | 注释(同DPI) | SDIO | RGB / 低有效 | **有** | KEY_R1 |
| CH04 | dual | 有+P C0 | SDIO | **LEDC** / 高有效 | 无 | — |
| BD316 | dual | 有+FIRE | SDIO+4线混杂 | RGB / 低有效 | **有** | KEY_R0 |
| MW650 | wired | 有 | **4线** | LEDC / 高有效 | 无 | KEY_R2 |
| HTW17 | dual | 有 | SDIO | RGB+LOW / 低有效 | **有** | KEY_R0 |
| BD319 | dual | 注释(同DPI) | 工程曾4线/JSON写SDIO | RGB / 高有效 | **无** | 曾 KEY_R2 |

## 工具边界

- `survey`：问卷 → `boards/*.json`
- `validate` / UI 校验：冲突、mux、LEDC
- `apply` / 写入：`user_config` + 可选 `board_features` + key_io/sleep 契约
- `scan_port_checklist`：LEDC/RTE 等移植缺口
- **不自动改**：配对业务状态机以外的 RF/HID 协议实现
