# 宏观金机：BD319

- 生成时间: 2026-09-17T19:56:31
- 输出目录: `C:\Users\123mc\Desktop\457_CH04\software\SE71M_0457_CH04_V4_20260829\tools\om_pinmux\synth\BD319`
- LOGO: RGB
- 模式脚: dual

## 禁止事项

- 无整仓金机时不要用 CH04 `port_apply` 整包覆盖 RGB 板（会错误引入 ledc*）。
- USB 字符串 / startup 产品字 / FCC 灯默认不写入（策略默认关）。

## 脚位表（pins）

| 宏 | Pxx |
|----|-----|
| `KEY_R0_PIN` | P26 |
| `KEY_R1_PIN` | P20 |
| `KEY_R2_PIN` | P21 |
| `KEY_B_PIN` | P00 |
| `KEY_P_PIN` | P01 |
| `KEY_DPI_PIN` | P36 |
| `WHEEL_A_PIN` | P24 |
| `WHEEL_B_PIN` | P25 |
| `MODE_24G_PIN` | P27 |
| `MODE_BLE_PIN` | P30 |
| `SENSOR_MOTION_PIN` | P07 |
| `SENSOR_NCS_PIN` | P10 |
| `SENSOR_SCLK_PIN` | P11 |
| `SENSOR_SDIO_PIN` | P12 |
| `LED_MODE_R_PIN` | P04 |
| `LED_MODE_G_PIN` | P05 |
| `LED_MODE_B_PIN` | P06 |
| `LED_R_PIN` | P04 |
| `LED_G_PIN` | P05 |
| `LED_B_PIN` | P06 |
| `USB_5V` | P32 |
| `BAT_CHG_PIN` | P31 |
| `LVD_PIN` | P33 |
| `USB_DN_PIN` | P02 |
| `USB_DP_PIN` | P03 |
| `FLASH_CS_PIN` | P17 |
| `FLASH_SCLK_PIN` | P15 |
| `FLASH_MOSI_PIN` | P16 |
| `FLASH_MISO_PIN` | P14 |

## 原理图

- 目录: `E:\pictures\BD319`
- 原理图索引: E:\pictures\BD319\README.md
- # BD319 原理图截图资料索引
- ## 板型要点（相对 CH04 / KC536 灯带板）
- ## 截图 ↔ 说明文档
- ## 读图注意
- 模块说明: encoder_wheel.md
- 模块说明: key_buttons.md
- 模块说明: logo_rgb_and_ffc.md
- 模块说明: mcu_om6239_main.md
- 模块说明: mcu_peripherals.md
- 模块说明: power_charge_mode.md
- 模块说明: sensor_paw3311.md
- 模块说明: test_and_marks.md

## 下一步

1. om_pinmux 选工程 → 选本板 → 核对脚位/策略
2. 「写入工程」脚位 + 「应用板级包」
3. 可选供体 SDK 拷 RGB 业务文件
4. 体检 → Keil → 冒烟
