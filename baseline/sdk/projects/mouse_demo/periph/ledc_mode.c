#include "ledc_mode.h"
#include "led.h"

#define LEDC_RGB_1      0
#define LEDC_RGB_2      1
#define LEDC_RGB_3      2
#define LEDC_RGB_4      3

uint8_t mode_stay_time;
#define MODE_BREAT_TIME     2
#define MODE_NOEN_TIME      2
#define MODE_COLORFUL_TIME  2
#define MODE_WT_TIME        1

uint8_t qcnh_tab[3] = {0};
uint8_t qcnh_gruop[][3] = {
        0,1,2,
        0,2,1,
        1,0,2,
        1,2,0,
        2,0,1,
        2,1,0,
};

uint8_t const ledc_color_tab [] =
{
    LEDC_RED,
    LEDC_GREEN,
    LEDC_BULE,
    LEDC_RED | LEDC_BULE,
    LEDC_RED | LEDC_GREEN,
    LEDC_GREEN | LEDC_BULE,
    LEDC_RED | LEDC_GREEN | LEDC_BULE,
};

uint8_t ledc_data_tab[LEDC_RGB_DATA_SIZE] = {0};

bool bledc_status;
uint8_t rgb_index;
uint8_t ledc_color;
uint8_t ledc_data_value;
uint8_t ledc_data_value_1;
uint8_t ledc_data_value_2;

uint8_t ledc_rgb_index;
static uint8_t  wave_count = 0;

__RAM_CODE void ledc_single_ctrl(uint8_t rgb_enbled, uint8_t color_enble, uint8_t red_data, uint8_t green_data, uint8_t blue_data)
{
    if ((red_data != 0) && (color_enble & LEDC_RED))
    {
        ledc_data_tab[rgb_enbled*3+1]    =  red_data;
    }
    else
    {
        ledc_data_tab[rgb_enbled*3+1]    =  0; 
    }

    if ((green_data != 0) && (color_enble & LEDC_GREEN))
    {
        ledc_data_tab[rgb_enbled*3]    =  green_data;
    }
    else
    {
        ledc_data_tab[rgb_enbled*3]   =  0;   
    }

    if ((blue_data != 0) && (color_enble & LEDC_BULE))
    {
        ledc_data_tab[rgb_enbled*3+2]    =  blue_data;
    }
    else
    {
        ledc_data_tab[rgb_enbled*3+2]    =  0; 
    }
}

/*************常亮***************** */
void    ledc_bright_init(void)
{
    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        ledc_single_ctrl(i, ledc_color_tab[6], LEDC_DATA_MAX, 0, 0);
    }
    
    ledc_color = 0;
}

void    ledc_mode_bright(void)
{
    static uint16_t switch_count = 0;
    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        ledc_single_ctrl(i, ledc_color_tab[ledc_color], LEDC_DATA_MAX, LEDC_DATA_MAX, LEDC_DATA_MAX);
    }

    switch_count++;
    if (switch_count > 250)
    {
        switch_count = 0;
        ledc_color++;
        if (ledc_color >= 7)
            ledc_color = 0;  
    }
    
}


/***********呼吸灯************** */
void    ledc_breath_init(void)
{
    memset(ledc_data_tab,0,sizeof(ledc_data_tab));
    bledc_status = 1;
    ledc_data_value = 0;
    ledc_color = 0;
}

void    ledc_mode_breath(void)
{
    mode_stay_time++;
    if (mode_stay_time > MODE_BREAT_TIME)
    {
        mode_stay_time = 0;
        if (!bledc_status)
        {
            ledc_data_value--;
            if (ledc_data_value == 0)
            {
                bledc_status = true;
                ledc_color++;
                if (ledc_color >= 7)
                    ledc_color = 0;
            }
        }
        else
        {
            ledc_data_value++;
            
            if (ledc_data_value >= LEDC_DATA_MAX)
            {
                bledc_status = false;
            }
            
        }
    }
    
    
    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        ledc_single_ctrl(i, ledc_color_tab[ledc_color], ledc_data_value, ledc_data_value, ledc_data_value);
    }
}

/**************霓虹灯*************** */
void    ledc_noen_init(void)
{
    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        ledc_single_ctrl(i, ledc_color_tab[6], LEDC_DATA_MAX, 0, 0);
    }
}

void    ledc_mode_noen(void)
{
    static uint8_t    none_dir = 0, none_count = 0;
    none_count++;
    if (none_count > 3)
    {
        none_count = 0;
        if (none_dir == 0)
        {
            qcnh_tab[0]--;
            qcnh_tab[1]++;
            qcnh_tab[2] = 0;
            if (qcnh_tab[0] == 0)
            {
                qcnh_tab[1] = LEDC_DATA_MAX;
                none_dir++;
            }
        }
        else if (none_dir == 1)
        {
            qcnh_tab[0]= 0;
            qcnh_tab[1]--;
            qcnh_tab[2]++;
            if (qcnh_tab[1] == 0)
            {
                qcnh_tab[2] = LEDC_DATA_MAX;
                none_dir++;
            }
        }
        else if (none_dir == 2)
        {
            qcnh_tab[0] ++;
            qcnh_tab[1] = 0;
            qcnh_tab[2] --;
            if (qcnh_tab[2] == 0)
            {
                qcnh_tab[0] = LEDC_DATA_MAX;
                none_dir = 0;
            }
        }
    }
    

    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        ledc_single_ctrl(i, ledc_color_tab[6], qcnh_tab[0], qcnh_tab[1], qcnh_tab[2]);
    }
}

/**************七彩霓虹*************** */
void    ledc_colorful_init(void)
{
    ledc_noen_init();
}

void    ledc_mode_colorful(void)
{
    static uint8_t    none_dir = 0;
    mode_stay_time++;
    if (mode_stay_time > MODE_COLORFUL_TIME)
    {
        mode_stay_time = 0;
        if (none_dir == 0)
        {
            qcnh_tab[0]--;
            qcnh_tab[1]++;
            qcnh_tab[2] = 0;
            if (qcnh_tab[0] == 0)
            {
                qcnh_tab[1] = LEDC_DATA_MAX;
                none_dir++;
            }
        }
        else if (none_dir == 1)
        {
            qcnh_tab[0]= 0;
            qcnh_tab[1]--;
            qcnh_tab[2]++;
            if (qcnh_tab[1] == 0)
            {
                qcnh_tab[2] = LEDC_DATA_MAX;
                none_dir++;
            }
        }
        else if (none_dir == 2)
        {
            qcnh_tab[0] ++;
            qcnh_tab[1] = 0;
            qcnh_tab[2] --;
            if (qcnh_tab[2] == 0)
            {
                qcnh_tab[0] = LEDC_DATA_MAX;
                none_dir = 0;
            }
        }
    }
    
    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        ledc_single_ctrl(i, 7, qcnh_tab[qcnh_gruop[i][0]], qcnh_tab[qcnh_gruop[i][1]], qcnh_tab[qcnh_gruop[i][2]]);
    }
}

/***************波浪*************** */
void    ledc_wave_init(void)
{
    ledc_noen_init();

    bledc_status = 0;
    ledc_data_value_1 = LEDC_DATA_MAX;
    ledc_data_value_2 = 0;
    ledc_color = 0;
    wave_count = 0;
}

void    ledc_mode_wave(void)
{
    if (!bledc_status)
    {
        ledc_data_value_1--;
        ledc_data_value_2++;
        if (ledc_data_value_1 <= 0)
        {
            bledc_status = true;
        }
    }
    else
    {
        ledc_data_value_1++;
        ledc_data_value_2--;
        if (ledc_data_value_2 <= 0)
        {
            bledc_status = false;
            wave_count++;
        }
        
    }

    if (wave_count >= 4)
    {
        wave_count = 0;
    
        ledc_color++;
        if (ledc_color >= 7)
            ledc_color = 0;
    }

    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        if (i%2)
            ledc_single_ctrl(i, ledc_color_tab[ledc_color], ledc_data_value_1, ledc_data_value_1, ledc_data_value_1);
        else
            ledc_single_ctrl(i, ledc_color_tab[ledc_color], ledc_data_value_2, ledc_data_value_2, ledc_data_value_2);
    }
}

/***********七彩常亮*********** */
void    ledc_bright_colorful_init(void)
{
    // for (uint8_t i = 0; i < LEDC_RGB_NUMBER; i++)
    // {
    //     ledc_single_ctrl(i, ledc_color_tab[7%i], LEDC_DATA_MAX, LEDC_DATA_MAX, LEDC_DATA_MAX);
    // }
}

void    ledc_mode_bright_colorful(void)
{
    static uint8_t  rand_count = 0, switch_count = 250;
    
    switch_count++;
    if (switch_count > 250)
    {
        switch_count = 0;
        for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
        {
            rand_count+=3;
            if (rand_count > 255)
            {
                rand_count = 0;
            }
            ledc_single_ctrl(i, ledc_color_tab[rand_count%7], LEDC_DATA_MAX, LEDC_DATA_MAX, LEDC_DATA_MAX);
        }
    }
}

/******************爆闪************************* */
void    ledc_mode_bright_bs(void)
{
    static uint8_t  bs_rand_count = 0, bs_switch_count = 25;
    
    bs_switch_count++;
    if (bs_switch_count > 25)
    {
        bs_switch_count = 0;
        for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
        {
            bs_rand_count+=5;
            if (bs_rand_count > 255)
            {
                bs_rand_count = 0;
            }
            if (bs_rand_count%3)
                ledc_single_ctrl(i, ledc_color_tab[bs_rand_count%7], LEDC_DATA_MAX, LEDC_DATA_MAX, LEDC_DATA_MAX);
            else
                ledc_single_ctrl(i, ledc_color_tab[bs_rand_count%7], 0, 0, 0);

        }
    }
}


/************************跑马************************************** */
void    ledc_mode_pm_init(void)
{
    ledc_data_value = LEDC_DATA_MAX;
    ledc_color = 0;
}

void    ledc_mode_pm(void)
{
    static uint8_t tw_delay_count = 0, tw_switch_count = 0;
    static bool bdir = 0;
    tw_delay_count++;
    if (tw_delay_count > 6)
    {
        tw_delay_count = 0;
        tw_switch_count++;
        if (tw_switch_count > LEDC_RGB_NUMBER+3)
        {
            tw_switch_count = 0;
            bdir = !bdir;
            if (!bdir)
            {
                ledc_color++;
                if (ledc_color > 7)
                    ledc_color = 0;
            }
            
        }
    }

    
    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        if (!bdir)
        {
            if (i <= tw_switch_count)
            {
                ledc_single_ctrl(i, ledc_color_tab[ledc_color], ledc_data_value, ledc_data_value, ledc_data_value);
            }
            else
            {
                ledc_single_ctrl(i, ledc_color_tab[ledc_color], 0, 0, 0);
            }
        }
        else
        {
            if (i <= tw_switch_count)
            {
                ledc_single_ctrl(i, ledc_color_tab[ledc_color], 0, 0, 0);
            }
            else
            {
                ledc_single_ctrl(i, ledc_color_tab[ledc_color], ledc_data_value, ledc_data_value, ledc_data_value);
            }

        }
    }
}

/***********************************拖尾*********************************************** */
void    ledc_mode_tw_init()
{
    ledc_mode_pm_init();
}

void    ledc_mode_tw_scan()
{
    static int8_t ledc_station_flag = 0;
    static uint8_t  scan_count = 0, switch_count = 0;

    for (int8_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        
        if (i <= ledc_station_flag )
        {
            if ((ledc_station_flag-2 >= 0 ) && i == ledc_station_flag-2)
                ledc_single_ctrl(i, ledc_color_tab[ledc_color], LEDC_DATA_QUARTER, LEDC_DATA_QUARTER, LEDC_DATA_QUARTER);
            else if ((ledc_station_flag-1 >= 0 ) && i == ledc_station_flag-1)
                ledc_single_ctrl(i, ledc_color_tab[ledc_color], LEDC_DATA_HALF, LEDC_DATA_HALF, LEDC_DATA_HALF);
            else if (i == ledc_station_flag)    
                ledc_single_ctrl(i, ledc_color_tab[ledc_color], LEDC_DATA_MAX, LEDC_DATA_MAX, LEDC_DATA_MAX);
            else
                ledc_single_ctrl(i, ledc_color_tab[ledc_color], 0, 0, 0);
        }
        else
        {
            ledc_single_ctrl(i, ledc_color_tab[ledc_color], 0, 0, 0);
        }
        
    }

    scan_count++;
    if (scan_count > 6)
    {
        scan_count = 0;
        
        ledc_station_flag++;
        if (ledc_station_flag >= LEDC_RGB_NUMBER+3)
        {
            ledc_station_flag = 0;
            ledc_color++;
            if (ledc_color > 7)
                ledc_color = 0;
        }
        
    }
    

}

void    ledc_mode_off(void)
{
    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        ledc_single_ctrl(i, ledc_color_tab[6], 0, 0, 0);
    }
}

void    ledc_mode_init(void)
{
    mode_stay_time = 0;
    switch (led_mode)
    {
        case LEDC_BRIGHT:
            ledc_bright_init();
            break;
        case LEDC_BREATH:
            ledc_breath_init();
            break;
        case LEDC_NONE:
            ledc_noen_init();
            break;
        case LEDC_COLORFUL:
            ledc_colorful_init();
            break;
        case LEDC_WAVE:
            ledc_wave_init();
            break;
        case LEDC_BRIGHT_COLORFUL:
            ledc_bright_colorful_init();
            break;
        case LEDC_BS:
            ledc_bright_colorful_init();
            break;
        case LEDC_PM:
            ledc_mode_pm_init();
            break;
        case LEDC_TW:
            ledc_mode_tw_init();
            break;
        case LEDC_MODE_OFF:
            ledc_mode_off();
            break;
        
        default:
            break;
    }
}

void    ledc_mode_scan(void)
{
    switch (led_mode)
    {
        case LEDC_BRIGHT:
            ledc_mode_bright();
            break;
        case LEDC_BREATH:
            ledc_mode_breath();
            break;
        case LEDC_NONE:
            ledc_mode_noen();
            break;
        case LEDC_COLORFUL:
            ledc_mode_colorful();
            break;
        case LEDC_WAVE:
            ledc_mode_wave();
            break;
        case LEDC_BRIGHT_COLORFUL:
            ledc_mode_bright_colorful();
            break;
        case LEDC_BS:
            ledc_mode_bright_bs();
            break;
        case LEDC_PM:
            ledc_mode_pm();
            break;
        case LEDC_TW:
            ledc_mode_tw_scan();
            break;
        case LEDC_MODE_OFF:
            ledc_mode_off();
            break;
        default:
            break;
    }   
}