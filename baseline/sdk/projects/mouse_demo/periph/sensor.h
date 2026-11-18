/**
 * @file sensor.h
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2025-05-22
 * 
 * @copyright Copyright (c) 2025
 * 
 */

#ifndef	_SENSOR_H_
#define _SENSOR_H_

//=============================================================================;
// 配置引用区                                                                  ;
//=============================================================================;


//-----------------------------------------------------------------------------;
//配置常量定义区
//
#define SNIPER_ADD     1
#define SNIPER_SUB     0

#define DEFAULT_DPI_GRADE  1
//-----------------------------------------------------------------------------;
//配置区
//
#define sensor_read             drv_senscan_read
#define sensor_write            drv_senscan_write
#define sensor_resync           drv_senscan_2wire_resync

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
// 内部定义外部部引用区                                                        ;
//=============================================================================;

//-----------------------------------------------------------------------------;
// 寄存器引用
//
//unsigned char                   key_plus_fun_ctrl;
//{
    #define bcom_fire_key       (1<<7)
    #define bfire_key           (1<<3)
    #define bdpi_change         (1<<2)
    #define bdpi_change_ctrl    (1<<1)
    #define bdpi_add_sub        (1<<0)
//}

extern unsigned char        sensor_status_reg;
//{
  #define bxy_data_invalid  (1<<6)
  #define by_sign           (1<<5)
  #define bx_sign           (1<<4)
  #define bsensor_sleep     (1<<3)
  #define bsensor_12bit     (1<<1)
  #define bsensor_s201x     (1<<0)
//}
extern unsigned char        dpi_grade;
extern unsigned char        dpi_value;

extern uint16_t             mouse_x;
extern uint16_t             mouse_y;

extern unsigned char        sensor_type;
extern uint8_t              sensor_scan_freq;
extern bool                 bscan_sensor_en;

extern unsigned char const sensor_dpi_ini[];
//-----------------------------------------------------------------------------;
// 函数引用
//
extern void senscan_init(void);

extern void sensor_power_up_init(void);
extern void sensor_clear_xy(void);
extern void sensor_read_xy_data(void);
extern void sensor_dat_init(void);

extern void sensor_set_dpi(void);
extern void sensor_xy_scan(void);

extern void sensor_sleep(void);
extern void sensor_wakeup(void);

extern void sensor_comm_resume(void);
extern void sensor_check_id(void);

extern void sniper_set_dpi(bool key_type);
extern void sniper_reset_dpi();

extern void dpi_key_press(uint8_t key_plus_fun_ctrl);
extern void sensor_change_dpi(uint8_t key_plus_fun_ctrl);

#endif
