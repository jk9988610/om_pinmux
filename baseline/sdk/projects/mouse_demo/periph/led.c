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
#include "key_io.h"
//-----------------------------------------------------------------------------;
// 常量定义区
//
#define iLED_RED                (0<<4)      // 红
#define iLED_GREEN              (1<<4)      // 绿
#define iLED_BULE               (2<<4)      // 蓝
#define iLED_PURPLE             (3<<4)      // 紫
#define iLED_YELLOW             (4<<4)      // 橙
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
unsigned char       const   dpi_rgb_en_tbl[]={
    iPWM_R,
    iPWM_G,
    iPWM_B,
    iPWM_B|iPWM_G,
    iPWM_R|iPWM_G,
    iPWM_B|iPWM_R,
    iPWM_R|iPWM_G|iPWM_B,
    0x07,
};

unsigned char       const   report_rgb_en_tbl[]={
    iLED_RED,
    iLED_GREEN,
    iLED_BULE,
    iLED_PURPLE,
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
//----------------------------------------------
    0x82,0x08,0x22,0x00,0xFF,0xFF,0xFF,0xFF,
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
    OM_PWM->PWMCR1 = 0x0000001C;
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
 void pwm_off(void)
{
    OM_PWM->PWMCON = 0x00000000;
    OM_GPIO0->DATAOUTCLR =
        (1u << LED_R_PIN) |
        (1u << LED_G_PIN) |
        (1u << LED_B_PIN);
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
    uint32_t set_mask = 0;
    uint32_t rgb_mask =
        (1u << LED_R_PIN) |
        (1u << LED_G_PIN) |
        (1u << LED_B_PIN);

    if ((pwm_r != 0) && (rgb_enable & iPWM_R))
        set_mask |= (1u << LED_R_PIN);

    if ((pwm_g != 0) && (rgb_enable & iPWM_G))
        set_mask |= (1u << LED_G_PIN);

    if ((pwm_b != 0) && (rgb_enable & iPWM_B))
        set_mask |= (1u << LED_B_PIN);

    OM_PWM->PWMCON = 0; //关闭PWM

    /* 修复：如果 R/G/B 全为 0，直接拉高引脚熄灭 */
    if (pwm_r == 0 && pwm_g == 0 && pwm_b == 0) {
        OM_GPIO0->DATAOUTSET = rgb_mask;
        return;
    }

    OM_GPIO0->DATAOUTCLR = rgb_mask; //清除RGB引脚
    OM_GPIO0->DATAOUTSET = set_mask; //设置RGB引脚
}
// }

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
                logo_ctrl |= iLED_GREEN; /* 硬件要求：2.4G 对应 P05(绿灯) */
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
        case iLED_CFG_REPORT_CHANGE:
            memcpy(led_dat, default_hint_led_tbl+8*8, 8);
            if (device_type == iDEVICE_TYPE_24G)
                logo_ctrl |= report_rgb_en_tbl[report_24g&0x03];
            else if (device_type == iDEVICE_TYPE_USB)
                logo_ctrl |= report_rgb_en_tbl[report_usb&0x03];
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
void rgb_flash_process(void) //RGB闪烁处理
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


/******************************************************************************
* 函数名称: logo_process
* 功能描述:
* 输入参数:
* 输出参数:
* 说    明:
******************************************************************************/
void logo_process(void)
{
    /* [终极拦截] 电池模式下（2.4G / BLE），灯效完全由 mode_led_hint 接管，
       底层原厂的 logo_process 一律不准跑，彻底切断底层乱点红灯的可能！ */
    if (iDEVICE_TYPE_USB != device_type)
    {
        OM_PWM->PWMCON = 0;
        /* P04/P05/P06 由 mode_led_hint 独占，此处不碰 */
        return;
    }

    /* USB 模式下，如果 DPI 正在跑快闪，也让路 */
    if (ind_mode == IND_MODE_FLASH)
    {
        return;
    }

    uint8_t i;


    if(true==bsave_status)
    {
        bsave_status = false;
        flash_save_status();
        if (device_type == iDEVICE_TYPE_24G && (ble_24g_ctrl&bom6239_sync_ok))
            brf_24g_reconnect = 1;
    } 

    if(true==bsave_driver_status)
    {
        bsave_driver_status = false;
        flash_save_driver_status();
        if (device_type == iDEVICE_TYPE_24G && (ble_24g_ctrl&bom6239_sync_ok))
            brf_24g_reconnect = 1;
    } 

    if(true == bhint_process)
    {                                           // 提示处理
        rgb_flash_process();
        return;
    }

    static bool bcharg_hint = 0;

    if(!USB_5V_PIN)     /* 电池供电：P04/P05/P06 由 mode_led_hint 独占 */
    {
        if(true != bhint_process && ind_mode == IND_MODE_OFF)
        {
            OM_PWM->PWMCON = 0;
            /* 不碰 P04/P05/P06 */
        }
    }
    else if(USB_5V_PIN)      /* 5V插入 */
    {
        /* [核心修复] 2.4G射频发射极易导致USB_5V_PIN产生瞬间毛刺高电平。
           如果当前不是USB模式，说明是电池供电受到了干扰，强行关灯即可，绝不能亮充电红灯！ */
        if (iDEVICE_TYPE_USB != device_type)
        {
            /* 毛刺高电平：不是 USB 模式，P04/P05/P06 不碰 */
            return;
        }

        bcharg_hint = true;
        OM_PWM->PWMCON = 0x00000000;
        /* P04/P05/P06 由 mode_led_hint 独占，充电只控 P00（S205 复用 low 灯） */
#ifdef LED_LOW_PIN
        if(BAT_CHG_OK)
            led_chg_off();          /* low 灯灭 = 充电完成 */
        else
            led_chg_on();           /* low 灯亮 = 充电中 */
#endif
        return;
    }
    else
    {
        if (bcharg_hint)
        {
            bcharg_hint = false;
            pwm_off();
        }
        
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

    // if(true == bhint_process)
    // {                                           // 提示处理
    //     rgb_flash_process();
    //     return;
    // }
    // rgb_enable = dpi_rgb_en_tbl[dpi_grade];
    // pwm_write(iPWM_MAX,iPWM_MAX,iPWM_MAX);

}


void sys_deep_sleep_process()
{
    if (USB_5V_PIN)
    {
        while (1)
        {
            if(BAT_CHG_OK)
            {
                OM_PWM->PWMCON = 0x00000000;
#ifdef LED_LOW_PIN
                led_chg_off();   /* low 灯灭 = 充电完成（S205 充电灯复用 low 灯） */
#endif
            }
            else
            {
                OM_PWM->PWMCON = 0x00000000;
#ifdef LED_LOW_PIN
                led_chg_on();    /* low 灯亮 = 充电中 */
#endif
            }
            drv_wdt_keep_alive(OM_WDT);
            delayms(1);
            key_io_scan();
            if (key_status)
            {
                NVIC_SystemReset();
            }

            if (!USB_5V_PIN)
            {
                break;
            }
            
            
        }
        
    }
    
}
