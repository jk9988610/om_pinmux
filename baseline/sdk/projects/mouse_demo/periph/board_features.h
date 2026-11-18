/* OMCFG BEGIN features */
/**
 * board_features.h — 由 omcfg 生成
 * board: KC536
 * 业务代码请用 #if BOARD_HAS_xxx / BOARD_LOGO_LEDC 包住板差异，避免直接假设宏存在。
 */
#ifndef BOARD_FEATURES_H
#define BOARD_FEATURES_H

#define BOARD_HAS_KEY_C0            (0)
#define BOARD_HAS_EXTRA_KEYS        (1)
#define BOARD_HAS_DPI_PAIR          (0)
#define BOARD_HAS_SENSOR_NCS        (0)
#define BOARD_HAS_LED_LOW           (0)
#define BOARD_MODE_DUAL_PIN         (0)
#define BOARD_MODE_SINGLE_PIN       (1)
#define BOARD_LOGO_LEDC             (0)
#define BOARD_LOGO_RGB              (1)
#define BOARD_LED_ACTIVE_HIGH       (0)
#define BOARD_LED_ACTIVE_LOW        (1)
#define BOARD_WHEEL_SOFT_GPIO       (0)

#define BOARD_WHEEL_IO_SELECT       ENCODER_PINMUX_SEL_IO_20_21
#define BOARD_LVD_CHECK_INDEX       POF_LVD_PIN_P23

/* 示例：
 * #if BOARD_HAS_KEY_C0
 *   ... 矩阵列扫描 ...
 * #endif
 * #if BOARD_LOGO_LEDC
 *   ledc_process();
 * #elif BOARD_LOGO_RGB
 *   logo_rgb_process();
 * #endif
 */

#endif /* BOARD_FEATURES_H */
/* OMCFG END features */

/* USER CODE BEGIN board_features_h */
/* USER CODE END board_features_h */
