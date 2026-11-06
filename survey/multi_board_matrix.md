# 多板脚位 / 拓扑对照（开板调查用）

生成自工程 `user_config.h` + `main.c`（2026-09-24）。

## 模式 / 配对 / 总线

| 板 | 模式拓扑 | 模式脚 | PAIR | 传感器宏 | LOGO | 灯极性 | first_24g_con | UART_PIN |
|----|----------|--------|------|----------|------|--------|---------------|----------|
| KC536 | single | P26 | P27 | SDIO P12 + SCLK P11 | RGB 模式灯 | active_low | 否 | KEY_R0 |
| A02 | dual | 24G=P32 BLE=P00 | 注释(P34=DPI) | SDIO | RGB | active_low | **是** | KEY_R1 |
| CH04 | dual | 24G=P27 BLE=P26 | P24 + C0=P31 | SDIO | LEDC P34 | active_high (+LED_LOW) | 否 | — |
| BD316 | dual | 24G=P31 BLE=P30 | P34 + FIRE=P26 | **同时有 SDIO 与 MOSI/MISO** | RGB | active_low | **是** | KEY_R0 |
| MW650 | wired | WIRED=P31 | P30 | 4线 NCS/SCLK/MOSI/MISO | LEDC P01 | active_high | 否 | KEY_R2 |
| HTW17 | dual | 24G=P31 BLE=P13 | P10 | SDIO | RGB + LED_LOW | active_low | **是** | KEY_R0 |
| BD319 | dual | 24G=P27 BLE=P30 | 注释(P36=DPI) | 工程 4 线；boards JSON 曾写 SDIO | RGB | active_high | **否** | 曾复用中键，现注释 |

## 按键 / 滚轮（摘要）

| 板 | L/R/M | 侧键/DPI | 滚轮 | mux |
|----|-------|----------|------|-----|
| KC536 | P34/P07/P10 | B=P22 P=P25 DPI=P31 | P21/P20 | IO_20_21 |
| A02 | P23/P36/P22 | B=P31 P=P05 DPI=P34 | P21/P20 | IO_20_21 |
| CH04 | P32/P36/P20 | PAIR/C0 | P00/P01 | IO_00_01 |
| BD316 | P27/P00/P32 | B=P23 P=P22 DPI=P25 | P21/P20 | IO_20_21 |
| MW650 | （见工程） | DPI=P27 PAIR=P30 | P05/P06 | IO_05_06 |
| HTW17 | P26/P20/P21 | B=P27 P=P34 DPI=P30 | P24/P25 | IO_24_25 |
| BD319 | P26/P20/P21 | B=P01 P=P00 DPI=P36 | P24/P25 | IO_24_25 |

## 开板应对原则（从差异归纳）

1. **先问卷后写脚**：不要直接抄邻板 `user_config.h`。
2. **传感器总线与驱动绑定**：3 线 → 只留 `SENSOR_SDIO_PIN` + `drv_senscan`；4 线 → NCS/MOSI/MISO + 对应驱动。
3. **无 PAIR 板**：勾 `first_24g_auto` + BLE `ble_id_ff_auto`；或接受无法手动重配对。
4. **LOGO 分家**：RGB 与 LEDC 策略包互斥。
5. **灯极性单独问**：同是 RGB 也可能 active_high（BD319）或 active_low（KC536/A02）。
6. **UART 复用单独问**：默认建议 `NONE`，需要打印再临时打开。
7. **模式 CHECK 两端同值要警报**（HTW17）。
