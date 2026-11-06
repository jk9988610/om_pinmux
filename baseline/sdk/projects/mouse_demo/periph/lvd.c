/**
 * @file lvd.c
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2025-05-22
 * 
 * @copyright Copyright (c) 2025
 * 
 */

#include "om_driver.h"
#include "main.h"
#include "led.h"
#include "lvd.h"
#include "time_delay.h"
#include "RF_PROTOCOL.H"
#include "key_io.h"
//-----------------------------------------------------------------------------;
// macro define 
//
#define is_5v_in()  gpio_read(USB_5V)
#define is_chg_ok()  gpio_read(BAT_CHG_PIN)

#define	mPOF_ENABLE     		OM_POF->POFCON |= 0x08
#define	mPOF_DISABLE     		OM_POF->POFCON &= ~0x08

#define	mPOF_WARM_READ     		(OM_POF->POFCON & 0x01)

/* threshold */
/* A2 */
#define	iLVD_0_VALUE            (0x02)
#define	iLVD_90_VALUE           (0x08)
#define	iLVD_100_VALUE          (0x09)

/* A3 */
#define	iLVD_0_VALUE_A3         (0x02)
#define	iLVD_90_VALUE_A3        (0x0F)
#define	iLVD_100_VALUE_A3       (0x10)

//-----------------------------------------------------------------------------;
// variable define 
//
bool    pre_bat_charge;
uint8_t bat_status;
uint8_t lvd_value;          
uint8_t bat_value;

bool    bkey_bat_update;
bool    bbat_update;

uint8_t lvd_scan_count;
uint32_t bat_power_delay;
uint32_t bat_delay_count;
uint32_t charge_time_count;
uint16_t threshold;
bool     bpower_down_hint;
bool     bbat_low_power;
bool     bpower_down;
//-----------------------------------------------------------------------------;
// extern variable declaration 
//
extern bool bsave_status;

//-----------------------------------------------------------------------------;
// table define 
//
uint8_t const bat_li_value_tbl[] = {       /* battery level for OM6239 V_A2 (default version)  */
    0,                  
    5,                  
    10,                 
    25,                 
    50,                 
    75,                 
    85,                
    95,
    100,
};

uint8_t const bat_li_value_a3_tbl[] = {     /* battery level for OM6239 V A3 (coming soon) */
    0  ,
    0  ,
    5  ,
    15 ,
    20 ,
    30 ,
    40 ,
    50 ,
    60 ,
    70 ,
    80 ,
    80 ,
    90 ,
    100 ,
    100,
};

//-----------------------------------------------------------------------------;
// local function  
//

/**
 * @brief 
 * 
 * @param threshold 
 */
#define mPOF_SET                 {OM_POF->POFCON &= ~0x1F8;\
                                    OM_POF->POFCON |= threshold;}

//-----------------------------------------------------------------------------;
// public function  
//

/**
 * @brief  Obtain the actual value after the approximate value
 * @note   
 * @retval None
 */
void lvd_check(void)
{
    for(uint8_t i=0; i<7; i++)
    {
        mPOF_SET;
        mPOF_ENABLE;
        delayus(5);
        if(0 != mPOF_WARM_READ)
            break;
        if(0 == threshold)
            break;
        threshold -= 0x10;
    }
}

/**
 * @brief return the index of battery level table..
 * @note   see the BAT TEST TABLE
 * @retval 
 */
uint8_t bat_voltage_check(void)
{
    uint8_t i;

	OM_POF->POFCON &= ~0x0E;
	OM_POF->POFCON |= (LVD_CHECK_INDEX << 1);

    threshold = POF_THRESHOLD_1_225V;
    mPOF_SET;
	mPOF_ENABLE;
    delayus(8);
    if(0 != mPOF_WARM_READ)
    {                                           // > 1.225v
        threshold = POF_THRESHOLD_1_400V;
        mPOF_SET;
        mPOF_ENABLE;
        delayus(8);
        if(0 != mPOF_WARM_READ)
        {                                       // > 1.400v
            threshold = POF_THRESHOLD_1_550V;
            lvd_check();
        }
        else
        {                                       // < 1.400v
            threshold = POF_THRESHOLD_1_400V;
            lvd_check();
        }
    }
    else
    {                                           // < 1.225v
        threshold = POF_THRESHOLD_1_050V;
        mPOF_SET;
        mPOF_ENABLE;
        delayus(8);
        if(0 != mPOF_WARM_READ)
        {                                       // > 1.050v
            threshold = POF_THRESHOLD_1_225V;
            lvd_check();
        }
        else
        {                                       // < 1.050v
            threshold = POF_THRESHOLD_1_050V;
            lvd_check();
        }
    }
    mPOF_DISABLE;
    i = ((threshold>>4)+1);
    return i;
}

/**
 * @brief init battery power
 * 
 */
void bat_init(void)
{
    bat_status |= blvd_power_on;
    bat_delay_count = 0;
    charge_time_count = 0;
}

/**
 * @brief  take actually battery level for different chip
 * @note   
 * @param  bat_level: 
 * @retval 
 */
 uint8_t bat_level_cal(uint8_t bat_level)
{
    if((iOM6239_A3_0 == OM_RF->LINE)||(iOM6239_A3_1 == OM_RF->LINE))
    {
        if(iLVD_0_VALUE_A3>=bat_level)
            bat_level = 0;
        else if(iLVD_100_VALUE_A3<=bat_level)
            bat_level = 100;
        else
            bat_level = bat_li_value_a3_tbl[(bat_level-iLVD_0_VALUE_A3)&0x0F];
    }
    else
    {
        if(iLVD_0_VALUE>=bat_level)
            bat_level = 0;
        else if(iLVD_100_VALUE<=bat_level)
            bat_level = 100;
        else
            bat_level = bat_li_value_tbl[(bat_level-iLVD_0_VALUE)&0x07];
    }
    
    return bat_level;
}

/**
 * @brief 低电压检测与电池电量处理
 * 
 */
void low_bat_pd()
{   
    if (USB_5V_PIN)
    {
        return;
    }
    
    pwm_off();
    extern void ex2_stk_uninit();
    ex2_stk_uninit();

    drv_encoder_control(OM_ENCODER, ENCODER_CONTROL_STOP, 0);
    drv_senscan_stop();
    extern void sensor_sleep(void);
    sensor_sleep();
    DRV_RCC_CLOCK_ENABLE(RCC_CLK_SENSCAN, 0U);
    DRV_RCC_CLOCK_ENABLE(RCC_CLK_ENCODER, 0U);
    for (size_t i = 0; i < 3; i++)
    {
        ledc_write0();
        delayms(8);
    }
    delayms(100);
    ledc_sleep();
    delayms(500);
    mouse_periph_wakeup_enable(WAKEUP_SLEEP_LEVEL2);
    drv_pmu_set_low_power_mode(PMU_LPM_DEEP_SLEEP);
    while(1);
}


/**
 * @brief 
 * 
 */
void power_check()
{
    int times = 0;
    for(int count = 0;count < 10;count++)
    {   
        uint8_t i = bat_voltage_check();
        uint8_t pd_val = ((iOM6239_A3_0 == OM_RF->LINE)||(iOM6239_A3_1 == OM_RF->LINE)) ? iLVD_0_VALUE_A3 : iLVD_0_VALUE;
        if(i > pd_val)
            times ++;
        
        delayus(10);
    }
    if(times < 5)
        low_bat_pd();
}


/** 
 * @brief BAT TEST TABLE FOR OM6239 A3 CHIP
 * 
 * *+----------------------------+---------+------------------------+------------+
 * *|   bat_voltage_check() rtv  |     Range of LVD PIN    |   Range of VBAT     |
 * *+----DEC-------+------HEX----+-------------------------+---VBAT---+-SHOW TBL-+
 * *|    0         |       00    |   <=0.900               |          |          |
 * *|    1         |       01    |   0.900 < vbat < 0.925  |          |          |
 * *|    2         |       02    |   0.925 < vbat < 0.950  |          |          |
 * *|    3         |       03    |   0.950 < vbat < 0.975  |          |          |
 * *|    4         |       04    |   0.975 < vbat < 1.000  |          |          |
 * *|    5         |       05    |   1.000 < vbat < 1.025  | 3.000 V  |    0   % |    <---- iLVD_0_VALUE_A3 = 0x05
 * *|    6         |       06    |   1.025 < vbat < 1.050  | 3.075 V  |    5   % |
 * *|    7         |       07    |   1.050 < vbat < 1.075  | 3.150 V  |    10  % |
 * *|    8         |       08    |   1.075 < vbat < 1.100  | 3.225 V  |    15  % |    
 * *|    9         |       09    |   1.100 < vbat < 1.125  | 3.300 V  |    20  % |
 * *|    10        |       0A    |   1.125 < vbat < 1.150  | 3.375 V  |    30  % |
 * *|    11        |       0B    |   1.150 < vbat < 1.175  | 3.450 V  |    40  % |
 * *|    12        |       0C    |   1.175 < vbat < 1.200  | 3.525 V  |    50  % |
 * *|    13        |       0D    |   1.200 < vbat < 1.225  | 3.600 V  |    60  % |
 * *|    14        |       0E    |   1.225 < vbat < 1.250  | 3.675 V  |    70  % |
 * *|    15        |       0F    |   1.250 < vbat < 1.275  | 3.750 V  |    80  % |
 * *|    16        |       10    |   1.275 < vbat < 1.300  | 3.825 V  |    80  % |
 * *|    17        |       11    |   1.300 < vbat < 1.325  | 3.900 V  |    90  % |
 * *|    18        |       12    |   1.325 < vbat < 1.350  | 3.975 V  |    90  % |    <---- iLVD_90_VALUE_A3 = 0x12 
 * *|    19        |       13    |   1.350 < vbat < 1.375  | 4.050 V  |    100 % |    <---- iLVD_100_VALUE_A3 = 0x13
 * *|    20        |       14    |   1.375 < vbat < 1.400  | 4.125 V  |          |    
 * *|    21        |       15    |   1.400 < vbat < 1.425  | 4.200 V  |          |               
 * *|    22        |       16    |   1.425 < vbat < 1.450  |          |          |               ^
 * *|    23        |       17    |   1.450 < vbat < 1.475  |          |          |               |
 * *|    24        |       18    |   1.475 < vbat < 1.500  |          |          |               |
 * *|    25        |       19    |   1.500 < vbat < 1.525  |          |          |               |
 * *|    26        |       1A    |   1.525 < vbat < 1.550  |          |          |               |
 * *|    27        |       1B    |   1.550 < vbat          |          |          |               |
 * *+----------------------------+---------+---------------+----------+----------+               |
 * *                                                                                             |
 * * Just modify the various thresholds of the LVD according to the customer's needs-------------+
 */

/**
 * @brief  check battery 
 * @note   
 * @retval None
 */
void bat_check(void)
{
    uint8_t bat_dat, bat_temp;
    uint32_t rtc_temp = drv_rtc_read(OM_RTC);
    static uint32_t lvd_hint_time = 0,lvd_filter_time = 0;
    bat_dat = bat_voltage_check();              /* get table index. */

    uint8_t pd_val = ((iOM6239_A3_0 == OM_RF->LINE)||(iOM6239_A3_1 == OM_RF->LINE)) ? iLVD_0_VALUE_A3 : iLVD_0_VALUE;
    if(bat_dat <= pd_val)                 /* SHUTDOWN */
    {
        if(!is_5v_in())
        {
            low_bat_pd();
        }
    }
    else if(bat_dat <= (pd_val + 2))      /* LOW POWER INDICATION */
    {   
        lvd_filter_time = rtc_temp;
        bbat_low_power = true;
        bpower_down_hint = false;
        if (bat_status & bcharging)
        {
            blvd_hint_flag = false;
        }
        else
        {
            if((!is_5v_in()) && (bom6239_sync_ok & ble_24g_ctrl))
            {
                if(false == blvd_hint_flag && !busb_dpi_flag)
                {
                    if ((rtc_temp - lvd_hint_time)  > mMS_TO_TICK(3500))
                    {
                        lvd_hint_time = rtc_temp;
                        blvd_hint_flag = true;
                    }
                    
                }
            }
        }
    }
    else
    {
        bbat_low_power = false;
        bpower_down_hint = false;
        if(true == blvd_hint_flag)
        {
            if ((rtc_temp - lvd_filter_time) > mMS_TO_TICK(3000))
            {
                /* code */
                blvd_hint_flag = false;
            }
            
        }
    }

    if(0 != (bat_status&blvd_power_on))
    {
        if(0x1F == (bat_status&0x1F))
        {                                       
            if(1000>sys_tick_count)
                return;                         // 解决上电电量不稳定的问题
            bat_status &= 0xE0;
            bat_status |= bat_dat;
            bsave_status = true;
        }

        if((true == pre_bat_charge)&&(0==(bat_status&bcharging)))
        {
            if(1000>sys_tick_count)
                return;                         // 解决上电电量不稳定的问题
            bat_status &= 0xE0;
            bat_status |= bat_dat;
            bsave_status = true;
        }

        lvd_value = (bat_status&0x1F);
        bat_value = bat_level_cal(lvd_value);
        bat_status &= ~blvd_power_on;
        bbat_update = true;
        return;
    }

    if(0 != (bat_status&bcharging))
    {                                           // 充电中
        if(3>=bat_dat)
        {
            if(false == pre_bat_charge)
            {                                   // 充电中，并且电压无效，保存充电状态
                pre_bat_charge = true;
                bsave_status = true;
            }
            return;
        }
    }

    if(0x07 == key_data)
    {
        if(false == bkey_bat_update)
        {
            bkey_bat_update = true;

            if(bat_dat != lvd_value)
            {
                lvd_value = bat_dat;

                bat_value = bat_level_cal(bat_dat);
                bat_status &= 0xE0;
                bat_status |= lvd_value;
                bsave_status = true;
                bbat_update = true;
            }
        }
    }
    else
    {
        bkey_bat_update = false;
    }



    if(bat_dat != lvd_value)
    {
        if(BATTERY_LEVEL_CHANGE_DELAY < rtc_temp - bat_power_delay)
        {
            bat_power_delay = rtc_temp;

            uint8_t lvd_value_temp;
            if((iOM6239_A3_0 == OM_RF->LINE)||(iOM6239_A3_1 == OM_RF->LINE))
                lvd_value_temp = iLVD_0_VALUE_A3;
            else
                lvd_value_temp = iLVD_0_VALUE;
            lvd_value = bat_dat;

            bat_status &= 0xE0;
            bat_status |= lvd_value;
            bat_value = bat_level_cal(lvd_value);
            bsave_status = true;
            bbat_update = true;

        }
    }
    else
    {
        bat_power_delay = rtc_temp;
    }
    
}


/**
 * @brief 
 * 
 */
void bat_ind_process(void)
{
    static uint32_t charge_hint_index = 0, charg_ok_count = 0;
    static bool     blvd_hint_dir = 0;

    rtc_cur_value = drv_rtc_read(OM_RTC);
    bat_status &= 0x9F;

    if(0 != is_5v_in())
    {
        bat_status |= bcharging;
        if (0 != is_chg_ok())
        {
            if ((rtc_cur_value - charg_ok_count) > mMS_TO_TICK(60000))
            {
                bat_status |= bcharge_ok;
            }
        }
        else
        {
            charg_ok_count = rtc_cur_value;
        }
    }
    else
    {
        charg_ok_count = rtc_cur_value;
    }

    
 
    if(mMS_TO_TICK(256) < (rtc_cur_value-bat_delay_count))
    {
        bat_delay_count = rtc_cur_value;
        bat_check();
    }

    if (bat_status & bcharging)
    {
        if (bat_status & bcharge_ok)
            led_low_off();
        else
            led_low_on();
        
    }
    else
    {
        if (blvd_hint_flag)
        {
            if ((rtc_cur_value - charge_hint_index) > mMS_TO_TICK(1000))
            {
                charge_hint_index = rtc_cur_value;

                if (blvd_hint_dir)
                    led_low_off();
                else
                    led_low_on();

                blvd_hint_dir = !blvd_hint_dir;
            }
            
        }
        else
        {
            led_low_off();
        }
        
    }
    
}


void charg_led_sleep_process()
{
    if (USB_5V_PIN)
    {
        while (1)
        {
            if (BAT_CHG_OK)
                break;
            else
                led_low_on();
            delayms(1);
            drv_wdt_keep_alive(OM_WDT);

            key_io_scan();
            if (key_status)
                NVIC_SystemReset();
            if (!USB_5V_PIN)
                break;;
        }
        
    }
    
}