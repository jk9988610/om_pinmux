/**
 * @file main_24g.c
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2025-05-23
 * 
 * @copyright Copyright (c) 2025
 * 
 */
#include "main_24g.h"

//-----------------------------------------------------------------------------;
// 变量定义
//

//-----------------------------------------------------------------------------;
// 变量定义
//
bool                        b24g_nromal;
bool                        is_app_enable;
volatile uint32_t           rtc_reload_value;
unsigned char               dat_24g_0[32];
unsigned char               dat_24g_1[32];

//=============================================================================;
// 代码区                                                                      ;
//=============================================================================;

extern void rtc_init(void);
extern void ex2_hal_uninit(void);
//=============================================================================;
// 代码区                                                                      ;
//=============================================================================;


/**
 * @brief 24g rf以及RTC初始化
 * 
 */
void mouse_24g_init(void)
{
    mouse_periph_wakeup_enable(WAKEUP_ALL_DISABLE);

    drv_rf24g_init();
    rf_mode_convert(iRF_MODE_SYNC);
    rtc_init();

    NVIC_EnableIRQ(RTC_IRQn);
    rtc_reload_value = drv_rtc_read(OM_RTC) + iTICK_INIT_VALUE;
    drv_rtc_set_alarm0(rtc_reload_value);

    __enable_irq();

    is_app_enable = APP_ENABLE;             /* 使能24G 驱动模式，如果不配驱动，这里配 APP_DISABLE */
    /* APP_ENABLE模式下，只能配OM6239的接收器，配合驱动使用，不配驱动 则可以兼容6239/6209的接收器 */
}

/**
 * @brief 24G主循环
 * 
 * @return none
 */
__RAM_CODE int main_24g(void)
{
    while(1)
    {
        if(0 != (sys_ctrl&bscan_flag))
        {
            key_process();
            drv_wdt_keep_alive(OM_WDT);
            mode_led_hint();
            if(iRF_MODE_NORMAL == rf_mode_type)
            {
                sensor_xy_scan();       
                ledc_polling();
				define_key_process();    
            }
            else
            {
                bat_ind_process();
                logo_process();
            }
            sys_ctrl &= ~bscan_flag;
            if(iRF_MODE_NORMAL == rf_mode_type)
            {
                if(ble_sleep_1_time_tbl[sleep_time_24g&0x07] < (drv_rtc_read(OM_RTC)-rtc_init_value))
                {   
                    if(!USB_5V_PIN)     /* USB5V接入不休眠 */
                        sleep_process();
                }
            }
            else
            {
                sleep_process();
            }
        }

        switch(rf_mode_type)
        {
            case iRF_MODE_CONNECT:          /* 24G配对 */
                rf_connect_process();

                break;
            case iRF_MODE_SYNC:             /* 24G搜索接收器 */
                rf_sync_process();

                break;
            case iRF_MODE_NORMAL:           /* 24G正常连接发送数据 */
                rf_nromal_process();

                break;
        }

        scan_mode_swtich(iMODE_CHECK_DELAY);        /* 模式切换 */
        if(true == bmode_swtich_valid)
        {
            rf_mode_convert(iRF_MODE_NONE);
            ex2_hal_uninit();
            break;              // 切换模式，返回主程序
        }
    }

    return 1;
}

/**
 * @brief 24G RTC中断回调函数
 * 
 * @return none
 */
__RAM_CODE void RTC_IRQHandler_24G(void)
{   
    switch(work_mode)
    {   
        case iMCU_MODE_NORMAL:
            sys_tick_count++;
            if(iRF_MODE_NORMAL == rf_mode_type)
            {
                uint32_t i;
                while (!OM_RTC->CNT_VALID);
                i = OM_RTC->CNT;
                rtc_reload_value += iTICK_INIT_VALUE;
                while(1)
                {
                    if(rtc_reload_value >= (i+5))
                        break;
                    rtc_reload_value += iTICK_INIT_VALUE;
                    if(0 == (sys_tick_count&0x01))
                    {
                        freq_index++;
                        rf_work_mode = iRF_WORK_TX0;
                    }
                    sys_tick_count++;
                }
                while (0 == (OM_RTC->CR & RTC_CR_ALARM0_WRITE_STATUS_MASK));
                OM_RTC->ALARM0 = rtc_reload_value;

                if(0 == (sys_tick_count&0x01))
                {
                    freq_index++;
                    freq_index&=0x1F;
                    rf_work_mode = iRF_WORK_TX0;
                    if(1 == (freq_index&0x03))
                    {
                        rf_rsp_time_count++;
                        if((iRF_RSP_CYCLE_COUNT <= rf_rsp_time_count))
                        {
                            rf_ctrl_reg |= brf_data_rx;
                        }
                    }
                }
                if(iREPORT_125 == report_24g)
                {
                    if(0 == (sys_tick_count&0x03))
                        sys_ctrl |= bscan_flag;
                }
                else if(iREPORT_250 == report_24g)
                {
                    if(0 == (sys_tick_count&0x01))
                        sys_ctrl |= bscan_flag;
                }
                else
                {
                    sys_ctrl |= bscan_flag;
                }
            }
            else
            {
                while (!OM_RTC->CNT_VALID);
                rtc_reload_value = OM_RTC->CNT + iTICK_INIT_VALUE_EX;
                while (0 == (OM_RTC->CR & RTC_CR_ALARM0_WRITE_STATUS_MASK));
                OM_RTC->ALARM0 = rtc_reload_value;

                rf_work_mode = iRF_WORK_TX0;
                if(0 == (sys_tick_count&0x01))
                {
                    sys_ctrl |= bscan_flag;
                }
            }
            break;
        case iMCU_MODE_SLEEP:
            while (!OM_RTC->CNT_VALID);
            rtc_reload_value = OM_RTC->CNT + iTICK_INIT_SLEEP;
            while (0 == (OM_RTC->CR & RTC_CR_ALARM0_WRITE_STATUS_MASK));
            OM_RTC->ALARM0 = rtc_reload_value;

            sys_ctrl |= bscan_flag;

            break;
        default:
            while (!OM_RTC->CNT_VALID);
            rtc_reload_value = (OM_RTC->CNT+iTICK_INIT_VALUE_EX);
            while (0 == (OM_RTC->CR & RTC_CR_ALARM0_WRITE_STATUS_MASK));
            OM_RTC->ALARM0 = rtc_reload_value;

            sys_tick_count++;
            if(0 == (sys_tick_count&0x01))
                sys_ctrl |= bscan_flag;
            break;

    }
}

/** @} */

