"use strict";
/* OM6239 板级配置器 —— 单一状态机 + 按步骤调度的视图。
   所有校验/生成/事务都在后端 omcfg，本文件只提交 JSON 与展示结果。 */

var $ = function(id) { return document.getElementById(id); };

var STEPS = {
  new: [
    { t: "项目身份", d: "给工程一个名字和落点" },
    { t: "选料", d: "按原理图选中物料，未选不推导" },
    { t: "板型选项", d: "由物料推导，可微调" },
    { t: "功能插件", d: "由物料联动，随时可拔除" },
    { t: "引脚分配", d: "需求组 · 约束栏 · 脚位图" },
    { t: "校验与预览", d: "确认无误，再看改动" },
    { t: "生成应用", d: "写盘并交付可编译工程" }
  ],
  open: [
    { t: "选择 SDK", d: "打开并初始化已有工程" },
    { t: "检查与调整", d: "校验并微调脚位" },
    { t: "预览 diff", d: "这一步不写盘" },
    { t: "应用", d: "写盘，可回滚" }
  ]
};
var PIN_ROWS = [
  ["P00","P01","P02","P03","P04","P05","P06","P07"],
  ["P10","P11","P12","P13","P14","P15","P16","P17"],
  ["P20","P21","P22","P23","P24","P25","P26","P27"],
  ["P30","P31","P32","P33","P34","P35","P36","P37"]
];
var TIERS = ["硬约束 (1 脚)", "窄约束 (2–4 脚)", "中约束 (5–10 脚)", "宽约束 (11–23 脚)", "无约束 (24 脚，全 GPIO)"];
var FORM_KEY = "om_pinmux.blankwiz";
var RECENT_KEY = "om_pinmux.recent";

var S = {
  route: null, step: 1, maxDone: 0, view: "work",
  sdk: "", blankMode: false, needsInit: null,
  options: null, config: null, pinmap: null, issues: [],
  caps: { roles: {}, demand_groups: [], board_enums: {}, board_defaults: {} },
  pluginState: { plugins: [], enabled: [] },
  material: { categories: [], selected: {}, params: {}, effects: {} },
  board: {}, boardChoice: {}, health: null,
  form: { name: "", id: "", customer: "BYC", ble: "", version: "1", out: "" },
  assignments: {}, removedRoles: {}, protectedRoles: {},
  selectedRole: null, selectedGroup: null, focusPin: null, roleQuery: "",
  diff: null, previewed: false, applied: false, applyResult: null,
  confirming: false, applying: false, recent: [],
  busy: false, dirty: false, lastConfig: ""
};

/* ==================== 工具 ==================== */
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, function(c) {
    return { "&":"&amp;", "<":"&lt;", ">":"&gt;", "\"":"&quot;", "'":"&#39;" }[c];
  });
}
function toast(msg, isError) {
  var el = $("toast");
  if (!el) return;
  el.textContent = msg || "";
  el.className = isError ? "show error" : "show";
  clearTimeout(el._tm);
  el._tm = setTimeout(function() { el.className = ""; }, 2600);
}
function toggleTheme() {
  var cur = document.documentElement.getAttribute("data-theme") || "light";
  document.documentElement.setAttribute("data-theme", cur === "dark" ? "light" : "dark");
}
(function() {
  var saved = null;
  try { saved = localStorage.getItem("om_pinmux.theme"); } catch (e) {}
  var initial = saved || (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  document.documentElement.setAttribute("data-theme", initial);
})();
function showHelp() { $("modal").classList.remove("hidden"); }
function hideHelp() { $("modal").classList.add("hidden"); }
function api() { return window.pywebview && window.pywebview.api; }
async function call(method) {
  var a = api();
  if (!a || typeof a[method] !== "function") { toast("pywebview 尚未就绪或后端缺少 " + method + "()", true); return null; }
  var args = Array.prototype.slice.call(arguments, 1);
  try { return await a[method].apply(a, args); }
  catch (e) { toast(String(e), true); return null; }
}
function parseId(raw) {
  var s = String(raw || "").trim();
  if (!s) return 1;
  var n = /^0x/i.test(s) ? parseInt(s, 16) : parseInt(s, 10);
  return isNaN(n) ? null : n;
}
function roleMeta(mac) { return (S.caps.roles && S.caps.roles[mac]) || {}; }
function roleName(mac) { return roleMeta(mac).display_name || mac; }
function findMacByRoleId(rid) {
  for (var mac in S.caps.roles) {
    if (S.caps.roles[mac] && S.caps.roles[mac].role_id === rid) return mac;
  }
  return null;
}
function tierOf(n) {
  if (n === 1) return TIERS[0];
  if (n <= 4) return TIERS[1];
  if (n <= 10) return TIERS[2];
  if (n < 24) return TIERS[3];
  return TIERS[4];
}
function operations() { return STEPS[S.route] || []; }

/* 健康视图（前后端联动的核心）：
   - 「哪些角色必需」由后端按当前板型/选料/插件/源码硬依赖动态推导（S.health.required）。
   - 「哪些角色已配」必须按本地 S.assignments 实时算：配脚改动在写盘前只存在前端，
     后端 blank_status 是上一次落盘的快照，若直接读它的 assigned/missing，用户点了
     必需脚后健康卡与门禁仍停在旧值——这正是「前端不同步、下一步点不动」的根因。 */
function healthView() {
  var h = (S.health && S.health.ok) ? S.health : null;
  var roles = S.caps.roles || {};
  var assignedRoles = {};
  for (var pin in S.assignments) if (S.assignments[pin]) assignedRoles[S.assignments[pin]] = pin;
  var assigned = Object.keys(assignedRoles).length;

  // 必需集合：后端动态推导优先；状态未加载时才退回静态标记（不能用 v1 过滤掉真实网络）。
  var required = h && Array.isArray(h.required) ? h.required : (function() {
    var out = [];
    for (var mac in roles) if ((roles[mac] || {}).required) out.push(mac);
    return out;
  })();
  var missingDetail = h && Array.isArray(h.missing_detail) ? h.missing_detail : [];
  var missing = [];
  required.forEach(function(mac) {
    if (!assignedRoles[mac]) {
      var hint = null;
      for (var i = 0; i < missingDetail.length; i++) if (missingDetail[i].role === mac) hint = missingDetail[i];
      missing.push({
        role: mac,
        suggested: (hint && hint.suggested) || (roles[mac] || {}).suggested_pin || ""
      });
    }
  });

  var errors = h ? (h.validate_errors || 0)
    : (S.issues || []).filter(function(i) { return i.level === "error"; }).length;
  var warnings = h ? (h.validate_warnings || 0) : Math.max(0, (S.issues || []).length - errors);
  var conflicts = h ? ((h.conflicts || []).length) : 0;
  return {
    assigned: assigned,
    total: h ? (h.total_roles || 0) : Object.keys(roles).length,
    requiredCount: required.length,
    missingCount: missing.length,
    missingDetail: missing,
    conflicts: conflicts,
    errors: errors,
    warnings: warnings,
    // 与门禁 gate() 同判据：必需脚齐 + 无冲突。校验错误留给校验步骤展示，不在这里卡进度。
    complete: missing.length === 0 && conflicts === 0
  };
}

/* ==================== 数据加载 ==================== */
async function loadWorkspace(sdk) {
  S.sdk = sdk || "";
  if (S.sdk) pushRecent(S.sdk);
  var data = await call("load", S.sdk);
  if (!data) return false;
  if (data.needs_init) {
    S.needsInit = data;
    return false;
  }
  S.needsInit = null;
  if (data.error) { toast(data.hint ? data.error + "；" + data.hint : data.error, true); return false; }

  S.config = data;
  S.pinmap = data.pinmap || { package: [], internal: [], unassigned: [] };
  S.issues = data.issues || [];
  S.assignments = {};
  (S.pinmap.package || []).forEach(function(row) {
    (row.assigned || []).forEach(function(r) { S.assignments[row.name] = r; });
  });
  S.protectedRoles = {};
  (S.pinmap.protected_roles || []).forEach(function(r) { S.protectedRoles[r] = true; });
  S.removedRoles = {};

  var caps = await call("role_capabilities");
  var roles = (caps && caps.roles) || {};
  var groups = (caps && caps.demand_groups) || [];
  var enums = (S.options && S.options.board_enums) || (caps && caps.board_enums) || {};
  var defaults = (S.options && S.options.board_defaults) || (caps && caps.board_defaults) || {};
  S.caps = { roles: roles, demand_groups: groups, board_enums: enums, board_defaults: defaults };

  var pst = await call("plugin_status", S.sdk);
  var plugins = [], enabled = [];
  if (pst && pst.ok) {
    if (pst.roles) S.caps.roles = pst.roles;
    if (pst.demand_groups) S.caps.demand_groups = pst.demand_groups;
    plugins = pst.plugins || [];
    enabled = pst.enabled || [];
  }
  S.pluginState = { plugins: plugins, enabled: enabled };

  if (api() && typeof api().blank_status === "function") {
    var st = await call("blank_status", S.sdk);
    S.health = st && st.ok ? st : null;
    if (S.health && S.health.board) S.board = S.health.board;
  }
  if (api() && typeof api().material_status === "function") {
    var ms = await call("material_status", S.sdk);
    if (ms && ms.ok) {
      S.material.categories = ms.categories || S.material.categories;
      S.material.selected = ms.selected || {};
      S.material.params = ms.params || {};
      S.material.effects = ms.effects || {};
    }
  }
  S.dirty = false;
  return true;
}

async function refreshHealth() {
  if (!S.sdk) return;
  var st = await call("blank_status", S.sdk);
  if (st && st.ok) {
    S.health = st; S.board = st.board || S.board;
    // 工程身份回显：缓存里没填蓝牙名时，用工程当前值（第一个广播名）填表单。
    var ident = st.identity || {};
    if (ident.ble_names && ident.ble_names.length && !S.form.ble) S.form.ble = ident.ble_names[0];
    if (ident.customer) S.form.customer = ident.customer;
  }
}

async function initOptions() {
  if (S.options) return;
  var o = await call("blank_options");
  if (!o || !o.ok) return;
  S.options = o;
  S.caps.board_enums = o.board_enums || S.caps.board_enums;
  S.caps.board_defaults = o.board_defaults || S.caps.board_defaults;
  S.boardChoice = Object.assign({}, S.caps.board_defaults || {});
  if (o.material_categories) S.material.categories = o.material_categories;
  loadFormCache();
}

function jsAttr(s) { return esc(s).replace(/\\/g, "\\\\").replace(/'/g, "\\'"); }
function loadRecent() {
  var list = [];
  try {
    var raw = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    if (Array.isArray(raw)) list = raw.filter(function(x) { return typeof x === "string" && x; });
  } catch (e) {}
  var old = "";
  try { old = localStorage.getItem("omcfg.sdk") || ""; } catch (e) {}
  if (old && list.indexOf(old) < 0) list.unshift(old);
  S.recent = list.slice(0, 5);
  return S.recent;
}
function pushRecent(sdk) {
  if (!sdk) return;
  var list = loadRecent().filter(function(x) { return x !== sdk; });
  list.unshift(sdk);
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 5))); } catch (e) {}
  try { localStorage.setItem("omcfg.sdk", sdk); } catch (e) {}
  S.recent = list.slice(0, 5);
}
function removeRecent(sdk) {
  var old = "";
  try { old = localStorage.getItem("omcfg.sdk") || ""; } catch (e) {}
  if (old === sdk) { try { localStorage.removeItem("omcfg.sdk"); } catch (e) {} }
  var list = loadRecent().filter(function(x) { return x !== sdk; });
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(list)); } catch (e) {}
  S.recent = list;
  renderRecent();
  if (S.route === "open" && S.step === 1) renderMain();
  toast("已从最近工程移除");
}
function loadFormCache() {
  try {
    var s = JSON.parse(localStorage.getItem(FORM_KEY) || "{}");
    S.form.name = s.name || "";
    S.form.id = s.id || "";
    S.form.customer = s.customer || "BYC";
    S.form.ble = s.ble || "";
    S.form.version = s.version || "1";
    S.form.out = s.out || "";
  } catch (e) {}
  // 缓存回填后输入框的值与按钮判定都依赖 S.form，
  // 这里同步一次渲染，避免「框里有值但下一步按钮灰着」。
  if (S.route === "new" && S.step === 1 && $("f-out")) {
    renderMain(); renderAction();
  }
}
function saveFormCache() {
  try { localStorage.setItem(FORM_KEY, JSON.stringify(S.form)); } catch (e) {}
}

/* ==================== 渲染框架 ==================== */
function render() {
  if (S.view === "success") { renderSuccess(); return; }
  renderTop(); renderStepper(); renderAside(); renderMain(); renderAction();
}
function renderTop() {
  $("route-name").textContent = S.route === "new" ? "从空白新建" : "打开已有工程";
  $("ctx-name").textContent = (S.route === "new" ? S.form.name : (S.board && S.board.name)) || (S.sdk ? "已打开工程" : "未命名工程");
  var wrap = $("ctx-sdk-wrap"), input = $("sdk");
  if (S.sdk) {
    wrap.classList.remove("hidden");
    if (input && input.value !== S.sdk) input.value = S.sdk;
  } else {
    wrap.classList.add("hidden");
  }
  var tag = $("dirty-tag");
  tag.className = S.dirty ? "tag warn" : "tag ok";
  tag.textContent = S.dirty ? "未保存" : "已保存";
}
function renderStepper() {
  var st = operations(), h = "";
  for (var i = 0; i < st.length; i++) {
    var n = i + 1;
    var cls = n < S.step || n <= S.maxDone ? "done" : (n === S.step ? "current" : "locked");
    var mark = (n <= S.maxDone && n !== S.step) ? "✓" : String(n);
    h += '<button class="step-item ' + cls + '" onclick="gotoStep(' + n + ')" ' + (cls === "locked" ? "disabled" : "") + '>' +
      '<span class="step-line"></span><span class="step-num">' + mark + '</span>' +
      '<span class="step-tx"><span class="t">' + esc(st[i].t) + '</span><span class="d">' + esc(st[i].d) + '</span></span></button>';
  }
  $("step-list").innerHTML = h;
  $("side-foot").innerHTML = S.route === "new"
    ? "主线：身份 → 选料 → 板型 → 插件 → 配脚 → 校验 → 生成。<br>可随时回退到已完成步骤。"
    : "主线：打开 → 调整 → 预览 → 应用。<br>严格校验模式，保存前检查冲突。";
}
function renderAside() {
  var h = healthView();
  var c = 2 * Math.PI * 32, off = c * (1 - h.assigned / (h.total || 1));
  var color = h.complete ? "var(--ok)" : "var(--brand)";
  var s = '<div class="health-h"><b>工程健康</b><span class="tag ' + (S.blankMode ? "info" : "neutral") + '">' + (S.blankMode ? "草稿" : "已有工程") + '</span></div>';
  s += '<div class="ring-wrap"><div class="ring"><svg width="74" height="74" viewBox="0 0 74 74">' +
    '<circle cx="37" cy="37" r="32" fill="none" stroke="var(--line)" stroke-width="7"/>' +
    '<circle cx="37" cy="37" r="32" fill="none" stroke="' + color + '" stroke-width="7" stroke-linecap="round" stroke-dasharray="' + c.toFixed(1) + '" stroke-dashoffset="' + off.toFixed(1) + '"/>' +
    '</svg><div class="pct">' + (h.total ? Math.round(h.assigned / h.total * 100) : 0) + '%</div></div>' +
    '<div class="ring-lbl"><b>已配 ' + h.assigned + ' / ' + h.total + '</b>共 ' + h.requiredCount + ' 个必需角色<br>' + (h.complete ? "配置已完整" : "继续补齐即可生成") + '</div></div>';
  s += '<div class="hrow link" onclick="jumpToPin()"><span class="k">已配脚</span><span class="v">' + h.assigned + ' / ' + h.total + '</span></div>';
  s += '<div class="hrow link" onclick="jumpToPin()"><span class="k">缺必需</span><span class="v ' + (h.missingCount ? "warn" : "ok") + '">' + h.missingCount + '</span></div>';
  s += '<div class="hrow"><span class="k">脚位冲突</span><span class="v ' + (h.conflicts ? "err" : "ok") + '">' + h.conflicts + '</span></div>';
  s += '<div class="hrow"><span class="k">校验错误</span><span class="v ' + (h.errors ? "err" : "ok") + '">' + h.errors + '</span></div>';
  s += '<div class="health-div"></div><div class="aside-lbl">功能插件</div>';
  var enabledPlugins = S.pluginState.enabled || [];
  if (!(S.pluginState.plugins || []).length) {
    s += '<div class="plugin-mini off"><span class="bullet"></span>无可用插件</div>';
  }
  (S.pluginState.plugins || []).forEach(function(p) {
    var on = enabledPlugins.indexOf(p.id) >= 0;
    var n = (p.unlock_roles || p.roles || []).length;
    s += '<div class="plugin-mini ' + (on ? "" : "off") + '"><span class="bullet"></span>' +
      esc(p.display_name || p.id) + ' · ' + (on ? "已启用 (+" + n + " 角色)" : "未启用") + '</div>';
  });
  s += '<div class="gen-box ' + (h.complete ? "ok" : "") + '"><div class="l">可生成</div>' +
    '<div class="g ' + (h.complete ? "ok" : "warn") + '">' + (h.complete ? "是" : "否") + '</div>' +
    '<div class="hint">' + (h.complete ? "必需脚齐全、无冲突，可进入「校验与预览」。" : "补齐 " + h.missingCount + " 个必需脚后即可进入「校验与预览」。") + '</div></div>';
  var help = helpForStep();
  s += '<div class="help-box"><h5>' + esc(help[0]) + '</h5><p>' + esc(help[1]) + '</p></div>';
  $("aside").innerHTML = s;
}
// 必需角色数跟随后端动态推导（板型/选料/插件），不再读 options.json 静态标记。
function countRequired() { return healthView().requiredCount; }
function helpForStep() {
  if (S.route === "new") {
    return [
      ["这一步在做什么", "给新工程一个身份与落点。工具会从内置 KC536 干净骨架复制一份，此时引脚全空 —— 这是正常状态。"],
      ["为什么先选料", "软件工程师拿到的是硬件画好的原理图，引脚归谁用由硬件决定。光电/灯带/充电按实物选型号；RGB 数量、拨杆段数、蓝牙通道按原理图填。所有项默认未指定，不选就不推导任何角色。"],
      ["板型由物料推导", "选料后板型已设好初值，这里只做微调。例如四线传感器要求 SPI 四脚；双脚模式要求 MODE_24G/BLE 成对。"],
      ["插件由物料联动", "灯带型号=WS2812 会自动启用 LEDC 插件。也可手动勾选或拔除；勾选即注入文件、解锁角色、腾让冲突脚。"],
      ["三个视图，同一批角色", "需求组按功能分组，约束栏按合法脚数分档，脚位图按物理位置摆放。选中其一，另外两处同步高亮。点「? 帮助」看完整说明。"],
      ["预览不写盘", "diff 只展示「如果应用会变成什么样」。确认后才进入下一步真正写入，且可用 manifest 回滚。"],
      ["最后一步", "确认摘要后写盘。写入走事务：先备份再落盘，失败自动回滚。"]
    ][S.step - 1] || ["下一步做什么", "底部主按钮永远只有一个，并写明下一步动作。"];
  }
  return [
    ["选择已有工程", "填入 SDK 根目录。若缺 OMCFG 标记会引导初始化，或从 user_config.h/.c 推导配置初稿。"],
    ["同一套工作区", "三视图与新建路径完全共用；这里走严格校验，保存前会检查必需脚与冲突。"],
    ["预览不写盘", "diff 只展示将变更的文件，不写入任何内容。"],
    ["最后一步", "确认后写盘，事务备份可用 manifest 回滚。"]
  ][S.step - 1] || ["下一步做什么", "底部主按钮永远只有一个。"];
}
function gate() {
  if (S.route === "new") {
    if (S.step === 1) {
      if (!S.form.name.trim()) return "请填写「项目名」后才能继续";
      if (!S.form.out.trim()) return "请填写「输出根目录」后才能继续";
      if (parseId(S.form.id) === null) return "项目号格式不对（0x0457 或十进制）";
    }
    if (S.step === 5) {
      var h = healthView();
      if (h.conflicts) return "存在 " + h.conflicts + " 处脚位冲突，请先在脚位图化解";
      if (h.missingCount) return "还差 " + h.missingCount + " 个必需脚，补齐后才能进入校验";
    }
    if (S.step === 6 && !S.previewed) return "请先点「生成预览」查看将变更的文件";
  } else {
    if (S.step === 1) {
      if (!S.sdk.trim()) return "请先填写或选择 SDK 根目录";
      if (S.needsInit) return "工程缺少 OMCFG 标记，请先在本页完成初始化";
    }
    if (S.step === 2) {
      var h2 = healthView();
      if (h2.conflicts) return "存在 " + h2.conflicts + " 处脚位冲突";
      if (h2.missingCount) return "还差 " + h2.missingCount + " 个必需脚";
    }
    if (S.step === 3 && !S.previewed) return "请先点「生成预览」查看将变更的文件";
  }
  return null;
}
function renderAction() {
  var st = operations(), g = gate(), last = S.step === st.length;
  $("btn-prev").disabled = S.step === 1;
  $("btn-save").disabled = !(S.sdk && (S.route === "new" ? S.step >= 5 : S.step === 2));
  var labelsNew = [
    "下一步：选料 →", "下一步：设置板型 →", "下一步：选择插件 →",
    "下一步：分配引脚 →", "下一步：校验与预览 →", "下一步：生成应用 →", "生成工程（写盘）"
  ];
  var labelsOpen = ["下一步：检查与调整 →", "下一步：预览 diff →", "下一步：应用 →", "应用改动（写盘）"];
  var btn = $("btn-next");
  btn.onclick = nextStep;
  btn.textContent = S.route === "new" ? labelsNew[S.step - 1] : labelsOpen[S.step - 1];
  var waiting = last && S.confirming;
  btn.disabled = !!g || S.busy || waiting;
  if (waiting) btn.textContent = "等待确认…";
  $("cta-sub").textContent = waiting ? "已到写盘步骤，请在上方确认" : (g ? "" :
    (last ? "确认后写入文件，可用 manifest 回滚" : st[Math.min(S.step, st.length - 1)].t + " 完成后进入下一步"));
  $("gate-wrap").innerHTML = waiting
    ? '<div class="gate-msg">⚠ 请在上方确认条点「确认写入」或「取消」</div>'
    : (g ? '<div class="gate-msg">⚠ ' + esc(g) + '</div>' : "");
}

/* ==================== 步骤视图 ==================== */
function renderMain() {
  var body = "";
  if (S.route === "new") {
    if (S.step === 1) body = viewIdentity();
    else if (S.step === 2) body = viewMaterial();
    else if (S.step === 3) body = viewBoard();
    else if (S.step === 4) body = viewPlugin();
    else if (S.step === 5) body = viewPins();
    else if (S.step === 6) body = viewValidate();
    else if (S.step === 7) body = viewApply();
  } else {
    if (S.step === 1) body = viewOpenSdk();
    else if (S.step === 2) body = viewPins();
    else if (S.step === 3) body = viewPreview();
    else if (S.step === 4) body = viewApply();
  }
  var st = operations()[S.step - 1];
  $("main").innerHTML = '<div class="stage-head"><div class="stage-eyebrow">第 ' + S.step + ' 步 / 共 ' + operations().length + ' 步</div>' +
    '<h2 class="stage-title">' + esc(st.t) + '</h2><p class="stage-desc">' + esc(stageDesc()) + '</p></div>' + body;
}
function stageDesc() {
  var d = S.route === "new" ? [
    "给工程一个名字与输出位置，工具会从 KC536 干净骨架复制一份空白工程。",
    "按原理图选物料：关键器件（光电/灯带/充电）选型号，数量与段数自己填。默认都是未指定，只有选中的才会推导角色与插件。",
    "板型由选料推导初值，可按原理图微调。不同的模式/灯效/滚轮选项决定哪些角色必须配脚。",
    "插件由选料联动（灯带→LEDC），也可手动勾选或拔除。勾选即注入文件、解锁角色、腾让冲突脚。",
    "用三种视图配同一批角色。先选需求组或角色，再在脚位图点绿格分配；改动会即时反映到右侧健康卡。",
    "确认没有错误，再查看「如果应用会改动什么」。预览阶段不会写入任何文件。",
    "最后一步写入生成文件。可回滚，写完后建议用 Keil 编译验证。"
  ] : [
    "填入已有 SDK 工程根目录；若缺 OMCFG 标记会引导初始化或从现状推导配置。",
    "检查现有配置并微调脚位，同一套三视图工作区，严格校验。",
    "查看将变更的文件与 diff，这一步不写盘。",
    "确认后写入文件，事务备份可用 manifest 回滚。"
  ];
  return d[S.step - 1] || "";
}

function field(label, key, ph, hint, full) {
  var id = "f-" + key;
  return '<div class="field' + (full ? " full" : "") + '"><label>' + esc(label) + '</label>' +
    '<input id="' + id + '" value="' + esc(S.form[key]) + '" placeholder="' + esc(ph) + '" oninput="syncForm()">' +
    (hint ? '<div class="fh">' + hint + '</div>' : '') + '</div>';
}
function viewOpenSdk() {
  var s = '<div class="info-strip"><div class="i">i</div><p><b>在顶部「SDK」输入框填入工程根目录并按回车</b>，或点下方「打开工程」按钮。工具读取 <span class="mono">projects/mouse_demo/project.omcfg</span>，配置随工程走。</p></div>';
  s += '<div class="section-title"><span class="n">1</span>打开工程</div>' +
    '<div class="row gap10 wrap mb-sm">' +
    '<button class="btn primary sm" onclick="initExisting()">打开工程 →</button>' +
    '<span class="muted tiny">当前：' + esc(S.sdk || "（未选择）") + '</span></div>';
  s += '<div class="section-title"><span class="n">2</span>最近工程</div><div class="recent-row">' + recentChips() + '</div>';
  s += '<div class="section-title"><span class="n">3</span>初始化引导（仅当缺 OMCFG 标记时出现）</div>';
  if (S.needsInit) {
    var ni = S.needsInit;
    var opts = (ni.configs || []).map(function(c) {
      return '<option value="' + esc(c.path) + '">' + esc(c.name) + (c.suggested ? "（自动匹配）" : "") + '</option>';
    }).join("");
    s += '<div class="issue warn"><div class="ic">!</div><div class="tx">' +
      '<b>未检测到 OMCFG / USER CODE 标记块</b>' +
      '<p>' + esc(ni.hint || "选择一份配置初始化，或从工程现状推导初稿。") +
      (ni.missing && ni.missing.length ? '<br>缺少：' + esc(ni.missing.join("、")) : '') + '</p>' +
      '<div class="input-row mt-sm maxw540">' +
      '<input id="f-config" list="cfg-options" value="' + esc(ni.prefill || "") + '" placeholder="configs\\KC536.omcfg">' +
      '<datalist id="cfg-options">' + opts + '</datalist></div>' +
      '<div class="row gap8 wrap mt-sm">' +
      '<button class="btn sm primary" onclick="doInitialize(document.getElementById(\'f-config\').value.trim())">初始化</button>' +
      '<button class="btn sm" onclick="doInitializeDerived()">从工程现状生成配置</button></div></div></div>';
  } else if (S.sdk) {
    s += '<div class="empty-ok">✓ 已检测到 OMCFG / USER CODE 标记，可直接进入下一步</div>';
  } else {
    s += '<div class="info-strip"><div class="i">i</div><p>选择 SDK 后，这里会显示标记检测结果；缺标记时给出可操作的初始化入口。</p></div>';
  }
  return s;
}
function viewIdentity() {
  return '<div class="form-grid">' +
    field("项目名", "name", "MyMouse", "用于目录名与工程标识", false) +
    field("项目号", "id", "0x0457（留空=1）", "十六进制或十进制", false) +
    field("客户名", "customer", "BYC", "写进 iCONSUMER_NAME", false) +
    field("蓝牙名", "ble", "留空=自动生成，如 S205-BLE", "BLE 广播名；创建/应用后写进 mouse_name（≤28 字符）", false) +
    field("版本", "version", "1", "", false) +
    '<div class="field full"><label>输出根目录</label><div class="input-row">' +
    '<input id="f-out" value="' + esc(S.form.out) + '" placeholder="E:\\work" oninput="syncForm()">' +
    '<button class="btn" onclick="browseOut()">浏览…</button></div>' +
    '<div class="fh">工程建在 &lt;输出根目录&gt;\\&lt;项目名&gt;，目标目录必须不存在</div></div></div>' +
    '<div class="info-strip"><div class="i">i</div><p><b>空白起步是刻意设计</b>：创建后已配 0 个脚、缺若干必需脚，这是正常状态。后续每配一个角色，健康卡的完成度就会上涨 —— 你随时知道还差多少。</p></div>' +
    (S.sdk ? '<div class="info-strip"><div class="i">✓</div><p>工程已创建：<span class="mono">' + esc(S.sdk) + '</span>。改客户名/蓝牙名后点「应用身份」写进工程与源码；项目名/目录不随这里变化。</p>' +
      '<button class="btn sm" onclick="applyIdentity()">应用身份（客户名 / 蓝牙名）</button></div>' : "");
}
async function applyIdentity() {
  if (!S.sdk) { toast("请先创建或打开工程", true); return; }
  syncForm();
  var r = await call("blank_set_identity", S.sdk, {
    customer: S.form.customer || "BYC",
    ble_names: S.form.ble ? [S.form.ble.trim()] : null
  });
  if (!r || !r.ok) { toast("身份保存失败：" + ((r && r.error) || "未知"), true); return; }
  toast("身份已保存；BLE 广播名已同步到源码" + (r.ble_names && r.ble_names.length ? "（" + r.ble_names.join(" / ") + "）" : ""));
}
function syncForm() {
  ["name","id","customer","ble","version","out"].forEach(function(k) {
    var el = $("f-" + k);
    if (el) S.form[k] = el.value;
  });
  S.dirty = true;
  saveFormCache();
  renderTop(); renderAction();
}
async function browseOut() {
  if (!api()) { toast("pywebview 未就绪", true); return; }
  var folder = await call("choose_folder", S.form.out);
  if (!folder) return;
  var el = $("f-out");
  if (el) el.value = folder;
  // 走 syncForm 统一回写 S.form / 缓存 / 顶部与底部按钮；
  // 只改 input.value 不会触发 oninput，底部「下一步」按钮会一直保持禁用。
  syncForm();
}

/* ---- 选料步骤：只记录用户显式选择；统计只是内部资料，不进入界面 ---- */
function matOptionButtons(c) {
  var sel = S.material.selected || {};
  var cur = sel[c.id];
  var h = '<div class="mat-opts">';
  (c.options || []).forEach(function(o) {
    var on = o.id === cur;
    h += '<button class="mat-opt ' + (on ? "on" : "") + '" onclick="pickMaterial(\'' + esc(c.id) + '\',\'' + esc(o.id) + '\')">' +
      '<span class="mo-dot"></span><span>' + esc(o.display_name) + '</span></button>';
  });
  h += '</div>';
  if (cur) {
    h += '<button class="mat-clear" onclick="pickMaterial(\'' + esc(c.id) + '\',\'\')">清除选择（不改其它物料）</button>';
  }
  return h;
}
function matParamControl(p) {
  var par = S.material.params || {};
  var val = par[p.id];
  var fn = 'setMaterialParam(\'' + esc(p.id) + '\',this.value)';
  // 整数：完全自由填写，只用 min/max 兜住明显非法值，不限制成几个统计取值。
  if (p.type === "int") {
    var min = p.min === undefined ? 1 : p.min;
    var max = p.max === undefined ? 64 : p.max;
    return '<div class="mat-param"><label>' + esc(p.display_name) + '</label>' +
      '<input class="mat-num" type="number" min="' + esc(min) + '" max="' + esc(max) + '" ' +
      'placeholder="按原理图填写" value="' + (val === undefined ? "" : esc(val)) + '" onchange="' + fn + '">' +
      '<small>可填 ' + esc(min) + '~' + esc(max) + ' 任意整数，留空表示沿用工程值</small></div>';
  }
  var labels = p.labels || {};
  var h = '<div class="mat-param"><label>' + esc(p.display_name) + '</label><select onchange="' + fn + '">' +
    '<option value=""' + (val === undefined ? " selected" : "") + '>未指定（沿用工程值）</option>';
  (p.allowed || []).forEach(function(a) {
    var label = labels[String(a)] || String(a);
    h += '<option value="' + esc(a) + '"' + (String(a) === String(val) ? " selected" : "") + '>' + esc(label) + '</option>';
  });
  return h + '</select></div>';
}
function viewMaterial() {
  var cats = S.material.categories || [];
  if (!cats.length) {
    return '<div class="info-strip"><div class="i">i</div><p>未读取到物料目录。请确认后端 <span class="mono">omcfg/data/material_catalog.json</span> 存在。</p></div>';
  }
  var s = '<div class="concept"><b>按原理图选物料，工具只推导你显式选中的东西</b>：' +
    '<div class="chain"><span>选中物料型号</span><i>推导</i><span>对应需求角色 + 插件</span><i>再到</i><span>脚位图自行配脚</span></div>' +
    '所有分类默认「未指定」，不选就不会新增或移除任何角色；统计资料不会变成你的配置。</div>';

  var keyCats = cats.filter(function(c) { return c.key; });
  var paramCats = cats.filter(function(c) { return !c.key; });

  s += '<div class="mat-section-h">关键物料 · 按实物选型号</div><div class="mat-grid">';
  keyCats.forEach(function(c) {
    s += '<div class="mat-card"><div class="mat-head"><b>' + esc(c.display_name) + '</b><span class="tag info">关键</span></div>' +
      '<p class="mat-note">' + esc(c.note || "") + '</p>' + matOptionButtons(c) + '</div>';
  });
  s += '</div>';

  s += '<div class="mat-section-h">其余参数 · 按原理图填写</div><div class="mat-grid">';
  paramCats.forEach(function(c) {
    s += '<div class="mat-card"><div class="mat-head"><b>' + esc(c.display_name) + '</b><span class="tag neutral">按需</span></div>' +
      '<p class="mat-note">' + esc(c.note || "") + '</p>';
    if ((c.options || []).length) {
      s += matOptionButtons(c);
    } else {
      (c.params || []).forEach(function(p) { s += matParamControl(p); });
    }
    s += '</div>';
  });
  s += '</div>';

  s += '<div class="info-strip"><div class="i">i</div><p>选料写入 <span class="mono">project.materials</span>，只影响你选中的项：例如选 <b>S203 四线</b> 才出现 SPI 四脚，选 <b>WS2812 灯带</b> 才启用 LEDC 插件。' +
    '<b>每只灯/按键的极性不在这里</b>：它由原理图接法决定，请在「板型选项」步骤按 R/G/B 逐只选择，选料不会自动改。</p></div>';
  return s;
}
async function pickMaterial(catId, optionId) {
  if (!S.sdk) { toast("请先完成项目身份", true); return; }
  await applyMaterialSelection(
    Object.assign({}, S.material.selected, (function() { var o = {}; o[catId] = optionId; return o; })()),
    S.material.params
  );
}
async function setMaterialParam(paramId, value) {
  if (!S.sdk) { toast("请先完成项目身份", true); return; }
  var p = Object.assign({}, S.material.params);
  if (value === "" || value === null) delete p[paramId];
  else p[paramId] = value;
  await applyMaterialSelection(S.material.selected, p);
}
async function applyMaterialSelection(selected, params) {
  var r = await call("material_apply", S.sdk, selected, params);
  if (!r || !r.ok) { toast("选料应用失败：" + ((r && r.error) || "未知"), true); return; }
  await loadWorkspace(S.sdk);
  if (r.effects) S.material.effects = r.effects;
  // 选料改了 board，同步板型页的选择初值。
  if (S.health && S.health.board) S.boardChoice = Object.assign({}, S.health.board);
  render();
  toast(r.message || "选料已应用");
}

function viewBoard() {
  var d = S.boardChoice || {};
  function opt(title, sub, key, items, effect) {
    var h = '<div class="opt-card"><h4>' + title + '</h4><p class="sub">' + sub + '</p><div class="seg">';
    items.forEach(function(it) {
      h += '<button class="' + (d[key] === it[0] ? "on" : "") + '" onclick="setBoardChoice(\'' + key + '\',\'' + it[0] + '\')">' +
        esc(it[1]) + '<small>' + esc(it[2] || "") + '</small></button>';
    });
    return h + '</div><div class="effect">↳ ' + esc(effect) + '</div></div>';
  }
  var modes = (S.caps.board_enums.mode_pins || ["single","dual","wired"]).map(function(v) {
    return [v, { single:"单模式脚", dual:"双脚模式", wired:"有线" }[v] || v, v];
  });
  var logos = (S.caps.board_enums.logo || ["rgb","ledc","none"]).map(function(v) {
    return [v, { rgb:"RGB 三色灯", ledc:"灯带", none:"无灯效" }[v] || v, v];
  });
  var wheels = (S.caps.board_enums.wheel || ["ENCODER_PINMUX_SEL_IO_00_01","ENCODER_PINMUX_SEL_IO_20_21","SOFT_GPIO"]).map(function(v) {
    return [v, { ENCODER_PINMUX_SEL_IO_00_01:"编码器 P00/P01", ENCODER_PINMUX_SEL_IO_20_21:"编码器 P20/P21", SOFT_GPIO:"软件 GPIO（可配 P24/P25）" }[v] || v, v];
  });
  var leds24 = (S.caps.board_enums.mode_24g_led || ["R","G","B"]).map(function(v) {
    return [v, { R:"红灯 R（KC536）", G:"绿灯 G（S205）", B:"蓝灯 B" }[v] || v, ""];
  });
  var indicators = (S.caps.board_enums.led_indicator || ["full","hint_only"]).map(function(v) {
    return [v, { full:"原版灯效", hint_only:"仅指示灯" }[v] || v, ""];
  });
  var modeEffect = d.mode_pins === "dual" ? "当前：MODE_24G / MODE_BLE 成对必需；拨杆三段（2.4G / BAT / BT）"
    : d.mode_pins === "single" ? "当前：MODE_BLE_24G 单脚必需"
    : d.mode_pins === "wired" ? "当前：有线模式，不额外要求模式脚"
    : "选中后角色出现在约束栏，必需项计入「缺必需」。";
  var led24Effect = "当前 2.4G 指示灯复用 " + (d.mode_24g_led || "R") + " 灯（LED_MODE_" + (d.mode_24g_led || "R") + "_PIN）；" +
    "由硬件决定，KC536 是红灯、S205 是 P05 绿灯。BT1 固定复用 G、BT0 固定复用 B。";
  var indicatorEffect = d.led_indicator === "hint_only"
    ? "当前：仅指示灯 —— mode_led_hint 独占模式灯，底层 PWM 点灯（开机/连接/低电闪灯）编译期排除，不串扰"
    : "当前：原版灯效 —— 保留全部底层点灯调用（KC536 默认）。若出现切换瞬间串灯，选「仅指示灯」";
  return opt("模式脚", "按原理图实际接法选；双脚=三段拨杆（2.4G/BAT/BT），只影响哪些模式角色必需", "mode_pins", modes, modeEffect) +
    opt("2.4G 指示灯", "2.4G 模式亮哪只物理模式灯，由原理图决定；工具不替你选", "mode_24g_led", leds24, led24Effect) +
    opt("指示灯", "模式指示灯方案：三色 LED / 灯带 / 无", "logo", logos, "RGB 模式要求 LED_R/G/B 三脚；灯带模式走 LEDC，底层 RGB 点灯编译期排除，不再要求这三脚。具体灯效由下面的「指示灯策略」决定。") +
    opt("指示灯策略", "原版灯效 vs 仅指示灯；只改生成语义，不改脚位", "led_indicator", indicators, indicatorEffect) +
    opt("滚轮编码器", "硬件 pinmux 组合；P24/P25 请选软件 GPIO 后到配脚步骤自行指定", "wheel", wheels, "WHEEL_A/B 必须成对配置；P24/P25 是合法脚，工具不替你选。") +
    viewPolaritySection() +
    '<div class="info-strip"><div class="i">i</div><p>板型选项<b>不直接改脚位</b>，只改「哪些角色必需」与生成语义。脚位请在你自己的工程里按原理图逐项指定，工具不会替你决定某只脚给谁用。</p></div>';
}

/* 逐脚极性：极性是每只灯/每个按键各自的电气属性，不是全板一个值。
   列表按当前已配脚动态生成（板上有几只就列几行），名字带 R/G/B，
   完全由工程师按原理图逐只指定；工具不按数量或统计统一分配。 */
function viewPolaritySection() {
  var roles = (S.health && S.health.polarity_roles) || [];
  var pmap = (S.health && S.health.polarity_map) || {};
  var h = '<div class="opt-card pol-card"><h4>逐脚极性</h4>' +
    '<p class="sub">按原理图逐只指定，板上有几只就列几行；不统一、不自动分配</p>';
  if (!roles.length) {
    h += '<div class="pol-empty">当前还没有任何已配脚的灯 / 按键。请先在「配脚」步骤分配脚位，这里会按实际脚位列出极性。</div>';
  } else {
    roles.forEach(function(r) {
      var cur = r.effective || pmap[r.role] || "active_low";
      var hi = cur === "active_high";
      var kindLabel = r.led ? "点亮" : "有效";
      h += '<div class="pol-row"><div class="pol-meta"><b>' + esc(r.display) + '</b>' +
        '<span class="mono">' + esc(r.role) + '</span><span class="tag neutral">' + esc(r.pin) + '</span></div>' +
        '<div class="seg pol-seg">' +
          '<button class="' + (!hi ? "on" : "") + '" onclick="setPolarity(\'' + r.role + '\',\'active_low\')">' +
            '低电平' + kindLabel + '<small>另一端接 VCC / 上拉</small></button>' +
          '<button class="' + (hi ? "on" : "") + '" onclick="setPolarity(\'' + r.role + '\',\'active_high\')">' +
            '高电平' + kindLabel + '<small>另一端接地 / 下拉</small></button>' +
        '</div></div>';
    });
  }
  h += '<div class="effect">↳ 极性写进每只脚，生成时各用各的；改数量不会动这里</div></div>';
  return h;
}
async function setPolarity(role, value) {
  if (!S.sdk) { toast("请先完成项目身份", true); return; }
  var r = await call("blank_set_polarity", S.sdk, (function() { var o = {}; o[role] = value; return o; })());
  if (!r || !r.ok) { toast("极性保存失败：" + ((r && r.error) || "未知"), true); return; }
  await refreshHealth();
  renderMain();
  toast(role + " → " + (value === "active_high" ? "高电平有效" : "低电平有效"));
}
function setBoardChoice(key, value) {
  if (!S.sdk) { toast("请先完成项目身份", true); return; }
  var old = S.boardChoice[key];
  S.boardChoice[key] = value;
  renderMain();
  (async function() {
    var r = await call("blank_set_board", S.sdk, {
      mode_pins: S.boardChoice.mode_pins, logo: S.boardChoice.logo, wheel: S.boardChoice.wheel,
      mode_24g_led: S.boardChoice.mode_24g_led || "R",
      led_indicator: S.boardChoice.led_indicator || "full"
    });
    if (!r || !r.ok) {
      S.boardChoice[key] = old; render();
      toast("板型保存失败：" + ((r && r.error) || "未知"), true);
      return;
    }
    await refreshHealth();
    // 板型改了「哪些角色必需」，约束栏/需求组的必需标签也必须重渲染，不能只刷健康卡。
    render();
    toast("板型已更新：" + (r.message || ""));
  })();
}

function viewPlugin() {
  var p = null;
  (S.pluginState.plugins || []).forEach(function(x) { if (x.id === "ledc") p = x; });
  if (!p) return '<div class="info-strip"><div class="i">i</div><p>未读取到插件契约。请确认 omcfg/data/plugins.json 存在。</p></div>';
  var on = (S.pluginState.enabled || []).indexOf("ledc") >= 0;
  var re = (p.auto_reassign || [])[0];
  var s = '<div class="plugin-card ' + (on ? "on" : "") + '"><div class="plugin-head">' +
    '<button class="switch ' + (on ? "on" : "") + '" onclick="togglePlugin()" aria-label="切换插件"></button>' +
    '<div class="tx"><h4>' + esc(p.display_name || "灯带 LEDC") + ' <span class="tag ' + (on ? "ok" : "neutral") + '">' + (on ? "已启用" : "未启用") + '</span></h4>' +
    '<p>' + esc(p.note || "按需扩展灯带功能") + '</p></div></div>' +
    '<div class="effect-list"><h5>启用后将自动完成（来自插件契约）</h5><ul>' +
    '<li>注入 <b>' + (p.files || []).length + ' 个文件</b>：' + esc((p.files || []).join(" / ")) + '，并登记 Keil 工程</li>' +
    '<li>新增 <b>' + (p.unlock_roles || []).length + ' 个可配角色</b>：' + esc((p.unlock_roles || []).join(" / ")) + '</li>' +
    (re ? '<li>自动腾让 <b>' + esc(re.role) + '：' + esc(re.from) + ' → ' + esc(re.to) + '</b>（DIN 与 RGB 抢脚时）</li>' : "") +
    '<li>board.logo 设为 <b>' + esc((p.board_effect || {}).logo || "ledc") + '</b></li>' +
    '</ul></div><div class="plugin-warn">⚠ 会改动现有脚位分配；工具自动腾让，无需手工处理。取消勾选会对称撤销。</div></div>' +
    '<div class="info-strip"><div class="i">i</div><p>插件状态写进 <span class="mono">project.plugins</span>，随工程持久化。所有行为由 <span class="mono">plugins.json</span> 数据驱动，新增插件无需改 UI。</p></div>';
  return s;
}
async function togglePlugin(id) {
  id = id || "ledc";
  if (!S.sdk) { toast("请先完成项目身份", true); return; }
  var on = (S.pluginState.enabled || []).indexOf(id) >= 0;
  var r = await call("plugin_toggle", S.sdk, id, !on);
  if (!r || !r.ok) { toast("插件切换失败：" + ((r && r.error) || "未知"), true); return; }
  await loadWorkspace(S.sdk);
  var p = findPlugin(id);
  // 启用后自动选中该需求组，解锁的角色立刻可见；停用则清除相关选择
  if (!on && p && p.require_group) { S.selectedGroup = p.require_group; S.selectedRole = null; }
  if (on) { S.selectedGroup = null; S.selectedRole = null; }
  S.focusPin = null;
  render();
  toast((p ? (p.display_name || id) : id) + " 已" + (on ? "停用" : "启用"));
}

/* ---- 三视图工作区 ---- */
function viewPins() {
  var h = '<div class="concept"><b>需求组、约束栏、脚位图是同一批角色的三种视图</b>，不是包含关系：' +
    '<div class="chain"><span>需求组 · 按功能分组</span><i>同一批角色</i><span>约束栏 · 按合法脚数分档</span><i>同一批角色</i><span>脚位图 · 按物理位置</span></div>' +
    '选中其一，另外两处同步高亮。<button class="btn sm ghost ml-6" onclick="showHelp()">? 详细</button></div>';
  h += '<div class="ctxbar">' + (S.selectedRole
      ? '<span>当前正在配：<b>' + esc(roleName(S.selectedRole)) + '</b></span><span class="tag info mono">' + esc(S.selectedRole) + '</span>' +
        '<span class="muted">合法 ' + (roleMeta(S.selectedRole).allowed_pins || []).length + ' 脚 · 请在右栏按原理图选一只脚</span>'
      : (S.selectedGroup ? '<span>已选需求组：<b>' + esc(groupName(S.selectedGroup)) + '</b></span><span class="muted">中栏已筛出该组角色，右栏高亮其合法脚</span>'
        : '<span><b>尚未选择角色</b></span><span class="muted">在中栏点一个角色，再到右栏按原理图选脚</span>')) +
    '<span class="spacer"></span>' +
    '<button class="btn sm" onclick="savePins()">保存到工程</button>' +
    (S.selectedRole || S.selectedGroup ? '<button class="btn sm ghost" onclick="clearSel()">清除选择</button>' : '') + '</div>';
  h += '<div class="tri">' + colGroups() + colRoles() + colMatrix() + '</div>';
  return h;
}
function groupName(id) {
  (S.caps.demand_groups || []).forEach(function(g) { if (g.id === id) return g.display_name; });
  var p = null;
  (S.pluginState.plugins || []).forEach(function(x) { if (x.require_group === id) p = x; });
  return p ? (p.display_name || id) : id;
}
function groupMacs(g) {
  var out = [];
  (g.roles || []).forEach(function(rid) {
    // 组里既可以写 role_id（如 wheel.a），也可以直接写宏名（如 USB_5V，它没有 role_id）。
    var mac = S.caps.roles[rid] ? rid : findMacByRoleId(rid);
    if (mac && out.indexOf(mac) < 0) out.push(mac);
  });
  return out;
}
function findPlugin(id) {
  var found = null;
  (S.pluginState.plugins || []).forEach(function(p) { if (p.id === id) found = p; });
  return found;
}
function findPluginByGroup(gid) {
  var found = null;
  (S.pluginState.plugins || []).forEach(function(p) { if (p.require_group === gid) found = p; });
  return found;
}
function colGroups() {
  var s = '<div class="tri-col"><div class="tri-h"><b>① 需求组</b><span>按功能 · ' + (S.caps.demand_groups || []).length + ' 组</span></div><div class="tri-b">';
  var enabled = S.pluginState.enabled || [];
  (S.caps.demand_groups || []).forEach(function(g) {
    var plug = findPluginByGroup(g.id);
    var plugOn = plug && enabled.indexOf(plug.id) >= 0;
    // 不再按 v1 过滤：需求组必须覆盖全部真实需求，v1 只用于统计趋势。
    var macs = groupMacs(g).filter(function(m) { return !!S.caps.roles[m] && (roleMeta(m).allowed_pins || []).length > 0; });
    var done = macs.filter(function(m) { return !!pinOfRole(m); }).length;
    var cls = "grp" + (S.selectedGroup === g.id ? " on" : "") + (plug && !plugOn ? " plug-off" : "");
    s += '<div class="' + cls + '" role="button" tabindex="0" onclick="selGroup(\'' + g.id + '\')">' +
      '<div class="r1"><b>' + esc(g.display_name) + '</b><span class="tag ' + (macs.length && done === macs.length ? "ok" : "neutral") + '">' + done + '/' + macs.length + '</span></div>' +
      '<div class="r2">' + esc(g.note || "") + '</div>';
    if (plug) {
      s += '<div class="grp-plug-row"><span>' + (plugOn ? "插件已启用" : "插件未启用 · 勾选解锁") + '</span>' +
        '<button class="mini-switch ' + (plugOn ? "on" : "") + '" title="在需求组直接切换插件" ' +
        'onclick="event.stopPropagation();togglePlugin(\'' + plug.id + '\')">' + (plugOn ? "✓" : "+") + '</button></div>';
    }
    s += '</div>';
  });
  s += '<div class="matrix-note mt-md">带「插件」的组可直接在这里勾选，与步骤 3 的开关双向同步；取消会对称撤销新角色。</div></div></div>';
  return s;
}
function pinOfRole(mac) {
  for (var pin in S.assignments) if (S.assignments[pin] === mac) return pin;
  return null;
}
// 原理图上的网络名可能写成宏名(LED_R_PIN)、显示名(业务灯 R)或 role_id(led.r)，
// 搜索把三者与别名都算进去，工程师不必猜工具内部叫什么。
function roleMatches(mac, meta, q) {
  if (!q) return true;
  var hay = [mac, meta.display_name || "", meta.role_id || ""]
    .concat(meta.aliases || []).join(" ").toLowerCase();
  return hay.indexOf(q) >= 0;
}
function onRoleQuery(v) {
  S.roleQuery = String(v || "").trim().toLowerCase();
  renderMain();
  var el = $("role-search");
  if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); }
}
function clearRoleQuery() {
  S.roleQuery = "";
  renderMain();
}
// 「必需」标签必须跟随当前板型/选料/插件推导，而不是 options.json 的静态标记。
// 静态标记里 MODE_BLE_24G_PIN（单脚）为 true，选了双脚后仍显示必需，自相矛盾。
function isRequiredRole(mac) {
  var req = S.health && S.health.required;
  if (Array.isArray(req)) return req.indexOf(mac) >= 0;
  return !!(roleMeta(mac).required);  // 状态未加载时退回静态值
}
function colRoles() {
  var q = S.roleQuery || "";
  var all = [];
  for (var mac in S.caps.roles) {
    var m = S.caps.roles[mac] || {};
    // 不再按 v1 过滤：v1=false 的角色同样是原理图上的真实网络（LED_R、SENSOR_MOSI 等）。
    if (!(m.allowed_pins || []).length) continue;
    all.push(mac);
  }
  var visible;
  if (q) {
    // 搜索时跨全部角色，不受需求组筛选限制
    visible = all.filter(function(m) { return roleMatches(m, roleMeta(m), q); });
  } else if (S.selectedGroup) {
    var g = null;
    (S.caps.demand_groups || []).forEach(function(x) { if (x.id === S.selectedGroup) g = x; });
    var macs = g ? groupMacs(g) : [];
    visible = all.filter(function(m) { return macs.indexOf(m) >= 0; });
  } else {
    visible = all;
  }

  var buckets = {};
  TIERS.forEach(function(t) { buckets[t] = []; });
  visible.forEach(function(m) { buckets[tierOf((roleMeta(m).allowed_pins || []).length)].push(m); });

  var scope = q ? ("搜索「" + esc(S.roleQuery) + "」· " + visible.length + " 命中")
    : (S.selectedGroup ? "需求组筛选 · " + visible.length : "全部角色 " + visible.length);
  var s = '<div class="tri-col"><div class="tri-h"><b>② 约束栏</b><span>' + scope + '</span></div>' +
    '<div class="role-search-wrap">' +
      '<input id="role-search" class="role-search" type="search" placeholder="搜原理图网络名：LED_R / SENSOR_MOSI / led.r" ' +
        'value="' + esc(S.roleQuery) + '" oninput="onRoleQuery(this.value)">' +
      (q ? '<button class="role-search-clear" onclick="clearRoleQuery()" title="清除搜索">×</button>' : '') +
    '</div>' +
    '<div class="role-scope-bar">' +
      '<button class="chip ' + (!S.selectedGroup && !q ? "on" : "") + '" onclick="selGroup(null)">全部角色</button>' +
      (S.caps.demand_groups || []).map(function(g) {
        return '<button class="chip ' + (S.selectedGroup === g.id && !q ? "on" : "") + '" onclick="selGroup(\'' + g.id + '\')">' + esc(g.display_name) + '</button>';
      }).join("") +
    '</div>' +
    '<div class="tri-b">';
  TIERS.forEach(function(t) {
    if (!buckets[t].length) return;
    s += '<div class="tier-h">' + esc(t) + ' · ' + buckets[t].length + '</div>';
    buckets[t].sort().forEach(function(m) {
      var meta = roleMeta(m), ap = pinOfRole(m), n = (meta.allowed_pins || []).length;
      s += '<button class="role ' + (S.selectedRole === m ? "on" : "") + '" onclick="selRole(\'' + m + '\')">' +
        '<div class="r1"><b>' + esc(meta.display_name || m) + '</b>' + (isRequiredRole(m) ? '<span class="tag err">必需</span>' : '') + '</div>' +
        '<span class="mac">' + esc(m) + (meta.role_id ? ' · ' + esc(meta.role_id) : '') + '</span><div class="r2">' +
        (ap ? '<span class="tag ok">已配 ' + esc(ap) + '</span>' : '<span class="tag neutral">未配</span>') +
        '<span>' + n + ' 脚可选</span></div></button>';
    });
  });
  if (!visible.length) s += '<div class="matrix-note">没有匹配的角色。试试宏名（LED_R_PIN）或显示名，或点「全部角色」。</div>';
  return s + '</div></div>';
}
function activeRoles() {
  if (S.selectedRole) return [S.selectedRole];
  if (S.selectedGroup) {
    var g = null;
    (S.caps.demand_groups || []).forEach(function(x) { if (x.id === S.selectedGroup) g = x; });
    if (g) return groupMacs(g);
  }
  return [];
}
function getPinRow(pin) {
  var pkg = (S.pinmap && S.pinmap.package) || [], internal = (S.pinmap && S.pinmap.internal) || [];
  for (var i = 0; i < pkg.length; i++) if (pkg[i].name === pin) return pkg[i];
  for (var j = 0; j < internal.length; j++) if (internal[j].name === pin) return internal[j];
  return null;
}
function getPinState(pin, role) {
  var row = getPinRow(pin);
  if (!row) return { state: "unknown", reason: "未知脚" };
  if (row.locked) return { state: "locked", reason: row.desc || "锁定" };
  var allowed = roleMeta(role).allowed_pins || [];
  if (allowed.indexOf(pin) < 0) return { state: "illegal", reason: "芯片不允许" };
  var occ = S.assignments[pin];
  if (occ === role) return { state: "own", reason: "本角色已占" };
  if (occ) return { state: "conflict", reason: "被 " + roleName(occ) + " 占用" };
  return { state: "ok", reason: "可配" };
}
function colMatrix() {
  var active = activeRoles(), allowed = {};
  active.forEach(function(m) { (roleMeta(m).allowed_pins || []).forEach(function(p) { allowed[p] = 1; }); });
  var s = '<div class="tri-col"><div class="tri-h"><b>③ 脚位图</b><span>32 封装脚 · 点绿格分配</span></div><div class="tri-b"><div class="pin-grid">';
  PIN_ROWS.forEach(function(row) {
    row.forEach(function(pin) {
      var st = "idle", label = "", click = "";
      if (!active.length) {
        if (S.assignments[pin]) label = shortName(S.assignments[pin]);
      } else if (!allowed[pin]) {
        st = "illegal";
      } else if (S.selectedRole) {
        var r = getPinState(pin, S.selectedRole);
        st = r.state;
        if (st === "own") label = "本角色";
        else if (st === "conflict") label = shortName(S.assignments[pin]);
        if (st === "ok" || st === "own" || st === "conflict") click = "onPinClick('" + pin + "')";
      } else {
        st = S.assignments[pin] ? "conflict" : "ok";
        if (S.assignments[pin]) label = shortName(S.assignments[pin]);
        click = "onPinClick('" + pin + "')";
      }
      var focusCls = S.focusPin === pin ? " focus" : "";
      s += '<button class="pin ' + st + focusCls + '" onclick="' + (click || "void(0)") + '" title="' + esc(pin) + (label ? ' · ' + esc(label) : '') + '">' +
        esc(pin) + (label ? '<small>' + esc(label) + '</small>' : '') + '</button>';
    });
  });
  s += '</div><div class="legend"><span><i class="lok"></i>可配</span>' +
    '<span><i class="lown"></i>本角色已占</span>' +
    '<span><i class="lconflict"></i>被其他角色占</span>' +
    '<span><i class="lillegal"></i>不合法 / 保留</span></div>';
  s += '<div class="matrix-note">' + (S.selectedRole
      ? '点击绿格把 <b>' + esc(S.selectedRole) + '</b> 分配到该脚；点深绿格取消，点黄格覆盖。'
      : (S.selectedGroup ? '高亮的是「' + esc(groupName(S.selectedGroup)) + '」全组角色的合法脚；再点中栏某角色可收窄到单角色。' : '先选组或角色，这里才会高亮可配范围 —— 避免盲点。')) + '</div></div></div>';
  return s;
}
function shortName(mac) {
  var n = roleName(mac);
  return n.length > 6 ? n.slice(0, 6) : n;
}
function selGroup(id) {
  S.selectedGroup = id || null;
  S.selectedRole = null;
  S.roleQuery = "";
  renderMain();
}
function selRole(mac) { S.selectedRole = mac; renderMain(); }
function clearSel() { S.selectedRole = null; S.selectedGroup = null; renderMain(); }
function onPinClick(pin) {
  var role = S.selectedRole;
  if (!role && S.selectedGroup) {
    toast("请先在约束栏点一个具体角色", true);
    return;
  }
  if (!role) return;
  var cur = S.assignments[pin];
  if (cur === role) {
    delete S.assignments[pin];
    S.removedRoles[role] = true;
    toast("已取消 " + pin + " 上的 " + role);
  } else {
    if (cur) S.removedRoles[cur] = true;
    for (var p in S.assignments) if (S.assignments[p] === role && p !== pin) delete S.assignments[p];
    S.assignments[pin] = role;
    delete S.removedRoles[role];
    toast("已把 " + role + " 配到 " + pin + (cur ? "（覆盖了原分配）" : ""));
  }
  S.dirty = true;
  render();
}
function jumpToPin() {
  var target = S.route === "new" ? 5 : 2;
  if (target <= S.maxDone + 1) { S.step = target; render(); }
  else toast("请先完成前面的步骤");
}
async function savePins() {
  if (!S.sdk) { toast("请先打开工程", true); return; }
  var assignments = {};
  for (var pin in S.assignments) {
    var role = S.assignments[pin];
    if (role) assignments[role] = pin;
  }
  (S.pinmap.package || []).forEach(function(row) {
    (row.assigned || []).forEach(function(r) {
      if (!(r in assignments) && !S.removedRoles[r]) assignments[r] = row.name;
    });
  });
  Object.keys(S.removedRoles).forEach(function(r) { assignments[r] = ""; });
  for (var r in S.removedRoles) {
    if (S.protectedRoles[r]) { toast(r + " 是必需/驱动引用，不能解除；可改到其它脚", true); return; }
  }
  var res = S.blankMode
    ? await call("blank_save", S.sdk, assignments)
    : await call("save_pinmap", S.sdk, assignments);
  if (!res || !res.ok) { toast("保存失败：" + ((res && res.error) || "未知"), true); return; }
  S.dirty = false;
  await loadWorkspace(S.sdk);
  render();
  toast("已保存（" + (res.changed || 0) + " 处改动）" + (res.status && res.status.complete === false ? " · 仍是草稿，可继续配脚" : ""));
}
async function fillRecommended() {
  if (!S.sdk) { toast("请先创建空白工程", true); return; }
  var r = await call("blank_fill_recommended", S.sdk);
  if (!r || !r.ok) { toast("按推荐配置失败：" + ((r && r.error) || "未知"), true); return; }
  await loadWorkspace(S.sdk);
  render();
  toast(r.message || "已整体套用 KC536 协调方案（可选动作）");
}

/* ---- 校验 / 预览 / 应用 ---- */
function diffFiles() {
  var f = ["user_config.h", "user_config.c", "board_features.h", "project.omcfg", "SE71M.uvprojx"];
  var on = (S.pluginState.enabled || []).indexOf("ledc") >= 0;
  if (on) f = f.concat(["ledc.c", "ledc.h", "ledc_mode.c", "ledc_mode.h"]);
  return f;
}
function diffBlock() {
  if (!S.previewed || !S.diff) {
    return '<div class="info-strip"><div class="i">i</div><p>尚未生成预览。预览只计算 <b>unified diff</b>，<b>不会写入任何文件</b>；确认后才在下一步写盘。</p></div>';
  }
  var h = '<div class="diff-files">';
  diffFiles().forEach(function(f) { h += '<span class="diff-file">projects/mouse_demo/' + esc(f) + '</span>'; });
  h += '</div><pre class="diff">' + escDiff(S.diff) + '</pre>';
  return h;
}
function hlDiffLine(line) {
  // 先分段着色再逐段转义，避免 HTML 注入；注释优先，其次字符串 / 预处理指令 / 脚号 / 数字
  var re = /(\/\/.*$)|("(?:[^"\\]|\\.)*")|(#\s*(?:define|include|pragma|if|ifdef|ifndef|endif|else|elif))|(\bP\d{2}\b)|(\b\d+\b)/g;
  var out = "", last = 0, m;
  while ((m = re.exec(line)) !== null) {
    out += esc(line.slice(last, m.index));
    var cls = m[1] ? "syn-com" : m[2] ? "syn-str" : m[3] ? "syn-kw" : "syn-num";
    out += '<span class="' + cls + '">' + esc(m[0]) + '</span>';
    last = re.lastIndex;
  }
  return out + esc(line.slice(last));
}
function escDiff(d) {
  var out = "";
  (d.diffs || []).forEach(function(item) {
    out += '<span class="meta">--- ' + esc(item.path || "") + '</span>\n';
    var lines = String(item.diff || "无内容变化").split("\n");
    lines.forEach(function(line) {
      var cls = /^\+/.test(line) ? "add" : (/^-/.test(line) ? "del" : "");
      var body = hlDiffLine(line);
      out += cls ? '<span class="' + cls + '">' + body + '</span>\n' : body + '\n';
    });
  });
  return out || "没有文件变化";
}
function viewValidate() {
  var h = healthView(), s = '<div class="section-title"><span class="n">1</span>校验结果</div>';
  if (h.complete && !h.errors) {
    s += '<div class="empty-ok">✓ 0 error · 0 warning · 必需脚齐全、无冲突，可以进入预览</div>';
  } else {
    (h.missingDetail || []).forEach(function(m) {
      var meta = S.caps.roles[m.role] || {};
      var allowed = meta.allowed_pins || [];
      s += '<div class="issue err"><div class="ic">!</div><div class="tx"><b>缺必需角色：' + esc(m.role ? roleName(m.role) : m.role) + '</b>' +
        '<p><span class="mono">' + esc(m.role) + '</span> · 合法脚 ' + allowed.length + ' 个，请按原理图选一只。这个角色未分配脚位，生成会被阻断。</p></div>' +
        '<button class="btn sm" onclick="fixRole(\'' + m.role + '\')">去修复 →</button></div>';
    });
    if (h.conflicts) s += '<div class="issue err"><div class="ic">!</div><div class="tx"><b>存在 ' + h.conflicts + ' 处脚位冲突</b><p>同一只脚被分配给多个角色，已在脚位图用黄色标出。</p></div><button class="btn sm" onclick="fixConflict()">去修复 →</button></div>';
    if (h.errors) s += '<div class="issue err"><div class="ic">!</div><div class="tx"><b>' + h.errors + ' 条校验错误</b><p>由后端校验器给出，定位到首个关联角色后修复。</p></div><button class="btn sm" onclick="fixIssue()">去修复 →</button></div>';
    if (!(h.missingDetail || []).length && !h.conflicts && !h.errors) s += '<div class="empty-ok">✓ 0 error · 0 warning</div>';
  }
  s += '<div class="section-title"><span class="n">2</span>生成预览（不写盘）</div>' +
    '<div class="row gap10 mb-md"><button class="btn primary sm" onclick="doPreview()">生成预览</button>' +
    (S.previewed ? '<span class="tag ok">✓ 已预览</span>' : '<span class="muted tiny">点这里才会放行「下一步」</span>') + '</div>' + diffBlock();
  return s;
}
function viewPreview() {
  return '<div class="row gap10 mb-md"><button class="btn primary sm" onclick="doPreview()">生成预览</button>' +
    (S.previewed ? '<span class="tag ok">✓ 已预览</span>' : '<span class="muted tiny">预览后才可进入应用</span>') + '</div>' + diffBlock();
}
function fixRole(mac, pin) {
  var target = S.route === "new" ? 5 : 2;
  S.step = target;
  S.maxDone = Math.max(S.maxDone, target - 1);
  S.selectedRole = mac || null; S.selectedGroup = null;
  S.focusPin = pin || null; S.view = "work";
  render();
  toast(mac ? "已定位到 " + roleName(mac) + (pin ? " · " + pin : "") : "已定位到脚位图");
}
function fixConflict() {
  var txt = ((S.health && S.health.conflicts) || []).join(" ");
  var m = txt.match(/P\d{2}/);
  var pin = m ? m[0] : null;
  fixRole(pin ? S.assignments[pin] : null, pin);
}
function fixIssue() {
  var it = null;
  (S.issues || []).forEach(function(x) { if (!it && (x.level === "error" || x.severity === "error")) it = x; });
  var mac = it && (it.role || it.macro || it.name);
  fixRole(mac && S.caps.roles[mac] ? mac : null, it && it.pin);
}
async function doPreview() {
  var r = await call("preview", S.sdk);
  if (!r) return;
  if (r.diffs === undefined && !r.ok) {
    toast("预览失败：" + (r.error || "草稿未补齐") + (r.hint ? "；" + r.hint : ""), true);
    return;
  }
  S.diff = r; S.previewed = true;
  render();
  toast("预览完成：" + (r.changed || 0) + " 个文件待写入（未写盘）");
}
function confirmBlock() {
  if (!S.confirming) return "";
  return '<div class="confirm-bar"><div class="cb-tx"><b>⚠ 最后确认</b>' +
    '<p>将写入 <span class="mono">' + diffFiles().length + ' 个文件</span>到 <span class="mono">' + esc(S.sdk) + '</span>。' +
    '写入走事务：先备份再落盘，失败自动回滚，成功后可用 manifest 回到写之前的状态。</p></div>' +
    '<div class="cb-acts"><button class="btn sm" onclick="cancelApply()">取消</button>' +
    '<button class="btn sm primary" onclick="doApply()">确认写入</button></div></div>';
}
function cancelApply() { S.confirming = false; render(); toast("已取消写入"); }
function viewApply() {
  var h = healthView();
  var s = '<div class="summary-box"><h4>写入前确认</h4>' +
    '<div class="summary-row"><span class="k">工程</span><b>' + esc(S.route === "new" ? S.form.name : S.sdk) + '</b></div>' +
    '<div class="summary-row"><span class="k">已配脚</span><b>' + h.assigned + ' / ' + h.total + '</b></div>' +
    '<div class="summary-row"><span class="k">缺必需 / 冲突</span><b class="' + (h.complete ? "ok" : "err") + '">' + h.missingCount + ' / ' + h.conflicts + '</b></div>' +
    '<div class="summary-row"><span class="k">功能插件</span><b>' + ((S.pluginState.enabled || []).indexOf("ledc") >= 0 ? "灯带 LEDC" : "无") + '</b></div>' +
    '<div class="summary-row"><span class="k">将变更文件</span><b>' + diffFiles().length + ' 个</b></div>' +
    '<div class="summary-row"><span class="k">安全网</span><b class="mono">.omcfg_bak_* / manifest.json</b></div></div>' +
    '<div class="info-strip"><div class="i">!</div><p>点击底部「' + (S.route === "new" ? "生成工程（写盘）" : "应用改动（写盘）") + '」后出现确认条，<b>在确认条点「确认写入」才会写盘</b>。建议写完后用 Keil 编译验证（预期 0 Error / 0 Warning）。</p></div>';
  return s + confirmBlock();
}
async function doApply() {
  if (!S.confirming) { S.confirming = true; render(); toast("请在上方确认条点「确认写入」"); return; }
  if (S.applying) return;
  S.applying = true;
  try {
    var method = S.route === "new" ? "blank_apply" : "apply";
    var r = await call(method, S.sdk);
    if (!r || !r.ok) { toast("应用失败：" + (r.error || "草稿未补齐") + (r.hint ? "；" + r.hint : ""), true); return; }
    S.applied = true; S.applyResult = r; S.view = "success"; S.dirty = false; S.confirming = false;
    render();
    toast("应用成功：已写入 " + (r.changed || 0) + " 个文件");
  } finally { S.applying = false; }
}

/* ==================== 步骤流转 ==================== */
// Windows 路径归一：把重复的 / 与 \ 折叠成单个 \，保留 UNC 的 \\ 前缀，去掉尾部斜杠。
// 这样手输 D:\work 与 D:\\work 会得到同一个目标路径，避免「必须写两个反斜杠」的错觉。
function normalizeDir(p) {
  var s = String(p == null ? "" : p).trim();
  if (!s) return "";
  var unc = /^[\\/]{2}[^\\/]/.test(s);
  s = s.replace(/[\\/]+/g, "\\");
  if (unc) s = "\\" + s;
  return s.replace(/\\+$/, "");
}
async function createBlank() {
  var name = S.form.name.trim(), out = normalizeDir(S.form.out), id = parseId(S.form.id);
  if (!name || !out || id === null) { toast("请补全项目名、输出目录与项目号", true); return false; }
  var target = out + "\\" + name;
  var r = await call("blank_new", name, target, S.form.customer || "BYC", parseInt(S.form.version, 10) || 1, id, S.form.ble || null);
  if (!r || !r.ok) { toast("创建失败：" + ((r && r.error) || "未知") + (r && r.hint ? "；" + r.hint : ""), true); return false; }
  S.sdk = r.sdk; S.blankMode = true;
  await loadWorkspace(S.sdk);
  toast(r.message || "空白工程已创建");
  return true;
}
async function initExisting() {
  var ok = await loadWorkspace(S.sdk);
  if (ok) { S.maxDone = Math.max(S.maxDone, 1); }
  else if (S.needsInit) toast("工程缺少 OMCFG 标记，请先在本页初始化");
  render();
}
async function doInitialize(configPath) {
  var r = await call("initialize", S.sdk, configPath);
  if (!r || !r.ok) { toast("初始化失败：" + ((r && r.error) || "未知"), true); return; }
  S.lastConfig = configPath;
  try { localStorage.setItem("omcfg.config:" + S.sdk, configPath); } catch (e) {}
  await loadWorkspace(S.sdk);
  render();
  toast("初始化完成，可进入下一步");
}
async function doInitializeDerived() {
  var r = await call("initialize_derived", S.sdk);
  if (!r || !r.ok) { toast("推导初始化失败：" + ((r && r.error) || "未知"), true); return; }
  await loadWorkspace(S.sdk);
  render();
  toast("已从工程现状生成配置并初始化");
}
async function nextStep() {
  var g = gate();
  if (g) { toast("✕ " + g, true); render(); return; }
  S.busy = true; renderAction();
  try {
    var last = S.step === operations().length;
    if (last) { await doApply(); return; }
    if (S.route === "new") {
      if (S.step === 1 && !S.sdk) { if (!(await createBlank())) return; }
      if (S.step === 5) await savePins();
      if (S.step === 6) S.previewed = false;
    } else {
      if (S.step === 2) await savePins();
      if (S.step === 3) S.previewed = false;
    }
    S.maxDone = Math.max(S.maxDone, S.step);
    S.step++;
    render();
  } finally {
    S.busy = false;
    if (S.view !== "success") renderAction();
  }
}
function prevStep() {
  if (S.step <= 1) return;
  S.step--;
  S.previewed = false; S.confirming = false;
  render();
}
function saveDraft() { toast("草稿已保存（blank_save / save_pinmap 由「保存到工程」执行）"); }
function gotoStep(n) {
  if (n > S.maxDone + 1) { toast("请先完成前面的步骤"); return; }
  S.step = n; S.view = "work"; S.confirming = false; render();
}
function startRoute(route) {
  S.route = route; S.step = 1; S.maxDone = 0; S.view = "work";
  S.sdk = ""; S.blankMode = false; S.needsInit = null;
  S.config = null; S.pinmap = null; S.issues = []; S.health = null;
  S.assignments = {}; S.removedRoles = {}; S.protectedRoles = {};
  S.selectedRole = null; S.selectedGroup = null;
  S.diff = null; S.previewed = false; S.applied = false; S.applyResult = null;
  S.confirming = false; S.applying = false; S.focusPin = null;
  S.dirty = false; S.busy = false;
  $("start").classList.add("hidden");
  $("workbench").classList.remove("hidden");
  render();
  if (route === "new") initOptions();
  else {
    var saved = "";
    try { saved = localStorage.getItem("omcfg.sdk") || ""; } catch (e) {}
    if (saved && $("sdk")) $("sdk").value = saved;
  }
}
function goStart() {
  $("workbench").classList.add("hidden");
  $("start").classList.remove("hidden");
  renderRecent();
}
function openRecent(sdk) {
  startRoute("open");
  if ($("sdk")) $("sdk").value = sdk;
  initExisting();
}
function recentChips() {
  var list = S.recent.length ? S.recent : loadRecent();
  if (!list.length) return '<span class="muted recent-empty">打开或新建工程后，这里会显示最近路径</span>';
  var h = "";
  list.forEach(function(sdk) {
    var name = sdk.split(/[\\/]/).filter(Boolean).pop() || sdk;
    h += '<span class="recent-chip"><button class="recent-item" onclick="openRecent(\'' + jsAttr(sdk) + '\')">' +
      '<span class="dot"></span><span><b>' + esc(name) + '</b><br><span class="tiny mono">' + esc(sdk) + '</span></span></button>' +
      '<button class="recent-del" title="从最近列表移除" onclick="removeRecent(\'' + jsAttr(sdk) + '\')">×</button></span>';
  });
  return h;
}
function renderRecent() {
  var el = $("recent-list");
  if (el) el.innerHTML = recentChips();
}
function renderSuccess() {
  var r = S.applyResult || {};
  var manifest = r.manifest || (r.data && r.data.manifest) || ".omcfg_bak_* 目录内的 manifest.json";
  $("main").innerHTML = '<div class="success"><div class="check">✓</div><h3>工程已生成</h3>' +
    '<p>配置已写入 SDK 副本。建议用 Keil 打开工程编译，预期 0 Error / 0 Warning。</p>' +
    '<div class="kv"><span class="k">写入文件</span><span class="v">' + (r.changed || 0) + ' 个</span>' +
    '<span class="k">固件版本</span><span class="v">' + (r.version != null ? "V" + r.version + "（iREAL_VERSION_ID / startup 已同步）" : "—") + '</span>' +
    '<span class="k">事务备份</span><span class="v">' + esc(manifest) + '</span>' +
    '<span class="k">回滚命令</span><span class="v">python -m omcfg rollback --manifest &lt;manifest.json&gt;</span>' +
    '<span class="k">工程目录</span><span class="v">' + esc(S.sdk) + '</span>' +
    '<span class="k">功能插件</span><span class="v">' + ((S.pluginState.enabled || []).indexOf("ledc") >= 0 ? "灯带 LEDC · 已启用" : "无") + '</span></div>' +
    '<div class="acts"><button class="btn primary" onclick="goStart()">返回启动页</button>' +
    '<button class="btn" onclick="startRoute(\'new\')">再建一个工程</button>' +
    '<button class="btn" onclick="openFolder()">打开目录</button></div></div>';
  $("aside").innerHTML = '<div class="help-box"><h5>下一步做什么</h5><p>用 Keil 打开 .uvprojx 编译验证。若需回到写盘前状态，用事务目录里的 manifest.json 执行 rollback。</p></div>';
  $("gate-wrap").innerHTML = "";
  $("cta-sub").textContent = "";
  $("btn-next").textContent = "返回启动页";
  $("btn-next").disabled = false;
  $("btn-next").onclick = goStart;
  $("btn-prev").disabled = true;
  $("btn-save").disabled = true;
}
async function openFolder() {
  var r = await call("open_folder", S.sdk);
  if (r && r.error) toast(String(r.error), true);
}

/* ==================== 启动 ==================== */
function init() {
  if (S._init) return;
  S._init = true;
  var sdk = $("sdk");
  if (sdk) {
    sdk.addEventListener("keydown", function(e) { if (e.key === "Enter") initExisting(); });
    sdk.addEventListener("change", function() { S.sdk = sdk.value.trim(); });
  }
  document.addEventListener("keydown", function(e) {
    var modalOpen = !$("modal").classList.contains("hidden");
    if (e.key === "Escape") {
      if (modalOpen) { hideHelp(); return; }
      if (S.confirming) { cancelApply(); return; }
    }
    if (e.key === "?" || (e.key === "/" && e.shiftKey)) { showHelp(); return; }
    if (modalOpen) return;
    if (e.ctrlKey || e.metaKey) {
      var k = e.key.toLowerCase();
      if (k === "s") { e.preventDefault(); savePins(); return; }
      if (k === "p") { e.preventDefault(); doPreview(); return; }
    }
    if (e.altKey && e.key === "ArrowRight") { e.preventDefault(); nextStep(); return; }
    if (e.altKey && e.key === "ArrowLeft") { e.preventDefault(); prevStep(); }
  });
  loadRecent();
  renderRecent();
}
window.addEventListener("pywebviewready", init);
document.addEventListener("DOMContentLoaded", init);

/* ==================== 自动填表（可视化） ==================== */
var AF = { projects: [], selected: "", timer: null, running: false };
function openAutofill() {
  $("start").classList.add("hidden");
  $("workbench").classList.add("hidden");
  $("autofill").classList.remove("hidden");
  var last = "";
  try { last = localStorage.getItem("omcfg.autofill.root") || ""; } catch (e) {}
  if (last && $("af-root")) $("af-root").value = last;
  var out = "";
  try { out = localStorage.getItem("omcfg.autofill.out") || ""; } catch (e) {}
  if (out && $("af-out")) $("af-out").value = out;
}
function closeAutofill() {
  if (AF.running) { toast("任务进行中，请等完成再退出", true); return; }
  $("autofill").classList.add("hidden");
  $("start").classList.remove("hidden");
  renderRecent();
}
async function afBrowseRoot() {
  var folder = await call("choose_folder", $("af-root").value.trim());
  if (folder) $("af-root").value = folder;
}
async function afBrowseOut() {
  var folder = await call("choose_folder", $("af-out").value.trim());
  if (folder) $("af-out").value = folder;
}
async function afScan() {
  var root = $("af-root").value.trim();
  if (!root) { toast("请先选择来源目录", true); return; }
  try { localStorage.setItem("omcfg.autofill.root", root); } catch (e) {}
  var r = await call("autofill_discover", root);
  if (!r || !r.ok) { toast((r && r.error) || "扫描失败", true); return; }
  AF.projects = r.projects || [];
  AF.selected = "";
  $("af-count").textContent = "共 " + (r.count || 0) + " 个";
  renderAfProjects();
  $("af-preview").innerHTML = '<p class="muted">选中工程后显示硬件事实</p>';
}
function renderAfProjects() {
  var box = $("af-projects");
  if (!AF.projects.length) { box.innerHTML = '<p class="muted">该目录下没有找到可填表工程（需含 projects/mouse_demo/periph/user_config.h）</p>'; return; }
  var html = "";
  for (var i = 0; i < AF.projects.length; i++) {
    var p = AF.projects[i];
    var err = p.error ? '<span class="err">· ' + esc(p.error) + '</span>' : "";
    var cls = "af-proj" + (AF.selected === p.header ? " sel" : "");
    html += '<button class="' + cls + '" onclick="afSelect(' + i + ')">' +
      '<div class="t">' + esc(p.name) +
      (p.style ? ' <span class="af-style">' + esc(p.style) + '</span>' : '') + '</div>' +
      '<div class="s">' + esc(p.project_name || '') + ' · 0x' + Number(p.id_low || 0).toString(16).toUpperCase() +
      ' · v' + esc(p.version || '?') + ' · ' + (p.pin_count || 0) + ' 脚' + err + '</div></button>';
  }
  box.innerHTML = html;
}
async function afSelect(idx) {
  var p = AF.projects[idx];
  if (!p) return;
  AF.selected = p.header;
  renderAfProjects();
  var r = await call("autofill_parse", p.header);
  if (!r || !r.ok) { $("af-preview").innerHTML = '<p class="err">' + esc((r && r.error) || "解析失败") + '</p>'; return; }
  var q = r.req;
  var sel = Object.keys(q.selections || {}).map(function(k) { return k + "=" + q.selections[k]; }).join(" · ") || "（无）";
  var rows = [
    ["工程", q.name + "  (0x" + Number(q.id_low || 0).toString(16).toUpperCase() + ")  v" + q.version + "  · " + q.style + " 风格"],
    ["客户 / BLE", q.customer + " / " + (q.ble_name || "自动生成")],
    ["脚位 / 极性", q.pin_count + " 脚 · " + q.polarity_count + " 只灯极性"],
    ["模式", (q.mode_dual ? "双脚三段" : "单脚") + (q.has_key_c0 ? " · 矩阵键 KEY_C0" : "") + (q.has_ledc ? " · 有LEDC脚" : "")],
    ["滚轮", q.wheel + " · 方向 CLOCK_" + q.dir_clock],
    ["灯效", (q.logo_label || q.logo || "-") + (q.led_effect_reason ? " · " + q.led_effect_reason : "")],
    ["指示灯", q.led_indicator + " · 2.4G灯 " + q.mode_24g_led],
    ["选料", sel],
  ];
  var html = '<div class="af-prev">';
  for (var i = 0; i < rows.length; i++) html += '<span class="k">' + esc(rows[i][0]) + '</span><span class="v">' + esc(rows[i][1]) + '</span>';
  html += '</div><p class="tiny" style="margin-top:10px">来源：' + esc(q.header) + '</p>';
  $("af-preview").innerHTML = html;
}
async function afStart() {
  if (!AF.selected) { toast("请先选择一个工程", true); return; }
  if (AF.running) { toast("任务已在进行中", true); return; }
  var out = $("af-out").value.trim();
  if (!out) { toast("请选择输出目录", true); return; }
  try { localStorage.setItem("omcfg.autofill.out", out); } catch (e) {}
  var keil = $("af-keil").checked;
  var r = await call("autofill_start", AF.selected, out, "", keil);
  if (!r || !r.ok) { toast((r && r.error) || "启动失败", true); return; }
  AF.running = true;
  $("af-start").disabled = true;
  $("af-log").textContent = "任务已启动…\n";
  AF.timer = setInterval(afPoll, 700);
}
async function afPoll() {
  var st = await call("autofill_status");
  if (!st) return;
  $("af-log").textContent = (st.lines || []).join("\n") + (st.running ? "\n…" : "");
  var log = $("af-log");
  log.scrollTop = log.scrollHeight;
  if (!st.running) {
    clearInterval(AF.timer); AF.timer = null; AF.running = false;
    $("af-start").disabled = false;
    var res = st.result || {};
    if (res.ok) toast("自动填表完成" + (res.keil ? " · Keil 0 Error/0 Warning" : ""));
    else toast((res.error || st.error || "失败"), true);
  }
}
