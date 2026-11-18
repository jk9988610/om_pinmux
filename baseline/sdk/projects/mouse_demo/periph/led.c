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

//-----------------------------------------------------------------------------;
// 常量定义区
//
#define iLED_RED                (0<<4)      // 红
#define iLED_GREEN              (1<<4)      // 绿
#define iLED_BULE               (2<<4)      // 蓝
#define iLED_YELLOW             (3<<4)      // 紫
#define iLED_PURPLE             (4<<4)      // 橙
#define iLED_CYAN               (5<<4)      // 青
#define iLED_WHITE              (6<<4)      // 白

#define PWM_0_PIN               (0*8+0)
#define PWM_1_PIN               (0*8+1)
#define PWM_2_PIN               (0*8+4)
#define PWM_3_PIN               (0*8+5)
#define PWM_4_PIN               (0*8+6)
#define PWM_5_PIN               (2*8+2)
#define PWM_6_PIN               (2*8+6)
#define PWM_7_PIN               (3*8+2)

#define iPWM_0_EN               (1<<0)
#define iPWM_1_EN               (1<<1)
#define iPWM_2_EN               (1<<2)
#define iPWM_3_EN               (1<<3)
#define iPWM_4_EN               (1<<4)
#define iPWM_5_EN               (1<<5)
#define iPWM_6_EN               (1<<6)
#define iPWM_7_EN               (1<<7)

#define pwm_0                   OM_PWM->PWMDC0
#define pwm_1                   OM_PWM->PWMDC1
#define pwm_2                   OM_PWM->PWMDC2
#define pwm_3                   OM_PWM->PWMDC3
#define pwm_4                   OM_PWM->PWMDC4
#define pwm_5                   OM_PWM->PWMDC5
#define pwm_6                   OM_PWM->PWMDC6
#define pwm_7                   OM_PWM->PWMDC7

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

unsigned char const default_hint_led_tbl[] =
{
//----------------------------------------------
    0x82,0x03,mHOLE_TIME(1500, 0),0x00,0xFF,0xFF,0xFF,0xFF, // iLED_CFG_POWER_ON 常亮3s
//----------------------------------------------
    0x82,0x08,mHOLE_TIME(500,500),0x00,0xFF,0x00,0x00,0xFF, // iLED_CFG_SENSOR_ERR 红色闪烁4次
//----------------------------------------------
    0x82,0x00,mHOLE_TIME(500,500),0x00,0xFF,0xFF,0xFF,0xFF, // iLED_CFG_CONNECT_ING  1Hz闪烁
//----------------------------------------------
    0x82,0x03,mHOLE_TIME(1500,0),0x00,0xFF,0xFF,0xFF,0xFF, // iLED_CFG_CONNECT_OK 常亮3s
//----------------------------------------------
    0x92,0x08,mHOLE_TIME(500,500),0x00,0xFF,0xFF,0xFF,0xFF, // iLED_CFG_DPI_CHANGE  加载Flash配置
//----------------------------------------------
    0x82,0x00,mHOLE_TIME(250,1750),0x00,0xFF,0xFF,0xFF,0xFF, // iLED_CFG_LVD 0.5Hz闪烁
//----------------------------------------------
    0x82,0x00,mHOLE_TIME(1750,0),0x00,0xFF,0xFF,0xFF,0xFF, // iLED_CFG_CHAR_ING 红色常亮
//----------------------------------------------
    0x92,0x00,mHOLE_TIME(1750,0),0x00,0xFF,0xFF,0xFF,0xFF, // iLED_CFG_CHAR_OK 绿色常亮
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
    DRV_RCC_CLOCK_ENABLE(RCC_CLK_PWM, 1U);
    OM_PWM->PWMCON = 0x00000000;

    OM_PWM->PWMCR0 = 0x0000001C;
    OM_PWM->PWMCR1 = 0x0000001c;
    OM_PWM->PWMDIV = 0x00000001;
    if(iLED_LEV_4 == led_light_lev)
        OM_PWM->PWMPRD = (iPWM_MAX+1);
    else if(iLED_LEV_3 == led_light_lev)
        OM_PWM->PWMPRD = ((iPWM_MAX+1)*2);
    else if(iLED_LEV_2 == led_light_lev)
        OM_PWM->PWMPRD = ((iPWM_MAX+1)*3);
    else //if(iLED_LEV_1 == led_light_lev)
        OM_PWM->PWMPRD = ((iPWM_MAX+1)*4);
}

/**
 * @brief PWM 关闭函数
 * 
 */
void pwm_off()
{
    OM_PWM->PWMCON = 0x00000000;
    OM_GPIO0->DATAOUTSET = 0x00000070;
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
    uint8_t i;

    OM_PWM->PWMCON = 0x00000000;
    i = 0;
    OM_GPIO0->DATAOUTSET = 0x00000070;

    if((0x00 != pwm_r) && (rgb_enable&iPWM_R))
    {
        pwm_2 = pwm_r;
        i |= (iPWM_2_EN);
    }
    else
    {
        OM_GPIO0->DATAOUT |= 1<<LED_R_PIN;
    }

    if((0x00 != pwm_g) && (rgb_enable&iPWM_G))
    {
        pwm_3 = pwm_g;
        i |= (iPWM_3_EN);
    }
    else
    {
        OM_GPIO0->DATAOUT |= 1<<LED_G_PIN;
    }

    if((0x00 != pwm_b) && (rgb_enable&iPWM_B))
    {
        pwm_4 = pwm_b;
        i |= iPWM_4_EN;
    }
    else
    {
        OM_GPIO0->DATAOUT |= 1<<LED_B_PIN;
    }
    OM_PWM->PWMCON = i;
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
    nhjb_led_index = 0;

    logo_hint_time_count = 0x00;
    pwm_value = iPWM_MAX;
    blogo_status = 1;

    led_delay_count = drv_rtc_read(OM_RTC);
    bhint_process = true;
    led_hint_mode = led_cfg_index;
    blvd_hint_flag = 0;
    bidle_chg_flag = 0;
    busb_dpi_flag = 0;

    switch(led_cfg_index)
    {
        case iLED_CFG_POWER_ON:                 // 上电
            memcpy(led_dat, default_hint_led_tbl+8*iLED_CFG_POWER_ON, 8);

            if(iDEVICE_TYPE_USB == device_type)
                logo_ctrl |= iLED_WHITE;
            else if(iDEVICE_TYPE_24G == device_type)
                logo_ctrl |= iLED_RED;
            else if(iDEVICE_TYPE_BT0 >= device_type)
                logo_ctrl |= iLED_GREEN;
            else if(iDEVICE_TYPE_BT1 >= device_type)
                logo_ctrl |= iLED_BULE;
            else //if(iDEVICE_TYPE_BT2 >= device_type)
                logo_ctrl |= iLED_WHITE;

            break;
        case iLED_CFG_SENSOR_ERR:               // Sensor错误
            memcpy(led_dat, default_hint_led_tbl+8*iLED_CFG_SENSOR_ERR, 8);

            break;
        case iLED_CFG_CONNECT_ING:              // 对码中
            memcpy(led_dat, default_hint_led_tbl+8*iLED_CFG_CONNECT_ING, 8);

            if(iDEVICE_TYPE_USB == device_type)
                logo_ctrl |= iLED_RED;
            else if(iDEVICE_TYPE_24G == device_type)
                logo_ctrl |= iLED_GREEN;
            else //if(iDEVICE_TYPE_BT2 >= device_type)
                logo_ctrl |= iLED_BULE;

            break;
        case iLED_CFG_CONNECT_OK:               // 对码成功
            memcpy(led_dat, default_hint_led_tbl+8*iLED_CFG_CONNECT_OK, 8);

            if(iDEVICE_TYPE_USB == device_type)
                logo_ctrl |= iLED_RED;
            else if(iDEVICE_TYPE_24G == device_type)
                logo_ctrl |= iLED_GREEN;
            else //if(iDEVICE_TYPE_BT2 >= device_type)
                logo_ctrl |= iLED_BULE;

            break;
        case iLED_CFG_DPI_CHANGE:
            flash_read(iCFG_BANK_ADDR+16+(dpi_grade<<3), 8);
            memcpy(led_dat, flash_fifo, 8);
            busb_dpi_flag = 1;
            usb_5v_in_hint = 1;
            break;
        case iLED_CFG_LVD:              // 低电压提示
            memcpy(led_dat, default_hint_led_tbl+8*iLED_CFG_LVD, 8);
            blvd_hint_flag = 1;
            break;
        case iLED_CFG_CHAR_ING:
            memcpy(led_dat, default_hint_led_tbl+8*iLED_CFG_CHAR_ING, 8);

            break;
        case iLED_CFG_CHAR_OK:
            memcpy(led_dat, default_hint_led_tbl+8*iLED_CFG_CHAR_OK, 8);

            break;
        case iLED_CFG_OFF:
            logo_ctrl = iLOGO_OFF;
            pwm_write(0,0,0);
            bhint_process = false;

            break;
        case iLED_CFG_IDLE:
        default:
            led_mode_bak = iLOGO_INVALID;
            bhint_process = false;
            bidle_chg_flag = 1;
            break;
    }
    flash_on_time = hold_on_time;
    flash_off_time = hold_off_time;

    r_value >>= 2;
    g_value >>= 2; 
    b_value >>= 2;
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
    uint16_t time_temp;

    time_temp = drv_rtc_read(OM_RTC) - led_delay_count;
    time_temp >>= 8;

    if(iRGB_MASK != (logo_ctrl&iRGB_MASK))
        logo_rgb_index = ((logo_ctrl>>4)&0x07);

    if(blogo_status)
    {
        rgb_enable = rgb_en_tbl[logo_rgb_index&0x07];
        if(0 != flash_on_time)
            pwm_write(r_value, g_value, b_value);

        if(time_temp <= flash_on_time)
            return;
    }
    else
    {
        rgb_enable = 0;
        if(0 != flash_off_time)
            pwm_write(0, 0, 0);
        if(time_temp <= flash_off_time)
            return;

        if(iRGB_MASK == (logo_ctrl&iRGB_MASK))
        {
            if(6 <= logo_rgb_index)
                logo_rgb_index = 0;
            else
                logo_rgb_index++;
        }
    }

    led_delay_count = drv_rtc_read(OM_RTC);
    blogo_status = !blogo_status;

    if(0 == flash_times)
    {
        return;
    }

    if(0 != flash_times)
    {
        flash_times--;
    }

    if(0 == flash_times)
    {
        rgb_enable = 0;
        pwm_write(0, 0, 0);
        bhint_process = false;
        logo_cfg(iLED_CFG_IDLE);
        usb_5v_in_hint = 0;
    }
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
    switch(logo_ctrl&iMODE_MASK)
    {
        case iLOGO_DILE:

            break;
        case iLOGO_OFF:
            OM_GPIO0->DATAOUTSET = PWM_2_PIN|PWM_3_PIN|PWM_4_PIN;
            OM_PWM->PWMCON = 0x00000000;

            break;
        case iLOGO_FLASH:
            rgb_flash_process();

            break;
        case iLOGO_BREATHE:
            if(led_speed_lev >logo_hint_time_count)
            {
                logo_hint_time_count++;
                return;
            }
            logo_hint_time_count = 0;
            if(true == blogo_status)
            {
                if(pwm_count >= iPWM_MAX)
                    pwm_value = 0;
                else
                    pwm_value = (iPWM_MAX - pwm_count);
            }
            else
            {
                if(pwm_count >= iPWM_MAX)
                    pwm_value = iPWM_MAX;
                else
                    pwm_value = pwm_count;
            }

            if(pwm_count >= iPWM_MAX)   // 最亮和最暗的时间加长
            {
                pwm_count = 0;
                blogo_status = !blogo_status;

                if(false == blogo_status)
                {
                    if(iRGB_MASK == (logo_ctrl&iRGB_MASK))
                    {
                        if(6 <= logo_rgb_index)
                            logo_rgb_index = 0;
                        else
                            logo_rgb_index++;
                    }
                    if(0 != breath_times)
                    {
                        breath_times--;
                        if(0 == breath_times)
                        {
                            rgb_enable = 0;
                            pwm_write(0, 0, 0);
                            bhint_process = false;
                            logo_cfg(iLED_CFG_IDLE);
                            return;
                        }
                    }
                }
            }
            pwm_count++;

            if(iRGB_MASK != (logo_ctrl&iRGB_MASK))
                logo_rgb_index = ((logo_ctrl>>4)&0x07);
            rgb_enable = rgb_en_tbl[logo_rgb_index&0x07];

            pwm_write(pwm_value, pwm_value, pwm_value);
       
            break;
        case iLOGO_NH:
            if(led_speed_lev >logo_hint_time_count)
            {
                logo_hint_time_count++;
                return;
            }
            logo_hint_time_count = 0;
            if(0 == nhjb_led_index)
            {
                r_value = iPWM_NH_MAX;
                g_value++;
                b_value = 0;
                if(iPWM_NH_MAX <= g_value)
                {
                    g_value = iPWM_NH_MAX;
                    nhjb_led_index++;
                }
            }
            else if(1 == nhjb_led_index)
            {
                r_value--;
                g_value = iPWM_NH_MAX;
                b_value = 0;
                if(0 == r_value)
                    nhjb_led_index++;
            }
            else if(2 == nhjb_led_index)
            {
                r_value = 0;
                g_value = iPWM_NH_MAX;
                b_value++;
                if(iPWM_NH_MAX <= b_value)
                {
                    b_value = iPWM_NH_MAX;
                    nhjb_led_index++;
                }
            }
            else if(3 == nhjb_led_index)
            {
                r_value = 0;
                g_value--;
                b_value = iPWM_NH_MAX;
                if(0 == g_value)
                    nhjb_led_index++;
            }
            else if(4 == nhjb_led_index)
            {
                r_value++;
                g_value = 0;
                b_value = iPWM_NH_MAX;
                if(iPWM_NH_MAX <= r_value)
                {
                    r_value = iPWM_NH_MAX;
                    nhjb_led_index++;
                }
            }
            else //if(5 == nhjb_led_index)
            {
                r_value = iPWM_NH_MAX;
                g_value = 0;
                b_value--;
                if(0 == b_value)
                    nhjb_led_index = 0;
            }
            rgb_enable = 0x07;
            pwm_write(r_value, g_value, b_value);
      
            break;
    }
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

    if(true == bhint_process)
    {                                           // 提示处理
        rgb_flash_process();
        return;
    }

    if(USB_5V_PIN)      /* 5V插入 */
    {
        if(BAT_CHG_OK)
        {
            OM_PWM->PWMCON = 0x00000000;
            gpio_clear(LED_G_PIN);
            gpio_set(LED_R_PIN);
            gpio_set(LED_B_PIN);
        }
        else
        {
            OM_PWM->PWMCON = 0x00000000;
            gpio_clear(LED_R_PIN);
            gpio_set(LED_G_PIN);
            gpio_set(LED_B_PIN);
        }
        return;
    }

    if(iDEVICE_TYPE_USB == device_type)
    {
        if(0 != (usb_ctrl_flag&busb_suspend_resume))
            return;
    }
    else
    {
        if(!(ble_24g_ctrl&bom6239_sync_ok))
            return;
    }

    if(true == bhint_process)
    {                                           // 提示处理
        rgb_flash_process();
        return;
    }

    if( (false == bled_bright_en) ||  (adv_cfg_value&(1<<5)))
    {
        gpio_set(LED_R_PIN);
        gpio_set(LED_G_PIN);
        gpio_set(LED_B_PIN);
        OM_PWM->PWMCON = 0x00000000;
        return;
    }

    if(led_mode != led_mode_bak)
    {
        led_mode_bak = led_mode;
        pwm_init();
        switch(led_mode&iMODE_MASK)
        {         
            case iLOGO_OFF:                     // 关闭
                logo_ctrl = iLOGO_OFF;
                r_value = 0;
                g_value = 0;
                b_value = 0;

                break;
            default:
                i = (iCFG_LED_PARA_ADDR+((led_mode-2)<<3));
                flash_read(iCFG_BANK_ADDR+i, 8);
                memcpy(led_dat, flash_fifo, 8);
                r_value >>= 2;
                g_value >>= 2;
                b_value >>= 2;

                if((0xFF == logo_ctrl)
                    || (iLOGO_MAX < (logo_ctrl&0x0F)))
                    logo_ctrl = iLOGO_OFF;      // 无效模式，自动切换到关灯

                logo_ctrl &= 0x8F;
                logo_ctrl |= ((rgb_ctrl&0x07)<<4);
                break;
        }
    }

    if(iLED_LEV_MIN == led_light_lev)
    {
        OM_GPIO0->DATAOUTSET = PWM_2_PIN|PWM_3_PIN|PWM_4_PIN;
        OM_PWM->PWMCON = 0x00000000;
        return;
    }

    if(iLOGO_FLASH == (logo_ctrl&iMODE_MASK))
    {
        flash_on_time = hold_on_time;
        flash_off_time = hold_off_time;

        for(uint8_t i=0; i<led_speed_lev; i++)
        {
            flash_on_time += flash_on_time;
            flash_off_time += flash_off_time;
        }
    }
    rgb_process();
}



