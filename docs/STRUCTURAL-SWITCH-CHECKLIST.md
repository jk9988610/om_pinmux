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