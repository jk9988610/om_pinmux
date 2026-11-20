# BYKC 项目物料统计报告

> 由 `scripts/scan_projects.py` 自动生成于 2026-11-20T11:50:14+08:00。
> 数据源：`E:/M_2026` + `E:/history` firmware source + PcbDoc BOM。
> 时间线主键：项目编号（同一项目多版本取最新 V/date）。

## 1. 覆盖率

- 扫描到固件构建目录：114
- 归一到项目号（每项目取最新构建）：**30**
- 含 PcbDoc BOM 的项目：13

## 2. 关键参数分布（按项目）

| 参数 | 取值分布 | 默认(众数) |
|---|---|---|
| RGB 极性 | {'active_low': 39, 'active_high': 48} | active_high |
| RGB 数量 | {'6': 2, '10': 1, '7': 1, '5': 1} | 6 |
| LEDC 启用率 | 0.233 | - |
| 光电两线/四线 | {'2': 18, '4': 12} | 2 |
| pair/mode 键存在率 | 0.6 | - |

## 3. 项目时间线（按编号）

| 项目号 | 构建 | LEDC | RGB数 | 极性 | 光电线数 | 编码器 A/B | pair键 | BOM 关键物料 |
|---|---|---|---|---|---|---|---|---|
| 23 | SE71M_0023_KC536_V1_20260909 | 否 | - | active_low | 2 | P21/P20 | P27 | - |
| 124 | SE71M_0124_MS11_V5_20251209 | 否 | - | active_low | 2 | P01/P00 | P34 | - |
| 168 | SE71M_0168_MA608_1_20260313 | 否 | - | active_low | 4 | P25/P24 | - | - |
| 177 | SE71M_0177_MC329_V4_20260401 | 否 | - | active_low | 2 | P25/P24 | P34 | - |
| 239 | SE71M_0239_SYX128_S203_V2_20260114 | 否 | - | active_high | 2 | P00/P01 | P30 | - |
| 242 | SE71M_0242_GM2505_V13_20260312_AULA | 否 | - | active_low | 4 | P00/P01 | - | - |
| 253 | SE71M_0253_HTS86V1_8925_203_V1_20260416 | 否 | - | - | 2 | P00/P01 | P30 | - |
| 267 | SE71M_0267_U6_V4_20260425 | 否 | - | active_high | 2 | P06/P05 | P21 | - |
| 274 | SE71M_0274_BD316_V4_20260331 | 否 | - | active_low | 2 | P21/P20 | P34 | - |
| 278 | SE71M_0278_SYX128_3311_V10_20260409_N401_Pro | 否 | - | active_low | 4 | P24/P25 | P34 | - |
| 280 | SE71M_0280_3108_V18_20260506 | 是 | - | active_high | 2 | P21/P20 | - | - |
| 295 | 295-A02 | 否 | - | active_low | 4 | P01/P00 | P34 | - |
| 302 | SE71M_0302_CD2872_V8_20260429 | 否 | - | active_low | 2 | P21/P20 | - | - |
| 323 | SE71M_323-661-3311 | 否 | - | active_high | 4 | P00/P01 | - | 4056H, 6206 2V/N, 6206 3.3V, OM6239 |
| 348 | SE71M_GM01_V1 | 是 | - | active_low | 2 | P21/P20 | - | - |
| 371 | SE71M_0371_HYC_289_3311 | 否 | - | active_high | 4 | P00/P01 | P21 | 4056H, 6206 2V/N, 6206 3.3V, OM6239 |
| 372 | SE71M_0372_M50 | 否 | - | active_low | 4 | P05/P06 | - | LDO-2.0V, LDO-3.3V, OM6239 |
| 382 | SE71M_0382_HYC352_S230-S202-3075_V5_20261102 | 否 | - | active_high | 2 | P00/P01 | P30 | - |
| 391 | 391-JY506_V1-3065 | 否 | - | active_high | 4 | P20/P21 | - | - |
| 393 | 393-M590 | 否 | - | active_high | 4 | P00/P01 | P21 | 4056H, 6206 2V/N, 6206 3.3V, OM6239 |
| 457 | SE71M_0457_CH04_V4_20260829 | 是 | 6 | active_high | 2 | P00/P01 | P24 | 6206 2V/N, OM6239 |
| 483 | SE71M_0483_483_HYC-275QLH_V1_20260915 | 否 | - | active_high | 2 | P00/P01 | P25 | 4056H, 6206 2V/N, 6206 3.3V, OM6239 |
| 489 | SE71M_0489_MW650_V1_20260918 | 是 | 6 | active_high | 4 | P05/P06 | P30 | LDO-2.0V, LDO-3.3V |
| 491 | SE71M_0491_HTW17_V1_20260921 | 否 | - | active_low | 2 | P24/P25 | P10 | LDO-3.3V, OM6239 |
| 492 | SE71M_0492_HTS092_3075_V4_20261013 | 是 | 10 | active_high | 2 | P00/P01 | P25 | 4056H, 6206 3V, OM6239 |
| 495 | SE71M_0495_V196_V1_20260927 | 否 | - | active_high | 4 | P20/P21 | - | - |
| 497 | SE71M_0497_497_HY003_V1_20261009 | 否 | - | active_high | 2 | P20/P21 | P10 | LDO-3.0V, OM6239 |
| 512 | SE71M_0512_S205_V1_20261017 | 否 | - | active_low | 4 | P24/P25 | - | LDO-3.3V, OM6239, S205 |
| 516 | SE71M_0516_BM2017_V1_20261022 | 是 | 7 | active_high | 2 | P00/P01 | - | 3528 ARGB, 4056H, 6206 2V/N, 6206 3V, OM6239 |
| 524 | SE71M_0524_LJ-V08_V1_20261103 | 是 | 5 | active_high | 2 | P21/P20 | - | 4056H, 6206 3.3V |

## 4. 物料型号频次（BOM 提取）

| 类别 | 型号 | 项目数 | 推导默认 |
|---|---|---|---|
| charger | 4056H | 7 | wire/pin=- |
| led_strip | 3528 ARGB | 7 | wire/pin=- |
| sensor | S205 | 1 | wire/pin=4 |

## 5. 关键脚位占用（pins -> 出现项目数）

| 脚 | 占用宏分布 |
|---|---|
| P00 | {'WHEEL_A_PIN': 11, 'BAT_CHG_PIN': 4, 'KEY_R0_PIN': 3, 'KEY_R1_PIN': 3, 'LED_MODE_G_PIN': 2} |
| P01 | {'WHEEL_B_PIN': 11, 'LEDC_PIN': 4, 'USB_5V': 4, 'WHEEL_A_PIN': 2, 'BAT_CHG_PIN': 2} |
| P04 | {'LED_R_PIN': 11, 'LED_MODE_R_PIN': 7, 'LED_MODE_24G_PIN': 5, 'BAT_CHG_PIN': 2, 'LED_MODE_B_PIN': 2} |
| P05 | {'LED_G_PIN': 10, 'LED_MODE_G_PIN': 9, 'LED_MODE_BT1_PIN': 8, 'MODE_24G_PIN': 3, 'LED_MODE_BT0_PIN': 2} |
| P06 | {'LED_B_PIN': 11, 'LED_MODE_B_PIN': 7, 'LED_MODE_BT0_PIN': 7, 'LED_MODE_24G_PIN': 3, 'LED_MODE_G_PIN': 2} |
| P10 | {'SENSOR_NCS_PIN': 12, 'KEY_PAIR_PIN': 2, 'KEY_R2_PIN': 1, 'KEY_B_PIN': 1, 'LED_MODE_R_PIN': 1} |
| P11 | {'SENSOR_SCLK_PIN': 30} |
| P12 | {'SENSOR_SDIO_PIN': 23, 'SENSOR_MOSI_PIN': 11} |
| P24 | {'KEY_R2_PIN': 4, 'KEY_P_PIN': 3, 'LED_MODE_R_PIN': 3, 'LED_MODE_24G_PIN': 3, 'BAT_CHG_PIN': 3} |
| P25 | {'KEY_P_PIN': 3, 'KEY_B_PIN': 3, 'USB_5V': 3, 'WHEEL_B_PIN': 3, 'WHEEL_A_PIN': 2} |
| P36 | {'KEY_R1_PIN': 11, 'LED_MODE_R_PIN': 2, 'LED_MODE_B_PIN': 2, 'LED_MODE_BT0_PIN': 2, 'USB_5V': 1} |

## 6. 已知偏差（需人工确认）

- S205(512) 源码中 P00 定义为 `USB_5V`（`LED_CHG_PIN` 注释掉），用户口述“充电指示灯 P00”，待查原理图确认是否复用；源码极性为低电平点亮（接 VCC），与用户陈述一致。
- 传感器型号是运行时按 PID 探测（sensor_type_check.c），源码枚举列出全部支持型号，并不代表该项目实际焊接型号；wire 线数由宏（NCS/SCLK 是否存在）判断更可靠。
