/* ----------------------------------------------------------------------------
 * Copyright (c) 2020-2030 OnMicro Limited. All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without modification,
 * are permitted provided that the following conditions are met:
 *   1. Redistributions of source code must retain the above copyright notice,
 *      this list of conditions and the following disclaimer.
 *   2. Redistributions in binary form must reproduce the above copyright notice,
 *      this list of conditions and the following disclaimer in the documentation
 *      and/or other materials provided with the distribution.
 *   3. Neither the name of OnMicroelectronics nor the names of its contributors
 *      may be used to endorse or promote products derived from this software
 *      without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 * CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 *
 * -------------------------------------------------------------------------- */

/**
 * @file     mouse_sw.c
 * @brief    ble mouse sensor & wheel scan use io simulate by hardware
 * @date     20 JUN 2024
 * @author   OnMicro SW Team
 *
 * @version
 * Version 1.0
 *  - Initial release
 *
 * @{
 */

/*******************************************************************************
 * INCLUDES
 */
#include <stdbool.h>
#include <stdio.h>
#include "om_driver.h"
#include "ex2_app_mouse.h"
#include "mouse.h"
#include "ex2_api.h"
#include "ex2_hal.h"
#include "main.h"
#include "led.h"
#include "lvd.h"
#include "flash_process.h"
#include "userdefined_key.h"
#include "time_delay.h"

#include "usb_cfg_info.h"

/*******************************************************************************
 * CONST & VARIABLES
 */
 ms_sleep_level_t ms_sleep_level = MS_SLEEP_LEVEL0;
static bool is_timer_started = 0;
 char mouse_name[MOUSE_NAME_MAX_LEN] =  "CH-04 Bt1";             /* 蓝牙名称 配置 */

uint8_t                     ble_interval;
bool                        bradio_receive;

extern bool                 bperiph_int;
extern uint32_t             adv_interval_ms;
extern uint8_t              reset_connect;


/**
 * @brief 蓝牙电源管理检测回调函数，在进入休眠之前会回调该函数，判断接下来的电源管理。
 * 
 * 
 * @return pmu_lpm_t 
 */
pmu_lpm_t pm_checker_callback(void)
{
    if((ms_sleep_level == MS_SLEEP_LEVEL0) && is_timer_started)
    {
        return PMU_LPM_IDLE;
    }
    else if(ms_sleep_level < MS_SLEEP_LEVEL2)                /* SLEEP LEV 1*/
    {
        if ((ex2_stk_sleep_duration_get() > 10))        /* 距下次唤醒时间充足时尝试进入STOP1，否则不走该深睡分支 */
        {
            if(0x00000000 == OM_PWM->PWMCON)
                return PMU_LPM_STOP1;                   /* PWM开启的情况下 不能进入STOP1，只能IDLE */
            else
                return PMU_LPM_IDLE;
        }
    }
    else                                                /* SLEEP LEV 2 */
    { 
        ex2_stk_uninit();
        pwm_off();
        sensor_wakeup();
        sensor_deepsleep_wakeup();
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
        ledc_polling();
        delayms(500);
        charg_led_sleep_process();
        mouse_periph_wakeup_enable(WAKEUP_SLEEP_LEVEL2);
        drv_pmu_set_low_power_mode(PMU_LPM_DEEP_SLEEP);
        while(1);
    }

    return PMU_LPM_IDLE;
}

extern bool ex2_hid_tx_notification_mouse(uint8_t *buf);
extern bool ex2_hid_tx_notification_keyboard(uint8_t *buf);
extern bool ex2_hid_tx_notification_consumer_control(uint8_t *buf);
extern bool profile_bas_tx_notification(uint8_t level);

void ex2_app_mouse_stop_led_scan_time(void)
{
    if(is_timer_started)
    {
        is_timer_started = 0;
        OM_CRITICAL_BEGIN();
        OM_RTC->CR &= ~RTC_CR_TICK_WAKEUP_EN_MASK;
        drv_rtc_set_tick_hz(OM_RTC, 0);
        drv_rtc_control(OM_RTC, RTC_CONTROL_TICK_INT_DISABLE, NULL);
        OM_CRITICAL_END();
    }
}

void ex2_app_mouse_start_led_scan_time(void)
{
    if(!is_timer_started)
    {
        is_timer_started = 1;
        OM_CRITICAL_BEGIN();
        drv_rtc_set_tick_hz(OM_RTC, 500);
        drv_rtc_control(OM_RTC, RTC_CONTROL_TICK_INT_EN, NULL);
        OM_CRITICAL_END();
    }
}

/**
 * @brief BLE APP外设扫描函数
 * @note  设备端正常配对连接成功后，会每7.5ms进入该函数扫描外设
 * 
 * @return __RAM_CODE 
 */
 uint8_t ex2_app_mouse_scan(void)
{
    uint8_t temp_buff[8];
        static bool has_enter_sleep_1 = false;
    if (!hid_notification_is_enabled()) {
        return 0;
    }
	ble_24g_ctrl |= bom6239_sync_ok;            /* 正常连接工作标志位 */

    key_process();
    if(mouse_x|mouse_y)
        m_tx_count = 3;

    if(MS_SLEEP_LEVEL0 == ms_sleep_level)
    {
        lvd_scan_count++;
        if(0==(lvd_scan_count&0x01))
            bat_ind_process();                  // 15ms
        logo_process();
        define_key_process();
        mode_led_hint();
        if(has_enter_sleep_1)
        {   
            has_enter_sleep_1 = 0;
            ledc_cmd(Cmd_Init,0);
        }
        else
        {
            ledc_polling();
        }
    }
    else
    {
        has_enter_sleep_1 = 1;
        ledc_cmd(Cmd_Power_Set,(void*)POWER_OFF);
        ind_sleep();
    }

    scan_mode_swtich(iMODE_CHECK_DELAY);

    if(0!=key_tx_count)                     /* 键盘数据发送 */
    {
        temp_buff[0] = std_key[0];
        temp_buff[1] = 0;
        temp_buff[2] = std_key[1];
        temp_buff[3] = std_key[2];
        temp_buff[4] = std_key[3];
        temp_buff[5] = std_key[4];
        temp_buff[6] = std_key[5];
        temp_buff[7] = std_key[6];
        if(true == ex2_hid_tx_notification_keyboard(temp_buff))
        {
            rtc_init_value = drv_rtc_read(OM_RTC);
            m_data_flag &= ~bstd_kb_data_send;
            key_tx_count = 0;
        }
        return 1;
    }
    else if(0!=mmk_tx_count)                /* 多媒体数据发送 */
    {
        temp_buff[0] = mmk_data_l;
        temp_buff[1] = mmk_data_h;
        if(true == ex2_hid_tx_notification_consumer_control(temp_buff))
        {
            rtc_init_value = drv_rtc_read(OM_RTC);
            m_data_flag &= ~bmmk_data_send;
            mmk_tx_count = 0;
        }
        return 1;
    }
    else if(false != bbat_update)
    {
        if(true == profile_bas_tx_notification(bat_value))
            bbat_update=false;
        return 1;
    }
    else if(0!=m_tx_count)                  /* 鼠标数据发送 */
    {                                           
        temp_buff[0] = mouse_data_key&0x1F;       // button
        temp_buff[1] = ((mouse_x>>0)&0xFF);       // x
        temp_buff[2] = (((mouse_x>>8)&0x0F)|((mouse_y<<4)&0xF0)); // y
        temp_buff[3] = ((mouse_y>>4)&0xFF);       //
        temp_buff[4] = mouse_data_z;              // wheel
        temp_buff[5] = 0;                         //til
        if(true == ex2_hid_tx_notification_mouse(temp_buff))
        {
            rtc_init_value = drv_rtc_read(OM_RTC);
            m_data_flag &=~(bmouse_data_send);
            mouse_x = 0;
            mouse_y = 0;
            mouse_data_z = 0;
            m_tx_count = 0;
            return 1;
        }
    }
    else
    {
        if(true == bsave_ble_id)            /* 空闲周期存ID */
        {
            bsave_ble_id = false;
            flash_save_ble_addr();
        }
    }
    return 0;
}

extern ex2_gap_ppcp_t       ex2_gap_ppcp_value;
extern mouse_adv_state_t    mouse_state;
extern bool                 bscan_sensor_en;

extern uint16_t ll_ctrl_get_peer_company_id(void);
extern void stk_notify_event_app(uint32_t evt);

/**
 * @brief BLE 事件调度函数
 * 
 * @param events 
 */
void app_ble_evt_dispatch(uint32_t events)
{
    static uint32_t connect_start_time = 0; /* work around intel bluetooth bug */
    if (events & EX2_EVENT_APP_CONNECT_IND) {                                               /* 从机接收到主机的连接请求事件 */
        mouse_periph_wakeup_enable(WAKEUP_ALL_DISABLE);
        drv_rf_set_tx_power(DRV_RF_PA_PWR_0dBm);
        /* stop polling the peripheral*/
        ex2_ll_polling_time_stop();
        connect_start_time = 0;
        ledc_cmd(Cmd_Idle_Cfg,NULL);
    }
    if (events & (EX2_EVENT_APP_SLAVE_TERMINATED)) {
        uint8_t bda[6];
        drv_ble_get_bda(bda);
        /* reset rtc & rf module */
        ex2_hal_uninit();
        /* Avoid conn activites during ms delay. */
        __disable_irq();
        ex2_stk_init(bda);
        mouse_state = MOUSE_LE_STATE_DISCONN;
        ex2_app_mouse_broadcast_fsm();
        __enable_irq();
    }
    if (events & EX2_EVENT_APP_CONN_TIMEOUT) {
        __disable_irq();
        NVIC_SystemReset();
    }

    if(events & EX2_EVENT_APP_MASTER_TERMINATED) {
        ms_sleep_level = MS_SLEEP_LEVEL2;
    }
    if (events & (EX2_EVENT_APP_PAIR_COMPLETED | EX2_EVENT_APP_RECONNECT)) {                 /* SMP密钥分发完成事件/从机回连事件 */
        if (events & EX2_EVENT_APP_RECONNECT) {
            hid_notification_enable(1);
        }
    }
    if (events & EX2_EVENT_APP_VERSION_EXCHANGE) {                                           /* 接收版本交换包，用于协议版本协商或兼容性检查 */
        uint16_t vresion_info = ll_ctrl_get_peer_company_id();

        bradio_receive = false;
        if(vresion_info == 0x0002/* Intel */)  /* work around intel bluetooth bug */
            connect_start_time = drv_rtc_read(OM_RTC);
        else if(vresion_info == 0x01BF)
            bradio_receive = true;
    }
    if (events & EX2_EVENT_APP_CONN_SLAVE) {                                                  /* 从机成功建立连接事件，初始化设备服务 */
        if (!(OM_RTC->INTMASK & RTC_INTMASK_ALARM0_INTRAW_STATUS_MASK)) {
            if (hid_notification_is_enabled())
            {
                ex2_l2cap_update_conn_para(&ex2_gap_ppcp_value);
                ex2_ll_polling_time_start();
                drv_encoder_control(OM_ENCODER, ENCODER_CONTROL_WAKEUP_DISABLE, NULL);
                drv_encoder_control(OM_ENCODER, ENCODER_CONTROL_START, NULL);

                bscan_sensor_en = 1;
                drv_senscan_stop();
                sensor_scan_freq = mSEN_SCAN_US(2500);
                drv_senscan_begin();

                if(ble_24g_ctrl&bom6239_conning)
                {
                    logo_cfg(iLED_CFG_CONNECT_OK);
                    ble_24g_ctrl &= ~bom6239_conning;
                    ble_24g_ctrl |= bom6239_conn_ok;
					if(false == bradio_receive)
                        bsave_ble_id = true;

                    reset_connect &= ~(uint8_t)(1<<device_type);
                }
                ind_val_t ind_val = {
                    .ind_color = IND_GREEN,
                    .ind_times = IND_TIMES_ONE,
                    .ind_on_time = BLE_RECONNECT_TIME_ON,
                    .ind_off_time = BLE_RECONNECT_TIME_OFF,
                };
                if(bt_index != iDEVICE_TYPE_BT0)
                    ind_val.ind_color = IND_BLUE;
                ind_config(&ind_val);
            }
        }
        if(connect_start_time) { /* work around intel bluetooth bug */
            if (EX2_TIME_OLDER_THAN(connect_start_time+EX2_MS_TO_TICK(5000), drv_rtc_read(OM_RTC))) {
                if(!hid_notification_is_enabled()) {
                    connect_start_time = 0;
                    stk_notify_event_app(EX2_EVENT_APP_CONN_TIMEOUT);
                }
            }
        }
    }
    if (events & EX2_EVENT_APP_ADV_TIMEOUT) {                             /* 广播超时事件*/
        if(mouse_state == MOUSE_LE_STATE_STOP) { 
            ms_sleep_level = MS_SLEEP_LEVEL2;
        } else {
            ex2_app_mouse_broadcast_fsm();
        }
    }

    if(events & EX2_EVENT_APP_ADV_EVENT_DONE) {                            /* 一次广播事件结束事件 */
        sys_tick_count += adv_interval_ms;
        ble_24g_ctrl |= bom6239_sync_ing;

        key_process();                          // 广播完成需要扫描一次按键，判断模式切换，进入配对，低电等操作
        sensor_clear_xy();
        bat_ind_process();
        logo_process();
        scan_mode_swtich(iMODE_CHECK_NO_DELAY);
        mode_led_hint();
        ledc_polling();
    }
}

/**
 * @brief BLE RTC中断回调函数
 * @note  连接成功后，协议栈会定时起来一次处理对应事件
 * 
 * @return __RAM_CODE 
 */
__RAM_CODE void drv_rtc_isr_callback(void)
{
    uint32_t rtc_count;

    rtc_count = drv_rtc_read(OM_RTC);
    if(!rtc_init_value)
    {
        rtc_init_value = rtc_count;
    }

    if(MS_SLEEP_LEVEL2 == ms_sleep_level)
    {
        while (0 == (OM_RTC->CR & RTC_CR_ALARM0_WRITE_STATUS_MASK));
        OM_RTC->ALARM0 = (rtc_count + mMS_TO_TICK(16));
        bat_ind_process();
        return;
    }

    if (hid_notification_is_enabled())
    {
        switch (ms_sleep_level)
        {
            case MS_SLEEP_LEVEL0:
                if( ble_sleep_1_time_tbl[sleep_time_ble&0x07] > (rtc_count-rtc_init_value) || (bat_status & bcharging))          /* 正常工作模式,Interval = 7.5MS */
                {
                    ex2_ll_set_next_polling_time(0);
                    sensor_xy_scan();
                }
                else                                                                /* 从正常工作模式切换至SLEEP 1模式 */
                {
                    rtc_init_value = rtc_count;
                    ms_sleep_level = MS_SLEEP_LEVEL1;
                    mouse_periph_wakeup_enable(WAKEUP_SLEEP_LEVEL1);
                    ex2_ll_set_next_polling_time(1);
                    logo_cfg(iLED_CFG_OFF);
                    led_low_off();
                    // ledc_cmd(Cmd_Power_Set,(void*)POWER_OFF);
                    ledc_write0();
                }
                sys_tick_count += 8;
 
                break;
            case MS_SLEEP_LEVEL1:
                if(ble_sleep_2_time_tbl[(sleep_time_ble>>4)&0x07]  > (rtc_count-rtc_init_value))      /* SLEEP MODE 1 : latency = 44 */          
				{
                    ex2_ll_set_next_polling_time(1);
                }   
                else                                                                /* 从SLEEP 1 切换到 SLEEP 2 */
                {   
                    rtc_init_value = rtc_count;
                    ex2_ll_set_next_polling_time(0);
                    ms_sleep_level = MS_SLEEP_LEVEL2;
                }
                sys_tick_count += 300;

                break;
            default:
                break;
        }
    }

    if(ex2_app_mouse_scan())                /* 定时处理外设 */
    {
        if(MS_SLEEP_LEVEL0 != ms_sleep_level)
        {
            ms_sleep_level = MS_SLEEP_LEVEL0;
            mouse_periph_wakeup_enable(WAKEUP_SLEEP_LEVEL0);
        }

        ex2_stk_interrupt();
    }
    else
    {
        if(ms_sleep_level == MS_SLEEP_LEVEL1)
            mouse_periph_wakeup_enable(WAKEUP_SLEEP_LEVEL1);
    }
}


void drv_tick_isr_callback()
{  
    // bat_polling();
}