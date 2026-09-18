# OM6239 PinMux

**只服务 OM6239**。硬件已定 → 对照**原理图网名** + **DataSheet 封装图**，快速生成 Keil 用的 `user_config` 片段，并做换板常见坑检查。

**唯一支持入口：桌面版**（`launch.py` / `launch.ps1`，Python + WebView2）。

## 换板阶段与工具边界

| 阶段 | 内容 | 本工具 |
|------|------|--------|
| **A** 脚位 | 网名 ↔ Pxx ↔ `user_config` | ✅ 点选 / 生成 / 写入 / **保存板 JSON** |
| **B** 契约 | PAIR / 模式脚 / DPI / 编码器 / **LEDC≠滚轮** | ✅ 同步契约 + 校验硬错误 |
| **C** 业务骨架 | LEDC 或 RGB 包、主循环、编译伴生… | ✅ 体检 + **关注策略 / 板级包** |
| **D** HAL/工程 | `RTE_LEDC`、SEL、PINMUX、`senscan` 12bit… | ✅ 策略补丁 / 供体拷贝 |
| **E** 无线体验 | 改灯用 `Cmd_Idle_Cfg` 等 | ✅ 体检提示 |
| **F** 元数据 | USB 字符串 / FCC / startup 产品字 | 策略默认关，可勾选 |

- **有整仓金机（如 CH04）**：可用 `port_apply` 对齐 `PORT_FOCUS`。  
- **无金机 / RGB 板（如 BD319）**：用 **宏观金机**（`synth_golden`）+ **板级包**（`board_pack`），**不要**对 RGB 板跑 CH04 `port_apply`（会错拷 ledc*）。

## 宏观金机 + 板级包（KC536→BD319）

原理图说明：`E:\pictures\BD319`（与 [`boards/BD319.json`](boards/BD319.json) 网名一致）。可选供体：本机已有 BD319 SDK（仅拷 RGB 业务文件）。

```powershell
cd tools\om_pinmux
# 1) 生成宏观金机 → synth/BD319/
python synth_golden.py --board BD319 --pictures E:\pictures\BD319

# 2) 准备干净 KC536 副本（勿用已改成 CH04 的工程）
#    例如: F:\SE71M_0023_KC536_to_BD319

# 3) dry-run / 应用板级包（可选 --donor 现有 BD319 SDK）
python board_pack.py --target F:\SE71M_0023_KC536_to_BD319 --board BD319 --dry-run
python board_pack.py --target F:\SE71M_0023_KC536_to_BD319 --board BD319 `
  --donor E:\M_2026\486_BD319\software\SE71M_0485_BD319_v1_20260915
```

GUI 流程：选板 **BD319** → 选工程 →（可选）选供体 → **生成宏观金机** → 勾选「关注策略」→ **保存板 JSON** → **写入工程** / **应用板级包** → **宏观对照** / 换板体检 → Keil → 冒烟。

`synth/<板>/` 含：`board_desc.json`、`expected_user_config.h`、`board_features.h`、`policy.json`、`checklist_expect.json`、`MANIFEST.md`。

## 关注策略（可在 UI 勾选）

| 策略 | RGB(BD319) 默认 | LEDC(CH04) 默认 |
|------|-----------------|-----------------|
| pins / biz_sync | 开 | 开 |
| senscan_12bit / usb_tx_flag / rf_callback / stack→0x240 | **开**（跟 KC536 底包；勿改回供体 8BIT/0x280） | 开 |
| senscan_donor | **关**（会盖掉 12BIT） | 关 |
| sensor_type_check / rgb_logo_pack | 开（需供体） | — / 关 |
| ledc_pack | **关** | 开 |
| USB 字符串 / startup / FCC | 关 | 关 |

## 验收闸门

成功 = **脚位/策略对齐** + **Keil 0 Error** + **实机冒烟**（不以全文 `.diff` 判成败）。

有金机 CH04 路径另见下文 `port_apply`；RGB 路径以宏观对照 + 体检为准。

## 有金机一键对齐（CH04 / LEDC）

```powershell
cd tools\om_pinmux
python port_apply.py --target <KC536根> --golden <CH04金机根> --board CH04 --dry-run
python port_apply.py --target <KC536根> --golden <CH04金机根> --board CH04
```

## 启动

```powershell
cd tools\om_pinmux
.\launch.ps1
python launch.py --maximize
python launch.py --project <SDK或mouse_demo或periph路径>
```

依赖：`requirements.txt`（`pywebview`）+ WebView2。失败看 `launch.log`。  
会话：`pinmux_state.json`（已 gitignore）。

## 硬规则（摘要）

- LEDC_SEL ∈ {P01,P05,P21,P33}，不得与 WHEEL_A/B 重叠  
- LOGO=LEDC 才拷 ledc* / `RTE_LEDC=1`；LOGO=RGB 走 `rgb_logo_pack`  
- PINMUX 解锁 `0x5A5A`；无线改灯优先 `Cmd_Idle_Cfg`

## 有限性

- 不能从原理图 PDF 自动读网名  
- 宏观金机不是整棵 SDK 克隆  
- 无供体时 RGB 动画细节可能仅 warn，需人工/供体补齐  

## 导出

`user_config` · `board_features.h` · sleep 模板 · `boards/*.json` · `synth/<板>/`
