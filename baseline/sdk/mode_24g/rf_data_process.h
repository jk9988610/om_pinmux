/**
 * @file rf_data_process.h
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2025-05-23
 * 
 * @copyright Copyright (c) 2025
 * 
 */

#ifndef _RF_DATA_PROCESS_H_
#define _RF_DATA_PROCESS_H_

//=============================================================================;
// 配置引用区                                                                  ;
//=============================================================================;

//-----------------------------------------------------------------------------;
// 配置常量定义区
//
#define iCONNECT_TIME_COUNT     234             // 234*16*4ms = 15s
#define iKEY_TX_TIMES           4

//-----------------------------------------------------------------------------;
// 配置区
//

//=============================================================================;
// 外部定义内部引用区                                                          ;
//=============================================================================;

//-----------------------------------------------------------------------------;
// 外部寄存器引用
//

//-----------------------------------------------------------------------------;
// 外部函数引用
//

//=============================================================================;
// 内部定义外部引用区                                                          ;
//=============================================================================;

//-----------------------------------------------------------------------------;
// 寄存器引用
//
extern uint32_t m24g_connect_count;
//-----------------------------------------------------------------------------;
// 函数引用
//
extern void clr_mouse_data(void);

extern void rf_tx0_idle_callback(void);
extern void rf_tx0_irq_callback(void);
extern void rf_tx1_idle_callback(void);
extern void rf_tx1_irq_callback(void);

extern void rf_wakeup_usb_callback();
extern bool rf_check_dongle_id_res();
extern void rf_sync_ok_process(void);
extern void rf_lost_connection();

extern void rf_conn_data_process(void);
extern void rf_normal_mode_sleep(void);
extern void rf_app_get_device_info();
extern void rf_app_get_online_info();
extern void rf_app_set_cmd();
extern void rf_respone_callback(uint8_t *RxPayload);
extern bool is_rf_tx_time_enough();
extern void rf_connect_get_device_info();
//
//-----------------------------------------------------------------------------;

#endif
