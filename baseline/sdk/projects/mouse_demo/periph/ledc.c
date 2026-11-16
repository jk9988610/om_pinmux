/**
 * @file ledc.c
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2026-01-21
 * 
 * @copyright Copyright (c) 2026
 * 
 */
#include "ledc.h"
#include "string.h"
#include "sensor.h"
#include "lvd.h"
#include "led.h"
#include "key_io.h"
#include "flash_process.h"

//-----------------------------------------------------------------------------;
// Macro
//
#define BREATH_DELAY_24G      16
#define BREATH_DELAY_USB      32
#define BREATH_DELAY_BLE      4

//-----------------------------------------------------------------------------;
// Local Variable
//
static uint8_t ledc_data[LEDC_RGB_DATA_SIZE] = {0};
static ledc_val_t ledc_val;
static bool bargb_light = 0;
static uint16_t bright_delay = 0;
   
uint32_t pre_timeStamp;
extern bool     bpower_down_hint;
extern bool     bbat_low_power;
extern bool     bpower_down;

bool            bledc_data_send;

/* 未来参数化入口：接 board.ledc_colors 时，这里改为
 *   #ifdef LEDC_COLOR_TAB_INIT
 *   uint8_t const dpi_rgb_tab[8][3] = LEDC_COLOR_TAB_INIT;
 *   #else
 *   ...默认值...
 *   #endif
 * 当前（路径 C）保留硬编码，改色需同步 omcfg/templates/ledc/ledc.c
 * 和 baseline/sdk/.../ledc.c 两份。
 */
uint8_t const dpi_rgb_tab[8][3] = {
    {240,   0,   0},   /* 0: 红（CH04 现状） */
    {  0, 240,   0},   /* 1: 绿（CH04 现状） */
    {  0,   0, 240},   /* 2: 蓝（CH04 现状） */
    {240,   0, 240},   /* 3: 紫（RED|BLUE 满亮，CH04 现状） */
    {240, 240,   0},   /* 4: 黄（RED|GREEN 满亮，CH04 现状） */
    {  0, 240, 240},   /* 5: 青（GREEN|BLUE 满亮，CH04 现状） */
    {240, 240, 240},   /* 6: 白（新增，防越界） */
    {  0,   0,   0},   /* 7: 黑（新增，保留） */
};
//-----------------------------------------------------------------------------;
// table
//

const Ind_Val_t ind_lvd = {
    .On_Time = mMS_TO_TICK(200),
    .Off_Time = mMS_TO_TICK(200),
    .Blink_Times = 0x3,
    .On_State = 1
} ;

const Ind_Val_t ind_dpi = {
    .On_Time = mMS_TO_TICK(200),
    .Off_Time = mMS_TO_TICK(200),
    .Blink_Times = 4,
    .On_State = 1
} ;

const Ind_Val_t ind_report = {
    .On_Time = mMS_TO_TICK(200),
    .Off_Time = mMS_TO_TICK(200),
    .Blink_Times = 3,
    .On_State = 1
} ;

const Ind_Val_t ind_power_down = {
    .On_Time = mMS_TO_TICK(175),
    .Off_Time = mMS_TO_TICK(175),
    .Blink_Times = 5,
    .On_State = 1
} ;


//-----------------------------------------------------------------------------;
// Public Function
//
void ledc_data_write(uint8_t rgb_enable, uint8_t color_enable, uint8_t red_value, uint8_t green_value, uint8_t blue_value)
{
    if (color_enable & LEDC_RED)
    {
        ledc_val.ind_val.Rgb_data[rgb_enable*3+1] = red_value;
    }
    else
    {
        ledc_val.ind_val.Rgb_data[rgb_enable*3+1] = 0;
    }

    if (color_enable & LEDC_GREEN)
    {
        ledc_val.ind_val.Rgb_data[rgb_enable*3] = green_value;
    }
    else
    {
        ledc_val.ind_val.Rgb_data[rgb_enable*3] = 0;
    }

    if (color_enable & LEDC_BULE)
    {
        ledc_val.ind_val.Rgb_data[rgb_enable*3+2] = blue_value;
    }
    else
    {
        ledc_val.ind_val.Rgb_data[rgb_enable*3+2] = 0;
    }
    
}


static void ledc_write()
{
    drv_ledc_write(OM_LEDC,ledc_data,sizeof(ledc_data));
}

/**
 * @brief  
 * @note   
 * @retval None
 */
static void ledc_init()
{
    ledc_config_t cfg = {
        .reset_cycles = 82*48-1,        /* 48MHz,80us */
        .long_pulse_cycles = 36 -1 ,    /* 0.8us * 48 */ 
        .short_pulse_cycles = 19 - 1,   /* 0.4us * 48 */
    };
    drv_ledc_init(OM_LEDC,&cfg);
    drv_pmu_ledc_sel(PMU_LEDC_SEL_IO_05);
    memset(&ledc_val,0,sizeof(ledc_val));
}

/**
 * @brief  
 * @note   
 * @retval None
 */
void ledc_neon(uint8_t reset_state)
{
    if(reset_state)
    {
        led_mode_bak = led_mode;
        ledc_mode_init();
        memcpy(ledc_data,ledc_data_tab,sizeof(ledc_data));
        ledc_write(); 
    }
    else
    {

        if (device_type != iDEVICE_TYPE_USB && !(ble_24g_ctrl & bom6239_sync_ok) || !bled_bright_en)
        {
            memset(ledc_data,0,sizeof(ledc_data));
            ledc_write();
            return;
        }

        // if (bat_status & bcharging)
        // {
        //     if (!(bat_status & bcharge_ok))
        //     {
        //         for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
        //         {
        //             ledc_single_ctrl(i,0x07,LEDC_DATA_MAX,0,0);
        //         }
                
        //         memcpy(ledc_data,ledc_data_tab,sizeof(ledc_data));
        //         ledc_write();
        //         return;
        //     }
            
        // }
        
        ledc_mode_scan();

        memcpy(ledc_data,ledc_data_tab,sizeof(ledc_data));
        ledc_write();
        
    }
}

//-----------------------------------------------------------------------------;
// Public Function
//

/**
 * @brief  
 * @note   
 * @param  cmd: 
 * @retval None
 */
uint32_t ledc_cmd(Ledc_Cmd_t cmd,void* arg)
{
    blvd_hint_flag = false;
    busb_dpi_flag = false;
    switch(cmd)
    {   
        case Cmd_Init:
            LEDC_POWER_SET(POWER_ON);
            ledc_init();
            break;

        case Cmd_Power_Set:
            memset(ledc_data,0,sizeof(ledc_data));
            ledc_write();
            LEDC_POWER_SET((uint32_t)arg);
            if (!arg)
                bargb_light = false;
            break;

        case Cmd_Power_Down_Cfg:
            ledc_val.is_indicate = true;
            memcpy(&ledc_val.ind_val,&ind_power_down,sizeof(ledc_val.ind_val));
            break;

        case Cmd_Lvd_Indicate_Cfg:
            ledc_val.is_indicate = true;
            ledc_val.is_lvd = true;
            ledc_val.is_charging = false;
            memcpy(&ledc_val.ind_val,&ind_lvd,sizeof(ledc_val.ind_val));
            for (uint8_t i = 0; i < LEDC_RGB_NUMBER; i++)
            {
                ledc_data_write(i,0x07,dpi_rgb_tab[0][0],dpi_rgb_tab[0][1],dpi_rgb_tab[0][2]);
            }
            blvd_hint_flag = true;
            break;

        case Cmd_Dpi_Indicate_Cfg:
            busb_dpi_flag = true;
            ledc_val.is_indicate = true;
            ledc_val.is_lvd = true;
            ledc_val.is_charging = false;
            memcpy(&ledc_val.ind_val,&ind_lvd,sizeof(ledc_val.ind_val));
            for (uint8_t i = 0; i < LEDC_RGB_NUMBER; i++)
            {
                ledc_data_write(i,0x07,dpi_rgb_tab[dpi_grade&0x07][0],dpi_rgb_tab[dpi_grade&0x07][1],dpi_rgb_tab[dpi_grade&0x07][2]);
            }
            break;

        case Cmd_Rep_Indicate_Cfg:
            busb_dpi_flag = true;
            ledc_val.is_indicate = true;
            ledc_val.is_lvd = false;
            ledc_val.is_charging = false;
            memcpy(&ledc_val.ind_val,&ind_dpi,sizeof(ledc_val.ind_val));
            for (uint8_t i = 0; i < LEDC_RGB_NUMBER; i++)
            {
                if (device_type == iDEVICE_TYPE_24G)
                    ledc_data_write(i,0x07,dpi_rgb_tab[report_24g&0x03][0],dpi_rgb_tab[report_24g&0x03][1],dpi_rgb_tab[report_24g&0x03][2]);
                else
                    ledc_data_write(i,0x07,dpi_rgb_tab[report_usb&0x03][0],dpi_rgb_tab[report_usb&0x03][1],dpi_rgb_tab[report_usb&0x03][2]);
            }
            break;

        case Cmd_Idle_Cfg:
            ledc_val.is_lvd = false;
            ledc_val.is_indicate = false;
            memset(&ledc_data,0,sizeof(ledc_data));
            ledc_write();
            ledc_neon(1);
            break;

        default:
            break;
    }

    pre_timeStamp = drv_rtc_read(OM_RTC);

    return 0;
}

/**
 * @brief  continue to send rgb data
 * @note   
 * @retval None
 */
void ledc_polling()
{
    uint32_t cur_timeStamp = drv_rtc_read(OM_RTC);
    
    if(true == ledc_val.is_indicate)
    {
        bledc_data_send = true;
        if(true == ledc_val.ind_val.On_State)
        {
            if(ledc_val.ind_val.On_Time > cur_timeStamp - pre_timeStamp)
            {
                memcpy(ledc_data,ledc_val.ind_val.Rgb_data,sizeof(ledc_data));
                ledc_write();
                return;
            }
            pre_timeStamp = cur_timeStamp;
            ledc_val.ind_val.On_State = false;
            return;
        }
        else
        {
            if(ledc_val.ind_val.Off_Time > cur_timeStamp - pre_timeStamp)
            {
                memset(ledc_data,0,sizeof(ledc_data));
                ledc_write();
                return;
            }
            pre_timeStamp = cur_timeStamp;
            ledc_val.ind_val.Blink_Times--;
            if(0 == ledc_val.ind_val.Blink_Times)
            {
                ledc_neon(1);
                ledc_val.is_indicate = false;
                return;
            }

            ledc_val.ind_val.On_State = true;
        }
    }   
    else
    {
        if (led_mode != led_mode_bak)
        {
            // led_mode_bak = led_mode;
            bledc_data_send = true;
            ledc_neon(1);
            return;
        }
        
        if ((cur_timeStamp - pre_timeStamp) > mMS_TO_TICK(8))
        {
            bledc_data_send = true;
            pre_timeStamp = cur_timeStamp;
            ledc_neon(0);
        }
        else
        {
            bledc_data_send = false;
        }
        
    }
}

void ledc_write0(void)
{
    memset(ledc_data,0,sizeof(ledc_data));
    ledc_write();    
}

void sys_deepsleep_process(void)
{
    if (USB_5V_PIN)
    {
        while (1)
        {
            if (!BAT_CHG_OK)
            {
                led_r_on();
            }
            

            drv_wdt_keep_alive(OM_WDT);

            delayms(8);

            key_io_scan();
            if (key_status)
            {
                NVIC_SystemReset();
            }
            
            if (!USB_5V_PIN || BAT_CHG_OK)
            {
                break;
            }
        }        
    }
    led_r_off();
    
}
