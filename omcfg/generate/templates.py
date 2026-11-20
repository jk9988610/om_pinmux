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
    if wake:
        mask = f"((1<<{wake[0]}) |" + "|".join(f"(1<<{key})" for key in wake[1:])
        mask += "|(1<<SENSOR_MOTION_PIN))"
    else:
        mask = "((1<<SENSOR_MOTION_PIN))"
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
        lines.append("/* 滚轮不在硬件 Encoder 对上：业务侧请 GPIO 软解码；下列宏仅满足 drv_encoder 编译 */")
        lines.append("#define WHEEL_SOFT_GPIO         1")
        lines.append("#ifndef WHEEL_IO_SELECT")
        lines.append(f"#define {pad('WHEEL_IO_SELECT', 24)}{wheel}")
        lines.append("#endif")
    else:
        lines.append(f"#define {pad('WHEEL_IO_SELECT', 24)}{wheel}")
    lines.append("")

    lines.append("//* SENSOR IO口配置 */")
    sensor_roles = ["SENSOR_MOTION_PIN", "SENSOR_SCLK_PIN"]
    if model.sensor_bus(config) == "spi_4wire":
        sensor_roles += ["SENSOR_MOSI_PIN", "SENSOR_MISO_PIN"]
    else:
        sensor_roles.append("SENSOR_SDIO_PIN")
    sensor_roles.append("SENSOR_NCS_PIN")
    for role in sensor_roles:
        if role in pins:
            lines.append(pin_line(role, pins[role]["pin"], 24))
    if model.sensor_v2_en(config):
        lines.append(f"#define {pad('SENSOR_2V_IN_EN', 24)}(1<<7|1<<6)")
    lines.append("")
    lines.append(f"#define {pad('SENSOR_DIR_DEFINE', 24)}SENSOR_DIR_CLOCK_{model.sensor(config).get('dir_clock')}")
    lines.append("#define SENSOR_DIR_CLOCK_0      1")
    lines.append("#define SENSOR_DIR_CLOCK_3      2")
    lines.append("#define SENSOR_DIR_CLOCK_6      3")
    lines.append("#define SENSOR_DIR_CLOCK_9      4")
    lines.append("                  ")

    mode_roles = model.mode_pins(config, pins)
    if model.board(config).get("mode_pins") == "dual":
        for role in mode_roles:
            lines.append(pin_line(role, pins[role]["pin"], 24))
        # 双脚拨杆各有独立有效电平（S205 两脚均高有效）；key_io 三档判断要用。
        lines.append("//{")
        lines.append("    #define MODE_BLE_CHECK      1")
        lines.append("    #define MODE_24G_CHECK      1")
        lines.append("//}")
    else:
        lines.append("//* 模式检测脚配置 */")
        for role in mode_roles:
            lines.append(pin_line(role, pins[role]["pin"], 24))
        lines.append("//{")
        lines.append("    #define MODE_BLE_CHECK      0   ")
        lines.append("    #define MODE_24G_CHECK      1")
        lines.append("//}")
    lines.append("")

    # 极性逐脚独立：每只灯读自己的 config.polarity，互不牵连。旧版别名
    # 24G/BT1/BT0 复用 R/G/B 物理脚，role_polarity 已让它们跟随对应主模式灯。
    def _on_off(role: str) -> tuple[str, str]:
        high = model.role_polarity(config, role) == "active_high"
        return ("gpio_set", "gpio_clear") if high else ("gpio_clear", "gpio_set")

    lines.append("//* LED指示灯配置 */")
    for role in ("LED_MODE_R_PIN", "LED_MODE_G_PIN", "LED_MODE_B_PIN", "LED_LOW_PIN"):
        if role in pins:
            width = 22 if role != "LED_LOW_PIN" else 22
            lines.append(pin_line(role, pins[role]["pin"], width))
    lines.append("//{")
    for fn, role in (
        ("led_r", "LED_MODE_R_PIN"),
        ("led_g", "LED_MODE_G_PIN"),
        ("led_b", "LED_MODE_B_PIN"),
    ):
        on, off = _on_off(role)
        lines.append(f"    #define {pad(fn + '_on()', 22)}({on}({role}))")
        lines.append(f"    #define {pad(fn + '_off()', 22)}({off}({role}))")
    if "LED_LOW_PIN" in pins:
        on, off = _on_off("LED_LOW_PIN")
        lines.append(f"    #define {pad('led_low_off()', 22)}({off}(LED_LOW_PIN))")
        lines.append(f"    #define {pad('led_low_on()', 22)}({on}(LED_LOW_PIN))")
        # S205 充电指示灯复用 low 灯（同极性），供 sys_deep_sleep_process 使用。
        lines.append(f"    #define {pad('led_chg_off()', 22)}({off}(LED_LOW_PIN))")
        lines.append(f"    #define {pad('led_chg_on()', 22)}({on}(LED_LOW_PIN))")
    # 批量宏按每只模式灯各自的极性分别置位/清零；三脚同极性时折叠成一条
    # DATAOUTSET/CLR，保持 KC536 基线字节一致。
    mode_leds = [r for r in ("LED_MODE_R_PIN", "LED_MODE_G_PIN", "LED_MODE_B_PIN") if r in pins]
    if mode_leds:
        highs = [model.role_polarity(config, r) == "active_high" for r in mode_leds]
        if len(set(highs)) == 1:
            reg = "DATAOUTCLR" if highs[0] else "DATAOUTSET"
            inv = "DATAOUTSET" if highs[0] else "DATAOUTCLR"
            mask = "|".join(f"(1<<{r})" for r in mode_leds)
            lines.append(f"    #define {pad('mode_led_all_off()', 22)}(OM_GPIO0->{reg} = {mask})")
            lines.append(f"    #define {pad('mode_led_all_on()', 22)}(OM_GPIO0->{inv} = {mask})")
        else:
            off_ops = " ".join(f"({_on_off(r)[1]}({r}));" for r in mode_leds)
            on_ops = " ".join(f"({_on_off(r)[0]}({r}));" for r in mode_leds)
            lines.append(f"    #define {pad('mode_led_all_off()', 22)}do {{ {off_ops} }} while(0)")
            lines.append(f"    #define {pad('mode_led_all_on()', 22)}do {{ {on_ops} }} while(0)")
    lines.append("//}")
    lines.append("")
    # 2.4G 指示灯复用 R/G/B 由硬件决定（board.mode_24g_led）：KC536=R，S205=G(P05)。
    lines.append(f"#define {pad('LED_MODE_24G_PIN', 24)}{model.mode_24g_main_role(config)}")
    lines.append(f"#define {pad('LED_MODE_BT1_PIN', 24)}LED_MODE_G_PIN")
    lines.append(f"#define {pad('LED_MODE_BT0_PIN', 24)}LED_MODE_B_PIN")
    lines.append("//{")
    for fn, role in (
        ("led_bt0", "LED_MODE_BT0_PIN"),
        ("led_24g", "LED_MODE_24G_PIN"),
        ("led_bt1", "LED_MODE_BT1_PIN"),
    ):
        on, off = _on_off(role)
        lines.append(f"    #define {pad(fn + '_on()', 24)}({on}({role}))")
        lines.append(f"    #define {pad(fn + '_off()', 24)}({off}({role}))")
    lines.append("//}")
    lines.append("")

    lines.append("//* LOGO灯配置 */")
    if model.board(config).get("logo") == "ledc":
        if "LEDC_CTRL_PIN" in pins:
            lines.append(pin_line("LEDC_CTRL_PIN", pins["LEDC_CTRL_PIN"]["pin"], 24))
        if "LEDC_PIN" in pins:
            lines.append(pin_line("LEDC_PIN", pins["LEDC_PIN"]["pin"], 24))
        lines.append(f"#define {pad('LEDC_RGB_NUMBER', 24)}{model.ledc_rgb_number(config)}")
        lines.append(f"#define {pad('LEDC_RGB_DATA_SIZE', 24)}LEDC_RGB_NUMBER*3")
    # KC536 骨架的 led.c / user_config.c 无条件引用 LED_R/G/B，因此这三个宏
    # 不再按 logo 分支：只要配置里保留了脚位就输出（灯带模式下同样需要）。
    # 旧 CH04 骨架的灯带工程不含 LED_R/G/B 脚，那里自然不会输出，行为不变。
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
    # 指示灯策略：hint_only 时定义守卫宏，编译期排除底层 logo_cfg/ind_config/gpio_toggle
    # 点灯调用，只留 mode_led_hint 独占。full（默认 KC536）不输出任何行 → 字节一致。
    if model.led_indicator(config) == "hint_only":
        lines.append("")
        lines.append("//* 指示灯策略：只用 mode_led_hint 独占（S205），底层点灯调用被排除 */")
        lines.append(f"#define {pad('BOARD_LED_INDICATOR_ONLY', 26)}1")
    return "\n".join(lines)


def _wake_macro(name: str, wake: list[str], kind: str, tail_spaces: dict[str, int], sensor_spaces: int) -> list[str]:
    lines: list[str] = []
    prefix = f"#define {pad(name, 24)}"
    for index, key in enumerate(wake):
        call = f"drv_pmu_wakeup_pin_set({key}, {kind});"
        if index == 0:
            lines.append(prefix + call + " " * tail_spaces.get(key, 1) + "\\")
        else:
            lines.append(" " * 32 + call + " " * tail_spaces.get(key, 1) + "\\")
    lines.append(" " * 32 + f"drv_pmu_wakeup_pin_set(SENSOR_MOTION_PIN, {kind});" + " " * sensor_spaces)
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
    # 物料参数：数量/极性/拨杆段数/蓝牙通道以数值宏暴露，业务代码不再写死字符串。
    lines += [
        "",
        "/* 物料参数（由选料写入 project.materials，经 board 派生） */",
        f"#define {pad('BOARD_RGB_COUNT', 28)}{model.ledc_rgb_number(config)}",
        f"#define {pad('BOARD_SWITCH_SEGMENTS', 28)}{model.switch_segments(config)}",
        f"#define {pad('BOARD_BLE_CHANNELS', 28)}{model.ble_channels(config)}",
        f"#define {pad('BOARD_MODE_KEY_PRESENT', 28)}{1 if model.mode_key_present(config) else 0}",
    ]
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
    """生成 user_config.c 的 periph_gpio_sleep_set() 实现（唯一强定义）。

    逐行复刻 SDK 既有写法：板型之间只差模式脚/LOGO 分支，避免无意义的整段
    重排。该 payload 写进 user_config.c 的 OMCFG sleep 块，不再生成独立 .c。
    """
    b = model.board(config)
    lines = [
        "/**",
        " * @brief 外设IO口配置，休眠前调用，避免漏电",
        " * ",
        " */",
        "void periph_gpio_sleep_set()",
        "{",
        "    gpio_set_pad_buffer(LVD_PIN,PAD_IN_BUFFER_OFF);     /* 关掉LVD的输入BUFFER，避免漏电 */",
        "",
        "    gpio_set_pd(WHEEL_A_PIN);",
        "    gpio_set_pd(WHEEL_B_PIN);",
        "",
    ]
    if b.get("logo") == "ledc" and "LEDC_PIN" in pins:
        lines += ["    gpio_dir_in(LEDC_PIN);", "    gpio_set_pd(LEDC_PIN);"]
        if "LED_LOW_PIN" in pins:
            lines.append("    led_low_off();")
        lines.append("")
    mode = b.get("mode_pins")
    if mode == "dual":
        lines += [
            "    if (gpio_read(MODE_24G_PIN))",
            "        gpio_set_pu(MODE_24G_PIN,PU_30K);",
            "    else",
            "        gpio_set_pd(MODE_24G_PIN);",
            "    if (gpio_read(MODE_BLE_PIN))",
            "        gpio_set_pu(MODE_BLE_PIN,PU_30K);",
            "    else",
            "        gpio_set_pd(MODE_BLE_PIN);",
            "    ",
            "    ",
        ]
    elif mode == "single":
        lines += [
            "    if(MODE_BLE_CHECK == gpio_read(MODE_BLE_24G_PIN))",
            "        gpio_set_pd(MODE_BLE_24G_PIN);",
            "    else",
            "        gpio_set_pu(MODE_BLE_24G_PIN,PU_30K);",
        ]
    lines += ["    OM_RCC->CLKGATE = 0x0742;", "}"]
    return "\n".join(lines)
