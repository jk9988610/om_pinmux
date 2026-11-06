"""生成模板：排版对齐 SDK 现有 user_config，避免无关 diff。"""

from __future__ import annotations

from .. import model


def pad(text: str, width: int) -> str:
    return f"{text:<{width}}"


def pin_line(macro: str, pin: str, width: int) -> str:
    return f"#define {pad(macro, width)}({pin})"


def render_pins(config: dict, pins: dict[str, dict[str, str]]) -> str:
    lines: list[str] = []
    key_roles = [r for r in model.GROUP_ORDER[0][1] if r in pins]
    lines.append("//* 按键配置 */")
    for role in key_roles:
        lines.append(pin_line(role, pins[role]["pin"], 24))
    lines.append("")

    wake = model.wake_keys(config, pins)
    lines.append("//* IO口唤醒配置 */")
    mask = f"((1<<{wake[0]}) |" + "|".join(f"(1<<{key})" for key in wake[1:])
    mask += "|(1<<SENSOR_MOTION_PIN))"
    lines.append(f"#define {pad('PIN_WAKE_UP_MASK', 24)}{mask}")
    lines.extend(
        _wake_macro(
            "KEY_PIN_WAKE_UP_EN()",
            wake,
            "PMU_PIN_WAKEUP_TYPE_FALL",
            {"KEY_R0_PIN": 3, "KEY_R1_PIN": 1, "KEY_R2_PIN": 1, "KEY_PAIR_PIN": 3},
            3,
        )
    )
    lines.append("")
    lines.extend(
        _wake_macro(
            "KEY_PIN_WAKE_UP_DIS()",
            wake,
            "PMU_PIN_WAKEUP_TYPE_DISABLE",
            {"KEY_R0_PIN": 3, "KEY_R1_PIN": 2, "KEY_R2_PIN": 2, "KEY_PAIR_PIN": 6},
            1,
        )
    )
    lines.append("")

    lines.append("//* 滚轮IO口配置 */")
    for role in ("WHEEL_A_PIN", "WHEEL_B_PIN"):
        if role in pins:
            lines.append(pin_line(role, pins[role]["pin"], 24))
    wheel = model.wheel_select(config)
    if model.board(config).get("wheel") == "SOFT_GPIO":
        lines.append(
            "/* 滚轮不在硬件 Encoder 对上：业务侧请 GPIO 软解码；下列宏仅满足 drv_encoder 编译 */"
        )
        lines.append("#define WHEEL_SOFT_GPIO         1")
        lines.append("#ifndef WHEEL_IO_SELECT")
        lines.append(f"#define {pad('WHEEL_IO_SELECT', 24)}{wheel}")
        lines.append("#endif")
    else:
        lines.append(f"#define {pad('WHEEL_IO_SELECT', 24)}{wheel}")
    lines.append("")

    lines.append("//* SENSOR IO口配置 */")
    for role in ("SENSOR_MOTION_PIN", "SENSOR_SCLK_PIN", "SENSOR_SDIO_PIN", "SENSOR_NCS_PIN"):
        if role in pins:
            lines.append(pin_line(role, pins[role]["pin"], 24))
    lines.append("")
    lines.append(
        f"#define {pad('SENSOR_DIR_DEFINE', 24)}"
        f"SENSOR_DIR_CLOCK_{model.sensor(config).get('dir_clock')}"
    )
    lines.append("#define SENSOR_DIR_CLOCK_0      1")
    lines.append("#define SENSOR_DIR_CLOCK_3      2")
    lines.append("#define SENSOR_DIR_CLOCK_6      3")
    lines.append("#define SENSOR_DIR_CLOCK_9      4")
    lines.append("                  ")

    mode_roles = model.mode_pins(config, pins)
    if model.board(config).get("mode_pins") == "dual":
        for role in mode_roles:
            lines.append(pin_line(role, pins[role]["pin"], 24))
    else:
        lines.append("//* 模式检测脚配置 */")
        for role in mode_roles:
            lines.append(pin_line(role, pins[role]["pin"], 24))
        lines.append("//{")
        lines.append("    #define MODE_BLE_CHECK      0   ")
        lines.append("    #define MODE_24G_CHECK      1")
        lines.append("//}")
    lines.append("")

    high = model.board(config).get("led_polarity") == "active_high"
    on = "gpio_set" if high else "gpio_clear"
    off = "gpio_clear" if high else "gpio_set"
    all_off = "DATAOUTCLR" if high else "DATAOUTSET"
    all_on = "DATAOUTSET" if high else "DATAOUTCLR"

    lines.append("//* LED指示灯配置 */")
    for role in ("LED_MODE_R_PIN", "LED_MODE_G_PIN", "LED_MODE_B_PIN", "LED_LOW_PIN"):
        if role in pins:
            width = 22 if role != "LED_LOW_PIN" else 22
            lines.append(pin_line(role, pins[role]["pin"], width))
    lines.append("//{")
    lines.append(f"    #define led_r_on()            ({on}(LED_MODE_R_PIN))")
    lines.append(f"    #define led_r_off()           ({off}(LED_MODE_R_PIN))")
    lines.append(f"    #define led_g_on()            ({on}(LED_MODE_G_PIN))")
    lines.append(f"    #define led_g_off()           ({off}(LED_MODE_G_PIN))")
    lines.append(f"    #define led_b_on()            ({on}(LED_MODE_B_PIN))")
    lines.append(f"    #define led_b_off()           ({off}(LED_MODE_B_PIN))")
    if "LED_LOW_PIN" in pins:
        lines.append(f"    #define led_low_off()         ({off}(LED_LOW_PIN))")
        lines.append(f"    #define led_low_on()          ({on}(LED_LOW_PIN))")
    lines.append(
        f"    #define mode_led_all_off()    (OM_GPIO0->{all_off} = "
        "(1<<LED_MODE_R_PIN)|(1<<LED_MODE_G_PIN)|(1<<LED_MODE_B_PIN))"
    )
    lines.append(
        f"    #define mode_led_all_on()     (OM_GPIO0->{all_on} = "
        "(1<<LED_MODE_R_PIN)|(1<<LED_MODE_G_PIN)|(1<<LED_MODE_B_PIN))"
    )
    lines.append("//}")
    lines.append("")
    lines.append(f"#define {pad('LED_MODE_24G_PIN', 24)}LED_MODE_R_PIN")
    lines.append(f"#define {pad('LED_MODE_BT1_PIN', 24)}LED_MODE_G_PIN")
    lines.append(f"#define {pad('LED_MODE_BT0_PIN', 24)}LED_MODE_B_PIN")
    lines.append("//{")
    lines.append(f"    #define led_bt0_on()            ({on}(LED_MODE_BT0_PIN))")
    lines.append(f"    #define led_bt0_off()           ({off}(LED_MODE_BT0_PIN))")
    lines.append(f"    #define led_24g_on()            ({on}(LED_MODE_24G_PIN))")
    lines.append(f"    #define led_24g_off()           ({off}(LED_MODE_24G_PIN))")
    lines.append(f"    #define led_bt1_on()            ({on}(LED_MODE_BT1_PIN))")
    lines.append(f"    #define led_bt1_off()           ({off}(LED_MODE_BT1_PIN))")
    lines.append("//}")
    lines.append("")

    lines.append("//* LOGO灯配置 */")
    if model.board(config).get("logo") == "ledc":
        if "LEDC_CTRL_PIN" in pins:
            lines.append(pin_line("LEDC_CTRL_PIN", pins["LEDC_CTRL_PIN"]["pin"], 24))
        if "LEDC_PIN" in pins:
            lines.append(pin_line("LEDC_PIN", pins["LEDC_PIN"]["pin"], 24))
        lines.append(f"#define {pad('LEDC_RGB_NUMBER', 24)}6")
        lines.append(f"#define {pad('LEDC_RGB_DATA_SIZE', 24)}LEDC_RGB_NUMBER*3")
    else:
        for role in ("LED_R_PIN", "LED_G_PIN", "LED_B_PIN"):
            if role in pins:
                lines.append(pin_line(role, pins[role]["pin"], 24))
    lines.append("")

    lines.append("//* USB 5V以及充电检测配置 */")
    if "USB_5V" in pins:
        lines.append(pin_line("USB_5V", pins["USB_5V"]["pin"], 24))
    if "BAT_CHG_PIN" in pins:
        lines.append(pin_line("BAT_CHG_PIN", pins["BAT_CHG_PIN"]["pin"], 24))
    lines.append("")
    lines.append(f"#define {pad('USB_5V_PIN', 24)}(gpio_read(USB_5V))")
    lines.append(f"#define {pad('BAT_CHG_OK', 24)}(gpio_read(BAT_CHG_PIN))")
    lines.append("")

    lines.append("//* LVD检测引脚 */")
    if "LVD_PIN" in pins:
        lines.append(pin_line("LVD_PIN", pins["LVD_PIN"]["pin"], 24))
        lines.append(f"#define {pad('LVD_CHECK_INDEX', 24)}({model.lvd_index(config, pins)})")
    lines.append("")

    lines.append("//* USB */")
    lines.append(pin_line("USB_DN_PIN", pins.get("USB_DN_PIN", {"pin": "P02"})["pin"], 24))
    lines.append(pin_line("USB_DP_PIN", pins.get("USB_DP_PIN", {"pin": "P03"})["pin"], 24))
    lines.append("")

    for role in ("FLASH_CS_PIN", "FLASH_SCLK_PIN", "FLASH_MOSI_PIN", "FLASH_MISO_PIN"):
        if role in pins:
            lines.append(pin_line(role, pins[role]["pin"], 24))
    lines.append("")
    lines.append("//* 当前UART仅调试用 */")
    lines.append(f"#define {pad('UART_PIN', 24)}({model.uart_pin(config)})")
    return "\n".join(lines)


def _wake_macro(
    name: str, wake: list[str], kind: str, tail_spaces: dict[str, int], sensor_spaces: int
) -> list[str]:
    lines: list[str] = []
    prefix = f"#define {pad(name, 24)}"
    for index, key in enumerate(wake):
        call = f"drv_pmu_wakeup_pin_set({key}, {kind});"
        if index == 0:
            lines.append(prefix + call + " " * tail_spaces.get(key, 1) + "\\")
        else:
            lines.append(" " * 32 + call + " " * tail_spaces.get(key, 1) + "\\")
    lines.append(
        " " * 32 + f"drv_pmu_wakeup_pin_set(SENSOR_MOTION_PIN, {kind});" + " " * sensor_spaces
    )
    return lines


def render_project_ids(config: dict) -> str:
    pid = model.project_id(config)
    return "\n".join(
        [
            f"#define iPROJECT_ID_H  {pid['high']:<20}/* 项目平台编号:OM6239 */",
            f"#define iPROJECT_ID_L  {pid['low']:<20}/* 项目编号 */",
        ]
    )


def render_project_version(config: dict) -> str:
    version = model.project_id(config)["version"]
    return (
        f"#define iREAL_VERSION_ID        {version:<13}"
        "/* 版本编号（0x80不能动），每次版本更新，后面的版本号要累加，第一个版本则为1 */"
    )


def render_project_names(config: dict) -> str:
    proj = model.project(config)
    return "\n".join(
        [
            f'#define iCONSUMER_NAME "{proj.get("customer", "")}"        /* 客户名字 */',
            f'#define iPROJECT_NAME  "{proj.get("name", "")}"      /* 项目名字 */',
        ]
    )


TABLE_TRAILING = {
    "KEY_R0_PIN": "      /* 按键配置 */",
    "KEY_R1_PIN": "    ",
    "KEY_R2_PIN": " ",
    "KEY_B_PIN": " ",
    "KEY_P_PIN": " ",
    "KEY_DPI_PIN": " ",
    "KEY_PAIR_PIN": " ",
    "WHEEL_A_PIN": "      /* 滚轮配置 */",
    "WHEEL_B_PIN": " ",
    "SENSOR_MOTION_PIN": " ",
    "SENSOR_SCLK_PIN": " ",
    "SENSOR_SDIO_PIN": " ",
    "SENSOR_NCS_PIN": " ",
    "LED_MODE_R_PIN": " ",
    "LED_MODE_G_PIN": " ",
    "LED_MODE_B_PIN": " ",
    "LED_LOW_PIN": " ",
    "LED_R_PIN": " ",
    "LED_G_PIN": " ",
    "LED_B_PIN": " ",
    "USB_5V": " ",
    "BAT_CHG_PIN": " ",
    "FLASH_CS_PIN": "       /* FLASH SPI IO CONFIG ，don't change */",
}


def render_gpio_table(config: dict, pins: dict[str, dict[str, str]]) -> str:
    lines = [
        "const user_gpio_config_t gpio_config_table[] = {",
        "    // PIN脚             模式                            上拉/下拉      初始电平",
    ]
    groups: list[list[str]] = []
    seen_pins: set[str] = set()
    for _name, roles in model.GROUP_ORDER:
        rows: list[str] = []
        for role in roles:
            if role not in pins or role in model.NO_GPIO_TABLE:
                continue
            pin = pins[role]["pin"]
            if pin in seen_pins:
                continue
            seen_pins.add(pin)
            rows.append(role)
        if rows:
            groups.append(rows)
    for index, rows in enumerate(groups):
        if index:
            lines.append("")
        for role in rows:
            item = pins[role]
            name = f"{role},"
            mode = f"{model.gpio_c_constant(item['mode'])},"
            pull = f"{model.pull_c_constant(item['pull'])},"
            level = model.level_c_constant(item["init"])
            tail = TABLE_TRAILING.get(role, "")
            lines.append("    {" + f"{name:<20}{mode:<32}{pull:<14}{level}" + "}," + tail)
    lines.append("};")
    return "\n".join(lines)


def render_features(config: dict, pins: dict[str, dict[str, str]]) -> str:
    feats = model.features(config, pins)
    name = model.project(config).get("name", "")
    lines = [
        "/**",
        " * board_features.h — 由 omcfg 生成",
        f" * board: {name}",
        " * 业务代码请用 #if BOARD_HAS_xxx / BOARD_LOGO_LEDC 包住板差异，避免直接假设宏存在。",
        " */",
        "#ifndef BOARD_FEATURES_H",
        "#define BOARD_FEATURES_H",
        "",
    ]
    for key, value in feats.items():
        lines.append(f"#define {pad(key, 28)}({1 if value else 0})")
    lines.append("")
    if model.board(config).get("wheel") == "SOFT_GPIO":
        lines.append("/* 无 BOARD_WHEEL_IO_SELECT：业务侧走 GPIO 正交解码 */")
    else:
        lines.append(f"#define {pad('BOARD_WHEEL_IO_SELECT', 28)}{model.wheel_select(config)}")
    if model.lvd_index(config, pins):
        lines.append(f"#define {pad('BOARD_LVD_CHECK_INDEX', 28)}{model.lvd_index(config, pins)}")
    lines += [
        "",
        "/* 示例：",
        " * #if BOARD_HAS_KEY_C0",
        " *   ... 矩阵列扫描 ...",
        " * #endif",
        " * #if BOARD_LOGO_LEDC",
        " *   ledc_process();",
        " * #elif BOARD_LOGO_RGB",
        " *   logo_rgb_process();",
        " * #endif",
        " */",
        "",
        "#endif /* BOARD_FEATURES_H */",
    ]
    return "\n".join(lines)


def render_sleep(config: dict, pins: dict[str, dict[str, str]]) -> str:
    name = model.project(config).get("name", "")
    b = model.board(config)
    lines = [
        "/**",
        " * periph_gpio_sleep_set() 板型模板 — 由 omcfg 生成，请合并进 user_config.c",
        f" * board: {name}",
        " */",
        "void periph_gpio_sleep_set()",
        "{",
        "    gpio_set_pad_buffer(LVD_PIN, PAD_IN_BUFFER_OFF);",
        "",
        "    gpio_set_pd(WHEEL_A_PIN);",
        "    gpio_set_pd(WHEEL_B_PIN);",
        "",
    ]
    if b.get("logo") == "ledc":
        lines += [
            "#if BOARD_LOGO_LEDC",
            "    gpio_dir_in(LEDC_PIN);",
            "    gpio_set_pd(LEDC_PIN);",
            "#endif",
        ]
    if "LED_LOW_PIN" in pins:
        lines += ["#if BOARD_HAS_LED_LOW", "    led_low_off();", "#endif"]
    lines.append("")
    if b.get("mode_pins") == "dual":
        lines += [
            "#if BOARD_MODE_DUAL_PIN",
            "    if (gpio_read(MODE_24G_PIN))",
            "        gpio_set_pu(MODE_24G_PIN, PU_30K);",
            "    else",
            "        gpio_set_pd(MODE_24G_PIN);",
            "    if (gpio_read(MODE_BLE_PIN))",
            "        gpio_set_pu(MODE_BLE_PIN, PU_30K);",
            "    else",
            "        gpio_set_pd(MODE_BLE_PIN);",
            "#endif",
        ]
    else:
        lines += [
            "#if BOARD_MODE_SINGLE_PIN",
            "    if (MODE_BLE_CHECK == gpio_read(MODE_BLE_24G_PIN))",
            "        gpio_set_pd(MODE_BLE_24G_PIN);",
            "    else",
            "        gpio_set_pu(MODE_BLE_24G_PIN, PU_30K);",
            "#endif",
        ]
    if b.get("logo") == "rgb":
        off_call = "gpio_clear" if b.get("led_polarity") == "active_high" else "gpio_set"
        lines += [
            "",
            "#if BOARD_LOGO_RGB",
            "    /* RGB LOGO：按原理图决定休眠时拉低/浮空，以下为常见关灯写法 */",
            f"    // {off_call}(LED_R_PIN); {off_call}(LED_G_PIN); {off_call}(LED_B_PIN);",
            "#endif",
        ]
    lines += ["", "    OM_RCC->CLKGATE = 0x0742;", "}"]
    return "\n".join(lines)
