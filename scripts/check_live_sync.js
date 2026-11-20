/* 用户视角回归：前端 / 后端联动——配脚未写盘时健康卡与门禁必须立即同步，
   板型切换后约束栏「必需」标签必须跟着后端推导重渲染。
   用法：node scripts/check_live_sync.js
   加载真实 web/app.js，用最小 DOM stub 驱动健康视图与门禁，不依赖后端或临时文件。
*/
"use strict";
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const code = fs.readFileSync(path.join(ROOT, "web", "app.js"), "utf8");

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
const localStorage = {
  _d: {},
  getItem(k) { return Object.prototype.hasOwnProperty.call(this._d, k) ? this._d[k] : null; },
  setItem(k, v) { this._d[k] = String(v); }, removeItem(k) { delete this._d[k]; },
};
const window = { matchMedia() { return { matches: false }; }, addEventListener() {}, pywebview: { api: {} } };
const ctx = {
  console, setTimeout, clearTimeout, document, localStorage, window,
  JSON, Math, String, Number, Object, Array, RegExp, Date, parseInt, parseFloat, isNaN, Promise,
};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(code, ctx, { filename: "app.js" });

let failures = 0;
function assert(cond, msg) { if (!cond) { failures++; console.error("FAIL " + msg); } }

// ---- 场景：新建流程走到配脚步骤，后端快照仍是「必需脚未配」 ----
ctx.S.route = "new";
ctx.S.step = 5;
ctx.S.blankMode = true;
ctx.S.form = { name: "S205", id: "0x0901", customer: "BYC", version: "1", out: "D:\\work" };
ctx.S.caps.roles = {
  MODE_BLE_24G_PIN: { display_name: "单脚模式", allowed_pins: ["P01"], required: true, suggested_pin: "P01" },
  MODE_24G_PIN: { display_name: "2.4G 模式", allowed_pins: ["P00"], required: false, suggested_pin: "P00" },
  LEGACY_STATIC: { display_name: "旧静态必需", allowed_pins: ["P03"], required: true, suggested_pin: "P03" },
};
ctx.S.caps.demand_groups = [];
ctx.S.assignments = {};
ctx.S.issues = [];
ctx.S.selectedGroup = null;
ctx.S.roleQuery = "";
// 后端上一次落盘的快照：单板型下只有 MODE_BLE_24G_PIN 必需，且尚未配置。
ctx.S.health = {
  ok: true,
  total_roles: 3,
  assigned: 0,
  required: ["MODE_BLE_24G_PIN"],
  missing: ["MODE_BLE_24G_PIN"],
  missing_detail: [{ role: "MODE_BLE_24G_PIN", suggested: "P01" }],
  conflicts: [],
  validate_errors: 0,
  validate_warnings: 0,
  complete: false,
};

// 1) 未配时健康卡与门禁正确拦截
let h = ctx.healthView();
assert(h.assigned === 0, "初始已配数为 0");
assert(h.missingCount === 1, "初始缺 1 个必需脚");
assert(h.complete === false, "初始不可生成");
assert(ctx.gate() !== null, "缺必需时门禁拦截");

// 2) 用户在脚位图点了必需脚：只改本地 S.assignments，尚未写盘，S.health 保持旧快照
ctx.S.assignments["P01"] = "MODE_BLE_24G_PIN";
h = ctx.healthView();
assert(h.assigned === 1, "配脚后「已配」立即 +1，不再读过期后端快照");
assert(h.missingCount === 0, "配脚后「缺必需」立即清零");
assert(h.missingDetail.length === 0, "配脚后缺必需明细同步清空");
assert(h.complete === true, "配脚后「可生成」立即变是");
assert(ctx.gate() === null, "配脚后门禁立即放行（修复 nextStep 先 gate 后 savePins 的死锁）");

// 3) 必需集合来自后端动态推导，静态 required 不再越权
assert(ctx.countRequired() === 1, "必需角色数读后端动态集合而非静态标记");
assert(ctx.isRequiredRole("MODE_BLE_24G_PIN") === true, "后端推导的必需脚显示必需");
assert(ctx.isRequiredRole("MODE_24G_PIN") === false, "后端未推导为必需的角色不显示必需");
assert(ctx.isRequiredRole("LEGACY_STATIC") === false, "静态 required=true 不再冒充当前必需");

// 4) 切板型后后端 required 变化，约束栏标签随之变化（整体重渲染）
ctx.S.health.required = ["MODE_24G_PIN"];
ctx.S.health.missing = ["MODE_24G_PIN"];
assert(ctx.isRequiredRole("MODE_24G_PIN") === true, "切板型后新必需脚显示必需");
assert(ctx.isRequiredRole("MODE_BLE_24G_PIN") === false, "切板型后旧必需脚不再显示必需");
const labels = ctx.colRoles();
assert(/selRole\('MODE_24G_PIN'\)[\s\S]{0,240}?必需/.test(labels), "约束栏对当前必需脚渲染必需标签");
const sb = code.slice(code.indexOf("function setBoardChoice"), code.indexOf("function viewPlugin"));
assert(/await refreshHealth\(\);[\s\S]*?\n\s*render\(\);/.test(sb), "板型保存后整体重渲染约束栏与健康卡");
assert(!/renderAside\(\);/.test(sb), "板型保存后不再只刷健康卡而漏掉约束栏");

// 5) 取消配脚后同步回退
ctx.S.health.required = ["MODE_BLE_24G_PIN"];
delete ctx.S.assignments["P01"];
h = ctx.healthView();
assert(h.assigned === 0 && h.missingCount === 1 && ctx.gate() !== null, "取消必需脚后健康卡与门禁同步回退");

if (failures) {
  console.error("\n" + failures + " 项失败");
  process.exit(1);
}
console.log("PASS 前后端实时联动：配脚即时同步健康卡/门禁 + 板型切换同步约束栏必需标签");
