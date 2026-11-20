/* 用户视角回归：加载真实 app.js，验证软件工程师照原理图配脚时：
   1) 约束栏能看到所有角色（含原 v1=false 的 LED_R / SENSOR_MOSI / KEY_L / 编码器等）；
   2) 按宏名 / 显示名 / role_id / 中文别名都能搜索定位；
   3) 界面不再出现「一键按推荐配置 / 推荐 Pxx」字样。
   用法：node scripts/check_constraint_view.js
   数据直接读仓库内 options.json + role_catalog.json，不依赖后端或临时文件。
*/
"use strict";
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const code = fs.readFileSync(path.join(ROOT, "web", "app.js"), "utf8");
const html = fs.readFileSync(path.join(ROOT, "web", "index.html"), "utf8");
const options = JSON.parse(fs.readFileSync(path.join(ROOT, "omcfg/data/options.json"), "utf8"));
const catalog = JSON.parse(fs.readFileSync(path.join(ROOT, "omcfg/data/role_catalog.json"), "utf8"));

// 复刻 Api.role_capabilities() 的字段组装（options.json 存在时走这条）
const roles = {};
for (const [mac, opt] of Object.entries(options.options || {})) {
  roles[mac] = {
    role_id: opt.role_id || "",
    aliases: [mac, ...(opt.aliases || [])],
    allowed_pins: opt.allowed_pins || [],
    v1: !!opt.v1,
    display_name: opt.display_name || mac,
    required: !!opt.required,
    suggested_pin: opt.suggested_pin || null,
  };
}
const caps = { roles, demand_groups: catalog.demand_groups || [] };

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
  JSON, Math, String, Number, Object, Array, RegExp, Date, parseInt, parseFloat, isNaN,
};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(code, ctx, { filename: "app.js" });

ctx.S.caps.roles = caps.roles;
ctx.S.caps.demand_groups = caps.demand_groups;
ctx.S.route = "new";
ctx.S.step = 4;
ctx.S.blankMode = true;
ctx.S.assignments = {};
ctx.S.pluginState = { plugins: [], enabled: [] };
ctx.S.selectedGroup = null;
ctx.S.roleQuery = "";

function assert(cond, msg) { if (!cond) throw new Error(msg); }
function hasRole(h, mac) { return h.indexOf("selRole('" + mac + "')") >= 0; }

// 1) 全量视图包含原 v1=false 的原理图网络
const full = ctx.colRoles();
const schematic = [
  "LED_R_PIN", "LED_G_PIN", "LED_B_PIN",
  "SENSOR_MOSI_PIN", "SENSOR_MISO_PIN", "SENSOR_NCS_PIN",
  "KEY_L_PIN", "KEY_M_PIN", "KEY_R_PIN",
  "H_ENCODER_A_PIN", "H_ENCODER_B_PIN", "MODE_WIRED_PIN",
];
const hidden = schematic.filter(function (m) { return !hasRole(full, m); });
assert(hidden.length === 0, "约束栏仍隐藏原理图网络: " + hidden.join(", "));

// 2) 搜索：宏名 / 显示名 / role_id / 中文别名
const cases = [
  ["LED_R", "LED_R_PIN"],
  ["SENSOR_MOSI", "SENSOR_MOSI_PIN"],
  ["led.r", "LED_R_PIN"],
  ["编码器", "H_ENCODER_A_PIN"],
  ["KEY_L", "KEY_L_PIN"],
  ["左键", "KEY_L_PIN"],
];
cases.forEach(function (c) {
  ctx.S.roleQuery = String(c[0]).toLowerCase();
  const h = ctx.colRoles();
  assert(hasRole(h, c[1]), "搜索「" + c[0] + "」未命中 " + c[1]);
});
ctx.S.roleQuery = "";

// 3) 需求组：全部 14 组都渲染，且每个角色都能通过点击某个组在约束栏找到
const groupHtml = ctx.colGroups();
const groupIds = caps.demand_groups.map(function (g) { return g.id; });
groupIds.forEach(function (gid) {
  assert(groupHtml.indexOf("selGroup('" + gid + "')") >= 0, "需求组未渲染: " + gid);
});
// 逐一选中每个组，收集约束栏出现的角色，验证覆盖全部 60 个
const reachable = new Set();
groupIds.forEach(function (gid) {
  ctx.S.selectedGroup = gid;
  const h = ctx.colRoles();
  Object.keys(caps.roles).forEach(function (mac) { if (hasRole(h, mac)) reachable.add(mac); });
});
ctx.S.selectedGroup = null;
const allMacs = Object.keys(caps.roles);
const unreachable = allMacs.filter(function (m) { return !reachable.has(m); });
assert(unreachable.length === 0, "需求组无法覆盖的角色: " + unreachable.join(", "));
assert(reachable.size === allMacs.length, "需求组覆盖 " + reachable.size + "/" + allMacs.length + " 角色");

// 4) 「必需」标签必须跟随板型，不能用 options.json 的静态 required
// 真实场景：选了双脚，单脚 MODE_BLE_24G_PIN 不能再显示「必需」。
function requiredTags(h) {
  const out = [];
  const re = /class="role[^"]*"[^>]*>[\s\S]*?<b>([^<]*)<\/b>(<span class="tag err">必需<\/span>)?/g;
  let m;
  while ((m = re.exec(h)) !== null) out.push([m[1], !!m[2]]);
  return out;
}
ctx.S.roleQuery = "mode_";
ctx.S.selectedGroup = null;
// 模拟后端 blank_status 返回的动态 required（选双脚）
ctx.S.health = { required: ["MODE_24G_PIN", "MODE_BLE_PIN"] };
const dualHtml = ctx.colRoles();
const dualTags = requiredTags(dualHtml);
assert(dualTags.some((t) => t[0].indexOf("2.4G 模式开关") >= 0 && t[1]), "双脚模式下 MODE_24G 应标必需");
assert(dualTags.some((t) => t[0].indexOf("BLE 模式开关") >= 0 && t[1]), "双脚模式下 MODE_BLE 应标必需");
assert(!dualTags.some((t) => t[0].indexOf("单脚") >= 0 && t[1]), "双脚模式下单脚 MODE_BLE_24G 不能再标必需");
// 选单脚：反过来，单脚必需、两只双脚角色不再标必需
ctx.S.health = { required: ["MODE_BLE_24G_PIN"] };
const singleTags = requiredTags(ctx.colRoles());
assert(singleTags.some((t) => t[0].indexOf("单脚") >= 0 && t[1]), "单脚模式下 MODE_BLE_24G 应标必需");
assert(!singleTags.some((t) => t[0].indexOf("2.4G 模式开关") >= 0 && t[1]), "单脚模式下 MODE_24G 不应标必需");
ctx.S.health = null;
ctx.S.roleQuery = "";

// 5) 界面无推荐配置导向
assert(!/一键按推荐配置/.test(code), "app.js 仍有「一键按推荐配置」入口");
assert(!/推荐 P/.test(code), "app.js 仍有「推荐 Pxx」字样");
assert(!/reco-badge/.test(html), "index.html 仍有推荐徽章");

console.log("PASS 约束栏全量可见 + 网络名搜索 + 需求组覆盖 " + reachable.size + " 角色 + 必需标签跟随板型 + 无推荐导向");
