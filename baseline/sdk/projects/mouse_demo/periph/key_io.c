/**
 * @file key_io.c
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
#include "mouse.h"
#include "main_24g.h"

#include "hid_process.h"
#include "usb_cfg_info.h"
#include "flash_process.h"

//-----------------------------------------------------------------------------;
// 常量定义区                                   // 定义只有函数内部使用的常量
//

//-----------------------------------------------------------------------------;
// 变量定义区
//
uint16_t    key_status;
uint16_t    key_status_bak;
volatile    uint32_t    key_data;

bool        bmode_swtich_valid;

extern bool busb_valid;

extern void hi5_usb_init(void);
extern void usb_disconnect(void);
//----------------------------------------------------------------------------;
// 表格定义区
//

//=============================================================================;
// 代码区                                                                      ;
//=============================================================================;

/**
 * @brief 按键IO扫描函数
 * 
 * @return none
 */
void key_io_scan(void)
{
    key_status = 0;

    if(0 == KEY_MODE_R0)
        key_status |= bkey_l;
    if(0 == KEY_MODE_R1)
        key_status |= bkey_r;
    if(0 == KEY_MODE_R2)
        key_status |= bkey_m; 
    if(0 == KEY_MODE_R3)
        key_status |= bkey_5;
    if(0 == KEY_MODE_R4)
        key_status |= bkey_4;
    if(0 == KEY_MODE_R7)
        key_status |= bkey_dpi; 
    if(0 == KEY_MODE_PAIR) 
        key_status |= bkey_pair;
}

/**
 * @brief 按键处理函数
 * 
 * @return None
 */
void key_process(void)
{
    static uint32_t conn_key_time_count = 0,key_delay = 0;
    static bool bconn_key_press = 0,bconnect_bak = 0;

    rtc_cur_value = drv_rtc_read(OM_RTC);   
    if(mMS_TO_TICK(10) > (rtc_cur_value-key_delay))
        return;  

    key_io_scan();
    if(key_status_bak != key_status)
    {                                           // 按键有变化先处理，后续再去抖
        key_status_bak = key_status;
        key_delay = rtc_cur_value;
    }

    key_data = (key_status&0x9F);

    if(iDEVICE_TYPE_USB == device_type)
        return;

    if(bkey_pair & key_status)
    {   
        if(0==(sys_ctrl&bmcu_reset))            /* 避免按键切换之后反复复位 */
        {
            if(!bconn_key_press)
            {
                bconn_key_press = 1;
                conn_key_time_count = rtc_cur_value;
            }
            else
            {
                if(mMS_TO_TICK(2000) > (rtc_cur_value-conn_key_time_count))     /* 长按配对键为对码 */
                    return;

                if((iDEVICE_TYPE_24G == device_type) && (!bconnect_bak))
                {
                    if(iMCU_MODE_NO_DONGLE == work_mode)
                    {
                        if(iRF_MODE_CONNECT != rf_mode_type)
                        {   
                            bconnect_bak = 1;
                            sensor_sleep();
                            mMCU_MODE_NORMAL;
                            m24g_connect_count = rtc_cur_value;
                            rf_mode_convert(iRF_MODE_CONNECT);          /* 24G长按配对键进入配对模式 */
                            ind_val_t ind_val = {
                                .ind_color = IND_RED,
                                .ind_times = ALWAYS_ON,
                                .ind_on_time = BLE_PAIR_TIME_ON,
                                .ind_off_time = BLE_PAIR_TIME_OFF,
                            };
                            ind_config(&ind_val);
                        }
                    }
                }
                else if(iDEVICE_TYPE_BT2 >= device_type)
                {
                    if(0 == (ble_24g_ctrl&bom6239_conning))             /* BLE长按配对键进入配对模式 */
					{
                        OM_PMU->SW_RSVD1 |= RSVD1_RF_CONN_EN;
                        NVIC_SystemReset();
                    }
                }
            }
        }
    }
    else
    {   
        if(bconn_key_press)
        {
            if(mMS_TO_TICK(1000) > (rtc_cur_value-conn_key_time_count))      /* 短按切换BT通道 */
            {
                if(iDEVICE_TYPE_BT2 >= device_type)
                {
                    if(bt_index == iDEVICE_TYPE_BT0)
                        bt_index = iDEVICE_TYPE_BT1;
                    else 
                        bt_index = iDEVICE_TYPE_BT0;
                    flash_save_status();
                }
            }
        }
        bconn_key_press = 0;
        bconnect_bak = 0;
        sys_ctrl &= ~bmcu_reset;
    }
}


/**
 * @brief 模式切换检测函数
 * @note  没有USB 5V插入的时候，通过开关切换24G/BLE,通过按键切换BLE通道
 * @note  有USB-5V插入时，通过USB信号枚举，枚举成功后再切换至USB模式，
 *        否则仅判定为充电线
 * 
 * @param type 模式切换的类型，
 * @return none
 */
void scan_mode_swtich(uint8_t type)
{
    static bool b5v_check_in = 0;
    static uint32_t usb_io_status = 0, mode_swtich_time = 0;

    if(iMODE_CHECK_POWERUP == type)
    {
        mode_swtich_time = 0;
    }
    else
    {
        if(iMODE_CHECK_DELAY == type)
        {
            rtc_cur_value = drv_rtc_read(OM_RTC);
            if(mMS_TO_TICK(32) > (rtc_cur_value-mode_swtich_time))
                return;
            mode_swtich_time = rtc_cur_value;
        }

        if(iDEVICE_TYPE_24G == device_type)
        {
            if(mMS_TO_TICK(2000) < (OM_RTC->ALARM0-drv_rtc_read(OM_RTC)))
            {
                if(mMS_TO_TICK(2000) < (OM_RTC->ALARM0-drv_rtc_read(OM_RTC)))
                    NVIC_SystemReset();
            }
        }
    }

    usb_io_status = USB_5V_PIN;

    device_type_t device_temp;

    if(MODE_BLE_CHECK == gpio_read(MODE_BLE_24G_PIN))
    {
        if(bt_index == 0)
            device_temp = iDEVICE_TYPE_BT0;
        else if(bt_index == 1)
            device_temp = iDEVICE_TYPE_BT1;
        else
            device_temp = iDEVICE_TYPE_BT2;
    }
    else //if(MODE_24G_CHECK == gpio_read(MODE_BLE_24G_PIN))
    {
        device_temp = iDEVICE_TYPE_24G;
    }


    if(0 != usb_io_status)          /* 5V IN */
    {
        if(iMODE_CHECK_POWERUP != type)
        {
            if(false == b5v_check_in)
            {
                b5v_check_in = true;
                hi5_usb_init();
                usb_ctrl_flag |= busb_suspend_resume;
            }

            if(0 == (usb_ctrl_flag&busb_suspend_resume))
            {
                if(iDEVICE_TYPE_USB != device_type)
                {
                    busb_valid = true;
                    bmode_swtich_valid = true;

                    sensor_wakeup();
                    device_type = iDEVICE_TYPE_USB;
                }
                return;
            }

            if(true == busb_valid)
                return;
        }
        else
        {
            device_type = device_temp;
            b5v_check_in = true;
            hi5_usb_init();
            usb_ctrl_flag |= busb_suspend_resume;
            return;
        }
    }
    else                    /* 5V OFF */
    {   
        if(iMODE_CHECK_POWERUP != type)
        {
            if(true == b5v_check_in)
            {
                b5v_check_in = false;
                busb_valid = false;
                usb_disconnect();
            }
        }
        else
        {
            device_type = device_temp;
            return;
        }
    }

    if(device_type == device_temp)
        return;
    
    bmode_swtich_valid = true;
    flash_save_status();

    if(iDEVICE_TYPE_BT0 == bt_index)
    {
        OM_PMU->SW_RSVD1 &= ~PMU_SW_RSVD1_RF_MDOE_MASK;
        OM_PMU->SW_RSVD1 |= iDEVICE_TYPE_BT0;
        NVIC_SystemReset();
    }
    else if(iDEVICE_TYPE_BT1 == bt_index)
    {
        OM_PMU->SW_RSVD1 &= ~PMU_SW_RSVD1_RF_MDOE_MASK;
        OM_PMU->SW_RSVD1 |= iDEVICE_TYPE_BT1;
        NVIC_SystemReset();
    }
    else if(iDEVICE_TYPE_BT2 == bt_index)
    {
        OM_PMU->SW_RSVD1 &= ~PMU_SW_RSVD1_RF_MDOE_MASK;
        OM_PMU->SW_RSVD1 |= iDEVICE_TYPE_BT2;
        NVIC_SystemReset();
    }
    else //if(iDEVICE_TYPE_24G == bt_index)
    {
        OM_PMU->SW_RSVD1 &= ~PMU_SW_RSVD1_RF_MDOE_MASK;
        OM_PMU->SW_RSVD1 |= iDEVICE_TYPE_24G;
        NVIC_SystemReset();
    }
}


void encoder_scan_val(uint8_t* define_key_fifo,uint32_t* define_key)
{
    if(OM_ENCODER->VALID&ENCODER_VALID_CNT_MASK)
    {
        wheel_data = OM_ENCODER->CNT;
        if(wheel_data & 0x08)
            wheel_data |= 0xf0;
        else
            wheel_data &= 0x0f;
    }

    if(0 != wheel_data)
    {
        if(0==(wheel_data&(1<<7)))
        {
            define_key_fifo[8] &= ~(1<<1);
            *define_key |= (1<<8);
        }
        else
        {
            define_key_fifo[9] &= ~(1<<1);
            *define_key |= (1<<9);
        }
    }
}


void wheel_fill_data(uint8_t* data_l)
{
    if (wheel_data)
    {
        /* code */
        if(*data_l & 0x80)      /* negative */
        {
            mouse_data_z = (wheel_data & 0x80) ? wheel_data : (0 - wheel_data);
        }
        else                    /* positive */
        {
            mouse_data_z = (wheel_data & 0x80) ? (0 - wheel_data) : wheel_data;
        }
    }
    else
    {
        mouse_data_z = *data_l;
    }
    
    wheel_data = 0;
    m_data_flag |= bmouse_data_send;
    m_tx_count = 4;
}
