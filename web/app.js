const $ = (id) => document.getElementById(id);
let busy = false;
let editingAllowed = false;
let lastConfig = "";

function setStatus(text, error = false) {
  const node = $("status");
  node.textContent = text;
  node.classList.toggle("error", error);
}

function updateButtons() {
  for (const id of ["load", "check", "init", "derive"]) $(id).disabled = busy;
  for (const id of ["save", "preview", "apply"]) $(id).disabled = busy || !editingAllowed;
}

function setBusy(value) {
  busy = value;
  updateButtons();
}

function setEditing(value) {
  editingAllowed = value;
  updateButtons();
}

function showInit(show) {
  $("init-panel").classList.toggle("hidden", !show);
}

let currentPinmap = null;
let protectedRoles = new Set();

function label(role) {
  return role ? role.replace(/_PIN$/, "") : "";
}

function cell(text, className) {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  return td;
}

function renderPinmap(data) {
  currentPinmap = data || { package: [], internal: [], unassigned: [] };
  protectedRoles = new Set(currentPinmap.protected_roles || []);
  renderPackage(currentPinmap.package);
  renderInternal(currentPinmap.internal);
  renderUnassigned(currentPinmap.unassigned);
}

function renderPackage(rows) {
  const body = $("pins");
  body.innerHTML = "";
  for (const row of rows || []) {
    const tr = document.createElement("tr");
    tr.appendChild(cell(String(row.pkg)));
    tr.appendChild(cell(row.name, "pin"));
    tr.appendChild(cell(row.assigned.map(label).join(" / ") || "—"));
    if (row.special) {
      tr.appendChild(cell("—"));
      tr.appendChild(cell(row.desc));
    } else if (row.assigned.length > 1) {
      tr.appendChild(cell("—"));
      tr.appendChild(cell("多个功能共用此脚，只读"));
    } else {
      const td = document.createElement("td");
      const select = document.createElement("select");
      select.className = "pin-select";
      select.dataset.pin = row.name;
      select.dataset.assigned = row.assigned.join(",");
      const blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "未分配";
      select.appendChild(blank);
      for (const role of row.candidates || []) {
        const option = document.createElement("option");
        option.value = role;
        option.textContent = label(role);
        if (row.assigned.includes(role)) option.selected = true;
        select.appendChild(option);
      }
      select.disabled = row.locked;
      td.appendChild(select);
      tr.appendChild(td);
      const protectedRole = row.assigned.find((role) => protectedRoles.has(role));
      tr.appendChild(cell(protectedRole ? "必需/驱动引用：可移动，不可解除" : ""));
    }
    body.appendChild(tr);
  }
}

function renderInternal(rows) {
  const body = $("internal-pins");
  body.innerHTML = "";
  for (const row of rows || []) {
    const tr = document.createElement("tr");
    tr.appendChild(cell(row.name, "pin"));
    tr.appendChild(cell(row.desc));
    tr.appendChild(cell(row.assigned.map(label).join(" / ") || "—"));
    tr.appendChild(cell("保留脚，只读"));
    body.appendChild(tr);
  }
}

function renderUnassigned(roles) {
  const list = $("unassigned");
  list.innerHTML = "";
  if (!roles || !roles.length) {
    const li = document.createElement("li");
    li.textContent = "所有已知功能都已分配";
    list.appendChild(li);
    return;
  }
  for (const role of roles) {
    const li = document.createElement("li");
    li.textContent = label(role);
    list.appendChild(li);
  }
}

function collectPinmap() {
  const map = {};
  const selects = Array.from(document.querySelectorAll("select.pin-select"));
  for (const select of selects) {
    for (const role of (select.dataset.assigned || "").split(",").filter(Boolean)) {
      map[role] = "";
    }
  }
  const chosen = new Set(selects.map((item) => item.value).filter(Boolean));
  const seen = {};
  for (const select of selects) {
    const role = select.value;
    if (!role) {
      const old = (select.dataset.assigned || "").split(",").filter(Boolean);
      const kept = old.find((item) => protectedRoles.has(item) && !chosen.has(item));
      if (kept) {
        setStatus(`${label(kept)} 是必需/驱动引用，不能解除；可改到其它脚`, true);
        return null;
      }
      continue;
    }
    if (seen[role]) {
      setStatus(`功能 ${label(role)} 被选到多个脚，请先改回其中一个`, true);
      return null;
    }
    seen[role] = true;
    map[role] = select.dataset.pin;
  }
  return map;
}

function renderIssues(issues) {
  const list = $("issues");
  list.innerHTML = "";
  if (!issues || !issues.length) {
    const empty = document.createElement("li");
    empty.textContent = "无问题";
    list.appendChild(empty);
    return;
  }
  for (const issue of issues) {
    const li = document.createElement("li");
    li.className = issue.level;
    li.textContent = `[${issue.level}] ${issue.path}: ${issue.message}`;
    list.appendChild(li);
  }
}

function renderDiff(diffs) {
  $("diff").textContent = diffs && diffs.length
    ? diffs.map((item) => item.diff || `无内容变化: ${item.path}`).join("\n\n")
    : "没有文件变化";
}

function renderNeedsInit(data) {
  setEditing(false);
  showInit(true);
  $("init-hint").textContent = data.hint || "";
  const missing = $("init-missing");
  missing.innerHTML = "";
  for (const item of data.missing || []) {
    const li = document.createElement("li");
    li.className = "warning";
    li.textContent = item;
    missing.appendChild(li);
  }
  const options = $("config-options");
  options.innerHTML = "";
  const configInput = $("config");
  const savedKey = `omcfg.config:${data.sdk || ""}`;
  const saved = localStorage.getItem(savedKey) || "";
  // data.config 是初始化后写入 project.omcfg 的位置，不能当输入配置预填。
  const current = saved && saved !== data.config ? saved : (data.prefill || "");
  configInput.value = current;
  for (const item of data.configs || []) {
    const option = document.createElement("option");
    option.value = item.path;
    option.label = item.suggested ? `${item.name}（自动匹配）` : item.name;
    options.appendChild(option);
  }
  $("summary").textContent = "未初始化";
  renderPinmap(null);
  renderIssues([]);
  $("diff").textContent = "尚未初始化";
  const detail = data.hint ? `${data.error}；${data.hint}` : data.error;
  setStatus(detail || "工程尚未初始化", true);
}

function render(data, action) {
  if (!data) return;
  if (data.needs_init) {
    renderNeedsInit(data);
    return;
  }
  showInit(false);
  if (data.error) {
    setEditing(false);
    const detail = data.hint ? `${data.error}；${data.hint}` : data.error;
    setStatus(detail, true);
    return;
  }
  setEditing(Boolean(data.ok));
  if (action === "初始化" && data.ok && data.sdk && lastConfig) {
    localStorage.setItem(`omcfg.config:${data.sdk}`, lastConfig);
  }
  $("summary").textContent = data.summary || "";
  renderPinmap(data.pinmap);
  renderIssues(data.issues);
  renderDiff(data.diffs || []);
  const count = data.issues ? data.issues.length : 0;
  const message = data.message || `${action}完成；问题 ${count} 条`;
  setStatus(message, !data.ok);
}

async function run(method, action, payload) {
  if (busy) return;
  const sdk = $("sdk").value.trim();
  if (!sdk) {
    setStatus("请先填写 SDK 根目录", true);
    return;
  }
  if (!window.pywebview || !window.pywebview.api) {
    setStatus("pywebview 尚未就绪，请稍等或重启工具", true);
    return;
  }
  setBusy(true);
  setStatus(`${action}中...`);
  try {
    localStorage.setItem("omcfg.sdk", sdk);
    const data = payload === undefined
      ? await window.pywebview.api[method](sdk)
      : await window.pywebview.api[method](sdk, payload);
    render(data, action);
  } catch (error) {
    setStatus(String(error), true);
  } finally {
    setBusy(false);
  }
}

function startInitialize() {
  const sdk = $("sdk").value.trim();
  const config = $("config").value.trim();
  if (!sdk) {
    setStatus("请先填写 SDK 根目录", true);
    return;
  }
  if (!config) {
    setStatus("请先选择或填写一份 .omcfg 配置", true);
    return;
  }
  if (!confirm(`用以下配置初始化工程？\n${config}\n\n会安装 project.omcfg 并插入 OMCFG/USER CODE 标记，不改引脚正文。`)) {
    return;
  }
  lastConfig = config;
  run("initialize", "初始化", config);
}

function startDerive() {
  const sdk = $("sdk").value.trim();
  if (!sdk) {
    setStatus("请先填写 SDK 根目录", true);
    return;
  }
  const message =
    "从当前工程现状推导配置并初始化？\n"
    + "会读取 user_config.h/.c 的引脚、模式、上下拉，写入 project.omcfg 并插入标记；"
    + "不改引脚正文。";
  if (!confirm(message)) return;
  run("initialize_derived", "生成配置并初始化");
}

let initialized = false;

document.addEventListener("change", (event) => {
  const select = event.target;
  if (!select.classList || !select.classList.contains("pin-select") || !select.value) return;
  for (const other of document.querySelectorAll("select.pin-select")) {
    if (other !== select && other.value === select.value) other.value = "";
  }
});

function init() {
  if (initialized) return;
  initialized = true;
  setEditing(false);
  const saved = localStorage.getItem("omcfg.sdk") || "";
  $("sdk").value = saved;
  $("sdk").addEventListener("keydown", (event) => {
    if (event.key === "Enter") run("load", "打开");
  });
  $("load").addEventListener("click", () => run("load", "打开"));
  $("browse").addEventListener("click", async () => {
    if (!window.pywebview || !window.pywebview.api) {
      setStatus("pywebview 尚未就绪，请稍等或重启工具", true);
      return;
    }
    const current = $("sdk").value.trim();
    try {
      const folder = await window.pywebview.api.choose_folder(current);
      if (folder) {
        $("sdk").value = folder;
      }
    } catch (e) {
      setStatus(String(e), true);
    }
  });
  $("check").addEventListener("click", () => run("check", "检查"));
  $("init").addEventListener("click", startInitialize);
  $("derive").addEventListener("click", startDerive);
  $("config").addEventListener("keydown", (event) => {
    if (event.key === "Enter") startInitialize();
  });
  $("save").addEventListener("click", () => {
    const map = collectPinmap();
    if (map) run("save_pinmap", "保存引脚", map);
  });
  $("preview").addEventListener("click", () => run("preview", "预览"));
  $("apply").addEventListener("click", () => {
    if (confirm("确认按 project.omcfg 写入 user_config.h/.c 与生成文件？")) run("apply", "应用");
  });
}

window.addEventListener("pywebviewready", init);
document.addEventListener("DOMContentLoaded", init);

// ==================== 按角色配引脚（v1 验证版） ====================
(function() {
  "use strict";
  var DEMO_ROLES = ["LEDC_PIN", "KEY_R0_PIN"];
  var roleAllowedMap = {};
  var roleMetaMap = {};
  var demandGroups = [];
  var packageRows = [];
  var internalRows = [];
  var currentSelectedRole = null;
  var currentAssignments = {};
  var lastPinmap = null;

  function ensureUI() {
    if (document.getElementById("roles-panel")) return;
    if (!document.getElementById("toggle-roles")) {
      var bar = document.createElement("div");
      bar.id = "roles-bar";
      bar.style.cssText = "padding:8px 16px;background:#f5f5f5;border-bottom:1px solid #ddd;color:#222";
      bar.innerHTML = '<button id="toggle-roles" style="padding:6px 12px;color:#222">按角色配引脚</button>' +
        '<span id="roles-hint" style="margin-left:12px;color:#666;font-size:12px"></span>';
      document.body.insertBefore(bar, document.body.firstChild);
    }
    var panel = document.createElement("div");
    panel.id = "roles-panel";
    panel.style.cssText = "display:none;margin:12px;padding:12px;border:1px solid #ccc;border-radius:6px;background:#fafafa;color:#222";
    panel.innerHTML =
      '<div style="display:flex;gap:16px">' +
        '<aside id="role-list" style="width:440px;min-width:440px;max-height:640px;overflow-y:auto;border-right:1px solid #eee;padding-right:12px"></aside>' +
        '<main id="pin-matrix" style="flex:1;min-width:0"></main>' +
      '</div>' +
      '<div style="margin-top:8px;padding-top:8px;border-top:1px solid #eee">' +
        '<button id="save-roles" style="padding:6px 12px;background:#1976d2;color:white;border:none;border-radius:4px;cursor:pointer">保存到工程</button>' +
        '<span id="roles-save-hint" style="margin-left:12px;color:#666;font-size:12px"></span>' +
      '</div>';
    var status = document.getElementById("status");
    if (status && status.parentElement) {
      status.parentElement.insertBefore(panel, status.nextSibling);
    } else {
      document.body.appendChild(panel);
    }
    document.getElementById("toggle-roles").addEventListener("click", togglePanel);
    document.getElementById("save-roles").addEventListener("click", saveRoles);
  }

  async function togglePanel() {
    var panel = document.getElementById("roles-panel");
    var hint = document.getElementById("roles-hint");
    var visible = panel.style.display !== "none";
    panel.style.display = visible ? "none" : "block";
    if (visible) return;
    var sdk = document.getElementById("sdk").value.trim();
    if (!sdk) { hint.textContent = "请先在顶部填 SDK 路径"; return; }
    if (!window.pywebview || !window.pywebview.api) { hint.textContent = "pywebview 未就绪"; return; }
    hint.textContent = "加载中...";
    try {
      var data = await window.pywebview.api.load(sdk);
      var pinmap = (data && data.pinmap) || data;
      if (!pinmap || !pinmap.package) {
        hint.textContent = "加载失败: " + JSON.stringify((data && data.error) || "未知格式");
        return;
      }
      lastPinmap = Object.assign({}, pinmap, { sdk: sdk });
      packageRows = pinmap.package || [];
      internalRows = pinmap.internal || [];

      // 关键：用芯片全量能力表，不依赖工程里已声明的角色
      var caps = await window.pywebview.api.role_capabilities();
      var rolesMap = (caps && caps.roles) || {};

      roleAllowedMap = {};
      roleMetaMap = {};
      for (var mac in rolesMap) {
        roleAllowedMap[mac] = new Set(rolesMap[mac].allowed_pins || []);
        roleMetaMap[mac] = rolesMap[mac];
      }
      demandGroups = (caps && caps.demand_groups) || [];

      // 当前已分配：从 package 的 assigned 拿
      currentAssignments = {};
      for (var i = 0; i < packageRows.length; i++) {
        var row = packageRows[i];
        var as = row.assigned || [];
        for (var k = 0; k < as.length; k++) {
          currentAssignments[row.name] = as[k];
        }
      }

      // DEMO 角色如果不在工程里，也要能显示
      currentSelectedRole = null;
      renderAll();
      hint.textContent = "已加载 " + packageRows.length + " 脚 · 芯片角色 " + Object.keys(roleAllowedMap).length + " 个";
    } catch (e) {
      hint.textContent = "加载出错: " + e;
    }
  }

  function rebuildFromLastPinmap() {
    // 已废弃：数据构建逻辑移入 togglePanel
  }

  function renderAll() {
    try { ensureDemandContainer(); } catch (e) { console.error("ensureDemandContainer:", e); }
    try { renderDemandGroups(); } catch (e) { console.error("renderDemandGroups:", e); }
    try { renderRoleList(); } catch (e) { console.error("renderRoleList:", e); }
    try { renderPinMatrix(); } catch (e) { console.error("renderPinMatrix:", e); }
  }

  function ensureDemandContainer() {
    if (document.getElementById("demand-groups")) return;
    var roleList = document.getElementById("role-list");
    if (!roleList) return;
    var div = document.createElement("div");
    div.id = "demand-groups";
    roleList.parentElement.insertBefore(div, roleList);
  }

  function findMacByRoleId(rid) {
    for (var mac in roleMetaMap) {
      if (roleMetaMap[mac] && roleMetaMap[mac].role_id === rid) return mac;
    }
    return null;
  }

  function renderDemandGroups() {
    if (typeof demandGroups === "undefined" || !demandGroups) { demandGroups = []; }
    var el = document.getElementById("demand-groups");
    if (!el) return;
    el.innerHTML = "";
    if (typeof demandGroups === "undefined") demandGroups = [];
    if (!demandGroups || demandGroups.length === 0) { el.style.display = "none"; return; }
    el.style.display = "block";
    var title = document.createElement("div");
    title.style.cssText = "margin:10px 0 6px;font-size:12px;color:#333;font-weight:bold";
    title.textContent = "需求组 (" + demandGroups.length + ")";
    el.appendChild(title);
    for (var i = 0; i < demandGroups.length; i++) {
      var g = demandGroups[i];
      var macs = [];
      var configured = 0;
      for (var j = 0; j < g.roles.length; j++) {
        var mac = findMacByRoleId(g.roles[j]);
        if (!mac) continue;
        macs.push(mac);
        for (var p in currentAssignments) {
          if (currentAssignments[p] === mac) { configured++; break; }
        }
      }
      var card = document.createElement("div");
      card.style.cssText = "margin-bottom:6px;border:1px solid #ddd;border-radius:4px;background:white;color:#222";
      var head = document.createElement("div");
      head.style.cssText = "padding:6px 8px;cursor:pointer;font-size:12px;background:#eef4fa;color:#222;font-weight:bold;border-radius:4px 4px 0 0";
      head.textContent = "▶ " + g.display_name + " " + configured + "/" + macs.length;
      var body = document.createElement("div");
      body.style.cssText = "display:none;padding:4px 8px;color:#222";
      for (var k = 0; k < macs.length; k++) {
        var m = macs[k];
        var meta = roleMetaMap[m] || {};
        var n = roleAllowedMap[m] ? roleAllowedMap[m].size : 0;
        var ap = null;
        for (var p2 in currentAssignments) { if (currentAssignments[p2] === m) { ap = p2; break; } }
        var row = document.createElement("button");
        row.style.cssText = "display:block;width:100%;text-align:left;margin:2px 0;padding:4px 6px;border:none;background:#f9f9f9;cursor:pointer;font-size:11px;color:#222;border-radius:3px";
        var st = ap ? ("已配 " + ap) : (n + " 脚");
        row.textContent = (meta.display_name || m) + " (" + m + ") · " + st;
        row.onclick = (function(mm) { return function() { currentSelectedRole = mm; renderAll(); }; })(m);
        body.appendChild(row);
      }
      head.onclick = (function(b) { return function() { b.style.display = b.style.display === "none" ? "block" : "none"; }; })(body);
      card.appendChild(head);
      card.appendChild(body);
      el.appendChild(card);
    }
  }

  function renderRoleList() {
    if (typeof roleAllowedMap === "undefined" || !roleAllowedMap) { roleAllowedMap = {}; }
    if (typeof roleMetaMap === "undefined" || !roleMetaMap) { roleMetaMap = {}; }
    if (typeof currentAssignments === "undefined" || !currentAssignments) { currentAssignments = {}; }
    var el = document.getElementById("role-list");
    if (!el) { console.error("role-list 不存在"); return; }
    el.innerHTML = "";

    var groups = { "硬约束": [], "窄约束": [], "中约束": [], "宽约束": [], "无约束": [] };
    for (var mac in roleAllowedMap) {
      var meta = roleMetaMap[mac] || {};
      if (!meta.v1) continue;
      var n = roleAllowedMap[mac].size;
      if (n === 0) continue;
      var g;
      if (n === 1) g = "硬约束";
      else if (n <= 4) g = "窄约束";
      else if (n <= 10) g = "中约束";
      else if (n < 24) g = "宽约束";
      else g = "无约束";
      groups[g].push(mac);
    }

    var order = ["硬约束", "窄约束", "中约束", "宽约束", "无约束"];
    var total = 0;
    for (var gi = 0; gi < order.length; gi++) {
      var gname = order[gi];
      var items = groups[gname];
      if (!items || items.length === 0) continue;
      total += items.length;
      var header = document.createElement("div");
      header.style.cssText = "margin:10px 0 6px;font-size:11px;color:#555;font-weight:bold";
      header.textContent = gname + " (" + items.length + ")";
      el.appendChild(header);
      items.sort();
      for (var i = 0; i < items.length; i++) {
        var _roleBtn = makeRoleButton(items[i]);
        if (typeof isLedcRole === "function" && isLedcRole(items[i])
            && typeof shouldBlockLedc === "function" && shouldBlockLedc()) {
          _roleBtn.disabled = true;
          _roleBtn.textContent = _roleBtn.textContent + "（未启用）";
          _roleBtn.title = "需重新准备工作区并勾选「灯带」";
        }
        el.appendChild(_roleBtn);
      }
    }
    if (total === 0) {
      el.innerHTML = "<p style=\"color:#999\">无 v1 角色（检查 role_capabilities 返回）</p>";
    }
  }

  function makeRoleButton(role) {
    var allowed = roleAllowedMap[role] || new Set();
    var meta = roleMetaMap[role] || {};
    var assignedPin = null;
    for (var p in currentAssignments) {
      if (currentAssignments[p] === role) { assignedPin = p; break; }
    }
    var free = 0;
    allowed.forEach(function(pin) {
      if (!currentAssignments[pin]) free++;
    });

    var btn = document.createElement("button");
    var active = currentSelectedRole === role;
    btn.style.cssText = "display:block;width:100%;text-align:left;margin-bottom:6px;padding:10px;border:1px solid " +
      (active ? "#1976d2" : "#ddd") + ";border-radius:4px;background:" +
      (active ? "#e3f2fd" : "white") + ";cursor:pointer;font-size:13px;color:#222";

    var name = meta.display_name ? (meta.display_name + " (" + role + ")") : role;
    var status;
    if (assignedPin) {
      status = "已配 " + assignedPin + " · 空闲 " + free + "/" + allowed.size;
    } else {
      status = allowed.size + " 脚 · " + (free > 0 ? "空闲 " + free : "0 空闲（需覆盖）");
    }
    var warnColor = (free === 0 && !assignedPin) ? "#c62828" : "#666";
    btn.innerHTML = '<div style="font-weight:bold">' + name + '</div>' +
      '<small style="color:" + warnColor + "">' + status + '</small>';
    btn.onclick = (function(r) { return function() { currentSelectedRole = r; renderAll(); }; })(role);
    return btn;
  }

  function getPinRow(pin) {
    for (var i = 0; i < packageRows.length; i++) if (packageRows[i].name === pin) return packageRows[i];
    for (var j = 0; j < internalRows.length; j++) if (internalRows[j].name === pin) return internalRows[j];
    return null;
  }

  function getPinState(pin, role) {
    var row = getPinRow(pin);
    if (!row) return { state: "unknown", reason: "未知脚" };
    if (row.locked) return { state: "locked", reason: row.desc || "锁定" };
    var allowed = roleAllowedMap[role] || new Set();
    if (!allowed.has(pin)) return { state: "illegal", reason: "芯片不允许" };
    var occupant = currentAssignments[pin];
    if (occupant === role) return { state: "own", reason: "本角色已占" };
    if (occupant) return { state: "conflict", reason: "被 " + occupant + " 占用" };
    return { state: "ok", reason: "可配" };
  }

  var PIN_ROWS = [
    ["P00","P01","P02","P03","P04","P05","P06","P07"],
    ["P10","P11","P12","P13","P14","P15","P16","P17"],
    ["P20","P21","P22","P23","P24","P25","P26","P27"],
    ["P30","P31","P32","P33","P34","P35","P36","P37"]
  ];

  var STATE_STYLE = {
    ok:       "background:#4caf50;color:white;cursor:pointer",
    own:      "background:#2e7d32;color:white;cursor:pointer;font-weight:bold",
    conflict: "background:#ffc107;color:#333;cursor:pointer",
    illegal:  "background:#e0e0e0;color:#999;cursor:not-allowed",
    locked:   "background:#bdbdbd;color:#666;cursor:not-allowed",
    unknown:  "background:#f5f5f5;color:#ccc;cursor:not-allowed"
  };

  function renderPinMatrix() {
    var el = document.getElementById("pin-matrix");
    if (!currentSelectedRole) {
      el.innerHTML = '<p style="color:#999">请先在左侧选择角色</p>';
      return;
    }
    el.innerHTML = "";
    var grid = document.createElement("div");
    grid.style.cssText = "display:grid;grid-template-columns:repeat(8,1fr);gap:4px";
    for (var i = 0; i < PIN_ROWS.length; i++) {
      for (var j = 0; j < PIN_ROWS[i].length; j++) {
        var pin = PIN_ROWS[i][j];
        var st = getPinState(pin, currentSelectedRole);
        var btn = document.createElement("button");
        btn.textContent = pin;
        btn.style.cssText = "padding:14px 6px;border:none;border-radius:4px;font-size:12px;" +
          (STATE_STYLE[st.state] || "");
        btn.title = pin + " · " + st.reason;
        btn.disabled = (st.state === "illegal" || st.state === "locked" || st.state === "unknown");
        if (!btn.disabled) {
          btn.onclick = (function(p) { return function() { onPinClick(p); }; })(pin);
        }
        grid.appendChild(btn);
      }
    }
    el.appendChild(grid);
    var legend = document.createElement("div");
    legend.style.cssText = "margin-top:8px;font-size:11px;color:#666";
    legend.innerHTML = "绿=可配 · 深绿=本角色已占 · 黄=被其他角色占 · 灰=不合法/保留";
    el.appendChild(legend);
  }

  function isLedcRole(r) {
    if (!r) return false;
    return /^ledc\./i.test(r) || /^LEDC_/i.test(r);
  }

  function shouldBlockLedc() {
    var _wz = window.__omWizardState;
    if (!_wz) return false;
    if (!_wz.prepared) return false;
    return !_wz.ledcPrepared;
  }

  function onPinClick(pin) {
    if (!currentSelectedRole) return;
    if (isLedcRole(currentSelectedRole) && typeof shouldBlockLedc === "function" && shouldBlockLedc()) {
      alert("需要重新准备工作区并勾选「灯带」");
      return;
    }
    var cur = currentAssignments[pin];
    if (cur === currentSelectedRole) {
      if (!confirm("取消 " + pin + " 上的 " + currentSelectedRole + "?")) return;
      delete currentAssignments[pin];
    } else if (cur) {
      if (!confirm(pin + " 已被 " + cur + " 占用，覆盖为 " + currentSelectedRole + "?")) return;
      currentAssignments[pin] = currentSelectedRole;
    } else {
      currentAssignments[pin] = currentSelectedRole;
    }
    renderAll();
    document.getElementById("roles-save-hint").textContent = "已修改，点「保存到工程」生效";
  }

  async function saveRoles() {
    if (!lastPinmap || !lastPinmap.sdk) { alert("请先打开工程"); return; }
    if (!window.pywebview || !window.pywebview.api) { alert("pywebview 未就绪"); return; }
    var assignments = {};
    for (var pin in currentAssignments) {
      assignments[currentAssignments[pin]] = pin;
    }
    // 补齐不在 DEMO_ROLES 的其他角色（保持现状）
    for (var i = 0; i < packageRows.length; i++) {
      var as = packageRows[i].assigned || [];
      for (var k = 0; k < as.length; k++) {
        var r = as[k];
        if (!(r in assignments) && DEMO_ROLES.indexOf(r) === -1) {
          assignments[r] = packageRows[i].name;
        }
      }
    }
    try {
      var res = await window.pywebview.api.save_pinmap(lastPinmap.sdk, assignments);
      if (res && !res.error) {
        document.getElementById("roles-save-hint").textContent =
          "已保存 (" + (res.changed || 0) + " 改动) · 请去表格视图点「预览 diff」";
        if (typeof run === "function") {
          try { run("load", "打开"); } catch (e) {}
        }
      } else {
        alert("保存失败: " + ((res && res.error) || "未知"));
      }
    } catch (e) {
      alert("保存出错: " + e);
    }
  }

  function initRolesUI() { ensureUI(); }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initRolesUI);
  } else {
    initRolesUI();
  }
})();
// ==================== 新建工程向导 ====================
(function() {
  "use strict";

  var state = {
    workspace: null,
    templatePath: null,
    prepared: false,
    ledcPrepared: false,
    generated: null
  };
  window.__omWizardState = state;

  function $(id) { return document.getElementById(id); }

  var FORM_KEY = "om_pinmux.newproj";

  function loadFormState() {
    try {
      var s = JSON.parse(localStorage.getItem(FORM_KEY) || "{}");
      var setIf = function(id, v) { var el = $(id); if (el && !el.value && v) el.value = v; };
      setIf("np-tpl", s.tpl);
      setIf("np-id", s.id);
      setIf("np-name", s.name);
      setIf("np-out", s.out);
      setIf("np-consumer", s.consumer);
      setIf("np-version", s.version);
    } catch (e) { console.warn("loadFormState:", e); }
  }

  function saveFormState() {
    try {
      var s = {
        tpl: ($("np-tpl") || {}).value || "",
        id: ($("np-id") || {}).value || "",
        name: ($("np-name") || {}).value || "",
        out: ($("np-out") || {}).value || "",
        consumer: ($("np-consumer") || {}).value || "",
        version: ($("np-version") || {}).value || ""
      };
      localStorage.setItem(FORM_KEY, JSON.stringify(s));
    } catch (e) { console.warn("saveFormState:", e); }
  }

  function bindFormPersistence() {
    ["np-tpl", "np-id", "np-name", "np-out", "np-consumer", "np-version"].forEach(function(id) {
      var el = $(id);
      if (!el || el.dataset.persistBound) return;
      el.dataset.persistBound = "1";
      el.addEventListener("change", saveFormState);
      el.addEventListener("blur", saveFormState);
    });
  }

  function ensureWizard() {
    if ($("newproj-panel")) return;

    // 1. 顶部按钮
    var bar = $("roles-bar");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "roles-bar";
      bar.style.cssText = "padding:8px 16px;background:#f5f5f5;border-bottom:1px solid #ddd;color:#222";
      document.body.insertBefore(bar, document.body.firstChild);
    }
    if (!$("toggle-newproj")) {
      var btn = document.createElement("button");
      btn.id = "toggle-newproj";
      btn.textContent = "新建工程";
      btn.style.cssText = "padding:6px 12px;color:#222;margin-right:8px";
      btn.onclick = toggleWizard;
      bar.insertBefore(btn, bar.firstChild);
    }

    // 2. 面板
    var panel = document.createElement("div");
    panel.id = "newproj-panel";
    panel.style.cssText = "display:none;margin:12px;padding:12px;border:1px solid #ccc;border-radius:6px;background:#fafafa;color:#222;max-width:820px";
    panel.innerHTML =
      '<h3 style="margin:0 0 10px">新建工程</h3>' +
      '<table style="border-collapse:collapse;font-size:13px">' +
      '<tr><td style="padding:4px 8px 4px 0">模板路径</td>' +
      '<td><input id="np-tpl" style="width:520px;color:#222" placeholder="E:\\M_2026\\0_T\\software\\trunk\\SE71M_0023_KC536_V1_20260909"></td>' +
      '<td><button id="np-tpl-browse" style="color:#222">浏览</button></td></tr>' +
      '<tr><td style="padding:4px 8px 4px 0">项目 ID</td>' +
      '<td><input id="np-id" style="width:120px;color:#222" placeholder="0x0525"></td></tr>' +
      '<tr><td style="padding:4px 8px 4px 0">项目名</td>' +
      '<td><input id="np-name" style="width:180px;color:#222" placeholder="E606"></td></tr>' +
      '<tr><td style="padding:4px 8px 4px 0">客户名</td>' +
      '<td><input id="np-consumer" style="width:120px;color:#222" placeholder="BYC" value="BYC"></td></tr>' +
      '<tr><td style="padding:4px 8px 4px 0">版本号</td>' +
      '<td><input id="np-version" type="number" min="1" style="width:80px;color:#222" value="1"></td></tr>' +
      '<tr><td style="padding:4px 8px 4px 0">输出根目录</td>' +
      '<td><input id="np-out" style="width:520px;color:#222" placeholder="E:\\M_2026"></td>' +
      '<td><button id="np-out-browse" style="color:#222">浏览</button></td></tr>' +
      '</table>' +
      '<div style="margin-top:6px"><label style="color:#222"><input type="checkbox" id="module-ledc"> 灯带（LEDC）</label></div>' +
      '<div style="margin-top:10px">' +
      '<button id="np-prepare" style="padding:6px 14px;background:#1976d2;color:white;border:none;border-radius:4px;cursor:pointer">准备工作区</button>' +
      '<button id="np-generate" style="padding:6px 14px;margin-left:8px;background:#388e3c;color:white;border:none;border-radius:4px;cursor:pointer" disabled>生成工程</button>' +
      '<button id="np-open" style="padding:6px 14px;margin-left:8px;color:#222" disabled>打开输出目录</button>' +
      '</div>' +
      '<div id="np-status" style="margin-top:8px;font-size:12px;color:#555"></div>' +
      '<div id="np-workspace" style="margin-top:4px;font-size:12px;color:#333"></div>' +
      '<div id="np-result" style="margin-top:8px;font-size:12px;color:#333;white-space:pre-wrap"></div>';

    var statusDiv = $("status");
    if (statusDiv && statusDiv.parentElement) {
      statusDiv.parentElement.insertBefore(panel, statusDiv.nextSibling);
    } else {
      document.body.appendChild(panel);
    }

    $("np-tpl-browse").onclick = browseTemplate;
    $("np-out-browse").onclick = browseOutput;
    $("np-prepare").onclick = prepare;
    $("np-generate").onclick = generate;
    $("np-open").onclick = openTarget;
    loadFormState();
    bindFormPersistence();
  }

  function toggleWizard() {
    var panel = $("newproj-panel");
    if (!panel) return;
    panel.style.display = panel.style.display === "none" ? "block" : "none";
  }

  async function browseTemplate() {
    if (!window.pywebview || !window.pywebview.api) { setNPStatus("pywebview 未就绪", true); return; }
    try {
      var cur = $("np-tpl").value.trim();
      var folder = await window.pywebview.api.choose_folder(cur);
      if (folder) $("np-tpl").value = folder;
    } catch (e) { setNPStatus("选择失败: " + e, true); }
  }

  async function browseOutput() {
    if (!window.pywebview || !window.pywebview.api) { setNPStatus("pywebview 未就绪", true); return; }
    try {
      var cur = $("np-out").value.trim();
      var folder = await window.pywebview.api.choose_folder(cur);
      if (folder) $("np-out").value = folder;
    } catch (e) { setNPStatus("选择失败: " + e, true); }
  }

  function setNPStatus(msg, isErr) {
    var el = $("np-status");
    if (!el) return;
    el.style.color = isErr ? "#c62828" : "#555";
    el.textContent = msg;
  }

  async function prepare() {
    saveFormState();
    var tpl = $("np-tpl").value.trim();
    var id = $("np-id").value.trim();
    var name = $("np-name").value.trim();
    if (!tpl) { setNPStatus("请填模板路径", true); return; }
    if (!id) { setNPStatus("请填项目 ID", true); return; }
    if (!name) { setNPStatus("请填项目名", true); return; }
    if (!window.pywebview || !window.pywebview.api) { setNPStatus("pywebview 未就绪", true); return; }

    // 工作区路径
    var ws = "E:\\tmp\\newproj\\" + id.replace(/^0x/i, "") + "_" + name + "_ws";
    if (state.prepared && state.workspace === ws) {
      if (!confirm("工作区已准备，重新准备会丢失当前修改。继续？")) return;
      var cr = await window.pywebview.api.cleanup_workspace(ws);
      if (!cr.ok) { setNPStatus("清理旧工作区失败: " + (cr.error || ""), true); return; }
    } else if (state.prepared && state.workspace && state.workspace !== ws) {
      if (!confirm("切换工程将丢弃当前工作区 " + state.workspace + "，继续？")) return;
      await window.pywebview.api.cleanup_workspace(state.workspace);
    }

    setNPStatus("复制模板中...");
    try {
      var ledcChk = $("module-ledc");
      var mods = [];
      if (ledcChk && ledcChk.checked) mods.push("ledc");

      if (mods.length > 0) {
        var rm = await window.pywebview.api.prepare_workspace_with_modules(tpl, ws, mods);
        if (!rm.ok) { setNPStatus("准备失败: " + (rm.error || JSON.stringify(rm)), true); return; }
        state.ledcPrepared = !!(rm.modules && rm.modules.ledc && rm.modules.ledc.ok);
      } else {
        var r1 = await window.pywebview.api.prepare_workspace(tpl, ws);
        if (!r1.ok) { setNPStatus("复制失败: " + (r1.error || ""), true); return; }
        setNPStatus("初始化配置中...");
        var r2 = await window.pywebview.api.initialize_derived(ws);
        if (!r2.ok) { setNPStatus("初始化失败: " + (r2.error || JSON.stringify(r2)), true); return; }
        state.ledcPrepared = false;
      }

      state.workspace = ws;
      state.templatePath = tpl;
      state.prepared = true;
      state.generated = null;

      $("np-workspace").textContent = "工作区: " + ws;
      $("np-generate").disabled = false;
      $("np-open").disabled = true;
      $("np-result").textContent = "";
      setNPStatus("准备完成 · 已切到「按角色配引脚」模式，配完回来点「生成工程」");

      // 联动：填 sdk 输入框 + 打开配引脚面板
      var sdkInput = $("sdk");
      if (sdkInput) sdkInput.value = ws;
      var roleBtn = $("toggle-roles");
      if (roleBtn) {
        var rolesPanel = $("roles-panel");
        if (!rolesPanel || rolesPanel.style.display === "none") {
          roleBtn.click();
        } else {
          // 已打开，重新触发一次加载
          roleBtn.click();
          setTimeout(function() { roleBtn.click(); }, 100);
        }
      }
    } catch (e) {
      setNPStatus("异常: " + e, true);
    }
  }

  async function generate() {
    saveFormState();
    if (!state.prepared || !state.workspace) { setNPStatus("请先准备工作区", true); return; }
    var out = $("np-out").value.trim();
    var id = $("np-id").value.trim();
    var name = $("np-name").value.trim();
    var consumer = $("np-consumer").value.trim();
    var version = parseInt($("np-version").value, 10) || 1;
    if (!out) { setNPStatus("请填输出根目录", true); return; }
    if (!window.pywebview || !window.pywebview.api) { setNPStatus("pywebview 未就绪", true); return; }

    setNPStatus("生成中...");
    try {
      var r = await window.pywebview.api.generate_project_to_root(state.workspace, out, id, name, consumer, version);
      if (!r.ok) { setNPStatus("生成失败: " + (r.error || JSON.stringify(r)), true); return; }
      state.generated = r;
      var apply = r.apply || {};
      var lines = [
        "✓ 生成成功",
        "项目根: " + (r.project_root || ""),
        "目标: " + (r.target || ""),
        "changed: " + (r.changed_count || 0) + "  added: " + (r.added_count || 0),
        "apply: ok=" + apply.ok + " changed=" + (apply.changed || 0),
        "清理备份: " + (r.cleaned_backups || []).length + " 个"
      ];
      $("np-result").textContent = lines.join("\n");
      $("np-open").disabled = false;
      setNPStatus("生成完成");
    } catch (e) {
      setNPStatus("异常: " + e, true);
    }
  }

  async function openTarget() {
    if (!state.generated || !state.generated.project_root) return;
    try {
      await window.pywebview.api.open_folder(state.generated.project_root);
    } catch (e) {
      // 降级：显示路径让用户手抄
      alert("请手动打开: " + state.generated.project_root);
    }
  }

  function initUI() { ensureWizard(); }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initUI);
  } else {
    initUI();
  }
})();