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
void sys_reset(void);       /* 三键组合恢复出厂：实现见文件末尾 */
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
#ifdef KEY_PAIR_PIN
    /* 可选独立对码键：S205 无此脚（DPI 长按对码），有脚的工程才扫描 */
    if(0 == KEY_MODE_PAIR)
        key_status |= bkey_pair;
#endif

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
    static uint32_t flash_save_wait = 0;
    static uint32_t factory_key_time_count = 0;
    static bool bfactory_key_press = 0,bfactory_key_done = 0;

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

    /* [factory-reset] 左(P26/bit0)+中(P21/bit2)+右(P20/bit1) 同时长按 3 秒恢复出厂。
     * 组合期间三个键仍按 HID 正常上报，不做屏蔽；bfactory_key_done 保证松手前只触发一次。
     * S205 无"左右切回报率"和"中+右对码"分支（对码走 DPI 键 bit7），与 0x07 掩码无交集。 */
    if((key_status & (bkey_l | bkey_r | bkey_m)) == (bkey_l | bkey_r | bkey_m))
    {
        if(!bfactory_key_press)
        {
            bfactory_key_press = true;
            bfactory_key_done = false;
            factory_key_time_count = rtc_cur_value;
        }
        else if(!bfactory_key_done
            && (mMS_TO_TICK(3000) < (rtc_cur_value - factory_key_time_count)))
        {
            bfactory_key_done = true;       /* 松手前不重复触发 */
            sys_reset();                    /* 清 flash + 复位，不返回 */
        }
    }
    else
    {
        bfactory_key_press = false;
        bfactory_key_done = false;
    }

    if(iDEVICE_TYPE_USB == device_type)
        return;

    /* [dpi-persist] 电池模式（2.4G/BLE）的 logo_process 在 led.c 提前 return，
       没有落盘通路，导致切 DPI 后直接断电会回到默认档。
       这里统一补一条：脏标记置位后静默 300ms 再写 Flash，
       保证掉电保持，同时把连按切档合并为一次擦写。 */
    if((true == bsave_status) || (true == bsave_driver_status))
    {
        if(0 == flash_save_wait)
            flash_save_wait = rtc_cur_value;
        else if(mMS_TO_TICK(300) <= (rtc_cur_value - flash_save_wait))
        {
            flash_save_wait = 0;
            if(true == bsave_status)
            {
                bsave_status = false;
                flash_save_status();
            }
            if(true == bsave_driver_status)
            {
                bsave_driver_status = false;
                flash_save_driver_status();
            }
        }
    }
    else
    {
        flash_save_wait = 0;
    }

    /* [dpi-pair] DPI 键: 短按切 DPI, 长按 2 秒对码
     * 按下期间屏蔽 key_data 的 DPI 位, 防止 define_key_process 立刻切 DPI */
    if(bkey_dpi & key_status)
    {   
        key_data &= ~bkey_dpi;   /* [dpi-pair] 屏蔽, 不让库立即切 DPI */

        if(0==(sys_ctrl&bmcu_reset))
        {
            if(!bconn_key_press)
            {
                bconn_key_press = 1;
                conn_key_time_count = rtc_cur_value;
            }
            else
            {
                if(mMS_TO_TICK(2000) > (rtc_cur_value-conn_key_time_count))
                    return;

                if((iDEVICE_TYPE_24G == device_type) && (!bconnect_bak))
                {
                    ble_24g_ctrl &= ~bom6239_sync_ok;
                    ble_24g_ctrl &= ~bom6239_conn_ok;

                    bconnect_bak = 1;
                    bmanual_pair = true;
                    sensor_sleep();
                    mMCU_MODE_NORMAL;
                    m24g_connect_count = rtc_cur_value;
                    rf_mode_convert(iRF_MODE_CONNECT);
                }
                else if(iDEVICE_TYPE_BT2 >= device_type)
                {
                    if(0 == (ble_24g_ctrl&bom6239_conning))
                    {
                        OM_PMU->SW_RSVD5 = 0xABCD;
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
            if(mMS_TO_TICK(1000) > (rtc_cur_value-conn_key_time_count))
            {
                if((iDEVICE_TYPE_BT2 >= device_type) || (iDEVICE_TYPE_24G == device_type))
                {
                    extern void dpi_key_press(uint8_t);
                    dpi_key_press(bdpi_add_sub | bdpi_change_ctrl);
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

    /* 拨杆三档判断 (高有效) */
    uint8_t ble_low = (MODE_BLE_CHECK == gpio_read(MODE_BLE_PIN)) ? 1 : 0;
    uint8_t g24_low = (MODE_24G_CHECK == gpio_read(MODE_24G_PIN)) ? 1 : 0;

    if (ble_low && !g24_low)
    {
        /* 拨到 BLE 档 */
        if(bt_index == 0)
            device_temp = iDEVICE_TYPE_BT0;
        else if(bt_index == 1)
            device_temp = iDEVICE_TYPE_BT1;
        else
            device_temp = iDEVICE_TYPE_BT2;
    }
    else if (g24_low && !ble_low)
    {
        /* 拨到 2.4G 档 */
        device_temp = iDEVICE_TYPE_24G;
    }
    else if (!ble_low && !g24_low)
    {
        /* 拨到 BAT 档：无 5V 时保持原模式不变；有 5V 时让下面分支接管进 USB */
        if(0 == usb_io_status)
            return;
        device_temp = device_type;   /* 保持当前模式，仅用于后面 != 判断 */
    }
    else
    {
        /* 异常状态，默认 2.4G */
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

/**
 * @brief 恢复出厂：清 flash 配置 + 重新配对 ID，然后软复位
 * @note  供"左+中+右长按 3s"调用；语义与 0516 工程一致
 */
void sys_reset(void)
{
    OM_CRITICAL_BEGIN();        /* 关中断，防止复位过程中再触发 flash 读写 */

    usb_disconnect();                       /* 先断开 USB，主机侧清按键状态 */
    flash_reset_all_info();                 /* 擦 bank0..18 + flash_reset_id() */

    static uint32_t reset_time = 0;
    reset_time = drv_rtc_read(OM_RTC);
    while(1)
    {
        if(drv_rtc_read(OM_RTC) - reset_time > mMS_TO_TICK(3000))
            break;
    }
    delayms(100);
    while(key_status)   key_io_scan();      /* 等所有键松开，避免复位后误判 */

    OM_CRITICAL_END();
    NVIC_SystemReset();
}
