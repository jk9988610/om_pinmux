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
#include "main_24g.h"
#include "ex2_app_mouse.h"
#include "user_config.h"
#include "lvd.h"
#include "rf_protocol.h"

static bool ind_state = 0;
bool ind_mode = IND_MODE_OFF;
static uint32_t cur_rtc_time;
static ind_val_t cur_val;
static uint32_t lvd_dither_count;
static uint8_t bat_status_bak;
bool                bdpi_switch;
bool                bmanual_pair = false; /* 0=自动对码慢闪, 1=长按DPI手动对码快闪 */
uint32_t            mode_led_flash_time = 0;
uint8_t             mode_led_flash_state = 0;

void ind_on()
{
    switch(cur_val.ind_color & 0x0F)
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
            led_r_on();
            led_g_on();
            led_b_on();
            break;
        case IND_DPI:
#ifdef LED_LOW_PIN
            led_low_on();
#endif
            break;
        default:
            break;
    }
}

void ind_off()
{
#ifdef LED_LOW_PIN
    if (cur_val.ind_color == IND_DPI)
        led_low_off();
#endif
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
            dpi_val.ind_color = IND_PURPLE;
            break;
        case 4:
            dpi_val.ind_color = IND_YELLOW;
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
/* 灯效状态机文件级变量，mode_led_hint 内使用 */
uint8_t  last_conn_24g = 0;
uint32_t conn_tick_24g = 0;
uint8_t  last_conn_ble = 0;
uint32_t conn_tick_ble = 0;
uint8_t  last_usb = 0;
uint32_t conn_tick_usb = 0;

void mode_led_hint()
{
    uint32_t rtc_time = drv_rtc_read(OM_RTC);
    static uint8_t applied_mask = 0xFF;
    static uint8_t force_write = 1;
    static uint8_t last_device_type = 0xFF;
    uint8_t target_mask = 0;

    extern uint8_t  last_conn_24g;
    extern uint32_t conn_tick_24g;
    extern uint8_t  last_conn_ble;
    extern uint32_t conn_tick_ble;
    extern uint8_t  last_usb;
    extern uint32_t conn_tick_usb;

    /* device_type 变化时重置所有状态，避免跨模式残留 */
    if(last_device_type != device_type)
    {
        last_device_type = device_type;
        applied_mask = 0xFF;
        force_write = 1;
        last_conn_24g = 0; conn_tick_24g = 0;
        last_conn_ble = 0; conn_tick_ble = 0;
        last_usb = 0;      conn_tick_usb = 0;
        mode_led_flash_state = 0;
        mode_led_flash_time = rtc_time;
    }

    /* ===== 最高优先级：USB 待枚举窗口 ===== */
    static uint8_t  last_5v_level = 0;
    static uint32_t fivev_edge_tick = 0;
    uint8_t now_5v = USB_5V_PIN ? 1 : 0;

    if(now_5v && !last_5v_level)
        fivev_edge_tick = rtc_time;
    last_5v_level = now_5v;

    /* 5V 插入但尚未枚举成 USB 的 2 秒内，强制关灯，打断所有状态（包括 DPI） */
    if(now_5v && iDEVICE_TYPE_USB != device_type
       && (uint32_t)(rtc_time - fivev_edge_tick) < mMS_TO_TICK(2000))
    {
        applied_mask = 0xFF;
        force_write = 1;
        if(ind_mode == IND_MODE_FLASH) ind_mode = IND_MODE_OFF; /* 打断底层误触发的 DPI 状态 */
        return;
    }

    /* ===== ① STATE_DPI：用户主动操作，独占 LED ===== */
    if(ind_mode == IND_MODE_FLASH)
    {
        if(ind_state)
        {
            if(mMS_TO_TICK(cur_val.ind_on_time) > (rtc_time - cur_rtc_time))
            {
                applied_mask = 0xFF;
                return;
            }
            cur_rtc_time = rtc_time;
            ind_state = 0;
            ind_off();
        }
        else
        {
            if(mMS_TO_TICK(cur_val.ind_off_time) > (rtc_time - cur_rtc_time))
            {
                applied_mask = 0xFF;
                return;
            }
            cur_rtc_time = rtc_time;
            cur_val.ind_times--;
            if(cur_val.ind_times == 0)
            {
                bdpi_switch = false;
                ind_mode = IND_MODE_OFF;
            }
            else
            {
                ind_state = 1;
                ind_on();
            }
        }
        applied_mask = 0xFF;
        force_write = 1;
        return;
    }

    /* ===== ② STATE_USB：枚举成功，P04 亮 3 秒 ===== */
    if(iDEVICE_TYPE_USB == device_type)
    {
        if(!last_usb)
        {
            last_usb = 1;
            conn_tick_usb = rtc_time;
        }
        if((uint32_t)(rtc_time - conn_tick_usb) < mMS_TO_TICK(3000))
            target_mask |= (1<<0);
    }
    /* ===== ③ STATE_24G ===== */
    else if(iDEVICE_TYPE_24G == device_type)
    {
        extern unsigned char dat_24g_0[];
        #define b24g_work_mode  dat_24g_0[27]
        #define iMCU_MODE_NO_DONGLE_ 2

        if(iRF_MODE_CONNECT == rf_mode_type)    /* 对码中：快闪 */
        {
            if(last_conn_24g)
            {
                mode_led_flash_state = 0;
                mode_led_flash_time = rtc_time;
            }
            last_conn_24g = 0;
            uint32_t period = bmanual_pair ? 150 : 500;
            if(mMS_TO_TICK(period) <= (rtc_time - mode_led_flash_time))
            {
                mode_led_flash_time = rtc_time;
                mode_led_flash_state = !mode_led_flash_state;
            }
            if(mode_led_flash_state)
                target_mask |= (1<<1);
        }
        else if(iMCU_MODE_NO_DONGLE_ == b24g_work_mode)    /* 找不到接收器：慢闪 */
        {
            if(last_conn_24g)    /* 从已连接切过来：从灭开始，立即切 */
            {
                mode_led_flash_state = 0;
                mode_led_flash_time = rtc_time;
            }
            last_conn_24g = 0;
            if(mMS_TO_TICK(500) <= (rtc_time - mode_led_flash_time))
            {
                mode_led_flash_time = rtc_time;
                mode_led_flash_state = !mode_led_flash_state;
            }
            if(mode_led_flash_state)
                target_mask |= (1<<1);
        }
        else if((iRF_MODE_NORMAL == rf_mode_type) && (ble_24g_ctrl & bom6239_sync_ok))
        {
            /* [核心修复] 底层必须明确是 NORMAL 状态且收到过握手包，才认为是真连接 */
            if(!last_conn_24g)
            {
                last_conn_24g = 1;
                conn_tick_24g = rtc_time;
            }
            if((uint32_t)(rtc_time - conn_tick_24g) < mMS_TO_TICK(3000))
                target_mask |= (1<<1);
        }
        else
        {
            /* 假同步或中间态，保持灭灯 */
            last_conn_24g = 0;
        }
    }
    /* ===== ④ STATE_BLE ===== */
    else if(iDEVICE_TYPE_BT2 >= device_type)
    {
        if(hid_notification_is_enabled())    /* 已连接：亮 3 秒 */
        {
            if(!last_conn_ble)
            {
                last_conn_ble = 1;
                conn_tick_ble = rtc_time;
            }
            if((uint32_t)(rtc_time - conn_tick_ble) < mMS_TO_TICK(3000))
                target_mask |= (1<<2);
        }
        else    /* 广播中：快闪 150ms（V196 原样） */
        {
            last_conn_ble = 0;
            if(mMS_TO_TICK(150) <= (rtc_time - mode_led_flash_time))
            {
                mode_led_flash_time = rtc_time;
                mode_led_flash_state = !mode_led_flash_state;
            }
            if(mode_led_flash_state)
                target_mask |= (1<<2);
        }
    }

    /* ===== 输出层：只写变化位 ===== */
    uint8_t changed;
    if(force_write)
    {
        changed = 0x07;   /* 未知状态：强制写所有位 */
        force_write = 0;
    }
    else
    {
        changed = target_mask ^ applied_mask;
    }
    if(changed & (1<<0))
    {
        if(target_mask & (1<<0)) OM_GPIO0->DATAOUTCLR = (1u << LED_MODE_R_PIN);
        else                     OM_GPIO0->DATAOUTSET = (1u << LED_MODE_R_PIN);
    }
    if(changed & (1<<1))
    {
        if(target_mask & (1<<1)) OM_GPIO0->DATAOUTCLR = (1u << LED_MODE_G_PIN);
        else                     OM_GPIO0->DATAOUTSET = (1u << LED_MODE_G_PIN);
    }
    if(changed & (1<<2))
    {
        if(target_mask & (1<<2)) OM_GPIO0->DATAOUTCLR = (1u << LED_MODE_B_PIN);
        else                     OM_GPIO0->DATAOUTSET = (1u << LED_MODE_B_PIN);
    }
    applied_mask = target_mask;
}


/* [新增] 常亮 2 秒后自动关灯 (用于对码成功或蓝牙连接) */
void ind_on_2s_then_off(uint8_t color)
{
    ind_val_t ind_val = {
        .ind_color = color,
        .ind_times = 1,
        .ind_on_time = 2000,
        .ind_off_time = 0,
    };
    ind_config(&ind_val);
}
