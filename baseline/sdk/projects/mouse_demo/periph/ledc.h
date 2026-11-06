/**
 * @file ledc.h
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2026-01-21
 * 
 * @copyright Copyright (c) 2026
 * 
 */
#ifndef _LEDC_H_
#define _LEDC_H_

#include <stdint.h>
#include <stdbool.h>
#include "om_driver.h"
#include "time_delay.h"
#include "main.h"
#include "ledc_mode.h"
//-----------------------------------------------------------------------------;
// MACRO
//
//* LEDC VDD CTRL */
#define POWER_ON        1
#define POWER_OFF       0

#define LEDC_POWER_SET(x)   (x ? GPIO_SET(LEDC_CTRL_PIN) : GPIO_CLEAR(LEDC_CTRL_PIN)) 

//-----------------------------------------------------------------------------;
// Typedef
//
typedef enum {
    Cmd_Init,
    Cmd_Power_Set,
    Cmd_Dpi_Indicate_Cfg,
    Cmd_Report_Indicate_Cfg,
    Cmd_Lvd_Indicate_Cfg,
    Cmd_Idle_Cfg,
    Cmd_Power_Down_Cfg,
}Ledc_Cmd_t;

typedef struct {
    uint32_t On_Time;
    uint32_t Off_Time;
    uint16_t Blink_Times;
    uint8_t Rgb_data[LEDC_RGB_NUMBER*3];
    bool On_State;
}Ind_Val_t;

typedef enum {
    Off,
    Neon,
    Breath,
    Bright
}rgb_Mode_t;

typedef struct {
    uint8_t rgb_val[3*3];
    uint8_t dir;
    uint32_t delay_counter;
}Neon_Val_t;

typedef struct {
    uint32_t reserved;
}Breath_Val_t;

typedef struct {
    uint32_t reserved;
}Bright_Val_t;

typedef struct {
    bool is_indicate;
    bool is_lvd;
    bool is_charging;
    Ind_Val_t ind_val;
    rgb_Mode_t mode;
    Neon_Val_t neon_val;
    Breath_Val_t breath_val;
    Bright_Val_t bright_val;
}ledc_val_t;

void ledc_neon(uint8_t reset_state);

//-----------------------------------------------------------------------------;
// Publc funtion
//
uint32_t ledc_cmd(Ledc_Cmd_t cmd,void* arg);
void ledc_polling();
void ledc_write0(void);
void ledc_sleep();
void sys_deepsleep_process(void);

#endif
/* end */