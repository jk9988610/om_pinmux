/**
 * @file sensor_type_check.c
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2025-05-22
 * 
 * @copyright Copyright (c) 2025
 * 
 */

#include <stdio.h>
#include "om_driver.h"

#include "main.h"
#include "sensor_type_check.h"
#include "sensor.h"
#include "time_delay.h"

//-----------------------------------------------------------------------------;
// 常量定义区
//

//-----------------------------------------------------------------------------;
// 变量定义区
//

//-----------------------------------------------------------------------------;
// 宏定义区
//

//----------------------------------------------------------------------------;
// SENSOR寄存器初始化表格定义区
//

uint8_t           const     ka8g2_ini[] =
{
    8*2+1,
    0x06,0x97,
    0x09,0xA5,
    0x46,0x34,
    0x60,0x07,
    0x69,0x04,
    0x7D,0x20,
    0x7E,0x00,
    0x19,0x04,
};

uint8_t         const       paw3065_ini[] =
{
    3*2+1,
    0x09,0x5A,
    0x0B,0xE0,
    0x09,0x00,
};

uint8_t         const       mx8650a_ini[] =
{
    5*2+1,
    0xFF,0x27,
    0xB5,0xD0,
    0xB6,0x40,
    0xFF,0x00,
    0x09,0x00,
};

uint8_t         const       s201b_ini[] =
{
    3*2+1,
    0x09,0xC3,
    0x22,0x01,
    0x09,0x00,
};
uint8_t         const       pan3212_ini[] =
{
    3*2+1,
    0x09,0x5A,
    0x26,0x34,
    0x19,0x04,
};

uint8_t         const       s203_game_ini[] =
{
    7*2+1,
    0x09,0xC3,
    0x55,0x94,
    0x5D,0x00,
    0x65,0x05,
    0x66,0x05,
    0x76,0xBD,
    0x09,0x00,
};

uint8_t         const       s205_work_ini[] =
{
    24*2+1,
    0x09,0xC3,
    0x64,0x80,
    0x65,0x03,
    0x66,0x83,
    0x50,0xe9,
    0x54,0x04,
    0x73,0x53,
    0x75,0x08,

    0x0a,0x73,
    0x1a,0x30,
    0x0b,0x30,
    0x6d,0xD0,
    0x6e,0xF0,
    0x7c,0x70,
    0x7b,0x10,
    0x24,0x4f,

    0x25,0x24,
    0x2f,0x01,
    0x74,0x20,
    0x77,0x30,
    0x2f,0x00,
    0x44,0x09,
    0x43,0xc4,
    0x09,0x00,    
};

uint8_t         const       s205_game_ini[] =
{
    24*2+1,
    0x09,0xC3,
    0x64,0x80,
    0x65,0x03,
    0x66,0x83,
    0x50,0xe9,
    0x54,0x04,
    0x73,0xd3,
    0x75,0x48,

    0x0a,0x17,
    0x1a,0x30,
    0x0b,0x00,
    0x6d,0xD0,
    0x6e,0xF0,
    0x7c,0x70,
    0x7b,0x10,
    0x24,0x4f,

    0x25,0x24,
    0x2f,0x01,
    0x74,0x20,
    0x77,0x30,
    0x2f,0x00,
    0x44,0x09,
    0x43,0xc4,
    0x09,0x00,  
};

/* SENSOR寄存器配置初始化表 */
uint8_t const  user_sensor_init_tbl[] =
{
    0x00,           // SENSCAN_IDADDR
    0x30,           // SENSCAN_ID
    0x02,           // SENSCAN_MOADDR
    0x03,           // SENSCAN_XADDR
    0x04,           // SENSCAN_YADDR
    0x12,           // SENSCAN_HADDR1
    0xFF,           // SENSCAN_HADDR2
};


//=============================================================================;
// 代码区                                                                      ;
//=============================================================================;

/**
 * @brief SENSOR 上电写复位寄存器
 * 
 */
void pan_poweron_wakeup(void)
{
    DRV_RCC_CLOCK_ENABLE(RCC_CLK_SENSCAN, 0U);
    sensor_write(0x06, 0x84);
    delayus(35000);
    DRV_RCC_CLOCK_ENABLE(RCC_CLK_SENSCAN, 1U);
}

/**
 * @brief SENSOR 设置硬件扫描的高位地址以及SENSOR数据长度
 * 
 */
void sensor_dat_format(void)
{
    if(0 != (sensor_status_reg&bsensor_12bit))
    {                                           // 12bit
        OM_SENSCAN->HADDR1 = iXY_12BIT_ADDR;

        OM_SENSCAN->CSR &= ~SENSACN_CSR_DATA_FORMAT_MASK;
        OM_SENSCAN->CSR |= SENSACN_CSR_DATA_FORMAT_12BIT;
    }
    else if(0 != (sensor_status_reg&bsensor_s201x))
    {                                           // 16bit
        OM_SENSCAN->HADDR1 = iX_16BIT_ADDR;
        OM_SENSCAN->HADDR2 = iY_16BIT_ADDR;

        OM_SENSCAN->CSR &= ~SENSACN_CSR_DATA_FORMAT_MASK;
        OM_SENSCAN->CSR |= SENSACN_CSR_DATA_FORMAT_16BIT;
    }
}

/**
 * @brief SENSOR检查类型，并进行对应的初始化寄存器配置
 * 
 */
void sensor_type_check(void)
{
    unsigned char i,j;
    unsigned char addr, dat;
    unsigned char const *prt=NULL;

// sensor的类型检测最多3次
    sensor_status_reg = 0;

    for(i=0; i<3; i++)
    {
        j = sensor_read(0x00);
        if(iPID_VALUE_KA5857_KA8G2 == j)
        {
            sensor_status_reg |= bsensor_12bit;
            sensor_type = iSENSOR_TYPE_KA8G2;
            prt = ka8g2_ini;
            break;
        }
        else if(iPID_VALUE_PAN3065 == j)
        {
            j = sensor_read(0x01);
            pan_poweron_wakeup();
            if(iPID_VALUE_PAN3205_TJNT == j)
            {
                sensor_type = iSENSOR_TYPE_3205_TJNT;
            }
            else
            {
                sensor_type = iSENSOR_TYPE_3065_D;
                prt = paw3065_ini;
            }
            break;
        }
        if(0x30 != (j & 0xFC))
        {
            sensor_comm_resume();
        }

        j = sensor_read(iPID_ADDR_PAN);
        if(0xFF != j)
        {
            if(iPID_VALUE_KA8 == (j & 0xf0))
            {
                pan_poweron_wakeup();
                if(iPID_VALUE_MX8650A == j)
                {
                    sensor_type = iSENSOR_TYPE_MX8650A;
                    prt = mx8650a_ini;
                }
                else
                {
                    sensor_type = iSENSOR_TYPE_KA8;
                }
                break;
            }
            else if(iPID_VALUE_PAN3205_S201 == (j & 0xf0))
            {
                pan_poweron_wakeup();

                sensor_status_reg |= bsensor_s201x;
                sensor_type = iSENSOR_TYPE_S201B;

                prt = s201b_ini;
                break;
            }
            else if(iPID_VALUE_PAN3212_3220_SG8912 == j)
            {
                sensor_status_reg |= bsensor_12bit;

                j = sensor_read(0x49);
                if(iPID_VALUE_S203 == j)
                {
                    sensor_type = iSENSOR_TYPE_S203;
                    if(iDEVICE_TYPE_USB == device_type)
                        prt = s203_game_ini;
                }
                else if(iPID_VALUE_S205 == j)
                {
                    sensor_type = iSENSOR_TYPE_S205;
                    if(iDEVICE_TYPE_USB == device_type)
                        prt = s205_game_ini;
                    else
                        prt = s205_work_ini;
                }
                else
                {
                    sensor_type = iSENSOR_TYPE_3212;
                    prt = pan3212_ini;
                }
                pan_poweron_wakeup();

                break;
            }
        }
    }

    if(NULL != prt)
    {
        for(i=1; i<prt[0];)
        {
            addr = prt[i++];
            dat = prt[i++];
            sensor_write(addr, dat);
        }
    }

    if((iSENSOR_TYPE_S203 == sensor_type)
        || (iSENSOR_TYPE_S205 == sensor_type))
    {
        sensor_write(0x09, 0xC3);
        sensor_write(0x19, (sensor_read(0x19)|0x04));
        sensor_write(0x09, 0x00);
    }

    sensor_dat_format();

// 设备识别成功
    sensor_set_dpi();

}
