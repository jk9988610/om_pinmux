#ifndef _LEDC_MODE_H_
#define _LEDC_MODE_H_

/**
 * @file ${TM_FILENAME_BASE/(.*)//upcase}  
 * @author 
 * @date 2026-04-14  //日期
 * @brief 
 */

// 可选：引入的库
#include <stdio.h>
#include <stdlib.h>
#include "string.h"
#include "main.h"
// #include "ledc.h"

// #define LEDC_RGB_NUMBER 6
// #define LEDC_RGB_DATA_SIZE LEDC_RGB_NUMBER*3

#define LEDC_RED        1<<1
#define LEDC_GREEN      1<<0
#define LEDC_BULE       1<<2

#define LEDC_DATA_MAX   240

#define LEDC_MODE_MAX   LEDC_MODE_OFF
#define LEDC_MODE_MIN   LEDC_COLORFUL
#define LEDC_DEFAULT_MODE   LEDC_COLORFUL

typedef enum
{
    LEDC_COLORFUL,
    LEDC_BS,
    LEDC_BRIGHT_COLORFUL,
    LEDC_BW,
    LEDC_COLORFUL_FLASH,
    LEDC_BREATH,
    LEDC_BRIGHT,
    LEDC_XYLS,
    LEDC_DDLS,
    LEDC_SW,
    LEDC_NONE,
    LEDC_MODE_OFF,
}ledc_mode;

extern uint8_t ledc_data_tab[LEDC_RGB_NUMBER*3];

__RAM_CODE void ledc_single_ctrl(uint8_t rgb_enbled, uint8_t color_enble, uint8_t red_data, uint8_t green_data, uint8_t blue_data);

void ledc_bright_init(void);
void ledc_mode_bright(void);

void ledc_breath_init(void);
void ledc_mode_breath(void);

void ledc_noen_init(void);
void ledc_mode_noen(void);

void ledc_colorful_init(void);
void ledc_mode_colorful(void);

void ledc_wave_init(void);
void ledc_mode_wave(void);

void ledc_bright_colorful_init(void);
void ledc_mode_bright_colorful(void);

void ledc_mode_off(void);

void ledc_mode_init(void);
void ledc_mode_scan(void);

#endif  // ${TM_FILENAME_BASE/(.*)//upcase}_H