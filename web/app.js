"use strict";
/* OM6239 板级配置器 —— 单一状态机 + 按步骤调度的视图。
   所有校验/生成/事务都在后端 omcfg，本文件只提交 JSON 与展示结果。 */

var $ = function(id) { return document.getElementById(id); };

var STEPS = {
  new: [
    { t: "项目身份", d: "给工程一个名字和落点" },
    { t: "板型选项", d: "决定哪些角色是必需的" },
    { t: "功能插件", d: "按需勾选，随时可拔除" },
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

var S = {
  route: null, step: 1, maxDone: 0, view: "work",
  sdk: "", blankMode: false, needsInit: null,
  options: null, config: null, pinmap: null, issues: [],
  caps: { roles: {}, demand_groups: [], board_enums: {}, board_defaults: {} },
  pluginState: { plugins: [], enabled: [] },
  board: {}, boardChoice: {}, health: null,
  form: { name: "", id: "", customer: "BYC", version: "1", out: "" },
  assignments: {}, removedRoles: {}, protectedRoles: {},
  selectedRole: null, selectedGroup: null, focusPin: null,
  diff: null, previewed: false, applied: false, applyResult: null,
  confirming: false, recent: [],
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

/* 健康视图：优先用后端 blank_status，未就绪时从已加载数据推导 */
function healthView() {
  if (S.health && S.health.ok) {
    return {
      assigned: S.health.assigned || 0,
      total: S.health.total_roles || 0,
      missingCount: (S.health.missing || []).length,
      missingDetail: S.health.missing_detail || [],
      conflicts: (S.health.conflicts || []).length,
      errors: S.health.validate_errors || 0,
      warnings: S.health.validate_warnings || 0,
      complete: !!S.health.complete
    };
  }
  var roles = S.caps.roles || {};
  var assignedRoles = {};
  for (var pin in S.assignments) if (S.assignments[pin]) assignedRoles[S.assignments[pin]] = pin;
  var missing = [];
  var total = 0, assigned = 0;
  for (var mac in roles) {
    var m = roles[mac] || {};
    if (m.v1 === false) continue;
    total++;
    if (assignedRoles[mac]) assigned++;
    else if (m.required) missing.push({ role: mac, suggested: m.suggested_pin || "" });
  }
  var errors = (S.issues || []).filter(function(i) { return i.level === "error"; }).length;
  return {
    assigned: assigned, total: total, missingCount: missing.length, missingDetail: missing,
    conflicts: 0, errors: errors, warnings: (S.issues || []).length - errors,
    complete: missing.length === 0 && errors === 0
  };
}

/* ==================== 数据加载 ==================== */
async function loadWorkspace(sdk) {
  S.sdk = sdk || "";
  if (S.sdk) {
    try { localStorage.setItem("omcfg.sdk", S.sdk); } catch (e) {}
  }
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
  S.dirty = false;
  return true;
}

async function refreshHealth() {
  if (!S.sdk) return;
  var st = await call("blank_status", S.sdk);
  if (st && st.ok) { S.health = st; S.board = st.board || S.board; }
}

async function initOptions() {
  if (S.options) return;
  var o = await call("blank_options");
  if (!o || !o.ok) return;
  S.options = o;
  S.caps.board_enums = o.board_enums || S.caps.board_enums;
  S.caps.board_defaults = o.board_defaults || S.caps.board_defaults;
  S.boardChoice = Object.assign({}, S.caps.board_defaults || {});
  loadFormCache();
}

function loadFormCache() {
  try {
    var s = JSON.parse(localStorage.getItem(FORM_KEY) || "{}");
    S.form.name = s.name || "";
    S.form.id = s.id || "";
    S.form.customer = s.customer || "BYC";
    S.form.version = s.version || "1";
    S.form.out = s.out || "";
  } catch (e) {}
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
    ? "主线：身份 → 板型 → 插件 → 配脚 → 校验 → 生成。<br>可随时回退到已完成步骤。"
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
    '<div class="ring-lbl"><b>已配 ' + h.assigned + ' / ' + h.total + '</b>共 ' + countRequired() + ' 个必需角色<br>' + (h.complete ? "配置已完整" : "继续补齐即可生成") + '</div></div>';
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
function countRequired() {
  var n = 0;
  for (var mac in S.caps.roles) { var m = S.caps.roles[mac] || {}; if (m.v1 !== false && m.required) n++; }
  return n;
}
function helpForStep() {
  if (S.route === "new") {
    return [
      ["这一步在做什么", "给新工程一个身份与落点。工具会从内置 KC536 干净骨架复制一份，此时引脚全空 —— 这是正常状态。"],
      ["为什么先选板型", "板型决定哪些角色成为「必需」。例如双脚模式要求 MODE_24G/BLE 成对配置；RGB 灯效要求 LED_R/G/B 留脚。"],
      ["插件是可选的", "不勾选也能继续。勾选即注入文件、解锁角色、腾让冲突脚；取消会对称撤销。"],
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
    if (S.step === 4) {
      var h = healthView();
      if (h.conflicts) return "存在 " + h.conflicts + " 处脚位冲突，请先在脚位图化解";
      if (h.missingCount) return "还差 " + h.missingCount + " 个必需脚，补齐后才能进入校验";
    }
    if (S.step === 5 && !S.previewed) return "请先点「生成预览」查看将变更的文件";
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
  $("btn-save").disabled = !(S.sdk && (S.route === "new" ? S.step >= 4 : S.step === 2));
  var labelsNew = ["下一步：设置板型 →", "下一步：选择插件 →", "下一步：分配引脚 →", "下一步：校验与预览 →", "下一步：生成应用 →", "生成工程（写盘）"];
  var labelsOpen = ["下一步：检查与调整 →", "下一步：预览 diff →", "下一步：应用 →", "应用改动（写盘）"];
  var btn = $("btn-next");
  btn.onclick = nextStep;
  btn.textContent = S.route === "new" ? labelsNew[S.step - 1] : labelsOpen[S.step - 1];
  btn.disabled = !!g || S.busy;
  $("cta-sub").textContent = g ? "" : (last ? "确认后写入文件，可用 manifest 回滚" : st[Math.min(S.step, st.length - 1)].t + " 完成后进入下一步");
  $("gate-wrap").innerHTML = g ? '<div class="gate-msg">⚠ ' + esc(g) + '</div>' : "";
}

/* ==================== 步骤视图 ==================== */
function renderMain() {
  var body = "";
  if (S.route === "new") {
    if (S.step === 1) body = viewIdentity();
    else if (S.step === 2) body = viewBoard();
    else if (S.step === 3) body = viewPlugin();
    else if (S.step === 4) body = viewPins();
    else if (S.step === 5) body = viewValidate();
    else if (S.step === 6) body = viewApply();
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
    "板型是「需求清单的来源」：不同的模式/灯效/滚轮选项决定哪些角色必须配脚。",
    "按需启用功能插件。勾选即注入文件、解锁角色、腾让冲突脚；不勾选也能继续。",
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
  var saved = "";
  try { saved = localStorage.getItem("omcfg.sdk") || ""; } catch (e) {}
  if (saved) {
    var name = saved.split(/[\\/]/).filter(Boolean).pop() || saved;
    s += '<div class="recent-row"><button class="recent-item" onclick="openRecent(\'' + esc(saved) + '\')">' +
      '<span class="dot"></span><span><b>' + esc(name) + '</b><br><span class="tiny mono">' + esc(saved) + '</span></span></button></div>';
  }
  s += '<div class="section-title"><span class="n">2</span>初始化引导（仅当缺 OMCFG 标记时出现）</div>';
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
    field("客户名", "customer", "BYC", "", false) +
    field("版本", "version", "1", "", false) +
    '<div class="field full"><label>输出根目录</label><div class="input-row">' +
    '<input id="f-out" value="' + esc(S.form.out) + '" placeholder="E:\\work" oninput="syncForm()">' +
    '<button class="btn" onclick="browseOut()">浏览…</button></div>' +
    '<div class="fh">工程建在 &lt;输出根目录&gt;\\&lt;项目名&gt;，目标目录必须不存在</div></div></div>' +
    '<div class="info-strip"><div class="i">i</div><p><b>空白起步是刻意设计</b>：创建后已配 0 个脚、缺若干必需脚，这是正常状态。后续每配一个角色，健康卡的完成度就会上涨 —— 你随时知道还差多少。</p></div>' +
    (S.sdk ? '<div class="info-strip"><div class="i">✓</div><p>工程已创建：<span class="mono">' + esc(S.sdk) + '</span>。返回修改名字不会重建工程；若要换名字请关闭后重新新建。</p></div>' : "");
}
function syncForm() {
  ["name","id","customer","version","out"].forEach(function(k) {
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
  if (folder) { S.form.out = folder; var el = $("f-out"); if (el) el.value = folder; saveFormCache(); }
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
  var wheels = (S.caps.board_enums["sensor.bus"] ? ["ENCODER_PINMUX_SEL_IO_00_01","ENCODER_PINMUX_SEL_IO_20_21","SOFT_GPIO"] : ["ENCODER_PINMUX_SEL_IO_00_01","ENCODER_PINMUX_SEL_IO_20_21","SOFT_GPIO"]).map(function(v) {
    return [v, { ENCODER_PINMUX_SEL_IO_00_01:"编码器 P00/P01", ENCODER_PINMUX_SEL_IO_20_21:"编码器 P20/P21", SOFT_GPIO:"软件 GPIO" }[v] || v, v];
  });
  return opt("模式脚", "决定 MODE_24G / MODE_BLE 是否为必需脚", "mode_pins", modes, "选中后角色出现在约束栏，必需项计入「缺必需」。") +
    opt("灯效", "决定 LED_R/G/B 或灯带角色是否出现", "logo", logos, "KC536 源码无条件引用 LED_R/G/B，RGB 模式下这三只脚必须保留。") +
    opt("滚轮", "决定 WHEEL_A/B 的合法脚对", "wheel", wheels, "WHEEL_A/B 必须成对配置，归到「中约束」。") +
    '<div class="info-strip"><div class="i">i</div><p>板型选项<b>不直接改脚位</b>，只改「哪些角色必需」。想整体套用 KC536 协调方案，可在下一步点「一键按推荐配置」（可选，不是主线）。</p></div>';
}
function setBoardChoice(key, value) {
  if (!S.sdk) { toast("请先完成项目身份", true); return; }
  var old = S.boardChoice[key];
  S.boardChoice[key] = value;
  renderMain();
  (async function() {
    var r = await call("blank_set_board", S.sdk, {
      mode_pins: S.boardChoice.mode_pins, logo: S.boardChoice.logo, wheel: S.boardChoice.wheel
    });
    if (!r || !r.ok) {
      S.boardChoice[key] = old; renderMain();
      toast("板型保存失败：" + ((r && r.error) || "未知"), true);
      return;
    }
    await refreshHealth();
    renderAside();
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
        '<span class="muted">合法 ' + (roleMeta(S.selectedRole).allowed_pins || []).length + ' 脚 · 推荐 ' + esc(roleMeta(S.selectedRole).suggested_pin || "—") + '</span>'
      : (S.selectedGroup ? '<span>已选需求组：<b>' + esc(groupName(S.selectedGroup)) + '</b></span><span class="muted">中栏已筛出该组角色，右栏高亮其合法脚</span>'
        : '<span><b>尚未选择角色</b></span><span class="muted">先在左侧点需求组，或在中栏点一个角色</span>')) +
    '<span class="spacer"></span>' +
    '<button class="btn sm" onclick="savePins()">保存到工程</button>' +
    (S.blankMode ? '<button class="btn sm" onclick="fillRecommended()">一键按推荐配置（可选）</button>' : '') +
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
    var mac = findMacByRoleId(rid);
    if (mac) out.push(mac);
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
    var macs = groupMacs(g).filter(function(m) { return !!S.caps.roles[m] && roleMeta(m).v1 !== false; });
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
function colRoles() {
  var visible = [];
  for (var mac in S.caps.roles) {
    var m = S.caps.roles[mac] || {};
    if (m.v1 === false) continue;
    var allowed = m.allowed_pins || [];
    if (!allowed.length) continue;
    visible.push(mac);
  }
  if (S.selectedGroup) {
    var g = null;
    (S.caps.demand_groups || []).forEach(function(x) { if (x.id === S.selectedGroup) g = x; });
    if (g) {
      var macs = groupMacs(g);
      visible = visible.filter(function(m) { return macs.indexOf(m) >= 0; });
    }
  }
  var buckets = {};
  TIERS.forEach(function(t) { buckets[t] = []; });
  visible.forEach(function(m) { buckets[tierOf((roleMeta(m).allowed_pins || []).length)].push(m); });
  var s = '<div class="tri-col"><div class="tri-h"><b>② 约束栏</b><span>按合法脚数 · ' + (S.selectedGroup ? "已筛选" : "全量 " + visible.length) + '</span></div><div class="tri-b">';
  TIERS.forEach(function(t) {
    if (!buckets[t].length) return;
    s += '<div class="tier-h">' + esc(t) + ' · ' + buckets[t].length + '</div>';
    buckets[t].sort().forEach(function(m) {
      var meta = roleMeta(m), ap = pinOfRole(m), n = (meta.allowed_pins || []).length;
      s += '<button class="role ' + (S.selectedRole === m ? "on" : "") + '" onclick="selRole(\'' + m + '\')">' +
        '<div class="r1"><b>' + esc(meta.display_name || m) + '</b>' + (meta.required ? '<span class="tag err">必需</span>' : '') + '</div>' +
        '<span class="mac">' + esc(m) + '</span><div class="r2">' +
        (ap ? '<span class="tag ok">已配 ' + esc(ap) + '</span>' : '<span class="tag neutral">未配</span>') +
        '<span>' + n + ' 脚</span>' + (meta.suggested_pin ? '<span>推荐 ' + esc(meta.suggested_pin) + '</span>' : '') + '</div></button>';
    });
  });
  if (!visible.length) s += '<div class="matrix-note">无 v1 角色，请检查 role_capabilities 返回。</div>';
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
function selGroup(id) { S.selectedGroup = id; S.selectedRole = null; renderMain(); }
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
  var target = S.route === "new" ? 4 : 2;
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
function escDiff(d) {
  var out = "";
  (d.diffs || []).forEach(function(item) {
    out += "--- " + esc(item.path || "") + "\n";
    var lines = String(item.diff || "无内容变化").split("\n");
    lines.forEach(function(line) {
      var cls = /^\+/.test(line) ? "add" : (/^-/.test(line) ? "del" : "");
      out += cls ? '<span class="' + cls + '">' + esc(line) + '</span>\n' : esc(line) + '\n';
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
      s += '<div class="issue err"><div class="ic">!</div><div class="tx"><b>缺必需角色：' + esc(m.role ? roleName(m.role) : m.role) + '</b>' +
        '<p><span class="mono">' + esc(m.role) + '</span> · 推荐 ' + esc(m.suggested || "—") + '。这个角色未分配脚位，生成会被阻断。</p></div>' +
        '<button class="btn sm" onclick="fixRole(\'' + m.role + '\',\'' + esc(m.suggested || "") + '\')">去修复 →</button></div>';
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
  var target = S.route === "new" ? 4 : 2;
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
function viewApply() {
  var h = healthView();
  return '<div class="summary-box"><h4>写入前确认</h4>' +
    '<div class="summary-row"><span class="k">工程</span><b>' + esc(S.route === "new" ? S.form.name : S.sdk) + '</b></div>' +
    '<div class="summary-row"><span class="k">已配脚</span><b>' + h.assigned + ' / ' + h.total + '</b></div>' +
    '<div class="summary-row"><span class="k">缺必需 / 冲突</span><b class="' + (h.complete ? "ok" : "err") + '">' + h.missingCount + ' / ' + h.conflicts + '</b></div>' +
    '<div class="summary-row"><span class="k">功能插件</span><b>' + ((S.pluginState.enabled || []).indexOf("ledc") >= 0 ? "灯带 LEDC" : "无") + '</b></div>' +
    '<div class="summary-row"><span class="k">将变更文件</span><b>' + diffFiles().length + ' 个</b></div>' +
    '<div class="summary-row"><span class="k">安全网</span><b class="mono">.omcfg_bak_* / manifest.json</b></div></div>' +
    '<div class="info-strip"><div class="i">!</div><p>点击底部「' + (S.route === "new" ? "生成工程（写盘）" : "应用改动（写盘）") + '」才真正写入。写入走事务：先备份再落盘，失败自动回滚；成功后可用 manifest 回到写之前的状态。<b>建议用 Keil 编译验证（预期 0 Error / 0 Warning）</b>。</p></div>';
}
async function doApply() {
  if (!window.confirm("确认按当前配置写入 user_config.h/.c 等文件？可用 manifest 回滚。")) return;
  var method = S.route === "new" ? "blank_apply" : "apply";
  var r = await call(method, S.sdk);
  if (!r || !r.ok) { toast("应用失败：" + (r.error || "草稿未补齐") + (r.hint ? "；" + r.hint : ""), true); return; }
  S.applied = true; S.applyResult = r; S.view = "success"; S.dirty = false;
  render();
  toast("应用成功：已写入 " + (r.changed || 0) + " 个文件");
}

/* ==================== 步骤流转 ==================== */
async function createBlank() {
  var name = S.form.name.trim(), out = S.form.out.trim(), id = parseId(S.form.id);
  if (!name || !out || id === null) { toast("请补全项目名、输出目录与项目号", true); return false; }
  var target = out.replace(/[\\/]+$/, "") + "\\" + name;
  var r = await call("blank_new", name, target, S.form.customer || "BYC", parseInt(S.form.version, 10) || 1, id);
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
      if (S.step === 4) await savePins();
      if (S.step === 5) S.previewed = false;
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
  S.previewed = false;
  render();
}
function saveDraft() { toast("草稿已保存（blank_save / save_pinmap 由「保存到工程」执行）"); }
function gotoStep(n) {
  if (n > S.maxDone + 1) { toast("请先完成前面的步骤"); return; }
  S.step = n; S.view = "work"; render();
}
function startRoute(route) {
  S.route = route; S.step = 1; S.maxDone = 0; S.view = "work";
  S.sdk = ""; S.blankMode = false; S.needsInit = null;
  S.config = null; S.pinmap = null; S.issues = []; S.health = null;
  S.assignments = {}; S.removedRoles = {}; S.protectedRoles = {};
  S.selectedRole = null; S.selectedGroup = null;
  S.diff = null; S.previewed = false; S.applied = false; S.applyResult = null;
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
function renderRecent() {
  var el = $("recent-list");
  if (!el) return;
  var saved = "";
  try { saved = localStorage.getItem("omcfg.sdk") || ""; } catch (e) {}
  if (!saved) {
    el.innerHTML = '<span class="muted recent-empty">打开或新建工程后，这里会显示最近路径</span>';
    return;
  }
  var name = saved.split(/[\\/]/).filter(Boolean).pop() || saved;
  el.innerHTML = '<button class="recent-item" onclick="openRecent(\'' + esc(saved).replace(/'/g, "\\'") + '\')">' +
    '<span class="dot"></span><span><b>' + esc(name) + '</b><br><span class="tiny mono">' + esc(saved) + '</span></span></button>';
}
function renderSuccess() {
  var r = S.applyResult || {};
  var manifest = r.manifest || (r.data && r.data.manifest) || ".omcfg_bak_* 目录内的 manifest.json";
  $("main").innerHTML = '<div class="success"><div class="check">✓</div><h3>工程已生成</h3>' +
    '<p>配置已写入 SDK 副本。建议用 Keil 打开工程编译，预期 0 Error / 0 Warning。</p>' +
    '<div class="kv"><span class="k">写入文件</span><span class="v">' + (r.changed || 0) + ' 个</span>' +
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
    if (e.key === "Escape" && !$("modal").classList.contains("hidden")) hideHelp();
  });
  renderRecent();
}
window.addEventListener("pywebviewready", init);
document.addEventListener("DOMContentLoaded", init);
