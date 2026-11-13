#include "ledc_mode.h"
#include "led.h"
#include <stdint.h>
#include "math.h"

#define LEDC_RGB_1      0
#define LEDC_RGB_2      1
#define LEDC_RGB_3      2
#define LEDC_RGB_4      3

uint8_t mode_stay_time;
#define MODE_BREAT_TIME     1
#define MODE_NOEN_TIME      2
#define MODE_COLORFUL_TIME  1
#define MODE_WT_TIME        2

#define STATUS_COUNT        6
#define STATUS_MODE         7

uint8_t qcnh_tab[3] = {0};
uint8_t qcnh_gruop[][3] = {
        0,1,2,
        1,2,0,
        2,0,1,
        1,0,2,
        0,2,1,
        2,1,0,
};

uint8_t rainbow_table[STATUS_MODE][3] =
{
    {240, 0,    0},    // 0 
    {120, 120,  0},    // 1
    {0,   240,  0},   // 2 
    {0,   120,  120},   // 3 
    {0,   0,    240},   // 4 
    {120, 0,    120},   // 5
    {240, 0,    0},   // 6 
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
int16_t ledc_data_value;
uint8_t ledc_data_value_1;
uint8_t ledc_data_value_2;

static bool xyls_dir = 0;
volatile int8_t xyls_count = 0;

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

/**************七彩霓虹*************** */
//根据输入index, 取一个颜色，
//      index        颜色索引，输入不同值会得到不同的颜色输出，输入范围：0~767
void getColors(uint8_t pColor, uint16_t index)
{
  //根据输入数值生成颜色，2个颜色之间此消彼长地变化
  if(index <= 255)
  {
    rainbow_table[pColor][1] = index;
    rainbow_table[pColor][0] = 0;
    rainbow_table[pColor][2] = 255-index;
  }
  else if(index <= 511)
  {
    rainbow_table[pColor][1] = 511 - index;
    rainbow_table[pColor][0] = index - 256;
    rainbow_table[pColor][2] = 0;
  }
  else if(index <= 767)
  {
    rainbow_table[pColor][1] = 0;
    rainbow_table[pColor][0] = 767 - index;
    rainbow_table[pColor][2] = index - 512;
  }
}

void    ledc_colorful_init(void)
{
    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        ledc_single_ctrl(i, 7, rainbow_table[i%STATUS_MODE][0],rainbow_table[i%STATUS_MODE][1],rainbow_table[i%STATUS_MODE][2]);
    }
    
}

void ledc_mode_colorful_grb_set()
{
    static uint16_t color_index = 0;
    for (uint8_t i = 0; i < STATUS_MODE; i++)
    {
        uint16_t index;
        //这段代码中的数字(60)，决定了每个灯之间的颜色差异(颜色渐变的缓和度，可自行测试, 如果设置为0，则失去流水灯效果)
        index  = color_index + (60) * i;
        if(index >= 768)
            index -= 768;
        getColors(i,index);
    }
    color_index++;
    if (color_index > 767)
    {
        color_index = 0;
    }
    
}

void    ledc_mode_colorful(void)
{
    ledc_mode_colorful_grb_set();
    

    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        ledc_single_ctrl(i, 7, rainbow_table[i%STATUS_MODE][0],rainbow_table[i%STATUS_MODE][1],rainbow_table[i%STATUS_MODE][2]);
    } 
}

/******************爆闪************************* */
void ledc_bs_init()
{
    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        ledc_single_ctrl(i, ledc_color_tab[6], 0, 0, 0);
    }
}

void    ledc_mode_bright_bs(void)
{
    static uint8_t  bs_rand_count = 0, bs_switch_count = 25;
    static bool bbs_light_dir = 0;
    bs_switch_count++;
    if (bs_switch_count > 25)
    {
        bs_rand_count+=bs_switch_count;
        bs_switch_count = 0;
        bbs_light_dir = !bbs_light_dir;
        if (bs_rand_count>255)
            bs_rand_count = 0;
    }
    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        if (bbs_light_dir)
        {
            if (i%2)
                ledc_single_ctrl(i, ledc_color_tab[bs_rand_count%7], LEDC_DATA_MAX, LEDC_DATA_MAX, LEDC_DATA_MAX);
            else
                ledc_single_ctrl(i, ledc_color_tab[bs_rand_count%7], 0, 0, 0);
        }
        else
        {
            if (i%2)
                ledc_single_ctrl(i, ledc_color_tab[bs_rand_count%7], 0, 0, 0);                
            else
                ledc_single_ctrl(i, ledc_color_tab[bs_rand_count%7], LEDC_DATA_MAX, LEDC_DATA_MAX, LEDC_DATA_MAX);
        }
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
    static uint16_t  rand_count = 15,rand_count_bak;
    static uint16_t switch_count = 250;
    switch_count++;
    if (switch_count > 1000)
    {
        switch_count = 0;
        rand_count+=9;
        if (rand_count > 65500)
        {
            rand_count = 15;
        }
        rand_count_bak = rand_count;
    }

    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        rand_count+=3;
        ledc_single_ctrl(i, ledc_color_tab[rand_count%7], LEDC_DATA_MAX, LEDC_DATA_MAX, LEDC_DATA_MAX);
    }
    rand_count = rand_count_bak;
}

/***************波纹*************** */
void    ledc_bw_init(void)
{
    ledc_noen_init();

    bledc_status = 0;
    ledc_data_value_1 = LEDC_DATA_MAX-2;
    ledc_data_value_2 = 2;
    wave_count = 0;
}

void    ledc_mode_bw(void)
{
    if (!bledc_status)
    {
        ledc_data_value_1-=2;
        ledc_data_value_2+=2;
        if (ledc_data_value_1 <= 2 || ledc_data_value_2 >= (LEDC_DATA_MAX-2))
        {
            bledc_status = true;
        }
    }
    else
    {
        ledc_data_value_1+=2;
        ledc_data_value_2-=2;
        if (ledc_data_value_1 >= (LEDC_DATA_MAX-2) || ledc_data_value_2 <= 2)
        {
            bledc_status = false;
            wave_count++;
        }
        
    }

    if (wave_count >= LEDC_RGB_NUMBER)
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

/***********七彩闪烁*********** */
void    ledc_colorful_flash_init(void)
{
    // for (uint8_t i = 0; i < LEDC_RGB_NUMBER; i++)
    // {
    //     ledc_single_ctrl(i, ledc_color_tab[7%i], LEDC_DATA_MAX, LEDC_DATA_MAX, LEDC_DATA_MAX);
    // }
}

void    ledc_mode_colorful_flash(void)
{
    static uint16_t  rand_count = 15,rand_count_bak;
    static uint16_t switch_count = 250;
    switch_count++;
    if (switch_count > 35)
    {
        switch_count = 0;
        rand_count+=5;
        if (rand_count > 65500)
        {
            rand_count = 15;
        }
        rand_count_bak = rand_count;
    }

    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        rand_count+=4;
        ledc_single_ctrl(i, ledc_color_tab[rand_count%7], LEDC_DATA_MAX, LEDC_DATA_MAX, LEDC_DATA_MAX);
    }
    rand_count = rand_count_bak;
}

/***********呼吸灯************** */
void    ledc_breath_init(void)
{
    memset(ledc_data_tab,0,sizeof(ledc_data_tab));
    bledc_status = 1;
    ledc_data_value = 0;
}

void    ledc_mode_breath(void)
{
    mode_stay_time++;
    if (mode_stay_time > MODE_BREAT_TIME)
    {
        mode_stay_time = 0;
        if (!bledc_status)
        {
            ledc_data_value-=2;
            if (ledc_data_value <= 2)
            {
                bledc_status = true;
                ledc_color++;
                if (ledc_color >= 7)
                    ledc_color = 0;
            }
        }
        else
        {
            ledc_data_value+=2;
            
            if (ledc_data_value >= (LEDC_DATA_MAX-2))
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

/*************常亮***************** */
void    ledc_bright_init(void)
{
    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        ledc_single_ctrl(i, ledc_color_tab[6], LEDC_DATA_MAX, 0, 0);
    }
    
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

/********************行云流水*************************** */
void ledc_xyls_init()
{
    ledc_data_value = 0;
    xyls_dir = 0;
    xyls_count = 0;
}

void ledc_mode_xyls()
{
    static bool bargb_stay = 0;
    static uint8_t  stay_count = 0;
    if (bargb_stay)
    {
        stay_count++;
        if (stay_count > 125)
        {
           stay_count = 0;
           bargb_stay = false;
        }
        
    }
    else
    {
        if (!xyls_dir)
        {
            ledc_data_value+=8;
            if (ledc_data_value >= (LEDC_DATA_MAX))
            {
                xyls_count++;
                ledc_data_value = 0;
                if (xyls_count >= (LEDC_RGB_NUMBER+1))
                {
                    bargb_stay = true;
                    xyls_count = LEDC_RGB_NUMBER;
                    ledc_data_value = 0;
                    xyls_dir = !xyls_dir;
                }
                
            }
        }
        else
        {
            ledc_data_value-=8;
            if (ledc_data_value < 0)
            {
                ledc_data_value = LEDC_DATA_MAX;
                xyls_count--;
                if (xyls_count < 0)
                {
                    xyls_count = 0;
                    bargb_stay = true;
                    ledc_data_value = 0;
                    xyls_dir = !xyls_dir;
                    ledc_color++;
                    if (ledc_color > 6)
                        ledc_color = 0;
                    return;
                }
            }
        }
    }

    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        if (i == xyls_count)
        {
            ledc_single_ctrl(i, ledc_color_tab[ledc_color], ledc_data_value, ledc_data_value, ledc_data_value);
        }
        else if (i < xyls_count)
        {
            ledc_single_ctrl(i, ledc_color_tab[ledc_color], LEDC_DATA_MAX, LEDC_DATA_MAX, LEDC_DATA_MAX);
        }
        else
        {
            ledc_single_ctrl(i, ledc_color_tab[ledc_color], 0, 0, 0);
        }
        
    }

}

/*************单灯流水***************** */
void    ledc_ddls_init(void)
{

    
}

void    ledc_mode_ddls(void)
{
    static uint8_t switch_count = 0;
    static uint8_t ddls_count = 0;
    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        if (ddls_count == i)
            ledc_single_ctrl(i, ledc_color_tab[ledc_color], LEDC_DATA_MAX, LEDC_DATA_MAX, LEDC_DATA_MAX);
        else
            ledc_single_ctrl(i, ledc_color_tab[ledc_color], 0, 0, 0);
    }

    switch_count++;
    if (switch_count > 20)
    {
        switch_count = 0;
        ddls_count++;
        if (ddls_count >= (LEDC_RGB_NUMBER+4))
        {
            ddls_count = 0;  
            ledc_color++;
            if (ledc_color > 6)
                ledc_color = 0;
        }
    }
    
}

/********************扫尾*************************** */
void ledc_sw_init()
{
    ledc_data_value = 3;
}

void ledc_sw_xyls()
{
    static bool sw_wait= 0;
    static uint32_t sw_wait_count= 0;
    static uint8_t sw_count = 0,sw_ledc1 = LEDC_DATA_MAX, sw_ledc2 = 120, sw_ledc3 = 60;

    if (sw_wait)
    {
        sw_wait_count++;
        if (sw_wait_count > 60)
        {
            sw_wait_count = 0;
            sw_wait = false;
        }
        else
        {
            return;
        }
        
    }
    
    ledc_data_value+=12;
    sw_ledc1-=6;
    sw_ledc2-=3;
    sw_ledc3-=1;
    if (ledc_data_value > (LEDC_DATA_MAX))
    {
        sw_ledc1 = LEDC_DATA_MAX;
        sw_ledc2 = 120;
        sw_ledc3 = 20;
        ledc_data_value = 0;
        sw_count++;
        if (sw_count > (LEDC_RGB_NUMBER+3))
        {
            sw_wait = true;
            sw_count = 0;
            ledc_color++;
            if (ledc_color > 6)
                ledc_color = 0;
        }
        
    }
    
    
    for (size_t i = 0; i < LEDC_RGB_NUMBER; i++)
    {
        if (sw_count==i)
            ledc_single_ctrl(i, ledc_color_tab[ledc_color], ledc_data_value, ledc_data_value, ledc_data_value);
        else if ((sw_count-1) >= 0 && i==(sw_count-1))
            ledc_single_ctrl(i, ledc_color_tab[ledc_color], sw_ledc1, sw_ledc1, sw_ledc1);
        else if ((sw_count-2) >= 0 && i==(sw_count-2))
        {
            ledc_single_ctrl(i, ledc_color_tab[ledc_color], sw_ledc2, sw_ledc2, sw_ledc2);
        }
        else if ((sw_count-3) >= 0 && i==(sw_count-3) )
        {
            ledc_single_ctrl(i, ledc_color_tab[ledc_color], sw_ledc3, sw_ledc3, sw_ledc3);
        }
        else
            ledc_single_ctrl(i, ledc_color_tab[ledc_color], 0, 0, 0);
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
        case LEDC_COLORFUL:
            ledc_colorful_init();
            break;
        case LEDC_BS:
            ledc_bs_init();
            break;
        case LEDC_BRIGHT_COLORFUL:
            ledc_bright_colorful_init();
            break;
        case LEDC_BW:
            ledc_bw_init();
            break;
        case LEDC_COLORFUL_FLASH:
            ledc_colorful_flash_init();
            break;
        case LEDC_BREATH:
            ledc_breath_init();
            break;
        case LEDC_BRIGHT:
            ledc_bright_init();
            break;
        case LEDC_XYLS:
            ledc_xyls_init();
            break;
        case LEDC_DDLS:
            ledc_ddls_init();
            break;
        case LEDC_SW:
            ledc_sw_init();
            break;
        case LEDC_NONE:
            ledc_noen_init();
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
        case LEDC_COLORFUL:
            ledc_mode_colorful();
            break;
      case LEDC_BS:
            ledc_mode_bright_bs();
            break;
        case LEDC_BRIGHT_COLORFUL:
            ledc_mode_bright_colorful();
            break;
        case LEDC_BW:
            ledc_mode_bw();
            break;
        case LEDC_COLORFUL_FLASH:
            ledc_mode_colorful_flash();
            break;
        case LEDC_BREATH:
            ledc_mode_breath();
            break;
        case LEDC_BRIGHT:
            ledc_mode_bright();
            break;
        case LEDC_XYLS:
            ledc_mode_xyls();
            break;
        case LEDC_DDLS:
            ledc_mode_ddls();
            break;
        case LEDC_SW:
            ledc_sw_xyls();
            break;
        case LEDC_NONE:
            ledc_mode_noen();
            break;
        case LEDC_MODE_OFF:
            ledc_mode_off();
            break;
        default:
            break;
    }   
}