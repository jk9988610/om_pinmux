/*******************************************************************************
* Copyright (c) 2013, SHENZHEN Co.,LTD.
* All rights reserved.
*
* 文件名称: led.h
*
* 功能说明:
* 修改说明:
*******************************************************************************/
#ifndef _LED_H_
#define _LED_H_

//=============================================================================;
// 配置引用区                                                                  ;
//=============================================================================;

//-----------------------------------------------------------------------------;
// 配置区
//
#define iLED_CFG_POWER_ON       0
#define iLED_CFG_SENSOR_ERR     1
#define iLED_CFG_CONNECT_ING    2
#define iLED_CFG_CONNECT_OK     3
#define iLED_CFG_DPI_CHANGE     4
#define iLED_CFG_LVD            5
#define iLED_CFG_CHAR_ING       6
#define iLED_CFG_CHAR_OK        7
#define iLED_CFG_OFF            8
#define iLED_CFG_IDLE           9
#define iLED_CFG_REPORT_CHANGE  10

#define iPWM_R                  0x01
#define iPWM_G                  0x02
#define iPWM_B                  0x04
#define iPWM_RGB                0x07

#define iPWM_MAX                63
#define iPWM_NH_MAX             32

#define mHOLE_TIME(iON_MS, iOFF_MS)  (((((iON_MS)/125L)<<4)&0xF0)|(((iOFF_MS)/125L)&0x0F))

//-----------------------------------------------------------------------------;
// 配置区
//
enum led_level
{
    iLED_LEV_MIN=0,// 最暗
    iLED_LEV_0 = 0,
    iLED_LEV_1 = 1,
    iLED_LEV_2 = 2,
    iLED_LEV_3 = 3,
    iLED_LEV_4 = 4,
    iLED_LEV_MAX = 4,	// 最亮
};

enum speed_level
{
    iSPEED_LEV_MIN = 0,
    iSPEED_LEV_1 = 0,
    iSPEED_LEV_2 = 1,
    iSPEED_LEV_3 = 2,
    iSPEED_LEV_4 = 3,
    iSPEED_LEV_5 = 4,
    iSPEED_LEV_MAX = 4,
};

typedef enum {
    iLOGO_DILE      = 0,
    iLOGO_OFF       = 1,
    iLOGO_FLASH     = 2,
    iLOGO_BREATHE   = 3,
    iLOGO_NH        = 4,
    iLOGO_MAX       = 5,
    iLOGO_INVALID   = 0x0F,
    iLOGO_NULL      = 0x0E,
} logo_mode_t;

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
extern bool                 blogo_status;
extern bool                 bled_bright_en;
extern bool                 blvd_hint_flag;
extern bool                 bidle_chg_flag;
extern bool                 busb_dpi_flag;
extern uint8_t              dpi_led_dat[8];
extern uint8_t              led_dat[8];
extern uint8_t               lvd_scan_count;
#define logo_ctrl           led_dat[0]
//{
    #define iRGB_MASK       0x70
    #define iPWM_B_EN       (1<<6)
    #define iPWM_G_EN       (1<<5)
    #define iPWM_R_EN       (1<<4)
    #define iMODE_MASK      0x0F
//}
#define logo_para           led_dat[1]
//{
    #define flash_times     logo_para
    #define breath_times    logo_para
//}
#define hold_time           led_dat[2]
//{                                             // 单位 闪烁模式下0.125s; 呼吸模式下0.5s
    #define hold_on_time    (hold_time & 0xF0)
    #define hold_off_time   ((hold_time<<4)&0xF0)
//}
#define break_time          led_dat[3]
#define r_value             led_dat[4]
#define g_value             led_dat[5]
#define b_value             led_dat[6]

extern uint8_t              led_hint_mode;
extern uint8_t              led_mode;
extern uint8_t              led_mode_bak;

extern uint8_t              led_light_lev;
extern uint8_t              led_speed_lev;

extern uint8_t              logo_hint_time_count;
extern uint8_t              logo_hint_on_time;
extern uint8_t              logo_hint_off_time;

extern uint8_t              rgb_enable;

//-----------------------------------------------------------------------------;
// 函数引用
//
extern void pwm_init(void);
extern void pwm_off();
extern void logo_cfg(unsigned char const led_cfg_index);
extern void logo_process(void);
//
//-----------------------------------------------------------------------------;
#endif
