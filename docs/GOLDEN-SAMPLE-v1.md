# GOLDEN-SAMPLE-v1 — 线 B 能力边界样本

> 日期：2026-11-14
> 作者：pinmux_1
> 起点：525_E606（纯净 KC536 副本，iPROJECT_ID_L=0x0023，iPROJECT_NAME=KC536）
> 目标：495_V196 配置（4w / 双脚 / high 极性 / 6 键）
> 执行：apply_policies(["project_id", "sensor", "wheel", "switch", "led", "power", "keys"])
> 结果：3 成功 + 4 拒绝

---

## 1. 背景

黄金样本测试的用途：证明线 B（brownfield 换板策略）的能力边界。不是「展示能做什么」，而是「明确不能做什么、为什么拒绝」。

- 起点：`E:\M_2026\525_E606\software\trunk\SE71M_0525_E606_V1_20261106` 的副本 `E:\tmp\525_golden`
- 起点状态：纯净 KC536（`iPROJECT_ID_L=0x0023` / `iPROJECT_NAME="KC536"` / 无 ledc.c）
- 目标配置：495_V196（sensor 4w / switch 双脚 / LED 高有效 / keys 6 键无 PAIR）
- 执行工具：`omcfg.workflow.apply_policies`（7 个 board_patch 策略）

---

## 2. 成功的 3 个 policy

| policy | applied 文件 | 改动 |
|---|---|---|
| `project_id` | `user_config.h` + `startup_om6239.S` + `mouse_hw.c` | ID 0x0023→0x0495 / 名称 KC536→V196 / 客户 BYC→App / BLE 名 BT5.1Mouse→V196 / version 5→1 |
| `wheel` | `user_config.h` | A/B 对调 P21/P20 → P20/P21 |
| `power` | `user_config.h` | USB_5V P24→P01 / BAT_CHG P30→P00 / LVD P23→P33 + LVD_CHECK_INDEX 同步 |

共 3 个文件被修改（`user_config.h` 被 3 个 policy 各改一次，FileTransaction 保证同一文件只备份一次）。

---

## 3. 拒绝的 4 个 policy

| policy | 拒绝原因（原文） | 结构差异 |
|---|---|---|
| `sensor` | interface=4w 需要 user_config.h 已有 SENSOR_NCS/MOSI/MISO_PIN；interface 切换需人工，本策略只做同 interface 值替换 | 525 是 2w（SDIO 单线），495 是 4w（NCS+SCLK+MOSI+MISO） |
| `switch` | user_config.h 缺少 MODE_24G_PIN 定义 | 525 是单脚 MODE_BLE_24G_PIN，495 是双脚 MODE_24G_PIN + MODE_BLE_PIN |
| `led` | LED 极性从 low 改为 high 需人工（涉及 led_*_on/off、mode_led_all_off/on 及调用点） | 525 是低有效（led_r_on=gpio_clear），495 是高有效（gpio_set） |
| `keys` | 文件有定义但 board 未声明的键: ['KEY_PAIR_PIN']；v1 不做增删行，若为 KEY_C0_PIN 或 KEY_PAIR_PIN 属 v1 不支持范围，需人工 | 525 有 PAIR 键（7 键），495 无 PAIR（6 键，已注释掉） |

4 处拒绝全是结构切换，不是值替换。v1 设计上就不做，拒绝是预期行为。

---

## 4. 完整 git diff（3 个文件 / 12 行）

~~~diff
--- a/hal/device/om6239/GCC/startup_om6239.S
+++ b/hal/device/om6239/GCC/startup_om6239.S
@@ -46 +46 @@ __Vectors:
-                .long    0x00710023
+                .long    0x00710495
--- a/projects/mouse_demo/main/mouse_hw.c
+++ b/projects/mouse_demo/main/mouse_hw.c
@@ -65 +65 @@
-const char mouse_name[MOUSE_NAME_MAX_LEN] =  "BT5.1Mouse";             /* 蓝牙名 配置 */
+const char mouse_name[MOUSE_NAME_MAX_LEN] =  "V196";             /* 蓝牙名 配置 */
--- a/projects/mouse_demo/periph/user_config.h
+++ b/projects/mouse_demo/periph/user_config.h
@@ -109,2 +109,2 @@
-#define WHEEL_A_PIN             (P21)
-#define WHEEL_B_PIN             (P20)
+#define WHEEL_A_PIN             (P20)
+#define WHEEL_B_PIN             (P21)
@@ -164,2 +164,2 @@
-#define USB_5V                  (P24)
-#define BAT_CHG_PIN             (P30)
+#define USB_5V                  (P01)
+#define BAT_CHG_PIN             (P00)
@@ -171,2 +171,2 @@
-#define LVD_PIN                 (P23)
-#define LVD_CHECK_INDEX         (POF_LVD_PIN_P23)
+#define LVD_PIN                 (P33)
+#define LVD_CHECK_INDEX         (POF_LVD_PIN_P33)
@@ -213 +213 @@
-#define iPROJECT_ID_L  0x0023              /* 项目编号 */
+#define iPROJECT_ID_L  0x0495              /* 项目编号 */
@@ -223 +223 @@
-#define iREAL_VERSION_ID        5            /* 版本编号 */
+#define iREAL_VERSION_ID        1            /* 版本编号 */
@@ -227,2 +227,2 @@
-#define iCONSUMER_NAME "BYC"        /* 客户名字 */
-#define iPROJECT_NAME  "KC536"      /* 项目名字 */
+#define iCONSUMER_NAME "App"        /* 客户名字 */
+#define iPROJECT_NAME  "V196"      /* 项目名字 */
~~~

---

## 5. Manifest 记录

- schema: `om6239-file-transaction/v1`
- operation: `golden_sample_e606_from_kc536`
- entries: 3（user_config.h / startup_om6239.S / mouse_hw.c）
- actions: 5（3 policy 写 5 个动作：project_id×3 + wheel×1 + power×1）
- backup_root: `E:\tmp\525_golden\.omcfg_bak_20261114_145357_888599`

---

## 6. 结论

v1 能力边界：**3/7 覆盖，4/7 拒绝**。

- 能做的：值替换（引脚、ID、名字、LVD 派生、wheel A/B 对调）。
- 不能做的：结构切换（sensor interface / switch 单双脚 / LED 极性 / keys 增删）。

**这不是缺陷，是设计边界**：结构切换涉及行数变化、语义反转、条件编译，v1 不做是为了「拒绝优于静默错改」。v2 待支持，或走「人工改结构 + 工具改值」的组合。

**下一步**：`GOLDEN-SAMPLE-full.md` 记录「人工改 4 处结构 + 工具改值」的完整流程，验证 v1 的组合能力。