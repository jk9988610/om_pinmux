/**
 * @file sensor_type_check.h
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2025-05-22
 * 
 * @copyright Copyright (c) 2025
 * 
 */

#ifndef _SENSOR_TYPE_CHECK_H_
#define _SENSOR_TYPE_CHECK_H_

//=============================================================================;
// 配置引用区                                                                  ;
//=============================================================================;
#define iSEN_DIR_0              0x61
#define iSEN_DIR_90             0x07
#define iSEN_DIR_180            0x52
#define iSEN_DIR_270            0x34
#define iSEN_DIR_ERR            0x01

//-------------------------------------------------------------------------------
// Sensor索引
//
#define iSENSOR_TYPE_S201B      1               // S201B

#define iSENSOR_TYPE_KA8        2               // OM15  PID == PAN_3204L
#define iSENSOR_TYPE_KA5857     4               // KA5857
#define iSENSOR_TYPE_3205_TJ3T  5               // PAN3205_TJ3R
#define iSENSOR_TYPE_3205_TJNT  6               // PAN3205_TJNT
#define iSENSOR_TYPE_YS8008     8               // YS8008

#define iSENSOR_TYPE_MX8650A    10              // MX8650A
#define iSENSOR_TYPE_S203       14              // S203
#define iSENSOR_TYPE_KA8G2      15              // KA8G2
#define iSENSOR_TYPE_S205       16              // S205
#define iSENSOR_TYPE_OM18       17              // OM18
#define iSENSOR_TYPE_SG8912     18              // SG8912
//#define iSENSOR_TYPE_3220_TJDS  19              // PAN3220_TJDS
#define iSENSOR_TYPE_3220_TJDL  20              // PAN3220_TJDL
#define iSENSOR_TYPE_3212       21              // PAN3212

#define iSENSOR_TYPE_3065_D     24              // FTC3065
#define iSENSOR_TYPE_3104_DB    28              // FTC3065
#define iSENSOR_TYPE_PAW3311     27
#define iSENSOR_TYPE_SG8925     29
//
//-------------------------------------------------------------------------------

//-------------------------------------------------------------------------------
// PID相关
//
#define iPID_ADDR_PAN           0x01            // pan pid地址0
#define iPID_VALUE_KA8          0x50            // KA8
#define iPID_VALUE_MX8650A      0x5A            // MX8650A

#define iPID_VALUE_PAN3205_S201 0xD0            // pan3205   pid 0xdx  pan3204ul

#define iPID_VALUE_PAN3065      0x31            // pan3065 pid 0x31
#define iPID_VALUE_KA5857_KA8G2 0x58            // pan3065 pid 0x31
//{
    #define iPID_VALUE_KA5857   0x57
    #define iPID_VALUE_KA8G2    0x59
//}
#define iPID_VALUE_FTC3065      0x70            // FTC3065 pid 0x31
#define iPID_VALUE_PAN3212_3220_SG8912 0x02     // pan3212 pid 0x03
//{
    #define iPID_VALUE_KA5857   0x57
    #define iPID_VALUE_KA8G2    0x59
    #define iPID_VALUE_S203     0xB1
    #define iPID_VALUE_S205     0xB2
//}
#define iPID_VALUE_PAN3205_TJNT 0x00            // pan3205 pid 0x00
#define iPID_VALUE_S201B        0xA1            //
#define iPID_VALUE_YS8008       0xD8            // pan3212 pid 0x03
#define iPID_VALUE_SG8925       0xC0
//
//-------------------------------------------------------------------------------

#define iXY_12BIT_ADDR          0x12            //
#define iX_16BIT_ADDR           0x20            //
#define iY_16BIT_ADDR           0x21            //

//-------------------------------------------------------------------------------
// Sensor配置信息
//
//---------------------------------------
//PAN3205配置信息

#define iPAN3205_DPI_CTRL_REG       0x06        // DPI设置寄存器
#define iPAN3205_DPI_CLR_MASK       0x47        // DPI设置屏蔽位
#define iPAN3205_DPI_SET_MASK       0x40        // DPI设置屏蔽位
#define iPAN3205_WAKEUP_SLEEP_ADDR  0x06        // 休眠唤醒寄存器
#define iPAN3205_WAKEUP_SLEEP_MASK  0x38        // 休眠唤醒屏蔽位
#define iPAN3205_SLEEP_VALUE        0x08        // 休眠值
#define iPAN3205_WAKEUP_VALUE       0x00        // 唤醒值

//---------------------------------------
//PAN3212配置信息
//
#define iPAN3212_DPI_CTRL_REG       0x0C        // DPI设置寄存器
#define iPAN3212_DPI_CLR_MASK       0x3F        // DPI设置屏蔽位
#define iPAN3212_DPI_SET_MASK       0x00        // DPI设置屏蔽位
#define iPAN3212_WAKEUP_SLEEP_ADDR  0x06        // 休眠唤醒寄存器
#define iPAN3212_WAKEUP_SLEEP_MASK  0xFF        // 休眠唤醒屏蔽位
#define iPAN3212_SLEEP_VALUE        0x18        // 休眠值
#define iPAN3212_WAKEUP_VALUE       0x10        // 唤醒值

//
//-----------------------------------------------------------------------------
// Sensor默认 DPI
//
#define iSENSOR_DPI_GRADE           0x00        //

#define iKA8_DPI_VALUE              0x44        // 1200
#define iMX8630A_DPI_VALUE          0x45        // 1000
#define iPAN3205_DPI_VALUE          0x42        // 1000
#define iMX8640_DPI_VALUE           0x45        // 1000
#define iPAN3212_DPI_VALUE          0x1B        // 1000

//-----------------------------------------------------------------------------;
// Sensor默认定义
//
#define iDPI_MODE0_VLAUE        2               // DPI默认当前级
#define iDPI_MODE1_VLAUE        2               // DPI默认当前级
#define iDPI_MODE2_VLAUE        2               // DPI默认当前级
#define iDPI_MODE3_VLAUE        2               // DPI默认当前级
#define iDPI_MODE4_VLAUE        2               // DPI默认当前级
//-----------------------------------------------------------------------------;
//配置区
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
// 内部定义外部部引用区                                                        ;
//=============================================================================;

//-----------------------------------------------------------------------------;
// 寄存器引用
//

void pan_poweron_wakeup(void);

//-----------------------------------------------------------------------------;
// 函数引用
//
extern void sensor_dat_format(void);
extern void sensor_dir_set(void);
extern void sensor_type_check(void);

#endif
