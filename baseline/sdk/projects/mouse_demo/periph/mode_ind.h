/**
 * @file mode_ind.h
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2025-03-27
 * 
 * @copyright Copyright (c) 2025
 * 
 */
#ifndef __MODE_IND_H
#define __MODE_IND_H

#include "main.h"
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include "om_driver.h"
#include "time_delay.h"
#include "user_config.h"

#define IND_MODE_FLASH      1
#define IND_MODE_OFF        0

#define IND_RED     0x01
#define IND_GREEN   0x02
#define IND_BLUE    0x04
#define IND_YELLOW  0x03
#define IND_PURPLE  0x05
#define IND_CYAN    0x06
#define IND_WHITE   0x07
#define IND_DPI     0x08

#define ALWAYS_ON       0xFFFF

#define BLE_PAIR_TIME_ON        175
#define BLE_PAIR_TIME_OFF       175
#define BLE_BOND_TIME_ON        500
#define BLE_BOND_TIME_OFF       500
#define BLE_RECONNECT_TIME_ON   3000
#define BLE_RECONNECT_TIME_OFF  20

#define DPI_TIME_ON             200
#define DPI_TIME_OFF            200

#define IND_TIMES_ONE           1
#define IND_DPI_THREE           3

extern bool ind_mode;

typedef struct{
    uint8_t  ind_color;
    uint16_t ind_times;
    uint32_t ind_on_time;
    uint32_t ind_off_time;
}ind_val_t;

extern void clear_ind_flag();
extern void ind_sleep();
extern void ind_config(const ind_val_t* set_val);
extern bool bmanual_pair;
extern uint32_t mode_led_flash_time;
extern uint8_t  mode_led_flash_state;
extern void ind_on_2s_then_off(uint8_t color);
extern void dpi_config(uint8_t dpi_grade);
extern void mode_led_hint();

#endif
