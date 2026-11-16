# STRUCTURAL-SWITCH-CHECKLIST — 结构切换人工指引

> 本文档是 v2 的需求文档，不是可执行方案。
> 不要照本文档写脚本——那是 v2 的活，需统筹立项。
> 本文档的用途：① v1 用户遇到结构切换时的人工指引；② v2 做结构切换 policy 时的规格输入。

---

## 背景

v1 的 7 个 policy 只做「值替换」，不做「结构切换」。525_golden 跑 7 policy 时，4 个被拒绝：
sensor / switch / led / keys。拒绝理由分别是「interface 切换」「单双脚切换」「极性反转」「按键增删」。

本文档把 4 处结构切换写成「代码片段级」的人工指引：
- **改前** = 525（纯净 KC536）的当前片段
- **改后** = 495（V196）的目标片段
- **涉及文件 / 行号** 只作定位参考，行号可能漂移，以片段内容为准

**引脚值说明**：目标值取自 495 的实际工程，是已验证的真实值。如果目标板不是 V196 同类硬件，引脚需查对应原理图，不能照抄。

---

## §1 sensor：2w(SDIO) → 4w(NCS+MOSI+MISO)

### 1.1 `user_config.h`：SENSOR 段替换

**改前（525 现状，L113-116）**：
~~~c
//* SENSOR IO口配置 */
#define SENSOR_MOTION_PIN       (P13)
#define SENSOR_SCLK_PIN         (P11)
#define SENSOR_SDIO_PIN         (P12)
~~~

**改后（495 目标）**：
~~~c
//* SENSOR IO口配置 */
#define SENSOR_NCS_PIN          (P10)
#define SENSOR_SCLK_PIN         (P11)
#define SENSOR_MOSI_PIN         (P12)
#define SENSOR_MISO_PIN         (P13)
#define SENSOR_MOTION_PIN       (P07)
#define SENSOR_2V_IN_EN         (1<<7|1<<6)
~~~

**关键联动**：`SENSOR_MOTION_PIN` 从 `P13` 挪到 `P07`，因为 `P13` 被新的 `SENSOR_MISO_PIN` 占用。**这是跨结构切换的联动，容易漏**。

`SENSOR_2V_IN_EN` 是 PAW3311 类传感器的 2V 使能，如果目标传感器不需要，可不加。

`SENSOR_DIR_DEFINE` 525 和 495 都是 `CLOCK_6`，不变。

### 1.2 `drv_senscan.c`：SDIO 宏目标替换

**改前（525 现状，L65-72）**：
~~~c
#define mSENSOR_SDIO_OUT        OM_GPIO0->OUTENSET = (1<<SENSOR_SDIO_PIN)
#define mSENSOR_SDIO_IN         OM_GPIO0->OUTENCLR = (1<<SENSOR_SDIO_PIN)
#define mSENSOR_SDIO_H          OM_GPIO0->DATAOUTSET = GPIO_MASK(SENSOR_SDIO_PIN)
#define mSENSOR_SDIO_L          OM_GPIO0->DATAOUTCLR = GPIO_MASK(SENSOR_SDIO_PIN)
#define mSENSOR_SDIO            (OM_GPIO0->DATA & (1<<SENSOR_SDIO_PIN))
~~~

**改后（495 目标）**：
~~~c
#define mSENSOR_NCS_OUT         OM_GPIO0->OUTENSET = (1<<SENSOR_NCS_PIN)
#define mSENSOR_NCS_IN          OM_GPIO0->OUTENCLR = (1<<SENSOR_NCS_PIN)
#define mSENSOR_SDIO_OUT        OM_GPIO0->OUTENSET = (1<<SENSOR_MOSI_PIN)
#define mSENSOR_SDIO_IN         OM_GPIO0->OUTENCLR = (1<<SENSOR_MOSI_PIN)
#define mSENSOR_NCS_H           OM_GPIO0->DATAOUTSET = GPIO_MASK(SENSOR_NCS_PIN)
#define mSENSOR_NCS_L           OM_GPIO0->DATAOUTCLR = GPIO_MASK(SENSOR_NCS_PIN)
#define mSENSOR_SDIO_H          OM_GPIO0->DATAOUTSET = GPIO_MASK(SENSOR_MOSI_PIN)
#define mSENSOR_SDIO_L          OM_GPIO0->DATAOUTCLR = GPIO_MASK(SENSOR_MOSI_PIN)
#define mSENSOR_SDIO            (OM_GPIO0->DATA & (1<<SENSOR_MISO_PIN))
~~~

**要点**：`SDIO_OUT/IN/H/L` 全部指向 `SENSOR_MOSI_PIN`（写），`SDIO`（读）指向 `SENSOR_MISO_PIN`；新增 `NCS_OUT/IN/H/L` 四行。

### 1.3 `drv_senscan.c`：SPI_MODE / DATA_FORMAT

**改前（525 现状，L127-129）**：
~~~c
SENSACN_CSR_DATA_FORMAT,     SENSCAN_DATA_FORMAT_8BIT,
SENSACN_CSR_SPI_MODE,        SENSCAN_SPI_MODE_2_WIRE,
~~~

**改后（495 目标）**：
~~~c
SENSACN_CSR_DATA_FORMAT,     SENSCAN_DATA_FORMAT_12BIT,
SENSACN_CSR_SPI_MODE,        SENSCAN_SPI_MODE_4_WIRE,
~~~

**说明**：DATA_FORMAT 8BIT→12BIT 是传感器型号相关（PAW3311 是 12bit）。**具体值取决于传感器规格书**，不是 4w 必然 12bit。如果目标传感器是 8bit 的，DATA_FORMAT 不改。

### 1.4 `drv_senscan.c`：`drv_senscan_write` 函数体

**改前（525 现状，L221-230）**：
~~~c
void drv_senscan_write(uint8_t sensor_addr, uint8_t  sensor_data)
{
    DRV_RCC_CLOCK_ENABLE(RCC_CLK_SENSCAN, 0U);
    OM_CRITICAL_BEGIN();
    sensor_w_sck(sensor_addr|0x80);
    delayus(5);
    sensor_w_sck(sensor_data);
    DRV_RCC_CLOCK_ENABLE(RCC_CLK_SENSCAN, 1U);
    OM_CRITICAL_END();
}
~~~

**改后（495 目标，L231-244）**：
~~~c
void drv_senscan_write(uint8_t sensor_addr, uint8_t  sensor_data)
{
    DRV_RCC_CLOCK_ENABLE(RCC_CLK_SENSCAN, 0U);
    OM_CRITICAL_BEGIN();
    mSENSOR_NCS_L;
    delayus(1);
    sensor_w_sck(sensor_addr|0x80);
    delayus(1);
    sensor_w_sck(sensor_data);
    DRV_RCC_CLOCK_ENABLE(RCC_CLK_SENSCAN, 1U);
    mSENSOR_NCS_H;
    OM_CRITICAL_END();
    delayus(2);
}
~~~

**4 处改动**：
1. `sensor_w_sck(sensor_addr|0x80);` 前加 `mSENSOR_NCS_L;` + `delayus(1);`
2. 两处 `delayus(5)` → `delayus(1)`
3. `DRV_RCC_CLOCK_ENABLE(..., 1U);` 后加 `mSENSOR_NCS_H;`
4. `OM_CRITICAL_END();` 后加 `delayus(2);`

**时序说明**：`delayus(5)→delayus(1)` 和末尾 `delayus(2)` 是 495 的实测值，可能和传感器型号相关。**如需精确时序，查传感器规格书的 SPI 时序要求**。

### 1.5 验证要点

改完后：
1. **`grep SENSOR_SDIO_PIN` 应无结果**（`user_config.h` 里已删）；
2. **`grep SENSOR_MISO_PIN` 应命中 `SENSOR_MISO_PIN (P13)`**（与 495 一致）；
3. **`SENSOR_MOTION_PIN` 必须是 P07，不是 P13**（否则和 MISO 冲突，编译能过但运行时传感器数据错）；
4. Keil 编译 0 Error / 0 Warning。
## §2 switch：单脚 MODE_BLE_24G_PIN → 双脚 MODE_24G_PIN + MODE_BLE_PIN

### 1. 改前（525 片段）

user_config.h：
    L125  #define MODE_BLE_24G_PIN        (P26)
    L127      #define MODE_BLE_CHECK      0
    L128      #define MODE_24G_CHECK      1

key_io.c：
    L208  if(MODE_BLE_CHECK == gpio_read(MODE_BLE_24G_PIN))
    L217  else //if(MODE_24G_CHECK == gpio_read(MODE_BLE_24G_PIN))

### 2. 改后（495 片段）

user_config.h：
    L132  #define MODE_BLE_PIN        (P26)
    L133  #define MODE_24G_PIN        (P34)
    L135      #define MODE_BLE_CHECK      1
    L136      #define MODE_24G_CHECK      1

key_io.c：
    L198  ble_low = (1 == gpio_read(MODE_BLE_PIN)) ? 1 : 0;
    L199  g24_low = (1 == gpio_read(MODE_24G_PIN)) ? 1 : 0;

### 3. 涉及文件

- projects/mouse_demo/periph/user_config.h：525 L125–L128 → 495 L132–L136（按宏名定位，行号会漂移）
- projects/mouse_demo/periph/key_io.c：525 L208–L217 → 495 L198–L199（判断逻辑整段改写，不是换宏名）

### 4. 联动提醒

- P34 跨文件冲突：525 中 P34 = KEY_R0_PIN（user_config.h L86）；495 把 P34 给 MODE_24G_PIN，KEY_R0 已迁 P23。改 matrix 时 P34 不得再复用为按键。
- P26 一致：MODE_BLE_PIN 在 525/495 都是 P26，未变。
- sensor 不冲突（已坐实）：495 sensor 占 P07(MOTION)/P10(NCS)/P11(SCLK)/P12(MOSI)/P13(MISO)，与 P26/P34 无交集。
- 移植陷阱：P13 在 525 是 SENSOR_MOTION_PIN，在 495 是 SENSOR_MISO_PIN——跨版本搬 sensor 代码时勿混。
- 语义变化：525 单脚电平二选一；495 双脚各自低有效。key_io.c 判断结构必须同步改，不能只换宏名。
- 上电默认电平：需与 495 user_config.c 中 MODE 行一致，探测未取该行，查 495 user_config.c。
## §3 led：低有效（led_on=gpio_clear）→ 高有效（led_on=gpio_set）

### 1. 改前（525 片段）

user_config.h：
    L132  #define LED_MODE_R_PIN        (P32)
    L133  #define LED_MODE_G_PIN        (P00)
    L134  #define LED_MODE_B_PIN        (P01)
    L136      #define led_r_on()            (gpio_clear(LED_MODE_R_PIN))
    L137      #define led_r_off()           (gpio_set(LED_MODE_R_PIN))
    L138      #define led_g_on()            (gpio_clear(LED_MODE_G_PIN))
    L139      #define led_g_off()           (gpio_set(LED_MODE_G_PIN))
    L140      #define led_b_on()            (gpio_clear(LED_MODE_B_PIN))
    L141      #define led_b_off()           (gpio_set(LED_MODE_B_PIN))
    L142      #define mode_led_all_off()    (OM_GPIO0->DATAOUTSET = (1<<LED_MODE_R_PIN)|...)
    L143      #define mode_led_all_on()     (OM_GPIO0->DATAOUTCLR = (1<<LED_MODE_R_PIN)|...)
    L146  #define LED_MODE_24G_PIN        LED_MODE_R_PIN
    L147  #define LED_MODE_BT1_PIN        LED_MODE_G_PIN
    L148  #define LED_MODE_BT0_PIN        LED_MODE_B_PIN
    L159  #define LED_R_PIN               (P04)
    L160  #define LED_G_PIN               (P05)
    L161  #define LED_B_PIN               (P06)

user_config.c：
    L52   {LED_MODE_R_PIN, USER_GPIO_MODE_OUTPUT_PP, PU_30K, PIN_HIGH_LEV},
    L53   {LED_MODE_G_PIN, USER_GPIO_MODE_OUTPUT_PP, PU_30K, PIN_HIGH_LEV},
    L54   {LED_MODE_B_PIN, USER_GPIO_MODE_OUTPUT_PP, PU_30K, PIN_HIGH_LEV},
    L55   {LED_R_PIN,      USER_GPIO_MODE_OUTPUT_PP, PU_30K, PIN_HIGH_LEV},
    L56   {LED_G_PIN,      USER_GPIO_MODE_OUTPUT_PP, PU_30K, PIN_HIGH_LEV},
    L57   {LED_B_PIN,      USER_GPIO_MODE_OUTPUT_PP, PU_30K, PIN_HIGH_LEV},

### 2. 改后（495 片段）

user_config.h：
    L141  #define LED_R_PIN             (P04)
    L142  #define LED_G_PIN             (P05)
    L143  #define LED_B_PIN             (P06)
    L144  #define led_r_on()            (gpio_set(LED_R_PIN))
    L145  #define led_r_off()           (gpio_clear(LED_R_PIN))
    L146  #define led_g_on()            (gpio_set(LED_G_PIN))
    L147  #define led_g_off()           (gpio_clear(LED_G_PIN))
    L148  #define led_b_on()            (gpio_set(LED_B_PIN))
    L149  #define led_b_off()           (gpio_clear(LED_B_PIN))
    L150  #define led_low_on()          (gpio_set(LED_R_PIN))
    L151  #define led_low_off()         (gpio_clear(LED_R_PIN))
    L152  #define led_chg_on()          (gpio_set(LED_G_PIN))
    L153  #define led_chg_off()         (gpio_clear(LED_G_PIN))
    L156  #define LED_MODE_R_PIN        (P24)
    L157  #define LED_MODE_G_PIN        (P25)
    L158  #define LED_MODE_B_PIN        (P31)
    L159  #define LED_MODE_24G_PIN      LED_MODE_R_PIN
    L160  #define LED_MODE_BLE_PIN      LED_MODE_B_PIN
    L162  #define led_24g_on()          (gpio_set(LED_MODE_24G_PIN))
    L163  #define led_24g_off()         (gpio_clear(LED_MODE_24G_PIN))
    L164  #define led_ble_on()          (gpio_set(LED_MODE_BLE_PIN))
    L165  #define led_ble_off()         (gpio_clear(LED_MODE_BLE_PIN))
    L166  #define mode_led_all_off()    do { led_24g_off(); led_ble_off(); } while (0)
    L167  #define mode_led_all_on()     do { led_24g_on();  led_ble_on();  } while (0)

user_config.c：
    L55   {LED_MODE_R_PIN, USER_GPIO_MODE_OUTPUT_PP, PU_30K, PIN_LOW_LEV},
    L56   {LED_MODE_G_PIN, USER_GPIO_MODE_OUTPUT_PP, PU_30K, PIN_LOW_LEV},
    L57   {LED_MODE_B_PIN, USER_GPIO_MODE_OUTPUT_PP, PU_30K, PIN_LOW_LEV},
    L58   {LED_R_PIN,      USER_GPIO_MODE_OUTPUT_PP, PU_30K, PIN_LOW_LEV},
    L59   {LED_G_PIN,      USER_GPIO_MODE_OUTPUT_PP, PU_30K, PIN_LOW_LEV},
    L60   {LED_B_PIN,      USER_GPIO_MODE_OUTPUT_PP, PU_30K, PIN_LOW_LEV},

### 3. 涉及文件

- projects/mouse_demo/periph/user_config.h：525 L132–L161 → 495 L141–L167（宏体逐个翻转 + 两套灯拆分，行号漂移）
- projects/mouse_demo/periph/user_config.c：525 L52–L57 → 495 L55–L60（六行初值 PIN_HIGH_LEV → PIN_LOW_LEV）

### 4. 联动提醒

- 两层灯别混：业务灯 led_r/g/b 在 525 用 LED_MODE_R/G/B 脚（P32/P00/P01），在 495 改用 LED_R/G/B 脚（P04/P05/P06）；模式灯另有一套 LED_MODE_*（495 = P24/P25/P31），由 led_24g/led_ble 驱动。
- 极性成对改：宏翻成 gpio_set 高有效后，gpio_config_table 六行初值必须同步 PIN_HIGH_LEV → PIN_LOW_LEV，否则上电瞬间全亮。
- P24/P25/P31 在 495 全局表中仅模式灯占用，与 §2（P26/P34）、§4（P22/P23/P27/P30/P32/P36）无冲突。
- 495 新增 led_low_on / led_chg_on（低电/充电指示，复用 R/G 脚），移植时按 495 保留，不要从 525 删。
- mode_led_all_on/off 在 495 改为函数式 do{...}while(0)，不能按 525 的位操作宏照抄。
## §4 keys：7 键（含 PAIR）→ 6 键（PAIR 注释掉）

### 1. 改前（525 片段）

user_config.h：
    L86   #define KEY_R0_PIN              (P34)
    L87   #define KEY_R1_PIN              (P07)
    L88   #define KEY_R2_PIN              (P10)
    L89   #define KEY_B_PIN               (P22)
    L90   #define KEY_P_PIN               (P25)
    L91   #define KEY_DPI_PIN             (P31)
    L92   #define KEY_PAIR_PIN            (P27)

key_io.h：
    L36   #define KEY_MODE_R0         (OM_GPIO0->DATA & (1<<KEY_R0_PIN))
    ...
    L42   #define KEY_MODE_R7         (OM_GPIO0->DATA & (1<<KEY_DPI_PIN))
    L43   #define KEY_MODE_PAIR       (OM_GPIO0->DATA & (1<<KEY_PAIR_PIN))
    L83   #define bkey_pair           (1<<6)

key_io.c（PAIR 运行时残留）：
    L67   if(0 == KEY_MODE_PAIR)
    L68   key_status |= bkey_pair;
    L97   if(bkey_pair & key_status)
    L125  .ind_on_time = BLE_PAIR_TIME_ON,
    L126  .ind_off_time = BLE_PAIR_TIME_OFF,

### 2. 改后（495 片段）

user_config.h：
    L86   #define KEY_R0_PIN              (P23)
    L87   #define KEY_R1_PIN              (P36)
    L88   #define KEY_R2_PIN              (P22)
    L89   #define KEY_B_PIN               (P30)
    L90   #define KEY_P_PIN               (P27)
    L91   #define KEY_DPI_PIN             (P32)
    L92   //#define KEY_PAIR_PIN            (P27)

key_io.h：
    L36   #define KEY_MODE_R0         (OM_GPIO0->DATA & (1<<KEY_R0_PIN))
    ...
    L42   #define KEY_MODE_R7         (OM_GPIO0->DATA & (1<<KEY_DPI_PIN))
    L43   //#define KEY_MODE_PAIR       (OM_GPIO0->DATA & (1<<KEY_PAIR_PIN))
    L83   #define bkey_pair           (1<<6)   （保留，495 key_io.c 无引用）

key_io.c（495 改由 DPI 长按对码替代 PAIR）：
    L97   /* [dpi-pair] DPI 键: 短按切 DPI, 长按 2 秒对码
    L101  key_data &= ~bkey_dpi;   /* [dpi-pair] 屏蔽, 不让库立即切 DPI */
    L117  /* [dpi-pair] 长按 DPI 无条件进入 2.4G 对码
    L124  bmanual_pair = true;
    L132  /* [dpi-pair] BLE 长按 DPI: 重新配对
    L136  OM_PMU->SW_RSVD5 = 0xABCD;   /* [manual-pair] 跨复位传标志 */

### 3. 涉及文件

- projects/mouse_demo/periph/user_config.h：525 L86–L92 → 495 L86–L92（7 条变 6 条 + 1 行注释）
- projects/mouse_demo/periph/key_io.h：525 L43 → 495 L43（KEY_MODE_PAIR 注释）；L83 bkey_pair 两版都保留
- projects/mouse_demo/periph/key_io.c：525 L67-68/L97/L125-126 的 PAIR 逻辑 → 495 L97–L136 的 DPI 长按对码逻辑（整段替换，不是注释）

### 4. 联动提醒

- P27 同脚是 PAIR 下线根因：495 中 KEY_P_PIN = P27，与注释掉的 KEY_PAIR_PIN 同脚；PAIR 不是不需要，是被 P 键占用。注释即正确做法，不要改成别的脚。
- PAIR 运行时残留必须一起处理：只注释 PIN 宏不够，525 的 key_io.c L67-68（读键）、L97（处理）、L125-126（指示时间）都要下线；495 已由 DPI 长按对码替代（L97–L136），移植时按 495 走，不要恢复 PAIR 键。
- bkey_pair 宏（key_io.h L83）两版都保留：495 key_io.c 无引用，但可能被库引用，不要删。
- 按键脚整体重排：525 R0/R1/R2/B/P/DPI = P34/P07/P10/P22/P25/P31；495 = P23/P36/P22/P30/P27/P32，除 P22 外全变，逐条按 495 改。
- P34 与 §2 联动：525 KEY_R0(P34) → 495 KEY_R0(P23)，P34 让给 MODE_24G_PIN，两节必须同批改。
- 扫描/键值映射未在探测范围：key 处理数组、键值表、上报逻辑中的 PAIR 条目需同步注释或删除，查 495 key 处理逻辑。
## §2–§4 事实坐实（探测补充，2026-11-14）

### 已坐实（探测定稿）

- §2 sensor 不冲突：495 sensor = P07(MOTION)/P10(NCS)/P11(SCLK)/P12(MOSI)/P13(MISO)，与 P26/P34 无交集。
- §2 跨版本陷阱：P13 在 525 = SENSOR_MOTION_PIN，在 495 = SENSOR_MISO_PIN。
- §3 495 六行 LED 初值全 PIN_LOW_LEV（user_config.c L55–L60），与高有效宏配对，PASS。
- §3 多宏同脚是正常映射：P24 = LED_MODE_24G + LED_MODE_R；P31 = LED_MODE_BLE + LED_MODE_B。
- §4 PAIR 三处已注释：user_config.h L92 / key_io.h L43 / user_config.c L41；key_io.c L67-68 读键也已注释。
- §4 bkey_pair(1<<6) 两版都保留，勿删；495 对码改走 DPI 长按（key_io.c L97–L136）。

### 待人工核对（探测未覆盖）

- 495 user_config.c 中 MODE_BLE_PIN / MODE_24G_PIN 的 gpio_config_table 初值（查 E:\M_2026\495_V196\...\user_config.c 对应行）。
- 495 PIN_WAKE_UP_MASK 是否已移除 KEY_PAIR_PIN（525 含）。
- 495 drv_pmu_wakeup_pin_set(KEY_PAIR_PIN, ...) 是否已移除（525 user_config.h L99/L105 有）。

### 探测发现的 checklist 未覆盖项

- WHEEL A/B 相序对调：525 P20=WHEEL_B/P21=WHEEL_A；495 P20=WHEEL_A/P21=WHEEL_B。滚轮加减方向可能反向（不在 §1–§4 范围，登记待办）。
- LED 宏改名：525 led_bt0_on/off、led_bt1_on/off → 495 led_ble_on/off、led_24g_on/off，业务调用点需同步改名。
- 495 新增 led_low_on / led_chg_on（复用 P04/P05），如业务引用需保留。

---

## 自动化状态（2026-11-16）

§1–§5 结构切换从"人工改代码"转为"配置驱动"，对照表：

| 节 | 原手动操作 | 自动化方式 | 验证 |
|---|---|---|---|
| §1 sensor 3w→4w | 手改 `user_config.h` SENSOR 段 + `drv_senscan.c` SDIO/SPI | `.omcfg` 的 `board.sensor.bus: spi_4wire`（NCS/MOSI/MISO 自动生成，`SENSOR_2V_IN_EN` 联动） | `tests/test_sensor_bus.py` 4 用例 |
| §2 switch 单/双脚 | 手改 `MODE_24G_PIN` / `MODE_BLE_PIN` / `MODE_BLE_24G_PIN` | `.omcfg` 的 `board.mode_pins: single/dual`（自动选宏，sleep 断电逻辑联动） | `tests/test_model.py::test_mode_pins_*` |
| §3 led 极性 | 手改 `led_*_on()` 宏的 `gpio_set` / `gpio_clear` | `.omcfg` 的 `board.led_polarity: active_high/active_low` | `tests/test_rules.py` polarity 用例 |
| §4 keys 7键→6键（PAIR） | 手注释 `key_io.h/.c` 的 PAIR 行 + 手改 `user_config.h` 唤醒掩码 | `.omcfg` 的 `pins` 省略 `KEY_PAIR_PIN`；baseline `key_io.h/.c` 用 `#ifdef KEY_PAIR_PIN` 保护；`wake_keys` / `PIN_WAKE_UP_MASK` 自动去掉 PAIR | `tests/test_keys_pair_optional.py` 4 用例 + CH04_6K Keil 0E0W |
| §5 wheel A/B 相序 | 手交换 `P20` / `P21` | 直接交换 `.omcfg` 的 `pins.WHEEL_A_PIN` / `pins.WHEEL_B_PIN`；`validate.py` 已校验 ENCODER 四对一致性 | `validate.py:L270-285` |

自动化后**不再需要**的手动步骤：

- 手工修改 `projects/mouse_demo/periph/user_config.h` 的任何 SENSOR/MODE/LED/KEY 段
- 手工修改 `projects/mouse_demo/periph/key_io.h/.c` 的 PAIR 相关行
- 手工核对 `PIN_WAKE_UP_MASK` / `KEY_PIN_WAKE_UP_EN()` / `KEY_PIN_WAKE_UP_DIS()`
- 手工改 `drv_senscan.c` 的 SDIO/SPI 宏

新增配置样例：

- `configs/CH04_6k.omcfg`：CH04 派生 6 键版（无 `KEY_PAIR_PIN`），用于验证 §4 自动化。
  生成命令：`python -m omcfg gen --sdk <工作区> --apply`，Keil 编译应 0 Error 0 Warning。

实现备注：

- baseline `key_io.h:L43-45` / `key_io.c:L83-86` 用 `#ifdef KEY_PAIR_PIN` 包裹 PAIR 代码，
  避免"无 PAIR 时宏未定义导致编译失败"。`META.json` 的 `tree_sha256` / `file_count` / `size_bytes`
  已按改动后的 baseline 重算。
- `rules.py` 的 `key_io.refs` 在配置无 PAIR 时按 `_strip_ifdef_block` 排除条件引用；
  并新增"配置无 PAIR 但 baseline 缺 `#ifdef` 保护"的 error 检查。
- `validate.py` 删除了旧的 `pins.KEY_PAIR_PIN` 无条件 warning（baseline 已加保护，硬编码提示过时）。## chip/om6239.json 说明（2026-11-16）

`chip/om6239.json` 在 commit `9a12711` 里被 `json.dumps(indent=2)` 全量重排，
git diff 会看到 467 行变化，但**业务变化只有 4 处**：

1. `mux.LEDC_SEL.options[0/1]` 加 `sdk_supported: true`（P01/P05）
2. `mux.LEDC_SEL.options[2/3]` 加 `sdk_supported: false`，`sdk_hint: null`（P21/P33）
3. `lessons` 加 `LEDC_SEL_SDK_GAP` 条目
4. `lessons.sel_pins` 保留 4 个脚，但工具策略只允许 P01/P05

后续若改 chip json：
- 保持原紧凑格式（`{ "key": val }` 单行），不要用 `json.dumps(indent=2)` 重写
- 或统一换成 indent=2 后一次性 commit（不要再混）
- 查真实业务变化：`git diff --ignore-all-space` 或直接看 Python 加载后的 dict

原因：2026-11-16 LEDC A+B 修复时用脚本改了字段，`json.dumps` 把原紧凑格式展开。
功能不影响，但让 diff 噪音变大。
