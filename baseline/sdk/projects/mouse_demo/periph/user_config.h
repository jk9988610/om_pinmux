/**
 * @file user_config.h
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2025-05-22
 * 
 * @copyright Copyright (c) 2025
 * 
 */
#ifndef __USER_CONFIG_H
#define __USER_CONFIG_H

#include <stdint.h>
#include <stdbool.h>
#include "om_driver.h"
#include "time_delay.h"

//----------------------------------------------------------------------------;
// IO口宏定义区
//
#define P00     (8*0+0)         /* PWM / WHB */
#define P01     (8*0+1)         /* PWM / WHA */
#define P02     (8*0+2)         /* D- */
#define P03     (8*0+3)         /* D+ */
#define P04     (8*0+4)         /* UART TX */
#define P05     (8*0+5)        
#define P06     (8*0+6)         /* UART RX */
#define P07     (8*0+7)

#define P10     (8*1+0) 
#define P11     (8*1+1)         /* UART RX */
#define P12     (8*1+2)         /* UART TX */
#define P13     (8*1+3)
#define P14     (8*1+4)         /* FLASH */
#define P15     (8*1+5)         /* FLASH */
#define P16     (8*1+6)         /* FLASH */
#define P17     (8*1+7)         /* FLASH */

#define P20     (8*2+0)
#define P21     (8*2+1)         
#define P22     (8*2+2)         /* TCK */
#define P23     (8*2+3) 
#define P24     (8*2+4)
#define P25     (8*2+5)         /* TMS */
#define P26     (8*2+6)
#define P27     (8*2+7)

#define P30     (8*3+0)
#define P31     (8*3+1)
#define P32     (8*3+2)
#define P33     (8*3+3)
#define P34     (8*3+4)
#define P35     (8*3+5)        
#define P36     (8*3+6)
#define P37     (8*3+7)         /* BOOT */

//----------------------------------------------------------------------------;
// IO口上下拉配置宏定义区
//
#define PU_NONE     0
#define PU_30K      2
#define PU_150K     1

#define PD_150K     0

#define PIN_HIGH_LEV    1
#define PIN_LOW_LEV     0

#define PAD_IN_BUFFER_EN 1
#define PAD_IN_BUFFER_OFF 0
//----------------------------------------------------------------------------;
// IO口 (方向/电平) 配置宏定义区
//
#define gpio_dir_out(pin)   (OM_GPIO0->OUTENSET = (1<<(pin)))
#define gpio_dir_in(pin)    (OM_GPIO0->OUTENCLR = (1<<(pin)))
#define gpio_set(pin)       (OM_GPIO0->DATAOUTSET = (1<<(pin)))
#define gpio_clear(pin)     (OM_GPIO0->DATAOUTCLR = (1<<(pin)))
#define gpio_toggle(pin)    (OM_GPIO0->DATAOUT ^= (1u << (pin)))
#define gpio_read(pin)      ((OM_GPIO0->DATA>>pin) & 0x1)

//----------------------------------------------------------------------------;
// IO口外设 配置宏定义区
//
/* OMCFG BEGIN pins */
//* 按键配置 */
#define KEY_R0_PIN              (P34)
#define KEY_R1_PIN              (P07)
#define KEY_R2_PIN              (P10)
#define KEY_B_PIN               (P22)
#define KEY_P_PIN               (P25)
#define KEY_DPI_PIN             (P31)
#define KEY_PAIR_PIN            (P27)

//* IO口唤醒配置 */
#define PIN_WAKE_UP_MASK        ((1<<KEY_R0_PIN) |(1<<KEY_R1_PIN)|(1<<KEY_R2_PIN)|(1<<KEY_PAIR_PIN)|(1<<SENSOR_MOTION_PIN))
#define KEY_PIN_WAKE_UP_EN()    drv_pmu_wakeup_pin_set(KEY_R0_PIN, PMU_PIN_WAKEUP_TYPE_FALL);   \
                                drv_pmu_wakeup_pin_set(KEY_R1_PIN, PMU_PIN_WAKEUP_TYPE_FALL); \
                                drv_pmu_wakeup_pin_set(KEY_R2_PIN, PMU_PIN_WAKEUP_TYPE_FALL); \
                                drv_pmu_wakeup_pin_set(KEY_PAIR_PIN, PMU_PIN_WAKEUP_TYPE_FALL);   \
                                drv_pmu_wakeup_pin_set(SENSOR_MOTION_PIN, PMU_PIN_WAKEUP_TYPE_FALL);   

#define KEY_PIN_WAKE_UP_DIS()   drv_pmu_wakeup_pin_set(KEY_R0_PIN, PMU_PIN_WAKEUP_TYPE_DISABLE);   \
                                drv_pmu_wakeup_pin_set(KEY_R1_PIN, PMU_PIN_WAKEUP_TYPE_DISABLE);  \
                                drv_pmu_wakeup_pin_set(KEY_R2_PIN, PMU_PIN_WAKEUP_TYPE_DISABLE);  \
                                drv_pmu_wakeup_pin_set(KEY_PAIR_PIN, PMU_PIN_WAKEUP_TYPE_DISABLE);      \
                                drv_pmu_wakeup_pin_set(SENSOR_MOTION_PIN, PMU_PIN_WAKEUP_TYPE_DISABLE); 

//* 滚轮IO口配置 */
#define WHEEL_A_PIN             (P21)
#define WHEEL_B_PIN             (P20)
#define WHEEL_IO_SELECT         ENCODER_PINMUX_SEL_IO_20_21

//* SENSOR IO口配置 */
#define SENSOR_MOTION_PIN       (P13)
#define SENSOR_SCLK_PIN         (P11)
#define SENSOR_SDIO_PIN         (P12)

#define SENSOR_DIR_DEFINE       SENSOR_DIR_CLOCK_6
#define SENSOR_DIR_CLOCK_0      1
#define SENSOR_DIR_CLOCK_3      2
#define SENSOR_DIR_CLOCK_6      3
#define SENSOR_DIR_CLOCK_9      4
                  
//* 模式检测脚配置 */
#define MODE_BLE_24G_PIN        (P26)
//{
    #define MODE_BLE_CHECK      0   
    #define MODE_24G_CHECK      1
//}

//* LED指示灯配置 */
#define LED_MODE_R_PIN        (P32)
#define LED_MODE_G_PIN        (P00)
#define LED_MODE_B_PIN        (P01)
//{
    #define led_r_on()            (gpio_clear(LED_MODE_R_PIN))
    #define led_r_off()           (gpio_set(LED_MODE_R_PIN))
    #define led_g_on()            (gpio_clear(LED_MODE_G_PIN))
    #define led_g_off()           (gpio_set(LED_MODE_G_PIN))
    #define led_b_on()            (gpio_clear(LED_MODE_B_PIN))
    #define led_b_off()           (gpio_set(LED_MODE_B_PIN))
    #define mode_led_all_off()    (OM_GPIO0->DATAOUTSET = (1<<LED_MODE_R_PIN)|(1<<LED_MODE_G_PIN)|(1<<LED_MODE_B_PIN))
    #define mode_led_all_on()     (OM_GPIO0->DATAOUTCLR = (1<<LED_MODE_R_PIN)|(1<<LED_MODE_G_PIN)|(1<<LED_MODE_B_PIN))
//}

#define LED_MODE_24G_PIN        LED_MODE_R_PIN
#define LED_MODE_BT1_PIN        LED_MODE_G_PIN
#define LED_MODE_BT0_PIN        LED_MODE_B_PIN
//{
    #define led_bt0_on()            (gpio_clear(LED_MODE_BT0_PIN))
    #define led_bt0_off()           (gpio_set(LED_MODE_BT0_PIN))
    #define led_24g_on()            (gpio_clear(LED_MODE_24G_PIN))
    #define led_24g_off()           (gpio_set(LED_MODE_24G_PIN))
    #define led_bt1_on()            (gpio_clear(LED_MODE_BT1_PIN))
    #define led_bt1_off()           (gpio_set(LED_MODE_BT1_PIN))
//}

//* LOGO灯配置 */
#define LED_R_PIN               (P04)
#define LED_G_PIN               (P05)
#define LED_B_PIN               (P06)

//* USB 5V以及充电检测配置 */
#define USB_5V                  (P24)
#define BAT_CHG_PIN             (P30)

#define USB_5V_PIN              (gpio_read(USB_5V))
#define BAT_CHG_OK              (gpio_read(BAT_CHG_PIN))

//* LVD检测引脚 */
#define LVD_PIN                 (P23)
#define LVD_CHECK_INDEX         (POF_LVD_PIN_P23)

//* USB */
#define USB_DN_PIN              (P02)
#define USB_DP_PIN              (P03)

#define FLASH_CS_PIN            (P17)
#define FLASH_SCLK_PIN          (P15)
#define FLASH_MOSI_PIN          (P16)
#define FLASH_MISO_PIN          (P14)

//* 当前UART仅调试用 */
#define UART_PIN                (KEY_R0_PIN)
/* OMCFG END pins */

//----------------------------------------------------------------------------;
// RF模式配置
//
#define APP_ENABLE    1               
#define APP_DISABLE   0  

#define RF_RATE       RF_RATE_2MHz
//{
    #define RF_RATE_1MHz      (1<<6)
    #define RF_RATE_2MHz      (0<<6)
//}
#define RF_PROTOCOL   RF_PROTOCOL_OLD
//{
    #define RF_PROTOCOL_OLD   (0<<5)
    #define RF_PROTOCOL_NEW   (1<<5)
//}
#define RF_CONN             RF_CONN_EN  /* RF配对模式设置 */
//{     
    #define RF_24G_BOND_EN          1   /* 配对模式 */
    #define RF_24G_BOND_DIS         0   /* 免对码模式 */
//}
#define iAPP_ID_H               0x02

//----------------------------------------------------------------------------;
// 项目ID定义区 项目立项的时候分配的项目ID
//
/* OMCFG BEGIN project_ids */
#define iPROJECT_ID_H  0x071               /* 项目平台编号:OM6239 */
#define iPROJECT_ID_L  0x0023              /* 项目编号 */
/* OMCFG END project_ids */

#define iPROJECT_ID_0  (iPROJECT_ID_L&0xFF)
#define iPROJECT_ID_1  ((iPROJECT_ID_L>>8)&0xFF)
#define iPROJECT_ID_2  (iPROJECT_ID_H&0xFF)
#define iPROJECT_ID_3  ((iPROJECT_ID_H>>8)&0xFF)

//----------------------------------------------------------------------------;
// 程序版本定义区 程序版本升级编号
//
/* OMCFG BEGIN project_version */
#define iREAL_VERSION_ID        5            /* 版本编号（0x80不能动），每次版本更新，后面的版本号要累加，第一个版本则为1 */
/* OMCFG END project_version */
#define iVERSION_ID_L     (0x80|RF_RATE|RF_PROTOCOL|iREAL_VERSION_ID)   
#define iVERSION_ID_H  iPROJECT_ID_0

/* OMCFG BEGIN project_names */
#define iCONSUMER_NAME "BYC"        /* 客户名字 */
#define iPROJECT_NAME  "KC536"      /* 项目名字 */
/* OMCFG END project_names */

//----------------------------------------------------------------------------;
// extern function
//
extern void gpio_set_pu(uint8_t pin,uint8_t mode);
extern void gpio_set_pd(uint8_t pin);
extern void gpio_set_float(uint8_t pin);
extern void periph_gpio_sleep_set();
extern void periph_gpio_init();
extern void uart_tx(uint8_t data);

#endif

/* USER CODE BEGIN user_config_h */
/* USER CODE END user_config_h */
