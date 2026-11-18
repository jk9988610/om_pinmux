/* ----------------------------------------------------------------------------
 * Copyright (c) 2020-2030 OnMicro Limited. All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without modification,
 * are permitted provided that the following conditions are met:
 *   1. Redistributions of source code must retain the above copyright notice,
 *      this list of conditions and the following disclaimer.
 *   2. Redistributions in binary form must reproduce the above copyright notice,
 *      this list of conditions and the following disclaimer in the documentation
 *      and/or other materials provided with the distributon.
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
 * @file     main.c
 * @brief    main entry
 * @date     18 Sept. 2023
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
#include "om_driver.h"
#include "evt.h"
//#include "pm.h"

#include "mouse.h"
#include "ex2_app_mouse.h"
#include "main_usb.h"
#include "main_24g.h"
#include "ex2_hal.h"

//-----------------------------------------------------------------------------;
//常量定义区
//

//-----------------------------------------------------------------------------;
//变量定义区
//
volatile uint8_t  ble_24g_ctrl;
volatile uint8_t  sys_ctrl;

device_type_t     device_type;
device_type_t     bt_index;           // 硬件切换模式，蓝牙多通道情况会使用到

volatile uint32_t sys_tick_count;
uint32_t          rtc_init_value;
uint32_t          rtc_cur_value;
uint32_t          rtc_temp_value;

//----------------------------------------------
// 鼠标键盘数据相关寄存器
//
uint8_t           m_data_flag;

uint8_t           m_tx_count;
uint8_t           key_tx_count;
uint8_t           mmk_tx_count;
uint8_t           def_tx_count;     /*  */

uint8_t           mouse_data_key;

uint8_t           mouse_data_z;
uint8_t           std_key[8];
uint8_t           mmk_data_l;
uint8_t           mmk_data_h;
uint8_t           wheel_data;
//
//----------------------------------------------
// 鼠标ID
//
uint8_t                     mouse_bd_addr[6];

//-----------------------------------------------------------------------------;
//外部引用区
//
extern void rf_freq_make(void);
extern pmu_lpm_t pm_checker_callback(void);
extern uint8_t reset_connect;
extern void rf_fcc_key_ctrl();

//----------------------------------------------------------------------------
//表格定义区
//

//============================================================================;
// 代码区                                                                     ;
//============================================================================;

/**
 * @brief 硬件编码器初始化 
 * 
 */
void encoder_init(void)
{
    drv_pmu_power_set(PMU_POWER_ID_RTC2M, PMU_POWER_ON);
    drv_encoder_init();
}

/**
 * @brief 外设唤醒设置
 * 
 * @param mask 不同休眠等级
 */
void mouse_periph_wakeup_enable(uint8_t mask)
{
    OM_CRITICAL_BEGIN();
    drv_gpio_set_trig(OM_GPIO0, PIN_WAKE_UP_MASK, GPIO_TRIG_NONE);
    NVIC_ClearPendingIRQ(WAKEUP_GPIO0_IRQn);
    drv_pmu_clear_wakeup();

    if(mask & WAKEUP_BTN_MASK) { /* button only faling edge wakeup*/
        drv_gpio_set_trig(OM_GPIO0, PIN_WAKE_UP_MASK, GPIO_TRIG_FALLING_EDGE);
        KEY_PIN_WAKE_UP_EN();
        NVIC_SetPriority(WAKEUP_GPIO0_IRQn, RTE_GPIO0_IRQ_PRIORITY);
        NVIC_EnableIRQ(WAKEUP_GPIO0_IRQn);
    }
    else {
        KEY_PIN_WAKE_UP_DIS();
        NVIC_DisableIRQ(WAKEUP_GPIO0_IRQn);
    }

    if(mask & WAKEUP_SENSOR_MASK) {
        OM_SENSCAN->IER |= SENSACN_IER_SCAN_DONE_MASK;
    }
    else {
        OM_SENSCAN->IER &= ~SENSACN_IER_SCAN_DONE_MASK;
    }

    if(mask & WAKEUP_WHEEL_MASK) {
        OM_ENCODER->EN |= (ENCODER_EN_INTERRUPT_EN_MASK|ENCODER_EN_WAKEUP_EN_MASK);
    }
    else {
        OM_ENCODER->EN &= ~(ENCODER_EN_INTERRUPT_EN_MASK|ENCODER_EN_WAKEUP_EN_MASK);
    }
    OM_CRITICAL_END();
}

/**
 * @brief main函数入口
 * 
 * @return int 
 */
int main(void)
{
    /* Initializing RCC */
    drv_rcc_init();

    drv_wdt_init(OM_WDT);
    drv_wdt_keep_alive(OM_WDT);

    /* 获取蓝牙地址(2.4G同步地址），生产时烧录 */
    drv_flash_read(CFG_START_SYNC_WORD_ADDR, mouse_bd_addr+2, 4);
    mouse_bd_addr[0] = iVERSION_ID_L;
    mouse_bd_addr[1] = iVERSION_ID_H;
#if (0)
    mouse_bd_addr[2]=0x92;                      // 调试使用，固定ID，在接收器也固定ID
    mouse_bd_addr[3]=0x22;                      // 直接通信避免串码
    mouse_bd_addr[4]=0x02;
#endif

    #if (RTE_ICACHE)
    drv_icache_enable();
    #endif

    periph_gpio_init();                                 /* GPIO初始化 */

    mouse_periph_wakeup_enable(WAKEUP_ALL_DISABLE);     /* 正常工作模式下不允许任何IO口唤醒 */
    ble_24g_ctrl &= ~bom6239_sync_ok;
    rtc_init_value = 0;

    encoder_init();                                     /* 编码器初始化，使用硬件扫描 */
    senscan_init();                                     /* SENSOR初始化，使用硬件扫描 */
    bat_init();

    laod_flash_cfg();                                   /* 加载FLASH配置数据 */
    pwm_init();
    scan_mode_swtich(iMODE_CHECK_POWERUP);              /* 确认当前的模式 */

    if((RCC_RST_TYPE_POWER_ON == (OM_RCC->RSTCTRL & 0x07))      
        || (RCC_RST_TYPE_WATCH_DOG == (OM_RCC->RSTCTRL & 0x07))
        || (iSCRATCH_BOOT_POWER == OM_PMU->SW_RSVD7))
    {
#if (0)                                           /* 调试的时候一定要打开，不然芯片成砖 */
        while(1)
        {
            key_io_scan();
            if(0==(key_status&(1<<0)))
                break;
        }
#endif
        sys_ctrl = 0;
        OM_PMU->SW_RSVD7 = 0;
        OM_RCC->CLKGATE &= ~RCC_DEV_CLK_GATE_SWD_CLK_GATE_MASK;     /* 关掉SWD接口之后无法通过KEIL烧录，需注意调试时候打开上面的WHILE(1) */
        rf_fcc_key_ctrl();
        sensor_type_check();
        OM_PMU->SW_RSVD1 = (device_type&PMU_SW_RSVD1_RF_MDOE_MASK);
        OM_PMU->SW_RSVD1 |= (sensor_type<<8);
        OM_PMU->SW_RSVD1 |= ((sensor_status_reg&0x0F)<<24);

        OM_PMU->SW_RSVD2 = iSEARCH_SYNC_WORD;
        sync_word = iSEARCH_SYNC_WORD;
        rf_ctrl_reg = (bsearch_dongle|brf_sync_time|brf_sync_status);

        sys_tick_count = 0;
        ble_24g_ctrl &= ~bom6239_conning;
        OM_PMU->SW_RSVD1 &= ~RSVD1_RF_CONN_EN;
    }
    else                                                            /* 软复位 */
    {
soft_reset_process:
        sys_ctrl |= bmcu_reset;

        OM_RCC->CLKGATE &= ~RCC_DEV_CLK_GATE_SWD_CLK_GATE_MASK; // disable jtag
        sensor_status_reg = ((OM_PMU->SW_RSVD1&PMU_SW_RSVD1_SENSOR_INFO_MASK)>>24);
        sensor_type = ((OM_PMU->SW_RSVD1&PMU_SW_RSVD1_SENSOR_MASK)>>8);

        ble_24g_ctrl &= ~bom6239_conning;
        if(OM_PMU->SW_RSVD1 & RSVD1_RF_CONN_EN)
            ble_24g_ctrl |= bom6239_conning;
        OM_PMU->SW_RSVD1 &= ~RSVD1_RF_CONN_EN;

        sensor_status_reg |= bsensor_sleep;
        sensor_dat_format();
        sensor_wakeup();
        dpi_value = 0xFF;
        sensor_set_dpi();
        if(iDEVICE_TYPE_24G == device_type)
        {
            if(iSEARCH_SYNC_WORD == OM_PMU->SW_RSVD2)               /* RF24G - 搜索接收器 */
            {
                rf_ctrl_reg |= (bsearch_dongle|brf_sync_time|brf_sync_status);
                sync_word = iSEARCH_SYNC_WORD;
            }
            else
            {
                rf_ctrl_reg |= (brf_sync_time|brf_sync_status);     /* RF24G - 回连接收器 */
                sync_word = OM_PMU->SW_RSVD2;
                rf_freq_make();
            }
        }
    }
    drv_senscan_mode_select(OM_SENSCAN, SENSCAN_MODE_SCAN);
    drv_senscan_control(OM_SENSCAN, SENSCAN_CONTROL_SCAN_MODE_SEL, (void*)SENSCAN_SCAN_MODE_CONTINUOUS);
    register_set1(&(OM_SENSCAN->CSR), SENSACN_CSR_SCAN_STOP_MASK);
    while(OM_SENSCAN->CSR & SENSACN_CSR_SCAN_EN_MASK);
    extern void power_check();              
	power_check();                                                  /* 开机检测低压关机 */
    while(1)
    {   
        sys_tick_count = 0;
        bmode_swtich_valid = false;
        rtc_init();
		b24g_nromal = false;
        logo_cfg(iLED_CFG_POWER_ON);
        ind_sleep();
        if(iDEVICE_TYPE_USB == device_type)                         /* USB模式 */
        {
            DRV_RCC_CLOCK_ENABLE(RCC_CLK_RF, 1U);
            mouse_usb_init();
            main_usb();
        }
        else if(iDEVICE_TYPE_24G == device_type)                    /* 24G模式 */
        {
            mouse_24g_init();
            mMCU_MODE_NORMAL;
            main_24g();
        }
        else //if(iDEVICE_TYPE_BT2 >= device_type)                  /* BLE模式 */
        {
            device_type &= 0x03;
            evt_init();
            flash_load_ble_addr();                                  /* 加载蓝牙地址 */
            if(0xFF == ble_id[device_type])                         /* 无效ID，则默认进入配对状态 */
                ble_24g_ctrl |= bom6239_conning;            
            if(reset_connect & (1<<(uint8_t)device_type))
                ble_24g_ctrl |= bom6239_conning;
            if(ble_24g_ctrl&bom6239_conning)                        /* 蓝牙配对模式配置 */
            {                                   
                ble_24g_ctrl &= ~bom6239_conn_ok;
                ble_id[device_type]++;
                if(0xFF == ble_id[device_type])
                    ble_id[device_type]++;
            }
            mouse_bd_addr[4] = ble_id[device_type];                 /* 蓝牙地址索引配置 */
            mouse_bd_addr[5] &= 0xFC;
            mouse_bd_addr[5] |= device_type;                        /* 通道参数配置 */

            ex2_app_mouse_ble_init();                               /* 蓝牙广播初始化 */
            while(1)
            {
                evt_schedule();                                     /* 进入BLE事件调度循环 */
                if(true == bmode_swtich_valid)
                {
                    ex2_hal_uninit();
                    break;                                          /* 切换模式，返回主程序 */
                }

                OM_CRITICAL_BEGIN();
                // if no event, do power manage
                if (evt_get_all() == 0U)
                {
                    drv_pmu_set_low_power_mode(pm_checker_callback());
                }
                OM_CRITICAL_END();
            }
        }
    }
}


/** @} */

