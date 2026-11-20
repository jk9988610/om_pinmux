/* 用户视角回归：加载真实 app.js + material_catalog.json，验证选料步骤：
   1) STEPS.new 含「选料」且在「板型」之前，共 7 步；
   2) viewMaterial() 渲染全部关键物料型号与参数控件；
   3) 关键步骤索引与视图分派一致（配脚=5、校验=6、生成=7）；
   4) 无残留旧步骤索引错误。
   用法：node scripts/check_material_view.js
*/
"use strict";
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const code = fs.readFileSync(path.join(ROOT, "web", "app.js"), "utf8");
const catalog = JSON.parse(fs.readFileSync(path.join(ROOT, "omcfg/data/material_catalog.json"), "utf8"));

let failures = 0;
function assert(cond, msg) {
  if (!cond) { failures++; console.error("FAIL " + msg); }
  else console.log("OK   " + msg);
}

function mkEl() {
  return {
    value: "", innerHTML: "", textContent: "", className: "", disabled: false,
    classList: { add() {}, remove() {}, contains() { return false; } },
    addEventListener() {}, setAttribute() {}, getAttribute() { return "dark"; },
    focus() {}, setSelectionRange() {},
  };
}
const els = {};
const document = {
  documentElement: mkEl(),
  getElementById(id) { return els[id] || (els[id] = mkEl()); },
  addEventListener() {}, querySelector() { return null; },
};
const localStorage = { getItem() { return null; }, setItem() {}, removeItem() {} };
const window = { matchMedia() { return { matches: false }; }, addEventListener() {}, pywebview: { api: {} } };
const ctx = {
  console, setTimeout, clearTimeout, document, localStorage, window,
  JSON, Math, String, Number, Object, Array, RegExp, Date, parseInt, parseFloat, isNaN,
};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(code, ctx, { filename: "app.js" });

// 1) 步骤结构
const steps = ctx.STEPS.new;
assert(steps.length === 7, "新建流程共 7 步（实际 " + steps.length + "）");
assert(steps[1] && steps[1].t === "选料", "第 2 步是「选料」");
assert(steps[2] && steps[2].t === "板型选项", "第 3 步是「板型选项」");

// 2) 契约本身不含任何默认/统计字段
assert(catalog.schema === "om6239-material-catalog/v3", "选料契约为 v3");
assert(!Object.prototype.hasOwnProperty.call(catalog, "params_default"), "目录无统计默认参数");
for (const c of catalog.categories) {
  assert(!Object.prototype.hasOwnProperty.call(c, "default"), c.id + " 无默认选择");
}
const rgb = catalog.categories.find((c) => c.id === "rgb");
assert(rgb && rgb.params.some((p) => p.type === "int" && !p.allowed), "RGB 数量是自由整数，不受统计取值集合限制");
assert(!catalog.categories.some((c) => (c.params || []).some((p) => p.id === "rgb_polarity")),
  "点亮极性不在选料契约里");

// 3) 注入"什么都没选"的选料状态并渲染
const sel = {}, par = {};
ctx.S.route = "new";
ctx.S.step = 2;
ctx.S.material.categories = catalog.categories;
ctx.S.material.selected = sel;
ctx.S.material.params = par;
const html = ctx.viewMaterial();
assert(!/统计默认|统计众数|默认 \(按需改\)/.test(html), "选料界面不出现统计默认文案");
assert(!/setMaterialParam\([^)]*polarity/.test(html), "选料界面不提供极性参数控件");
assert(html.includes("type=\"number\""), "RGB 数量使用自由数字输入");
assert(html.includes("未指定"), "枚举参数提供未指定选项");

const keyCats = catalog.categories.filter((c) => c.key);
for (const c of keyCats) {
  assert(html.includes(c.display_name), "关键物料渲染分类：" + c.display_name);
  for (const o of (c.options || [])) {
    assert(html.includes(o.display_name), "  型号可见：" + o.display_name);
  }
}
const paramCats = catalog.categories.filter((c) => !c.key);
for (const c of paramCats) {
  assert(html.includes(c.display_name), "参数分类渲染：" + c.display_name);
  for (const p of (c.params || [])) assert(html.includes(p.display_name), "  参数可见：" + p.display_name);
}
assert(html.includes("pickMaterial("), "型号点击绑定 pickMaterial()");
assert(html.includes("setMaterialParam("), "参数变更绑定 setMaterialParam()");

// 3) 步骤分派一致性：逐 step renderMain 的 body 必须由对应 view 产出（用 marker 反推）
const dispatch = (s) => {
  ctx.S.step = s;
  ctx.S.route = "new";
  // 只取 stage 之后的内容判断，避免与 stage-desc 混淆
  const out = ctx.viewMaterial();
  return out;
};
assert(typeof ctx.viewMaterial === "function", "viewMaterial() 已定义");
assert(/\bif \(S\.step === 2\) body = viewMaterial\(\);/.test(code), "step2 分派到 viewMaterial");
assert(/\belse if \(S\.step === 5\) body = viewPins\(\);/.test(code), "step5 分派到 viewPins");
assert(/\belse if \(S\.step === 6\) body = viewValidate\(\);/.test(code), "step6 分派到 viewValidate");
assert(/\belse if \(S\.step === 7\) body = viewApply\(\);/.test(code), "step7 分派到 viewApply");

// 4) gate / nextStep 索引
assert(/if \(S\.step === 5\) \{\s*\n\s*var h = healthView\(\);/.test(code), "gate 配脚校验在 step5");
assert(/if \(S\.step === 5\) await savePins\(\);/.test(code), "nextStep 在 step5 保存脚位");
assert(!/if \(S\.step === 4\) await savePins\(\);/.test(code), "无残留 step4 savePins");
assert(!/S\.route === "new" \? 4 : 2/.test(code), "无残留配脚跳转 step4");

// 5) 极性逐脚分配（按 R/G/B 命名），按实际已配脚动态列出；不再有全局开关
ctx.S.caps.board_enums = { wheel: [
  "ENCODER_PINMUX_SEL_IO_00_01", "ENCODER_PINMUX_SEL_IO_20_21", "SOFT_GPIO",
] };
ctx.S.boardChoice = { mode_pins: "single", logo: "rgb", wheel: "SOFT_GPIO" };
ctx.S.health = { board: {}, polarity_roles: [
  { role: "LED_MODE_R_PIN", display: "模式灯 R", led: true, pin: "P00", effective: "active_low" },
  { role: "LED_MODE_G_PIN", display: "模式灯 G", led: true, pin: "P01", effective: "active_high" },
  { role: "KEY_R0_PIN", display: "按键 R0", led: false, pin: "P34", effective: "active_low" },
], polarity_map: { LED_MODE_G_PIN: "active_high" } };
const boardHtml = ctx.viewBoard();
assert(boardHtml.includes("逐脚极性"), "板型步骤提供逐脚极性面板");
assert(boardHtml.includes("模式灯 R") && boardHtml.includes("模式灯 G") && boardHtml.includes("按键 R0"), "极性按 R/G/B 与按键名逐只列出");
assert(boardHtml.includes("低电平点亮") && boardHtml.includes("高电平点亮"), "LED 极性按原理图接法逐只选");
assert(boardHtml.includes("低电平有效") && boardHtml.includes("高电平有效"), "按键极性按有效电平逐只选");
assert(boardHtml.includes("P24/P25"), "滚轮选项说明 P24/P25 可自由分配");
assert(/blank_set_polarity/.test(code), "逐脚极性走独立保存接口");
assert(!/led_polarity: S\.boardChoice\.led_polarity/.test(code), "板型设置不再提交全局极性字段");
assert(!/opt\([^\n]*LED 点亮极性/.test(code), "不再有全局 LED 极性开关");

if (failures) { console.error("\n" + failures + " 项失败"); process.exit(1); }
console.log("\nPASS 选料步骤渲染 + 索引一致性");
