/**
 * @file led.c
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2025-05-23
 * 
 * @copyright Copyright (c) 2025
 * 
 */

#include <string.h>
#include "om_driver.h"

#include "main.h"
#include "lvd.h"
#include "led.h"
#include "sensor.h"

#include "flash.h"
#include "flash_process.h"
#include "usb_cfg_info.h"
#include "drv_ledc.h"
//-----------------------------------------------------------------------------;
// 常量定义区
//



//-----------------------------------------------------------------------------;
// 变量定义区
//
bool                        bhint_process;
bool                        blogo_status;
bool                        bled_bright_en;
bool                        blvd_hint_flag;
bool                        bidle_chg_flag;
bool                        busb_dpi_flag;
bool                        brf_24g_reconnect;

__ALIGNED(4) uint8_t        led_dat[8];

uint8_t                     led_hint_mode;
uint8_t                     led_mode;
uint8_t                     led_mode_bak;
uint8_t                     led_light_lev;
uint8_t                     led_speed_lev;

uint8_t                     logo_hint_time_count;
uint8_t                     rgb_enable;

uint8_t                     pwm_value;
uint8_t                     pwm_count;

uint8_t                     nhjb_led_index;

uint16_t                    flash_on_time;
uint16_t                    flash_off_time;
uint32_t                    led_delay_count;

bool                        usb_5v_in_hint;
//-----------------------------------------------------------------------------;
// 表格定义区
//
unsigned char       const   rgb_en_tbl[]={
    iPWM_R,
    iPWM_G,
    iPWM_B,
    iPWM_B|iPWM_R,
    iPWM_R|iPWM_G,
    iPWM_B|iPWM_G,
    iPWM_R|iPWM_G|iPWM_B,
    0x07,
};


//=============================================================================;
// 代码区                                                                      ;
//=============================================================================;

/******************************************************************************
* 函数名称: led_hint_process
* 功能描述:
* 输入参数:
* 输出参数:
* 说    明:
******************************************************************************/
void pwm_init(void)
{

}

/**
 * @brief PWM 关闭函数
 * 
 */
void pwm_off()
{

}

/******************************************************************************
* 函数名称: pwm_write
* 功能描述:
* 输入参数:
* 输出参数:
* 说    明:
******************************************************************************/

void pwm_write(uint8_t pwm_r, uint8_t pwm_g, uint8_t pwm_b)
{
   
}

/*******************************************************************************
* 函数名称: led_process()
* 功能描述:
* 输入参数： 无
* 输出参数： 无
* 说    明:
*******************************************************************************/
void logo_cfg(unsigned char const led_cfg_index)
{

}

/******************************************************************************
* 函数名称: led_hint_process
* 功能描述:
* 输入参数:
* 输出参数:
* 说    明:
******************************************************************************/
void rgb_flash_process(void)
{
   
}

/******************************************************************************
* 函数名称: rgb_process
* 功能描述:
* 输入参数:
* 输出参数:
* 说    明:
******************************************************************************/
void rgb_process(void)
{
   
}

/******************************************************************************
* 函数名称: logo_process
* 功能描述:
* 输入参数:
* 输出参数:
* 说    明:
******************************************************************************/
void logo_process(void)
{
    uint8_t i;

    if(true==bsave_status)
    {
        bsave_status = false;
        flash_save_status();
        brf_24g_reconnect = 1;
    } 

    if(true==bsave_driver_status)
    {
        bsave_driver_status = false;
        flash_save_driver_status();
        brf_24g_reconnect = 1;
    } 

  
}



