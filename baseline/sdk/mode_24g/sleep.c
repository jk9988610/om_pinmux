/**
 * @file sleep.c
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
// 常量定义区                                   // 定义只有函数内部使用的常量
//

//-----------------------------------------------------------------------------;
// 变量定义区
//
extern bool                 bperiph_int;
//============================================================================;
// 代码区                                                                     ;
//============================================================================;

/**
 * @brief 休眠函数
 * 
 */
void sleep_process(void)
{
    uint8_t i;
    uint32_t rtc_value,j;
    static uint8_t no_dongle_time_count;
    static bool led_24g_sta;
    static uint8_t  ha_pin_status, bak_ha_pin_status;
    static uint8_t  hb_pin_status, bak_hb_pin_status;
    switch(work_mode)
    {
        case iMCU_MODE_NORMAL:
            if(iRF_MODE_NORMAL == rf_mode_type)
            {                               // RF正常模式,进入一级休眠
                mRF_CE_LOW_IDLE;
                delayus(250);
                mouse_periph_wakeup_enable(WAKEUP_SLEEP_LEVEL1);
                drv_pmu_clear_wakeup();
                mMCU_MODE_SLEEP;
                // ledc_cmd(Cmd_Power_Set,(void*)POWER_OFF);
                ledc_write0();
                drv_senscan_stop();
                sensor_scan_freq = mSEN_SCAN_US(50000);

                drv_senscan_begin();
                drv_senscan_mode_select(OM_SENSCAN, SENSCAN_MODE_SCAN);
                drv_senscan_control(OM_SENSCAN, SENSCAN_CONTROL_SCAN_MODE_SEL, (void*)SENSCAN_SCAN_MODE_CONTINUOUS);
                drv_senscan_control(OM_SENSCAN, SENSCAN_CONTROL_SCAN_EN, NULL);

                NVIC_ClearPendingIRQ(ENCODER_IRQn);
                NVIC_ClearPendingIRQ(SENSCAN_IRQn);

                rtc_cur_value = drv_rtc_read(OM_RTC);
                sys_ctrl |= bscan_flag;
                bperiph_int = 0;
				logo_cfg(iLED_CFG_OFF);
                rtc_value = drv_rtc_read(OM_RTC);
                led_low_off();
                while(1)
                {
                    drv_wdt_keep_alive(OM_WDT);
                    drv_pmu_set_low_power_mode(PMU_LPM_STOP1);          /* 进入STOP1模式，通过SENSOR的MOTION脚或者按键唤醒 */
                    if(bperiph_int)                                     /* 判断是否为中断唤醒，是则退出休眠 */
                        break;

                    if(ble_sleep_2_time_tbl[(sleep_time_24g>>4)&0x07]  < (drv_rtc_read(OM_RTC)-rtc_cur_value))
                        goto MCU_MODE_PD_PRPCESS;                       /* 进入深度休眠 */
                }

                rf_ctrl_reg |= (brf_sync_time|brf_sync_status);
				mMCU_MODE_NORMAL;
                mouse_24g_init();
                ledc_cmd(Cmd_Init,NULL);
            }
            else if(iRF_MODE_SYNC == rf_mode_type)
            {
                if((rf_ctrl_reg & brf_sync_end)
                    &&(0==(rf_ctrl_reg & brf_sync_result)))
                {
                    mMCU_MODE_NO_DONGLE;
                    no_dongle_time_count = 0;
                    b24g_nromal = false;
                    ble_24g_ctrl |= bom6239_sync_ing;
                    if (!(ble_24g_ctrl & bom6239_sync_ok))
                    {
                        // ledc_cmd(Cmd_24G_Reconnect,NULL);
                    }
                }
            }

            break;
        case iMCU_MODE_NO_DONGLE:
            if(rf_ctrl_reg & brf_sync_end)
            {
                if(rf_ctrl_reg & brf_sync_result)
                {
                    rf_ctrl_reg |= brf_sync_time;
                    rf_mode_convert(iRF_MODE_SYNC);
                }
                else
                {
                    key_io_scan();
                    key_status_bak = key_status;
                    rf_ctrl_reg &= ~(brf_sync_time|brf_sync_status);
                    if(3 == no_dongle_time_count)
                    {
                        drv_senscan_stop();
                        sensor_sleep();
                        drv_encoder_control(OM_ENCODER, ENCODER_CONTROL_WAKEUP_DISABLE, NULL);
                        drv_encoder_control(OM_ENCODER, ENCODER_CONTROL_STOP, NULL);
                    }
                    mouse_periph_wakeup_enable(WAKEUP_ALL_DISABLE);
                    led_bt0_off();
                    led_bt1_off();
                    gpio_toggle(LED_MODE_24G_PIN);
                    for(uint32_t i=0; i<500; i++)
                    {   
                        delayus(1000);
                        OM_CRITICAL_BEGIN();
                        ledc_polling();
                        OM_CRITICAL_END();
                        drv_wdt_keep_alive(OM_WDT);
                        

                        if(0==(i&0x01))
                        {
                            
                            key_io_scan();
                            if(key_status_bak != key_status)
                            {
                                no_dongle_time_count=0;
                                rf_ctrl_reg |= (brf_sync_time|brf_sync_status);
                                break;
                            }
                        }
                        else if(1==(i&0x02))
                        {
                            scan_mode_swtich(iMODE_CHECK_NO_DELAY);
                            if(true == bmode_swtich_valid)
                                return;
                        }

                    }
                    no_dongle_time_count++;
                    if(iDEFAULT_NO_DONGLE_MODE_TIME <= no_dongle_time_count)        /* 搜索30次之后，则进入深度休眠 */
                    {
                        goto MCU_MODE_PD_PRPCESS;
                    }

                    mouse_24g_init();
                    sys_ctrl |= bscan_flag;
                }
            }
            break;
        case iMCU_MODE_PD:                  /* 深度休眠 */
MCU_MODE_PD_PRPCESS:
            pwm_off();
            sensor_wakeup();
            sensor_deepsleep_wakeup();
			OM_ENCODER->EN &= ~(ENCODER_EN_INTERRUPT_EN_MASK|ENCODER_EN_WAKEUP_EN_MASK);
            drv_encoder_control(OM_ENCODER, ENCODER_CONTROL_STOP, NULL);
            drv_senscan_stop();
            sensor_sleep();
            DRV_RCC_CLOCK_ENABLE(RCC_CLK_SENSCAN, 0U);
            DRV_RCC_CLOCK_ENABLE(RCC_CLK_ENCODER, 0U);
            // sys_deepsleep_process(); 
            for (size_t i = 0; i < 3; i++)
            {
                ledc_write0();
                delayms(8);
            }
            delayms(100);
            ledc_sleep();
            delayms(500);
            charg_led_sleep_process();
            mouse_periph_wakeup_enable(WAKEUP_SLEEP_LEVEL2);
            drv_pmu_set_low_power_mode(PMU_LPM_DEEP_SLEEP);
            while(1);
            break;
    }
}
