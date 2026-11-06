/*******************************************************************************
* Copyright (c) 2009, SHENZHEN Co.,LTD.
* All rights reserved.
*
* 文件名称: rf_connect_check.c
* 文件描述: RF对码检测
*******************************************************************************/
#include "main_24g.h"
#include "hid_process.h"
#include "usb_cfg_info.h"

//----------------------------------------------------------------------------;
//变量定义
//
extern uint8_t                  rf_rsp_freq[16];

#define fcc_temp                rf_rsp_freq[8]
#define test_freq               rf_rsp_freq[9]
#define test_power              rf_rsp_freq[10]
#define tx_time                 rf_rsp_freq[11]
#define idle_time               rf_rsp_freq[12]

extern void wait_irq(void);

//----------------------------------------------------------------------------;
// 表格定义区
//
unsigned char           const    fcc_hop_freq_tbl[] ={
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

/******************************************************************************
* 函数名称: hid_cmd_fcc_test
* 功能描述:
* 输入参数:
* 输出参数:
* 说    明:
******************************************************************************/
void hid_cmd_fcc_test(void)
{
    uint8_t i;
    uint32_t rtc_temp;

    mRF_CE_LOW_IDLE;
    delayus(250);
    DRV_RCC_RESET(RCC_RST_RF_FSM);
    mFLUSH_FIFO;

    drv_rf24g_init();

    test_freq = out_report_data[3];
    test_power = (out_report_data[4] & 0x1F);
    tx_time = out_report_data[5];
    idle_time = out_report_data[6];

    drv_rf_set_tx_power(test_power);

    switch(out_report_data[2])
    {
        case iHID_CMD_FCC_FREQ:                 // 跳频测试
            OM_RF->CONFIG = 0x8A;

            while(1)
            {
                rtc_temp = drv_rtc_read(OM_RTC);
                while(1)
                {   
                    drv_wdt_keep_alive(OM_WDT);
                    if(hid_ctrl_reg & bhid_data_process)
                        return;
                    if(mMS_TO_TICK(2) < drv_rtc_read(OM_RTC)-rtc_temp)
                        break;
                }

                mFLUSH_FIFO;
                mRF_CLR_STATUS;

                freq_index++;
                if(test_freq < 40)
                {
                    if(freq_index>=16)
                        freq_index = 0;
                        
                    OM_RF->RF_CH = fcc_hop_freq_tbl[freq_index&0x0F];	
                }
                else
                {
                    if(freq_index>=40)
                        freq_index = 0;
                    OM_RF->RF_CH = ((freq_index<<1)+2);	
                }

                if(0 == tx_time)
                    tx_time = 1;

                drv_rf_write_tx_payload_noack(rf_data_fifo, tx_time&0x1F);
                OM_RF->CE_PULSE = 1;
                wait_irq();
            }

            break;
        case iHID_CMD_FCC_TX:
            OM_RF->CONFIG = 0x8A;
            OM_RF->RF_CH = test_freq;

            /* random tx */
            OM_RF->AGC_CTRL |= (1<<23);
            OM_RF->CAL_CTL  |= (1<<14);

            mRF_CE_HIGH_TX;
            while(1)
            {
                drv_wdt_keep_alive(OM_WDT);
                OM_RF->AGC_CTRL |= (1<<23) ;
                if((0 == tx_time) ||(0 == idle_time))
                {
                    while(1)
                    {   
                        drv_wdt_keep_alive(OM_WDT);
                        if(0!=(hid_ctrl_reg & bhid_data_process))
                            break;
                    }
                    goto fcc_hspf_test_out;
                }
    
                for(fcc_temp=0; fcc_temp<=tx_time; fcc_temp++)
                {
                    if(0!=(hid_ctrl_reg & bhid_data_process))
                        goto fcc_hspf_test_out;

                    delayus(95);
                }
    
                OM_RF->AGC_CTRL &= ~(1<<23) ;
                for(fcc_temp=1; fcc_temp<=idle_time; fcc_temp++)
                {
                    if(0!=(hid_ctrl_reg & bhid_data_process))
                        goto fcc_hspf_test_out;
                    delayus(95);
                }
            }
fcc_hspf_test_out:
            mRF_CE_LOW_TX;

            OM_RF->AGC_CTRL &= ~(1<<23);
            OM_RF->CAL_CTL &= ~(1<<14);

            break;
        case iHID_CMD_FCC_RX:
            OM_RF->CONFIG = 0x8B;
            OM_RF->RF_CH = test_freq;

            mRF_CE_HIGH_RX;
            while(1)
            {
                drv_wdt_keep_alive(OM_WDT);
                if(0!=(hid_ctrl_reg & bhid_data_process))
                    break;
            }
            mRF_CE_LOW_RX

            break;
        case iHID_CMD_FCC_CONT_WAVE:
            OM_RF->CONFIG = 0x8A;
            OM_RF->RF_SETUP |= 0x80;
            OM_RF->RF_CH = test_freq;

            mRF_CE_HIGH_RX;
            while(1)
            {
                drv_wdt_keep_alive(OM_WDT);
                if(0!=(hid_ctrl_reg & bhid_data_process))
                    break;
            }
            mRF_CE_LOW_RX

            break;
    }
}



