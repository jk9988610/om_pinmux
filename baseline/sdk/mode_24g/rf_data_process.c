/**
 * @file rf_data_process.c
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2025-05-23
 * 
 * @copyright Copyright (c) 2025
 * 
 */

#include "main_24g.h"
#include "usb_cfg_info.h"
#include "rf_data_process.h"

uint32_t m24g_connect_count;
extern bool is_app_enable;

//外部函数
extern void hid_get_fw_mode_info(void);
extern void hid_process();
//-----------------------------------------------------------------------------;
//常量定义区
//

//----------------------------------------------------------------------------
//变量定义区
//


//----------------------------------------------------------------------------
//表格定义区
//

//============================================================================;
// 代码区                                                                     ;
//============================================================================;

/**
 * @brief 正常连接之后需要把SENSOR数据清空
 * 
 */
void clr_mouse_data(void)
{
    mouse_x_1 = 0;
    mouse_y_1 = 0;
    mouse_xy_1 = 0;

    mouse_x_2 = 0;
    mouse_y_2 = 0;
    mouse_xy_2 = 0;

    mouse_x_3 = 0;
    mouse_y_3 = 0;
    mouse_xy_3 = 0;
}

/**
 * @brief 对码判断函数，在进入配对模式之后，会持续在此判断配对结果
 * 
 */
void rf_conn_data_process(void)
{
    if(0==(ble_24g_ctrl&bom6239_conn_ok))               /* 配对中 */
    {   
        if(mMS_TO_TICK(60*1000) > (drv_rtc_read(OM_RTC)-m24g_connect_count))        /* 配对超时判断 */
        {                                 
            return;
        }
        ble_24g_ctrl &= ~bom6239_conning;                   /* 配对超时，并未在配对时间中配对接收器 */
        rf_ctrl_reg |= (brf_sync_time|brf_sync_status);
        rf_mode_convert(iRF_MODE_SYNC);
        ind_sleep();
    }
    else
    {
        ind_sleep();
        rf_ctrl_reg |= (bsearch_dongle|brf_sync_time|brf_sync_status);
        sync_word = iSEARCH_SYNC_WORD;
        rf_mode_convert(iRF_MODE_SYNC);                 /* 配对成功，切换至同步模式搜索接收器 */
    }
}


/**
 * @brief RF24G，通知接收器通过USB唤醒电脑，通知成功后会调用此函数
 * @note 
 * 
 */
void rf_wakeup_usb_callback()
{

}

/**
 * @brief RF24G,搜索到接收器之后，判断ID，并返回结果
 * 
 * @return 0:并非当前配对的接收器 
 *         1:与该接收器连接
 */
bool rf_check_dongle_id_res()
{
    if((rf_data_fifo[0] != mouse_bd_addr[2])
        || (rf_data_fifo[1] != mouse_bd_addr[3])
        || (rf_data_fifo[2] != mouse_bd_addr[4]))           /* 判断配对的DONGLE */
    {
        if((rf_data_fifo[3] !=iRADIO_SYNC_WORD_0)       
            || (rf_data_fifo[4] != iRADIO_SYNC_WORD_1)
            || (rf_data_fifo[5] != iRADIO_SYNC_WORD_2)
            || (rf_data_fifo[6] != iRADIO_SYNC_WORD_3)) /* 判断万能接收器 */
        {           // 判断广播模式
            return 0;
        }
    }

    return 1;
}

/**
 * @brief RF24G，跟接收器同步成功之后，会调用此函数
 * @note 
 * 
 */
void rf_sync_ok_process(void)
{
    if(iMCU_MODE_NORMAL != work_mode)
        logo_cfg(iLED_CFG_IDLE);
    mMCU_MODE_NORMAL;
    clr_mouse_data();

    if(adv_cfg_value&(1<<5))
        report_24g = iREPORT_125;
    else
        report_24g = ((report_dpi[key_mode]>>4)&0x03);

    if(sensor_status_reg & bsensor_sleep)
        sensor_wakeup();

    m_tx_count = 0;
    drv_encoder_control(OM_ENCODER, ENCODER_CONTROL_START, NULL);

    drv_senscan_mode_select(OM_SENSCAN, SENSCAN_MODE_SCAN);
    drv_senscan_control(OM_SENSCAN, SENSCAN_CONTROL_SCAN_MODE_SEL, (void*)SENSCAN_SCAN_MODE_CONTINUOUS);
    register_set1(&(OM_SENSCAN->CSR), SENSACN_CSR_SCAN_STOP_MASK);
    while(OM_SENSCAN->CSR & SENSACN_CSR_SCAN_EN_MASK);

    bscan_sensor_en = 1;
    drv_senscan_stop();
    sensor_scan_freq = mSEN_SCAN_US(1000);
    drv_senscan_begin();

    if(true == b24g_nromal)
    {
        ble_24g_ctrl &= ~bom6239_sync_ing;
    }

#if !BOARD_LED_INDICATOR_ONLY
    /* hint_only：2.4G 连接成功不闪 RGB，只让 mode_led_hint 管模式灯（S205 [no-24g-rgb]） */
    if(!brf_24g_reconnect)      /* 操作FLASH导致的回连，不指示 */
    {
        ind_val_t ind_val = {
            .ind_color = IND_RED,
            .ind_times = IND_TIMES_ONE,
            .ind_on_time = BLE_RECONNECT_TIME_ON,
            .ind_off_time = BLE_RECONNECT_TIME_OFF,
        };
        ind_config(&ind_val);
    }
#endif
    brf_24g_reconnect = 0;

    if(OM_PMU->SW_RSVD3 == iMODE_24G_RESET_VAL)     /* 24G模式下复位之后回连，先发设备信息通知驱动 */
    {
        OM_PMU->SW_RSVD3 = 0;
        def_tx_count = 7;
    }

    ble_24g_ctrl |= bom6239_sync_ok;
    rtc_init_value = drv_rtc_read(OM_RTC);
}


/**
 * @brief RF24G，连接成功后会交换版本地址信息。
 * 
 */
void __attribute__((noinline)) rf_device_info(void)
{
    rf_data_fifo[0] = (iRF_M_TYPE_REQUST | 7);
    rf_data_fifo[1] = mouse_bd_addr[2];
    rf_data_fifo[2] = mouse_bd_addr[3];
    rf_data_fifo[3] = mouse_bd_addr[4];
    rf_data_fifo[4] = mouse_bd_addr[5];
    rf_data_fifo[5] = iVERSION_ID_L;
    rf_data_fifo[6] = iVERSION_ID_H;
    rf_data_fifo[7] = (sensor_type&0x1F);
}


/**
 * @brief 发射端由于持续收不到应答包导致与接收器断联后，会调用此函数
 * 
 */
void rf_lost_connection()
{

}

/**
 * @brief RF24G，正常发射数据，空闲时会调用对应函数，时序如下：
 ** --------------------------------
 ** |    2ms   |    2ms   |  周期   |
 ** |    TX0   |    TX1   |  发射   |
 ** |    IRQ   |    IRQ   |  中断   |
 ** | TX0 IDLE | TX1 IDLE |  空闲   |
 ** --------------------------------
 *@note 在空闲周期进行指示灯或者LOGO灯处理，时间不能太长
 */
void rf_tx0_idle_callback(void)
{
    lvd_scan_count++;
    if(0==(lvd_scan_count&0x07))
        bat_ind_process();                    
}
void rf_tx0_irq_callback(void)
{
    lvd_scan_count++;
    if(0==(lvd_scan_count&0x07))
        bat_ind_process();
}
void rf_tx1_idle_callback(void)
{
    if(1==(lvd_scan_count&0x03))
        logo_process();
}
void rf_tx1_irq_callback(void)
{
    if(1==(lvd_scan_count&0x03))
        logo_process();
}

/**
 ** RF空闲周期会执行该函数，如果有PWM等外设运行，则进IDLE，否则进IDLE
 */
__RAM_CODE void rf_normal_mode_sleep(void)
{
    OM_CRITICAL_BEGIN();
    if(0x00000000 == OM_PWM->PWMCON)
        drv_pmu_set_low_power_mode(PMU_LPM_STOP1);
    else
        drv_pmu_set_low_power_mode(PMU_LPM_IDLE);
    OM_CRITICAL_END();
}


/**
 ** 驱动需要获取设备信息时，会调用这个函数
 ** 
 */
void rf_app_get_device_info()
{
    hid_get_fw_mode_info();
}

/**
 ** 驱动需要确认设备是否在线时，会调用这个函数。
 ** 如果鼠标上报数据，则驱动会认为鼠标在线，如果鼠标并未上报任何数据，
 ** 此时每隔2~3个应答周期，即300ms左右，鼠标会上报一次在线信息，超过1S未上报，
 ** 则驱动会判断鼠标离线。
 */
void rf_app_get_online_info()
{
    rf_data_fifo[0] = (iRF_M_TYPE_REQUST | 7);
    rf_data_fifo[1] = mouse_bd_addr[2];
    rf_data_fifo[2] = mouse_bd_addr[3];
    rf_data_fifo[3] = mouse_bd_addr[4];
    rf_data_fifo[4] = mouse_bd_addr[5];
    rf_data_fifo[5] = iVERSION_ID_L;
    rf_data_fifo[6] = iVERSION_ID_H;
    rf_data_fifo[7] = (sensor_type&0x1F);

    if(is_app_enable)
    {
        rf_data_fifo[8] = bat_value;        						/* 通知鼠标的电量信息 */
        if(USB_5V_PIN)
            rf_data_fifo[8] |= (1<<7);                              /* 鼠标是否处于充电状态 */
        rf_data_fifo[9] = 0x80;                                     /* 鼠标在线标志位 */
        //if(adv_cfg_value&iXY_OPTIMIZE)                            /* 鼠标线性优化，默认开启 */
            //rf_data_fifo[9] |= 0x40;
        rf_data_length = iRF_MK_LENGTH_10B;
    }
    else
    {
        rf_data_fifo[0] = (iRF_M_TYPE_REQUST | 7);
        rf_data_length = iRF_MK_LENGTH_8B;
    }
}

/**
 ** 驱动下发命令，命令格式与USB一致
 */
void rf_app_set_cmd()
{
    hid_process();
}

/**
 ** RF应答周期回调
 */
void rf_respone_callback(uint8_t *RxPayload)
{

}

/**
 ** 由于带2.4G驱动，对于协议的时序要求比较严格，目前2M的速率下，2.4G模式下，
 ** 请在700us里边执行完所有的任务。如果有一些任务比如说LOGO灯扫描，或者说
 ** 并不需要在RF发数据之前执行的，请放到rf的tx或者idle回调中，目前设置的
 ** RF TX冗余时间是1300us，即1.3ms,留给应用端执行所有任务的时间是700us
 */
bool is_rf_tx_time_enough()
{
    return (iRF_TX_MAX > (OM_RTC->ALARM0-drv_rtc_read(OM_RTC)))?(false):(true);
}


/**
 * @brief  interactive device info
 * @note   
 * @retval None
 */
void rf_connect_get_device_info()
{
    rf_device_info();
    if(0!=is_app_enable)
    {
        rf_data_fifo[10] = iPROJECT_ID_2;
        rf_data_fifo[11] = iPROJECT_ID_3;
        rf_data_fifo[12] = iPROJECT_ID_0;
        rf_data_fifo[13] = iPROJECT_ID_1;
        rf_data_fifo[14] = 0x04;
        rf_data_fifo[15] = iAPP_ID_H;
    }
    else
    {
        rf_data_fifo[0] = iRF_M_TYPE_CONN_RSP;
    }
}

void rf_tx_data_callback(uint8_t *TxPayload, uint8_t lenght)
{

}
