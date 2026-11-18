/**
 * @file mode_ind.c
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2025-03-27
 * 
 * @copyright Copyright (c) 2025
 * 
 */
#include "mode_ind.h"
#include "lvd.h"
#include "rf_protocol.h"

static bool ind_state = 0;
static bool ind_mode = IND_MODE_OFF;
static uint32_t cur_rtc_time;
static ind_val_t cur_val;
static uint32_t lvd_dither_count;
static uint8_t bat_status_bak;

void ind_on()
{
    switch(cur_val.ind_color & 0x07)
    {
        case IND_RED:
            led_r_on();
            break;
        case IND_GREEN:
            led_g_on();
            break;
        case IND_BLUE:
            led_b_on();
            break;
        case IND_YELLOW:
            led_r_on();
            led_g_on();
            break;
        case IND_PURPLE:
            led_r_on();
            led_b_on();
            break;
        case IND_CYAN:
            led_g_on();
            led_b_on();
            break;
        case IND_WHITE:
        default:
            led_r_on();
            led_g_on();
            led_b_on();
            break;
    }
}

void ind_off()
{
    mode_led_all_off();
}

void ind_sleep()
{
    mode_led_all_off();
    ind_mode = IND_MODE_OFF;
}

void clear_ind_flag()
{
    ind_mode = IND_MODE_OFF;
}

void ind_config(const ind_val_t* set_val)
{
    if (set_val != NULL)
        cur_val = *set_val;
    cur_rtc_time = drv_rtc_read(OM_RTC);
    ind_off();
    ind_on();
    ind_state = 1;
    ind_mode = IND_MODE_FLASH;
}

void dpi_config(uint8_t dpi_grade)
{
    ind_val_t dpi_val = {
        .ind_color = IND_BLUE,
        .ind_times = IND_DPI_THREE,
        .ind_on_time = DPI_TIME_ON,
        .ind_off_time = DPI_TIME_OFF,
    };
    switch(dpi_grade)
    {
        case 0:
            dpi_val.ind_color = IND_WHITE;
            break;
        case 1:
            dpi_val.ind_color = IND_CYAN;
            break;
        case 2:
            dpi_val.ind_color = IND_BLUE;
            break;
        case 3:
            dpi_val.ind_color = IND_YELLOW;
            break;
        case 4:
            dpi_val.ind_color = IND_PURPLE;
            break;
        case 5:
            dpi_val.ind_color = IND_RED;
            break;
        case 6:
            dpi_val.ind_color = IND_GREEN;
            break;
        defualt:
            dpi_val.ind_color = IND_GREEN;
            break;
    }
    ind_config(&dpi_val);
}

/**
 * @brief 
 * 
 */
void mode_led_hint()
{   
    static bool lvd_flag = 0;
    uint32_t rtc_time = drv_rtc_read(OM_RTC);

    if(ind_mode == IND_MODE_FLASH)
    {
        if(ind_state)       /* indicate on */
        {
            if(mMS_TO_TICK(cur_val.ind_on_time) > (rtc_time-cur_rtc_time))
            {
                return;
            }
            cur_rtc_time = rtc_time;

            ind_state = 0;
            ind_off();
        }
        else
        {
            if(mMS_TO_TICK(cur_val.ind_off_time) > (rtc_time-cur_rtc_time))
            {
                return;
            }
            cur_rtc_time = rtc_time;

            cur_val.ind_times --;
            if(cur_val.ind_times == 0)
            {
                ind_mode = IND_MODE_OFF;
            }
            else
            {
                ind_state = 1;
                ind_on();
            }
            
        }
    }
    else if(ind_mode == IND_MODE_OFF)
    {   
        
    }
    
}

