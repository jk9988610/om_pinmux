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

function renderPins(pins) {
  const body = $("pins");
  body.innerHTML = "";
  for (const item of pins || []) {
    const row = document.createElement("tr");
    for (const [value, cls] of [
      [item.role, ""], [item.pin, "pin"], [item.mode, ""], [item.pull, ""], [item.init, ""],
    ]) {
      if (cls === "pin") {
        const cell = document.createElement("td");
        const input = document.createElement("input");
        input.className = "pin-input";
        input.dataset.role = item.role;
        input.value = value;
        cell.appendChild(input);
        row.appendChild(cell);
        continue;
      }
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    }
    body.appendChild(row);
  }
}

function collectPins() {
  return Array.from(document.querySelectorAll("input.pin-input")).map((input) => ({
    role: input.dataset.role,
    pin: input.value.trim(),
  }));
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
  renderPins([]);
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
  renderPins(data.pins);
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
  $("check").addEventListener("click", () => run("check", "检查"));
  $("init").addEventListener("click", startInitialize);
  $("derive").addEventListener("click", startDerive);
  $("config").addEventListener("keydown", (event) => {
    if (event.key === "Enter") startInitialize();
  });
  $("save").addEventListener("click", () => run("save_pins", "保存引脚", collectPins()));
  $("preview").addEventListener("click", () => run("preview", "预览"));
  $("apply").addEventListener("click", () => {
    if (confirm("确认按 project.omcfg 写入 user_config.h/.c 与生成文件？")) run("apply", "应用");
  });
}

window.addEventListener("pywebviewready", init);
document.addEventListener("DOMContentLoaded", init);
