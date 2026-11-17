/**
 * @file user_config.c
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2025-05-22
 * 
 * @copyright Copyright (c) 2025
 * 
 */
#include "user_config.h"

//-----------------------------------------------------------------------------;
// 变量定义区
//
typedef enum {
    USER_GPIO_MODE_INPUT_FLOATING = 0x00,  // 浮空输入
    USER_GPIO_MODE_INPUT_PULLUP,           // 上拉输入
    USER_GPIO_MODE_INPUT_PULLDOWN,         // 下拉输入
    USER_GPIO_MODE_OUTPUT_PP,              // 推挽输出
} user_gpio_mode_t;

typedef struct {
    uint32_t pin;           // PIN脚编号
    user_gpio_mode_t mode;  // 输入/输出模式
    uint8_t pull;           // 上拉/下拉/浮空（仅输入模式有效
    uint8_t init_level;     // 初始电平（仅输出模式有效）
} user_gpio_config_t;

//-----------------------------------------------------------------------------;
// 表格定义区
//
/* OMCFG BEGIN gpio_table */
const user_gpio_config_t gpio_config_table[] = {
    // PIN脚             模式                            上拉/下拉      初始电平
    {KEY_R0_PIN,         USER_GPIO_MODE_INPUT_PULLUP,    PU_30K,       PIN_HIGH_LEV},      /* 按键配置 */
    {KEY_R1_PIN,         USER_GPIO_MODE_INPUT_PULLUP,    PU_30K,       PIN_HIGH_LEV},    
    {KEY_R2_PIN,         USER_GPIO_MODE_INPUT_PULLUP,    PU_30K,       PIN_HIGH_LEV}, 
    {KEY_PAIR_PIN,       USER_GPIO_MODE_INPUT_PULLUP,    PU_30K,       PIN_HIGH_LEV}, 
    {KEY_C0_PIN,         USER_GPIO_MODE_OUTPUT_PP,       PU_30K,       PIN_HIGH_LEV},

    {WHEEL_A_PIN,        USER_GPIO_MODE_INPUT_PULLUP,    PU_30K,       PIN_HIGH_LEV},      /* 滚轮配置 */
    {WHEEL_B_PIN,        USER_GPIO_MODE_INPUT_PULLUP,    PU_30K,       PIN_HIGH_LEV}, 

    {SENSOR_MOTION_PIN,  USER_GPIO_MODE_INPUT_PULLUP,    PU_30K,       PIN_HIGH_LEV}, 
    {SENSOR_SCLK_PIN,    USER_GPIO_MODE_OUTPUT_PP,       PU_30K,       PIN_HIGH_LEV}, 
    {SENSOR_SDIO_PIN,    USER_GPIO_MODE_INPUT_PULLUP,    PU_30K,       PIN_HIGH_LEV}, 

    {MODE_24G_PIN,       USER_GPIO_MODE_INPUT_PULLDOWN,  PD_150K,      PIN_HIGH_LEV},
    {MODE_BLE_PIN,       USER_GPIO_MODE_INPUT_PULLDOWN,  PD_150K,      PIN_HIGH_LEV},

    {LED_MODE_R_PIN,     USER_GPIO_MODE_OUTPUT_PP,       PU_30K,       PIN_LOW_LEV}, 
    {LED_MODE_G_PIN,     USER_GPIO_MODE_OUTPUT_PP,       PU_30K,       PIN_LOW_LEV}, 
    {LED_MODE_B_PIN,     USER_GPIO_MODE_OUTPUT_PP,       PU_30K,       PIN_LOW_LEV}, 
    {LED_LOW_PIN,        USER_GPIO_MODE_OUTPUT_PP,       PU_30K,       PIN_LOW_LEV}, 
    {LEDC_CTRL_PIN,      USER_GPIO_MODE_OUTPUT_PP,       PU_30K,       PIN_HIGH_LEV},
    {LEDC_PIN,           USER_GPIO_MODE_OUTPUT_PP,       PU_30K,       PIN_HIGH_LEV},

    {USB_5V,             USER_GPIO_MODE_INPUT_PULLDOWN,  PD_150K,      PIN_HIGH_LEV}, 
    {BAT_CHG_PIN,        USER_GPIO_MODE_INPUT_PULLUP,    PU_30K,       PIN_HIGH_LEV}, 

    {LVD_PIN,            USER_GPIO_MODE_INPUT_FLOATING,  PU_NONE,      PIN_HIGH_LEV},

    {FLASH_CS_PIN,       USER_GPIO_MODE_INPUT_PULLUP,    PU_30K,       PIN_HIGH_LEV},       /* FLASH SPI IO CONFIG ，don't change */
    {FLASH_SCLK_PIN,     USER_GPIO_MODE_INPUT_PULLUP,    PU_30K,       PIN_HIGH_LEV},
    {FLASH_MOSI_PIN,     USER_GPIO_MODE_INPUT_PULLUP,    PU_30K,       PIN_HIGH_LEV},
    {FLASH_MISO_PIN,     USER_GPIO_MODE_INPUT_PULLUP,    PU_30K,       PIN_HIGH_LEV},
};
/* OMCFG END gpio_table */


//=============================================================================;
// 代码区                                                                      ;
//=============================================================================;

/**
 * @brief IO口上拉配置函数
 * 
 * @param pin P00~P37
 * @param mode PU_30K/PU_150K
 */
void gpio_set_pu(uint8_t pin,uint8_t mode)   
{   
    OM_PMU->PAD_PD_CTRL &= ~(1u << pin);

    if(pin < P20)
    {
        OM_PMU->PAD_PU_CTRL &= ~(3u << (pin*2));
        OM_PMU->PAD_PU_CTRL |= (mode << (pin*2));
    }
    else
    {
        pin -= P20;
        OM_PMU->PAD_PU_CTRL_1 &= ~(3u << (pin*2));
        OM_PMU->PAD_PU_CTRL_1 |= (mode << (pin*2));
    }
}

/**
 * @brief IO口下拉配置函数
 * 
 * @param pin P00~P37
 * @note 下拉固定为150K，没得配置
 */
void gpio_set_pd(uint8_t pin)   
{   
    OM_PMU->PAD_PD_CTRL |= (1u << pin);

    if(pin < P20)
    {
        OM_PMU->PAD_PU_CTRL &= ~(3u << (pin*2));
    }
    else
    {
        pin -= P20;
        OM_PMU->PAD_PU_CTRL_1 &= ~(3u << (pin*2));
    }
}

/**
 * @brief IO口浮空配置函数
 * 
 * @param pin 
 */
void gpio_set_float(uint8_t pin)
{
    OM_PMU->PAD_PD_CTRL &= ~(1u << pin);

    if(pin < P20) 
    {
        OM_PMU->PAD_PU_CTRL &= ~(3u << (pin*2));
    } 
    else 
    {
        OM_PMU->PAD_PU_CTRL_1 &= ~(3u << ((pin-P20)*2));
    }
}

/**
 * @brief 设置输入BUFFER
 * 
 */
void gpio_set_pad_buffer(uint8_t pin ,bool en)
{
	if(en) 
        OM_PMU->PAD_BUF_EN |= (1 << pin);   
    else 
        OM_PMU->PAD_BUF_EN &= ~(1 << pin);  
}


/**
 * @brief 外设GPIO初始化
 * 
 * @note 根据自己喜欢的方式去配置GPIO初始化
 */
void periph_gpio_init()
{
    OM_RCC->CLKGATE |= RCC_DEV_CLK_GATE_GPIO_CLK_GATE_MASK;

    #if 0                               /* 直接写寄存器 */
    OM_PMU->PAD_PU_CTRL = 0x00A28000;       
    OM_PMU->PAD_PU_CTRL_1 = 0x0208A82A;
    OM_PMU->PAD_PD_CTRL = 0x00100000;

    OM_GPIO0->DATAOUT |= 0xFFFFFFFF;
    OM_GPIO0->OUTENSET = 0x05000273;            
    OM_GPIO0->OUTENCLR = ~0x05000273;

    #else                               /* 填表初始化 */

    OM_PMU->PAD_PU_CTRL = 0xFFFFFFFF;
    OM_PMU->PAD_PU_CTRL_1 = 0xFFFFFFFF;
    OM_PMU->PAD_PD_CTRL = 0;

    OM_GPIO0->DATAOUT = 0xFFFFFFFF;
    OM_GPIO0->OUTENSET = 0;            
    OM_GPIO0->OUTENCLR = 0xFFFFFFFF;

    const uint32_t table_size = sizeof(gpio_config_table)/sizeof(user_gpio_config_t);
    for(uint32_t i=0; i<table_size; i++)
    {
        const user_gpio_config_t *cfg = &gpio_config_table[i];

        uint8_t pin = cfg->pin;

        /* 模式配置 */
        switch(cfg->mode)
        {
            case USER_GPIO_MODE_INPUT_FLOATING:
                gpio_set_float(pin);
                gpio_dir_in(pin);
                break;
            case USER_GPIO_MODE_INPUT_PULLUP:
                gpio_set_pu(pin, cfg->pull);
                gpio_dir_in(pin);
                break;
            case USER_GPIO_MODE_INPUT_PULLDOWN:
                gpio_set_pd(pin);
                gpio_dir_in(pin);
                break;
            case USER_GPIO_MODE_OUTPUT_PP:
                gpio_set_float(pin);
                if(cfg->init_level) 
					gpio_set(pin);
				else 
					gpio_clear(pin);

                gpio_dir_out(pin);
                break;
        }
    }
    
    #endif

    gpio_set_pad_buffer(LVD_PIN,PAD_IN_BUFFER_EN);
}

/* OMCFG BEGIN sleep */
/**
 * @brief 外设IO口配置，休眠前调用，避免漏电
 * 
 */
void periph_gpio_sleep_set()
{
    gpio_set_pad_buffer(LVD_PIN,PAD_IN_BUFFER_OFF);     /* 关掉LVD的输入BUFFER，避免漏电 */

    gpio_set_pd(WHEEL_A_PIN);
    gpio_set_pd(WHEEL_B_PIN);

    gpio_dir_in(LEDC_PIN);
    gpio_set_pd(LEDC_PIN);
    led_low_off();

    if (gpio_read(MODE_24G_PIN))
        gpio_set_pu(MODE_24G_PIN,PU_30K);
    else
        gpio_set_pd(MODE_24G_PIN);
    if (gpio_read(MODE_BLE_PIN))
        gpio_set_pu(MODE_BLE_PIN,PU_30K);
    else
        gpio_set_pd(MODE_BLE_PIN);
    
    
    OM_RCC->CLKGATE = 0x0742;
}
/* OMCFG END sleep */

/**
 * @brief 串口调试函数，用于平时的串口打印
 * 
 * @param data 
 * @note 波特率：2127659
 * @return NONE
 */
__RAM_CODE void uart_tx(uint8_t data)
{	
	#if 0
    volatile uint8_t i;
    
    gpio_dir_out(UART_PIN);
OM_CRITICAL_BEGIN();

    OM_GPIO0->DATAOUT |= (1<<UART_PIN);
    __NOP();__NOP();
    OM_GPIO0->DATAOUT &= ~(1<<UART_PIN);
    if(data&(1<<0))
        OM_GPIO0->DATAOUT |= (1<<UART_PIN);
    else
        OM_GPIO0->DATAOUT &= ~(1<<UART_PIN);

    if(data&(1<<1))
        OM_GPIO0->DATAOUT |= (1<<UART_PIN);
    else
        OM_GPIO0->DATAOUT &= ~(1<<UART_PIN);

    if(data&(1<<2))
        OM_GPIO0->DATAOUT |= (1<<UART_PIN);
    else
        OM_GPIO0->DATAOUT &= ~(1<<UART_PIN);

    if(data&(1<<3))
        OM_GPIO0->DATAOUT |= (1<<UART_PIN);
    else
        OM_GPIO0->DATAOUT &= ~(1<<UART_PIN);

    if(data&(1<<4))
        OM_GPIO0->DATAOUT |= (1<<UART_PIN);
    else
        OM_GPIO0->DATAOUT &= ~(1<<UART_PIN);

    if(data&(1<<5))
        OM_GPIO0->DATAOUT |= (1<<UART_PIN);
    else
        OM_GPIO0->DATAOUT &= ~(1<<UART_PIN);

    if(data&(1<<6))
        OM_GPIO0->DATAOUT |= (1<<UART_PIN);
    else
        OM_GPIO0->DATAOUT &= ~(1<<UART_PIN);

    if(data&(1<<7))
        OM_GPIO0->DATAOUT |= (1<<UART_PIN);
    else
        OM_GPIO0->DATAOUT &= ~(1<<UART_PIN);
    __NOP();__NOP();__NOP();__NOP();__NOP();__NOP();__NOP();
    OM_GPIO0->DATAOUTSET = (1<<UART_PIN);
OM_CRITICAL_END();

	#endif
}


/* USER CODE BEGIN user_config_c */
/* USER CODE END user_config_c */
