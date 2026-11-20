/* 回归检查：
   1) 点「浏览」选择输出目录后，底部「下一步：设置板型」按钮必须立即高亮；
   2) Windows 路径归一：D:\work 与 D:\\work 等价，UNC 的 \\ 前缀保留。
   用法：node scripts/check_web_browseout.js
*/
"use strict";

const fs = require("fs");
const vm = require("vm");
const path = require("path");

const appPath = path.join(__dirname, "..", "web", "app.js");
const code = fs.readFileSync(appPath, "utf8");

function mkEl() {
  return {
    value: "", innerHTML: "", textContent: "", className: "", disabled: false,
    classList: { add() {}, remove() {}, contains() { return false; } },
    addEventListener() {}, setAttribute() {}, getAttribute() { return "dark"; },
  };
}
const els = {};
function el(id) { return els[id] || (els[id] = mkEl()); }

const document = {
  documentElement: mkEl(),
  getElementById: el,
  addEventListener() {},
  querySelector() { return null; },
};
const localStorage = {
  _d: {},
  getItem(k) { return Object.prototype.hasOwnProperty.call(this._d, k) ? this._d[k] : null; },
  setItem(k, v) { this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; },
};
const CHOSEN = "D:\\work"; // 字面 D:\work（单个反斜杠，正是文件对话框返回的形式）
const window = {
  matchMedia() { return { matches: false }; },
  addEventListener() {},
  pywebview: { api: { choose_folder: async function () { return CHOSEN; } } },
};

const ctx = {
  console, setTimeout, clearTimeout, document, localStorage, window,
  JSON, Math, String, Number, Object, Array, RegExp, Date, parseInt, parseFloat, isNaN,
};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(code, ctx, { filename: "app.js" });

function assert(cond, msg) { if (!cond) throw new Error(msg); }

(async function () {
  ctx.S.route = "new";
  ctx.S.step = 1;
  ctx.S.form = { name: "MyMouse", id: "0x0457", customer: "BYC", version: "1", out: "" };
  el("f-name").value = "MyMouse";
  el("f-id").value = "0x0457";
  el("f-customer").value = "BYC";
  el("f-version").value = "1";
  el("f-out").value = "";

  ctx.renderMain();
  ctx.renderAction();
  assert(el("btn-next").disabled === true, "输出目录为空时按钮应禁用");

  await ctx.browseOut();

  assert(el("f-out").value === CHOSEN,
    "浏览回填的 input 值应为 " + CHOSEN + "，实际 " + el("f-out").value);
  assert(ctx.S.form.out === CHOSEN, "S.form.out 未与浏览结果同步");
  assert(el("btn-next").disabled === false,
    "浏览选择路径后按钮仍被禁用（browseOut 未刷新底部按钮）");

  const n1 = ctx.normalizeDir("D:\\work");
  const n2 = ctx.normalizeDir("D:\\\\work");
  const n3 = ctx.normalizeDir("D:/work/");
  const n4 = ctx.normalizeDir("\\\\server\\share");
  assert(n1 === CHOSEN && n2 === CHOSEN && n3 === CHOSEN,
    "路径归一失败: " + JSON.stringify([n1, n2, n3]));
  assert(n4 === "\\\\server\\share", "UNC 前缀被破坏: " + n4);

  console.log("PASS browseOut 刷新按钮 + Windows 路径归一");
})().catch(function (e) {
  console.error("FAIL " + e.message);
  process.exit(1);
});
