/**
 * @file sensor.c
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2025-05-22
 * 
 * @copyright Copyright (c) 2025
 * 
 */

#include "om_driver.h"
#include "main.h"
#include "sensor.h"
#include "sensor_type_check.h"
#include "flash_process.h"
#include "HID_PROCESS.H"
#include "led.h"
//-----------------------------------------------------------------------------;
// 常量定义区                                   // 定义只有函数内部使用的常量
//

//-----------------------------------------------------------------------------;
// 变量定义区
//
bool         bsensor_error;
uint8_t      sensor_status_reg;

uint8_t      dpi_grade;
uint8_t      dpi_value;
uint8_t      sensor_type;

uint8_t      sensor_scan_freq;

uint16_t     mouse_x;
uint16_t     mouse_y;

uint8_t      ui8idx;
uint16_t     iir_pre_x;
uint16_t     iir_pre_y;

uint16_t     pub_xmf[4];
uint16_t     pub_ymf[4];

bool         bdpi_mul;
//----------------------------------------------------------------------------;
// 表格定义区
//
uint16_t const S205_dpi_tbl[][2]=
{
    // 索引 | 寄存器值 | DPI值
    50L/50L,         50,     // 索引0x00
    100L/50L,        100,    // 索引0x01
    150L/50L,        150,    // 索引0x02
    200L/50L,        200,    // 索引0x03
    250L/50L,        250,    // 索引0x04
    300L/50L,        300,    // 索引0x05
    350L/50L,        350,    // 索引0x06
    400L/50L,        400,    // 索引0x07
    450L/50L,        450,    // 索引0x08
    500L/50L,        500,    // 索引0x09
    550L/50L,        550,    // 索引0x0A
    600L/50L,        600,    // 索引0x0B
    650L/50L,        650,    // 索引0x0C
    700L/50L,        700,    // 索引0x0D
    750L/50L,        750,    // 索引0x0E
    800L/50L,        800,    // 索引0x0F
    850L/50L,        850,    // 索引0x10
    900L/50L,        900,    // 索引0x11
    950L/50L,        950,    // 索引0x12
    1000L/50L,       1000,   // 索引0x13
    1050L/50L,       1050,   // 索引0x14
    1100L/50L,       1100,   // 索引0x15
    1150L/50L,       1150,   // 索引0x16
    1200L/50L,       1200,   // 索引0x17
    1250L/50L,       1250,   // 索引0x18
    1300L/50L,       1300,   // 索引0x19
    1350L/50L,       1350,   // 索引0x1A
    1400L/50L,       1400,   // 索引0x1B
    1450L/50L,       1450,   // 索引0x1C
    1500L/50L,       1500,   // 索引0x1D
    1550L/50L,       1550,   // 索引0x1E
    1600L/50L,       1600,   // 索引0x1F
    1650L/50L,       1650,   // 索引0x20
    1700L/50L,       1700,   // 索引0x21
    1750L/50L,       1750,   // 索引0x22
    1800L/50L,       1800,   // 索引0x23
    1850L/50L,       1850,   // 索引0x24
    1900L/50L,       1900,   // 索引0x25
    1950L/50L,       1950,   // 索引0x26
    2000L/50L,       2000,   // 索引0x27
    2050L/50L,       2050,   // 索引0x28
    2100L/50L,       2100,   // 索引0x29
    2150L/50L,       2150,   // 索引0x2A
    2200L/50L,       2200,   // 索引0x2B
    2250L/50L,       2250,   // 索引0x2C
    2300L/50L,       2300,   // 索引0x2D
    2350L/50L,       2350,   // 索引0x2E
    2400L/50L,       2400,   // 索引0x2F
    2450L/50L,       2450,   // 索引0x30
    2500L/50L,       2500,   // 索引0x31
    2550L/50L,       2550,   // 索引0x32
    2600L/50L,       2600,   // 索引0x33
    2650L/50L,       2650,   // 索引0x34
    2700L/50L,       2700,   // 索引0x35
    2750L/50L,       2750,   // 索引0x36
    2800L/50L,       2800,   // 索引0x37
    2850L/50L,       2850,   // 索引0x38
    2900L/50L,       2900,   // 索引0x39
    2950L/50L,       2950,   // 索引0x3A
    3000L/50L,       3000,   // 索引0x3B
    3050L/50L,       3050,   // 索引0x3C
    3100L/50L,       3100,   // 索引0x3D
    3150L/50L,       3150,   // 索引0x3E
    3200L/50L,       3200,   // 索引0x3F
    3250L/50L,       3250,   // 索引0x40
    3300L/50L,       3300,   // 索引0x41
    3350L/50L,       3350,   // 索引0x42
    3400L/50L,       3400,   // 索引0x43
    3450L/50L,       3450,   // 索引0x44
    3500L/50L,       3500,   // 索引0x45
    3550L/50L,       3550,   // 索引0x46
    3600L/50L,       3600,   // 索引0x47
    3650L/50L,       3650,   // 索引0x48
    3700L/50L,       3700,   // 索引0x49
    3750L/50L,       3750,   // 索引0x4A
    3800L/50L,       3800,   // 索引0x4B
    3850L/50L,       3850,   // 索引0x4C
    3900L/50L,       3900,   // 索引0x4D
    3950L/50L,       3950,   // 索引0x4E
    4000L/50L,       4000,   // 索引0x4F
    4050L/50L,       4050,   // 索引0x50
    4100L/50L,       4100,   // 索引0x51
    4150L/50L,       4150,   // 索引0x52
    4200L/50L,       4200,   // 索引0x53
    4250L/50L,       4250,   // 索引0x54
    4300L/50L,       4300,   // 索引0x55
    4350L/50L,       4350,   // 索引0x56
    4400L/50L,       4400,   // 索引0x57
    4450L/50L,       4450,   // 索引0x58
    4500L/50L,       4500,   // 索引0x59
    4550L/50L,       4550,   // 索引0x5A
    4600L/50L,       4600,   // 索引0x5B
    4650L/50L,       4650,   // 索引0x5C
    4700L/50L,       4700,   // 索引0x5D
    4750L/50L,       4750,   // 索引0x5E
    4800L/50L,       4800,   // 索引0x5F
    4850L/50L,       4850,   // 索引0x60
    4900L/50L,       4900,   // 索引0x61
    4950L/50L,       4950,   // 索引0x62
    5000L/50L,       5000,   // 索引0x63
    5050L/50L,       5050,   // 索引0x64
    5100L/50L,       5100,   // 索引0x65
    5150L/50L,       5150,   // 索引0x66
    5200L/50L,       5200,   // 索引0x67
    5250L/50L,       5250,   // 索引0x68
    5300L/50L,       5300,   // 索引0x69
    5350L/50L,       5350,   // 索引0x6A
    5400L/50L,       5400,   // 索引0x6B
    5450L/50L,       5450,   // 索引0x6C
    5500L/50L,       5500,   // 索引0x6D
    5550L/50L,       5550,   // 索引0x6E
    5600L/50L,       5600,   // 索引0x6F
    5650L/50L,       5650,   // 索引0x70
    5700L/50L,       5700,   // 索引0x71
    5750L/50L,       5750,   // 索引0x72
    5800L/50L,       5800,   // 索引0x73
    5850L/50L,       5850,   // 索引0x74
    5900L/50L,       5900,   // 索引0x75
    5950L/50L,       5950,   // 索引0x76
    6000L/50L,       6000,   // 索引0x77
    6050L/50L,       6050,   // 索引0x78
    6100L/50L,       6100,   // 索引0x79
    6150L/50L,       6150,   // 索引0x7A
    6200L/50L,       6200,   // 索引0x7B
    6250L/50L,       6250,   // 索引0x7C
    6300L/50L,       6300,   // 索引0x7D
    6350L/50L,       6350,   // 索引0x7E
    6400L/50L,       6400,   // 索引0x7F

    6450L/100L,      6450,   // 索引0x80
    6500L/100L,      6500,   // 索引0x81
    6550L/100L,      6550,   // 索引0x82
    6600L/100L,      6600,   // 索引0x83
    6650L/100L,      6650,   // 索引0x84
    6700L/100L,      6700,   // 索引0x85
    6750L/100L,      6750,   // 索引0x86
    6800L/100L,      6800,   // 索引0x87
    6850L/100L,      6850,   // 索引0x88
    6900L/100L,      6900,   // 索引0x89
    6950L/100L,      6950,   // 索引0x8A
    7000L/100L,      7000,   // 索引0x8B
    7050L/100L,      7050,   // 索引0x8C
    7100L/100L,      7100,   // 索引0x8D
    7150L/100L,      7150,   // 索引0x8E
    7200L/100L,      7200,   // 索引0x8F
    7250L/100L,      7250,   // 索引0x90
    7300L/100L,      7300,   // 索引0x91
    7350L/100L,      7350,   // 索引0x92
    7400L/100L,      7400,   // 索引0x93
    7450L/100L,      7450,   // 索引0x94
    7500L/100L,      7500,   // 索引0x95
    7550L/100L,      7550,   // 索引0x96
    7600L/100L,      7600,   // 索引0x97
    7650L/100L,      7650,   // 索引0x98
    7700L/100L,      7700,   // 索引0x99
    7750L/100L,      7750,   // 索引0x9A
    7800L/100L,      7800,   // 索引0x9B
    7850L/100L,      7850,   // 索引0x9C
    7900L/100L,      7900,   // 索引0x9D
    7950L/100L,      7950,   // 索引0x9E
    8000L/100L,      8000,   // 索引0x9F
    8050L/100L,      8050,   // 索引0xA0
    8100L/100L,      8100,   // 索引0xA1
    8150L/100L,      8150,   // 索引0xA2
    8200L/100L,      8200,   // 索引0xA3
    8250L/100L,      8250,   // 索引0xA4
    8300L/100L,      8300,   // 索引0xA5
    8350L/100L,      8350,   // 索引0xA6
    8400L/100L,      8400,   // 索引0xA7
    8450L/100L,      8450,   // 索引0xA8
    8500L/100L,      8500,   // 索引0xA9
    8550L/100L,      8550,   // 索引0xAA
    8600L/100L,      8600,   // 索引0xAB
    8650L/100L,      8650,   // 索引0xAC
    8700L/100L,      8700,   // 索引0xAD
    8750L/100L,      8750,   // 索引0xAE
    8800L/100L,      8800,   // 索引0xAF
    8850L/100L,      8850,   // 索引0xB0
    8900L/100L,      8900,   // 索引0xB1
    8950L/100L,      8950,   // 索引0xB2
    9000L/100L,      9000,   // 索引0xB3
    9050L/100L,      9050,   // 索引0xB4
    9100L/100L,      9100,   // 索引0xB5
    9150L/100L,      9150,   // 索引0xB6
    9200L/100L,      9200,   // 索引0xB7
    9250L/100L,      9250,   // 索引0xB8
    9300L/100L,      9300,   // 索引0xB9
    9350L/100L,      9350,   // 索引0xBA
    9400L/100L,      9400,   // 索引0xBB
    9450L/100L,      9450,   // 索引0xBC
    9500L/100L,      9500,   // 索引0xBD
    9550L/100L,      9550,   // 索引0xBE
    9600L/100L,      9600,   // 索引0xBF
    9650L/100L,      9650,   // 索引0xC0
    9700L/100L,      9700,   // 索引0xC1
    9750L/100L,      9750,   // 索引0xC2
    9800L/100L,      9800,   // 索引0xC3
    9850L/100L,      9850,   // 索引0xC4
    9900L/100L,      9900,   // 索引0xC5
    9950L/100L,      9950,   // 索引0xC6
    10000L/100L,     10000,  // 索引0xC7
    
};
//=============================================================================;
// 代码区                                                                      ;
//=============================================================================;

/**
 * @brief SENSOR 硬件扫描初始化
 * 
 */
void senscan_init(void)
{
    drv_pmu_power_set(PMU_POWER_ID_RTC2M, PMU_POWER_ON);
    drv_senscan_init();
    drv_senscan_mode_select(OM_SENSCAN, SENSCAN_MODE_CONFIG);
}

/**
 * @brief SENSOR 平滑算法变量初始化
 * 
 */
void sensor_dat_init(void)
{
    ui8idx = 0;
    iir_pre_x = 0;
    iir_pre_y = 0;

    for(uint8_t i=0; i<4; i++)
    {
        pub_xmf[i] = 0;
        pub_ymf[i] = 0;
    }
}

/**
 * @brief SENSOR 清空之前的数据
 * 
 */
void sensor_clear_xy(void)
{
    sensor_read(2);
    sensor_read(3);
    sensor_read(4);
    sensor_dat_init();
}

/**
 * @brief SESNOR 休眠
 * 
 */
void sensor_sleep(void)
{
    if(0!=(sensor_status_reg & bsensor_sleep))
        return;

    sensor_status_reg |= bsensor_sleep;

    if(iSENSOR_TYPE_3212 == sensor_type)
        sensor_write(0x06, 0x18);
    else
        sensor_write(0x06, sensor_read(0x06)|0x08);
}

/**
 * @brief SENSOR 唤醒
 * 
 */
void sensor_wakeup(void)
{
    if(0==(sensor_status_reg & bsensor_sleep))
        return;
    sensor_status_reg &= ~bsensor_sleep;

    sensor_check_id();
    if(true == bsensor_error)
    {
        sensor_comm_resume();
    }

    if(iSENSOR_TYPE_3212 == sensor_type)
        sensor_write(0x06, 0x10);
    else
        sensor_write(0x06, (sensor_read(0x06)&0x77));
}

/**
 * @brief SENSOR 硬件扫描数据处理，将XY数据读出
 * 
 * @return none 
 */
__RAM_CODE void sensor_xy_scan(void)
{
    uint16_t x, y, z;
    uint32_t isr;

    x = 0;
    y = 0;
    for(uint8_t i=0; i<40; i++)
    {
        if(0==(OM_SENSCAN->CSR&SENSACN_CSR_SCAN_BUSY_MASK))
        {
            isr = OM_SENSCAN->ISR;
            OM_SENSCAN->ISR |= isr;
            if(isr & DRV_EVENT_SENSCAN_SCAN_DONE)
            {
                delayus(5);
                x = OM_SENSCAN->X_DATA;
                y = OM_SENSCAN->Y_DATA;
                #if (SENSOR_DIR_DEFINE == SENSOR_DIR_NONE)
                    /* 无旋转：直接使用原始 x / y */
                #elif (SENSOR_DIR_DEFINE == SENSOR_DIR_CLOCK_0)
                    y = 0 - y;
                #elif (SENSOR_DIR_DEFINE == SENSOR_DIR_CLOCK_3)
                    z = x;
                    x = y;
                    y = z;
                #elif (SENSOR_DIR_DEFINE == SENSOR_DIR_CLOCK_6)
                    x = 0 - x;
                #elif (SENSOR_DIR_DEFINE == SENSOR_DIR_ROT_90)
                    /* 顺时针 90°：x' = -y, y' = x */
                    z = x;
                    x = 0 - y;
                    y = z;
                #elif (SENSOR_DIR_DEFINE == SENSOR_DIR_ROT_270)
                    /* 逆时针 90°：x' = y, y' = -x */
                    z = y;
                    y = 0 - x;
                    x = z;
                #else
                    /* 反对角线镜像：x' = -y, y' = -x */
                    z = y;
                    y = 0 - x;
                    x = 0 - z;
                #endif

                if(sensor_status_reg&bxy_data_invalid)
                {
                    sensor_status_reg &= ~bxy_data_invalid;
                    sensor_dat_init();
                }
            }
            break;
        }
        else
        {
            delayus(5);
        }
    }

    if (bdpi_mul)
    {
        x<<=1;
        y<<=1;
    }


    if(adv_cfg_value&(1<<6))            /* SENSOR画线数据圆滑处理 */
    {
        pub_xmf[ui8idx&0x03] =  x;
        pub_ymf[ui8idx&0x03] =  y;
        ui8idx++;

        x = (pub_xmf[0] +
            pub_xmf[1] +
            pub_xmf[2] +
            pub_xmf[3] +
            iir_pre_x);

        y = (pub_ymf[0] +
            pub_ymf[1] +
            pub_ymf[2] +
            pub_ymf[3] +
            iir_pre_y);

        iir_pre_x = (x&0x0003);
        iir_pre_y = (y&0x0003);
        x = (x>>2);
        y = (y>>2);
    }

    mouse_x += x;
    mouse_y += y;
    if(mouse_x|mouse_y)
        m_tx_count = 4;
}

/* S205 DPI初始化加载表（存 S205_dpi_tbl 的索引，非寄存器值）
   档位：1200 / 1600(默认) / 2400 / 3200 / 6400，共 5 档
   6400 对应索引 0x7F，仍走 50DPI 步进，不需要 bdpi_mul 倍频 */
unsigned char const sensor_dpi_ini[] =
{
    1200L/50L - 1,
    1600L/50L - 1,
    2400L/50L - 1,
    3200L/50L - 1,
    6400L/50L - 1,
    0xFF,
    0xFF,
    0xFF,
};

/**
 * @brief SENSOR 设置DPI
 * 
 */
void sensor_set_dpi(void)
{
    uint8_t i;

    OM_PMU->SW_RSVD1 &= ~PMU_SW_RSVD1_DPI_MASK;
    OM_PMU->SW_RSVD1 |= ((dpi_grade<<4)&PMU_SW_RSVD1_DPI_MASK);
    if(dpi_value == dpi_value_tbl[dpi_grade&0x07])
        return; 

    drv_senscan_stop();
    dpi_value = dpi_value_tbl[dpi_grade&0x07];
	if(sensor_status_reg&bsensor_12bit)
    {
        sensor_write(0x09, 0x5A);   //解锁
        sensor_write(0x0D, S205_dpi_tbl[dpi_value][0]); //写CPI_X
        sensor_write(0x0E, S205_dpi_tbl[dpi_value][0]); //写CPI_Y
        sensor_write(0x09, 0x00); //锁定
        if (dpi_value > 0x7F)
            bdpi_mul = true;
        else
            bdpi_mul = false;
        
    }
    else
    {
        sensor_write(0x06, (sensor_read(0x06)&0x70)|(dpi_value&0x47));
    }
    sensor_status_reg |= bxy_data_invalid;
    drv_senscan_begin();
}

/**
 * @brief 狙击键按下触发，每个SENSOR的配置DPI方式可能不同，在这里去配置
 * 
 * @param key_type 
 */
void sniper_set_dpi(bool key_type)
{
    uint8_t sensor_val;
	
	sensor_val = (SNIPER_ADD == key_type) ? para_cfg_dat[2] : para_cfg_dat[3];

    if(sensor_val == 0xFF)
        return;
    drv_senscan_stop();
    if(sensor_status_reg&bsensor_12bit)
    {
        sensor_write(0x09, 0x5A);
        sensor_write(0x0D, S205_dpi_tbl[sensor_val][0]);
        sensor_write(0x0E, S205_dpi_tbl[sensor_val][0]);
        sensor_write(0x09, 0x00);
        if (sensor_val > 0x7F)
            bdpi_mul = true;
        else
            bdpi_mul = false;
    }
    else
    {
        sensor_write(0x06, (sensor_read(0x06)&0x70)|(sensor_val&0x47));
    }
    drv_senscan_begin();
}

/**
 * @brief 狙击键松开触发，恢复原来的DPI
 * 
 * @param none 
 */
void sniper_reset_dpi()
{
    drv_senscan_stop();
    dpi_value = dpi_value_tbl[dpi_grade&0x07];
	if(sensor_status_reg&bsensor_12bit)
    {
        sensor_write(0x09, 0x5A);
        sensor_write(0x0D, S205_dpi_tbl[dpi_value][0]);
        sensor_write(0x0E, S205_dpi_tbl[dpi_value][0]);
        sensor_write(0x09, 0x00);
        if (dpi_value > 0x7F)
            bdpi_mul = true;
        else
            bdpi_mul = false;
    }
    else
    {
        sensor_write(0x06, (sensor_read(0x06)&0x70)|(dpi_value&0x47));
    }
    drv_senscan_begin();
}

/**
 * @brief 按键解码出来判断是DPI按键按下,调用这个函数处理
 * 
 */
void dpi_key_press(uint8_t key_plus_fun_ctrl)
{
    extern unsigned char dat_24g_0[];
    #define rf_mode_type_local dat_24g_0[26]
    #define iRF_MODE_NORMAL_LOCAL 0x03
    
    if((iDEVICE_TYPE_USB == device_type)
        || ((iDEVICE_TYPE_BT2 >= device_type) && (ble_24g_ctrl & bom6239_sync_ok))              /* BLE已连接 */
        || ((ble_24g_ctrl & bom6239_sync_ok) && (iRF_MODE_NORMAL_LOCAL == rf_mode_type_local))) /* 2.4G已连接 */
    {
        sensor_change_dpi(key_plus_fun_ctrl);
        sensor_set_dpi();
        hid_ctrl_reg |= bdevice_status_change;
        def_tx_count = 3;
        dpi_config(dpi_grade);   /* 切档后由 mode_led_hint 的 DPI 优先块点灯，不走原厂灯效表 */
        bsave_status = true;
    }
}

/**
 * @brief 判断DPI加减
 * 
 * @param key_plus_fun_ctrl 
 */
void sensor_change_dpi(uint8_t key_plus_fun_ctrl)
{
    unsigned char i,j;

    j = (dpi_grade&0x07);
    i = 0;
    do
    {
        if(key_plus_fun_ctrl&bdpi_add_sub)      // 判断下一个有效的DPI值
        {                                       // dpi+
            j++;
            if(0x08==j)
            {
                if(0==(key_plus_fun_ctrl&bdpi_change_ctrl))
                    return;                     // 单级dpi加，已经到达最大dpi
                else
                    j = 0x00;
            }
        }
        else
        {                                       // dpi-
            j--;
            if(0xFF==j)
            {                                   // 单级dpi减，已经到达最小dpi
                return;
            }
        }
 
        if(0xFF != dpi_value_tbl[j])
        {
            break;
        }
        i++;
        if(8 <= i)
        {
            return;
        }
    }
    while(1);

    dpi_grade = (j&0x07);
    report_dpi[key_mode] &= 0xF8;
    report_dpi[key_mode] |= dpi_grade;
}


/**
 * @brief SENSOR 两线通信模式下有可能出现通信数据错误，此时需要恢复
 * 
 */
void sensor_comm_resume(void)
{
    uint8_t i;

    i=3;                    /* 重试次数从16降到3，避免长时间阻塞 */
    do
    {
        drv_wdt_keep_alive(OM_WDT);
        sensor_resync();
        sensor_check_id();
        if(false==bsensor_error)
        {
            return;
        }
    }
    while(--i);
}

/**
 * @brief SENSOR 检测ID，判断通信是否异常
 * 
 */
void sensor_check_id(void)
{
    uint8_t i;

    bsensor_error = false;
    i = sensor_read(0x00);
    if((0x30 != (i & 0xFC)) && (0x58 != i))
    {
        bsensor_error = true;
    }
}

