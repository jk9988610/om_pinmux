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


//----------------------------------------------------------------------------;
// 表格定义区
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
                #if (SENSOR_DIR_DEFINE == SENSOR_DIR_CLOCK_0)
                    y = 0 - y;
                #elif (SENSOR_DIR_DEFINE == SENSOR_DIR_CLOCK_3)
                    z = x;
                    x = y;
                    y = z;
                #elif (SENSOR_DIR_DEFINE == SENSOR_DIR_CLOCK_6)
                    x = 0 - x;
                #else
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

/* S205 DPI初始化加载表 */
unsigned char const sensor_dpi_ini[] =
{
    800/50,
    1600/50,
    2400/50,
    3200/50,
    6400/50,
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
        sensor_write(0x09, 0x5A);
        sensor_write(0x0D, dpi_value);
        sensor_write(0x0E, dpi_value);
        sensor_write(0x09, 0x00);
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
        sensor_write(0x0D, dpi_value);
        sensor_write(0x0E, dpi_value);
        sensor_write(0x09, 0x00);
    }
    else
    {
        sensor_write(0x06, (sensor_read(0x06)&0x70)|(dpi_value&0x47));
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
        sensor_write(0x0D, dpi_value);
        sensor_write(0x0E, dpi_value);
        sensor_write(0x09, 0x00);
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
        logo_cfg(iLED_CFG_DPI_CHANGE);
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

