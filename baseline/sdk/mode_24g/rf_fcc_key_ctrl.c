/**
 * @file rf_fcc_keyCtrl.c
 * @author cfn
 * @brief 
 * @version 0.1
 * @date 2026-01-13
 * 
 * @copyright Copyright (c) 2026 OM
 * 
 */

#include "main_24g.h"
#include "user_config.h"

/**
 * @brief Macro
 * 
 */
#define RX_DO_NOTHING       0

#define RF_CE_LOW()         (OM_RF->RFCE=0)
#define RF_CE_HIGH()        (OM_RF->RFCE=1)
#define RF_CE_PULSE()       (OM_RF->CE_PULSE = 1)

#define RF_TX_MODE()        (OM_RF->CONFIG = 0x8A)
#define RF_RX_MODE()        (OM_RF->CONFIG = 0x8B)

#define RF_CLR_STATUS()     (OM_RF->RF_STATUS = OM_RF->RF_STATUS & 0xF8)

#define CONST_WAVE_BIT      (1<<7)
#define RF_CARRIER_EN()     (OM_RF->RF_SETUP |= CONST_WAVE_BIT)
#define RF_CARRIER_DIS()    (OM_RF->RF_SETUP &= ~CONST_WAVE_BIT)

#define RF_RANDOM_TX_EN()   {OM_RF->AGC_CTRL |= (1<<23);OM_RF->CAL_CTL  |= (1<<14);}
#define RF_RANDOM_TX_DIS()  {OM_RF->AGC_CTRL &= ~(1<<23);OM_RF->CAL_CTL &= ~(1<<14);}

#define RF_FLUSH_FIFO()     \
do { \
    OM_RF->DMA_CMD = DMA_CMD_FLUSH_TX;  \
    OM_RF->DMA_CMD =  DMA_CMD_FLUSH_RX; \
} while (0)

#define RF_WAIT_FOR_IRQ()   \
do  { \
    for(uint8_t i=0; i<250; i++)    \
    {   \
        rf_irq_status = OM_RF->RF_STATUS;   \
        if(rf_irq_status&0x30)  \
        {   \
            RF_CLR_STATUS();  \
            break;  \
        }   \
        delayus(3); \
    }   \
} while (0)

 
#define WAIT_FOR_KEY_RELEASE()  \
while(1)    \
{   \
    FEED_DOG(); \
    key_io_scan();  \
    if(!key_status)     \
    {   \
        delayms(50);    \
        break;  \
    }   \
}   \

#define WAIT_FOR_KEY_PRESS()    \
while(1)\
{\
    FEED_DOG(); \
    key_io_scan();\
    if((key_status) & bkey_l)\
    {\
        delayms(50);\
        break;\
    }   \
}\


/**
 * @brief Extern Declaration
 * 
 */
extern void drv_wdt_keep_alive(OM_WDT_Type *om_wdt);
#define FEED_DOG()      drv_wdt_keep_alive(OM_WDT)
//#define FEED_DOG()        

/**
 * @brief Local Variable
 * 
 */
typedef enum{
    CarrierMode2402,
    CarrierMode2440,
    CarrierMode2480,
    ModulationMode2402,
    ModulationMode2440,
    ModulationMode2480,
    ReceiveMode2402,
    ReceiveMode2440,
    ReceiveMode2480,
    HoppingMode16Chn,
    HoppingMode40Chn,
}rf_test_mode_t;


/**
 * @brief Public Variable
 * 
 */


/**
 * @brief table
 * 
 */
const uint8_t tx_power_tbl[] = {
    DRV_RF_PA_PWR_N6dBm ,
    DRV_RF_PA_PWR_0dBm  ,
    DRV_RF_PA_PWR_4dBm  ,
    DRV_RF_PA_PWR_5dBm  ,
    DRV_RF_PA_PWR_8dBm  ,
};

const uint8_t freq_16_tbl[] ={
    (2402 - 2400),
    (2468 - 2400),
	(2432 - 2400),
	(2448 - 2400),
	(2464 - 2400),
	(2404 - 2400),
	(2450 - 2400),
	(2440 - 2400),
	(2428 - 2400),
	(2410 - 2400),
	(2476 - 2400),
	(2412 - 2400),
	(2454 - 2400),
	(2418 - 2400),
	(2470 - 2400),
	(2480 - 2400),
};


/**
 * @brief Local Funtion
 * 
 */

/**
 * @brief  switch next rf test mode
 */
static rf_test_mode_t switch_next_mode(rf_test_mode_t mode)
{
    switch(mode)
    {
        case CarrierMode2402:    mode = CarrierMode2440;    break;
        case CarrierMode2440:    mode = CarrierMode2480;    break;
        case CarrierMode2480:    mode = ModulationMode2402; break;
        case ModulationMode2402: mode = ModulationMode2440; break;
        case ModulationMode2440: mode = ModulationMode2480; break;
        case ModulationMode2480: mode = ReceiveMode2402;    break;
        case ReceiveMode2402:    mode = ReceiveMode2440;    break;
        case ReceiveMode2440:    mode = ReceiveMode2480;    break;
        case ReceiveMode2480:    mode = HoppingMode16Chn;   break;
        case HoppingMode16Chn:   mode = HoppingMode40Chn;   break;
        case HoppingMode40Chn:   
        default:                 mode = CarrierMode2402;    break;
    }
    return mode;
}

/**
 * @brief  judge whether enter fcc test mode or not
 * @note   
 * @retval yes or no.
 */
static bool is_enter_rf_test_mode()
{
    bool enter_state = 1;

    for(int count = 0;count < 200;count ++)
    {   
        FEED_DOG();
        key_io_scan();
        if(key_status != (bkey_l|bkey_m))
        {
            enter_state = 0;
            break;
        }
        delayms(5);
    }

    return enter_state;
}

/**
 * @brief  led indication for different situation.
 */
static void led_indication_for_enter()
{
    mode_led_all_on();
}

static void led_indication_for_1M_init()
{
    mode_led_all_off();
    led_r_on();
}

static void led_indication_for_2M_init()
{
    mode_led_all_off();
    led_g_on();
}

static void led_indication_for_switch_power()
{
    mode_led_all_off();
    delayms(100);
    mode_led_all_on();
}

static void led_indication_for_start_test()
{
    mode_led_all_off();
}

static void led_indication_for_carrier_2402()
{
    led_r_on();
}

static void led_indication_for_carrier_2440()
{
    led_g_on();
}

static void led_indication_for_carrier_2480()
{
    led_b_on();
}

static void led_indication_for_modulation_2402()
{
    led_r_on();
    led_g_on();
}

static void led_indication_for_modulation_2440()
{
    led_g_on();
    led_b_on();
}

static void led_indication_for_modulation_2480()
{
    led_r_on();
    led_b_on();
}

static void led_indication_for_receive_2402()
{
    led_r_on();
}

static void led_indication_for_receive_2440()
{
    led_g_on();
}

static void led_indication_for_receive_2480()
{
    led_b_on();
}

static void led_indication_for_hop_16_freq()
{
    mode_led_all_on();
}

static void led_indication_for_hop_40_freq()
{
    mode_led_all_off();
}


/**
 * @brief Public Funtion
 * 
 */
void rf_fcc_key_ctrl()
{
    if(!is_enter_rf_test_mode())
        return;

    rf_test_mode_t rf_mode = CarrierMode2402;
    uint8_t rf_channel = 2,is_40_channel = 0,hopping_channel_index = 0;
    uint8_t tx_power_index = 1,tx_power_level_max = sizeof(tx_power_tbl);

    OM_CRITICAL_BEGIN();

    led_indication_for_enter();
    WAIT_FOR_KEY_RELEASE();
    
    RF_CE_LOW();
    delayus(250);
    DRV_RCC_RESET(RCC_RST_RF_FSM);
    RF_FLUSH_FIFO();

    bool exit_flag = 0;
    while(!exit_flag)                    /* waiting for rf config and init */
    {
        FEED_DOG();
        key_io_scan();
        switch(key_status)
        {
            case bkey_l:
            {
                drv_rf24g_2M_init();
                led_indication_for_2M_init();
                exit_flag = 1;
                break;
            }
            case bkey_r:
            {
                drv_rf24g_1M_init();
                led_indication_for_1M_init();
                exit_flag = 1;
                break;
            }
            case bkey_m:
            {
                tx_power_index++;
                if(tx_power_index > tx_power_level_max)
                    tx_power_index = 0;
                led_indication_for_switch_power();
                WAIT_FOR_KEY_RELEASE();
                break;
            }
            default:
                break;
        }
    }

    WAIT_FOR_KEY_RELEASE();

    delayms(200);
    drv_rf_set_tx_power(tx_power_tbl[tx_power_index]);

    while(1)
    {
        is_40_channel = 1;
        led_indication_for_start_test();
        switch(rf_mode)
        {
            case CarrierMode2402:
            case CarrierMode2440:
            case CarrierMode2480:
            {
                switch(rf_mode)
                {
                    case CarrierMode2402:
                        rf_channel = 2;
                        led_indication_for_carrier_2402();
                        break;
                    case CarrierMode2440:
                        rf_channel = 40;
                        led_indication_for_carrier_2440();
                        break;
                    case CarrierMode2480:
                    default:
                        led_indication_for_carrier_2480();
                        rf_channel = 80;
                        break;
                }
                RF_TX_MODE();
                RF_CARRIER_EN();
                OM_RF->RF_CH = rf_channel;
                RF_CE_HIGH();
                WAIT_FOR_KEY_PRESS();
                WAIT_FOR_KEY_RELEASE();
                RF_CE_LOW();
                RF_CARRIER_DIS();

                break;
            }
            case ModulationMode2402:
            case ModulationMode2440:
            case ModulationMode2480:
            {
                switch(rf_mode)
                {
                    case ModulationMode2402:
                        rf_channel = 2;
                        led_indication_for_modulation_2402();
                        break;
                    case ModulationMode2440:
                        rf_channel = 40;
                        led_indication_for_modulation_2440();
                        break;
                    case ModulationMode2480:
                    default:
                        rf_channel = 80;
                        led_indication_for_modulation_2480();
                        break;
                }
                RF_TX_MODE();
                OM_RF->RF_CH = rf_channel;
                RF_RANDOM_TX_EN();
                RF_CE_HIGH();
                WAIT_FOR_KEY_PRESS();
                RF_CE_LOW();
                RF_RANDOM_TX_DIS();
                WAIT_FOR_KEY_RELEASE();
                break;
            }
            case ReceiveMode2402:
            case ReceiveMode2440:
            case ReceiveMode2480:
            {
                #if RX_DO_NOTHING
                RF_CE_LOW();
                #else
                switch(rf_mode)
                {
                    case ReceiveMode2402:
                        rf_channel = 2;
                        led_indication_for_receive_2402();
                        break;
                    case ReceiveMode2440:
                        rf_channel = 40;
                        led_indication_for_receive_2440();
                        break;
                    case ReceiveMode2480:
                    default:
                        rf_channel = 80;
                        led_indication_for_receive_2480();
                        break;
                }
                RF_RX_MODE();
                OM_RF->RF_CH = rf_channel;
                RF_CE_HIGH();
                #endif
                WAIT_FOR_KEY_PRESS();
                RF_CE_LOW();
                break;
            }
            case HoppingMode16Chn:
                is_40_channel = 0;
            case HoppingMode40Chn:
            {
                if(is_40_channel)
                    led_indication_for_hop_40_freq();
                else
                    led_indication_for_hop_16_freq();

                RF_TX_MODE();
                while(1)
                {   
                    FEED_DOG();
                    delayms(2);
                    key_io_scan();
                    if(key_status&bkey_l)   break;
                    
                    RF_FLUSH_FIFO();
                    RF_CLR_STATUS();

                    hopping_channel_index ++;
                    if(!is_40_channel)
                    {
                        if(hopping_channel_index >= 16)
                            hopping_channel_index = 0;
                        OM_RF->RF_CH = freq_16_tbl[hopping_channel_index&0x0F];
                    }
                    else
                    {
                        if(hopping_channel_index >= 40)
                            hopping_channel_index = 0;
                        OM_RF->RF_CH = ((hopping_channel_index<<1)+2);	
                    }
                    drv_rf_write_tx_payload_noack(rf_data_fifo, 16);
                    RF_CE_PULSE();
                    RF_WAIT_FOR_IRQ();
                }
                break;
            }
        }
        WAIT_FOR_KEY_RELEASE();
        rf_mode = switch_next_mode(rf_mode);
    }
    OM_CRITICAL_END();
}


/* end */
