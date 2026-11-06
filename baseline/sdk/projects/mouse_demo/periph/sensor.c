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
#include "ledc.h"
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

bool         bdpi_is_change;
bool         bdpi_mul;

static int16_t x_last = 0, y_last = 0;
static int16_t xsum = 0, ysum = 0;
//----------------------------------------------------------------------------;
// 表格定义区
uint16_t const S205_dpi_tbl[][2]=
{
    // 索引 | 寄存器值 | DPI值
    /* 0x00 */  200L/50L,       200  ,   // 索引0
    /* 0x01 */  400L/50L,       400  ,   // 索引1
    /* 0x02 */  600L/50L,       600  ,   // 索引2
    /* 0x03 */  800L/50L,       800  ,   // 索引3
    /* 0x04 */ 1000L/50L,       1000 ,   // 索引4
    /* 0x05 */ 1200L/50L,       1200 ,   // 索引5
    /* 0x06 */ 1400L/50L,       1400 ,   // 索引6
    /* 0x07 */ 1600L/50L,       1600 ,   // 索引7
    /* 0x08 */ 1800L/50L,       1800 ,   // 索引8
    /* 0x09 */ 2000L/50L,       2000 ,   // 索引9
    /* 0x0A */ 2200L/50L,       2200 ,   // 索引10
    /* 0x0B */ 2400L/50L,       2400 ,   // 索引11
    /* 0x0C */ 2600L/50L,       2600 ,   // 索引12
    /* 0x0D */ 2800L/50L,       2800 ,   // 索引13
    /* 0x0E */ 3000L/50L,       3000 ,   // 索引14
    /* 0x0F */ 3200L/50L,       3200 ,   // 索引15
    /* 0x10 */ 3400L/50L,       3400 ,   // 索引16
    /* 0x11 */ 3600L/50L,       3600 ,   // 索引17
    /* 0x12 */ 3800L/50L,       3800 ,   // 索引18
    /* 0x13 */ 4000L/50L,       4000 ,   // 索引19
    /* 0x14 */ 4200L/50L,       4200 ,   // 索引20
    /* 0x15 */ 4400L/50L,       4400 ,   // 索引21
    /* 0x16 */ 4600L/50L,       4600 ,   // 索引22
    /* 0x17 */ 4800L/50L,       4800 ,   // 索引23
    /* 0x18 */ 5000L/50L,       5000 ,   // 索引24
    /* 0x19 */ 5200L/50L,       5200 ,   // 索引25
    /* 0x1A */ 5400L/50L,       5400 ,   // 索引26
    /* 0x1B */ 5600L/50L,       5600 ,   // 索引27
    /* 0x1C */ 5800L/50L,       5800 ,   // 索引28
    /* 0x1D */ 6000L/50L,       6000 ,   // 索引29
    /* 0x1E */ 6200L/50L,       6200 ,   // 索引30
    /* 0x1F */ 6400L/50L,       6400 ,   // 索引31

    /* 0x20 */  6600L/100L,       6600 ,   // 索引32
    /* 0x21 */  6800L/100L,       6800 ,   // 索引33
    /* 0x22 */  7000L/100L,       7000 ,   // 索引34
    /* 0x23 */  7200L/100L,       7200 ,   // 索引35
    /* 0x24 */  7400L/100L,       7400 ,   // 索引36
    /* 0x25 */  7600L/100L,       7600 ,   // 索引37
    /* 0x26 */  7800L/100L,       7800 ,   // 索引38
    /* 0x27 */  8000L/100L,       8000 ,   // 索引39
    /* 0x28 */  8200L/100L,       8200 ,   // 索引40
    /* 0x29 */  8400L/100L,       8400 ,   // 索引41
    /* 0x2A */  8600L/100L,       8600 ,   // 索引42
    /* 0x2B */  8800L/100L,       8800 ,   // 索引43
    /* 0x2C */  9000L/100L,       9000 ,   // 索引44
    /* 0x2D */  9200L/100L,       9200 ,   // 索引45
    /* 0x2E */  9400L/100L,       9400 ,   // 索引46
    /* 0x2F */  9600L/100L,       9600 ,   // 索引47
    /* 0x30 */  9800L/100L,       9800 ,   // 索引48
    /* 0x31 */ 10000L/100L,       10000,   // 索引49
    /* 0x32 */ 10200L/100L,       10200,   // 索引50
    /* 0x33 */ 10400L/100L,       10400,   // 索引51
    /* 0x34 */ 10600L/100L,       10600,   // 索引52
    /* 0x35 */ 10800L/100L,       10800,   // 索引53
    /* 0x36 */ 11000L/100L,       11000,   // 索引54
    /* 0x37 */ 11200L/100L,       11200,   // 索引55
    /* 0x38 */ 11400L/100L,       11400,   // 索引56
    /* 0x39 */ 11600L/100L,       11600,   // 索引57
    /* 0x3A */ 11800L/100L,       11800,   // 索引58
    /* 0x3B */ 12000L/100L,       12000,   // 索引59
    /* 0x3C */ 12200L/100L,       12200,   // 索引60 
    /* 0x3D */ 12400L/100L,       12400,   // 索引61 
    /* 0x3E */ 12600L/100L,       12600,   // 索引62 
    /* 0x3F */ 12800L/100L,       12800,   // 索引63 
    
};
//
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

void sensor_deepsleep_wakeup()
{
    uint8_t mon_val = 0;
    bool bsensor_stop = 0;
    for (uint8_t i = 0; i < 100; i++)
    {
        sensor_read(0x03);
        delayms(3);
        sensor_read(0x04);
        delayms(3);
        sensor_read(0x12);
        delayms(3);
        mon_val = sensor_read(0x02);
        if ((mon_val&0x80) == 0)
        {
            bsensor_stop = true;
            break;
        }
        drv_wdt_keep_alive(OM_WDT);
    }

    if (!bsensor_stop)
    {
        NVIC_SystemReset();
    }
    
    
}

/**
 * @brief SENSOR 硬件扫描数据处理，将XY数据读出
 * 
 * @return none 
 */
__RAM_CODE void sensor_xy_scan(void)
{
    int16_t x, y, xy_h, z;
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
                x =0 - OM_SENSCAN->X_DATA;
                y = OM_SENSCAN->Y_DATA;

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

    
    mouse_x += x;
    mouse_y += y;
    if(mouse_x|mouse_y)
    {
        m_tx_count = 4;
    }
}

/* S205 DPI初始化加载表 */
unsigned char const sensor_dpi_ini[] =
{
    1200L/200L-1,
    1600L/200L-1,
    2400L/200L-1,
    3600L/200L-1,
    4800L/200L-1,
    6400L/200L-1,
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

        sensor_write(0x09, 0x5A);
        sensor_write(0x0D, S205_dpi_tbl[dpi_value][0]);
        sensor_write(0x0E, S205_dpi_tbl[dpi_value][0]);
        sensor_write(0x09, 0x00);
        if (dpi_value <= 0x1F)
            bdpi_mul = false;
        else
            bdpi_mul = true;            
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
        if (sensor_val <= 0x1F)
            bdpi_mul = false;
        else
            bdpi_mul = true;      
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
        if (dpi_value <= 0x1F)
            bdpi_mul = false;
        else
            bdpi_mul = true;      
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
    if((iDEVICE_TYPE_USB == device_type) || (ble_24g_ctrl & bom6239_sync_ok))
    {
        sensor_change_dpi(key_plus_fun_ctrl);
        sensor_set_dpi();
        hid_ctrl_reg |= bdevice_status_change;
		def_tx_count = 3;
        bsave_status = true;
        ledc_cmd(Cmd_Dpi_Indicate_Cfg,NULL);
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
            if(0x06==j)
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

    i=16;
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

