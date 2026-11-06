const $ = (id) => document.getElementById(id);
let busy = false;

function setStatus(text, error = false) {
  const node = $("status");
  node.textContent = text;
  node.classList.toggle("error", error);
}

function setBusy(value) {
  busy = value;
  for (const id of ["load", "check", "preview", "apply"]) $(id).disabled = value;
}

function renderPins(pins) {
  const body = $("pins");
  body.innerHTML = "";
  for (const item of pins || []) {
    const row = document.createElement("tr");
    for (const [value, cls] of [
      [item.role, ""], [item.pin, "pin"], [item.mode, ""], [item.pull, ""], [item.init, ""],
    ]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      if (cls) cell.className = cls;
      row.appendChild(cell);
    }
    body.appendChild(row);
  }
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

function render(data, action) {
  if (!data) return;
  if (data.error) {
    setStatus(data.error, true);
    return;
  }
  $("summary").textContent = data.summary || "";
  renderPins(data.pins);
  renderIssues(data.issues);
  if (data.diffs) renderDiff(data.diffs);
  const count = data.issues ? data.issues.length : 0;
  const message = data.message || `${action}完成；问题 ${count} 条`;
  setStatus(message, !data.ok);
}

async function run(method, action) {
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
    const data = await window.pywebview.api[method](sdk);
    render(data, action);
  } catch (error) {
    setStatus(String(error), true);
  } finally {
    setBusy(false);
  }
}

function init() {
  const saved = localStorage.getItem("omcfg.sdk") || "";
  $("sdk").value = saved;
  $("sdk").addEventListener("keydown", (event) => {
    if (event.key === "Enter") run("load", "打开");
  });
  $("load").addEventListener("click", () => run("load", "打开"));
  $("check").addEventListener("click", () => run("check", "检查"));
  $("preview").addEventListener("click", () => run("preview", "预览"));
  $("apply").addEventListener("click", () => {
    if (confirm("确认按 project.omcfg 写入 user_config.h/.c 与生成文件？")) run("apply", "应用");
  });
}

window.addEventListener("pywebviewready", init);
document.addEventListener("DOMContentLoaded", init);
