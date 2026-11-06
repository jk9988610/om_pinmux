# OM6239 PinMux (`om_pinmux`)

硬件脚位 / 板级特征写入工具。业务协议（RF/HID 映射）不在范围内。

## 换板推荐流程（调查表先行）

1. 打开并填写调查表说明：`survey/QUESTIONNAIRE.md`
2. 多板差异对照：`survey/multi_board_matrix.md`
3. 生成并填写答案 JSON：

```bat
cd /d E:\tools\om_pinmux
python om_pinmux.py survey blank --out survey\answers_NEWBOARD.json
:: 编辑 answers_NEWBOARD.json
python om_pinmux.py survey check  --answers survey\answers_NEWBOARD.json
python om_pinmux.py survey export --answers survey\answers_NEWBOARD.json
```

4. 双击 `launch.bat`（或 `打开引脚工具.bat`）打开 UI；也可 `launch.ps1` → 选板 → 校验 → 写入工程 `user_config`
5. 冒烟：键控灯 → 滚轮 → 光流 → USB HID → 24G/BLE 配对

等价：`python survey.py blank|check|export ...`

## 已收录板 JSON

`boards/`：KC536、CH04、A02、BD316、BD319、MW650、HTW17

## 调查表会强制提醒的坑

- 传感器 3 线 SDIO 与 4 线 MOSI/MISO 混用
- DPI 与 PAIR 同脚
- UART 复用按键
- LEDC 与滚轮重叠
- 无 PAIR 且关闭 24G 首次自动配对
- RGB 板整包套 CH04 LEDC

## 其它命令

```bat
python om_pinmux.py validate --all
python om_pinmux.py apply --target <SDK根> --board BD319 --dry-run
```
