/*******************************************************************************
* Copyright (c) 2013, SHENZHEN OM Co.,LTD.
* All rights reserved.
*
* 文件名称: main.h
*
* 功能说明:
* 修改说明:
*******************************************************************************/
#ifndef __MAIN_H_
#define __MAIN_H_

#include <stdint.h>
#include <stdbool.h>
#include "user_config.h"
#include "mode_ind.h"
//=============================================================================;
// 配置引用区                                                                  ;
//=============================================================================;


//-----------------------------------------------------------------------------;
//配置常量定义区
//
#define RC_CLK        3200UL
//#define RC_CLK      2000000UL
#if(2000000UL == RTC)
#define mRTC_US(x)              (x*2L)   //
#else
#define mRTC_US(x)              ((x*4L) / 125L) //
#endif

#define iSCRATCH_BOOT_POWER 0x550A5500
#define iAPP_INTO_BOOT      0x55AA55AA
#define iMODE_24G_RESET_VAL 0x12345678
//----------------------------------------------------------------------------;
// 通用类型定义
//
#define TIMER_PIN               (1*8+0)

#define CE_PIN                  (0*8+7)
#define IRQ_PIN                 (0*8+7)

#define io_debug0()             //{gpio_toggle(KEY_R1_PIN);gpio_dir_out(KEY_R1_PIN);}

//
//----------------------------------------------------------------------------;
//
//-----------------------------------------------------------------------------

#define mMS_TO_TICK(ms)         ((ms)<<5)
#define mSEN_SCAN_US(us)        ((us/ 250) - 1)

//-----------------------------------------------------------------------------;
// 唤醒配置
//
#define WAKEUP_BTN_MASK        0x01
#define WAKEUP_SENSOR_MASK     0x02
#define WAKEUP_WHEEL_MASK      0x04
#define WAKEUP_ALL_ENABLE      0x07
#define WAKEUP_ALL_DISABLE     0x00
#define WAKEUP_SLEEP_LEVEL0    (WAKEUP_ALL_DISABLE)
#define WAKEUP_SLEEP_LEVEL1    (WAKEUP_ALL_ENABLE)
#define WAKEUP_SLEEP_LEVEL2    (WAKEUP_BTN_MASK)

/**
 * @brief  Wireless Mouse RF Modes.
 */
typedef enum {
    iDEVICE_TYPE_BLE  = 1U,   /*<<< EX2_BLE mode */
    iDEVICE_TYPE_BT0  = 0U,   /*<<< EX2_BLE mode */
    iDEVICE_TYPE_BT1  = 1U,   /*<<< EX2_BLE mode */
    iDEVICE_TYPE_BT2  = 2U,   /*<<< EX2_BLE mode */
    iDEVICE_TYPE_24G  = 3U,   /*<<< OnMicro 2.4G proprietary protocol */
    iDEVICE_TYPE_USB  = 4U,
} device_type_t;

//-----------------------------------------------------------------------------;
// 外部引用寄存器
//
extern volatile uint8_t         ble_24g_ctrl;
//{
    #define bom6239_sync_ok (1<<3)              // 连接标志 0:没有连接;1：连接上
    #define bom6239_sync_ing (1<<2)             // 同步状态 0:没有回连；1：同步中
    #define bom6239_conn_ok (1<<1)              // 对码状态
    #define bom6239_conning (1<<0)              // 对码状态
//}

extern volatile unsigned char   sys_ctrl;
//{
    #define bmcu_reset      (1<<3)
    #define bscan_flag      (1<<2)
//}
extern device_type_t        device_type;
extern device_type_t        bt_index;

extern volatile uint32_t    sys_tick_count;
extern uint32_t             rtc_init_value;
extern uint32_t             rtc_cur_value;
extern uint32_t             rtc_temp_value;

extern uint8_t              wheel_data;
extern uint8_t              m_tx_count;
extern uint8_t              key_tx_count;
extern uint8_t              mmk_tx_count;
extern uint8_t              def_tx_count;

//----------------------------------------------
// 鼠标键盘数据寄存器
//
extern unsigned char            m_data_flag;
//{
    #define bhid_data_send      (1<<4)
    #define bsys_data_send      (1<<3)
    #define bmmk_data_send      (1<<2)
    #define bstd_kb_data_send   (1<<1)
    #define bmouse_data_send    (1<<0)
//}

extern uint8_t                  mouse_data_key;
extern uint8_t                  mouse_data_z;
// 键盘寄存器
extern unsigned char            std_key[];
#define std_kb_data             std_key           // 按键数据
//{
    #define std_kb_data_modifier std_key[0]
    #define std_kb_data_key1    std_key[1]
    #define std_kb_data_key2    std_key[2]
    #define std_kb_data_key3    std_key[3]
    #define std_kb_data_key4    std_key[4]
    #define std_kb_data_key5    std_key[5]
    #define std_kb_data_key6    std_key[6]
//}
// 多媒体寄存器
extern uint8_t                  mmk_data_l;
extern uint8_t                  mmk_data_h;
extern uint8_t                  mouse_bd_addr[];

extern uint32_t const           ble_sleep_1_time_tbl[];
extern uint32_t const           ble_sleep_2_time_tbl[];

//----------------------------------------------------------------------------;
// 通用类型定义
//
extern void mouse_periph_wakeup_enable(uint8_t mask); 

#endif  /* __MOUSE_H */
