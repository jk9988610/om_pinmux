/*******************************************************************************
* Copyright (c) 2016, SHENZHEN Co.,LTD.
* All rights reserved.
*
* 文件名称: Main.c
*
* 功能说明: 主函数处理程序
* 修改说明:
*******************************************************************************/
#include "main.h"
#include "main_usb.h"

//-----------------------------------------------------------------------------;
// 变量定义
//

//-----------------------------------------------------------------------------;
// 变量定义
//
bool                        busb_valid;

extern bool                 bperiph_int;

//=============================================================================;
// 代码区                                                                      ;
//=============================================================================;

extern void                 hi5_usb_init(void);
extern void                 usb_sleep(void);

/*********************************************************************
 * PUBLIC FUNCTIONS
 */
void mouse_usb_init(void)
{
    hi5_usb_init();

    sensor_wakeup();
    bscan_sensor_en = 1;
    drv_senscan_stop();
    sensor_scan_freq = mSEN_SCAN_US(1000);
    drv_senscan_begin();

    drv_encoder_control(OM_ENCODER, ENCODER_CONTROL_WAKEUP_DISABLE, NULL);
    drv_encoder_control(OM_ENCODER, ENCODER_CONTROL_START, NULL);

    mouse_periph_wakeup_enable(WAKEUP_ALL_DISABLE);
    __enable_irq();
    busb_valid = false;
}

/**
 * @brief when you turn off some PC like lenovo xiaoxin series while charging,
 *        the 5V output of the USB bus will not be turned off. but there will be 
 *        no USB D+&D- signal.
 *        the remote wakeup feature will be set before the PC is turned off.when 
 *        you press any key, device will be waked up. SOF interrupt occur at regular
 *        intervals.
 *        So,Exit USB mode if there is no signal after 5 seconds.
 * 
 */
#define CLEAR_EXIT_TIME_OUT    0
#define CHECK_EXIT_TIME_OUT    1
#define EXIT_TIME_OUT_VAL      mMS_TO_TICK(5000)        
void usb_invalid_time_check(bool check_mode)
{
    static uint32_t exit_timeout = 0;
    uint32_t rtc_cur_val = drv_rtc_read(OM_RTC);

    if(CLEAR_EXIT_TIME_OUT == check_mode)
    {
        exit_timeout = rtc_cur_val;
    }
    else
    {   
        if(mMS_TO_TICK(5000) < (rtc_cur_val-exit_timeout))
        {
            extern void usb_disconnect(void);
            usb_disconnect();
            delayms(50);
            NVIC_SystemReset();
        }
    }
}

/******************************************************************************
* 函数名称: main_24g()
* 功能描述:
* 说    明:
******************************************************************************/
int main_usb(void)
{
    usb_invalid_time_check(CLEAR_EXIT_TIME_OUT);

    while(1)
    {
        if(0 != (sys_ctrl&bscan_flag))
        {
            ledc_polling();
            key_process();
            sensor_xy_scan();
            drv_wdt_keep_alive(OM_WDT);
            mode_led_hint();
            if(1 == (sys_tick_count&0x07))
                logo_process();                 // 8ms扫描一次
            if(0 == (sys_tick_count&0x0F))
                bat_ind_process();

            define_key_process();
			usb_invalid_time_check(CLEAR_EXIT_TIME_OUT);
            if(0 != key_tx_count)
            {
                key_tx_count = 0;
                m_data_flag |= bstd_kb_data_send;
            }
            if(0 != mmk_tx_count)
            {
                mmk_tx_count = 0;
                m_data_flag |= bmmk_data_send;
            }
            if(m_tx_count)
            {
                m_tx_count = 0;
                m_data_flag |= bmouse_data_send;
            }

            sys_ctrl &= ~bscan_flag;
        }

        scan_mode_swtich(iMODE_CHECK_DELAY);
        
        usb_invalid_time_check(CHECK_EXIT_TIME_OUT);

        if(0 == (usb_ctrl_flag&busb_suspend_resume))
        {
            hid_process();
            usb_data_process();
        }
        else
        {
            if(3000<sys_tick_count)
                usb_sleep();
            else
            {
                sys_tick_count++;
                delayus(1000);
                sys_ctrl |= bscan_flag;
            }
        }
    }

    return 1;
}

/******************************************************************************
* 函数名称: usb_sleep()
* 功能描述:
* 说    明:
******************************************************************************/
void usb_sleep(void)
{
    if(0 == (usb_ctrl_flag&bsleep_eable))
    {
        usb_ctrl_flag &= ~busb_suspend_resume;
        return;
    }

    logo_cfg(iLED_CFG_OFF);
    drv_senscan_stop();
    led_low_off();
    if(0 == (usb_ctrl_flag & bwakeup_usb_enable))
    {                                       // 不可唤醒
        sensor_sleep();
        DRV_RCC_CLOCK_ENABLE(RCC_CLK_SENSCAN, 0U);
        DRV_RCC_CLOCK_ENABLE(RCC_CLK_ENCODER, 0U);
        mouse_periph_wakeup_enable(WAKEUP_BTN_MASK);

        for(uint32_t i=0; i<500; i++)
        {
            drv_wdt_keep_alive(OM_WDT);
            delayus(5000);
            scan_mode_swtich(iMODE_CHECK_NO_DELAY);
            if(0==(usb_ctrl_flag&busb_suspend_resume))
                goto usb_wakeup_process;
        }

        while(1)
        {
            bperiph_int = 0;
			if(0==(usb_ctrl_flag&busb_suspend_resume))
            	drv_pmu_set_low_power_mode(PMU_LPM_STOP1);

            if(bperiph_int)
            {
                drv_wdt_keep_alive(OM_WDT);
                delayus(5000);
                scan_mode_swtich(iMODE_CHECK_NO_DELAY);
            }

            if(0==(usb_ctrl_flag&busb_suspend_resume))
                break;
        }


        DRV_RCC_CLOCK_ENABLE(RCC_CLK_SENSCAN, 1U);
        DRV_RCC_CLOCK_ENABLE(RCC_CLK_ENCODER, 1U);
    }
    else
    {                                       // 可唤醒
        mouse_periph_wakeup_enable(WAKEUP_ALL_ENABLE);
        sensor_clear_xy();
        if(0==(adv_cfg_value&(1<<7)))
        {                           // 不可移动唤醒
            sensor_sleep();
        }
        else
        {
            sensor_scan_freq = mSEN_SCAN_US(50000);
            drv_senscan_begin();
        }

        while(1)
        {
            bperiph_int = 0;
            drv_pmu_set_low_power_mode(PMU_LPM_STOP1);
            drv_wdt_keep_alive(OM_WDT);
            if(bperiph_int)
            {
                delayus(5000);
                scan_mode_swtich(iMODE_CHECK_NO_DELAY);
                delayus(5000);
                scan_mode_swtich(iMODE_CHECK_NO_DELAY);

                // Wakeup the USB controller via remote pin
                OM_USB->POWER |= USB_POWER_RESUME;
                delayus(10000);
                OM_USB->POWER &= ~USB_POWER_RESUME;

                usb_ctrl_flag &= ~busb_suspend_resume;
            }
            if(0 == (usb_ctrl_flag&busb_suspend_resume))
            {
                break;
            }
        }
    }
usb_wakeup_process:
    drv_wdt_keep_alive(OM_WDT);
	DRV_RCC_CLOCK_ENABLE(RCC_CLK_SENSCAN, 1U);
    DRV_RCC_CLOCK_ENABLE(RCC_CLK_ENCODER, 1U);
    mouse_periph_wakeup_enable(WAKEUP_ALL_DISABLE);
    sensor_wakeup();

    bscan_sensor_en = 1;
    drv_senscan_stop();
    sensor_scan_freq = mSEN_SCAN_US(1000);
    drv_senscan_begin();

    drv_senscan_mode_select(OM_SENSCAN, SENSCAN_MODE_SCAN);
    drv_encoder_control(OM_ENCODER, ENCODER_CONTROL_START, NULL);
    logo_cfg(iLED_CFG_IDLE);
	busb_valid = false;
    usb_invalid_time_check(CLEAR_EXIT_TIME_OUT);
}

/** @} */

