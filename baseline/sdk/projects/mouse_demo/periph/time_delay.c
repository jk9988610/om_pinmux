/**
 * @file time_delay.c
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

//=============================================================================;
// 代码区                                                                      ;
//=============================================================================;

/**
 * @brief US延时函数
 * 
 * @param time us
 */
__RAM_CODE void delayus(volatile uint32_t time)
{
    time<<=1;
    do
    {
        __NOP();
        time--;
    }
    while(time);
}

